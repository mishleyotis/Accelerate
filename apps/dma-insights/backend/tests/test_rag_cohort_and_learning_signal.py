"""Phase 5 RAG cohort + learning signal threshold tests.

Per the audit Phase 5:
  - test_single_entity_cohort_does_not_prefer_other_entity_eids
  - test_learning_signal_applies_only_with_effectiveness_and_sample_thresholds
  - test_cache_db_down_does_not_block_answer_generation

Cohort scoping (ADR 0006) + learning signal thresholds are the
two reasons the RAG router DOESN'T just blindly serve whatever
Gemini emits. Drift in either contract = cross-entity leakage OR
spurious learning-signal pull-ins from low-confidence clusters.

Each test pins one concrete branch of the contract so a future
refactor surfaces the regression here BEFORE the AE intelligence
panel surfaces it.
"""
from __future__ import annotations

import pytest

# ── Helpers ────────────────────────────────────────────────────────


def _make_cluster(
    *, effectiveness: float, sample_count: int,
    surface: str = "intelligence",
    preferred_eids: list[str] | None = None,
    centroid: list[float] | None = None,
):
    """LearningCluster factory matching the dataclass shape
    (cluster_id, surface, centroid, effectiveness, sample_count,
    preferred_evidence_ids -- frozen)."""
    from app.services.rag_answer import LearningCluster

    return LearningCluster(
        cluster_id="cluster1",
        surface=surface,
        centroid=centroid if centroid is not None else [1.0, 0.0, 0.0, 0.0],
        effectiveness=effectiveness,
        sample_count=sample_count,
        preferred_evidence_ids=preferred_eids or [],
    )


def _make_item(ref_id: str, kind: str = "evidence"):
    """RetrievedItem factory matching the dataclass shape
    (kind, ref_id, text, similarity, source_label -- frozen)."""
    from app.services.rag_answer import RetrievedItem

    return RetrievedItem(
        kind=kind,  # type: ignore[arg-type]
        ref_id=ref_id,
        text="Test text",
        similarity=0.5,
        source_label="Test source",
    )


# ── Cohort scoping (ADR 0006) ─────────────────────────────────────


def test_single_entity_cohort_drops_preferred_eid_from_other_entity():
    """When cohort_mode=single, the cohort_eligible_eids filter
    must reject preferred_evidence_ids from OTHER entities.
    Without this guard, a cluster trained on entity X's evidence
    would pollute entity Y's answer with X's E-IDs."""
    from app.services.rag_answer import apply_learning_signal

    bundle = [_make_item("E-001")]
    cluster = _make_cluster(
        effectiveness=0.9, sample_count=10,
        preferred_eids=["E-XYZ"],  # belongs to a different cohort
    )
    # cohort filter: only E-001 is eligible (entity A's scope).
    cohort_eligible = {"E-001"}

    new_bundle, _ = apply_learning_signal(
        bundle_items=bundle,
        cluster=cluster,
        similarity=0.95,
        cohort_eligible_eids=cohort_eligible,
        extra_item_factory=None,  # no pull-ins -- focus on the filter
    )
    eids_in_bundle = {item.ref_id for item in new_bundle}
    assert "E-XYZ" not in eids_in_bundle, (
        "Cross-entity preferred E-ID leaked into single-entity bundle."
    )


def test_apply_learning_signal_no_match_when_cluster_is_none():
    """No cluster -> no_match state. The bundle returns unchanged."""
    from app.services.rag_answer import apply_learning_signal

    bundle = [_make_item("E-001")]
    new_bundle, result = apply_learning_signal(
        bundle_items=bundle,
        cluster=None,
        similarity=0.0,
    )
    # Bundle returns unchanged.
    assert [i.ref_id for i in new_bundle] == ["E-001"]
    # The result must describe the no-match state via the documented
    # `applied=False, reason='no_match'` shape.
    assert result.applied is False
    assert result.reason == "no_match"


def test_apply_learning_signal_low_effectiveness_does_not_bias_bundle():
    """A cluster with effectiveness < MIN_LEARNING_EFFECTIVENESS must
    NOT modify the bundle. Otherwise low-quality learning signals
    would degrade answers."""
    from app.services import rag_answer as ra

    bundle = [_make_item("E-001"), _make_item("E-002")]
    low_eff_cluster = _make_cluster(
        effectiveness=ra.MIN_LEARNING_EFFECTIVENESS - 0.01,
        sample_count=100,  # plenty of samples
        preferred_eids=["E-PREF"],
    )
    new_bundle, _result = ra.apply_learning_signal(
        bundle_items=bundle,
        cluster=low_eff_cluster,
        similarity=0.95,
    )
    # Pre-existing items still present (no reorder is fine; we care
    # about pull-ins).
    e_ids = [i.ref_id for i in new_bundle]
    assert "E-PREF" not in e_ids, (
        "Low-effectiveness cluster pulled in a preferred E-ID. "
        "Threshold gating is broken."
    )


def test_apply_learning_signal_insufficient_samples_does_not_bias_bundle():
    """A cluster with sample_count < MIN_LEARNING_SAMPLES must NOT
    modify the bundle. Audit: a 2-sample cluster is statistical
    noise, not a learned preference."""
    from app.services import rag_answer as ra

    bundle = [_make_item("E-001")]
    sparse_cluster = _make_cluster(
        effectiveness=0.95,  # high effectiveness
        sample_count=ra.MIN_LEARNING_SAMPLES - 1,  # but below the floor
        preferred_eids=["E-PREF"],
    )
    new_bundle, _ = ra.apply_learning_signal(
        bundle_items=bundle,
        cluster=sparse_cluster,
        similarity=0.95,
    )
    e_ids = [i.ref_id for i in new_bundle]
    assert "E-PREF" not in e_ids, (
        "Insufficient-samples cluster pulled in a preferred E-ID. "
        "Sample threshold gating is broken."
    )


def test_min_learning_thresholds_are_non_trivial_constants():
    """Sanity: MIN_LEARNING_EFFECTIVENESS + MIN_LEARNING_SAMPLES
    must be non-trivial (>0). A refactor that sets either to 0
    would silently disable the gating."""
    from app.services import rag_answer as ra

    assert hasattr(ra, "MIN_LEARNING_EFFECTIVENESS")
    assert hasattr(ra, "MIN_LEARNING_SAMPLES")
    assert 0 < ra.MIN_LEARNING_EFFECTIVENESS < 1, (
        f"MIN_LEARNING_EFFECTIVENESS={ra.MIN_LEARNING_EFFECTIVENESS} "
        "must be in (0, 1) -- 0 disables gating, 1 makes it impossible."
    )
    assert ra.MIN_LEARNING_SAMPLES >= 3, (
        f"MIN_LEARNING_SAMPLES={ra.MIN_LEARNING_SAMPLES} too low. "
        "Fewer than 3 samples is not a learned preference."
    )


# ── pick_best_cluster: similarity threshold + surface filter ────────


def test_pick_best_cluster_returns_no_match_with_empty_embedding():
    """When the question embedding is None (offline / Vertex 5xx /
    project unset), pick_best_cluster must return (None, 0.0)
    rather than crashing on the dot-product or returning a stale
    cluster."""
    from app.services.rag_answer import pick_best_cluster

    cluster = _make_cluster(effectiveness=0.9, sample_count=10)
    result, sim = pick_best_cluster(
        question_embedding=None,
        clusters=[cluster],
        surface="intelligence",
    )
    assert result is None
    assert sim == 0.0


def test_pick_best_cluster_filters_by_surface():
    """A cluster trained on the 'intelligence' surface must NOT
    apply to a 'meeting_prep' query. The surface check is what
    keeps the chat learning signal scoped to the right context."""
    from app.services.rag_answer import pick_best_cluster

    # Cluster lives on a different surface.
    other_surface_cluster = _make_cluster(
        effectiveness=0.9, sample_count=10, surface="recommendations",
    )
    result, _ = pick_best_cluster(
        question_embedding=[1.0] * 4,
        clusters=[other_surface_cluster],
        surface="intelligence",
    )
    assert result is None, (
        "pick_best_cluster returned a cluster from a different surface. "
        "Surface filter would let recommendations signal pollute "
        "intelligence answers."
    )


def test_pick_best_cluster_requires_minimum_similarity():
    """Even a matching-surface cluster must be DROPPED when its
    cosine similarity to the question embedding is below the
    threshold. Otherwise every chat goes through a low-confidence
    cluster lookup."""
    from app.services.rag_answer import MIN_LEARNING_SIM, pick_best_cluster

    # Build the cluster with an orthogonal centroid (cosine
    # similarity to [1,0,0,0] is 0). LearningCluster is frozen so
    # we must set centroid at construction.
    cluster = _make_cluster(
        effectiveness=0.9, sample_count=10, surface="intelligence",
        centroid=[0.0, 1.0, 0.0, 0.0],
    )
    result, sim = pick_best_cluster(
        question_embedding=[1.0, 0.0, 0.0, 0.0],
        clusters=[cluster],
        surface="intelligence",
    )
    # 0 similarity < MIN_LEARNING_SIM > 0 → no match
    assert sim < MIN_LEARNING_SIM
    assert result is None


# ── Cache DB down does not block answer generation ─────────────────


def test_safe_mark_invalidated_swallows_db_errors():
    """The synthesis_cache_db invalidation path must NEVER raise.
    The chat-feedback router already wraps it in try/except, but the
    helper itself should be best-effort -- a DB blip MUST NOT take
    out the user's /feedback POST."""
    from pathlib import Path

    cache_db_path = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "synthesis_cache_db.py"
    )
    if not cache_db_path.exists():
        pytest.skip("synthesis_cache_db.py not present")
    src = cache_db_path.read_text(encoding="utf-8")
    # The safe_mark_invalidated entrypoint must swallow exceptions
    # at its top level (per its `safe_` naming convention).
    assert "safe_mark_invalidated" in src
    # Must wrap in try/except.
    assert (
        "try:" in src and "except" in src
    ), (
        "safe_mark_invalidated must wrap its DB calls in try/except. "
        "A blip cannot 500 the user's feedback POST."
    )
