"""0027 — the contract fields promotion had nowhere to put.

One defect, ten instances. A field is declared by the contract, validated at
submit, and then dropped on the floor at promotion because the serving table
has no column for it. Every gate passes; the client sees an empty surface.
`context_sentiment.context_tiles`, the leadership route and `techstack.dropped`
each shipped that way under a real client's name, which is why CG-13 exists.

CG-13 only ever looked at SECTION-level fields, so the whole ITEM level went
unswept: the keys a section's item shape declares (`Per issue: {…}`,
`Per item: {…}`) were never resolved against the writer's `item:` bindings.
This revision is the sweep's result — every item key the 34 writers could not
store, given a column, with the two families that legitimately have no column
recorded in the test rather than left to be re-discovered:

  context_issue_register.capped_subcap_ids
      "an issue is only interesting here because it CAPS something" (C2). The
      cells a matter caps, each with its cap level — {subcap_id, cap_level},
      the same item shape C3's enforcement_actions already carries inside its
      JSONB. Without it a reader sees a regulatory matter beside a score it
      appears not to touch, and the score looks unexplained. JSONB because the
      element is an object, not an id.

  overview_findings.subcap_id / score / peer_median / name
      The finding's ANCHOR: "the score chip and the anchor id must name the
      SAME cell (W1_workbook_fidelity)". The gate asserts the agreement at
      submit and then the three figures it compared were discarded, so the
      chip had nothing to render from and `linked_subcap_ids` (a list) cannot
      say which single cell the quoted score belongs to.

  overview_opportunity.headline / anchor_subcap_id
      Both named "(sources table)" by the O-tile contract: the gap framed as
      available value, and the cell the tile is about.

  platform_roadmap.phase_id / capability_labels
      `phase_id` is the phase's identity (`phase` is its ordinal). The
      contract lists rec_ids[] AND capabilities[] separately; 0008's
      `capabilities` column carries the REC IDS by its own DDL comment, so the
      capability labels had no home. The new column is bound to the contract's
      `capabilities` key by the writer spec — the column name differs from the
      payload key deliberately, because the taken name means something else.

  techstack_items.as_of
      The register row's own verification date. "A technographic claim about a
      named institution is a research finding: without source_url and as_of it
      is not one."

  heatmap_focus_areas.confidence, heatmap_cell_evidence.reach_note,
  heatmap_cohort_patterns.category_name
      Declared by their item shapes, stored nowhere.

  <five tables>.item_provenance
      The envelope-versus-item collision, and the one place two authorities
      disagree in a way the authority order does resolve. The Backend Schema
      wins on TABLE SHAPE: `provenance provenance_t` is one value per row, part
      of the universal envelope, and it stays exactly as it is — the writer
      fills it from `sys:provenance`, the submission-level argument, and the
      serving envelope reads it. The Surface Specification wins on PAYLOAD
      SHAPE: it states `provenance` per recommendation, per starter, per phase,
      per issue and per cell, "required, never blank". Those are two different
      facts — who produced the SECTION, and how THIS row was arrived at — and
      the writer was collapsing them, so a per-item value validated at submit
      and vanished, and a page with a mix of analyst and derived rows could not
      express it. Measured: `provenance` absent on 8 of 8 served
      recommendations and 5 of 5 starters. A second column, under a name the
      envelope has not taken, bound by the writer spec to the payload key
      `provenance` — so the payload shape is unchanged in both directions.

      TEXT, not `provenance_t`: the vocabularies genuinely differ per surface
      (starters are TEMPLATE_FILL|ANALYST, recommendations ANALYST|DERIVED,
      the roadmap analyst|derived) and an enum column would abort the promote
      transaction on a value the contract itself declares. They are policed at
      SUBMIT instead, by CG-09's contract-vocabulary registry, which is where a
      bad value can still be refused instead of crashing a promotion.

Expand only: nine ADD COLUMNs on nine existing tables, every one nullable, no
backfill, no rewrite, no index. Table-level grants already cover new columns in
Postgres (0008 grants SELECT on the table to svc_api and DML to svc_mcp), so no
new grant is owed — the re-grant below is belt and braces and is idempotent.

The tenth instance needed no column. `platform_story.gap_rows` was sourced from
`section:platforms.0.gaps` — the FIRST tile's gap rows out of five. The run
submitted five platform tiles, each with its own fit_score, gaps and story, and
promotion kept one; the client clicked the other four and found them empty. The
fix is in the writer spec (gap_rows now takes the whole `platforms[]` list, the
shape the column's own DDL comment predates), so all this revision does about it
is correct the comment the next reader will trust.
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

# (table, column, type) — every one nullable, every one a contract field the
# item shape declares and the writer had no column for.
COLUMNS = (
    ("context_issue_register", "capped_subcap_ids", "JSONB"),
    ("overview_findings", "subcap_id", "TEXT"),
    ("overview_findings", "score", "NUMERIC(4,2)"),
    ("overview_findings", "peer_median", "NUMERIC(4,2)"),
    ("overview_findings", "name", "TEXT"),
    ("overview_opportunity", "headline", "TEXT"),
    ("overview_opportunity", "anchor_subcap_id", "TEXT"),
    ("platform_roadmap", "phase_id", "TEXT"),
    ("platform_roadmap", "capability_labels", "TEXT[]"),
    ("techstack_items", "as_of", "DATE"),
    ("heatmap_focus_areas", "confidence", "confidence_t"),
    ("heatmap_cell_evidence", "reach_note", "TEXT"),
    ("heatmap_cohort_patterns", "category_name", "TEXT"),
    # the item's own provenance, beside — never instead of — the envelope's
    ("platform_recommendations", "item_provenance", "TEXT"),
    ("platform_starters", "item_provenance", "TEXT"),
    ("platform_roadmap", "item_provenance", "TEXT"),
    ("context_issue_register", "item_provenance", "TEXT"),
    ("heatmap_cell_evidence", "item_provenance", "TEXT"),
)

COMMENTS = (
    ("context_issue_register", "capped_subcap_ids",
     "[{subcap_id, cap_level}] — the cells this matter caps and at what level; "
     "same item shape as context_regulatory_standing.enforcement_actions"),
    ("overview_findings", "subcap_id",
     "the ANCHOR cell whose score the chip quotes; W1_workbook_fidelity "
     "asserts score/peer_median are this cell's own figures"),
    ("platform_roadmap", "capability_labels",
     "the contract's capabilities[] — human-readable capability labels. NOT "
     "the rec ids: those are in `capabilities`, per 0008's own comment"),
    ("techstack_items", "as_of",
     "the row's verification date; a technographic claim without one is not a "
     "research finding"),
    ("platform_recommendations", "item_provenance",
     "the contract's per-item provenance (how THIS row was arrived at). The "
     "envelope's `provenance` is a different fact — who produced the section "
     "— and keeps its own column"),
    ("platform_story", "gap_rows",
     "the contract's platforms[] — FIVE tiles of {platform, rank, fit_score, "
     "gaps[], story_md, ...}. 0008's comment described one tile's gaps[] "
     "because the DDL predates the five-tile shape; promotion stored tile 0 "
     "and discarded four (0027). `story` keeps the rank-1 tile's story_md for "
     "readers that predate the change"),
)


def upgrade() -> None:
    for table, column, type_ in COLUMNS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_}")
    for table, column, comment in COMMENTS:
        # A comment quotes the contract, and the contract is full of
        # apostrophes; doubling them here rather than in the literals keeps
        # the prose readable and the statement legal.
        op.execute("COMMENT ON COLUMN {}.{} IS '{}'".format(
            table, column, comment.replace("'", "''")))

    # Grants in the same revision as the table (build charter). Column
    # privileges follow the table's in Postgres, so these are already implied;
    # restating them is idempotent and costs nothing, and a future reader
    # looking for the grant finds it beside the DDL rather than in 0008.
    for table in sorted({t for t, _, _ in COLUMNS}):
        op.execute(f"GRANT SELECT ON {table} TO svc_api")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO svc_mcp")

    conn = op.get_bind()
    present = conn.exec_driver_sql("""
        SELECT table_name, column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND (table_name, column_name) IN (%s)
         ORDER BY 1, 2
    """ % ", ".join(f"('{t}','{c}')" for t, c, _ in COLUMNS)).fetchall()
    print(f"VERIFY 0027 columns added: {len(present)} of {len(COLUMNS)}", flush=True)
    for row in present:
        print(f"VERIFY 0027 column: {row[0]}.{row[1]}", flush=True)


def downgrade() -> None:
    for table, column, _ in COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
