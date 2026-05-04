"""Extended feature set ``fs_xgb_001`` for tabular models (spec section 11).

Computed at reference time ``H``; uses only data with ``published_at <= H``
(no temporal leakage). Latest annotation per item is used (annotator-aware
``DISTINCT ON`` already applied in the underlying queries).

Feature inventory (18 numerical features):

- Volumes: ``trump_n_{1h,6h,24h}``, ``eco_n_{1h,6h,24h}``.
- Valence aggregates: ``trump_mean_{6h,24h}``, ``trump_max_{6h,24h}``,
  ``eco_mean_{6h,24h}``, ``eco_max_6h``.
- Trend approximation (last 3h mean minus prior 3h mean):
  ``trend_trump_6h``, ``trend_eco_6h``.
- Calendar signals: ``hour_of_day`` (UTC), ``day_of_week``,
  ``is_weekend``, ``is_us_business_hours_et``, ``is_fox_friends_et``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FEATURE_SET_VERSION = "fs_xgb_001"

FEATURE_NAMES: tuple[str, ...] = (
    "trump_n_1h",
    "trump_n_6h",
    "trump_n_24h",
    "eco_n_1h",
    "eco_n_6h",
    "eco_n_24h",
    "trump_mean_6h",
    "trump_mean_24h",
    "trump_max_6h",
    "trump_max_24h",
    "eco_mean_6h",
    "eco_mean_24h",
    "eco_max_6h",
    "trend_trump_6h",
    "trend_eco_6h",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_us_business_hours_et",
    "is_fox_friends_et",
)


@dataclass(frozen=True, slots=True)
class ExtendedFeatures:
    """One row of features at reference time ``h``."""

    h: datetime
    trump_n_1h: int
    trump_n_6h: int
    trump_n_24h: int
    eco_n_1h: int
    eco_n_6h: int
    eco_n_24h: int
    trump_mean_6h: float
    trump_mean_24h: float
    trump_max_6h: int
    trump_max_24h: int
    eco_mean_6h: float
    eco_mean_24h: float
    eco_max_6h: int
    trend_trump_6h: float
    trend_eco_6h: float
    hour_of_day: int
    day_of_week: int
    is_weekend: int
    is_us_business_hours_et: int
    is_fox_friends_et: int

    def to_array(self) -> list[float]:
        """Return features in the canonical :data:`FEATURE_NAMES` order."""

        return [float(getattr(self, name)) for name in FEATURE_NAMES]


_SIDE_QUERY = text(
    """
    WITH ann AS (
        SELECT DISTINCT ON (item_id) item_id, valence_level AS v
        FROM valence_annotations
        ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
    )
    SELECT
        COUNT(*) FILTER (WHERE r.published_at > :t_1h)::int AS n_1h,
        COUNT(*) FILTER (WHERE r.published_at > :t_6h)::int AS n_6h,
        COUNT(*) FILTER (WHERE r.published_at > :t_24h)::int AS n_24h,
        COALESCE(AVG(ann.v) FILTER (WHERE r.published_at > :t_6h)::float, 0.0) AS mean_6h,
        COALESCE(AVG(ann.v) FILTER (WHERE r.published_at > :t_24h)::float, 0.0) AS mean_24h,
        COALESCE(MAX(ann.v) FILTER (WHERE r.published_at > :t_6h), -1)::int AS max_6h,
        COALESCE(MAX(ann.v) FILTER (WHERE r.published_at > :t_24h), -1)::int AS max_24h,
        COALESCE(AVG(ann.v) FILTER (WHERE r.published_at > :t_3h)::float, 0.0) AS mean_recent_3h,
        COALESCE(AVG(ann.v) FILTER (
            WHERE r.published_at > :t_6h AND r.published_at <= :t_3h
        )::float, 0.0) AS mean_older_3h
    FROM raw_items r
    JOIN items i ON i.raw_item_id = r.id
    JOIN sources s ON s.id = r.source_id
    LEFT JOIN ann ON ann.item_id = i.id
    WHERE r.published_at <= :h
      AND COALESCE(s.metadata->>'trump_primary', 'false') = :primary
    """
)


async def _side_stats(session: AsyncSession, h: datetime, *, trump: bool) -> dict[str, float]:
    """Return one side's stats (Trump-primary or ecosystem) at H."""

    row = (
        (
            await session.execute(
                _SIDE_QUERY,
                {
                    "h": h,
                    "t_1h": h - timedelta(hours=1),
                    "t_3h": h - timedelta(hours=3),
                    "t_6h": h - timedelta(hours=6),
                    "t_24h": h - timedelta(hours=24),
                    "primary": "true" if trump else "false",
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return {
            "n_1h": 0,
            "n_6h": 0,
            "n_24h": 0,
            "mean_6h": 0.0,
            "mean_24h": 0.0,
            "max_6h": -1,
            "max_24h": -1,
            "mean_recent_3h": 0.0,
            "mean_older_3h": 0.0,
        }
    return dict(row)


def _calendar_features(h: datetime) -> dict[str, int]:
    """UTC-based calendar features. ``hour_of_day`` is UTC; the ET-derived
    flags translate (no DST handling — uses UTC-4 offset, sufficient for
    May 2026 which is in EDT)."""

    h_utc = h.astimezone(UTC)
    et_hour = (h_utc.hour - 4) % 24  # EDT
    return {
        "hour_of_day": h_utc.hour,
        "day_of_week": h_utc.weekday(),
        "is_weekend": 1 if h_utc.weekday() >= 5 else 0,
        "is_us_business_hours_et": 1 if (9 <= et_hour < 17 and h_utc.weekday() < 5) else 0,
        "is_fox_friends_et": 1 if (6 <= et_hour < 9 and h_utc.weekday() < 5) else 0,
    }


async def fetch_extended_features(session: AsyncSession, h: datetime) -> ExtendedFeatures:
    """Compute all extended features at reference time ``h``."""

    trump = await _side_stats(session, h, trump=True)
    eco = await _side_stats(session, h, trump=False)
    cal = _calendar_features(h)

    trend_trump = float(trump["mean_recent_3h"]) - float(trump["mean_older_3h"])
    trend_eco = float(eco["mean_recent_3h"]) - float(eco["mean_older_3h"])

    return ExtendedFeatures(
        h=h,
        trump_n_1h=int(trump["n_1h"]),
        trump_n_6h=int(trump["n_6h"]),
        trump_n_24h=int(trump["n_24h"]),
        eco_n_1h=int(eco["n_1h"]),
        eco_n_6h=int(eco["n_6h"]),
        eco_n_24h=int(eco["n_24h"]),
        trump_mean_6h=float(trump["mean_6h"]),
        trump_mean_24h=float(trump["mean_24h"]),
        trump_max_6h=int(trump["max_6h"]),
        trump_max_24h=int(trump["max_24h"]),
        eco_mean_6h=float(eco["mean_6h"]),
        eco_mean_24h=float(eco["mean_24h"]),
        eco_max_6h=int(eco["max_6h"]),
        trend_trump_6h=trend_trump,
        trend_eco_6h=trend_eco,
        hour_of_day=cal["hour_of_day"],
        day_of_week=cal["day_of_week"],
        is_weekend=cal["is_weekend"],
        is_us_business_hours_et=cal["is_us_business_hours_et"],
        is_fox_friends_et=cal["is_fox_friends_et"],
    )


def feature_window_label(window_end: datetime) -> dict[str, datetime | timedelta]:
    """Return the spec-aligned 2h window endpoints for documentation purposes."""

    return {"window_end": window_end, "window_hours": timedelta(hours=2)}
