"""A connector an agent declares and the harness denies is a silent failure.

REPORTED 2026-08-30: "enrichment connectors not being called by the agents
for enrichment purposes before close of a category."

Two barriers stood between a dispatched agent and Clay/Exa/Tavily, and only
one of them was written down anywhere.

The known one: `agent_run.py`'s docstring says a headless child does not
carry the claude.ai connectors, because they are attached to the Routine.
That is a BINDING fact and it belongs to the harness.

The one nobody had noticed: `agent_run.py` dispatches with
`--permission-mode dontAsk`, where everything not pre-approved is DENIED
rather than asked — and its `--allowedTools` list named exactly one MCP
namespace, the DMA connector. Every `mcp__Clay__*`, `mcp__Exa__*`,
`mcp__Tavily__*`, `mcp__Quartr__*`, `mcp__Vibe_Prospecting__*` and
`mcp__Indeed__*` call was refused by the PERMISSION layer before binding
ever came into it. That is MEM-0111's starvation shape — a child that
cannot act does not report that it could not act; it returns an empty
result that reads as "looked and found nothing".

Granting a namespace is not the same as binding it, and this file does not
pretend otherwise. It pins the half the repository controls: if an agent
manifest declares a connector, the dispatcher must not be the thing that
denies it.

The required set is DERIVED FROM THE ROSTER rather than typed here. A list
maintained by hand drifts the moment someone adds a connector to one agent,
and the drift is invisible until a run comes back thin.
"""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PLUGIN = HERE.parents[2]
AGENTS = PLUGIN / "agents"
REPO = PLUGIN.parents[1]
SCRIPT = PLUGIN / "scripts" / "agent_run.py"

#: Namespaces that are NOT enrichment and are granted (or withheld) on other
#: grounds, so the roster sweep below must not demand them.
_NOT_ENRICHMENT = {"mcp__plugin_dma-insights_connector"}


def declared_namespaces() -> Counter:
    """mcp__<Family> -> how many agent manifests declare it."""
    seen: Counter = Counter()
    for p in sorted(AGENTS.rglob("*.md")):
        if p.name == "README.md":
            continue
        m = re.search(r"^tools:(.*)$", p.read_text(encoding="utf-8")[:8000], re.M)
        if not m:
            continue
        for ns in set(re.findall(r"(mcp__[A-Za-z0-9_]+?)__", m.group(1))):
            if ns not in _NOT_ENRICHMENT:
                seen[ns] += 1
    return seen


def test_the_roster_declares_connectors_at_all():
    """Floor assertion: if this sweep stops finding anything, every test
    below passes vacuously and guards nothing."""
    seen = declared_namespaces()
    assert len(seen) >= 5, (
        f"only {len(seen)} connector namespace(s) found across the roster — "
        f"either the manifests changed shape or this regex stopped matching, "
        f"and either way the checks below are no longer guarding anything")


def _allowed_set() -> set:
    """The string agent_run.py ACTUALLY passes to --allowedTools.

    Read by importing and splitting the real constant, not by grepping the
    source. Grepping passed against a build where CONNECTOR_NAMESPACES was
    declared and then never spliced into ALLOWED — the namespaces were in
    the file and absent from the flag, which is exactly the bug wearing a
    disguise.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("agent_run", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return set(m.ALLOWED.split(","))


def test_every_declared_connector_is_allowed_by_the_dispatcher():
    """The one that was failing. In dontAsk mode, absent means DENIED."""
    allowed = _allowed_set()
    missing = sorted(ns for ns in declared_namespaces() if ns not in allowed)
    assert not missing, (
        f"agent manifests declare {missing} but agent_run.py does not "
        f"pre-approve them. It dispatches with --permission-mode dontAsk, "
        f"where anything not pre-approved is DENIED rather than asked, so "
        f"those calls fail silently and the child returns an empty verdict "
        f"that reads as 'searched and found nothing'.")


def test_every_declared_connector_is_allowed_in_project_settings():
    """The top session is the half that HAS the connectors bound — it must
    not stop to ask about each one, because a scheduled firing has nobody
    to answer."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    allow = set(settings.get("permissions", {}).get("allow", []))
    missing = sorted(ns for ns in declared_namespaces() if ns not in allow)
    assert not missing, (
        f"{missing} are declared by agents but not in .claude/settings.json "
        f"permissions.allow — a trigger-fired session has nobody to answer a "
        f"permission prompt, so it blocks or is denied. `dma-refresh-drift-"
        f"daily` was measured ABANDONED on exactly that shape.")


def test_explorium_reaches_the_technographic_lane():
    """The charter's REQ-A: the technographic scan is sourced from Explorium
    and Clay, NOT incidental web. Explorium ships as Vibe_Prospecting."""
    scanner = AGENTS / "research" / "technographic-scanner.md"
    if not scanner.exists():
        pytest.skip("technographic-scanner not at the expected path")
    tools = re.search(r"^tools:(.*)$", scanner.read_text()[:8000], re.M)
    assert tools, "technographic-scanner declares no tools line"
    for need in ("mcp__Vibe_Prospecting__", "mcp__Clay__"):
        assert need in tools.group(1), (
            f"{need} absent from the technographic scanner, whose whole "
            f"charter mandate (REQ-A) is to source the estate from Explorium "
            f"and Clay rather than incidental web search")


def test_the_dispatcher_grant_is_a_namespace_not_a_tool():
    """Namespace grants survive a connector adding a tool.

    `mcp__Exa` covers every Exa tool; `mcp__Exa__web_search_exa` covers one
    and silently denies the next one the connector ships. The narrower form
    is how a grant rots without anyone editing it.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    block = re.search(r"CONNECTOR_NAMESPACES = \((.*?)\)", src, re.S)
    assert block, "CONNECTOR_NAMESPACES is gone — the grant lost its source"
    for ns in re.findall(r'"([^"]+)"', block.group(1)):
        assert not ns.count("__") > 1, (
            f"{ns!r} grants ONE tool rather than the namespace; the next tool "
            f"that connector ships is denied and nobody edits this file")
