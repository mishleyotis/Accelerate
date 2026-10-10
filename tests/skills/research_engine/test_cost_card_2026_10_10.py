"""The measured 5.5 rate card and the WebSearch fee (R-INTERAC-20261010, 2026-10-10).

Every figure below is a billed `total_cost_usd` from the CLI, kept as a fixture
so the card can be re-proved whenever it changes: the engine's price of a lane's
own modelUsage must reproduce what the lane was billed."""
import json
from pathlib import Path

import pytest

from engine import cost

# (input, cache_write, cache_read, output, web_search_requests, billed $) — claude-haiku-5-5
HAIKU_LANES = [
    (39200, 6456, 5663, 2390, 3, 0.03646283),      # controlled probe: 3 WebSearch calls
    (1190, 1273, 3045, 17, 0, 0.00041255),         # controlled probe: no tool
    (64344, 61489, 276537, 36323, 5, 0.08965907),  # lane P1C1-L1
    (71521, 43367, 237648, 24000, 6, 0.09020198),  # lane P2C1-L1
    (65209, 43361, 293514, 26358, 5, 0.08130724),  # lane P2C4-L1
    (127810, 71311, 388036, 40872, 10, 0.15135956),  # lane P4C1-L1
    (204123, 90735, 429742, 56337, 16, 0.23102522),  # lane P4C4-L1
]
# (input, cache_write, cache_read, output, billed $) — claude-sonnet-5-5
SONNET_LANES = [
    (14, 30066, 134220, 9727, 0.230984),           # judgement lane P3C1-J
    (10, 23446, 82772, 9329, 0.1953712),           # repair lane P3C1-R
    (12, 15663, 74701, 3053, 0.1006761),           # challenge P3C1 round 2
    (24, 69462, 623445, 6513, 0.4053705),          # prelim-techscan
]


@pytest.mark.parametrize("inp,cw,cr,out,ws,billed", HAIKU_LANES)
def test_the_card_reproduces_every_billed_haiku_lane(inp, cw, cr, out, ws, billed):
    got = cost.cost_of(model="haiku", uncached=inp, cache_write=cw, cache_read=cr,
                       output=out, web_searches=ws)["total_usd"]
    assert got == pytest.approx(billed, abs=0.0005)


@pytest.mark.parametrize("inp,cw,cr,out,billed", SONNET_LANES)
def test_the_card_reproduces_billed_sonnet_lanes_within_the_fit_residual(inp, cw, cr, out, billed):
    got = cost.cost_of(model="sonnet", uncached=inp, cache_write=cw, cache_read=cr,
                       output=out)["total_usd"]
    assert got == pytest.approx(billed, abs=0.0065)   # the least-squares fit's worst residual


def test_a_websearch_is_a_cent_on_the_model_bill_and_a_connector_search_is_not():
    p = cost.cost_of(model="haiku", uncached=39200, cache_write=6456, cache_read=5663,
                     output=2390, web_searches=3)
    assert p["parts_usd"]["search_fees"] == pytest.approx(0.03)
    assert p["share"]["search_fees"] > 0.8, "on a search-heavy turn the fee IS the cost"
    lean_ws = cost.research_price(57, categories=1, capabilities=9, lean=True)
    lean_cx = cost.research_price(57, categories=1, capabilities=9, lean=True, search_tool="connector")
    assert lean_ws["usd"] > lean_cx["usd"] * 1.5
    assert lean_cx["vendor_searches"] == lean_ws["searches"]


def test_capture_charges_a_turn_once_however_many_blocks_it_has(tmp_path):
    """A transcript writes one line per content block, each repeating the
    message's usage; a 15-call volley is 15 lines of ONE turn."""
    class Run:
        run_id = "R-TEST-1"
        qa_dir = tmp_path / "qa"
    Run.qa_dir.mkdir()
    d = tmp_path / "p" / "s" / "subagents"
    d.mkdir(parents=True)
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 1000,
             "cache_read_input_tokens": 50000, "output_tokens": 5}
    lines = [json.dumps({"type": "user", "message": {"content": "work for run R-TEST-1"}})]
    for i in range(15):
        lines.append(json.dumps({"type": "assistant", "message": {
            "id": "msg_1", "model": "claude-haiku-5-5", "usage": usage,
            "content": [{"type": "tool_use", "name": "WebSearch", "input": {"query": f"q{i}"}}]}}))
    (d / "agent-x.jsonl").write_text("\n".join(lines) + "\n")
    (d / "agent-x.meta.json").write_text(json.dumps({"description": "research"}))
    ledger = []
    orig = cost.record
    cost.record = lambda run, **kw: ledger.append(kw)
    try:
        got = cost.capture_workflows(Run, base=tmp_path)
    finally:
        cost.record = orig
    assert got["captured"] == 1 and got["turns"] == 1
    one_turn = cost.cost_of(model="haiku", uncached=10, cache_write=1000, cache_read=50000,
                            output=0)["total_usd"]
    # tokens once + 15 search fees; output is the blocks' own content
    assert got["usd"] == pytest.approx(one_turn + 15 * 0.01, abs=0.002)
