"""Prometheus metrics shared by API and background jobs."""

from __future__ import annotations

from prometheus_client import Counter

PREDICTIONS_WRITTEN = Counter(
    "trumporacle_predictions_written_total",
    "Baseline MVP predictions persisted",
)
OUTCOMES_WRITTEN = Counter(
    "trumporacle_outcomes_written_total",
    "Window outcomes materialized",
)
INGEST_ITEMS = Counter(
    "trumporacle_ingest_items_total",
    "Raw items inserted during ingest tick",
)
