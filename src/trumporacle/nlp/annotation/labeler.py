"""Anthropic + instructor valence labeling with diskcache."""

from __future__ import annotations

import hashlib
from pathlib import Path

import instructor
from anthropic import Anthropic
from diskcache import Cache
from loguru import logger

from trumporacle.config import get_settings
from trumporacle.nlp.annotation.rubric import RUBRIC_BODY, RUBRIC_VERSION, build_user_prompt
from trumporacle.nlp.annotation.schemas import ValenceAnnotationResult


def _cache_dir() -> Path:
    return Path(".cache") / "llm_labels"


def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha256((RUBRIC_VERSION + model + text).encode("utf-8")).hexdigest()
    return h


def annotate_valence(
    text: str,
    *,
    model: str | None = None,
) -> ValenceAnnotationResult | None:
    """Return structured annotation or None if API key missing."""

    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set; skipping LLM annotation")
        return None

    resolved_model = model or settings.anthropic_model
    cache = Cache(str(_cache_dir()))
    key = _cache_key(text, resolved_model)
    cached = cache.get(key)
    if isinstance(cached, str):
        try:
            return ValenceAnnotationResult.model_validate_json(cached)
        except ValueError:
            pass

    client = instructor.from_anthropic(Anthropic(api_key=settings.anthropic_api_key))
    result = client.chat.completions.create(
        model=resolved_model,
        max_tokens=1024,
        response_model=ValenceAnnotationResult,
        messages=[
            {"role": "system", "content": RUBRIC_BODY.strip()},
            {"role": "user", "content": build_user_prompt(text)},
        ],
    )
    cache.set(key, result.model_dump_json())
    return ValenceAnnotationResult.model_validate(result.model_dump())
