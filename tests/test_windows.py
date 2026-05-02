"""Tests for 2h window label construction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trumporacle.features.windows import TrumpPost, iter_window_labels


def test_iter_window_labels_counts_posts() -> None:
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    posts = [
        TrumpPost(t0 + timedelta(minutes=10), 2),
        TrumpPost(t0 + timedelta(hours=2, minutes=10), 4),
    ]
    labels = iter_window_labels(
        posts,
        horizon_start=t0,
        horizon_end=t0 + timedelta(hours=4),
        window_hours=2,
    )
    assert len(labels) == 2
    assert labels[0].n_posts == 1
    assert labels[0].v_max == 2
    assert labels[1].n_posts == 1
    assert labels[1].v_max == 4
