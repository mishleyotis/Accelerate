"""W2 — evidence→subcap matching: propose, record contentions, never assign.

Why this exists
---------------
Evidence reaches cells today only via ids stated in the workbook, and on a
real run that grounds 69 of 765 scored cells (9%). This pass raises coverage
HONESTLY: it PROPOSES links where the geometry is unambiguous, records a
CONTENTION (with candidates, scores and the reason) everywhere it is not,
and never silently assigns. Contentions land in ``parser_observations``
(kind ``link_contention``) for adjudication by the scheduled Claude session;
accepted proposals land in ``evidence_subcap_links`` with
``link_basis='embedding_proposal'`` so a proposed link is forever
distinguishable from a stated one.

Order of authority per evidence row
-----------------------------------
1. **Stated links win.** A row that already holds any link for this run is
   never touched (ingest wrote those with basis package / research_workbook /
   score_row).
2. **Exact id match next.** An excerpt that verbatim states a scored cell id
   (``P2C1.1.1``) links on that statement — basis ``stated_id_in_excerpt``,
   score None (nothing was computed; invariant 9 forbids a made-up number).
3. **Embeddings only for the rest**, and only ever as a proposal.

Thresholds — provenance and reasoning
-------------------------------------
Named constants below; the reference is the legacy linker
(``apps/dma-insights/backend/app/services/nlp/thresholds.py``, Training Spec
Tab-01 §2.1) — read for the approach, nothing imported:

* ``PROPOSAL_FLOOR = 0.62`` — the ladder's CANDIDATE line: the cosine below
  which the spec does not let a link be asserted as a candidate. The legacy
  shipping path attached down at a raw fused-support floor of 0.30, but only
  because a cross-encoder verified every excerpt↔subcap pair first; this
  worker ships the bi-encoder alone, so the floor stays at the ladder's
  candidate line. Precision over recall: a wrong link mis-grounds a cell,
  which is worse than an honest contention.
* ``REVIEW_FLOOR = 0.45`` — the ladder's reject line ("a link asserted below
  this threshold anywhere in the app is a QA-ML-03 failure"). Between the
  two floors the best candidate is plausible-but-unproven: a CONTENTION.
  Below it there is no plausible candidate and the row is skipped (recorded,
  not adjudicated — queueing geometric noise would drown the real cases).
* ``RUNNER_UP_MARGIN = 0.05`` — the ladder's hard-negative rule: a top-1
  whose margin over the runner-up is under 0.05 cosine is ambiguous
  REGARDLESS of absolute score, and routes to contention.
* ``TOP_K = 2`` — candidates carried into every contention/skip record, per
  the legacy's top-2 posture. Acceptance itself is top-1 only: propose-only
  tightens the legacy's attach-both-hits behaviour, because an excerpt that
  matches two cells is precisely what adjudication is for.

Determinism and invariants
--------------------------
Same inputs ⇒ same proposals: inputs are sorted, ties break on subcap_id,
no randomness, no clock in any decision (``occurred_at`` is bookkeeping on
the observation row, not an input). Runs as a batch job / CLI only — the
serving path never touches this module (invariant 1). Scores are computed
or None, never defaulted (invariant 9).

Encoder reuse
-------------
The encoder is the vector tier's own (``embed.minilm_encoder`` — 384-dim
MiniLM class, CPU, L2-normalised), injected so tests run without torch.
Persisted vectors in ``bundle_embeddings`` cannot be reused here: that table
only holds chunks for evidence that is already LINKED (``embed.collect_items``
joins ``evidence_subcap_links``), and catalogue subcap text is never embedded
at ingest — so both sides are encoded fresh, one batch, deterministic.

Invocation
----------
``python -m dma_worker.link_propose --run-id <uuid> [--dry-run] [--model-dir D]``
or, through the worker Job, ``LINK_PROPOSE_RUN_ID=<uuid>`` (see job_main).
NOT part of the scheduled scan: the scheduled session invokes it on demand.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

# ── Policy constants (provenance in the module docstring) ──────────────
PROPOSAL_FLOOR = 0.62    # legacy ladder CANDIDATE — floor to ACCEPT a proposal
REVIEW_FLOOR = 0.45      # legacy ladder REJECT line — floor to raise a contention
RUNNER_UP_MARGIN = 0.05  # legacy hard-negative rule — ambiguity margin
TOP_K = 2                # candidates recorded per contention / skip
MIN_EXCERPT_CHARS = 40   # legacy _MIN_EXCERPT; the schema's excerpts are 50–500

# Un-named placeholder subcaps ("capability dimension N") ground nothing —
# they stay out of the similarity corpus (legacy posture, kept verbatim).
PLACEHOLDER_NAME = re.compile(r"^\s*capability dimension\s+\d+\s*$", re.I)

# A scored-cell id stated verbatim in an excerpt: P1C1.1.1, P1C1.3.CU1, …
# The regex only nominates tokens; membership in the run's scored set decides.
SUBCAP_ID_RE = re.compile(r"\bP[1-4]C\d{1,2}(?:\.[A-Z0-9]{1,4}){1,3}\b")

BASIS_EMBEDDING = "embedding_proposal"
BASIS_STATED_ID = "stated_id_in_excerpt"
OBS_CONTENTION = "link_contention"
OBS_PASS = "link_proposal_pass"


@dataclass(frozen=True)
class Subcap:
    """One scored cell: id, canonical name, and the corpus text to match
    against (name plus whatever catalogue prose the loader found)."""
    subcap_id: str
    name: str | None
    text: str


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def propose(evidence_rows, subcaps, existing_links, encoder, *,
            floor: float = PROPOSAL_FLOOR, review_floor: float = REVIEW_FLOOR,
            margin: float = RUNNER_UP_MARGIN, top_k: int = TOP_K) -> dict:
    """Pure core: no IO, no clock, no randomness.

    evidence_rows   iterable of (e_id, excerpt-or-None)
    subcaps         iterable of Subcap (the run's scored cells)
    existing_links  iterable of (e_id, subcap_id) already linked FOR THIS RUN
    encoder         .name + .encode(list[str]) -> list of L2-normalised vectors
                    (the embed.py contract); called at most once, on the
                    sorted distinct texts that actually need vectors

    Returns {"accepted": [...], "contentions": [...], "skipped": [...],
    "params": {...}} — every list sorted by e_id, every entry explaining
    itself. Same inputs ⇒ same output, whatever order the inputs arrived in.
    """
    linked_e_ids = {e for e, _s in existing_links}
    id_set = {s.subcap_id for s in subcaps}
    corpus = [s for s in sorted(subcaps, key=lambda s: s.subcap_id)
              if s.name and not PLACEHOLDER_NAME.match(s.name)
              and (s.text or "").strip()]

    accepted: list[dict] = []
    contentions: list[dict] = []
    skipped: list[dict] = []
    pending: list[tuple[str, str]] = []

    for e_id, text in sorted(evidence_rows, key=lambda r: str(r[0])):
        if e_id in linked_e_ids:
            skipped.append({"e_id": e_id, "reason": "already_linked"})
            continue
        clean = (text or "").strip()
        if len(clean) < MIN_EXCERPT_CHARS:
            skipped.append({"e_id": e_id, "reason": "no_usable_text"})
            continue
        stated = sorted({m.group(0) for m in SUBCAP_ID_RE.finditer(clean)}
                        & id_set)
        if stated:
            # Exact id match first: the excerpt itself names the cell(s).
            # Nothing was computed, so the score is None — never a sentinel.
            for sid in stated:
                accepted.append({"e_id": e_id, "subcap_id": sid,
                                 "score": None, "basis": BASIS_STATED_ID})
            continue
        pending.append((e_id, clean))

    if pending and corpus:
        distinct = sorted({t for _, t in pending} | {s.text for s in corpus})
        vectors = dict(zip(distinct, encoder.encode(distinct)))
        for e_id, text in pending:
            ev = vectors[text]
            hits = sorted(((s.subcap_id, _dot(ev, vectors[s.text]))
                           for s in corpus),
                          key=lambda t: (-t[1], t[0]))[:top_k]
            best_sid, best = hits[0]
            runner = hits[1][1] if len(hits) > 1 else None
            cands = [{"subcap_id": sid, "score": round(c, 4)}
                     for sid, c in hits]
            if best < review_floor:
                skipped.append({"e_id": e_id,
                                "reason": "no_plausible_candidate",
                                "candidates": cands})
            elif best < floor:
                contentions.append({"e_id": e_id,
                                    "reason": "below_proposal_floor",
                                    "candidates": cands})
            elif runner is not None and (best - runner) < margin:
                contentions.append({"e_id": e_id,
                                    "reason": "runner_up_within_margin",
                                    "candidates": cands})
            else:
                accepted.append({"e_id": e_id, "subcap_id": best_sid,
                                 "score": round(best, 4),
                                 "basis": BASIS_EMBEDDING})
    elif pending:
        # Every matchable subcap was a placeholder (or nameless): recorded,
        # never guessed.
        for e_id, _ in pending:
            skipped.append({"e_id": e_id, "reason": "no_matchable_subcaps"})

    return {
        "accepted": sorted(accepted, key=lambda a: (a["e_id"], a["subcap_id"])),
        "contentions": sorted(contentions, key=lambda c: c["e_id"]),
        "skipped": sorted(skipped, key=lambda s: s["e_id"]),
        "params": {"floor": floor, "review_floor": review_floor,
                   "margin": margin, "top_k": top_k,
                   "min_excerpt_chars": MIN_EXCERPT_CHARS,
                   "encoder": getattr(encoder, "name", None),
                   "corpus_cells": len(corpus),
                   "placeholder_cells_excluded": len(subcaps) - len(corpus)},
    }


# ── DB half ─────────────────────────────────────────────────────────────
def load_inputs(conn, run_id):
    """Assemble the pure core's inputs from the ingested + catalogue tiers.

    The corpus is the run's SCORED cells (subcap_scores ⋈ ccg_subcaps at the
    run's pinned version): a proposal's whole point is grounding a cell this
    run scored. Corpus text = canonical name + category display name + the
    M-band maturity narratives where the catalogue carries them — the nearest
    analogue of the legacy's "name + description".

    Evidence is the run's ENTITY's rows (evidence_index has no run column;
    reference_date is pinned per run but identity is per entity), minus
    identity-failed rows (identity_ok = FALSE is excluded from coverage
    everywhere else, so it must not ground cells here either).

    A run with no pinned catalogue version refuses loudly — matching against
    a guessed version would be a silent assignment of a different kind.
    """
    cur = conn.cursor()
    cur.execute("SELECT entity_id, ccg_catalog_version FROM runs WHERE id = %s",
                (run_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"run {run_id} not found")
    entity_id, version = row
    if version is None:
        raise ValueError(
            f"run {run_id} has no pinned catalogue version; refusing to match "
            "against a guessed one (no silent assignment)")

    cur.execute(
        """SELECT s.subcap_id, s.name,
                  COALESCE(cat.name, ''),
                  COALESCE((SELECT string_agg(d.narrative, ' ' ORDER BY d.band)
                              FROM ccg_maturity_descriptors d
                             WHERE d.version = s.version
                               AND d.subcap_id = s.subcap_id
                               AND d.narrative IS NOT NULL), '')
             FROM subcap_scores sc
             JOIN ccg_subcaps s ON s.subcap_id = sc.subcap_id
                               AND s.version = %s
             LEFT JOIN ccg_categories cat ON cat.version = s.version
                                         AND cat.category_id = s.category_id
            WHERE sc.run_id = %s
            ORDER BY s.subcap_id""",
        (version, run_id))
    subcaps = [Subcap(sid, name,
                      ". ".join(p for p in (name, cat_name, desc) if p))
               for sid, name, cat_name, desc in cur.fetchall()]

    cur.execute(
        """SELECT e_id, excerpt FROM evidence_index
            WHERE entity_id = %s
              AND identity_ok IS DISTINCT FROM FALSE
            ORDER BY e_id""",
        (entity_id,))
    evidence = [(e, x) for e, x in cur.fetchall()]

    cur.execute("SELECT e_id, subcap_id FROM evidence_subcap_links WHERE run_id = %s",
                (run_id,))
    links = {(e, s) for e, s in cur.fetchall()}
    return evidence, subcaps, links


def persist_result(conn, run_id, result, *, dry_run: bool = False) -> dict:
    """Write one pass's outcome, or (dry_run) write nothing at all.

    Accepted → evidence_subcap_links with the proposal's basis (ON CONFLICT
    DO NOTHING — a stated link is never overwritten). Contentions → one
    parser_observations row each (kind ``link_contention``). One summary row
    (kind ``link_proposal_pass``) carries the params, the counts and every
    accepted link WITH its score — the audit trail invariant: basis, score
    and run are all recorded. Idempotent the way embed_run is: this pass's
    prior observation rows are replaced wholesale, and re-running cannot
    duplicate a link. linked_evidence_count is refreshed from the links
    table (recomputed, never incremented — counts are computed, not stored).

    dry_run touches nothing — the connection is not used (callers may pass
    conn=None to prove it).
    """
    stats = {"dry_run": dry_run, "links_written": 0,
             "accepted": len(result["accepted"]),
             "contentions": len(result["contentions"]),
             "skipped": len(result["skipped"])}
    if dry_run:
        return stats

    cur = conn.cursor()
    cur.execute(
        "DELETE FROM parser_observations WHERE run_id = %s AND kind IN (%s, %s)",
        (run_id, OBS_CONTENTION, OBS_PASS))
    for a in result["accepted"]:
        cur.execute(
            """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (a["e_id"], a["subcap_id"], run_id, a["basis"]))
        stats["links_written"] += cur.rowcount or 0
    for c in result["contentions"]:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,%s,%s, now())""",
            (run_id, OBS_CONTENTION, json.dumps(c)))
    skip_reasons: dict[str, int] = {}
    for s in result["skipped"]:
        skip_reasons[s["reason"]] = skip_reasons.get(s["reason"], 0) + 1
    cur.execute(
        """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
           VALUES (%s,%s,%s, now())""",
        (run_id, OBS_PASS, json.dumps({
            "params": result["params"],
            "counts": {"accepted": len(result["accepted"]),
                       "links_written": stats["links_written"],
                       "contentions": len(result["contentions"]),
                       "skipped": len(result["skipped"])},
            "skip_reasons": skip_reasons,
            "accepted": result["accepted"]})))
    if stats["links_written"]:
        # The linker count — recomputed from the links table for the whole
        # run, exactly as ingest does it.
        cur.execute(
            """UPDATE subcap_scores sc
                  SET linked_evidence_count =
                        (SELECT count(*) FROM evidence_subcap_links l
                          WHERE l.run_id = sc.run_id AND l.subcap_id = sc.subcap_id)
                WHERE sc.run_id = %s""",
            (run_id,))
    conn.commit()
    return stats


def _coverage(cur, run_id) -> tuple[set, int]:
    """(cells with any linked evidence, scored cells) — recomputed from the
    links table, never read off the stored counter."""
    cur.execute(
        """SELECT sc.subcap_id, count(l.e_id)
             FROM subcap_scores sc
             LEFT JOIN evidence_subcap_links l ON l.run_id = sc.run_id
                                              AND l.subcap_id = sc.subcap_id
            WHERE sc.run_id = %s
            GROUP BY sc.subcap_id""",
        (run_id,))
    rows = cur.fetchall()
    return {sid for sid, n in rows if n}, len(rows)


def run_for_run(conn, run_id, encoder, *, dry_run: bool = False) -> dict:
    """Load → propose → persist for one run; print one auditable summary."""
    evidence, subcaps, links = load_inputs(conn, run_id)
    result = propose(evidence, subcaps, links, encoder)
    covered, total = _coverage(conn.cursor(), run_id)
    stats = persist_result(conn, run_id, result, dry_run=dry_run)
    would_cover = covered | {a["subcap_id"] for a in result["accepted"]}
    exact = sum(1 for a in result["accepted"] if a["basis"] == BASIS_STATED_ID)
    print(f"link_propose [{'DRY-RUN' if dry_run else 'wrote'}]: run={run_id} "
          f"evidence={len(evidence)} accepted={len(result['accepted'])} "
          f"(exact={exact} embedding={len(result['accepted']) - exact}) "
          f"contentions={len(result['contentions'])} "
          f"skipped={len(result['skipped'])} "
          f"coverage {len(covered)}/{total} -> {len(would_cover)}/{total}",
          flush=True)
    return {"result": result, "stats": stats}


def _encoder(model_dir: str | None):
    from dma_worker.embed import minilm_encoder
    return minilm_encoder(model_dir)


def _connect():
    """Mirror of job_main._connect, duplicated so the CLI never imports the
    scan flow's Drive dependencies."""
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        host = os.environ["LOCAL_DATABASE_URL"].split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(
            user="dmai-worker@digital-maturity-assessor.iam",
            password="local", host=host, port=5432, database="dma_insights")
    from google.cloud.sql.connector import Connector
    return Connector().connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


def run_from_env(conn) -> int:
    """The job_main hook: LINK_PROPOSE_RUN_ID (+ LINK_PROPOSE_DRY_RUN=1)."""
    run_id = os.environ["LINK_PROPOSE_RUN_ID"].strip()
    dry = bool(os.environ.get("LINK_PROPOSE_DRY_RUN"))
    try:
        encoder = _encoder(os.environ.get("EMBED_MODEL_DIR"))
    except ImportError as exc:
        print(f"link_propose: encoder unavailable ({exc!r}); "
              "the worker image bundles the model at EMBED_MODEL_DIR")
        return 2
    try:
        run_for_run(conn, run_id, encoder, dry_run=dry)
        return 0
    except Exception as exc:  # noqa: BLE001 — surfaced, never half-written
        conn.rollback()
        print(f"link_propose FAILED (nothing written): {exc!r}")
        return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m dma_worker.link_propose",
        description="Propose evidence→subcap links for one run; record "
                    "contentions; never silently assign.")
    ap.add_argument("--run-id", required=True, help="runs.id (uuid)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen; write nothing")
    ap.add_argument("--model-dir", default=os.environ.get("EMBED_MODEL_DIR"),
                    help="bundled MiniLM directory (default: $EMBED_MODEL_DIR)")
    args = ap.parse_args(argv)

    try:
        encoder = _encoder(args.model_dir)
    except ImportError as exc:
        print(f"link_propose: encoder unavailable ({exc!r}); install the "
              "worker's model dependencies or run inside the worker image")
        return 2

    conn = _connect()
    try:
        run_for_run(conn, args.run_id, encoder, dry_run=args.dry_run)
        return 0
    except Exception as exc:  # noqa: BLE001 — surfaced, never half-written
        conn.rollback()
        print(f"link_propose FAILED (nothing written): {exc!r}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
