#!/usr/bin/env python3
"""Which MCP tools would prompt — measured by running the real hook.

    python3 scripts/audit_autoapprove.py [--roster FILE] [--json] [--strict]

WHY THIS EXISTS. Two questions look the same and are not:

  1. does every MCP tool THIS PLUGIN NAMES get through headless?
  2. does every MCP tool A SESSION ACTUALLY ATTACHES get through?

`tests/test_autoapprove_connector.py` has always answered (1), by scanning the
plugin's own markdown. It cannot answer (2), because the plugin's markdown does
not mention Slack, Salesforce, Google Admin, Auctor or GitHub — and those are
most of what a person is actually clicking through. Measured 2026-08-30 by
feeding the hook the 86 tools one session carried: **16 approved, 70
prompting.** Every one of the 70 had simply never been looked at.

WHAT IT DOES. It runs `hooks/autoapprove_connector.py` as a subprocess, once
per tool, with the real PreToolUse event shape — no re-implementation of the
matching rules, because a checker that re-derives the rule it is checking
agrees with itself by construction. Then it classifies each prompting tool:

    WITHHELD     on the record in SERVER_SURFACES[...]["withheld"] — it
                 writes, publishes, deletes, spends, or runs someone else's
                 code, and prompting is the decision, not an oversight
    UNCLASSIFIED on a server the hook already knows, in neither set. This is
                 the finding: a tool nobody has ruled on, prompting forever
    UNKNOWN      on a server the hook has never seen at all

`--strict` exits non-zero on UNCLASSIFIED only. WITHHELD is correct and
UNKNOWN is a connector nobody has classified yet — reporting those as failures
would make the check cry wolf, and a check people stop running is worse than
no check.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hooks", "autoapprove_connector.py")
ROSTER = os.path.join(HERE, "tests", "mcp_roster.txt")

sys.path.insert(0, os.path.join(HERE, "hooks"))
import autoapprove_connector as AAC                          # noqa: E402

ALLOWED = "ALLOWED"
WITHHELD = "WITHHELD"
GUARDED = "GUARDED"
UNCLASSIFIED = "UNCLASSIFIED"
UNKNOWN = "UNKNOWN_SERVER"


def read_roster(path=ROSTER) -> list[str]:
    with open(path) as fh:
        return [ln.strip() for ln in fh
                if ln.strip() and not ln.startswith("#")]


def server_of(tool: str) -> str:
    """`mcp__<server>__<tool>` — the middle segment. Returns "" for a name
    that is not shaped like an MCP tool at all."""
    parts = tool.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else ""


def ask_the_hook(tool: str) -> bool:
    """Run the REAL hook. Not a re-implementation: a checker that re-derives
    the rule it checks agrees with itself and proves nothing."""
    r = subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"tool_name": tool,
                                         "hook_event_name": "PreToolUse"}),
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not r.stdout.strip():
        return False
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    return (out.get("hookSpecificOutput", {}).get("permissionDecision")
            == "allow")


def suffix_of(tool: str) -> str:
    return tool.rsplit("__", 1)[1] if "__" in tool else tool


def classify(tool: str, allowed: bool) -> str:
    if allowed:
        return ALLOWED
    # The connector's own two tools that stand aside for their own PreToolUse
    # guards. They prompt from HERE by design — precheck_submit.py and
    # precheck_promote.py emit the decision — so counting them as unruled-on
    # would report the deliberate arrangement as the defect.
    if tool in AAC.GUARDED:
        return GUARDED
    if tool in AAC.WITHHELD_TOOLS or suffix_of(tool) in AAC.WITHHELD_SUFFIXES:
        return WITHHELD
    if server_of(tool) in AAC.SERVER_SURFACES:
        return UNCLASSIFIED
    return UNKNOWN


def audit(roster=None) -> dict:
    tools = roster if roster is not None else read_roster()
    rows = [{"tool": t, "verdict": classify(t, ask_the_hook(t))}
            for t in tools]
    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r["tool"])
    return {
        "total": len(rows), "rows": rows,
        "allowed": by.get(ALLOWED, []),
        "withheld": by.get(WITHHELD, []),
        "guarded": by.get(GUARDED, []),
        "unclassified": by.get(UNCLASSIFIED, []),
        "unknown_server": by.get(UNKNOWN, []),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--roster", default=ROSTER,
                    help=f"one MCP tool name per line; # comments ignored "
                         f"(default: {os.path.relpath(ROSTER, os.getcwd())})")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when a tool on a classified server is in "
                         "neither its read nor its withheld set")
    a = ap.parse_args(argv)

    out = audit(read_roster(a.roster))
    rc = 1 if (a.strict and out["unclassified"]) else 0
    if a.json:
        print(json.dumps(out, indent=2))
        return rc

    print(f"{len(out['allowed'])}/{out['total']} MCP tool(s) auto-approved · "
          f"{len(out['withheld'])} withheld on the record · "
          f"{len(out['guarded'])} guarded by their own precheck · "
          f"{len(out['unclassified'])} UNCLASSIFIED · "
          f"{len(out['unknown_server'])} on a server nobody has "
          f"classified\n")
    if out["unclassified"]:
        print("UNCLASSIFIED — on a server this hook already knows, in neither "
              "its read nor its withheld set. Each of these prompts on every "
              "call and nobody ever decided that:")
        for t in out["unclassified"]:
            print(f"  ! {t}")
        print()
    if out["unknown_server"]:
        servers = sorted({server_of(t) for t in out["unknown_server"]})
        print(f"servers with no entry in SERVER_SURFACES: {servers}\n"
              f"  every tool on them prompts. Classify the server to fix "
              f"that; leaving it is a choice, not an accident.\n")
    print(f"withheld deliberately: {len(out['withheld'])} tool(s) that write, "
          f"publish, delete, spend or run code somebody else authored.")
    if not out["unclassified"]:
        print("\nNo tool on a classified server is unruled on.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
