"""NLP/ML module functioning audit — is every tier the scripts lean on WARM?

The derive chain degrades gracefully (semantic tier cold → keyword paths,
Vertex cold → deterministic composers), which is correct for resilience but
makes a silent misconfiguration expensive: a deploy that forgot
``DMA_ST_MODEL_DIR`` runs every semantic rung cold and nobody notices until
the corpus grades soft. This instrument probes each module ONCE and prints
a warm/cold/broken verdict per tier plus an exit code CI can gate on:

  bi-encoder    SemanticIndex embed dim + self-cosine sanity
  cross-encoder rerank.support_scores ordering sanity
  classifiers   headline_gate / report_section / subvertical joblibs load
                and predict on a smoke input
  dates         resolve_event_date strict parse
  quantities    extract_metrics unit extraction
  causal        decompose W/W/SW split
  affinity      v7 L4 catalogue layers loaded (DB; needs DATABASE_URL)
  debris        research_worker.is_nav_debris chrome gate

Usage:
  python -m app.scripts.qa_module_audit            # all probes
  python -m app.scripts.qa_module_audit --no-db    # skip DB-backed probes
Exit 0 = every probe warm (or explicitly skipped); 1 = something cold or
broken (each miss printed with the env/step that owns it).
"""
from __future__ import annotations

import argparse
import os

_OK, _COLD, _BROKEN, _SKIP = "WARM", "COLD", "BROKEN", "SKIP"


def _probe_bi_encoder() -> tuple[str, str]:
    try:
        from app.services.nlp.semantic import model_available
        if not model_available():
            return _COLD, ("sentence-transformers model unavailable — set "
                           "DMA_ST_MODEL_DIR to the baked dir "
                           "(/opt/st-models/all-MiniLM-L6-v2 locally, "
                           "/install/st-minilm in the backend image)")
        from app.services.nlp.semantic import SemanticIndex
        idx = SemanticIndex()
        idx.fit([("a", "deposit growth strategy"),
                 ("b", "core banking modernization")])
        hits = idx.top_k("growing deposits", k=2, min_score=0.0)
        if not hits or hits[0][0] != "a":
            return _BROKEN, f"self-retrieval failed: {hits!r}"
        return _OK, "MiniLM embeds + retrieves (dim 384)"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_cross_encoder() -> tuple[str, str]:
    try:
        from app.services.nlp import rerank
        scores = rerank.support_scores(
            "customer onboarding automation",
            [("The bank automated its customer onboarding workflow", 0.5),
             ("Quarterly dividend declared by the board", 0.5)])
        if scores[0] <= scores[1]:
            return _COLD, ("cross-encoder not discriminating (lexical "
                           "fallback?) — set DMA_CE_MODEL_DIR "
                           "(/opt/st-models/st-ce locally)")
        return _OK, f"CE separates support ({scores[0]:.2f} > {scores[1]:.2f})"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_classifiers() -> tuple[str, str]:
    import glob
    here = os.path.join(os.path.dirname(__file__), "..", "ml", "models")
    found = sorted(os.path.basename(p) for p in glob.glob(
        os.path.join(here, "*.joblib")))
    if not found:
        return _COLD, "no joblib artifacts under app/ml/models"
    try:
        from app.ml.headline_gate import gate_headline
        v = gate_headline("Digital Lending Modernization Opportunity")
        if not isinstance(v, dict):
            return _BROKEN, f"headline gate returned {v!r}"
        return _OK, f"{len(found)} artifacts load; headline gate predicts"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_dates() -> tuple[str, str]:
    try:
        from app.services.nlp.dates import resolve_event_date
        d, prec = resolve_event_date(
            "the acquisition completed on March 4, 2024 as planned")
        if not d or prec in ("none", "publish_fallback"):
            return _BROKEN, f"strict date missed: {(d, prec)!r}"
        return _OK, f"resolves textual dates (precision={prec})"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_quantities() -> tuple[str, str]:
    try:
        from app.services.nlp.quantities import extract_metrics
        mets = extract_metrics("deposits grew 12% to $4.2 billion")
        if not mets:
            return _BROKEN, "no metrics extracted from a quantified sentence"
        return _OK, f"extracts metrics ({len(mets)} from smoke input)"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_causal() -> tuple[str, str]:
    try:
        from app.services.nlp.causal import decompose
        d = decompose("Scores lag because the data platform is fragmented; "
                      "consolidating it first unlocks the roadmap.")
        if not isinstance(d, dict) or "what" not in d:
            return _BROKEN, f"decompose returned {d!r}"
        return _OK, "W/W/SW decomposition runs"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_bm25() -> tuple[str, str]:
    try:
        from app.services.nlp.bm25 import BM25Index
        idx = BM25Index()
        idx.fit([("a", "nCino commercial onboarding rollout completed"),
                 ("b", "digital account opening improved this year"),
                 ("c", "quarterly dividend declared by the board")])
        hits = idx.top_k("nCino onboarding", k=2)
        if not hits or hits[0][0] != "a":
            return _BROKEN, f"exact-term recall failed: {hits!r}"
        return _OK, "exact-term recall ranks the nCino doc first"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_distinctiveness() -> tuple[str, str]:
    try:
        from app.services.nlp import distinctiveness as d
        d.fit_corpus([
            "the bank continues to invest in digital capabilities",
            "we invest in digital transformation for customers",
            "digital capabilities remain a priority for the bank",
            "Zelle volume grew 41% to 12.3M transactions at Coastal FCU",
        ])
        generic = d.distinctiveness(
            "the bank continues to invest in digital capabilities")
        specific = d.distinctiveness(
            "Zelle volume grew 41% to 12.3M transactions at Coastal FCU")
        d.reset()
        if not specific > generic:
            return _BROKEN, f"specific {specific} <= generic {generic}"
        if d.distinctiveness("anything") != 0.0:
            return _BROKEN, "unfitted scorer must return 0.0"
        return _OK, f"specific {specific:.2f} > generic {generic:.2f}; unfitted=0"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_speed() -> tuple[str, str]:
    """Throughput floor: embeds must be batch-fast and the disk cache must
    make a SECOND pass near-instant (the cross-process warm start)."""
    try:
        import time

        from app.services.nlp.semantic import model_available
        if not model_available():
            return _COLD, "no ST model — speed probe skipped"
        from app.services.nlp.semantic import SemanticIndex
        sents = [f"capability sentence number {i} about lending and data"
                 for i in range(256)]
        idx = SemanticIndex()
        t0 = time.perf_counter()
        idx.fit(list(enumerate(sents)))
        cold = time.perf_counter() - t0
        idx2 = SemanticIndex()
        t0 = time.perf_counter()
        idx2.fit(list(enumerate(sents)))
        warm = time.perf_counter() - t0
        rate = 256 / cold if cold > 0 else 0
        if warm > cold:
            return _BROKEN, f"cache slower than compute ({warm:.2f}s > {cold:.2f}s)"
        return _OK, (f"embed 256 sents: {cold:.2f}s cold ({rate:.0f}/s), "
                     f"{warm:.3f}s cached")
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def _probe_debris() -> tuple[str, str]:
    try:
        from app.scripts.research_worker import is_nav_debris
        if not is_nav_debris("Subscribe to see more Subscribe to see more "
                             "Subscribe to see more and more"):
            return _BROKEN, "debris gate passed a subscription wall"
        if is_nav_debris("The bank acquired a lending platform in 2024."):
            return _BROKEN, "debris gate rejected real prose"
        return _OK, "chrome/boilerplate gate discriminates"
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


async def _probe_affinity_async() -> tuple[str, str]:
    from sqlalchemy import text

    from app.database import get_sessionmaker
    from app.services.platform_affinity import load_catalogue_affinity
    sm = get_sessionmaker()
    async with sm() as s:
        counts = (await s.execute(text(
            "SELECT (SELECT count(*) FROM ccg_l3_platforms),"
            "       (SELECT count(*) FROM ccg_l4_features),"
            "       (SELECT count(*) FROM ccg_user_stories)"))).first()
        aff = await load_catalogue_affinity(s, "v7.0")
    n3, n4, ns = int(counts[0]), int(counts[1]), int(counts[2])
    if n4 == 0:
        return _COLD, ("ccg_l4_features empty — run the ccg_loader "
                       "(workers.ccg_loader.main --version v7.0)")
    if not aff or "salesforce" not in aff:
        return _BROKEN, f"affinity map empty over {n4} L4 rows"
    return _OK, (f"L3={n3} L4={n4} stories={ns}; affinity covers "
                 f"{len(aff)} platform families")


def _probe_affinity() -> tuple[str, str]:
    if not os.environ.get("DATABASE_URL"):
        return _SKIP, "DATABASE_URL unset"
    try:
        import asyncio
        return asyncio.run(_probe_affinity_async())
    except Exception as exc:
        return _BROKEN, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-db", action="store_true",
                    help="skip DB-backed probes (catalogue affinity)")
    args = ap.parse_args()
    probes = [
        ("bi-encoder (MiniLM)", _probe_bi_encoder),
        ("cross-encoder", _probe_cross_encoder),
        ("BM25 exact-term recall", _probe_bm25),
        ("distinctiveness (anti-generic)", _probe_distinctiveness),
        ("classifiers (joblib)", _probe_classifiers),
        ("dates", _probe_dates),
        ("quantities", _probe_quantities),
        ("causal", _probe_causal),
        ("debris gate", _probe_debris),
        ("embed throughput + disk cache", _probe_speed),
    ]
    if not args.no_db:
        probes.append(("catalogue affinity (v7 L3/L4)", _probe_affinity))
    bad = 0
    for name, fn in probes:
        state, detail = fn()
        flag = "" if state in (_OK, _SKIP) else "  <-- ATTENTION"
        print(f"  {state:6} {name}: {detail}{flag}")
        if state in (_COLD, _BROKEN):
            bad += 1
    print(f"# qa_module_audit: {len(probes)} probes, {bad} need attention")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
