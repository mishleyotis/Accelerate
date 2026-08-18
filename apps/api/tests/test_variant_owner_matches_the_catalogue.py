"""The id-suffix rule, checked against the catalogue that mints the ids.

`variant_subvertical()` reads a cell's owner off its id — `P1C1.3.CU1` is a
credit-union variant — which is the catalogue's minting CONVENTION rather than
a stated fact. A convention held only in this repo is a convention that can
drift from its source without anything noticing.

The v7.0 catalogue does state it, in `2_Capability_Map!Tier`:

    T1         686 cells   a base cell; applies to every sub-vertical
    T2-<CODE>  127 cells   the catalogue NAMES the owner
    T2          38 cells   a variant the catalogue leaves unqualified

Measured 2026-08-15 against all four Pillar workbooks at
`gs://digital-maturity-assessor-catalogue-staging/v7.0/`: on every one of the
127 the catalogue names, the suffix agrees. **Zero contradictions.** On the 38
it leaves bare, the suffix does name an owner — and those include
`P1C1.3.IC1` "Insurance Line Strategy" and `P1C1.4.IB1", two of the exact cells
a credit union was served in the defect `subverticals.py` exists to close.

So the suffix rule is not merely consistent with the catalogue: it is strictly
MORE complete, and swapping it for the column would lose 38 exclusions. These
tests stop that being an assumption — if a later catalogue version qualifies
the remaining 38, or contradicts the suffix anywhere, this fails and the rule
gets re-derived instead of quietly drifting from its own source of truth.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import (SUBVERTICAL_CODES,  # noqa: E402
                                  serves, variant_subvertical)

TIER = json.loads(
    (ROOT / "packages" / "shared" / "catalogue_v70_tier.json").read_text())["tier"]


def _stated(tier: str):
    """The owner the CATALOGUE names, or None where it leaves it bare."""
    return tier.split("-", 1)[1] if tier.startswith("T2-") else None


def test_the_fixture_is_the_whole_catalogue():
    """851 cells is the charter's own count for v7.0. A truncated fixture
    would let this suite pass over a fraction of the taxonomy."""
    assert len(TIER) == 851, f"{len(TIER)} cells; v7.0 is 851"
    assert sum(1 for t in TIER.values() if t == "T1") == 686


def test_the_suffix_never_contradicts_the_catalogue():
    """The load-bearing assertion. Not 'mostly agrees' — never disagrees."""
    clashes = [(c, t, _stated(t), variant_subvertical(c))
               for c, t in TIER.items()
               if _stated(t) is not None and _stated(t) != variant_subvertical(c)]
    assert not clashes, (
        "the id-suffix derivation disagrees with the catalogue's own Tier "
        f"column on {len(clashes)} cell(s): {clashes[:5]}. The catalogue is "
        "the authority — re-derive the rule, do not adjust this test.")


def test_every_owner_the_catalogue_names_is_a_code_we_know():
    """A catalogue that adds a sub-vertical must not silently become one this
    module cannot see: an unknown code reads as 'not a claim' and serves to
    everybody."""
    named = {_stated(t) for t in TIER.values() if _stated(t)}
    assert named <= set(SUBVERTICAL_CODES), (
        f"the catalogue names {sorted(named - set(SUBVERTICAL_CODES))}, which "
        "SUBVERTICAL_CODES does not carry — those cells would serve to every "
        "entity")


def test_a_base_cell_is_never_read_as_owned():
    """T1 is 686 of 851. If the suffix rule ever claimed one, it would hide
    a cell from everyone — over-exclusion, the worse direction."""
    owned = [c for c, t in TIER.items()
             if t == "T1" and variant_subvertical(c) is not None]
    assert not owned, f"base cells read as variants: {owned[:5]}"


def test_the_catalogue_leaves_38_unqualified_and_the_suffix_covers_them():
    """The gap that makes the suffix rule worth keeping. Pinned by COUNT so
    that a catalogue which closes the gap is noticed rather than assumed."""
    bare = [c for c, t in TIER.items() if t == "T2"]
    assert len(bare) == 38, (
        f"the catalogue now leaves {len(bare)} variants unqualified, not 38. "
        "If it has started naming them, prefer the column and re-derive.")
    unowned = [c for c in bare if variant_subvertical(c) is None]
    assert not unowned, (
        f"the catalogue is silent AND the suffix is silent on {unowned[:5]} — "
        "those cells serve to every entity with nothing having decided so")


def test_the_two_cells_from_the_original_defect_are_still_excluded():
    """`P1C1.3.IC1` and `P1C1.4.IB1` are named in this module's docstring as
    cells a credit union was served. The catalogue leaves both bare, so they
    are precisely the cells that would come back if the column replaced the
    suffix."""
    for cell, owner in (("P1C1.3.IC1", "IC"), ("P1C1.4.IB1", "IB")):
        assert TIER[cell] == "T2", "the catalogue used to leave this bare"
        assert variant_subvertical(cell) == owner
        assert serves(cell, "CU") is False, "a credit union must not see it"
        assert serves(cell, owner) is True, "its own sub-vertical must"
