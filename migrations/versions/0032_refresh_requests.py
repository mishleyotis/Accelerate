"""0032 — the refresh queue, and the one production row that would have been
drained as work.

## Part 1 · the queue

The 6-month refresh cadence has, until now, existed nowhere: no due-date
concept, no way for a reader to ask for a rerun, and nothing the scheduled
synthesis routine could read to learn that one had been asked for. 0031 gave
the cadence its date and its due date. This gives the *request* somewhere to
live.

`refresh_requests` is a WORKFLOW table, in the same tier as `alert_actions`
and `annotations`: it records that a person (or the cadence) asked for a
client to be reassessed, who asked, when, and what became of it. It holds no
assessment content, no prose, no score, and nothing it holds is ever rendered
as a finding. Invariant 2's boundary — content enters only through the
connector — is untouched by it.

Who may write it, and why not svc_api:

    svc_worker   SELECT, INSERT, UPDATE.  The `dmai-refresh` Cloud Run Job
                 runs as dmai-worker and is what actually records a request.
                 The web service fires that Job the same way the admin "Run
                 scan now" button already fires `dmai-worker` — so the click
                 reaches the database through the ingest identity, not
                 through a serving endpoint.
    svc_mcp      SELECT, UPDATE.  The connector closes a request when the run
                 that answers it promotes.
    svc_api      SELECT only.  The read path renders "requested by X on Y";
                 it does not create the request.

The alternative — `POST /v1/entities/{id}/refresh` behind an
Idempotency-Key, exactly the shape of the alert-action write — is a better
piece of engineering (synchronous, replayable, no cold start) and it is NOT
implemented here, because invariant 2 enumerates the API's writes as
annotations and alert actions and a refresh request is neither. Widening
that enumeration is the user's call, not this revision's. The grant above is
therefore deliberately narrow: if invariant 2 is later amended, the only
change needed is one GRANT and one endpoint.

De-duplication is a partial unique index rather than an Idempotency-Key,
because the Job path has no key to carry: one open request per entity, so a
double-click collapses into the request that already exists.

The index is created plainly, not CONCURRENTLY: the table is created empty in
this same revision, so there is no populated relation to lock and nothing for
a concurrent build to protect.

## Part 2 · Baxter's second run

Production carries two runs for `DMA-ASM-BCU-20260330-0001` — the same
package, the same 765 scored cells, the same 2.71 composite:

    run_seq 1   PROMOTED, is_active, 6,215 evidence links   <- serving
    run_seq 2   INGESTED, never claimed, never submitted,
                2,657 evidence links, no gate results

They differ in exactly two ways: run 2's manifest carries the pillar weights
run 1's lacks (it was parsed by a later worker), and run 2 has 3,558 fewer
evidence links. It is a re-ingest of one package, not a second assessment —
0029 diagnoses the mint path and closes it, and this row predates that fix.

Left as `INGESTED` it is a live hazard rather than clutter. `promote.py`
supersedes the *previous* active run when a new one promotes, so anything
that treated run 2 as pending work and promoted it would silently swap the
only live client's pages onto the copy with 43% of the evidence — a
regression with no reader-visible cause. Once a refresh queue exists,
"pending run for a client someone asked to refresh" is precisely the shape of
work a producer looks for.

So run 2 is marked `SUPERSEDED` and `is_active = FALSE` — the same pair
`promote.py` writes on a run that has been replaced. SUPERSEDED here means
what it means there: this run will not serve, because another run of this
assessment does. Nothing is deleted. Its scores, its manifest and its 2,657
evidence links stay exactly where they are, and one UPDATE reverses it.

The predicate is narrow on purpose — an unpromoted run whose entity already
holds a PROMOTED run carrying the SAME request id. Three other entities (WLI,
PENT, TROW) also hold duplicate request-id pairs; none of them has a promoted
member, so which copy is the keeper is genuinely undecided and this revision
does not decide it. They are counted in the VERIFY lines and left alone.
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

#: An unpromoted run whose entity already holds a PROMOTED run carrying the
#: same request id. Written once, used by the repair and by both VERIFY reads.
_SHADOWED = """
      SELECT r.id, r.run_seq, r.request_id, e.display_id, r.status::text
        FROM runs r
        JOIN entities e ON e.id = r.entity_id
       WHERE r.promoted_at IS NULL
         AND r.is_active IS NOT TRUE
         AND r.request_id IS NOT NULL
         AND EXISTS (SELECT 1 FROM runs p
                      WHERE p.entity_id = r.entity_id
                        AND p.request_id = r.request_id
                        AND p.id <> r.id
                        AND p.promoted_at IS NOT NULL)
"""


def upgrade() -> None:
    conn = op.get_bind()

    op.execute(
        """
        CREATE TABLE refresh_requests (
          id                  BIGSERIAL PRIMARY KEY,
          entity_id           UUID NOT NULL REFERENCES entities(id),
          observed_run_id     UUID REFERENCES runs(id),  -- serving when asked
          origin              TEXT NOT NULL,             -- human · cadence
          requested_by        TEXT,                      -- actor; NULL = cadence
          reason              TEXT,
          status              TEXT NOT NULL,
          fulfilled_by_run_id UUID REFERENCES runs(id),
          requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
          note                TEXT,
          CONSTRAINT refresh_origin_known
            CHECK (origin IN ('human', 'cadence')),
          CONSTRAINT refresh_status_known
            CHECK (status IN ('REQUESTED', 'ACKNOWLEDGED', 'FULFILLED',
                              'CANCELLED')),
          -- a human request with no human named is an anonymous instruction
          CONSTRAINT refresh_human_is_named
            CHECK (origin <> 'human' OR requested_by IS NOT NULL),
          -- "fulfilled" without the run that fulfilled it is unfalsifiable
          CONSTRAINT refresh_fulfilled_names_its_run
            CHECK (status <> 'FULFILLED' OR fulfilled_by_run_id IS NOT NULL),
          -- and a closed request must say when it closed
          CONSTRAINT refresh_closed_is_stamped
            CHECK (status IN ('REQUESTED', 'ACKNOWLEDGED')
                   OR updated_at IS NOT NULL)
        )
        """
    )
    # One open request per entity: the Job path carries no Idempotency-Key,
    # so the double-click collapses here instead.
    op.execute(
        """CREATE UNIQUE INDEX refresh_requests_open_uq ON refresh_requests
             (entity_id) WHERE status IN ('REQUESTED', 'ACKNOWLEDGED')"""
    )
    op.execute(
        """CREATE INDEX refresh_requests_entity ON refresh_requests
             (entity_id, requested_at DESC)"""
    )
    op.execute(
        """CREATE INDEX refresh_requests_open ON refresh_requests
             (requested_at) WHERE status IN ('REQUESTED', 'ACKNOWLEDGED')"""
    )

    # Grants in the same revision as the table (charter, working discipline).
    op.execute("GRANT SELECT, INSERT, UPDATE ON refresh_requests TO svc_worker")
    op.execute("GRANT SELECT, UPDATE ON refresh_requests TO svc_mcp")
    op.execute("GRANT SELECT ON refresh_requests TO svc_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE refresh_requests_id_seq TO svc_worker")

    grants = conn.exec_driver_sql("""
        SELECT grantee, string_agg(DISTINCT privilege_type, ',' ORDER BY privilege_type)
          FROM information_schema.role_table_grants
         WHERE table_name = 'refresh_requests' AND grantee LIKE 'svc\\_%'
         GROUP BY grantee ORDER BY grantee
    """).fetchall()
    print("VERIFY 0032 refresh_requests grants: "
          + "; ".join(f"{g}={p}" for g, p in grants))

    # --- Part 2 · the shadowed run -------------------------------------
    before = conn.exec_driver_sql(_SHADOWED).fetchall()
    for r in before:
        print(f"VERIFY 0032 shadowed run: {r[3]} {r[2]} run_seq={r[1]} "
              f"status={r[4]} id={r[0]}")

    repaired = conn.exec_driver_sql(f"""
        UPDATE runs SET status = 'SUPERSEDED', is_active = FALSE
         WHERE id IN (SELECT id FROM ({_SHADOWED}) s WHERE s.status = 'INGESTED')
        RETURNING id, request_id, run_seq
    """).fetchall()
    for r in repaired:
        print(f"VERIFY 0032 marked SUPERSEDED: {r[1]} run_seq={r[2]} id={r[0]}")
    print(f"VERIFY 0032 shadowed runs marked: {len(repaired)}")

    # Nothing left of the run is touched. Say so with numbers rather than
    # with a claim.
    for r in repaired:
        kept = conn.exec_driver_sql(
            "SELECT (SELECT count(*) FROM subcap_scores WHERE run_id = %s), "
            "       (SELECT count(*) FROM evidence_subcap_links WHERE run_id = %s), "
            "       (SELECT count(*) FROM run_manifest WHERE run_id = %s)",
            (r[0], r[0], r[0])).fetchone()
        print(f"VERIFY 0032 retained on {r[1]} run_seq={r[2]}: "
              f"subcap_scores={kept[0]} evidence_links={kept[1]} manifests={kept[2]}")

    # Duplicate request-id pairs with NO promoted member — deliberately not
    # touched, because which copy is the keeper is undecided.
    undecided = conn.exec_driver_sql("""
        SELECT request_id, count(*)
          FROM runs
         WHERE request_id IS NOT NULL
         GROUP BY request_id
        HAVING count(*) > 1
           AND count(*) FILTER (WHERE promoted_at IS NOT NULL) = 0
         ORDER BY request_id
    """).fetchall()
    print("VERIFY 0032 duplicate request ids left undecided (no promoted "
          "member, so no keeper): "
          + (", ".join(f"{q}×{n}" for q, n in undecided) or "none"))


def downgrade() -> None:
    # The repair is reversed by name — the runs this revision marked are the
    # ones still shadowed by a promoted sibling.
    op.execute(f"""
        UPDATE runs SET status = 'INGESTED', is_active = NULL
         WHERE id IN (SELECT id FROM ({_SHADOWED}) s WHERE s.status = 'SUPERSEDED')
    """)
    op.execute("DROP TABLE IF EXISTS refresh_requests")
