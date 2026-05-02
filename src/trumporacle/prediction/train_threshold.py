"""Train XGBoost binary threshold models (C2.k)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow
import mlflow.xgboost
import numpy as np
import xgboost as xgb
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.model_selection import train_test_split

from trumporacle.config import get_settings
from trumporacle.prediction.calibration import apply_isotonic, fit_isotonic


def train_xgb_threshold(
    X: np.ndarray,
    y: np.ndarray,
    *,
    threshold_k: int,
    run_name: str | None = None,
) -> tuple[xgb.XGBClassifier, Any]:
    """Train XGBoost binary classifier for P(v_max >= k); calibrate on holdout."""

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

    X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, shuffle=False)
    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.8,
        eval_metric="logloss",
        tree_method="hist",
    )
    model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    raw_val = model.predict_proba(X_val)[:, 1]
    iso = fit_isotonic(raw_val, y_val)
    cal_val = apply_isotonic(iso, raw_val)
    ap = average_precision_score(y_val, cal_val)
    brier = brier_score_loss(y_val, cal_val)

    with mlflow.start_run(run_name=run_name or f"c2_{threshold_k}"):
        mlflow.log_param("threshold_k", threshold_k)
        mlflow.log_metric("val_average_precision", ap)
        mlflow.log_metric("val_brier", brier)
        mlflow.xgboost.log_model(model, artifact_path="xgboost")

    return model, iso


def save_artifacts(model: xgb.XGBClassifier, iso: Any, path: Path) -> None:
    """Persist model and isotonic calibrator to disk."""

    import pickle

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({"model": model, "isotonic": iso}, f)
