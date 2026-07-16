"""Tests for the value-chain + capability + platform-area clustering."""
from __future__ import annotations

from app.services.value_chain import (
    SubcapForCluster,
    cluster_by_capability,
    cluster_by_platform_area,
    cluster_by_stage,
)


def _sc(
    sid: str,
    score: float | None,
    *,
    stages: list[str] | None = None,
    cap_id: str | None = None,
    cap_name: str | None = None,
    area_id: str | None = None,
    area_name: str | None = None,
) -> SubcapForCluster:
    return SubcapForCluster(
        subcap_id=sid,
        score=score,
        stages=stages or [],
        capability_id=cap_id,
        capability_name=cap_name,
        platform_area_id=area_id,
        platform_area_name=area_name,
    )


class TestClusterByStage:
    def test_groups_by_stage(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, stages=["Market", "Sales"]),
            _sc("P1C1.1.2", 4.0, stages=["Sales"]),
            _sc("P2C2.1.1", 2.5, stages=["Back Office"]),
        ]
        clusters = cluster_by_stage(subcaps)
        by_stage = {c.stage: c for c in clusters}
        assert set(by_stage.keys()) == {"Market", "Sales", "Back Office"}
        # P1C1.1.1 appears in BOTH Market and Sales
        assert "P1C1.1.1" in by_stage["Market"].subcap_ids
        assert "P1C1.1.1" in by_stage["Sales"].subcap_ids
        # Sales has both P1C1.1.1 and P1C1.1.2
        assert by_stage["Sales"].subcap_ids == ["P1C1.1.1", "P1C1.1.2"]
        # Average for Sales = (3.0 + 4.0) / 2 = 3.5
        assert by_stage["Sales"].average_score == 3.5

    def test_null_score_excluded_from_average_but_in_cluster(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", None, stages=["Market"]),
            _sc("P1C1.1.2", 4.0, stages=["Market"]),
        ]
        clusters = cluster_by_stage(subcaps)
        market = next(c for c in clusters if c.stage == "Market")
        assert market.cell_count == 2
        assert market.scored_cell_count == 1
        assert market.average_score == 4.0
        # Null-scored subcap still listed
        assert "P1C1.1.1" in market.subcap_ids

    def test_all_null_scores_average_is_none(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", None, stages=["Market"]),
            _sc("P1C1.1.2", None, stages=["Market"]),
        ]
        clusters = cluster_by_stage(subcaps)
        assert clusters[0].average_score is None

    def test_subcap_with_no_stages_excluded(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, stages=[]),
            _sc("P1C1.1.2", 4.0, stages=["Market"]),
        ]
        clusters = cluster_by_stage(subcaps)
        assert [c.stage for c in clusters] == ["Market"]
        assert "P1C1.1.1" not in clusters[0].subcap_ids

    def test_deterministic_ordering(self) -> None:
        subcaps = [
            _sc("P1C2.1.1", 3.0, stages=["Sales"]),
            _sc("P1C1.1.1", 3.0, stages=["Sales"]),
            _sc("P1C3.1.1", 3.0, stages=["Sales"]),
        ]
        clusters = cluster_by_stage(subcaps)
        # Subcap IDs sorted within each stage
        assert clusters[0].subcap_ids == ["P1C1.1.1", "P1C2.1.1", "P1C3.1.1"]


class TestClusterByCapability:
    def test_groups_by_capability(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, cap_id="cap_a", cap_name="Vision"),
            _sc("P1C1.1.2", 4.0, cap_id="cap_a", cap_name="Vision"),
            _sc("P1C1.2.1", 2.0, cap_id="cap_b", cap_name="OKR Cascade"),
        ]
        clusters = cluster_by_capability(subcaps)
        by_id = {c.capability_id: c for c in clusters}
        assert by_id["cap_a"].capability_name == "Vision"
        assert by_id["cap_a"].average_score == 3.5
        assert by_id["cap_a"].subcap_ids == ["P1C1.1.1", "P1C1.1.2"]
        assert by_id["cap_b"].average_score == 2.0

    def test_subcap_without_capability_id_skipped(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, cap_id=None),
            _sc("P1C1.1.2", 4.0, cap_id="cap_a", cap_name="X"),
        ]
        clusters = cluster_by_capability(subcaps)
        assert [c.capability_id for c in clusters] == ["cap_a"]

    def test_capability_name_falls_back_to_id(self) -> None:
        subcaps = [_sc("P1C1.1.1", 3.0, cap_id="cap_a", cap_name=None)]
        clusters = cluster_by_capability(subcaps)
        assert clusters[0].capability_name == "cap_a"


class TestClusterByPlatformArea:
    def test_groups_by_area(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, area_id="salesforce_core", area_name="Salesforce Core"),
            _sc("P1C1.1.2", 4.0, area_id="salesforce_core", area_name="Salesforce Core"),
            _sc("P2C1.1.1", 2.0, area_id="data_cloud", area_name="Data Cloud"),
        ]
        clusters = cluster_by_platform_area(subcaps)
        by_id = {c.platform_area_id: c for c in clusters}
        assert by_id["salesforce_core"].platform_area_name == "Salesforce Core"
        assert by_id["salesforce_core"].average_score == 3.5
        assert by_id["data_cloud"].subcap_ids == ["P2C1.1.1"]

    def test_subcaps_without_area_skipped(self) -> None:
        subcaps = [
            _sc("P1C1.1.1", 3.0, area_id=None),
            _sc("P1C1.1.2", 4.0, area_id="x", area_name="X"),
        ]
        clusters = cluster_by_platform_area(subcaps)
        assert [c.platform_area_id for c in clusters] == ["x"]


class TestEmptyInput:
    def test_no_subcaps_emits_no_clusters(self) -> None:
        assert cluster_by_stage([]) == []
        assert cluster_by_capability([]) == []
        assert cluster_by_platform_area([]) == []
