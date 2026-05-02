"""Sync engine for migrations and scripts; async pool helper for ingestion."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trumporacle.config import get_settings

_sync_engine: Engine | None = None
_async_engine: AsyncEngine | None = None


def _needs_ssl(url: str) -> bool:
    lowered = url.lower()
    return "neon.tech" in lowered or "sslmode=require" in lowered


def _asyncpg_url(url: str) -> str:
    """Build asyncpg URL; drop sslmode query (asyncpg uses connect_args ssl)."""

    if url.startswith("postgresql+psycopg://"):
        out = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        out = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        out = url
    if not _needs_ssl(url):
        return out
    parsed = urlparse(out)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "sslmode"]
    new_q = urlencode(query)
    return urlunparse(parsed._replace(query=new_q))


def _async_connect_args(url: str) -> dict[str, Any]:
    if _needs_ssl(url):
        return {"ssl": True}
    return {}


def get_sync_engine() -> Engine:
    """SQLAlchemy sync engine (Alembic, batch jobs)."""

    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _sync_engine


@contextmanager
def sync_connection() -> Iterator[Connection]:
    """Yield a sync connection with commit/rollback."""

    engine = get_sync_engine()
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


def get_async_engine() -> AsyncEngine:
    """Async engine for httpx ingestion pipelines."""

    global _async_engine
    if _async_engine is None:
        db_url = get_settings().database_url
        _async_engine = create_async_engine(
            _asyncpg_url(db_url),
            pool_pre_ping=True,
            connect_args=_async_connect_args(db_url),
        )
    return _async_engine


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory for async CRUD."""

    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    """Async session with commit/rollback."""

    factory = get_async_sessionmaker()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
