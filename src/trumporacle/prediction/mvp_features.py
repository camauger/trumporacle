"""Load MVP tabular features at reference time H from Postgres (SQLAlchemy async)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class MvpFeatures:
    """Scalar features for baseline MVP (no leak: uses rows with published_at <= H)."""

    h: datetime
    ecosystem_mean_valence_6h: float
    ecosystem_n_6h: int
    trump_mean_valence_24h: float
    trump_n_24h: int
    trump_posts_6h: int


async def fetch_mvp_features(session: AsyncSession, h: datetime) -> MvpFeatures:
    """Aggregate annotated items strictly before or at H."""

    t_eco_lo = h - timedelta(hours=6)
    t_trump_lo24 = h - timedelta(hours=24)
    t_trump_lo6 = h - timedelta(hours=6)

    eco = await session.execute(
        text(
            """
            WITH ann AS (
                SELECT DISTINCT ON (item_id) item_id, valence_level AS v
                FROM valence_annotations
                ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
            )
            SELECT COALESCE(AVG(ann.v)::double precision, 0.0) AS mu,
                   COUNT(*)::int AS n
            FROM ann
            JOIN items i ON i.id = ann.item_id
            JOIN raw_items r ON r.id = i.raw_item_id
            JOIN sources s ON s.id = r.source_id
            WHERE r.published_at > :t_lo AND r.published_at <= :h
              AND COALESCE(s.metadata->>'trump_primary', 'false') <> 'true'
            """
        ),
        {"t_lo": t_eco_lo, "h": h},
    )
    erow = eco.mappings().first()
    eco_mu = float(erow["mu"] if erow else 0.0)
    eco_n = int(erow["n"] if erow else 0)

    trump24 = await session.execute(
        text(
            """
            WITH ann AS (
                SELECT DISTINCT ON (item_id) item_id, valence_level AS v
                FROM valence_annotations
                ORDER BY item_id, annotated_at DESC, llm_labeler_version DESC
            )
            SELECT COALESCE(AVG(ann.v)::double precision, 0.0) AS mu,
                   COUNT(*)::int AS n
            FROM ann
            JOIN items i ON i.id = ann.item_id
            JOIN raw_items r ON r.id = i.raw_item_id
            JOIN sources s ON s.id = r.source_id
            WHERE r.published_at > :t_lo AND r.published_at <= :h
              AND COALESCE(s.metadata->>'trump_primary', 'false') = 'true'
            """
        ),
        {"t_lo": t_trump_lo24, "h": h},
    )
    trow = trump24.mappings().first()
    trump_mu = float(trow["mu"] if trow else 0.0)
    trump_n = int(trow["n"] if trow else 0)

    trump6 = await session.execute(
        text(
            """
            SELECT COUNT(*)::int AS n
            FROM raw_items r
            JOIN sources s ON s.id = r.source_id
            WHERE r.published_at > :t_lo AND r.published_at <= :h
              AND COALESCE(s.metadata->>'trump_primary', 'false') = 'true'
            """
        ),
        {"t_lo": t_trump_lo6, "h": h},
    )
    trump_posts_6h = int(trump6.scalar_one())

    return MvpFeatures(
        h=h,
        ecosystem_mean_valence_6h=eco_mu,
        ecosystem_n_6h=eco_n,
        trump_mean_valence_24h=trump_mu,
        trump_n_24h=trump_n,
        trump_posts_6h=trump_posts_6h,
    )
