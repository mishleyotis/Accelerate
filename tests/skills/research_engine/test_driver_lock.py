"""One driver per run, and the hook and the engine agree on what that means.

Measured 2026-09-14: nothing stopped two drivers walking one run at once.
The engine's only lock is the per-workbook `.xlsx.lock` flock, which
serialises ROWS — it makes each write safe and says nothing about two
processes dispatching the same category, spending two budgets against one
ceiling, and overwriting each other's `pipeline_state.json`. That state file
was also written in place, so a reader could see half a document.

The lock is cooperative and says so. It cannot stop a driver that ignores
it, which is why `guard_driver_lock.py` reads the same file at the command
seam — and why this module asserts the two readers agree rather than each
having its own opinion of "held".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import runstate

import fixtures as F

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "guard_driver_lock.py"


def _run(tmp_path):
    return F.new_run(tmp_path, n=2)


# ── the engine's own answer ──────────────────────────────────────────────

def test_an_unlocked_run_is_claimed_and_says_who_holds_it(tmp_path):
    run = _run(tmp_path)
    assert runstate.read_driver_lock(run) is None
    rec = runstate.acquire_driver_lock(run, command="engine.pipeline run")
    assert rec["pid"] == os.getpid() and rec["run_id"] == run.run_id
    held = runstate.read_driver_lock(run)
    assert held["live"] is True and held["stale_reason"] is None


def test_a_second_driver_is_refused_and_told_what_it_costs(tmp_path):
    """The refusal has to name the consequence, or the next person works
    around it: two drivers dispatch one category twice and spend two budgets
    against one ceiling."""
    run = _run(tmp_path)
    runstate.acquire_driver_lock(run)
    # Someone else's live pid: pid 1 exists in every container and is not us.
    p = runstate.driver_lock_path(run)
    rec = json.loads(p.read_text())
    rec["pid"] = 1
    p.write_text(json.dumps(rec))
    with pytest.raises(runstate.DriverLocked) as e:
        runstate.acquire_driver_lock(run)
    assert "held by pid 1" in str(e.value)
    assert "two budgets against one ceiling" in str(e.value)
    assert e.value.holder["pid"] == 1


def test_the_same_process_may_reclaim_its_own_run(tmp_path):
    """A resume inside one process is not a second driver."""
    run = _run(tmp_path)
    runstate.acquire_driver_lock(run)
    runstate.acquire_driver_lock(run)                  # no refusal


def test_a_dead_pid_is_reaped_rather_than_waited_on(tmp_path):
    """A run nobody can resume because a dead container's file is still
    there is the worse failure."""
    run = _run(tmp_path)
    p = runstate.driver_lock_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 2 ** 22, "host": runstate._hostname(),
                             "at": "2026-09-14T10:00:00Z",
                             "heartbeat": "2026-09-14T10:00:00Z"}))
    held = runstate.read_driver_lock(run)
    assert held["live"] is False and "pid is gone" in held["stale_reason"]
    rec = runstate.acquire_driver_lock(run)
    assert rec["reaped"] and rec["pid"] == os.getpid()


def test_a_stale_heartbeat_is_reaped_even_when_the_pid_is_alive(tmp_path):
    """A pid can be reused, and a driver that stopped beating half an hour
    ago is not walking a run."""
    run = _run(tmp_path)
    p = runstate.driver_lock_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 1, "host": runstate._hostname(),
                             "at": "2020-01-01T00:00:00Z",
                             "heartbeat": "2020-01-01T00:00:00Z"}))
    held = runstate.read_driver_lock(run)
    assert held["live"] is False and "heartbeat" in held["stale_reason"]
    runstate.acquire_driver_lock(run)                  # no refusal


def test_a_lock_from_another_host_never_blocks_this_one(tmp_path):
    """Pids are meaningless across containers, and a run root can be shared."""
    run = _run(tmp_path)
    p = runstate.driver_lock_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 1, "host": "some-other-box",
                             "at": "2026-09-14T10:00:00Z",
                             "heartbeat": "2026-09-14T10:00:00Z"}))
    assert runstate.read_driver_lock(run)["live"] is False
    runstate.acquire_driver_lock(run)


def test_an_unreadable_lock_is_not_a_held_run(tmp_path):
    """Fail OPEN on a file this code did not write: a truncated lock must not
    make a run permanently unrunnable."""
    run = _run(tmp_path)
    p = runstate.driver_lock_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    assert runstate.read_driver_lock(run) is None
    runstate.acquire_driver_lock(run)


def test_the_heartbeat_moves_and_only_the_holder_may_move_it(tmp_path):
    run = _run(tmp_path)
    runstate.acquire_driver_lock(run)
    before = runstate.read_driver_lock(run)["heartbeat"]
    assert runstate.heartbeat_driver_lock(run) is True
    p = runstate.driver_lock_path(run)
    rec = json.loads(p.read_text())
    rec["pid"] = 1
    p.write_text(json.dumps(rec))
    assert runstate.heartbeat_driver_lock(run) is False, (
        "a process that no longer holds the lock must not steal it back")
    assert before                                       # the field exists


def test_release_is_idempotent_and_only_the_holder_releases(tmp_path):
    run = _run(tmp_path)
    runstate.acquire_driver_lock(run)
    assert runstate.release_driver_lock(run) is True
    assert runstate.release_driver_lock(run) is False
    assert runstate.read_driver_lock(run) is None


def test_the_lock_is_written_whole_or_not_at_all(tmp_path):
    """Write-then-rename. `pipeline_state.json` was written in place, so a
    reader could see half a document; the lock uses the same helper and this
    is where that helper is pinned."""
    import inspect
    src = inspect.getsource(runstate._write_atomic)
    assert "os.replace" in src, "rename, never a partial write in place"
    run = _run(tmp_path)
    runstate.acquire_driver_lock(run)
    assert json.loads(runstate.driver_lock_path(run).read_text())["pid"] == os.getpid()
    assert not list(runstate.driver_lock_path(run).parent.glob("*.tmp"))


# ── the hook reads the same file the same way ────────────────────────────

def _hook(cmd: str, run) -> dict:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": cmd}, "cwd": str(run.root)}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def _decision(out: dict) -> str:
    h = out.get("hookSpecificOutput") or {}
    return str(h.get("permissionDecision") or out.get("decision") or "")


@pytest.mark.skipif(not HOOK.is_file(), reason="guard_driver_lock.py not installed")
def test_the_hook_denies_the_second_driver_the_engine_would_refuse(tmp_path):
    run = _run(tmp_path)
    cmd = f"python3 -m engine.pipeline run --run {run.run_id} --root {run.root}"
    assert _decision(_hook(cmd, run)) != "deny", "an unlocked run is not held"
    runstate.acquire_driver_lock(run)
    p = runstate.driver_lock_path(run)
    rec = json.loads(p.read_text())
    rec["pid"] = 1                                       # someone else, alive
    p.write_text(json.dumps(rec))
    assert runstate.read_driver_lock(run)["live"] is True
    assert _decision(_hook(cmd, run)) == "deny"


@pytest.mark.skipif(not HOOK.is_file(), reason="guard_driver_lock.py not installed")
def test_the_hook_allows_what_the_engine_would_reap(tmp_path):
    """Two statements of one rule drift. This is the case that catches it:
    a lock the engine calls stale must not be a lock the hook calls held."""
    run = _run(tmp_path)
    p = runstate.driver_lock_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 2 ** 22, "host": runstate._hostname(),
                             "at": "2026-09-14T10:00:00Z",
                             "heartbeat": "2026-09-14T10:00:00Z"}))
    assert runstate.read_driver_lock(run)["live"] is False
    cmd = f"python3 -m engine.pipeline run --run {run.run_id} --root {run.root}"
    assert _decision(_hook(cmd, run)) != "deny"
