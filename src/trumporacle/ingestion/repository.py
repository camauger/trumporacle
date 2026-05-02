"""Persistence helpers for ingestion (append-only raw_items / items)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.ingestion.base import RawItemPayload


async def get_or_create_source(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    url: str | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Return sources.id, inserting if missing."""

    meta = metadata or {}
    row = await session.execute(
        text("SELECT id FROM sources WHERE name = :name"),
        {"name": name},
    )
    found = row.scalar_one_or_none()
    if found is not None:
        return int(found)

    ins = await session.execute(
        text(
            """
            INSERT INTO sources (name, kind, url, metadata)
            VALUES (:name, :kind, :url, CAST(:metadata AS jsonb))
            RETURNING id
            """
        ),
        {"name": name, "kind": kind, "url": url, "metadata": json.dumps(meta)},
    )
    return int(ins.scalar_one())


async def insert_raw_item(
    session: AsyncSession,
    *,
    source_id: int,
    payload: RawItemPayload,
) -> int | None:
    """Insert raw_item if not duplicate (source_id, external_id). Returns id or None if skip."""

    dup = await session.execute(
        text(
            "SELECT id FROM raw_items WHERE source_id = :source_id AND external_id = :external_id"
        ),
        {"source_id": source_id, "external_id": payload.external_id},
    )
    if dup.scalar_one_or_none() is not None:
        return None

    row = await session.execute(
        text(
            """
            INSERT INTO raw_items (
                source_id, external_id, published_at, author, raw_content, media_urls, raw_metadata
            )
            VALUES (
                :source_id, :external_id, :published_at, :author, :raw_content,
                CAST(:media_urls AS jsonb), CAST(:raw_metadata AS jsonb)
            )
            RETURNING id
            """
        ),
        {
            "source_id": source_id,
            "external_id": payload.external_id,
            "published_at": payload.published_at,
            "author": payload.author,
            "raw_content": payload.raw_content,
            "media_urls": json.dumps(payload.media_urls),
            "raw_metadata": json.dumps(payload.raw_metadata),
        },
    )
    return int(row.scalar_one())


async def upsert_item_for_raw(
    session: AsyncSession,
    *,
    raw_item_id: int,
    clean_text: str,
    language: str | None,
    token_count: int | None,
) -> int:
    """Create items row linked to raw_item (idempotent on raw_item_id unique)."""

    row = await session.execute(
        text("SELECT id FROM items WHERE raw_item_id = :rid"),
        {"rid": raw_item_id},
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        return int(existing)

    ins = await session.execute(
        text(
            """
            INSERT INTO items (raw_item_id, language, clean_text, token_count)
            VALUES (:raw_item_id, :language, :clean_text, :token_count)
            RETURNING id
            """
        ),
        {
            "raw_item_id": raw_item_id,
            "language": language,
            "clean_text": clean_text,
            "token_count": token_count,
        },
    )
    return int(ins.scalar_one())


def utcnow() -> datetime:
    """Timezone-aware UTC now."""

    from datetime import UTC

    return datetime.now(tz=UTC)
