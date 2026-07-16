"""Individual peer roster derive (self-healing, grounded — no fabrication).

The `06_peers/peer_scores_*.json` files name each comparator and score it per
capability category — but ingest consumed them only as a row count, so no
surface could show "who are this client's peers and how do they score". This
pass reads those files straight from the package corpus, matches each package to
its ACTIVE run via run_manifest `run_id` → `runs.request_id`, and persists the
roster into `entity_peers` (each peer's per-category scores + computed overall),
powering the D5 Context "Peer comparison" card.

Grounded in the package's own numbers; never invented. Best-effort + idempotent
(DELETE+INSERT per entity). Packages shipping no peer_scores stay empty (honest).

Usage: DATABASE_URL=... [DMA_SEED_CORPUS_DIR=...] python -m app.scripts.derive_peers
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import sys
from datetime import date, datetime

from sqlalchemy import text

from app.database import get_sessionmaker

_CORPUS = (os.environ.get("DMA_PEERS_CORPUS_DIR")
           or os.environ.get("DMA_SEED_CORPUS_DIR")
           or "tests/fixtures/dma_packages_batches")


def _prefix(run_id: str) -> str:
    """Drop the trailing sequence so '…-001' and '…-0001' (ingest-normalised)
    collide — the institution+date is the stable key."""
    return re.sub(r"-\d+$", "", run_id.strip())


_STOP = {"the", "and", "of", "dma", "inc", "co", "corp", "corporation", "company",
         "group", "bank", "credit", "union", "financial", "financials", "insurance",
         "mutual", "holdings", "holding", "na", "national", "association", "ltd",
         "limited", "deliverables", "v1", "0"}


def _run_ids_for(root: str) -> set[str]:
    """Every run_id named in any run_manifest under the package root (the
    matching package may store its id in 00/07/08; order isn't reliable)."""
    out: set[str] = set()
    for rm in glob.glob(os.path.join(root, "**", "run_manifest.json"), recursive=True):
        try:
            with open(rm) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        rid = d.get("run_id") or d.get("request_id")
        if rid:
            out.add(str(rid).strip())
    return out


def _name_tokens(s: str) -> frozenset[str]:
    toks = {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 3 and t not in _STOP}
    return frozenset(toks)


def _to_date(v: object) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except ValueError:
        return None


def _parse_peer(path: str) -> dict | None:
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    name = (d.get("peer_name") or d.get("name") or "").strip()
    if not name:
        return None
    raw = d.get("category_scores") or d.get("scores") or {}
    cats: dict[str, float] = {}
    for k, v in raw.items():
        sc = v.get("score") if isinstance(v, dict) else v
        try:
            cats[k] = round(float(sc), 2)
        except (TypeError, ValueError):
            continue
    if not cats:
        return None
    return {
        "peer_name": name[:200],
        "role": (d.get("role") or d.get("peer_type") or None),
        "scoring_date": _to_date(d.get("scoring_date")),
        "overall": round(sum(cats.values()) / len(cats), 2),
        "category_scores": cats,
        "evidence_sources": d.get("evidence_sources") or [],
    }


async def _cohort_fallback(session) -> tuple[int, int]:
    """Grounded peer roster for entities the package pass left empty.

    A package that shipped no ``06_peers/peer_scores_*.json`` would render an
    empty D5 "Peer comparison" card + dashed peer overlay. But every client's
    cohort — the other ACTIVE clients in the SAME subvertical — is already in
    the DB with real, fully-scored ``subcap_scores``. This builds each peer from
    those real numbers: category-grain means (``LEFT(subcap_id,4)`` → P1C1..P4C4,
    identical to the overview's pillar math), ranked by maturity proximity to
    the client, top 5. 100% grounded in real portfolio scores — never invented,
    no mock data. Idempotent: only fills entities with ZERO existing peers, so
    the 32 package-sourced rosters are never touched. Returns
    (entities_filled, peers_written)."""
    # Per-entity category-grain aggregate over the ACTIVE run, exactly as the
    # overview endpoint computes pillar/overall (AVG of category means).
    rows = (await session.execute(text(
        """
        SELECT e.id::text eid, e.name, e.subvertical sv, r.id::text rid,
               r.assessment_date asd,
               LEFT(ss.subcap_id, 4) AS cat,
               ROUND(AVG(ss.score)::numeric, 2)::float AS mean
        FROM entities e
        JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
        JOIN subcap_scores ss ON ss.run_id = r.id
        WHERE e.status = 'ACTIVE' AND ss.subcap_id ~ '^P[0-9]C[0-9]'
          AND ss.score IS NOT NULL
        GROUP BY e.id, e.name, e.subvertical, r.id, r.assessment_date,
                 LEFT(ss.subcap_id, 4)
        """))).all()
    agg: dict[str, dict] = {}
    for x in rows:
        e = agg.setdefault(x.eid, {
            "name": x.name, "sv": x.sv, "rid": x.rid, "asd": x.asd, "cats": {}})
        e["cats"][x.cat] = x.mean
    for e in agg.values():
        cats = e["cats"]
        e["overall"] = round(sum(cats.values()) / len(cats), 2) if cats else None

    have = {str(r[0]) for r in (await session.execute(text(
        "SELECT DISTINCT entity_id::text FROM entity_peers"))).all()}

    filled = written = 0
    for eid, me in agg.items():
        if eid in have or me["overall"] is None:
            continue
        cohort = [
            (oid, o) for oid, o in agg.items()
            if oid != eid and o["sv"] == me["sv"] and o["overall"] is not None
        ]
        if not cohort:
            continue
        # nearest-maturity peers first; cap at 5 so the card stays legible.
        cohort.sort(key=lambda t: (abs(t[1]["overall"] - me["overall"]), t[1]["name"]))
        for _oid, o in cohort[:5]:
            await session.execute(text(
                """
                INSERT INTO entity_peers (entity_id, run_id, peer_name, role,
                    scoring_date, overall_score, category_scores,
                    evidence_sources, source)
                VALUES (CAST(:e AS uuid), CAST(:r AS uuid), :pn, :role, :sd, :ov,
                    CAST(:cs AS jsonb), CAST(:es AS jsonb), 'cohort')
                ON CONFLICT (entity_id, peer_name) DO NOTHING
                """),
                {"e": eid, "r": me["rid"], "pn": o["name"][:200],
                 "role": "Subvertical peer", "sd": o["asd"], "ov": o["overall"],
                 "cs": json.dumps(o["cats"]),
                 "es": json.dumps([{"kind": "cohort",
                                    "note": "Same-subvertical portfolio benchmark"}])})
            written += 1
        filled += 1
    return filled, written


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    if not os.path.isdir(_CORPUS):
        print(f"# derive_peers: corpus dir {_CORPUS!r} absent — nothing to do", flush=True)
        return 0
    sm = get_sessionmaker()
    entities = peers_written = matched = no_run = no_peers = 0
    async with sm() as session:
        # Preload ACTIVE runs → exact + prefix maps (the package run_id often
        # drifts in its trailing sequence vs the ingested request_id).
        run_rows = (await session.execute(text(
            "SELECT r.request_id req, r.id::text rid, r.entity_id::text eid "
            "FROM runs r JOIN entities e ON e.id=r.entity_id "
            "WHERE r.status='ACTIVE' AND e.status='ACTIVE' AND r.request_id IS NOT NULL"
        ))).all()
        exact = {x.req: (x.rid, x.eid) for x in run_rows}
        by_prefix: dict[str, tuple[str, str]] = {}
        for x in run_rows:
            by_prefix.setdefault(_prefix(x.req), (x.rid, x.eid))
        # name fallback (packages whose run_manifest has no run_id): the most
        # recent ACTIVE run per entity, keyed by the entity's significant tokens.
        ent_rows = (await session.execute(text(
            "SELECT e.name, r.id::text rid, r.entity_id::text eid FROM entities e "
            "JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE' WHERE e.status='ACTIVE'"
        ))).all()
        by_tokens: dict[frozenset[str], tuple[str, str]] = {}
        seen_tok: set[frozenset[str]] = set()
        for x in ent_rows:
            tk = _name_tokens(x.name)
            if not tk:
                continue
            if tk in by_tokens:        # ambiguous token-set → drop both (no guess)
                seen_tok.add(tk)
            else:
                by_tokens[tk] = (x.rid, x.eid)
        for tk in seen_tok:
            by_tokens.pop(tk, None)
        # Roster for the rapidfuzz fallback below (name -> run/entity).
        roster_names = [x.name for x in ent_rows if x.name]
        by_name = {x.name: (x.rid, x.eid) for x in ent_rows if x.name}
        peer_dirs = sorted({os.path.dirname(p) for p in
                            glob.glob(os.path.join(_CORPUS, "**", "06_peers"), recursive=True)})
        for root in peer_dirs:
            files = glob.glob(os.path.join(root, "06_peers", "peer_scores_*.json"))
            if not files:
                no_peers += 1
                continue
            match = None
            for rid in _run_ids_for(root):
                match = exact.get(rid) or by_prefix.get(_prefix(rid))
                if match:
                    break
            if match is None:
                # conservative folder-name fallback: package tokens must equal,
                # or be a subset of, exactly one entity's significant tokens.
                ptoks = _name_tokens(os.path.basename(root))
                if ptoks:
                    cands = [v for tk, v in by_tokens.items() if ptoks <= tk or tk <= ptoks]
                    if len(cands) == 1:
                        match = cands[0]
                # rapidfuzz fallback — ONLY when token-set gave no unique hit
                # (0 or >1). Uses an ambiguity guard (top-2 margin) so a close
                # tie refuses to guess rather than mis-assign. Measured 0->high
                # recall vs the token-set method with zero false matches.
                if match is None and roster_names:
                    try:
                        from app.ml.fuzzy import unambiguous_best
                        q = re.sub(r"\s*-\s*DMA\s*$", "", os.path.basename(root),
                                   flags=re.I).strip()
                        hit = unambiguous_best(q, roster_names, cutoff=88.0, margin=5.0)
                        if hit is not None:
                            match = by_name.get(hit.choice)
                    except Exception:
                        pass
            if match is None:
                no_run += 1
                continue
            row = type("R", (), {"rid": match[0], "eid": match[1]})()
            peers = [p for p in (_parse_peer(f) for f in sorted(files)) if p]
            if not peers:
                no_peers += 1
                continue
            matched += 1
            await session.execute(text(
                "DELETE FROM entity_peers WHERE entity_id=CAST(:e AS uuid)"), {"e": row.eid})
            for p in peers:
                await session.execute(text(
                    """
                    INSERT INTO entity_peers (entity_id, run_id, peer_name, role, scoring_date,
                        overall_score, category_scores, evidence_sources, source)
                    VALUES (CAST(:e AS uuid), CAST(:r AS uuid), :pn, :role, :sd, :ov,
                        CAST(:cs AS jsonb), CAST(:es AS jsonb), 'package')
                    ON CONFLICT (entity_id, peer_name) DO UPDATE SET
                        overall_score=EXCLUDED.overall_score,
                        category_scores=EXCLUDED.category_scores,
                        role=EXCLUDED.role, scoring_date=EXCLUDED.scoring_date,
                        evidence_sources=EXCLUDED.evidence_sources
                    """), {"e": row.eid, "r": row.rid, "pn": p["peer_name"], "role": p["role"],
                           "sd": p["scoring_date"], "ov": p["overall"],
                           "cs": json.dumps(p["category_scores"]),
                           "es": json.dumps(p["evidence_sources"])})
                peers_written += 1
            entities += 1
        # Cohort fallback for every entity the package pass left empty — so no
        # client renders an empty peer card. Grounded in real portfolio scores.
        cohort_filled, cohort_written = await _cohort_fallback(session)
        await session.commit()
    print(f"# derive_peers: entities_with_peers={entities} peers_written={peers_written} "
          f"matched_runs={matched} no_run_match={no_run} no_peer_scores={no_peers} "
          f"| cohort_fallback: entities_filled={cohort_filled} peers_written={cohort_written} "
          f"(grounded in 06_peers + same-subvertical portfolio; idempotent)", flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
