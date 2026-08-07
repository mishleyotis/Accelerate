"""The curated value-chain arrangement, as tests.

Two halves. The first needs no database: the arrangement's own
invariants — the cap, one home per workbook label, and the property that
makes the rename re-runnable. The second joins against a loaded
catalogue and skips cleanly without one, in the style of
`test_catalogue_load.py`.

The defect these exist for: `ccg_value_chains.name` and
`ccg_vc_mapping.value_chain_stages` are joined by NAME, so a rename
applied to one side alone empties every stage while leaving both tables
looking perfectly well-formed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "migrations"))

from ccg_loader.value_chains import (  # noqa: E402
    ARRANGEMENTS, arrangement, curate_row, has_arrangement, is_marker)

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")

# The loader's own vocabulary. Every sub-vertical the catalogue keys on
# must have an arrangement, or its clients fall back to 45-plus raw
# labels without anything saying so.
SUBVERTICALS = ("RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB")


def test_every_subvertical_has_an_arrangement():
    assert sorted(ARRANGEMENTS) == sorted(SUBVERTICALS)


def test_no_arrangement_exceeds_eight_stages():
    over = {sv: len(stages) for sv, stages in ARRANGEMENTS.items()
            if len(stages) > 8}
    assert not over, f"more than eight stages: {over}"


def test_stage_names_are_unique_within_an_arrangement():
    for sv, stages in ARRANGEMENTS.items():
        names = [name for name, _ in stages]
        assert len(names) == len(set(names)), f"{sv} repeats a stage name"


def test_each_workbook_label_has_exactly_one_home():
    """A label folded into two stages would put its cells in both, which
    is how a stage silently acquires cells that belong elsewhere."""
    for sv, stages in ARRANGEMENTS.items():
        seen = {}
        for name, raws in stages:
            for raw in raws:
                assert raw not in seen, (
                    f"{sv}: {raw!r} is folded into both {seen[raw]!r} "
                    f"and {name!r}")
                seen[raw] = name


def test_no_curated_name_is_also_a_workbook_label():
    """What makes applying the rename twice a no-op: a curated name is
    never a key of the map that produced it."""
    for sv, stages in ARRANGEMENTS.items():
        labels = {raw for _, raws in stages for raw in raws}
        for name, _ in stages:
            assert name not in labels, f"{sv}: {name!r} is also a raw label"


def test_curate_row_is_idempotent():
    for sv, stages in ARRANGEMENTS.items():
        labels = [raw for _, raws in stages for raw in raws]
        once = curate_row(sv, labels)
        assert curate_row(sv, once) == once, f"{sv} does not settle"


def test_curate_row_folds_duplicates_and_keeps_order():
    # CU's three servicing labels are one stage, named once.
    got = curate_row("CU", ["MEMBER SERVICING & BRANCH/DIGITAL",
                            "MEMBER SUPPORT & HARDSHIP CARE",
                            "MEMBER SERVICE & DIGITAL ENGAGEMENT",
                            "PAYMENTS / CARD PROCESSOR"])
    assert got == ["Member servicing & digital engagement",
                   "Payments & card operations"]


def test_markers_are_dropped_and_unknown_labels_are_kept():
    got = curate_row("CU", ["- (N/A)",
                            "Not applicable — credit unions follow NCUA framework",
                            "(applicable via CIB pattern)",
                            "(SV-Specific: P3C1.3.CU1)",
                            "Indirect: credit unions also cooperative",
                            "SOMETHING THE WORKBOOK GREW LATER"])
    # Markers out; a label with no home stays visible rather than taking
    # its cells down with it.
    assert got == ["SOMETHING THE WORKBOOK GREW LATER"]
    assert all(is_marker(m) for m in (
        "- (N/A)", "Not applicable — x", "(applicable via RB pattern)",
        "(SV-Specific: P3C1.8.CU1)", "Indirect: whatever", "", "  "))
    assert not is_marker("MEMBER SERVICING & BRANCH/DIGITAL")


def test_an_unknown_subvertical_passes_through_untouched():
    assert not has_arrangement("ZZ")
    assert curate_row("ZZ", ["- (N/A)", "WHATEVER"]) == ["- (N/A)", "WHATEVER"]


def test_stage_order_is_dense_and_one_based():
    for sv in ARRANGEMENTS:
        orders = [s["stage_order"] for s in arrangement(sv)]
        assert orders == list(range(1, len(orders) + 1)), sv


# ── against a loaded catalogue ────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    pg8000 = pytest.importorskip("pg8000.dbapi")
    host = DSN.split("@")[1].split(":")[0]
    try:
        conn = pg8000.connect(user="postgres", password="local", host=host,
                              port=5432, database="dma_insights")
    except Exception as exc:                                # pragma: no cover
        pytest.skip(f"no database: {exc}")
    cur = conn.cursor()
    cur.execute("SELECT version FROM ccg_versions WHERE is_current")
    row = cur.fetchone()
    if not row:
        pytest.skip("no catalogue loaded")
    yield conn, row[0]
    conn.rollback()
    conn.close()


def _q(db, sql, params=()):
    conn, _ = db
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def test_loaded_catalogue_serves_at_most_eight_stages_per_subvertical(db):
    _, version = db
    rows = _q(db, """SELECT sub_vertical, count(*) FROM ccg_value_chains
                      WHERE version = %s GROUP BY 1 ORDER BY 1""", (version,))
    over = [(sv, n) for sv, n in rows if n > 8]
    assert not over, f"arrangements over the cap: {over}"


def test_no_loaded_stage_name_is_a_workbook_marker(db):
    _, version = db
    names = [n for (n,) in _q(
        db, "SELECT DISTINCT name FROM ccg_value_chains WHERE version = %s",
        (version,))]
    assert names, "no stages loaded"
    assert not [n for n in names if is_marker(n)]


def test_every_cell_a_real_label_named_still_lands_in_a_stage(db):
    """Cell conservation. A curated stage is the union of its sources, so
    the set of cells reachable through the arrangement must not shrink —
    the only cells that may fall out are those a MARKER alone named, and
    those are another sub-vertical's variant cells."""
    _, version = db
    for sv in SUBVERTICALS:
        (loose,) = _q(db, """
            SELECT count(*) FROM ccg_vc_mapping m
             WHERE m.version = %s AND m.subvertical_code = %s
               AND cardinality(m.value_chain_stages) > 0
               AND NOT EXISTS (
                     SELECT 1 FROM ccg_value_chains vc
                      WHERE vc.version = m.version
                        AND vc.sub_vertical = m.subvertical_code
                        AND vc.name = ANY (m.value_chain_stages))""",
                      (version, sv))[0]
        assert loose == 0, f"{sv}: {loose} cells name a stage that does not exist"
