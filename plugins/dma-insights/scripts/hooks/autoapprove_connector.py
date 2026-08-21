#!/usr/bin/env python3
"""PreToolUse on the connector — approve this plugin's own tools, nothing else.

WHY THIS EXISTS (measured 2026-08-21, and it is what had stopped every
scheduled firing of the synthesis routine).

A trigger-fired session bound the connector correctly and then stopped on:

    Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress

There is nobody in a scheduled container to answer that, and the owner has
confirmed the prompt is never surfaced to them either — it is not that the
approval was slow, it is that no human can ever see it. So the firing burns
its twelve-hour slot, stages nothing and records nothing. 178 clients sat
INGESTED behind this (MEM-0118).

Every earlier diagnosis reached for the binding defect (MEM-0112) because
from outside the two are indistinguishable: a session that CANNOT call a tool
and one that is NOT ALLOWED to both simply stop, with the plugin enabled and
the doctor green.

WHY A HOOK RATHER THAN A SETTINGS GRANT. A user-scope `permissions.allow`
entry also works, but only if something writes it BEFORE session start —
which means the environment setup script, wired by hand, per environment,
and silently absent the moment anyone stands up a new one. Project-scope
settings do not work at all: their permission rules are skipped in a
non-interactive session. A hook ships INSIDE the plugin, travels with it, and
needs no environment wiring, so a fresh environment is correct by default.
Both are in place; this is the one that cannot be forgotten.

SCOPE, deliberately narrow. This approves ONLY tools whose name begins with
this plugin's own connector prefix. It cannot approve Bash, a file write, a
web fetch, another MCP server, or anything else — a hook that auto-approved
broadly would be a far worse bug than the one it fixes, and it would be
invisible until it mattered.

It also STANDS ASIDE for the two tools that carry their own PreToolUse
guards. `submit_page_payload` and `promote_run` emit their own decision from
precheck_submit.py / precheck_promote.py, which can still refuse. Approving
them from here as well would put two hooks on one tool with opposite
opinions, and the resolution order is not something to bet a promote on.
"""
import json
import sys

PREFIX = "mcp__plugin_dma-insights_connector__"

# Tools whose own PreToolUse hook owns the decision. Listed here rather than
# excluded by the matcher regex, because a matcher that has to express "all of
# these except two" is a matcher nobody will read correctly later.
GUARDED = {
    PREFIX + "submit_page_payload",   # precheck_submit.py
    PREFIX + "promote_run",           # precheck_promote.py
}

REASON = (
    "dma-insights connector tool, auto-approved by the plugin's own hook: a "
    "scheduled session has nobody to answer a permission prompt. Writes still "
    "pass the connector's server-side validation, gate families and atomic "
    "promote; submit_page_payload and promote_run keep their own precheck "
    "hooks, which this hook does not touch."
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                        # noqa: BLE001
        # Say nothing rather than guess. No output means no decision, which
        # leaves the tool exactly as it would have been without this hook.
        return 0

    tool = event.get("tool_name")
    if not isinstance(tool, str):
        return 0
    # startswith on the full prefix — never a substring match, never a regex.
    # `mcp__plugin_dma-insights_connector__x` is ours; anything else is not,
    # including a server that merely contains this name inside a longer one.
    if not tool.startswith(PREFIX) or tool in GUARDED:
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": REASON,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
