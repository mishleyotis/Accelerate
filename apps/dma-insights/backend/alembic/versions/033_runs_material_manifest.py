"""033 - runs.material_manifest_hash for intelligent re-ingest

Per the 2026-06-07 operator mandate: "A reingest should strictly be
for the changed artifact, and ONLY if the information influences the
DMA. If it was a cosmetic change, this can just be dropped. The
backfill should be super intelligent to avoid just reingesting."

The backfill needs to answer "did the *material* content of this
package change since the last successful ingest?" — a folder mtime
touch (deck swap, README edit, PNG reupload) must NOT trigger
re-ingest. The materiality classifier in
``app/services/artifact_manifest.py`` rolls up a deterministic
SHA256 over just the material files; we persist it on the runs row
and compare on the next backfill pass.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "033_runs_material_manifest"
down_revision = "032_caps_log_widen_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='runs' AND column_name='material_manifest_hash'
            ) THEN
                ALTER TABLE runs
                ADD COLUMN material_manifest_hash VARCHAR(64);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE runs DROP COLUMN IF EXISTS material_manifest_hash"
    )
