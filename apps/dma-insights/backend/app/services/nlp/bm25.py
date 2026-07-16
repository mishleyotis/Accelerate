"""Okapi BM25 index — the exact-term recall rung the bi-encoder lacks.

MiniLM embeddings are excellent at paraphrase but systematically under-
weight rare exact tokens: a query for "nCino onboarding" ranks a fluent
sentence about "digital account opening" above the one excerpt that
actually names nCino. BM25 is the complementary signal — pure term
statistics, IDF-dominated, zero model weight — so the hybrid recall
(cosine + BM25 union, cross-encoder as judge) catches both paraphrase and
exact-name material.

Pure python, no dependencies, framework-free; fits in O(corpus) and
queries in O(query terms x postings). Scores are normalized to [0,1]
by the top hit so callers can floor/fuse them like cosines.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z][\w&'./-]{1,}|\d[\d,.]*")
_K1 = 1.5
_B = 0.75


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


class BM25Index:
    """Okapi BM25 over an id→text corpus."""

    def __init__(self) -> None:
        self._ids: list[Any] = []
        self._tf: list[Counter] = []
        self._len: list[int] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0

    def fit(self, docs: Sequence[tuple[Any, str]]) -> None:
        self._ids = [d for d, _ in docs]
        self._tf, self._len = [], []
        self._df = Counter()
        for _, text in docs:
            toks = _tokens(text)
            tf = Counter(toks)
            self._tf.append(tf)
            self._len.append(len(toks))
            for term in tf:
                self._df[term] += 1
        self._avg_len = (sum(self._len) / len(self._len)) if self._len else 0.0

    def top_k(self, query: str, k: int, min_score: float = 0.0) -> list[tuple[Any, float]]:
        if not self._ids or not query or k <= 0:
            return []
        n = len(self._ids)
        q_terms = set(_tokens(query))
        scores = [0.0] * n
        for term in q_terms:
            df = self._df.get(term)
            if not df:
                continue
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self._tf):
                f = tf.get(term)
                if not f:
                    continue
                denom = f + _K1 * (1.0 - _B + _B * self._len[i] / (self._avg_len or 1.0))
                scores[i] += idf * (f * (_K1 + 1.0)) / denom
        best = max(scores)
        if best <= 0.0:
            return []
        ranked = sorted(range(n), key=lambda i: (-scores[i], i))[:k]
        return [(self._ids[i], round(scores[i] / best, 4))
                for i in ranked if scores[i] / best >= min_score and scores[i] > 0.0]
