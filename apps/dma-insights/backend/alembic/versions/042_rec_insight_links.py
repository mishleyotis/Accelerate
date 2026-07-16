"""042 - rec_insight_links (insight→rec source link + rec prerequisite chain)

Closes the two deferred W5 overlay items. Both columns are populated at
ingest and only carry data after the 94 packages are re-ingested; they are
nullable / default-empty so the live app keeps working pre-reingest.

- insight_cards.source_rec_id: the recommendation an insight was DERIVED from
  (`insights_from_recommendations` carries the rec_id forward instead of
  discarding it). Powers the D2 InsightModal "Linked recommendation" callout
  (faithful single link; the endpoint also computes a subcap-join
  `related_rec_ids` fallback that needs no re-ingest).
- recommendations.prerequisite_rec_ids: sibling rec_ids that must ship first,
  parsed from the source `recommendation_validation.json` `prerequisite`
  clause (e.g. Greenstone R8 <- R2 + R5). Powers the D4 RecommendationModal
  Dependencies tab / DependencyMap; "unlocks" is the read-time inverse.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "042_rec_insight_links"
down_revision = "041_entity_peers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insight_cards",
        sa.Column("source_rec_id", sa.String(16), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "prerequisite_rec_ids",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "prerequisite_rec_ids")
    op.drop_column("insight_cards", "source_rec_id")
