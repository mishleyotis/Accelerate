"""run_seq stops being a read-modify-write nobody serialises.

AUD-0089: persist.py allocates a run's sequence with

    SELECT COALESCE(max(run_seq), 0) + 1 FROM runs WHERE entity_id = %s

with no FOR UPDATE and no unique index behind it. The sole serialisation is
`pg_try_advisory_lock(815002)`, taken in `job_main.main()` — a lock that
exists only inside the worker Job. Every other writer of `runs` (a backfill,
a remint, a manual repair, a second worker revision during a rolling deploy)
races it, and the failure is silent: two runs for one entity carrying the
same `run_seq`, after which `ORDER BY run_seq DESC` picks arbitrarily and
`serving_directory (entity_id, run_seq DESC)` — which the directory reads
for its header AND its rows — resolves to whichever row the planner reached
first.

The fix is the constraint, not more locking. A partial unique index makes a
duplicate allocation FAIL LOUDLY at the moment it happens, in every writer
including the ones that do not exist yet, and turns the advisory lock from
the only defence into an optimisation. `run_seq` is nullable in 0005, and
rows without one are legitimate (a run that never reached allocation), so
the index is partial.

If the index cannot be created because duplicates already exist, that is
the defect this revision exists to surface: the failure names the entities,
and they are repaired by renumbering, never by dropping the constraint.
"""
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Report before enforcing: a bare CREATE UNIQUE INDEX on a table that
    # already holds a duplicate fails with a message naming a tuple, not an
    # entity, and the operator then has to go looking.
    op.execute("""
        DO $$
        DECLARE dupes text;
        BEGIN
            SELECT string_agg(format('%s (run_seq %s x%s)',
                                     entity_id, run_seq, n), ', ')
              INTO dupes
              FROM (SELECT entity_id, run_seq, count(*) AS n
                      FROM runs WHERE run_seq IS NOT NULL
                     GROUP BY entity_id, run_seq HAVING count(*) > 1) d;
            IF dupes IS NOT NULL THEN
                RAISE EXCEPTION
                  'runs already holds duplicate (entity_id, run_seq): %. '
                  'These are the silent collisions AUD-0089 predicted. '
                  'Renumber them — the later ingest takes the next free '
                  'sequence — then re-run this migration. Do not drop the '
                  'constraint.', dupes;
            END IF;
        END $$;
    """)
    # CONCURRENTLY is not available inside Alembic's transaction, and this
    # index is small (one row per run) — the lock is measured in
    # milliseconds on a table of this size.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS runs_entity_run_seq_uniq
            ON runs (entity_id, run_seq)
         WHERE run_seq IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS runs_entity_run_seq_uniq")
