"""0017 — the why-now signal's kind reaches the card.

The overview.why_now contract declares `kind` in the signal's item schema
and the producer sends it ('M&A', 'LEADERSHIP', 'REGULATORY',
'TECHNOLOGY'), but overview_why_now has no column for it, so the value was
dropped at promotion and the card rendered its badge from nothing. This is
the expand half of expand-migrate-contract: add the column, then the
writer spec sources it, and the next promote fills it. Nullable, so every
already-promoted row stays valid.

Not an invented field: the contract names it, the DDL simply never did.
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE overview_why_now ADD COLUMN IF NOT EXISTS kind TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE overview_why_now DROP COLUMN IF EXISTS kind")
