#!/usr/bin/env python3
"""Fingerprint, cluster and rank findings, and state the minimum rung each
cluster requires.

    python scripts/triage.py findings.json
    python scripts/triage.py findings.json --json > clusters.json
    list_open_findings(...) > findings.json && python scripts/triage.py findings.json

Input is what `list_open_findings` / `search_findings` return: a JSON array of
findings, or an object with a "findings" key. Shape: templates/finding.schema.json.

It does the counting. You do the naming and the rung choice — see
01-loop/2-clustering.md and 01-loop/3-the-ladder.md.

Two things it deliberately does NOT do quietly:

  * A finding it cannot fingerprint is a FAILURE, not a skip. A triage that
    silently drops the findings it could not parse reports a clean cluster set
    over the ones it never looked at — the same silent-skip mode that let
    `Per issue:` opt out of both CG-13 and AG-03 for as long as it existed.
  * It never invents a cluster. Ranking is over what was sighted; a run with no
    findings prints "nothing above threshold" and exits 0.

Exit codes: 0 clean · 1 unfingerprintable findings present.
"""
import argparse
import json
import re
import sys
from collections import defaultdict

RUNGS = ["R1", "R2", "R3", "R4", "R5"]

VERBS = ("discarded", "fabricated", "unchecked", "miscited", "misgrained",
         "leaked", "stale", "unreachable")
LOCI = ("package", "synthesis", "submit", "promote", "serve", "render")

# Reach that forces R3 or above by the ladder's second rule: prose did not
# catch it the first time and the reader who missed it is someone else next time.
REACHED_CLIENT = ("rendered", "promoted")

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_IDS = re.compile(r"\b(?:E|IC|F|FA|TS|WN|REC)-[0-9A-Za-z_]+\b")
_IDX = re.compile(r"\[\s*\d+\s*\]")
_RUNKEY = re.compile(r"\bDMA-ASM-[A-Z0-9]+-\d{8}-\d+\b")


def normalise(path):
    """Collapse the parts that make two sightings of one defect look distinct.

    overview.findings[3].score and overview.findings[11].score are one path.
    """
    p = (path or "").strip()
    p = _UUID.sub("<id>", p)
    p = _RUNKEY.sub("<run>", p)
    p = _IDS.sub("<id>", p)
    p = _IDX.sub("[]", p)
    return re.sub(r"\s+", " ", p)


def fingerprint(f):
    return (f.get("invariant") or "", f.get("verb") or "", normalise(f.get("path")))


def unfingerprintable(f):
    """Why this finding cannot be placed. Empty list means it can."""
    why = []
    if not (f.get("invariant") or "").strip():
        why.append("no invariant (UNKNOWN is legal; blank is not)")
    if (f.get("verb") or "") not in VERBS:
        why.append("verb not one of " + "/".join(VERBS))
    if not (f.get("path") or "").strip():
        why.append("no path")
    if (f.get("locus") or "") not in LOCI:
        why.append("locus not one of " + "/".join(LOCI))
    return why


def prior_rung(f):
    """The highest rung any refinement against this finding landed on."""
    best = None
    for r in f.get("refinements") or []:
        rung = (r.get("rung") if isinstance(r, dict) else None) or ""
        if rung in RUNGS and (best is None or RUNGS.index(rung) > RUNGS.index(best)):
            best = rung
    return best


def is_recurrence(f):
    """A sighting against a finding a refinement already answered."""
    if f.get("status") == "recurrence" or f.get("recurrence_count"):
        return True
    for r in f.get("refinements") or []:
        if isinstance(r, dict) and r.get("held") is False:
            return True
    # A refinement exists and the finding is open again: the fix did not hold.
    return bool(f.get("refinements")) and f.get("status") in ("open", "reopened", None)


def minimum_rung(cluster):
    """The floor, with the reason. Never the final answer — that is judgement."""
    floor, why = "R1", "first sighting, no client reach"

    if len(cluster["findings"]) >= 3 or cluster["sightings"] >= 3:
        floor, why = "R3", (f"{len(cluster['findings'])} distinct paths / "
                            f"{cluster['sightings']} sightings — one class, "
                            "not N patches")
    elif any((f.get("severity") == "blocking") for f in cluster["findings"]):
        floor, why = "R2", "a blocking sighting; prose alone was not enough"

    if cluster["client_reach"] in REACHED_CLIENT:
        if RUNGS.index(floor) < 2:
            floor, why = "R3", (f"reached the client ({cluster['client_reach']}) "
                                "— ladder rule 2: never below R3")

    if cluster["prior_rung"]:
        nxt = RUNGS[min(RUNGS.index(cluster["prior_rung"]) + 1, len(RUNGS) - 1)]
        if RUNGS.index(nxt) > RUNGS.index(floor):
            floor = nxt
        why = (f"RECURRENCE — previous refinement landed on "
               f"{cluster['prior_rung']} and did not hold; strictly above it. "
               "FIRST run that existing check against this instance: if it PASSES "
               "on a genuine instance the defect is scope, not rung, and the "
               "upstream move is to widen the same rung — usually one grain down")
        if cluster["prior_rung"] == "R5":
            why += " (already R5: this is a scope or ceiling question, not a rung one)"
    return floor, why


def build(findings):
    # One row per fingerprint. Two records with the same fingerprint are two
    # sightings of one finding, which is exactly what the store's dedup does —
    # and the sighting count is the signal, so it accumulates rather than
    # collapsing.
    by_fp = {}
    for f in findings:
        fp = fingerprint(f)
        if fp not in by_fp:
            rec = dict(f)
            rec["sightings"] = int(f.get("sightings") or 1)
            rec["refinements"] = list(f.get("refinements") or [])
            by_fp[fp] = rec
            continue
        rec = by_fp[fp]
        rec["sightings"] += int(f.get("sightings") or 1)
        rec["refinements"] += list(f.get("refinements") or [])
        for key in ("severity", "client_reach", "surface", "excerpt"):
            if not rec.get(key) and f.get(key):
                rec[key] = f[key]

    classes = defaultdict(list)
    for fp, f in by_fp.items():
        classes[(fp[0], fp[1])].append(f)

    out = []
    for (inv, verb), fs in classes.items():
        sightings = sum(int(f.get("sightings") or 1) for f in fs)
        reaches = [f.get("client_reach") for f in fs if f.get("client_reach")]
        reach = next((r for r in ("rendered", "promoted", "submitted",
                                  "caught_before_submit", "none") if r in reaches), "none")
        rungs = [prior_rung(f) for f in fs if prior_rung(f)]
        prior = max(rungs, key=RUNGS.index) if rungs else None
        depth = sum(1 for f in fs if is_recurrence(f))
        c = {
            "invariant": inv, "verb": verb,
            "paths": sorted(normalise(f.get("path")) for f in fs),
            "findings": fs, "sightings": sightings,
            "client_reach": reach, "prior_rung": prior, "recurrence_depth": depth,
            "surfaces": sorted({f.get("surface") for f in fs if f.get("surface")}),
            "loci": sorted({f.get("locus") for f in fs if f.get("locus")}),
        }
        c["minimum_rung"], c["rung_reason"] = minimum_rung(c)
        c["shape"] = ("class — one structural change" if len(fs) > 1
                      else "single path — recurrence check first")
        out.append(c)

    # Ordering: recurrence depth, then client reach, then sighting count.
    order = {"rendered": 4, "promoted": 3, "submitted": 2,
             "caught_before_submit": 1, "none": 0}
    out.sort(key=lambda c: (c["recurrence_depth"], order.get(c["client_reach"], 0),
                            c["sightings"]), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings", nargs="?", default="-",
                    help="JSON array of findings, or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--min-sightings", type=int, default=1,
                    help="threshold; clusters below it are listed as below-threshold, "
                         "never dropped silently")
    a = ap.parse_args()

    raw = sys.stdin.read() if a.findings == "-" else open(a.findings, encoding="utf-8").read()
    doc = json.loads(raw)
    findings = doc.get("findings", doc) if isinstance(doc, dict) else doc
    if not isinstance(findings, list):
        print("input is neither a list of findings nor {findings: [...]}", file=sys.stderr)
        return 1

    bad = [(i, f, unfingerprintable(f)) for i, f in enumerate(findings)]
    bad = [(i, f, w) for i, f, w in bad if w]
    good = [f for f in findings if not unfingerprintable(f)]

    clusters = build(good)
    above = [c for c in clusters if c["sightings"] >= a.min_sightings]
    below = [c for c in clusters if c["sightings"] < a.min_sightings]

    if a.json:
        print(json.dumps({"clusters": above, "below_threshold": below,
                          "unfingerprintable": [{"index": i, "why": w} for i, _, w in bad]},
                         indent=1, default=str))
    else:
        print(f"\n  {len(good)} findings · {len(clusters)} clusters · "
              f"{len(bad)} unfingerprintable\n")
        if not above:
            print("  nothing above threshold — say so and stop. Do not lower it.\n")
        for n, c in enumerate(above, 1):
            print(f"  {n}. {c['invariant']} / {c['verb']}   "
                  f"[{c['shape']}]")
            print(f"     paths        {len(c['paths'])}  sightings {c['sightings']}  "
                  f"reach {c['client_reach']}  recurrences {c['recurrence_depth']}")
            for p in c["paths"][:8]:
                print(f"       · {p}")
            if len(c["paths"]) > 8:
                print(f"       · … {len(c['paths']) - 8} more")
            print(f"     minimum rung {c['minimum_rung']} — {c['rung_reason']}")
            print(f"     name the class yourself: 12-30 words, and state the two "
                  f"points it lives between\n")
        for c in below:
            print(f"  (below threshold) {c['invariant']}/{c['verb']} "
                  f"— {c['sightings']} sighting(s)")
        if bad:
            print("\n  UNFINGERPRINTABLE — these were NOT clustered and NOT counted:")
            for i, _, w in bad:
                print(f"    [{i}] {'; '.join(w)}")
            print("  A triage that drops what it cannot parse reports clean over the")
            print("  findings it never looked at. Fix the records, then re-run.")
        print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
