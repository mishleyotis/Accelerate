#!/usr/bin/env python3
"""The research -> assessment handoff, built FROM the workbook.

WHY THIS EXISTS, and what it deliberately is NOT.

AUD-0002 measured `research_handoff.json` as the de-facto inter-skill
contract: dma-assessment's documented primary mode keys on the FILE's
presence ("IF FOUND -> set RESEARCH_HANDOFF mode, skip Phase 1"), the
workbook played no role in the handoff at all, and the builder read five JSON
sources and zero sheets. The audit's own repair direction is explicit: "the
correct repair direction is to move the recorded state into the WORKBOOK, not
to add readers of the JSON."

So this file is a PROJECTION, not an interface. The workbook is the handoff;
`Handoff_Lock` carries the catalogue hash the assessment compares against and
refuses on. What is emitted here is a convenience index over the same sheets,
and it says so in its own `_contract` block, so a reader that starts treating
it as the authority is contradicted by the artefact itself.

Three further defects are designed out rather than carried over:

  AUD-0065  triangulation / why_it_matters / dma_impact are CARRIED. They were
      omitted, and the strip deleted the only other copy.
  AUD-0078  a subcap with no evidence is emitted with `ceiling_band: null`.
      `band_from_hints` used to return ("M2", 0.5) for a subcap nobody had
      looked at, so 45 of 49 records in a real run asserted a band; and the
      category ceiling was then converted to a FLOAT, putting a maturity
      score into the one artefact scores are forbidden in.
  AUD-0138  safeguard_gates / tech_utilization / critical_unknowns /
      org_capability_proxies were hardcoded to empty containers regardless of
      ledger content. They are read from the workbook, and a facet that was
      never run is emitted as NOT_RUN with its reason — never as `[]`, which
      reads as "we looked and found nothing".
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
from . import completeness, floors_gate, quality as Q, runstate, validator
from .workbook import RunWorkbook, FLOOR_ITEMS, _split_ids

HANDOFF_NAME = "research_handoff.json"


def build(wb: RunWorkbook, *, qa_dir: Path | None = None,
          strict: bool = True) -> dict:
    """Project the workbook into a handoff index, or refuse."""
    fails = validator.validate(wb.path, run_id=str(wb.metadata().get("run_id")))
    if fails and strict:
        raise SystemExit(
            "REFUSED: the workbook does not satisfy its own contract, so a "
            "handoff built from it would carry the defect forward:\n  "
            + "\n  ".join(str(f) for f in fails))
    # The validator checks SHAPE; a sheet with correct headers and no rows
    # passes it. Golden 1 shipped six empty tabs that way, so the handoff
    # also asks whether there is anything IN the workbook.
    if strict:
        try:
            completeness.require(wb)
        except completeness.CompletenessRefusal as e:
            raise SystemExit(f"REFUSED: {e}") from None
    md = wb.metadata()
    register = wb.evidence_index()
    tax = C.taxonomy()

    records, by_cat = [], {}
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell:
            continue
        eids = [i.split(":")[0] for i in _split_ids(r.get("Evidence_IDs"))
                if i and i != C.NO_EVIDENCE]
        synth = str(r.get("Dominant_Claim") or "").strip()
        band = str(r.get("Ceiling_Band") or "").strip() or None
        if band and band not in C.BANDS:
            raise SystemExit(
                f"{cell}: Ceiling_Band {band!r} is not one of {C.BANDS}")
        rec = {
            "subcap_id": cell,
            "category": cell.split(".")[0],
            "tier": tax.tier.get(cell),
            "evidence_ids": eids,
            "evidence_count": len(eids),
            "floor_met": len(eids) >= FLOOR_ITEMS,
            # AUD-0078: null, not a default that looks like data.
            "ceiling_band": band if synth else None,
            "uncertainty": _num(r.get("Uncertainty")) if synth else None,
            "state": ("closed" if synth else
                      "volleyed" if eids else "not_researched"),
            "research_synthesis": None if not synth else {
                "dominant_claim": r.get("Dominant_Claim"),
                "claim_label": r.get("Claim_Label"),
                "what_we_found": r.get("What_We_Found"),
                # the three AUD-0065 named
                "triangulation": r.get("Triangulation"),
                "why_it_matters": r.get("Why_It_Matters"),
                "dma_impact": r.get("DMA_Impact"),
                "ceiling_reasoning": r.get("Ceiling_Reasoning"),
                "facet_coverage": r.get("Facet_Coverage"),
                "contradiction_disposition": r.get("Contradiction_Disposition"),
                "discovery_questions": r.get("Discovery_Questions"),
                "challenge_verdict": r.get("Challenge_Verdict"),
                "dq_answers": {f.lower().replace("dq_", ""): r.get(f)
                               for f in ("DQ_Works", "DQ_Fails", "DQ_Value",
                                         "DQ_Corroborates", "DQ_Contradicts")},
            },
        }
        records.append(rec)
        by_cat.setdefault(rec["category"], []).append(rec)

    # Category ceilings stay BAND WORDS. AUD-0078 measured v1_compat turning
    # them into floats — a numeric maturity score in the artefact R1 forbids
    # scores in.
    ceilings = {}
    for cat, rows in sorted(by_cat.items()):
        bands = [r["ceiling_band"] for r in rows if r["ceiling_band"]]
        ceilings[cat] = {
            "ceiling_band": max(bands, key=C.BANDS.index) if bands else None,
            "basis": (f"{len(bands)} of {len(rows)} subcaps carry a band"
                      if bands else
                      "no subcap in this category reached a band; the category "
                      "has no ceiling and stating one would be invention"),
            "floor_pass_rate": round(
                sum(1 for r in rows if r["floor_met"]) / len(rows), 3),
        }

    gates = {}
    for cat in sorted(by_cat):
        v = floors_gate.read_verdict(qa_dir, cat) if qa_dir else None
        gates[cat] = ({"verdict": "NOT_RUN",
                       "reason": "the floors gate has no recorded verdict for "
                                 "this category"} if v is None
                      else {"verdict": v["gate"], "blocking": v["blocking"],
                            "require_synthesis": bool(v.get("require_synthesis"))})

    # AUD-0116: THE SYNTHESIS-AND-CHALLENGE CHAIN IS SEQUENCED HERE, not left to
    # whoever runs the assessment stage to remember. (Extracted to
    # `_assert_scoreable` so it is unit-testable without first satisfying the
    # validator and completeness gates above.)
    if strict:
        _assert_scoreable(gates)

    return {
        "_contract": {
            "authority": "the scoring workbook",
            "this_file": ("a read-only index over the workbook's sheets. It is "
                          "NOT the interface: the assessment stage reads the "
                          "workbook and compares Handoff_Lock.catalogue_hash "
                          "before scoring. If this file and the workbook "
                          "disagree, the workbook is right."),
            "workbook": str(wb.path),
            "handoff_lock": wb.handoff_lock(),
        },
        "run": {k: md.get(k) for k in (
            "run_id", "entity_name", "entity_id", "sub_vertical", "scope_mode",
            "reference_date", "catalogue_version", "catalogue_hash",
            "engine_version")},
        "counts": C.counts(),
        "coverage": wb.coverage(),
        "gates": gates,
        "capability_ceilings": ceilings,
        "subcap_records": records,
        "evidence_register": [
            {"e_id": e, "source_name": v.get("Source_Name"),
             "source_url": v.get("Source_URL"), "tier": v.get("Tier"),
             "published": v.get("Date_Published"), "recency": v.get("Recency"),
             "claim_type": v.get("Claim_Type"), "origin": v.get("Origin"),
             "subcaps": _split_ids(v.get("SubCap_IDs")),
             "excerpt": v.get("Excerpt")}
            for e, v in sorted(register.items())],
        "timeline": wb.rows("Entity_Timeline"),
        # AUD-0138: measured, or NOT_RUN with a reason. Never `[]`.
        **_facets(wb, records),
    }


def _assert_scoreable(gates: dict) -> None:
    """Refuse a handoff whose categories are not ready to be SCORED (AUD-0116).

    ROOT CAUSE this fixes: `--require-synthesis` was opt-in on the floors gate,
    and handoff — the one boundary between research and scoring — only REPORTED
    whatever verdict happened to be recorded. So a category could reach scoring
    "volleyed" (evidence gathered, never synthesised, never challenged), and the
    score would be struck on raw evidence rather than on a challenged claim. The
    independent challenge existed as a gate TERM but nothing forced the mode
    that runs it before the score.

    A handoff feeds the assessment/scoring stage. So it is refused unless every
    category cleared the gate in the mode that REQUIRES every evidenced subcap
    to be synthesised AND independently challenged (the synthesis_missing,
    challenge_missing and challenge_not_independent terms all live behind
    require_synthesis / the synthesised-row checks). That makes "synthesise and
    independently challenge before you score" structural: a run cannot skip it
    and reach a handoff, whoever is driving."""
    not_ready = {}
    for cat in sorted(gates):
        g = gates[cat]
        if g.get("verdict") != "PASS":
            not_ready[cat] = (f"floors gate is {g.get('verdict')}"
                              + (f" (blocking: {g.get('blocking')})"
                                 if g.get("blocking") else ""))
        elif not g.get("require_synthesis"):
            not_ready[cat] = (
                "floors gate passed WITHOUT --require-synthesis, so its "
                "evidenced subcaps were never required to be synthesised and "
                "independently challenged")
    if not_ready:
        lines = "\n  ".join(f"{c}: {why}" for c, why in not_ready.items())
        raise SystemExit(
            "REFUSED: a handoff feeds the scoring stage, and these categories "
            "are not ready to be scored — every evidenced subcap must be "
            "synthesised and then independently challenged (run the floors gate "
            "with --require-synthesis and clear it) BEFORE a handoff, so the "
            f"score reflects a challenged claim and not raw evidence:\n  {lines}")


def _facets(wb: RunWorkbook, records: list[dict]) -> dict:
    """The four fields that used to be hardcoded empty."""
    searches = wb.rows("Search_Log")
    gate_rows = wb.rows("Gate_Log")
    proxies = [r for r in wb.scoring_rows()
               if str(r.get("Proxy_Log") or "").strip()]
    unknowns = [r["subcap_id"] for r in records
                if r["state"] == "not_researched"]
    tech = [e for e in wb.rows("Evidence_Detail")
            if str(e.get("Claim_Type") or "") == "FACT"
            and "utilis" in str(e.get("Excerpt") or "").lower()
            or "utiliz" in str(e.get("Excerpt") or "").lower()]

    def facet(name, value, ran: bool, reason: str):
        return {name: value} if ran else {
            name: {"outcome": "NOT_RUN", "reason": reason}}

    out = {}
    out.update(facet("safeguard_gates",
                     [{"gate": g["Gate"], "scope": g["Scope"],
                       "verdict": g["Verdict"], "detail": g["Detail"]}
                      for g in gate_rows],
                     bool(gate_rows),
                     "no gate has been run against this run yet"))
    out.update(facet("tech_utilization",
                     [{"e_id": e.get("E_ID"), "excerpt": e.get("Excerpt")}
                      for e in tech],
                     bool(searches),
                     "no search was run, so presence-vs-utilisation was never "
                     "distinguishable"))
    out.update(facet("critical_unknowns", unknowns, True,
                     "every selected subcap was researched"))
    out.update(facet("org_capability_proxies",
                     {str(r["SubCap_ID"]): r.get("Proxy_Log") for r in proxies},
                     bool(proxies),
                     "no proxy search was logged on any row"))
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--root")
    ap.add_argument("--out")
    ap.add_argument("--no-strict", action="store_true")
    a = ap.parse_args(argv)
    r = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = r.open()
    doc = build(wb, qa_dir=r.qa_dir, strict=not a.no_strict)
    out = Path(a.out) if a.out else r.deliverables / HANDOFF_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, default=str))
    print(json.dumps({"written": str(out),
                      "subcap_records": len(doc["subcap_records"]),
                      "evidence": len(doc["evidence_register"])}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
