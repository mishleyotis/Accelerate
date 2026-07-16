"""Adversarial-learning reranking tests for /api/v1/rag/answer.

State transitions exercised:
  - applied              → bundle ordering changes; learning_signal.applied=true
  - low_effectiveness    → no boost; reason="low_effectiveness"
  - insufficient_samples → no boost; reason="insufficient_samples"
  - no_match             → similarity < 0.75; reason="no_match"
  - cohort filter        → preferred E-ID from a different subvertical
                            does NOT get pulled in if cohort_mode=single
  - backward compat      → empty chat_learning_signals → identical bundle
                            ordering as the prior batch
"""
from __future__ import annotations

from app.services.rag_answer import (
    LearningCluster,
    RetrievedItem,
    apply_learning_signal,
    pick_best_cluster,
)


def _bundle(*eids: str, base_sim: float = 0.9) -> list[RetrievedItem]:
    """Build a deterministic bundle ordered E-1, E-2, E-3 by descending sim."""
    return [
        RetrievedItem(
            kind="evidence", ref_id=eid,
            text=f"source for {eid}: lorem ipsum",
            similarity=base_sim - 0.05 * i,
            source_label=f"src-{eid}",
        )
        for i, eid in enumerate(eids)
    ]


def _cluster(
    *, eff: float = 0.8, samples: int = 10,
    preferred: list[str] | None = None,
    centroid: list[float] | None = None,
    cid: str = "c1", surface: str = "rag_answer",
) -> LearningCluster:
    return LearningCluster(
        cluster_id=cid, surface=surface,
        centroid=centroid or [1.0, 0.0],
        effectiveness=eff,
        sample_count=samples,
        preferred_evidence_ids=preferred or ["E-2"],
    )


class TestPickBestCluster:
    def test_no_clusters_returns_none(self) -> None:
        c, sim = pick_best_cluster(
            question_embedding=[1.0, 0.0], clusters=[], surface="rag_answer",
        )
        assert c is None
        assert sim == 0.0

    def test_no_embedding_returns_none(self) -> None:
        c, _sim = pick_best_cluster(
            question_embedding=None, clusters=[_cluster()], surface="rag_answer",
        )
        assert c is None

    def test_below_min_similarity_returns_none(self) -> None:
        # Orthogonal vectors → cosine sim = 0
        c, _sim = pick_best_cluster(
            question_embedding=[0.0, 1.0],
            clusters=[_cluster(centroid=[1.0, 0.0])],
            surface="rag_answer",
        )
        assert c is None

    def test_aligned_above_threshold_returns_cluster(self) -> None:
        c, sim = pick_best_cluster(
            question_embedding=[1.0, 0.0],
            clusters=[_cluster(centroid=[1.0, 0.0])],
            surface="rag_answer",
        )
        assert c is not None
        assert sim == 1.0

    def test_filters_by_surface(self) -> None:
        clusters = [
            _cluster(cid="meeting_one", surface="meeting_prep"),
            _cluster(cid="answer_one", surface="rag_answer"),
        ]
        c, _ = pick_best_cluster(
            question_embedding=[1.0, 0.0],
            clusters=clusters, surface="rag_answer",
        )
        assert c is not None
        assert c.cluster_id == "answer_one"


class TestApplyLearningSignal_NoMatch:
    def test_none_cluster_yields_no_match(self) -> None:
        bundle = _bundle("E-1", "E-2", "E-3")
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=None, similarity=0.3,
        )
        assert out == bundle
        assert sig.applied is False
        assert sig.reason == "no_match"
        assert sig.items_boosted == 0
        assert sig.items_pulled == 0


class TestApplyLearningSignal_Gates:
    def test_low_effectiveness_no_boost(self) -> None:
        """eff < 0.5 → no boost; reason="low_effectiveness"."""
        bundle = _bundle("E-1", "E-2", "E-3")
        c = _cluster(eff=0.4, samples=10, preferred=["E-2"])
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.9,
        )
        assert sig.applied is False
        assert sig.reason == "low_effectiveness"
        # Bundle untouched
        assert [i.ref_id for i in out] == ["E-1", "E-2", "E-3"]
        # Metadata still records the cluster + effectiveness for audit
        assert sig.effectiveness == 0.4
        assert sig.cluster_id == "c1"

    def test_insufficient_samples_no_boost(self) -> None:
        """sample_count < 5 → no boost; reason="insufficient_samples"."""
        bundle = _bundle("E-1", "E-2", "E-3")
        c = _cluster(eff=0.9, samples=3, preferred=["E-2"])
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.9,
        )
        assert sig.applied is False
        assert sig.reason == "insufficient_samples"
        assert sig.sample_count == 3
        # Bundle untouched
        assert [i.ref_id for i in out] == ["E-1", "E-2", "E-3"]


class TestApplyLearningSignal_Applied:
    def test_boosts_preferred_items_in_bundle(self) -> None:
        """A preferred E-ID already in the bundle gets +LEARNING_BOOST
        added to its similarity → re-sorted ordering."""
        # E-3 starts with the LOWEST similarity (0.80). After +0.15 boost
        # it becomes 0.95 — higher than E-1 (0.90) and E-2 (0.85).
        bundle = _bundle("E-1", "E-2", "E-3")
        # bundle similarities: E-1=0.90, E-2=0.85, E-3=0.80
        c = _cluster(eff=0.9, samples=20, preferred=["E-3"])
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.92,
        )
        assert sig.applied is True
        assert sig.reason == "applied"
        assert sig.items_boosted == 1
        # E-3 should now be first.
        assert out[0].ref_id == "E-3"

    def test_pulls_in_preferred_eids_not_in_bundle(self) -> None:
        """Preferred E-IDs not initially retrieved are pulled in (up to 3)."""
        bundle = _bundle("E-1", "E-2")
        c = _cluster(
            eff=0.9, samples=20,
            preferred=["E-99", "E-101", "E-102", "E-103"],
        )

        def factory(eid: str) -> RetrievedItem | None:
            return RetrievedItem(
                kind="evidence", ref_id=eid, text=f"pulled {eid}",
                similarity=0.0, source_label="ext",
            )

        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.9,
            extra_item_factory=factory,
        )
        assert sig.applied is True
        assert sig.items_pulled == 3  # capped at MAX_PULL_IN
        eids = {i.ref_id for i in out}
        assert "E-99" in eids
        assert "E-101" in eids
        # Original items preserved
        assert "E-1" in eids and "E-2" in eids

    def test_audit_payload_shape(self) -> None:
        """`learning_signal.applied=true` audit dict shape."""
        bundle = _bundle("E-1", "E-2")
        c = _cluster(eff=0.85, samples=12, preferred=["E-2"])
        _, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.91,
        )
        d = sig.to_dict()
        assert d["applied"] is True
        assert d["reason"] == "applied"
        assert d["cluster_id"] == "c1"
        assert d["effectiveness"] == 0.85
        assert d["sample_count"] == 12
        assert d["items_boosted"] == 1
        assert d["items_pulled"] == 0
        assert d["similarity"] == 0.91


class TestApplyLearningSignal_CohortFilter:
    def test_cohort_filter_drops_ineligible_pullins(self) -> None:
        """When cohort_eligible_eids is supplied AND a factory is also
        supplied, preferred items not in the eligible set are dropped
        before the factory is even invoked.

        This is the "single cohort" defense: a preferred E-ID from a
        different subvertical should not bleed into a cohort_mode=single
        answer.
        """
        bundle = _bundle("E-1")
        c = _cluster(
            eff=0.9, samples=20,
            preferred=["E-99-cu", "E-100-rb"],  # CU + RB
        )

        def factory(eid: str) -> RetrievedItem | None:
            return RetrievedItem(
                kind="evidence", ref_id=eid, text=f"pulled {eid}",
                similarity=0.0, source_label="ext",
            )

        # Cohort filter: only CU is eligible.
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=0.9,
            cohort_eligible_eids={"E-99-cu"},
            extra_item_factory=factory,
        )
        assert sig.applied is True
        assert sig.items_pulled == 1
        eids = {i.ref_id for i in out}
        assert "E-99-cu" in eids
        assert "E-100-rb" not in eids


class TestBackwardCompatibility:
    def test_empty_clusters_means_no_match(self) -> None:
        """When no chat_learning_signals exist, /answer behaves identically
        to the prior batch: pick_best_cluster returns (None, 0) →
        apply_learning_signal returns the bundle unchanged + no_match."""
        bundle = _bundle("E-1", "E-2", "E-3")
        original_sims = [(i.ref_id, i.similarity) for i in bundle]
        c, sim = pick_best_cluster(
            question_embedding=[1.0, 0.0],
            clusters=[],
            surface="rag_answer",
        )
        out, sig = apply_learning_signal(
            bundle_items=bundle, cluster=c, similarity=sim,
        )
        # Identical ordering, identical similarities.
        assert [(i.ref_id, i.similarity) for i in out] == original_sims
        assert sig.applied is False
        assert sig.reason == "no_match"
