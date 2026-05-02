"""Integration tests against a real Postgres (docker compose)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from trumporacle.storage.db import sync_connection


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
def test_db_connect_and_sources_roundtrip() -> None:
    with sync_connection() as conn:
        conn.execute(text("SELECT 1"))
        conn.execute(
            text(
                "INSERT INTO sources (name, kind, url, metadata) "
                "VALUES ('test_source', 'rss', 'http://example.com', '{}'::jsonb) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
