"""Discord/Telegram webhooks for drift thresholds (spec 11.5)."""

from __future__ import annotations

import httpx
from loguru import logger

from trumporacle.config import get_settings


async def send_discord_alert(message: str) -> None:
    """POST a simple message to DISCORD_WEBHOOK_URL if configured."""

    url = get_settings().discord_webhook_url
    if not url:
        logger.debug("No DISCORD_WEBHOOK_URL; skipping alert")
        return
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(url, json={"content": message[:2000]})
