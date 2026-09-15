"""The scope guard denies at the call, and stays silent about everything else.

It duplicates a refusal the ledger already makes, and the duplication is the
point: a refusal that arrives after the command ran has already cost the
turn, and a lane that has spent its turns is re-dispatched — the shape that
turned a $20 budget into $96.65.

What these pin is mostly the SILENCE. A PreToolUse guard on Bash sees every
command a session runs, so the ways it must not fire matter more than the
one way it must.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = (Path(__file__).resolve().parents[1] / "hooks" / "guard_actor_scope.py")
PLUGIN = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("guard_actor_scope", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def run_hook(payload, env=None):
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
                            **(env or {})})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


EVIDENCE = ("python3 -m engine.cli evidence --run R --root /r "
            "--subcap {cell} --source S --tier T1 --excerpt E --actor {actor}")


# ── it denies ──────────────────────────────────────────────────────────

def test_a_lane_writing_another_category_is_denied():
    out = run_hook(bash(EVIDENCE.format(cell="P3C2.4.1",
                                        actor="research-p1c1-producer")))
    d = out["hookSpecificOutput"]
    assert d["permissionDecision"] == "deny"
    assert "only P1C1 cells" in d["permissionDecisionReason"]
    assert "engine/scope.py" in d["permissionDecisionReason"]


def test_the_actor_can_come_from_the_environment():
    """A headless lane cannot be identified from inside a hook; the
    dispatcher puts the name in the child's environment."""
    cmd = ("python3 -m engine.cli search --run R --root /r "
           "--subcap P3C2.4.1 --facet works --query q --tool exa")
    assert run_hook(bash(cmd)) is None
    out = run_hook(bash(cmd), env={"DMA_ACTOR": "research-p1c1-producer"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_lane_may_not_challenge_even_its_own_cell():
    cmd = ("python3 -m engine.cli challenge --run R --root /r "
           "--subcap P1C1.1.1 --verdict PASS --actor research-p1c1-producer "
           "--rationale x")
    assert "may not challenge" in \
        run_hook(bash(cmd))["hookSpecificOutput"]["permissionDecisionReason"]


def test_an_equals_form_flag_is_read_the_same_way():
    out = run_hook(bash("python3 -m engine.cli evidence --subcap=P3C2.4.1 "
                        "--actor=research-p1c1-producer --source S"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── it stays silent ────────────────────────────────────────────────────

def test_a_lane_writing_its_own_category_passes():
    assert run_hook(bash(EVIDENCE.format(cell="P1C1.1.1",
                                         actor="research-p1c1-producer"))) is None


def test_the_servicing_tier_registers_anywhere():
    """The correlation point: the conductor draining a relay batch logs
    against any cell in the run. Denying that would remove the mechanism by
    which one lane's find reaches another lane's cell."""
    for actor in ("research-conductor", "enrichment-web-specialist"):
        assert run_hook(bash(EVIDENCE.format(cell="P3C2.4.1", actor=actor))) is None


def test_an_unnamed_actor_is_not_governed():
    assert run_hook(bash(EVIDENCE.format(cell="P3C2.4.1", actor="a-person"))) is None
    assert run_hook(bash(EVIDENCE.format(cell="P3C2.4.1", actor=""))) is None


@pytest.mark.parametrize("command", [
    "ls -la", "git status", "pytest tests/",
    "python3 -m engine.cli gate --run R --category P3C2",
    "python3 -m engine.pipeline run --run R",
    "python3 -m engine.cost report --run R",
    "echo 'python3 -m engine.cli evidence --subcap P3C2.4.1'",
])
def test_it_says_nothing_about_commands_that_are_not_scoped_writes(command):
    assert run_hook(bash(command)) is None


def test_a_non_bash_tool_is_ignored():
    assert run_hook({"tool_name": "Read", "tool_input": {"file_path": "/x"}}) is None


# ── it fails open ──────────────────────────────────────────────────────

def test_malformed_stdin_is_allowed_not_bricked():
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0 and not r.stdout.strip()


def test_an_unclosed_quote_is_not_our_business():
    assert guard.decide("python3 -m engine.cli evidence --subcap 'P3C2.4.1") == ""


def test_it_is_silent_when_the_engine_cannot_be_imported(monkeypatch):
    """The ledger still refuses; a hook that cannot read the rule must not
    invent one."""
    monkeypatch.setattr(guard, "_engine_scope",
                        lambda: (_ for _ in ()).throw(ImportError("no engine")))
    assert guard.decide(EVIDENCE.format(cell="P3C2.4.1",
                                        actor="research-p1c1-producer")) == ""


# ── it is wired ────────────────────────────────────────────────────────

def test_the_hook_is_registered_before_anything_can_approve():
    """`autoapprove_builtins` says allow on Bash; a denial decided after it
    is a denial that arrives too late to matter."""
    d = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    pre = d["hooks"]["PreToolUse"]
    def idx(name):
        return next(i for i, e in enumerate(pre)
                    for h in e["hooks"] if name in h.get("command", ""))
    assert idx("guard_actor_scope.py") < idx("autoapprove_builtins.py")
    entry = pre[idx("guard_actor_scope.py")]
    assert entry["matcher"] == "Bash"
    assert "if [ -f" in entry["hooks"][0]["command"], (
        "every hook command carries its own existence check, so a partial "
        "install degrades to a message rather than a broken session")
