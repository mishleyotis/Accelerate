#!/usr/bin/env python3
"""Is a run's evidence CITABLE, and does the run say so?

THE DEFECT THIS MEASURES. `evidence_index.excerpt` has two writers.
`register_evidence` refuses a span outside 50-500 characters, refuses a FACT
with no traceable URL, and verifies the span against the artefact it fetches.
The worker's workbook-parse path shared the column and enforced none of it, so
a package could land evidence that links to cells and can never be cited.
Measured on Logix run d7ed1d90 on 2026-08-18: 36 of 62 rows carried a
zero-length excerpt. Every gate passed. The run promoted. It read on a client
dashboard as a thin assessment of a thin institution, and the thinness was
ours.

WHY IT DISCLOSES RATHER THAN BLOCKS, mostly. Thinness is a property of the
public record as much as of the work: an institution whose own domain answers
this verifier with a 403 — Logix does, at the Cloudflare edge, while serving
an ordinary browser normally — cannot be researched to the same depth as one
that does not. Refusing those runs would refuse the finding. So the floor here
is not "enough evidence"; it is **the run must know and state what it has**.

Two things DO fail hard, because neither is a fact about the world:

  * an ingested row holding the empty string. NULL and '' were two spellings
    of "no excerpt" and only one was ever queried for — the repair job selects
    on IS NULL, embed filters on IS NOT NULL, and the dedup hash goes NULL
    with the excerpt, so '' is invisible to all three while reading as
    populated. `citable_span` in the worker now writes None; this is the
    corpus-wide check that it stays that way.
  * a run whose citable share is under the floor and whose payload nowhere
    says so. That is the combination that shipped.

    gate_g_citable_evidence.py --run <uuid>          # against the connector
    gate_g_citable_evidence.py --from-dir <dir>      # against fetched pages

Exit 0 clean, 1 on a hard failure, 2 when only disclosure warnings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# The share of an evidence register that must be citable before a run is
# expected to say something about it. Not a quality bar — a disclosure
# trigger. Logix sat at 42% (26 of 62) and said so in four places, which is
# the behaviour this encodes.
DISCLOSURE_FLOOR = 0.60
EXCERPT_MIN, EXCERPT_MAX = 50, 500

# Phrases that count as the run stating its own reach. Deliberately about the
# SHAPE of the admission, not its wording: a run may disclose in prose, in an
# empty_state reason, or in a closure condition.
DISCLOSURE_MARKERS = (
    "cannot be cited", "could not be cited", "carry no excerpt",
    "no verbatim excerpt", "zero-length excerpt", "not citable",
    "uncitable", "403", "refuses automated", "refuses retrieval",
    "evidence verifier", "stores a verbatim excerpt",
)


def _walk_strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)
    elif isinstance(node, str):
        yield node


def audit(evidence_rows: list, pages: dict) -> dict:
    total = len(evidence_rows)
    empty_string = [r for r in evidence_rows
                    if isinstance(r.get("excerpt"), str) and not r["excerpt"].strip()]
    short = [r for r in evidence_rows
             if (r.get("excerpt") or "").strip()
             and len((r["excerpt"]).strip()) < EXCERPT_MIN]
    citable = [r for r in evidence_rows
               if EXCERPT_MIN <= len((r.get("excerpt") or "").strip()) <= EXCERPT_MAX]
    share = (len(citable) / total) if total else 1.0

    prose = " ".join(_walk_strings(pages)).lower()
    disclosed = any(m in prose for m in DISCLOSURE_MARKERS)

    blockers, warnings = [], []
    if empty_string:
        blockers.append(
            f"{len(empty_string)} evidence rows hold the EMPTY STRING rather than "
            f"NULL: {[r.get('e_id') for r in empty_string][:6]}. A row holding '' is "
            "outside repair_evidence_namespace (IS NULL), outside the embedding "
            "corpus (IS NOT NULL) and outside the dedup index (NULL content_hash), "
            "while reading as populated to every check written against None.")
    if short:
        blockers.append(
            f"{len(short)} evidence rows carry a span under the {EXCERPT_MIN}-character "
            f"floor: {[r.get('e_id') for r in short][:6]}. It links, and it is refused "
            "at ET-04 the moment a producer cites it — a defect manufactured at ingest "
            "and surfaced two stages later.")
    if share < DISCLOSURE_FLOOR and not disclosed:
        blockers.append(
            f"citable evidence is {share:.0%} of the register ({len(citable)}/{total}) "
            f"and no page says so. Under {DISCLOSURE_FLOOR:.0%} the run must state its "
            "own reach — a reader cannot tell a thin institution from a thin search, "
            "and the difference is the finding.")
    elif share < DISCLOSURE_FLOOR:
        warnings.append(
            f"citable evidence is {share:.0%} ({len(citable)}/{total}) — disclosed by "
            "the payload, which is the correct posture, not a defect.")
    return {"total": total, "citable": len(citable), "share": share,
            "empty_string": len(empty_string), "short": len(short),
            "disclosed": disclosed, "blockers": blockers, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", help="a get_evidence-shaped JSON file")
    ap.add_argument("--pages", help="the run's six pages as JSON")
    a = ap.parse_args()
    if not a.evidence:
        print("nothing to audit: pass --evidence")
        return 0
    raw = json.loads(Path(a.evidence).read_text())
    rows = raw.get("found") if isinstance(raw, dict) else raw
    pages = json.loads(Path(a.pages).read_text()) if a.pages else {}
    rep = audit(rows or [], pages)

    print(f"evidence rows        {rep['total']}")
    print(f"citable (50-500)     {rep['citable']}  ({rep['share']:.0%})")
    print(f"empty-string rows    {rep['empty_string']}")
    print(f"under the floor      {rep['short']}")
    print(f"run discloses reach  {rep['disclosed']}")
    for b in rep["blockers"]:
        print(f"\nBLOCKER  {b}")
    for w in rep["warnings"]:
        print(f"\nwarning  {w}")
    return 1 if rep["blockers"] else (2 if rep["warnings"] else 0)


if __name__ == "__main__":
    sys.exit(main())
