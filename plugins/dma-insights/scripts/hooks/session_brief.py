#!/usr/bin/env python3
"""The routing brief — for every session start, every subagent, every compaction.

WHY THIS FILE CHANGED.

  AUD-0004  Claude Code delivers SessionStart hooks to TOP-LEVEL sessions only.
      Measured over the project's transcripts: the parent carried 4
      `SessionStart:startup` attachments; 3 of 3 subagent transcripts carried
      0. And the synthesis Routine orders the top session to "dispatch every
      routed stage DIRECTLY via the Agent tool", so the ENTIRE routed producer
      population — 30 producers, 3 checkers, the consolidator, the vetter —
      started without "route before you produce", without "read
      get_memory_digest first", without "only the surface-producer submits",
      and without the routing.md pointer. The harness offers `SubagentStart`
      with `additionalContexts`; hooks.json declared 3 event types and not
      that one.

  AUD-0054  the source filter admitted `startup` and `clear` only. The CLI's
      SessionStart enum is five values, so the brief was silent on `resume`,
      `compact` and `fork` — and the docstring's justification ("resumes and
      compaction continuations already carry the brief in context") was
      asserted, never tested. A synthesis firing that produces six pages WILL
      compact, and after it does, the routing rule is whatever the summariser
      chose to keep.

So: all five sources print, subagents get their own brief through
SubagentStart, and the compaction case gets the one thing it never had — a
destination to route to (`05-lifecycle/routing.md § After a compaction`).

Contract: reads the hook event as JSON on stdin, prints to stdout. No
network, no state, fails OPEN — a brief that cannot decide prints, because
failing closed costs the brief on exactly the session that needed it.
"""
import json
import sys

ROUTING = "skills/dma-surface-production/05-lifecycle/routing.md"

CORE = (
    "dma-insights: route before you produce. Entry fork first — an entity + "
    "evidence mode with NO package yet is a RESEARCH engagement "
    "(research-conductor produces the package; it is not Drive ingestion); "
    "a finished '<Client> - DMA' folder goes to package-vetter, then "
    "production; a repair naming a surface or page routes by the table. In "
    "production: one surface -> that page's per-surface producer, then "
    "finding-challenger, then page-consolidator; only the surface-producer "
    "submits or promotes. Read get_memory_digest before authoring anything, "
    "and end every production with the qa-overseer so the findings memory "
    f"learns. Routing table: {ROUTING}"
)

#: The research children work a different substrate (the scoring workbook,
#: not the connector), so the production brief is wrong for them — telling a
#: category researcher "produce only the surface you were dispatched for"
#: is exactly the kind of half-applicable rule a compacted child obeys into
#: a mess. They get their own.
RESEARCH_BRIEF = (
    "dma-insights research tier: the workbook is the substrate — what you do "
    "not write there did not happen. First command (and after ANY "
    "interruption or compaction): engine.cli orient --run <R> --root <ROOT> "
    "--category <YOURS>; obey its do_first literally, then engine.memory "
    "status for notes your context no longer holds. Protocol: "
    "skills/dma-research/references/RESEARCH-PROTOCOL.md — the five volleys "
    "in order (works, fails, value, contradicts, corroborates; every one "
    "answered or NOT_RUN with reason), the memory notebook, the refusals. "
    "Work only your own category; never score, never submit, never promote."
)

#: What each start source needs ON TOP of the core rule. `resume`, `compact`
#: and `fork` used to print nothing at all.
BY_SOURCE = {
    "startup": "",
    "clear": "",
    "resume": (" This session RESUMED: re-read the routing table before "
               "acting — a resumed turn carries whatever context survived, "
               "not necessarily this rule."),
    "compact": (" This session was COMPACTED: the routing rule, the memory "
                f"rule and the submit boundary are NOT guaranteed to have "
                f"survived the summary. Re-read {ROUTING} § After a "
                f"compaction before your next tool call."),
    "fork": (" This session is a FORK: it inherits a transcript it did not "
             "write. Confirm which run and which surface you own before "
             "producing anything."),
}

SUBAGENT = (
    " You are a SUBAGENT. You do not inherit the parent's brief — this is it. "
    "Produce only the surface you were dispatched for; do not re-produce a "
    "page to repair a field, and do not submit or promote: that boundary "
    "belongs to the surface-producer alone."
)


def brief(event: dict) -> str:
    hook = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    agent = str(event.get("agent_type") or event.get("agentType") or "")
    if hook == "SubagentStart" or agent:
        if "research-" in agent:
            return RESEARCH_BRIEF
        return CORE + SUBAGENT
    source = str(event.get("source") or "startup")
    return CORE + BY_SOURCE.get(source, BY_SOURCE["resume"])


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            event = {}
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        event = {}
    text = brief(event)
    # SubagentStart takes `additionalContexts`; SessionStart takes plain
    # stdout. Emitting the JSON form for a subagent is what actually puts the
    # brief in the child's context — printing to stdout there would be
    # swallowed, which is the AUD-0004 failure wearing a fix.
    if event.get("hook_event_name") == "SubagentStart" or \
            event.get("hookEventName") == "SubagentStart":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContexts": [text],
            }
        }))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
