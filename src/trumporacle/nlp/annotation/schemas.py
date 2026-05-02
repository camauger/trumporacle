"""Structured LLM outputs (instructor + Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ValenceAnnotationResult(BaseModel):
    """Single post valence annotation (spec section 4)."""

    level: int = Field(ge=0, le=6)
    target_type: Literal["person", "institution", "group", "media", "self_referential", "none"]
    target_name: str | None = None
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
