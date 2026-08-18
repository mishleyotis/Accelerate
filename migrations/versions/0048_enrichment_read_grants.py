"""The enrichment routine can read the tables it reads from.

0047 created `enrichment_jobs` and `enrichment_attempts` and granted svc_worker
on both — its OWN tables. It did not grant svc_worker on the tables the routine
READS to find the gaps in the first place, and the job died in production on

    permission denied for table submissions

after scanning 287 runs. The charter's rule is "grants in the same revision as
the table", and this is the gap in it that rule does not cover: a new CONSUMER
of an existing table needs a grant nobody writes, because no table was created.

What the routine reads, and why each one:

    runs             which runs are in an enrichable state at all
    submissions      the live page payloads. The gap set is COMPUTED from the
                     promoted payload against the contract (invariant 8), so
                     without this the routine can count runs and nothing else —
                     exactly what production showed: "287 run(s), 0 gap(s)".
    evidence_index   the self-domain resolver derives an entity's own domain
                     from the dominant non-aggregator host across its evidence,
                     so it reads source_url and refuses on a tie.

SELECT only. The routine resolves values; it does not write them here. A
resolved value still travels the only path content may take — registered as
evidence and submitted through the connector (invariant 2). The write grants it
holds are on its own two workflow tables and nowhere else, and this revision
does not widen that.

Idempotent and role-guarded in the same shape as 0047: a role that does not
exist in a given environment is skipped rather than failing the migration, so
local docker-compose (which has no IAM roles) and production apply the same
file.
"""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

# The read set, derived from apps/worker/dma_worker/enrichment.py, and written
# out one literal statement per table rather than looped over a tuple.
#
# Two reasons. A wildcard (GRANT ... ON ALL TABLES) would hand the routine the
# whole serving tier to satisfy three reads, so the next table it needs should
# be a visible line in a migration rather than a capability it silently already
# had. And a loop leaves `GRANT SELECT ON {table}` in the file, which no grep —
# and no test — can resolve back to a table name; the check in
# apps/worker/tests/test_enrichment_grants.py reads these statements to prove
# every table the routine's SQL mentions is granted, and it can only read what
# is written down.
_STMT = """
  DO $$
  BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_worker')
       AND EXISTS (SELECT 1 FROM information_schema.tables
                    WHERE table_name = '%(t)s'
                      AND table_schema = current_schema()) THEN
      EXECUTE '%(verb)s';
    END IF;
  END $$;
"""


def upgrade():
    # which runs are in an enrichable state at all
    op.execute(_STMT % {"t": "runs",
                        "verb": "GRANT SELECT ON runs TO svc_worker"})
    # the live page payloads. The gap set is COMPUTED from the promoted payload
    # against the contract (invariant 8), so without this the routine can count
    # runs and nothing else — exactly what production showed.
    op.execute(_STMT % {"t": "submissions",
                        "verb": "GRANT SELECT ON submissions TO svc_worker"})
    # the self-domain resolver derives an entity's own domain from the dominant
    # non-aggregator host across its evidence, and refuses on a tie.
    op.execute(_STMT % {"t": "evidence_index",
                        "verb": "GRANT SELECT ON evidence_index TO svc_worker"})


def downgrade():
    op.execute(_STMT % {"t": "runs",
                        "verb": "REVOKE SELECT ON runs FROM svc_worker"})
    op.execute(_STMT % {"t": "submissions",
                        "verb": "REVOKE SELECT ON submissions FROM svc_worker"})
    op.execute(_STMT % {"t": "evidence_index",
                        "verb": "REVOKE SELECT ON evidence_index FROM svc_worker"})
