"""Two ways a run burned money without anyone being told.

1. NOBODY ASKED WHETHER THE WORK FITS THE LANE. At T1_CORE scope the
   per-subcap design needs 37.7 lane-equivalents of turns and the driver is
   given 16 — every category is 1.4-3.1x over its lane's 200-turn ceiling. A
   lane that cannot finish does not fail loudly: it runs out of turns, hands
   back, and is re-dispatched, re-paying its ~18K-token context floor cold.
   That is knowable before a single lane starts and was never computed.

2. THE WATCHDOG SPENT MORE ON A RUN THAT COULD NOT PROGRESS. A run with no
   enrichment connector reads as STALLED, and the hourly `dma-watchdog`
   Routine is told to `--revive` a STALLED run — a signal meaning "burning
   time, writing nothing" wired to a process authorised to spend more on it.
   `--revive` also walked ACTIONABLE rather than AGENT_ADVANCEABLE, so it
   re-dispatched even the states that list already excluded.
"""
from __future__ import annotations

import sys
from pathlib import Path

from engine import contract as C, cost, runstate, watchdog as W
import fixtures as F

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
sys.path.insert(0, str(PLUGIN / "scripts"))
import connector_contract as cc  # noqa: E402


# ── lane fit ────────────────────────────────────────────────────────────

def test_the_turn_cap_is_read_from_the_manifests_not_restated():
    """There is no `--max-turns` on the claude CLI, so the manifest value is
    the ONLY cap a lane has. A second copy here would drift from it in
    silence, which is how the version floors failed."""
    import re
    caps = set()
    for f in sorted((PLUGIN / "agents" / "research" / "categories").glob("*.md")):
        m = re.search(r"^maxTurns:\s*(\d+)", f.read_text(), re.M)
        if m:
            caps.add(int(m.group(1)))
    assert caps, "the research manifests must declare maxTurns"
    assert cost.lane_turn_budget() == min(caps)


def test_a_full_scope_run_does_not_fit_its_lanes(tmp_path):
    """THE MEASUREMENT. Pinned so the grain change has a number to beat."""
    tax = C.taxonomy()
    run = runstate.start(run_id="R-FIT", entity_name="Acme", entity_id="acme",
                         sub_vertical="CU", scope_mode="T1_CORE",
                         reference_date="2026-08-29", root=tmp_path / "run",
                         selected=list(tax.selected(scope="T1_CORE", sv=None)))
    fit = cost.lane_fit(run.open())
    assert fit["ok"] is False
    assert len(fit["over"]) == 16, "every category is over today"
    assert fit["lane_equivalents"] > 16, (
        "more lane-equivalents of work than there are lanes — the run cannot "
        "finish, and re-dispatch is the only thing that happens instead")
    assert "re-dispatched" in fit["why"] and "context floor" in fit["why"]


def test_a_small_category_does_fit(tmp_path):
    """The check must be able to say yes, or it is not a check."""
    run = F.new_run(tmp_path, n=4)
    fit = cost.lane_fit(run.open())
    assert fit["ok"] is True and fit["over"] == []


# ── the watchdog ────────────────────────────────────────────────────────

def _run_with_baseline(tmp_path, tools):
    run = F.new_run(tmp_path, n=4)
    run.open()
    cc.write_baseline(tools, str(run.root))
    return run


def test_a_run_with_no_connector_is_blocked_not_merely_stalled(tmp_path):
    run = _run_with_baseline(tmp_path, ["Read", "Bash", "WebSearch"])
    row = W.inspect(run)
    assert row["state"] == "BLOCKED_NO_CONNECTOR"
    assert "A HUMAN attaches the connector" in row["detail"]


def test_that_state_is_actionable_but_never_auto_revived():
    """Someone must be told; no agent can fix it from inside the container."""
    assert "BLOCKED_NO_CONNECTOR" in W.ACTIONABLE
    assert "BLOCKED_NO_CONNECTOR" not in W.AGENT_ADVANCEABLE


def test_a_run_that_holds_its_connectors_is_not_blocked(tmp_path):
    fam = cc.families()
    run = _run_with_baseline(tmp_path, [fam["exa"][0], fam["tavily"][0], fam["clay"][0]])
    assert W.inspect(run)["state"] != "BLOCKED_NO_CONNECTOR"


def test_revive_walks_agent_advanceable_not_actionable():
    """ACTIONABLE means "tell someone", not "an agent can fix it". `--revive`
    walked the wrong list, so it re-dispatched UNREADABLE and HALTED runs
    that AGENT_ADVANCEABLE already excluded."""
    import inspect as _inspect
    text = _inspect.getsource(W.main)
    assert 'r["state"] in AGENT_ADVANCEABLE' in text
    assert 'if r["state"] in ACTIONABLE:\n                revived.append(revive(' not in text
