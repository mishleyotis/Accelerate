#!/usr/bin/env python3
"""The evidence-source yield ledger: which sources actually produce.

Owner instruction, 2026-08-20: "Enrichment trends that work may also be
within the learning loop and evidence sources that yield rich results may
be logged for future references to ensure that our evidence source list
keeps expanding."

What this is. A cross-client, taxonomy-level record of how enrichment
sources PERFORM: for each search a session runs, one entry — the source
(domain or connector pathway), the facet, the subcap family it served, the
evidence tier of what came back, and the outcome. Ranking reads the ledger
back: given a facet (and optionally a subcap family), the sources ordered
by measured yield, so the next session opens its richest source first and
spends its searches — and its tokens — where they have paid before.

The declared register vs the measured ledger. `02-inputs/
enrichment_sources.json` declares what pathways EXIST and their tier
ceilings; this ledger measures what they DELIVER. A source that appears
here rich and repeatedly but is missing from the register is a candidate
the `rectifier` promotes into the register with provenance — that is the
"keeps expanding" half. Neither file ever holds client prose: domains,
facets, families, tiers, outcomes and dates only. The story behind an
entry lives in that client's memory file (research log).

Outcomes, deliberately three: rich (registered evidence above T3 that a
surface cited), thin (something came back but below the bar or generic),
empty (a clean negative — which is still worth ranking on, because a
source that is reliably empty for a facet should be opened LAST, and a
recorded empty stops the next session repeating it).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
LEDGER = PLUGIN / "fixtures" / "source_yield.json"

OUTCOMES = ("rich", "thin", "empty")
# Yield weights: a rich result is worth pursuing again; a thin one slightly
# better than nothing; an empty costs the search it took.
_W = {"rich": 3.0, "thin": 0.5, "empty": -1.0}
# Newer results matter more: full weight inside a year, half after.
_RECENT_DAYS = 365


def _load(path: Path) -> dict:
    if not path.exists():
        return {"_doc": _DOC, "entries": []}
    return json.loads(path.read_text())


_DOC = ("Measured yield of enrichment sources, appended by the learning "
        "loop (enrichment agents at session end, qa-overseer on review). "
        "Taxonomy only — domains, facets, subcap families, tiers, outcomes, "
        "dates; never client prose. Sources rich here but absent from "
        "02-inputs/enrichment_sources.json are register candidates the "
        "rectifier promotes with provenance.")


def log(source: str, facet: str, outcome: str, tier: str | None = None,
        family: str | None = None, raised_by: str = "session",
        note: str | None = None, path: Path = LEDGER) -> dict:
    if outcome not in OUTCOMES:
        raise SystemExit(f"outcome must be one of {OUTCOMES}")
    if not source or "://" in source:
        raise SystemExit("source is a bare domain or connector pathway name "
                         "(e.g. ncua.gov, clay:tech-stack), not a URL")
    d = _load(path)
    entry = {"source": source.lower(), "facet": facet.lower(),
             "outcome": outcome, "on": _dt.date.today().isoformat(),
             "raised_by": raised_by}
    if tier:
        entry["tier"] = tier.upper()
    if family:
        entry["family"] = family
    if note:
        entry["note"] = note
    d["entries"].append(entry)
    path.write_text(json.dumps(d, indent=1) + "\n")
    return entry


def rank(facet: str, family: str | None = None, today: str | None = None,
         path: Path = LEDGER) -> list:
    """Sources for a facet, best measured yield first. A family match
    doubles an entry's weight — a source rich for THIS kind of subcap
    outranks one rich for the facet at large."""
    d = _load(path)
    now = _dt.date.fromisoformat(today) if today else _dt.date.today()
    score, seen = defaultdict(float), defaultdict(int)
    for e in d["entries"]:
        if e["facet"] != facet.lower():
            continue
        w = _W[e["outcome"]]
        age = (now - _dt.date.fromisoformat(e["on"])).days
        if age > _RECENT_DAYS:
            w *= 0.5
        if family and e.get("family") == family:
            w *= 2.0
        score[e["source"]] += w
        seen[e["source"]] += 1
    return [{"source": s, "yield_score": round(v, 2), "entries": seen[s]}
            for s, v in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))]


def candidates(path: Path = LEDGER,
               register: Path = PLUGIN / "skills" / "dma-surface-production"
               / "02-inputs" / "enrichment_sources.json") -> list:
    """Sources rich at least twice that the declared register does not name
    — the expansion worklist for the rectifier."""
    d = _load(path)
    declared = register.read_text().lower() if register.exists() else ""
    rich = defaultdict(int)
    for e in d["entries"]:
        if e["outcome"] == "rich":
            rich[e["source"]] += 1
    return sorted(s for s, n in rich.items() if n >= 2 and s not in declared)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_log = sub.add_parser("log", help="record one search's outcome")
    p_log.add_argument("--source", required=True)
    p_log.add_argument("--facet", required=True)
    p_log.add_argument("--outcome", required=True, choices=OUTCOMES)
    p_log.add_argument("--tier")
    p_log.add_argument("--family", help="subcap family, e.g. P4C2.5")
    p_log.add_argument("--raised-by", default="session")
    p_log.add_argument("--note")
    p_rank = sub.add_parser("rank", help="best sources for a facet")
    p_rank.add_argument("--facet", required=True)
    p_rank.add_argument("--family")
    p_cand = sub.add_parser("candidates",
                            help="rich sources the register does not declare")
    a = ap.parse_args(argv)
    if a.cmd == "log":
        print(json.dumps(log(a.source, a.facet, a.outcome, a.tier, a.family,
                             a.raised_by, a.note), indent=1))
        return 0
    if a.cmd == "rank":
        print(json.dumps(rank(a.facet, a.family), indent=1))
        return 0
    if a.cmd == "candidates":
        print(json.dumps(candidates(), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
