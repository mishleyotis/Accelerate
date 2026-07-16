"""044 - tech_stack prototype alignment (l3_id + status enum)

Brings `tech_stack_entries` onto the prototype's TechStack contract:
  - adds `l3_id` (links a tech entry to one of the five scored platform areas
    — the prototype's tech→platform link; NULL when no scored platform maps).
  - normalises the legacy free-form `status` ('active') onto the prototype
    enum DETECTED | CONFIRMED | CONFIRMED_REMOVED so the API's Literal holds
    without a full re-ingest (evidence-backed rows read as CONFIRMED, the rest
    DETECTED). New ingests write the enum + l3_id directly via the parser.

`product_name` is exposed by the API as an alias of the existing `product`
column — no new column needed.
"""
import sqlalchemy as sa

from alembic import op

revision = "044_tech_stack_prototype_fields"
down_revision = "043_cross_entity_patterns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tech_stack_entries",
        sa.Column("l3_id", sa.String(16), nullable=True),
    )
    op.execute(
        """
        UPDATE tech_stack_entries
        SET status = CASE
            WHEN status IN ('DETECTED', 'CONFIRMED', 'CONFIRMED_REMOVED')
                THEN status
            WHEN COALESCE(cardinality(evidence_e_ids), 0) > 0
                THEN 'CONFIRMED'
            ELSE 'DETECTED'
        END
        """
    )


def downgrade() -> None:
    op.drop_column("tech_stack_entries", "l3_id")
