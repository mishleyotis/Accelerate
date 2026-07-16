"""Pure-logic helpers for the peer_patterns worker.

State transitions:
  cohort size (entities) < 3
    → returns a single "insufficient_data" archetype, sample_count=N,
      silhouette=None. The endpoint surfaces insufficient_data=True.
  cohort size 3..6
    → k=2 (we don't try to over-cluster small cohorts; silhouette
      collapses below 4 samples per cluster anyway)
  cohort size 7..20
    → k chosen via silhouette score scan over k=2..min(5, n-1)
  cohort size 20+
    → k scan over 2..6
  all entities have identical scores
    → k=1; silhouette=None (degenerate); single archetype "homogeneous"

Pure-logic only. Live DB IO is in main.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EntityVector:
    entity_id: str
    subcap_ids: list[str]   # subcap_id list (alignment key)
    scores: list[float]     # parallel to subcap_ids


@dataclass
class Archetype:
    label: str
    centroid: list[float]
    defining_subcap_ids: list[str]
    member_entity_ids: list[str]
    sample_count: int
    silhouette: float | None = None


def _l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=False)))


def _mean(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def align_vectors(entities: list[EntityVector]) -> tuple[list[str], list[list[float]], list[str]]:
    """Project each entity's scores onto the union of subcap_ids; missing
    cells fill with the column mean. Returns (subcap_ids, matrix, entity_ids).
    """
    all_caps: list[str] = []
    seen: set[str] = set()
    for ev in entities:
        for sid in ev.subcap_ids:
            if sid not in seen:
                all_caps.append(sid)
                seen.add(sid)
    # Build per-entity dict
    entity_dicts = [dict(zip(e.subcap_ids, e.scores, strict=False)) for e in entities]
    # Column means for fill
    col_mean: dict[str, float] = {}
    for sid in all_caps:
        vals = [d[sid] for d in entity_dicts if sid in d]
        col_mean[sid] = sum(vals) / len(vals) if vals else 0.0
    matrix = [
        [d.get(sid, col_mean[sid]) for sid in all_caps]
        for d in entity_dicts
    ]
    return all_caps, matrix, [e.entity_id for e in entities]


def kmeans(
    data: list[list[float]], k: int, *, max_iter: int = 50, seed: int = 7
) -> tuple[list[int], list[list[float]]]:
    """Tiny pure-Python KMeans. Returns (assignments, centroids).

    We seed deterministically (no numpy) by picking the first `k` items as
    initial centroids — fine for the cohort sizes we run (~10s of entities).
    """
    n = len(data)
    if n == 0:
        return [], []
    k = max(1, min(k, n))
    # Deterministic init: pick rows at regular stride
    stride = max(1, n // k)
    centroids = [list(data[(i * stride) % n]) for i in range(k)]
    assignments = [0] * n
    for _ in range(max_iter):
        # Assign
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
        # Update
        for c in range(k):
            members = [data[i] for i in range(n) if assignments[i] == c]
            if members:
                centroids[c] = _mean(members)
        if not changed:
            break
    return assignments, centroids


def silhouette_score(data: list[list[float]], labels: list[int]) -> float | None:
    """Simplified silhouette: for each point, (b - a) / max(a, b) where
    a = mean intra-cluster distance, b = mean nearest-cluster distance.

    Returns None when only one cluster is present (silhouette undefined).
    """
    unique = set(labels)
    if len(unique) < 2 or len(data) < 3:
        return None
    scores: list[float] = []
    by_cluster: dict[int, list[list[float]]] = {}
    for vec, lab in zip(data, labels, strict=False):
        by_cluster.setdefault(lab, []).append(vec)
    for vec, lab in zip(data, labels, strict=False):
        same = [v for v in by_cluster[lab] if v is not vec]
        a = (sum(_l2(vec, v) for v in same) / len(same)) if same else 0.0
        b_vals = []
        for other_lab, others in by_cluster.items():
            if other_lab == lab:
                continue
            b_vals.append(sum(_l2(vec, v) for v in others) / len(others))
        b = min(b_vals) if b_vals else 0.0
        denom = max(a, b)
        scores.append(0.0 if denom == 0 else (b - a) / denom)
    return sum(scores) / len(scores)


def pick_k(matrix: list[list[float]], k_min: int = 2, k_max: int = 5) -> tuple[int, float | None]:
    """Pick k via silhouette scan. Falls back to k_min on ties or degenerate
    matrices. Returns (k, silhouette_at_k)."""
    n = len(matrix)
    if n < 3:
        return 1, None
    k_max = min(k_max, n - 1)
    best_k = k_min
    best_sil: float | None = None
    for k in range(k_min, k_max + 1):
        labels, _ = kmeans(matrix, k)
        sil = silhouette_score(matrix, labels)
        if sil is None:
            continue
        if best_sil is None or sil > best_sil:
            best_sil = sil
            best_k = k
    return best_k, best_sil


def label_archetype(idx: int, total: int) -> str:
    """Stable archetype labels. The set is deliberately small + opinionated
    so AEs see consistent vocabulary across surfaces.
    """
    names = (
        "compliance-first", "experience-first", "agentic-pilot",
        "platform-rationalizing", "data-foundations",
    )
    if total == 1:
        return "homogeneous"
    if idx < len(names):
        return names[idx]
    return f"archetype-{idx + 1}"


def defining_subcaps_for_archetype(
    centroid: list[float], all_caps: list[str], top_n: int = 8,
) -> list[str]:
    """The subcap_ids whose centroid value is furthest from 3.0 (the mid-
    band). These are the capabilities that define the archetype's
    identity within the cohort.
    """
    scored = [
        (sid, abs(c - 3.0))
        for sid, c in zip(all_caps, centroid, strict=False)
    ]
    scored.sort(key=lambda kv: -kv[1])
    return [sid for sid, _ in scored[:top_n]]


def compute_archetypes(entities: list[EntityVector]) -> list[Archetype]:
    """End-to-end pure pipeline. Returns 1..k Archetype rows ready to
    persist."""
    if not entities:
        return []
    if len(entities) < 3:
        # Insufficient cohort
        return [
            Archetype(
                label="insufficient_data",
                centroid=[],
                defining_subcap_ids=[],
                member_entity_ids=[e.entity_id for e in entities],
                sample_count=len(entities),
                silhouette=None,
            )
        ]
    all_caps, matrix, eids = align_vectors(entities)
    k, sil = pick_k(matrix)
    labels, centroids = kmeans(matrix, k)
    archetypes: list[Archetype] = []
    for c in range(k):
        members = [eids[i] for i in range(len(eids)) if labels[i] == c]
        if not members:
            continue
        archetypes.append(
            Archetype(
                label=label_archetype(c, k),
                centroid=centroids[c],
                defining_subcap_ids=defining_subcaps_for_archetype(
                    centroids[c], all_caps,
                ),
                member_entity_ids=members,
                sample_count=len(members),
                silhouette=sil,
            )
        )
    return archetypes
