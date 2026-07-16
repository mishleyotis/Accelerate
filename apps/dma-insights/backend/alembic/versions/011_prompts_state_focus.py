"""011 — prompt_templates, user_session_state, focus_areas

Revision ID: 011_prompts_state_focus
Revises: 010_embeddings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011_prompts_state_focus"
down_revision = "010_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("surface_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("response_schema", postgresql.JSONB, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("surface_id", "version", name="uq_prompt_surface_version"),
    )
    op.create_index("uq_prompt_active", "prompt_templates", ["surface_id"], unique=True,
                    postgresql_where=sa.text("active = TRUE"))

    op.create_table(
        "user_session_state",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state_key", sa.String(64), nullable=False),
        sa.Column("blob", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("user_id", "state_key"),
    )

    op.create_table(
        "focus_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_quote", sa.Text, nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("page_number", sa.Integer),
        sa.Column("financial_reference", sa.Text),
        sa.Column("involved_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_focus_areas_entity", "focus_areas", ["entity_id"])


def downgrade() -> None:
    # `IF EXISTS` defends against migration 018 (intelligence layer)
    # also dropping focus_areas in its downgrade — a base-to-head
    # round-trip would otherwise fail with UndefinedTable here.
    op.execute("DROP TABLE IF EXISTS focus_areas")
    op.execute("DROP TABLE IF EXISTS user_session_state")
    op.execute("DROP TABLE IF EXISTS prompt_templates")
