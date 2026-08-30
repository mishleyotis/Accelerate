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


# ── the allowlist must keep step with what the agents actually require ────
#
# Owner, 2026-08-23: "each time I have to approve MCP tool calls in the
# routine eg Tavily, Clay etc. Ensure this runs headless."
#
# The list was extended by hand that day and one required call was still
# missing — not because anyone forgot it, but because the SUFFIX rule could
# not express it: `mcp__Quartr__search` would have needed the bare suffix
# `search`, which allows `search` on every connector a session ever attaches.
# That is why QUALIFIED_TOOLS exists.
#
# The test below is the part that lasts. It reads every MCP tool the plugin's
# own agents and skills name and asserts each is either allowed or
# deliberately not, so the next agent that gains a connector tool either gets
# it allowed or fails here — instead of a routine stopping in a container
# with nobody to answer.

import importlib.util as _ilu
import re as _re
from pathlib import Path as _Path

_PLUGIN = _Path(__file__).resolve().parents[2]


def _load_hook():
    """Import the hook as a module. The tests above drive it as a subprocess,
    which is the right shape for asserting its OUTPUT; these assert its
    allowlists against the plugin's own files, which needs the objects."""
    spec = _ilu.spec_from_file_location("autoapprove_connector", AUTO)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aac = _load_hook()

#: Named by an agent and deliberately NOT auto-approved, each with the reason.
#: A tool may only sit here because approving it would be WRONG, never because
#: nobody got to it.
_DELIBERATELY_PROMPTING = {
    # Clay writes into the user's own workspace. Granted in the enrichment
    # specialist's frontmatter, never actually called anywhere in its prose,
    # so leaving the prompt costs no firing and auto-approving would hand a
    # scheduled session a write nobody sanctioned.
    "add-company-data-points": "writes to the user's Clay workspace",
    "add-contact-data-points": "writes to the user's Clay workspace",
    # Named ONLY by docs/CLIENT-SELECTION.md §3.5, as the reply path of a
    # Slack channel that is specified and NOT BUILT. A send publishes to an
    # external surface: it reaches people, it is not retractable, and no
    # Routine calls it today, so the prompt costs no firing. Whoever builds
    # §3 has to make that approval deliberately, in the same change that
    # builds the sender — inheriting a blanket allow from a document that
    # merely NAMES the tool is how an unattended session acquires a voice.
    "slack_send_message": "publishes to an external surface; the channel that "
                          "would use it is specified and not built",
}


def _tools_named_by_the_plugin():
    pat = _re.compile(r"\bmcp__([A-Za-z0-9_\-]+)__([A-Za-z0-9_\-]+)")
    found = {}
    for f in _PLUGIN.rglob("*.md"):
        for m in pat.finditer(f.read_text(errors="ignore")):
            found.setdefault(m.group(0), set()).add(
                str(f.relative_to(_PLUGIN)))
    return found


def _is_allowed(full: str) -> bool:
    if full.startswith(aac.PREFIX):
        return full not in aac.GUARDED          # the connector's own tools
    if full in aac.QUALIFIED_TOOLS:
        return True
    return full.rsplit("__", 1)[1] in aac.ENRICHMENT_TOOLS


def test_every_mcp_tool_the_plugin_names_is_allowed_or_deliberately_not():
    named = _tools_named_by_the_plugin()
    assert named, "found no MCP tool names to check — the scan is broken"
    unexplained = {}
    for full, where in named.items():
        if _is_allowed(full):
            continue
        if full in aac.GUARDED:
            # submit_page_payload and promote_run carry their OWN PreToolUse
            # hooks (precheck_submit.py, precheck_promote.py) which emit the
            # decision. This hook stands aside on purpose — two hooks on one
            # tool with opposite opinions is not a resolution order to bet a
            # promote on — so they are answered for, not left prompting.
            continue
        if full.rsplit("__", 1)[1] in _DELIBERATELY_PROMPTING:
            continue
        unexplained[full] = sorted(where)[0]
    assert not unexplained, (
        "these MCP tools are named by the plugin's own agents or skills and "
        "will stop a scheduled firing on a permission prompt nobody can "
        "answer. Either add each to ENRICHMENT_TOOLS (read-only, opaque "
        "server segment) or QUALIFIED_TOOLS (read-only, stable server "
        "segment), or record it in _DELIBERATELY_PROMPTING with the reason "
        f"approving it would be wrong: {unexplained}")


def test_quartr_search_is_allowed_by_its_full_name_only():
    """The call the suffix rule could not express."""
    assert "mcp__Quartr__search" in aac.QUALIFIED_TOOLS
    assert "search" not in aac.ENRICHMENT_TOOLS, (
        "allowing the bare suffix would allow `search` on every connector "
        "this session ever attaches — LunarCrush's included")


def test_a_common_word_suffix_stays_unapproved_on_another_connector():
    assert not _is_allowed("mcp__LunarCrush__search")
    assert not _is_allowed("mcp__SomeOtherServer__search")


def test_the_qualified_list_never_carries_an_opaque_server_segment():
    """A per-attachment UUID cannot be written down in advance; a full name
    containing one is a rule that will silently stop matching."""
    uuidish = _re.compile(r"__[0-9a-f]{8}-[0-9a-f]{4}-", _re.I)
    for t in aac.QUALIFIED_TOOLS:
        assert not uuidish.search(t), t
        assert t.startswith("mcp__") and t.count("__") >= 2, t


def test_the_clay_writes_are_still_refused():
    for t in ("mcp__Clay__add-company-data-points",
              "mcp__Clay__add-contact-data-points",
              "mcp__Clay__run_subroutine",
              "mcp__Clay__run_subroutine_direct"):
        assert not _is_allowed(t), t


def test_the_guarded_pair_is_answered_by_its_own_hooks_not_left_prompting():
    """This hook stands aside for them; something else must not. If either
    precheck hook stopped emitting a decision, a scheduled firing would hang
    on a submit — the exact failure this whole file exists to prevent."""
    cfg = json.loads(HOOKS_JSON.read_text())
    pre = json.dumps(cfg["hooks"]["PreToolUse"])
    for tool, script in ((PREFIX + "submit_page_payload", "precheck_submit.py"),
                         (PREFIX + "promote_run", "precheck_promote.py")):
        assert tool in pre, f"{tool} has no PreToolUse entry of its own"
        assert script in pre, f"{script} is not wired for {tool}"
        assert (HOOKS / script).exists(), f"{script} is missing from the plugin"
