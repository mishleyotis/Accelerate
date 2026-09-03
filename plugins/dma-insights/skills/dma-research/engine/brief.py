#!/usr/bin/env python3
"""The orchestration layer: what one agent hands the next, and what a run
already knows.

    python3 -m engine.brief dispatch  --run R --category P1C1 [--out FILE] [--json]
    python3 -m engine.brief batch     --run R [--out-dir DIR] [--only P1C1,P2C3]
    python3 -m engine.brief shared    --run R [--json]
    python3 -m engine.brief reuse     --run R --subcap P1C1.1.1
    python3 -m engine.brief handback  --run R --category P1C1 [--json]

REPORTED 2026-09-03 by the engagement owner: "There is no orchestration
existing between the subagents and main agents. Ensure efficient context
management and information sharing where needed. As they work independently,
they should also have enough context of the compacted data they have
collected to avoid redoing."

WHAT WAS ACTUALLY WRONG, measured in this repo rather than assumed:

  * The conductor dispatched each of the sixteen category researchers with
    "the run id, the root, and nothing else (the workbook carries the
    rest)". That is the token-safe extreme of a bad choice: the alternative
    on offer was pasting context into the prompt, which is the token bleed.
    Neither is a brief, so every producer opened its category by reading
    whatever it thought to read.
  * `orient` carries PRELIM's findings (AUD, 2026-08-31) — the run's shared
    BACKGROUND. It carries nothing about what the run has learned SINCE:
    fifteen siblings are working the same entity in parallel and a producer
    cannot see one fact any of them registered.
  * `memory.status` reports notebook COUNTS. A producer whose context
    compacted gets a number, not its own material, so it re-searches what
    it already found and wrote down.
  * Nothing measured whether a registered evidence row was ever CONSOLIDATED
    into the cell it names. The register is run-wide and rows carry
    `SubCap_IDs`; a row banked by P1C1 naming a P2C1 cell was invisible to
    P2C1, which then closed that cell as empty. That is the mechanism behind
    the owner's other complaint — "limited evidence is consolidated in most
    runs making the entire assessment very evidence deficient" — and it is
    not a prompting failure, it is a missing read.

WHAT THIS MODULE IS. Four bounded views, all DERIVED from the workbook, so
none of them can become a second source of truth that drifts from the
substrate (the AUD-0001 settlement: sheets are the record). Nothing here
writes a sheet.

  `shared`    what the run knows, run-wide: the estate by layer, the named
              leaders, the peer set, the timeline span, which source
              identities are already registered, the open contradictions,
              and the per-category state of play. One read, ~2 KB.
  `reusable`  for one cell: the registered rows that NAME it and it does not
              cite, then the rows naming a capability sibling. A producer's
              first move on a cell is now free.
  `dispatch`  the packet a category producer starts from: shared, its own
              worklist with the volleys each open cell still owes, the
              reusable evidence per open cell, its notebook digest (its own
              compacted state, so a resumed lane does not redo), the budget
              left before the checkpoint wall, and the pinned template
              binding. Bounded by BRIEF_CHAR_CEILING and measured on the
              packet itself.
  `handback`  what the category established, computed from its sheets rather
              than reported in prose: closed cells, declared absences,
              evidence banked, tools used, what is still open, and the leads
              that belong to OTHER categories. The conductor reads this
              instead of re-reading the workbook, and it is the same shape
              whether the lane succeeded, died or lied.

THE ENFORCEMENT IS NOT HERE. A view nobody must read is a view nobody
reads, so the refusals live where the work lands: `ledger.declare_absence`
refuses a cell the register already names, and the floors gate carries
`absence_over_evidence` (blocking) and `evidence_unattached` (advisory).
This module is what an agent reads to satisfy them.
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import sys
from pathlib import Path

from . import contract as C
from . import ledger as L
from . import runstate
from .workbook import RunWorkbook

#: A dispatch packet must fit the top of a turn beside the agent's own
#: manifest. `orient`'s card ceiling is 3200 chars for ONE cell; a category
#: packet covers the category, so it gets twice that and is measured the
#: same way — reported on the packet, and trimmed by dropping the lowest-
#: value rows rather than by silently truncating a field.
BRIEF_CHAR_CEILING = 6400

#: How many reusable rows a packet offers per open cell. The point is to
#: make the producer's first move free, not to ship the register.
REUSE_PER_CELL = 3

#: How many open cells the packet details. Beyond this it reports the count
#: and the producer asks `orient` for the next card, which is the paged
#: reader that already exists.
CELLS_DETAILED = 8


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _ids(v) -> list[str]:
    out = []
    for part in str(v or "").replace(";", ",").split(","):
        got = part.strip().split(":")[0]
        if got and got != C.NO_EVIDENCE:
            out.append(got)
    return out


def capability_of(subcap: str) -> str:
    """`P1C1.1.1` and `P1C1.1.CU2` both belong to capability `P1C1.1`.

    The capability is the grain at which two cells are close enough that one
    cell's source is worth offering to the other — a sibling under the same
    capability answers a neighbouring diagnostic question, which is exactly
    the reuse the run keeps paying twice for.
    """
    parts = _clean(subcap).split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else _clean(subcap)


def category_of(subcap: str) -> str:
    return _clean(subcap).split(".")[0]


# ── what the run knows, once ─────────────────────────────────────────────

def shared(wb: RunWorkbook) -> dict:
    """Run-wide state, derived. The one read a producer makes before its own.

    Everything here is a FACT the run has already paid for: an estate row, a
    named person, a peer, a registered source identity, a contradiction
    somebody logged. No prose — the argument behind any of it is one
    `Report_Narrative` read away, and a packet that carries arguments is a
    packet nobody finishes reading.
    """
    md = wb.metadata()
    register = wb.evidence_index()

    by_layer: dict[str, list[str]] = {}
    for r in wb.rows("Tech_Register"):
        layer = _clean(r.get("Layer")).upper()
        prod = _clean(r.get("Product"))
        if layer and prod:
            by_layer.setdefault(layer, []).append(
                f"{prod} [{_clean(r.get('Status')) or 'UNKNOWN'}]")

    hosts: dict[str, int] = {}
    for row in register.values():
        url = _clean(row.get("Source_URL"))
        host = url.split("//")[-1].split("/")[0].lower() if url else ""
        key = host or _clean(row.get("Source_Name")).lower()
        if key:
            hosts[key] = hosts.get(key, 0) + 1

    contradictions = []
    for r in wb.scoring_rows():
        got = _clean(r.get("DQ_Contradicts"))
        disp = _clean(r.get("Contradiction_Disposition"))
        if got and not got.upper().startswith(("NOT_RUN", "NO_FINDING")) \
                and not disp:
            contradictions.append(_clean(r.get("SubCap_ID")))

    cats: dict[str, dict] = {}
    for cat in sorted({category_of(c) for c in wb.selected_subcaps()}):
        wl = L.worklist(wb, cat)
        cats[cat] = {k: (len(v) if isinstance(v, (list, tuple, set)) else v)
                     for k, v in wl.items() if k != "category"}

    return {
        "run_id": md.get("run_id"),
        "entity": md.get("entity_name"),
        "sub_vertical": md.get("sub_vertical"),
        "evidence_mode": md.get("evidence_mode"),
        "stage": C.stage_of(md),
        "template_binding": _clean(md.get("template_binding")) or None,
        "estate_by_layer": by_layer,
        "layers_searched_empty": sorted(
            lay for lay, rows in by_layer.items()
            if rows and all("[ABSENT]" in r for r in rows)),
        "peers": sorted({n.strip() for r in wb.rows("Peer_Benchmarks")
                         for n in str(r.get("Peer_Names") or "").split(",")
                         if n.strip()}),
        "evidence_rows": len(register),
        "source_identities": sorted(hosts, key=lambda h: (-hosts[h], h))[:12],
        "searches_fired": len([s for s in wb.rows("Search_Log")
                               if _clean(s.get("Query"))]),
        "open_contradictions": contradictions[:12],
        "categories": cats,
    }


# ── the evidence the run already holds for a cell ────────────────────────

def reusable(wb: RunWorkbook, subcap: str, *, register: dict | None = None) -> dict:
    """Registered rows this cell could cite and does not.

    `names_this_cell` is the strong case and the one the gate enforces: the
    register itself says the row is about this cell. A cell closing empty
    while one of these exists is the run failing to consolidate what it
    bought, which is what `absence_over_evidence` refuses.

    `capability_siblings` is the weaker, still valuable case: a source
    registered against a neighbouring cell under the same capability, which
    a producer should READ before searching. Offered, never asserted — the
    producer decides whether the excerpt answers its own question, and the
    ledger's excerpt rules apply either way.
    """
    subcap = _clean(subcap)
    row = wb.scoring_row(subcap)
    cited = set(_ids(row.get("Evidence_IDs")) if row else [])
    cap = capability_of(subcap)
    mine, sibs = [], []
    # `register` is passed in by the callers that ask about many cells
    # (`unattached`, the gate, a dispatch packet): `evidence_index` walks
    # every row to build its dict, and rebuilding it per cell made a
    # category-wide read quadratic in the register for no reason.
    for eid, ev in sorted((register if register is not None
                           else wb.evidence_index()).items()):
        named = [_clean(s) for s in _ids(ev.get("SubCap_IDs"))]
        item = {
            "e_id": eid,
            "source": _clean(ev.get("Source_Name")),
            "tier": _clean(ev.get("Tier")),
            "published": _clean(ev.get("Date_Published")) or None,
            "excerpt": _clean(ev.get("Excerpt"))[:180],
        }
        if subcap in named:
            if eid not in cited:
                mine.append(item)
        elif any(capability_of(n) == cap for n in named):
            item["registered_against"] = ", ".join(
                n for n in named if capability_of(n) == cap)[:60]
            sibs.append(item)
    return {
        "subcap": subcap,
        "name": C.subcap_names().get(subcap) or None,
        "cites_now": sorted(cited),
        "names_this_cell": mine,
        "capability_siblings": sibs[:REUSE_PER_CELL],
        "read_before_searching": bool(mine or sibs),
    }


def unattached(wb: RunWorkbook, category: str | None = None) -> list[dict]:
    """Cells the register names that do not cite the row naming them.

    The run paid for the source, the source says which cell it is about, and
    the cell does not carry it. Computed for the whole run or one category.
    """
    out = []
    register = wb.evidence_index()
    for r in wb.scoring_rows():
        cell = _clean(r.get("SubCap_ID"))
        if not cell or (category and not cell.startswith(category)):
            continue
        got = reusable(wb, cell, register=register)
        if got["names_this_cell"]:
            out.append({
                "subcap": cell,
                "e_ids": [i["e_id"] for i in got["names_this_cell"]],
                "declared_absent": L.is_declared_absent(r),
                "synthesised": bool(_clean(r.get("Dominant_Claim"))),
            })
    return out


# ── an agent's own compacted state ───────────────────────────────────────

def notebook_digest(run: runstate.Run, category: str, *,
                    limit: int = 12) -> dict:
    """What THIS lane already wrote down, compacted.

    `memory.status` answers "how many notes" and a resumed producer needs
    "what did I find" — the difference between a lane that continues and a
    lane that starts again. Entries are the notebook's own parse, trimmed to
    subject and one clause, newest first, with the BLOCKED ones surfaced
    first because those are the ones still owed something.
    """
    from . import memory
    path = memory.memory_path(run, category)
    if not path.exists():
        return {"category": category, "notes": 0, "entries": [],
                "note": "no notebook yet — this lane has written nothing"}
    entries = memory.parse(path)
    ranked = sorted(
        entries,
        key=lambda e: (0 if str(e.get("status")) == "BLOCKED" else 1,))
    out = []
    for e in ranked[:limit]:
        f = e.get("fields") or {}
        # The gist is whatever the note actually carried, in the order a
        # reader would want it: the reason it is blocked, then the material,
        # then the thought. `blocked_reason` is written by consolidation.
        gist = next((_clean(f[k]) for k in
                     ("blocked_reason", "excerpt", "anchor_quote", "note",
                      "lead", "claim", "source_name")
                     if _clean(f.get(k))), "")
        out.append({
            "status": e.get("status"),
            "subcap": e.get("subcap"),
            "facet": e.get("facet"),
            "kind": _clean(f.get("kind")) or None,
            "gist": gist[:200],
        })
    return {
        "category": category,
        "notes": len(entries),
        "blocked": len([e for e in entries
                        if str(e.get("status")) == "BLOCKED"]),
        "consolidated": len([e for e in entries
                             if str(e.get("status")) == "CONSOLIDATED"]),
        "entries": out,
        "note": ("these are YOUR notes from earlier in this run — read them "
                 "before searching anything again"),
    }


# ── the packet ───────────────────────────────────────────────────────────

def dispatch(wb: RunWorkbook, category: str, *,
             run: runstate.Run | None = None) -> dict:
    """The bounded packet one category producer starts from."""
    category = _clean(category).upper()
    cells = [c for c in wb.selected_subcaps() if c.startswith(category)]
    if not cells:
        raise ValueError(
            f"{category} carries no selected subcapability in this run "
            f"(categories in scope: "
            f"{', '.join(sorted({category_of(c) for c in wb.selected_subcaps()}))})")

    wl = L.worklist(wb, category)
    searches = wb.rows("Search_Log")
    open_states = ("pending", "in_volley", "searched_empty", "volleyed")
    open_cells: list[str] = []
    for state in open_states:
        for c in wl.get(state) or []:
            got = c if isinstance(c, str) else _clean(
                (c or {}).get("subcap") or (c or {}).get("SubCap_ID"))
            if got and got not in open_cells:
                open_cells.append(got)

    detail = []
    register = wb.evidence_index()
    for cell in open_cells[:CELLS_DETAILED]:
        vs = L.volley_status(wb, cell, searches)
        got = reusable(wb, cell, register=register)
        detail.append({
            "subcap": cell,
            "name": C.subcap_names().get(cell) or None,
            "volleys_owed": vs["missing"],
            "volleys_fired": vs["fired"],
            "tools_used": vs["tools"],
            "already_registered_for_this_cell": [
                {"e_id": i["e_id"], "source": i["source"],
                 "excerpt": i["excerpt"][:120]}
                for i in got["names_this_cell"][:REUSE_PER_CELL]],
            "capability_siblings_worth_reading": [
                {"e_id": i["e_id"], "source": i["source"],
                 "registered_against": i.get("registered_against")}
                for i in got["capability_siblings"]],
        })

    stats = L.stats(wb)
    packet = {
        "category": category,
        "agent": f"research-{category.lower()}-producer",
        "cells_in_scope": len(cells),
        "shared": shared(wb),
        "worklist": {k: (len(v) if isinstance(v, (list, tuple, set)) else v)
                     for k, v in wl.items() if k != "category"},
        "open_cells": len(open_cells),
        "work_next": detail,
        "budget": {
            "searches_since_checkpoint": stats["search_ops_since_checkpoint"],
            "ceiling": stats["search_op_ceiling"],
            "checkpoint_required": stats["checkpoint_required"],
            "note": ("at the ceiling: `runstate.checkpoint(wb, '<where you "
                     "got to>')` then continue — the wall is per conversation"),
        },
        "unattached_evidence": unattached(wb, category),
        "rules": [
            "read `already_registered_for_this_cell` BEFORE searching: the "
            "run has already paid for those rows and the cell does not cite "
            "them yet",
            "every askable volley needs a logged search for THAT cell "
            "(`volleys_owed` is what is still missing)",
            "an empty cell closes ONLY through `engine.cli absence` — and it "
            "is refused while the register names the cell",
            "note as you go (`engine.memory note`); the notebook is what "
            "survives a compaction",
        ],
    }
    if run is not None:
        packet["your_notes"] = notebook_digest(run, category)
    packet["packet_chars"] = len(json.dumps(packet, default=str))
    packet["packet_ceiling"] = BRIEF_CHAR_CEILING
    if packet["packet_chars"] > BRIEF_CHAR_CEILING:
        # Trim the detailed cells rather than a field: a half-written field
        # reads as a complete one, and `orient` is the paged reader for the
        # cells this drops.
        keep = max(1, CELLS_DETAILED // 2)
        packet["work_next"] = packet["work_next"][:keep]
        packet["trimmed"] = (
            f"detail trimmed to {keep} cell(s) to stay under the packet "
            f"ceiling; `engine.cli orient --category {category}` serves the "
            f"rest one card at a time")
        packet["packet_chars"] = len(json.dumps(packet, default=str))
    return packet


def as_markdown(packet: dict) -> str:
    """The packet as a prompt file — what `agent_run.py --batch` delivers.

    JSON is the contract and markdown is the delivery: a model reads a
    prompt, and a prompt that is a JSON blob spends its first tokens
    parsing. Both come from the same object, so they cannot disagree.
    """
    s = packet["shared"]
    lines = [
        f"# {packet['category']} — dispatch brief",
        "",
        f"Run `{s['run_id']}` · entity **{s['entity']}** "
        f"({s.get('sub_vertical') or 'sub-vertical not set'}, "
        f"{s.get('evidence_mode') or 'mode not set'} evidence) · "
        f"stage {s['stage']}.",
        "",
        "## What the run already knows",
        "",
        f"- Evidence registered so far: **{s['evidence_rows']}** rows over "
        f"{len(s['source_identities'])} source identities; "
        f"{s['searches_fired']} searches fired.",
    ]
    if s["estate_by_layer"]:
        for lay in sorted(s["estate_by_layer"]):
            lines.append(f"- Estate {lay}: "
                         + "; ".join(s["estate_by_layer"][lay][:6]))
    if s["layers_searched_empty"]:
        lines.append(f"- Searched and EMPTY (a result, not a gap — do not "
                     f"re-run): {', '.join(s['layers_searched_empty'])}")
    if s["peers"]:
        lines.append(f"- Peer set: {', '.join(s['peers'][:8])}")
    if s["open_contradictions"]:
        lines.append(f"- Contradictions logged and undisposed: "
                     f"{', '.join(s['open_contradictions'][:6])}")
    lines += ["", "## Your category", "",
              f"{packet['cells_in_scope']} cell(s) in scope · "
              f"{packet['open_cells']} open · worklist "
              + ", ".join(f"{k} {v}" for k, v in
                          sorted(packet["worklist"].items())),
              ""]
    if packet.get("your_notes", {}).get("notes"):
        n = packet["your_notes"]
        lines += [f"### Your own notes from earlier in this run "
                  f"({n['notes']}, {n['blocked']} blocked)", ""]
        for e in n["entries"]:
            lines.append(f"- [{e['status']}] {e['subcap']} · {e['facet']}: "
                         f"{e['gist']}")
        lines.append("")
    lines += ["### Work next", ""]
    for d in packet["work_next"]:
        lines.append(f"**{d['subcap']} — {d['name'] or 'unnamed'}**")
        if d["volleys_owed"]:
            lines.append(f"  - volleys still owed: "
                         f"{', '.join(d['volleys_owed'])}")
        for i in d["already_registered_for_this_cell"]:
            lines.append(f"  - ALREADY REGISTERED for this cell, not yet "
                         f"cited: {i['e_id']} ({i['source']}) — "
                         f"{i['excerpt']}")
        for i in d["capability_siblings_worth_reading"]:
            lines.append(f"  - sibling source worth reading: {i['e_id']} "
                         f"({i['source']}, registered against "
                         f"{i['registered_against']})")
        lines.append("")
    if packet["unattached_evidence"]:
        lines += ["### Evidence this run bought and never consolidated", ""]
        for u in packet["unattached_evidence"][:8]:
            lines.append(f"- {u['subcap']}: {', '.join(u['e_ids'])}"
                         + (" — and the cell is DECLARED ABSENT, which the "
                            "gate refuses" if u["declared_absent"] else ""))
        lines.append("")
    b = packet["budget"]
    lines += [
        "### Budget",
        "",
        f"- {b['searches_since_checkpoint']} of {b['ceiling']} searches "
        f"since the last checkpoint"
        + (" — **checkpoint before your next search**"
           if b["checkpoint_required"] else ""),
        "",
        "### Rules",
        "",
    ]
    lines += [f"{i + 1}. {r}" for i, r in enumerate(packet["rules"])]
    if packet.get("trimmed"):
        lines += ["", f"_{packet['trimmed']}_"]
    return "\n".join(lines) + "\n"


def batch(wb: RunWorkbook, *, run: runstate.Run | None = None,
          out_dir: Path, only: list[str] | None = None) -> dict:
    """A prompt file per category plus the `agent_run.py --batch` array.

    The conductor's dispatch becomes one command over a file it did not
    compose, which is the point: a hand-written prompt is where context
    either goes missing or goes twice.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cats = sorted({category_of(c) for c in wb.selected_subcaps()})
    if only:
        want = {_clean(c).upper() for c in only}
        cats = [c for c in cats if c in want]
    rows, wrote = [], []
    for cat in cats:
        packet = dispatch(wb, cat, run=run)
        path = out_dir / f"{cat}.md"
        path.write_text(as_markdown(packet), encoding="utf-8")
        (out_dir / f"{cat}.json").write_text(
            json.dumps(packet, indent=2, default=str), encoding="utf-8")
        rows.append({"agent": packet["agent"], "prompt_file": str(path)})
        wrote.append({"category": cat, "prompt_file": str(path),
                      "chars": packet["packet_chars"],
                      "open_cells": packet["open_cells"]})
    batch_path = out_dir / "batch.json"
    batch_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {"batch": str(batch_path), "lanes": len(rows), "briefs": wrote,
            "dispatch": (f"python3 plugins/dma-insights/scripts/agent_run.py "
                         f"--batch {batch_path} --stream")}


# ── what a lane hands back ───────────────────────────────────────────────

def handback(wb: RunWorkbook, category: str) -> dict:
    """What the category established, computed from its sheets.

    The conductor reads THIS instead of re-reading the workbook or trusting
    a lane's prose. Its shape does not depend on the lane having behaved: a
    lane that died mid-cell and a lane that reported success produce the
    same fields, and the numbers come from the substrate either way.

    `leads_for_other_categories` is the half that makes sixteen parallel
    lanes one run: a source this category registered that NAMES a cell in
    another category. Without it that row sits in the register until someone
    happens to look, and the other category searches for it again.
    """
    category = _clean(category).upper()
    cells = [c for c in wb.selected_subcaps() if c.startswith(category)]
    register = wb.evidence_index()
    closed, absent, open_cells, items = [], [], [], 0
    for cell in cells:
        r = wb.scoring_row(cell) or {}
        eids = _ids(r.get("Evidence_IDs"))
        items += len(eids)
        if L.is_declared_absent(r):
            absent.append(cell)
        elif _clean(r.get("Dominant_Claim")):
            closed.append(cell)
        else:
            open_cells.append(cell)

    mine = {c: True for c in cells}
    leads: dict[str, list[str]] = {}
    for eid, ev in register.items():
        named = [_clean(s) for s in _ids(ev.get("SubCap_IDs"))]
        if not any(n in mine for n in named):
            continue
        for n in named:
            other = category_of(n)
            if other and other != category:
                leads.setdefault(other, [])
                if eid not in leads[other]:
                    leads[other].append(eid)

    searches = [s for s in wb.rows("Search_Log")
                if _clean(s.get("SubCap_ID")).startswith(category)]
    tools = sorted({_clean(s.get("Tool")) for s in searches
                    if _clean(s.get("Tool"))})
    return {
        "category": category,
        "cells_in_scope": len(cells),
        "synthesised": closed,
        "declared_absent": absent,
        "still_open": open_cells,
        "evidence_items": items,
        "searches": len(searches),
        "tools_used": tools,
        "unattached_evidence": unattached(wb, category),
        "leads_for_other_categories": {k: v[:8] for k, v in
                                       sorted(leads.items())},
        "done": not open_cells,
        "note": ("`done` means every cell is synthesised or declared absent. "
                 "It is NOT the gate: run `engine.cli gate --category "
                 f"{category} --require-synthesis` for the verdict."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.brief",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        p.add_argument("--json", action="store_true")
        return p

    d = common(sub.add_parser("dispatch"))
    d.add_argument("--category", required=True)
    d.add_argument("--out", help="write the markdown brief here")

    b = common(sub.add_parser("batch"))
    b.add_argument("--out-dir", required=True)
    b.add_argument("--only", help="comma-separated categories")

    common(sub.add_parser("shared"))

    r = common(sub.add_parser("reuse"))
    r.add_argument("--subcap", required=True)

    h = common(sub.add_parser("handback"))
    h.add_argument("--category", required=True)

    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "dispatch":
            packet = dispatch(wb, a.category, run=run)
            if a.out:
                Path(a.out).write_text(as_markdown(packet), encoding="utf-8")
                print(f"{a.out} — {packet['packet_chars']} chars, "
                      f"{packet['open_cells']} open cell(s)")
            elif a.json:
                print(json.dumps(packet, indent=2, default=str))
            else:
                print(as_markdown(packet))
        elif a.cmd == "batch":
            out = batch(wb, run=run, out_dir=Path(a.out_dir),
                        only=a.only.split(",") if a.only else None)
            print(json.dumps(out, indent=2))
        elif a.cmd == "shared":
            print(json.dumps(shared(wb), indent=2, default=str))
        elif a.cmd == "reuse":
            print(json.dumps(reusable(wb, a.subcap), indent=2, default=str))
        else:
            print(json.dumps(handback(wb, a.category), indent=2, default=str))
    except (ValueError, KeyError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
