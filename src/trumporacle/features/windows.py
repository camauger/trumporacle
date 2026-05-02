"""Build 2h window labels from Trump post series (spec section 5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from trumporacle.evaluation.baselines import WindowLabel


@dataclass(frozen=True, slots=True)
class TrumpPost:
    """Minimal post for window aggregation."""

    published_at: datetime
    valence: int


def iter_window_labels(
    posts: list[TrumpPost],
    *,
    window_hours: int = 2,
    horizon_start: datetime,
    horizon_end: datetime,
    recent_hours: int = 24,
) -> list[WindowLabel]:
    """Slide 2h windows; v_recent = mean valence in [H-24h, H)."""

    if not posts:
        return []

    posts_sorted = sorted(posts, key=lambda p: p.published_at)
    out: list[WindowLabel] = []
    h = horizon_start.astimezone(UTC)
    end = horizon_end.astimezone(UTC)
    step = timedelta(hours=window_hours)

    def mean_recent(ref: datetime) -> float:
        lo = ref - timedelta(hours=recent_hours)
        vals = [p.valence for p in posts_sorted if lo <= p.published_at < ref]
        return sum(vals) / len(vals) if vals else 0.0

    while h + step <= end:
        w_start = h
        w_end = h + step
        in_win = [p.valence for p in posts_sorted if w_start <= p.published_at < w_end]
        v_max = max(in_win) if in_win else -1
        out.append(
            WindowLabel(
                window_start=w_start,
                window_end=w_end,
                v_max=v_max,
                v_recent=mean_recent(w_start),
                n_posts=len(in_win),
            )
        )
        h += step
    return out
