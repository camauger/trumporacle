"""Telethon-based public channel reader (Phase 3 wiring)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from trumporacle.ingestion.base import RawItemPayload, SourceConnector


class TelegramChannelConnector(SourceConnector):
    """Placeholder connector; implement Telethon session + fetch in Phase 3."""

    def __init__(self, *, source_name: str, channel_username: str) -> None:
        self.source_name = source_name
        self._channel = channel_username

    async def fetch_since(self, since: datetime | None) -> list[RawItemPayload]:
        """No-op until TELEGRAM_API_ID / TELEGRAM_API_HASH configured."""

        _ = since
        return []


def load_channel_list(path: str) -> list[dict[str, Any]]:
    """Load YAML/JSON list of channels (usernames) from config file."""

    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data) if isinstance(data, list) else []
