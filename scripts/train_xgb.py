"""Train calibrated XGBoost models for C2.3 and C2.4 (spec section 11).

Pipeline:
1. Load all closed windows with outcomes from DB.
2. Compute extended features at each window_start (no temporal leakage).
3. Split chronologically (--since/--until/--train-until).
4. Fit XGBoost binary classifier for each threshold.
5. Wrap with CalibratedClassifierCV (isotonic, 5-fold) — spec D10.
6. Score on test. Log to MLflow. Save pickle.
7. Print comparison vs MVP-baseline + B1/B4 on the same test set.

Usage:
    uv run python scripts/train_xgb.py \\
        --since 2026-04-24 --until 2026-05-04 --train-until 2026-05-01
"""

from __future__ import annotations

import argparse
import asyncio
import pickle
from datetime import UTC, date, datetime
from pathlib import Path

import mlflow
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score
from xgboost import XGBClassifier

from trumporacle.config import get_settings
from trumporacle.evaluation.backtest import expected_calibration_error
from trumporacle.evaluation.backtest_report import (
    WindowRow,
    b4_calibrated_probs,
    bin_from_eco,
    fetch_predictions,
    fetch_windows_with_outcomes,
    split_train_test,
)
from trumporacle.features.extended import FEATURE_NAMES, fetch_extended_features
from trumporacle.storage.db import async_session_scope

THRESHOLDS = (3, 4)
MIN_TRAIN_POSITIVES = 5
MIN_TEST_POSITIVES = 1


def _parse_iso_date_utc(value: str) -> datetime:
    d = date.fromisoformat(value)
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


async def collect_features(since: datetime, until: datetime) -> tuple[list[WindowRow], np.ndarray]:
    """Fetch windows + compute extended features for each."""

    async with async_session_scope() as s:
        windows = await fetch_windows_with_outcomes(s, since=since, until=until)
        rows: list[list[float]] = []
        for w in windows:
            ext = await fetch_extended_features(s, w.window_start)
            rows.append(ext.to_array())
    return windows, np.asarray(rows, dtype=float)


async def fetch_baseline_scores(
    since: datetime,
    until: datetime,
    test_keys: list[tuple[datetime, datetime]],
    train: list[WindowRow],
) -> dict[str, dict[tuple[datetime, datetime], dict[str, float]]]:
    """Pull MVP predictions + compute B1/B4 calibrated for the same test set."""

    async with async_session_scope() as s:
        mvp_preds = await fetch_predictions(s, since=since, until=until)
    n_train = len(train)
    marginals = (
        {k: sum(1 for w in train if w.v_max >= k) / n_train for k in THRESHOLDS}
        if n_train
        else {k: 0.0 for k in THRESHOLDS}
    )
    b4_table = b4_calibrated_probs(train)

    out: dict[str, dict[tuple[datetime, datetime], dict[str, float]]] = {
        "B1": {},
        "B4": {},
        "mvp-baseline-b4soft-001": dict(mvp_preds.get("mvp-baseline-b4soft-001", {})),
    }
    return out, marginals, b4_table


def _baseline_probs(
    test_windows: list[WindowRow],
    marginals: dict[int, float],
    b4_table: dict[int, dict[int, float]],
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Return per-threshold B1 and B4 probability arrays aligned with ``test_windows``."""

    b1: dict[int, np.ndarray] = {}
    b4: dict[int, np.ndarray] = {}
    for k in THRESHOLDS:
        b1[k] = np.full(len(test_windows), marginals[k], dtype=float)
        b4[k] = np.asarray(
            [b4_table[k][bin_from_eco(w.eco_mean_6h)] for w in test_windows],
            dtype=float,
        )
    return b1, b4


def _mvp_probs(
    test_windows: list[WindowRow],
    mvp_by_window: dict[tuple[datetime, datetime], dict[str, float]],
) -> dict[int, np.ndarray | None]:
    """Pull MVP probs aligned to the test windows; ``None`` if MVP missing for any."""

    out: dict[int, np.ndarray | None] = {}
    for k in THRESHOLDS:
        col = f"c2_{k}_prob"
        vals: list[float] = []
        complete = True
        for w in test_windows:
            key = (w.window_start, w.window_end)
            preds = mvp_by_window.get(key)
            if preds is None or col not in preds:
                complete = False
                break
            vals.append(float(preds[col]))
        out[k] = np.asarray(vals, dtype=float) if complete else None
    return out


def _format_metrics(
    name: str, k: int, probs: np.ndarray, labels: np.ndarray
) -> tuple[str, float, float]:
    if len(np.unique(labels)) < 2 or len(probs) == 0:
        nan = float("nan")
        return f"{name:<24} C2.{k}  AUC-PR=  -    ECE=  -   (degenerate)", nan, nan
    auc = float(average_precision_score(labels, probs))
    ece = expected_calibration_error(probs, labels)
    return f"{name:<24} C2.{k}  AUC-PR={auc:.3f}  ECE={ece:.3f}", auc, ece


async def main(since: datetime, until: datetime, train_until: datetime) -> None:
    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("trumporacle-xgb")

    print(f"Loading windows {since} -> {until}, train_until={train_until}")
    windows, X = await collect_features(since, until)
    print(f"  fetched {len(windows)} windows, X shape={X.shape}")

    train_windows, test_windows = split_train_test(windows, train_until)
    train_idx = [i for i, w in enumerate(windows) if w.window_end <= train_until]
    test_idx = [i for i, w in enumerate(windows) if w.window_end > train_until]
    X_train, X_test = X[train_idx], X[test_idx]
    print(f"  train={len(train_idx)} test={len(test_idx)}")
    print()

    artifact_root = Path(settings.artifacts_dir) / "models"
    artifact_root.mkdir(parents=True, exist_ok=True)

    baselines, marginals, b4_table = await fetch_baseline_scores(
        since, until, [(w.window_start, w.window_end) for w in test_windows], train_windows
    )
    b1_probs, b4_probs = _baseline_probs(test_windows, marginals, b4_table)
    mvp_probs = _mvp_probs(test_windows, baselines["mvp-baseline-b4soft-001"])

    summary: list[str] = []
    for k in THRESHOLDS:
        labels = np.asarray([1 if w.v_max >= k else 0 for w in windows], dtype=int)
        y_train, y_test = labels[train_idx], labels[test_idx]

        train_pos = int(y_train.sum())
        test_pos = int(y_test.sum())
        if train_pos < MIN_TRAIN_POSITIVES or test_pos < MIN_TEST_POSITIVES:
            msg = (
                f"C2.{k}: skipped (train_pos={train_pos}, test_pos={test_pos}; "
                f"need >= {MIN_TRAIN_POSITIVES}/{MIN_TEST_POSITIVES})"
            )
            print(msg)
            summary.append(msg)
            continue

        with mlflow.start_run(run_name=f"c2_{k}_xgb_v1"):
            params = {
                "threshold_k": k,
                "n_estimators": 200,
                "max_depth": 4,
                "learning_rate": 0.1,
                "tree_method": "hist",
                "random_state": 42,
                "calibration": "isotonic_cv5",
                "n_features": X_train.shape[1],
                "n_train": int(X_train.shape[0]),
                "n_test": int(X_test.shape[0]),
                "train_pos_rate": float(y_train.mean()),
            }
            mlflow.log_params(params)

            base_clf = XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.1,
                objective="binary:logistic",
                tree_method="hist",
                random_state=42,
                eval_metric="logloss",
            )
            calibrated = CalibratedClassifierCV(base_clf, method="isotonic", cv=5)
            calibrated.fit(X_train, y_train)

            probs_xgb = calibrated.predict_proba(X_test)[:, 1]
            xgb_auc = float(average_precision_score(y_test, probs_xgb))
            xgb_ece = expected_calibration_error(probs_xgb, y_test)

            # Baseline scores
            b1_auc = float(average_precision_score(y_test, b1_probs[k]))
            b1_ece = expected_calibration_error(b1_probs[k], y_test)
            b4_auc = float(average_precision_score(y_test, b4_probs[k]))
            b4_ece = expected_calibration_error(b4_probs[k], y_test)

            mvp = mvp_probs[k]
            if mvp is not None and len(mvp) == len(y_test):
                mvp_auc = float(average_precision_score(y_test, mvp))
                mvp_ece = expected_calibration_error(mvp, y_test)
            else:
                mvp_auc = float("nan")
                mvp_ece = float("nan")

            metrics = {
                "test_auc_pr": xgb_auc,
                "test_ece": xgb_ece,
                "test_pos_rate": float(y_test.mean()),
                "baseline_b1_auc_pr": b1_auc,
                "baseline_b4_auc_pr": b4_auc,
                "baseline_mvp_auc_pr": mvp_auc,
                "delta_vs_mvp": xgb_auc - mvp_auc if not np.isnan(mvp_auc) else float("nan"),
                "delta_vs_b4": xgb_auc - b4_auc,
            }
            mlflow.log_metrics(metrics)

            artifact_path = artifact_root / f"c2_{k}_xgb_v1.pkl"
            with artifact_path.open("wb") as fh:
                pickle.dump(
                    {"model": calibrated, "feature_names": FEATURE_NAMES, "threshold_k": k},
                    fh,
                )
            mlflow.log_artifact(str(artifact_path))

            print(f"=== C2.{k} ===")
            print(f"  base_rate(train)={y_train.mean():.3f}  base_rate(test)={y_test.mean():.3f}")
            print(f"  XGB-cal           AUC-PR={xgb_auc:.3f}  ECE={xgb_ece:.3f}")
            print(f"  MVP-baseline      AUC-PR={mvp_auc:.3f}  ECE={mvp_ece:.3f}")
            print(f"  B4-calibrated     AUC-PR={b4_auc:.3f}  ECE={b4_ece:.3f}")
            print(f"  B1-marginal       AUC-PR={b1_auc:.3f}  ECE={b1_ece:.3f}")
            print(f"  delta XGB - MVP   = {xgb_auc - mvp_auc:+.3f}")
            print(f"  delta XGB - B4    = {xgb_auc - b4_auc:+.3f}")
            print(f"  saved -> {artifact_path}")
            print()
            summary.append(
                f"C2.{k}: XGB={xgb_auc:.3f}  MVP={mvp_auc:.3f}  B4={b4_auc:.3f}  "
                f"delta_mvp={xgb_auc - mvp_auc:+.3f}"
            )

    print("=== summary ===")
    for line in summary:
        print(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=_parse_iso_date_utc, required=True)
    parser.add_argument("--until", type=_parse_iso_date_utc, required=True)
    parser.add_argument("--train-until", type=_parse_iso_date_utc, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.since, args.until, args.train_until))
