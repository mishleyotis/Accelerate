"""009 — entity_assignments + ops_* mirror tables + dma_runs_requested

Revision ID: 009_assignments_bot
Revises: 008_streaming
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_assignments_bot"
down_revision = "008_streaming"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(256)),
        sa.Column("confidence", sa.Numeric(4, 2)),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "source IN ('ops_sheet','ops_sheet_backfill','drive_inference',"
            "'admin_manual','bot_request','bot_request_oob')",
            name="entity_assignments_source_chk",
        ),
    )
    op.create_index(
        "uq_entity_assignments_active",
        "entity_assignments",
        ["entity_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_entity_assignments_user_active",
        "entity_assignments",
        ["user_id"],
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_entity_assignments_entity_active",
        "entity_assignments",
        ["entity_id"],
        postgresql_where=sa.text("superseded_at IS NULL"),
    )

    op.create_table(
        "ops_team",
        sa.Column("slack_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("calendar_id", sa.String(255), nullable=False),
        sa.Column("daily_cap", sa.Numeric(3, 1)),
        sa.Column("stretch_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_synced_utc", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("uq_ops_team_name_lower", "ops_team", [sa.text("LOWER(name)")], unique=True)

    op.create_table(
        "ops_requests",
        sa.Column("request_id", sa.String(32), primary_key=True),
        sa.Column("ts_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("requester_slack_id", sa.String(32)),
        sa.Column("requester_name", sa.String(128)),
        sa.Column("submitter_slack_id", sa.String(32)),
        sa.Column("submitter_name", sa.String(128)),
        sa.Column("entity", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("mode", sa.String(16), nullable=False, server_default="public"),
        sa.Column("notes", sa.Text),
        sa.Column("priority", sa.String(16)),
        sa.Column("source", sa.String(32)),
        sa.Column("parent_request_id", sa.String(32)),
        sa.Column("requested_due_date", sa.Date),
        sa.Column("assigned_to", sa.String(64)),
        sa.Column("scheduled_date", sa.Date),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("delivered_date", sa.Date),
        sa.Column("folder_url", sa.Text),
        sa.Column("assessment_url", sa.Text),
        sa.Column("research_url", sa.Text),
        sa.Column("deck_url", sa.Text),
        sa.Column("sla_met", sa.Boolean),
        sa.Column("last_updated_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("workflow_ts", sa.String(32)),
        sa.Column("feedback_status", sa.String(16)),
        sa.Column("feedback_rating", sa.SmallInteger),
        sa.Column("feedback_comments", sa.Text),
        sa.Column("feedback_at_utc", sa.TIMESTAMP(timezone=True)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("last_synced_utc", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("sheet_row_url", sa.Text),
        sa.CheckConstraint("mode IN ('public','hybrid')", name="ops_requests_mode_chk"),
    )
    op.create_index("ix_ops_requests_status", "ops_requests", ["status", "last_updated_utc"])
    op.create_index("ix_ops_requests_assigned_to", "ops_requests", ["assigned_to"])
    op.create_index("ix_ops_requests_entity", "ops_requests", ["entity_id"])

    op.create_table(
        "ops_capacity",
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("assignee", sa.String(64), nullable=False),
        sa.Column("base_cap", sa.Numeric(3, 1), nullable=False),
        sa.Column("stretch_cap", sa.Numeric(3, 1), nullable=False),
        sa.Column("booked_count", sa.Numeric(3, 1), nullable=False),
        sa.Column("blocked_reason", sa.Text),
        sa.Column("last_synced_utc", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("date", "assignee"),
    )

    op.create_table(
        "ops_holidays",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
    )

    op.create_table(
        "ops_audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("s_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_slack_id", sa.String(32)),
        sa.Column("before_json", postgresql.JSONB),
        sa.Column("after_json", postgresql.JSONB),
        sa.UniqueConstraint("request_id", "s_utc", "action", name="uq_ops_audit_replay"),
    )
    op.create_index("ix_ops_audit_request", "ops_audit", ["request_id"])

    op.create_table(
        "ops_historical_stats",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("dma_count", sa.Numeric(12, 1)),
        sa.Column("last_scanned_utc", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "ops_comments",
        sa.Column("comment_id", sa.String(32), primary_key=True),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("ts_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("author_slack_id", sa.String(32)),
        sa.Column("author_name", sa.String(128)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "visibility IN ('internal','external')",
            name="ops_comments_visibility_chk",
        ),
    )
    op.create_index("ix_ops_comments_request", "ops_comments", ["request_id", "ts_utc"])

    op.create_table(
        "ops_ingest_pending",
        sa.Column("pending_key", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(32)),
        sa.Column("ae_slack_id", sa.String(32)),
        sa.Column("ae_name", sa.String(128)),
        sa.Column("entity", sa.String(255)),
        sa.Column("domain", sa.String(255)),
        sa.Column("notes", sa.Text),
        sa.Column("mode", sa.String(16)),
        sa.Column("priority", sa.String(16)),
        sa.Column("deadline_days", sa.Integer),
        sa.Column("deadline_date_iso", sa.Date),
        sa.Column("offered_date_iso", sa.Date),
        sa.Column("offered_assignee", sa.String(64)),
        sa.Column("channel_id", sa.String(64)),
        sa.Column("workflow_ts", sa.String(32)),
        sa.Column("mode_evidence_json", postgresql.JSONB),
        sa.Column("hubbl_flag", sa.Boolean),
        sa.Column("kind", sa.String(32)),
        sa.Column("created_at_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolved_at_utc", sa.TIMESTAMP(timezone=True)),
        sa.Column("resolved_by", sa.String(64)),
    )
    op.create_index("ix_ops_ingest_pending_status", "ops_ingest_pending",
                    ["status", "created_at_utc"])

    op.create_table(
        "dma_runs_requested",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", sa.String(32), nullable=False, unique=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("evidence_mode", sa.String(16), nullable=False),
        sa.Column("is_rerun", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("parent_request_id", sa.String(32)),
        sa.Column("materials_gs_urls", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("bot_payload", postgresql.JSONB, nullable=False),
        sa.Column("bot_response", postgresql.JSONB),
        sa.Column("ops_sheet_row_url", sa.Text),
        sa.Column("state", sa.String(32), nullable=False, server_default="SUBMITTED"),
        sa.Column("last_polled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("poll_progress", postgresql.JSONB),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "state IN ('SUBMITTED','BOT_ACCEPTED','IN_RUN','COMPLETED','FAILED','CANCELLED')",
            name="dma_runs_requested_state_chk",
        ),
        sa.CheckConstraint(
            "evidence_mode IN ('public','hybrid')",
            name="dma_runs_requested_mode_chk",
        ),
    )
    op.create_index("ix_dma_runs_requested_state", "dma_runs_requested",
                    ["state", "last_polled_at"])


def downgrade() -> None:
    op.drop_table("dma_runs_requested")
    op.drop_table("ops_ingest_pending")
    op.drop_table("ops_comments")
    op.drop_table("ops_historical_stats")
    op.drop_table("ops_audit")
    op.drop_table("ops_holidays")
    op.drop_table("ops_capacity")
    op.drop_table("ops_requests")
    op.drop_table("ops_team")
    op.drop_table("entity_assignments")
