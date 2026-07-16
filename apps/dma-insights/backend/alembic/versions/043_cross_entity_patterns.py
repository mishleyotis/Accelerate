"""043 - cross_entity_patterns (D6 Health cross-entity recurring patterns)

Output table for the `cross_entity_patterns` worker: per (subvertical,
catalogue_version) cohort, the sub-capabilities that recur across >= 3
entities as a below-peer-median gap (`subcap_gap`) or an open issue
(`issue_theme`). Mirrors `peer_archetypes` (full DELETE/INSERT per cohort;
a single `insufficient_data` marker row when the cohort has < 3 entities).
Powers the D6 Health "Patterns" tab; empty until the worker runs in the
deploy env.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043_cross_entity_patterns"
down_revision = "042_rec_insight_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cross_entity_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("subvertical", sa.String(8), nullable=False),
        sa.Column("catalogue_version", sa.String(16), nullable=False),
        sa.Column("pattern_type", sa.String(24), nullable=False),
        sa.Column("pattern_key", sa.String(64), nullable=False),
        sa.Column("pattern_label", sa.Text(), nullable=False),
        sa.Column("primary_subcap_id", sa.String(32), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("affected_entity_ids",
                  postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                  nullable=False, server_default=sa.text("'{}'::uuid[]")),
        sa.Column("severity_mix", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("median_peer_gap", sa.Numeric(4, 2), nullable=True),
        sa.Column("sample_subcap_ids", postgresql.ARRAY(sa.String(32)),
                  nullable=False, server_default=sa.text("'{}'::varchar[]")),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("subvertical", "catalogue_version", "pattern_type",
                            "pattern_key",
                            name="uq_cross_entity_patterns_cohort_key"),
    )
    op.create_index("ix_cross_entity_patterns_cohort", "cross_entity_patterns",
                    ["subvertical", "catalogue_version"])
    op.create_index("ix_cross_entity_patterns_affected", "cross_entity_patterns",
                    ["affected_entity_ids"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_cross_entity_patterns_affected",
                  table_name="cross_entity_patterns")
    op.drop_index("ix_cross_entity_patterns_cohort",
                  table_name="cross_entity_patterns")
    op.drop_table("cross_entity_patterns")
