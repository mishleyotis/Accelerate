"""Hook and script regressions from the Cross Insurance live QA run
(2026-10-01, qa_audit/2026-10-01-cross/CASE_FACTS.md). Each test names the
case-facts id it pins. Hooks run as real subprocesses with the real event
shape, as the other hook suites do.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
HOOKS = SCRIPTS / "hooks"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HOOKS))

import agent_run  # noqa: E402
import connector_contract as cc  # noqa: E402
import doctor  # noqa: E402
import ensure_headless as eh  # noqa: E402


def _hook(name, event, env=None):
    r = subprocess.run([sys.executable, str(HOOKS / name)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, **(env or {})})
    out = r.stdout.strip()
    if not out:
        return None
    return (json.loads(out).get("hookSpecificOutput") or {}).get("permissionDecision")


# ── C-20 · a plain Firecrawl scrape is a read; an Alexandria call is spend ─

def test_firecrawl_scrape_of_a_url_is_approved():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "mcp__Firecrawl__firecrawl_scrape",
          "tool_input": {"url": "https://www.example.com/about",
                         "formats": ["query"], "queryOptions": {"prompt": "x"}}}
    assert _hook("autoapprove_connector.py", ev) == "allow"


def test_firecrawl_alexandria_execution_still_prompts():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "mcp__Firecrawl__firecrawl_scrape",
          "tool_input": {"alexandria": {"provider": "fred", "capability": "series"}}}
    assert _hook("autoapprove_connector.py", ev) is None


# ── C-10 · a registered run root is a write root ───────────────────────

def test_a_registered_run_root_is_a_write_root(tmp_path, monkeypatch):
    import autoapprove_builtins as ab
    root = tmp_path / "runs" / "acme"
    root.mkdir(parents=True)
    (root / "DMA_Scoring_Workbook_acme_2026-10-01.xlsx").write_bytes(b"x")
    gone = tmp_path / "runs" / "never-started"
    gone.mkdir()
    reg = tmp_path / "dma_run_registry.jsonl"
    reg.write_text(json.dumps({"run_id": "R-1", "root": str(root)}) + "\n"
                   + json.dumps({"run_id": "R-2", "root": str(gone)}) + "\n"
                   + json.dumps({"run_id": "R-3", "root": "/"}) + "\n")
    monkeypatch.setenv("DMA_RUN_REGISTRY", str(reg))
    roots = ab.registered_run_roots()
    assert root in roots
    assert gone not in roots            # no workbook: not a run root
    assert Path("/") not in roots       # never a top-level directory
    assert root in ab.write_roots()


# ── C-27 · the session's WebSearch budget ──────────────────────────────

def test_the_session_start_hook_sets_the_web_search_budget_once(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"permissions": {"defaultMode": "auto"}}))
    assert eh.ensure_web_search_budget(settings).startswith("websearch set")
    cfg = json.loads(settings.read_text())
    assert cfg["env"][eh.WEB_SEARCH_ENV] == eh.WEB_SEARCH_BUDGET
    assert cfg["permissions"]["defaultMode"] == "auto"
    cfg["env"][eh.WEB_SEARCH_ENV] = "900"           # a human's own number
    settings.write_text(json.dumps(cfg))
    assert eh.ensure_web_search_budget(settings) == "websearch kept=900"


def test_the_doctor_reports_the_web_search_budget(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION", raising=False)
    row = doctor.web_search_budget_check()
    assert row["ok"] and "WARN" in row["detail"] and "200" in row["detail"]
    monkeypatch.setenv("CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION", "4000")
    assert "WARN" not in doctor.web_search_budget_check()["detail"]


def test_bootstrap_sets_the_budget_before_the_session_starts():
    src = (SCRIPTS / "bootstrap_session.sh").read_text()
    assert "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION" in src


# ── C-17 · present is not funded: the measured health record ───────────

def test_connector_health_is_recorded_and_merged(tmp_path):
    cc.write_health(["exa=NO_CREDITS:HTTP 402", "tavily=OK"], str(tmp_path))
    cc.write_health(["tavily=RATE_LIMITED"], str(tmp_path))
    fams = cc.read_health(str(tmp_path))
    assert fams["exa"]["status"] == "NO_CREDITS" and fams["exa"]["note"] == "HTTP 402"
    assert fams["tavily"]["status"] == "RATE_LIMITED"
    try:
        cc.write_health(["exa=MAYBE"], str(tmp_path))
    except SystemExit as e:
        assert "STATUS" in str(e)
    else:
        raise AssertionError("an off-vocabulary status was recorded")


# ── C-09 · research lanes get a research preamble ──────────────────────

def test_research_family_lanes_get_the_research_preamble():
    names = agent_run.roster()
    for agent in ("research-conductor", "technographic-scanner",
                  "research-p1c1-producer", "scoring-critic", "report-validator"):
        pre = agent_run.preamble_for(agent, names)
        assert pre is agent_run.RESEARCH_PREAMBLE, agent
        assert "routing.md" not in pre and "get_memory_digest" not in pre
    assert agent_run.preamble_for("overview-hero-producer", names) is agent_run.PREAMBLE
    assert "MAY carry" in agent_run.PREAMBLE
