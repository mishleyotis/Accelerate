"""0022 — pin a run to the catalogue it was actually scored against.

`serving_subcaps` names a cell by joining `ccg_subcaps` on
`COALESCE(r.ccg_catalog_version, <current>)`. So a run with a NULL
`ccg_catalog_version` is joined against the CURRENT catalogue — and a v5.0-shaped
assessment (17 categories, including the P1C5 ESG category v7.0 killed) matches
nothing there.

## What this was measured on

Baxter Credit Union, run `DMA-ASM-BCU-20260330-0001`, served through the API:

    subcaps served                765
      carrying a NAME               0      <- every heatmap cell is nameless
    get_capability_catalogue(run)
      ccg_catalog_version        NULL
      pillar names               NULL
      categories                    0
      subcaps                       0

Every cell on the grid, every drawer heading and every drilldown label therefore
rendered a raw taxonomy code or an em dash. It is the most visible single defect
on the heatmap, and it is one NULL column.

## Why a migration rather than a re-scan

The scanner resolves the version at ingest now, but a re-scan is idempotent by
design — an unchanged tree creates nothing — so it never revisits a run already
ingested. Same shape as 0021.

## How the version is chosen, and when it refuses to choose

Not from a category COUNT. Counting is what makes 16-vs-17 look like the whole
question, and it silently mis-pins a run whose category set happens to be the
right size and the wrong shape. Instead, the run's OWN distinct category ids are
matched as a SET against each catalogue version's category set, and a version is
pinned only when:

  · the run's categories are a SUBSET of that version's, and
  · exactly ONE version satisfies that.

A run matching several versions (its categories are common to both) or none is
left NULL and logged. Leaving it NULL keeps today's behaviour — the join falls
back to current — which is wrong but visible; guessing would be wrong and
invisible. Absent beats wrong applies to our own data repairs too.

Only NULL columns are written, so re-running is a no-op. The VERIFY lines are the
production proof.
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    versions = conn.exec_driver_sql(
        "SELECT version, count(*) FROM ccg_categories GROUP BY 1 ORDER BY 1"
    ).fetchall()
    print("VERIFY 0022 catalogues: "
          + ", ".join(f"{v}={n} categories" for v, n in versions))

    unpinned = conn.exec_driver_sql("""
        SELECT r.id, r.request_id,
               (SELECT count(DISTINCT s.category_id)
                  FROM subcap_scores s WHERE s.run_id = r.id) AS cats
          FROM runs r
         WHERE r.ccg_catalog_version IS NULL
         ORDER BY r.request_id
    """).fetchall()
    print(f"VERIFY 0022 runs with no catalogue pin: {len(unpinned)}")

    pinned = ambiguous = 0
    for run_id, request_id, cats in unpinned:
        # The run's own category ids, as a set — the shape, not the count.
        # pg8000 accepts only %s placeholders — a named parameter raises
        # "Only %s and %% are supported in the query", which rolled the whole
        # alembic transaction back and took 0021's work with it.
        matches = conn.exec_driver_sql("""
            SELECT c.version
              FROM ccg_categories c
             GROUP BY c.version
            HAVING NOT EXISTS (
                     SELECT 1
                       FROM (SELECT DISTINCT category_id
                               FROM subcap_scores
                              WHERE run_id = %s
                                AND category_id IS NOT NULL) r
                      WHERE r.category_id NOT IN (
                              SELECT category_id FROM ccg_categories
                               WHERE version = c.version))
        """, (run_id,)).fetchall()
        names = [m[0] for m in matches]
        if len(names) == 1:
            conn.exec_driver_sql(
                "UPDATE runs SET ccg_catalog_version = %s WHERE id = %s",
                (names[0], run_id))
            pinned += 1
            print(f"VERIFY 0022 pin: {request_id} ({cats} categories) -> {names[0]}")
        else:
            ambiguous += 1
            print(f"VERIFY 0022 LEFT NULL: {request_id} ({cats} categories) "
                  f"matches {names or 'no catalogue'} — a subset of "
                  f"{len(names)} versions is not an identification")

    print(f"VERIFY 0022 pinned={pinned} left_null={ambiguous}")

    named = conn.exec_driver_sql("""
        SELECT count(*) FILTER (WHERE sc.name IS NOT NULL), count(*)
          FROM subcap_scores s
          LEFT JOIN runs r ON r.id = s.run_id
          LEFT JOIN ccg_subcaps sc
                 ON sc.subcap_id = s.subcap_id
                AND sc.version = r.ccg_catalog_version
    """).fetchone()
    print(f"VERIFY 0022 scored cells resolving a catalogue NAME: "
          f"{named[0]} of {named[1]}")


def downgrade() -> None:
    """Not reversible in a way that means anything.

    Clearing every ccg_catalog_version would also clear the pins the scanner set
    correctly, and there is no record of which runs this touched. The forward
    direction only ever fills a NULL, and only on an unambiguous set match, so
    re-running is a no-op and there is nothing to undo.
    """
    pass
