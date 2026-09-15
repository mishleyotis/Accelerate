#!/usr/bin/env python3
"""PreToolUse on the whole-page fetchers: a research lane reads WINDOWS.

WHY (measured, and the largest single lever on the bill). A lane that wants a
50-500 character excerpt fetches the whole page to find it. The page then
sits in that lane's context and is re-read on every later turn: on the
measured six-cell lane 76% of the bill was cache reads — 24.45M cache-read
tokens, $4.89 of $6.45. One fetch is 5-40K tokens re-read every turn after
it; three 240-character windows are ~200 tokens, read once.

AND THE WINDOW IS THE ONLY FORM THE ENGINE CAN VERIFY. `engine.cli fetch`
caches the extracted text under the run, so `ledger.append_evidence` can
compare the registered span against the page it came from (invariant 4). An
excerpt pasted out of a WebFetch result is a claim about a page nobody kept.

WHO IS DENIED, AND WHO IS NOT. The rule is the actor table in
`engine/scope.py`, read and never restated here:

  category-researcher / challenger   DENIED — they cite, and a citation must
                                     be verifiable.
  servicing (research-conductor,
  enrichment-*-specialist)           ALLOWED — the verbatim read is their
                                     path; Tavily extract is how a drain
                                     lane services a relay batch.
  technographic-scanner              ALLOWED — it reads vendor pages whole.
  an actor the table does not know   ALLOWED — a person at a terminal.

WHO IS ASKING: the subagent's `agent_type`, else $DMA_ACTOR, which
`agent_run.py` puts in every headless child's environment (a headless lane
carries no `agent_type`). Both halves measured in this container, 2026-09-14:
a PreToolUse event raised INSIDE an Agent-tool subagent carries `agent_type`
(and `agent_id`); a `claude -p --agent` child does not, which is what the
environment variable is for.

IT SITS BESIDE AN AUTO-APPROVAL, AND WINS. `autoapprove_connector.py` is
registered on `WebSearch|WebFetch` and returns `allow` so a headless routine
does not prompt. Measured in this container (Claude Code 2.1.270,
2026-09-14) with two PreToolUse hooks on one matcher — allow registered
FIRST, deny second: the call was denied and the deny hook's reason was what
reached the model. A deny from any hook beats an allow from another, whatever
the order, so this guard does not need the auto-approval to stand aside.

Fails OPEN on anything it did not parse. A guard that denies on its own bug
stops the research it exists to make cheaper.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

#: The tools that return a whole page. `WebSearch` is NOT here: a result list
#: is small and is how a lane finds the URL it then windows.
FETCHERS = ("WebFetch", "mcp__Exa__web_fetch_exa")

#: Actor classes whose reading is citation, so must go through the cache.
DENIED_CLASSES = ("category-researcher", "challenger")

REASON = (
    "dma-insights: {actor} reads pages through the engine, not whole.\n\n"
    "  python3 -m engine.cli fetch --run <RUN> --root <ROOT> \\\n"
    "      --url {url} --query '<the diagnostic question text>'\n\n"
    "It returns the ranked 240-character windows that answer the question, "
    "and it caches the extracted page under the run so the ledger can verify "
    "the excerpt you register against the page it came from — which is what "
    "makes the citation real (invariant 4: every cited id carries a verbatim "
    "excerpt).\n\n"
    "The cost, measured: a whole page is 5-40K tokens that then sit in this "
    "lane's context and are re-read on every later turn — 76% of one "
    "measured run's bill was cache reads. Three windows are ~200 tokens, "
    "read once. That is the difference between a lane that finishes inside "
    "its budget and one that is re-dispatched.\n\n"
    "If the page will not extract, say so with `--via-text -` (pipe the text "
    "you do have) or record the cell as a declared absence — never paste a "
    "span from a page the run did not keep."
)


def _engine_scope():
    """`engine.scope`, imported from the plugin this hook ships in."""
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT")
                or Path(__file__).resolve().parents[2])
    sys.path.insert(0, str(root / "skills" / "dma-research"))
    from engine import scope                                    # noqa: PLC0415
    return scope


def actor_of(payload: dict) -> str:
    """Who is making this call: the subagent's type, else the child's env."""
    agent = str(payload.get("agent_type") or payload.get("agentType") or "")
    return (agent.split(":")[-1].strip()
            or str(os.environ.get("DMA_ACTOR") or "").strip())


def decide(payload: dict) -> str:
    """The reason to deny, or "" to allow."""
    tool = str(payload.get("tool_name") or "")
    if tool not in FETCHERS:
        return ""
    actor = actor_of(payload)
    if not actor:
        return ""
    try:
        scope = _engine_scope()
    except Exception:                                           # noqa: BLE001
        return ""                      # no table, no rule: allow
    try:
        klass = scope.classify(actor).get("class") or ""
    except Exception:                                           # noqa: BLE001
        return ""
    if klass not in DENIED_CLASSES:
        return ""
    ti = payload.get("tool_input") or {}
    url = ""
    if isinstance(ti, dict):
        url = str(ti.get("url") or ti.get("uri") or "").strip()
    return REASON.format(actor=actor, url=url or "<the url>")


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
