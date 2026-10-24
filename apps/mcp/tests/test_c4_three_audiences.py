"""CG-03b (C4) — the context sentiment grid is three audience tiles, each with
a state that agrees with its rows.

RC-09 (SWBC gold audit, 2026-10-04; slice CTX-11). C4.md says "three tiles:
customer, employee, market" and "where nothing survives, the tile still ships:
rows: [], a state rung, and a sources_searched ladder". The machine contract
said only "Per tile: {audience, rows, e_ids}", so SWBC promoted TWO tiles (no
market tile) and no state on the empty employee tile, and every gate passed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_prose_shapes  # noqa: E402

RATED = {"source": "Google reviews", "rating": 4.9, "scale": "1-5", "n": 1000}


def _run(tiles):
    return _check_prose_shapes("context", "context_sentiment",
                               {"context_tiles": tiles})


SWBC = [{"audience": "customer", "rows": [RATED], "e_ids": ["E-CC-1434"]},
        {"audience": "employee", "rows": [], "e_ids": [],
         "note": "no dated rated line", "sources_searched": ["CareerBliss"]}]


def test_swbc_context_sentiment_two_tiles_is_refused():
    out = _run(SWBC)
    assert {r["gate_id"] for r in out} == {"CG-03b"}
    assert any("market" in r["message"] for r in out)
    assert any(r["path"].endswith("[1].state") for r in out)


def test_three_tiles_with_states_pass():
    tiles = [{"audience": "customer", "rows": [RATED], "e_ids": []},
             {"audience": "employee", "rows": [], "e_ids": [],
              "state": "WORKED_ABSENT"},
             {"audience": "market", "rows": [], "e_ids": [],
              "state": "UNWORKED"}]
    assert _run(tiles) == []


def test_industry_is_market():
    tiles = [{"audience": "customer", "rows": [RATED]},
             {"audience": "employee", "rows": [RATED]},
             {"audience": "industry", "rows": [RATED]}]
    assert _run(tiles) == []


def test_a_state_that_contradicts_the_rows_is_refused():
    tiles = [{"audience": "customer", "rows": [RATED], "state": "UNWORKED"},
             {"audience": "employee", "rows": [], "state": "RATED"},
             {"audience": "market", "rows": [], "state": "SOMETIMES"}]
    assert len(_run(tiles)) == 3


def test_the_shape_is_machine_contract():
    spec = sections("context")["context_sentiment"]["fields"]["context_tiles"]
    assert spec["item_shape"]["audiences"] == ["customer", "employee", "market"]
    assert "state" in spec["item_shape"]
    assert "{audience, state, rows, e_ids}" in spec["doc"]
