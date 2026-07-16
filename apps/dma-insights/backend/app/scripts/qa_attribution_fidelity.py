"""QA gate — the deploy pipeline OBSERVES the AI layer (2026-07-09).

The four existing qa-gates harnesses (render / adversarial / language /
self-healing) all read PERSISTED text: they prove a surface is non-empty and
consultant-grade, but none of them exercises the intelligence layer itself, so a
silently-cold cross-encoder (models not baked into the image) or a degraded
attribution pass would ship undetected. This harness closes that: it makes CI
verify the AI layer is (1) LIVE, (2) actually DISCRIMINATING, and (3) producing
FAITHFUL evidence↔capability attributions on the real corpus.

Three checks, each deploy-blocking:

  1. Tier liveness — the bi-encoder (MiniLM) and cross-encoder (stsb) tiers must
     load. Advisory by default; HARD when ``--require-ai`` is passed (qa-gates
     passes it, because the image bakes both models and NLP is HOT there — a
     cold tier means a broken bake, not an expected degrade).

  2. Calibration probe — a canonical STRONG (capability, evidence) pair must fuse
     high and a topical DECOY must fuse low, with a clear margin. This proves the
     cross-encoder is not just present but genuinely reasoning about support
     (a mis-baked / wrong-checkpoint model that returns a constant is caught
     here even though ``available()`` is True).

  3. Attribution fidelity — a sample of the PERSISTED evidence→subcap links
     (``evidence_index.linked_subcap_ids`` across ACTIVE runs, sampled
     representatively across clients) is re-scored with the exact
     retrieve-then-rerank fusion the derive path uses. The fraction whose fused
     support clears the floor is the fidelity, gated as a REGRESSION GUARD: the
     measured baseline is ~0.68 because the LINKS FILLED BY link_evidence_subcaps
     carry a CE support gate but the INGEST-TAGGED links never did (a board-bio
     row tagged to "Model Governance Framework" at ingest scores ~0). The gate
     therefore fails on a grounding COLLAPSE (regression), not on that
     pre-existing ingest-tag noise; the worst-scoring links are surfaced so the
     remediation — CE-verifying the ingest-tagged links, a scoped follow-up — is
     actionable. Override with ``--min-fidelity`` once that remediation lands.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.qa_attribution_fidelity
  python -m app.scripts.qa_attribution_fidelity --require-ai --output /tmp/attr.tsv
  python -m app.scripts.qa_attribution_fidelity --sample 500 --min-fidelity 0.85

Exit code: 0 when every enabled check passes; 1 otherwise. CI-gateable.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.nlp import rerank
from app.services.nlp.semantic import SemanticIndex, model_available

# The support floor mirrors the derive path's own attach gate
# (link_evidence_subcaps _SUPPORT_FLOOR / derive_insights _CITE_MIN_SUPPORT):
# a persisted link is "faithful" when it re-scores at or above this.
_SUPPORT_FLOOR = 0.30
# Regression guard, not an aspirational bar: the measured corpus baseline is
# ~0.68 (ingest-tagged links were never CE-gated — see module docstring). This
# floor sits below it so a grounding COLLAPSE fails the deploy while the
# pre-existing ingest noise does not. Raise it after the ingest-tag CE-verify
# remediation lands.
_MIN_FIDELITY = 0.60
_SAMPLE = 600                # links to re-score (CE budget-bounded)
_MIN_EXCERPT = 40

# Calibration probe — fixed pair the cross-encoder must separate. STRONG is a
# near-verbatim support; DECOY is topical-adjacent but unsupported.
_CAL_CAP = "Digital account opening and customer onboarding"
_CAL_STRONG = ("The bank launched a fully digital account-opening flow that "
               "opens a new checking account online in under five minutes.")
_CAL_DECOY = ("The board's compensation committee met quarterly to review "
              "executive pay and governance policy.")


async def _fetch_links(sample: int) -> list[tuple[str, str, str, str]]:
    """(display_id, subcap_id, subcap_text, excerpt) for persisted links on
    ACTIVE runs, catalogue-joined for the capability text.

    Sampled REPRESENTATIVELY across clients (round-robin by per-client rank) so
    the fidelity is a corpus number, not one governance-heavy client's — a plain
    ORDER BY display_id LIMIT would draw every row from the first entity."""
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (await s.execute(text("""
            WITH links AS (
              SELECT e.display_id AS did, sc.subcap_id AS sid,
                     sc.name || '. ' || COALESCE(sc.description, '') AS subcap_text,
                     ei.excerpt AS excerpt,
                     ROW_NUMBER() OVER (PARTITION BY e.display_id
                                        ORDER BY ei.e_id, sc.subcap_id) AS rn
                FROM evidence_index ei
                JOIN runs r ON r.id = ei.run_id
                JOIN entities e ON e.id = r.entity_id
                JOIN LATERAL unnest(ei.linked_subcap_ids) AS lsid(subcap_id) ON TRUE
                JOIN ccg_subcaps sc ON sc.subcap_id = lsid.subcap_id
                                   AND sc.version = r.ccg_catalog_version
               WHERE e.status = 'ACTIVE'
                 AND ei.excerpt IS NOT NULL AND ei.excerpt <> '(no excerpt)'
                 AND length(ei.excerpt) > :ml
                 AND sc.name IS NOT NULL
            )
            SELECT did, sid, subcap_text, excerpt
              FROM links
             ORDER BY rn, did          -- round-robin across clients, then by client
             LIMIT :lim
        """), {"ml": _MIN_EXCERPT, "lim": sample})).all()
    return [(r.did, r.sid, r.subcap_text, r.excerpt) for r in rows]


def _fused(cap: str, excerpt: str, idx: SemanticIndex) -> float:
    """The derive path's own signal: bi-encoder cosine → cross-encoder fused
    support (raw cosine when the CE tier is cold — zero regression)."""
    bi = idx.relevance(cap, excerpt)
    return rerank.support_score(cap, excerpt, bi)


async def main_async(args: argparse.Namespace) -> int:
    idx = SemanticIndex()
    bi_live, ce_live = model_available(), rerank.available()
    print(f"# AI tiers: bi-encoder(MiniLM)={bi_live}  cross-encoder(stsb)={ce_live}",
          flush=True)

    failures: list[str] = []

    # ── 1. tier liveness ────────────────────────────────────────────────
    if args.require_ai and not (bi_live and ce_live):
        failures.append(
            f"AI layer NOT live where it must be (bi={bi_live}, ce={ce_live}) — "
            "the image bake is broken; qa-gates runs NLP-HOT")

    # ── 2. calibration probe (only meaningful when the CE tier is live) ──
    if ce_live:
        strong = _fused(_CAL_CAP, _CAL_STRONG, idx)
        decoy = _fused(_CAL_CAP, _CAL_DECOY, idx)
        print(f"# calibration: strong={strong:.3f}  decoy={decoy:.3f}  "
              f"margin={strong - decoy:.3f}", flush=True)
        if not (strong >= 0.50 and decoy <= 0.40 and strong - decoy >= 0.20):
            failures.append(
                f"cross-encoder does not DISCRIMINATE (strong={strong:.3f} "
                f"decoy={decoy:.3f}) — model present but not reasoning about "
                "support; expected strong≥0.50, decoy≤0.40, margin≥0.20")
    else:
        print("# calibration SKIPPED — cross-encoder tier cold "
              "(fidelity below runs on the bi-encoder/lexical fallback)",
              flush=True)

    # ── 3. attribution fidelity on the real corpus ──────────────────────
    links = await _fetch_links(args.sample)
    print(f"# re-scoring {len(links)} persisted evidence→subcap links", flush=True)
    rows = ["display_id\tsubcap_id\tfused_support\tpass\texcerpt"]
    faithful = 0
    worst: list[tuple[float, str, str, str]] = []
    for did, sid, cap, excerpt in links:
        f = _fused(cap, excerpt, idx)
        ok = f >= _SUPPORT_FLOOR
        faithful += int(ok)
        rows.append(f"{did}\t{sid}\t{f:.3f}\t{'Y' if ok else 'N'}\t{excerpt[:120]}")
        if not ok:
            worst.append((f, did, sid, excerpt[:100]))

    fidelity = faithful / len(links) if links else 1.0
    print(f"\n# ATTRIBUTION FIDELITY: {faithful}/{len(links)} links clear the "
          f"support floor {_SUPPORT_FLOOR:.2f}  → fidelity={fidelity:.3f} "
          f"(threshold {args.min_fidelity:.2f})", flush=True)
    if worst:
        print(f"# {len(worst)} below-floor links (worst first) — mostly "
              f"ingest-tagged pairs never CE-verified; remediation: a CE-verify "
              f"pass over existing linked_subcap_ids:", flush=True)
        for f, did, sid, ex in sorted(worst)[:12]:
            print(f"  {f:.3f}  {did:26} {sid:14} {ex}", flush=True)
    if links and fidelity < args.min_fidelity:
        failures.append(
            f"attribution fidelity {fidelity:.3f} < {args.min_fidelity:.2f} — "
            "persisted evidence→capability grounding has drifted")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"# wrote matrix to {out}", flush=True)

    if failures:
        print("\n# ATTRIBUTION-FIDELITY GATE: FAIL", flush=True)
        for f in failures:
            print(f"  ✗ {f}", flush=True)
        return 1
    print("\n# ATTRIBUTION-FIDELITY GATE: PASS", flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--output", help="write the per-link TSV matrix to this path")
    p.add_argument("--sample", type=int, default=_SAMPLE,
                   help=f"links to re-score (default {_SAMPLE})")
    p.add_argument("--min-fidelity", type=float, default=_MIN_FIDELITY,
                   help=f"minimum pass fraction (default {_MIN_FIDELITY})")
    p.add_argument("--require-ai", action="store_true",
                   help="HARD-fail when the bi/cross-encoder tiers are not live "
                        "(qa-gates passes this — the image bakes both models)")
    args = p.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
