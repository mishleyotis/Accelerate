"""020 — job_executions: every admin-triggered or scheduler-triggered
worker run lands here so the Admin UI can show real "Last run …" + status.

Revision ID: 020_job_executions
Revises: 019_vertex_synthesis_cache

State-transition contract for `status`:
  running     — row inserted at trigger; workers UPDATE on each step
  succeeded   — worker completed; result counts populated
  failed      — worker raised; error_message + stderr_tail populated
  cancelled   — admin/operator killed the row; worker exited cleanly

Trigger sources (`trigger_source`):
  admin_ui    — POST /api/v1/admin/jobs/{job_name}:execute
  scheduler   — Cloud Run Jobs scheduled trigger
  pubsub      — dma.ingest.completed subscriber
  cli         — direct `python -m workers.<job>` invocation

Workers MUST UPDATE the matching row at start (already running),
at meaningful milestones (folders_seen += …, files_parsed += …),
and at completion (set completed_at + duration_sec + final counts).
The endpoint creates the row in 'running' state synchronously so the
UI can poll for it immediately.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "020_job_executions"
down_revision = "019_vertex_synthesis_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=True),
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("triggered_by_email", sa.String(255), nullable=True),
        sa.Column("trigger_source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Numeric(10, 2), nullable=True),
        # Optional entity scope — peer_patterns / intelligence_recompute
        # can run per-entity; drive_crawler is global.
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        # Result detail — all nullable so a job can populate only the
        # ones that make sense for it (drive_crawler fills folders_*,
        # embedder fills rows_*, etc.).
        sa.Column("folders_seen", sa.Integer(), nullable=True),
        sa.Column("folders_new", sa.Integer(), nullable=True),
        sa.Column("folders_changed", sa.Integer(), nullable=True),
        sa.Column("files_parsed", sa.Integer(), nullable=True),
        sa.Column("files_skipped", sa.Integer(), nullable=True),
        sa.Column("files_errored", sa.Integer(), nullable=True),
        sa.Column("rows_added", sa.Integer(), nullable=True),
        sa.Column("rows_updated", sa.Integer(), nullable=True),
        sa.Column("rows_deleted", sa.Integer(), nullable=True),
        sa.Column(
            "parser_warnings", postgresql.JSONB(), nullable=True
        ),
        sa.Column("stderr_tail", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "args", postgresql.JSONB(), nullable=True,
            comment="raw {mode, ...} dict passed to the executor",
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','cancelled')",
            name="ck_job_executions_status",
        ),
        sa.CheckConstraint(
            "trigger_source IN ('admin_ui','scheduler','pubsub','cli')",
            name="ck_job_executions_trigger_source",
        ),
    )
    op.execute(
        "CREATE INDEX ix_job_executions_job_started "
        "ON job_executions (job_name, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_job_executions_running "
        "ON job_executions (status) WHERE status = 'running'"
    )
    op.execute(
        "CREATE INDEX ix_job_executions_entity_started "
        "ON job_executions (entity_id, started_at DESC) "
        "WHERE entity_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_job_executions_entity_started", "job_executions")
    op.drop_index("ix_job_executions_running", "job_executions")
    op.drop_index("ix_job_executions_job_started", "job_executions")
    op.drop_table("job_executions")
