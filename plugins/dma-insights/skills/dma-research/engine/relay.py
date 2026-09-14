#!/usr/bin/env python3
"""engine.relay — the `search_requests` relay, as code (MEM-0333).

    python3 -m engine.relay harvest     --run R [--root ROOT] [--category P1C1,P2C3]
    python3 -m engine.relay list        --run R [--root ROOT] [--status OPEN] [--category C] [--json]
    python3 -m engine.relay batch       --run R [--root ROOT] [--group-by capability|tool] [--category C] [--out-dir DIR] [--json]
    python3 -m engine.relay record      --run R [--root ROOT] (--id SR-… | --ids SR-a,SR-b) --status SERVED|EMPTY|BLOCKED [--note …] [--tool X]
    python3 -m engine.relay reconcile   --run R [--root ROOT]
    python3 -m engine.relay state       --run R [--root ROOT] [--json]
    python3 -m engine.relay drain-brief --run R [--root ROOT] --out-dir DIR [--category C]
    python3 -m engine.relay enrichment  --run R [--root ROOT] [--category C] [--json]
    python3 -m engine.relay heal        --run R [--root ROOT] --category C [--json]

WHY THIS EXISTS. Every dispatched lane is told (agent_run.py's DISPATCH-MODE
preamble, routing.md, CONNECTORS.md) that where it cannot run an enrichment
connector it must emit a `search_requests` array and "the orchestrating
session runs them through the real connectors, registers the evidence and
re-invokes". The 2026-08-28 headless audit measured that sentence against the
tree: zero code read a `search_requests`, called a connector, registered a row
or re-dispatched anything (MEM-0333, BLOCKER). The relay ran on a top
session's unenforced diligence, and the owner's live runs (2026-09-07) showed
the shape that produces: categories passing their floors gate on bare
WebSearch, and the connector work "aspirational".

THE MECHANISM, in five verbs, all reading and writing the run tree:

  harvest     read each lane's transcript (`agent_logs/<lane>.jsonl`, and the
              `.out` beside it when a batch wrote one), find the
              `search_requests` it emitted — whole-JSON output, a fenced JSON
              block, or the key embedded in prose — and queue each one ONCE
              (the id is a hash of the normalised query and the cell) in
              `07_qa/search_relay.jsonl`, append-only, as an OPEN request.
  batch       (the servicing path since 2026-09-14) group the OPEN requests
              for the SESSION THAT HOLDS THE CONNECTORS. Queries are
              deduplicated by their normalised form across the whole run —
              two categories asking the same thing owe one search — grouped
              by capability, and written as one batch file plus ONE
              self-contained prompt per group under `briefs/relay_r<n>/`.
              Each query carries the single `engine.cli search` call whose
              repeated `--subcap` writes a row per cell and charges the
              search-op ceiling once, and the single `engine.relay record
              --ids a,b` that closes every request behind it. Nothing is
              dispatched: the conductor spins one fresh in-process subagent
              per prompt, which inherits its connectors, and the results
              land in the workbook rather than in anybody's context.
  drain       (the fallback, `mode="lane"`) one brief per category for
              `enrichment-web-specialist` — carrying the open requests and
              the same commands — as an `agent_run.py --batch` array. Kept
              explicit because a container that DOES hold the connectors can
              still use it; the default is `batch`, because a headless child
              holds none.
  reconcile   mark OPEN requests SERVED or EMPTY from the Search_Log itself —
              a row through an enrichment tool whose query matches — so a lane
              that did the work and forgot the `record` still closes its
              request from the substrate, and a `record` with no row behind it
              does not.
  heal        for a category whose Search_Log shows NO enrichment-connector
              search, say which half is broken, measured: the grants this
              repository hands a child (`agent_run.ALLOWED`), the tools the
              lane's manifest declares, and what the transcript witnesses —
              a connector attempted and refused (`grants`), a connector never
              tried (`instruction`), or a connector used and logged as
              `web_search` (`logging`). The driver puts that verdict in the
              ENRICHMENT gate row and in the fresh lane's brief.

Everything here is deterministic and local. No model, no network: the lanes
search; this module queues, briefs, reconciles and measures.
"""
from __future__ import annotations

# Runnable both ways: -m engine.<module>, or by path for --help (audit_skills).
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

from . import contract as C
from . import ledger as L
from . import runstate

QUEUE_NAME = "search_relay.jsonl"
LOGS_DIR = "agent_logs"
DRAIN_AGENT = "enrichment-web-specialist"
REQUEST_STATUSES = ("OPEN", "SERVED", "EMPTY", "BLOCKED")
CLOSING_STATUSES = ("SERVED", "EMPTY", "BLOCKED")

PLUGIN = Path(__file__).resolve().parents[3]
AGENTS_DIR = PLUGIN / "agents"
AGENT_RUN = PLUGIN / "scripts" / "agent_run.py"
SKILL_REL = "plugins/dma-insights/skills/dma-research"

#: The connector namespaces a research lane may call. Mirrors
#: `agent_run.CONNECTOR_NAMESPACES`; a test pins the two equal.
CONNECTOR_NAMESPACES = (
    "mcp__Clay", "mcp__Exa", "mcp__Tavily", "mcp__Vibe_Prospecting",
    "mcp__Indeed", "mcp__Quartr", "mcp__Google_Drive",
)

#: What a refused tool call reads as in a child's transcript. Mirrors
#: `agent_run._BLOCKED_MARKERS` (MEM-0111); a test pins the two equal, because
#: a marker one side knows and the other does not is a refusal one side reads
#: as "found nothing".
BLOCKED_MARKERS = (
    "was blocked. For security",
    "haven't granted it yet",
    "requested permissions to",
    "blocked_capabilities",
    "permission denied by hook",
)

#: Namespace → the closed Search_Log vocabulary (`contract.SEARCH_TOOLS`).
TOOL_OF_NAMESPACE = {
    "mcp__Exa": "exa", "mcp__Tavily": "tavily", "mcp__Clay": "clay",
    "mcp__Vibe_Prospecting": "vibe", "mcp__Indeed": "indeed",
    "mcp__Quartr": "quartr", "mcp__Google_Drive": "drive",
}

#: The heal verdicts, and what each tells the fresh lane instance to do. A
#: verdict is measured (see `heal_plan`), never inferred from the absence of
#: rows alone.
HEAL_INSTRUCTIONS = {
    "grants": (
        "a connector call was REFUSED in your previous instance's transcript. "
        "The grants this repository hands you already name every connector "
        "namespace; a refusal means the harness did not bind it for a headless "
        "child. Try the connector ONCE more (the binding can differ between "
        "instances); if it is refused again, emit the queries as "
        "`search_requests` and say so in your final output — never log a "
        "connector search you did not run."),
    "instruction": (
        "your previous instance logged every search through "
        "web_search/web_fetch and emitted no `search_requests`, so no cell "
        "of yours carries the enrichment effort the floors gate counts. YOU "
        "HOLD NO CONNECTOR, and that is the design rather than a fault: they "
        "bind once at session start, in the orchestrator's session, and a "
        "headless lane is a different session. So for each open cell emit "
        "the primary and contradicts volleys you WOULD have fired as "
        "`search_requests` entries — one JSON object each, with `query`, "
        "`facet`, `subcap` and a preferred `tool` — and say so in your final "
        "output. The conductor runs them in one batch per capability through "
        "the real connectors and logs them against your cells. Never log a "
        "connector search you did not run."),
    "logging": (
        "your previous instance CALLED a connector (the transcript witnesses "
        "it) but every Search_Log row names `web_search`/`web_fetch`. The gate "
        "reads the Search_Log, not the transcript: log connector searches with "
        "the tool that ran them (`--tool exa|tavily|clay|drive`), so the "
        "enrichment effort behind each cell is countable."),
    "unbound": (
        "the connector is NOT BOUND in this container — the run's own "
        "connector baseline is short of a required family, your manifest "
        "declares it and the grants allow it, and your previous instance's "
        "transcript shows neither an attempt nor a refusal (an absent tool "
        "produces no tool_use to witness). DO NOT retry it: there is nothing "
        "to retry against, and a fresh lane told to 'try harder' spends a full "
        "context floor to discover the same absence. Work the cells through "
        "web_search, emit every enrichment query you would have run as a "
        "`search_requests` entry, and declare the cells you cannot close "
        "with `engine.cli absence … --enrichment-unavailable` — the flag "
        "that writes the absence at REDUCED rigour with this reason on the "
        "row. It is verified against the run's own connector baseline, "
        "which is what proves your container never had one. A human "
        "attaches the connector on the Routine's own edit screen; no lane "
        "can."),
    "manifest": (
        "NOBODY in this run can service an enrichment request: neither this "
        "lane (which is not meant to) nor the connector holder declares a "
        "connector tool, so a fresh "
        "instance cannot call one either. This is a toolchain defect for the "
        "rectifier (scripts/provision_agent_tools.py), not something a lane can "
        "heal; emit the queries as `search_requests` so the relay's drain lane "
        "runs them."),
}


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── the queue ─────────────────────────────────────────────────────────────

def queue_path(run: runstate.Run) -> Path:
    return run.qa_dir / QUEUE_NAME


def normalize(query: str) -> str:
    """The identity of a query: case, whitespace and outer quoting removed.
    Two lanes asking the same thing in different casing owe one search."""
    q = " ".join(str(query or "").split()).strip().strip("\"'`“”‘’").strip()
    return q.lower()


def request_id(norm: str, subcap: str | None, category: str | None) -> str:
    key = f"{norm}|{subcap or ''}|{category or ''}"
    return "SR-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _append(run: runstate.Run, event: dict) -> None:
    p = queue_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def _events(run: runstate.Run) -> list[dict]:
    p = queue_path(run)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            continue                       # a torn line is skipped, never fatal
        if isinstance(ev, dict) and ev.get("id"):
            out.append(ev)
    return out


def requests(run: runstate.Run) -> dict:
    """id → the request as it stands: the OPEN row's fields, then every later
    event folded over it (latest wins). Append-only underneath, so a lane
    recording while the driver reads costs a re-read and never a lost row."""
    rows: dict[str, dict] = {}
    for ev in _events(run):
        rid = ev["id"]
        kind = str(ev.get("event") or "").lower()
        if kind == "open":
            row = {k: v for k, v in ev.items() if k != "event"}
            row["status"] = "OPEN"
            row.setdefault("history", [])
            prior = rows.get(rid)
            if prior:                      # re-harvest of a known id: keep status
                row["status"] = prior["status"]
                row["history"] = prior["history"]
                row.update({k: prior[k] for k in ("note", "closed_at", "closed_by")
                            if k in prior})
            rows[rid] = row
        elif kind in ("served", "empty", "blocked"):
            row = rows.get(rid)
            if row is None:
                continue                   # a record for a request never opened
            row["status"] = kind.upper()
            row["note"] = str(ev.get("note") or "")
            row["closed_at"] = ev.get("at")
            row["closed_by"] = ev.get("actor") or ""
            row["history"].append({k: ev.get(k) for k in ("at", "event", "actor", "note")})
    return rows


def open_requests(run: runstate.Run, category: str | None = None) -> list[dict]:
    cat = str(category or "").strip().upper() or None
    out = [r for r in requests(run).values() if r["status"] == "OPEN"
           and (cat is None or str(r.get("category") or "").upper() == cat)]
    return sorted(out, key=lambda r: (str(r.get("category") or ""), r["id"]))


def state(run: runstate.Run) -> dict:
    rows = requests(run)
    by_status = {s: 0 for s in REQUEST_STATUSES}
    by_cat: dict[str, dict] = {}
    for r in rows.values():
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        c = str(r.get("category") or "RUN")
        by_cat.setdefault(c, {s: 0 for s in REQUEST_STATUSES})
        by_cat[c][r["status"]] += 1
    return {"queue": str(queue_path(run)), "total": len(rows),
            "by_status": by_status, "by_category": by_cat,
            "open": [r["id"] for r in rows.values() if r["status"] == "OPEN"]}


# ── harvest: what the lanes asked for ─────────────────────────────────────

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_KEY = re.compile(r'"search_requests"\s*:\s*\[')
_LANE_RE = re.compile(r"^research-(p\dc\d)-producer$", re.I)


def _bracket_slice(text: str, start: int) -> str | None:
    """text[start] is '['; return the balanced array or None."""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _candidates(text: str):
    yield text
    for m in _FENCE.finditer(text):
        yield m.group(1)
    for m in _KEY.finditer(text):
        arr = _bracket_slice(text, m.end() - 1)
        if arr:
            yield '{"search_requests": ' + arr + "}"


def _tool_token(v) -> str | None:
    s = str(v or "").strip().lower()
    if not s:
        return None
    if s in C.ENRICHMENT_TOOLS:
        return s
    for ns, tok in TOOL_OF_NAMESPACE.items():
        if ns.lower() in s or tok in s:
            return tok
    return None


def _one(item, category: str | None) -> dict | None:
    if isinstance(item, str):
        item = {"query": item}
    if not isinstance(item, dict):
        return None
    q = item.get("query") or item.get("q") or item.get("search")
    if not isinstance(q, str) or len(q.strip()) < 4:
        return None
    facet = str(item.get("facet") or "").strip().lower() or None
    if facet not in C.DQ_FACETS:
        facet = None
    subcap = str(item.get("subcap") or item.get("cell") or item.get("subcap_id")
                 or item.get("SubCap_ID") or "").strip().upper() or None
    cat = str(item.get("category") or "").strip().upper() or category
    if subcap and not cat:
        cat = ".".join(subcap.split(".")[:1]).split(".")[0][:4] or None
    norm = normalize(q)
    return {
        "id": request_id(norm, subcap, cat),
        "query": " ".join(q.split()).strip(),
        "norm": norm,
        "falsifier": (" ".join(str(item.get("falsifier") or item.get("falsifier_query")
                                   or "").split()).strip() or None),
        "facet": facet, "subcap": subcap, "category": cat,
        "tool": _tool_token(item.get("tool")),
        "proves": (str(item.get("proves") or item.get("why")
                       or item.get("what_a_hit_would_prove") or "").strip()[:300] or None),
    }


def extract_requests(text: str, *, category: str | None = None) -> list[dict]:
    """Every `search_requests` entry a lane's output carries, deduplicated by
    id. Conservative: only an object with the key counts — a bare list of
    strings is not identified as requests."""
    out: dict[str, dict] = {}
    if not text or "search_requests" not in text:
        return []
    for cand in _candidates(text):
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        arr = obj.get("search_requests")
        if not isinstance(arr, list):
            continue
        for item in arr:
            row = _one(item, category)
            if row and row["id"] not in out:
                out[row["id"]] = row
    return list(out.values())


def lane_output(transcript: Path) -> str:
    """The lane's final text from its stream-json transcript: the result
    event's text, else every assistant text block in order — the same fallback
    chain agent_run._final_text walks, so both read the same answer."""
    if not transcript.is_file():
        return ""
    events = []
    for raw in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except ValueError:
            continue
    for e in reversed(events):
        if isinstance(e, dict) and e.get("type") == "result":
            for key in ("result", "text", "content"):
                v = e.get(key)
                if isinstance(v, str) and v.strip():
                    return v
    blocks = [b.get("text") for e in events if isinstance(e, dict) and e.get("type") == "assistant"
              for b in ((e.get("message") or {}).get("content") or [])
              if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
    return "\n".join(blocks)


def _lanes(logs: Path, categories: list[str] | None) -> list[tuple[str, str | None]]:
    """(lane name, category) pairs whose transcripts to read."""
    if categories:
        return [(f"research-{str(c).lower()}-producer", str(c).upper()) for c in categories]
    out = []
    for p in sorted(logs.glob("*.jsonl")) if logs.is_dir() else []:
        m = _LANE_RE.match(p.stem)
        if m:
            out.append((p.stem, m.group(1).upper()))
        elif p.stem in ("technographic-scanner", "enrichment-connector-specialist",
                        "research-conductor"):
            out.append((p.stem, None))
    return out


def harvest(run: runstate.Run, categories: list[str] | None = None, *,
            logs_dir: Path | None = None, round_no: int | None = None) -> dict:
    """Queue every request the named lanes emitted that is not already known.
    Reads transcripts only; a lane that emitted none contributes none."""
    logs = Path(logs_dir) if logs_dir else run.root / LOGS_DIR
    known = requests(run)
    new, seen, by_cat = [], 0, {}
    for lane, cat in _lanes(logs, categories):
        texts = [lane_output(logs / f"{lane}.jsonl")]
        out_file = logs / f"{lane}.out"
        if out_file.is_file():
            texts.append(out_file.read_text(encoding="utf-8", errors="replace"))
        found: dict[str, dict] = {}
        for t in texts:
            for r in extract_requests(t, category=cat):
                found.setdefault(r["id"], r)
        seen += len(found)
        for rid, r in found.items():
            if rid in known:
                continue
            ev = dict(r, event="open", lane=lane, round=round_no, at=_utcnow())
            _append(run, ev)
            known[rid] = dict(r, status="OPEN")
            new.append(rid)
            by_cat[cat or "RUN"] = by_cat.get(cat or "RUN", 0) + 1
    return {"harvested": len(new), "seen": seen, "new_ids": new,
            "by_category": by_cat, "queue": str(queue_path(run))}


# ── record / reconcile ────────────────────────────────────────────────────

def record(run: runstate.Run, req_ids, status: str, *, note: str = "",
           actor: str = "", tool: str | None = None) -> dict:
    """Close one request or MANY.

    One search now closes several requests: `batch` deduplicates by the
    normalised query, so a single connector call answers every category that
    asked for it, and closing them one at a time would put the round-trip
    back that the batching removed.

    A PARTIAL FAILURE RECORDS THE REST. An id the queue does not know is a
    refusal that NAMES it — and the ids that were good are already written,
    because the alternative is a conductor re-running every query in the
    batch to close the one request a typo lost.
    """
    status = str(status or "").strip().upper()
    if status not in CLOSING_STATUSES:
        raise L.LedgerRefusal(f"status {status!r} must be one of {CLOSING_STATUSES}")
    ids = ([req_ids] if isinstance(req_ids, str)
           else [str(i).strip() for i in (req_ids or []) if str(i).strip()])
    if not ids:
        raise L.LedgerRefusal("record needs at least one request id")
    if status == "BLOCKED" and not str(note or "").strip():
        raise L.LedgerRefusal(
            "BLOCKED must carry the refusal text as --note — a blocked request "
            "with no reason is indistinguishable from one nobody tried")
    rows = requests(run)
    done, missing = [], []
    for rid in ids:
        if rid not in rows:
            missing.append(rid)
            continue
        _append(run, {"event": status.lower(), "id": rid, "note": str(note or "")[:600],
                      "actor": actor, "tool": tool, "at": _utcnow()})
        done.append(rid)
    if missing:
        raise L.LedgerRefusal(
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not "
            f"queued request(s) in {queue_path(run)}; recorded "
            f"{', '.join(done) if done else 'nothing'}")
    out = {"ids": done, "status": status, "recorded": len(done)}
    if len(done) == 1:
        out["id"] = done[0]
    return out


def _matches(req: dict, row: dict) -> bool:
    q = normalize(row.get("Query"))
    n = req["norm"]
    if not q or not n or not (q == n or n in q or q in n):
        return False
    cell = str(row.get("SubCap_ID") or "").strip().upper()
    if req.get("subcap"):
        return cell == req["subcap"]
    if req.get("category"):
        return cell.startswith(req["category"]) or not cell
    return True


def reconcile(run: runstate.Run, wb) -> dict:
    """Close OPEN requests from the Search_Log: a row through an enrichment
    tool whose query matches is SERVED when it kept anything, EMPTY when it
    returned nothing. The substrate decides, not the lane's report."""
    closed = {"SERVED": 0, "EMPTY": 0}
    rows = [r for r in wb.rows("Search_Log")
            if str(r.get("Tool") or "").strip().lower() in C.ENRICHMENT_TOOLS]
    for req in open_requests(run):
        hit = next((r for r in rows if _matches(req, r)), None)
        if hit is None:
            continue
        kept = int(hit.get("Kept") or 0) or int(hit.get("Hits") or 0)
        status = "SERVED" if kept else "EMPTY"
        record(run, req["id"], status,
               note=f"reconciled from Search_Log seq {hit.get('Seq')} ({hit.get('Tool')})",
               actor="engine.relay reconcile", tool=str(hit.get("Tool") or ""))
        closed[status] += 1
    return {"closed": closed, "still_open": len(open_requests(run))}


# ── the batch: what the connector holder runs, grouped ────────────────────

#: The two ways a batch can be grouped. `capability` is the default because
#: it is the grain a single subagent can hold: sibling cells under one
#: capability answer neighbouring diagnostic questions, so one prompt's
#: queries reinforce each other. `tool` is for a conductor that would rather
#: spin one subagent per connector.
GROUP_BYS = ("capability", "tool")

#: The relay's two servicing modes. See `drain_batch`.
RELAY_MODES = ("orchestrator", "lane")
DEFAULT_RELAY_MODE = "orchestrator"

#: WHICH CONNECTOR ANSWERS THIS QUERY — a deliberately tiny table.
#:
#: It exists to save the conductor a judgement call on a few hundred queries
#: a run, not to classify language. KEEP IT SMALL: a table that grows by
#: habit is one nobody can satisfy — every addition is a rule a lane must
#: now predict to get the connector it wanted, and the escape hatch already
#: exists, because a request that names its own `tool` wins outright. When a
#: proposal is wrong, the fix is the request's `tool` field, not a new word
#: here.
_PEOPLE_WORDS = ("cio", "cto", "chief", "head of", "leadership", "headcount",
                 "employees", "revenue", "founded")
_TECHNO_WORDS = ("uses", "platform", "vendor", "stack", "core banking", "crm",
                 "technograph")
DEFAULT_TOOL = "exa"


def _hits(query: str, words) -> bool:
    # Anchored at a word boundary and open at the end, so `technograph`
    # catches `technographic` and `stack` catches `stacks` without a second
    # entry in the table.
    q = " ".join(str(query or "").lower().split())
    return any(re.search(r"\b" + re.escape(w), q) for w in words)


def propose_tool(req) -> str:
    """The connector this request should be run through.

    A request that names an enrichment tool is honoured — the lane that
    wrote the query knows what it was reaching for, and the keyword table is
    a fallback, never an override. A tool outside `contract.ENRICHMENT_TOOLS`
    (`web_search`, a typo, a namespace) is ignored rather than refused: the
    relay exists BECAUSE the lane could not reach a connector, so a bare-web
    preference is not a preference the servicing tier can act on.
    """
    if isinstance(req, str):
        req = {"query": req}
    req = req or {}
    named = str(req.get("tool") or "").strip().lower()
    if named in C.ENRICHMENT_TOOLS:
        return named
    q = req.get("query") or ""
    if _hits(q, _PEOPLE_WORDS):
        return "clay"
    if _hits(q, _TECHNO_WORDS):
        return "vibe"
    return DEFAULT_TOOL


def capability_of(subcap: str) -> str:
    """`P1C1.1.1` and `P1C1.1.CU2` both belong to capability `P1C1.1`.

    Derived here rather than imported from `engine.brief`: the relay is the
    one module a conductor runs on its own, and a batch that cannot be
    written because the brief builder failed to import is a batch nobody
    services. `brief.capability_of` is the same two components; a test pins
    the two in agreement.
    """
    parts = [p for p in str(subcap or "").strip().upper().split(".") if p]
    return ".".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")


def _shq(s: str) -> str:
    """Single-quote for a shell. These commands get pasted; a query carrying
    an apostrophe that ends its own quote is a command that does something
    else."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def _merge_queries(reqs: list[dict]) -> list[dict]:
    """One entry per normalised query, carrying every request behind it.

    THE CROSS-CATEGORY DEDUPE. Two lanes that asked the same thing about two
    cells owe ONE connector call, one Search_Log row naming both cells and
    one record closing both requests. The rows already carry `norm`, so the
    identity is the queue's, not a second opinion."""
    out: dict[str, dict] = {}
    for r in reqs:
        key = r.get("norm") or normalize(r.get("query"))
        q = out.get(key)
        if q is None:
            q = {"query": r.get("query") or "", "norm": key, "request_ids": [],
                 "subcaps": [], "categories": [], "facet": None, "tool": None,
                 "falsifiers": [], "proves": [], "_named": None}
            out[key] = q
        q["request_ids"].append(r["id"])
        cell = str(r.get("subcap") or "").strip().upper()
        if cell and cell not in q["subcaps"]:
            q["subcaps"].append(cell)
        cat = str(r.get("category") or "").strip().upper()
        if cat and cat not in q["categories"]:
            q["categories"].append(cat)
        if not q["facet"] and r.get("facet"):
            q["facet"] = r["facet"]
        if r.get("falsifier") and r["falsifier"] not in q["falsifiers"]:
            q["falsifiers"].append(r["falsifier"])
        if r.get("proves") and r["proves"] not in q["proves"]:
            q["proves"].append(r["proves"])
        if q["_named"] is None and r.get("tool") in C.ENRICHMENT_TOOLS:
            q["_named"] = r["tool"]
    for q in out.values():
        q["tool"] = propose_tool({"query": q["query"], "tool": q.pop("_named")})
    return list(out.values())


def _commands(run: runstate.Run, q: dict) -> dict:
    rr = f"--run {run.run_id} --root {run.root}"
    parts = ["python3 -m engine.cli search", rr]
    if q["subcaps"]:
        # ONE call, one `--subcap` per cell: `append_search` writes a row per
        # cell (so `volley_status` sees each of them searched) and charges
        # the search-op ceiling once. One call per cell would charge it once
        # per cell for the same query.
        parts += [f"--subcap {c}" for c in q["subcaps"]]
        parts.append(f"--facet {q['facet'] or C.PRIMARY_FACET}")
    else:
        parts.append("--prelim")
    parts += [f"--tool {q['tool']}", f"--query {_shq(q['query'])}",
              "--hits N", "--kept K"]
    return {
        "command_search": " ".join(parts),
        "command_record": (f"python3 -m engine.relay record {rr} "
                           f"--ids {','.join(q['request_ids'])} "
                           f"--status SERVED|EMPTY|BLOCKED "
                           f"--tool {q['tool']} --note '…'"),
    }


def _group_key(q: dict, group_by: str) -> str:
    if group_by == "tool":
        return q["tool"]
    if q["subcaps"]:
        return capability_of(q["subcaps"][0])
    return (q["categories"] or ["RUN"])[0]


def _round_no(run: runstate.Run, out_dir: Path | None) -> int:
    if out_dir is not None:
        m = re.search(r"relay_r(\d+)$", Path(out_dir).name)
        if m:
            return int(m.group(1))
    n = 0
    while (run.qa_dir / f"relay_batch_r{n}.json").is_file():
        n += 1
    return n


def batch_prompt(run: runstate.Run, wb, key: str, tool: str,
                 queries: list[dict]) -> str:
    """ONE batch's prompt, self-contained and carrying nothing else.

    The conductor dispatches a FRESH in-process subagent per batch. Whatever
    else sits in this file is context that subagent pays for on every turn,
    and work it may do twice — so a batch names its own cells, its own
    queries and its own record commands, and no other batch's."""
    e = _entity(wb)
    cells = sorted({c for q in queries for c in q["subcaps"]})
    lines = [
        f"# Search relay — batch `{key}` — run `{run.run_id}`",
        "",
        f"Entity **{e['entity']}** ({e['sub_vertical'] or 'sub-vertical not set'}). "
        f"Run root `{run.root}`. Run every command below from `{SKILL_REL}`.",
        "",
        f"You hold the enrichment connectors. A research lane does not — they "
        f"bind once, at session start, in this session — so it emitted these "
        f"queries as `search_requests` rather than fabricating a result. "
        f"Work THIS batch and nothing else: no new research, no synthesis, "
        f"no score, no other cells.",
        "",
        f"**Connector for this batch: `{tool}`.** "
        f"Cells it bears on: {', '.join(f'`{c}`' for c in cells) or '(run-level, no cell)'}.",
        "",
        f"## The {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}",
        "",
    ]
    for i, q in enumerate(queries, 1):
        lines.append(f"### {i}. {q['query']}")
        lines.append("")
        lines.append(f"- cells: {', '.join(f'`{c}`' for c in q['subcaps']) or '(none — run-level)'}")
        lines.append(f"- facet: `{q['facet'] or C.PRIMARY_FACET}` · tool: `{q['tool']}` "
                     f"· requests: {', '.join(q['request_ids'])}")
        for f in q["falsifiers"]:
            lines.append(f"- falsifier (fire it when the query hits): {f}")
        for p in q["proves"]:
            lines.append(f"- what a hit would prove: {p}")
        lines += [
            "- log the search the moment it returns:",
            f"  ```\n  {q['command_search']}\n  ```",
            "- close the request(s):",
            f"  ```\n  {q['command_record']}\n  ```",
            "",
        ]
    rr = f"--run {run.run_id} --root {run.root}"
    lines += [
        "## For each query, in this order",
        "",
        f"1. Run it through `{tool}`. If the call is refused or the tool is "
        "not present, do NOT retry another way and do NOT run it through "
        "WebSearch instead: record it BLOCKED with the refusal text verbatim "
        "and move on. Never log a connector search you did not run.",
        "2. Run the `engine.cli search` line above, with `N`/`K` replaced by "
        "the real hit and kept counts (`--outcome '<one line>'` is welcome).",
        "3. Register every source you keep: "
        f"`python3 -m engine.cli evidence {rr} --subcap <cell> --source "
        "'<name>' --url <url> --tier <T1|T2|T3|T4> --excerpt '<50–500 "
        "verbatim characters>' [--published YYYY-MM-DD]`. Pass `--published` "
        "only when the source states a date — undated evidence is "
        "UNVERIFIED, never current.",
        "4. Run the `engine.relay record` line, with the status you actually "
        "got. EMPTY is an honest outcome (the connector ran and returned "
        "nothing usable); BLOCKED is a measured one and needs the refusal "
        "text; SERVED means at least one row was registered.",
        "",
        "## Refusals you will meet",
        "",
        f"- `engine.cli search` refuses a tool outside {list(C.SEARCH_TOOLS)} and a "
        "query carrying an unbound `{token}`.",
        "- `engine.cli evidence` refuses an excerpt outside 50–500 characters and "
        "a row that names no cell.",
        "- `engine.relay record` refuses BLOCKED without a note, and names any "
        "id it does not know while recording the rest.",
        "",
        "## Report",
        "",
        "Return ONLY this JSON: "
        '`{"served": n, "empty": n, "blocked": n, "blocked_reasons": ["…"]}`. '
        "Never invent a result; a request you did not reach stays OPEN and the "
        "driver will say so.",
    ]
    return "\n".join(lines) + "\n"


def _batch_md(run: runstate.Run, out: dict) -> str:
    lines = [f"# Relay batch r{out['round']} — run `{run.run_id}`", "",
             f"{out['requests']} open request(s) → {out['queries']} "
             f"deduplicated quer(y|ies) over {len(out['groups'])} batch(es), "
             f"grouped by {out['group_by']}.", ""]
    for g in out["groups"]:
        lines.append(f"## `{g['key']}` · tool `{g['tool']}` · "
                     f"{len(g['queries'])} quer(y|ies)")
        lines.append("")
        lines.append(f"Prompt: `{g['prompt_file']}`")
        lines.append("")
        for q in g["queries"]:
            lines.append(f"- {q['query']}  \n  cells "
                         f"{', '.join(q['subcaps']) or '(run-level)'} · "
                         f"ids {', '.join(q['request_ids'])}")
        lines.append("")
    return "\n".join(lines) + "\n"


def batch(run: runstate.Run, wb, *, group_by: str = "capability",
          categories: list[str] | None = None, out_dir: Path | None = None,
          round_no: int | None = None) -> dict:
    """The OPEN requests, deduplicated and grouped, written for the holder.

    Writes `07_qa/relay_batch_r<n>.json` (the index the conductor reads),
    a `.md` beside it (the same thing for a person), and one self-contained
    prompt per group under `briefs/relay_r<n>/<key>.md`. Dispatches nothing:
    the conductor spins one fresh in-process subagent per prompt, because
    those inherit its connectors and a headless child does not.
    """
    group_by = str(group_by or "capability").strip().lower()
    if group_by not in GROUP_BYS:
        raise ValueError(f"group_by {group_by!r} must be one of {GROUP_BYS}")
    want = {str(c).strip().upper() for c in categories} if categories else None
    reqs = [r for r in open_requests(run)
            if want is None or not r.get("category")
            or str(r["category"]).upper() in want]
    n = _round_no(run, out_dir) if round_no is None else int(round_no)
    out_dir = Path(out_dir) if out_dir is not None else (
        run.root / "briefs" / f"relay_r{n}")
    out: dict = {"round": n, "group_by": group_by, "run_id": run.run_id,
                 "root": str(run.root), "requests": len(reqs), "queries": 0,
                 "groups": [], "prompts": [], "batch_file": None,
                 "md_file": None, "out_dir": str(out_dir)}
    if not reqs:
        return out
    merged = _merge_queries(reqs)
    for q in merged:
        q.update(_commands(run, q))
    groups: dict[str, list[dict]] = {}
    for q in merged:
        groups.setdefault(_group_key(q, group_by), []).append(q)
    out["queries"] = len(merged)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in sorted(groups):
        qs = groups[key]
        tool = (key if group_by == "tool"
                else max({t: sum(1 for q in qs if q["tool"] == t) for t in
                          {q["tool"] for q in qs}}.items(),
                         key=lambda kv: (kv[1], kv[0]))[0])
        prompt = out_dir / f"{key}.md"
        prompt.write_text(batch_prompt(run, wb, key, tool, qs), encoding="utf-8")
        g = {"key": key, "tool": tool, "prompt_file": str(prompt),
             "requests": sum(len(q["request_ids"]) for q in qs),
             "queries": [{k: q[k] for k in
                          ("query", "request_ids", "subcaps", "facet", "tool",
                           "command_search", "command_record")} for q in qs]}
        out["groups"].append(g)
        out["prompts"].append({"key": key, "tool": tool,
                               "prompt_file": str(prompt),
                               "queries": len(qs), "requests": g["requests"]})
    bf = run.qa_dir / f"relay_batch_r{n}.json"
    bf.parent.mkdir(parents=True, exist_ok=True)
    out["batch_file"] = str(bf)
    out["md_file"] = str(bf.with_suffix(".md"))
    bf.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    bf.with_suffix(".md").write_text(_batch_md(run, out), encoding="utf-8")
    return out


# ── the drain brief ───────────────────────────────────────────────────────

def _entity(wb) -> dict:
    md = wb.metadata() if wb is not None else {}
    return {"entity": md.get("entity_name") or "?", "sub_vertical": md.get("sub_vertical") or ""}


def drain_brief(run: runstate.Run, wb, reqs: list[dict], category: str | None) -> str:
    e = _entity(wb)
    rr = f"--run {run.run_id} --root {run.root}"
    lines = [
        f"# Search relay — {category or 'run-level'} — run `{run.run_id}`",
        "",
        f"Entity **{e['entity']}** ({e['sub_vertical'] or 'sub-vertical not set'}). "
        f"Run root `{run.root}`. Run every command below from `{SKILL_REL}`.",
        "",
        "A category lane could not run these searches and emitted them as "
        "`search_requests` instead of fabricating. You hold the enrichment "
        "connectors its manifest names. Work every request below, nothing "
        "else — no new research, no synthesis, no score.",
        "",
        f"## Requests ({len(reqs)})",
        "",
    ]
    for r in reqs:
        lines.append(f"- **{r['id']}** · facet `{r.get('facet') or 'primary'}` · cell "
                     f"`{r.get('subcap') or '(none — use --prelim)'}` · preferred tool "
                     f"`{r.get('tool') or 'exa'}`")
        lines.append(f"  - query: {r['query']}")
        if r.get("falsifier"):
            lines.append(f"  - falsifier (fire it when the query hits): {r['falsifier']}")
        if r.get("proves"):
            lines.append(f"  - what a hit would prove: {r['proves']}")
    lines += [
        "",
        "## For EACH request, in this order",
        "",
        "1. Run the query through a connector — `mcp__Exa__web_search_exa` or "
        "`mcp__Tavily__tavily_search` (Clay only where your manifest allows "
        "and the request is about people or a company record). If the call is "
        "refused or the tool is not present, do NOT retry another way and do "
        "NOT run it through WebSearch instead: record it BLOCKED (step 4) with "
        "the refusal text verbatim, and move on.",
        "2. Log the search the moment it returns, with the tool that ran it: "
        f"`python3 -m engine.cli search {rr} --subcap <cell> --facet <facet> "
        "--tool exa --query '<query>' --hits N --kept K --outcome '<one line>'` "
        "(`--prelim` instead of `--subcap/--facet` when the request names no "
        "cell; `--tool tavily` / `--tool clay` when that is what ran).",
        "3. Register every source you keep: "
        f"`python3 -m engine.cli evidence {rr} --subcap <cell> --source '<name>' "
        "--url <url> --tier <T1|T2|T3|T4> --excerpt '<50–500 verbatim characters>' "
        "[--published YYYY-MM-DD]`. Pass `--published` only when the source "
        "states a date — undated evidence is UNVERIFIED, never current.",
        "4. Close the request: "
        f"`python3 -m engine.relay record {rr} --id <SR-id> --status "
        "SERVED|EMPTY|BLOCKED --note '<what happened>'`. EMPTY is an honest "
        "outcome (the connector ran and returned nothing usable); BLOCKED is a "
        "measured one and needs the refusal text; SERVED means at least one "
        "row was registered.",
        "",
        "## Refusals you will meet",
        "",
        f"- `engine.cli search` refuses a tool outside {list(C.SEARCH_TOOLS)} and a "
        "query carrying an unbound `{token}`.",
        "- `engine.cli evidence` refuses an excerpt outside 50–500 characters and "
        "a row that names no cell (use `--profile` only for institution-profile "
        "sources).",
        "- `engine.relay record` refuses BLOCKED without a note.",
        "",
        "## Report",
        "",
        "Return ONLY this JSON: "
        '`{"served": n, "empty": n, "blocked": n, "blocked_reasons": ["…"]}`. '
        "Never invent a result; a request you did not reach stays OPEN and the "
        "driver will say so.",
    ]
    return "\n".join(lines) + "\n"


def drain_batch(run: runstate.Run, wb, *, out_dir: Path,
                categories: list[str] | None = None,
                mode: str = DEFAULT_RELAY_MODE,
                group_by: str = "capability") -> dict:
    """Service the open requests — in one of two modes.

    `"orchestrator"` (the DEFAULT) writes the batch and its per-capability
    prompts and dispatches NOTHING, returning `{"lanes": 0, "pending": n,
    "batch_file": …}`. The conductor reads that index and spins one fresh
    in-process subagent per prompt, which inherits the session's connectors.
    This is the only arrangement that can work: connectors bind once, at
    session start, and a `claude -p` child is a different session with none
    of them — the measured cost of pretending otherwise was sixteen lane
    context floors a round (~290K tokens) to discover an absent tool.

    `"lane"` is the pre-2026-09-14 dispatch, kept as an explicit fallback:
    one `enrichment-web-specialist` lane per category with OPEN requests, as
    an `agent_run.py --batch` array whose rows carry a `label` so sixteen
    lanes of one agent keep sixteen transcripts. It is right only where the
    container itself holds the connectors.
    """
    mode = str(mode or "").strip().lower()
    if mode not in RELAY_MODES:
        raise ValueError(f"relay mode {mode!r} must be one of {RELAY_MODES}")
    out_dir = Path(out_dir)
    if mode == "orchestrator":
        b = batch(run, wb, group_by=group_by, categories=categories,
                  out_dir=out_dir)
        return {"mode": mode, "lanes": 0, "batch": None,
                "pending": b["requests"], "requests": b["requests"],
                "queries": b["queries"], "batch_file": b["batch_file"],
                "md_file": b["md_file"], "prompts": b["prompts"],
                "briefs": b["prompts"]}
    want = {str(c).upper() for c in categories} if categories else None
    groups: dict[str, list[dict]] = {}
    for r in open_requests(run):
        cat = str(r.get("category") or "").upper() or "RUN"
        if want is not None and cat != "RUN" and cat not in want:
            continue
        groups.setdefault(cat, []).append(r)
    if not groups:
        return {"batch": None, "lanes": 0, "requests": 0, "briefs": []}
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, briefs = [], []
    for cat, reqs in sorted(groups.items()):
        path = out_dir / f"relay_{cat}.md"
        path.write_text(drain_brief(run, wb, reqs, None if cat == "RUN" else cat),
                        encoding="utf-8")
        rows.append({"agent": DRAIN_AGENT, "prompt_file": str(path),
                     "label": f"{DRAIN_AGENT}@{cat}"})
        briefs.append({"category": cat, "prompt_file": str(path), "requests": len(reqs)})
    batch_path = out_dir / "batch.json"
    batch_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {"batch": str(batch_path), "lanes": len(rows),
            "requests": sum(b["requests"] for b in briefs), "briefs": briefs}


# ── heal: which half is broken, measured ─────────────────────────────────

def grants_check() -> dict:
    """Does `agent_run.ALLOWED` pre-approve every connector namespace? Read
    from the script itself, so this cannot disagree with what a child gets."""
    try:
        spec = importlib.util.spec_from_file_location("_agent_run_probe", AGENT_RUN)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)                       # type: ignore[union-attr]
        allowed = set(str(m.ALLOWED).split(","))
        missing = [ns for ns in CONNECTOR_NAMESPACES if ns not in allowed]
        return {"measured": True, "ok": not missing, "missing": missing}
    except Exception as e:                               # noqa: BLE001
        return {"measured": False, "ok": None, "missing": [],
                "note": f"could not read {AGENT_RUN.name}: {e.__class__.__name__}"}


#: The tier that HOLDS the enrichment connectors. Since the 2026-09-14
#: roster change they are bound in the orchestrator's session, not in a
#: headless lane's: a lane emits `search_requests` and the conductor
#: services them in batches, which is the only arrangement that can work —
#: connectors bind once, at session start, and a `claude -p` child of the
#: conductor is a different session with none of them.
CONNECTOR_HOLDER = "research-conductor"


def manifest_check(lane: str) -> dict:
    """Which connector tools the lane's own manifest declares.

    `ok` answers "is this manifest as it should be", which since the roster
    change is NOT "does it declare a connector". A research lane that
    declares none is correct; what would be broken is the HOLDER declaring
    none, because then nobody in the run can service what the lane emits.
    So a lane's `ok` is judged against the holder's manifest, and the
    `manifest` heal re-targets the human who must fix it.
    """
    hits = list(AGENTS_DIR.rglob(f"{lane}.md")) if AGENTS_DIR.is_dir() else []
    if not hits:
        return {"path": None, "declares": [], "ok": False,
                "note": f"no manifest named {lane}.md under {AGENTS_DIR}"}
    head = hits[0].read_text(encoding="utf-8", errors="replace")[:6000]
    m = re.search(r"^tools:\s*(.+)$", head, re.M)
    tools = [t.strip() for t in (m.group(1) if m else "").split(",") if t.strip()]
    declares = [t for t in tools if any(t.startswith(ns + "__") for ns in CONNECTOR_NAMESPACES)]
    if declares or lane == CONNECTOR_HOLDER:
        return {"path": str(hits[0]), "declares": declares,
                "ok": bool(declares), "holder": lane}
    # A lane with no connector is the contract. Whether the RUN can enrich
    # is then a question about the holder, so ask it there.
    holder = manifest_check(CONNECTOR_HOLDER)
    return {"path": str(hits[0]), "declares": declares,
            "ok": bool(holder["declares"]), "holder": CONNECTOR_HOLDER,
            "holder_declares": holder["declares"],
            "note": (None if holder["declares"] else
                     f"neither {lane}.md nor the holder {CONNECTOR_HOLDER}.md "
                     f"declares a connector tool, so nothing in this run can "
                     f"service a search request")}


def transcript_connector_witness(transcript: Path) -> dict:
    """What the transcript proves about connector use: calls attempted by
    namespace, and refusals (a tool_result carrying a blocked marker)."""
    out = {"attempted": 0, "refused": 0, "tools": {}, "refusals": [], "read": False}
    if not transcript.is_file():
        return out
    out["read"] = True
    for raw in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        content = (ev.get("message") or {}).get("content") or []
        if ev.get("type") == "assistant":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name = str(b.get("name") or "")
                    ns = next((n for n in CONNECTOR_NAMESPACES if name.startswith(n + "__")), None)
                    if ns:
                        out["attempted"] += 1
                        out["tools"][ns] = out["tools"].get(ns, 0) + 1
        elif ev.get("type") == "user":
            for b in content:
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                txt = b.get("content")
                if isinstance(txt, list):
                    txt = " ".join(str(x.get("text") or "") for x in txt if isinstance(x, dict))
                txt = str(txt or "")
                if any(mk in txt for mk in BLOCKED_MARKERS):
                    out["refused"] += 1
                    if len(out["refusals"]) < 3:
                        out["refusals"].append(" ".join(txt.split())[:240])
    return out


def _baseline_short(run) -> str:
    """The required connector families the run's baseline does NOT hold, or
    "" when it holds them all or no baseline was ever written.

    An absent baseline returns "" on purpose: it means nobody measured, which
    is not evidence that the connector is unbound. The preflight is what makes
    the baseline exist; this only reads it.
    """
    try:
        import json as _json
        import sys as _sys
        _sys.path.insert(0, str(PLUGIN / "scripts"))
        import connector_contract as cc                        # noqa: PLC0415
        path = cc.baseline_path(str(run.root))
        if not Path(path).is_file():
            return ""
        held = _json.loads(Path(path).read_text()).get("mcp_tools") or []
        out = cc.check(held)
        if out["ok"]:
            return ""
        return f"the run's connector baseline is short of {', '.join(out['missing'])}"
    except Exception:                                          # noqa: BLE001
        return ""


def heal_plan(run: runstate.Run, wb, category: str, *, logs_dir: Path | None = None) -> dict:
    """For one category: the measured enrichment status and, when it shows
    no connector search, WHICH half is broken and what the fresh lane must do.
    `heal` is None when nothing needs healing."""
    cat = str(category).upper()
    lane = f"research-{cat.lower()}-producer"
    logs = Path(logs_dir) if logs_dir else run.root / LOGS_DIR
    st = L.enrichment_status(wb, cat)
    tr = transcript_connector_witness(logs / f"{lane}.jsonl")
    manifest = manifest_check(lane)
    grants = grants_check()
    n_open = len(open_requests(run, cat))
    heal, reason = None, ""
    if st["enrichment_searches"] > 0:
        reason = (f"{st['enrichment_searches']} of {st['searches']} search(es) ran through "
                  f"{', '.join(st['enrichment_tools'])}")
    elif st["searches"] == 0:
        reason = "no searches logged for the category; the floors gate owns this"
    elif not manifest["ok"]:
        heal, reason = "manifest", (manifest.get("note") or
                                     f"{Path(manifest['path']).name} declares no connector tool")
    elif grants["measured"] and not grants["ok"]:
        heal, reason = "grants", f"agent_run.ALLOWED lacks {', '.join(grants['missing'])}"
    elif tr["refused"]:
        heal, reason = "grants", (f"{tr['refused']} connector call(s) refused in the transcript: "
                                  f"{(tr['refusals'] or ['(text not captured)'])[0][:160]}")
    elif tr["attempted"]:
        heal, reason = "logging", (f"{tr['attempted']} connector call(s) witnessed "
                                   f"({', '.join(sorted(tr['tools']))}) but every Search_Log row "
                                   f"names {', '.join(st['tools']) or 'nothing'}")
    elif _baseline_short(run):
        # THE CASE THAT HAD NO VERDICT. An UNBOUND connector produces no
        # tool_use to witness and no refusal marker, so manifest and grants
        # both pass and every branch above falls through to "instruction" —
        # which tells a fresh lane "you never ATTEMPTED a connector; fire one"
        # about a tool that does not exist in this container. Measured
        # 2026-09-12: that is a loop, and each turn of it costs a full lane.
        # The run's own connector baseline is what tells the two apart.
        heal, reason = "unbound", (
            f"{_baseline_short(run)}; {st['searches']} search(es) all through "
            f"{', '.join(st['tools']) or 'nothing'}, and the transcript shows "
            f"neither an attempt nor a refusal — the tool is absent, not refused")
    else:
        heal, reason = "instruction", (f"{st['searches']} search(es), all through "
                                       f"{', '.join(st['tools']) or 'nothing'}; no connector "
                                       f"call in the transcript"
                                       + ("" if tr["read"] else " (no transcript to read)"))
    return {"category": cat, "lane": lane, "heal": heal, "reason": reason,
            "instruction": HEAL_INSTRUCTIONS.get(heal) if heal else None,
            "status": st, "transcript": tr, "manifest": manifest, "grants": grants,
            "open_requests": n_open}


# ── command line ─────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.relay", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        p.add_argument("--json", action="store_true")
        return p

    h = common(sub.add_parser("harvest", help="queue the search_requests the lanes emitted"))
    h.add_argument("--category", help="comma-separated; default: every research lane transcript")
    h.add_argument("--logs")
    ls = common(sub.add_parser("list"))
    ls.add_argument("--status", choices=REQUEST_STATUSES)
    ls.add_argument("--category")
    bt = common(sub.add_parser(
        "batch", help="group the open requests for the session that holds the "
                      "connectors: one prompt per capability, dispatched by nobody"))
    bt.add_argument("--group-by", choices=GROUP_BYS, default="capability")
    bt.add_argument("--category", help="comma-separated; default: every open request")
    bt.add_argument("--out-dir", help="default: <run>/briefs/relay_r<n>")
    rc = common(sub.add_parser("record", help="close one request, or many"))
    rc.add_argument("--id", help="one request id")
    rc.add_argument("--ids", help="comma-separated request ids — one search "
                                  "closes every request that asked for it")
    rc.add_argument("--status", required=True, choices=CLOSING_STATUSES)
    rc.add_argument("--note", default="")
    rc.add_argument("--actor", default="")
    rc.add_argument("--tool")
    common(sub.add_parser("reconcile", help="close OPEN requests from the Search_Log"))
    common(sub.add_parser("state"))
    d = common(sub.add_parser("drain-brief", help="write the drain batch for the specialist"))
    d.add_argument("--out-dir", required=True)
    d.add_argument("--category")
    en = common(sub.add_parser("enrichment", help="per-category connector usage, from the Search_Log"))
    en.add_argument("--category")
    he = common(sub.add_parser("heal", help="which half is broken for a category with no connector search"))
    he.add_argument("--category", required=True)
    he.add_argument("--logs")
    a = ap.parse_args(argv)

    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    cats = [c.strip() for c in (getattr(a, "category", None) or "").split(",") if c.strip()] or None

    def emit(obj, text=None):
        if a.json or text is None:
            print(json.dumps(obj, indent=2, default=str))
        else:
            print(text)
        return 0

    if a.cmd == "harvest":
        out = harvest(run, cats, logs_dir=Path(a.logs) if a.logs else None)
        return emit(out, f"harvested {out['harvested']} new request(s) ({out['seen']} seen) → {out['queue']}")
    if a.cmd == "list":
        rows = [r for r in requests(run).values()
                if (not a.status or r["status"] == a.status)
                and (not cats or str(r.get("category") or "").upper() in cats)]
        return emit(rows, "\n".join(f"{r['id']}  {r['status']:<7} {r.get('category') or '-':<5} "
                                    f"{r.get('subcap') or '-':<12} {r['query'][:90]}" for r in rows)
                    or "no requests queued")
    if a.cmd == "batch":
        out = batch(run, run.open(), group_by=a.group_by, categories=cats,
                    out_dir=Path(a.out_dir) if a.out_dir else None)
        return emit(out, f"{out['requests']} open request(s) → {out['queries']} "
                         f"query(ies) over {len(out['groups'])} batch(es) → "
                         f"{out['batch_file'] or 'nothing to write'}")
    if a.cmd == "record":
        ids = ([i.strip() for i in (a.ids or "").split(",") if i.strip()]
               + ([a.id] if a.id else []))
        if not ids:
            ap.error("record needs --id or --ids")
        return emit(record(run, ids, a.status, note=a.note, actor=a.actor,
                           tool=a.tool))
    if a.cmd == "reconcile":
        return emit(reconcile(run, run.open()))
    if a.cmd == "state":
        return emit(state(run))
    if a.cmd == "drain-brief":
        return emit(drain_batch(run, run.open(), out_dir=Path(a.out_dir), categories=cats))
    if a.cmd == "enrichment":
        wb = run.open()
        from .brief import category_of
        want = cats or sorted({category_of(c) for c in wb.selected_subcaps()})
        return emit([L.enrichment_status(wb, c) for c in want])
    if a.cmd == "heal":
        return emit(heal_plan(run, run.open(), cats[0], logs_dir=Path(a.logs) if a.logs else None))
    return 2


if __name__ == "__main__":
    sys.exit(main())
