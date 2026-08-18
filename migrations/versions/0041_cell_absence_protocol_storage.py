"""0041 — the cell-grain absence protocol gets the two columns it always needed.

## The measurement

On one Frost Bank heatmap payload, **394 of 697 `cell_evidence.cells` carried
`state` and `sources_searched`** — item keys the Surface Spec's H2 shape does
not declare and `heatmap_cell_evidence` has no column for. Because CG-04 sweeps
SECTION keys only, they validated; because `records_absence` and AG-03 read
whatever key is present, they bought exemption from CG-15 and from the citation
gate; and because no writer binds an unnamed key, promotion dropped every one
of them. Strip the invented keys and AG-03 refuses all 394 cells.

That is the discarded-field class (0027's own defect) being used as an escape
hatch, and the escape hatch was not dishonesty on the producer's part — it was
the only way to say a true thing the shape had no room for.

## Why the keys are legitimate, and why the fix is columns

The authority order settles it. The **TRD** (authority 2) already declares the
cell-level protocol under *Representing absence*: `thin: true`,
`sources_searched`, `closure_condition`. The **Surface Specification**
(authority 3) omits the last two from H2's item shape. The higher authority
wins, so the keys are real and what is missing is storage — not a rule against
using them.

`heatmap_alerts` has carried `sources_searched TEXT[]` and `closure_condition
TEXT` since 0008. This brings one table into line with its sibling; it invents
no shape.

Landed together with the contract entry and the two `item:` writer bindings, in
both copies of `writer_spec.json`, because `test_field_census.py`'s item-level
sweep goes red the moment a declared key has no column — that forcing function
is the whole reason the keys could not be added on their own.

Expand-only, exactly 0027's pattern: two nullable columns on an existing table,
no backfill, no default that would look like data. A promoted row from before
this revision reads NULL, which is the truth — nobody recorded a ladder there.

Revision ID: 0041
Revises: 0036
Create Date: 2026-08-08

Chained from 0036, not 0040: the file numbers here are not the revision order
(0031 revises 0035, 0036 revises 0040) and `alembic upgrade head` refuses to
run with two heads. The head is what it is whatever the next filename says.
"""
from alembic import op

revision = "0041"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE heatmap_cell_evidence
          ADD COLUMN IF NOT EXISTS sources_searched  TEXT[],
          ADD COLUMN IF NOT EXISTS closure_condition TEXT
        """
    )
    op.execute("""
        COMMENT ON COLUMN heatmap_cell_evidence.sources_searched IS
          'The ladder that established the absence: every source run across '
          'for THIS cell. TRD, Representing absence. Null where the cell '
          'cites evidence instead.'
    """)
    op.execute("""
        COMMENT ON COLUMN heatmap_cell_evidence.closure_condition IS
          'What would settle the question for THIS cell. Meaningless without '
          'sources_searched and thin — the three are one statement.'
    """)
    # Grants follow the table, not the column, and svc_mcp/svc_api already hold
    # theirs on heatmap_cell_evidence (0008). Re-asserted here so a rebuilt
    # database cannot end up with a column its readers cannot select.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON heatmap_cell_evidence TO svc_mcp")
    op.execute("GRANT SELECT ON heatmap_cell_evidence TO svc_api")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE heatmap_cell_evidence
          DROP COLUMN IF EXISTS closure_condition,
          DROP COLUMN IF EXISTS sources_searched
        """
    )
