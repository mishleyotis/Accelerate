"""The generated band reads the RAW score, not a 2dp copy of it (MEM-0560)

Invariant 6: four bands, strict less-than, on the RAW score before display
rounding; the DB generated column and the frontend resolver must agree.

WHAT WAS MEASURED. `overview_scores.composite` and
`heatmap_workbook_scores.score` were NUMERIC(4,2), and each table's `band`
was GENERATED ALWAYS from that stored — already rounded — value (0008 BAND_EXPR).
`runs.composite`, the figure `serving_directory` serves on the client card
(0060's COALESCE), was NUMERIC(4,2) as well. SWBC's overview submission
29a75b69 (promoted 2026-10-01) sent composite 2.0073; the column held 2.01.
Both band Building, so nothing visibly broke — but a raw score in
[1.995, 2.0), [2.995, 3.0) or [3.995, 4.0) stored as the next whole number
and banded one tier HIGH, and the raw value existed nowhere in the serving
tier for the frontend resolver to agree with. The producer was then steered
to send 2dp "by owner decision", which made the loss permanent at source.
The display precision had been chosen as the storage precision, and the
band attached to the stored value.

THE CHANGE. The three columns widen to unscaled NUMERIC, so the value the
producer (or the workbook) states is the value stored, and `band` — and
the workbook grid's `delta` — are regenerated from it. Display rounding is
the frontend resolver's, which is where invariant 7 puts score -> band ->
hex already. Widening is lossless: every NUMERIC(4,2) value is a NUMERIC
value, so readers see the same numbers for every row written before today.

Expand-only in effect: no reader changes, no data moves, no column a
reader names disappears (the generated columns are dropped and re-added
under the same names in the same statement block; a generated expression
cannot be altered in place on PostgreSQL 16). The stored generated
columns are recomputed for every row — `overview_scores` holds one row per
run and the grid ~850 — so the rewrite is small.

`serving_directory` reads both `r.composite` and `os.composite`, and
PostgreSQL refuses to change the type of a column a view depends on, so
the materialised view is dropped first and rebuilt with 0061's body
verbatim, its indexes, its refresh function and EVERY grant on it — 0059's
`svc_worker` grant included, the one 0060 records that a rebuild silently
drops. Grants on the two tables are table-level and survive a column
change; nothing here grants anything new.

Out of scope, recorded: `subcap_scores.score` (the ingested tier, read-only
once scanned) is NUMERIC(4,2) with no generated band; the serving grid
reads `heatmap_workbook_scores`. Partitioning: not touched.

Revision ID: 0064
Revises: 0063
"""
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

#: 0008's BAND_EXPR verbatim — four branches, strict less-than.
BAND_EXPR = """(
  CASE WHEN {col} IS NULL THEN NULL
       WHEN {col} < 2.0   THEN 'Activating'::band_t
       WHEN {col} < 3.0   THEN 'Building'::band_t
       WHEN {col} < 4.0   THEN 'Competing'::band_t
       ELSE 'Differentiating'::band_t END)"""

#: 0061's body verbatim (the current serving_directory definition).
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

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _drop_directory() -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS serving_directory")


def _build_directory() -> None:
    """0061's rebuild, with every grant carried through it."""
    op.execute(f"CREATE MATERIALIZED VIEW serving_directory AS {_VIEW_BODY}")
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


#: The narrowing first and the widening second, as literal statements:
#: scripts/gen_column_types.py reads ALTER ... TYPE off the migration text,
#: later occurrences winning, so the type the database ends on is the last
#: one written here.
_NARROW = (
    "ALTER TABLE overview_scores ALTER COLUMN composite TYPE NUMERIC(4,2)",
    "ALTER TABLE heatmap_workbook_scores ALTER COLUMN score TYPE NUMERIC(4,2)",
    "ALTER TABLE runs ALTER COLUMN composite TYPE NUMERIC(4,2)",
)
_WIDEN = (
    "ALTER TABLE overview_scores ALTER COLUMN composite TYPE NUMERIC",
    "ALTER TABLE heatmap_workbook_scores ALTER COLUMN score TYPE NUMERIC",
    "ALTER TABLE runs ALTER COLUMN composite TYPE NUMERIC",
)


def _retype(statements) -> None:
    """Every score column that carries a generated band, retyped, with the
    generated columns dropped before and re-added after."""
    op.execute("ALTER TABLE overview_scores DROP COLUMN IF EXISTS band")
    op.execute("ALTER TABLE heatmap_workbook_scores DROP COLUMN IF EXISTS band")
    op.execute("ALTER TABLE heatmap_workbook_scores DROP COLUMN IF EXISTS delta")
    for sql in statements:
        op.execute(sql)
    op.execute("ALTER TABLE overview_scores ADD COLUMN band band_t "
               f"GENERATED ALWAYS AS {BAND_EXPR.format(col='composite')} STORED")
    op.execute("ALTER TABLE heatmap_workbook_scores ADD COLUMN band band_t "
               f"GENERATED ALWAYS AS {BAND_EXPR.format(col='score')} STORED")
    # delta stays a 2dp display difference; it is not banded.
    op.execute("ALTER TABLE heatmap_workbook_scores ADD COLUMN delta NUMERIC(4,2) "
               "GENERATED ALWAYS AS (score - peer_median) STORED")


def upgrade() -> None:
    _drop_directory()
    _retype(_WIDEN)
    _build_directory()
    op.execute("REFRESH MATERIALIZED VIEW serving_directory")
    # The production proof (private-IP DB): prod_apply.py logs VERIFY lines.
    print("VERIFY 0064 overview_scores.composite, heatmap_workbook_scores.score, "
          "runs.composite are unscaled NUMERIC; band regenerated from the raw value")


def downgrade() -> None:
    # Narrowing rounds every raw value to 2dp again — the defect this
    # revision removes. Kept so the chain is reversible, not because it is
    # a state anyone should return to.
    _drop_directory()
    _retype(_NARROW)
    _build_directory()
    op.execute("REFRESH MATERIALIZED VIEW serving_directory")
