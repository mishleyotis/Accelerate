"""Tests for the global quick-search shaper (pure)."""
from __future__ import annotations

from app.services.search import (
    ENTITY_LIMIT,
    EVIDENCE_LIMIT,
    INSIGHT_LIMIT,
    build_search_results,
    subvertical_label,
)


class TestSubverticalLabel:
    def test_known_code_maps_to_human_label(self) -> None:
        assert subvertical_label("RB") == "Regional bank"
        assert subvertical_label("cu") == "Credit union"   # case-insensitive

    def test_unknown_or_missing_falls_back(self) -> None:
        assert subvertical_label("ZZ") == "Financial institution"
        assert subvertical_label(None) == "Financial institution"


class TestBuildSearchResults:
    def test_orders_entities_then_insights_then_evidence(self) -> None:
        hits = build_search_results(
            entities=[("alma-bank-0001", "Alma Bank", "RB")],
            insights=[("IC-012", "Fragmented data estate", "RISK", "alma-bank-0001")],
            evidence=[("E-031", "10-K risk factor", "T1", "alma-bank-0001")],
        )
        assert [h.kind for h in hits] == ["entity", "insight", "evidence"]

    def test_entity_hit_shape(self) -> None:
        (hit,) = build_search_results([("alma-bank-0001", "Alma Bank", "CL")], [], [])
        assert hit.kind == "entity"
        assert hit.title == "Alma Bank"
        assert hit.sub == "Commercial lender"
        assert hit.route == "/clients/alma-bank-0001/overview"
        assert hit.icon == "users"

    def test_insight_hit_routes_to_parent_with_card_param(self) -> None:
        (hit,) = build_search_results(
            [], [("IC-007", "Manual onboarding", "OPPORTUNITY", "wintrust-0002")], []
        )
        assert hit.kind == "insight"
        assert hit.title == "Manual onboarding"
        assert hit.sub == "IC-007 · OPPORTUNITY"
        assert hit.route == "/clients/wintrust-0002/insights?card=IC-007"
        assert hit.icon == "insight"

    def test_evidence_hit_routes_to_parent_with_evidence_param(self) -> None:
        (hit,) = build_search_results(
            [], [], [("E-019", "Earnings call transcript", "T2", "wintrust-0002")]
        )
        assert hit.kind == "evidence"
        assert hit.sub == "E-019 · T2"
        assert hit.route == "/clients/wintrust-0002/insights?evidence=E-019"
        assert hit.icon == "evidence"

    def test_insight_subtitle_omits_empty_severity(self) -> None:
        (hit,) = build_search_results([], [("IC-001", "Untriaged", None, "e-1")], [])
        assert hit.sub == "IC-001"

    def test_falls_back_to_id_when_title_missing(self) -> None:
        (ins,) = build_search_results([], [("IC-009", "", "RISK", "e-1")], [])
        assert ins.title == "IC-009"
        (ev,) = build_search_results([], [], [("E-009", "", "T1", "e-1")])
        assert ev.title == "E-009"

    def test_drops_rows_that_cannot_route(self) -> None:
        # NULL entity join / missing id → no dead-link rows.
        hits = build_search_results(
            entities=[("", "Ghost", "RB")],
            insights=[("IC-1", "Orphan insight", "RISK", "")],
            evidence=[("E-1", "Orphan evidence", "T1", "")],
        )
        assert hits == []

    def test_enforces_per_surface_caps(self) -> None:
        ents = [(f"e-{i}", f"Entity {i}", "RB") for i in range(ENTITY_LIMIT + 3)]
        ins = [(f"IC-{i}", f"Insight {i}", "RISK", "e-0") for i in range(INSIGHT_LIMIT + 3)]
        evs = [(f"E-{i}", f"Evidence {i}", "T1", "e-0") for i in range(EVIDENCE_LIMIT + 3)]
        hits = build_search_results(ents, ins, evs)
        kinds = [h.kind for h in hits]
        assert kinds.count("entity") == ENTITY_LIMIT
        assert kinds.count("insight") == INSIGHT_LIMIT
        assert kinds.count("evidence") == EVIDENCE_LIMIT

    def test_empty_inputs_yield_no_hits(self) -> None:
        assert build_search_results([], [], []) == []
