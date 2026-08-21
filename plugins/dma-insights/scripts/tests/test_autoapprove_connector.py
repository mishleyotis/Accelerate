"""The hook that lets a scheduled session call its own connector.

A trigger-fired session bound the connector correctly and then stopped on
"Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress"
(measured 2026-08-21T02:34Z, and again at 02:43Z). The owner has confirmed
that prompt is never surfaced to them through any hook — so it is not a slow
approval, it is an approval that cannot happen. 178 clients sat INGESTED
behind it.

Two properties have to hold, and the second is the one that would hurt:

  1. the connector's tools are approved without a human, and
  2. NOTHING ELSE IS. A hook that auto-approved broadly would be a far worse
     defect than the one it fixes, and it would stay invisible until the day
     it mattered.

Most of this file is (2). The scope tests are not padding — `startswith` on a
full prefix is one edit away from a substring match or a regex, and either
would silently widen this hook to tools it must never speak for.

The two guarded tools are tested for the opposite property: their own
prechecks must still be able to REFUSE. An approval that also disabled the
M5-band and colour-hex checks would trade one silent failure for another.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
AUTO = HOOKS / "autoapprove_connector.py"
SUBMIT = HOOKS / "precheck_submit.py"
PROMOTE = HOOKS / "precheck_promote.py"
HOOKS_JSON = HOOKS.parent.parent / "hooks" / "hooks.json"
PREFIX = "mcp__plugin_dma-insights_connector__"


def run(script: Path, event: dict):
    r = subprocess.run([sys.executable, str(script)], input=json.dumps(event),
                       capture_output=True, text=True)
    return r


def decision(script: Path, event: dict):
    """The permissionDecision a hook emits, or None when it stays silent."""
    r = run(script, event)
    out = r.stdout.strip()
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


# ── 1 · the connector is approved ──


@pytest.mark.parametrize("tool", [
    "get_run_progress", "claim_run", "register_evidence", "get_evidence",
    "get_report_bundle", "get_page_contract", "open_payload",
    "append_payload_part", "get_validation_verdict", "record_finding",
    "get_platform_fit", "get_staged_payload", "withdraw_run",
])
def test_a_connector_tool_is_approved_without_a_human(tool):
    assert decision(AUTO, {"tool_name": PREFIX + tool}) == "allow"


# ── 2 · nothing else is, and this is the half that matters ──


@pytest.mark.parametrize("tool", [
    "Bash", "Write", "Edit", "Read", "WebFetch", "Task",
    "mcp__Gmail__send_message",
    "mcp__Google_Drive__update_file",
    "mcp__github__create_pull_request",
    "mcp__plugin_other-plugin_connector__do_thing",
])
def test_no_other_tool_is_ever_approved(tool):
    assert decision(AUTO, {"tool_name": tool}) is None, (
        f"{tool} drew a decision from a hook that must only speak for this "
        f"plugin's connector")


def test_a_lookalike_prefix_is_not_ours():
    """`startswith` on the full prefix, never a substring search. A tool whose
    name merely CONTAINS the prefix belongs to somebody else."""
    for tool in (f"evil_{PREFIX}get_run_progress",
                 f"x{PREFIX}claim_run",
                 f"mcp__notplugin_dma-insights_connector__claim_run"):
        assert decision(AUTO, {"tool_name": tool}) is None, tool


def test_the_bare_prefix_with_no_tool_is_not_approved():
    assert decision(AUTO, {"tool_name": PREFIX.rstrip("_")}) is None


@pytest.mark.parametrize("event", [
    {}, {"tool_name": None}, {"tool_name": 123}, {"tool_name": ["a"]},
    {"tool_input": {"command": "rm -rf /"}},
])
def test_a_malformed_event_draws_no_decision(event):
    assert decision(AUTO, event) is None


def test_unparseable_stdin_neither_crashes_nor_approves():
    r = subprocess.run([sys.executable, str(AUTO)], input="not json at all",
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


# ── 3 · the guarded tools keep their own guards ──


def test_the_hook_stands_aside_for_the_two_guarded_tools():
    """Exactly one hook decides each tool. Two hooks with opposite opinions on
    a promote is not something to find out about during a promote."""
    for tool in ("submit_page_payload", "promote_run"):
        assert decision(AUTO, {"tool_name": PREFIX + tool}) is None, tool


def _submit(payload):
    return {"tool_name": PREFIX + "submit_page_payload",
            "tool_input": {"run_id": "r", "page": "context", "payload": payload}}


CLEAN = {"timeline": {"produced_at": "2026-08-17T00:00:00Z",
                      "producer_version": "1.0.0", "e_ids": [],
                      "internal_only": [], "arc_shape": "STEADY_INVESTMENT"}}


def test_a_clean_submit_is_approved():
    assert decision(SUBMIT, _submit(CLEAN)) == "allow"


def test_a_banned_band_word_is_still_refused():
    """Invariant 6 — M5/Transformational does not exist. The approval may not
    cost this check; it fires BEFORE the network round-trip, which is the
    whole reason precheck_submit exists."""
    bad = json.loads(json.dumps(CLEAN))
    bad["timeline"]["note"] = "the entity is Transformational on this axis"
    r = run(SUBMIT, _submit(bad))
    assert r.returncode == 2
    assert r.stdout.strip() == "", "a refused submit must not also be approved"
    assert "M5" in r.stderr or "Transformational" in r.stderr


def test_a_colour_hex_is_still_refused():
    """Invariant 7 — no colour in any payload."""
    bad = json.loads(json.dumps(CLEAN))
    bad["timeline"]["note"] = "render it in #62D7B8 please"
    r = run(SUBMIT, _submit(bad))
    assert r.returncode == 2
    assert r.stdout.strip() == ""


def test_a_missing_envelope_is_still_refused():
    r = run(SUBMIT, _submit({"timeline": {"arc_shape": "STEADY_INVESTMENT"}}))
    assert r.returncode == 2
    assert r.stdout.strip() == ""
    assert "envelope missing" in r.stderr


def test_promote_is_approved_and_keeps_its_whole_advisory():
    """The advisory used to be a bare print. Owning the decision means stdout
    must be the decision JSON — so the warning moves into the reason rather
    than being traded away for the approval."""
    r = run(PROMOTE, {"tool_name": PREFIX + "promote_run",
                      "tool_input": {"run_id": "7a6ad71c"}})
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow"
    reason = out["permissionDecisionReason"]
    for phrase in ("ALL SIX pages", "atomically", "customer_allowlist",
                   "one-page fix", "7a6ad71c"):
        assert phrase in reason, f"advisory lost {phrase!r}"


# ── 4 · the wiring ──


def test_the_hook_is_registered_for_the_connector():
    cfg = json.loads(HOOKS_JSON.read_text())
    pre = cfg["hooks"]["PreToolUse"]
    matchers = {e["matcher"]: e for e in pre}
    ours = [m for m in matchers if m.startswith("mcp__plugin_dma-insights_connector__")
            and m.endswith(".*")]
    assert ours, f"no connector-wide PreToolUse matcher in hooks.json: {list(matchers)}"
    cmds = " ".join(h["command"] for h in matchers[ours[0]]["hooks"])
    assert "autoapprove_connector.py" in cmds


def test_the_credential_guard_is_still_registered():
    """The deny hook and the allow hook are siblings; landing one must never
    quietly drop the other."""
    cfg = json.loads(HOOKS_JSON.read_text())
    cmds = " ".join(h["command"] for e in cfg["hooks"]["PreToolUse"]
                    for h in e["hooks"])
    assert "deny_credential_ops.py" in cmds
    assert "precheck_submit.py" in cmds
    assert "precheck_promote.py" in cmds


def test_every_registered_hook_script_exists():
    cfg = json.loads(HOOKS_JSON.read_text())
    for event, entries in cfg["hooks"].items():
        for e in entries:
            for h in e["hooks"]:
                name = h["command"].split("/")[-1].strip('"')
                assert (HOOKS / name).exists(), f"{event}: {name} is missing"
