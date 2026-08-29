#!/usr/bin/env python3
"""Retrieval that gets better with more queries: RRF fusion + BM25 rerank.

    python3 -m engine.retrieval fuse --in results.json [--top 10] [--query '...']
    python3 -m engine.retrieval plan --run R --subcap P1C1.1.1 [--facet works]

WHY THIS EXISTS. A category researcher fires several query variants per
diagnostic question — the facet probe, the toolkit's named artefacts, the
adversarial operators — across whatever search tools the session holds
(WebSearch, Exa, Tavily). Each returns its own ranked list. Taking the top
of ONE list wastes the others; concatenating them rewards whichever tool
returned the most rows. The audit's own query-fidelity finding (AUD-0074:
40% of DQ/query pairs had no responsive query) is partly a fusion problem —
one templated query per facet, winner-takes-all.

RECIPROCAL RANK FUSION is the standard answer: score(d) = Σ 1/(k + rank_i(d))
over every list that ranks d, with k = 60 — Cormack, Clarke & Buettcher,
SIGIR 2009 ("Reciprocal Rank Fusion outperforms Condorcet and individual
Rank Learning Methods"), and the constant every production system has kept
(Elasticsearch's rrf retriever, OpenSearch hybrid search, Azure AI Search,
Chroma). RRF prefers CONSENSUS: a source ranked #8 by three differently-
shaped queries beats a source ranked #1 by one and absent from the rest —
which is exactly the property evidence gathering wants, because a document
that answers the works probe AND the toolkit's named artefact AND survives
the adversarial phrasing is the document worth fetching first.

BM25 (Okapi; after dorianbrown/rank_bm25, reimplemented on the stdlib
because this plugin adds no dependencies) reranks the fused list against
the DIAGNOSTIC QUESTION's own text — fusion says "consistently retrieved",
BM25 says "actually about the question" — and it ABSTAINS: a candidate
scoring under the floor is returned in `below_floor`, not silently ranked,
because AUD-0075's mapper had no abstain path and filed county-fair mascots
under Fair Lending Governance.

Everything here is deterministic and local. No model, no network: the
session's search TOOLS produce the input lists; this module only fuses and
reranks what they returned.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import contract as C

#: Cormack et al.'s constant, unchanged by a decade of production use. Not
#: configurable per call on purpose: a knob nobody can justify moving is a
#: knob that gets moved to make one run look better.
RRF_K = 60

#: BM25 free parameters, the textbook defaults.
BM25_K1, BM25_B = 1.5, 0.75

#: Below this BM25 score against the question text, a candidate ABSTAINS
#: rather than ranks — measured on the probe battery style of AUD-0075:
#: zero-overlap noise scores 0.0, and topical-but-thin scores under ~1.0.
ABSTAIN_FLOOR = 0.5

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
             "utm_content", "gclid", "fbclid", "ref", "mc_cid", "mc_eid"}


def normalise_url(url: str) -> str:
    """One URL, one identity: scheme/host case, default ports, tracking
    params and trailing slashes do not make a second source."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return str(url or "").strip().lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    query = "&".join(sorted(
        p for p in parts.query.split("&")
        if p and p.split("=")[0].lower() not in _TRACKING))
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def rrf(result_lists, *, k: int = RRF_K, top: int | None = None) -> list[dict]:
    """Fuse ranked lists of {url, title?, snippet?} into one consensus list.

    Returns items carrying `rrf_score`, `lists_ranking_it` and `provenance`
    ({list index: rank}) — the fusion must be auditable, because "why is
    this source first" is a question the challenger will ask."""
    scores: dict[str, float] = {}
    seen: dict[str, dict] = {}
    prov: dict[str, dict] = {}
    for li, results in enumerate(result_lists):
        for rank, item in enumerate(results or [], start=1):
            if isinstance(item, str):
                item = {"url": item}
            url = item.get("url") or item.get("link") or ""
            key = normalise_url(url)
            if not key or key == "/":
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            prov.setdefault(key, {})[li] = rank
            best = seen.get(key)
            # Merge toward the richest copy (longest snippet), but the URL is
            # first-seen and stays: the variants are one identity by
            # construction of the key, and swapping the fetchable URL for a
            # later tracking-parameter variant would make the audit trail
            # depend on list order.
            if best is None or len(str(item.get("snippet") or "")) > \
                    len(str(best.get("snippet") or "")):
                merged = dict(best or {})
                merged.update({kk: vv for kk, vv in item.items() if vv})
                if best and best.get("url"):
                    merged["url"] = best["url"]
                seen[key] = merged
    out = []
    for key, sc in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
        item = dict(seen[key])
        item["url"] = item.get("url") or key
        item["rrf_score"] = round(sc, 6)
        item["lists_ranking_it"] = len(prov[key])
        item["provenance"] = {str(i): r for i, r in sorted(prov[key].items())}
        out.append(item)
    return out[:top] if top else out


# ── BM25, stdlib ─────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9][a-z0-9'&.-]*")
_STOP = frozenset(
    "a an and are as at be by for from has have how in is it its of on or "
    "that the this to was what when where which who with does do did their "
    "they".split())


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(str(text or "").lower())
            if t not in _STOP]


def bm25_scores(query: str, docs: list[str], *, k1: float = BM25_K1,
                b: float = BM25_B) -> list[float]:
    """Okapi BM25 of one query against small in-memory docs. The +0.5/+0.5
    IDF smoothing keeps a term in every doc from going negative."""
    toks = [_tokens(d) for d in docs]
    n = len(toks)
    if n == 0:
        return []
    avgdl = sum(len(t) for t in toks) / max(1, n) or 1.0
    df = Counter()
    for t in toks:
        df.update(set(t))
    q = _tokens(query)
    out = []
    for t in toks:
        tf = Counter(t)
        dl = len(t)
        s = 0.0
        for term in q:
            f = tf.get(term, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        out.append(round(s, 4))
    return out


def rerank(question: str, fused: list[dict], *, floor: float = ABSTAIN_FLOOR
           ) -> dict:
    """BM25-rerank a fused list against the DQ text, with an abstain path.

    {ranked: [...], below_floor: [...]} — below_floor is returned, never
    dropped: the researcher decides whether a thin match is worth a fetch,
    and the challenger can see what was set aside."""
    docs = [" ".join(str(x.get(f) or "") for f in ("title", "snippet", "url"))
            for x in fused]
    scores = bm25_scores(question, docs)
    ranked, below = [], []
    for item, s in zip(fused, scores):
        item = dict(item)
        item["bm25_vs_question"] = s
        (ranked if s >= floor else below).append(item)
    ranked.sort(key=lambda x: (-x["bm25_vs_question"], -x.get("rrf_score", 0)))
    return {"question": question, "ranked": ranked, "below_floor": below,
            "abstain_floor": floor}


# ── query planning ───────────────────────────────────────────────────────

#: Adversarial operator pack per facet — the vocabulary quality.py's
#: contradicts detector recognises, kept in one place with it.
_FACET_OPERATORS = {
    "works": 'implementation OR rollout OR "went live" OR launched OR deployed',
    "fails": 'delayed OR descoped OR postponed OR abandoned OR "did not"',
    "value": 'results OR outcome OR adoption OR "reduced" OR "increased" OR ROI',
    "contradicts": ('enforcement OR lawsuit OR criticism OR abandoned OR '
                    '"yet to" OR complaint OR fine OR breach'),
    "corroborates": 'regulator OR analyst OR review OR rating OR award OR filing',
    "ai_deployment": '"AI" OR "machine learning" OR automation OR chatbot OR model',
    "ai_data": '"data governance" OR "data platform" OR warehouse OR "single view"',
    "ai_constraint": '"model risk" OR "AI policy" OR "responsible AI" OR governance',
    "primary": "",
}

#: A toolkit source-list entry ("1) Annual Report—strategy section (US-...")
#: becomes a quoted search operand.
_SOURCE_ITEM = re.compile(r"\d+\)\s*([^;\n(]{4,60})")


def plan_queries(entity: str, subcap_name: str | None, facet: str,
                 question: str, public_sources: str | None = None) -> list[str]:
    """The query variants ONE DQ deserves — each a differently-shaped probe,
    so the fusion has real disagreement to reconcile.

    1. entity + subcap-name + facet operators   (presence-shaped)
    2. entity + the question's own content words (responsiveness — the
       AUD-0074 gap: a query that carries what the DQ actually asks)
    3. entity + each toolkit-named public artefact (the source lists are
       the toolkit telling us WHERE the answer lives)"""
    if facet not in C.DQ_FACETS:
        raise ValueError(f"facet {facet!r} not in {C.DQ_FACETS}")
    e = f'"{entity}"'
    name = (subcap_name or "").strip()
    out = []
    ops = _FACET_OPERATORS.get(facet, "")
    if name or ops:
        out.append(" ".join(x for x in (e, name, ops) if x).strip())
    # The question's INFORMATIVE words. The graded stems ("to what extent",
    # "established", "since when") are scaffolding every DQ shares — carrying
    # them makes every responsive probe the same probe.
    _generic = {"extent", "formal", "documented", "established", "defined",
                "there", "reviewed", "since", "today", "trace", "earliest",
                "signal", "refreshes", "stalls", "organization", "well"}
    ent_toks = set(_tokens(entity))
    content = " ".join([t for t in _tokens(question)
                        if t not in ent_toks and t not in _generic][:10])
    if content:
        out.append(f"{e} {content}")
    for m in _SOURCE_ITEM.finditer(public_sources or ""):
        src = m.group(1).strip().rstrip("—-")
        if src:
            out.append(f'{e} "{src}"')
    # dedupe, keep order
    seen, uniq = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq[:6]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fuse", help="RRF-fuse ranked result lists; optional "
                                    "BM25 rerank against --query")
    f.add_argument("--in", dest="infile", required=True,
                   help="JSON: a list of result lists, or "
                        "{lists: [...], query: '...'}")
    f.add_argument("--top", type=int, default=10)
    f.add_argument("--query", help="DQ text to rerank against (BM25 + abstain)")
    p = sub.add_parser("plan", help="query variants for one subcap's DQ")
    p.add_argument("--run", required=True)
    p.add_argument("--root")
    p.add_argument("--subcap", required=True)
    p.add_argument("--facet", default="works", choices=C.DQ_FACETS)
    a = ap.parse_args(argv)
    if a.cmd == "fuse":
        doc = json.loads(Path(a.infile).read_text())
        lists = doc["lists"] if isinstance(doc, dict) else doc
        query = a.query or (doc.get("query") if isinstance(doc, dict) else None)
        fused = rrf(lists, top=None)
        out = rerank(query, fused) if query else {"ranked": fused,
                                                  "below_floor": []}
        out["ranked"] = out["ranked"][:a.top]
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "plan":
        from . import kg, runstate
        run = runstate.locate(a.run, Path(a.root) if a.root else None)
        wb = run.open()
        md = wb.metadata()
        split = kg.dqs_for(wb, a.subcap)
        row = next((d for d in split["ask"] if d["facet"] == a.facet), None)
        if row is None:
            print(json.dumps({"error": f"{a.facet} is not askable for "
                              f"{a.subcap} in mode {split['mode']}",
                              "deferred": split["deferred"]}, indent=2))
            return 1
        qs = plan_queries(str(md.get("entity_name")), None, a.facet,
                          str(row["question"]),
                          row.get("public_sources"))
        print(json.dumps({"subcap": a.subcap, "facet": a.facet,
                          "queries": qs}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
