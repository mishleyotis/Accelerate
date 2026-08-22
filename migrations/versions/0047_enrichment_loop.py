"""The enrichment loop's own tables — what it tried, what it closed, when it ran.

Owner, 2026-08-15: "There should be a working enrichment routine; not you doing
it as Claude Code" and "confirm that this enrichment loop happens robustly as
the web app runs."

Both halves of that need a store. Until now the gap list was COMPUTED on demand
(`list_enrichment_gaps`) and nothing recorded whether anything ever acted on it,
so "the loop runs" was a claim with no evidence behind it. Computing the gaps
stays computed — invariant 8, and a stored gap list would go stale the instant a
page re-promoted. What is stored here is the OPPOSITE: not the gaps, but the
ATTEMPTS, which are history and cannot be recomputed.

    enrichment_jobs     one row per execution of the routine. This is the row
                        the app reads to answer "is the loop alive?" — a
                        finished_at that is hours old, or a run that found
                        gaps and resolved none, is a broken loop showing as a
                        broken loop.
    enrichment_attempts one row per (gap, resolver) pair tried. RESOLVED rows
                        carry the value and its provenance; NOT_RUN rows carry
                        the REASON, which is the fail-closed half — a resolver
                        that could not reach its source must say so rather than
                        leave a gap looking unattempted.

WHO WRITES THESE, and why not svc_api. Same reasoning as refresh_requests
(0032): this is a WORKFLOW tier table. It holds no assessment content, no
prose, no score, and nothing here is ever rendered as a finding. Invariant 2 is
untouched — the routine does not write serving content. When an attempt
RESOLVES a value, that value still has to travel the only path content may
take: registered as evidence and submitted through the connector. This table
records that the attempt happened; it is not a side door into the serving tier.

    svc_worker  SELECT, INSERT, UPDATE — the routine runs as dmai-worker.
    svc_mcp     SELECT — the producer session reads what the routine already
                resolved so it does not re-run a search that has an answer.
    svc_api     SELECT — the read path renders loop health.
"""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE enrichment_jobs (
          id             BIGSERIAL PRIMARY KEY,
          started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at    TIMESTAMPTZ,
          trigger        TEXT NOT NULL,            -- schedule · manual · deploy
          runs_scanned   INTEGER NOT NULL DEFAULT 0,
          gaps_found     INTEGER NOT NULL DEFAULT 0,
          resolved       INTEGER NOT NULL DEFAULT 0,
          not_run        INTEGER NOT NULL DEFAULT 0,
          failed         INTEGER NOT NULL DEFAULT 0,
          error          TEXT,
          CONSTRAINT enrichment_trigger_known
            CHECK (trigger IN ('schedule', 'manual', 'deploy', 'test'))
        );

        CREATE TABLE enrichment_attempts (
          id             BIGSERIAL PRIMARY KEY,
          job_id         BIGINT NOT NULL REFERENCES enrichment_jobs(id) ON DELETE CASCADE,
          run_id         UUID NOT NULL REFERENCES runs(id),
          entity_id      UUID NOT NULL REFERENCES entities(id),
          page           TEXT NOT NULL,
          section        TEXT NOT NULL,
          field          TEXT NOT NULL,
          field_path     TEXT NOT NULL,
          resolver       TEXT NOT NULL,
          status         TEXT NOT NULL,
          value          TEXT,
          unit           TEXT,
          as_of          DATE,
          source_url     TEXT,
          excerpt        TEXT,
          confidence     TEXT,
          -- REQUIRED on anything that is not RESOLVED. A resolver that came
          -- back empty without saying why is indistinguishable from one that
          -- never ran, which is the exact confusion this whole loop exists to
          -- end; the constraint makes the silence impossible rather than
          -- discouraged.
          reason         TEXT,
          attempted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT enrichment_status_known
            CHECK (status IN ('RESOLVED', 'NOT_RUN', 'NO_SOURCE', 'FAILED')),
          CONSTRAINT enrichment_resolved_has_a_value
            CHECK (status <> 'RESOLVED' OR (value IS NOT NULL AND value <> '')),
          CONSTRAINT enrichment_unresolved_has_a_reason
            CHECK (status = 'RESOLVED' OR (reason IS NOT NULL AND reason <> ''))
        );

        CREATE INDEX enrichment_attempts_run ON enrichment_attempts (run_id, field);
        CREATE INDEX enrichment_attempts_job ON enrichment_attempts (job_id);
        CREATE INDEX enrichment_jobs_started ON enrichment_jobs (started_at DESC);
    """)

    # Grants in the same revision as the table (charter: working discipline).
    for role, grant in (
        ("svc_worker", "SELECT, INSERT, UPDATE"),
        ("svc_mcp", "SELECT"),
        ("svc_api", "SELECT"),
    ):
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'GRANT {grant} ON enrichment_jobs TO {role}';
                EXECUTE 'GRANT {grant} ON enrichment_attempts TO {role}';
              END IF;
            END $$;
        """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_worker') THEN
            EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE enrichment_jobs_id_seq TO svc_worker';
            EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE enrichment_attempts_id_seq TO svc_worker';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS enrichment_attempts")
    op.execute("DROP TABLE IF EXISTS enrichment_jobs")
