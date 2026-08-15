#!/usr/bin/env python3
"""Is this app ready to ingest reports it has never seen?

The two promoted clients prove the pipeline works twice. They do not prove it
works on the NEXT package, and the corpus is heterogeneous in ways that only
show up at scale: 61 distinct spellings of "sub-vertical", two workbook
generations, merged files carrying the assessment and the research layer in one
workbook, and packages whose scoring tabs state category ids where cells belong.

So this parses a whole corpus directory and reports a census. It is not a unit
test — the corpus is gigabytes and lives outside the repo — it is the thing to
run before answering "can we take on more clients", and its baseline is
committed so a later run can be compared rather than re-judged.

    python scripts/ingest_readiness.py --corpus <dir> [--baseline <json>]
    python scripts/ingest_readiness.py --corpus <dir> --write-baseline

A directory holding `<id>.workbook.xlsx` and optional `<id>.manifest.json`.

EXIT CODES
    0  every package parsed, and no metric regressed against the baseline
    1  a package raised, or a metric regressed
    2  the corpus directory is unusable

What counts as a REGRESSION is deliberately one-sided: parse failures,
unresolved sub-verticals and duplicate ids may only go DOWN. Observation counts
may move either way — a parser that starts recording something it used to miss
is an improvement that shows up as more observations, and a ratchet on those
would punish it.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import resolve_subvertical, scope_status  # noqa: E402
from dma_worker.persist import _institution  # noqa: E402
from dma_worker.workbook_parser import parse_scoring_workbook  # noqa: E402

BASELINE = ROOT / "apps" / "web" / "tests" / "acceptance" / "ingest_baseline.json"

#: Metrics that may only improve. Everything else is reported, not ratcheted.
_ONE_SIDED = ("parse_failures", "zero_cell_packages", "duplicate_ids_remaining",
              "subvertical_unresolved", "packages_without_identity")


def census(corpus: str) -> dict:
    books = sorted(glob.glob(os.path.join(corpus, "*.workbook.xlsx")))
    if not books:
        raise SystemExit(f"no *.workbook.xlsx under {corpus!r}")

    out = {
        "packages": len(books), "parsed": 0, "parse_failures": 0,
        "zero_cell_packages": 0, "duplicate_ids_remaining": 0,
        "subvertical_resolved": 0, "subvertical_unresolved": 0,
        "packages_without_identity": 0, "scored_cells_total": 0,
        "scored_cells_max": 0, "observations_total": 0,
    }
    kinds = collections.Counter()
    failures, zero, unresolved = [], [], []

    for book in books:
        pid = os.path.basename(book).split(".")[0]
        try:
            parsed = parse_scoring_workbook(book)
        except Exception as exc:                      # noqa: BLE001 — census
            out["parse_failures"] += 1
            failures.append({"package": pid,
                             "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        out["parsed"] += 1
        ids = [s.subcap_id for s in parsed.scores]
        out["duplicate_ids_remaining"] += len(ids) - len(set(ids))
        out["scored_cells_total"] += parsed.scored_cells
        out["scored_cells_max"] = max(out["scored_cells_max"], parsed.scored_cells)
        out["observations_total"] += len(parsed.observations)
        for obs in parsed.observations:
            kinds[obs.kind] += 1
        if not parsed.scored_cells:
            out["zero_cell_packages"] += 1
            zero.append({"package": pid,
                         "reasons": sorted({o.kind for o in parsed.observations})})

        manifest = os.path.join(corpus, f"{pid}.manifest.json")
        if not os.path.exists(manifest):
            continue
        try:
            inst = _institution(json.load(open(manifest)))
        except Exception:                             # noqa: BLE001 — census
            out["packages_without_identity"] += 1
            continue
        if not inst.get("name"):
            out["packages_without_identity"] += 1
        stated = inst.get("sub_vertical")
        if stated is None:
            continue
        if resolve_subvertical(stated):
            out["subvertical_resolved"] += 1
        else:
            out["subvertical_unresolved"] += 1
            unresolved.append({"stated": str(stated)[:80],
                               "why": scope_status(stated)["reason"][:120]})

    out["observation_kinds"] = dict(kinds.most_common())
    out["_detail"] = {"parse_failures": failures[:20],
                      "zero_cell_packages": zero[:20],
                      "subvertical_unresolved": unresolved[:20]}
    return out


def compare(now: dict, base: dict) -> list:
    """One-sided: the metrics that mean "something is broken" may only fall."""
    bad = []
    for key in _ONE_SIDED:
        then, here = base.get(key), now.get(key, 0)
        if then is None:
            continue
        if here > then:
            bad.append(f"{key}: {then} -> {here} (may only decrease)")
    # A corpus that shrank is not a pass: fewer packages means fewer chances
    # to fail, and the counts above would improve for the wrong reason.
    if now["packages"] < base.get("packages", 0):
        bad.append(f"packages: {base['packages']} -> {now['packages']} — a "
                   "smaller corpus makes every count below look better")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    now = census(args.corpus)
    print(f"INGEST READINESS — {now['packages']} package(s) under {args.corpus}\n")
    print(f"  parsed                    {now['parsed']}")
    print(f"  parse failures            {now['parse_failures']}")
    print(f"  zero-cell packages        {now['zero_cell_packages']}")
    print(f"  duplicate ids remaining   {now['duplicate_ids_remaining']}")
    print(f"  sub-vertical resolved     {now['subvertical_resolved']}")
    print(f"  sub-vertical unresolved   {now['subvertical_unresolved']}")
    print(f"  packages without identity {now['packages_without_identity']}")
    print(f"  scored cells, max         {now['scored_cells_max']}")
    print(f"  observations              {now['observations_total']}")
    print("\n  observation kinds:")
    for kind, n in now["observation_kinds"].items():
        print(f"    {n:6d}  {kind}")
    for entry in now["_detail"]["parse_failures"]:
        print(f"\n  FAILED {entry['package']}: {entry['error']}")
    if now["_detail"]["subvertical_unresolved"]:
        print("\n  unresolved sub-verticals (every T2 variant serves):")
        for u in now["_detail"]["subvertical_unresolved"][:10]:
            print(f"    {u['stated']!r}")

    if args.write_baseline:
        keep = {k: v for k, v in now.items() if k != "_detail"}
        Path(args.baseline).write_text(json.dumps(keep, indent=1) + "\n")
        print(f"\nbaseline written to {args.baseline}")
        return 0

    if not os.path.exists(args.baseline):
        print(f"\nno baseline at {args.baseline}; run --write-baseline first.")
        return 1 if now["parse_failures"] else 0

    bad = compare(now, json.loads(Path(args.baseline).read_text()))
    if bad:
        print("\nINGEST READINESS REGRESSED:")
        for b in bad:
            print(f"  {b}")
        return 1
    print("\ningest readiness holds: nothing regressed against the baseline.")
    return 1 if now["parse_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
