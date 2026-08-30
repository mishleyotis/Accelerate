#!/usr/bin/env python3
"""Evidence Rank Score — computed where the evidence is banked.

    python3 -m engine.ers recompute --run R [--root DIR]
    python3 -m engine.ers show      --run R [--json]
    python3 -m engine.ers explain   --e-id E-004 --run R
    python3 -m engine.ers formula

WHY THIS EXISTS. `ERS` is a column of the contract-v3 evidence register,
`scripts/calculate_ers.py` is a full implementation of the score, and the
2026-08-30 audit found that **nothing joined them**. `append_evidence` took
`ers` as an optional caller-supplied argument defaulting to None; no caller
in the repository ever passed one; the standalone calculator ran over an
`evidence_index.json` projection that no stage feeds it. Measured on the
Golden 1 workbook: twenty evidence rows, twenty empty ERS cells.

An empty ERS is not a cosmetic gap. Three things downstream are supposed to
read it and cannot:

  - the report's **evidence base** section, which ranks what the assessment
    actually rests on;
  - the **thin-evidence** judgement, which currently sees only a count where
    it should see a weighted mass;
  - the **corroboration** signal, which is the whole reason a second
    independent source is worth banking.

So the score is computed HERE, at the write, and recomputed when
corroboration changes it. The formula is the archive's own — nothing is
invented — but two things are new and deliberate:

  1. **Corroboration is measured over SOURCE IDENTITIES, not rows.** Three
     pages of one annual report are one source (the same rule
     `single_source_fact` enforces on the floors gate), so citing a document
     three times no longer raises its own score.
  2. **RRF and BM25 feed specificity when the retrieval log has them.** A
     source that several independent query formulations ranked highly, and
     that BM25 says is actually about the diagnostic question, is more
     specific than one that appeared once. Where those signals are absent
     the term degrades to the excerpt-shape heuristic and SAYS SO in
     `explain`, rather than silently scoring as if it had them.
"""
from __future__ import annotations

# Runnable both ways: -m engine.ers, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import re
import sys
from pathlib import Path

from . import contract as C


def C_COLS():
    return C.SHEETS["Evidence_Detail"]

#: The archive's weights (scripts/calculate_ers.py), kept verbatim so a
#: score computed here is comparable with one computed there.
W_TIER, W_RECENCY, W_SPECIFICITY, W_CORROBORATION = 0.35, 0.25, 0.20, 0.20

TIER_SCORE = {"T1": 5.0, "T2": 4.0, "T3": 3.0, "T4": 2.0, "T5": 1.0}
RECENCY_SCORE = {"CURRENT": 5.0, "RECENT": 4.0, "DATED": 3.0,
                 "LEGACY": 1.5, "ARCHIVAL": 1.0,
                 # Undated is NOT treated as middling-recent. Invariant 9:
                 # undated evidence is UNVERIFIED, never current, and a
                 # score that flatters it is the AUD-0020 shape.
                 "UNVERIFIED": 2.0}

#: A citable excerpt that carries a figure, a date or a named product is
#: more specific than one that carries none. The fallback when the
#: retrieval log has no ranking for this source.
_FIGURE = re.compile(r"\d[\d,.]*\s*(percent|%|million|billion|bn|m\b)|"
                     r"\b(19|20)\d{2}\b|\$\s?\d")
_NAMED = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+|\s[A-Z][a-z]+)+\b")

#: Below this, an evidence base is thin however many rows it has. Set at the
#: score a single dated T3 with no corroboration earns, because that is the
#: point at which "we have three sources" stops meaning "we know".
THIN_ERS = 2.6


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def source_identity(row: dict) -> str:
    """One source, however many rows cite it.

    Host first, source name second — the same identity rule the floors
    gate's `single_source_fact` term uses, so the two cannot disagree about
    what counts as a second opinion."""
    url = _clean(row.get("Source_URL"))
    if url:
        host = url.split("//")[-1].split("/")[0].lower()
        if host:
            return host
    return _clean(row.get("Source_Name")).lower()


def specificity(row: dict, ranking: dict | None = None) -> tuple[float, str]:
    """How much this source actually says, 1-5, and why.

    `ranking` is an optional retrieval record for this URL:
    {"lists": <how many independent query formulations ranked it>,
     "bm25": <rerank score against the diagnostic question>}."""
    if ranking:
        lists = int(ranking.get("lists") or 0)
        bm25 = float(ranking.get("bm25") or 0.0)
        # Consensus across independent formulations is the RRF signal; the
        # BM25 score is topical fit. Both are already normalised 0..1-ish by
        # engine/retrieval.py, so this maps them onto the 1-5 band.
        score = 1.0 + min(3.0, lists * 0.75) + min(1.0, max(0.0, bm25))
        return round(min(5.0, score), 2), (
            f"retrieval: ranked by {lists} independent query formulation(s), "
            f"BM25 {bm25:.2f} against the diagnostic question")
    text = _clean(row.get("Excerpt"))
    score = 2.0
    why = ["excerpt heuristic (no retrieval ranking recorded for this URL)"]
    if _FIGURE.search(text):
        score += 1.5
        why.append("carries a figure or a date")
    if _NAMED.search(text):
        score += 1.0
        why.append("names a product, vendor or person")
    if len(text) >= 150:
        score += 0.5
        why.append("substantive length")
    return round(min(5.0, score), 2), "; ".join(why)


def corroboration(row: dict, all_rows: list[dict]) -> tuple[float, str]:
    """How many OTHER source identities carry a claim about the same cells.

    Identities, not rows: three pages of one annual report are one source,
    so citing a document three times cannot corroborate itself."""
    mine = source_identity(row)
    cells = {c.strip() for c in _clean(row.get("SubCap_IDs")).split(",")
             if c.strip()}
    if not cells:
        # Institution-profile evidence supports the client, not a cell.
        # It has no cell-mates by construction; scoring it 1.0 would be
        # punishing it for being what it is.
        return 3.0, "institution-profile source; corroboration not applicable"
    others = set()
    for r in all_rows:
        if source_identity(r) == mine:
            continue
        their = {c.strip() for c in _clean(r.get("SubCap_IDs")).split(",")
                 if c.strip()}
        if cells & their:
            others.add(source_identity(r))
    n = len(others)
    score = {0: 1.0, 1: 3.0, 2: 4.0}.get(n, 5.0)
    return score, (f"{n} other source identit{'y' if n == 1 else 'ies'} "
                   f"carr{'ies' if n == 1 else 'y'} a claim about the same "
                   f"cell(s)" + (f": {', '.join(sorted(others)[:4])}" if others
                                 else " — this source stands alone"))


def score_row(row: dict, all_rows: list[dict],
              ranking: dict | None = None) -> dict:
    """The full score with every term shown, so a reader can argue with it."""
    tier = _clean(row.get("Tier")).upper()
    rec = _clean(row.get("Recency")).upper()
    t = TIER_SCORE.get(tier, 1.0)
    r = RECENCY_SCORE.get(rec, 2.0)
    s, s_why = specificity(row, ranking)
    c, c_why = corroboration(row, all_rows)
    ers = W_TIER * t + W_RECENCY * r + W_SPECIFICITY * s + W_CORROBORATION * c
    return {
        "e_id": row.get("E_ID"), "ers": round(ers, 2),
        "terms": {
            "tier": {"band": tier or None, "score": t, "weight": W_TIER},
            "recency": {"band": rec or None, "score": r, "weight": W_RECENCY},
            "specificity": {"score": s, "weight": W_SPECIFICITY,
                            "why": s_why},
            "corroboration": {"score": c, "weight": W_CORROBORATION,
                              "why": c_why},
        },
        "thin": ers < THIN_ERS,
        "source_identity": source_identity(row),
    }


def rankings_for(run) -> dict[str, dict]:
    """Retrieval rankings per normalised URL, if the run recorded any.

    `engine.retrieval fuse` writes its fused output to 02_search/ when a
    researcher runs it. Absent, every specificity term degrades to the
    excerpt heuristic and says so — never silently."""
    out: dict[str, dict] = {}
    d = Path(run.root) / "02_search"
    if not d.is_dir():
        return out
    from . import retrieval as R
    for p in sorted(d.glob("*.json")):
        try:
            doc = json.loads(p.read_text())
        except ValueError:
            continue
        rows = doc if isinstance(doc, list) else (doc.get("fused")
                                                  or doc.get("results") or [])
        for item in rows if isinstance(rows, list) else []:
            url = item.get("url") or item.get("link")
            if not url:
                continue
            key = R.normalise_url(url)
            prev = out.get(key, {"lists": 0, "bm25": 0.0})
            out[key] = {
                "lists": max(prev["lists"],
                             int(item.get("lists") or item.get("n_lists") or 0)),
                "bm25": max(prev["bm25"],
                            float(item.get("bm25") or item.get("score") or 0.0)),
            }
    return out


def recompute(wb, run=None) -> dict:
    """Score every evidence row, and write the scores back.

    Recomputation is the point: corroboration is a property of the register
    as a whole, so a row banked first is re-scored when its second source
    arrives. A score frozen at insert would permanently under-rate the
    evidence a run gathers in the order runs actually gather it."""
    from . import retrieval as R
    rows = [r for r in wb.rows("Evidence_Detail") if _clean(r.get("E_ID"))]
    rank = rankings_for(run) if run is not None else {}
    scored = []
    for row in rows:
        url = _clean(row.get("Source_URL"))
        ranking = rank.get(R.normalise_url(url)) if url else None
        scored.append(score_row(row, rows, ranking))

    # ONE worksheet pass, one save. `update_row` scans the sheet per call,
    # which made this O(n^2) on a path that runs at every evidence append —
    # measured at ~0.3s per bank on a 24-row register, and every append pays
    # it. The score is still recomputed across the whole register, because
    # corroboration is a property of the register; only the WRITE is cheap.
    by_id = {str(x["e_id"]): x["ers"] for x in scored}
    if by_id:
        ws = wb._sheet("Evidence_Detail")
        cols = list(C_COLS())
        idc, ersc = cols.index("E_ID") + 1, cols.index("ERS") + 1
        for r_ in range(2, ws.max_row + 1):
            eid = str(ws.cell(row=r_, column=idc).value or "").strip()
            if eid in by_id:
                ws.cell(row=r_, column=ersc, value=by_id[eid])
        wb.save()
    vals = [s["ers"] for s in scored]
    return {
        "scored": len(scored),
        "mean": round(sum(vals) / len(vals), 2) if vals else None,
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
        "thin_rows": [s["e_id"] for s in scored if s["thin"]],
        "thin_pct": (round(100 * sum(1 for s in scored if s["thin"])
                           / len(scored), 1) if scored else None),
        "rankings_available": len(rank),
        "specificity_basis": ("retrieval rankings" if rank
                              else "excerpt heuristic (no fused retrieval "
                                   "output in 02_search/)"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.ers",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("recompute", "show"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        p.add_argument("--json", action="store_true")
    e = sub.add_parser("explain")
    e.add_argument("--run", required=True); e.add_argument("--root")
    e.add_argument("--e-id", required=True)
    sub.add_parser("formula")

    a = ap.parse_args(argv)
    if a.cmd == "formula":
        print(f"ERS = {W_TIER}*tier + {W_RECENCY}*recency + "
              f"{W_SPECIFICITY}*specificity + {W_CORROBORATION}*corroboration"
              f"\n  tier      {TIER_SCORE}"
              f"\n  recency   {RECENCY_SCORE}"
              f"\n  specific  retrieval consensus (RRF lists) + BM25 fit, "
              f"else excerpt heuristic"
              f"\n  corrob    OTHER source identities on the same cells "
              f"(hosts, not rows)"
              f"\n  thin      ERS < {THIN_ERS}")
        return 0
    from . import runstate
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    if a.cmd == "recompute":
        out = recompute(wb, run)
        print(json.dumps(out, indent=2))
        return 0
    rows = [r for r in wb.rows("Evidence_Detail") if _clean(r.get("E_ID"))]
    rank = rankings_for(run)
    from . import retrieval as R
    if a.cmd == "explain":
        row = next((r for r in rows if _clean(r.get("E_ID")) == a.e_id), None)
        if row is None:
            print(f"no evidence {a.e_id} in this run", file=sys.stderr)
            return 1
        url = _clean(row.get("Source_URL"))
        s = score_row(row, rows, rank.get(R.normalise_url(url)) if url else None)
        print(json.dumps(s, indent=2))
        return 0
    scored = [score_row(r, rows, rank.get(R.normalise_url(
        _clean(r.get("Source_URL"))))) for r in rows]
    if a.json:
        print(json.dumps(scored, indent=2))
    else:
        for s in sorted(scored, key=lambda x: -x["ers"]):
            print(f"  {s['ers']:>5.2f} {'THIN ' if s['thin'] else '     '}"
                  f"{s['e_id']:<8} {s['source_identity'][:48]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
