"""No served cell belongs to another institution's sub-vertical.

Reported from production: Baxter Credit Union's heatmap drilled into
insurance-carrier, RIA and insurance-broker cells — sub-vertical T2
VARIANT cells (`P1C1.3.IC1`, `P2C4.6.RIA1`, `P1C1.4.IB1`) that the
assessment workbook carried and the ingest faithfully stored. 59 of the
765 cells the run served belonged to somebody else, and none of them
carried a synthesis card, which is how they were spotted.

The exclusion is a SERVING decision (the ingested tier is read-only once
scanned), so these tests drive the read path, not the loader. Two things
are asserted and one is asserted about: that a foreign variant never
serves, that a base or family cell always does, and that the /subcaps
grid and the value-chain derivation apply the SAME rule — a cell hidden
from the grid but listed in a stage would render an unresolvable tile.

The fixture ids are shaped like the catalogue's, never copied from it:
nothing here is a list of production ids, and adding a variant cell to
the catalogue must not require touching this file.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import (SUBVERTICAL_CODES, resolve_subvertical,  # noqa: E402
                                  scope_to_entity, serves,
                                  variant_subvertical)
from dma_api.value_chain import read_value_chain                  # noqa: E402

# A credit union's run, as production serves one: its own variants, other
# sub-verticals' variants, a family-code variant and plain base cells.
OWN = ["P1C1.3.CU1", "P2C1.1.CU2", "P3C1.8.CU1"]
FOREIGN = ["P1C1.3.IC1", "P2C4.6.RIA1", "P1C1.4.IB1", "P2C1.1.CIB3",
           "P1C1.3.CL1", "P1C2.4.RB1", "P4C1.2.AM1", "P3C2.1.FC1"]
FAMILY = ["P1C2.7.BK1", "P3C4.2.PEN1", "P1C1.3.WM1"]
BASE = ["P1C1.1.1", "P2C3.10.4", "P4C2.9.12"]
ALL_CELLS = OWN + FOREIGN + FAMILY + BASE


# ── the derivation ─────────────────────────────────────────────────────
def test_base_cells_have_no_owning_subvertical():
    """A base cell's terminal segment is numeric. Nothing about it names
    a sub-vertical, so it serves for everyone."""
    for cell in BASE:
        assert variant_subvertical(cell) is None


@pytest.mark.parametrize("cell,code", [
    ("P1C1.3.CU1", "CU"), ("P1C1.3.IC1", "IC"), ("P2C4.6.RIA1", "RIA"),
    ("P1C1.4.IB1", "IB"), ("P2C1.1.CIB3", "CIB"), ("P3C2.1.FC1", "FC"),
])
def test_variant_suffix_names_the_owning_subvertical(cell, code):
    assert variant_subvertical(cell) == code


def test_family_and_product_codes_are_not_treated_as_owners():
    """BK ("NCUA/FFIEC Governance") is the depository family — NCUA is the
    credit-union regulator — WM spans AM and RIA, PEN is a product line.
    None of the three names ONE sub-vertical, so none of them excludes."""
    for cell in FAMILY:
        assert variant_subvertical(cell) is None
        assert serves(cell, "CU") and serves(cell, "IC")


def test_every_single_subvertical_code_excludes_every_other():
    """The rule is symmetric across the whole vocabulary, so no
    sub-vertical is quietly exempt from it."""
    for owner in SUBVERTICAL_CODES:
        cell = f"P1C1.1.{owner}1"
        for viewer in SUBVERTICAL_CODES:
            assert serves(cell, viewer) is (owner == viewer)


# ── the serving decision ───────────────────────────────────────────────
def test_no_served_cell_belongs_to_a_foreign_subvertical():
    """The headline assertion: for an entity of a known sub-vertical, the
    served register contains no variant owned by another one."""
    served = scope_to_entity(ALL_CELLS, "SV2")          # SV2 = credit unions
    assert resolve_subvertical("SV2") == "CU"
    for cell in served:
        owner = variant_subvertical(cell)
        assert owner in (None, "CU"), f"{cell} belongs to {owner}"
    assert not set(FOREIGN) & set(served)


def test_own_base_and_family_cells_all_survive():
    """Only foreign variants go. Excluding a cell the assessment scored is
    the worse failure of the two, so it is asserted separately."""
    served = scope_to_entity(ALL_CELLS, "Credit Unions")
    assert set(served) == set(OWN + FAMILY + BASE)
    assert len(served) == len(ALL_CELLS) - len(FOREIGN)


def test_order_is_preserved_so_the_query_order_is_the_served_order():
    assert scope_to_entity(ALL_CELLS, "SV2") == [
        c for c in ALL_CELLS if c not in FOREIGN]


def test_an_unknown_sub_vertical_hides_nothing():
    """Not knowing who the entity is, is not grounds for hiding scores
    (invariant 9: absent beats wrong, in both directions)."""
    for raw in (None, "", "SV42", "Municipal Utilities"):
        assert scope_to_entity(ALL_CELLS, raw) == ALL_CELLS


def test_rows_may_be_tuples_or_dicts():
    """The /subcaps endpoint scopes DB tuples by column index; other
    callers scope dicts. One helper, so one rule."""
    tuples = [(c, 3.0) for c in ALL_CELLS]
    assert [r[0] for r in scope_to_entity(tuples, "SV2", key=0)] == \
        scope_to_entity(ALL_CELLS, "SV2")
    dicts = [{"subcap_id": c} for c in ALL_CELLS]
    assert [r["subcap_id"] for r in
            scope_to_entity(dicts, "SV2", key="subcap_id")] == \
        scope_to_entity(ALL_CELLS, "SV2")


# ── the two surfaces agree ─────────────────────────────────────────────
class _Cur:
    """The four reads read_value_chain makes, with the run's served
    register returned unscoped — exactly as serving_subcaps returns it."""

    def __init__(self, served):
        self.served = served
        self._out: list = []

    def execute(self, sql, params=None):
        if "FROM ccg_versions" in sql:
            self._out = [("v7.0",)]
        elif "FROM ccg_value_chains" in sql:
            self._out = [("VC-CU-01", "Member Acquisition", 1)]
        elif "FROM ccg_vc_mapping" in sql:
            self._out = [(cell, ["Member Acquisition"]) for cell in ALL_CELLS]
        elif "FROM serving_subcaps" in sql:
            self._out = [(cell,) for cell in self.served]
        else:                                            # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        return self._out


def test_value_chain_lists_only_cells_the_grid_also_serves():
    """A stage may name a foreign variant — the catalogue's mapping is not
    entity-scoped — but the run must not SERVE it. It counts as not_scored
    instead, which is the same treatment as any mapped-but-unscored cell."""
    data, empty = read_value_chain(
        _Cur(ALL_CELLS), {"sub_vertical": "SV2"},
        {"run_id": "11111111-1111-1111-1111-111111111111",
         "ccg_catalog_version": "v7.0"})
    assert empty is None
    listed = data["chains"][0]["subcaps"]
    assert not set(FOREIGN) & set(listed)
    assert set(listed) == set(OWN + FAMILY + BASE)
    # counted, never silently dropped (invariant 8)
    assert data["chains"][0]["not_scored"] == len(FOREIGN)
    assert data["not_scored_cells"] == len(FOREIGN)
