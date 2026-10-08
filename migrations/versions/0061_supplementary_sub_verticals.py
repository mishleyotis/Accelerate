"""An entity may be bound to more than one sub-vertical's variant cells

`entities.sub_vertical` holds ONE value, and every scope rule in the build —
the API's `serves()` on read, the connector's ET-05 on submit — admits a T2
variant cell only when its code is that one value. A multi-line-of-business
institution therefore had nowhere to say "these other lines are ours too".

WHAT THAT COSTS, measured on SWBC (`swbc`, run 7968492e, 2026-09-30). The
owner bound it primary IB (insurance brokers) with supplementary IC, CL and
RIA: its insurance carrier, commercial lending and wealth lines are real
businesses the assessment researched — 66 variant cells beyond the 694 a
single IB binding selects (the research engine's
`binding.supplementary_sub_verticals`, CASE_FACTS I-06). With one column the
serve path would hide all 66 as "somebody else's" and ET-05 would refuse the
pages that cite them. Equally, no OTHER sub-vertical's variants may serve:
RB (retail banking) cells are not SWBC's whatever the workbook measured.

## What this revision adds

1. `entities.supplementary_sub_verticals TEXT[]`, nullable, default NULL.
   NULL means "none bound", which is every entity today — the scope rule is
   unchanged for all of them. The values are the catalogue's VC codes (the
   nine `SUBVERTICAL_CODES`), CHECKed here so a misspelling is refused at
   write rather than silently admitting nothing on read. The PRIMARY stays
   in `sub_vertical` and keeps its free-form vocabulary; only it drives the
   display label.
2. `serving_directory` gains `trading_name` and
   `supplementary_sub_verticals`. svc_api holds no SELECT on `entities` (by
   design, 0013): everything the read path knows about an entity comes from
   this one view, so a column the scope rule needs and the view does not
   carry is a column the API cannot see. `trading_name` rides the same
   rebuild because the web's name fallback (legal → trading → display id)
   needs it on the same row the header already reads.

## Grants

None new on the table: `entities` grants are table-level (svc_worker
INSERT/SELECT/UPDATE, svc_mcp SELECT), and a table-level grant covers a
column added later. The view rebuild re-applies every grant 0060 applies —
svc_api SELECT, and EXECUTE on `refresh_serving_directory()` for svc_mcp
AND svc_worker (0059). Dropping the function takes its grants with it, and
recreating only one of them would silently un-fix 0059.

Expand only. Nothing is dropped that is not rebuilt in the same statement
group; no data moves. Downgrade rebuilds 0060's view and drops the column.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-02
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

#: The catalogue's VC codes — `SUBVERTICAL_CODES` in
#: apps/api/dma_api/subverticals.py and its connector mirror. A test holds
#: this tuple to that one.
SUBVERTICAL_CODES = ("RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB")

_CODES_SQL = ", ".join(f"'{c}'" for c in SUBVERTICAL_CODES)

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
               COALESCE(r.composite, os.composite) AS composite,
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
               (ad.assessment_date + INTERVAL '6 months')::date AS refresh_due_date,
               e.trading_name,
               e.supplementary_sub_verticals
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          LEFT JOIN overview_scores os ON os.run_id = r.id
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(COALESCE(rm.payload -> 'workbook_metadata', '{}'::jsonb)
                                              || COALESCE(rm.payload -> 'manifest', '{}'::jsonb), r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
           AND r.withdrawn_at IS NULL
"""

# The two new columns are APPENDED, so every positional reader of the view
# keeps its indexes; removing exactly those two lines is 0060's body.
_PRE_0061 = _VIEW_BODY.replace(
    "refresh_due_date,\n               e.trading_name,\n"
    "               e.supplementary_sub_verticals\n",
    "refresh_due_date\n")

# 0042's guard, for its reason: a substitution that produced the same string
# either way would make downgrade() a no-op that reports success.
assert _PRE_0061 != _VIEW_BODY, (
    "0061: the column removal did not apply, so downgrade() would rebuild "
    "the view WITH the columns it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0060's rebuild, with every grant carried through it."""
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
    op.execute("ALTER TABLE entities "
               "ADD COLUMN IF NOT EXISTS supplementary_sub_verticals TEXT[] "
               "DEFAULT NULL")
    op.execute("ALTER TABLE entities "
               "DROP CONSTRAINT IF EXISTS entities_supplementary_sv_known")
    op.execute("ALTER TABLE entities ADD CONSTRAINT "
               "entities_supplementary_sv_known CHECK ("
               "supplementary_sub_verticals IS NULL OR "
               f"supplementary_sub_verticals <@ ARRAY[{_CODES_SQL}]::TEXT[])")
    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    # The view first: it reads the column the next statement drops.
    _rebuild(_PRE_0061)
    op.execute("ALTER TABLE entities "
               "DROP CONSTRAINT IF EXISTS entities_supplementary_sv_known")
    op.execute("ALTER TABLE entities "
               "DROP COLUMN IF EXISTS supplementary_sub_verticals")
