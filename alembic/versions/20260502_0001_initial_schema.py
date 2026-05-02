"""Initial TRUMPORACLE schema (spec section 8).

Revision ID: 20260502_0001
Revises:
Create Date: 2026-05-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = "20260502_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # TimescaleDB: do not CREATE EXTENSION here. Managed DBs (Neon, etc.) preload it and
    # repeating CREATE in-session raises "already been loaded with another version".
    # Local Docker enables it in docker/db/init-extensions.sql on first init.

    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            comment="truth_social|telegram|tv|rss|podcast",
        ),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )

    op.create_table(
        "raw_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("published_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "captured_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("media_urls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("raw_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_raw_items_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Timescale hypertable omitted: PK(id) without ``published_at`` violates Timescale’s rule
    # that UNIQUE/PK include the partition column; fixing it requires a composite FK from ``items``.
    # ``raw_items`` stays a normal table (Neon-friendly); BRIN/partitioning can be a later migration.

    op.create_index(
        "ix_raw_items_source_external",
        "raw_items",
        ["source_id", "external_id"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_items_source_published "
        "ON raw_items (source_id, published_at DESC);"
    )

    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("clean_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("entities", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"], name="fk_items_raw_item"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_item_id", name="uq_items_raw_item"),
    )
    op.execute("ALTER TABLE items ADD COLUMN embedding vector(1024);")

    op.create_table(
        "valence_annotations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("annotator", sa.Text(), nullable=False),
        sa.Column("valence_level", sa.SmallInteger(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "annotated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("llm_labeler_version", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_valence_item"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_valence_item", "valence_annotations", ["item_id"])

    op.create_table(
        "gold_standard",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("valence_level", sa.SmallInteger(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column("gold_version", sa.Text(), nullable=False),
        sa.Column(
            "frozen_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_gold_item"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "taxonomy_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("definition", JSONB(), nullable=False),
        sa.Column("effective_from", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("effective_to", TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feature_sets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("definition", JSONB(), nullable=False),
        sa.Column("effective_from", TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_feature_sets_name_version"),
    )

    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("algo", sa.Text(), nullable=False),
        sa.Column("trained_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("train_period_start", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("train_period_end", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("feature_set_id", sa.BigInteger(), nullable=True),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["feature_set_id"], ["feature_sets.id"], name="fk_models_feature_set"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", "task", name="uq_models_version_task"),
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("prediction_made_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_start", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("feature_hash", sa.Text(), nullable=False),
        sa.Column("feature_set_version", sa.Text(), nullable=True),
        sa.Column("c1_value", sa.Float(), nullable=True),
        sa.Column("c2_3_prob", sa.Float(), nullable=True),
        sa.Column("c2_4_prob", sa.Float(), nullable=True),
        sa.Column("c2_5_prob", sa.Float(), nullable=True),
        sa.Column("c2_6_prob", sa.Float(), nullable=True),
        sa.Column("c3_prob", sa.Float(), nullable=True),
        sa.Column("c4_prob", sa.Float(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_predictions_window",
        "predictions",
        ["window_start", "window_end"],
    )

    op.create_table(
        "outcomes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("window_start", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("v_max", sa.SmallInteger(), nullable=False),
        sa.Column("n_posts", sa.Integer(), nullable=False),
        sa.Column("targets_observed", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("had_jump", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("computed_at", TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_start", "window_end", name="uq_outcomes_window"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=True),
        sa.Column("affected_topics", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", name="uq_entities_canonical"),
    )

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], name="fk_entity_aliases_entity"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias", name="uq_entity_aliases_alias"),
    )

    op.create_table(
        "model_metrics_live",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recorded_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("window_days", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "drift_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("alert_type", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW trump_posts AS
        SELECT i.*
        FROM items i
        INNER JOIN raw_items r ON r.id = i.raw_item_id
        INNER JOIN sources s ON s.id = r.source_id
        WHERE COALESCE(s.metadata->>'trump_primary', 'false') = 'true';
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS trump_posts;")
    op.drop_table("drift_alerts")
    op.drop_table("model_metrics_live")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
    op.drop_table("events")
    op.drop_table("outcomes")
    op.drop_table("predictions")
    op.drop_table("models")
    op.drop_table("feature_sets")
    op.drop_table("taxonomy_versions")
    op.drop_table("gold_standard")
    op.drop_table("valence_annotations")
    op.execute("DROP TABLE IF EXISTS items CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw_items CASCADE;")
    op.drop_table("sources")
