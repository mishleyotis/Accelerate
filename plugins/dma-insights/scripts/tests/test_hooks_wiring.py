"""Every hook this plugin declares exists, is bound where it can fire, and
degrades rather than breaking a session.

A hook is the one kind of code in this repository that nothing calls: the
harness does, or nothing does. So the failure mode is silence — a script
renamed, an event unbound, a matcher that no longer matches — and silence
here reads exactly like a rule everyone is obeying.

`test_ensure_headless.py` pinned one hook's registration this way and the
pattern is worth generalising: these assert the manifest as a whole.
"""
import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
MANIFEST = PLUGIN / "hooks" / "hooks.json"
HOOKS = json.loads(MANIFEST.read_text())["hooks"]


def _commands():
    for event, entries in HOOKS.items():
        for entry in entries:
            for h in entry["hooks"]:
                yield event, entry.get("matcher"), h


def _script_of(command: str) -> str:
    m = re.search(r"scripts/hooks/(\w+\.py)", command)
    return m.group(1) if m else ""


def test_the_manifest_is_valid_json_and_binds_something():
    assert HOOKS and all(isinstance(v, list) and v for v in HOOKS.values())


@pytest.mark.parametrize("event,matcher,hook", list(_commands()),
                         ids=lambda x: str(x)[:40])
def test_every_declared_hook_script_exists(event, matcher, hook):
    script = _script_of(hook["command"])
    assert script, f"{event}: command names no script under scripts/hooks/"
    assert (PLUGIN / "scripts" / "hooks" / script).is_file(), script


@pytest.mark.parametrize("event,matcher,hook", list(_commands()),
                         ids=lambda x: str(x)[:40])
def test_every_hook_command_carries_its_own_existence_check(event, matcher, hook):
    """A stale or partial install must degrade to a systemMessage, not to a
    session that cannot run a Bash command."""
    cmd = hook["command"]
    assert "if [ -f" in cmd and "systemMessage" in cmd, cmd[:120]


@pytest.mark.parametrize("event,matcher,hook", list(_commands()),
                         ids=lambda x: str(x)[:40])
def test_every_hook_declares_a_timeout(event, matcher, hook):
    assert isinstance(hook.get("timeout"), int) and hook["timeout"] > 0


def test_the_events_this_plugin_depends_on_are_all_bound():
    """Each of these carries a rule nothing else carries."""
    for event in ("SessionStart", "SubagentStart", "PreToolUse",
                  "PostToolUse", "Stop"):
        assert event in HOOKS, event


def _bash_guard_order():
    src = (PLUGIN / "scripts" / "hooks" / "bash_guard.py").read_text()
    body = src[src.index("ORDER = ("):src.index("APPROVER =")]
    return re.findall(r'\("([\w.]+\.py)"', body)


def test_a_denial_is_decided_before_anything_can_approve():
    """Every Bash guard runs inside bash_guard.py (QA audit F-H01-023), in
    the order that file pins, and the approver is the last word in it. On
    the manifest, the one Bash guard is bound before any approver."""
    order = _bash_guard_order()
    for denier in ("guard_driver_lock.py", "deny_credential_ops.py", "deny_bulk_read.py",
                   "deny_artefact_writes.py", "guard_actor_scope.py", "deliverable_gate.py"):
        assert denier in order, denier
    src = (PLUGIN / "scripts" / "hooks" / "bash_guard.py").read_text()
    assert 'APPROVER = "autoapprove_builtins.py"' in src
    pre = HOOKS["PreToolUse"]
    pos = {}
    for i, e in enumerate(pre):
        for h in e["hooks"]:
            pos.setdefault(_script_of(h["command"]), i)
    assert pos["bash_guard.py"] < pos["autoapprove_builtins.py"]
    assert pos["bash_guard.py"] < pos["autoapprove_connector.py"]
    bash_entries = [e for e in pre if "Bash" in (e.get("matcher") or "")]
    assert len(bash_entries) == 1 and _script_of(bash_entries[0]["hooks"][0]["command"]) == "bash_guard.py", (
        "exactly one process guards Bash")


def test_stage_advance_runs_only_for_a_dispatch_or_an_engine_command():
    """PostToolUse on every Bash result cost 571 ms of interpreter start-up
    per `ls` (F-H01-023). The wrapper reads stdin first and execs the hook
    only when the command was a dispatch, an engine command or a ship."""
    entries = [h for e in HOOKS["PostToolUse"] if e.get("matcher") == "Bash"
               for h in e["hooks"] if _script_of(h["command"]) == "stage_advance.py"]
    assert len(entries) == 1
    cmd = entries[0]["command"]
    assert cmd.startswith('IN=$(cat); case "$IN" in') and "*engine.*" in cmd and "*agent_run.py*" in cmd
    import os
    import subprocess
    import time
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    t = time.perf_counter()
    r = subprocess.run(["bash", "-c", cmd], input=json.dumps(
        {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls -la"}}),
        capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert time.perf_counter() - t < 0.1, "a plain command never starts the interpreter"


def test_the_scope_guard_is_bound_to_bash():
    """Through bash_guard.py, whose one entry matches Bash (F-H01-023)."""
    assert "guard_actor_scope.py" in _bash_guard_order()
    entries = [e for e in HOOKS["PreToolUse"]
               if any(_script_of(h["command"]) == "bash_guard.py" for h in e["hooks"])]
    assert len(entries) == 1
    assert "Bash" in entries[0]["matcher"].split("|")


def test_the_dispatcher_tells_a_child_who_it_is_and_whose_guard_is_off():
    """The hooks above can only scope a lane's writes if something carries
    the lane's name into the process, and the Stop guard must stay the
    conductor's — a lane that is held open re-dispatches its siblings."""
    src = (PLUGIN / "scripts" / "agent_run.py").read_text()
    assert "DMA_ACTOR" in src and '"DMA_STAGE_GUARD": "off"' in src


def test_no_hook_script_under_hooks_is_orphaned():
    """A script nobody binds is a rule nobody enforces, wearing the
    appearance of one."""
    declared = {_script_of(h["command"]) for _, _, h in _commands()}
    # a guard bash_guard.py runs in-process is bound through it
    declared |= set(_bash_guard_order()) | {"autoapprove_builtins.py"}
    on_disk = {p.name for p in (PLUGIN / "scripts" / "hooks").glob("*.py")
               if not p.name.startswith("_")}
    assert on_disk - declared == set(), f"unbound: {sorted(on_disk - declared)}"
