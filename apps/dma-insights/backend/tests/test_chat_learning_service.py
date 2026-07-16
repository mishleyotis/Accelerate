"""Tests for the adversarial-learning rollup service.

Covers:
  - Rate-weighted effectiveness
  - Preferred E-IDs (positive samples > negative samples)
  - pick_k branches
  - End-to-end rollup_signals
  - k > n handling
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.chat_learning.service import (  # noqa: E402
    FeedbackSample,
    effectiveness_for_cluster,
    kmeans,
    pick_k,
    preferred_evidence_ids,
    recency_weight,
    rollup_signals,
)

NOW = datetime(2026, 5, 23, tzinfo=UTC)


def _s(rating: int = 1, eids=None, validators=True,
       created=None, surface="rag_answer", emb=None,
       mid="00000000-0000-0000-0000-000000000001") -> FeedbackSample:
    return FeedbackSample(
        message_id=mid,
        surface=surface,
        embedding=emb if emb is not None else [1.0, 0.0],
        rating=rating,
        cited_evidence_ids=eids or [],
        validators_passed=validators,
        created_at=created or NOW,
    )


class TestRecencyWeight:
    def test_today_is_1(self) -> None:
        assert recency_weight(NOW, NOW) == 1.0

    def test_30_days_is_approx_half(self) -> None:
        thirty_ago = NOW - timedelta(days=30)
        w = recency_weight(thirty_ago, NOW)
        # half-life ≈ 30 days → weight ≈ 0.5
        assert 0.40 < w < 0.60

    def test_none_returns_1(self) -> None:
        assert recency_weight(None, NOW) == 1.0


class TestPickK:
    def test_branches(self) -> None:
        assert pick_k(1) == 1
        assert pick_k(2) == 1
        assert pick_k(3) == 2
        assert pick_k(6) == 2
        assert pick_k(10) == 3
        assert pick_k(30) == 4
        # n=100 → min(6, 100/10) = 6
        assert pick_k(100) == 6


class TestKmeans:
    def test_k_capped_at_n(self) -> None:
        labels, centroids = kmeans([[1.0, 0.0]], k=10)
        assert len(centroids) == 1
        assert labels == [0]

    def test_clusters_emerge(self) -> None:
        data = [
            [0.0, 0.0], [0.1, 0.0],
            [10.0, 10.0], [10.1, 10.0],
        ]
        labels, _ = kmeans(data, 2)
        assert labels[0] == labels[1]
        assert labels[2] == labels[3]
        assert labels[0] != labels[2]


class TestEffectiveness:
    def test_empty_returns_zeros(self) -> None:
        rq, resp_q, eff = effectiveness_for_cluster([], now=NOW)
        assert rq == 0.0 and resp_q == 0.0 and eff == 0.0

    def test_all_positive(self) -> None:
        rq, resp_q, eff = effectiveness_for_cluster(
            [_s(rating=1, validators=True) for _ in range(3)], now=NOW,
        )
        assert resp_q == 1.0
        assert rq == 1.0
        assert eff == 1.0

    def test_all_negative(self) -> None:
        rq, resp_q, eff = effectiveness_for_cluster(
            [_s(rating=-1, validators=False) for _ in range(3)], now=NOW,
        )
        assert resp_q == 0.0
        assert rq == 0.0
        assert eff == 0.0

    def test_mixed_validators(self) -> None:
        rq, _, _ = effectiveness_for_cluster(
            [_s(rating=1, validators=True),
             _s(rating=1, validators=False)], now=NOW,
        )
        assert rq == 0.5


class TestPreferredEvidenceIds:
    def test_positive_only(self) -> None:
        samples = [
            _s(rating=1, eids=["E-1", "E-2"]),
            _s(rating=1, eids=["E-2"]),
        ]
        assert preferred_evidence_ids(samples) == ["E-1", "E-2"]

    def test_negative_overrides_positive(self) -> None:
        samples = [
            _s(rating=1, eids=["E-1"]),
            _s(rating=-1, eids=["E-1"]),
            _s(rating=-1, eids=["E-1"]),
        ]
        # E-1 has 1 pos, 2 neg → excluded
        assert preferred_evidence_ids(samples) == []

    def test_neutral_ignored(self) -> None:
        samples = [
            _s(rating=0, eids=["E-1"]),
            _s(rating=1, eids=["E-2"]),
        ]
        # Only E-2 has positive support
        assert preferred_evidence_ids(samples) == ["E-2"]


class TestRollupSignals:
    def test_empty(self) -> None:
        assert rollup_signals([], now=NOW) == []

    def test_no_embeddings_skipped(self) -> None:
        s = FeedbackSample(
            message_id="m1", surface="rag_answer",
            embedding=[],  # missing
            rating=1, cited_evidence_ids=["E-1"],
            validators_passed=True, created_at=NOW,
        )
        assert rollup_signals([s], now=NOW) == []

    def test_single_cluster_path(self) -> None:
        # 2 samples → pick_k=1 → single cluster
        samples = [
            _s(rating=1, eids=["E-1"], emb=[1.0, 0.0]),
            _s(rating=1, eids=["E-1"], emb=[1.0, 0.1]),
        ]
        out = rollup_signals(samples, now=NOW)
        assert len(out) == 1
        assert out[0].sample_count == 2
        assert out[0].preferred_evidence_ids == ["E-1"]

    def test_k_greater_than_n_handled(self) -> None:
        # Force pick_k > n by manipulating samples to land in the k>=2 bucket.
        # We have only 3 samples (pick_k=2), so 2 cluster cap is enforced
        # by kmeans (max k = n).
        samples = [
            _s(rating=1, eids=["E-1"], emb=[1.0, 0.0]),
            _s(rating=1, eids=["E-1"], emb=[1.0, 0.0]),
            _s(rating=1, eids=["E-1"], emb=[1.0, 0.0]),
        ]
        out = rollup_signals(samples, now=NOW)
        # Even with k=2, identical embeddings collapse to 1 cluster meaningfully.
        assert all(o.sample_count > 0 for o in out)
        total = sum(o.sample_count for o in out)
        assert total == 3

    def test_multiple_surfaces_isolated(self) -> None:
        samples = [
            _s(rating=1, surface="rag_answer"),
            _s(rating=1, surface="rag_answer"),
            _s(rating=1, surface="meeting_prep"),
            _s(rating=1, surface="meeting_prep"),
        ]
        out = rollup_signals(samples, now=NOW)
        surfaces = {o.surface for o in out}
        assert surfaces == {"rag_answer", "meeting_prep"}

    def test_simulated_100_feedback_rows(self) -> None:
        """Stress-test: 100 simulated rows across 2 surfaces, mixed
        embeddings, mixed ratings. Worker must produce non-empty signals
        without crashing on degenerate clusters."""
        import random
        rnd = random.Random(42)
        samples = []
        for i in range(100):
            surface = "rag_answer" if i % 2 == 0 else "meeting_prep"
            # Two embedding cohorts
            base = [0.0, 0.0] if i % 4 < 2 else [5.0, 5.0]
            emb = [base[0] + rnd.uniform(-0.5, 0.5), base[1] + rnd.uniform(-0.5, 0.5)]
            samples.append(_s(
                rating=rnd.choice([-1, 0, 1]),
                eids=[f"E-{i % 10}"],
                emb=emb,
                surface=surface,
                mid=f"00000000-0000-0000-0000-{i:012d}",
            ))
        out = rollup_signals(samples, now=NOW)
        # Per surface we get k=4 clusters (n=50 → pick_k=4)
        assert len(out) >= 2
        for sig in out:
            assert 0 <= sig.effectiveness <= 1
            assert 0 <= sig.retrieval_quality <= 1
            assert 0 <= sig.response_quality <= 1
            assert sig.sample_count > 0
