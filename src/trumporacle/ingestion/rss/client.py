"""Generic RSS item fetch (Breitbart-style sites)."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from trumporacle.ingestion.base import RawItemPayload, SourceConnector


def _entry_dt(entry: Any) -> datetime:
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=UTC)
    if getattr(entry, "published", None):
        try:
            dt = parsedate_to_datetime(entry.published)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.now(tz=UTC)


class RSSFeedConnector(SourceConnector):
    """Fetch entries from a single RSS URL."""

    def __init__(self, *, source_name: str, feed_url: str) -> None:
        self.source_name = source_name
        self._feed_url = feed_url

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
    async def fetch_since(self, since: datetime | None) -> list[RawItemPayload]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self._feed_url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)

        out: list[RawItemPayload] = []
        for entry in parsed.entries:
            published = _entry_dt(entry)
            if since is not None and published <= since:
                continue
            eid = str(
                getattr(entry, "id", None) or getattr(entry, "link", "") or published.isoformat()
            )
            summary = getattr(entry, "summary", "") or ""
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            text = content or summary
            out.append(
                RawItemPayload(
                    external_id=eid,
                    published_at=published,
                    author=getattr(entry, "author", None),
                    raw_content=text,
                    media_urls=[],
                    raw_metadata={"link": getattr(entry, "link", None)},
                )
            )
        return out
