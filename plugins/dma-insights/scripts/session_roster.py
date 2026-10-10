#!/usr/bin/env python3
"""The MCP tools THIS session holds, read from its own transcript.

WHY THIS EXISTS (Interac, 2026-10-10 — and every DMA session before it).
The doctor's `connector contract` row failed at the start of every run with
"UNVERIFIED: no baseline", because the baseline had to be written by the
model typing every tool name it holds into `connector_contract.py baseline`,
and that step needs a run root that does not exist yet when the doctor runs.
The Interac session then typed 334 names by hand — abbreviating whole
families on its first attempt — to produce a file a script could have read.

MEM-0112 said no subprocess can enumerate a session's bound MCP tools. That
was true of the process table and of `claude plugin list`; it is not true of
the transcript. Claude Code appends a `deferred_tools_delta` attachment to
the session's JSONL whenever the deferred tool roster changes — every MCP
tool by name, with `addedNames` / `readdedNames` / `removedNames` — and the
session id is in every Bash child's environment (CLAUDE_CODE_SESSION_ID).
Folding those deltas in order gives the roster as it stands NOW, including a
connector that dropped mid-session, which a typed list never shows.

WHAT IT CANNOT SEE, stated rather than guessed:
  * built-in tools that are not deferred (Bash, Agent, Workflow...) are not
    in the delta. `workflow_tool` is therefore only reported when the
    transcript PROVES it: the RESULT of a `Workflow` call — answered (held)
    or refused "No such tool available: Workflow" (lost). Otherwise it is None — unknown,
    which every consumer already reads as "not proven absent".
  * a session with tool search off lists its tools in the prompt, not the
    transcript: `found` is False and callers fall back to the typed list.

    session_roster.py [--session ID] [--transcript PATH] [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

_WF_LOST = "No such tool available: Workflow"


def _config_dirs() -> list[Path]:
    out = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        out.append(Path(os.environ["CLAUDE_CONFIG_DIR"]))
    out.append(Path.home() / ".claude")
    return out


def transcript_path(session_id: str | None = None) -> Path | None:
    """This session's transcript, or None. Never another session's: the file
    is located by the session id itself, not by recency."""
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid or "/" in sid or ".." in sid:
        return None
    for base in _config_dirs():
        hits = sorted(glob.glob(str(base / "projects" / "*" / f"{sid}.jsonl")))
        if hits:
            return Path(hits[0])
    return None


def read(path: Path | str) -> dict:
    """Fold the transcript's roster deltas in order. Main thread only:
    a sidechain (subagent) line describes another agent's tools."""
    held: set[str] = set()
    found = False
    used: set[str] = set()
    calls: dict[str, str] = {}            # tool_use id -> tool name
    workflow = None
    failed_servers = 0
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return {"found": False, "tools": [], "mcp_tools": [],
                "workflow_tool": None, "transcript": str(path),
                "reason": "transcript unreadable"}
    with fh:
        for line in fh:
            if "deferred_tools_delta" not in line and "tool_use" not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain"):
                continue
            a = o.get("attachment") or {}
            if a.get("type") == "deferred_tools_delta":
                found = True
                for n in (a.get("addedNames") or []) + (a.get("readdedNames") or []):
                    held.add(n)
                for n in a.get("removedNames") or []:
                    held.discard(n)
                if isinstance(a.get("failedMcpServers"), (int, list)):
                    f = a["failedMcpServers"]
                    failed_servers = len(f) if isinstance(f, list) else f
                continue
            msg = o.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name"):
                    calls[c.get("id") or ""] = c["name"]
                elif (c.get("type") == "tool_result"
                      and calls.get(c.get("tool_use_id") or "") == "Workflow"):
                    # ONLY the answer to a Workflow call counts. A file that
                    # QUOTES the refusal (this module's docstring, the
                    # contract's comment) printed by Bash is not evidence —
                    # measured: matching the phrase anywhere read a session
                    # holding Workflow as one that had lost it.
                    body = c.get("content")
                    text = body if isinstance(body, str) else json.dumps(body)
                    workflow = not (c.get("is_error") and _WF_LOST in (text or ""))
                    if workflow:
                        used.add("Workflow")
                    continue
                if c.get("type") == "tool_result":
                    name = calls.get(c.get("tool_use_id") or "")
                    if name and not c.get("is_error"):
                        used.add(name)      # answered: the tool is bound
    tools = sorted(held | {u for u in used if u.startswith("mcp__")})
    return {"found": found, "tools": tools,
            "mcp_tools": [t for t in tools if t.startswith("mcp__")],
            "workflow_tool": workflow, "failed_mcp_servers": failed_servers,
            "transcript": str(path),
            "reason": ("" if found else
                       "the transcript carries no deferred_tools_delta "
                       "(tool search off, or not yet written)")}


def current(session_id: str | None = None) -> dict:
    """The roster of THIS session, or {"found": False, "reason": ...}.

    `DMA_SESSION_ROSTER=0` switches it off — for a test that must see a
    container with no measurable roster while it runs inside a session."""
    if os.environ.get("DMA_SESSION_ROSTER", "1") == "0":
        return {"found": False, "tools": [], "mcp_tools": [],
                "workflow_tool": None, "transcript": None,
                "session_id": None,
                "reason": "DMA_SESSION_ROSTER=0 (switched off)"}
    path = transcript_path(session_id)
    if path is None:
        return {"found": False, "tools": [], "mcp_tools": [],
                "workflow_tool": None, "transcript": None,
                "session_id": session_id or os.environ.get("CLAUDE_CODE_SESSION_ID"),
                "reason": ("no CLAUDE_CODE_SESSION_ID in the environment — "
                           "not inside a Claude Code session"
                           if not (session_id or os.environ.get(
                               "CLAUDE_CODE_SESSION_ID")) else
                           "this session's transcript was not found under "
                           "~/.claude/projects")}
    out = read(path)
    out["session_id"] = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", default=None)
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = read(a.transcript) if a.transcript else current(a.session)
    if a.json:
        print(json.dumps(out, indent=1))
    elif out["found"]:
        for t in out["tools"]:
            print(t)
    else:
        print(f"no roster: {out['reason']}", file=sys.stderr)
    return 0 if out["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
