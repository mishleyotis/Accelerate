"""Synthesis and verification roles search nothing; the memory has one owner.

Measured 28-09-2026 (QA audit F-D02-008, F-G01-035): 31 agents that
synthesise or verify carried WebSearch and WebFetch (every per-surface
producer, the six page routers, the checkers, the challenger, the
verifiers), and three agents could write the findings memory. These tests
pin the boundary in three places at once — the manifests the provisioner
writes, the actor classes the hooks and the ledger refuse by, and the
instruction every stripped agent carries for asking the research tier
instead.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
AGENTS = PLUGIN / "agents"
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))
from engine import scope  # noqa: E402

HOOK = PLUGIN / "scripts" / "hooks" / "deny_whole_page_fetch.py"
NO_WEB_DIRS = ("production/", "checkers/", "qa/")
EXCEPT_FETCH = {"qa/deployed-app-auditor.md"}
MEMORY = ("record_finding", "record_refinement", "resolve_finding",
          "report_recurrence", "ingest_reviewer_feedback")


def _manifests():
    for p in sorted(AGENTS.rglob("*.md")):
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = FM.match(text)
        fm, body = m.group(1), text[m.end():]
        tools = {t.strip() for t in re.search(r"^tools:\s*(.*)$", fm, re.M).group(1).split(",")}
        yield str(p.relative_to(AGENTS)), tools, body


def test_no_synthesis_or_verification_agent_can_search_or_fetch():
    offenders = []
    for rel, tools, _ in _manifests():
        if not rel.startswith(NO_WEB_DIRS):
            continue
        if "WebSearch" in tools:
            offenders.append(f"{rel}: WebSearch")
        if "WebFetch" in tools and rel not in EXCEPT_FETCH:
            offenders.append(f"{rel}: WebFetch")
        if any(t.startswith(("mcp__Exa__", "mcp__Tavily__")) for t in tools):
            offenders.append(f"{rel}: search connector")
    assert offenders == [], offenders


def test_a_category_lane_holds_websearch_and_never_webfetch():
    """QA audit F-L11-042 pair 8 (29-09-2026): the protocol forbids a lane a
    whole-page fetch and the guard denies it, so a WebFetch grant on the
    sixteen lanes was a tool list that contradicted the rule it sat under."""
    lanes = [(rel, t) for rel, t, _ in _manifests() if rel.startswith("research/categories/")]
    assert len(lanes) == 16
    for rel, tools in lanes:
        assert "WebSearch" in tools and "WebFetch" not in tools, rel
        assert not any(t.startswith(("mcp__Exa__", "mcp__Tavily__")) for t in tools), rel


def test_the_app_auditor_keeps_its_read_of_production_and_nothing_else():
    tools = next(t for rel, t, _ in _manifests() if rel == "qa/deployed-app-auditor.md")
    assert "WebFetch" in tools and "WebSearch" not in tools


def test_the_findings_memory_has_one_owner_and_one_closer():
    holders = {rel for rel, tools, _ in _manifests()
               if any(t.endswith("__" + m) for t in tools for m in MEMORY)}
    assert holders == {"qa/qa-overseer.md", "learning/rectifier.md"}, holders


def test_every_stripped_agent_is_told_how_to_ask_the_research_tier():
    missing = []
    for rel, tools, body in _manifests():
        if rel.startswith(("production/", "checkers/")) or rel in (
                "qa/adversarial-verifier.md", "enrichment/enrichment-ledger-auditor.md",
                "enrichment/enrichment-planner.md"):
            if "search_requests" not in body or "## Searching is not this role's" not in body:
                missing.append(rel)
    assert missing == [], missing


def test_the_scope_table_names_the_new_classes():
    for actor, klass in [
        ("heatmap-focus-producer", "surface-producer"),
        ("overview-surface-producer", "surface-producer"),
        ("context-timeline-producer", "surface-producer"),
        ("evidence-integrity-checker", "verifier"),
        ("adversarial-verifier", "verifier"),
        ("enrichment-planner", "verifier"),
        ("deployed-app-auditor", "app-auditor"),
        ("research-p1c1-producer", "category-researcher"),
        ("finding-challenger", "challenger"),
        ("enrichment-web-specialist", "servicing"),
    ]:
        assert scope.classify(actor)["class"] == klass, actor
    # a synthesis class may write no research row through the ledger
    assert scope.violation("heatmap-focus-producer", "search", ["P1C1.1.1"])
    assert scope.violation("evidence-integrity-checker", "evidence", ["P1C1.1.1"])


def _hook(tool, agent, env=None):
    import os
    e = dict(os.environ)
    e.pop("DMA_ACTOR", None)
    e.update(env or {})
    ev = {"tool_name": tool, "tool_input": {"query": "x", "url": "https://example.com"}}
    if agent:
        ev["agent_type"] = f"dma-insights:{agent}"
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, timeout=60, env=e)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", ""), \
        (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


def test_the_hook_denies_a_search_to_a_synthesis_role_and_names_the_relay():
    for tool in ("WebSearch", "mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search"):
        for agent in ("heatmap-focus-producer", "finding-challenger",
                      "adversarial-verifier", "deployed-app-auditor"):
            decision, why = _hook(tool, agent)
            assert decision == "deny", (tool, agent)
            assert "search_requests" in why and "F-D02-008" in why
    # Tavily extract is a FETCHER (QA audit F-L11-042 pair 7, 29-09-2026):
    # denied to the same roles, with the fetch reason
    for agent in ("heatmap-focus-producer", "finding-challenger", "adversarial-verifier"):
        decision, why = _hook("mcp__Tavily__tavily_extract", agent)
        assert decision == "deny" and "engine.cli fetch" in why, (agent, why)
    # and a fetch, for the roles that read nothing on the web
    assert _hook("WebFetch", "heatmap-focus-producer")[0] == "deny"
    assert _hook("WebFetch", "evidence-integrity-checker")[0] == "deny"


def test_the_hook_still_lets_the_research_tier_search_and_the_app_auditor_fetch():
    assert _hook("WebSearch", "research-p1c1-producer")[0] == ""
    assert _hook("mcp__Exa__web_search_exa", "enrichment-web-specialist")[0] == ""
    assert _hook("WebSearch", "research-conductor")[0] == ""
    assert _hook("WebFetch", "deployed-app-auditor")[0] == ""
    # a headless child is identified by its environment
    assert _hook("WebSearch", None, env={"DMA_ACTOR": "overview-hero-producer"})[0] == "deny"
    assert _hook("WebSearch", None, env={"DMA_ACTOR": "research-p2c1-producer"})[0] == ""


def test_the_hook_is_wired_for_the_search_tools():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    matchers = [e.get("matcher", "") for e in hooks["hooks"]["PreToolUse"]
                if any("deny_whole_page_fetch" in h.get("command", "") for h in e.get("hooks", []))]
    assert matchers, "the hook is not wired"
    for tool in ("WebSearch", "mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search"):
        assert any(tool in m for m in matchers), tool
