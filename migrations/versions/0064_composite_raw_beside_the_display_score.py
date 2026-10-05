"""The band reads a raw score kept BESIDE the 2dp display score (MEM-0560)

Owner decision A, 2026-10-04 (the Backend Schema, authority #1, against
invariant 6):

    keep `composite` NUMERIC(4,2) for display exactly as the Backend Schema
    states; ADD an expand-only raw column on the tables whose band is
    generated from it, and generate the band from the raw value. Do not
    widen `composite`.

WHAT WAS MEASURED. `overview_scores.band` and `heatmap_workbook_scores.band`
are GENERATED from `composite` / `score`, both NUMERIC(4,2) (0008), so the
band was computed AFTER rounding. SWBC's overview submission 29a75b69 sent
composite 2.0073; the column held 2.01. Both band Building, so nothing broke
visibly — but any raw value in [1.995, 2.0), [2.995, 3.0) or [3.995, 4.0)
stores as the next whole number and bands one tier HIGH. `runs.composite`
(the directory card's figure, read from the workbook at ingest) is rounded
the same way and the raw value existed nowhere.

THE CHANGE. Expand-only:

    runs                      + composite_raw NUMERIC, composite_raw_backfilled BOOLEAN
    overview_scores           + composite_raw NUMERIC, composite_raw_backfilled BOOLEAN
    heatmap_workbook_scores   + score_raw     NUMERIC, score_raw_backfilled     BOOLEAN

`composite` and `score` keep their NUMERIC(4,2) type, their values and every
reader. The raw columns are unscaled, so the figure the payload (or the
workbook) states is the figure stored. `band` is regenerated from
COALESCE(raw, display): the raw value wherever one exists, and the stored
display value only where nothing better was ever written — a row a
pre-0064 writer lands during a rolling deploy still bands exactly as it did.
PostgreSQL 16 cannot alter a generated expression in place, so `band` is
dropped and re-added under the same name in this one transaction; no view,
index or constraint references it (serving_directory reads `composite`).
`delta` is untouched: a 2dp display difference, not banded.

THE BACKFILL IS MARKED, BECAUSE IT IS NOT A RAW. Rows that exist before this
revision have no raw value anywhere — the rounding discarded it. They get
`*_raw` = the stored 2dp value and `*_raw_backfilled = TRUE`, only where no
raw exists, so their band is EXACTLY the band they had (COALESCE of equal
values). A reader that needs a true raw — a boundary audit, the DB<->resolver
agreement test — must exclude backfilled rows; the flag is what lets it. The
serving tables are rewritten on every promote, so a re-promote replaces the
backfill with the payload's raw value and the flag clears by construction.

WHO WRITES THE RAW VALUE. The promote writer (writer_spec.json) binds
`overview_scores.composite_raw` to the payload's `scores.composite` and
`heatmap_workbook_scores.score_raw` to each row's `score` — the same payload
field as the display column, stored without the NUMERIC(4,2) rounding. The
worker writes `runs.composite_raw` at ingest from the workbook's composite
before it rounds it once for `runs.composite`.

GRANTS, IN THIS REVISION. The tables carry table-level grants (0005, 0008),
which already reach a new column; the new columns are granted explicitly as
well, so the revision states who may read and write them rather than relying
on that inheritance: svc_api reads the serving pair, svc_mcp writes them,
svc_worker writes `runs`' and svc_mcp reads it.

Supersedes the unreleased 0064 that widened the three columns to unscaled
NUMERIC — never applied to production; replaced by owner decision before
merge.

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

#: (table, display column, raw column, generated band?)
_PAIRS = (
    ("runs", "composite", "composite_raw", False),
    ("overview_scores", "composite", "composite_raw", True),
    ("heatmap_workbook_scores", "score", "score_raw", True),
)


def _grant(sql: str, role: str) -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE '{sql} TO {role}';
          END IF;
        END $$;
    """)


def upgrade() -> None:
    # One statement per line, so scripts/gen_column_types.py reads each new
    # column's type straight off this file.
    op.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS composite_raw NUMERIC")
    op.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS composite_raw_backfilled BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE overview_scores ADD COLUMN IF NOT EXISTS composite_raw NUMERIC")
    op.execute("ALTER TABLE overview_scores ADD COLUMN IF NOT EXISTS composite_raw_backfilled BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE heatmap_workbook_scores ADD COLUMN IF NOT EXISTS score_raw NUMERIC")
    op.execute("ALTER TABLE heatmap_workbook_scores ADD COLUMN IF NOT EXISTS score_raw_backfilled BOOLEAN NOT NULL DEFAULT FALSE")

    for table, display, raw, banded in _PAIRS:
        if banded:
            # Dropped before the backfill so the generated column is computed
            # once, from the final values, when it is re-added below.
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS band")
        # Only where no raw exists, and marked: a 2dp copy is not a raw.
        op.execute(f"""UPDATE {table}
                          SET {raw} = {display}, {raw}_backfilled = TRUE
                        WHERE {raw} IS NULL AND {display} IS NOT NULL""")
        if banded:
            src = f"COALESCE({raw}, {display})"
            op.execute(f"ALTER TABLE {table} ADD COLUMN band band_t "
                       f"GENERATED ALWAYS AS {BAND_EXPR.format(col=src)} STORED")

    cols_os = "composite_raw, composite_raw_backfilled"
    cols_hws = "score_raw, score_raw_backfilled"
    _grant(f"GRANT SELECT ({cols_os}) ON overview_scores", "svc_api")
    _grant(f"GRANT SELECT, INSERT, UPDATE ({cols_os}) ON overview_scores", "svc_mcp")
    _grant(f"GRANT SELECT ({cols_hws}) ON heatmap_workbook_scores", "svc_api")
    _grant(f"GRANT SELECT, INSERT, UPDATE ({cols_hws}) ON heatmap_workbook_scores", "svc_mcp")
    _grant(f"GRANT SELECT, INSERT, UPDATE ({cols_os}) ON runs", "svc_worker")
    _grant(f"GRANT SELECT ({cols_os}) ON runs", "svc_mcp")

    # The production proof (private-IP DB): prod_apply.py logs VERIFY lines.
    print("VERIFY 0064 composite_raw on runs/overview_scores and score_raw on "
          "heatmap_workbook_scores (unscaled, backfilled rows marked); band "
          "generated from COALESCE(raw, display); composite/score stay NUMERIC(4,2)")


def downgrade() -> None:
    for table, display, raw, banded in _PAIRS:
        if banded:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS band")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {raw}_backfilled")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {raw}")
        if banded:
            op.execute(f"ALTER TABLE {table} ADD COLUMN band band_t "
                       f"GENERATED ALWAYS AS {BAND_EXPR.format(col=display)} STORED")
