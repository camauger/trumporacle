"""Single MVP pipeline tick: ingest → predict → outcomes (used by jobs and CLI)."""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from trumporacle.config import get_settings
from trumporacle.ingestion.truth_pipeline import ingest_truth_social_once
from trumporacle.prediction.mvp_predict import write_baseline_prediction
from trumporacle.prediction.outcomes_live import materialize_due_outcomes
from trumporacle.storage.db import async_session_scope


async def run_mvp_tick(*, now: datetime | None = None) -> dict[str, int | bool]:
    """Run one full MVP cycle. Returns counters for logging/UI."""

    now = now or datetime.now(tz=UTC)
    settings = get_settings()
    annotate = bool(settings.anthropic_api_key)

    new_raw, ann_n = await ingest_truth_social_once(annotate_with_llm=annotate)
    async with async_session_scope() as session:
        pred_inserted = await write_baseline_prediction(session, now=now)
        out_n = await materialize_due_outcomes(session, now=now)

    logger.info(
        "mvp_tick raw={} ann={} pred_inserted={} outcomes={}",
        new_raw,
        ann_n,
        pred_inserted,
        out_n,
    )
    return {
        "ingest_new_raw": new_raw,
        "ingest_annotations": ann_n,
        "prediction_inserted": int(pred_inserted),
        "outcomes_written": out_n,
    }
