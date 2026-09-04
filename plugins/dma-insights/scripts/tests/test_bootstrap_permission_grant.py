"""Installing the plugin is not the same as being allowed to use it.

Measured 2026-08-21, and it is the reason the scheduled synthesis routine had
never once produced a client. A session created with the repo attached bound
the connector perfectly — `mcp__plugin_dma-insights_connector__get_run_progress`
existed, and the session called it — and then stopped on:

    Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress

A trigger-fired container has nobody to answer that. The firing burns its
twelve-hour slot, stages nothing and records nothing, which is exactly the
trace the 00:08 firing left: fired 00:10:43Z, zero staged rows, zero findings.
Every diagnosis before this one looked at binding, because a session that
cannot call a tool and a session that is not allowed to call it fail
identically from the outside.

Two things have to hold, and the second is the one that is easy to get wrong:

  * the rule's server segment must be GLOB-FREE — `mcp__<server>__*` is
    honoured, `mcp__*` is skipped with a warning and approves nothing;
  * the grant must live in USER scope. The repo's own .claude/settings.json is
    PROJECT scope, and project permission rules are not applied in a
    non-interactive session — the workspace is untrusted and the rules are
    skipped. A grant committed there reviews as correct and changes nothing.

The tests below run the REAL block out of bootstrap_session.sh rather than a
copy of it, because a copy would keep passing after the script drifted.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
BOOTSTRAP = HERE.parent / "bootstrap_session.sh"
GRANT = "mcp__plugin_dma-insights_connector__*"
# The built-in web tools the grant block always adds (AUD-0117), in append
# order after the connector. The research routine's primary retrieval is
# WebSearch/WebFetch; granting them is what keeps a new session headless.
WEB = ["WebSearch", "WebFetch"]
# The pipeline's own commands and files (2026-09-03, the headless audit): the
# belt for `hooks/autoapprove_builtins.py`, in the order the block appends
# them. Prefix rules only — no bare Bash, no Write without a path.
BUILTIN = [
    "Bash(python3 -m engine.*)",
    "Bash(python3 plugins/dma-insights/*)",
    "Bash(python3 /home/user/Accelerate/plugins/dma-insights/*)",
    "Bash(python3 -m pytest *)",
    "Bash(bash plugins/dma-insights/scripts/*)",
    "Bash(bash /home/user/Accelerate/plugins/dma-insights/scripts/*)",
    "Write(/root/.dma/**)", "Edit(/root/.dma/**)",
    "Write(/home/claude/dma_output/**)", "Edit(/home/claude/dma_output/**)",
    "Write(/tmp/**)", "Edit(/tmp/**)",
]
BASE_GRANTS = [GRANT] + WEB + BUILTIN


def grant_block() -> str:
    """The permission-grant python, lifted out of the shell script itself.

    `<<'PY'` is not the end of its line — the redirection and an `|| echo`
    fallback follow it — so the pattern has to skip to the newline rather than
    demand one straight after the delimiter.
    """
    src = BOOTSTRAP.read_text()
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", src, re.S)
    for b in blocks:
        if "permissions" in b and "allow" in b:
            return b
    raise AssertionError(
        f"no permission-grant python block found in {BOOTSTRAP.name} "
        f"({len(blocks)} PY blocks seen)")


def code_lines() -> str:
    """The script with comments stripped — the rules it EXECUTES, not the
    prose about them. The comment above the grant quotes `mcp__*` as the form
    that does not work, and a naive substring search reads its own
    explanation as the defect."""
    return "\n".join(l for l in BOOTSTRAP.read_text().splitlines()
                     if not l.lstrip().startswith("#"))


def run_grant(settings: Path):
    r = subprocess.run([sys.executable, "-c", grant_block()],
                       capture_output=True, text=True,
                       env={"CLAUDE_SETTINGS": str(settings), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


# ── the rule itself ──


def test_the_script_grants_the_connector_at_all():
    assert GRANT in BOOTSTRAP.read_text(), (
        "bootstrap_session.sh no longer grants the connector — an unattended "
        "session will stop on a permission prompt nobody can answer")


def test_the_server_segment_is_glob_free():
    """`mcp__*` is skipped with a warning and approves nothing. A rule that
    looks more permissive and grants less is the worst possible outcome."""
    code = code_lines()
    for bad in ("mcp__*", "mcp__plugin_*", "mcp__plugin_dma-insights_*"):
        assert bad not in code, f"{bad} is skipped by the permission engine"
    assert GRANT in code, "the working rule is not in the executed script"


def test_the_grant_targets_user_scope_not_the_repo():
    """THE DISTINCTION THE WHOLE FIX TURNS ON. Project-scope rules are not
    applied in a non-interactive session, so a grant written into the repo's
    .claude/settings.json would have been invisible in exactly the sessions it
    was written for."""
    src = BOOTSTRAP.read_text()
    assert 'CLAUDE_SETTINGS="${HOME:-/root}/.claude/settings.json"' in src, (
        "the grant must be written to the user's settings, not the repo's")
    grant_region = src[src.index(GRANT) - 3000:src.index(GRANT) + 3000]
    assert "$REPO_DIR/.claude/settings.json" not in grant_region


# ── behaviour, against the real block ──


def test_a_missing_settings_file_is_created(tmp_path):
    s = tmp_path / ".claude" / "settings.json"
    assert "granted" in run_grant(s)
    assert json.loads(s.read_text())["permissions"]["allow"] == BASE_GRANTS


def test_running_twice_does_not_duplicate_the_rule(tmp_path):
    s = tmp_path / "settings.json"
    run_grant(s)
    out = run_grant(s)
    assert "already granted" in out
    assert json.loads(s.read_text())["permissions"]["allow"] == BASE_GRANTS


def test_headless_never_prompt_mode_is_set(tmp_path):
    """The mode-level guarantee that survives a stale plugin bind (owner
    2026-09-01, third recurring-prompt report). A fresh settings file must come
    out with defaultMode dontAsk, so a session that boots a snapshot's stale
    auto-approve hook still never queues a prompt no headless container can
    answer — anything the allow-list and hook do not cover is denied, not hung."""
    s = tmp_path / ".claude" / "settings.json"
    run_grant(s)
    assert json.loads(s.read_text())["permissions"]["defaultMode"] == "dontAsk"


def test_an_existing_mode_is_never_overridden(tmp_path):
    """A human who chose a mode keeps it — dontAsk is set only when unset."""
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"permissions": {"allow": [], "defaultMode": "plan"}}))
    run_grant(s)
    cfg = json.loads(s.read_text())
    assert cfg["permissions"]["defaultMode"] == "plan"
    assert cfg["permissions"]["allow"] == BASE_GRANTS  # grants still applied


def test_the_mode_persists_even_when_every_grant_is_present(tmp_path):
    """The bug this guards: the write used to be skipped when no grant was
    added, so a mode set on a fully-granted file was computed and thrown away.
    A second run adds no grant, yet the mode must be on disk."""
    s = tmp_path / "settings.json"
    run_grant(s)                              # first run grants + sets mode
    s.write_text(json.dumps({"permissions": {  # mode stripped, grants kept
        "allow": json.loads(s.read_text())["permissions"]["allow"]}}))
    out = run_grant(s)
    assert "already granted" in out
    assert json.loads(s.read_text())["permissions"]["defaultMode"] == "dontAsk"


def test_the_plugin_install_keys_survive_the_grant(tmp_path):
    """bootstrap writes enabledPlugins/extraKnownMarketplaces/pluginConfigs to
    this same file earlier in its own run. Clobbering them to fix permissions
    would uninstall the plugin in order to be allowed to use it."""
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({
        "enabledPlugins": {"dma-insights@zennify-dma": True},
        "extraKnownMarketplaces": {"zennify-dma": {"source": {"path": "/x"}}},
        "pluginConfigs": {"dma-insights@zennify-dma": {"options": {}}},
    }))
    run_grant(s)
    cfg = json.loads(s.read_text())
    assert cfg["enabledPlugins"] == {"dma-insights@zennify-dma": True}
    assert cfg["extraKnownMarketplaces"]["zennify-dma"]["source"]["path"] == "/x"
    assert "pluginConfigs" in cfg
    assert cfg["permissions"]["allow"] == BASE_GRANTS


def test_an_unrelated_allow_rule_is_kept(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"permissions": {"allow": ["Bash(git status)"],
                                             "deny": ["Read(//root/.dma/sa.json)"]}}))
    run_grant(s)
    cfg = json.loads(s.read_text())
    assert cfg["permissions"]["allow"] == ["Bash(git status)"] + BASE_GRANTS
    assert cfg["permissions"]["deny"] == ["Read(//root/.dma/sa.json)"]


# ── negative controls: refusing beats corrupting ──


def test_a_malformed_settings_file_is_left_untouched(tmp_path):
    """A broken settings.json silently disables EVERY setting in it. If the
    file is mid-edit or hand-damaged, refusing is the only safe move —
    overwriting it would take the plugin down to grant a permission."""
    s = tmp_path / "settings.json"
    s.write_text("{ this is not json")
    out = run_grant(s)
    assert "SKIPPED" in out
    assert s.read_text() == "{ this is not json"


def test_a_non_list_allow_is_refused_rather_than_replaced(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text('{"permissions":{"allow":"oops"}}')
    out = run_grant(s)
    assert "SKIPPED" in out
    assert json.loads(s.read_text())["permissions"]["allow"] == "oops"


def test_a_settings_file_that_is_not_an_object_is_refused(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text('["a", "list"]')
    out = run_grant(s)
    assert "SKIPPED" in out
    assert json.loads(s.read_text()) == ["a", "list"]


# ── the script still runs ──


def test_bootstrap_still_parses():
    """The first cut of this block nested a here-document inside `$( )`, which
    bash mis-parses: it warned `unterminated here-document` and leaked a stray
    `)` into the log."""
    r = subprocess.run(["bash", "-n", str(BOOTSTRAP)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "unterminated" not in r.stderr


def test_no_command_substitution_closes_on_the_heredoc_opener_line():
    """The precise defect, not the family it belongs to.

    `X="$(python3 - <<'PY' 2>/dev/null` followed by the body, `PY`, then `)"`
    on its own line is FINE — the connector probe has used exactly that shape
    for months and returns its tool count without a murmur.

    What broke was closing the substitution on the SAME line as the opener:

        X="$(... python3 - <<'PY' 2>/dev/null || echo fallback)
        <body>
        PY

    The `)` ends the substitution before the here-document body is reached, so
    bash warns `unterminated here-document` and leaks a stray `)` into the
    output. An earlier version of this test banned every here-doc inside `$( )`
    and would have failed the working code.
    """
    offenders = []
    for n, line in enumerate(BOOTSTRAP.read_text().splitlines(), 1):
        if "<<'PY'" not in line:
            continue
        after = line.split("<<'PY'", 1)[1]
        if ")" in after and line.count("$(") >= 1:
            offenders.append(f"line {n}: {line.strip()[:90]}")
    assert not offenders, (
        "command substitution closed on the here-doc opener line:\n  "
        + "\n  ".join(offenders))

# ── the connector was never the only server that prompts ─────────────────
#
# Measured 2026-08-24 on a provisioned container: user settings carried
# exactly one rule, `mcp__plugin_dma-insights_connector__*`, while the
# routines are required to read the world through Clay, Exa, Tavily,
# Vibe-Prospecting and Indeed. Every one of those is a separate MCP server
# with its own permission rule, so the first enrichment call in an unattended
# firing stops on a prompt nobody can answer — the same way the connector did
# before it was granted, and with the same result: the slot burns and nothing
# is produced. The set is DERIVED from the plugin tree so that adding a
# connector to an agent's allow-list grants it, rather than requiring someone
# to remember this file.

CONNECTORS_DOC = HERE.parent.parent / "docs" / "CONNECTORS.md"


def derived_grants() -> list:
    """The grant list the REAL script computes, run as the script computes it."""
    text = BOOTSTRAP.read_text(encoding="utf-8")
    start = text.index('GRANTS="$(')
    end = text.index('\n)"', start) + len('\n)"')
    snippet = text[start:end] + '\nprintf "%s\\n" $GRANTS\n'
    r = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True,
                       env={"REPO_DIR": str(HERE.parent.parent.parent.parent),
                            "PATH": "/usr/bin:/bin:/usr/local/bin"})
    assert r.returncode == 0, r.stderr
    return [l for l in r.stdout.split() if l]


def _servers(grants) -> set:
    return {g[len("mcp__"):g.rindex("__")] for g in grants}


def test_every_enrichment_connector_the_docs_require_is_granted():
    """CONNECTORS.md is the authority on which connectors the routines need;
    a grant list that does not cover it is a firing that stops on a prompt.

    Coverage is per SERVER, not per wildcard: a server the hook classifies is
    granted by exact read tool name instead, which is a narrower grant and a
    better one."""
    grants = derived_grants()
    required = ["Clay", "Exa", "Tavily", "Vibe_Prospecting", "Indeed"]
    missing = [n for n in required if n not in _servers(grants)]
    assert not missing, (
        f"CONNECTORS.md names these as the enrichment set and they are not "
        f"granted: {missing}. An unattended firing stops on the first call "
        f"to one of them.")


def test_no_classified_server_is_granted_by_wildcard():
    """The defect this replaced. `mcp__<Server>__*` approves the writes too,
    settings win without the hook being consulted, and the hook's read/write
    split is overruled silently. It was already true of Google Drive —
    `trash_file` and `share_file` granted by a wildcard the hook refuses —
    and naming ONE Slack tool in a design document was about to extend it to
    `slack_send_message`, because this list is read out of the tree and a doc
    is part of the tree."""
    import sys as _sys
    _sys.path.insert(0, str(HERE.parent / "hooks"))
    import autoapprove_connector as _aac

    bad = [g for g in derived_grants()
           if g.endswith("__*")
           and g[len("mcp__"):g.rindex("__")] in _aac.SERVER_SURFACES]
    assert not bad, f"wildcard overrules the hook's own read/write split: {bad}"


def test_every_granted_tool_is_one_the_hook_would_also_approve():
    """Settings and hook are two answers to one question, and the moment they
    differ the broader one wins without anybody being told."""
    import sys as _sys
    _sys.path.insert(0, str(HERE.parent / "hooks"))
    import autoapprove_connector as _aac

    # Compared through the hook's OWN canonical form: a grant written for the
    # `mcp__claude_ai_<Server>__` spelling (the one Claude Code gives a
    # connector it fetches itself) is the same decision as the delivered
    # spelling, and the hook reads it that way at call time.
    disagree = [g for g in derived_grants()
                if not g.endswith("__*")
                and _aac._canonical(g) not in _aac.QUALIFIED_TOOLS
                and not g.startswith(_aac.PREFIX)]
    assert not disagree, (
        f"granted in user settings and NOT on the hook's read allowlist: "
        f"{disagree}")


def test_the_connector_itself_is_always_granted():
    assert GRANT in derived_grants()


def test_no_rule_is_written_with_the_hyphen_spelling_the_docs_use():
    """The Routine record and the docs say Vibe-Prospecting, Google-Drive,
    PDF-Viewer; the TOOL names carry underscores. A rule written the way the
    docs read matches nothing, and matches nothing SILENTLY."""
    bad = [g for g in derived_grants()
           if "-" in g.split("__")[1] and not g.startswith("mcp__plugin_")]
    assert not bad, f"hyphenated server segments match no tool: {bad}"


def test_the_server_segment_is_never_a_glob():
    """`mcp__*` is skipped by the permission engine with a warning and
    approves nothing — it looks like a grant and is none."""
    for g in derived_grants():
        server = g[len("mcp__"):g.rindex("__")]
        assert "*" not in server, f"glob in the server segment: {g}"


def test_the_set_is_derived_rather_than_a_typed_list():
    """If someone replaces the derivation with a literal list, the connectors
    stop tracking the agents' allow-lists and drift silently. Pinned by
    checking that a server named ONLY in an agent file still comes out."""
    grants = derived_grants()
    assert "mcp__Exa__*" in grants, (
        "Exa appears only in agent allow-lists — its presence is the "
        "evidence that the list is read out of the tree, not typed. (Quartr "
        "was this witness until 2026-08-30; it is now granted by exact read "
        "name because the hook classifies it, so it can no longer show that "
        "an UNCLASSIFIED server is picked up from the tree.)")


# ── self-healing: a new session must LOAD the current hooks (owner 2026-09-01) ──

def test_bootstrap_self_heals_the_install_unconditionally():
    """A session must LOAD the current hooks, not a snapshot's stale copy.
    bootstrap runs plugin_version.py --heal — which uninstalls and reinstalls a
    DIVERGED tree (same version, different content: exactly how a stale
    auto-approve hook survives) — and it is not gated behind a version-string
    match. Favouring self-healing is this line staying present and ungated."""
    code = code_lines()
    assert "plugin_version.py" in code and "--heal" in code, (
        "bootstrap no longer self-heals the install; a new session can bind a "
        "stale auto-approve hook that prompts on tools this repo auto-approves")


# ── workspace trust: the lever dontAsk does not pull (owner 2026-09-01) ──────
#
# Traced to live state: user-scope grants + dontAsk cover the HEADLESS routines,
# but an interactive session also reads the repo's project .claude/settings.json,
# and an UNTRUSTED workspace makes Claude Code discard every rule in it —
# "Ignoring N permissions.allow entries ... this workspace has not been trusted".
# The setup script is the only place the flag can be set without a human clicking
# the trust dialog, so the block below must keep setting it for new sessions.

def trust_block() -> str:
    """The workspace-trust python, lifted out of the shell script itself."""
    src = BOOTSTRAP.read_text()
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", src, re.S)
    for b in blocks:
        if "hasTrustDialogAccepted" in b and "projects" in b:
            return b
    raise AssertionError(
        f"no workspace-trust python block found in {BOOTSTRAP.name} "
        f"({len(blocks)} PY blocks seen)")


def run_trust(state: Path, repo: str = "/home/user/Accelerate"):
    r = subprocess.run([sys.executable, "-c", trust_block()],
                       capture_output=True, text=True,
                       env={"CLAUDE_STATE": str(state), "TRUST_REPO": repo,
                            "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_fresh_state_file_is_trusted(tmp_path):
    """A brand-new container has no ~/.claude.json; the block creates it with
    the workspace trusted, so the project allow-list applies from the first run."""
    s = tmp_path / ".claude.json"
    out = run_trust(s)
    assert "trusted" in out
    proj = json.loads(s.read_text())["projects"]["/home/user/Accelerate"]
    assert proj["hasTrustDialogAccepted"] is True
    assert proj["hasCompletedProjectOnboarding"] is True


def test_trust_is_idempotent(tmp_path):
    """Second run on an already-trusted workspace changes nothing and says so —
    a scheduled container re-runs the setup script on every boot."""
    s = tmp_path / ".claude.json"
    run_trust(s)
    before = s.read_text()
    out = run_trust(s)
    assert "already trusted" in out
    assert s.read_text() == before


def test_trust_preserves_other_projects_and_top_level_keys(tmp_path):
    """The CLI's state file carries every project and much else; trusting one
    workspace must never drop another project or a top-level key."""
    s = tmp_path / ".claude.json"
    s.write_text(json.dumps({
        "numStartups": 42,
        "projects": {
            "/some/other/repo": {"hasTrustDialogAccepted": True, "keep": "me"},
            "/home/user/Accelerate": {"hasTrustDialogAccepted": False,
                                      "allowedTools": ["x"]},
        },
    }))
    run_trust(s)
    cfg = json.loads(s.read_text())
    assert cfg["numStartups"] == 42
    assert cfg["projects"]["/some/other/repo"] == {"hasTrustDialogAccepted": True,
                                                   "keep": "me"}
    acc = cfg["projects"]["/home/user/Accelerate"]
    assert acc["hasTrustDialogAccepted"] is True          # flipped
    assert acc["allowedTools"] == ["x"]                   # sibling key kept


def test_a_malformed_state_file_is_left_untouched(tmp_path):
    """~/.claude.json is the CLI's own; a broken one is refused, not overwritten."""
    s = tmp_path / ".claude.json"
    s.write_text("{ not json")
    out = run_trust(s)
    assert "SKIPPED" in out
    assert s.read_text() == "{ not json"


# ── the stress test the goal asks for: no recurrence across NEW sessions ─────

def _headless_ready(home: Path, repo: str = "/home/user/Accelerate") -> bool:
    """One provisioned container is headless-ready when BOTH levers are set:
    user-scope defaultMode=dontAsk (+ the connector granted) AND the workspace
    trusted so the project allow-list applies. Either alone leaves a gap the
    owner actually hit."""
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    state = json.loads((home / ".claude.json").read_text())
    perms = settings.get("permissions", {})
    proj = state.get("projects", {}).get(repo, {})
    return (perms.get("defaultMode") == "dontAsk"
            and GRANT in perms.get("allow", [])
            and proj.get("hasTrustDialogAccepted") is True)


def test_ten_fresh_sessions_all_end_headless_ready(tmp_path):
    """Resilience across ANY new run (the /goal). Ten independent fresh HOMEs,
    each provisioned exactly as the setup script provisions one, must EVERY time
    converge to the never-prompt posture — no ordering, no carried state, no
    lucky first run."""
    for i in range(10):
        home = tmp_path / f"session{i}"
        (home / ".claude").mkdir(parents=True)
        run_grant(home / ".claude" / "settings.json")
        run_trust(home / ".claude.json")
        assert _headless_ready(home), f"session {i} did not end headless-ready"


def test_a_partially_provisioned_session_is_healed_not_left_split(tmp_path):
    """The exact live defect: a container that already carried the grants but
    NOT dontAsk, and an untrusted workspace (measured 2026-09-01). Re-running the
    setup script must heal BOTH gaps rather than declaring victory on the half
    that was already there."""
    home = tmp_path / "partial"
    (home / ".claude").mkdir(parents=True)
    # grants present, mode missing — the state this container was found in
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"permissions": {"allow": [GRANT, "WebSearch", "WebFetch"]}}))
    # workspace explicitly untrusted — the other half of the live defect
    (home / ".claude.json").write_text(json.dumps(
        {"projects": {"/home/user/Accelerate": {"hasTrustDialogAccepted": False}}}))
    assert not _headless_ready(home)                      # starts split
    run_grant(home / ".claude" / "settings.json")
    run_trust(home / ".claude.json")
    assert _headless_ready(home)                          # ends whole
