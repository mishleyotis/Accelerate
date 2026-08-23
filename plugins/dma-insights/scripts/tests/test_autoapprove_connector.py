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
import os
import re
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


def test_the_hook_is_registered_for_every_mcp_tool():
    """The matcher is deliberately wide and the SCRIPT is narrow.

    It has to see enrichment connectors too, and their server segment is an
    opaque per-attachment UUID that no matcher can name — so the matcher lets
    every MCP tool through and the allowlists above decide. The scope tests in
    this file are what keep that safe; a narrow matcher would have hidden them
    behind a rule nobody could read."""
    cfg = json.loads(HOOKS_JSON.read_text())
    matchers = {e["matcher"]: e for e in cfg["hooks"]["PreToolUse"]}
    assert "mcp__.*" in matchers, f"matchers present: {list(matchers)}"
    cmds = " ".join(h["command"] for h in matchers["mcp__.*"]["hooks"])
    assert "autoapprove_connector.py" in cmds


# ── the enrichment connectors ──


@pytest.mark.parametrize("tool", [
    "mcp__5e0fe4f4-8fd9-448d-a1b5-fafc63f9aa67__search_jobs",  # the real one
    "mcp__Exa__web_search_exa",
    "mcp__Exa__web_fetch_exa",
    "mcp__Tavily__tavily_search",
    "mcp__Tavily__tavily_extract",
    "mcp__Clay__find-and-enrich-company",
    "mcp__Vibe_Prospecting__enrich-business",
    "mcp__Indeed__get_company_data",
])
def test_a_read_only_enrichment_lookup_is_approved(tool):
    """STEP 0(b) makes these REQUIRED — the routine never runs in degrade
    mode — so a prompt on one of them stops a firing as dead as a prompt on
    our own connector. Measured 2026-08-21T03:09Z: the run reached the Drive
    pull and then stopped on search_jobs."""
    assert decision(AUTO, {"tool_name": tool}) == "allow"


def test_the_uuid_server_segment_is_not_what_grants_it():
    """The allowlist is by TOOL NAME. An unlisted tool on the very same server
    that carries an approved one draws nothing — otherwise approving one
    connector would approve everything it ever exposes."""
    server = "mcp__5e0fe4f4-8fd9-448d-a1b5-fafc63f9aa67__"
    assert decision(AUTO, {"tool_name": server + "search_jobs"}) == "allow"
    for unlisted in ("delete_everything", "send_message", "post_application",
                     "update_profile", "pay_invoice"):
        assert decision(AUTO, {"tool_name": server + unlisted}) is None, unlisted


@pytest.mark.parametrize("tool", [
    "mcp__Gmail__send_message", "mcp__Gmail__trash_thread",
    "mcp__Gmail__create_draft", "mcp__Google_Drive__update_file",
    "mcp__Google_Drive__trash_file", "mcp__github__create_pull_request",
    "mcp__github__merge_pull_request", "mcp__Figma__create_new_file",
])
def test_no_tool_that_writes_sends_or_spends_is_ever_approved(tool):
    assert decision(AUTO, {"tool_name": tool}) is None


def test_the_allowlist_contains_no_obvious_write_verb():
    """A cheap guard on the list itself: someone adding `send_message` or
    `create_*` to it later should have to notice they are doing so."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("aac", AUTO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in mod.ENRICHMENT_TOOLS:
        low = name.lower().replace("-", "_")
        for verb in ("send", "delete", "trash", "create", "update", "write",
                     "post", "pay", "purchase", "merge", "apply"):
            assert not low.startswith(verb), (
                f"{name!r} looks like a write; this list is read-only lookups")


def test_the_credential_guard_is_still_registered():
    """The deny hook and the allow hook are siblings; landing one must never
    quietly drop the other."""
    cfg = json.loads(HOOKS_JSON.read_text())
    cmds = " ".join(h["command"] for e in cfg["hooks"]["PreToolUse"]
                    for h in e["hooks"])
    assert "deny_credential_ops.py" in cmds
    assert "precheck_submit.py" in cmds
    assert "precheck_promote.py" in cmds


#: The handler path inside a hook command, wrapped or bare.
_HOOK_PATH = re.compile(r"/scripts/hooks/([A-Za-z0-9_.-]+\.py)")


def test_every_registered_hook_script_exists():
    """THE PACKAGING INVARIANT, and it has teeth now.

    A hooks.json that registers a script the package does not ship is not a
    cosmetic defect: a PreToolUse hook on Bash whose handler is missing
    blocks EVERY Bash call, which leaves the session unable to run
    plugin_version.py or the doctor — the two things that would tell it the
    install is stale. Measured 2026-08-23: a synthesis lane lost its whole
    firing to exactly that deadlock and misdiagnosed it as a harness hook.
    """
    cfg = json.loads(HOOKS_JSON.read_text())
    seen = 0
    for event, entries in cfg["hooks"].items():
        for e in entries:
            for h in e["hooks"]:
                names = _HOOK_PATH.findall(h["command"])
                assert names, f"{event}: no handler path in {h['command'][:80]}"
                # A wrapped command names the same script more than once
                # (the test and the message); they must agree.
                assert len(set(names)) == 1, f"{event}: {set(names)}"
                assert (HOOKS / names[0]).exists(), \
                    f"{event}: {names[0]} is registered and not shipped"
                seen += 1
    assert seen >= 8, f"only {seen} hook commands checked — extraction broke"


def test_a_missing_handler_allows_rather_than_blocking():
    """The other half of the same lesson. Shipping is enforced above; this
    pins what happens if it ever fails anyway — the session must keep its
    Bash tool and be TOLD, not silently lose every command."""
    cfg = json.loads(HOOKS_JSON.read_text())
    bash = [g for g in cfg["hooks"]["PreToolUse"] if g.get("matcher") == "Bash"]
    assert bash, "no Bash PreToolUse hook registered"
    cmd = bash[0]["hooks"][0]["command"]
    r = subprocess.run(["sh", "-c", cmd], input=b'{"tool_name":"Bash"}',
                       capture_output=True,
                       env={**os.environ,
                            "CLAUDE_PLUGIN_ROOT": "/nonexistent-plugin-root"})
    assert r.returncode == 0, "a missing handler must not block the call"
    assert b"MISSING" in r.stdout, "and it must say so"
    assert b"plugin_version" in r.stdout, "and name the check that diagnoses it"


def test_a_present_handler_can_still_deny():
    """The guard must keep guarding. `a && b || c` would have swallowed a
    real deny, because a deny exits non-zero; the wrapper uses an explicit
    if and passes the handler's exit through with exec."""
    cfg = json.loads(HOOKS_JSON.read_text())
    bash = [g for g in cfg["hooks"]["PreToolUse"] if g.get("matcher") == "Bash"]
    cmd = bash[0]["hooks"][0]["command"]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command":
        "git push https://x:ghp_" + "A" * 36 + "@github.com/a/b"}}).encode()
    r = subprocess.run(["sh", "-c", cmd], input=payload, capture_output=True,
                       env={**os.environ,
                            "CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})
    assert b"deny" in r.stdout, (
        f"the credential guard stopped denying through the wrapper: "
        f"{r.stdout[:200]!r}")
