#!/usr/bin/env python3
"""SessionStart hook — the thirty-word brief that saves a wrong first hour.

No network, no state: it prints the routing rule and the memory rule so a
fresh session neither re-produces a whole run to fix one card nor produces
anything before reading what past runs already learned.

Prints only on a fresh session (source startup) or an explicit /clear:
resumes and compaction continuations already carry the brief in context,
and re-printing it on every continuation is noise. No event on stdin
prints anyway — failing open costs thirty words, failing closed costs the
brief on the one session that needed it.
"""
import json
import sys


def _should_print() -> bool:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return True
    return str(event.get("source") or "startup") in ("startup", "clear")


if __name__ == "__main__":
    if _should_print():
        print(
            "dma-insights: route before you produce. One surface -> that "
            "page's surface producer, then finding-challenger, then "
            "page-consolidator; only the surface-producer submits or "
            "promotes. Read get_memory_digest before authoring anything, "
            "and end every production with the qa-overseer so the findings "
            "memory learns. Routing table: "
            "skills/dma-surface-production/05-lifecycle/routing.md"
        )
