"""Tests for the pure pattern-drift service."""
from __future__ import annotations

from app.services.pattern_drift import (
    PILLARS,
    _bucket_for,
    compute_drift,
)


class TestBuckets:
    def test_threshold_boundaries(self) -> None:
        # critical_low: <= -1.0
        assert _bucket_for(-1.5) == "critical_low"
        assert _bucket_for(-1.0) == "critical_low"
        # below: -1.0 < x < -0.4
        assert _bucket_for(-0.9) == "below"
        assert _bucket_for(-0.5) == "below"
        # nominal: -0.4 <= x <= 0.4
        assert _bucket_for(-0.4) == "nominal"
        assert _bucket_for(0.0) == "nominal"
        assert _bucket_for(0.4) == "nominal"
        # above: 0.4 < x < 1.0
        assert _bucket_for(0.5) == "above"
        assert _bucket_for(0.9) == "above"
        # critical_high: >= 1.0
        assert _bucket_for(1.0) == "critical_high"
        assert _bucket_for(2.5) == "critical_high"


class TestComputeDrift:
    def test_happy_path_all_pillars_covered(self) -> None:
        scores = [
            ("P1C1.1.1", 3.0),  # vs peer 2.0 → +1.0 critical_high
            ("P1C1.1.2", 2.0),  # vs peer 3.5 → -1.5 critical_low
            ("P2C1.1.1", 3.5),  # vs peer 3.4 → +0.1 nominal
            ("P3C1.1.1", 3.0),  # vs peer 2.5 → +0.5 above
            ("P4C1.1.1", 2.0),  # vs peer 2.5 → -0.5 below
        ]
        peers = [
            ("P1C1.1.1", 2.0, 5),
            ("P1C1.1.2", 3.5, 5),
            ("P2C1.1.1", 3.4, 5),
            ("P3C1.1.1", 2.5, 5),
            ("P4C1.1.1", 2.5, 5),
        ]
        report = compute_drift(entity_scores=scores, peer_benchmarks=peers)
        # No skips
        assert report.cohort_insufficient_count == 0
        assert report.entity_missing_count == 0
        # All 4 pillars represented in pillar_drifts (order PILLARS)
        assert [pd.pillar for pd in report.pillar_drifts] == list(PILLARS)
        # P1 mean of [+1.0, -1.5] = -0.25 (nominal aggregate even with extremes)
        p1 = next(p for p in report.pillar_drifts if p.pillar == "P1")
        assert p1.drift_score == -0.25
        assert p1.subcap_count == 2
        # By-bucket counts on P1
        assert p1.by_bucket == {"critical_high": 1, "critical_low": 1}
        # Overall drift averages the 4 pillar means
        assert report.overall_drift is not None

    def test_cohort_insufficient_filters_subcap(self) -> None:
        scores = [("P1C1.1.1", 3.0)]
        peers = [("P1C1.1.1", 2.0, 2)]  # n < min_n=3
        report = compute_drift(entity_scores=scores, peer_benchmarks=peers)
        assert report.cohort_insufficient_count == 1
        assert report.subcap_drifts[0].bucket == "cohort_insufficient"
        assert report.subcap_drifts[0].drift_score is None
        # No pillar drift for P1 since the only subcap was skipped
        p1 = next(p for p in report.pillar_drifts if p.pillar == "P1")
        assert p1.drift_score is None
        assert p1.subcap_count == 0
        assert report.overall_drift is None

    def test_entity_missing_score_flagged(self) -> None:
        # Cohort knows P1C1.1.1 but entity doesn't
        report = compute_drift(
            entity_scores=[("P2C1.1.1", 3.0)],
            peer_benchmarks=[
                ("P1C1.1.1", 3.0, 5),
                ("P2C1.1.1", 3.5, 5),
            ],
        )
        assert report.entity_missing_count == 1
        missing = next(
            s for s in report.subcap_drifts if s.bucket == "entity_missing"
        )
        assert missing.subcap_id == "P1C1.1.1"
        assert missing.entity_score is None

    def test_lowered_min_n(self) -> None:
        scores = [("P1C1.1.1", 3.0)]
        peers = [("P1C1.1.1", 2.0, 2)]
        report = compute_drift(
            entity_scores=scores, peer_benchmarks=peers, min_n=1,
        )
        assert report.cohort_insufficient_count == 0
        assert report.subcap_drifts[0].bucket == "critical_high"

    def test_empty_inputs(self) -> None:
        report = compute_drift(entity_scores=[], peer_benchmarks=[])
        assert report.subcap_drifts == []
        assert report.overall_drift is None
        # All 4 pillar drifts present with None scores
        assert all(p.drift_score is None for p in report.pillar_drifts)
        assert [p.pillar for p in report.pillar_drifts] == list(PILLARS)

    def test_unknown_pillar_prefix_skipped_from_aggregate(self) -> None:
        # 'X1C1.1.1' is not a known pillar — should NOT contribute to
        # any pillar_drifts row, but should still appear in subcap_drifts.
        scores = [("X1C1.1.1", 3.0), ("P1C1.1.1", 4.0)]
        peers = [("X1C1.1.1", 2.0, 5), ("P1C1.1.1", 3.0, 5)]
        report = compute_drift(entity_scores=scores, peer_benchmarks=peers)
        # subcap row present for X1
        x1 = next(s for s in report.subcap_drifts if s.subcap_id == "X1C1.1.1")
        assert x1.pillar == "?"
        # P1's pillar_drift averages only the P1 subcap
        p1 = next(p for p in report.pillar_drifts if p.pillar == "P1")
        assert p1.subcap_count == 1
        assert p1.drift_score == 1.0  # 4.0 - 3.0

    def test_deterministic(self) -> None:
        # Same inputs in any order → identical report
        scores = [("P1C1.1.1", 3.0), ("P2C1.1.1", 2.5)]
        peers = [("P1C1.1.1", 2.0, 5), ("P2C1.1.1", 3.0, 5)]
        a = compute_drift(entity_scores=scores, peer_benchmarks=peers)
        b = compute_drift(
            entity_scores=list(reversed(scores)),
            peer_benchmarks=list(reversed(peers)),
        )
        assert [s.subcap_id for s in a.subcap_drifts] == \
               [s.subcap_id for s in b.subcap_drifts]
        assert a.overall_drift == b.overall_drift
