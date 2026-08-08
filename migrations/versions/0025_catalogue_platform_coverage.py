"""0025 — a catalogue that lost its platform vocabulary said nothing about it

`ccg_subcaps.l3_platform_areas` and `.l4_features` are the per-cell
platform vocabulary: which named platforms address this capability, and
which features of them. They are what `get_report_bundle` hands a
producer when it asks "what could serve this gap", and what
`serving_subcaps` puts behind every chip on the workbook grid.

For every run pinned to v5.0 they were empty. All 836 cells, both
columns' worth for the platform column and 837 rows' worth for features
— not thin, EMPTY. The cause was a header spelling:

    v7.0   L3_Platforms_Addressing_SubCap   L4_Features_Available
    v5.0   Primary Products                 Key Features

The parser listed the v7.0 names only, so v5.0 fell through
`_get`'s prefix search and every cell loaded `{}`. The workbook was never
short of the data — "CRM Analytics, Tableau, Salesforce Platform" sits in
row 2 of Pillar 1 — and across the four v5.0 workbooks it names Twilio,
Databricks (five modules), Tableau, nCino, MuleSoft, Shield and 234 more
distinct platforms over 675 of the 837 cells.

What that cost is not abstract. A producer synthesising the platform page
for a credit union pinned to v5.0 had NO catalogue-derived candidates, so
it drew the candidate set from the entity's own Salesforce estate plus
two generic solution categories — and one of those two was an insurance
carrier product, set aside on a client-facing card that spent its words
explaining to a credit union why insurance policy administration does
not apply to them.

## The third silent drop

This pipeline has now lost a column to a header alias three times, and
each time the loss was invisible: the load succeeded, the row count was
right, the VERIFY lines were green, and the emptiness only surfaced when
somebody read a rendered page and found it generic. A load that drops a
column should not be able to look like a load that did not.

So `ccg_versions` gains one number:

    platform_mapped_cells INTEGER   -- cells whose l3_platform_areas is non-empty

The loader computes it in the same transaction that writes `cell_count`,
and `prod_apply.py` prints it beside the cell count. The database is
private-IP only, so that VERIFY line is the production proof — and a
future alias miss now reads as `platform_mapped=0` on a version with 836
cells, in the deploy log, at the moment it happens, instead of arriving
months later as a client asking why their recommendations sound generic.

Nullable, because it is a measurement of a load and a version loaded by
an older loader has no honest value to report. Backfilled here for the
versions already on disk rather than left NULL — the number is derivable
from the rows themselves, so leaving it unset would be a second way to
say "not measured" when the rows can be counted right now.

Expand only: one nullable column, no rewrite of a served row, no change
to any read path. The DATA fix rides the loader, which replaces a
version's rows on every run and is safe to re-run; this migration and
that reload land in the same migrate execution.

No GRANT is needed: 0004 grants `ccg_versions` at table level to all
three service roles.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-08
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ccg_versions "
               "ADD COLUMN IF NOT EXISTS platform_mapped_cells INTEGER")
    # Backfill from the rows themselves — every version already loaded gets
    # its true figure, including the zero that is the point of the column.
    op.execute(
        """
        UPDATE ccg_versions v
           SET platform_mapped_cells = (
                 SELECT count(*) FROM ccg_subcaps s
                  WHERE s.version = v.version
                    AND s.l3_platform_areas IS NOT NULL
                    AND cardinality(s.l3_platform_areas) > 0)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ccg_versions DROP COLUMN IF EXISTS platform_mapped_cells")
