"""A citing lane reads windows; a servicing one reads the page.

The measurement behind the rule: a whole-page fetch is 5-40K tokens that then
sit in the lane's context and are re-read every later turn — 76% of one
measured run's bill was cache reads — where `engine.cli fetch` returns
240-character windows and caches the page so the ledger can verify the
excerpt against it.

The line is the actor table in engine/scope.py, and these pin BOTH sides of
it: the deny for the tiers that cite, the allow for the tiers that retrieve,
and the fail-open that keeps a guard from denying on its own bug.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "plugins" / "dma-insights" / "scripts" / "hooks" / "deny_whole_page_fetch.py"


def _run(payload: str, env=None) -> dict:
    e = dict(os.environ)
    e.pop("DMA_ACTOR", None)
    e.update(env or {})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                       capture_output=True, text=True, timeout=60, env=e)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _fetch(agent=None, tool="WebFetch", url="https://example.com/ir", env=None):
    ev = {"tool_name": tool, "tool_input": {"url": url, "prompt": "find it"}}
    if agent:
        ev["agent_type"] = f"dma-insights:{agent}"
    return _run(json.dumps(ev), env=env)


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "")


def test_a_research_lane_is_denied_and_told_the_command():
    out = _fetch("research-p1c1-producer")
    assert _decision(out) == "deny"
    why = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "engine.cli fetch" in why
    assert "--query" in why
    assert "https://example.com/ir" in why
    assert "cache reads" in why          # the measurement, not an assertion


def test_a_challenger_is_denied_too():
    for agent in ("research-challenger", "finding-challenger"):
        assert _decision(_fetch(agent)) == "deny", agent


def test_the_exa_fetcher_is_denied_on_the_same_rule():
    out = _fetch("research-p2c3-producer", tool="mcp__Exa__web_fetch_exa")
    assert _decision(out) == "deny"


def test_a_servicing_actor_is_allowed_verbatim_reading_is_its_path():
    for agent in ("research-conductor", "enrichment-web-specialist",
                  "enrichment-connector-specialist", "technographic-scanner"):
        assert _fetch(agent) == {}, agent


def test_a_person_at_a_terminal_is_untouched():
    assert _fetch(None) == {}
    assert _fetch("some-agent-this-table-never-heard-of") == {}


def test_a_headless_lane_is_identified_by_its_environment():
    """A headless child carries no `agent_type`; agent_run.py puts the name
    in DMA_ACTOR and every engine CLI defaults to it."""
    out = _fetch(None, env={"DMA_ACTOR": "research-p3c2-producer"})
    assert _decision(out) == "deny"
    assert _fetch(None, env={"DMA_ACTOR": "research-conductor"}) == {}


def test_websearch_is_never_denied_a_result_list_is_how_a_lane_finds_the_url():
    ev = {"tool_name": "WebSearch", "tool_input": {"query": "x"},
          "agent_type": "research-p1c1-producer"}
    assert _run(json.dumps(ev)) == {}


def test_it_fails_open_on_input_it_did_not_parse():
    assert _run("not json at all") == {}
    assert _run("") == {}
    assert _run("[1, 2, 3]") == {}
    assert _run(json.dumps({"tool_name": "WebFetch", "tool_input": "a string",
                            "agent_type": "research-p1c1-producer"})
                ).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
