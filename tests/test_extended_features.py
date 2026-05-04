"""Unit tests for trumporacle.features.extended (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

from trumporacle.features.extended import (
    FEATURE_NAMES,
    ExtendedFeatures,
    _calendar_features,
)


def _make(h: datetime, **kwargs: float | int) -> ExtendedFeatures:
    """Build an ExtendedFeatures with all-zero defaults except overrides."""

    defaults: dict[str, float | int] = {
        "trump_n_1h": 0,
        "trump_n_6h": 0,
        "trump_n_24h": 0,
        "eco_n_1h": 0,
        "eco_n_6h": 0,
        "eco_n_24h": 0,
        "trump_mean_6h": 0.0,
        "trump_mean_24h": 0.0,
        "trump_max_6h": -1,
        "trump_max_24h": -1,
        "eco_mean_6h": 0.0,
        "eco_mean_24h": 0.0,
        "eco_max_6h": -1,
        "trend_trump_6h": 0.0,
        "trend_eco_6h": 0.0,
        "hour_of_day": 0,
        "day_of_week": 0,
        "is_weekend": 0,
        "is_us_business_hours_et": 0,
        "is_fox_friends_et": 0,
    }
    defaults.update(kwargs)
    return ExtendedFeatures(h=h, **defaults)  # type: ignore[arg-type]


def test_feature_names_count_matches_dataclass_fields() -> None:
    h = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    feat = _make(h)
    assert len(FEATURE_NAMES) == 20
    assert len(feat.to_array()) == 20


def test_to_array_preserves_canonical_order() -> None:
    h = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    feat = _make(h, trump_n_1h=3, eco_max_6h=4, is_fox_friends_et=1)
    arr = feat.to_array()
    assert arr[FEATURE_NAMES.index("trump_n_1h")] == 3
    assert arr[FEATURE_NAMES.index("eco_max_6h")] == 4
    assert arr[FEATURE_NAMES.index("is_fox_friends_et")] == 1


def test_calendar_fox_friends_window_weekday_morning_et() -> None:
    # Tuesday 2026-05-05, 11 UTC = 7 EDT -> Fox & Friends weekday morning
    h = datetime(2026, 5, 5, 11, 0, tzinfo=UTC)
    cal = _calendar_features(h)
    assert cal["hour_of_day"] == 11
    assert cal["day_of_week"] == 1  # Tuesday
    assert cal["is_weekend"] == 0
    assert cal["is_fox_friends_et"] == 1
    assert cal["is_us_business_hours_et"] == 0  # 7 ET is before business hours


def test_calendar_business_hours_et_weekday() -> None:
    # Wednesday 2026-05-06, 17 UTC = 13 EDT -> business hours
    h = datetime(2026, 5, 6, 17, 0, tzinfo=UTC)
    cal = _calendar_features(h)
    assert cal["is_us_business_hours_et"] == 1
    assert cal["is_fox_friends_et"] == 0
    assert cal["is_weekend"] == 0


def test_calendar_weekend_excludes_business_hours() -> None:
    # Saturday 2026-05-09, 17 UTC = 13 EDT
    h = datetime(2026, 5, 9, 17, 0, tzinfo=UTC)
    cal = _calendar_features(h)
    assert cal["is_weekend"] == 1
    assert cal["is_us_business_hours_et"] == 0
    assert cal["is_fox_friends_et"] == 0


def test_calendar_naive_datetime_treated_as_utc() -> None:
    h_naive = datetime(2026, 5, 6, 17, 0)
    h_utc = datetime(2026, 5, 6, 17, 0, tzinfo=UTC)
    assert _calendar_features(h_utc) == _calendar_features(h_naive.replace(tzinfo=UTC))
