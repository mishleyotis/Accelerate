"""034 - runs.artifact_manifest_json for per-artifact diff (Batch 2)

Per the 2026-06-07 operator mandate "a reingest should strictly be
for the changed artifact": migration 033 added the rollup
``material_manifest_hash`` so the backfill can SKIP cleanly when
nothing material changed. Batch 2 needs more granularity -- when a
hash differs, we need to know WHICH artifacts differ so we can
re-persist only their downstream tables (the artifact -> tables
mapping in ``app/services/artifact_manifest.affected_tables``).

Stored as JSONB on the runs row: the per-file
``[{rel_path, cls, content_hash, size_bytes}, ...]`` array. On the
next backfill pass we deserialize the prior manifest, call
``diff_manifests(prior, current)``, then
``affected_tables(diff)`` -> ``skip_tables`` -> ``persist_package``.

Default NULL on legacy rows. The backfill falls back to "persist
everything" when prior is NULL (full re-ingest); subsequent passes
use the selective path.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "034_runs_artifact_manifest"
down_revision = "033_runs_material_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='runs'
                  AND column_name='artifact_manifest_json'
            ) THEN
                ALTER TABLE runs
                ADD COLUMN artifact_manifest_json JSONB;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE runs DROP COLUMN IF EXISTS artifact_manifest_json"
    )
