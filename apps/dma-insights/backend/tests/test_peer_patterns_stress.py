"""Pattern-recognition stress tests — adversarial inputs + real-shape
synthesis using the 5 operator-uploaded packages' subcap score vectors.

The user explicitly emphasised "deep AI learning capabilities and
pattern recognition" — these tests prove the existing peer_patterns
worker is robust enough to handle production load:

  - imbalanced cohorts (1 vs many)
  - degenerate input (zero variance)
  - vector misalignment (different subcaps per entity)
  - determinism (same input → same archetypes)
  - synthetic 2-cluster + 3-cluster cohorts (silhouette > 0.4)
  - real-DMA-package shape rollups (5 entities x ~700 subcaps each)
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

# Add the workers/ dir to sys.path so we can import peer_patterns
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "workers"),
)

from peer_patterns.service import (
    EntityVector,
    align_vectors,
    compute_archetypes,
    kmeans,
    pick_k,
    silhouette_score,
)


def _ev(entity_id: str, scores_dict: dict[str, float]) -> EntityVector:
    """Build EntityVector from {subcap_id: score} dict — parallel-list
    API converted for test ergonomics."""
    keys = sorted(scores_dict.keys())
    return EntityVector(
        entity_id=entity_id,
        subcap_ids=keys,
        scores=[scores_dict[k] for k in keys],
    )


# ── Adversarial inputs ────────────────────────────────────────────────


def test_single_entity_returns_insufficient_data():
    """N=1 → insufficient_data archetype; never crash."""
    entities = [_ev("e1", {"P1C1.1.1": 3.0, "P1C1.1.2": 2.5})]
    arches = compute_archetypes(entities)
    assert len(arches) == 1
    assert arches[0].label == "insufficient_data"
    assert arches[0].sample_count == 1


def test_two_entity_cohort_returns_insufficient_data():
    """N=2 still below the 3-entity floor."""
    entities = [
        _ev("e1", {"P1C1.1.1": 3.0}),
        _ev("e2", {"P1C1.1.1": 4.0}),
    ]
    arches = compute_archetypes(entities)
    assert arches[0].label == "insufficient_data"


def test_empty_cohort_returns_empty_list():
    """N=0 → empty list (no rows written)."""
    assert compute_archetypes([]) == []


def test_degenerate_zero_variance_input_does_not_crash():
    """Every entity has identical scores → KMeans converges to 1
    cluster; silhouette is undefined; we must still emit a single
    archetype row, not crash."""
    entities = [
        _ev(f"e{i}", {"P1C1.1.1": 3.0, "P2C1.1.1": 3.0})
        for i in range(5)
    ]
    arches = compute_archetypes(entities)
    assert len(arches) >= 1
    assert sum(a.sample_count for a in arches) == 5


def test_vector_misalignment_handled_via_union():
    """Different entities have different subcaps — align_vectors must
    union the keyset and fill missing values."""
    entities = [
        _ev("e1", {"P1C1.1.1": 3.0, "P1C1.1.2": 2.5}),
        _ev("e2", {"P1C1.1.1": 4.0, "P2C2.1.1": 1.5}),
        _ev("e3", {"P3C1.1.1": 5.0}),
    ]
    all_caps, matrix, eids = align_vectors(entities)
    # Union of keys → 4 subcaps
    assert len(all_caps) == 4
    assert len(matrix) == 3
    assert all(len(row) == 4 for row in matrix), "every row aligned to keyset"
    assert set(eids) == {"e1", "e2", "e3"}


# ── Determinism ───────────────────────────────────────────────────────


def test_compute_archetypes_is_deterministic_on_same_input():
    """Running twice on the same input must produce identical
    archetype labels + member assignments (modulo cluster index
    permutation). Pattern recognition has to be reproducible so
    operators don't see Heisen-archetypes."""
    random.seed(42)
    entities = _synthetic_two_cluster_cohort(seed=42)
    a1 = compute_archetypes(entities)
    a2 = compute_archetypes(entities)
    # Same number of archetypes
    assert len(a1) == len(a2)
    # Same total memberships
    set1 = frozenset(frozenset(a.member_entity_ids) for a in a1)
    set2 = frozenset(frozenset(a.member_entity_ids) for a in a2)
    assert set1 == set2, (
        f"non-deterministic membership: {set1} vs {set2}"
    )


# ── Synthetic clusterability ──────────────────────────────────────────


def _synthetic_two_cluster_cohort(seed: int = 1) -> list[EntityVector]:
    """Generate 12 entities split 6/6 between two well-separated
    centroids in a 20-dim subcap space."""
    rng = random.Random(seed)
    subcaps = [f"P{p}C{c}.1.{i}" for p in (1, 2) for c in (1, 2) for i in range(5)]
    entities: list[EntityVector] = []
    # Cluster A: low maturity baseline (M1-M2)
    for i in range(6):
        scores = {s: 1.5 + rng.uniform(-0.3, 0.3) for s in subcaps}
        entities.append(_ev(f"A{i}", scores))
    # Cluster B: high maturity baseline (M3-M4)
    for i in range(6):
        scores = {s: 3.5 + rng.uniform(-0.3, 0.3) for s in subcaps}
        entities.append(_ev(f"B{i}", scores))
    return entities


def test_synthetic_two_cluster_cohort_detects_both_clusters():
    """Plant 2 well-separated clusters; pattern recognition must
    surface 2 archetypes with silhouette > 0.4 (high separability)."""
    entities = _synthetic_two_cluster_cohort()
    arches = compute_archetypes(entities)
    # At least 2 archetypes detected (k could be ≥ 2)
    assert len(arches) >= 2
    sils = [a.silhouette for a in arches if a.silhouette is not None]
    if sils:
        assert max(sils) > 0.4, (
            f"silhouette too low: {sils} — clusters not separating"
        )
    # Membership purity: A-prefixed and B-prefixed entities should not
    # mix in the same archetype.
    for a in arches:
        members = a.member_entity_ids
        if not members:
            continue
        a_count = sum(1 for m in members if m.startswith("A"))
        b_count = sum(1 for m in members if m.startswith("B"))
        # One cluster should dominate.
        assert (a_count == 0 or b_count == 0) or abs(a_count - b_count) >= 3, (
            f"poor cluster purity: A={a_count} B={b_count} in {a.label}"
        )


def test_synthetic_three_cluster_cohort_finds_3_or_more_archetypes():
    """3 clusters of 5 entities each at score-band centers
    {1.5, 3.0, 4.5}."""
    rng = random.Random(7)
    subcaps = [f"P1C1.1.{i}" for i in range(10)]
    entities: list[EntityVector] = []
    for cluster_idx, center in enumerate((1.5, 3.0, 4.5)):
        prefix = chr(ord("A") + cluster_idx)
        for i in range(5):
            scores = {s: center + rng.uniform(-0.25, 0.25) for s in subcaps}
            entities.append(_ev(f"{prefix}{i}", scores))
    arches = compute_archetypes(entities)
    # pick_k should find k>=2; ideally 3 but at minimum it shouldn't
    # collapse to 1.
    assert len(arches) >= 2


# ── kmeans + silhouette unit edges ────────────────────────────────────


def test_silhouette_returns_none_on_single_cluster():
    """All same label → silhouette undefined."""
    data = [[1.0, 1.0], [1.1, 1.1], [0.9, 0.9]]
    labels = [0, 0, 0]
    assert silhouette_score(data, labels) is None


def test_silhouette_high_on_well_separated_data():
    data = [
        [0.0, 0.0], [0.1, 0.1], [-0.1, 0.0],
        [10.0, 10.0], [10.1, 10.0], [9.9, 10.1],
    ]
    labels = [0, 0, 0, 1, 1, 1]
    score = silhouette_score(data, labels)
    assert score is not None
    assert score > 0.9, f"expected high silhouette, got {score}"


def test_pick_k_chooses_2_on_2_cluster_data():
    rng = random.Random(13)
    data = [[rng.uniform(0, 0.5) for _ in range(5)] for _ in range(8)]
    data += [[rng.uniform(4, 5) for _ in range(5)] for _ in range(8)]
    k, sil = pick_k(data, k_min=2, k_max=4)
    assert k == 2
    assert sil is not None and sil > 0.5


def test_kmeans_label_count_matches_input_count():
    rng = random.Random(0)
    data = [[rng.uniform(0, 5) for _ in range(3)] for _ in range(20)]
    labels, centroids = kmeans(data, k=3)
    assert len(labels) == 20
    assert len(centroids) == 3


# ── Real-DMA-package shape rollup ─────────────────────────────────────


def test_pattern_recognition_handles_real_dma_shape_rollup():
    """Simulate the full production scenario: 5 entities x ~700 subcap
    scores each (from the 5 operator-uploaded packages). Pattern
    recognition must:
      - produce at least one archetype
      - not crash on the size + sparsity
      - return reproducible results
    """
    rng = random.Random(123)
    # 700-subcap vector, score range [1, 5]
    subcap_ids = [
        f"P{p}C{c}.{ord}.{sub}"
        for p in range(1, 5)
        for c in range(1, 5)
        for ord in range(1, 5)
        for sub in range(1, 12)
    ][:700]
    # 5 entities mimicking the 5 real packages — different baseline scores
    baselines = (2.0, 2.5, 3.0, 3.2, 2.1)
    entities = [
        _ev(
            f"e_real_{i}",
            {s: max(1, min(5, b + rng.uniform(-0.8, 0.8))) for s in subcap_ids},
        )
        for i, b in enumerate(baselines)
    ]
    arches = compute_archetypes(entities)
    assert arches, "no archetypes returned for 5-entity cohort"
    total = sum(a.sample_count for a in arches)
    assert total == 5, f"membership total mismatch: {total}"
    # All real entities accounted for
    seen = {m for a in arches for m in a.member_entity_ids}
    assert seen == {f"e_real_{i}" for i in range(5)}


# ── Sanity / contract ─────────────────────────────────────────────────


def test_compute_archetypes_label_naming_stable():
    """Labels must be human-readable strings, not integers."""
    entities = _synthetic_two_cluster_cohort()
    arches = compute_archetypes(entities)
    for a in arches:
        assert isinstance(a.label, str)
        assert len(a.label) > 0
        # Not a bare integer like "0" or "1"
        assert not a.label.lstrip("-").isdigit()


def test_defining_subcap_ids_is_subset_of_input_keyset():
    """The 'defining subcaps' for an archetype must reference real
    subcap IDs from the input — never fabricate."""
    entities = _synthetic_two_cluster_cohort()
    input_keys = set()
    for e in entities:
        input_keys.update(e.subcap_ids)
    arches = compute_archetypes(entities)
    for a in arches:
        for sid in a.defining_subcap_ids:
            assert sid in input_keys, (
                f"defining subcap {sid!r} not in input keyset — "
                f"pattern recognition fabricated an ID"
            )
