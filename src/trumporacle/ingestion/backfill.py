"""Calendar-month backfill of Trump's Truth RSS (spec Phase 1, ~24 months)."""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from loguru import logger

from trumporacle.config import get_settings
from trumporacle.dashboard.metrics import INGEST_ITEMS
from trumporacle.ingestion.repository import (
    get_or_create_source,
    insert_raw_item,
    upsert_item_for_raw,
)
from trumporacle.ingestion.truth_social.client import TruthSocialRSSConnector
from trumporacle.nlp.normalize import normalize_text
from trumporacle.storage.db import async_session_scope


@dataclass(frozen=True)
class MonthWindow:
    """Inclusive [start, end] calendar-month window."""

    start: date
    end: date


def iter_months(since: date, until: date) -> Iterator[MonthWindow]:
    """Yield calendar-month windows from ``since`` (incl) to ``until`` (incl)."""

    cur = date(since.year, since.month, 1)
    end_anchor = date(until.year, until.month, 1)
    if cur > end_anchor:
        return
    while cur <= end_anchor:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        yield MonthWindow(cur, date(cur.year, cur.month, last_day))
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)


def windowed_url(base_url: str, window: MonthWindow) -> str:
    """Replace any existing ``start_date``/``end_date`` query params with ``window``."""

    parsed = urlparse(base_url)
    params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k not in {"start_date", "end_date"}
    ]
    params.append(("start_date", window.start.isoformat()))
    params.append(("end_date", window.end.isoformat()))
    return urlunparse(parsed._replace(query=urlencode(params)))


async def backfill_truth_social(
    *,
    since: date,
    until: date,
    base_url: str | None = None,
) -> dict[str, int]:
    """Loop month windows, persist raw_items + items. Returns totals.

    No LLM annotation here on purpose: backfill volume × API cost is not free.
    Run ``ingest-truth`` afterwards to annotate, or batch-annotate explicitly.
    """

    settings = get_settings()
    base = base_url or settings.truth_social_rss_url
    if not base:
        raise RuntimeError("TRUTH_SOCIAL_RSS_URL unset and no base_url provided")

    total_new_raw = 0
    months = 0
    total_payloads = 0

    async with async_session_scope() as session:
        sid = await get_or_create_source(
            session,
            name="truth_social_trump",
            kind="truth_social",
            url=base,
            metadata={"trump_primary": "true"},
        )
        for win in iter_months(since, until):
            url = windowed_url(base, win)
            connector = TruthSocialRSSConnector(rss_url=url)
            payloads = await connector.fetch_since(since=None)
            month_raw = 0
            for p in payloads:
                rid = await insert_raw_item(session, source_id=sid, payload=p)
                if rid is None:
                    continue
                month_raw += 1
                INGEST_ITEMS.inc()
                clean, tc = normalize_text(p.raw_content, is_html=True)
                await upsert_item_for_raw(
                    session,
                    raw_item_id=rid,
                    clean_text=clean,
                    language="en",
                    token_count=tc,
                )
            total_new_raw += month_raw
            total_payloads += len(payloads)
            months += 1
            logger.info(
                "backfill {}–{}: payloads={} new_raw={}",
                win.start,
                win.end,
                len(payloads),
                month_raw,
            )

    return {
        "months": months,
        "payloads_seen": total_payloads,
        "new_raw": total_new_raw,
    }
