"""The dispatch verifier — the coordination layer that reads a lane's RETURN.

The pipeline advances a stage on the SUBSTRATE the lanes wrote — the workbook,
the connector — gated by `floors_gate.run`, `assessment.gate`, the ship
verdict. Every one of those reads what a lane PRODUCED. None of them reads
whether the lane actually DID the work it logged. The floors gate decides a
cell's volleys from the `Search_Log` the lane itself wrote, and trusts it: a
lane that appends Search_Log rows without ever calling a retrieval tool
satisfies the evidence floor with fabricated searches, and nothing sees it.
That is the gap the engagement owner named — "no orchestrator agent that
checks the subagent outputs ... to ensure the agents have completed their work
with no fabrication."

This module is that check, at the one grain the substrate cannot self-witness:
the lane's own CLI transcript. `agent_run.py --stream` writes every lane's
tool calls verbatim to `agent_logs/<lane>.jsonl`, overwritten per dispatch, so
the file is exactly this round's work. A research lane LOGS a search by
shelling `engine.cli search …` and RETRIEVES by calling WebSearch / WebFetch /
a connector search. A transcript that carries the logging calls and no
retrieval behind them is a lane that logged searches it never ran.

DELIBERATELY CONSERVATIVE AND FAIL-SAFE. It accuses only on positive
evidence — the lane demonstrably ran (its transcript carries tool calls), it
logged at least two searches, and it made ZERO retrieval-shaped calls of any
kind. The retrieval matcher is deliberately GENEROUS, so the only way to trip
the gate is to have retrieved nothing at all. Anything it cannot read — a
missing transcript, an unparseable line, a lane whose log it cannot find — it
treats as witnessed, because a verifier that cannot see the work must never
call it fabricated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: A logged search is the lane shelling the engine's own search command. Both
#: the module form (`python3 -m engine.cli search`) and the console form
#: (`engine.cli search`) appear; `absence` also logs searches but presupposes
#: them, so `search` is the honest counter.
_LOGGED_SEARCH = re.compile(r"engine\.cli\s+search\b|(?:^|\s)cli\s+search\b")

#: Retrieval, matched GENEROUSLY on the tool NAME: the built-in web tools and
#: any connector tool whose name reads as a fetch of the outside world. Being
#: generous is the safety margin — a lane that made ANY of these did retrieve,
#: so the gate stays silent; it fires only when a lane retrieved nothing at all.
_RETRIEVAL_NAME = re.compile(
    r"websearch|webfetch|web_search|web_fetch"
    r"|search|fetch|extract|crawl|\bmap\b|enrich|scrape|browse"
    r"|exa|tavily|quartr|vibe|indeed|clay|drive|download|read_file",
    re.I)

#: A shell that reaches the network is retrieval too — but an `engine.` call is
#: the engine talking to itself, never a fetch, so it is excluded even when a
#: query it carries happens to hold a URL.
_SHELL_FETCH = re.compile(r"\bcurl\b|\bwget\b|https?://")


def _tool_uses(transcript: Path):
    """Yield (name, input_dict) for every tool_use block in a lane transcript,
    reading the CLI's stream-json verbatim. Malformed lines are skipped, not
    fatal — a verifier that dies on one bad line witnesses nothing."""
    for raw in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except Exception:                                   # noqa: BLE001
            continue
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield (str(block.get("name") or ""),
                       block.get("input") if isinstance(block.get("input"), dict)
                       else {})


def witness(transcript: Path) -> dict:
    """What the transcript proves the lane did. `ran` is any tool call at all —
    the evidence the stream captured tools and the lane is not a blank log;
    `logged_searches` and `retrievals` are the two the fabrication test weighs."""
    ran = logged = retrievals = 0
    for name, inp in _tool_uses(transcript):
        ran += 1
        blob = ""
        try:
            blob = json.dumps(inp, default=str)
        except Exception:                                   # noqa: BLE001
            blob = str(inp)
        is_engine_shell = "engine." in blob
        if _LOGGED_SEARCH.search(blob):
            logged += 1
        if _RETRIEVAL_NAME.search(name):
            retrievals += 1
        elif not is_engine_shell and _SHELL_FETCH.search(blob):
            retrievals += 1
    return {"ran": ran, "logged_searches": logged, "retrievals": retrievals}


#: Two logged searches with zero retrievals is the floor at which "the stream
#: missed a call" stops being a plausible innocent reading and "logged a search
#: it never ran" is the only one left. One is left to the transcript's own
#: noise; the gate wants the pattern, not a single row.
_MIN_LOGGED = 2


def research_lane_fabrication(category: str, agent_logs_dir) -> list:
    """Blocking reasons for one research category, or [] when its lane's logged
    searches are witnessed. The lane is `research-<category>-producer`; its
    transcript is `<category-lower>` named in `agent_logs/`."""
    logs = Path(agent_logs_dir)
    lane = f"research-{str(category).lower()}-producer"
    transcript = logs / f"{lane}.jsonl"
    if not transcript.is_file():
        return []                       # cannot witness → never accuse
    w = witness(transcript)
    if w["ran"] == 0:
        return []                       # a blank transcript proves nothing
    if w["logged_searches"] >= _MIN_LOGGED and w["retrievals"] == 0:
        return [
            f"fabricated_search: the lane logged {w['logged_searches']} "
            f"search(es) to the Search_Log the floors gate trusts, and its "
            f"transcript shows {w['ran']} tool call(s) with NOT ONE retrieval "
            f"behind them — no WebSearch, no WebFetch, no connector fetch, no "
            f"shell that reached the network. A logged volley with no real "
            f"search behind it satisfies the evidence floor with a row nobody "
            f"ran; run the retrieval for each logged volley, then log it."]
    return []
