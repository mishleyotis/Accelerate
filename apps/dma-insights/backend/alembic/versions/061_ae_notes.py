"""061 - AE notes on rec cards / roadmap items + recalibration assessments

New prototype feature (2026-07-06): recommendation cards and roadmap
items are drillable and carry an AE-notes segment. Notes may flag
``recalibrate=true`` — field intelligence the AE believes should change
findings/scores. That flag NEVER mutates any score directly: it feeds a
Gemini-backed impact-assessment path (services/ae_notes) that SIMULATES
what would change (which scores/findings, with reasoning + E-ID-cited
evidence) and stores the assessment for admin review with full
provenance (model, created_at, grounding E-IDs, validators_passed).

Tables:
  ae_notes — one row per note. ``target_kind``/``target_id`` address the
    display grain (rec_id / phase-N / ic_id) so notes survive re-ingest
    (UUID pks change per run; display codes don't). Soft-delete via
    ``deleted_at``.
  ae_note_assessments — one row per recalibration simulation attempt.
    ``impact`` JSONB holds the structured simulation
    ([{surface, target_id, current_value, simulated_direction,
    reasoning, evidence_e_ids}...]); ``status`` walks
    PENDING → SIMULATED → REVIEWED (or FAILED). Nothing here writes back
    into scores — admin review is a human step by design.

Idempotent: CREATE TABLE/INDEX IF NOT EXISTS throughout.
"""
from alembic import op

revision = "061_ae_notes"
down_revision = "060_kpi_evidence_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ae_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            target_kind VARCHAR(24) NOT NULL CHECK (
                target_kind IN ('recommendation', 'roadmap_phase', 'insight_card')
            ),
            target_id VARCHAR(64) NOT NULL,
            author_email VARCHAR(255) NOT NULL,
            author_role VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (
                status IN ('ACTIONED', 'PENDING', 'SUPERSEDED')
            ),
            body TEXT NOT NULL,
            sf_opp_id VARCHAR(64),
            recalibrate BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ae_notes_target
        ON ae_notes (entity_id, target_kind, target_id)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ae_note_assessments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            note_id UUID NOT NULL REFERENCES ae_notes(id) ON DELETE CASCADE,
            status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (
                status IN ('PENDING', 'SIMULATED', 'FAILED', 'REVIEWED')
            ),
            assessment_md TEXT,
            impact JSONB,
            model VARCHAR(64),
            grounding_evidence_ids TEXT[] NOT NULL DEFAULT '{}',
            validators_passed BOOLEAN NOT NULL DEFAULT FALSE,
            failure_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_by VARCHAR(255),
            reviewed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ae_note_assessments_status
        ON ae_note_assessments (status, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ae_note_assessments")
    op.execute("DROP TABLE IF EXISTS ae_notes")
