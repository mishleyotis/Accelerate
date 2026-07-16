"""005 — alerts, safeguard_gates, peer_benchmarks, platform_scores, issue_register

Revision ID: 005_alerts_health
Revises: 004_evidence_insights_recs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_alerts_health"
down_revision = "004_evidence_insights_recs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("linked_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("linked_e_ids", postgresql.ARRAY(sa.String(16))),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("resolution", sa.String(32)),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low','info')",
            name="alerts_severity_chk",
        ),
    )
    op.create_index("ix_alerts_open", "alerts", ["entity_id", "opened_at"],
                    postgresql_where=sa.text("closed_at IS NULL"))

    op.create_table(
        "alert_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "LENGTH(note) >= 50 OR action <> 'waive'",
            name="alert_actions_waive_note_chk",
        ),
    )
    op.create_index("ix_alert_actions_alert", "alert_actions", ["alert_id"])

    op.create_table(
        "safeguard_gates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gate_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('PASS','PARTIAL','FAIL','DEFERRED')",
            name="safeguard_gates_status_chk",
        ),
        sa.UniqueConstraint("run_id", "gate_id", name="uq_safeguard_run_gate"),
    )

    op.create_table(
        "peer_benchmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("subvertical", sa.String(8), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("ccg_catalog_version", sa.String(16), nullable=False),
        sa.Column("median", sa.Numeric(3, 2), nullable=False),
        sa.Column("p25", sa.Numeric(3, 2)),
        sa.Column("p75", sa.Numeric(3, 2)),
        sa.Column("n", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("subvertical", "subcap_id", "ccg_catalog_version",
                            name="uq_peer_subv_subcap_ver"),
    )
    op.create_index("ix_peer_benchmarks_subcap", "peer_benchmarks", ["subcap_id"])

    op.create_table(
        "platform_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_id", sa.String(64), nullable=False),
        sa.Column("fit_score", sa.Numeric(4, 2), nullable=False),
        sa.Column("readiness_index", sa.String(16), nullable=False),
        sa.Column("prerequisite_checks", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("addressable_subcap_ids", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("state", sa.String(32), nullable=False, server_default="READY"),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "readiness_index IN ('green','amber','red')",
            name="platform_scores_readiness_chk",
        ),
        sa.CheckConstraint(
            "state IN ('READY','PENDING_REVIEW','INSUFFICIENT_EVIDENCE','RECOMPUTE_NEEDED')",
            name="platform_scores_state_chk",
        ),
        sa.UniqueConstraint("run_id", "platform_id", name="uq_platform_run_platform"),
    )

    op.create_table(
        "issue_register",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_id", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("opened_on", sa.Date),
        sa.Column("resolved_on", sa.Date),
        sa.Column("linked_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("source_path", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("run_id", "issue_id", name="uq_issue_run_issue"),
    )


def downgrade() -> None:
    op.drop_table("issue_register")
    op.drop_table("platform_scores")
    op.drop_table("peer_benchmarks")
    op.drop_table("safeguard_gates")
    op.drop_table("alert_actions")
    op.drop_table("alerts")
