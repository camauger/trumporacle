"""One-shot Truth Social ingest: RSS → raw_items → items → optional LLM annotations."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text

from trumporacle.config import get_settings
from trumporacle.dashboard.metrics import INGEST_ITEMS
from trumporacle.ingestion.repository import (
    get_or_create_source,
    insert_raw_item,
    upsert_item_for_raw,
)
from trumporacle.ingestion.truth_social.client import TruthSocialRSSConnector
from trumporacle.nlp.annotation.labeler import annotate_valence
from trumporacle.nlp.annotation.rubric import RUBRIC_VERSION
from trumporacle.nlp.normalize import normalize_text
from trumporacle.storage.db import async_session_scope


async def ingest_truth_social_once(
    *,
    annotate_with_llm: bool = True,
) -> tuple[int, int]:
    """Fetch RSS, persist new rows. Returns (new_raw_items, annotations_written)."""

    settings = get_settings()
    connector = TruthSocialRSSConnector()
    payloads = await connector.fetch_since(since=None)
    if not payloads:
        logger.debug(
            "ingest_truth_social_once: no payloads (TRUTH_SOCIAL_RSS_URL unset or empty feed)"
        )
        return (0, 0)

    new_raw = 0
    ann_n = 0
    async with async_session_scope() as session:
        sid = await get_or_create_source(
            session,
            name=connector.source_name,
            kind="truth_social",
            url=settings.truth_social_rss_url,
            metadata={"trump_primary": "true"},
        )
        for p in payloads:
            rid = await insert_raw_item(session, source_id=sid, payload=p)
            if rid is None:
                continue
            new_raw += 1
            INGEST_ITEMS.inc()
            clean, tc = normalize_text(p.raw_content, is_html=True)
            iid = await upsert_item_for_raw(
                session,
                raw_item_id=rid,
                clean_text=clean,
                language="en",
                token_count=tc,
            )
            if not annotate_with_llm:
                continue
            ann = annotate_valence(clean)
            if ann is None:
                continue
            await session.execute(
                text(
                    """
                    INSERT INTO valence_annotations (
                        item_id,
                        annotator,
                        valence_level,
                        target_type,
                        target_name,
                        confidence,
                        rationale,
                        llm_labeler_version
                    )
                    VALUES (:item_id, :annotator, :level, :ttype, :tname, :conf, :rat, :ver)
                    """
                ),
                {
                    "item_id": iid,
                    "annotator": "llm",
                    "level": ann.level,
                    "ttype": ann.target_type,
                    "tname": ann.target_name,
                    "conf": ann.confidence,
                    "rat": ann.rationale,
                    "ver": RUBRIC_VERSION,
                },
            )
            ann_n += 1
    logger.info("ingest_truth_social_once: new_raw={} annotations={}", new_raw, ann_n)
    return (new_raw, ann_n)
