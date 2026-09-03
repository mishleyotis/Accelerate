"""The clients directory shows the composite the client's own overview shows

A promoted run whose workbook states no rollup composite writes
`runs.composite` NULL, and that is by design: workbook_parser treats a
workbook that states no overall figure as a fact, not one to invent from the
pillars (`persist.py` only falls further back to a manifest `stated_overall`).
But the overview HERO still renders a composite -- `overview_scores.composite`,
authored by the surface producer from the same four pillar means and already
shown on the client's own overview page. `serving_directory` read
`r.composite` alone, so a client in exactly this state showed its four pillar
bars and NO overall score on the clients page while its overview page showed a
number.

Measured on a promoted run whose workbook stated no rollup figure:
`runs.composite` resolved NULL while `overview_scores.composite` was
populated -- the card showed the word "maturity" with no figure. The golden
fixture, whose
workbook states its rollup, shows the same figure on both card and hero. That gap -- one card
scored, one not -- is the recurrent defect this closes: it recurs for every
promoted client whose workbook omits the rollup composite, which is a property
of the workbook generation, not of the client.

`serving_directory` ALREADY `LEFT JOIN`s `overview_scores` (it reads
`os.pillars`). This rebuild reads `COALESCE(r.composite, os.composite)`: the
workbook's stated composite when it has one -- unchanged for every run that
already showed a score -- else the composite the client's overview hero is
already displaying. `runs.composite` itself, the honest "the workbook stated
none" fact that `get_client_state` and the diff read, is left exactly as it
was; only the client-facing card gains the fallback.

A materialised view is rebuilt whole or not changed, so 0058's body is carried
verbatim with only the composite expression parameterised -- exactly as 0058
carried 0045's and 0045 carried 0042's.

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-03
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


# 0058's LATERAL argument (the widened workbook_metadata || manifest), carried
# verbatim so this rebuild changes the composite expression and nothing else.
_ARG = ("COALESCE(rm.payload -> 'workbook_metadata', '{}'::jsonb)\n"
        "                                              || "
        "COALESCE(rm.payload -> 'manifest', '{}'::jsonb)")

_COMPOSITE_NEW = "COALESCE(r.composite, os.composite) AS composite"
_COMPOSITE_OLD = "r.composite"

# 0058's body verbatim, with only the composite expression parameterised.
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
               {composite},
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

_VIEW_BODY = _VIEW_BODY_TMPL.format(arg=_ARG, composite=_COMPOSITE_NEW)
_PRE_0059_BODY = _VIEW_BODY_TMPL.format(arg=_ARG, composite=_COMPOSITE_OLD)
# 0042's guard, for its reason: a substitution that produced the same string
# either way would make downgrade() a no-op that reports success to nobody.
assert _PRE_0059_BODY != _VIEW_BODY, (
    "0059: the composite fallback did not change the view body, so downgrade() "
    "would rebuild the view WITH the change it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0058's rebuild, verbatim: the refresh function depends on the view, so
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
    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    _rebuild(_PRE_0059_BODY)
