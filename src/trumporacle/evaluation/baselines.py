"""Baselines B1–B4 (spec section 10.3)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class WindowLabel:
    """Observed targets for a 2h window (spec section 5)."""

    window_start: datetime
    window_end: datetime
    v_max: int
    v_recent: float
    n_posts: int


def b1_constant(train_windows: Iterable[WindowLabel], k: int) -> float:
    """B1: marginal P(v_max >= k) over last 90d proxy = train windows."""

    ws = list(train_windows)
    if not ws:
        return 0.0
    return sum(1 for w in ws if w.v_max >= k) / len(ws)


def b2_persistence_trump(v_recent: float, k: int) -> float:
    """B2: predict 1 if recent rolling level crosses k (crude step)."""

    return 1.0 if v_recent >= float(k) else 0.0


def b3_ar1_prediction(v_prev_window_max: int, k: int) -> float:
    """B3: AR(1)-style persistence on discrete max of previous window."""

    return 1.0 if v_prev_window_max >= k else 0.0


def b4_media_persistence(ecosystem_mean_valence_6h: float, k: int) -> float:
    """B4: ecosystem valence persistence (spec 10.3) — probability proxy."""

    return 1.0 if ecosystem_mean_valence_6h >= float(k) else 0.0


def rolling_mean_valence(values: list[tuple[datetime, int]], cutoff: datetime, hours: int) -> float:
    """Mean valence of items with timestamps in (cutoff - hours, cutoff]."""

    start = cutoff - timedelta(hours=hours)
    subset = [v for ts, v in values if start < ts <= cutoff]
    if not subset:
        return 0.0
    return float(sum(subset) / len(subset))
