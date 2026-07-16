"""Tests for the pattern schemas — score bounds + cohort_mode field."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.patterns import (
    RecurringSubcapResponse,
    RecurringSubcapTheme,
    SimilarInsightOut,
    SimilarInsightsResponse,
    SimilarRecommendationOut,
)


class TestSimilarInsightOut:
    def _ok(self, **overrides) -> dict:
        base = {
            "insight_card_id": "11111111-1111-1111-1111-111111111111",
            "ic_id": "IC-9",
            "entity_name": "Anchor FCU",
            "title": "Paper-driven origination",
            "severity": "high",
            "linked_subcap_id": "P1C1.1.1",
            "cohort_match": 0.6,
            "text_similarity": 0.85,
            "combined_score": 0.51,
        }
        base.update(overrides)
        return base

    def test_round_trip(self) -> None:
        m = SimilarInsightOut.model_validate(self._ok())
        assert m.combined_score == 0.51

    def test_cohort_match_bounded(self) -> None:
        with pytest.raises(ValidationError):
            SimilarInsightOut.model_validate(self._ok(cohort_match=1.5))
        with pytest.raises(ValidationError):
            SimilarInsightOut.model_validate(self._ok(cohort_match=-0.1))

    def test_text_similarity_bounded(self) -> None:
        with pytest.raises(ValidationError):
            SimilarInsightOut.model_validate(self._ok(text_similarity=1.5))


class TestSimilarInsightsResponse:
    def test_empty_items_ok(self) -> None:
        r = SimilarInsightsResponse(
            seed_ic_id="IC-1", cohort_mode="single", items=[],
        )
        assert r.items == []
        assert r.cohort_mode == "single"


class TestSimilarRecommendationOut:
    def test_optional_platform_id(self) -> None:
        m = SimilarRecommendationOut(
            recommendation_id="x", rec_id="REC-1",
            entity_name="X", title="t",
            cohort_match=1.0, text_similarity=0.9, combined_score=0.9,
        )
        assert m.platform_id is None


class TestRecurringSubcapResponse:
    def test_themes_sortable(self) -> None:
        r = RecurringSubcapResponse(
            subcap_id="P1C1.1.1", cohort_mode="multi_lob",
            themes=[
                RecurringSubcapTheme(
                    title="Paper origination", severity="high",
                    occurrence_count=12, sample_entities=["A", "B"],
                ),
                RecurringSubcapTheme(
                    title="No member portal", severity="medium",
                    occurrence_count=5, sample_entities=["C"],
                ),
            ],
        )
        # We don't sort in the schema, but verifying field presence.
        assert r.themes[0].occurrence_count == 12
        assert r.themes[1].sample_entities == ["C"]
