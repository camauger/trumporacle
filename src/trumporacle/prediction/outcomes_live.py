"""Materialize outcomes for closed prediction windows (MVP)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.dashboard.metrics import OUTCOMES_WRITTEN


async def _trump_window_stats(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> tuple[int, int]:
    """Return (n_posts, v_max) for Trump-primary annotated posts in [start, end)."""

    row = await session.execute(
        text(
            """
            SELECT COUNT(*)::int AS n,
                   COALESCE(MAX(ann.v), -1)::int AS vmax
            FROM raw_items r
            JOIN items i ON i.raw_item_id = r.id
            JOIN sources s ON s.id = r.source_id
            LEFT JOIN (
                SELECT DISTINCT ON (item_id) item_id, valence_level AS v
                FROM valence_annotations
                ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
            ) ann ON ann.item_id = i.id
            WHERE COALESCE(s.metadata->>'trump_primary', 'false') = 'true'
              AND r.published_at >= :ws AND r.published_at < :we
            """
        ),
        {"ws": window_start, "we": window_end},
    )
    m = row.mappings().first()
    if not m:
        return (0, -1)
    return int(m["n"]), int(m["vmax"])


async def _trump_recent_mean(session: AsyncSession, h: datetime) -> float:
    """Mean Trump valence over (h-24h, h]."""

    row = await session.execute(
        text(
            """
            WITH ann AS (
                SELECT DISTINCT ON (item_id) item_id, valence_level AS v
                FROM valence_annotations
                ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
            )
            SELECT COALESCE(AVG(ann.v)::double precision, 0.0) AS mu
            FROM ann
            JOIN items i ON i.id = ann.item_id
            JOIN raw_items r ON r.id = i.raw_item_id
            JOIN sources s ON s.id = r.source_id
            WHERE r.published_at > :lo AND r.published_at <= :h
              AND COALESCE(s.metadata->>'trump_primary', 'false') = 'true'
            """
        ),
        {"lo": h - timedelta(hours=24), "h": h},
    )
    return float(row.scalar_one())


async def write_outcome_for_window(
    session: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
    computed_at: datetime | None = None,
) -> bool:
    """Insert outcomes row if missing. Returns True if inserted."""

    computed_at = computed_at or datetime.now(tz=UTC)
    exists = await session.execute(
        text(
            """
            SELECT id FROM outcomes
            WHERE window_start = :ws AND window_end = :we
            LIMIT 1
            """
        ),
        {"ws": window_start, "we": window_end},
    )
    if exists.scalar_one_or_none() is not None:
        return False

    n_posts, v_max = await _trump_window_stats(session, window_start, window_end)
    v_recent = await _trump_recent_mean(session, window_start)
    had_jump = bool(n_posts and v_max >= 0 and v_max >= v_recent + 2)

    targets = json.dumps({"v_recent": v_recent})
    ins = await session.execute(
        text(
            """
            INSERT INTO outcomes (
                window_start,
                window_end,
                v_max,
                n_posts,
                targets_observed,
                had_jump,
                computed_at
            )
            VALUES (
                :ws,
                :we,
                :vmax,
                :n,
                CAST(:targets AS jsonb),
                :jump,
                :computed_at
            )
            ON CONFLICT ON CONSTRAINT uq_outcomes_window DO NOTHING
            RETURNING id
            """
        ),
        {
            "ws": window_start,
            "we": window_end,
            "vmax": v_max,
            "n": n_posts,
            "targets": targets,
            "jump": had_jump,
            "computed_at": computed_at.astimezone(UTC),
        },
    )
    new_id = ins.scalar_one_or_none()
    if new_id is None:
        return False
    OUTCOMES_WRITTEN.inc()
    logger.info(
        "outcome written ws={} we={} v_max={} n={} jump={}",
        window_start,
        window_end,
        v_max,
        n_posts,
        had_jump,
    )
    return True


async def materialize_due_outcomes(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    """Close predictions whose window_end < now and have no outcome row."""

    now = now or datetime.now(tz=UTC)
    rows = await session.execute(
        text(
            """
            SELECT p.window_start, p.window_end
            FROM predictions p
            LEFT JOIN outcomes o
              ON o.window_start = p.window_start AND o.window_end = p.window_end
            WHERE p.window_end < :now AND o.id IS NULL
            ORDER BY p.window_end ASC
            LIMIT :lim
            """
        ),
        {"now": now.astimezone(UTC), "lim": limit},
    )
    n_ins = 0
    for row in rows.mappings():
        if await write_outcome_for_window(
            session,
            window_start=row["window_start"],
            window_end=row["window_end"],
            computed_at=now,
        ):
            n_ins += 1
    return n_ins
