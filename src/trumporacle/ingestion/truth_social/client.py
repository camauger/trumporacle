"""Truth Social connector: RSS feed (configurable) with httpx + feedparser."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from trumporacle.config import get_settings
from trumporacle.ingestion.base import RawItemPayload, SourceConnector


def _parse_dt(entry: Any) -> datetime:
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


class TruthSocialRSSConnector(SourceConnector):
    """Fetch posts via RSS URL in ``TRUTH_SOCIAL_RSS_URL`` (e.g. Trump's Truth feed)."""

    def __init__(
        self,
        *,
        source_name: str = "truth_social_trump",
        rss_url: str | None = None,
    ) -> None:
        self.source_name = source_name
        self._rss_url = rss_url

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
    async def fetch_since(self, since: datetime | None) -> list[RawItemPayload]:
        """Parse RSS; filter by ``since`` when provided."""

        settings = get_settings()
        url = self._rss_url or settings.truth_social_rss_url
        if url is None:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)

        out: list[RawItemPayload] = []
        for entry in parsed.entries:
            published = _parse_dt(entry)
            if since is not None and published <= since:
                continue
            external_id = str(
                getattr(entry, "id", None) or getattr(entry, "link", "") or published.isoformat()
            )
            summary = getattr(entry, "summary", "") or ""
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            raw_content = content or summary
            author = getattr(entry, "author", None)
            out.append(
                RawItemPayload(
                    external_id=external_id,
                    published_at=published,
                    author=author,
                    raw_content=raw_content,
                    media_urls=[],
                    raw_metadata={"link": getattr(entry, "link", None)},
                )
            )
        return out
