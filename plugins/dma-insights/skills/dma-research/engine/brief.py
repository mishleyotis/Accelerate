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
import re
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
                # The FLAG, not the proven declaration: a cell that claims
                # absence over rows the register names is the
                # under-consolidation defect whether the flag was earned
                # (`engine.cli absence`) or written around it — the gate's
                # `absence_over_evidence` must block both.
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
             run: runstate.Run | None = None,
             with_handback: bool = False) -> dict:
    """The bounded packet one category producer starts from.

    `with_handback` is the RE-DISPATCH shape (owner issue 8, 2026-09-03: the
    handback was computed and never fed back): the packet also carries what
    the lane's previous run established (`handback`) and the last FLOORS
    verdict on the category with its blocking terms (`last_gate`), so a
    second lane continues the category instead of re-finding it."""
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
    if with_handback:
        hb = handback(wb, category)
        packet["handback"] = {k: hb[k] for k in hb
                              if k not in ("category",)}
        packet["last_gate"] = last_gate(wb, "FLOORS", category)
        packet["rules"].append(
            "this is a RE-DISPATCH: `handback` is what your previous run "
            "established and `last_gate.blocking` is exactly what the floors "
            "gate refused — work those terms, not the category from scratch")
    packet["packet_chars"] = len(json.dumps(packet, default=str))
    packet["packet_ceiling"] = BRIEF_CHAR_CEILING
    if packet["packet_chars"] > BRIEF_CHAR_CEILING and with_handback:
        # the handback's long lists first — the gate terms are the point
        hb = packet["handback"]
        for k, v in list(hb.items()):
            if isinstance(v, list) and len(v) > 6:
                hb[k] = v[:6] + [f"… and {len(v) - 6} more"]
        packet["packet_chars"] = len(json.dumps(packet, default=str))
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
    if packet.get("last_gate"):
        g = packet["last_gate"]
        lines += ["", "### The last floors gate on this category", "",
                  f"- verdict **{g.get('verdict') or 'NOT_RUN'}**"
                  + (f" at {g['at']}" if g.get("at") else ""),
                  ]
        for term in g.get("blocking") or []:
            lines.append(f"- BLOCKING: {term}")
        if g.get("detail"):
            lines.append(f"- detail: {g['detail'][:400]}")
    if packet.get("handback"):
        hb = packet["handback"]
        lines += ["", "### What your previous run established (the handback)", ""]
        for k, v in hb.items():
            if isinstance(v, (list, tuple)):
                lines.append(f"- {k}: " + (", ".join(str(x) for x in v[:8]) if v else "none"))
            elif isinstance(v, dict):
                lines.append(f"- {k}: " + ", ".join(f"{a} {b}" for a, b in list(v.items())[:8]))
            else:
                lines.append(f"- {k}: {v}")
    if packet.get("trimmed"):
        lines += ["", f"_{packet['trimmed']}_"]
    return "\n".join(lines) + "\n"


def last_gate(wb: RunWorkbook, gate: str, scope: str | None = None) -> dict:
    """The most recent Gate_Log row for `gate` (and `scope`), with the
    blocking terms parsed out of its detail. NOT_RUN when there is none."""
    last = None
    for g in wb.rows("Gate_Log"):
        if _clean(g.get("Gate")) != gate:
            continue
        if scope and _clean(g.get("Scope")) != _clean(scope):
            continue
        last = g
    if last is None:
        return {"gate": gate, "scope": scope, "verdict": "NOT_RUN", "blocking": [],
                "detail": "", "at": None}
    detail = str(last.get("Detail") or "")
    terms = []
    verdict = _clean(last.get("Verdict"))
    if verdict == "FAIL" and detail and detail.lower() != "all terms met":
        # floors_gate records `"; ".join(sorted(blocking))` — the terms, verbatim
        terms = [t.strip() for t in detail.split(";") if t.strip()]
    return {"gate": gate, "scope": scope, "verdict": _clean(last.get("Verdict")),
            "blocking": terms, "detail": detail, "at": last.get("Timestamp")}


def batch(wb: RunWorkbook, *, run: runstate.Run | None = None,
          out_dir: Path, only: list[str] | None = None,
          with_handback: bool = False) -> dict:
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
    skipped = []
    if with_handback:
        # a re-dispatch never includes a category whose gate already PASSED
        need = categories_needing_dispatch(wb)
        skipped = [c for c in cats if c in need["passed"]]
        cats = [c for c in cats if c not in need["passed"]]
    rows, wrote = [], []
    for cat in cats:
        packet = dispatch(wb, cat, run=run, with_handback=with_handback)
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
            "skipped_passed": skipped,
            "dispatch": (_dispatch_line(batch_path, run, "RESEARCH") if rows
                         else None)}


def categories_needing_dispatch(wb: RunWorkbook) -> dict:
    """Which categories a driver dispatches (again), and why — the FLOORS
    gate decides, not a lane's report. A category whose last gate is PASS is
    never re-dispatched (the redo the owner measured); one with no gate row
    or a FAIL is, with the gate's blocking terms in its brief."""
    out = {"dispatch": [], "passed": [], "reasons": {}}
    for cat in sorted({category_of(c) for c in wb.selected_subcaps()}):
        g = last_gate(wb, "FLOORS", cat)
        if g["verdict"] == "PASS":
            out["passed"].append(cat)
        else:
            out["dispatch"].append(cat)
            out["reasons"][cat] = (g["blocking"] or
                                   [f"floors gate {g['verdict']}"])
    return out


def _dispatch_line(batch_path: Path, run, stage: str) -> str:
    """ONE lane constant. The conductor said `--lanes 4`, agent_run defaulted
    to 16 and `cost.schedule` divided by 16 (measured 2026-09-03): the
    documented dispatch ran the research phase at a quarter of the speed the
    schedule promised. The number comes from `cost.PARALLEL_LANES` here and
    nowhere else."""
    from . import cost
    line = (f"python3 plugins/dma-insights/scripts/agent_run.py "
            f"--batch {batch_path} --stream --lanes {cost.PARALLEL_LANES} "
            f"--retries 1")
    if run is not None:
        line += (f" --record-run {run.run_id} --record-root {run.root} "
                 f"--record-stage {stage}")
    return line


# ── briefs for EVERY tier ────────────────────────────────────────────────
#
# Owner issue 8 (2026-09-03): the conductor dispatched scorers, the critic,
# the report producers and the page producers "with the run id and the root"
# — no brief — while the category researchers got a measured packet. The
# lanes below get the same treatment: what the run knows, what is owed, the
# exact commands, the refusals they will meet, bounded by the same ceiling.

def _bound(packet: dict, *lists: str) -> dict:
    packet["packet_ceiling"] = BRIEF_CHAR_CEILING
    packet["packet_chars"] = len(json.dumps(packet, default=str))
    for key in lists:
        while packet["packet_chars"] > BRIEF_CHAR_CEILING and \
                isinstance(packet.get(key), list) and len(packet[key]) > 3:
            keep = max(3, len(packet[key]) // 2)
            dropped = len(packet[key]) - keep
            packet[key] = packet[key][:keep]
            packet["trimmed"] = (packet.get("trimmed") or "") + \
                f"{key}: {dropped} item(s) trimmed to stay under the ceiling; "
            packet["packet_chars"] = len(json.dumps(packet, default=str))
    return packet


def _md(title: str, packet: dict) -> str:
    """A generic prompt rendering: the shared header, then each packet field
    as a section. JSON stays the contract; this is the delivery."""
    s = packet.get("shared") or {}
    lines = [f"# {title}", "",
             f"Run `{s.get('run_id')}` · entity **{s.get('entity')}** "
             f"({s.get('sub_vertical') or 'sub-vertical not set'}, "
             f"{s.get('evidence_mode') or 'mode not set'} evidence) · "
             f"stage {s.get('stage')}.", ""]
    if packet.get("first_commands"):
        lines += ["## Your first commands", ""]
        lines += [f"    {c}" for c in packet["first_commands"]]
        lines.append("")
    for k, v in packet.items():
        if k in ("shared", "first_commands", "agent", "packet_chars",
                 "packet_ceiling", "trimmed"):
            continue
        lines += [f"## {k.replace('_', ' ')}", ""]
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    lines.append("- " + " · ".join(f"{a}: {b}" for a, b in item.items()))
                else:
                    lines.append(f"- {item}")
        elif isinstance(v, dict):
            for a, b in v.items():
                lines.append(f"- **{a}**: {b}")
        else:
            lines.append(str(v))
        lines.append("")
    if packet.get("trimmed"):
        lines += [f"_{packet['trimmed']}_", ""]
    return "\n".join(lines)


def _write_lanes(out_dir: Path, lanes: list[tuple[str, dict, str]], *, run,
                 stage: str, batch_name: str = "batch.json") -> dict:
    """Write <name>.md/.json per lane plus the agent_run batch array."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, wrote = [], []
    for name, packet, title in lanes:
        path = out_dir / f"{name}.md"
        path.write_text(_md(title, packet), encoding="utf-8")
        (out_dir / f"{name}.json").write_text(
            json.dumps(packet, indent=2, default=str), encoding="utf-8")
        rows.append({"agent": packet["agent"], "prompt_file": str(path)})
        wrote.append({"lane": name, "agent": packet["agent"],
                      "prompt_file": str(path), "chars": packet["packet_chars"]})
    batch_path = out_dir / batch_name
    batch_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {"batch": str(batch_path), "lanes": len(rows), "briefs": wrote,
            "dispatch": _dispatch_line(batch_path, run, stage)}


def _engine(run) -> str:
    return f"--run {run.run_id} --root {run.root}" if run is not None else "--run <R> --root <ROOT>"


def prelim_brief(wb: RunWorkbook, *, run, out_dir: Path) -> dict:
    """The PRELIM lanes: the institution before its capabilities. Three
    agents, one prompt each — the conductor in PRELIM-ONLY mode for the
    narrative sections, the technographic scanner for `tech_baseline`, the
    connector specialist for the contact pass and the machine scan."""
    from . import prelim, profile
    st = prelim.state(wb)
    fin = profile.financial_depth(wb)
    sh = shared(wb)
    e = _engine(run)
    sections = [{"section": x["section"], "status": x["status"],
                 "heading": prelim.SECTIONS[x["section"]]["heading"],
                 "why": prelim.SECTIONS[x["section"]].get("why", "")}
                for x in st["sections"]]
    common_rules = [
        "PRELIM ONLY. Do not dispatch a category researcher, do not score, "
        "do not write a report section — the driver runs those stages once "
        "`engine.prelim state` reads COMPLETE.",
        "every section is written through `engine.prelim narrate` (cited) or "
        "declared through `engine.prelim declare` (with a ladder); "
        "`engine.prelim complete` refuses while one is OPEN",
        "PRELIM searches are logged `engine.cli search … --prelim` (no cell yet)",
    ]
    conductor = _bound({
        "agent": "research-conductor", "shared": sh,
        "first_commands": [f"python3 -m engine.prelim state {e}",
                           f"python3 -m engine.profile state {e}"],
        "prelim_sections": sections,
        "financial_series": {"years": fin.get("years"), "metrics": fin.get("metrics"),
                             "floor_met": fin.get("met"), "fix": fin.get("fix")},
        "owed": st["open"],
        "rules": common_rules + [
            "the five-year financial series goes in through `engine.profile "
            "financial --metric … --fy … --value … --unit … --evidence …` — "
            "three metrics over five fiscal years is the floor the reports read"],
    }, "prelim_sections")
    scanner = _bound({
        "agent": "technographic-scanner", "shared": sh,
        "first_commands": [f"python3 -m engine.techscan state {e}",
                           f"python3 -m engine.prelim state {e}"],
        "layers": ["OPS", "CUST", "DATA", "INFRA"],
        "estate_known": sh.get("estate_by_layer") or {},
        "owed": ["tech_baseline"] if "tech_baseline" in st["open"] else [],
        "rules": common_rules + [
            "every layer carries a row (CONFIRMED · INFERRED · CLAIMED · ABSENT) "
            "with the method that found it; a layer never looked at is stated, "
            "not left blank"],
    })
    connector = _bound({
        "agent": "enrichment-connector-specialist", "shared": sh,
        "first_commands": [f"python3 -m engine.prelim state {e}"],
        "owed": [x for x in ("leadership", "firmographics", "peers") if x in st["open"]],
        "rules": common_rules + [
            "the contact pass names the leaders `leadership` needs (min two "
            "named people); the machine technographic scan is registered at "
            "the tier it earns, never T1",
            "record every attempt with the outcome it had (RESOLVED, NOT_RUN, "
            "NO_SOURCE, FAILED) — a refused connector is stated, not dressed "
            "as a result"],
    })
    return _write_lanes(out_dir, [
        ("prelim-conductor", conductor, "PRELIM — the institution, before its capabilities"),
        ("prelim-techscan", scanner, "PRELIM — technology baseline"),
        ("prelim-connectors", connector, "PRELIM — connector enrichment"),
    ], run=run, stage="PRELIM")


def challenge_batch(wb: RunWorkbook, *, run, out_dir: Path) -> dict:
    """One `finding-challenger` lane per category with unchallenged
    syntheses: the cells, their claims, and the `engine.cli challenge`
    command — the actor is the challenger, never the author."""
    e = _engine(run)
    sh = shared(wb)
    challenged = {_clean(r.get("SubCap_ID")) for r in wb.rows("Challenge_Log")
                  if _clean(r.get("Verdict"))}
    by_cat: dict[str, list] = {}
    for sheet in C.PILLAR_SHEETS:
        for r in wb.rows(sheet):
            sub = _clean(r.get("SubCap_ID"))
            if not sub or sub not in wb.selected_subcaps():
                continue
            if not _clean(r.get("Dominant_Claim")):
                continue
            if sub in challenged or _clean(r.get("Challenge_Verdict")):
                continue
            if L.is_declared_absent(r, wb):
                continue          # an absence is gated by its ladder, not a challenge
            by_cat.setdefault(category_of(sub), []).append({
                "subcap": sub, "name": C.subcap_names().get(sub),
                "claim": _clean(r.get("Dominant_Claim"))[:200],
                "label": _clean(r.get("Claim_Label")),
                "author": L.actor_for(wb, sub, "synthesis"),
                "evidence": len(_ids(r.get("Evidence_IDs"))),
            })
    lanes = []
    dims = " ".join(f"--dimension {d}=PASS|FAIL|NOT_RUN" for d in C.CHALLENGE_DIMENSIONS)
    for cat in sorted(by_cat):
        packet = _bound({
            "agent": "finding-challenger", "shared": sh,
            "first_commands": [
                f"python3 -m engine.cli orient {e} --category {cat}",
                f"python3 -m engine.cli challenge {e} --subcap <CELL> --verdict PASS|FAIL "
                f"--actor finding-challenger --rationale '…' {dims}"],
            "category": cat,
            "cells_to_challenge": by_cat[cat],
            "rules": [
                "steelman, then falsify: read the row's evidence and the claim, "
                "and record every one of the seven dimensions by name",
                "any FAIL is FAIL — the engine refuses a PASS over a failed dimension",
                "you did not write these syntheses; the engine refuses a verdict "
                "from the synthesis's author or its session",
                "repair nothing — a FAIL goes back to the category lane through "
                "the floors gate",
            ],
        }, "cells_to_challenge")
        lanes.append((f"challenge-{cat}", packet, f"Challenge — {cat}"))
    if not lanes:
        return {"batch": None, "lanes": 0, "briefs": [], "dispatch": None,
                "note": "every synthesis in scope already carries a challenge verdict"}
    return _write_lanes(out_dir, lanes, run=run, stage="CHALLENGE",
                        batch_name="batch_challenge.json")


def scoring_batch(wb: RunWorkbook, *, run, out_dir: Path, critic: bool = False,
                  solutions: bool = False) -> dict:
    """The scoring lanes: one `scoring-p<N>-producer` per pillar in scope
    (default), or the `scoring-critic` (`critic=True`), or the solutions/
    peer-adoption duty (`solutions=True`)."""
    from . import assessment as A
    e = _engine(run)
    sh = shared(wb)
    st = A.state(wb)
    pillars = sorted({str(c).split("C")[0] for c in wb.selected_subcaps()})
    weights = {_clean(r.get("pillar_id")): r.get("weight")
               for r in wb.rows("Pillar_Weights") if _clean(r.get("pillar_id"))}
    lanes = []
    if critic:
        packet = _bound({
            "agent": "scoring-critic", "shared": sh,
            "first_commands": [
                f"python3 -m engine.assessment state {e}",
                f"python3 -m engine.assessment critique {e} --pillar <P> --verdict PASS|FAIL "
                f"--actor scoring-critic --note '<80+ chars: what you re-derived and what moved>'"],
            "pillars_in_scope": pillars,
            "scored": st.get("scored"), "subcaps": st.get("subcaps"),
            "critic_verdicts_so_far": st.get("critic_verdicts") or {},
            "rules": [
                "re-derive a sample of scores from their rationales and rubric "
                "descriptors; run the differentiation and ceiling checks; hunt "
                "the score that flatters",
                "you struck none of these scores — the engine refuses a critique "
                "from a pillar's own scorer",
                "`engine.assessment gate` will not PASS without your verdict on "
                "every pillar in scope",
            ],
        })
        lanes.append(("scoring-critic", packet, "Scoring critic — every pillar"))
    elif solutions:
        packet = _bound({
            "agent": "technographic-scanner", "shared": sh,
            "first_commands": [
                f"python3 -m engine.assessment state {e}",
                f"python3 -m engine.assessment solution {e} --sol-id SOL-NN --name '…' "
                f"--platform '…' --categories P1C1,…",
                f"python3 -m engine.assessment peer-adoption {e} …"],
            "estate_known": sh.get("estate_by_layer") or {},
            "rules": [
                "one Solution_Catalogue row per platform the assessment can argue "
                "for, named against the categories it addresses",
                "Platform_Peer_Adoption is filled where a peer's deployment can be "
                "examined and DECLARED (`engine.cli complete declare`) where it cannot",
            ],
        })
        lanes.append(("scoring-solutions", packet, "Scoring stage — solutions and peer adoption"))
    else:
        for pillar in pillars:
            rows = []
            sheet = f"{pillar}_Subcap_Scoring"
            for r in wb.rows(sheet):
                sub = _clean(r.get("SubCap_ID"))
                if not sub or sub not in wb.selected_subcaps():
                    continue
                if r.get("Score") not in (None, ""):
                    continue
                rows.append({"subcap": sub, "name": C.subcap_names().get(sub),
                             "label": _clean(r.get("Claim_Label")),
                             "ceiling_band": _clean(r.get("Ceiling_Band")),
                             "challenge": _clean(r.get("Challenge_Verdict")) or "none",
                             "evidence": len(_ids(r.get("Evidence_IDs"))),
                             "absent": bool(L.is_declared_absent(r, wb))})
            packet = _bound({
                "agent": f"scoring-{pillar.lower()}-producer", "shared": sh,
                "first_commands": [
                    f"python3 -m engine.assessment state {e}",
                    f"python3 -m engine.cli orient {e} --category {pillar}C1",
                    f"python3 -m engine.assessment score {e} --subcap <CELL> --score <0.5-5.0> "
                    f"--confidence HIGH|MEDIUM|LOW --rationale '<150+ chars>' "
                    f"--actor scoring-{pillar.lower()}-producer --ai-applicability … "
                    f"--data-dependency … --data-readiness …"],
                "pillar": pillar, "weight": weights.get(pillar),
                "stage": st.get("stage"),
                "rows_to_score": rows,
                "rules": [
                    "the stage is already open — `engine.assessment open` has NO "
                    "--force; if `state` says research, stop and say so",
                    "score only your pillar; read the challenged synthesis, do not "
                    "re-research",
                    "the engine refuses a score on an unchallenged row, above the "
                    "evidence ceiling, with a rationale under 150 characters or "
                    "citing nothing the row carries, or with a blank AI/data overlay",
                    "a declared absence scores as the rubric's absence, with the "
                    "ladder in the rationale — never as a guess",
                ],
            }, "rows_to_score")
            lanes.append((f"scoring-{pillar}", packet, f"Scoring — pillar {pillar}"))
    return _write_lanes(out_dir, lanes, run=run, stage="SCORING",
                        batch_name="batch_scoring.json")


def report_batch(wb: RunWorkbook, *, run, out_dir: Path, validator: bool = False) -> dict:
    """The two report producers (default) or the report validator."""
    from . import narrative as N, report_spec as RS, template as T
    e = _engine(run)
    sh = shared(wb)
    qa_dir = run.qa_dir if run is not None else Path(wb.path).resolve().parent / "07_qa"
    lanes = []
    templates = {
        "report_templates": str(T.TEMPLATES_DIR / "report_templates.json"),
        "gold_reference": str(T.TEMPLATES_DIR / "gold_reference.json"),
        "client_profile_markdown": str(T.TEMPLATES_DIR / "client_profile_template.md"),
        "assessment_markdown": str(T.TEMPLATES_DIR / "assessment_report_template.md"),
        "shell_docx": str(T.REPORT_SHELL),
    }
    for key, spec in RS.SPECS.items():
        pre = N.stage_preconditions(wb, key, qa_dir)
        full = N.state(wb, key)["reports"][key]
        # compact: the section ids by status, not every detail string — the
        # producer runs `narrative state` for the detail; the brief is bounded
        by_status: dict[str, list] = {}
        for sec_state in full.get("sections") or []:
            by_status.setdefault(str(sec_state.get("status")), []).append(
                str(sec_state.get("id") or sec_state.get("section")))
        state = {"ready": full.get("ready"), "sections_by_status": by_status}
        sections = []
        for sec in spec.sections:
            row = {"id": sec.id, "heading": sec.heading, "kind": sec.kind,
                   "min_words": N.min_words_for(wb, sec)}
            if sec.kind in RS.CARD_KINDS:
                row["cards_min"] = N.card_floor_for(wb, sec)
                row["card_prefix"] = sec.card_prefix
            if sec.blocks:
                row["blocks"] = [b[:60] for b in sec.blocks]
            sections.append(row)
        agent = ("report-research-producer" if key == "client_research"
                 else "report-assessment-producer")
        packet = _bound({
            "agent": agent, "shared": sh,
            "first_commands": [
                f"python3 -m engine.cli narrative preconditions {e} --report {key}",
                f"python3 -m engine.cli narrative state {e} --report {key}",
                f"python3 -m engine.cli narrative write {e} --report {key} --section <ID> "
                f"--actor {agent} --body-file <path> [--card <PREFIX>NN]",
                f"python3 -m engine.cli report {e} --report {key}"],
            "report": key, "title": spec.title,
            "templates_read_before_authoring": templates,
            "preconditions_failing": pre,
            "sections_state": state,
            "sections": sections,
            "report_min_words": N.report_min_words_for(wb, spec),
            "rules": [
                "every section goes through `engine.narrative write`, which refuses "
                "prose that is not an argument and a body missing a block",
                "a failing precondition means STOP and report — no --force writes a "
                "section; --force on `report` yields a DRAFT_ no package accepts",
                "the report's numbers are the sheets' numbers; cite only E-ids the "
                "register carries",
                "you never review your own sections — `report-validator` does",
                "the gold gate (`engine.gold_standard report`) reads gold_reference.json",
            ],
        }, "sections")
        lanes.append((f"report-{key}", packet, f"Report — {spec.title}"))
    if validator:
        st = N.state(wb)
        packet = _bound({
            "agent": "report-validator", "shared": sh,
            "first_commands": [
                f"python3 -m engine.cli narrative state {e}",
                f"python3 -m engine.cli narrative review {e} --report <KEY> --section <ID> "
                f"--verdict READY|REVISE --actor report-validator --note '…'",
                f"python3 -m engine.gold_standard report <docx> --workbook <xlsx>"],
            "reports_state": {k: {"ready": v.get("ready"),
                                  "sections": [f"{x.get('id') or x.get('section')}:"
                                               f"{x.get('status')}"
                                               for x in (v.get("sections") or [])]}
                              for k, v in st["reports"].items()},
            "templates_read_before_reviewing": templates,
            "rules": [
                "six named dimensions per section, then the whole-report "
                "adversarial pass (cross-section contradiction, prose figures vs "
                "sheets, the strongest case the assessment is wrong)",
                "the engine refuses a verdict from a section's own author",
            ],
        })
        lanes = [("report-validator", packet, "Report validation — both reports")]
    return _write_lanes(out_dir, lanes, run=run, stage="REPORTS",
                        batch_name="batch_reports.json")


PAGES = ("techstack", "context", "heatmap", "overview", "insights", "platform")


def page_batch(wb: RunWorkbook, *, run, out_dir: Path, connector_run: str,
               contract_file: Path, verdicts_file: Path | None = None,
               pages: list[str] | None = None) -> dict:
    """One `<page>-surface-producer` lane per page: the connector run id,
    the PATH of the page contract, the reasons the last verdict gave for
    that page — and NO payload bytes. A prompt that carries a payload is the
    stage-7b token bleed (owner issue 7)."""
    from . import ship
    from . import surface_export as SX
    e = _engine(run)
    sh = shared(wb)
    st = ship.state(wb)
    verdicts = {}
    if verdicts_file and Path(verdicts_file).is_file():
        try:
            verdicts = json.loads(Path(verdicts_file).read_text())
        except ValueError:
            verdicts = {"_error": "verdicts file did not parse"}
    want = [p.strip().lower() for p in (pages or PAGES)]
    lanes = []
    for page in want:
        if page not in ship.PAGES:
            raise ValueError(f"unknown page {page!r}; pages are {ship.PAGES}")
        pst = st["pages"].get(page) or {}
        cf = Path(contract_file)
        if cf.is_dir():
            cf = cf / f"{page}.json"          # one contract file per page
        reasons = verdicts.get(page) if isinstance(verdicts, dict) else None
        if isinstance(reasons, dict):
            reasons = reasons.get("reasons") or reasons.get("failures") or list(reasons.values())
        sp = SX.plan(page)
        packet = _bound({
            "agent": f"{page}-surface-producer", "shared": sh,
            "first_commands": [
                f"python3 -m engine.ship state {e}",
                f"python3 -m engine.surface_export plan --page {page}",
                f"# read the contract at the path below, not from memory",
                f"python3 plugins/dma-insights/skills/dma-surface-production/scripts/ship_page.py "
                f"{connector_run} {page} --sections <your sections dir> --incremental "
                f"--claim --verdicts-out <ROOT>/07_qa/verdict_{page}.json"],
            "page": page, "connector_run_id": connector_run,
            "contract_file": str(cf),
            "ready_in_workbook": pst.get("ready"),
            "waiting_on": pst.get("waiting_on") or [],
            "recording_map_tabs": pst.get("recording_map_tabs") or [],
            # The dual-source plan: for each section on this page, where it is
            # fed FROM and how it is produced. `format_only` sections are a
            # matter of shape, not synthesis; only `produce` sections need a
            # per-surface producer and an enrichment pass.
            "section_plan": sp["sections"],
            "format_only_sections": sp["convert"],
            "produce_sections": sp["produce"],
            "server_sections": sp["server"],
            "last_verdict_reasons": [str(r)[:300] for r in (reasons or [])][:12],
            "rules": [
                "read `get_memory_digest` and the contract FILE before authoring; "
                "the payload shape is law — never invent a field",
                "produce the section JSON to disk; `ship_page.py` submits — you "
                "never call submit_page_payload or promote_run yourself",
                "a verdict FAIL names the gate, the JSON path and the arithmetic: "
                "repair that path, not the page",
                "the workbook is the source: every figure comes from a tab in "
                "`recording_map_tabs`, every citation from Evidence_Detail",
                "`format_only_sections` (see section_plan) are FORMATTED from the "
                "workbook tab or report section named there — do NOT re-synthesise "
                "them and do NOT re-challenge them; the research layer already "
                "challenged that content. Only `produce_sections` need new "
                "synthesis (and enrichment registered as evidence first)",
                "`server_sections` submit fields:{} plus this page's "
                "narrative_thread — the app joins the arrangement server-side",
            ],
        }, "last_verdict_reasons", "waiting_on")
        lanes.append((f"page-{page}", packet, f"Page — {page}"))
    out = _write_lanes(out_dir, lanes, run=run, stage="PAGES",
                       batch_name="batch_pages.json")
    # the promise this view makes: no payload bytes in any prompt
    for w in out["briefs"]:
        text = Path(w["prompt_file"]).read_text(encoding="utf-8")
        assert '"e_ids"' not in text and '"narrative_thread"' not in text, \
            "a page brief carried payload bytes"
    return out


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
        if L.is_declared_absent(r, wb):
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
    b.add_argument("--with-handback", action="store_true",
                   help="RE-DISPATCH shape: each brief carries the lane's "
                        "handback and the last floors verdict's blocking terms")
    d.add_argument("--with-handback", action="store_true")

    pr = common(sub.add_parser("prelim", help="the three PRELIM lanes"))
    pr.add_argument("--out-dir", required=True)
    cb = common(sub.add_parser("challenge-batch",
                               help="one finding-challenger lane per category with "
                                    "unchallenged syntheses"))
    cb.add_argument("--out-dir", required=True)
    sb = common(sub.add_parser("scoring-batch",
                               help="one scoring lane per pillar; --critic or --solutions "
                                    "for those lanes instead"))
    sb.add_argument("--out-dir", required=True)
    sb.add_argument("--critic", action="store_true")
    sb.add_argument("--solutions", action="store_true")
    rb = common(sub.add_parser("report-batch",
                               help="the two report producers; --validator for the validator"))
    rb.add_argument("--out-dir", required=True)
    rb.add_argument("--validator", action="store_true")
    pb = common(sub.add_parser("page-batch",
                               help="one page producer per page; paths, never payload bytes"))
    pb.add_argument("--out-dir", required=True)
    pb.add_argument("--connector-run", required=True)
    pb.add_argument("--contract-file", required=True)
    pb.add_argument("--verdicts-file")
    pb.add_argument("--pages", help="comma-separated subset")

    common(sub.add_parser("shared"))
    common(sub.add_parser("needs", help="which categories the floors gate says to (re)dispatch"))

    r = common(sub.add_parser("reuse"))
    r.add_argument("--subcap", required=True)

    h = common(sub.add_parser("handback"))
    h.add_argument("--category", required=True)

    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "dispatch":
            packet = dispatch(wb, a.category, run=run, with_handback=a.with_handback)
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
                        only=a.only.split(",") if a.only else None,
                        with_handback=a.with_handback)
            print(json.dumps(out, indent=2))
        elif a.cmd == "prelim":
            print(json.dumps(prelim_brief(wb, run=run, out_dir=Path(a.out_dir)), indent=2))
        elif a.cmd == "challenge-batch":
            print(json.dumps(challenge_batch(wb, run=run, out_dir=Path(a.out_dir)), indent=2))
        elif a.cmd == "scoring-batch":
            print(json.dumps(scoring_batch(wb, run=run, out_dir=Path(a.out_dir),
                                           critic=a.critic, solutions=a.solutions), indent=2))
        elif a.cmd == "report-batch":
            print(json.dumps(report_batch(wb, run=run, out_dir=Path(a.out_dir),
                                          validator=a.validator), indent=2))
        elif a.cmd == "page-batch":
            print(json.dumps(page_batch(
                wb, run=run, out_dir=Path(a.out_dir), connector_run=a.connector_run,
                contract_file=Path(a.contract_file),
                verdicts_file=Path(a.verdicts_file) if a.verdicts_file else None,
                pages=a.pages.split(",") if a.pages else None), indent=2))
        elif a.cmd == "shared":
            print(json.dumps(shared(wb), indent=2, default=str))
        elif a.cmd == "needs":
            print(json.dumps(categories_needing_dispatch(wb), indent=2, default=str))
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
