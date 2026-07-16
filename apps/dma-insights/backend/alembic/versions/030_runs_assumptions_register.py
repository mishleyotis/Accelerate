"""030 — runs.assumptions_register JSONB

Per the v2-QA under-leveraged matrix §C11 finding (2026-06-07), 2 of 5
real DMA packages ship the analyst's assumptions register:

  Calprivate `08_appendices/assumptions_register.json`   (5 entries)
  Nicola     `07_governance/A9_Assumptions_Register.csv` (~8 entries)

Surfaces "we assumed FIS Horizon is the core banking system (MEDIUM-HIGH
confidence) because CTO Birkmann worked at Pacific Mercantile Bank — a
documented FIS Horizon client" on the D1 ClientOverview footer card.
Defensible rationale for AE sales calls.

Stored as JSONB list on the run row (matches the qa_verdict_l1/l2
pattern from migration 029). Avoids a new table when the per-row read
pattern is "show all assumptions for the active run" — a single-row
JSONB fetch is faster than a JOIN.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "030_runs_assumptions_register"
down_revision = "029_runs_qa_verdicts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'runs'
            ) THEN
                BEGIN
                    ALTER TABLE runs
                        ADD COLUMN IF NOT EXISTS assumptions_register JSONB;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS assumptions_register")
