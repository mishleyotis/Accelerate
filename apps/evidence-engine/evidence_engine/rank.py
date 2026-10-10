"""Chunk ranking: BM25 first, dense + cross-encoder only when bundled.

WHY. Fusion says "consistently retrieved"; ranking says "actually about the
question", and it has to ABSTAIN rather than file a thin match (the
plugin's retrieval.rerank returns `below_floor` for the same reason —
AUD-0075's mapper had no abstain path). The card's `relevance` is this
score (CARD-CONTRACT.md §3) and the excerpt selector reads the top chunks.
Invariant 1 (no model call at request time) is kept the way DISCOVERY.md
§6 states it: the ONNX embedding / reranker are deterministic, local and
bundled in the image; nothing is downloaded, ever.

THE RULE.
  stage 1  sentence-window chunks (~3 sentences, exact offsets into
           Document.text) scored by rank_bm25.BM25Okapi against the
           question + facet text; tokeniser lower-case \\w+ minus a small
           stopword list; scores min-max normalised over the candidate set;
           a chunk under FLOOR (0.05) abstains into `below_floor`.
  stage 2  OPTIONAL: when settings.models_dir is set AND that directory
           exists, fastembed TextEmbedding (cosine to the question) and
           TextCrossEncoder (query, chunk) rerank the stage-1 survivors;
           final = 0.5 * bm25_norm + 0.5 * rerank_norm. Otherwise the stage
           is skipped and reported as rerank="bm25-only".
  ties     by lexical url_key, then chunk_start — never by input order.
"""
from __future__ import annotations

import os
import re

from rank_bm25 import BM25Okapi

from .config import settings
from .search import url_key
from .textnorm import sentences
from .types import Document

WINDOW = 3
FLOOR = 0.05
_STOP = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the "
    "this to was what when where which who with does do did their they there these "
    "those than then into onto over under about after before".split())
_TOKEN = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(str(text or "").lower()) if t not in _STOP]


def chunks_of(doc: Document, window: int = WINDOW) -> list[dict]:
    """Sentence windows with exact offsets: doc.text[start:end] == text."""
    spans = sentences(doc.text or "")
    out = []
    for i in range(0, len(spans), window):
        group = spans[i:i + window]
        start, end = group[0][0], group[-1][1]
        out.append({"chunk_start": start, "chunk_end": end, "text": doc.text[start:end]})
    return out


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [1.0 if hi > 0 else 0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def dense_available() -> tuple[bool, str]:
    """(usable, reason). Usable only when the models are bundled."""
    s = settings()
    if not s.models_dir:
        return False, "EE_MODELS_DIR not set"
    if not os.path.isdir(s.models_dir):
        return False, f"models dir {s.models_dir} does not exist"
    try:
        import fastembed  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"fastembed unavailable: {type(e).__name__}"
    return True, "bundled models present"


def _dense_scores(question: str, texts: list[str]) -> list[float] | None:
    """Cross-encoder scores (preferred) or cosine similarity, local files
    only; None when the models cannot be loaded without a download."""
    s = settings()
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        ce = TextCrossEncoder(model_name=s.rerank_model, cache_dir=s.models_dir, local_files_only=True)
        return [float(x) for x in ce.rerank(question, texts)]
    except Exception:  # noqa: BLE001 — fall through to the embedding
        pass
    try:
        import math
        from fastembed import TextEmbedding
        te = TextEmbedding(model_name=s.embed_model, cache_dir=s.models_dir, local_files_only=True)
        q = list(te.embed([question]))[0]
        out = []
        qn = math.sqrt(sum(float(x) * float(x) for x in q)) or 1.0
        for v in te.embed(texts):
            vn = math.sqrt(sum(float(x) * float(x) for x in v)) or 1.0
            out.append(sum(float(a) * float(b) for a, b in zip(q, v)) / (qn * vn))
        return out
    except Exception:  # noqa: BLE001
        return None


def rank_chunks(question: str, docs: list[Document], top_k: int = 20, *,
                facet_text: str = "", floor: float = FLOOR) -> dict:
    """-> {ranked: [{url_key, chunk_start, chunk_end, text, score, stages}],
    below_floor: [same shape], rerank: 'bm25-only' | 'dense+cross-encoder',
    rerank_reason: str, floor}."""
    cands = []
    for d in docs:
        key = url_key(d.url)
        for c in chunks_of(d):
            cands.append({"url_key": key, **c})
    if not cands:
        return {"ranked": [], "below_floor": [], "rerank": "bm25-only",
                "rerank_reason": "no chunks", "floor": floor}
    corpus = [tokenize(c["text"]) for c in cands]
    query = tokenize(" ".join(x for x in (question, facet_text) if x))
    raw = [0.0] * len(cands)
    if query and any(corpus):
        bm = BM25Okapi([t or ["<empty>"] for t in corpus])
        raw = [float(x) for x in bm.get_scores(query)]
    norm = _minmax(raw)
    for c, r, n in zip(cands, raw, norm):
        c["stages"] = {"bm25": round(r, 4), "bm25_norm": round(n, 4)}
        c["score"] = round(n, 4)

    def order(c):
        return (-c["score"], c["url_key"], c["chunk_start"])

    survivors = [c for c in cands if c["stages"]["bm25_norm"] >= floor and c["stages"]["bm25"] > 0]
    below = sorted([c for c in cands if c not in survivors], key=order)
    survivors.sort(key=order)
    survivors = survivors[:max(top_k, 1) * 3]      # the rerank candidate pool

    usable, reason = dense_available()
    mode = "bm25-only"
    if usable and survivors:
        dense = _dense_scores(question, [c["text"] for c in survivors])
        if dense is not None and len(dense) == len(survivors):
            dn = _minmax(dense)
            for c, dv, dnv in zip(survivors, dense, dn):
                c["stages"]["rerank"] = round(dv, 4)
                c["stages"]["rerank_norm"] = round(dnv, 4)
                c["score"] = round(0.5 * c["stages"]["bm25_norm"] + 0.5 * dnv, 4)
            mode = "dense+cross-encoder"
            survivors.sort(key=order)
        else:
            reason = "models present but not loadable offline; bm25 only"
    return {"ranked": survivors[:top_k], "below_floor": below, "rerank": mode,
            "rerank_reason": reason, "floor": floor}
