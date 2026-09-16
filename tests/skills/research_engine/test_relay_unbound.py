"""An UNBOUND connector is not a lane that did not try.

Measured 2026-09-12: with a connector absent rather than refused, the tool
never appears in the child's tool list, so it emits no `tool_use` to witness
and produces no refusal marker. `manifest_check` passes (the .md declares
Exa) and `grants_check` passes (ALLOWED names every namespace), so every
branch of `heal_plan` fell through to `instruction` — whose text tells a
fresh lane "your previous instance never ATTEMPTED an enrichment connector …
fire one through mcp__Exa__web_search_exa".

That is a loop: an environment with no binding is permanently told it did not
try, and sent back to use a tool that does not exist. Each turn of it costs a
full lane instance. The run's own connector baseline is what tells the two
cases apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

from engine import ledger as L, relay
import fixtures as F

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
sys.path.insert(0, str(PLUGIN / "scripts"))
import connector_contract as cc  # noqa: E402


def _run_all_web_search(tmp_path, tools):
    run = F.new_run(tmp_path, n=4)
    wb = run.open()
    for c in [x for x in wb.selected_subcaps() if x.startswith("P1C1")][:2]:
        F.fire_volleys(wb, c, n=0, tool="web_search")
    cc.write_baseline(tools, str(run.root))
    return run, wb


def test_a_short_baseline_makes_the_verdict_unbound(tmp_path):
    run, wb = _run_all_web_search(tmp_path, ["Read", "Bash", "WebSearch"])
    plan = relay.heal_plan(run, wb, "P1C1")
    assert plan["heal"] == "unbound", plan["reason"]
    assert "not refused" in plan["reason"]
    assert "DO NOT retry" in plan["instruction"]
    assert "A human attaches the connector" in plan["instruction"]


def test_without_that_evidence_it_stays_the_old_instruction(tmp_path):
    """No baseline means nobody measured — which is not evidence the
    connector is unbound. The verdict must not be guessed."""
    run = F.new_run(tmp_path, n=4)
    wb = run.open()
    for c in [x for x in wb.selected_subcaps() if x.startswith("P1C1")][:2]:
        F.fire_volleys(wb, c, n=0, tool="web_search")
    assert relay.heal_plan(run, wb, "P1C1")["heal"] == "instruction"


def test_a_bound_session_is_not_called_unbound(tmp_path):
    fam = cc.families()
    run, wb = _run_all_web_search(
        tmp_path, [fam["exa"][0], fam["tavily"][0], fam["clay"][0]])
    assert relay.heal_plan(run, wb, "P1C1")["heal"] != "unbound"


def test_the_unbound_instruction_never_tells_a_lane_to_try_again(tmp_path):
    """The specific text that caused the loop."""
    unbound = relay.HEAL_INSTRUCTIONS["unbound"]
    assert "never ATTEMPTED" not in unbound
    assert "DO NOT retry" in unbound
    assert "search_requests" in unbound, "it must still say where the queries go"


def test_the_driver_discloses_unbound_without_spending_a_heal():
    """A heal is a fresh lane instance. Spending one on an absent tool buys a
    full context floor to rediscover the absence."""
    import inspect
    from engine import pipeline as P
    text = inspect.getsource(P.Pipeline._enrich_research)
    assert 'plan["heal"] == "unbound"' in text
    i, j = text.index('plan["heal"] == "unbound"'), text.index("if used < self.opts.enrichment_heals")
    assert i < j, "the unbound branch must come BEFORE the heal budget is spent"
