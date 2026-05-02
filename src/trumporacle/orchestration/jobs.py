"""Periodic ingestion, inference, and outcome materialization."""

from __future__ import annotations

from loguru import logger


async def job_ingest_truth_social() -> None:
    """Poll Truth Social RSS; annotate only if ANTHROPIC_API_KEY is set."""

    try:
        from trumporacle.config import get_settings
        from trumporacle.ingestion.truth_pipeline import ingest_truth_social_once

        annotate = bool(get_settings().anthropic_api_key)
        new_raw, ann_n = await ingest_truth_social_once(annotate_with_llm=annotate)
        logger.debug("job_ingest_truth_social raw={} ann={}", new_raw, ann_n)
    except Exception:
        logger.exception("job_ingest_truth_social failed")


async def job_predict_windows() -> None:
    """Write baseline MVP prediction for the current 2h window if absent."""

    try:
        from datetime import UTC, datetime

        from trumporacle.prediction.mvp_predict import write_baseline_prediction
        from trumporacle.storage.db import async_session_scope

        async with async_session_scope() as session:
            await write_baseline_prediction(session, now=datetime.now(tz=UTC))
    except Exception:
        logger.exception("job_predict_windows failed")


async def job_materialize_outcomes() -> None:
    """Persist outcomes for prediction windows that have closed."""

    try:
        from datetime import UTC, datetime

        from trumporacle.prediction.outcomes_live import materialize_due_outcomes
        from trumporacle.storage.db import async_session_scope

        async with async_session_scope() as session:
            n = await materialize_due_outcomes(session, now=datetime.now(tz=UTC))
            if n:
                logger.info("job_materialize_outcomes wrote {}", n)
    except Exception:
        logger.exception("job_materialize_outcomes failed")
