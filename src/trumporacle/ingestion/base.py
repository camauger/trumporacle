"""Abstract ingestion connector: idempotent fetch into raw_items."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RawItemPayload:
    """Normalized payload before DB insert."""

    external_id: str
    published_at: datetime
    author: str | None
    raw_content: str
    media_urls: list[str]
    raw_metadata: dict[str, Any]


class SourceConnector(ABC):
    """Pluggable source connector (retry/backoff implemented per call site)."""

    source_name: str

    @abstractmethod
    async def fetch_since(self, since: datetime | None) -> list[RawItemPayload]:
        """Return new items since watermark (None = full backfill window)."""
