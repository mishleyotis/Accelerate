"""006 — tech_stack_entries, timeline_events, import_*

Revision ID: 006_tech_admin
Revises: 005_alerts_health
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_tech_admin"
down_revision = "005_alerts_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tech_stack_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tech_id", sa.String(64), nullable=False),
        sa.Column("vendor", sa.String(128), nullable=False),
        sa.Column("product", sa.String(255), nullable=False),
        sa.Column("layer", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("evidence_e_ids", postgresql.ARRAY(sa.String(16))),
        sa.Column("linked_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("detected_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "layer IN ('foundation','platform','application','intelligence')",
            name="tech_layer_chk",
        ),
        sa.UniqueConstraint("entity_id", "tech_id", name="uq_tech_entity_tech"),
    )

    op.create_table(
        "timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("e_id", sa.String(16)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_timeline_entity_date", "timeline_events", ["entity_id", "event_date"])

    op.create_table(
        "import_scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_kind", sa.String(32), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("files_seen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("files_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("files_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("files_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("summary", postgresql.JSONB),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.CheckConstraint(
            "status IN ('RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="import_scans_status_chk",
        ),
    )

    op.create_table(
        "import_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("import_scans.id", ondelete="SET NULL")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("drive_file_id", sa.String(64), nullable=False),
        sa.Column("drive_modified_time", sa.TIMESTAMP(timezone=True)),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_kind", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("sha256", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="DETECTED"),
        sa.Column("parser_warnings", postgresql.JSONB),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "status IN ('DETECTED','PROCESSING','OK','PENDING_REVIEW','FAILED','SKIPPED')",
            name="import_files_status_chk",
        ),
        sa.UniqueConstraint("drive_file_id", "drive_modified_time",
                            name="uq_import_drive_mtime"),
    )
    op.create_index("ix_import_files_status", "import_files", ["status"])

    op.create_table(
        "score_stream_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="QUEUED"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("error_text", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("score_stream_jobs")
    op.drop_table("import_files")
    op.drop_table("import_scans")
    op.drop_table("timeline_events")
    op.drop_table("tech_stack_entries")
