"""041 - entity_peers (individual peer roster + scores)

QA audit 2026-06-15: the `06_peers/peer_scores_*.json` roster (each named
comparator with per-category scores + rationale) was parsed into `pkg.peers`
but consumed ONLY as a row count — individual peer identities/scores were
dropped, so no surface could show "who are this client's peers and how do they
score". Only the aggregate cohort medians survived (peer_benchmarks).

`entity_peers` persists the roster so the D5 Context "Peer comparison" card can
render each named peer's overall maturity + per-pillar scores vs the client.
Populated by `app.scripts.derive_peers` (corpus scan, matched via the package
run_manifest run_id → runs.request_id). Best-effort surface — absent for
packages that ship no peer_scores (honest-empty, not gated).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_entity_peers"
down_revision = "040_alerts_producer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_peers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("peer_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(80), nullable=True),
        sa.Column("scoring_date", sa.Date(), nullable=True),
        sa.Column("overall_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("category_scores", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_sources", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(40), server_default="package"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("entity_id", "peer_name", name="uq_entity_peers_entity_peer"),
    )
    op.create_index("ix_entity_peers_entity", "entity_peers", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_peers_entity", table_name="entity_peers")
    op.drop_table("entity_peers")
