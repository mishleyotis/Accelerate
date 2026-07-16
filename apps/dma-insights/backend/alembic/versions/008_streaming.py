"""008 — streaming/SSE state, customer_feedback

Revision ID: 008_streaming
Revises: 007_documents
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_streaming"
down_revision = "007_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sse_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(128), nullable=False),
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_event_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("disconnected_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_sse_user_channel", "sse_subscriptions",
                    ["user_id", "channel"],
                    postgresql_where=sa.text("disconnected_at IS NULL"))

    op.create_table(
        "customer_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rating", sa.SmallInteger),
        sa.Column("comments", sa.Text),
        sa.Column("at_utc", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "rating IS NULL OR (rating BETWEEN 0 AND 10)",
            name="customer_feedback_rating_chk",
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_feedback")
    op.drop_table("sse_subscriptions")
