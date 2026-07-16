"""029 — runs.qa_verdict_l1 / qa_verdict_l2 JSONB columns

Per the v2-QA under-leveraged matrix §C5 finding (2026-06-07), 2 of 5
real DMA packages (Odlum_Brown + Calprivate) ship BOTH a first-pass
(L1) verdict AND a final (L2) verdict, capturing a 2-stage QA
escalation chain (e.g. L1=PASS, L2=PASS_WITH_NOTES). The previous
parser dropped both — qa_verdict was loaded onto `IngestedPackage`
but never persisted or surfaced; L1 was missed entirely.

This migration adds:
  runs.qa_verdict_l1 JSONB - the first-pass verdict (NULL when the
                             package shipped only an L2 verdict, as
                             with Alma / WSFS / Nicola).
  runs.qa_verdict_l2 JSONB - the final/L2 verdict (replaces the
                             silent parse-and-drop on the old
                             qa_verdict field).

Surfaces on the D6 Gates tab as a top-of-tab "QA verdict chain" card.

Idempotent: ADD COLUMN IF NOT EXISTS within a DO $$ ... END $$ block,
matching the pattern from migration 018.
"""
from alembic import op

revision = "029_runs_qa_verdicts"
down_revision = "028_caps_applied_log"
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
                        ADD COLUMN IF NOT EXISTS qa_verdict_l1 JSONB;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
                BEGIN
                    ALTER TABLE runs
                        ADD COLUMN IF NOT EXISTS qa_verdict_l2 JSONB;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS qa_verdict_l2")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS qa_verdict_l1")
