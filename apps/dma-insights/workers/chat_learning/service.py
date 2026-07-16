"""Pure-logic helpers for the chat_learning rollup worker.

State transitions:
  sample_count < 1 in a cluster
    → cluster is dropped from the rollup (effectiveness undefined)
  all feedback in a cluster has rating=0 (neutral)
    → effectiveness = 0.5 (neutral); the next-prompt selector treats
      this as "no signal"
  preferred_evidence_ids appear only in rating>=0 messages
    → boosted in the rollup so the /answer service can re-rank
      retrieval toward them on similar future questions
  k > n (more requested clusters than samples)
    → service caps k at n; this is the worker's contract with main.py

Pure-logic only. Live DB IO is in main.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FeedbackSample:
    """One user-question + assistant-response + feedback row, joined
    upstream by the worker's SQL."""
    message_id: str
    surface: str
    embedding: list[float]
    rating: int               # -1, 0, +1
    cited_evidence_ids: list[str] = field(default_factory=list)
    validators_passed: bool = True
    created_at: datetime | None = None


@dataclass
class ClusterSignal:
    surface: str
    prompt_centroid: list[float]
    exemplar_question: str
    retrieval_quality: float
    response_quality: float
    effectiveness: float
    sample_count: int
    preferred_evidence_ids: list[str]


def _l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=False)))


def _mean(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def kmeans(
    data: list[list[float]], k: int, *, max_iter: int = 40, seed: int = 11,
) -> tuple[list[int], list[list[float]]]:
    """Deterministic mini KMeans. Mirrors workers.peer_patterns.service.
    Inlined here so the chat_learning worker has zero cross-package
    coupling (it must keep running even if peer_patterns is paused).
    """
    n = len(data)
    if n == 0:
        return [], []
    k = max(1, min(k, n))
    stride = max(1, n // k)
    centroids = [list(data[(i * stride) % n]) for i in range(k)]
    assignments = [0] * n
    for _ in range(max_iter):
        changed = False
        for i, row in enumerate(data):
            best = 0
            best_d = _l2(row, centroids[0])
            for c in range(1, k):
                d = _l2(row, centroids[c])
                if d < best_d:
                    best_d = d
                    best = c
            if assignments[i] != best:
                changed = True
                assignments[i] = best
        for c in range(k):
            members = [data[i] for i in range(n) if assignments[i] == c]
            if members:
                centroids[c] = _mean(members)
        if not changed:
            break
    return assignments, centroids


def pick_k(n: int, *, k_min: int = 2, k_max: int = 6) -> int:
    """Heuristic k chooser.

    State branches:
      n <= 2  → k = 1 (degenerate; one signal row)
      3..6    → k = 2
      7..15   → k = 3
      16..40  → k = 4
      40+     → k = min(k_max, n // 10)
    """
    if n <= 2:
        return 1
    if n <= 6:
        return 2
    if n <= 15:
        return 3
    if n <= 40:
        return 4
    return min(k_max, max(2, n // 10))


def recency_weight(created_at: datetime | None, now: datetime) -> float:
    """Exponential decay: 1.0 today, 0.5 at 30 days, ~0 at 90+ days."""
    if created_at is None:
        return 1.0
    delta_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return math.exp(-delta_days / 43.28)  # half-life ≈ 30 days


def effectiveness_for_cluster(
    samples: list[FeedbackSample], *, now: datetime,
) -> tuple[float, float, float]:
    """Returns (retrieval_quality, response_quality, effectiveness).

    Definitions:
      response_quality = recency-weighted mean of (rating in {-1,0,+1})
        normalized to [0, 1] via (r + 1) / 2.
      retrieval_quality = fraction of samples whose validators_passed=True.
      effectiveness = 0.6 * response_quality + 0.4 * retrieval_quality.
    """
    if not samples:
        return 0.0, 0.0, 0.0
    weights = [recency_weight(s.created_at, now) for s in samples]
    total_w = sum(weights) or 1.0
    norm_ratings = [(s.rating + 1) / 2.0 for s in samples]
    response_quality = sum(
        nr * w for nr, w in zip(norm_ratings, weights, strict=False)
    ) / total_w
    retrieval_quality = sum(1 for s in samples if s.validators_passed) / len(samples)
    effectiveness = 0.6 * response_quality + 0.4 * retrieval_quality
    return retrieval_quality, response_quality, effectiveness


def preferred_evidence_ids(samples: list[FeedbackSample]) -> list[str]:
    """Evidence IDs cited in positively-rated messages (and not in
    negatively-rated ones). The /answer service uses these to re-rank
    retrieval on the next similar question — the explicit adversarial-
    learning signal.
    """
    positive: dict[str, int] = {}
    negative: dict[str, int] = {}
    for s in samples:
        for eid in s.cited_evidence_ids:
            if s.rating > 0:
                positive[eid] = positive.get(eid, 0) + 1
            elif s.rating < 0:
                negative[eid] = negative.get(eid, 0) + 1
    out = []
    for eid, pos in positive.items():
        neg = negative.get(eid, 0)
        if pos > neg:
            out.append(eid)
    return sorted(out)


def rollup_signals(
    samples: list[FeedbackSample], *, now: datetime,
    question_lookup: dict[str, str] | None = None,
) -> list[ClusterSignal]:
    """Cluster the samples per surface, compute one row per (surface, cluster).

    `question_lookup` is an optional message_id → question_text map used
    to set ClusterSignal.exemplar_question (purely cosmetic — surfaces
    in the admin UI).
    """
    by_surface: dict[str, list[FeedbackSample]] = {}
    for s in samples:
        by_surface.setdefault(s.surface, []).append(s)

    out: list[ClusterSignal] = []
    for surface, group in by_surface.items():
        # Drop samples without an embedding — they can't be clustered.
        usable = [s for s in group if s.embedding]
        if not usable:
            continue
        k = pick_k(len(usable))
        matrix = [s.embedding for s in usable]
        labels, centroids = kmeans(matrix, k)
        for c in range(k):
            members = [usable[i] for i in range(len(usable)) if labels[i] == c]
            if not members:
                continue
            rq, resp_q, eff = effectiveness_for_cluster(members, now=now)
            exemplar = ""
            if question_lookup:
                # Pick the most recent positively-rated member as exemplar;
                # fall back to any member.
                pos = [m for m in members if m.rating >= 0]
                pick = pos[-1] if pos else members[-1]
                exemplar = question_lookup.get(pick.message_id, "")
            out.append(
                ClusterSignal(
                    surface=surface,
                    prompt_centroid=centroids[c],
                    exemplar_question=exemplar,
                    retrieval_quality=round(rq, 3),
                    response_quality=round(resp_q, 3),
                    effectiveness=round(eff, 3),
                    sample_count=len(members),
                    preferred_evidence_ids=preferred_evidence_ids(members),
                )
            )
    return out
