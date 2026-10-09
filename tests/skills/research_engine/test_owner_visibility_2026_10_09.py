"""The owner sees every run, and every dollar, whichever way it was worked.

Owner, 2026-10-09: "I never saw the workflow." Three root causes, measured:
the owner follows every DMA session from the Claude app, where /workflows
does not render (it is a CLI/Desktop/IDE view); a session without the
Workflow tool worked handoffs as in-session agents, silently (the hook said
"STOP and restart", the skill said "do not restart, spawn agents"); and those
agents' spend reached no ledger — R-IMA-20261009's PRELIM relay agent cost
$8.85 over 158 turns, never booked, and the run read $18.41 of $25 while it
had spent $27.26.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from engine import cost
from engine import ledger as L
from engine import pipeline as P
from engine import pipeline_stub as S
from engine import preflight
from fixtures import new_run, preflight_doc, two_category_selection

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "dma-insights"
ENGINE = PLUGIN / "skills" / "dma-research" / "engine"


def _agent(d: Path, aid: str, prompt: str, meta: dict | None = None, turns: int = 3):
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "user", "message": {"content": prompt}})]
    for _ in range(turns):
        lines.append(json.dumps({"type": "assistant", "message": {
            "model": "claude-sonnet-x", "usage": {"input_tokens": 10,
            "cache_read_input_tokens": 100_000, "cache_creation_input_tokens": 1000,
            "output_tokens": 50}}}))
    (d / f"agent-{aid}.jsonl").write_text("\n".join(lines))
    if meta is not None:
        (d / f"agent-{aid}.meta.json").write_text(json.dumps(meta))


def test_an_in_session_agent_working_the_run_is_charged_to_the_stage_it_names(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    sub = tmp_path / "proj" / "sess" / "subagents"
    _agent(sub, "relay", f"You are servicing the PRELIM connector relay for DMA run {run.run_id}. "
                         f"connector run output follows",
           {"agentType": "dma-insights:enrichment-connector-specialist",
            "description": "Service PRELIM connector relay"})
    _agent(sub, "coll", f"collect batch for DMA run {run.run_id}",
           {"agentType": "dma-insights:research-evidence-collector", "description": "P3C2 collect 1"})
    # a helper that only READ the run (its prompt does not name it) is not its spend
    _agent(sub, "helper", "audit the sessions for workflow use",
           {"agentType": "general-purpose", "description": "Mine sessions"})
    (sub / "agent-helper.jsonl").write_text((sub / "agent-helper.jsonl").read_text()
                                            + "\n" + json.dumps({"type": "user", "message": {
                                                "content": f"tool output mentioning {run.run_id}"}}))
    got = cost.capture_workflows(run, base=tmp_path)
    assert got["captured"] == 2 and got["by_via"] == {"workflow": 0, "agent": 2}, got
    assert set(got["by_stage"]) == {"PRELIM", "RESEARCH"}, got["by_stage"]
    notes = [r["note"] for r in cost.ledger(run)]
    assert any("in-session agents (no workflow)" in n for n in notes), notes
    assert cost.capture_workflows(run, base=tmp_path)["captured"] == 0, "charged twice"


def test_a_handoff_worked_by_agents_is_recorded_and_said(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    logs = []
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                  reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                                  folder_root=tmp_path / "o", ingest_poll_s=0,
                                  sleep=lambda s: None, log=logs.append))
    p._note_worked_via({"by_via": {"workflow": 0, "agent": 3},
                        "by_stage": {"RESEARCH": {"via": {"agent": 3}}}})
    assert any("NOT a persisted workflow" in m for m in logs), logs
    rows = [r for r in run.open().rows("Gate_Log") if r["Gate"] == "HANDOFF_RESEARCH_WORKED_VIA"]
    assert rows and rows[0]["Verdict"] == "WARN"
    assert "say so to the owner" in p.state["worked_via_warning"]
    upd = p.owner_update({"outcome": "AWAITING_WORKFLOW", "stage": "RESEARCH"})
    assert "WARN" in upd


def test_every_run_ends_with_the_owner_update(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                  reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                                  folder_root=tmp_path / "o", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="tiers", tiers_direct=False,
                                  stage_budget={"RESEARCH": 100}))
    out = p.run_all()
    upd = p.owner_update(out)
    assert upd.startswith("OWNER UPDATE · ") and "spend $" in upd and "envelopes " in upd
    assert "research 0/2 categories pass" in upd and "now AWAITING_WORKFLOW" in upd
    assert "handed dma-research-tiers.js" in upd and "next " in upd
    assert (run.qa_dir / "progress.md").read_text().startswith("OWNER UPDATE")
    src = (ENGINE / "pipeline.py").read_text()
    assert 'print("\\n" + upd)' in src and '"owner_update": upd' in src, \
        "the run command prints the block, plain and --json"


def test_every_verdict_the_driver_writes_is_one_the_ledger_accepts():
    src = (ENGINE / "pipeline.py").read_text()
    written = set(re.findall(r'_record\(\w+, "([A-Z_]+)"', src)) | set(
        re.findall(r'verdict="([A-Z_]+)"', src))
    assert written and written <= set(L.GATE_VERDICTS), written - set(L.GATE_VERDICTS)


def _hook():
    spec = importlib.util.spec_from_file_location("stage_advance",
                                                  PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_hook_relays_the_owner_update_and_holds_one_no_workflow_rule(tmp_path, monkeypatch):
    sa = _hook()
    monkeypatch.setenv("DMA_RUN_ROOT", str(tmp_path))
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "python3 -m engine.pipeline run --run R --root X"},
          "tool_response": {"stdout": "SCOPE_COMPLETE at RESEARCH\n\nOWNER UPDATE · IMA · R\n  spend $1"}}
    ctx = sa.on_post_tool_use(ev)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("RELAY TO THE OWNER") and "Claude app" in ctx
    text = (PLUGIN / "scripts" / "hooks" / "stage_advance.py").read_text()
    assert "If Workflow is not available in this session, STOP" not in text, \
        "one rule: tell the owner, then the stage's fallback"
    assert text.count("NO_WORKFLOW_FIRST +") + text.count("NO_WORKFLOW_FIRST\n") >= 4
    # a tiers handoff's fallback is the driver running the same lean lanes
    hand = tmp_path / "07_qa" / "research_workflow.json"
    hand.parent.mkdir(parents=True)
    hand.write_text(json.dumps({"workflow": "/x/dma-research-tiers.js",
                                "invocations": [{"cats": ["P1C1"], "tiers": True}],
                                "then": "python3 -m engine.pipeline run --run R"}))
    ev2 = {**ev, "tool_response": {"stdout": f"AWAITING_WORKFLOW at RESEARCH — {hand}"}}
    ctx2 = sa.on_post_tool_use(ev2)["hookSpecificOutput"]["additionalContext"]
    assert "--tiers-direct" in ctx2 and "FIRST tell the owner" in ctx2


def test_the_skill_says_where_the_owner_sees_the_run():
    doc = (PLUGIN / "commands" / "run-assessment.md").read_text()
    assert "OWNER UPDATE" in doc and "Claude app" in doc
    assert "tell the owner" in doc.lower()


# ── the Workflow tool drops on a resume (SWBC 10-01, B1 10-08, Cross, Arbor) ──

def _contract():
    spec = importlib.util.spec_from_file_location(
        "connector_contract", PLUGIN / "scripts" / "connector_contract.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_baseline_records_the_workflow_tool_only_when_built_ins_were_listed(tmp_path):
    cc = _contract()
    assert cc.write_baseline(["Bash", "Read", "Workflow", "mcp__Clay__search-companies"],
                             root=tmp_path / "a")["workflow_tool"] is True
    assert cc.write_baseline(["Bash", "Read", "Agent"], root=tmp_path / "b")["workflow_tool"] is False
    assert "workflow_tool" not in cc.write_baseline(["mcp__Clay__search-companies"],
                                                    root=tmp_path / "c"), "unknown is not absent"


def test_a_degraded_run_in_a_session_without_workflow_runs_the_lanes_itself(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    (run.root / "connectors_baseline.json").write_text(json.dumps(
        {"present": [], "mcp_tools": [], "workflow_tool": False}))
    logs = []
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                  reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                                  folder_root=tmp_path / "o", ingest_poll_s=0,
                                  sleep=lambda s: None, log=logs.append, until="RESEARCH",
                                  research_mode="auto", tiers_direct=False,
                                  stage_budget={"RESEARCH": 100}))
    p.state["enrichment_degraded"] = True
    out = p.run_all()
    assert out["outcome"] != "AWAITING_WORKFLOW", "no workflow handed to a session that cannot run one"
    assert any("NO Workflow tool" in m for m in logs), logs
    assert "no Workflow tool" in p.owner_update(out)
