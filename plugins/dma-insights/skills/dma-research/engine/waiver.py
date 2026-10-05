"""A person's decision to accept a research gap — recorded, bounded, disclosed.

WHY THIS EXISTS (arbor-bank-2026-10-05, MEM-0591). The driver withholds a
category whose repair stalls and says "a person decides whether to repair at
the source or accept the gap" — but nothing could record the second answer.
Three walls stood in the way of an accepted gap: the research done-check
(`brief.categories_needing_dispatch`), the scoring boundary
(`assessment.research_ready` → `handoff._assert_scoreable`) and the SCORING
gate's `unscored` term. A waiver is the one record all three read.

WHAT A WAIVER IS — and is not:

  * Named cells in ONE category, a PERSON's name, a reason. Never an agent:
    the stall message hands the decision to a person, and the waiver is that
    person's signature.
  * Only cell-level content failures are waivable (`WAIVABLE_TERMS`): a
    challenge that FAILED, or a claim label its evidence cannot carry. A
    category-level floor, a missing synthesis, a missing or non-independent
    challenge, an unresolved citation — none of these can be waived; the
    recorder refuses and names them.
  * It covers a category only while the LIVE gate's blocking cells all sit
    inside it. A new failure anywhere else re-opens the category: a waiver
    is a decision about named cells, not a pass for the category.
  * Waived cells are left UNSCORED — null, never a default that looks like
    data (invariant 9). Scoring still refuses them (`assessment.score`
    requires a PASS challenge); the SCORING gate exempts exactly them from
    `unscored`; the roll-ups already skip a null.
  * Disclosed: the Gate_Log row (internal), and at scoring open one
    Caps_Applied_Log row per waived cell stating it is unscored, why and by
    whose decision — the sheet `heatmap.safeguard_gates` reads its caps from.
"""
from __future__ import annotations

import json
import re

from . import ledger as L
from .workbook import RunWorkbook

GATE = "FLOORS_WAIVER"

#: Cell-level CONTENT failures a person may accept. Everything else the floors
#: gate blocks on is a process the run must complete, and stays unwaivable.
WAIVABLE_TERMS = frozenset({"challenge_failed", "claim_unsupported"})

REASON_MIN = 40

#: A waiver is signed by a person. These are the shapes an agent's name takes.
_AGENTISH = re.compile(r"(producer|challenger|conductor|scorer|critic|agent|"
                       r"workflow|claude|session|bot)\b", re.I)


class WaiverRefusal(ValueError):
    pass


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def live_blocking(wb: RunWorkbook, category: str) -> tuple[set[str], dict[str, set[str]]]:
    """(blocking terms, {term: cells}) of the floors gate evaluated NOW,
    never recorded (persist=False), in the mode scoring requires."""
    from . import floors_gate
    from .floors_gate import _cells_of
    out = floors_gate.run(wb, category, require_synthesis=True, persist=False)
    terms = set(out.get("blocking") or [])
    cells: dict[str, set[str]] = {}
    for t in terms:
        cells[t] = {c for item in (out.get(t) or []) for c in _cells_of(item)}
    return terms, cells


def record(wb: RunWorkbook, *, category: str, cells, by: str, reason: str) -> dict:
    """Record a person's waiver for named cells of one category."""
    category = _clean(category).upper()
    cells = sorted({_clean(c) for c in (cells or []) if _clean(c)})
    by, reason = _clean(by), _clean(reason)
    if not by or _AGENTISH.search(by):
        raise WaiverRefusal(
            f"a waiver is a person's decision; {by!r} is not a person's name. "
            f"The stall hands this to a person — record it under their name.")
    if len(reason) < REASON_MIN:
        raise WaiverRefusal(f"the reason is {len(reason)} chars; state why the gap "
                            f"is accepted in at least {REASON_MIN}")
    if not cells:
        raise WaiverRefusal("name the cells; a waiver never covers a whole category")
    foreign = [c for c in cells if c.split(".")[0] != category]
    if foreign:
        raise WaiverRefusal(f"{foreign} are not cells of {category}")
    terms, by_term = live_blocking(wb, category)
    unwaivable = sorted(terms - WAIVABLE_TERMS)
    if unwaivable:
        raise WaiverRefusal(
            f"{category} blocks on {unwaivable}, which are not waivable (only "
            f"{sorted(WAIVABLE_TERMS)}); complete that work first")
    named = set().union(*by_term.values()) if by_term else set()
    unnamed = [c for c in cells if c not in named]
    if unnamed:
        raise WaiverRefusal(
            f"{unnamed} are not failing the live gate; a waiver covers only "
            f"cells the gate names ({sorted(named)})")
    detail = {"cells": cells,
              "terms": {c: sorted(t for t, cs in by_term.items() if c in cs)
                        for c in cells},
              "by": by, "reason": reason}
    L.append_gate(wb, gate=GATE, scope=category, verdict="FAIL",
                  detail=json.dumps(detail, sort_keys=True), blocking=False)
    return {"category": category, **detail,
            "covers_category": not (named - set(cells))}


def active(wb: RunWorkbook) -> dict[str, dict]:
    """{category: waiver} — the latest FLOORS_WAIVER row per category."""
    out: dict[str, dict] = {}
    for g in wb.rows("Gate_Log"):
        if _clean(g.get("Gate")) != GATE:
            continue
        try:
            d = json.loads(str(g.get("Detail") or ""))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("cells"):
            d["at"] = g.get("Timestamp")
            out[_clean(g.get("Scope")).upper()] = d
    return out


def waived_cells(wb: RunWorkbook) -> dict[str, dict]:
    """{cell: {category, by, reason, terms, at}} for every active waiver."""
    out = {}
    for cat, d in active(wb).items():
        for c in d["cells"]:
            out[c] = {"category": cat, "by": d.get("by"), "reason": d.get("reason"),
                      "terms": (d.get("terms") or {}).get(c, []), "at": d.get("at")}
    return out


def covers(wb: RunWorkbook, category: str) -> tuple[bool, str]:
    """Does a recorded waiver account for EVERY live blocker of `category`?"""
    w = active(wb).get(_clean(category).upper())
    if not w:
        return False, "no waiver recorded"
    terms, by_term = live_blocking(wb, category)
    if not terms:
        return True, "the live gate passes; the waiver is moot"
    if terms - WAIVABLE_TERMS:
        return False, f"blocks on unwaivable {sorted(terms - WAIVABLE_TERMS)}"
    named = set().union(*by_term.values())
    outside = sorted(named - set(w["cells"]))
    if outside:
        return False, f"cells outside the waiver now fail: {outside}"
    return True, f"waived by {w.get('by')} ({len(w['cells'])} cell(s))"


def disclosure(cell: str, w: dict) -> str:
    """The one sentence a waived cell carries wherever it is shown."""
    terms = ", ".join(w.get("terms") or []) or "a failed check"
    return (f"UNSCORED — research gap accepted ({terms}); waived by "
            f"{w.get('by')}: {w.get('reason')}")


def disclose_in_caps_log(wb: RunWorkbook) -> list[str]:
    """At scoring open: one Caps_Applied_Log row per waived, unscored cell,
    with no score (null) and the disclosure as its caps text."""
    rows = {str(r.get("SubCap_ID")): r for r in wb.scoring_rows()}
    have = {_clean(r.get("subcap_id")) for r in wb.rows("Caps_Applied_Log")}
    done = []
    for cell, w in sorted(waived_cells(wb).items()):
        r = rows.get(cell) or {}
        if r.get("Score") not in (None, ""):
            continue                     # repaired and scored since; nothing to disclose
        crow = {"subcap_id": cell, "category": r.get("Category"),
                "final_score": None, "evidence_ceiling": None,
                "caps_applied": disclosure(cell, w)}
        if cell in have:
            wb.update_row("Caps_Applied_Log", "subcap_id", cell, crow, save=False)
        else:
            wb.append("Caps_Applied_Log", crow, save=False)
        wb.set_scoring(cell, {"Caps_Applied": crow["caps_applied"]}, save=False)
        done.append(cell)
    if done:
        wb.save()
    return done
