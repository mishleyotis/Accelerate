"""031 — runs.audit_logs JSONB

Per the v2-QA under-leveraged matrix §C7 finding (2026-06-07), 2 of 5
real DMA packages ship bot governance audit logs:

  Nicola : 07_governance/reasoning_chain_log.json (12 subcap chains
           with 5-step decision_path each) + contradiction_log.csv (3 rows)
  Odlum  : 07_governance/contradiction_log.csv (3 rows)

Surfaces "the bot reached M2.0 via these 5 reasoning steps; contradiction
CONTRA-001 was resolved with E-113 as winner" defensibility on D6 Health
"Audit" tab (Analyst-only role gate). Reviewer trust gap closed —
auditor can confirm the bot's logic aligns with the final scoring
without re-deriving from raw evidence.

Stored as JSONB on the run row (matches the qa_verdict_l1/l2 +
assumptions_register pattern from migrations 029-030). Avoids a new
table when the per-row read pattern is "show all audit logs for the
active run" — a single-row JSONB fetch is faster than a JOIN.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "031_runs_audit_logs"
down_revision = "030_runs_assumptions_register"
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
                        ADD COLUMN IF NOT EXISTS audit_logs JSONB;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS audit_logs")
