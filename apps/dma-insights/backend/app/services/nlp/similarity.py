"""Lemma-normalized TF-IDF linker — the offline twin of the Vertex linker.

Why: evidence↔claim linking, insight affects[] classification, timeline
dedup and retrieval fallback all need "which docs is this text closest
to?" WITHOUT a network call — the derive chain must produce a full pack
on a cold, credential-less regen. :class:`LexicalIndex` exposes the same
fit/top_k interface as the Vertex-embedding linker so call sites swap
tiers freely; scoring is pure scikit-learn TF-IDF with a spaCy-lemma
analyzer (regex tokens when the model is degraded), l2-normalized so
the dot product IS cosine similarity.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z][\w'-]+|\d[\d,.]*")


def _nlp() -> Any:  # deferred — avoids circular import at package init
    from app.services.nlp import get_nlp

    return get_nlp()


def _lemma_tokens(text: str) -> list[str]:
    """Analyzer: spaCy lemmas (stop/punct-filtered) or regex tokens."""
    if not text:
        return []
    nlp = _nlp()
    if nlp is None:
        return [t.lower() for t in _TOKEN_RE.findall(text)]
    doc = nlp(text)
    return [
        t.lemma_.lower()
        for t in doc
        if not (t.is_stop or t.is_punct or t.is_space)
    ]


def _build_matrix(texts: list[str]) -> tuple[Any, Any] | None:
    """(vectorizer, l2-normalized doc matrix) or None when unusable.

    Returns None — degrading to "no similarity" — in BOTH failure modes:
      * ImportError: scikit-learn is absent (a core install without the `nlp`
        extra, i.e. the shipped image). The similarity tier is optional; its
        callers (``fit``/``top_k``/``near_duplicates``) already treat a None
        matrix as "no matches", so degrading here keeps the NLP layer's "never
        raises" contract true instead of hard-failing derive_context /
        link_evidence_subcaps / derive_insights / ingest (audit 2026-07-03).
      * ValueError: empty vocabulary (all-stopword/empty corpus).
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(analyzer=_lemma_tokens, norm="l2")
        matrix = vectorizer.fit_transform(texts)
    except (ImportError, ValueError):
        return None
    return vectorizer, matrix


class LexicalIndex:
    """Cosine top-k over an id→text corpus. Same interface as the Vertex tier."""

    def __init__(self) -> None:
        self._ids: list[Any] = []
        self._vectorizer: Any = None
        self._matrix: Any = None

    def fit(self, docs: Sequence[tuple[Any, str]]) -> None:
        """Index ``[(id, text), ...]``. Refitting replaces the corpus."""
        self._ids = [doc_id for doc_id, _text in docs]
        self._vectorizer = None
        self._matrix = None
        texts = [text or "" for _doc_id, text in docs]
        if not texts:
            return
        built = _build_matrix(texts)
        if built is not None:
            self._vectorizer, self._matrix = built

    def top_k(self, query: str, k: int, min_score: float = 0.08) -> list[tuple[Any, float]]:
        """The ``k`` closest docs to ``query`` → ``[(id, score), ...]`` desc.

        Scores below ``min_score`` are dropped — an 0.08 floor keeps
        stopword-only overlap from fabricating links.
        """
        if self._matrix is None or not query or k <= 0:
            return []
        vec = self._vectorizer.transform([query])
        scores = (self._matrix @ vec.T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        return [
            (self._ids[i], float(scores[i]))
            for i in order
            if scores[i] >= min_score
        ]


def near_duplicates(
    items: Sequence[Any],
    key: Callable[[Any], str] | None = None,
    threshold: float = 0.85,
) -> list[tuple[int, int, float]]:
    """Index pairs of near-duplicate items → ``[(i, j, score), ...]``, i < j.

    Used for cross-source dedup (the timeline audit counted 66 duplicate
    events). ``key`` extracts the comparable text from each item
    (default ``str``); pairs at or above ``threshold`` cosine are
    returned, strongest first.
    """
    if len(items) < 2:
        return []
    extract = key or str
    texts = [extract(item) or "" for item in items]
    built = _build_matrix(texts)
    if built is None:
        return []
    _vectorizer, matrix = built
    sims = (matrix @ matrix.T).toarray()
    pairs: list[tuple[int, int, float]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            score = float(sims[i, j])
            if score >= threshold:
                pairs.append((i, j, score))
    pairs.sort(key=lambda p: -p[2])
    return pairs
