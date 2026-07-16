"""Tests for the pure helpers in pattern_recognition.

The SQL-executing functions are covered by integration tests against a
live DB; here we lock down the cohort_case + vector formatting contracts.
"""
from __future__ import annotations

from app.services.pattern_recognition import (
    SimilarEvidence,
    SimilarInsight,
    SimilarRecommendation,
    _cohort_case,
    _format_vector,
)


class TestFormatVector:
    def test_simple_vector(self) -> None:
        s = _format_vector([0.1, 0.2, -0.3])
        assert s == "[0.10000000,0.20000000,-0.30000000]"

    def test_empty_vector(self) -> None:
        assert _format_vector([]) == "[]"

    def test_pgvector_text_shape(self) -> None:
        """pgvector accepts '[v1,v2,...]' literal; commas (no spaces) inside."""
        s = _format_vector([1.0, 2.0])
        assert s.startswith("[") and s.endswith("]")
        assert " " not in s  # no whitespace breaks pgvector parsing


class TestCohortCase:
    def test_empty_weights_returns_constant_zero(self) -> None:
        sql, params = _cohort_case({})
        assert "0::numeric" in sql
        assert params == {}

    def test_only_lob_overlap_falls_back_to_default(self) -> None:
        """If the only key is the synthetic __lob_overlap__, the CASE
        clause has no concrete subvertical to match — so we use the
        constant 0.3 fallback (matches the rag_cohort default weight for
        distant matches)."""
        sql, params = _cohort_case({"__lob_overlap__": 0.7})
        assert "0.3::numeric" in sql
        assert params == {}

    def test_builds_when_clauses_per_subvertical(self) -> None:
        sql, params = _cohort_case({"RB": 1.0, "CU": 0.6, "IB": 0.3})
        # 3 WHEN clauses
        assert sql.count("WHEN e.subvertical = :") == 3
        # All params for binds present
        assert any(v == "RB" for v in params.values())
        assert any(v == "CU" for v in params.values())
        assert any(v == 1.0 for v in params.values())
        assert any(v == 0.6 for v in params.values())
        # ELSE fallback included
        assert "ELSE 0.3::numeric END" in sql

    def test_skips_lob_overlap_marker_when_others_present(self) -> None:
        sql, _params = _cohort_case({"RB": 1.0, "__lob_overlap__": 0.7})
        # Only one real WHEN (for RB); the synthetic key is dropped from
        # the SQL CASE (LOB overlap is scored client-side, not here).
        assert sql.count("WHEN") == 1
        assert "lob_overlap" not in sql


class TestDataclasses:
    def test_similar_insight_frozen(self) -> None:
        s = SimilarInsight(
            insight_card_id="x", ic_id="IC-1", entity_name="X",
            title="t", severity="high", linked_subcap_id="P1C1.1.1",
            cohort_match=1.0, text_similarity=0.9, combined_score=0.9,
        )
        # Frozen → cannot mutate
        try:
            s.cohort_match = 0.5  # type: ignore[misc]
            raise AssertionError("expected frozen dataclass to raise")
        except Exception:
            pass

    def test_combined_score_field_present(self) -> None:
        ev = SimilarEvidence(
            evidence_id="x", e_id="E-1", entity_name="X",
            source_name="src", excerpt="...", tier=2,
            cohort_match=0.6, text_similarity=0.5, combined_score=0.3,
        )
        assert ev.combined_score == 0.3
        rec = SimilarRecommendation(
            recommendation_id="x", rec_id="REC-1", entity_name="X",
            title="t", platform_id=None,
            cohort_match=0.6, text_similarity=0.5, combined_score=0.3,
        )
        assert rec.platform_id is None
