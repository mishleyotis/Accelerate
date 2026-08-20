#!/usr/bin/env python3
"""Dispatch one plugin agent from a session that has no agent-launch tool.

Trigger-fired sessions run under the subagent harness: they carry Bash but
no Agent tool, so the routed pipeline (produce -> challenge -> consolidate,
05-lifecycle/routing.md) cannot fan out in-process. Measured 2026-08-20 on
the first live synthesis firing, which correctly refused to write six pages
inline rather than skip the challenge stage.

This script is the sanctioned fallback: it runs the named agent as a
HEADLESS claude CLI session (`claude -p --agent dma-insights:<name>`), which
applies the agent's own front matter — model tier, effort, skills, tool
bans — exactly as the Agent tool would. The child session reaches the DMA
connector natively (static /mcp + header token), so evidence reads, memory
digests and gate checks all work.

What the child does NOT have: the claude.ai enrichment connectors (Clay,
Exa, Tavily, Vibe-Prospecting, Indeed) — those are attached to the Routine
and exist only in the top session. The DISPATCH-MODE preamble (prepended to
every prompt) tells the agent to emit `search_requests` instead of running
or fabricating external searches; the orchestrating session executes them
through its connectors, registers the evidence, and re-invokes.

Usage:
  agent_run.py --agent finding-challenger --prompt-file /tmp/stage.md
  agent_run.py --agent package-vetter < prompt.md
  agent_run.py --list          # the roster this script will accept

Exit code is the child's. Output is the child's stdout, verbatim.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS_DIR = HERE.parent / "agents"
PLUGIN_PREFIX = "dma-insights"
DEFAULT_TIMEOUT = 2400

PREAMBLE = """DISPATCH MODE — you are running as a headless session, not an
in-process subagent. Two things differ from your usual footing:
1. You carry the DMA Insights connector tools but NOT the claude.ai
   enrichment connectors (Clay, Exa, Tavily, Vibe-Prospecting, Indeed).
   Where your rulebook requires an external search you cannot run, do NOT
   fabricate and do NOT skip silently: add the exact query, its falsifier
   pairing and the facet it serves to a `search_requests` array in your
   final output. The orchestrating session runs them through the real
   connectors, registers what they return, and re-invokes you with the
   evidence ids.
2. Your final output is read by the orchestrating session, not a human —
   return the JSON or report your role defines, nothing else.

--- TASK ---
"""


def roster() -> dict:
    """name -> path, from the agents tree's front-matter name fields."""
    out = {}
    for p in sorted(AGENTS_DIR.rglob("*.md")):
        if p.name == "README.md":
            continue
        head = p.read_text(encoding="utf-8")[:2000]
        m = re.search(r"^name:\s*(\S+)\s*$", head, re.M)
        if m:
            out[m.group(1)] = p
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", help="agent name from the plugin roster")
    ap.add_argument("--prompt-file", help="file holding the stage prompt; "
                                          "stdin when omitted")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--no-preamble", action="store_true",
                    help="skip the dispatch-mode preamble (rarely right)")
    ap.add_argument("--list", action="store_true",
                    help="print the accepted roster and exit")
    a = ap.parse_args(argv)

    names = roster()
    if a.list:
        for n in sorted(names):
            print(n)
        return 0
    if not a.agent:
        ap.error("--agent is required (or --list)")
    name = a.agent.removeprefix(f"{PLUGIN_PREFIX}:")
    if name not in names:
        close = [n for n in names if name in n or n in name]
        raise SystemExit(
            f"unknown agent {a.agent!r} — a guessed agent name is a route "
            f"to nothing (routing.md). "
            + (f"Did you mean: {', '.join(close)}?" if close
               else "agent_run.py --list prints the roster."))

    if a.prompt_file:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        raise SystemExit("empty prompt — a stage with no task is a no-op")
    if not a.no_preamble:
        prompt = PREAMBLE + prompt

    repo_root = HERE.parents[2]
    cmd = ["claude", "-p", "--agent", f"{PLUGIN_PREFIX}:{name}",
           "--permission-mode", "dontAsk", prompt]
    try:
        r = subprocess.run(cmd, cwd=repo_root, timeout=a.timeout,
                           env={**os.environ})
    except subprocess.TimeoutExpired:
        print(f"DISPATCH TIMEOUT: {name} exceeded {a.timeout}s — treat as a "
              f"failed stage, never as an empty verdict", file=sys.stderr)
        return 124
    except FileNotFoundError:
        print("DISPATCH FAILED: the claude CLI is not on PATH in this "
              "container", file=sys.stderr)
        return 127
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
