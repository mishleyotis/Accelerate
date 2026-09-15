"""The date the workbook states about itself, where the resolver can see it

`run_assessment_date` walks six manifest keys, then the YYYYMMDD token in the
run's request id, then gives up. Golden 1 (`DMA-2026-GOLDEN1-001`) carries
none of the six and its request id has no eight-digit token, so the run
resolved UNKNOWN — while `Run_Metadata!last_written_at` on its own workbook
states `2026-08-31T09:33:59Z`, and nothing had ever read that tab for a date.

The cost is not a missing header line. `assessment_date` draws the freshness
dot, and the same candidate list feeds `runs.completed_at`, which becomes
every evidence row's `reference_date` — with it null the generated
`age_months` is null and `recency_band` falls to UNVERIFIED for EVERY item.
537 rows on this run.

## Two changes, and the second is why the first can work

**The rung.** `last_written_at` joins the DERIVED_ARTEFACT_TIMESTAMP group,
beside `generated_at` / `execution_timestamp` / `last_updated`. It is when
the artefact was written, not when the assessment completed, and 0031's
whole point is that the basis says so rather than the date pretending. It
goes LAST within that group: a package that states both should serve the one
it chose to call a generation time.

**Where the resolver looks.** The workbook is not the manifest, and the
manifest must not be edited to carry it — the ingested tier is read-only
once scanned, and a key written into `payload.manifest` afterwards would be
indistinguishable from one the package shipped. So the worker stores the tab
BESIDE it, at `run_manifest.payload.workbook_metadata`, exactly as
`workbook_grains` sits beside it and for the same reason; and the view hands
the function `workbook_metadata || manifest`.

`||` is right-biased, so the manifest is the right operand: it is the
authority, and the workbook only fills what it left empty. Reversing them
would let a workbook's `completed_at` overwrite the package's own.

## Shape

Expand only. The function is replaced (same signature, same return type, so
the view's LATERAL join is unchanged in shape), and the view is rebuilt
because a materialised view's body cannot be altered in place. Indexes,
grants and the SECURITY DEFINER refresh function are recreated with it, per
0015. Nothing is dropped, nothing is rewritten, re-running is a no-op.

A run whose workbook states no date, or which has no `workbook_metadata` key
at all, resolves exactly as it did before: absent beats wrong.

Revision ID: 0058
Revises: 0057
Create Date: 2026-09-02
"""
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def _fn(with_last_written: bool) -> str:
    """0031's function, with the one probe row present or absent."""
    extra = ("            ['last_written_at',     'DERIVED_ARTEFACT_TIMESTAMP'],\n"
             if with_last_written else "")
    return f"""
        CREATE OR REPLACE FUNCTION run_assessment_date(manifest jsonb,
                                                       request_id text)
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
{extra}            ['last_updated',        'DERIVED_ARTEFACT_TIMESTAMP']];
          i   int;
          raw text;
          d   date;
          out assessment_date_t;
        BEGIN
          IF manifest IS NOT NULL AND jsonb_typeof(manifest) = 'object' THEN
            FOR i IN 1 .. array_length(probe, 1) LOOP
              IF probe[i][1] = 'assessment.date' THEN
                raw := manifest #>> '{{assessment,date}}';
              ELSE
                raw := manifest ->> probe[i][1];
              END IF;
              d := dma_isoish_date(raw);
              IF d IS NOT NULL THEN
                out := (d, probe[i][2], 'manifest.' || probe[i][1]);
                RETURN out;
              END IF;
            END LOOP;

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

          out := (NULL::date, 'UNKNOWN', NULL::text);
          RETURN out;
        END
        $fn$
    """


_ARG_OLD = "rm.payload -> 'manifest'"
_ARG_NEW = ("COALESCE(rm.payload -> 'workbook_metadata', '{}'::jsonb)\n"
            "                                              || "
            "COALESCE(rm.payload -> 'manifest', '{}'::jsonb)")

# 0045's body verbatim, with only the LATERAL argument parameterised.
_VIEW_BODY_TMPL = """
        SELECT e.id            AS entity_id,
               e.display_id,
               e.legal_name,
               e.sub_vertical,
               e.size_tier,
               e.domain        AS entity_domain,
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
          CROSS JOIN LATERAL run_assessment_date({arg}, r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
           AND r.withdrawn_at IS NULL
"""

_VIEW_BODY = _VIEW_BODY_TMPL.format(arg=_ARG_NEW)
_PRE_0058_BODY = _VIEW_BODY_TMPL.format(arg=_ARG_OLD)
# 0042's guard, for its reason: a substitution that produced the same string
# either way would make downgrade() a no-op that reports success.
assert _PRE_0058_BODY != _VIEW_BODY, (
    "0058: the widened manifest argument did not change the view body, so "
    "downgrade() would rebuild the view WITH the change it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0045's rebuild, verbatim: the refresh function depends on the view, so
    it is dropped first and recreated after, with the same grants."""
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


def upgrade() -> None:
    op.execute(_fn(with_last_written=True))
    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    op.execute(_fn(with_last_written=False))
    _rebuild(_PRE_0058_BODY)
