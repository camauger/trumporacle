"""Backtest report: predictions ⨝ outcomes + B1–B4 baselines (spec §10.3–10.5).

Pragmatic v1: AUC-PR (sklearn) + ECE (own bins) + MAE; no inferential stats.
B4 stays as a step rule on ecosystem 6h mean (returns 0/1) — calibrated B4
via empirical binning is a follow-up; the report surfaces ``ecosystem_n_posts``
so the reader knows when B4 is degenerate due to missing ecosystem data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.evaluation.backtest import auc_pr, expected_calibration_error

THRESHOLDS: tuple[int, ...] = (3, 4, 5, 6)


@dataclass(frozen=True)
class WindowRow:
    """One closed window with observed outcome and ecosystem context."""

    window_start: datetime
    window_end: datetime
    v_max: int
    n_posts: int
    had_jump: bool
    v_recent: float
    eco_mean_6h: float
    eco_n_6h: int


@dataclass(frozen=True)
class TargetMetrics:
    """Metrics for one prediction target on the test set."""

    target: str
    n: int
    auc_pr: float | None
    ece: float | None
    mae: float | None
    base_rate: float | None


@dataclass(frozen=True)
class ScoreSet:
    """All target metrics for one model or baseline."""

    name: str
    n_test: int
    metrics: list[TargetMetrics]


@dataclass(frozen=True)
class BacktestReport:
    """Top-level backtest output."""

    period_start: datetime
    period_end: datetime
    train_until: datetime
    n_windows_total: int
    n_windows_train: int
    n_windows_test: int
    ecosystem_posts_test: int
    score_sets: list[ScoreSet]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict."""

        return asdict(self)


async def fetch_windows_with_outcomes(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
) -> list[WindowRow]:
    """Outcomes joined with ecosystem 6h-mean at each ``window_start``."""

    result = await session.execute(
        text(
            """
            WITH ann AS (
                SELECT DISTINCT ON (item_id) item_id, valence_level AS v
                FROM valence_annotations
                ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
            )
            SELECT
                o.window_start AS window_start,
                o.window_end   AS window_end,
                o.v_max        AS v_max,
                o.n_posts      AS n_posts,
                o.had_jump     AS had_jump,
                COALESCE((o.targets_observed->>'v_recent')::float, 0.0) AS v_recent,
                COALESCE(eco.mu, 0.0) AS eco_mean_6h,
                COALESCE(eco.n, 0)    AS eco_n_6h
            FROM outcomes o
            LEFT JOIN LATERAL (
                SELECT COALESCE(AVG(ann.v)::float, 0.0) AS mu,
                       COUNT(*)::int AS n
                FROM ann
                JOIN items i      ON i.id = ann.item_id
                JOIN raw_items r  ON r.id = i.raw_item_id
                JOIN sources s    ON s.id = r.source_id
                WHERE r.published_at >  o.window_start - INTERVAL '6 hours'
                  AND r.published_at <= o.window_start
                  AND COALESCE(s.metadata->>'trump_primary', 'false') <> 'true'
            ) eco ON TRUE
            WHERE o.window_start >= :since AND o.window_end <= :until
            ORDER BY o.window_start ASC
            """
        ),
        {"since": since, "until": until},
    )
    rows = result.mappings().all()
    return [
        WindowRow(
            window_start=r["window_start"],
            window_end=r["window_end"],
            v_max=int(r["v_max"]),
            n_posts=int(r["n_posts"]),
            had_jump=bool(r["had_jump"]),
            v_recent=float(r["v_recent"]),
            eco_mean_6h=float(r["eco_mean_6h"]),
            eco_n_6h=int(r["eco_n_6h"]),
        )
        for r in rows
    ]


async def fetch_predictions(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
) -> dict[str, dict[tuple[datetime, datetime], dict[str, float]]]:
    """Return ``{model_version: {(ws, we): probs}}`` for the period."""

    result = await session.execute(
        text(
            """
            SELECT window_start, window_end, model_version,
                   c1_value, c2_3_prob, c2_4_prob, c2_5_prob, c2_6_prob,
                   c3_prob, c4_prob
            FROM predictions
            WHERE window_start >= :since AND window_end <= :until
            ORDER BY window_start ASC
            """
        ),
        {"since": since, "until": until},
    )
    by_model: dict[str, dict[tuple[datetime, datetime], dict[str, float]]] = {}
    for r in result.mappings().all():
        mv = str(r["model_version"])
        key = (r["window_start"], r["window_end"])
        by_model.setdefault(mv, {})[key] = {
            "c1_value": float(r["c1_value"]) if r["c1_value"] is not None else 0.0,
            "c2_3_prob": float(r["c2_3_prob"]) if r["c2_3_prob"] is not None else 0.0,
            "c2_4_prob": float(r["c2_4_prob"]) if r["c2_4_prob"] is not None else 0.0,
            "c2_5_prob": float(r["c2_5_prob"]) if r["c2_5_prob"] is not None else 0.0,
            "c2_6_prob": float(r["c2_6_prob"]) if r["c2_6_prob"] is not None else 0.0,
            "c3_prob": float(r["c3_prob"]) if r["c3_prob"] is not None else 0.0,
            "c4_prob": float(r["c4_prob"]) if r["c4_prob"] is not None else 0.0,
        }
    return by_model


def split_train_test(
    windows: list[WindowRow], train_until: datetime
) -> tuple[list[WindowRow], list[WindowRow]]:
    """Chronological split. Train = windows ending at/before ``train_until``."""

    train = [w for w in windows if w.window_end <= train_until]
    test = [w for w in windows if w.window_end > train_until]
    return train, test


@dataclass(frozen=True)
class B1Marginals:
    """All marginal rates B1 needs (one ``P`` per binary target)."""

    threshold_rates: dict[int, float]
    jump_rate: float
    posts_rate: float


def b1_marginals(train: list[WindowRow]) -> B1Marginals:
    """B1: marginal probabilities computed on the training subset."""

    n = len(train)
    if n == 0:
        return B1Marginals({k: 0.0 for k in THRESHOLDS}, 0.0, 0.0)
    return B1Marginals(
        threshold_rates={k: sum(1 for w in train if w.v_max >= k) / n for k in THRESHOLDS},
        jump_rate=sum(1 for w in train if w.had_jump) / n,
        posts_rate=sum(1 for w in train if w.n_posts > 0) / n,
    )


def baselines_for_test(
    train: list[WindowRow], test: list[WindowRow]
) -> dict[str, dict[tuple[datetime, datetime], dict[str, float]]]:
    """Synthesize B1/B2/B3/B4 probabilities per test window.

    - B1 covers all targets (training marginals).
    - B2/B3/B4 cover C2.k only; missing targets are reported as ``n=0`` downstream.
    - B3 uses ``v_max`` of the immediately preceding window in the merged
      chronological sequence; the very first test window falls back to B1 marginals.
    """

    m = b1_marginals(train)
    full_seq = sorted(train + test, key=lambda w: w.window_start)
    prev_vmax: dict[tuple[datetime, datetime], int | None] = {}
    last_vmax: int | None = None
    for w in full_seq:
        prev_vmax[(w.window_start, w.window_end)] = last_vmax
        last_vmax = w.v_max

    by_baseline: dict[str, dict[tuple[datetime, datetime], dict[str, float]]] = {
        "B1": {},
        "B2": {},
        "B3": {},
        "B4": {},
    }
    for w in test:
        key = (w.window_start, w.window_end)
        b1: dict[str, float] = {}
        b2: dict[str, float] = {}
        b3: dict[str, float] = {}
        b4: dict[str, float] = {}
        for k in THRESHOLDS:
            col = f"c2_{k}_prob"
            b1[col] = float(m.threshold_rates[k])
            b2[col] = 1.0 if w.v_recent >= float(k) else 0.0
            b4[col] = 1.0 if w.eco_mean_6h >= float(k) else 0.0
            prev = prev_vmax[key]
            b3[col] = float(m.threshold_rates[k]) if prev is None else (1.0 if prev >= k else 0.0)
        b1["c3_prob"] = m.jump_rate
        b1["c4_prob"] = m.posts_rate
        by_baseline["B1"][key] = b1
        by_baseline["B2"][key] = b2
        by_baseline["B3"][key] = b3
        by_baseline["B4"][key] = b4
    return by_baseline


def _safe_metric(probs: list[float], labels: list[int]) -> tuple[float | None, float | None]:
    """Return ``(auc_pr, ece)`` or ``(None, None)`` when the label set is degenerate."""

    if not probs or len(set(labels)) < 2:
        return None, None
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=int)
    return auc_pr(p, y), expected_calibration_error(p, y)


def compute_target_metrics(
    target: str,
    probs: list[float],
    labels: list[int],
) -> TargetMetrics:
    """AUC-PR + ECE for binary targets; MAE only for ``c1``."""

    if target == "c1":
        if not probs:
            return TargetMetrics("c1", 0, None, None, None, None)
        diffs = [abs(p - lab) for p, lab in zip(probs, labels, strict=True)]
        mae = float(sum(diffs) / len(diffs))
        return TargetMetrics(
            target="c1",
            n=len(probs),
            auc_pr=None,
            ece=None,
            mae=mae,
            base_rate=float(sum(labels) / len(labels)),
        )

    a, e = _safe_metric(probs, labels)
    base_rate = float(sum(labels) / len(labels)) if labels else 0.0
    return TargetMetrics(
        target=target,
        n=len(probs),
        auc_pr=a,
        ece=e,
        mae=None,
        base_rate=base_rate,
    )


def labels_for_window(w: WindowRow) -> dict[str, int]:
    """Binary labels per target, for one test window."""

    return {
        "c2_3_prob": int(w.v_max >= 3),
        "c2_4_prob": int(w.v_max >= 4),
        "c2_5_prob": int(w.v_max >= 5),
        "c2_6_prob": int(w.v_max >= 6),
        "c3_prob": int(w.had_jump),
        "c4_prob": int(w.n_posts > 0),
    }


def score_set_for_predictions(
    name: str,
    test: list[WindowRow],
    preds_by_window: dict[tuple[datetime, datetime], dict[str, float]],
    *,
    include_c1: bool,
) -> ScoreSet:
    """Align predictions with test windows; targets absent from ``preds`` get ``n=0``."""

    aligned: list[tuple[WindowRow, dict[str, float]]] = []
    for w in test:
        key = (w.window_start, w.window_end)
        if key in preds_by_window:
            aligned.append((w, preds_by_window[key]))

    metrics: list[TargetMetrics] = []
    for col in ("c2_3_prob", "c2_4_prob", "c2_5_prob", "c2_6_prob", "c3_prob", "c4_prob"):
        pairs = [(preds[col], labels_for_window(w)[col]) for w, preds in aligned if col in preds]
        probs = [p for p, _ in pairs]
        labels = [lab for _, lab in pairs]
        target_label = col.replace("_prob", "")
        metrics.append(compute_target_metrics(target_label, probs, labels))

    if include_c1:
        pairs_c1 = [
            (preds["c1_value"], w.v_max if w.v_max >= 0 else 0)
            for w, preds in aligned
            if "c1_value" in preds
        ]
        probs_c1 = [p for p, _ in pairs_c1]
        labels_c1 = [lab for _, lab in pairs_c1]
        metrics.append(compute_target_metrics("c1", probs_c1, labels_c1))

    return ScoreSet(name=name, n_test=len(aligned), metrics=metrics)


async def build_backtest_report(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    train_until: datetime | None = None,
) -> BacktestReport:
    """Run the whole backtest pipeline and return a structured report."""

    windows = await fetch_windows_with_outcomes(session, since=since, until=until)
    if not windows:
        return BacktestReport(
            period_start=since,
            period_end=until,
            train_until=train_until or since,
            n_windows_total=0,
            n_windows_train=0,
            n_windows_test=0,
            ecosystem_posts_test=0,
            score_sets=[],
            notes=["no_outcomes_in_period"],
        )

    if train_until is None:
        mid_idx = len(windows) // 2
        train_until = windows[mid_idx - 1].window_end if mid_idx > 0 else windows[0].window_end

    train, test = split_train_test(windows, train_until)
    notes: list[str] = []
    if not test:
        notes.append("empty_test_set")
    if not train:
        notes.append("empty_train_set_b1_zero")

    eco_posts_test = sum(w.eco_n_6h for w in test)
    if eco_posts_test == 0:
        notes.append("no_ecosystem_data_b4_degenerate")

    score_sets: list[ScoreSet] = []

    baselines = baselines_for_test(train, test)
    for bname in ("B1", "B2", "B3", "B4"):
        score_sets.append(
            score_set_for_predictions(bname, test, baselines[bname], include_c1=False)
        )

    preds_by_model = await fetch_predictions(session, since=since, until=until)
    for mv, preds in preds_by_model.items():
        score_sets.append(score_set_for_predictions(mv, test, preds, include_c1=True))

    return BacktestReport(
        period_start=since,
        period_end=until,
        train_until=train_until,
        n_windows_total=len(windows),
        n_windows_train=len(train),
        n_windows_test=len(test),
        ecosystem_posts_test=eco_posts_test,
        score_sets=score_sets,
        notes=notes,
    )
