"""The hooks are only enforcing if they are BOUND, and bound correctly.

Every failure this file pins has happened: AUD-0004 (SubagentStart existed in
the harness and hooks.json declared three event types, so 35 routed producers
started with no brief), AUD-0054 (three of the five SessionStart sources
printed nothing), and the shape errors that make a wrapper fail CLOSED — a
missing script that emits nothing, a `printf` whose double quotes let the
shell expand a backtick in the message.

So: every script named in hooks.json exists; every event and matcher the
seam depends on is bound; every wrapper keeps the existence-check shape and
prints valid JSON when the script is absent; and `agent_run.py` still passes
DMA_ACTOR into the child and still sets DMA_STAGE_GUARD=off.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
HOOK_DIR = PLUGIN / "scripts" / "hooks"


def _doc() -> dict:
    return json.loads(HOOKS_JSON.read_text())["hooks"]


def _commands():
    """(event, matcher, script, command, timeout) for every bound hook."""
    for event, entries in _doc().items():
        for entry in entries:
            for h in entry.get("hooks", []):
                m = re.search(r"scripts/hooks/([A-Za-z0-9_]+\.py)", h["command"])
                yield (event, entry.get("matcher"), m.group(1) if m else None,
                       h["command"], h.get("timeout"))


# ── every script named is a script that exists ───────────────────────────

def test_every_script_named_in_hooks_json_exists():
    missing = sorted({s for _, _, s, _, _ in _commands()
                      if s and not (HOOK_DIR / s).is_file()})
    assert not missing, f"hooks.json names scripts that are not there: {missing}"


def test_every_hook_names_a_script():
    nameless = [(e, c[:60]) for e, _, s, c, _ in _commands() if not s]
    assert not nameless, nameless


# ── the seams this stream was asked to bind ──────────────────────────────

BINDINGS = [
    # (event, script, a regex the matcher must satisfy)
    ("PreToolUse", "deny_whole_page_fetch.py", r"WebFetch"),
    ("PreToolUse", "deny_whole_page_fetch.py", r"web_fetch_exa"),
    ("PreToolUse", "guard_dispatch.py", r"Agent"),
    ("PreToolUse", "guard_driver_lock.py", r"Bash"),
    ("PreToolUse", "deny_artefact_writes.py", r"Bash"),
    ("PostToolUse", "harvest_on_return.py", r"Agent"),
    ("PostToolUse", "stage_advance.py", r"Bash"),
    ("Stop", "stage_advance.py", None),
    ("SubagentStart", "session_brief.py", None),
    ("SubagentStop", "record_handback.py", r"research-"),
    ("SessionStart", "session_brief.py", None),
    ("PostCompact", "session_brief.py", None),
]


@pytest.mark.parametrize("event,script,matcher_re", BINDINGS)
def test_the_seam_is_bound(event, script, matcher_re):
    found = [(m or "") for e, m, s, _, _ in _commands()
             if e == event and s == script]
    assert found, f"{script} is not bound on {event}"
    if matcher_re:
        assert any(re.search(matcher_re, m) for m in found), \
            f"{script} on {event} has matchers {found}, none matching {matcher_re}"


def test_the_events_that_were_not_bound_before_are_bound_now():
    """SubagentStop and PostCompact were the two missing bindings."""
    events = set(_doc())
    assert {"SubagentStop", "PostCompact"} <= events, sorted(events)


def test_subagent_stop_matches_the_research_lanes_and_the_plugin_prefix():
    """A lane arrives as `research-p1c1-producer` OR
    `dma-insights:research-p1c1-producer`, depending on how it was
    dispatched — the matcher has to admit both."""
    matchers = [m for e, m, s, _, _ in _commands()
                if e == "SubagentStop" and s == "record_handback.py"]
    assert matchers
    for pat in matchers:
        rx = re.compile(pat)
        assert rx.search("research-p1c1-producer"), pat
        assert rx.search("dma-insights:research-p3c4-producer"), pat
        assert not rx.search("scoring-p1-producer"), pat


# ── the wrapper shape ────────────────────────────────────────────────────

def test_every_wrapper_checks_the_script_exists_and_fails_open():
    for event, _, script, cmd, _ in _commands():
        assert 'if [ -f "$H" ]' in cmd, (event, script)
        assert "exec python3" in cmd, (event, script)
        assert "exit 0" in cmd, (event, script)
        assert "${CLAUDE_PLUGIN_ROOT}" in cmd, (event, script)


def test_a_missing_script_still_prints_valid_json_and_exits_zero():
    """The branch that runs on a partial install. It has to be JSON: a
    wrapper that printed a bare sentence would be read as a malformed hook
    result, and the systemMessage naming the repair would never be seen."""
    for event, _, script, cmd, _ in _commands():
        r = subprocess.run(
            ["bash", "-c", cmd.replace("${CLAUDE_PLUGIN_ROOT}", "/nonexistent")],
            capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, (event, script, r.stderr[:200])
        doc = json.loads(r.stdout)
        assert doc.get("systemMessage"), (event, script)
        assert script in doc["systemMessage"], (event, script)


def test_no_wrapper_lets_the_shell_expand_its_own_message():
    """The message is data. Double-quoting it would let a backtick or a $
    inside the prose run as a command on the exact install that is already
    broken."""
    for event, _, script, cmd, _ in _commands():
        payload = cmd.split("printf ", 1)[1]
        assert payload.startswith("'%s' '"), (event, script, payload[:40])


def test_every_hook_has_a_timeout():
    for event, _, script, _, timeout in _commands():
        assert isinstance(timeout, int) and timeout > 0, (event, script)


# ── the child environment the hooks read ─────────────────────────────────

def test_agent_run_passes_dma_actor_and_keeps_the_stage_guard_off():
    """A headless lane carries no `agent_type`, so DMA_ACTOR is the only
    thing that tells a hook who is calling; and the Stop guard must reach
    the conductor only, or sixteen lanes each hold themselves open."""
    src = (PLUGIN / "scripts" / "agent_run.py").read_text()
    assert '"DMA_STAGE_GUARD": "off"' in src
    assert '"DMA_ACTOR": name' in src


def test_the_actor_table_is_imported_never_restated():
    """One table, several enforcers. A hook with its own copy of the rule is
    the drift this repository keeps removing."""
    for script in ("guard_actor_scope.py", "deny_whole_page_fetch.py"):
        src = (HOOK_DIR / script).read_text()
        assert "from engine import scope" in src, script


# ── the family rule: fail OPEN, every one of them ────────────────────────

MALFORMED = ('not json at all', '', '[1, 2, 3]', '"a bare string"', 'null',
             '{"tool_input": [1]}',
             '{"tool_name": "Bash", "tool_input": {"command": 123}}',
             '{"tool_name": "Agent", "tool_input": null, "tool_response": [1]}')


@pytest.mark.parametrize("script", sorted(
    p.name for p in HOOK_DIR.glob("*.py") if not p.name.startswith("_")))
def test_every_hook_exits_zero_on_input_it_did_not_parse(script):
    """A hook that raises on an unexpected stdin shape exits NON-ZERO with a
    traceback, which is a hook failing CLOSED on its own bug — the one
    failure a guard may never have. Measured 2026-09-14: six of them did
    (a JSON list, a bare string or null raised AttributeError)."""
    for payload in MALFORMED:
        p = subprocess.run(["python3", str(HOOK_DIR / script)], input=payload,
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (script, payload, p.stderr[-400:])


@pytest.mark.parametrize("script", sorted(
    p.name for p in HOOK_DIR.glob("*.py") if not p.name.startswith("_")))
def test_no_hook_denies_on_input_it_did_not_parse(script):
    """Silence, not a refusal. Deny only on a violation positively
    identified — a guard that denies when it cannot read its own event stops
    the work it was meant to protect."""
    for payload in MALFORMED:
        p = subprocess.run(["python3", str(HOOK_DIR / script)], input=payload,
                           capture_output=True, text=True, timeout=120)
        if not p.stdout.strip():
            continue
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            continue               # SessionStart prints prose, by contract
        assert (doc.get("hookSpecificOutput") or {}).get("permissionDecision") \
            != "deny", (script, payload)
        assert doc.get("decision") != "block", (script, payload)
