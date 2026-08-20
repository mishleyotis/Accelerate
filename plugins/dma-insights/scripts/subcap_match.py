#!/usr/bin/env python3
"""Evidence-to-subcap matching that learns from the feedback loop.

Owner instruction, 2026-08-20: "ensure … that evidence matching to subcaps
is accurate. The plugin should install good semantic matching modules that
would learn from the continuous feedback and learning loops."

What this is. A deterministic, offline ranker: given an evidence excerpt
and the capability catalogue (ids, names, descriptions — fetched through
`get_capability_catalogue`, never invented), it ranks the subcap cells the
excerpt most plausibly grounds, says WHY (the matched terms), and ABSTAINS
when the ranking is too close to call. It complements, never replaces, the
connector's server-side V4 grounding: V4 judges a citation already made;
this module helps a producer make the right one, and the two disagreeing is
a finding.

How it learns. plugins/dma-insights/fixtures/match_feedback.json is the
ledger the learning loop writes: when the qa-overseer or rectifier confirms
or rejects an evidence-to-subcap assignment, the VOCABULARY of that
decision (term-to-cell boosts and vetoes — never client prose, never
excerpts) is appended with provenance. The ledger is taxonomy, so it lives
in the repository and compounds across clients; the per-client corrections
that produced each entry live in that client's memory file
(client_memory.py, "evidence matching corrections").

Why not an embedding model here. Fresh session containers carry stdlib
Python only, and the serving invariant is model-free; a wheel-only TF-IDF
ranker runs everywhere the plugin runs, gives the same answer twice, and
its mistakes are legible enough to learn from — which is the property the
feedback loop needs most. The embedding half of matching already exists
where it belongs: inside the connector, at submit, on server hardware.

Abstention is the accuracy feature: an assignment made under a thin margin
is exactly the assignment that used to be wrong. Below --min-margin the
answer is AMBIGUOUS with the contenders listed, and the producer (or a
human) decides — fail closed, like everything else in this system.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
FEEDBACK = PLUGIN / "fixtures" / "match_feedback.json"

_TOKEN = re.compile(r"[a-z0-9][a-z0-9.+-]{1,}")
_STOP = frozenset("""a an and are as at be but by for from has have in into is
it its of on or that the this to was were will with our their your they we
""".split())

# A confirmed term-to-cell boost counts this many extra occurrences of the
# term in the cell's document; a veto removes the term for that cell.
BOOST_WEIGHT = 3.0


def tokens(text: str) -> list:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def load_catalogue(path: str) -> list:
    """[{cell_id, name, description?, category?, pillar?}, …] — the shape
    get_capability_catalogue returns; extra keys are ignored."""
    d = json.loads(Path(path).read_text())
    rows = d.get("cells", d) if isinstance(d, dict) else d
    out = []
    for r in rows:
        cid = r.get("cell_id") or r.get("subcap_id") or r.get("id")
        if not cid:
            continue
        doc = " ".join(str(r.get(k, "")) for k in
                       ("name", "description", "category", "category_name",
                        "pillar", "pillar_name"))
        out.append({"cell_id": str(cid), "doc": doc, "name": r.get("name", "")})
    if not out:
        raise SystemExit("catalogue file yielded no cells — pass the JSON "
                         "get_capability_catalogue returned")
    return out


def load_feedback(path: Path = FEEDBACK) -> dict:
    if not path.exists():
        return {"boosts": {}, "vetoes": {}}
    d = json.loads(path.read_text())
    boosts, vetoes = {}, {}
    for e in d.get("entries", []):
        bucket = boosts if e.get("verdict") == "confirmed" else vetoes
        bucket.setdefault(e["cell_id"], set()).update(
            t.lower() for t in e.get("terms", []))
    return {"boosts": boosts, "vetoes": vetoes}


def rank(excerpt: str, catalogue: list, feedback: dict | None = None,
         top: int = 5) -> list:
    """→ [{cell_id, name, score, matched_terms}], best first. TF-IDF cosine
    over the catalogue corpus, with the ledger's boosts and vetoes applied
    to each cell's document before anything is scored."""
    fb = feedback or {"boosts": {}, "vetoes": {}}
    docs = []
    for c in catalogue:
        ts = tokens(c["doc"])
        vet = fb["vetoes"].get(c["cell_id"], set())
        ts = [t for t in ts if t not in vet]
        counts = Counter(ts)
        for t in fb["boosts"].get(c["cell_id"], set()):
            counts[t] += BOOST_WEIGHT
        docs.append(counts)
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {t: math.log((n + 1) / (df[t] + 0.5)) for t in df}
    q = Counter(tokens(excerpt))
    results = []
    for c, d in zip(catalogue, docs):
        num, matched = 0.0, []
        for t, qc in q.items():
            if t in d:
                num += qc * d[t] * idf.get(t, 0.0) ** 2
                matched.append(t)
        if num <= 0:
            continue
        norm = math.sqrt(sum((v * idf.get(t, 0.0)) ** 2
                             for t, v in d.items())) or 1.0
        qnorm = math.sqrt(sum((v * idf.get(t, 0.0)) ** 2
                              for t, v in q.items())) or 1.0
        results.append({"cell_id": c["cell_id"], "name": c["name"],
                        "score": round(num / (norm * qnorm), 6),
                        "matched_terms": sorted(matched)})
    results.sort(key=lambda r: (-r["score"], r["cell_id"]))
    return results[:top]


def decide(ranked: list, min_margin: float) -> dict:
    """The fail-closed wrapper: a single defensible answer, or abstention."""
    if not ranked:
        return {"decision": "NO_MATCH", "assign": None,
                "reason": "no catalogue cell shares scoring vocabulary with "
                          "the excerpt"}
    if len(ranked) > 1 and (ranked[0]["score"] - ranked[1]["score"]) < min_margin:
        return {"decision": "AMBIGUOUS", "assign": None,
                "contenders": ranked[:3],
                "reason": f"margin {ranked[0]['score'] - ranked[1]['score']:.4f} "
                          f"below {min_margin} — a producer or a human decides, "
                          f"and the decision feeds the ledger"}
    return {"decision": "MATCH", "assign": ranked[0],
            "runner_up": ranked[1] if len(ranked) > 1 else None}


def learn(cell_id: str, verdict: str, terms: list, raised_by: str,
          note: str | None = None, path: Path = FEEDBACK) -> dict:
    if verdict not in ("confirmed", "rejected"):
        raise SystemExit("verdict must be confirmed or rejected")
    if not terms:
        raise SystemExit("name the terms that decided it — the ledger stores "
                         "vocabulary, and vocabulary is what it learns from")
    d = json.loads(path.read_text()) if path.exists() else {
        "_doc": "Learned evidence-to-subcap matching vocabulary. Appended by "
                "the learning loop (qa-overseer, rectifier) when an "
                "assignment is confirmed or rejected. Terms and cell ids "
                "only — never client prose, never excerpts; the per-client "
                "story behind each entry is in that client's memory file.",
        "entries": []}
    entry = {"cell_id": cell_id, "verdict": verdict,
             "terms": sorted({t.lower() for t in terms}),
             "raised_by": raised_by, "on": _dt.date.today().isoformat()}
    if note:
        entry["note"] = note
    d["entries"].append(entry)
    path.write_text(json.dumps(d, indent=1, sort_keys=False) + "\n")
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_rank = sub.add_parser("rank", help="rank subcaps for an excerpt")
    p_rank.add_argument("--catalogue", required=True,
                        help="JSON from get_capability_catalogue")
    p_rank.add_argument("--excerpt", required=True)
    p_rank.add_argument("--top", type=int, default=5)
    p_rank.add_argument("--min-margin", type=float, default=0.05)
    p_learn = sub.add_parser("learn", help="append a feedback ledger entry")
    p_learn.add_argument("--cell", required=True)
    p_learn.add_argument("--verdict", required=True,
                         choices=("confirmed", "rejected"))
    p_learn.add_argument("--terms", required=True,
                         help="comma-separated deciding terms")
    p_learn.add_argument("--raised-by", required=True,
                         help="who decided (agent name, MEM id, USER)")
    p_learn.add_argument("--note")
    a = ap.parse_args(argv)

    if a.cmd == "rank":
        ranked = rank(a.excerpt, load_catalogue(a.catalogue),
                      load_feedback(), a.top)
        print(json.dumps(decide(ranked, a.min_margin), indent=1))
        return 0
    if a.cmd == "learn":
        entry = learn(a.cell, a.verdict,
                      [t.strip() for t in a.terms.split(",") if t.strip()],
                      a.raised_by, a.note)
        print(json.dumps(entry, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
