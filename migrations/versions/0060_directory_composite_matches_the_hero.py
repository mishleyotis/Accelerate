"""The client card's number comes from the same place as its bars

`serving_directory` already joins `overview_scores` and already takes the
card's four pillar bars from it (`os.pillars`). It took the headline figure
from somewhere else — `r.composite`, the value read out of the scoring
workbook at ingest. One card, two sources.

WHAT THAT COSTS, measured 2026-09-04 on goeasy Ltd.
(`DMA-RES-GSY-20260830-0002`). Its workbook states no OVERALL row — the
composite repair opened it eight times and reported "workbook states none"
every time, which is honest and correct: absent beats invented. So
`runs.composite` is NULL. But the run's own promoted overview hero states
`composite: 2.11`, and the client directory rendered the word "maturity"
over an empty slot beside four bars — 2.09 / 2.19 / 2.01 / 2.16 — drawn
from that very same hero row.

The two surfaces disagreed because they were reading two different columns,
and the fix is to stop them being able to: `COALESCE(r.composite,
os.composite)`.

ORDER IS DELIBERATE. The workbook-stated figure wins where there is one —
it is the assessment's own arithmetic and the authority the charter gives
scores. The hero fills the SILENCE, and only the silence. Neither is
derived: both are figures a human or a producer wrote down and the validator
accepted, so nothing here invents a number from the pillars above it. A run
whose workbook states none and whose hero states none still serves NULL and
still says so.

`os.composite` is `NUMERIC(4,2)` exactly as `r.composite` is, so the column
type, the band generated from it, and every reader downstream are unchanged.

Expand only: the view body changes, nothing is dropped and no data moves.
A materialised view's body cannot be altered in place, so it is rebuilt on
0045's pattern with its indexes, grants and refresh function recreated.

0059's GRANT IS RE-APPLIED HERE, and that is not decoration. Rebuilding
drops `refresh_serving_directory()`, which takes every grant on it with it —
including the one 0059 gave `svc_worker` so the scan Job can publish the
composites it repairs. A rebuild that recreated only `svc_mcp`'s grant would
silently un-fix 0059 and the worker's repairs would go unpublished again.

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-04
"""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_ARG = ("COALESCE(rm.payload -> 'workbook_metadata', '{}'::jsonb)\n"
        "                                              || "
        "COALESCE(rm.payload -> 'manifest', '{}'::jsonb)")

#: 0058's body verbatim, with only the composite expression parameterised.
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
               __COMPOSITE__,
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
          CROSS JOIN LATERAL run_assessment_date(%s, r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
           AND r.withdrawn_at IS NULL
""" % _ARG

# A plain token, not str.format: the body carries `'{}'::jsonb` literals and
# format() reads those braces as replacement fields.
_PRE_0060 = _VIEW_BODY_TMPL.replace("__COMPOSITE__", "r.composite")
_VIEW_BODY = _VIEW_BODY_TMPL.replace(
    "__COMPOSITE__", "COALESCE(r.composite, os.composite) AS composite")

# 0042's guard, for its reason: a substitution that produced the same string
# either way would make downgrade() a no-op that reports success.
assert _PRE_0060 != _VIEW_BODY, (
    "0060: the composite expression did not change, so downgrade() would "
    "rebuild the view WITH the change it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0058's rebuild, with 0059's grant carried through it."""
    op.execute("DROP FUNCTION IF EXISTS refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS serving_directory")
    op.execute(f"CREATE MATERIALIZED VIEW serving_directory AS {body}")
    op.execute("CREATE UNIQUE INDEX serving_directory_run "
               "ON serving_directory (run_id)")
    op.execute("CREATE INDEX serving_directory_entity "
               "ON serving_directory (entity_id, run_seq DESC)")
    op.execute("GRANT SELECT ON serving_directory TO svc_api")
    op.execute(_REFRESH_FN)
    op.execute("REVOKE ALL ON FUNCTION refresh_serving_directory() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() TO svc_mcp")
    # 0059. Dropping the function dropped this with it.
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() "
               "TO svc_worker")


def upgrade() -> None:
    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    _rebuild(_PRE_0060)
