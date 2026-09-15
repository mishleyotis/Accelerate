#!/usr/bin/env python3
"""PostToolUse on Agent: the lane's return, drained into the substrate.

WHAT A RETURNING LANE LEAVES IN THE AIR. A research lane that meets a
question its own tools cannot answer emits `search_requests` — queries for
the session that actually holds the connectors. Until something reads them
they are prose in a transcript: the next dispatch re-searches what the last
lane already asked for, and the relay queue the whole mechanism is built on
stays empty (MEM-0333: zero code read a `search_requests`).

This hook runs at the one moment the answer is free — the lane has returned,
its output is in hand, and nothing has been summarised away yet:

  1. the return text is written into a scratch log directory under the lane's
     own name and `engine.relay harvest --logs` is run over it. The GRAMMAR
     is relay's, not a second copy of it: whole-JSON, fenced, and the
     key-in-prose bracket walk all come from `relay.extract_requests`.
  2. `engine.relay reconcile` closes the requests the Search_Log shows were
     already answered — a batch nobody needs to service.
  3. for a research lane, `engine.brief handback --category <C>` computes
     what the category actually established, from its sheets rather than
     from the lane's report of itself.

Then it says, as `additionalContext`: the cells still open, the cells that
are empty AND undeclared (the ones that will block the floors gate), any
relay batch now waiting with the specialist that services it, and the exact
next dispatch.

AND THE ONE THING THE LANE CANNOT SAY ABOUT ITSELF. If the substrate did not
change between the dispatch and the return, the lane wrote nothing — whatever
its prose claims — and re-dispatching the same prompt buys the same nothing.
The hook says so and points at the handback instead.

IT NEVER BLOCKS. The lane's output is expensive and already exists; refusing
the tool result throws away the very work this hook exists to preserve.
Every step is best-effort and reported as what it is.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _runctx as ctx                                          # noqa: E402

SKILL = ctx.SKILL

#: Lanes whose return is worth draining. A general-purpose subagent and a
#: production producer emit no `search_requests` and own no category.
GOVERNED = re.compile(
    r"^(research-|enrichment-|technographic-scanner$)|(-challenger)$", re.I)

LANE = re.compile(r"^research-(p\d+c\d+)-producer$", re.I)

#: Lane stems `engine.relay` recognises when no --category is given. A name
#: outside this set and outside the research-lane pattern is harvested under
#: no lane at all, which the hook REPORTS rather than papering over.
RELAY_KNOWN = ("technographic-scanner", "enrichment-connector-specialist",
               "research-conductor")

#: Who drains a relay batch. The lanes hold no connector; this actor does.
DRAIN_AGENT = "enrichment-web-specialist"

#: The whole hook's budget, INSIDE the wrapper's timeout (hooks.json: 120s).
#: Each engine call is bounded by what is left of it rather than by its own
#: number: four calls each allowed 120 seconds is a hook the harness kills
#: mid-drain, and a drain that is killed halfway has queued some of the
#: lane's requests and dropped the rest.
DEADLINE_S = float(os.environ.get("DMA_HARVEST_DEADLINE_S", "95"))
_STARTED = time.monotonic()


def _left(cap: float) -> float:
    """What remains of the hook's budget, never more than `cap`."""
    return max(0.0, min(cap, DEADLINE_S - (time.monotonic() - _STARTED)))


# ── the return, read ──────────────────────────────────────────────────────

def response_text(event: dict) -> str:
    """Every scrap of text the tool_response carries, in order."""
    tr = event.get("tool_response")
    return _flatten(tr)


def _flatten(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("content", "text", "result", "output", "response"):
            if k in v:
                return _flatten(v[k])
        return json.dumps(v)
    if isinstance(v, list):
        return "\n".join(_flatten(i) for i in v if i is not None)
    return "" if v is None else str(v)


def agent_of(event: dict) -> str:
    ti = event.get("tool_input") or {}
    a = ""
    if isinstance(ti, dict):
        a = ti.get("subagent_type") or ti.get("agent") or ti.get("agent_type") or ""
    if not isinstance(a, str) or not a.strip():
        a = str(event.get("agent_type") or "")
    return a.split(":")[-1].strip()


# ── the three engine calls ────────────────────────────────────────────────

def _engine(run, module: str, *args, timeout: float = 40) -> dict | None:
    """One engine subcommand, as a subprocess, JSON if it gives one.

    Defensive by contract: a subcommand this engine does not carry, a
    non-zero exit, a timeout or unreadable output all return None. Three
    other streams are moving inside `engine/` — a hook that died because a
    CLI grew a flag would cost the drain it exists to perform.
    """
    if run is None:
        return None
    budget = _left(timeout)
    if budget <= 1:
        return None                    # out of time: say nothing, never guess
    cmd = [sys.executable, "-m", f"engine.{module}", *args,
           "--run", run.run_id, "--root", str(run.root)]
    try:
        r = subprocess.run(cmd, cwd=str(SKILL), capture_output=True,
                           text=True, timeout=budget)
    except Exception:                                          # noqa: BLE001
        return None
    out = (r.stdout or "").strip()
    if not out:
        return None
    try:
        doc = json.loads(out)
    except ValueError:
        return {"_text": out, "_rc": r.returncode}
    return doc if isinstance(doc, dict) else {"_list": doc, "_rc": r.returncode}


def harvest(run, agent: str, text: str) -> dict:
    """Queue what the lane asked for. Returns what happened, honestly."""
    out = {"harvested": 0, "seen": 0, "unqueued": 0, "note": ""}
    if run is None or not text or "search_requests" not in text:
        return out
    m = LANE.match(agent or "")
    category = m.group(1).lower() if m else ""
    stem = f"research-{category}-producer" if category else agent
    tmp = Path(tempfile.mkdtemp(prefix="dma-harvest-"))
    try:
        # BOTH shapes relay reads: the stream-json transcript (its `result`
        # event) and the plain `.out` companion. Writing both means the
        # harvest does not depend on which one relay prefers today.
        (tmp / f"{stem}.jsonl").write_text(
            json.dumps({"type": "result", "result": text}) + "\n",
            encoding="utf-8")
        (tmp / f"{stem}.out").write_text(text, encoding="utf-8")
        args = ["harvest", "--logs", str(tmp), "--json"]
        if category:
            args += ["--category", category]
        got = _engine(run, "relay", *args) or {}
        out["harvested"] = int(got.get("harvested") or 0)
        out["seen"] = int(got.get("seen") or 0)
        if not out["seen"] and stem not in RELAY_KNOWN and not category:
            found = _extract_count(text)
            if found:
                out["unqueued"] = found
                out["note"] = (
                    f"{found} search_request(s) were in {agent}'s return and "
                    f"`engine.relay harvest` queued none: its lane table "
                    f"recognises the research lanes plus "
                    f"{', '.join(RELAY_KNOWN)}, and not this name. Queue them "
                    f"by hand or add the lane to `relay._lanes` — they are "
                    f"lost otherwise.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def _extract_count(text: str) -> int:
    """How many requests the text carries, by relay's OWN grammar."""
    try:
        (relay,) = ctx.engine("relay")
        return len(relay.extract_requests(text))
    except Exception:                                          # noqa: BLE001
        return 0


# ── the report ────────────────────────────────────────────────────────────

def _cells(v, cap: int = 12) -> str:
    rows = [str(c) for c in (v or [])]
    if not rows:
        return "none"
    head = ", ".join(rows[:cap])
    return head + (f" and {len(rows) - cap} more" if len(rows) > cap else "")


def context_for(run, agent: str, text: str) -> str | None:
    """The paragraph this return earns, or None when it earns none."""
    lines = []
    h = harvest(run, agent, text)
    if h["harvested"]:
        lines.append(
            f"RELAY — {h['harvested']} new search_request(s) from {agent} are "
            f"queued ({h['seen']} seen). They are queries this lane could not "
            f"answer with the tools it holds; the session that holds the "
            f"connectors answers them.")
    if h["note"]:
        lines.append("RELAY — " + h["note"])

    rec = _engine(run, "relay", "reconcile", "--json")
    if isinstance(rec, dict) and isinstance(rec.get("closed"), dict):
        n = sum(int(v or 0) for v in rec["closed"].values())
        if n:
            lines.append(
                f"RELAY — reconcile closed {n} request(s) the Search_Log "
                f"shows were already answered ("
                + ", ".join(f"{k} {v}" for k, v in sorted(rec["closed"].items()) if v)
                + f"); {rec.get('still_open', '?')} still open.")

    m = LANE.match(agent or "")
    if m:
        cat = m.group(1).upper()
        hb = _engine(run, "brief", "handback", "--category", cat, "--json")
        if isinstance(hb, dict) and not hb.get("_text"):
            still = hb.get("still_open") or []
            lines.append(
                f"HANDBACK {cat} — computed from the sheets, not from the "
                f"lane's report of itself: {len(hb.get('synthesised') or [])} "
                f"cell(s) synthesised, {len(hb.get('declared_absent') or [])} "
                f"declared absent, {len(still)} still open"
                + (f" ({_cells(still)})" if still else "")
                + f"; {hb.get('evidence_items', 0)} evidence item(s) over "
                  f"{hb.get('searches', 0)} search(es).")
            leads = hb.get("leads_for_other_categories") or {}
            if isinstance(leads, dict) and leads:
                lines.append(
                    "HANDBACK — rows this lane registered that name ANOTHER "
                    "category's cells: "
                    + "; ".join(f"{k}: {len(v)}" for k, v in sorted(leads.items()))
                    + ". They travel to those lanes through the handback — "
                      "never by this lane writing their rows.")

    g = _engine(run, "brief", "gaps", "--json", timeout=60)
    if isinstance(g, dict) and isinstance(g.get("categories"), dict):
        openish = []
        for cat, row in sorted(g["categories"].items()):
            if not isinstance(row, dict):
                continue
            if row.get("open_cells") or row.get("undeclared_empty"):
                openish.append(
                    f"  {cat}: {len(row.get('open_cells') or [])} open, "
                    f"{len(row.get('undeclared_empty') or [])} empty-and-undeclared"
                    + (f", {row['unserviced_requests']} unserviced request(s)"
                       if row.get("unserviced_requests") else ""))
        if openish:
            lines.append("STILL OPEN, per category (an empty cell closes only "
                         "as a declared absence — `engine.cli absence` — and "
                         "an undeclared one blocks the floors gate):\n"
                         + "\n".join(openish[:16]))

    batches = _pending_batches(run)
    if batches:
        lines.append(
            "RELAY BATCH waiting: " + ", ".join(batches[:4])
            + f". It is serviced by `{DRAIN_AGENT}` — the actor that holds "
              f"the connectors — not by another research lane:\n"
              f"  python3 {ctx.PLUGIN / 'scripts' / 'agent_run.py'} --agent "
              f"{DRAIN_AGENT} --prompt-file {batches[0]} --stream")

    nxt = _next_dispatch(run)
    if nxt:
        lines.append("NEXT: " + nxt)

    wrote = ctx.wrote_since_dispatch(run, agent)
    if wrote is False:
        lines.append(
            f"THE SUBSTRATE DID NOT CHANGE while {agent} ran: no workbook "
            f"write, no relay entry, no notebook entry. Whatever the return "
            f"text says, this lane left nothing behind — and what it did not "
            f"write there did not happen. DO NOT RE-DISPATCH IT VERBATIM: the "
            f"same prompt buys the same nothing. Read the handback above, and "
            f"dispatch against what it says is still open, or record why the "
            f"cells cannot be closed.")

    return "\n\n".join(lines) if lines else None


def _pending_batches(run) -> list[str]:
    """The most recent relay batch files, when the queue still has OPEN rows.

    APPROXIMATE, AND SAYS SO. `pipeline._pending_relay_batches` maps each
    recorded batch to the request ids inside it; that mapping is the driver's
    private bookkeeping and this hook does not reach into it. What it can say
    without guessing is: requests are open, and here are the batches most
    recently written. A conductor that opens the wrong one of two finds it
    already serviced — `relay.record` refuses to reopen a closed request —
    which is a cheap wrong answer. Claiming a batch is drained when it is not
    would be an expensive one.
    """
    st = ctx.pipeline_state(run)
    recorded = [str(p) for p in (st.get("relay_batches") or [])]
    if not recorded:
        return []
    try:
        (relay,) = ctx.engine("relay")
        rows = relay.requests(run)
    except Exception:                                          # noqa: BLE001
        return recorded[-2:]
    if not any(r.get("status") == "OPEN" for r in rows.values()):
        return []
    return recorded[-2:]


def _next_dispatch(run) -> str:
    """The watchdog's own resume plan for this run, as one line."""
    try:
        (watchdog,) = ctx.engine("watchdog")
        row = watchdog.inspect(run)
    except Exception:                                          # noqa: BLE001
        return ""
    plan = (row or {}).get("resume") or {}
    if plan.get("command"):
        return f"`{' '.join(str(c) for c in plan['command'])}` ({row.get('state')})"
    if plan.get("agent"):
        agents = plan.get("parallel") or [plan["agent"]]
        return (", ".join(f"`{a}`" for a in agents)
                + f" — {plan.get('why', '')} ({row.get('state')})")
    return ""


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
    except Exception:                                          # noqa: BLE001
        return 0                       # fail OPEN, silent
    if str(event.get("tool_name") or "") not in ("Agent", "Task"):
        return 0
    agent = agent_of(event)
    if not agent or not GOVERNED.search(agent):
        return 0
    try:
        run = ctx.locate()
        text = response_text(event)
        out = context_for(run, agent, text)
    except Exception:                                          # noqa: BLE001
        return 0
    if not out:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": out,
    }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                          # noqa: BLE001
        sys.exit(0)                    # never block a returning lane
