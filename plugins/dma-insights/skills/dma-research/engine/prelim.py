#!/usr/bin/env python3
"""PRELIM — the preliminary research the whole run is read against.

    python3 -m engine.prelim state    --run R [--json]
    python3 -m engine.prelim narrate  --run R --section firmographics \
                                      --heading "…" --body "…" [--evidence E-001]
    python3 -m engine.prelim timeline --run R --date 2024-06-06 --event "…" \
                                      --signal INVESTMENT [--evidence E-001]
    python3 -m engine.prelim peers    --run R --peer "…" --basis "…"
    python3 -m engine.prelim declare  --run R --section leadership --ladder "…"
    python3 -m engine.prelim complete --run R

WHY THIS EXISTS. The Golden 1 calibration went straight from `start` to a
category worklist. It produced twenty evidence rows about six subcapabilities
and nothing at all about the institution: no firmographics, no leadership, no
timeline, no peer set, no technology baseline. `Entity_Timeline`,
`Tech_Register` and `Peer_Benchmarks` were empty at the end because nothing
had ever been asked to fill them, and the Client Research Profile — whose
whole first half is the client, not the capabilities — had no material to
render from. A run that skips this does category research in a vacuum: the
subcap researchers have no institutional context to weigh a finding against,
and the research report has to invent one or ship thin.

So PRELIM is a PHASE, with a gate. `orient` will not serve a category card
while it is open, because dispatching sixteen researchers against an entity
nobody has profiled is the expensive way to discover the profile matters.

Every section can be closed two ways and only two: RESEARCHED, or DECLARED
with the ladder that establishes the absence. There is no third state where
the work quietly did not happen — that state is what this file removes.
"""
from __future__ import annotations

# Runnable both ways: -m engine.prelim, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from . import contract as C
from . import runstate
from .workbook import RunWorkbook

NOT_AVAILABLE = "NOT_AVAILABLE:"
_MIN_BODY = 120
_MIN_LADDER = 60

#: The signal vocabulary an Entity_Timeline row may carry. Tokens, not prose,
#: for the same reason every other vocabulary in this engine is a token: a
#: free-text signal cannot be counted, filtered or reconciled downstream.
TIMELINE_SIGNALS = ("INVESTMENT", "DIVESTMENT", "LEADERSHIP", "PLATFORM",
                    "REGULATORY", "MERGER", "INCIDENT", "LAUNCH", "PARTNERSHIP")

#: The sections, what closes each, and why the run needs it. `key` is the
#: `--section` argument; `section_id` is what lands in Report_Narrative.
SECTIONS = {
    "firmographics": dict(
        section_id="PRELIM-FIRM", kind="narrative",
        heading="Institution profile",
        why="charter, scale, geography and membership — the frame every "
            "capability finding is read against"),
    "financials": dict(
        section_id="PRELIM-FIN", kind="narrative",
        heading="Financial profile and lines of business",
        why="the revenue split the sub-vertical binding rests on; written "
            "by the binding preflight, not by hand"),
    "leadership": dict(
        section_id="PRELIM-LEAD", kind="narrative",
        heading="Leadership and digital ownership",
        why="who owns digital, and whether the role exists at all — a "
            "finding in itself, and the research report's second section"),
    "timeline": dict(
        section_id="PRELIM-TIME", kind="timeline", min_rows=3,
        heading="Digital evolution",
        why="dated events, so 'they have been modernising since 2022' is a "
            "row somebody can check rather than an impression"),
    "peers": dict(
        section_id="PRELIM-PEER", kind="peers", min_rows=1,
        heading="Peer set",
        why="the comparison set, frozen before any score exists — a peer "
            "set chosen after the fact is chosen to flatter"),
    "tech_baseline": dict(
        section_id="PRELIM-TECH", kind="tech", min_rows=1,
        heading="Technology baseline",
        why="the platforms already visible from outside, so category "
            "researchers recognise a system instead of re-discovering it"),
}

#: PRELIM sections that must be RESEARCHED and may not be declared away.
#: The financial review is the binding basis; declaring it absent is what
#: `financials.not_run` in the preflight is for, under that file's own
#: ladder rules, and it has already happened by the time PRELIM runs.
UNDECLARABLE = ("financials",)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(v) -> str:
    return " ".join(str(v or "").split())


class PrelimRefusal(ValueError):
    """PRELIM is not closed, and here is exactly what is open."""


# ── reading the state ────────────────────────────────────────────────────

def _narrative_rows(wb: RunWorkbook) -> dict[str, dict]:
    out = {}
    for r in wb.rows("Report_Narrative"):
        sid = _clean(r.get("Section_ID"))
        if sid.startswith("PRELIM-"):
            out[sid] = r
    return out


def _section_state(wb: RunWorkbook, key: str, spec: dict,
                   narr: dict[str, dict]) -> dict:
    sid = spec["section_id"]
    row = narr.get(sid)
    body = _clean(row.get("Body")) if row else ""
    if body.upper().startswith(NOT_AVAILABLE):
        ladder = body[len(NOT_AVAILABLE):].strip()
        if len(ladder) < _MIN_LADDER:
            return {"section": key, "status": "OPEN",
                    "detail": f"declared absent with a {len(ladder)}-char "
                              f"ladder; {_MIN_LADDER} is the floor",
                    "fix": f"engine.prelim declare --section {key} --ladder '…'"}
        return {"section": key, "status": "DECLARED", "detail": ladder[:160]}

    kind = spec["kind"]
    if kind == "narrative":
        if len(body) >= _MIN_BODY:
            return {"section": key, "status": "RESEARCHED",
                    "detail": f"{len(body)} chars, evidence "
                              f"{_clean(row.get('Evidence_IDs')) or 'none'}"}
        return {"section": key, "status": "OPEN",
                "detail": f"no {sid} row of at least {_MIN_BODY} chars "
                          f"({len(body)} found)",
                "fix": f"engine.prelim narrate --section {key} --body '…'"}

    sheet, need = {
        "timeline": ("Entity_Timeline", spec.get("min_rows", 1)),
        "peers": ("Peer_Benchmarks", spec.get("min_rows", 1)),
        "tech": ("Tech_Register", spec.get("min_rows", 1)),
    }[kind]
    n = len([r for r in wb.rows(sheet) if any(_clean(v) for v in r.values())])
    if n >= need:
        return {"section": key, "status": "RESEARCHED",
                "detail": f"{n} row(s) in {sheet}"}
    verb = {"timeline": "timeline", "peers": "peers",
            "tech": "techscan record"}[kind]
    return {"section": key, "status": "OPEN",
            "detail": f"{sheet} has {n} row(s), {need} required",
            "fix": (f"engine.prelim {verb} …" if kind != "tech"
                    else "engine.cli techscan record …")}


def state(wb: RunWorkbook) -> dict:
    narr = _narrative_rows(wb)
    sections = [_section_state(wb, k, v, narr) for k, v in SECTIONS.items()]
    open_ = [s["section"] for s in sections if s["status"] == "OPEN"]
    md = wb.metadata()
    recorded = _clean(md.get("prelim_status")) or "OPEN"
    return {
        "run_id": md.get("run_id"), "entity": md.get("entity_name"),
        "prelim_status": "COMPLETE" if (recorded == "COMPLETE" and not open_)
                         else "OPEN",
        "recorded_status": recorded,
        "completed_at": _clean(md.get("prelim_completed_at")) or None,
        "open": open_, "sections": sections,
        "blocks_category_dispatch": bool(open_) or recorded != "COMPLETE",
    }


def require_complete(wb: RunWorkbook) -> None:
    """The gate `orient` calls before serving a category card."""
    st = state(wb)
    if not st["blocks_category_dispatch"]:
        return
    lines = [f"  - {s['section']}: {s['detail']}"
             + (f"\n      fix: {s['fix']}" if s.get("fix") else "")
             for s in st["sections"] if s["status"] == "OPEN"]
    if st["recorded_status"] != "COMPLETE" and not st["open"]:
        lines.append("  - every section is closed but PRELIM was never "
                     "signed off\n      fix: engine.prelim complete")
    raise PrelimRefusal(
        "PRELIM is open, so no category card will be served. Dispatching "
        "sixteen category researchers against an entity nobody has profiled "
        "spends the run's whole budget discovering that the profile "
        "mattered.\n" + "\n".join(lines))


# ── writing it ───────────────────────────────────────────────────────────

def narrate(wb: RunWorkbook, section: str, *, heading: str | None,
            body: str, evidence: list[str] | None = None,
            author: str = "prelim") -> dict:
    spec = SECTIONS.get(section)
    if spec is None:
        raise PrelimRefusal(
            f"unknown PRELIM section {section!r}; one of "
            f"{', '.join(SECTIONS)}")
    if spec["kind"] != "narrative":
        raise PrelimRefusal(
            f"{section} is not a narrative section — close it with "
            f"`engine.prelim {spec['kind']}` instead")
    text = _clean(body)
    if len(text) < _MIN_BODY and not text.upper().startswith(NOT_AVAILABLE):
        raise PrelimRefusal(
            f"the {section} body is {len(text)} chars; {_MIN_BODY} is the "
            f"floor. This section is {spec['why']} — a sentence does not "
            f"carry it.")
    eids = [e for e in (evidence or []) if _clean(e)]
    known = set(wb.evidence_index())
    unknown = [e for e in eids if e not in known]
    if unknown:
        raise PrelimRefusal(
            f"evidence {', '.join(unknown)} is not in this run's register. "
            f"Bank it first (engine.cli evidence …); invariant 4 is "
            f"fail-closed and a PRELIM section is not exempt.")
    if not eids and not text.upper().startswith(NOT_AVAILABLE):
        raise PrelimRefusal(
            f"the {section} section cites nothing. The research report "
            f"renders this verbatim to a client; an uncited paragraph about "
            f"a named institution is the shape of a hallucination.")
    row = {"Report": "client_research", "Section_ID": spec["section_id"],
           "Heading": _clean(heading) or spec["heading"], "Body": text,
           "Evidence_IDs": ", ".join(eids), "Kind": "section",
           "Author": author, "Written_At": _utcnow()}
    existing = _narrative_rows(wb).get(spec["section_id"])
    if existing:
        wb.update_row("Report_Narrative", "Section_ID", spec["section_id"], row)
    else:
        wb.append("Report_Narrative", row)
    return {"section": section, "section_id": spec["section_id"],
            "chars": len(text), "evidence": eids}


def declare(wb: RunWorkbook, section: str, ladder: str,
            author: str = "prelim") -> dict:
    """Close a section as a documented absence, with the search behind it."""
    if section in UNDECLARABLE:
        raise PrelimRefusal(
            f"{section} cannot be declared absent here — it is the binding "
            f"basis. Record the ladder in the preflight's "
            f"financials.not_run, where it is checked against the binding.")
    spec = SECTIONS.get(section)
    if spec is None:
        raise PrelimRefusal(f"unknown PRELIM section {section!r}")
    text = _clean(ladder)
    if len(text) < _MIN_LADDER:
        raise PrelimRefusal(
            f"the ladder is {len(text)} chars; {_MIN_LADDER} is the floor. "
            f"Name the registries, queries and dates that came back empty — "
            f"an absence asserted is not an absence established.")
    row = {"Report": "client_research", "Section_ID": spec["section_id"],
           "Heading": spec["heading"], "Body": f"{NOT_AVAILABLE} {text}",
           "Evidence_IDs": "", "Kind": "section", "Author": author,
           "Written_At": _utcnow()}
    existing = _narrative_rows(wb).get(spec["section_id"])
    if existing:
        wb.update_row("Report_Narrative", "Section_ID", spec["section_id"], row)
    else:
        wb.append("Report_Narrative", row)
    return {"section": section, "status": "DECLARED", "ladder_chars": len(text)}


def timeline(wb: RunWorkbook, *, date: str, event: str, signal: str,
             subcaps: list[str] | None = None,
             evidence: list[str] | None = None) -> dict:
    sig = _clean(signal).upper()
    if sig not in TIMELINE_SIGNALS:
        raise PrelimRefusal(
            f"signal {sig!r} is not one of {', '.join(TIMELINE_SIGNALS)}")
    d = _clean(date)
    if not d or len(d) < 4:
        raise PrelimRefusal(
            "a timeline row needs a date. An undated event is UNVERIFIED, "
            "never current (invariant 9), and an undated timeline argues "
            "nothing about direction.")
    eids = [e for e in (evidence or []) if _clean(e)]
    known = set(wb.evidence_index())
    unknown = [e for e in eids if e not in known]
    if unknown:
        raise PrelimRefusal(
            f"evidence {', '.join(unknown)} is not in this run's register")
    if not eids:
        raise PrelimRefusal(
            "a timeline row cites nothing. Every dated claim about a named "
            "institution carries its source or it does not ship.")
    wb.append("Entity_Timeline", {
        "Event_Date": d, "Event": _clean(event), "Signal": sig,
        "SubCap_IDs": ", ".join(subcaps or []),
        "Evidence_IDs": ", ".join(eids)})
    return {"date": d, "signal": sig, "evidence": eids}


def peers(wb: RunWorkbook, names: list[str], *, rule: str,
          basis: str = "inferred") -> dict:
    """Freeze the peer set. Before any score exists, by design.

    TWO things, deliberately not one. `basis` is the provenance TOKEN the
    handoff lock takes (how the peer figures will be obtained), and `rule` is
    the SELECTION rule in prose (what makes these the comparison set). The
    lock needs the token to stay machine-readable; a reader needs the rule,
    because a peer set with no stated rule is a peer set chosen to flatter."""
    clean = [_clean(n) for n in names if _clean(n)]
    if not clean:
        raise PrelimRefusal("no peer named")
    if basis not in C.PEER_BASIS:
        raise PrelimRefusal(
            f"peer basis {basis!r} is not one of {', '.join(C.PEER_BASIS)}")
    if len(_clean(rule)) < 40:
        raise PrelimRefusal(
            "the peer selection rule is too short. Say what makes these the "
            "comparison set — asset band, charter, geography, digital "
            "posture — because a peer set with no stated rule is a peer set "
            "chosen to flatter.")
    locked = wb.lock_peer_set(clean, basis=basis)
    for name in clean:
        wb.append("Peer_Benchmarks", {
            "Category_ID": "", "Category_Name": "", "Entity_Score": "",
            "Peer_Median": "", "Peer_P25": "", "Peer_P75": "",
            "Peer_N": len(clean), "Peer_Basis": f"{basis}: {_clean(rule)}",
            "Source_Cell": "", "Peer_Names": name, "Peer_Scores": "",
            "As_Of": _utcnow()[:10]})
    return {"peers": clean, "locked": locked, "rule": _clean(rule)}


def complete(wb: RunWorkbook) -> dict:
    """Sign PRELIM off — refusing while anything is open."""
    st = state(wb)
    if st["open"]:
        raise PrelimRefusal(
            "PRELIM cannot be signed off with open sections: "
            + ", ".join(st["open"]))
    wb.set_metadata("prelim_status", "COMPLETE")
    wb.set_metadata("prelim_completed_at", _utcnow())
    return {**state(wb), "signed_off_at": _utcnow()}


# ── command line ─────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.prelim",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    s = common(sub.add_parser("state")); s.add_argument("--json",
                                                        action="store_true")
    n = common(sub.add_parser("narrate"))
    n.add_argument("--section", required=True, choices=sorted(SECTIONS))
    n.add_argument("--heading"); n.add_argument("--body", required=True)
    n.add_argument("--evidence", action="append", default=[])
    n.add_argument("--author", default="prelim")

    d = common(sub.add_parser("declare"))
    d.add_argument("--section", required=True, choices=sorted(SECTIONS))
    d.add_argument("--ladder", required=True)

    t = common(sub.add_parser("timeline"))
    t.add_argument("--date", required=True); t.add_argument("--event",
                                                            required=True)
    t.add_argument("--signal", required=True, choices=TIMELINE_SIGNALS)
    t.add_argument("--subcap", action="append", default=[])
    t.add_argument("--evidence", action="append", default=[])

    p = common(sub.add_parser("peers"))
    p.add_argument("--peer", action="append", required=True)
    p.add_argument("--rule", required=True,
                   help="the SELECTION rule: what makes these the comparison "
                        "set (asset band, charter, geography, posture)")
    p.add_argument("--basis", default="inferred", choices=C.PEER_BASIS,
                   help="how the peer FIGURES will be obtained; this is the "
                        "token the handoff lock freezes")

    common(sub.add_parser("complete"))

    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "state":
            st = state(wb)
            if a.json:
                print(json.dumps(st, indent=2))
            else:
                print(f"PRELIM {st['prelim_status']} — {st['entity']}")
                for sec in st["sections"]:
                    mark = {"RESEARCHED": "✓", "DECLARED": "·",
                            "OPEN": "✗"}[sec["status"]]
                    print(f"  {mark} {sec['section']:<14} {sec['status']:<11}"
                          f" {sec['detail']}")
                    if sec.get("fix"):
                        print(f"      fix: {sec['fix']}")
            return 0 if st["prelim_status"] == "COMPLETE" else 1
        if a.cmd == "narrate":
            print(json.dumps(narrate(wb, a.section, heading=a.heading,
                                     body=a.body, evidence=a.evidence,
                                     author=a.author), indent=2))
        elif a.cmd == "declare":
            print(json.dumps(declare(wb, a.section, a.ladder), indent=2))
        elif a.cmd == "timeline":
            print(json.dumps(timeline(wb, date=a.date, event=a.event,
                                      signal=a.signal, subcaps=a.subcap,
                                      evidence=a.evidence), indent=2))
        elif a.cmd == "peers":
            print(json.dumps(peers(wb, a.peer, rule=a.rule, basis=a.basis),
                             indent=2, default=str))
        else:
            print(json.dumps(complete(wb), indent=2))
    except PrelimRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
