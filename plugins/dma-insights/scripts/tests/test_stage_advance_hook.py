"""The stage machine reaches the session at the moments it can act.

`hooks/stage_advance.py` runs `engine.watchdog` over the runs this container
holds and (a) after a dispatched agent or an engine command returns, tells
the session what state the run is in, the criterion that closes it and the
next agent to dispatch; (b) on Stop, refuses ONCE per state to end a session
whose run has a stage an agent can advance. These run the REAL hook as a
subprocess against a REAL run built through the engine's own start path.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOOKS = HERE.parent / "hooks"
HOOK = HOOKS / "stage_advance.py"
HOOKS_JSON = HERE.parent.parent / "hooks" / "hooks.json"
SKILL = HERE.parent.parent / "skills" / "dma-research"

sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(HOOKS))
from engine import runstate  # noqa: E402
import stage_advance as sa  # noqa: E402


def run_hook(event: dict, env: dict) -> dict | None:
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, **env})
    assert r.returncode == 0, f"the hook must never exit non-zero: {r.stderr}"
    return json.loads(r.stdout) if r.stdout.strip() else None


@pytest.fixture
def prelim_open_run(tmp_path):
    """A started run whose PRELIM is open — the first agent-advanceable
    state, and the one every real run passes through."""
    from engine import contract as C
    tax = C.taxonomy()
    cells = list(tax.cells_in("P1C1"))[:3]
    root = tmp_path / "runs"
    run = runstate.start(run_id="R-HOOK-1", entity_name="Acme Credit Union",
                         entity_id="acme-cu", sub_vertical="CU",
                         scope_mode="T1_CORE", reference_date="2026-08-29",
                         root=root / "R-HOOK-1", selected=cells)
    from engine import assemble
    assemble.open_folder(run, tmp_path / "client", push=False)
    return run, {"DMA_RUN_ROOT": str(root)}


# ── after an agent returns ────────────────────────────────────────────────

def test_an_agent_return_announces_the_state_criterion_and_next_agent(prelim_open_run):
    run, env = prelim_open_run
    out = run_hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                    "tool_input": {"subagent_type": "dma-insights:technographic-scanner"},
                    "tool_response": "done"}, env)
    assert out, "no context was added after a dispatched agent returned"
    text = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "STAGE ADVANCE" in text and "R-HOOK-1" in text
    assert "PRELIM_OPEN" in text
    assert "Completion criterion" in text and "engine.prelim complete" in text
    assert "research-conductor" in text
    assert "agent_run.py --agent research-conductor" in text


def test_a_headless_dispatch_finishing_announces_it_too(prelim_open_run):
    run, env = prelim_open_run
    out = run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                    "tool_input": {"command": "python3 plugins/dma-insights/scripts/"
                                              "agent_run.py --agent research-p1c1-producer "
                                              "--prompt-file /tmp/p.md"}}, env)
    assert out and "STAGE ADVANCE" in out["hookSpecificOutput"]["additionalContext"]


def test_an_unrelated_bash_call_does_not_open_a_workbook(prelim_open_run):
    run, env = prelim_open_run
    assert run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "ls -la /tmp"}}, env) is None


def test_a_container_with_no_runs_says_nothing(tmp_path):
    env = {"DMA_RUN_ROOT": str(tmp_path / "empty")}
    assert run_hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                     "tool_input": {"subagent_type": "x"}}, env) is None
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": False}, env) is None


def test_a_run_nobody_touched_recently_is_not_this_sessions(prelim_open_run):
    run, env = prelim_open_run
    old = 1_600_000_000                     # 2020
    os.utime(run.workbook_path, (old, old))
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": False}, env) is None


# ── on Stop ───────────────────────────────────────────────────────────────

def test_stop_is_refused_once_while_an_agent_can_advance_the_run(prelim_open_run):
    run, env = prelim_open_run
    out = run_hook({"hook_event_name": "Stop", "stop_hook_active": False}, env)
    assert out and out["decision"] == "block"
    assert "PRELIM_OPEN" in out["reason"] and "research-conductor" in out["reason"]
    # the marker records the state it refused on
    marker = json.loads((run.qa_dir / sa.MARKER).read_text())
    assert marker["blocked_on"] == "PRELIM_OPEN"


def test_the_same_state_twice_is_allowed_to_stop(prelim_open_run):
    """A stage that did not move after one re-dispatch needs a reader, not a
    third attempt — the loop guard, independent of stop_hook_active."""
    run, env = prelim_open_run
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": False}, env)
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": False}, env) is None


def test_stop_hook_active_is_always_honoured(prelim_open_run):
    run, env = prelim_open_run
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": True}, env) is None


def test_the_guard_can_be_switched_off_for_an_interactive_session(prelim_open_run):
    run, env = prelim_open_run
    assert run_hook({"hook_event_name": "Stop", "stop_hook_active": False},
                    {**env, "DMA_STAGE_GUARD": "off"}) is None


def test_a_decision_a_person_makes_never_blocks(tmp_path, monkeypatch):
    """HALTED (the catalogue moved), UNREADABLE and MISSING_LOCALLY are
    reported and never hold a session."""
    monkeypatch.setattr(sa, "recent_runs", lambda hours=12: [
        {"run_id": "R", "root": str(tmp_path), "state": "HALTED",
         "detail": "catalogue moved", "resume": {"actionable": False}},
        {"run_id": "R2", "root": str(tmp_path), "state": "MISSING_LOCALLY",
         "detail": "not here", "resume": {"actionable": True,
                                          "command": ["python3", "-m", "engine.registry", "pull"]}},
    ])
    assert sa.on_stop({"hook_event_name": "Stop", "stop_hook_active": False}) is None


def test_next_step_names_parallel_lanes_for_the_scoring_stage():
    row = {"run_id": "R", "entity": "Acme", "root": "/tmp/r",
           "state": "SCORING_OPEN", "detail": "unscored P1=3, P4=2",
           "criterion": "scored == subcaps",
           "resume": {"actionable": True, "agent": "scoring-p1-producer",
                      "parallel": ["scoring-p1-producer", "scoring-p4-producer"],
                      "prompt": "score", "why": "column D belongs to the scorers"}}
    text = sa.next_step(row)
    assert "`scoring-p1-producer`, `scoring-p4-producer` in parallel lanes" in text
    assert "Completion criterion: scored == subcaps" in text


def test_a_shipped_run_hands_over_to_the_synthesis_side():
    row = {"run_id": "R", "entity": "Acme", "root": "/tmp/r", "state": "SHIPPED",
           "detail": "package complete", "criterion": "done",
           "resume": {"actionable": False, "agent": None,
                      "why": "the package scan takes it"}}
    text = sa.next_step(row)
    assert "package scan" in text and "engine.ship state" in text


# ── resilience and wiring ────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["{ not json", "[]", "42", ""])
def test_malformed_input_is_silent(raw):
    r = subprocess.run([sys.executable, str(HOOK)], input=raw,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and not r.stdout.strip()


def test_the_hook_is_wired_at_all_three_moments():
    cfg = json.loads(HOOKS_JSON.read_text())
    post = {e.get("matcher"): " ".join(h["command"] for h in e["hooks"])
            for e in cfg["hooks"]["PostToolUse"]
            if "stage_advance.py" in " ".join(h["command"] for h in e["hooks"])}
    assert "Task|Agent" in post, "not wired after a dispatched agent returns"
    assert "Bash" in post, "not wired after a headless dispatch or engine gate"
    stop = cfg["hooks"].get("Stop") or []
    assert any("stage_advance.py" in h["command"] for e in stop for h in e["hooks"]), \
        "not wired on Stop — a session can end with a stage runnable"


def test_a_missing_handler_never_traps_a_session():
    cfg = json.loads(HOOKS_JSON.read_text())
    cmd = cfg["hooks"]["Stop"][0]["hooks"][0]["command"]
    r = subprocess.run(["sh", "-c", cmd], input=b'{"hook_event_name":"Stop"}',
                       capture_output=True,
                       env={**os.environ, "CLAUDE_PLUGIN_ROOT": "/nonexistent"})
    assert r.returncode == 0
    assert b"MISSING" in r.stdout and b"decision" not in r.stdout
