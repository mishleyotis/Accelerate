"""The coverage block: novelty, saturation, conflicts, the ladder searched.

Returned with every `research_brief` and summarised by `coverage_report`.
Everything here is COMPUTED from the cards a run holds (brief §3); nothing
is resolved — a conflict is flagged for the agents, never averaged.

Saturation (the stop rule): true when two consecutive calls on the same
facet each added less than 10% novel origin clusters relative to what the
run already held for that facet. Concentration: one origin cluster over
40% of a unit's cards is flagged. Proxy ladder: when a question returns
zero cards, the rungs that WERE searched are listed, so an absence cites a
documented search rather than silence.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .contract import FACETS, LADDER_RUNGS, RECENCY_WORDS

NOVELTY_SATURATION = 0.10
CONCENTRATION_FLAG = 0.40

#: numeric-field detectors for conflict candidates: (label, regex over the
#: excerpt). A label groups figures that describe the same thing.
_FIELDS = (
    ("members", re.compile(r"(\d[\d,\.]*\s?(?:million|thousand|k)?)\s+(?:members|member-owners)\b", re.I)),
    ("customers", re.compile(r"(\d[\d,\.]*\s?(?:million|thousand|k)?)\s+(?:customers|clients)\b", re.I)),
    ("employees", re.compile(r"(\d[\d,\.]*\s?(?:million|thousand|k)?)\s+(?:employees|staff|team members)\b", re.I)),
    ("branches", re.compile(r"(\d[\d,]*)\s+(?:branches|locations|offices)\b", re.I)),
    ("assets", re.compile(r"\$\s?(\d[\d,\.]*\s?(?:billion|million|B|M)?)\s+(?:in\s+)?(?:total\s+)?assets\b", re.I)),
    ("founded", re.compile(r"\b(?:founded|established|chartered)\s+in\s+((?:19|20)\d{2})\b", re.I)),
    ("app_rating", re.compile(r"(\d\.\d)\s*(?:stars?|/5|out of 5)\b", re.I)),
)


def _norm_figure(s: str) -> str:
    s = s.lower().replace(",", "").strip()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(billion|million|thousand|b|m|k)?", s)
    if not m:
        return s
    v = float(m.group(1))
    mult = {"billion": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}.get(m.group(2) or "", 1)
    return f"{v * mult:.0f}"


def conflict_candidates(cards: list[dict]) -> list[dict]:
    """Cards from DIFFERENT origin clusters carrying different values for
    the same numeric field. Flagged, never resolved."""
    by_field: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    where: dict[tuple, list] = defaultdict(list)
    for c in cards:
        ex = c["item"]["excerpt"]
        oc = c["provenance"].get("origin_cluster", "")
        for label, pat in _FIELDS:
            for m in pat.finditer(ex):
                val = _norm_figure(m.group(1))
                by_field[label][val].add(oc)
                where[(label, val)].append(c["card_id"])
    out = []
    for label, vals in by_field.items():
        if len(vals) < 2:
            continue
        clusters = {v: ocs for v, ocs in vals.items()}
        # different values from different clusters
        all_ocs = set().union(*clusters.values())
        if len(all_ocs) < 2:
            continue
        out.append({"field": label,
                    "values": [{"value": v, "origin_clusters": sorted(ocs),
                                "card_ids": sorted(where[(label, v)])}
                               for v, ocs in sorted(clusters.items())],
                    "disposition": "open — adjudicate; the engine never averages"})
    return sorted(out, key=lambda r: r["field"])


def novelty(returned_clusters: list[str], known_clusters: set[str]) -> float:
    rc = set(returned_clusters)
    if not rc:
        return 0.0
    return len(rc - known_clusters) / len(rc)


def saturation(history: list[float]) -> bool:
    """Two consecutive calls each under the novelty floor."""
    return len(history) >= 2 and all(h < NOVELTY_SATURATION for h in history[-2:])


def concentration(cards: list[dict]) -> dict:
    n = len(cards)
    if not n:
        return {"flag": False, "top_cluster": None, "share": 0.0}
    cnt = Counter(c["provenance"].get("origin_cluster", "") for c in cards)
    oc, k = cnt.most_common(1)[0]
    share = k / n
    return {"flag": share > CONCENTRATION_FLAG and n >= 3, "top_cluster": oc,
            "share": round(share, 3), "cards": n}


def recency_distribution(cards: list[dict]) -> dict:
    cnt = Counter(c["provenance"].get("recency", "UNVERIFIED") for c in cards)
    return {w: cnt.get(w, 0) for w in RECENCY_WORDS}


def source_diversity(cards: list[dict]) -> dict:
    hosts = Counter(c["provenance"].get("host", "") for c in cards)
    types_ = Counter(c["provenance"].get("source_type_hint", "other") for c in cards)
    return {"distinct_hosts": len([h for h in hosts if h]),
            "distinct_origin_clusters": len({c["provenance"].get("origin_cluster") for c in cards}),
            "by_source_type": dict(sorted(types_.items()))}


def ladder_searched(queries: list[dict], sources_used: list[str], rungs_hit: set[str]) -> list[str]:
    """Which proxy-ladder rungs a brief actually searched: from the query
    kinds (site: packs), the sources that answered, and the rungs the
    returned/considered pages sat on."""
    rungs = set(rungs_hit)
    for q in queries:
        k = q.get("kind", "")
        if k.startswith("site:entity"):
            rungs.add("entity_site")
        elif k.startswith("site:regulator"):
            rungs.add("regulator")
        elif k.startswith("site:trade_press"):
            rungs.add("trade_press")
        elif k.startswith("site:careers"):
            rungs.add("careers")
    if any(s.startswith("edgar") for s in sources_used):
        rungs.add("filings")
    if any(s in ("searxng", "parallel") for s in sources_used):
        rungs.add("news")
    return [r for r in LADDER_RUNGS if r in rungs]


def coverage_block(*, run_state: dict, facet: str | None, returned: list[dict],
                   queries: list[dict], sources_used: list[str]) -> dict:
    """The block attached to a research_brief result. `run_state` is the
    run's persisted state BEFORE this call (clusters per facet, novelty
    history per facet); the caller persists the update returned here."""
    facet_key = facet or "all"
    known = set(run_state.get("clusters", {}).get(facet_key, []))
    rc = [c["provenance"].get("origin_cluster", "") for c in returned]
    nov = novelty(rc, known)
    hist = list(run_state.get("novelty_history", {}).get(facet_key, [])) + [round(nov, 3)]
    sat = saturation(hist)
    rungs_hit = {c["provenance"].get("ladder_rung", "other") for c in returned}
    block = {
        "facet": facet_key,
        "cards_returned": len(returned),
        "novelty": round(nov, 3),
        "novel_origin_clusters": sorted(set(rc) - known),
        "saturation": sat,
        "saturation_rule": f"two consecutive calls on this facet each added < {int(NOVELTY_SATURATION * 100)}% novel origin clusters",
        "conflict_candidates": conflict_candidates(returned),
        "concentration": concentration(returned),
        "ladder_searched": ladder_searched(queries, sources_used, rungs_hit),
        "recency": recency_distribution(returned),
        "source_diversity": source_diversity(returned),
        "entity_match": dict(Counter(c["provenance"].get("entity_match", "ambiguous") for c in returned)),
    }
    new_state = {
        "clusters": {**run_state.get("clusters", {}), facet_key: sorted(known | set(rc))},
        "novelty_history": {**run_state.get("novelty_history", {}), facet_key: hist[-10:]},
    }
    return block, new_state


def coverage_report(cards: list[dict], run_state: dict, labels_by_card: dict[str, list[str]] | None = None) -> dict:
    """Per-facet and per-label counts over everything a run holds."""
    labels_by_card = labels_by_card or {}
    per_facet: dict[str, list] = defaultdict(list)
    per_label: dict[str, list] = defaultdict(list)
    for c in cards:
        for f in c["provenance"].get("facet_hints") or ["unfaceted"]:
            per_facet[f].append(c)
        for lab in labels_by_card.get(c["card_id"], []):
            per_label[lab].append(c)
    def unit(cs):
        return {"cards": len(cs), "concentration": concentration(cs),
                "recency": recency_distribution(cs),
                "source_diversity": source_diversity(cs)}
    out = {
        "cards_total": len(cards),
        "per_facet": {f: unit(per_facet.get(f, [])) for f in list(FACETS) + ["unfaceted"] if f in per_facet},
        "per_label": {k: unit(v) for k, v in sorted(per_label.items())},
        "conflict_candidates": conflict_candidates(cards),
        "concentration": concentration(cards),
        "recency": recency_distribution(cards),
        "source_diversity": source_diversity(cards),
        "saturation_by_facet": {f: saturation(h) for f, h in (run_state.get("novelty_history") or {}).items()},
        "entity_match": dict(Counter(c["provenance"].get("entity_match", "ambiguous") for c in cards)),
    }
    return out
