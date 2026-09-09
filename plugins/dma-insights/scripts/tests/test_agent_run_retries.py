"""A lane that timed out or came back empty is re-dispatched; a lane that
failed on its own terms is not — and every lane says what it cost in wall
clock and attempts.

Owner issue 9 (2026-09-03): the assessment took over six hours and nothing
recorded where they went; a starved or timed-out lane was re-run by hand
once somebody noticed. `--retries` makes the retry mechanical and BOUNDED
to the two codes that mean "did not run" (124 timeout, 125 empty verdict);
the batch summary carries per-lane started/ended/elapsed/attempts; and
`--record-run` lands the stage's wall clock in the run's cost ledger.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "dma-insights" / "scripts" / "agent_run.py"
if not SCRIPT.exists():
    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent_run.py"


def _module():
    spec = importlib.util.spec_from_file_location("agent_run", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fn(codes):
    """A fake dispatch that returns the given codes in order."""
    calls = []

    def fake(name, prompt, timeout, repo_root, allowed):
        calls.append(prompt)
        code = codes[min(len(calls) - 1, len(codes) - 1)]
        return {"agent": name, "code": code, "stdout": "x" * 300, "stderr": "",
                "note": "DISPATCH TIMEOUT" if code == 124 else ""}
    fake.calls = calls
    return fake


def test_a_timeout_is_retried_and_the_retry_says_so():
    m = _module()
    fn = _fn([124, 0])
    res = m.dispatch_with_retries(fn, "research-p1c1-producer", "go", 10, Path("."), "",
                                  retries=2, sleep=lambda s: None)
    assert res["code"] == 0 and res["attempts"] == 2
    assert res["attempt_codes"] == [124, 0]
    assert "ATTEMPT 2 OF 3" in fn.calls[1] and "timed out" in fn.calls[1]
    assert fn.calls[0] == "go"                      # the first attempt is untouched
    assert res["started_at"] and res["ended_at"] and res["elapsed_s"] >= 0


def test_an_empty_verdict_is_retried_too():
    m = _module()
    fn = _fn([125, 125, 0])
    res = m.dispatch_with_retries(fn, "x", "go", 10, Path("."), "", retries=2,
                                  sleep=lambda s: None)
    assert res["code"] == 0 and res["attempts"] == 3
    assert "produced nothing" in fn.calls[2]


def test_a_real_failure_is_never_retried():
    m = _module()
    for code in (1, 2, 127):
        fn = _fn([code, 0])
        res = m.dispatch_with_retries(fn, "x", "go", 10, Path("."), "", retries=3,
                                      sleep=lambda s: None)
        assert res["code"] == code and res["attempts"] == 1, code


def test_retries_are_bounded_and_the_last_failure_is_loud():
    m = _module()
    fn = _fn([124])
    slept = []
    res = m.dispatch_with_retries(fn, "x", "go", 10, Path("."), "", retries=2,
                                  backoff_s=1.5, sleep=slept.append)
    assert res["code"] == 124 and res["attempts"] == 3
    assert slept == [1.5, 3.0]                       # backoff x attempt, two waits
    assert "3 attempts" in res["note"] and "not a fourth try" in res["note"]


def test_zero_retries_is_one_attempt():
    m = _module()
    fn = _fn([124])
    res = m.dispatch_with_retries(fn, "x", "go", 10, Path("."), "", retries=0,
                                  sleep=lambda s: None)
    assert res["attempts"] == 1 and res["code"] == 124


class _Result:
    def __init__(self, code=0, out="x" * 300, err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_the_batch_summary_carries_every_lanes_timing(monkeypatch, tmp_path, capsys):
    m = _module()
    seen = {"n": 0}

    def fake(cmd, **_):
        seen["n"] += 1
        # the first lane's first attempt is empty; everything else is fine
        return _Result(out="") if seen["n"] == 1 else _Result()
    monkeypatch.setattr(m.subprocess, "run", fake)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    rows = [{"agent": "research-p1c1-producer", "prompt": "go"},
            {"agent": "research-p1c2-producer", "prompt": "go"}]
    timing = tmp_path / "timing.json"
    rc = m.run_batch(rows, 1, 10, tmp_path, "", None, None, retries=1,
                     timing_out=timing)
    assert rc == 0
    summ = json.loads(timing.read_text())
    assert summ["dispatched"] == 2 and summ["ok"] == 2
    assert {d["agent"] for d in summ["lanes_detail"]} == {r["agent"] for r in rows}
    assert sum(d["attempts"] for d in summ["lanes_detail"]) == 3
    for d in summ["lanes_detail"]:
        assert d["started_at"] and d["ended_at"] and d["elapsed_s"] is not None
    assert summ["started_at"] and summ["elapsed_s"] >= 0
    assert "retries_allowed" in summ and summ["retries_allowed"] == 1


def test_record_run_shells_the_cost_ledger(monkeypatch, tmp_path):
    m = _module()
    monkeypatch.setattr(m.subprocess, "run", lambda cmd, **_: _Result())
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    calls = []

    def fake_record(record, summary, repo_root):
        calls.append((record, summary["elapsed_s"], summary["lanes"]))
        return {"recorded": True, "detail": "ok"}
    monkeypatch.setattr(m, "_record_cost", fake_record)
    rows = [{"agent": "research-p1c1-producer", "prompt": "go"}]
    rc = m.run_batch(rows, 1, 10, tmp_path, "", None, None,
                     record={"run": "R-1", "root": str(tmp_path), "stage": "RESEARCH"})
    assert rc == 0
    assert calls and calls[0][0]["stage"] == "RESEARCH" and calls[0][2] == 1


def test_the_record_command_is_the_engines_own(monkeypatch, tmp_path):
    """`_record_cost` runs `engine.cost record` with the batch's timings —
    the same command a person would type, so the ledger has one writer."""
    m = _module()
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"], seen["cwd"] = cmd, kw.get("cwd")
        return _Result(out='{"ok": true}')
    monkeypatch.setattr(m.subprocess, "run", fake)
    summary = {"elapsed_s": 42.0, "started_at": "2026-09-04T00:00:00Z",
               "ended_at": "2026-09-04T00:00:42Z", "lanes": 4, "ok": 4,
               "dispatched": 4, "turns": 120, "usd": 1.5,
               "lanes_detail": [{"attempts": 1}] * 3 + [{"attempts": 2}]}
    out = m._record_cost({"run": "R-1", "root": "/r", "stage": "SCORING"}, summary,
                         Path("/repo"))
    assert out["recorded"]
    cmd = seen["cmd"]
    assert cmd[1:4] == ["-m", "engine.cost", "record"]
    assert "--stage" in cmd and cmd[cmd.index("--stage") + 1] == "SCORING"
    assert cmd[cmd.index("--attempts") + 1] == "5"
    assert cmd[cmd.index("--elapsed-s") + 1] == "42.0"
    assert str(seen["cwd"]).endswith("skills/dma-research")


def test_the_flags_are_spelled_in_help():
    m = _module()
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            m.main(["--help"])
        except SystemExit:
            pass
    text = buf.getvalue()
    for flag in ("--retries", "--retry-backoff-s", "--timing-out", "--record-run",
                 "--record-root", "--record-stage"):
        assert flag in text, flag
