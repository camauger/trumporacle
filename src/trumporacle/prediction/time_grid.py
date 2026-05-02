"""Align prediction reference time H to a fixed grid (MVP: 15-minute buckets)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def floor_to_grid(dt: datetime, *, step_minutes: int = 15) -> datetime:
    """Floor ``dt`` (timezone-aware) to ``step_minutes`` boundary in UTC."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    step = step_minutes * 60
    sec = int(dt.timestamp())
    floored = sec - (sec % step)
    return datetime.fromtimestamp(floored, tz=UTC)


def prediction_window(h: datetime, *, window_hours: int = 2) -> tuple[datetime, datetime]:
    """Return [H, H + window_hours) for spec window W(H)."""

    h0 = floor_to_grid(h, step_minutes=15)
    return h0, h0 + timedelta(hours=window_hours)
