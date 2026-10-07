"""The Workflow in-flight hook: a handoff workflow the session starts is
recorded, a second identical start is denied, a resume passes.

Measured 2026-10-07: nothing recorded that a session had started the
workflows a handoff named, so the watchdog read a quiet one as orphaned and
the Stop hook printed the same Workflow calls again — every agent bought
twice. The hook is the one place the double dispatch can be refused: at the
tool, before it starts.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
HOOK = PLUGIN / "scripts" / "hooks" / "workflow_inflight.py"


def _event(hook: str, root: Path, *, resume: str | None = None, response=None) -> dict:
    ti = {"scriptPath": str(PLUGIN / "workflows" / "dma-pillar-scoring.js"),
          "args": {"run": "R-1", "root": str(root), "pillar": "P2",
                   "briefs": ["/b/1.md"], "rounds": 3}}
    if resume:
        ti["resumeFromRunId"] = resume
    ev = {"hook_event_name": hook, "tool_name": "Workflow", "tool_input": ti}
    if response is not None:
        ev["tool_response"] = response
    return ev


def _run(event: dict, env: dict | None = None) -> dict:
    import os
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=30,
                       env={**os.environ, **(env or {})})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else {}


def test_a_start_is_recorded_with_its_label_and_then_its_run_id(tmp_path):
    assert _run(_event("PreToolUse", tmp_path)) == {}            # allowed, silent
    doc = json.loads((tmp_path / "07_qa" / "workflow_inflight.json").read_text())
    (entry,) = doc["workflows"].values()
    assert entry["label"] == "SCORING P2" and entry["run"] == "R-1" and entry["started_at"]
    _run(_event("PostToolUse", tmp_path, response="Workflow started (run id wf_a1b2c3-scoring)"))
    doc = json.loads((tmp_path / "07_qa" / "workflow_inflight.json").read_text())
    (entry,) = doc["workflows"].values()
    assert entry["workflow_run_id"] == "wf_a1b2c3-scoring"
    assert 'resumeFromRunId: "wf_a1b2c3-scoring"' in entry["resume"]


def test_a_second_identical_start_is_denied_and_names_the_resume(tmp_path):
    _run(_event("PreToolUse", tmp_path))
    _run(_event("PostToolUse", tmp_path, response={"id": "wf_a1b2c3-scoring"}))
    out = _run(_event("PreToolUse", tmp_path))
    h = out["hookSpecificOutput"]
    assert h["permissionDecision"] == "deny"
    assert "already started" in h["permissionDecisionReason"]
    assert "wf_a1b2c3-scoring" in h["permissionDecisionReason"]


def test_a_resume_and_a_declared_restart_pass(tmp_path):
    _run(_event("PreToolUse", tmp_path))
    assert _run(_event("PreToolUse", tmp_path, resume="wf_a1b2c3-scoring")) == {}
    assert _run(_event("PreToolUse", tmp_path), env={"DMA_WORKFLOW_RESTART": "1"}) == {}


def test_a_different_handoff_is_not_a_duplicate(tmp_path):
    _run(_event("PreToolUse", tmp_path))
    other = _event("PreToolUse", tmp_path)
    other["tool_input"]["args"]["pillar"] = "P3"
    assert _run(other) == {}
    doc = json.loads((tmp_path / "07_qa" / "workflow_inflight.json").read_text())
    assert len(doc["workflows"]) == 2


def test_the_hook_fails_open_on_anything_else(tmp_path):
    assert _run({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "ls"}}) == {}
    assert _run({"hook_event_name": "PreToolUse", "tool_name": "Workflow",
                 "tool_input": {"scriptPath": "x.js", "args": "not json"}}) == {}
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and not r.stdout.strip()


def test_the_manifest_binds_the_hook_before_and_after_the_tool():
    doc = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    for event in ("PreToolUse", "PostToolUse"):
        assert any(e.get("matcher") == "Workflow" and "workflow_inflight.py" in e["hooks"][0]["command"]
                   for e in doc[event]), event
