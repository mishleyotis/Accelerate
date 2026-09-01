#!/usr/bin/env python3
"""The category gate — and it writes where orient reads.

WHY THIS EXISTS. AUD-0007 is the sharpest finding in the research half of the
audit: the gate's output had THREE readers and NO WRITER. `floors_gate.py`
printed JSON to stdout; `orient.py:71`, `render_client_report.py:45` and
`render_findings.py:30` all read `$RUN/07_qa/floors_{cat}.json`, which nothing
created. Demonstrated live: the gate returned FAIL with exit 1 while orient on
the same run printed `gate: null` and `do_first: ['state clean']`.

So `run()` WRITES the file, and also appends to the workbook's Gate_Log, and
returns the verdict. Three surfaces, one computation, no path where a gate can
fail and the next command report clean.

The second half of the fix is what the gate MEASURES. The old one checked
field presence and length, which is why AUD-0016 could feed it an unmodified
STUB skeleton with two mechanical edits and get `{'gate': 'PASS'}`. The checks
below are the ones the audit proved absent:

    AUD-0016/0019/0026  content plausibility, not length
    AUD-0022            the >=20-items-per-category floor USED, not reported
    AUD-0025/0082       a challenge verdict must EXIST
    AUD-0073            the contradicts probe read from the query
    AUD-0076            sibling evidence smearing
    AUD-0079            absence claims declared
    AUD-0080            ladders counted, not attested
    AUD-0083            every cited id resolved against the register
    AUD-0021            proxy-only evidence cannot close as FACT
    AUD-0115            >=70% of a category's subcaps carry resolvable evidence
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
from . import ledger as L
from . import quality as Q
from . import runstate
from .workbook import (RunWorkbook, FLOOR_ITEMS, FLOOR_CATEGORY_ITEMS,
                       COVERAGE_FLOOR, _split_ids)


#: Computed every run, and deliberately NOT blocking. Kept as a named set so
#: the choice is reviewable: `advisory` in each verdict says which of these
#: actually fired, so anyone arguing one should be promoted to blocking can
#: see its real hit rate first instead of guessing.
ADVISORY_TERMS = (
    "closed_below_floor",
    "contradicts_unprobed",
    "followups_outstanding",
    "ladder_overstated",
    "timeline_missing",
)


def run(wb: RunWorkbook, category: str, *, require_synthesis: bool = False,
        qa_dir: Path | None = None) -> dict:
    """Evaluate one category and RECORD the verdict in both places."""
    tax = C.taxonomy()
    if category not in tax.categories:
        raise ValueError(f"{category} is not one of the {tax.n_categories} "
                         f"categories in catalogue {tax.version}")
    rows = [r for r in wb.scoring_rows()
            if str(r.get("SubCap_ID") or "").startswith(category + ".")]
    register = wb.evidence_index()
    searches = wb.rows("Search_Log")
    cat_searches = [s for s in searches
                    if str(s.get("SubCap_ID") or "").startswith(category)]

    findings: dict[str, list] = {
        "dq_gaps": [], "unresolved_citations": [], "absence_undeclared": [],
        "closed_below_floor": [], "synthesis_missing": [], "boilerplate": [],
        "claim_unsupported": [], "contradicts_unprobed": [],
        "single_source_fact": [],
        "ladder_overstated": [], "evidence_smear": [], "challenge_missing": [],
        "challenge_not_independent": [],
        "timeline_missing": [], "followups_outstanding": [],
        "absence_unsearched": [],
    }
    items = 0
    searched_cells = 0
    evidenced_cells = 0
    for r in rows:
        cell = str(r["SubCap_ID"]).strip()
        eids = [i.split(":")[0] for i in _split_ids(r.get("Evidence_IDs"))
                if i and i != C.NO_EVIDENCE]
        items += len(eids)
        # AUD-0115: a subcap COUNTS toward coverage only if at least one of
        # its cited ids actually resolves in the register — a dead citation is
        # not evidence, and neither is an empty cell.
        if any(e in register for e in eids):
            evidenced_cells += 1

        # AUD-0083: the archive's own golden fixture cited an item that did
        # not exist, and nothing resolved a citation at any point.
        dead = [e for e in eids if e not in register]
        if dead:
            findings["unresolved_citations"].append(
                {"subcap": cell, "ids": sorted(set(dead))})

        synthesised = bool(str(r.get("Dominant_Claim") or "").strip())
        if len(eids) < FLOOR_ITEMS:
            findings["closed_below_floor"].append(
                {"subcap": cell, "items": len(eids), "floor": FLOOR_ITEMS})
        if require_synthesis and not synthesised:
            findings["synthesis_missing"].append(cell)

        # YOU CANNOT REPORT THAT THERE IS NOTHING WITHOUT HAVING LOOKED.
        #
        # Reported 2026-08-30 against a live workbook: "the research agents
        # have a huge issue of leaving most subcaps unresearched and just
        # marking no evidence without doing deep searches."
        #
        # Nothing here could catch that. A subcap with zero evidence hit
        # `closed_below_floor`, which is ADVISORY, and then `if not
        # synthesised: continue` skipped every remaining check — absence
        # declaration, DQ coverage, the contradicts probe, all of it. So a
        # category passed on ~20 items contributed by a handful of worked
        # subcaps while the rest were empty, and the verdict said PASS.
        #
        # An empty subcap is only honest if somebody searched for it. The
        # Search_Log records every retrieval with its tool, in every evidence
        # mode, so "no rows for this cell" means no one looked — which is a
        # different claim from "we looked and found nothing", and only the
        # second one may close a subcap.
        cell_searches = [s for s in cat_searches
                         if str(s.get("SubCap_ID") or "").strip() == cell]
        if cell_searches:
            searched_cells += 1
        if not eids and not cell_searches:
            findings["absence_unsearched"].append(cell)

        if not synthesised:
            continue

        for field in L.SYNTHESIS_REQUIRED:
            why = Q.is_boilerplate(r.get(field))
            if why:
                findings["boilerplate"].append(
                    {"subcap": cell, "field": field, "why": why})
        why = Q.is_fluent_but_empty(r.get("What_We_Found"))
        if why:
            findings["boilerplate"].append(
                {"subcap": cell, "field": "What_We_Found", "why": why})

        for f in L.DQ_FIELDS:
            v = str(r.get(f) or "").strip()
            if not v or (v.upper().startswith("NOT_RUN")
                         and len(v) < len("NOT_RUN:") + 12):
                findings["dq_gaps"].append(f"{cell}:{f}")

        bad = Q.claim_label_supported(r)
        if bad:
            findings["claim_unsupported"].append({"subcap": cell, "why": bad})

        # Nothing rests on one document's say-so (functional_language.md § 4):
        # a FACT whose whole evidence base resolves to ONE source identity is
        # a single-source claim wearing the strongest label. Identity is the
        # registered URL's host, falling back to the source name — two pages
        # of the same annual report are one source, however many rows they
        # fill.
        if str(r.get("Claim_Label") or "").strip().upper() == "FACT":
            idents = set()
            for e in eids:
                row_e = register.get(e) or {}
                url = str(row_e.get("Source_URL") or "").strip()
                host = url.split("//")[-1].split("/")[0].lower() if url else ""
                idents.add(host or str(row_e.get("Source_Name") or "").strip().lower())
            idents.discard("")
            if len(idents) < 2:
                findings["single_source_fact"].append(
                    {"subcap": cell, "distinct_sources": sorted(idents)})

        if Q.claims_absence(r.get("Dominant_Claim")):
            declared = str(r.get("Absence_Claimed") or "").upper() in \
                ("YES", "TRUE", "1")
            if not declared or not str(r.get("Proxy_Log") or "").strip():
                findings["absence_undeclared"].append(cell)

        mine = [s for s in cat_searches
                if str(s.get("SubCap_ID") or "") == cell]
        if not any(Q.probes_contradicts(s.get("Query"), s.get("Facet"))
                   for s in mine):
            findings["contradicts_unprobed"].append(cell)

        lad = _parse_ladder(r.get("Negative_Ladder"))
        if lad:
            rep = Q.ladder_report(lad, searches)
            if rep["claimed_not_fired"]:
                findings["ladder_overstated"].append(
                    {"subcap": cell, **rep})

        # AUD-0025 / AUD-0082: no gate anywhere required a challenge verdict
        # to exist, and a FAILED provisional challenge still reported HIGH
        # confidence. AUD-0018 / AUD-0024: and the challenge had no
        # structural independence — the same actor wrote the synthesis and
        # its verdict.
        verdict = str(r.get("Challenge_Verdict") or "").strip().upper()
        if verdict not in ("PASS", "FAIL", "NOT_RUN") and \
                not verdict.startswith("NOT_RUN"):
            findings["challenge_missing"].append(cell)
        else:
            logged = L.challenge_for(wb, cell)
            if logged is None:
                findings["challenge_missing"].append(cell)
            else:
                author = L.actor_for(wb, cell, "synthesis")
                challenger = str(logged.get("Actor") or "")
                if author and challenger == author:
                    findings["challenge_not_independent"].append(
                        {"subcap": cell, "actor": challenger})
                if str(logged.get("Verdict") or "").upper() != verdict:
                    findings["challenge_missing"].append(cell)

    findings["evidence_smear"] = Q.evidence_smear(rows)

    # AUD-0022: the >=20-items-per-category floor was computed, reported and
    # then not used. It is a gate term here.
    category_floor_met = items >= FLOOR_CATEGORY_ITEMS

    # AUD-0115: the per-category evidence-COVERAGE floor. `evidenced_cells` is
    # subcaps carrying at least one resolvable citation; the floor is a
    # fraction of the category's selected subcaps. A category with no selected
    # subcaps has undefined coverage and is not blocked on this term (its
    # emptiness is caught by category_never_searched / the item floors).
    coverage = (evidenced_cells / len(rows)) if rows else None
    coverage_floor_met = coverage is None or coverage >= COVERAGE_FLOOR

    # AUD-0027 / timeline: a run with dated evidence and no timeline row for
    # this category cannot argue an arc.
    if not any(str(t.get("SubCap_IDs") or "").find(category) >= 0
               for t in wb.rows("Entity_Timeline")):
        findings["timeline_missing"].append(category)

    # WHAT TOOLS ACTUALLY RAN FOR THIS CATEGORY. Search_Log carries a Tool
    # per row, so this is measured, not recalled — and it is the answer to
    # "were the enrichment connectors ever called before the category
    # closed", which nothing here could previously answer at all.
    tools_used = sorted({str(s.get("Tool") or "").strip()
                         for s in cat_searches if str(s.get("Tool") or "").strip()})

    blocking = [k for k in (
        "unresolved_citations", "boilerplate", "claim_unsupported",
        "absence_undeclared", "evidence_smear", "challenge_missing",
        "challenge_not_independent", "single_source_fact",
        "synthesis_missing", "dq_gaps", "absence_unsearched",
    ) if findings[k]]
    if not category_floor_met:
        blocking.append("category_items_below_floor")
    if not coverage_floor_met:
        blocking.append("coverage_below_floor")
    # REPORTED 2026-08-30, from a live run in another account: "enrichment
    # connectors not being called by the agents for enrichment purposes
    # before close of a category". They were right, and no gate term could
    # see it — `search_ops` was COMPUTED here and printed, and then not used,
    # the same shape AUD-0022 records for the per-category item floor.
    #
    # A category with zero Search_Log rows performed no retrieval OF ANY
    # KIND. That is mode-independent: the log records every retrieval with
    # the tool that ran it, so an INTERNAL run reading only the client corpus
    # still logs rows. Zero means the category was closed on recall, which no
    # evidence mode permits.
    #
    # The floor is zero deliberately. A higher one would need calibration
    # this run does not have, and a threshold invented here would be a
    # number nobody measured — exactly the failure being fixed. What a
    # non-zero-but-thin category gets instead is `tools_used` in the verdict,
    # so "searched, but never through a connector" is visible to a reader
    # even where it does not block.
    if not cat_searches:
        blocking.append("category_never_searched")

    verdict = "PASS" if not blocking else "FAIL"
    out = {
        "gate": verdict,
        "category": category,
        "run_id": wb.metadata().get("run_id"),
        "category_evidence": f"{items}/{FLOOR_CATEGORY_ITEMS}",
        "category_floor_met": category_floor_met,
        "evidence_coverage": (
            f"{evidenced_cells}/{len(rows)} "
            f"({round(100 * coverage)}%)" if coverage is not None
            else f"{evidenced_cells}/0 (n/a)"),
        "coverage_floor": COVERAGE_FLOOR,
        "coverage_floor_met": coverage_floor_met,
        "subcaps": len(rows),
        "search_ops": len(cat_searches),
        "tools_used": tools_used,
        "subcaps_searched": f"{searched_cells}/{len(rows)}",
        "blocking": sorted(blocking),
        # FIVE TERMS ARE COMPUTED HERE AND DO NOT BLOCK. That is a deliberate
        # calibration choice, not an oversight — but until now a reader could
        # not tell the two apart, because a non-empty non-blocking finding
        # looked exactly like an empty one from the verdict's summary. Naming
        # them keeps the choice honest and reviewable: whoever decides one of
        # these should block can see how often it fires first.
        "advisory": sorted(k for k in ADVISORY_TERMS if findings.get(k)),
        # The finding lists are spread FLAT, deliberately — `out["dq_gaps"]`,
        # not `out["findings"]["dq_gaps"]`. Callers have guessed the nested
        # shape and hit KeyError (reported 2026-08-30), so the key set is
        # published here rather than left to be read out of the source.
        "finding_keys": sorted(findings),
        **findings,
    }

    # ── the half that did not exist: recording it ────────────────────────
    qa = Path(qa_dir) if qa_dir else None
    if qa is not None:
        qa.mkdir(parents=True, exist_ok=True)
        (qa / f"floors_{category}.json").write_text(
            json.dumps(out, indent=2, sort_keys=True))
        out["written_to"] = str(qa / f"floors_{category}.json")
    L.append_gate(wb, gate="FLOORS", scope=category, verdict=verdict,
                  detail=("; ".join(sorted(blocking)) or "all terms met"),
                  blocking=True)
    return out


def read_verdict(qa_dir: Path, category: str) -> dict | None:
    """The recorded verdict, or None. `None` means NOT RUN — never PASS."""
    p = Path(qa_dir) / f"floors_{category}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return None


def _parse_ladder(v):
    if not v:
        return []
    if isinstance(v, list):
        return v
    try:
        d = json.loads(str(v))
    except ValueError:
        return []
    return d if isinstance(d, list) else [d]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--root")
    ap.add_argument("--category", required=True)
    ap.add_argument("--require-synthesis", action="store_true")
    a = ap.parse_args(argv)
    r = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = r.open()
    out = run(wb, a.category, require_synthesis=a.require_synthesis,
              qa_dir=r.qa_dir)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
