"""004 — subcap_scores, evidence_index, insight_cards, recommendations

Revision ID: 004_evidence_insights_recs
Revises: 003_entities_runs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_evidence_insights_recs"
down_revision = "003_entities_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subcap_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("source_subcap_id", sa.String(32)),
        sa.Column("alias_resolved_from", sa.String(16)),
        sa.Column("score", sa.Numeric(3, 2), nullable=False),
        sa.Column("band", sa.CHAR(2), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("rationale", sa.Text),
        sa.Column("peer_median", sa.Numeric(3, 2)),
        sa.Column("peer_gap", sa.Numeric(3, 2)),
        sa.Column("is_thin_evidence", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cap_applied", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cap_reason", sa.Text),
        sa.Column("platform_tags", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("score BETWEEN 1.0 AND 5.0", name="subcap_scores_score_chk"),
        sa.CheckConstraint("band IN ('M1','M2','M3','M4','M5')", name="subcap_scores_band_chk"),
        sa.UniqueConstraint("run_id", "subcap_id", name="uq_subcap_scores_run_subcap"),
    )
    op.create_index("ix_subcap_scores_entity_subcap", "subcap_scores",
                    ["entity_id", "subcap_id"])
    op.create_index("ix_subcap_scores_run", "subcap_scores", ["run_id"])

    op.create_table(
        "evidence_index",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("e_id", sa.String(16), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("tier", sa.SmallInteger, nullable=False),
        sa.Column("recency_months", sa.SmallInteger),
        sa.Column("published_date", sa.Date),
        sa.Column("linked_subcap_ids", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("tier BETWEEN 1 AND 8", name="evidence_index_tier_chk"),
        sa.UniqueConstraint("run_id", "e_id", name="uq_evidence_run_eid"),
    )
    op.create_index("ix_evidence_entity", "evidence_index", ["entity_id"])
    op.create_index("ix_evidence_linked_subcaps", "evidence_index", ["linked_subcap_ids"],
                    postgresql_using="gin")

    op.create_table(
        "insight_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ic_id", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("what_text", sa.Text, nullable=False),
        sa.Column("why_text", sa.Text, nullable=False),
        sa.Column("so_what_text", sa.Text, nullable=False),
        sa.Column("linked_subcap_id", sa.String(32), nullable=False),
        sa.Column("linked_e_ids", postgresql.ARRAY(sa.String(16)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')",
            name="insight_cards_severity_chk",
        ),
        sa.UniqueConstraint("run_id", "ic_id", name="uq_insight_run_icid"),
    )
    op.create_index("ix_insight_cards_entity_severity", "insight_cards",
                    ["entity_id", "severity"])

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rec_id", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("target_subcap_ids", postgresql.ARRAY(sa.String(32)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("platform_id", sa.String(64)),
        sa.Column("addressable_offerings", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("cited_l4_features", postgresql.ARRAY(sa.Text), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("cited_constructs", postgresql.ARRAY(sa.String(128)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("cited_agents", postgresql.ARRAY(sa.String(64)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("uplift_per_pillar", postgresql.JSONB),
        sa.Column("effort_band", sa.String(16)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("run_id", "rec_id", name="uq_recs_run_recid"),
    )
    op.create_index("ix_recs_entity_platform", "recommendations", ["entity_id", "platform_id"])

    op.create_table(
        "annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_ref", sa.String(64), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_annotations_target", "annotations",
                    ["entity_id", "target_type", "target_ref"])


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_table("recommendations")
    op.drop_table("insight_cards")
    op.drop_table("evidence_index")
    op.drop_table("subcap_scores")
