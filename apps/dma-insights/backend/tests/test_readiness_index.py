"""Tests for the platform readiness traffic-light aggregator."""
from __future__ import annotations

from app.services.readiness_index import (
    aggregate_readiness,
    evaluate_prereq,
)


class TestEvaluatePrereq:
    def test_met_when_score_meets_threshold(self) -> None:
        c = evaluate_prereq(
            name="data_cloud_ready", required_subcap_id="P4C1.1.1",
            threshold=3.5, scores_by_subcap={"P4C1.1.1": 3.5},
        )
        assert c.status == "MET"

    def test_partial_within_half_band(self) -> None:
        c = evaluate_prereq(
            name="x", required_subcap_id="P1C1.1.1",
            threshold=3.5, scores_by_subcap={"P1C1.1.1": 3.0},
        )
        assert c.status == "PARTIAL"

    def test_unmet_more_than_half_below(self) -> None:
        c = evaluate_prereq(
            name="x", required_subcap_id="P1C1.1.1",
            threshold=3.5, scores_by_subcap={"P1C1.1.1": 2.0},
        )
        assert c.status == "UNMET"

    def test_missing_when_no_score(self) -> None:
        c = evaluate_prereq(
            name="x", required_subcap_id="P1C9.9.9",
            threshold=3.5, scores_by_subcap={},
        )
        assert c.status == "MISSING"
        assert c.current_score is None


class TestAggregateReadiness:
    def test_empty_is_amber(self) -> None:
        assert aggregate_readiness([]) == "amber"

    def test_all_met_is_green(self) -> None:
        from app.services.readiness_index import PrereqCheck
        checks = [
            PrereqCheck("a", "P1C1.1.1", 3.5, "MET", 4.0),
            PrereqCheck("b", "P2C1.1.1", 3.0, "MET", 3.0),
        ]
        assert aggregate_readiness(checks) == "green"

    def test_any_unmet_is_red(self) -> None:
        from app.services.readiness_index import PrereqCheck
        checks = [
            PrereqCheck("a", "P1C1.1.1", 3.5, "MET", 4.0),
            PrereqCheck("b", "P2C1.1.1", 3.5, "UNMET", 2.0),
            PrereqCheck("c", "P3C1.1.1", 3.5, "PARTIAL", 3.0),
        ]
        assert aggregate_readiness(checks) == "red"

    def test_partial_only_is_amber(self) -> None:
        from app.services.readiness_index import PrereqCheck
        checks = [
            PrereqCheck("a", "P1C1.1.1", 3.5, "MET", 4.0),
            PrereqCheck("b", "P2C1.1.1", 3.5, "PARTIAL", 3.1),
        ]
        assert aggregate_readiness(checks) == "amber"

    def test_missing_is_treated_as_red(self) -> None:
        from app.services.readiness_index import PrereqCheck
        checks = [
            PrereqCheck("a", "P1C1.1.1", 3.5, "MET", 4.0),
            PrereqCheck("b", "P2C1.1.1", 3.5, "MISSING", None),
        ]
        # MISSING → cannot claim readiness → red
        assert aggregate_readiness(checks) == "red"
