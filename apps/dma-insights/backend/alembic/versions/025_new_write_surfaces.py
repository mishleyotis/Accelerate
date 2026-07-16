"""025 — new write surfaces for the uploaded-wireframe rebuild:
insight_annotations (B-7), focus_area_kpi_overrides (B-8), notifications (B-9).

Revision ID: 025_new_write_surfaces
Revises: 024_post_commit_trigger

These three surfaces are net-new in the 2026-06 wireframe and have no
existing producer:

- ``insight_annotations`` — analyst notes on an insight card (D2 InsightModal
  "Annotations" tab): free-text body + workflow status + optional Salesforce
  opportunity id. Append-only per (run, ic, author); the UI shows the latest.
- ``focus_area_kpi_overrides`` — per-client customisation of a focus area's
  KPI strip (D3 focus-area CustomizableKpiStrip): each KPI's source mode
  (public-inference / client-provided / hidden) + optional overridden
  current/target values. UPSERT keyed by (entity, focus_area, kpi_label).
- ``notifications`` — per-user notification feed (TopBar NotificationsPopover):
  kind + title + body + optional entity/route deep-link + seen_at.

B-3 (multi-year financials) does NOT need a column here — it is shaped at
read time from the existing ``firmographics.financial_highlights`` JSONB.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "025_new_write_surfaces"
down_revision = "024_post_commit_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── B-7 insight_annotations ──────────────────────────────────────────
    op.create_table(
        "insight_annotations",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "entity_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("ic_id", sa.String(16), nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'PENDING'")),
        sa.Column("sf_opp_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIONED','PENDING','SUPERSEDED')",
            name="ck_insight_annotations_status",
        ),
        sa.CheckConstraint(
            "role IN ('AE','ANALYST','ADMIN')",
            name="ck_insight_annotations_role",
        ),
    )
    op.execute(
        "CREATE INDEX ix_insight_annotations_run_ic "
        "ON insight_annotations (run_id, ic_id, created_at DESC)"
    )

    # ── B-8 focus_area_kpi_overrides ─────────────────────────────────────
    op.create_table(
        "focus_area_kpi_overrides",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "entity_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fa_id", sa.String(32), nullable=False),
        sa.Column("kpi_label", sa.String(255), nullable=False),
        sa.Column("source_mode", sa.String(16), nullable=False,
                  server_default=sa.text("'public'")),
        sa.Column("current_value", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "source_mode IN ('public','client','hidden')",
            name="ck_fa_kpi_source_mode",
        ),
        sa.UniqueConstraint(
            "entity_id", "fa_id", "kpi_label",
            name="uq_fa_kpi_entity_fa_label",
        ),
    )

    # ── B-9 notifications ────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "entity_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "kind IN ('alert','completion','system')",
            name="ck_notifications_kind",
        ),
    )
    op.execute(
        "CREATE INDEX ix_notifications_user_unseen "
        "ON notifications (user_id, created_at DESC) "
        "WHERE seen_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_notifications_user_created "
        "ON notifications (user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created", "notifications")
    op.drop_index("ix_notifications_user_unseen", "notifications")
    op.drop_table("notifications")
    op.drop_table("focus_area_kpi_overrides")
    op.drop_index("ix_insight_annotations_run_ic", "insight_annotations")
    op.drop_table("insight_annotations")
