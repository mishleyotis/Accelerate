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


def test_a_denial_is_decided_before_anything_can_approve():
    """`autoapprove_builtins` answers allow on Bash. Any guard that denies
    a Bash command must be registered ahead of it, or its answer arrives
    after the decision is made."""
    pre = HOOKS["PreToolUse"]
    order = [(_script_of(h["command"]), i)
             for i, e in enumerate(pre) for h in e["hooks"]]
    pos = dict(order)
    approve = pos["autoapprove_builtins.py"]
    for denier in ("deny_credential_ops.py", "deny_bulk_read.py",
                   "deny_artefact_writes.py", "guard_actor_scope.py"):
        assert pos[denier] < approve, denier


def test_the_scope_guard_is_bound_to_bash():
    entries = [e for e in HOOKS["PreToolUse"]
               if any(_script_of(h["command"]) == "guard_actor_scope.py"
                      for h in e["hooks"])]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"


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
    on_disk = {p.name for p in (PLUGIN / "scripts" / "hooks").glob("*.py")
               if not p.name.startswith("_")}
    assert on_disk - declared == set(), f"unbound: {sorted(on_disk - declared)}"
