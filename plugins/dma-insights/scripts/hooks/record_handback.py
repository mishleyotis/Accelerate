#!/usr/bin/env python3
"""SubagentStop on a research lane: write down what it left, and let it go.

MEASURED IN THIS CONTAINER, 2026-09-14, Claude Code 2.1.270: SubagentStop
DOES fire for Agent-tool subagents. The probe dispatched one general-purpose
subagent with a hook writing its stdin to a file; the payload carried
`agent_type`, `agent_id`, `stop_hook_active`, `last_assistant_message` and —
the field this hook is built on — `agent_transcript_path`, a JSONL of the
subagent's own turns. (The CLI's built-in hook table does not list the event;
it fires anyway. The first probe measured nothing because the model reached
for TaskCreate instead of Agent — a dispatch that never happened, not an
event that never fired.)

WHAT IT DOES. Reads the lane's transcript, harvests the `search_requests` it
emitted by relay's OWN grammar, and writes
`07_qa/handbacks/<agent>-<ts>.json` carrying `still_open`, `notes_written`
and `substrate_writes` — computed from the substrate, never from the lane's
prose.

WHAT IT DELIBERATELY DOES NOT DO: force the lane to continue. SubagentStop
can block, and blocking here is the expensive mistake — a lane that cannot
finish has usually run out of the thing that would let it finish (an open
question, a missing connector, a cell whose evidence does not exist), and
another turn spent inside it is another turn billed against the same wall.
The driver re-dispatches it WITH this handback, inside the run's budget,
which is both cheaper and the only form that carries what the last attempt
established. So: non-blocking, always.

H4 (`harvest_on_return`, PostToolUse on Agent) covers the same ground from
the parent's side and is the proven fallback: it fires for Agent-tool
subagents, and the SubagentStop binding additionally reaches headless
children. Both are idempotent — relay's queue dedupes by request id, so the
two paths harvesting the same lane queue one copy.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _runctx as ctx                                          # noqa: E402

SKILL = ctx.SKILL
HANDBACK_DIR = "handbacks"

LANE = re.compile(r"^research-(p\d+c\d+)-producer$", re.I)
GOVERNED = re.compile(r"^research-", re.I)


def agent_of(event: dict) -> str:
    return str(event.get("agent_type") or event.get("agentType")
               or "").split(":")[-1].strip()


def lane_text(path: str) -> str:
    """The subagent's own output, through relay's transcript reader.

    `relay.lane_output` walks a `result` event first and falls back to every
    assistant text block in order — which is exactly the shape of the
    `agent_transcript_path` JSONL this event carries (verified against a
    real one, 2026-09-14). One reader, both transcript kinds.
    """
    if not path:
        return ""
    try:
        (relay,) = ctx.engine("relay")
        return relay.lane_output(Path(path))
    except Exception:                                          # noqa: BLE001
        pass
    try:                               # the engine is unavailable: read plainly
        out = []
        for line in Path(path).read_text(encoding="utf-8",
                                         errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = (e or {}).get("message") or {}
            for b in (msg.get("content") or []) if isinstance(msg.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    out.append(b["text"])
        return "\n".join(out)
    except OSError:
        return ""


def requests_in(text: str) -> list[dict]:
    """The `search_requests` the lane emitted, by relay's grammar."""
    if not text or "search_requests" not in text:
        return []
    try:
        (relay,) = ctx.engine("relay")
        return relay.extract_requests(text)
    except Exception:                                          # noqa: BLE001
        return []


#: INSIDE the wrapper's own timeout (hooks.json: 60s). A subprocess budget
#: larger than the hook's is a hook the harness kills mid-write.
def _engine_json(run, module: str, *args, timeout: int = 25):
    if run is None:
        return None
    cmd = [sys.executable, "-m", f"engine.{module}", *args,
           "--run", run.run_id, "--root", str(run.root)]
    try:
        r = subprocess.run(cmd, cwd=str(SKILL), capture_output=True,
                           text=True, timeout=timeout)
    except Exception:                                          # noqa: BLE001
        return None
    try:
        return json.loads((r.stdout or "").strip())
    except ValueError:
        return None


def record(event: dict) -> Path | None:
    """Write the handback file, and return where it went."""
    agent = agent_of(event)
    if not agent or not GOVERNED.search(agent):
        return None
    run = ctx.locate()
    if run is None:
        return None
    text = lane_text(str(event.get("agent_transcript_path") or ""))
    reqs = requests_in(text)

    m = LANE.match(agent)
    category = m.group(1).upper() if m else ""
    still_open, evidence_items, searches = None, None, None
    if category:
        hb = _engine_json(run, "brief", "handback", "--category", category)
        if isinstance(hb, dict):
            still_open = hb.get("still_open")
            evidence_items = hb.get("evidence_items")
            searches = hb.get("searches")

    notes = None
    if category:
        st = _engine_json(run, "memory", "status", "--category", category,
                          timeout=15)
        if isinstance(st, dict):
            per = (st.get("categories") or {}).get(category) or {}
            notes = per.get("entries")

    doc = {
        "agent": agent,
        "category": category or None,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run.run_id,
        "agent_id": event.get("agent_id"),
        "last_assistant_message": str(event.get("last_assistant_message")
                                      or "")[:2000],
        # computed from the substrate, not from the lane's prose
        "still_open": still_open,
        "notes_written": notes,
        "substrate_writes": ctx.wrote_since_dispatch(run, agent),
        "evidence_items": evidence_items,
        "searches": searches,
        "search_requests": reqs,
        "note": ("`substrate_writes` is null when no dispatch fingerprint was "
                 "recorded to compare against; false means the workbook, the "
                 "relay queue and the notebooks were all unchanged while this "
                 "lane ran. A lane that cannot finish is re-dispatched WITH "
                 "this file, inside the run's budget — forcing it to continue "
                 "here would burn turns against the same wall."),
    }
    out = Path(run.qa_dir) / HANDBACK_DIR / f"{agent}-{int(time.time())}.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str))
        tmp.replace(out)
    except OSError:
        return None
    return out


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
    except Exception:                                          # noqa: BLE001
        return 0                       # fail OPEN, silent
    try:
        where = record(event)
    except Exception:                                          # noqa: BLE001
        return 0
    if where:
        # A note, never a block. SubagentStop's `decision: block` would force
        # the lane to continue; see the module docstring for why it must not.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": (
                f"dma-insights: this lane's handback was written to {where} — "
                f"what it closed, what is still open, what it noted and "
                f"whether it wrote to the substrate at all, each read from "
                f"the run rather than from the lane's report of itself. The "
                f"re-dispatch reads this file; it is not a request to keep "
                f"working."),
        }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                          # noqa: BLE001
        sys.exit(0)                    # never block a subagent's stop
