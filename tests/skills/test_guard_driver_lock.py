"""One driver per run — and the belt is honest that the brace is missing.

Two `engine.pipeline run` processes on one run is not a race for a row: it is
two lane fleets writing one workbook, two budgets counted as one, and a
`pipeline_state.json` whose round counter belongs to whoever wrote last. The
symptom is a run that reads as stalled while it is being driven twice.

The ENGINE primary (`runstate.acquire_driver_lock`) does not exist yet —
measured 2026-09-14, nothing in the plugin writes or reads a `driver.lock`.
These tests therefore also DOCUMENT the lock file shape this hook assumes, so
the engine's lock can be built to match it.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "plugins" / "dma-insights" / "scripts" / "hooks" / "guard_driver_lock.py"

DRIVE = "python3 -m engine.pipeline run --run {run} --root {root} --step"


@pytest.fixture()
def run(tmp_path: Path) -> Path:
    d = tmp_path / "run-driver-lock"
    (d / "07_qa").mkdir(parents=True)
    (d / f"DMA_Scoring_Workbook_{d.name}.xlsx").write_bytes(b"stub")
    return d


def _lock(run: Path, **over):
    doc = {"pid": os.getpid(), "host": socket.gethostname(),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "run_id": run.name,
           "command": "python3 -m engine.pipeline run --step"}
    doc.update(over)
    (run / "07_qa" / "driver.lock").write_text(json.dumps(doc))


def _run(command: str, run: Path | None = None) -> dict:
    e = dict(os.environ)
    if run is not None:
        e["DMA_RUN_ID"], e["DMA_RUN_ROOT"] = run.name, str(run)
    p = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True, text=True, timeout=60, env=e)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _decision(out) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "")


def _why(out) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


# ── the refusal ──────────────────────────────────────────────────────────

def test_a_second_driver_is_denied_while_the_first_is_live(run):
    _lock(run)                          # this test process IS a live pid
    out = _run(DRIVE.format(run=run.name, root=run), run)
    assert _decision(out) == "deny"
    assert "already has a driver" in _why(out)
    assert "engine.pipeline status" in _why(out)      # what to do instead


def test_the_refusal_says_the_engine_primary_is_still_missing(run):
    _lock(run)
    why = _why(_run(DRIVE.format(run=run.name, root=run), run))
    assert "acquire_driver_lock" in why
    assert "not built yet" in why


def test_the_lock_is_found_from_the_commands_own_root_flag(tmp_path, run):
    """The command names the run; the hook must not need the environment."""
    _lock(run)
    out = _run(DRIVE.format(run=run.name, root=run), None)
    assert _decision(out) == "deny"


# ── every unknown allows ─────────────────────────────────────────────────

def test_no_lock_file_allows(run):
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}


def test_a_dead_pid_allows(run):
    _lock(run, pid=999999)
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}


def test_a_stale_heartbeat_allows(run):
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))
    _lock(run, heartbeat=old, at=old)
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}


def test_a_lock_from_another_host_allows(run):
    """A pid on another machine is not a pid this hook can ask about."""
    _lock(run, host="some-other-container")
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}


def test_an_unparsable_lock_allows(run):
    (run / "07_qa" / "driver.lock").write_text("{not json at all")
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}
    (run / "07_qa" / "driver.lock").write_text('"a string"')
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}
    (run / "07_qa" / "driver.lock").write_text('{"no": "pid"}')
    assert _run(DRIVE.format(run=run.name, root=run), run) == {}


# ── what it does not match ───────────────────────────────────────────────

def test_the_read_only_pipeline_verbs_are_never_denied(run):
    _lock(run)
    for verb in ("plan", "status --watch", "env", "stages"):
        assert _run(f"python3 -m engine.pipeline {verb} --run {run.name}", run) == {}, verb


def test_an_unrelated_bash_command_is_untouched(run):
    _lock(run)
    assert _run("ls -la", run) == {}
    assert _run("python3 -m engine.cli evidence --run x --subcap P1C1.3", run) == {}


def test_it_fails_open_on_input_it_did_not_parse():
    for payload in ("not json", "", "[1,2,3]"):
        p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0
        assert not p.stdout.strip()
