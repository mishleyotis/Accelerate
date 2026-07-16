"""Tests for the 4-zoom heatmap aggregator."""
from __future__ import annotations

import pytest

from app.services.heatmap_aggregator import (
    SubcapInput,
    aggregate_for_zoom,
)


def _sc(
    subcap_id: str,
    score: float,
    *,
    pillar: str = "P1",
    category: str = "P1C1",
    l1: str = "P1C1::strategy-vision",
    peer_median: float | None = None,
    is_thin: bool = False,
    cap: bool = False,
    aliased_from: str | None = None,
    band: str | None = None,
) -> SubcapInput:
    return SubcapInput(
        subcap_id=subcap_id,
        score=score,
        band=band or "M3",
        peer_median=peer_median,
        peer_gap=(round(score - peer_median, 2) if peer_median is not None else None),
        is_thin_evidence=is_thin,
        cap_applied=cap,
        cap_reason=None,
        aliased_from=aliased_from,
        pillar_id=pillar,
        category_id=category,
        l1_id=l1,
    )


class TestSubcapZoom:
    def test_emits_one_cell_per_subcap_sorted_by_id(self) -> None:
        inputs = [_sc("P1C1.1.2", 3.0), _sc("P1C1.1.1", 2.5)]
        agg = aggregate_for_zoom(inputs, "subcap")
        assert [c.id for c in agg.cells] == ["P1C1.1.1", "P1C1.1.2"]
        assert agg.cells[0].score == 2.5
        assert agg.cells[1].band == "M3"

    def test_alias_passes_through(self) -> None:
        inputs = [_sc("P1C1.1.1", 3.2, aliased_from="P1C1.1.1-old-v5")]
        agg = aggregate_for_zoom(inputs, "subcap")
        assert agg.cells[0].aliased_from == "P1C1.1.1-old-v5"

    def test_issue_count_pulled_from_overlay_map(self) -> None:
        inputs = [_sc("P1C1.1.1", 3.0)]
        agg = aggregate_for_zoom(inputs, "subcap",
                                  issue_counts_by_subcap={"P1C1.1.1": 4})
        assert agg.cells[0].issue_count == 4


class TestCapabilityZoom:
    def test_means_per_l1(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 2.0, l1="A"),
            _sc("P1C1.1.2", 4.0, l1="A"),
            _sc("P1C1.2.1", 3.0, l1="B"),
        ]
        agg = aggregate_for_zoom(inputs, "capability")
        by_id = {c.id: c for c in agg.cells}
        assert by_id["A"].score == 3.0  # (2+4)/2
        assert by_id["B"].score == 3.0
        assert by_id["A"].parent_id == "P1C1"  # category from child

    def test_thin_evidence_propagates_up(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 2.0, is_thin=True),
            _sc("P1C1.1.2", 4.0),
        ]
        agg = aggregate_for_zoom(inputs, "capability")
        assert agg.cells[0].is_thin_evidence is True

    def test_peer_gap_recomputed_at_aggregate_level(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 2.0, peer_median=3.0),
            _sc("P1C1.1.2", 4.0, peer_median=3.0),
        ]
        agg = aggregate_for_zoom(inputs, "capability")
        c = agg.cells[0]
        assert c.score == 3.0
        assert c.peer_median == 3.0
        assert c.peer_gap == 0.0


class TestCategoryAndPillarZoom:
    def test_category_zoom(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 2.0, category="P1C1"),
            _sc("P1C1.2.1", 4.0, category="P1C1"),
            _sc("P1C2.1.1", 3.0, category="P1C2"),
        ]
        agg = aggregate_for_zoom(inputs, "category")
        by_id = {c.id: c for c in agg.cells}
        assert by_id["P1C1"].score == 3.0
        assert by_id["P1C2"].score == 3.0
        assert by_id["P1C1"].parent_id == "P1"

    def test_pillar_zoom_rolls_up_across_categories(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 2.0, pillar="P1", category="P1C1"),
            _sc("P1C2.1.1", 4.0, pillar="P1", category="P1C2"),
            _sc("P2C1.1.1", 3.0, pillar="P2", category="P2C1"),
        ]
        agg = aggregate_for_zoom(inputs, "pillar")
        by_id = {c.id: c for c in agg.cells}
        assert by_id["P1"].score == 3.0
        assert by_id["P2"].score == 3.0
        assert by_id["P1"].parent_id is None
        # Pillar zoom drops the issue rationale (cap_reason is per-leaf only)
        assert by_id["P1"].cap_reason is None


class TestUnknownZoomRaises:
    def test_raises(self) -> None:
        with pytest.raises(ValueError):
            aggregate_for_zoom([], "galaxy")


class TestBandFromAverage:
    def test_band_derived_from_aggregate_score(self) -> None:
        inputs = [
            _sc("P1C1.1.1", 4.5, l1="X"),
            _sc("P1C1.1.2", 4.5, l1="X"),
        ]
        agg = aggregate_for_zoom(inputs, "capability")
        # mean 4.5 → M5
        assert agg.cells[0].band == "M5"
