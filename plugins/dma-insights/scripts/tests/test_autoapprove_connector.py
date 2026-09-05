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
    "Bash", "Write", "Edit", "Read", "Task",
    "mcp__Gmail__send_message",
    "mcp__Google_Drive__update_file",
    "mcp__github__create_pull_request",
    "mcp__plugin_other-plugin_connector__do_thing",
])
def test_no_other_tool_is_ever_approved(tool):
    assert decision(AUTO, {"tool_name": tool}) is None, (
        f"{tool} drew a decision from a hook that must only speak for this "
        f"plugin's connector")


# ── the built-in web tools ARE approved (AUD-0117) ──
#
# Owner, 2026-09-01: "still getting approval prompts" while sixteen research
# producers ran. Root cause: this hook was wired only to `mcp__.*`, but the
# producers' PRIMARY retrieval is the built-in WebSearch/WebFetch, which no
# auto-approve hook matched and permissions.allow did not list — so each fell
# through to a prompt. They are read-only web reads and must run headless.


@pytest.mark.parametrize("tool", ["WebSearch", "WebFetch"])
def test_the_builtin_web_tools_are_approved_without_a_human(tool):
    assert decision(AUTO, {"tool_name": tool}) == "allow", (
        f"{tool} must auto-approve — it is the research routine's primary "
        f"read-only retrieval path and blocking it stops headless operation")


def test_bash_and_write_are_still_not_web_approved():
    """The web allowance is exactly WebSearch/WebFetch — not a blanket
    built-in grant. Bash keeps its own deny hooks; Write/Edit are never web."""
    for tool in ("Bash", "Write", "Edit"):
        assert decision(AUTO, {"tool_name": tool}) is None, tool


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
    # add-company-data-points / add-contact-data-points were here until
    # 2026-09-05 with the reason "writes to the user's Clay workspace". They are
    # REQUIRED by the technographic scan and the enrichment rulebooks and were
    # measured prompting a plain session, so — owner's decision — they moved to
    # SANCTIONED_WORKSPACE_WRITES and are auto-approved by the hook
    # (test_the_clay_data_point_writes_are_sanctioned proves it). The Clay
    # writes that STAY refused are run_subroutine / run_subroutine_direct, a
    # user-authored subroutine that can do anything.
    "run_subroutine": "a user-authored workspace subroutine can do anything",
    "run_subroutine_direct": "a user-authored workspace subroutine can do anything",
    # `slack_send_message` was here until 2026-08-30 with the reason "the
    # channel that would use it is specified and not built". The channel IS
    # built now — the assessment intake reads #deal-desk and replies in the
    # request's thread — so the obligation that entry recorded has been
    # discharged, and the tool moved to CONDITIONAL_TOOLS: allowed into that
    # one channel, still prompting everywhere else. Leaving it here would
    # have made this table say a thing that is no longer true.
    #
    # Cowork's shell tool (2026-09-04). Not blanket-approved by THIS hook on
    # purpose: a shell command is approved or not by its CONTENT, and that
    # decision is autoapprove_builtins.py's, which is registered against
    # `mcp__workspace__bash` and applies the same grammar it applies to Bash.
    # Approving the tool by name here would wave through `git push` in Cowork.
    "bash": "Cowork's shell — decided command by command by autoapprove_builtins.py",
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
    suffix = full.rsplit("__", 1)[1]
    return (suffix in aac.ENRICHMENT_TOOLS
            or suffix in aac.SANCTIONED_WORKSPACE_WRITES)


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
        if full in aac.CONDITIONAL_TOOLS:
            # Allowed on an ARGUMENT rather than a name. It is answered for —
            # see test_the_conditional_send_is_scoped_to_one_channel, which
            # proves both halves of the claim.
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


def test_the_clay_data_point_writes_are_sanctioned_and_subroutines_are_not():
    # Owner 2026-09-05: the two data-point writes are REQUIRED by the
    # technographic scan and the enrichment rulebooks and must run headless, so
    # they are approved by the plugin's own hook rather than a bootstrap wildcard.
    for t in ("mcp__Clay__add-company-data-points",
              "mcp__Clay__add-contact-data-points"):
        assert _is_allowed(t), t
    # A workspace subroutine is user-authored and can do anything: still refused.
    for t in ("mcp__Clay__run_subroutine",
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
        # MATCHES rather than CONTAINS. The matchers became regexes on
        # 2026-08-31 so the prechecks fire for the connector under its
        # claude.ai server name too — `mcp__.*__submit_page_payload` no
        # longer contains the literal tool name, and asserting containment
        # would have failed the widening that closed the gap.
        import re as _re
        pats = [e.get("matcher") for e in json.loads(pre)
                if e.get("matcher") and _re.fullmatch(str(e["matcher"]), tool)]
        assert pats, f"{tool} has no PreToolUse entry of its own"
        assert script in pre, f"{script} is not wired for {tool}"
        assert (HOOKS / script).exists(), f"{script} is missing from the plugin"


# ── the SESSION's roster, not just the tools this repo writes down ───────
#
# The scan above reads the plugin's own markdown, so it can only ever see
# tools this repository mentions. Measured 2026-08-30, the owner's actual
# complaint was the other kind — "I do not constantly have to approve tool
# calls" is mostly Slack, Salesforce, Google Admin, Auctor and GitHub, none of
# which this plugin names anywhere. Feeding the real hook the 86 tools one
# session carried: 16 approved, 70 prompting, and not one of the 70 had ever
# been ruled on.

import importlib.util as _ilu                                # noqa: E402

_AUDIT = _ilu.spec_from_file_location(
    "audit_autoapprove", _PLUGIN / "scripts" / "audit_autoapprove.py")
AA = _ilu.module_from_spec(_AUDIT)
_AUDIT.loader.exec_module(AA)


def test_every_tool_on_the_measured_roster_has_a_decision():
    """ALLOWED, WITHHELD or GUARDED. `UNCLASSIFIED` means a tool sits on a
    server this hook already knows and nobody ever ruled on it — so it
    prompts on every call, forever, and no one is told."""
    out = AA.audit(AA.read_roster())
    assert out["total"] > 100, "the roster looks truncated"
    assert not out["unclassified"], out["unclassified"]
    assert not out["unknown_server"], out["unknown_server"]


def test_the_roster_is_mostly_approved():
    """The point of the exercise. A roster where most calls still prompt is
    the state the owner reported, whatever the classification says."""
    out = AA.audit(AA.read_roster())
    assert len(out["allowed"]) > out["total"] / 2, (
        f"only {len(out['allowed'])} of {out['total']} approved")


def test_read_and_withheld_never_overlap():
    for server, surface in aac.SERVER_SURFACES.items():
        clash = surface["read"] & surface["withheld"]
        assert not clash, f"{server}: {clash} is both allowed and refused"
    assert not (aac.QUALIFIED_TOOLS & aac.WITHHELD_TOOLS)


#: Verbs that mean a call CHANGES something, matched as whole TOKENS. A read
#: allowlist is one careless addition away from carrying a write, and the
#: addition would look exactly like every other line in the table.
#:
#: Tokens, not substrings: the first version matched `request_` inside
#: `pull_request_read` and called a read a write. A lint that cries wolf gets
#: widened until it says nothing, so `request` is not here at all — it is a
#: noun in every name this session carries — while `run` is absent for the
#: same reason (`get_check_run`).
_WRITE_VERBS = frozenset({
    "create", "update", "delete", "remove", "add", "send", "post", "push",
    "merge", "archive", "suspend", "trash", "share", "write", "export",
    "save", "move", "schedule", "enable", "disable", "offboard", "swap",
    "trigger", "fork", "resolve", "unresolve", "subscribe", "unsubscribe",
})


def _tokens(name: str) -> list[str]:
    """Split on `_`, `-`, and camelCase — `listRecentSobjectRecords` and
    `list_recent_files` have to tokenise the same way or half this session's
    connectors slip past the lint on spelling alone."""
    spaced = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [t for t in _re.split(r"[_\-]+", spaced.lower()) if t]


def test_nothing_on_the_read_allowlist_looks_like_a_write():
    """A name-shape lint, deliberately blunt. It cannot prove a tool is
    read-only — only its server can — but every write this session's
    connectors expose is named for what it does, and a blunt check that fires
    on the next careless addition beats a subtle one that does not exist."""
    offenders = []
    for server, surface in aac.SERVER_SURFACES.items():
        for tool in surface["read"]:
            if set(_tokens(tool)) & _WRITE_VERBS:
                offenders.append(f"mcp__{server}__{tool}")
    assert not offenders, (
        f"these are auto-approved and named like writes: {offenders}. If one "
        f"really is read-only, say so where it is listed; do not widen the "
        f"lint.")


def test_the_lint_would_actually_catch_a_write_smuggled_into_a_read_set():
    """A lint nobody has seen fire is a lint nobody should trust."""
    for name in ("create_file", "slack_send_message", "auctor_update_space",
                 "createSobjectRecord", "bulk_offboard_users",
                 "merge_pull_request", "trash_file"):
        assert set(_tokens(name)) & _WRITE_VERBS, name
    for name in ("pull_request_read", "get_check_run", "soqlQuery",
                 "listRecentSobjectRecords", "list_saved_items",
                 "pmo_retrieve_grounding_bundle", "get_file_permissions"):
        assert not (set(_tokens(name)) & _WRITE_VERBS), name


def test_the_writes_this_session_carries_are_all_still_refused():
    for t in ("mcp__Slack__slack_send_message_draft",
              "mcp__Salesforce_Prod__deleteSobjectRecord",
              "mcp__Salesforce_Prod__createSobjectRecord",
              "mcp__GAdmin_MCP__suspend_user",
              "mcp__GAdmin_MCP__bulk_offboard_users",
              "mcp__Google_Drive__trash_file",
              "mcp__Google_Drive__share_file",
              "mcp__github__merge_pull_request",
              "mcp__github__push_files",
              "mcp__Auctor_MCP__auctor_update_space"):
        assert not _is_allowed(t), f"{t} must keep its prompt"


def test_the_reads_this_session_carries_are_allowed():
    for t in ("mcp__Slack__slack_read_channel",
              "mcp__Slack__slack_search_public",
              "mcp__Salesforce_Prod__soqlQuery",
              "mcp__GAdmin_MCP__list_users",
              "mcp__Google_Drive__get_file_permissions",
              "mcp__github__pull_request_read",
              "mcp__github__get_job_logs",
              "mcp__Auctor_MCP__auctor_list_spaces",
              "mcp__Grace_PMO__pmo_retrieve_grounding_bundle",
              "mcp__Indeed__get_resume"):
        assert _is_allowed(t), f"{t} still prompts"


def test_the_audit_runs_the_real_hook_rather_than_re_deriving_it():
    """A checker that re-implements the rule it checks agrees with itself by
    construction and proves nothing."""
    src = (_PLUGIN / "scripts" / "audit_autoapprove.py").read_text()
    assert "subprocess.run([sys.executable, HOOK]" in src, src[:200]


def test_strict_fails_on_an_unclassified_tool_on_a_known_server(tmp_path):
    roster = tmp_path / "r.txt"
    roster.write_text("# a tool nobody ruled on\n"
                      "mcp__Slack__slack_invent_a_new_verb\n")
    assert AA.main(["--roster", str(roster), "--strict"]) == 1


def test_strict_passes_when_every_tool_is_ruled_on(tmp_path):
    roster = tmp_path / "r.txt"
    roster.write_text("mcp__Slack__slack_read_channel\n"
                      "mcp__Slack__slack_send_message\n"
                      "mcp__plugin_dma-insights_connector__promote_run\n")
    assert AA.main(["--roster", str(roster), "--strict"]) == 0


# ── the conditional send: one channel, and only one ─────────────────────
#
# The assessment intake reads #deal-desk for requests and replies in the
# request's own thread when the assessment is delivered. That reply is a SEND,
# and a scheduled session has nobody to answer its prompt — the failure this
# whole file exists to prevent. Blanket-approving it would hand every agent in
# every firing the ability to post anywhere in the workspace, so the decision
# reads the ARGUMENT instead.

def _decide(tool, args=None):
    """The REAL hook, with a real PreToolUse event."""
    event = {"tool_name": tool, "hook_event_name": "PreToolUse"}
    if args is not None:
        event["tool_input"] = args
    r = subprocess.run([sys.executable, str(HOOKS / "autoapprove_connector.py")],
                       input=json.dumps(event), capture_output=True,
                       text=True, timeout=60)
    if not r.stdout.strip():
        return None
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_the_conditional_send_is_scoped_to_one_channel():
    tool = "mcp__Slack__slack_send_message"
    assert _decide(tool, {"channel_id": aac.DEAL_DESK_CHANNEL_ID,
                          "message": "done"}) == "allow"
    assert _decide(tool, {"channel_id": "C0SOMEWHEREELSE",
                          "message": "done"}) is None
    assert _decide(tool, {"message": "no channel at all"}) is None
    assert _decide(tool) is None, "no arguments at all must not allow"


def test_an_out_of_scope_send_is_not_DENIED_only_undecided():
    """A deny would also block a person driving an interactive session. This
    hook exists to spare an unattended session a prompt, not to take a
    decision away from someone who is there to make it."""
    assert _decide("mcp__Slack__slack_send_message",
                   {"channel_id": "C0SOMEWHEREELSE", "message": "x"}) is None


def test_a_conditional_tool_is_never_in_a_read_set_or_the_settings_grant():
    """The trap. `bootstrap_session.sh` derives user-scope permissions.allow
    from the read sets, and a settings grant is honoured WITHOUT the hook
    being consulted — so a conditional tool in a read set would be approved
    everywhere and its channel check would exist and never run."""
    for tool in aac.CONDITIONAL_TOOLS:
        assert tool not in aac.QUALIFIED_TOOLS, tool
        assert tool not in aac.WITHHELD_TOOLS, tool
        assert aac.suffix_of(tool) not in aac.ENRICHMENT_TOOLS \
            if hasattr(aac, "suffix_of") else True

    src = (_PLUGIN / "scripts" / "bootstrap_session.sh").read_text()
    assert "CONDITIONAL_TOOLS" in src, (
        "the grant derivation must exclude conditional tools explicitly, or "
        "moving one into a read set silently un-scopes it")


def test_the_channel_constant_agrees_with_the_intake_script():
    """Two files naming one channel is how a rule starts applying to the
    wrong room. The hook cannot import from scripts/ — it runs standalone
    from the installed plugin — so the constants are pinned to each other
    here instead."""
    sys.path.insert(0, str(_PLUGIN / "scripts"))
    import slack_intake

    assert aac.DEAL_DESK_CHANNEL_ID == slack_intake.DEAL_DESK_CHANNEL_ID


def test_every_conditional_tool_states_why_and_what_it_is_scoped_to():
    for tool, rule in aac.CONDITIONAL_TOOLS.items():
        assert rule["why"].strip(), tool
        assert rule["scope"].strip(), tool
        assert callable(rule["test"]), tool


# ── the same connector under a different server name ──────────────────────
#
# OWNER, 2026-08-31: "I keep on getting requests to approve the get client
# state tool." The plugin installs the DMA connector as
# `mcp__plugin_dma-insights_connector__*`. A Routine attaches the SAME
# server as a claude.ai connector, and its trigger record names it
# `DMA-Insights` — so a trigger-fired session sees
# `mcp__DMA-Insights__get_client_state`, which matched nothing here and
# prompted. A scheduled container has nobody to answer.
#
# `audit_autoapprove.py --strict` reported PASS through all of it, because
# it audits the names this hook already knows: a check that reads the config
# it is checking can only ever confirm it.

_ALT = "mcp__DMA-Insights__"


def test_the_connector_is_approved_under_a_claude_ai_server_name():
    for tool in ("get_client_state", "list_pending_runs", "get_evidence",
                 "claim_run", "get_memory_digest"):
        assert _decide(_ALT + tool) == "allow", tool


def test_the_guarded_pair_still_prompts_under_any_server_name():
    """Auto-approving these would wave a submit or a promote through with
    no precheck at all if the precheck matcher did not fire for that server
    segment. A prompt in a scheduled session STOPS the firing, which is the
    safe direction for the two calls that write serving content."""
    for tool in ("submit_page_payload", "promote_run"):
        assert _decide(_ALT + tool) != "allow", tool
        assert _decide(PREFIX + tool) != "allow", tool


def test_the_precheck_hooks_fire_for_both_server_names():
    """The other half of the same fix: widening the auto-approve without
    widening the prechecks would move the guarded pair out from under its
    own gate."""
    import json as _json
    import re as _re
    hooks = _json.loads(
        (HOOKS.parent.parent / "hooks" / "hooks.json").read_text())
    matchers = [e.get("matcher") for lst in hooks["hooks"].values()
                for e in lst if e.get("matcher")]
    for suffix in ("submit_page_payload", "promote_run"):
        pats = [m for m in matchers if m.endswith(suffix)]
        assert pats, suffix
        for m in pats:
            for name in (PREFIX + suffix, _ALT + suffix):
                assert _re.fullmatch(m, name), (m, name)


def test_the_allowed_set_is_exactly_what_the_connector_serves():
    """DERIVED, not typed. The 33 tool names are read out of
    apps/mcp/server.py, so a tool added to the connector and forgotten here
    fails this test rather than prompting in production."""
    import ast
    import pathlib as _pl
    h = aac
    server = (_pl.Path(__file__).resolve().parents[4]
              / "apps" / "mcp" / "server.py")
    if not server.is_file():                       # packaged install
        import pytest as _pytest
        _pytest.skip("apps/mcp/server.py is not in this tree")
    tree = ast.parse(server.read_text())
    served = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)
              and any(getattr(d, "attr", None) == "tool"
                      or (isinstance(d, ast.Call)
                          and getattr(d.func, "attr", "") == "tool")
                      for d in n.decorator_list)}
    assert served, "no @mcp.tool functions found — the parser is wrong"
    assert h.DMA_TOOLS == served, (
        f"only in the hook: {sorted(h.DMA_TOOLS - served)}; "
        f"only in the connector: {sorted(served - h.DMA_TOOLS)}")


# ── stress: server spelling resilience (AUD-0114, owner 2026-09-01) ──
#
# The owner kept being prompted for Google-Drive / Vibe-Prospecting: the tables
# spell those servers with underscores, the live connector attaches under a
# HYPHEN segment, and a full-name rule written one way missed the other. These
# tests drive from SERVER_SURFACES itself so coverage cannot drift, and assert
# every classified read approves under BOTH spellings while every write still
# prompts under both.
import importlib as _importlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "hooks"))
_AAC = _importlib.import_module("autoapprove_connector")


def _hyphen_server(tool: str) -> str:
    parts = tool.split("__")
    parts[1] = parts[1].replace("_", "-")
    return "__".join(parts)


@pytest.mark.parametrize("server", sorted(_AAC.SERVER_SURFACES))
def test_classified_reads_approve_under_both_server_spellings(server):
    for t in sorted(_AAC.SERVER_SURFACES[server]["read"]):
        full = f"mcp__{server}__{t}"
        if full in _AAC.CONDITIONAL_TOOLS:
            continue
        for name in (full, _hyphen_server(full)):
            assert decision(AUTO, {"tool_name": name, "tool_input": {}}) == "allow", \
                f"{name}: a classified read must auto-approve under either spelling"


@pytest.mark.parametrize("server", sorted(_AAC.SERVER_SURFACES))
def test_classified_writes_still_prompt_under_both_server_spellings(server):
    for t in sorted(_AAC.SERVER_SURFACES[server]["withheld"]):
        full = f"mcp__{server}__{t}"
        for name in (full, _hyphen_server(full)):
            assert decision(AUTO, {"tool_name": name, "tool_input": {}}) is None, \
                f"{name}: a withheld write must NOT be auto-approved under any spelling"


@pytest.mark.parametrize("tool", [
    # every connector the owner named, plus the multi-word ones both ways
    "mcp__Tavily__tavily_search", "mcp__Tavily__tavily_extract",
    "mcp__Exa__web_search_exa", "mcp__Exa__web_fetch_exa",
    "mcp__Clay__find-and-enrich-company", "mcp__Clay__get-task-context",
    "mcp__Indeed__search_jobs", "mcp__Indeed__get_company_data",
    "mcp__Vibe-Prospecting__enrich-business",
    "mcp__Vibe_Prospecting__enrich-business",
    "mcp__Google-Drive__search_files", "mcp__Google_Drive__search_files",
    "mcp__Google-Drive__get_file_permissions",
    "mcp__DMA-Insights__get_client_state",
    "mcp__plugin_dma-insights_connector__get_client_state",
])
def test_the_connectors_the_owner_named_all_auto_approve(tool):
    assert decision(AUTO, {"tool_name": tool, "tool_input": {}}) == "allow", \
        f"{tool} must auto-approve without a human — the routine runs headless"


# ── the resilient default: new / renamed tools classified by verb ──
#
# Owner 2026-09-01: the hook must factor in tools nobody listed — new ones and
# renamed ones — the moment they appear. A read verb approves; a write/send
# verb prompts; an unrecognised verb prompts; explicit withholds win.

@pytest.mark.parametrize("tool", [
    "mcp__BrandNewCo__get_widgets", "mcp__BrandNewCo__list_accounts",
    "mcp__Whatever__search_v2_results", "mcp__Exa__web_search_v3_exa",
    "mcp__NewCo__retrieve_report", "mcp__NewCo__fetch_thing",
    "mcp__NewCo__describe_dataset", "mcp__NewCo__lookup_entity",
])
def test_an_unlisted_read_tool_on_any_connector_auto_approves(tool):
    assert decision(AUTO, {"tool_name": tool, "tool_input": {}}) == "allow", \
        f"{tool}: a read verb must auto-approve without a rule change"


@pytest.mark.parametrize("tool", [
    "mcp__BrandNewCo__create_widget", "mcp__BrandNewCo__update_record",
    "mcp__BrandNewCo__delete_thing", "mcp__BrandNewCo__send_email",
    "mcp__BrandNewCo__export_data", "mcp__BrandNewCo__run_job",
    "mcp__BrandNewCo__post_message", "mcp__BrandNewCo__share_folder",
    "mcp__BrandNewCo__get_and_delete_record",   # WRITE wins over the read verb
])
def test_an_unlisted_write_tool_still_prompts(tool):
    assert decision(AUTO, {"tool_name": tool, "tool_input": {}}) is None, \
        f"{tool}: a write/send verb must still prompt"


@pytest.mark.parametrize("tool", [
    "mcp__BrandNewCo__frobnicate", "mcp__BrandNewCo__handshake",
    "mcp__BrandNewCo__widgetize",
])
def test_an_unrecognised_verb_prompts(tool):
    assert decision(AUTO, {"tool_name": tool, "tool_input": {}}) is None, \
        f"{tool}: a name with no read or write verb must prompt, not guess"


def test_an_explicit_withhold_wins_over_a_read_looking_name():
    # github resolve_review_thread is a WRITE the hook withholds; it must stay a
    # prompt even though a naive reader might see "resolve" as harmless.
    assert decision(AUTO, {"tool_name": "mcp__github__resolve_review_thread",
                           "tool_input": {}}) is None


@pytest.mark.parametrize("evil", [
    {"tool_name": "mcp__x__y__z__weird", "tool_input": {}},
    {"tool_name": "mcp__", "tool_input": None},
    {"tool_name": "mcp__a__b", "tool_input": {"weird": "☃"}},
    {"tool_name": "mcp__a__b__" + "x" * 5000},
    {"tool_name": 12345},
    {},
])
def test_the_hook_never_crashes_and_never_errors(evil):
    # A hook that can exit non-zero is not resilient. Whatever valid JSON event
    # arrives, it must exit 0 — a decision or silence, never an error.
    r = run(AUTO, evil)
    assert r.returncode == 0, f"hook errored on {evil!r}: {r.stderr}"


# ── the third spelling: connectors Claude Code fetches from claude.ai itself ─
#
# Permissions reference, measured 2026-09-04 while chasing the Tavily and Exa
# prompts the owner still saw on every surface: "Tools from connectors Claude
# Code fetches itself appear as `mcp__claude_ai_<server>__<tool>`". A read
# set written for `Google_Drive` must see through that prefix, and so must
# the withheld set — or a Drive write under this spelling is judged by the
# verb heuristic alone.

@pytest.mark.parametrize("tool", [
    "mcp__claude_ai_Tavily__tavily_search",
    "mcp__claude_ai_Exa__web_search_exa",
    "mcp__claude_ai_Google_Drive__search_files",
    "mcp__claude_ai_Google-Drive__read_file_content",
    "mcp__claude_ai_Quartr__search",
    "mcp__claude_ai_Clay__find-and-enrich-company",
])
def test_a_read_under_the_claude_ai_prefix_is_approved(tool):
    assert decision(AUTO, {"tool_name": tool}) == "allow", tool


@pytest.mark.parametrize("tool", [
    "mcp__claude_ai_Google_Drive__trash_file",
    "mcp__claude_ai_Google_Drive__share_file",
    "mcp__claude_ai_Slack__slack_send_message_draft",
    "mcp__claude_ai_Clay__run_subroutine",
])
def test_a_write_under_the_claude_ai_prefix_still_prompts(tool):
    assert decision(AUTO, {"tool_name": tool}) is None, tool


def test_the_canonical_form_strips_the_claude_ai_prefix_only_on_the_server():
    assert aac._canonical("mcp__claude_ai_Google-Drive__search_files") == \
        "mcp__Google_Drive__search_files"
    assert aac._canonical("mcp__Google_Drive__search_files") == \
        "mcp__Google_Drive__search_files"
    # a TOOL id that happens to contain the prefix is left alone
    assert aac._canonical("mcp__X__claude_ai_thing") == "mcp__X__claude_ai_thing"
