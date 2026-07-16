"""014 — build_qa_gates (CI verdict ledger surfaced at /admin/build-qa)

Revision ID: 014_build_qa_gates
Revises: 013_ccg_run_pinning
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014_build_qa_gates"
down_revision = "013_ccg_run_pinning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "build_qa_gates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("stage", sa.String(8), nullable=False),
        sa.Column("gate_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("acceptance_criteria", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("evidence_url", sa.Text),
        sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("evaluated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("build_id", sa.String(64)),
        sa.Column("git_sha", sa.String(40)),
        sa.UniqueConstraint("stage", "gate_id", "build_id", name="uq_qa_gate_build"),
        sa.CheckConstraint(
            "status IN ('PENDING','PASS','PARTIAL','FAIL','DEFERRED')",
            name="build_qa_gates_status_chk",
        ),
    )
    op.create_index("ix_build_qa_gates_stage", "build_qa_gates", ["stage", "status"])


def downgrade() -> None:
    op.drop_table("build_qa_gates")
