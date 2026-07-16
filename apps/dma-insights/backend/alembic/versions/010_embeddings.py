"""010 — pgvector embedding tables

Revision ID: 010_embeddings
Revises: 009_assignments_bot
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "010_embeddings"
down_revision = "009_assignments_bot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_embeddings",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("evidence_index.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedded_text", sa.Text, nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.execute(
        "CREATE INDEX ix_evidence_embeddings_cos "
        "ON evidence_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )

    op.create_table(
        "insight_embeddings",
        sa.Column("insight_card_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("insight_cards.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedded_text", sa.Text, nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.execute(
        "CREATE INDEX ix_insight_embeddings_cos "
        "ON insight_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )

    op.create_table(
        "recommendation_embeddings",
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("recommendations.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedded_text", sa.Text, nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.execute(
        "CREATE INDEX ix_recommendation_embeddings_cos "
        "ON recommendation_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )


def downgrade() -> None:
    op.drop_table("recommendation_embeddings")
    op.drop_table("insight_embeddings")
    op.drop_table("evidence_embeddings")
