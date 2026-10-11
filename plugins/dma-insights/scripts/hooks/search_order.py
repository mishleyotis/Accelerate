#!/usr/bin/env python3
"""PreToolUse on the general web searchers: the free chain is an ORDER.

Owner, 2026-10-11: "avoid calling web search severally and batch queries to
the open source connectors first". The collector's prompt says it; this
hook makes it so. For a research actor (collector, category researcher,
servicing, technographic scanner) a `WebSearch` / Exa / Tavily search is
refused:

  * before this agent has fired ONE `research_brief` (the batched call —
    every cell question of the capability in one `questions[]`), while the
    evidence service is marked AVAILABLE by the plugin's own proxy;
  * past WEB_PER_BRIEF general searches per brief fired, unless the last
    brief answered an error or `needs_spend_approval` (the engine could
    not answer: the chain moves on).

Who is asking: the subagent's `agent_type`, else $DMA_ACTOR (a headless
child), resolved to a class by `engine.scope`, exactly as
deny_whole_page_fetch.py does. Counts are per (session, agent) in a small
state file the PostToolUse half (`--post`) of this same script keeps for
`research_brief` and the searchers. The availability marker is
`<DMA_RESEARCH_LAYER_STATE>/evidence.json`, written by evidence_proxy.py at
every `initialize`; no marker, a stale one (> 12 h), or `available: false`
means the layer is down and the hook steps aside — the fallback is the
point. FAILS OPEN on anything it did not parse.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SEARCHERS = ("WebSearch", "mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search")
BRIEF = "mcp__plugin_dma-insights_evidence__research_brief"
#: the classes whose searching is citation and must start at the engine
ORDERED_CLASSES = ("category-collector", "category-researcher", "servicing", "technographic-scanner")
WEB_PER_BRIEF = 3
MARKER_MAX_AGE_S = 12 * 3600

LAYER_DIR = Path(os.environ.get("DMA_RESEARCH_LAYER_STATE") or "/root/.dma/research_layer")
STATE_DIR = Path(os.environ.get("DMA_SEARCH_ORDER_STATE") or "/root/.dma/search_order")

FIRST = (
    "dma-insights search order: {actor} has fired no research_brief yet in this agent, and the "
    "evidence engine is available. Batch this capability's questions into ONE "
    "mcp__plugin_dma-insights_evidence__research_brief call first — `questions` as objects, one per "
    "cell question: {{\"question\": \"...\", \"subcap_ids\": [\"<cell>\"], \"facet\": \"primary\"}}, plus one "
    "per owed facet naming every cell it bears on. Its cards come back register-ready with "
    "`item.linked_subcap_ids` and `by_question[]` names what nothing answered. The free chain is "
    "research_brief → searxng / parallel → WebSearch; WebSearch is the last rung, for a question the "
    "layer answered an error on."
)
BUDGET = (
    "dma-insights search order: {actor} has fired {web} general searches against {briefs} "
    "research_brief call(s). Batch the remaining questions into one more research_brief (the "
    "unanswered `by_question` rows, with their tail or alias wording), or the raw layer "
    "(mcp__plugin_dma-insights_searxng__searxng_web_search / "
    "mcp__plugin_dma-insights_parallel__web_search — or mcp__Parallel_Search__web_search where the "
    "claude.ai connector shadows it — one message), before another WebSearch. "
    "{limit} general searches per brief is the ceiling; a brief that answers an error lifts it."
)


def _engine_scope():
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])
    sys.path.insert(0, str(root / "skills" / "dma-research"))
    from engine import scope                                    # noqa: PLC0415
    return scope


def actor_of(payload: dict) -> str:
    agent = str(payload.get("agent_type") or payload.get("agentType") or "")
    return agent.split(":")[-1].strip() or str(os.environ.get("DMA_ACTOR") or "").strip()


def actor_class(actor: str, scope=None) -> str:
    if not actor:
        return ""
    try:
        scope = scope or _engine_scope()
        return str(scope.classify(actor).get("class") or "")
    except Exception:                                           # noqa: BLE001
        # a name the table would know by shape, when the engine is not importable
        a = actor.lower()
        if a.endswith("-collector") or a == "research-evidence-collector":
            return "category-collector"
        if a.startswith("research-p") and a.endswith("-producer"):
            return "category-researcher"
        if a in ("research-conductor", "enrichment-web-specialist", "enrichment-connector-specialist"):
            return "servicing"
        if a == "technographic-scanner":
            return "technographic-scanner"
        return ""


def agent_key(payload: dict) -> str:
    return (str(payload.get("agent_id") or payload.get("agentId") or "").strip()
            or str(os.environ.get("DMA_ACTOR") or "").strip() or "main")


def layer_available(layer_dir: Path = LAYER_DIR, now=time.time) -> bool | None:
    """True / False from the proxy's marker; None when nothing is known."""
    try:
        d = json.loads((layer_dir / "evidence.json").read_text(encoding="utf-8"))
        if now() - float(d.get("ts") or 0) > MARKER_MAX_AGE_S:
            return None
        return bool(d.get("available"))
    except Exception:                                           # noqa: BLE001
        return None


def _state_path(payload: dict, state_dir: Path) -> Path:
    sid = str(payload.get("session_id") or "nosession").replace("/", "_")[:80]
    return state_dir / f"{sid}.json"


def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:                                           # noqa: BLE001
        return {}


def _save(path: Path, d: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:                                           # noqa: BLE001
        pass


def record(payload: dict, *, state_dir: Path = STATE_DIR) -> dict:
    """PostToolUse: count a brief (and whether it answered) or a searcher."""
    tool = str(payload.get("tool_name") or "")
    path = _state_path(payload, state_dir)
    st = _load(path)
    row = st.setdefault(agent_key(payload), {"briefs": 0, "web": 0, "last_brief_error": False})
    if tool == BRIEF:
        row["briefs"] += 1
        resp = payload.get("tool_response")
        text = json.dumps(resp)[:4000].lower() if resp is not None else ""
        err = bool(isinstance(resp, dict) and (resp.get("isError") or resp.get("is_error"))) \
            or '"error"' in text or "needs_spend_approval" in text or "service unavailable" in text
        row["last_brief_error"] = err
    elif tool in SEARCHERS:
        row["web"] += 1
    _save(path, st)
    return row


def decide(payload: dict, *, state_dir: Path = STATE_DIR, layer_dir: Path = LAYER_DIR,
           scope=None, now=time.time) -> str:
    """PreToolUse: the reason to deny, or "" to allow."""
    tool = str(payload.get("tool_name") or "")
    if tool not in SEARCHERS:
        return ""
    actor = actor_of(payload)
    cls = actor_class(actor, scope)
    if cls not in ORDERED_CLASSES:
        return ""
    if layer_available(layer_dir, now) is not True:
        return ""                           # the layer is down or unknown: WebSearch is the fallback
    row = _load(_state_path(payload, state_dir)).get(agent_key(payload)) or {}
    briefs, web = int(row.get("briefs") or 0), int(row.get("web") or 0)
    if briefs == 0:
        return FIRST.format(actor=actor)
    if row.get("last_brief_error"):
        return ""
    if web >= WEB_PER_BRIEF * briefs:
        return BUDGET.format(actor=actor, web=web, briefs=briefs, limit=WEB_PER_BRIEF)
    return ""


def main(argv: list[str]) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except Exception:                                           # noqa: BLE001
        return 0
    try:
        if "--post" in argv:
            record(payload)
            return 0
        why = decide(payload)
    except Exception:                                           # noqa: BLE001
        return 0
    if not why:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": why}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
