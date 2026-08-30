"""0024 — the value chain reads as a business, not as a tab of a workbook.

`ccg_value_chains` is derived, never authored. The 0.4 loader walks the
`21_VC_Mapping_PerSubcap` tab, collects every distinct stage label a
sub-vertical's column names across ~850 cells, and mints one stage row
per label. That is a faithful derivation and it produced this:

    RB  49 stage rows    CU  48    IB  50    RIA 50    FC  45
    AM  54              CIB 53    CL  52    IC  54

Baxter Credit Union's heatmap served 30 of CU's 48 — the API strips two
marker shapes on read — and the front end then showed the five with the
deepest coverage and a line admitting to twenty-five more. A value chain
you have to truncate is not an arrangement; it is a list.

The count was the smaller half of the problem. Because four pillar
workbooks each named their own columns, one process arrived as several
stages in several voices:

    MEMBER SERVICING & BRANCH/DIGITAL       136 cells   pillar 2
    MEMBER SERVICE & DIGITAL ENGAGEMENT      96 cells   pillar 4
    MEMBER SUPPORT & HARDSHIP CARE           76 cells   pillar 2

Three stages, one process, three cases. Beside the prototype's standard —
"Digital Account Opening", "Loan Origination", "Member Servicing" — the
catalogue was shipping internal taxonomy to a client who expects to see
their own business.

## What lands here, and why it lands in the catalogue

`migrations/ccg_loader/value_chains.py` carries the arrangement: eight
stages per sub-vertical, in process order, each folding the workbook
labels that name the same process. It is a SELECTION and a RENAMING and
nothing else —

  · every curated stage's cell membership is the UNION of the labels it
    folds, so no cell is assigned by hand, invented, or lost;
  · no score is touched, and this tier cannot reach one;
  · markers are dropped ("- (N/A)", "Not applicable — credit unions
    follow NCUA framework", "(applicable via CIB pattern)",
    "(SV-Specific: P3C1.3.CU1)", "Indirect: …"), and across all nine
    sub-verticals the cells reachable ONLY through a marker are, without
    exception, another sub-vertical's variant cells — exactly the ones
    `subverticals.serves()` already keeps off the grid. For CU: 22 cells,
    all foreign.

It lands in the catalogue rather than in the renderer because the shape
of an institution's value chain is catalogue knowledge: every future
client of that sub-vertical inherits it, the API keeps deriving the
section by the join it always did, and the front end stops needing a cap
it should never have had.

## Both tables move together

The join between `ccg_value_chains.name` and
`ccg_vc_mapping.value_chain_stages` is by NAME. Renaming one side alone
empties every stage, silently, so the rename is applied to both in one
transaction — here for versions already loaded, and in the loader for
every version loaded from now on. `test_every_value_chain_stage_maps_to_
at_least_one_cell` is the standing check that they never drift apart.

Applying the map twice is a no-op: curated names are sentence case and
every workbook label is upper case, so a curated name is never a key of
the map that produced it. The migration is therefore safe to re-run, and
safe to run before OR after the loader re-loads the same version.

## The column

`source_stages TEXT[]` records which workbook labels a curated stage
folds. It is provenance, not data the API serves: without it, "which of
the workbook's words became this stage" is answerable only by reading
this module, and an arrangement nobody can audit is an arrangement
nobody should trust. Nullable, so the fallback derivation (a
sub-vertical the arrangement does not know) still loads. No GRANT is
needed: 0004 grants at table level.

## Measured on the catalogue this migration was written against

    v7.0  ccg_value_chains  445 stage rows -> 72   (nine sub-verticals x 8)
    v5.0  no VC tab in the workbooks, so no arrangement to curate; a
          v5.0-pinned run borrows v7.0's, which is the path Baxter takes
    Baxter Credit Union, run c1351d25: 30 served stages -> 8, and the
    cells under them unchanged.
"""
from alembic import op

from ccg_loader.value_chains import ARRANGEMENTS, arrangement, curate_row

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _array(values):
    """(sql fragment, params) for a TEXT[] literal.

    Built element-wise rather than passed as a list: this migration runs
    under pg8000 in the Cloud Run Job and under whatever
    LOCAL_DATABASE_URL names in dev, and an explicit ARRAY[...] means
    neither driver has to agree about how a Python list becomes an
    array.
    """
    if not values:
        return "ARRAY[]::text[]", []
    return ("ARRAY[" + ", ".join(["%s"] * len(values)) + "]::text[]",
            list(values))


def upgrade() -> None:
    conn = op.get_bind()

    op.execute("ALTER TABLE ccg_value_chains "
               "ADD COLUMN IF NOT EXISTS source_stages TEXT[]")

    versions = [r[0] for r in conn.exec_driver_sql(
        "SELECT DISTINCT version FROM ccg_value_chains ORDER BY 1").fetchall()]
    print(f"VERIFY 0024 catalogue versions carrying an arrangement: {versions}")

    for version in versions:
        for sv in sorted(ARRANGEMENTS):
            rows = conn.exec_driver_sql(
                """SELECT subcap_id, value_chain_stages
                     FROM ccg_vc_mapping
                    WHERE version = %s AND subvertical_code = %s
                    ORDER BY subcap_id""", (version, sv)).fetchall()
            if not rows:
                continue

            # 1 · the mapping side of the rename. Idempotent: a row already
            #     curated maps to itself.
            rewritten = 0
            for subcap_id, stages in rows:
                before = list(stages or ())
                after = curate_row(sv, before)
                if after == before:
                    continue
                frag, params = _array(after)
                conn.exec_driver_sql(
                    f"""UPDATE ccg_vc_mapping SET value_chain_stages = {frag}
                         WHERE version = %s AND subvertical_code = %s
                           AND subcap_id = %s""",
                    (*params, version, sv, subcap_id))
                rewritten += 1

            # 2 · the arrangement side. Replaced wholesale rather than
            #     updated in place: chain_id is half the primary key and the
            #     curated arrangement renumbers the stages (VC-CU-01..08),
            #     so there is no row-to-row correspondence to update along.
            (before_n,) = conn.exec_driver_sql(
                "SELECT count(*) FROM ccg_value_chains "
                "WHERE version = %s AND sub_vertical = %s",
                (version, sv)).fetchone()
            conn.exec_driver_sql(
                "DELETE FROM ccg_value_chains "
                "WHERE version = %s AND sub_vertical = %s", (version, sv))
            for stage in arrangement(sv):
                frag, params = _array(stage["source_stages"])
                conn.exec_driver_sql(
                    f"""INSERT INTO ccg_value_chains
                          (chain_id, version, sub_vertical, name, stage_order,
                           source_stages)
                        VALUES (%s, %s, %s, %s, %s, {frag})""",
                    (f"VC-{sv}-{stage['stage_order']:02d}", version, sv,
                     stage["name"], stage["stage_order"], *params))

            (covered,) = conn.exec_driver_sql(
                """SELECT count(*) FROM ccg_vc_mapping
                    WHERE version = %s AND subvertical_code = %s
                      AND cardinality(value_chain_stages) > 0""",
                (version, sv)).fetchone()
            print(f"VERIFY 0024 {version} {sv}: {before_n} stages -> "
                  f"{len(arrangement(sv))}, {rewritten} of {len(rows)} mapping "
                  f"rows rewritten, {covered} cells land in a stage")

    # The standing invariant of the pair, asserted here rather than trusted:
    # a stage no cell names would render an empty column under a client's
    # heading, and it is the exact failure a one-sided rename produces.
    orphans = conn.exec_driver_sql("""
        SELECT vc.version, vc.sub_vertical, vc.name
          FROM ccg_value_chains vc
         WHERE NOT EXISTS (
                 SELECT 1 FROM ccg_vc_mapping m
                  WHERE m.version = vc.version
                    AND m.subvertical_code = vc.sub_vertical
                    AND vc.name = ANY (m.value_chain_stages))
         ORDER BY 1, 2, 3""").fetchall()
    print(f"VERIFY 0024 stages naming no cell: {len(orphans)}"
          + (f" — {[tuple(o) for o in orphans[:5]]}" if orphans else ""))
    assert not orphans, "a value-chain stage that no cell maps to"

    totals = conn.exec_driver_sql(
        "SELECT version, count(*) FROM ccg_value_chains GROUP BY 1 ORDER BY 1"
    ).fetchall()
    print("VERIFY 0024 ccg_value_chains: "
          + ", ".join(f"{v}={n} stage rows" for v, n in totals))


def downgrade() -> None:
    """The column goes; the arrangement does not come back.

    Re-deriving the workbook's 45-to-54 raw labels needs the workbook,
    which is in GCS and not in this transaction — and the loader does
    exactly that on the next `--version` run, from the source of record.
    Dropping the column is the reversible half; re-loading the catalogue
    is the other half, and it belongs to the loader.
    """
    op.execute("ALTER TABLE ccg_value_chains DROP COLUMN IF EXISTS source_stages")
