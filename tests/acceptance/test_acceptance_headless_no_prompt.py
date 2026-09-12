"""Acceptance: a scheduled routine — or a plain Claude Code session — never
stops on a permission prompt, proven by running the REAL autoapprove hook
against every MCP tool the plugin's own agents and skills name.

Measured 2026-09-05: `scripts/tests/test_autoapprove_connector.py` checks a
REIMPLEMENTATION of the allow rule (`_is_allowed`), never the hook itself. That
is exactly how the two Clay data-point writes were named by 36 agents, required
by the technographic scan and the enrichment rulebooks, and STILL prompted a
plain session — headless-safe only through a `bootstrap_session.sh` wildcard the
plugin cannot guarantee. This test invokes the hook's own `main()` over a
synthesized PreToolUse event, so a tool that would prompt fails HERE rather than
in a live firing nobody is watching.
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "autoapprove_connector.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aac = _load(HOOK, "aac_headless")


def _decide(tool: str, args: dict | None = None):
    """Run the hook exactly as Claude Code invokes it — a PreToolUse event on
    stdin, a decision (or silence) on stdout. Returns the permissionDecision
    string, or None when the hook stays silent (silence == a PROMPT)."""
    event = json.dumps({"tool_name": tool, "tool_input": args or {}})
    buf, old = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(event)
    try:
        with redirect_stdout(buf):
            aac.main()
    finally:
        sys.stdin = old
    out = buf.getvalue().strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None


_MCP = re.compile(r"\bmcp__[A-Za-z0-9_\-]+__[A-Za-z0-9_\-]+")

#: A named tool may legitimately NOT be auto-approved only for a reason the hook
#: itself records: a WITHHELD suffix (a write the workflow does not require —
#: run_subroutine, export-to-csv, the Quartr writes), Cowork's `bash` (decided
#: by autoapprove_builtins.py command-by-command), an argument-scoped
#: CONDITIONAL tool (slack_send_message into #deal-desk), or the GUARDED
#: connector pair (submit/promote), which carry their own precheck hooks.
_PROMPT_ON_PURPOSE = set(aac.WITHHELD_SUFFIXES) | {"bash"}


def _named_tools() -> dict[str, str]:
    found: dict[str, str] = {}
    for f in PLUGIN.rglob("*.md"):
        for m in _MCP.finditer(f.read_text(errors="ignore")):
            found.setdefault(m.group(0), str(f.relative_to(PLUGIN)))
    return found


def test_every_named_mcp_tool_is_allowed_by_the_real_hook():
    named = _named_tools()
    assert named, "found no MCP tool names to check — the scan is broken"
    prompting = {}
    for tool in sorted(named):
        suffix = tool.rsplit("__", 1)[1]
        if suffix in _PROMPT_ON_PURPOSE or tool in aac.CONDITIONAL_TOOLS:
            continue
        if tool in aac.GUARDED:
            assert _decide(tool) is None, (
                f"{tool} must be left to its precheck hook, not decided here")
            continue
        if _decide(tool) != "allow":
            prompting[tool] = named[tool]
    assert not prompting, (
        "these MCP tools are named by the plugin's own agents or skills and the "
        "REAL autoapprove hook does not allow them, so a scheduled firing (or a "
        "plain session) stops on a prompt nobody can answer. Add each to "
        "ENRICHMENT_TOOLS / SANCTIONED_WORKSPACE_WRITES / QUALIFIED_TOOLS, or "
        f"record why it must prompt: {prompting}")


def test_the_two_clay_writes_no_longer_prompt():
    """The exact 2026-09-05 gap, proven closed by the hook itself."""
    for t in ("mcp__Clay__add-company-data-points",
              "mcp__Clay__add-contact-data-points"):
        assert _decide(t) == "allow", t


def test_the_web_reads_are_allowed_by_the_real_hook():
    for t in ("WebSearch", "WebFetch"):
        assert _decide(t) == "allow", t


def test_a_user_authored_subroutine_still_prompts():
    """A workspace subroutine can do anything, so it keeps its prompt — and it
    is named by no plugin body, so the inventory above never reaches it."""
    for t in ("mcp__Clay__run_subroutine", "mcp__Clay__run_subroutine_direct"):
        assert _decide(t) is None, t
