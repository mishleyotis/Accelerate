#!/usr/bin/env python3
"""PreToolUse hook on promote_run — the advisory exclusion mirror.

Advisory and FAIL-OPEN by design: the authoritative exclusion boundary is
server code (the connector's gates at submit, the API's customer serve
allowlist at read), and a hook that blocked promotes on a client-side guess
would be a second authority that drifts. This prints one reminder of what
promotion is about to do and exits 0 on every path — including unreadable
input, per the same posture as precheck_submit's fail-open branch.

It exists because constraint [E] names it: the only place a client-side
exclusion mirror can run is a tool-event hook, and promote_run is the tool
event where the working set becomes the served set.
"""
import json
import sys


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    run_id = (event.get("tool_input") or {}).get("run_id") or "this run"
    advisory = (
        f"dma-insights: promoting {run_id} republishes ALL SIX pages "
        "atomically and re-runs today's format gates over every retained "
        "payload — pre-gate pages pay their accumulated debt now, not "
        "later. The customer audience serves only allowlisted keys "
        "(apps/api customer_allowlist.json); internal-shaped content "
        "(probe ladders, tier codes, cap vocabulary) is dropped at the "
        "serve boundary even if promotion carries it. If the intent is a "
        "one-page fix, submit that page and re-promote rather than "
        "re-synthesising six."
    )
    # THE ADVISORY IS CARRIED, NOT DROPPED. This used to be a bare print, which
    # is fine for a hook that only informs — but this hook now also owns the
    # permission decision for promote_run (autoapprove_connector.py stands
    # aside so exactly one hook decides it), and stdout has to be the decision
    # JSON. Putting the advisory in permissionDecisionReason keeps every word
    # of it where the decision is read, instead of trading the warning for the
    # approval.
    #
    # Without the approval a scheduled session stops here on a prompt no human
    # will ever see — measured 2026-08-21, and the reason no run has ever been
    # promoted by the routine.
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": advisory,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
