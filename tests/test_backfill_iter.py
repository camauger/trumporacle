"""Unit tests for calendar-month backfill helpers."""

from __future__ import annotations

from datetime import date

from trumporacle.ingestion.backfill import iter_months, windowed_url


def test_iter_months_single_month() -> None:
    months = list(iter_months(date(2024, 3, 15), date(2024, 3, 1)))
    assert len(months) == 1
    assert months[0].start == date(2024, 3, 1)
    assert months[0].end == date(2024, 3, 31)


def test_iter_months_year_boundary() -> None:
    months = list(iter_months(date(2023, 11, 1), date(2024, 2, 1)))
    starts = [m.start for m in months]
    ends = [m.end for m in months]
    assert starts == [
        date(2023, 11, 1),
        date(2023, 12, 1),
        date(2024, 1, 1),
        date(2024, 2, 1),
    ]
    assert ends == [
        date(2023, 11, 30),
        date(2023, 12, 31),
        date(2024, 1, 31),
        date(2024, 2, 29),
    ]


def test_iter_months_empty_when_since_after_until() -> None:
    assert list(iter_months(date(2025, 6, 1), date(2024, 1, 1))) == []


def test_iter_months_handles_leap_year() -> None:
    months = list(iter_months(date(2024, 2, 1), date(2024, 2, 1)))
    assert months[0].end == date(2024, 2, 29)


def test_windowed_url_replaces_dates() -> None:
    base = "https://example.com/feed?start_date=2020-01-01&end_date=2020-02-01&lang=en"
    win_url = windowed_url(base, next(iter_months(date(2024, 6, 1), date(2024, 6, 1))))
    assert "start_date=2024-06-01" in win_url
    assert "end_date=2024-06-30" in win_url
    assert "lang=en" in win_url
    assert "start_date=2020-01-01" not in win_url


def test_windowed_url_appends_when_no_query() -> None:
    base = "https://example.com/feed"
    win_url = windowed_url(base, next(iter_months(date(2024, 1, 1), date(2024, 1, 1))))
    assert win_url.endswith("?start_date=2024-01-01&end_date=2024-01-31")
