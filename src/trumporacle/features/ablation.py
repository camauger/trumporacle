"""Feature ablation flags (e.g. disable temporal columns)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatureAblation:
    """Toggle feature families for diagnostics (spec 15.2 timing-only risk)."""

    include_temporal: bool = True
    include_lexical: bool = True
    include_topics: bool = True
