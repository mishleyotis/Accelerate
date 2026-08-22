#!/usr/bin/env python3
"""Rank the store's open findings into clusters, and state the minimum rung each
one requires.

    list_open_findings(...)  > findings.json && python scripts/triage.py findings.json
    get_memory_digest(days=7) > digest.json   && python scripts/triage.py digest.json
    python scripts/triage.py findings.json --json > clusters.json

Input is whatever the connector's memory tools returned: a list of findings, a
`{findings: […]}` / `{results: […]}` envelope, or a full `get_memory_digest`
payload (recognised by its `open_by_class` key). Shapes:
templates/finding.schema.json and 02-inputs/2-memory-tools.md.

The store already does the class grain — `defect_class` is a foreign key and the
digest's `open_by_class` says which SHAPE of defect the build is still
producing. This adds the two things it does not: the ORDER to work in, and the
FLOOR each cluster's rung has to clear. The naming and the rung choice remain
judgement; see 01-loop/2-clustering.md and 01-loop/3-the-ladder.md.

Two things it deliberately does NOT do quietly:

  * A finding it cannot place is a FAILURE, not a skip. A triage that silently
    drops the records it could not read reports a clean cluster set over the
    findings it never looked at — the same silent-skip mode that let
    `Per issue:` opt out of both CG-13 and AG-03 for as long as it existed.
  * It never invents a cluster. Ranking is over what was sighted; no findings
    prints "nothing above threshold" and exits 0.

Exit codes: 0 clean · 1 unreadable findings present.
"""
import argparse
import json
import sys
from collections import defaultdict

RUNGS = ["R1", "R2", "R3", "R4", "R5"]

# target_kind IS the rung. The store has no rung column; this is the mapping.
KIND_RUNG = {"DOC": "R1", "PROCESS": "R1", "SKILL": "R2", "AGENT": "R2",
             "TEST": "R3", "COMPONENT": "R3", "GATE": "R4", "SCHEMA": "R5"}

SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "INFO")
SEV_ORDER = {s: i for i, s in enumerate(reversed(SEVERITIES))}

# A component that serves the client. A defect here reached, or could reach, a
# rendered surface — the ladder's second rule then forbids anything below R3.
CLIENT_FACING = ("web", "api")


def unreadable(f):
    """Why this finding cannot be placed. Empty list means it can."""
    why = []
    if not (f.get("defect_class") or "").strip():
        why.append("no defect_class (it is a foreign key, not a label — read "
                   "list_defect_classes)")
    if not (f.get("component") or "").strip():
        why.append("no component")
    if not (f.get("title") or "").strip():
        why.append("no title")
    if (f.get("severity") or "") not in SEVERITIES:
        why.append("severity not one of " + "/".join(SEVERITIES))
    return why


def prior_rung(f):
    """The highest rung any refinement against this finding landed on.

    Present only when the record came from get_finding — list_open_findings
    does not carry refinements, and 'no refinements listed' is NOT 'no
    refinements exist'. None means unknown, which the caller must not read as
    'first attempt'.
    """
    best = None
    for r in f.get("refinements") or []:
        if not isinstance(r, dict):
            continue
        rung = KIND_RUNG.get((r.get("target_kind") or "").upper())
        if rung and (best is None or RUNGS.index(rung) > RUNGS.index(best)):
            best = rung
    return best


def recurrences(f):
    n = int(f.get("recurrences") or 0)
    if not n and (f.get("status") or "").upper() == "RECURRED":
        n = 1
    return n


def locator(f):
    return (f.get("file_path") or f.get("surface") or f.get("gate_id") or "")


def minimum_rung(c):
    """The FLOOR, with its reason. Never the final answer — that is judgement."""
    floor, why = "R1", "first sighting, nothing forcing it higher"

    if c["findings"] >= 3 or c["sightings"] >= 3:
        floor, why = "R3", (f"{c['findings']} findings / {c['sightings']} sightings "
                            "in one class — one structural change, not N patches")
    elif c["worst_severity"] == "BLOCKER":
        floor, why = "R2", "a BLOCKER in the class; prose alone was not enough"

    if c["client_facing"] and RUNGS.index(floor) < 2:
        floor, why = "R3", (f"reached a client-facing component ({', '.join(c['components'])}) "
                            "— ladder rule 2: never below R3")

    if c["recurrences"]:
        if c["prior_rung"]:
            nxt = RUNGS[min(RUNGS.index(c["prior_rung"]) + 1, len(RUNGS) - 1)]
            if RUNGS.index(nxt) > RUNGS.index(floor):
                floor = nxt
            why = (f"RECURRENCE — the previous refinement landed on "
                   f"{c['prior_rung']} (target_kind) and did not hold; strictly "
                   "above it")
            if c["prior_rung"] == "R5":
                why += " (already R5: a scope or ceiling question, not a rung one)"
        else:
            if RUNGS.index(floor) < 2:
                floor = "R3"
            why = ("RECURRENCE — no refinement in this record, so the previous rung "
                   "is UNKNOWN. Call get_finding before choosing; 'not listed' is "
                   "not 'none exists'")
        why += (". FIRST run the existing check against this instance: if it PASSES "
                "on a genuine instance the defect is scope, not rung, and the "
                "upstream move is to widen the same rung — usually one grain down")
    return floor, why


def build(findings):
    classes = defaultdict(list)
    for f in findings:
        classes[f["defect_class"]].append(f)

    out = []
    for cls, fs in classes.items():
        comps = sorted({f.get("component") for f in fs if f.get("component")})
        rungs = [prior_rung(f) for f in fs if prior_rung(f)]
        sev = sorted({(f.get("severity") or "INFO") for f in fs},
                     key=lambda s: SEV_ORDER.get(s, 0), reverse=True)
        c = {
            "defect_class": cls,
            "findings": len(fs),
            "finding_ids": sorted(f.get("finding_id") or "?" for f in fs),
            "sightings": sum(int(f.get("sightings") or 1) for f in fs),
            "recurrences": sum(recurrences(f) for f in fs),
            "components": comps,
            "client_facing": any(c0 in CLIENT_FACING for c0 in comps),
            "worst_severity": sev[0] if sev else "INFO",
            "max_age_days": max((int(f.get("age_days") or 0) for f in fs), default=0),
            "locators": sorted({locator(f) for f in fs if locator(f)}),
            "prior_rung": max(rungs, key=RUNGS.index) if rungs else None,
            "titles": [f.get("title") for f in fs][:8],
        }
        c["minimum_rung"], c["rung_reason"] = minimum_rung(c)
        c["shape"] = ("class — one structural change" if len(fs) > 1
                      else "single finding — check for a recurrence first")
        out.append(c)

    out.sort(key=lambda c: (c["recurrences"], SEV_ORDER.get(c["worst_severity"], 0),
                            c["sightings"], c["max_age_days"]), reverse=True)
    return out


def extract(doc):
    """Findings out of whatever the tools returned."""
    if isinstance(doc, list):
        return doc, "list"
    if not isinstance(doc, dict):
        return [], "unknown"
    if "open_by_class" in doc:                       # get_memory_digest
        rows = list(doc.get("new_findings_in_window") or [])
        rows += list(doc.get("recurrences_in_window") or [])
        rows += list(doc.get("ageing_unrefined") or [])
        seen, uniq = set(), []
        for r in rows:                               # a row may appear twice
            k = r.get("finding_id")
            if k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        return uniq, "digest"
    for key in ("findings", "results", "rows", "open"):
        if isinstance(doc.get(key), list):
            return doc[key], key
    return [], "unknown"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings", nargs="?", default="-",
                    help="what a memory tool returned, or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--min-sightings", type=int, default=1,
                    help="threshold; clusters below it are listed as "
                         "below-threshold, never dropped silently")
    a = ap.parse_args()

    raw = sys.stdin.read() if a.findings == "-" else open(a.findings, encoding="utf-8").read()
    findings, shape = extract(json.loads(raw))

    bad = [(i, unreadable(f)) for i, f in enumerate(findings)]
    bad = [(i, w) for i, w in bad if w]
    good = [f for f in findings if not unreadable(f)]

    clusters = build(good)
    above = [c for c in clusters if c["sightings"] >= a.min_sightings]
    below = [c for c in clusters if c["sightings"] < a.min_sightings]

    if a.json:
        print(json.dumps({"input_shape": shape, "clusters": above,
                          "below_threshold": below,
                          "unreadable": [{"index": i, "why": w} for i, w in bad]},
                         indent=1, default=str))
        return 1 if bad else 0

    print(f"\n  {len(good)} findings ({shape}) · {len(clusters)} classes · "
          f"{len(bad)} unreadable\n")
    if not above:
        print("  nothing above threshold — say so and stop. Do not lower it, and do")
        print("  not go looking for defects nobody sighted.\n")
    for n, c in enumerate(above, 1):
        print(f"  {n}. {c['defect_class']}   [{c['shape']}]")
        print(f"     findings {c['findings']}  sightings {c['sightings']}  "
              f"recurrences {c['recurrences']}  worst {c['worst_severity']}  "
              f"oldest {c['max_age_days']}d")
        print(f"     components   {', '.join(c['components']) or '—'}")
        for t in c["titles"]:
            print(f"       · {t}")
        if c["findings"] > len(c["titles"]):
            print(f"       · … {c['findings'] - len(c['titles'])} more")
        print(f"     minimum rung {c['minimum_rung']} — {c['rung_reason']}")
        print("     name the class yourself: 12-30 words, stating the two points "
              "it lives between\n")
    for c in below:
        print(f"  (below threshold) {c['defect_class']} — "
              f"{c['sightings']} sighting(s)")
    if bad:
        print("\n  UNREADABLE — these were NOT clustered and NOT counted:")
        for i, w in bad:
            print(f"    [{i}] {'; '.join(w)}")
        print("  A triage that drops what it cannot read reports clean over the")
        print("  findings it never looked at. Fix the records, then re-run.")
    print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
