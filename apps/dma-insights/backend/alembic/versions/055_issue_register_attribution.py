"""055 - issue_register DMA-impact attribution (kind/status/dma_impact/caps)

The Context-page Issue Register defect family (2026-07-06): the pack
rendered assessment-QA meta rows ("Missing governance artifact:
caps_applied_log.csv"), blank titles, and no DMA-impact attribution
because the table could not distinguish the client's REAL business
issues from the bot's own QA checklist, and dropped the parsed
status / per-capability cap levels on the floor.

Adds (all additive; old rows keep serving):
  - ``kind``       'client' | 'assessment_qa' — only 'client' rows
                   surface on the AE-facing Context register + heatmap
                   overlay; QA rows stay available for the Health page.
  - ``status``     canonical OPEN/RESOLVED from the register's status
                   cell ("SETTLED", "Resolved Jan 2025") — before this,
                   resolution was derivable only from a resolved_on
                   date that ingest never wrote (0/662 resolved).
  - ``dma_impact`` one-line grounded attribution composed from the
                   row's own fields ("Caps P1C2 at M3.0, P3C3 at M2.5 —
                   FDIC, open").
  - ``caps``       JSONB {P-code: cap level} mined from
                   Capability_Impact / Ceiling_Impact / Cap_Value cells.

Backfill: legacy rows whose title matches the assessment-QA fingerprint
(governance-artifact filenames, run_manifest / citation-density /
sheet-naming checks) are re-kinded 'assessment_qa' so they vanish from
the AE registers immediately, without waiting for a re-ingest. The
regex mirrors ``package_csvs.ASSESSMENT_QA_TITLE_RE`` (kept in
lock-step; parser-side is canonical).

Idempotent: IF NOT EXISTS guards; the backfill only flips rows still
kinded 'client'.
"""
from alembic import op

revision = "055_issue_register_attribution"
down_revision = "054_category_display_names"
branch_labels = None
depends_on = None

# Keep in lock-step with app.services.parsers.package_csvs.ASSESSMENT_QA_TITLE_RE.
_QA_TITLE_SQL_RE = (
    r"governance artifact|run_manifest|caps_applied|contradiction_log|"
    r"reasoning_chain|citation (density|coverage)|e-?id density|"
    r"peer references|sheets? nam(e|ing)|patch block|"
    r"missing required fields|rationales? missing|workbook export|"
    r"unique e-?ids|evidence mode|\.(csv|json|xlsx)\M"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE issue_register
            ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'client',
            ADD COLUMN IF NOT EXISTS status VARCHAR(16),
            ADD COLUMN IF NOT EXISTS dma_impact TEXT,
            ADD COLUMN IF NOT EXISTS caps JSONB
        """
    )
    # Legacy meta rows → assessment_qa (guarded: only rows still
    # default-kinded; a re-ingest with the fixed parser always wins).
    op.execute(
        f"""
        UPDATE issue_register
        SET kind = 'assessment_qa'
        WHERE kind = 'client'
          AND title ~* '{_QA_TITLE_SQL_RE}'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE issue_register
            DROP COLUMN IF EXISTS caps,
            DROP COLUMN IF EXISTS dma_impact,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS kind
        """
    )
