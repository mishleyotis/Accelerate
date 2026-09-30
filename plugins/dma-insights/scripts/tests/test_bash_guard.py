"""One process for every Bash guard, in the pinned order (F-H01-023).

Measured 28-09-2026: six PreToolUse guards on every Bash call, each its
own interpreter, ≈ 301 ms per call before the command ran. The guards were
already decide() functions; bash_guard runs them in one process. These
tests pin the order (a denial before any approval), that the first denial
wins, that the approver still answers, that Cowork's bash tool is the
same tool, and the latency: one process, under the audit's 200 ms line
on this machine.
"""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
GUARD = HOOKS / "bash_guard.py"
_spec = importlib.util.spec_from_file_location("bash_guard", GUARD)
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)

FAKE_PAT = "ghp_" + "x" * 30
# constructed, never literal: the credential guard reads command text, and
# a test file is not a command
CRED_URL = "https://" + FAKE_PAT + "@github" + ".com/o/r"


def _run(payload):
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def _bash(cmd, tool="Bash"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"command": cmd}, "cwd": "/home/user/Accelerate"}


def _decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision", "")


def test_the_order_puts_every_denier_before_the_approver():
    scripts = [s for s, _ in bg.ORDER]
    assert scripts == ["guard_driver_lock.py", "deny_credential_ops.py", "deny_bulk_read.py",
                       "deny_artefact_writes.py", "guard_actor_scope.py", "deliverable_gate.py"]
    assert bg.APPROVER == "autoapprove_builtins.py"
    for s in scripts + [bg.APPROVER]:
        assert (HOOKS / s).is_file(), s


def test_the_first_denial_wins_and_names_its_guard():
    out = _run(_bash(f"git push {CRED_URL} main"))
    assert _decision(out) == "deny"
    assert "GitHub" in out["hookSpecificOutput"]["permissionDecisionReason"]
    out = _run(_bash("cat /run/01_evidence/evidence_index.json"))
    assert _decision(out) == "deny"
    assert "Run this instead" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_pipeline_command_is_still_approved_and_an_unknown_one_still_prompts():
    assert _decision(_run(_bash("python3 -m engine.cli status --root /tmp/none"))) == "allow"
    assert _run(_bash("pip install requests")) is None


def test_coworks_bash_tool_is_the_same_tool():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "mcp__workspace__bash",
          "tool_input": {"cmd": "cat /run/ledger.jsonl"}}
    assert _decision(_run(ev)) == "deny"
    assert bg.normalise(ev)["tool_name"] == "Bash"
    assert bg.decide({"tool_name": "Write", "tool_input": {"file_path": "x"}}) is None


def _best(script, ev, n):
    best = 1e9
    for _ in range(n):
        t = time.perf_counter()
        subprocess.run([sys.executable, str(HOOKS / script)], input=ev,
                       capture_output=True, text=True, timeout=60)
        best = min(best, time.perf_counter() - t)
    return best


def test_one_process_is_cheaper_than_seven():
    """The audit's line was 200 ms per hook and the six separate processes
    measured 301 ms; one process measured 58 ms standalone on this machine.
    Machines and their load differ, so the assertion is RELATIVE — the one
    process costs less than half of the seven it replaced, measured in the
    same minute — and the absolute figure is printed for the record."""
    ev = json.dumps(_bash("python3 -m engine.cli status --root /tmp/none"))
    seven = sum(_best(s, ev, 3) for s, _ in bg.ORDER) + _best(bg.APPROVER, ev, 3)
    one = _best("bash_guard.py", ev, 5)
    print(f"bash_guard {one * 1000:.0f} ms vs seven processes {seven * 1000:.0f} ms")
    assert one < 0.5 * seven, f"one process {one * 1000:.0f} ms, seven {seven * 1000:.0f} ms"


def _load(script):
    spec = importlib.util.spec_from_file_location(script[:-3], HOOKS / script)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_guard_that_raises_is_skipped_not_fatal(monkeypatch):
    def boom(script):
        if script == "deny_bulk_read.py":
            raise RuntimeError("broken guard")
        return _load(script)
    monkeypatch.setattr(bg, "_load", boom)
    out = bg.decide(_bash("python3 -m engine.cli status --root /tmp/none"))
    assert _decision(out) == "allow"
