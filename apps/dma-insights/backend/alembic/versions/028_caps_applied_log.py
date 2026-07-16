"""028 — caps_applied_log table

Per the v2-QA under-leveraged matrix §C10 finding (2026-06-07), 4 of 5
real DMA packages ship `07_governance/caps_applied_log.csv` with cap-
event rows that surface WHY a particular subcap was ceiling-capped
(evidence ceiling, severity ceiling, regulatory ceiling, …).

Counts per real fixture:
  Alma         8
  Calprivate 115
  Nicola       8
  Odlum       10
  WSFS         0  (embeds equivalent semantics in subcap_scores.caps_applied)

Total 141 cap events across 4 folders. Surfaces "this subcap scored
M2.5 because IR-003 severity capped it" defensibility on D6 Health
Gates tab.

Idempotent: CREATE TABLE IF NOT EXISTS; CREATE INDEX IF NOT EXISTS.
Re-ingest semantics: DELETE-then-INSERT per run_id (matches the
issue_register pattern at package_persist.py:980).
"""
from alembic import op

revision = "028_caps_applied_log"
down_revision = "027_firmographics_parsed_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS caps_applied_log (
            id            BIGSERIAL PRIMARY KEY,
            run_id        UUID NOT NULL,
            entity_id     UUID NOT NULL,
            log_id        VARCHAR(64) NOT NULL,
            subcap_id     VARCHAR(64) NOT NULL,
            cap_type      VARCHAR(64),
            trigger_condition TEXT,
            cap_ceiling   VARCHAR(32),
            trigger_evidence TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            affected_categories TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            severity      VARCHAR(32),
            date_applied  VARCHAR(32),
            recalc_verified VARCHAR(32),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Per-run lookup index (D6 Health Gates tab loads by run).
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_caps_applied_log_run
            ON caps_applied_log (run_id, subcap_id)
    """)
    # Per-entity lookup for cross-run analyses (e.g. "which caps
    # repeatedly trigger for this entity?").
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_caps_applied_log_entity
            ON caps_applied_log (entity_id, created_at DESC)
    """)
    # Uniqueness within a run: same log_id should not appear twice.
    # Allows DELETE-then-INSERT re-ingest without unique violations.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_caps_applied_log_run_logid
            ON caps_applied_log (run_id, log_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_caps_applied_log_run_logid")
    op.execute("DROP INDEX IF EXISTS ix_caps_applied_log_entity")
    op.execute("DROP INDEX IF EXISTS ix_caps_applied_log_run")
    op.execute("DROP TABLE IF EXISTS caps_applied_log")
