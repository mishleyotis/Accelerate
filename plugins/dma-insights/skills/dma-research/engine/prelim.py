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
import re
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
#: Both vocabularies live in the contract, because both are the APP's and a
#: second copy here is the drift this engine has paid for before.
TIMELINE_SIGNALS = C.TIMELINE_SIGNALS
TIMELINE_KINDS = C.TIMELINE_KINDS

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
        section_id="PRELIM-LEAD", kind="narrative", min_named=2,
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
        layers=C.TECH_LAYERS,
        heading="Technology baseline",
        why="the platforms already visible from outside, so category "
            "researchers recognise a system instead of re-discovering it"),
    "thought_leadership": dict(
        section_id="PRELIM-THOUGHT", kind="narrative",
        heading="Thought leadership and stated direction",
        why="what these leaders say in public about where the institution "
            "is going — the conference talks, bylines and interviews a "
            "category researcher weighs a finding against, and the only "
            "PRELIM section written in the client's own voice"),
}

#: The workbook tab a PRELIM section owns. Declaring the section declares
#: the tab, with the SAME ladder — one reason, in one place, at the stricter
#: of the two floors.
OWNS_SHEET = {
    "timeline": "Entity_Timeline",
    "peers": "Peer_Benchmarks",
    "tech_baseline": "Tech_Register",
}

#: ONE FIX LINE FOR THE TECHNOLOGY BASELINE, whether it has no rows or
#: three layers' worth. They are the same instruction and were two: the
#: empty case printed the old one-row command and said nothing about layers,
#: so a run that had done no scanning at all was told less than one that had
#: half-done it.
_TECH_FIX = (
    "run the four-layer technographic scan NOW, in PRELIM, not after the "
    "categories: `engine.cli techscan clay-plan`, then `import-explorium` / "
    "`record --provider … --layer <LAYER>` until OPS, CUST, DATA and INFRA "
    "each carry a row — `techscan status` lists the ones still in "
    "`layers_never_looked_at`. A layer you looked at and found nothing in "
    "is a row with status ABSENT naming what you searched FOR, with the "
    "search itself in its detection basis (the engine refuses an ABSENT "
    "that does not state one). A layer simply left out is not that: the "
    "scan document prints it as NOT SCANNED in red precisely because a "
    "missing layer reads to every later surface as a clean estate.")

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


#: A personal name as it appears in a written section: two or more adjacent
#: capitalised words. Deliberately crude and deliberately not a lookup — the
#: floor it enforces is "somebody did the contact pass", and the reviewer who
#: reads the section is the one who judges whether the names are right. It
#: skips the openers that would otherwise read as names.
_NAME_STOPWORDS = {
    "Chief", "Digital", "Officer", "The", "Its", "Their", "A", "An",
    "Credit", "Union", "Bank", "Board", "Executive", "Committee", "Group",
    "Information", "Technology", "Operating", "Financial", "Data", "Product",
    "Head", "Vice", "President", "Senior", "Managing", "Director", "Chair",
}
_NAME_RE = re.compile(r"\b([A-Z][a-z]{1,15})\s+([A-Z][a-z]{1,15})\b")


def _named_people(body: str) -> list[str]:
    """Distinct human names the section actually states."""
    out = []
    for first, last in _NAME_RE.findall(body):
        if first in _NAME_STOPWORDS or last in _NAME_STOPWORDS:
            continue
        name = f"{first} {last}"
        if name not in out:
            out.append(name)
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
            # NAMED PEOPLE, NOT A DESCRIPTION OF A STRUCTURE (owner,
            # 2026-08-31: leadership enrichment "with contacts"). A
            # leadership section that closes on "digital ownership sits with
            # a Chief Digital Officer" tells a category researcher nothing
            # it can weigh: it cannot search that person's talks, match a
            # LinkedIn post to a platform decision, or notice that the role
            # was filled three months ago. The connector pass that answers
            # this is Clay or Explorium, and it belongs here, before the
            # categories, not in a surface producer months downstream.
            need_named = int(spec.get("min_named") or 0)
            if need_named:
                found = _named_people(body)
                if len(found) < need_named:
                    return {
                        "section": key, "status": "OPEN",
                        "detail": (f"{len(body)} chars but names "
                                   f"{len(found)} identifiable "
                                   f"{'person' if len(found) == 1 else 'people'}"
                                   f" ({', '.join(found) or 'none'}); "
                                   f"{need_named} is the floor"),
                        "fix": ("run the contact pass now — Clay or "
                                "Explorium via the enrichment specialist — "
                                "and name the people with their roles. "
                                "Where a role genuinely has no public "
                                "holder, say so as a finding with the "
                                "ladder behind it: an unfilled digital "
                                "ownership role is one of the most "
                                "load-bearing facts a run can carry"),
                    }
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
    rows = [r for r in wb.rows(sheet) if any(_clean(v) for v in r.values())]
    n = len(rows)

    # THE FOUR-LAYER FLOOR (owner, 2026-08-31: "Let the technographic scans
    # happen in the prelim … such that when the category research happens
    # they already have deep background from enrichment").
    #
    # One row used to close this section, which made the technology baseline
    # whatever the first search happened to trip over, and left the
    # deliberate four-layer scan to run AFTER the categories — by which time
    # sixteen researchers had already re-discovered the estate one system at
    # a time, each without knowing what the others found. The scan is the
    # cheapest context in the run and it was being bought last.
    #
    # A layer where nothing was found is NOT a missing layer: it is an
    # ABSENT row, which is the scanner's own vocabulary and the distinction
    # that stops a gap in the looking from reading as a clean estate.
    want_layers = tuple(spec.get("layers") or ())
    if want_layers and n >= need:
        # `techscan.scan_state` already computes this, under the name the
        # scan's own renderer prints in red — "layers never looked at". Read
        # it rather than recomputing beside it: two answers to one question
        # is how a gate and the document it gates drift apart.
        seen = {_clean(r.get("Layer")).upper() for r in rows}
        missing = [lay for lay in want_layers if lay not in seen]
        if missing:
            return {
                "section": key, "status": "OPEN",
                "detail": (f"{sheet} has {n} row(s) but covers "
                           f"{len(want_layers) - len(missing)} of "
                           f"{len(want_layers)} layers — nothing for "
                           f"{', '.join(missing)}"),
                "fix": _TECH_FIX,
            }
    if n >= need:
        return {"section": key, "status": "RESEARCHED",
                "detail": (f"{n} row(s) in {sheet}"
                           + (f", all {len(want_layers)} layers covered"
                              if want_layers else ""))}
    verb = {"timeline": "timeline", "peers": "peers",
            "tech": "techscan record"}[kind]
    return {"section": key, "status": "OPEN",
            "detail": f"{sheet} has {n} row(s), {need} required",
            "fix": (f"engine.prelim {verb} …" if kind != "tech"
                    else _TECH_FIX)}


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
    # A PRELIM section that OWNS a tab declares that tab too, with the same
    # ladder. Until 2026-08-30 there were two independent declarations at
    # two layers — PRELIM's 60-character ladder and completeness's
    # 40-character reason — with nothing cross-checking them, so a run could
    # declare the timeline absent in one place and be asked for it again in
    # the other, or satisfy the weaker one and never meet the stronger.
    sheet = OWNS_SHEET.get(section)
    tab = None
    if sheet:
        from . import completeness as K
        if sheet not in K.NEVER_EMPTY and not [
                r for r in wb.rows(sheet) if any(_clean(v)
                                                 for v in r.values())]:
            tab = K.declare(wb, sheet, text)["sheet"]
    return {"section": section, "status": "DECLARED",
            "ladder_chars": len(text), "sheet_declared": tab}


def timeline(wb: RunWorkbook, *, date: str, event: str, signal: str,
             kind: str | None = None, body: str = "",
             maturity_effect: str = "", claim_label: str = "REPORTED",
             subcaps: list[str] | None = None,
             evidence: list[str] | None = None) -> dict:
    """One dated event, in the vocabulary the served C1 surface filters on.

    `signal` is the DIRECTION (POSITIVE/NEUTRAL/NEGATIVE) and `kind` is the
    CLASS — two different questions that were one column until 2026-08-30,
    which is why this tab could not feed the surface it was gathered for. A
    caller passing one of the nine old event classes as `signal` is bridged
    to its class rather than refused, and told so.
    """
    sig = _clean(signal).upper()
    k = _clean(kind).upper()
    bridged = None
    if sig not in TIMELINE_SIGNALS and sig in C.TIMELINE_KIND_BRIDGE:
        # An old-vocabulary caller: the word it passed is a CLASS.
        bridged, k, sig = sig, k or C.TIMELINE_KIND_BRIDGE[sig], "NEUTRAL"
    if sig not in TIMELINE_SIGNALS:
        raise PrelimRefusal(
            f"signal {sig!r} is not one of {', '.join(TIMELINE_SIGNALS)}. "
            f"The signal is the event's DIRECTION for maturity; its CLASS is "
            f"--kind, one of {', '.join(TIMELINE_KINDS)}.")
    if not k:
        raise PrelimRefusal(
            f"a timeline row needs a --kind, one of "
            f"{', '.join(TIMELINE_KINDS)}. D5 FILTERS on it, so an event "
            f"without one renders on a page no filter can reach.")
    if k not in TIMELINE_KINDS:
        raise PrelimRefusal(
            f"kind {k!r} is not one of {', '.join(TIMELINE_KINDS)}. A "
            f"near-miss is not a synonym — 'TECHNOLOGY' for PLATFORM and "
            f"'CAPABILITY' for DATA are events no filter can reach.")
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
        "Event_Date": d, "Title": _clean(event), "Body": _clean(body),
        "Kind": k, "Signal": sig,
        "Maturity_Effect": _clean(maturity_effect),
        "Claim_Label": _clean(claim_label).upper() or "REPORTED",
        "SubCap_IDs": ", ".join(subcaps or []),
        "Evidence_IDs": ", ".join(eids)})
    return {"date": d, "signal": sig, "kind": k, "evidence": eids,
            "bridged_from": bridged}


_CATEGORY_RE = re.compile(r"^(P\d+C\d+)")


def _category_of(subcap: str) -> str | None:
    """`P1C1.3.CU1` -> `P1C1`. The grain the app's peer parser requires."""
    m = _CATEGORY_RE.match(str(subcap or "").strip())
    return m.group(1) if m else None


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
    # CATEGORY GRAIN, not peer grain. The app's parser reads this tab by
    # matching the first column against a category id and discards every row
    # that does not — so the previous shape (one row per peer, Category_ID
    # blank) meant a run could do its peer work correctly and still land in
    # the app with zero peer scores, indistinguishable from a run that
    # declared the tab empty. The peer SET is frozen in Handoff_Lock, which
    # is where a set belongs; this tab is the per-category grid the medians
    # are later filled into.
    cats: list[str] = []
    for cell in wb.selected_subcaps():
        cid = _category_of(cell)
        if cid and cid not in cats:
            cats.append(cid)
    if not cats:
        raise PrelimRefusal(
            "this run has no selected subcapability, so there is no category "
            "for a peer comparison to be at. Select the scope first.")
    names = ", ".join(clean)
    for cid in cats:
        wb.append("Peer_Benchmarks", {
            # Category_Name is left for the assessment stage, which is where
            # a category acquires a rendered label; the parser stores None
            # for a blank and never invents one.
            "Category_ID": cid, "Category_Name": "",
            "Entity_Score": "", "Peer_Median": "", "Peer_P25": "",
            "Peer_P75": "", "Peer_N": len(clean),
            "Peer_Basis": f"{basis}: {_clean(rule)}",
            "Source_Cell": "", "Peer_Names": names, "Peer_Scores": "",
            "As_Of": _utcnow()[:10]})
    return {"peers": clean, "locked": locked, "rule": _clean(rule),
            "categories": cats}


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
    t.add_argument("--signal", required=True, choices=TIMELINE_SIGNALS,
                   help="the event's DIRECTION for maturity")
    t.add_argument("--kind", choices=TIMELINE_KINDS,
                   help="the event's CLASS, which the C1 surface filters on")
    t.add_argument("--body", default="",
                   help="what happened, in a sentence or two")
    t.add_argument("--maturity-effect", default="",
                   help="the consequence for maturity, with one clause of "
                        "reasoning")
    t.add_argument("--claim-label", default="REPORTED")
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
                                      signal=a.signal, kind=a.kind,
                                      body=a.body,
                                      maturity_effect=a.maturity_effect,
                                      claim_label=a.claim_label,
                                      subcaps=a.subcap,
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
