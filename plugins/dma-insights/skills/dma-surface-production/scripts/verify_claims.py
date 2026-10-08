#!/usr/bin/env python3
"""Is every sentence of every synthesis IN the excerpts it cites?

    verify_claims.py drafts.json [--entity NAME] [--json] [--strict]

WHY THIS EXISTS. Measured 28-09-2026 (QA audit F-D04-005) on a promoted
run's `heatmap.cell_evidence`: 30 cells, 67 claims, 20 cells verifiable
from the excerpts cited under them (67%); 12 claims had no excerpt behind
them — a named CEO attribution, a committee structure, an after-state
("hours to minutes"). Each was the most rigorous-sounding sentence in its
drawer, and each was the one a client would quote back.

The judge is `engine.quality.verify_claim` (the research skill's, one
owner): lexical, offline, deterministic. Every figure, name and quoted
phrase in a sentence must be in the cited excerpts, and most of its
content words. Verdicts per sentence — entailed / partial / not_supported /
frame — and per cell the worst of them. A `not_supported` sentence is
rewritten from the excerpt, or its claim goes out as a `search_requests`
row; it is never returned as cited. A declared absence (thin +
sources_searched + closure_condition, no items) is verified by its ladder,
not here.

Accepts a whole `cells[]` array, a `{"cells": [...]}` section body, a
section envelope with `data.cells`, or the producer's return shape
`{"cell_evidence": {...}}`. Exit 1 when any cell is not_supported (always
with --strict; without it, when any cell is not_supported).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[2]
RESEARCH = PLUGIN / "skills" / "dma-research"


def _quality():
    if str(RESEARCH) not in sys.path:
        sys.path.insert(0, str(RESEARCH))
    from engine import quality                      # noqa: E402
    return quality


def _cells(doc):
    if isinstance(doc, list):
        return doc
    if not isinstance(doc, dict):
        return []
    for key in ("cell_evidence",):
        if isinstance(doc.get(key), dict):
            return _cells(doc[key])
    if isinstance(doc.get("data"), dict):
        return _cells(doc["data"])
    if isinstance(doc.get("cells"), list):
        return doc["cells"]
    return []


def verify(doc, *, entity: str | None = None) -> dict:
    Q = _quality()
    rows = [Q.verify_cell(c, entity=entity) for c in _cells(doc) if isinstance(c, dict)]
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in Q.VERIFY_VERDICTS}
    return {"cells": len(rows), "counts": counts,
            "not_supported": [
                {"subcap_id": r.get("subcap_id"),
                 "sentences": [{"text": s["text"], "missing": s["missing"],
                                "missing_hard": s["missing_hard"]}
                               for s in r.get("sentences", [])
                               if s["verdict"] == "not_supported"]}
                for r in rows if r["verdict"] == "not_supported"],
            "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("drafts", help="a JSON file: cells[], a section, or the producer's return")
    ap.add_argument("--entity", default=None,
                    help="the client's name, exempt from the name check")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="also exit 1 on any `partial` sentence")
    a = ap.parse_args(argv)
    doc = json.loads(Path(a.drafts).read_text(encoding="utf-8"))
    out = verify(doc, entity=a.entity)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        c = out["counts"]
        print(f"verify_claims: {out['cells']} cell(s) — entailed {c['entailed']}, "
              f"partial {c['partial']}, not_supported {c['not_supported']}, "
              f"frame-only {c['frame']}")
        for r in out["not_supported"]:
            for s in r["sentences"]:
                print(f"  NOT_SUPPORTED {r['subcap_id']}: {s['text'][:110]!r} — "
                      f"missing {s['missing_hard'] or s['missing']}")
    bad = out["counts"]["not_supported"] + (out["counts"]["partial"] if a.strict else 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
