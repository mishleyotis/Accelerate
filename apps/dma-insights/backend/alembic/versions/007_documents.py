"""007 — document_sections, document_lineage, document_evidence_items, gemini_cache

Revision ID: 007_documents
Revises: 006_tech_admin
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_documents"
down_revision = "006_tech_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("import_files.id", ondelete="SET NULL")),
        sa.Column("section_kind", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("heading", sa.Text),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_doc_sections_run_kind", "document_sections", ["run_id", "section_kind"])

    op.create_table(
        "document_lineage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_ref", sa.String(64), nullable=False),
    )
    op.create_index("ix_doc_lineage_target", "document_lineage",
                    ["target_type", "target_ref"])

    op.create_table(
        "document_evidence_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("e_id", sa.String(16), nullable=False),
        sa.Column("quoted_excerpt", sa.Text),
    )

    op.create_table(
        "gemini_cache",
        sa.Column("cache_key", sa.String(128), primary_key=True),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("response_text", sa.Text, nullable=False),
        sa.Column("response_json", postgresql.JSONB),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("validators_passed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("hallucination_flags", postgresql.JSONB),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_gemini_cache_expires", "gemini_cache", ["expires_at"])

    op.create_table(
        "gemini_hallucination_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("cache_key", sa.String(128)),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("flags", postgresql.JSONB, nullable=False),
        sa.Column("response_text", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_table("gemini_hallucination_alerts")
    op.drop_table("gemini_cache")
    op.drop_table("document_evidence_items")
    op.drop_table("document_lineage")
    op.drop_table("document_sections")
