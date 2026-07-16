"""049 - raw_artifacts: compressed originals persisted in the database

Per the operator mandate "download client Drive folders into the DB,
process, then compress": NOTHING raw is persisted today — package
files die with the tmp dir, so every re-parse means a re-download and
provenance stops at `import_files` metadata. The ingestion audit
measured the corpus at 240MB / 4,681 files / 113 packages with the
material text layer compressing to ~60-70MB (JSON -78%, CSV -72%,
MD -51%, TXT -64%; docx/xlsx/png/pdf stored as-is) — trivial for
Postgres.

One row per unique artifact byte-stream:

  - ``sha256`` UNIQUE      — global dedup (peer JSONs repeat across
    packages); ``first_seen_run``/``last_seen_run`` track the lineage
    window instead of duplicating content.
  - ``materiality``        — reuses artifact_manifest's MATERIAL/COSMETIC
    classes (cosmetic PNGs/decks are excluded by the pipeline anyway).
  - ``codec``              — zstd | gzip | none; ``size_raw``/``size_stored``
    make the compression ratio auditable.
  - ``import_file_id``     — joins back to the Drive crawl bookkeeping row.

Drive backfill downloads each folder ONCE into this table; ALL parsing
reads from DB bytes (re-parse without re-download, deterministic
re-ingest, exact artifact→section→field provenance).

Idempotent: CREATE TABLE/INDEX IF NOT EXISTS.
"""
from alembic import op

revision = "049_raw_artifacts"
down_revision = "048_recommendation_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL
                REFERENCES entities(id) ON DELETE CASCADE,
            run_id UUID
                REFERENCES runs(id) ON DELETE SET NULL,
            import_file_id UUID
                REFERENCES import_files(id) ON DELETE SET NULL,
            drive_file_id VARCHAR(64),
            rel_path TEXT NOT NULL,
            file_kind VARCHAR(32) NOT NULL DEFAULT 'unknown',
            materiality VARCHAR(16) NOT NULL DEFAULT 'MATERIAL'
                CHECK (materiality IN ('MATERIAL', 'COSMETIC')),
            sha256 CHAR(64) NOT NULL UNIQUE,
            size_raw INTEGER NOT NULL DEFAULT 0,
            size_stored INTEGER NOT NULL DEFAULT 0,
            codec VARCHAR(8) NOT NULL DEFAULT 'none'
                CHECK (codec IN ('zstd', 'gzip', 'none')),
            content BYTEA NOT NULL,
            first_seen_run UUID
                REFERENCES runs(id) ON DELETE SET NULL,
            last_seen_run UUID
                REFERENCES runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_artifacts_entity_path "
        "ON raw_artifacts (entity_id, rel_path)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw_artifacts")
