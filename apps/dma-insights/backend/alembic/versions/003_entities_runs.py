"""003 — entities, runs, firmographics

Revision ID: 003_entities_runs
Revises: 002_identity
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_entities_runs"
down_revision = "002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_id", sa.String(32), nullable=False, unique=True),
        sa.Column("domain", sa.String(255)),
        sa.Column("subvertical", sa.String(8)),
        sa.Column("lobs", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("hq_country", sa.String(8)),
        sa.Column("hq_region", sa.String(64)),
        sa.Column("drive_folder_id", sa.String(64)),
        sa.Column("drive_folder_name", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("explorium_synced_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED','MERGED','PENDING_REVIEW')",
            name="entities_status_chk",
        ),
    )
    op.create_index("ix_entities_subvertical", "entities", ["subvertical"])
    op.create_index("ix_entities_drive_folder_id", "entities", ["drive_folder_id"], unique=True,
                    postgresql_where=sa.text("drive_folder_id IS NOT NULL"))
    op.create_index("ix_entities_name_trgm", "entities", ["name"],
                    postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"})

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(32), nullable=False, unique=True),
        sa.Column("parent_request_id", sa.String(32)),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("evidence_mode", sa.String(16), nullable=False, server_default="public"),
        sa.Column("status", sa.String(32), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("ccg_catalog_version", sa.String(16), nullable=False, server_default="v7.0"),
        sa.Column("scqa", postgresql.JSONB),
        sa.Column("why_now_signals", postgresql.JSONB),
        sa.Column("top_findings", postgresql.JSONB),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("superseded_by_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("batch_history", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS','ACTIVE','SUPERSEDED','STALE','FAILED','PENDING_REVIEW')",
            name="runs_status_chk",
        ),
        sa.CheckConstraint(
            "evidence_mode IN ('public','hybrid')",
            name="runs_evidence_mode_chk",
        ),
        sa.CheckConstraint(
            "data_source IN ('DRIVE_PARSE','PROJECT_API','MANUAL_BACKFILL')",
            name="runs_data_source_chk",
        ),
    )
    op.create_index("ix_runs_entity", "runs", ["entity_id"])
    op.create_index("ix_runs_status_active", "runs", ["entity_id", "status"],
                    postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_index("ix_runs_request_id", "runs", ["request_id"], unique=True)

    op.create_table(
        "firmographics",
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("aum_usd", sa.Numeric(20, 2)),
        sa.Column("revenue_usd", sa.Numeric(20, 2)),
        sa.Column("headcount", sa.Integer),
        sa.Column("hq_address", sa.Text),
        sa.Column("primary_regulator", sa.String(64)),
        sa.Column("leadership", postgresql.JSONB),
        sa.Column("thought_leadership", postgresql.JSONB),
        sa.Column("sentiment", postgresql.JSONB),
        sa.Column("clay_synced_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("tl_synced_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("sentiment_synced_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("explorium_synced_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("firmographics")
    op.drop_table("runs")
    op.drop_table("entities")
