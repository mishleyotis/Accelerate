"""0029 — the run a re-scan mints for a package that has not changed.

`persist_package` inserts into `runs` unconditionally. Nothing on the run row
records WHICH artefact produced it or what that artefact's bytes were, so
nothing can tell a first ingest from the same ingest happening again. Every
path that re-presents an unchanged package therefore mints a second run:

  · `_requeue` blanks the stored checksum of a failed package, so the next
    scan classifies a byte-identical workbook as CHANGED;
  · `RESET_SCAN` blanks every checksum;
  · `FORCE_FOLDER` re-ingests a named folder deliberately.

The first two are the scan retrying itself. They are supposed to be free —
"an unchanged tree creates nothing" is the scan's stated contract — and
instead they mint duplicates. Six entities in production carry more than one
run for the same package.

This revision gives the run row the two facts that make the ingest
idempotent:

  · `source_artefact_id` — the scoring workbook the run was read from, FK to
    import_files so it cannot name an artefact the scan never saw;
  · `source_checksum` — that artefact's checksum AT INGEST. The live value in
    import_files is blanked by a requeue, so the run must keep its own copy;
    without it the identity is only as stable as the column the retry clears.

Backfill is deliberately absent. `source_artefact_id` cannot be inferred for
runs already ingested — the artefact that produced them was never recorded,
and picking today's best-ranked workbook for the folder would be a guess
written into a provenance column. Existing runs keep NULL, the partial unique
index ignores them, and the guard below treats a NULL as "unknown, mint" —
so the first re-ingest of an old run stamps it and every one after that is a
no-op.

Expand only: two nullable columns and one partial unique index. Nothing is
rewritten, nothing is dropped, and re-running is a no-op.
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("source_artefact_id", "TEXT",
     "the scoring workbook this run was read from (import_files.artefact_id)"),
    ("source_checksum", "TEXT",
     "that artefact's checksum AT INGEST; a requeue blanks the live one"),
)


def upgrade() -> None:
    conn = op.get_bind()
    for column, type_, comment in _COLUMNS:
        op.execute(f"ALTER TABLE runs ADD COLUMN IF NOT EXISTS {column} {type_}")
        op.execute(f"COMMENT ON COLUMN runs.{column} IS '{comment}'")
    op.execute(
        """ALTER TABLE runs
             DROP CONSTRAINT IF EXISTS runs_source_artefact_fk""")
    op.execute(
        """ALTER TABLE runs
             ADD CONSTRAINT runs_source_artefact_fk
             FOREIGN KEY (source_artefact_id)
             REFERENCES import_files(artefact_id)""")
    # Partial: rows ingested before this revision carry NULL and are not
    # candidates for the uniqueness this enforces.
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS runs_source_artefact_uq
             ON runs (entity_id, source_artefact_id, source_checksum)
          WHERE source_artefact_id IS NOT NULL""")

    dupes = conn.exec_driver_sql(
        """SELECT count(*) FROM (
             SELECT entity_id FROM runs
              WHERE source_folder_id IS NOT NULL
              GROUP BY entity_id, source_folder_id HAVING count(*) > 1) d"""
    ).scalar()
    print(f"VERIFY 0029: {dupes} (entity, source_folder_id) group(s) already "
          f"hold more than one run; they keep NULL provenance and are left "
          f"exactly as they are")
    stamped = conn.exec_driver_sql(
        "SELECT count(*) FROM runs WHERE source_artefact_id IS NOT NULL"
    ).scalar()
    print(f"VERIFY 0029: {stamped} run(s) carry a source artefact; the ingest "
          f"stamps the rest as it re-reads them")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS runs_source_artefact_uq")
    op.execute("ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_source_artefact_fk")
    for column, _type, _comment in _COLUMNS:
        op.execute(f"ALTER TABLE runs DROP COLUMN IF EXISTS {column}")
