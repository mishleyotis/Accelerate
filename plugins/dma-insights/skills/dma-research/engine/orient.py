#!/usr/bin/env python3
"""The session opener, and the one command R32 makes every agent run.

WHY THIS EXISTS. Three findings all land on this file:

  AUD-0006 / AUD-0085  a subcap with evidence banked and no synthesis is
      `volleyed`. The card server only served `pending`, so on resume the
      interrupted subcap was skipped; at category end orient printed
      `next_card {}` and `do_first ['state clean - proceed to next_card']`
      while `volleyed: 1` remained open. The subcap was never re-served,
      never closed, and escaped the synthesis gate.
  AUD-0007  every entry of `do_first` was populated from a gate file nothing
      wrote, so the whole gate view read null and the list said "clean".
  AUD-0015  the card was built without binding the entity, so 15 literal
      `{entity}` placeholders reached the agent, which then fired them.
  AUD-0037  the >=40 search-op wall was reported (45/40) and then walked past.

The rule this file now holds: **orient may not say the state is clean while
anything is open.** `do_first` is derived from open work, and when there is
open work there is no "clean" branch to take.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
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
from . import floors_gate
from . import ledger as L
from . import prelim
from . import runstate
from .workbook import RunWorkbook

#: A work card must fit a turn. AUD-0143 measured the card exceeding its
#: stated ~750 tok in 790 of 851 cases under the invocation the protocol
#: prescribes, with nothing gating card size. Measured here in characters —
#: ~4 chars/token is the working ratio — and reported on the card itself.
CARD_CHAR_CEILING = 3200


def orient(wb: RunWorkbook, category: str | None, *,
           qa_dir: Path | None = None) -> dict:
    md = wb.metadata()
    entity = str(md.get("entity_name") or "").strip()
    if not entity or "{" in entity:
        # AUD-0015 at its source: an unbound entity is not a run.
        raise ValueError(
            f"Run_Metadata.entity_name is {entity!r}. Every question this "
            f"command issues names the entity; an unbound card produces "
            f"searches for a literal placeholder.")
    tax = C.taxonomy()
    cats = [category] if category else list(tax.categories)
    budget = L.stats(wb, category)

    state = {"run_id": md.get("run_id"), "entity": entity,
             "sub_vertical": md.get("sub_vertical") or None,
             "scope_mode": md.get("scope_mode"),
             "reference_date": md.get("reference_date"),
             "catalogue_version": md.get("catalogue_version"),
             "budget": budget}

    work = {c: L.worklist(wb, c) for c in cats}
    open_volleyed = [s for c in cats for s in work[c]["volleyed"]]
    open_pending = [s for c in cats for s in work[c]["pending"]]

    gates = {}
    for c in cats:
        v = floors_gate.read_verdict(qa_dir, c) if qa_dir else None
        gates[c] = {"verdict": "NOT_RUN",
                    "reason": "no recorded verdict at "
                              f"{qa_dir}/floors_{c}.json"} if v is None else v

    do_first: list[str] = []

    # 0. PRELIM outranks everything, including the budget wall — a run that
    #    has not profiled the institution has nothing to spend the budget ON.
    #    The Golden 1 calibration went start -> category worklist and finished
    #    with Entity_Timeline, Tech_Register and Peer_Benchmarks empty,
    #    because no phase had ever been asked to fill them.
    prelim_state = prelim.state(wb)
    if prelim_state["blocks_category_dispatch"]:
        opens = prelim_state["open"]
        if opens:
            do_first.append(
                "PRELIM is open — no category card will be served. "
                f"{len(opens)} section(s) outstanding: {', '.join(opens)}. "
                f"Run `engine.prelim state` for the fix line on each.")
        else:
            do_first.append(
                "every PRELIM section is closed but PRELIM was never signed "
                "off. Run `engine.prelim complete`.")

    # 1. The wall comes first, and it is an instruction, not a number.
    if budget["checkpoint_required"]:
        do_first.append(
            f"STOP: {budget['search_ops']} search-ops this run against a "
            f"ceiling of {budget['search_op_ceiling']}. Checkpoint the run "
            f"(runstate.checkpoint) and end the turn. Do not take the next "
            f"card.")

    # 2. A recorded FAIL is work, and it is named.
    for c, g in gates.items():
        if g.get("gate") == "FAIL":
            do_first.append(
                f"{c}: floors gate FAILED on {', '.join(g.get('blocking', []))} "
                f"— repair before taking new work")
        elif g.get("verdict") == "NOT_RUN" and not work[c]["pending"]:
            do_first.append(
                f"{c}: no pending subcaps and no recorded gate verdict. Run "
                f"floors_gate --category {c} --require-synthesis; a category "
                f"is not closed by running out of cards.")

    # 3. Volleyed work outranks new work. This is AUD-0006's whole fix.
    if open_volleyed:
        do_first.append(
            f"{len(open_volleyed)} subcap(s) hold evidence with no synthesis "
            f"and will never be re-served as pending: "
            f"{', '.join(open_volleyed[:8])}"
            + (" …" if len(open_volleyed) > 8 else "")
            + ". Synthesise these before taking a new card.")

    if not do_first:
        if open_pending:
            do_first.append(f"{len(open_pending)} pending subcap(s) remain — "
                            f"take next_card.")
        else:
            do_first.append("no open work in scope: closed and gate-passed.")

    # The card. Withheld while the budget wall or volleyed work is open —
    # handing over a new card is exactly what AUD-0006 and AUD-0037 measured.
    card = None
    blocked = None
    if prelim_state["blocks_category_dispatch"]:
        blocked = ("PRELIM is open: "
                   + (", ".join(prelim_state["open"]) or "not signed off"))
    elif budget["checkpoint_required"]:
        blocked = "search-op ceiling reached"
    elif open_volleyed:
        blocked = f"{len(open_volleyed)} volleyed subcap(s) must be synthesised first"
        card = _card(wb, open_volleyed[0], entity, md, mode="synthesise")
    elif open_pending:
        card = _card(wb, open_pending[0], entity, md, mode="research")

    return {
        "state": state,
        "worklist": {c: {k: (len(v) if isinstance(v, list) else v)
                         for k, v in work[c].items()} for c in cats},
        "open": {"volleyed": open_volleyed, "pending_count": len(open_pending)},
        "gate": gates if category else {c: g.get("gate") or g.get("verdict")
                                        for c, g in gates.items()},
        "prelim": {k: prelim_state[k] for k in
                   ("prelim_status", "open", "blocks_category_dispatch")},
        "do_first": do_first,
        "next_card": card,
        "next_card_withheld_because": blocked if card is None else None,
        "clean": not open_volleyed and not open_pending
                 and not prelim_state["blocks_category_dispatch"]
                 and all(g.get("gate") == "PASS" for g in gates.values()),
    }


def _card(wb: RunWorkbook, subcap: str, entity: str, md: dict,
          *, mode: str) -> dict:
    """One work card, with the entity BOUND.

    Every question is rendered here, once, with the entity substituted. A
    card that still carries a brace after rendering is refused rather than
    handed over — AUD-0015 measured 15 unbound placeholders per card reaching
    an agent that then searched for them."""
    tax = C.taxonomy()
    row = wb.scoring_row(subcap) or {}
    sv = md.get("sub_vertical") or ""
    ev_mode = str(md.get("evidence_mode") or "PUBLIC")
    # The KG's split: only the questions ANSWERABLE in this run's evidence
    # mode are asked; the rest ride the card as deferred discovery questions
    # so the gap is disclosed in the synthesis, never silently unprobed.
    from . import kg as _kg
    split = _kg.dqs_for(wb, subcap, ev_mode)
    if split["ask"] or split["deferred"]:
        questions = [{"facet": d["facet"],
                      "question": _bind(str(d["question"] or ""), entity, sv),
                      "probe_tier": d.get("probe_tier"),
                      "internal_sources": d.get("internal_sources"),
                      "public_sources": d.get("public_sources")}
                     for d in sorted(split["ask"],
                                     key=lambda d: d.get("order") or 0)]
        deferred = [{"facet": d["facet"],
                     "discovery_question":
                         _bind(str(d["question"] or ""), entity, sv),
                     "mode_fit": d.get("mode_fit")}
                    for d in split["deferred"]]
    else:
        questions = [{"facet": f, "question": _bind(_DEFAULT_DQ[f], entity, sv)}
                     for f in C.FACETS]
        deferred = []
    queries = [{"facet": f, "query": _bind(_DEFAULT_Q[f], entity, sv)}
               for f in C.FACETS]
    card = {
        "id": subcap, "mode": mode, "entity": entity,
        "evidence_mode": ev_mode,
        "category": subcap.split(".")[0],
        "tier": tax.tier.get(subcap),
        "evidence_on_row": row.get("Evidence_IDs"),
        "questions": questions,
        "deferred_questions": deferred,
        "queries": queries,
        "kg_built": bool(str(md.get("kg_checksum") or "").strip()),
    }
    blob = json.dumps(card)
    leftovers = [t for t in ("{entity}", "{sv}", "{{", "}}") if t in blob]
    if leftovers:
        raise ValueError(
            f"card for {subcap} still carries unbound token(s) {leftovers}; "
            f"refusing to hand it over")
    card["size_chars"] = len(blob)
    card["size_within_ceiling"] = len(blob) <= CARD_CHAR_CEILING
    if not card["size_within_ceiling"]:
        card["size_note"] = (
            f"{len(blob)} chars exceeds the {CARD_CHAR_CEILING} ceiling; the "
            f"card is served anyway and the overrun is stated rather than "
            f"hidden (AUD-0143)")
    return card


_DEFAULT_DQ = {
    "works": ("Where has {entity} demonstrated this capability, from the "
              "earliest signal through refreshes, expansions or stalls to today?"),
    "fails": ("What has {entity} attempted here that did not hold — delayed, "
              "descoped, abandoned or repeated?"),
    "value": ("What does this capability change for {entity} — which decisions "
              "does it make faster, cheaper or more accountable?"),
    "contradicts": ("What public record cuts against {entity}'s account of "
                    "this capability?"),
    "corroborates": ("Which independent party — regulator, analyst, customer "
                     "body — has said something about {entity} here?"),
}

_DEFAULT_Q = {
    "works": '"{entity}" {sv} implementation OR rollout OR "went live"',
    "fails": '"{entity}" delayed OR descoped OR postponed OR "did not"',
    "value": '"{entity}" results OR outcome OR adoption OR "reduced by"',
    "contradicts": ('"{entity}" enforcement OR lawsuit OR criticism OR '
                    'abandoned OR "yet to" OR complaint'),
    "corroborates": '"{entity}" regulator OR analyst OR review OR rating',
}


def _bind(text: str, entity: str, sv: str) -> str:
    return (text.replace("{entity}", entity)
                .replace("{sv}", sv or "")
                .replace("  ", " ").strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--root")
    ap.add_argument("--category")
    ap.add_argument("--skeleton", metavar="SUBCAP",
                    help="print the field names a synthesis must carry. NOT a "
                         "fillable template: AUD-0009 measured the old one "
                         "passing every gate unmodified.")
    a = ap.parse_args(argv)
    r = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = r.open()
    if a.skeleton:
        print(json.dumps({
            "subcap": a.skeleton,
            "required_fields": {k: f"minimum {v} characters of your own prose"
                                for k, v in L.SYNTHESIS_REQUIRED.items()},
            "dq_fields": {f: "an answer, or NOT_RUN: <reason worth reading>"
                          for f in L.DQ_FIELDS},
            "note": ("No default values are supplied on purpose. The previous "
                     "skeleton shipped STUB_ strings that satisfied five of "
                     "six length constraints and closed the subcap; the write "
                     "path now refuses placeholder text, so a filled template "
                     "would be rejected rather than accepted."),
        }, indent=2))
        return 0
    out = orient(wb, a.category, qa_dir=r.qa_dir)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
