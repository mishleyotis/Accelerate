"""Tests for the report-section → UI-surface router."""
from __future__ import annotations

from app.services.section_routing import (
    SECTION_TO_SURFACES,
    SectionPayload,
    build_narrative_context,
    build_narrative_health,
    build_narrative_heatmap,
    build_narrative_insights,
    build_narrative_overview,
    build_narrative_platform,
    narrative_state,
    sections_for_surface,
    surfaces_for_section,
)


def test_every_section_routes_somewhere() -> None:
    for section, surfaces in SECTION_TO_SURFACES.items():
        assert surfaces, f"{section} has no target surface"


def test_d1_overview_picks_up_scqa_and_benchmark_and_gap() -> None:
    secs = sections_for_surface("D1_overview")
    assert "executive_summary_scqa" in secs
    assert "benchmark_comparison" in secs
    assert "gap_prioritization" in secs


def test_d2_insights_picks_up_pillar_deep_dives() -> None:
    secs = sections_for_surface("D2_insights")
    for p in ("pillar_deep_dive_p1", "pillar_deep_dive_p2",
              "pillar_deep_dive_p3", "pillar_deep_dive_p4"):
        assert p in secs
    assert "recommendations" in secs


def test_d3_heatmap_consumes_issue_register_and_benchmark() -> None:
    secs = sections_for_surface("D3_heatmap")
    assert "issue_register" in secs
    assert "benchmark_comparison" in secs
    # And every pillar deep-dive feeds the rationale on heatmap drill
    for p in ("pillar_deep_dive_p1", "pillar_deep_dive_p2",
              "pillar_deep_dive_p3", "pillar_deep_dive_p4"):
        assert p in secs


def test_d4_platform_consumes_recs_roadmap_and_gap() -> None:
    secs = sections_for_surface("D4_platform")
    assert "recommendations" in secs
    assert "roadmap" in secs
    assert "gap_prioritization" in secs


def test_d5_context_picks_trend_analysis() -> None:
    secs = sections_for_surface("D5_context")
    assert "trend_analysis" in secs
    assert "issue_register" in secs


def test_d6_health_picks_data_gaps() -> None:
    secs = sections_for_surface("D6_health")
    assert "data_gaps" in secs


def test_evidence_registry_lands_on_drawer() -> None:
    assert surfaces_for_section("evidence_registry") == ["evidence_drawer"]


def test_surfaces_for_unknown_section_is_empty() -> None:
    assert surfaces_for_section("foo") == []  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Narrative bundle builders — state-transition matrix
# ----------------------------------------------------------------------

def _scqa() -> SectionPayload:
    return SectionPayload(
        kind="executive_summary_scqa",
        heading="Executive Summary",
        body_md="Situation: ABC. Complication: DEF.",
    )


def _pillar(n: int, subcaps: list[str] | None = None, e_ids: list[str] | None = None) -> SectionPayload:
    return SectionPayload(
        kind=f"pillar_deep_dive_p{n}",
        heading=f"Pillar {n}",
        body_md=f"Findings for P{n}.\n\nP{n}C1.1.1 scored 3.0.",
        linked_subcap_ids=subcaps or [f"P{n}C1.1.1"],
        linked_e_ids=e_ids or [f"E-{n}01"],
    )


class TestNarrativeOverview:
    def test_empty_sections_returns_none(self) -> None:
        assert build_narrative_overview([]) is None

    def test_scqa_only_populates_scqa_md(self) -> None:
        bundle = build_narrative_overview([_scqa()])
        assert bundle is not None
        assert "Situation" in bundle["scqa_md"]
        assert "benchmark_md" not in bundle or bundle.get("benchmark_md") is None

    def test_no_relevant_kinds_returns_none(self) -> None:
        bundle = build_narrative_overview([_pillar(1)])
        assert bundle is None


class TestNarrativeInsights:
    def test_per_pillar_keyed_correctly(self) -> None:
        sections = [_pillar(1), _pillar(2), _pillar(3), _pillar(4)]
        bundle = build_narrative_insights(sections)
        assert bundle is not None
        per = bundle["per_pillar"]
        assert {"P1", "P2", "P3", "P4"} <= set(per.keys())
        assert "P1C1.1.1" in per["P1"]["linked_subcap_ids"]

    def test_only_recommendations_populates_partial(self) -> None:
        recs = SectionPayload(
            kind="recommendations", heading="Recommendations",
            body_md="Adopt Salesforce.",
        )
        bundle = build_narrative_insights([recs])
        assert bundle is not None
        assert bundle["per_pillar"] is None
        assert "Adopt Salesforce" in bundle["recommendations_md"]


class TestNarrativeHeatmap:
    def test_per_subcap_derived_from_pillar_body(self) -> None:
        sec = SectionPayload(
            kind="pillar_deep_dive_p1",
            heading="Pillar 1",
            body_md="Strategy strong.\n\nP1C1.1.1 underperforms peers by 0.5.",
            linked_subcap_ids=["P1C1.1.1"],
        )
        bundle = build_narrative_heatmap([sec])
        assert bundle is not None
        assert "P1" in bundle["per_pillar_md"]
        assert "P1C1.1.1" in bundle["per_subcap_md"]
        assert "underperforms" in bundle["per_subcap_md"]["P1C1.1.1"]


class TestNarrativePlatform:
    def test_recommendations_and_roadmap_aggregated(self) -> None:
        recs = SectionPayload(kind="recommendations", heading="Recs", body_md="Buy.")
        rm = SectionPayload(kind="roadmap", heading="Roadmap", body_md="Phase 1.")
        bundle = build_narrative_platform([recs, rm])
        assert bundle is not None
        assert bundle["recommendations_md"] == "Buy."
        assert bundle["roadmap_md"] == "Phase 1."


class TestNarrativeContext:
    def test_trend_and_issues(self) -> None:
        trend = SectionPayload(kind="trend_analysis", heading="Trends", body_md="Up.")
        bundle = build_narrative_context([trend])
        assert bundle is not None
        assert bundle["trend_md"] == "Up."


class TestNarrativeHealth:
    def test_data_gaps_populates_field(self) -> None:
        gaps = SectionPayload(kind="data_gaps", heading="Data Gaps", body_md="Sparse.")
        bundle = build_narrative_health([gaps])
        assert bundle is not None
        assert bundle["data_gaps_md"] == "Sparse."


class TestNarrativeState:
    def test_empty_is_lineage_empty(self) -> None:
        assert narrative_state([]) == "lineage_empty"

    def test_partial_is_lineage_partial(self) -> None:
        sections = [_scqa()]
        assert narrative_state(sections) == "lineage_partial"

    def test_complete_is_lineage_complete(self) -> None:
        from app.services.section_routing import SectionPayload as SP
        kinds = [
            "executive_summary_scqa", "trend_analysis", "issue_register",
            "pillar_deep_dive_p1", "pillar_deep_dive_p2",
            "pillar_deep_dive_p3", "pillar_deep_dive_p4",
            "benchmark_comparison", "gap_prioritization",
            "recommendations", "roadmap",
        ]
        sections = [SP(kind=k, heading=k, body_md="x") for k in kinds]
        # 11 of 12 = 0.917, above 0.80 threshold
        assert narrative_state(sections) == "lineage_complete"
