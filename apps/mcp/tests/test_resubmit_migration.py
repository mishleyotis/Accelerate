"""A page promoted under an older gate set has a NAMED way back.

Review of fix/mcp-gates-contract (2026-10-04), residual P2: RC-09 made the C4
tile `state` required on a tile with no rated row, and RC-06 made
`firmographics.sub_vertical_undefined` a required boolean. Both are right, and
both land on clients already promoted before the keys existed:

  * Golden 1 (a gold run) serves two empty C4 tiles with no `state`, so its
    context page is refused by CG-03b on any resubmit — and promote_run
    re-gates RETAINED pages with the same validate_pass1, so fixing any OTHER
    page of Golden 1 is refused on the context page too;
  * Baxter serves sub_vertical_undefined: null, so its overview is refused by
    CG-02 the same way.

The refusal was correct and silent about the remedy: 'carries no rated row
and no state' / 'required field missing'. A producer met it on a page nobody
had touched. The migration now lives in the contract beside the key that
needs it (`item_shape.state_migration`, the field's `migration`), and the
refusal names it — what to set, how to choose the value from what the page
already carries, and that only that page needs resubmitting. For a C4 tile the
refusal also proposes the value from the tile's own ladder.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_prose_shapes, validate_pass1  # noqa: E402

RATED = {"source": "Apple App Store", "rating": 4.7, "scale": "1-5",
         "n": 87000, "as_of": "2026-05-01"}

# Golden 1's promoted context_sentiment, shape only (texts abridged): the
# customer tile is rated; employee and market are empty, carry a worked
# ladder, and predate `state`.
GOLDEN1_TILES = [
    {"audience": "customer", "rows": [RATED, dict(RATED, source="Play")],
     "e_ids": ["E-CC-606"], "note": "two rated rows",
     "sources_searched": ["Apple App Store listing — RESOLVED: 4.7 of 5"]},
    {"audience": "employee", "rows": [], "e_ids": ["E-CC-612"],
     "note": "quotable and not rateable",
     "sources_searched": [
         "Glassdoor employer overview — REACHED AND NOT CITABLE AS A BAR",
         "Great Place To Work directory — RESOLVED AS A CERTIFICATION",
         "Comparably, Built In and ZipRecruiter — NOT RUN on this pass"]},
    {"audience": "market", "rows": [], "e_ids": ["E-CC-680"],
     "note": "placements, not scales",
     "sources_searched": [
         "J.D. Power rankings naming Golden 1 — UNRESOLVED: no placement",
         "PRNewswire release, 12 January 2026 — RESOLVED AS A PLACEMENT"]},
]


def _c4(tiles):
    return _check_prose_shapes("context", "context_sentiment",
                               {"context_tiles": tiles})


def test_the_migration_is_contract_data():
    shape = sections("context")["context_sentiment"]["fields"][
        "context_tiles"]["item_shape"]
    assert "state_migration" in shape and "2-versioning" in \
        shape["state_migration"]
    fld = sections("overview")["firmographics"]["fields"][
        "sub_vertical_undefined"]
    assert "migration" in fld and "2-versioning" in fld["migration"]


def test_golden1_c4_refusal_names_the_migration_and_the_value():
    out = _c4(GOLDEN1_TILES)
    assert [r["path"] for r in out] == [
        "context_sentiment.context_tiles[1].state",
        "context_sentiment.context_tiles[2].state"]
    for r in out:
        assert r["gate_id"] == "CG-03b"
        msg = r["message"]
        assert "promoted before 2026-10-04" in msg, msg
        assert "2-versioning.md" in msg, msg
        # Both empty tiles carry a ladder whose every rung names an outcome,
        # so the proposed value is WORKED_ABSENT.
        assert "propose state: WORKED_ABSENT" in msg, msg


def test_a_tile_with_no_ladder_is_proposed_unworked():
    tiles = copy.deepcopy(GOLDEN1_TILES)
    tiles[2]["sources_searched"] = ["J.D. Power rankings"]   # no outcome
    out = _c4(tiles)
    assert "propose state: UNWORKED" in out[1]["message"], out[1]["message"]
    del tiles[2]["sources_searched"]
    out = _c4(tiles)
    assert "propose state: UNWORKED" in out[1]["message"], out[1]["message"]


def test_applying_the_named_migration_clears_the_gate():
    tiles = copy.deepcopy(GOLDEN1_TILES)
    tiles[1]["state"] = "WORKED_ABSENT"
    tiles[2]["state"] = "WORKED_ABSENT"
    assert _c4(tiles) == []


def _baxter_firmographics(value):
    body = {"fields": [{"field": "total_assets", "value": "1.2B"}],
            "sub_vertical_undefined": value}
    return {"firmographics": body}


def _cg02_on_flag(payload):
    return [r for r in validate_pass1("overview", payload)
            if r["path"] == "firmographics.sub_vertical_undefined"]


def test_baxter_null_flag_refusal_names_the_migration():
    out = _cg02_on_flag(_baxter_firmographics(None))
    assert [r["gate_id"] for r in out] == ["CG-02"]
    msg = out[0]["message"]
    assert "promoted before 2026-10-04" in msg, msg
    assert "2-versioning.md" in msg, msg


def test_the_flag_migration_clears_the_refusal():
    assert _cg02_on_flag(_baxter_firmographics(False)) == []
