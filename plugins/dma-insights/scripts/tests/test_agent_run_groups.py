"""Lanes are process groups, deadlines are clocks, stop means stop.

Measured 2026-09-07 (owner): four paused drivers were killed; their lanes'
`claude` children and grandchildren kept running — fifty processes, load at
115 and climbing — until every subprocess was force-cleared by hand. These
tests run REAL children (a Python stand-in for the claude CLI that prints,
spawns a grandchild, or hangs) so the group kill, the clock deadline, the
signal reaper and `reap` are proved on processes, not on fakes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "dma-insights" / "scripts" / "agent_run.py"
if not SCRIPT.exists():                     # running from the repo root
    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent_run.py"


def _module():
    spec = importlib.util.spec_from_file_location("agent_run_groups", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def _fake_claude(tmp_path: Path, body: str) -> Path:
    """A stand-in for the claude CLI: ignores its arguments, runs `body`."""
    script = tmp_path / "fake_claude.py"
    script.write_text(textwrap.dedent(body))
    sh = tmp_path / "claude"
    sh.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    sh.chmod(0o755)
    return sh


GRANDCHILD_THEN_HANG = """
    import json, os, subprocess, sys, time
    gc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": f"grandchild {gc.pid}"}]}}), flush=True)
    time.sleep(300)
"""

SILENT_HANG = """
    import time
    time.sleep(300)
"""

CLEAN_EXIT = """
    import json
    print(json.dumps({"type": "result", "result": "verdict: " + "x" * 400}), flush=True)
"""


# ── the group dies with the lane ────────────────────────────────────────

def test_a_timed_out_lane_takes_its_grandchildren_with_it(tmp_path, monkeypatch):
    m = _module()
    monkeypatch.setattr(m, "CLAUDE_BIN", str(_fake_claude(tmp_path, GRANDCHILD_THEN_HANG)))
    logs = tmp_path / "logs"
    t0 = time.monotonic()
    res = m.dispatch_streaming("research-p1c1-producer", "go", 2, tmp_path, "", logs)
    assert res["code"] == 124 and "process group" in res["note"]
    assert time.monotonic() - t0 < 15
    st = json.loads((logs / "research-p1c1-producer.status.json").read_text())
    assert st["state"] == "timeout" and st["pid"] == st["pgid"]
    assert st["driver_pid"] == os.getpid()
    gc_pid = int(res["stdout"].split("grandchild ")[1].split()[0])
    assert _wait_dead(gc_pid), "the grandchild outlived the lane"
    assert _wait_dead(st["pid"])
    assert m._LIVE == {}, "the lane was untracked when it ended"


def test_a_silent_lane_still_meets_its_deadline(tmp_path, monkeypatch):
    """`for line in proc.stdout` only woke when a line arrived, so a child
    that printed nothing never timed out. The deadline is a clock now."""
    m = _module()
    monkeypatch.setattr(m, "CLAUDE_BIN", str(_fake_claude(tmp_path, SILENT_HANG)))
    t0 = time.monotonic()
    res = m.dispatch_streaming("research-p1c2-producer", "go", 1, tmp_path, "", tmp_path / "logs")
    assert res["code"] == 124
    assert time.monotonic() - t0 < 10, "the silent child was killed at the deadline, not never"


def test_a_clean_lane_reports_as_before(tmp_path, monkeypatch):
    m = _module()
    monkeypatch.setattr(m, "CLAUDE_BIN", str(_fake_claude(tmp_path, CLEAN_EXIT)))
    logs = tmp_path / "logs"
    res = m.dispatch_streaming("research-p1c3-producer", "go", 30, tmp_path, "", logs,
                               label="research-p1c3-producer@x")
    assert res["code"] == 0 and res["stdout"].startswith("verdict:")
    assert res["label"] == "research-p1c3-producer@x"
    assert (logs / "research-p1c3-producer@x.jsonl").is_file(), "the label names the transcript"
    st = json.loads((logs / "research-p1c3-producer@x.status.json").read_text())
    assert st["state"] == "ok" and st["agent"] == "research-p1c3-producer"


def test_the_lane_is_a_session_leader(tmp_path, monkeypatch):
    m = _module()
    seen = {}
    real = subprocess.Popen

    class Spy(real):
        def __init__(self, *a, **kw):
            seen.update(kw)
            super().__init__(*a, **kw)
    monkeypatch.setattr(m.subprocess, "Popen", Spy)
    monkeypatch.setattr(m, "CLAUDE_BIN", str(_fake_claude(tmp_path, CLEAN_EXIT)))
    m.dispatch_streaming("research-p1c4-producer", "go", 30, tmp_path, "", tmp_path / "logs")
    assert seen.get("start_new_session") is True


def test_the_default_dispatch_is_a_session_leader_too(monkeypatch):
    m = _module()
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)

        class R:
            returncode, stdout, stderr = 0, "verdict: " + "x" * 400, ""
        return R()
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    m.dispatch("finding-challenger", "go", 10, Path("."), "")
    assert seen.get("start_new_session") is True


# ── a signal to the batch stops every lane ──────────────────────────────

def test_sigterm_to_the_batch_kills_every_live_lane_group(tmp_path):
    """Run agent_run.py --batch as a real process with two hanging lanes,
    SIGTERM it, and prove the lanes (and their grandchildren) are gone."""
    fake = _fake_claude(tmp_path, GRANDCHILD_THEN_HANG)
    logs = tmp_path / "logs"
    batch = tmp_path / "batch.json"
    (tmp_path / "p.md").write_text("go")
    batch.write_text(json.dumps([
        {"agent": "research-p1c1-producer", "prompt_file": str(tmp_path / "p.md")},
        {"agent": "research-p1c2-producer", "prompt_file": str(tmp_path / "p.md")}]))
    env = {**os.environ, "DMA_CLAUDE_BIN": str(fake)}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--batch", str(batch), "--lanes", "2",
                             "--timeout", "120", "--stream", "--log-dir", str(logs),
                             "--no-lane-cap"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # wait until both lanes have written a pid
    end = time.monotonic() + 20
    pids = {}
    while time.monotonic() < end and len(pids) < 2:
        for f in logs.glob("*.status.json") if logs.is_dir() else []:
            try:
                st = json.loads(f.read_text())
            except ValueError:
                continue
            if st.get("pid"):
                pids[f.name] = st["pid"]
        time.sleep(0.1)
    assert len(pids) == 2, "both lanes started"
    # each lane's grandchild pid is in its transcript
    grand = []
    end = time.monotonic() + 10
    while time.monotonic() < end and len(grand) < 2:
        grand = []
        for f in logs.glob("*.jsonl"):
            txt = f.read_text()
            if "grandchild " in txt:
                grand.append(int(txt.split("grandchild ")[1].split('"')[0]))
        time.sleep(0.1)
    assert len(grand) == 2
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 128 + signal.SIGTERM, (proc.returncode, err[-400:])
    assert "stopped 2 lane group(s)" in err
    for pid in list(pids.values()) + grand:
        assert _wait_dead(pid), f"{pid} survived the driver"


# ── reap: the groups a dead driver left behind ──────────────────────────

def test_reap_kills_groups_whose_driver_is_gone_and_skips_live_drivers(tmp_path):
    m = _module()
    logs = tmp_path / "logs"
    logs.mkdir()
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                              start_new_session=True)
    owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                             start_new_session=True)
    try:
        # a driver pid that certainly does not exist
        dead_driver = 2 ** 22 - 7
        while _alive(dead_driver):
            dead_driver -= 1
        (logs / "a.status.json").write_text(json.dumps(
            {"agent": "research-p1c1-producer", "state": "running", "pid": orphan.pid,
             "pgid": orphan.pid, "driver_pid": dead_driver}))
        (logs / "b.status.json").write_text(json.dumps(
            {"agent": "research-p1c2-producer", "state": "running", "pid": owned.pid,
             "pgid": owned.pid, "driver_pid": os.getpid()}))
        (logs / "c.status.json").write_text(json.dumps(
            {"agent": "research-p1c3-producer", "state": "ok", "pid": 1, "pgid": 1}))
        dry = m.reap(logs, dry_run=True)
        assert [r["result"] for r in dry] == ["would kill", "skipped: its driver is alive (use --force)"]
        assert _alive(orphan.pid) and _alive(owned.pid)
        rows = m.reap(logs)
        by = {r["agent"]: r["result"] for r in rows}
        assert by["research-p1c1-producer"] in ("terminated", "killed")
        assert by["research-p1c2-producer"].startswith("skipped")
        # THIS process is the orphan's parent, so the SIGTERM'd child is a
        # zombie until waited (in the field the dead driver's children are
        # reparented to init, which reaps them); wait() is the honest check.
        orphan.wait(timeout=5)
        assert orphan.returncode is not None and _alive(owned.pid)
        st = json.loads((logs / "a.status.json").read_text())
        assert st["state"] == "reaped" and st.get("reaped_at")
        # --force takes the live driver's group too
        forced = m.reap(logs, force=True)
        assert {r["agent"]: r["result"] for r in forced}["research-p1c2-producer"] in ("terminated", "killed")
        owned.wait(timeout=5)
        assert owned.returncode is not None
        # a stale file for a group that already exited is relabelled, not reported running
        again = m.reap(logs)
        assert all(r["result"] == "gone" for r in again) or again == []
    finally:
        for p in (orphan, owned):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()


def test_reap_is_a_command(tmp_path):
    m = _module()
    (tmp_path / "logs").mkdir()
    rc = m.main(["reap", "--log-dir", str(tmp_path / "logs")])
    assert rc == 0


# ── host capacity ────────────────────────────────────────────────────────

def test_the_lane_cap_is_a_measurement_with_its_inputs():
    m = _module()
    cap = m.host_capacity(16, mem_mb=4 * 1024, cpus=8, per_lane_mb=600)
    assert cap["lanes"] == (4 * 1024 - m.LANE_MEM_HEADROOM_MB) // 600 == 5
    assert cap["capped"] and cap["binding"] == "memory"
    cap = m.host_capacity(16, mem_mb=64 * 1024, cpus=2, per_lane_mb=600)
    assert cap["lanes"] == 4 and cap["binding"] == "cpu"
    cap = m.host_capacity(16, mem_mb=64 * 1024, cpus=32, per_lane_mb=600)
    assert cap["lanes"] == 16 and not cap["capped"] and cap["binding"] == "requested"
    # never below one, even on a box the estimate says cannot hold one
    assert m.host_capacity(16, mem_mb=512, cpus=1, per_lane_mb=600)["lanes"] == 1
    # unreadable memory: the request stands, and the result says so
    cap = m.host_capacity(16, mem_mb=None, cpus=64, per_lane_mb=600)
    assert cap["lanes"] == 16 and cap["by_mem"] is None and cap["mem_available_mb"] is None


def test_the_per_lane_estimate_is_overridable_from_the_environment(monkeypatch):
    m = _module()
    monkeypatch.setenv("DMA_LANE_MEM_MB", "100")
    cap = m.host_capacity(16, mem_mb=2 * 1024, cpus=64)
    assert cap["per_lane_mb"] == 100 and cap["lanes"] == 10


def test_the_batch_applies_the_cap_and_reports_it(tmp_path, monkeypatch, capsys):
    m = _module()
    monkeypatch.setattr(m, "host_capacity",
                        lambda requested, **kw: {"requested": requested, "lanes": 2, "capped": True,
                                                "binding": "memory", "cpus": 4,
                                                "mem_available_mb": 2500, "per_lane_mb": 600,
                                                "by_cpu": 8, "by_mem": 2})
    seen = {"max_workers": None}
    real = m.concurrent.futures.ThreadPoolExecutor

    class Spy(real):
        def __init__(self, max_workers=None, **kw):
            seen["max_workers"] = max_workers
            super().__init__(max_workers=max_workers, **kw)
    monkeypatch.setattr(m.concurrent.futures, "ThreadPoolExecutor", Spy)

    def fake_run(cmd, **kw):
        class R:
            returncode, stdout, stderr = 0, "verdict: " + "x" * 400, ""
        return R()
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    batch = tmp_path / "batch.json"
    (tmp_path / "p.md").write_text("go")
    batch.write_text(json.dumps([{"agent": f"research-p1c{i}-producer",
                                  "prompt_file": str(tmp_path / "p.md")} for i in (1, 2, 3, 4)]))
    timing = tmp_path / "timing.json"
    rc = m.main(["--batch", str(batch), "--lanes", "4", "--timing-out", str(timing)])
    assert rc == 0 and seen["max_workers"] == 2
    err = capsys.readouterr().err
    assert "lane cap: 4 requested, running 2" in err
    summ = json.loads(timing.read_text())
    assert summ["lanes"] == 2 and summ["lane_cap"]["binding"] == "memory"
    # --no-lane-cap runs the requested count and says the cap was overridden
    rc = m.main(["--batch", str(batch), "--lanes", "4", "--timing-out", str(timing), "--no-lane-cap"])
    assert rc == 0 and seen["max_workers"] == 4
    assert json.loads(timing.read_text())["lane_cap"]["overridden"] is True


def test_capacity_is_a_command(capsys):
    m = _module()
    assert m.main(["capacity", "--lanes", "16"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["requested"] == 16 and 1 <= out["lanes"] <= 16 and "note" in out


def test_the_default_lane_count_is_still_the_cost_models(monkeypatch):
    """The cap is applied at dispatch; the constant the schedule divides by
    is untouched, and the pin between them stands."""
    m = _module()
    assert m.DEFAULT_LANES == 16
