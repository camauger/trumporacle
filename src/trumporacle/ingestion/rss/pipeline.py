"""One-shot ecosystem RSS ingest: feeds → raw_items → items → optional LLM annotations."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.dashboard.metrics import INGEST_ITEMS
from trumporacle.ingestion.repository import (
    get_or_create_source,
    insert_raw_item,
    upsert_item_for_raw,
)
from trumporacle.ingestion.rss.client import RSSFeedConnector
from trumporacle.ingestion.rss.feeds import ECOSYSTEM_FEEDS, RSSFeed
from trumporacle.nlp.annotation.labeler import annotate_valence
from trumporacle.nlp.annotation.rubric import RUBRIC_VERSION
from trumporacle.nlp.normalize import normalize_text
from trumporacle.storage.db import async_session_scope

ANNOTATION_TEXT_MAX_CHARS = 4000


async def _persist_one_feed(
    session: AsyncSession,
    feed: RSSFeed,
    *,
    annotate_with_llm: bool,
) -> dict[str, int]:
    """Fetch + persist one feed; failures are logged and reported as zero."""

    try:
        connector = RSSFeedConnector(source_name=feed.name, feed_url=feed.url)
        payloads = await connector.fetch_since(since=None)
    except Exception as exc:
        logger.warning("rss feed {} fetch failed: {}", feed.label, exc)
        return {"new_raw": 0, "annotations": 0, "fetch_error": 1}

    sid = await get_or_create_source(
        session,
        name=feed.name,
        kind="rss",
        url=feed.url,
        metadata={"label": feed.label},
    )

    new_raw = 0
    ann_n = 0
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
        if not annotate_with_llm or not clean:
            continue
        excerpt = clean[:ANNOTATION_TEXT_MAX_CHARS]
        ann = annotate_valence(excerpt)
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

    return {"new_raw": new_raw, "annotations": ann_n, "fetch_error": 0}


async def ingest_rss_ecosystem_once(*, annotate_with_llm: bool = True) -> dict[str, Any]:
    """Loop ecosystem feeds; persist + (optionally) LLM-annotate. Returns counters."""

    per_feed: dict[str, dict[str, int]] = {}
    total_raw = 0
    total_ann = 0
    fetch_errors = 0
    async with async_session_scope() as session:
        for feed in ECOSYSTEM_FEEDS:
            stats = await _persist_one_feed(session, feed, annotate_with_llm=annotate_with_llm)
            per_feed[feed.name] = stats
            total_raw += stats["new_raw"]
            total_ann += stats["annotations"]
            fetch_errors += stats["fetch_error"]

    summary: dict[str, Any] = {
        "feeds": len(ECOSYSTEM_FEEDS),
        "total_new_raw": total_raw,
        "total_annotations": total_ann,
        "fetch_errors": fetch_errors,
        "per_feed": per_feed,
    }
    logger.info(
        "ingest_rss_ecosystem_once feeds={} new_raw={} annotations={} fetch_errors={}",
        len(ECOSYSTEM_FEEDS),
        total_raw,
        total_ann,
        fetch_errors,
    )
    return summary
