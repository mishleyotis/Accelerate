"""Ground heatmap cells: link unlinked evidence to subcaps via NLP similarity.

Why this exists
---------------
Heatmap synthesis drawers render their "Source reports & evidence" list from
``evidence_index.linked_subcap_ids`` (the router unions these into subcap
cells). That column is populated at ingest ONLY from subcap tags carried in
the source package — and 27/94 clients arrived with rich evidence (avg ~92
rows) whose rows carried NO subcap tag, so every one of their heatmap cells
rendered evidence-empty (audit 2026-07-03: heatmap_evidence_clients 60/94).

This step is the plan's Part 6.3 "similarity roll-up for the rest": for each
run, it fits a lexical (TF-IDF cosine) index over the catalogue subcaps
(name + description) and attaches each still-unlinked, real-excerpt evidence
row to its closest subcap(s) above a conservative floor. Precision over
recall — a wrong link mis-grounds a cell, which is worse than an honest empty
one — so the floor is high, placeholder ("capability dimension N") subcaps are
excluded from the corpus, and only the top-2 hits are kept.

Idempotent + additive: only rows with an EMPTY ``linked_subcap_ids`` are
touched; explicitly-tagged rows are never overwritten. ``--dry-run`` reports
coverage without writing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.nlp import rerank, thresholds
from app.services.nlp.semantic import SemanticIndex, model_available
from app.services.nlp.similarity import LexicalIndex

# subcaps whose "name" is an un-named placeholder — matching evidence to them
# grounds nothing, so they stay out of the similarity corpus.
_PLACEHOLDER_NAME = re.compile(r"^\s*capability dimension\s+\d+\s*$", re.I)
_MIN_SCORE = 0.17          # lexical (cold-fallback) recall floor
_SEM_RECALL = 0.28         # bi-encoder recall floor (denser than TF-IDF)
_SUPPORT_FLOOR = 0.30      # cross-encoder fused-support floor to ATTACH a link
_TOP_K = 2
_REVIEW_QUEUE = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "benchmarks", "eval",
    "review_queue.jsonl"))


def _queue_review(entity: str, e_id: str, subcap_id: str,
                  cos: float, runner: float | None) -> None:
    reason = ("margin_lt_0.05" if runner is not None
              and (cos - runner) < thresholds.RUNNERUP_MARGIN
              and cos >= thresholds.CANDIDATE else "band_review")
    try:
        os.makedirs(os.path.dirname(_REVIEW_QUEUE), exist_ok=True)
        with open(_REVIEW_QUEUE, "a") as fh:
            fh.write(json.dumps({
                "entity": entity, "evidence_id": e_id, "subcap_id": subcap_id,
                "cos": round(cos, 4),
                "runner_up": round(runner, 4) if runner is not None else None,
                "reason": reason}) + "\n")
    except OSError:
        pass
_MIN_EXCERPT = 40


async def _amain() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report coverage; write nothing")
    ap.add_argument("--min-score", type=float, default=_MIN_SCORE)
    ap.add_argument("--ladder", action="store_true",
                    help="enable Tab-01 threshold-ladder routing on raw "
                         "bi-encoder cosines. OFF by default: the measured "
                         "cosine distribution routes ~72%% of true links to "
                         "the review band (eval_evidence_mapping), starving "
                         "evidence coverage; the CE support prune below "
                         "remains the shipping precision gate until the "
                         "calibrated ladder meets the <2%% misattribution "
                         "budget.")
    ap.add_argument("--legacy", action="store_true",
                    help="alias for the default (ladder off)")
    args = ap.parse_args()

    # Two-tier grounding (2026-07-09): the bi-encoder RECALLS candidate subcaps
    # semantically, then the cross-encoder VERIFIES each excerpt↔subcap pair
    # actually supports the link before it is attached — precision the bare
    # TF-IDF floor could not give (a word-overlap excerpt mis-grounds a cell).
    # When the models are cold this degrades EXACTLY to the prior lexical path
    # (LexicalIndex + the 0.17 floor), so a creds-less regen is unchanged.
    use_bi = model_available()
    use_ce = rerank.available()

    sm = get_sessionmaker()
    async with sm() as s:
        runs = (await s.execute(text(
            "SELECT DISTINCT ON (r.entity_id) r.id rid, r.ccg_catalog_version cat, "
            "       e.display_id did "
            "FROM runs r JOIN entities e ON e.id=r.entity_id "
            "WHERE e.status='ACTIVE' "
            "ORDER BY r.entity_id, r.created_at DESC"
        ))).all()

    # cache the fitted index + subcap text per catalogue version (all share v7.0)
    index_by_cat: dict = {}
    clients_linked = rows_linked = 0
    recall_floor = _SEM_RECALL if use_bi else args.min_score

    for run in runs:
        async with sm() as s:
            if run.cat not in index_by_cat:
                subs = (await s.execute(text(
                    "SELECT subcap_id, name, COALESCE(description,'') d "
                    "FROM ccg_subcaps WHERE version=:v"
                ), {"v": run.cat})).all()
                corpus = [(r.subcap_id, f"{r.name}. {r.d}") for r in subs
                          if r.name and not _PLACEHOLDER_NAME.match(r.name)]
                idx = SemanticIndex() if use_bi else LexicalIndex()
                idx.fit(corpus)
                index_by_cat[run.cat] = (idx, dict(corpus))
            idx, subcap_text = index_by_cat[run.cat]

            evs = (await s.execute(text(
                "SELECT e_id, excerpt FROM evidence_index "
                "WHERE run_id=:rid AND array_length(linked_subcap_ids,1) IS NULL "
                "AND excerpt IS NOT NULL AND excerpt <> '(no excerpt)' "
                "AND length(excerpt) > :ml"
            ), {"rid": run.rid, "ml": _MIN_EXCERPT})).all()

            updates: list[tuple[str, list[str]]] = []
            for e in evs:
                # recall wider when we can re-rank; the CE prunes false hits
                k = _TOP_K * 3 if use_ce else _TOP_K
                hits = idx.top_k(e.excerpt, k=k, min_score=recall_floor)
                if not hits:
                    continue
                if use_bi and args.ladder and not args.legacy:
                    # Tab-01 §2.1 ladder over the bi-encoder cosines: reject
                    # and review candidates never reach the attach path; the
                    # review band (incl. margin-forced) queues for
                    # adjudication. The CE support prune below is unchanged.
                    runner = hits[1][1] if len(hits) > 1 else None
                    survivors = []
                    for i, (sid, cos) in enumerate(hits):
                        verdict = thresholds.classify(
                            cos, runner_up=runner if i == 0 else None)
                        if verdict == "reject":
                            continue
                        if verdict == "review":
                            _queue_review(run.did, e.e_id, sid, cos, runner)
                            continue
                        survivors.append((sid, cos))
                    hits = survivors
                    if not hits:
                        continue
                if use_ce:
                    # cross-encoder support: keep only subcaps the excerpt truly
                    # supports (capability=subcap_text, evidence=excerpt), batched.
                    sups = rerank.support_scores(
                        e.excerpt,
                        [(subcap_text.get(sid, ""), cos) for sid, cos in hits])
                    scored = sorted(
                        ((sid, sups[i]) for i, (sid, _c) in enumerate(hits)
                         if sups[i] >= _SUPPORT_FLOOR),
                        key=lambda x: x[1], reverse=True)
                    keep = [sid for sid, _s in scored[:_TOP_K]]
                else:
                    keep = [sid for sid, _sc in hits[:_TOP_K]]
                if keep:
                    updates.append((e.e_id, keep))

            if updates:
                clients_linked += 1
                rows_linked += len(updates)
                if not args.dry_run:
                    for e_id, sids in updates:
                        await s.execute(text(
                            "UPDATE evidence_index SET linked_subcap_ids=:sids "
                            "WHERE run_id=:rid AND e_id=:eid "
                            "AND array_length(linked_subcap_ids,1) IS NULL"
                        ), {"sids": sids, "rid": run.rid, "eid": e_id})
                    await s.commit()

    mode = "DRY-RUN" if args.dry_run else "wrote"
    print(f"# link_evidence_subcaps [{mode}]: runs={len(runs)} "
          f"clients_newly_linked={clients_linked} rows_linked={rows_linked} "
          f"min_score={args.min_score}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_amain()))
