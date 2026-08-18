"""The entity's own domain, so O11 can compute a share of anything

`evidence_coverage.self_sourced_pct` is a required O11 field and it has
never rendered, for any client, ever — and not because the read path
skipped it (0038 fixed that). It resolved the entity's own publication
domains from evidence rows carrying `origin = 'internal'`, and measured on
production 2026-08-09:

    SELECT origin::text, count(*) FROM evidence_index GROUP BY 1
      package  25385
      producer   152

`evidence_origin_t` HAS an `internal` label. No row has ever carried it.
So the condition was unsatisfiable, the numerator was always zero, `own`
was always empty, and the field was always null. A mechanism that cannot
fire is worse than no mechanism, because the code reads as though the path
exists and the surface reads as though the producer left it empty.

`entities.domain` is the column the schema declares for this. It is also
empty (0 of 166 rows), because nothing in the package scan writes it —
that half is upstream and stays open. What this migration fixes is the
half that would still have been broken after it was populated: **`svc_api`
holds no grant on `entities`** (only svc_migrate, svc_worker and svc_mcp
do), by the same design that makes `serving_directory` the one window the
API reads. So the read path could not have reached the column even once it
carried a value.

Carried on the view rather than granted on the base table, because 0013's
rule is the reason a header and its rows cannot disagree: the API resolves
a run in exactly one place. Named `entity_domain` rather than `domain`
because `overview_leadership.domain` already exists in this schema and
holds something else entirely — a FUNCTIONAL domain ("Technology",
"Risk", "Enterprise") — and two columns called `domain` meaning different
things is how the next reader gets it wrong.

Until something populates `entities.domain`, `self_sourced_pct` stays
null. It now says so on the surface, with the reason and what closes it,
instead of being absent.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-09
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


# 0042's body, verbatim, plus `e.domain`. A materialised view is rebuilt or
# it is not changed, so the body is carried whole rather than patched —
# exactly as 0042 carried 0031's and 0031 carried 0015's.
_VIEW_BODY = """
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
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
           AND r.withdrawn_at IS NULL
"""

_DOMAIN_COLUMN = "               e.domain        AS entity_domain,\n"
_PRE_0045_BODY = _VIEW_BODY.replace(_DOMAIN_COLUMN, "")
# 0042's guard, kept for the same reason: a .replace() that matches nothing
# returns the string unchanged and reports that to nobody, which would make
# downgrade() a no-op that claims success.
assert _PRE_0045_BODY != _VIEW_BODY, (
    "0045: the entity_domain column did not match the view body verbatim, so "
    "downgrade() would rebuild the view WITH the column it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0042's rebuild, verbatim: the refresh function depends on the view, so
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
    op.execute(
        "COMMENT ON COLUMN entities.domain IS "
        "'The entity''s own primary web domain, bare and lowercased "
        "(client.example, not https://www.client.example/). The denominator side of "
        "O11''s self_sourced_pct: an evidence row published here is the "
        "entity speaking about itself rather than a third party doing so. "
        "NULL on every row as of 0045 because no ingest path writes it; "
        "until one does the share is null with its reason stated, never a "
        "zero standing in for an uncomputed value.'")
    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    _rebuild(_PRE_0045_BODY)
