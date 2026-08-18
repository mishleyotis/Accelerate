"""0031 — the assessment date as a derivation that states its own basis, and
the six-month due date computed from it.

## What the app shows today, and what it actually knows

Every client page renders "Assessment Mar 30, 2026" from `runs.completed_at`.
That column is not a completion timestamp any package stated. For Baxter — the
only live client — it was reverse-engineered by the ingest parser from the
`20260330` token inside the run's own request id, `DMA-ASM-BCU-20260330-0001`.
Read as a header line beside a maturity score, it presents a filename token as
a stated fact. Invariant 9: a derived value is computed or null, never a
default that looks like data — and a date whose provenance is invisible is
exactly that.

Measured over the 130 runs in production at the time of writing:

    manifests stating `assessment_date`                 17
    manifests stating `completed_at`                     5
    manifests carrying an `assessment` object            5
    manifests stating `generated_at`                    11   <- artefact write
    manifests stating `execution_timestamp`              1      time, not the
    manifests stating `last_updated`                     1      assessment's
    manifests carrying a `run_id` (date token in it)    83
    runs with no resolvable date at all                 43

So three quite different things are being conflated into one column: a date the
package STATES, a timestamp recording when the package FILE was written, and a
token parsed out of an identifier. The 6-month refresh cadence hangs off this
date; a cadence computed from a file-write timestamp and a cadence computed
from a stated assessment date are not the same cadence, and today nothing can
tell them apart.

## Column or computation

Computation, and deliberately so.

  · The source of truth is already stored and already immutable. The whole
    manifest is retained verbatim in `run_manifest.payload`, and the ingested
    tier is read-only once scanned. A derivation over it is reproducible for
    every run that exists, including the 130 already ingested.
  · A stored column would be a second copy of a fact the manifest already
    carries, which invariant 8 asks us not to keep, and it would need the
    ingest worker to write it — leaving those 130 runs needing a backfill
    whose result would be indistinguishable, in the column, from a value a
    package actually stated. That is the defect this revision exists to
    remove, reintroduced one layer down.
  · The basis is only meaningful as part of the same evaluation that picks the
    date. Two columns written at different times can disagree; one function
    returning both cannot.

So: one IMMUTABLE function, evaluated where the read path can see it. The
matview `serving_directory` — the one window svc_api is granted — carries the
result, and refreshes with the promote that already refreshes it.

## The precedence, and why it is the ingest worker's, unchanged

`run_assessment_date` walks exactly the candidate list
`apps/worker/dma_worker/persist.py::_stated_completed_at` walks, in the same
order, so `assessment_date` agrees with `completed_at` for every run where
`completed_at` is set. Changing the order here would have created a second,
differently-derived date in a system that already renders the first one.

What changes is that each rung now names itself:

    STATED                      the package states an assessment/completion
                                date (`assessment.date`, `assessment_date`,
                                `completed_at`)
    DERIVED_ARTEFACT_TIMESTAMP  the package states only when the artefact was
                                written (`generated_at`, `execution_timestamp`,
                                `last_updated`). Close to the assessment,
                                not the assessment.
    DERIVED_REQUEST_ID_TOKEN    the YYYYMMDD token in the run's own request id
    UNKNOWN                     nothing resolves; the date is NULL and the due
                                date with it. Absent beats wrong.

A candidate that is not ISO-shaped, or that is an impossible date, is skipped
rather than raised — a mangled date must not sink a read.

## The due date

`assessment_date + 6 months`, as a date, in the view. NULL when the assessment
date is NULL, never a sentinel. "Due in N weeks" / "overdue by N weeks" is NOT
computed here: it depends on the wall clock, and a clock reading frozen into a
materialised view is a lie that ages. The API computes the distance at request
time from this date (`dma_api.cadence`).

## Shape

Expand only. Three new functions, one composite type, and a rebuild of
`serving_directory` with four columns added (its body cannot be altered in
place). Indexes, grants and the SECURITY DEFINER refresh function are recreated
with it unchanged, per 0015. Nothing is dropped, nothing is rewritten, and
re-running is a no-op.
"""
from alembic import op

revision = "0031"
down_revision = "0035"
branch_labels = None
depends_on = None


# The worker's `_ISOISH` (`^\d{4}-\d{2}-\d{2}`), as a whole-token test over the
# first ten characters: the corpus writes both bare dates and full ISO
# timestamps, and the worker takes the string whole and lets the DATE column
# cast it. Here the cast is done explicitly so an impossible date returns NULL
# instead of aborting a read.
_ISOISH = r"^\d{4}-\d{2}-\d{2}$"

# The worker's `_REQ_ID_DATE` (`-(\d{4})(\d{2})(\d{2})-\d+\s*$`) as one group:
# the YYYYMMDD token in DMA-ASM-<ENTITY>-YYYYMMDD-<seq>.
_REQ_ID_DATE = r"-(\d{8})-\d+$"

_VIEW_BODY = """
        SELECT e.id            AS entity_id,
               e.display_id,
               e.legal_name,
               e.sub_vertical,
               e.size_tier,
               r.id            AS run_id,
               r.request_id,
               r.run_seq,
               r.is_active,
               enum_label(r.status) AS run_status,
               r.composite,
               r.scored_cells,
               r.catalogue_cells,
               r.ccg_catalog_version,
               r.completed_at,
               r.promoted_at,
               os.pillars,
               (SELECT count(*) FROM heatmap_alerts a
                 WHERE a.run_id = r.id AND a.status = 'open') AS open_alerts,
               ad.assessment_date,
               ad.basis         AS assessment_date_basis,
               ad.source_field  AS assessment_date_source,
               (ad.assessment_date + INTERVAL '6 months')::date AS refresh_due_date
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          LEFT JOIN overview_scores os ON os.run_id = r.id
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
"""

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0015's rebuild, verbatim in shape: the refresh function depends on the
    view, so it is dropped first and recreated after, with the same grants."""
    op.execute("DROP FUNCTION IF EXISTS refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS serving_directory")
    op.execute(f"CREATE MATERIALIZED VIEW serving_directory AS {body}")
    op.execute("CREATE UNIQUE INDEX serving_directory_run ON serving_directory (run_id)")
    op.execute("CREATE INDEX serving_directory_entity "
               "ON serving_directory (entity_id, run_seq DESC)")
    op.execute("GRANT SELECT ON serving_directory TO svc_api")
    op.execute(_REFRESH_FN)
    op.execute("REVOKE ALL ON FUNCTION refresh_serving_directory() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() TO svc_mcp")


_PRE_0031_BODY = _VIEW_BODY.replace(
    """,
               ad.assessment_date,
               ad.basis         AS assessment_date_basis,
               ad.source_field  AS assessment_date_source,
               (ad.assessment_date + INTERVAL '6 months')::date AS refresh_due_date""",
    "").replace(
    """
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad""", "")


def upgrade() -> None:
    conn = op.get_bind()

    op.execute(
        f"""
        CREATE FUNCTION dma_isoish_date(v text) RETURNS date
          LANGUAGE plpgsql IMMUTABLE AS $fn$
        BEGIN
          IF v IS NULL THEN RETURN NULL; END IF;
          IF left(btrim(v), 10) !~ '{_ISOISH}' THEN RETURN NULL; END IF;
          RETURN left(btrim(v), 10)::date;
        EXCEPTION WHEN others THEN
          -- an impossible date (2026-02-31) is absent, not fatal
          RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION dma_request_id_date(rid text) RETURNS date
          LANGUAGE plpgsql IMMUTABLE AS $fn$
        DECLARE tok text;
        BEGIN
          tok := substring(upper(btrim(coalesce(rid, ''))) from '{_REQ_ID_DATE}');
          IF tok IS NULL THEN RETURN NULL; END IF;
          RETURN make_date(substr(tok, 1, 4)::int, substr(tok, 5, 2)::int,
                           substr(tok, 7, 2)::int);
        EXCEPTION WHEN others THEN
          RETURN NULL;
        END $fn$
        """
    )
    # The composite is the point: the date and the reason it is that date are
    # one answer, produced by one evaluation. Two columns filled separately can
    # disagree; these cannot.
    op.execute(
        """
        CREATE TYPE assessment_date_t AS (
          assessment_date date,
          basis           text,
          source_field    text
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION run_assessment_date(manifest jsonb, request_id text)
          RETURNS assessment_date_t
          LANGUAGE plpgsql IMMUTABLE AS $fn$
        DECLARE
          -- field, basis — the ingest worker's candidate list, same order
          -- (apps/worker/dma_worker/persist.py::_stated_completed_at).
          probe text[][] := ARRAY[
            ['assessment.date',     'STATED'],
            ['assessment_date',     'STATED'],
            ['completed_at',        'STATED'],
            ['generated_at',        'DERIVED_ARTEFACT_TIMESTAMP'],
            ['execution_timestamp', 'DERIVED_ARTEFACT_TIMESTAMP'],
            ['last_updated',        'DERIVED_ARTEFACT_TIMESTAMP']];
          i   int;
          raw text;
          d   date;
          out assessment_date_t;
        BEGIN
          IF manifest IS NOT NULL AND jsonb_typeof(manifest) = 'object' THEN
            FOR i IN 1 .. array_length(probe, 1) LOOP
              IF probe[i][1] = 'assessment.date' THEN
                raw := manifest #>> '{assessment,date}';
              ELSE
                raw := manifest ->> probe[i][1];
              END IF;
              d := dma_isoish_date(raw);
              IF d IS NOT NULL THEN
                out := (d, probe[i][2], 'manifest.' || probe[i][1]);
                RETURN out;
              END IF;
            END LOOP;

            -- The request id the package itself states, before the copy of it
            -- on the run row: the manifest is the artefact, the column is our
            -- transcription of it.
            d := dma_request_id_date(manifest ->> 'run_id');
            IF d IS NOT NULL THEN
              out := (d, 'DERIVED_REQUEST_ID_TOKEN', 'manifest.run_id');
              RETURN out;
            END IF;
          END IF;

          d := dma_request_id_date(request_id);
          IF d IS NOT NULL THEN
            out := (d, 'DERIVED_REQUEST_ID_TOKEN', 'runs.request_id');
            RETURN out;
          END IF;

          -- Nothing resolves. NULL date, named reason, no due date.
          out := (NULL::date, 'UNKNOWN', NULL::text);
          RETURN out;
        END $fn$
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION run_assessment_date(jsonb, text) "
               "TO svc_api, svc_mcp, svc_worker")

    _rebuild(_VIEW_BODY)

    # --- VERIFY: the database is private-IP only, so these lines are the
    #     production proof (migrations/README.md, 0021's precedent).
    rows = conn.exec_driver_sql("""
        SELECT ad.basis, count(*), count(ad.assessment_date)
          FROM runs r
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad
         GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    print("VERIFY 0031 basis over every run: "
          + ", ".join(f"{b}={n} (dated {d})" for b, n, d in rows))

    agree = conn.exec_driver_sql("""
        SELECT count(*) FILTER (WHERE r.completed_at IS NOT NULL
                                  AND ad.assessment_date IS NOT NULL
                                  AND r.completed_at::date = ad.assessment_date),
               count(*) FILTER (WHERE r.completed_at IS NOT NULL
                                  AND (ad.assessment_date IS NULL
                                       OR r.completed_at::date <> ad.assessment_date)),
               count(*) FILTER (WHERE r.completed_at IS NULL
                                  AND ad.assessment_date IS NOT NULL)
          FROM runs r
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad
    """).fetchone()
    print(f"VERIFY 0031 vs runs.completed_at: agree={agree[0]} disagree={agree[1]} "
          f"newly dated={agree[2]}")

    served = conn.exec_driver_sql("""
        SELECT display_id, request_id, assessment_date, assessment_date_basis,
               assessment_date_source, refresh_due_date
          FROM serving_directory ORDER BY display_id, run_seq
    """).fetchall()
    for r in served:
        print(f"VERIFY 0031 served: {r[0]} {r[1]} assessment={r[2]} "
              f"basis={r[3]} from={r[4]} due={r[5]}")
    print(f"VERIFY 0031 promoted rows in serving_directory: {len(served)}")


def downgrade() -> None:
    _rebuild(_PRE_0031_BODY)
    op.execute("DROP FUNCTION IF EXISTS run_assessment_date(jsonb, text)")
    op.execute("DROP TYPE IF EXISTS assessment_date_t")
    op.execute("DROP FUNCTION IF EXISTS dma_request_id_date(text)")
    op.execute("DROP FUNCTION IF EXISTS dma_isoish_date(text)")
