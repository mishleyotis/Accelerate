#!/usr/bin/env python3
"""PreToolUse guard on Skill: a retired skill is not loaded, it is redirected.

WHY (measured 28-09-2026, QA audit F-A05-001 / F-B03-002, regression seed
10). Three retired skills — dma-p1, dma-orchestrator, dma-core — were still
installed at account level with live "ALWAYS use" trigger descriptions,
beside four account copies of this plugin's own skills that had drifted
from it (17 categories, ~836 subcaps, M1-M5 in one of them). A fresh
Sonnet router given only the installed descriptions routed 6 of 64
utterances to the retired three ("P1 research", "research handoff",
"CCG/RSG", "SIB assembly", "ESG research", "DMA engagement … hybrid") and
scored 84.4% top-1 against a 95% bar. A wrong skill loading means every
later gate runs against the wrong contract, silently.

The plugin cannot delete an account-level skill; the owner does that on
claude.ai. This hook is the belt-and-braces: the Skill tool call is denied
with the current owner named, so a session that reaches for a retired
skill on a legacy phrase lands on dma-insights:dma-research instead.

Fail-open on anything unparsable, like every guard here: a hook that
bricks the Skill tool when the harness changes the payload shape costs
more than a misroute it was never going to catch.
"""
import json
import sys

#: retired skill -> the current owner of everything it covered.
RETIRED = {
    "dma-p1": "dma-insights:dma-research",
    "dma-orchestrator": "dma-insights:dma-research",
    "dma-core": "dma-insights:dma-research",
}

#: Account-level copies of this plugin's own skills. The plugin copy is the
#: one the routing table, the engine and the gates are written against; the
#: account copy has drifted before (contract v3 vs v7, 17 vs 16 categories)
#: and will again.
DUPLICATE_PREFIX = "anthropic-skills:"
DUPLICATES = ("dma-assessment", "dma-research", "dma-governance",
              "dma-first-call-deck")

REASON_RETIRED = (
    "dma-insights: `{asked}` is RETIRED and is not loaded. Everything it "
    "covered — P1 / Pillar 1 research, research handoff production, CCG/RSG "
    "inspection, SIB assembly, ESG research, public-only / internal-only / "
    "hybrid DMA research engagements — belongs to `{owner}` on Capability "
    "Taxonomy v7.0. Load that skill instead. (The retired copy still "
    "advertises its triggers because it lives in the claude.ai account's "
    "synced skills, which this plugin cannot remove; the owner deletes it "
    "there.)"
)
REASON_DUPLICATE = (
    "dma-insights: `{asked}` is the account-level copy of a skill this "
    "plugin ships; the two have drifted before (a different category count, "
    "a fifth band word) and the routing table, engine and gates are written "
    "against the plugin copy. Load `{owner}` instead."
)


def _asked(payload: dict) -> str:
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return ""
    for key in ("skill", "name", "skill_name", "command"):
        v = ti.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lstrip("/")
    return ""


def decide(payload: dict) -> str:
    """The reason to deny, or "" to allow."""
    if str(payload.get("tool_name") or "") != "Skill":
        return ""
    asked = _asked(payload)
    if not asked:
        return ""
    bare = asked.split(":")[-1].strip()
    prefix = asked[: -len(bare)] if asked.endswith(bare) else ""
    if bare in RETIRED:
        return REASON_RETIRED.format(asked=asked, owner=RETIRED[bare])
    if prefix == DUPLICATE_PREFIX and bare in DUPLICATES:
        return REASON_DUPLICATE.format(asked=asked, owner=f"dma-insights:{bare}")
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except Exception:                                           # noqa: BLE001
        return 0                       # fail OPEN, on purpose
    try:
        why = decide(payload)
    except Exception:                                           # noqa: BLE001
        return 0
    if not why:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": why,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
