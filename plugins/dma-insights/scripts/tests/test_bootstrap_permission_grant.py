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
    assert json.loads(s.read_text())["permissions"]["allow"] == [GRANT]


def test_running_twice_does_not_duplicate_the_rule(tmp_path):
    s = tmp_path / "settings.json"
    run_grant(s)
    out = run_grant(s)
    assert "already granted" in out
    assert json.loads(s.read_text())["permissions"]["allow"] == [GRANT]


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
    assert cfg["permissions"]["allow"] == [GRANT]


def test_an_unrelated_allow_rule_is_kept(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"permissions": {"allow": ["Bash(git status)"],
                                             "deny": ["Read(//root/.dma/sa.json)"]}}))
    run_grant(s)
    cfg = json.loads(s.read_text())
    assert cfg["permissions"]["allow"] == ["Bash(git status)", GRANT]
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
