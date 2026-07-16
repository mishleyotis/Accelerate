"""Pure-logic tests for `app.services.prompt_quality`.

The DB-touching aggregator paths (`rollup_by_surface_and_version`,
`rollup_by_surface`, `compare_versions`) are covered by the broader
e2e suite + the admin-router integration. These tests pin the
primitives that determine "is v2 actually better than v1?" — the
verdict math the operator reads on the Admin → Prompt Quality table.

Contracts asserted here:
  - `_safe_rate` is bounded [0.0, 1.0] AND zero-call-safe (no 0/0).
  - `_classify_verdict` correctly routes to one of the 4 verdict
    strings based on sample size + tie-band gates.
  - `_MIN_RESPONSES_FOR_VERDICT` is the documented sample floor (25),
    `_TIE_BAND` is the documented absolute tie threshold (0.02 = 2pp).
  - The three dataclasses (`SurfaceVersionRollup`, `SurfaceRollup`,
    `VersionDiff`) are constructable + carry the keys the admin
    `PromptQualityResponse` schema enumerates.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.prompt_quality import (
    _MIN_RESPONSES_FOR_VERDICT,
    _TIE_BAND,
    SurfaceRollup,
    SurfaceVersionRollup,
    VersionDiff,
    _classify_verdict,
    _safe_rate,
)

# ---------------------------------------------------------------------------
# _safe_rate
# ---------------------------------------------------------------------------


class TestSafeRate:
    def test_zero_denom_returns_zero(self) -> None:
        assert _safe_rate(0, 0) == 0.0

    def test_zero_numer_returns_zero(self) -> None:
        assert _safe_rate(0, 10) == 0.0

    def test_normal_case(self) -> None:
        assert _safe_rate(3, 10) == 0.3

    def test_numerator_exceeds_denominator_clamps_to_one(self) -> None:
        # Should never happen in practice (attribution can't exceed
        # totals) but the bound is real defensively.
        assert _safe_rate(15, 10) == 1.0

    def test_negative_numerator_clamps_to_zero(self) -> None:
        assert _safe_rate(-5, 10) == 0.0

    def test_negative_denominator_returns_zero(self) -> None:
        # Treated as the zero-denom case.
        assert _safe_rate(5, -1) == 0.0

    def test_full_hallucination(self) -> None:
        assert _safe_rate(10, 10) == 1.0

    @pytest.mark.parametrize("numer,denom,expected", [
        (1, 4, 0.25),
        (3, 4, 0.75),
        (7, 100, 0.07),
        (1, 1000, 0.001),
    ])
    def test_various_normal_rates(self, numer: int, denom: int, expected: float) -> None:
        assert abs(_safe_rate(numer, denom) - expected) < 1e-9


# ---------------------------------------------------------------------------
# _classify_verdict
# ---------------------------------------------------------------------------


class TestClassifyVerdict:
    def test_insufficient_data_baseline_below_floor(self) -> None:
        assert _classify_verdict(
            baseline_rate=0.10, candidate_rate=0.02,
            baseline_n=_MIN_RESPONSES_FOR_VERDICT - 1, candidate_n=200,
        ) == "insufficient_data"

    def test_insufficient_data_candidate_below_floor(self) -> None:
        assert _classify_verdict(
            baseline_rate=0.10, candidate_rate=0.02,
            baseline_n=200, candidate_n=_MIN_RESPONSES_FOR_VERDICT - 1,
        ) == "insufficient_data"

    def test_insufficient_data_both_at_zero(self) -> None:
        assert _classify_verdict(0.0, 0.0, 0, 0) == "insufficient_data"

    def test_candidate_better_meaningful_drop(self) -> None:
        # 12% → 3% halluc rate after the prompt rewrite.
        assert _classify_verdict(0.12, 0.03, 200, 200) == "candidate_better"

    def test_candidate_worse_meaningful_rise(self) -> None:
        assert _classify_verdict(0.03, 0.12, 200, 200) == "candidate_worse"

    def test_tie_below_band(self) -> None:
        # 1pp difference — not actionable.
        assert _classify_verdict(0.05, 0.06, 200, 200) == "tie"

    def test_tie_exactly_at_band_is_NOT_tie(self) -> None:
        # 2pp difference exactly — _TIE_BAND uses strict `<`, so 2pp
        # = NOT tie. (Defensive: avoids floating-point flakiness right
        # at the band edge.)
        assert _classify_verdict(0.05, 0.05 + _TIE_BAND, 200, 200) != "tie"

    def test_min_responses_floor_documented(self) -> None:
        """The floor is 25; that's the contract the admin panel
        communicates ("collecting samples…" badge until reached)."""
        assert _MIN_RESPONSES_FOR_VERDICT == 25

    def test_tie_band_documented(self) -> None:
        """2pp = the documented threshold below which the prompt
        change is judged statistically/operationally indistinguishable."""
        assert _TIE_BAND == 0.02

    def test_exactly_at_floor_is_sufficient(self) -> None:
        # Floor itself counts (>=, not >).
        assert _classify_verdict(
            0.10, 0.02,
            _MIN_RESPONSES_FOR_VERDICT, _MIN_RESPONSES_FOR_VERDICT,
        ) == "candidate_better"


# ---------------------------------------------------------------------------
# Dataclass shape contract
# ---------------------------------------------------------------------------


class TestDataclassShapes:
    def test_surface_version_rollup_carries_all_admin_response_keys(self) -> None:
        """The PromptQualityVersionRow schema mirrors this shape; if
        the dataclass loses a field the admin endpoint's projector
        crashes with AttributeError. Pin the field list."""
        r = SurfaceVersionRollup(
            surface="rag_answer",
            prompt_template_version="v2",
            total_responses=120,
            total_hallucinations=4,
            hallucination_rate=0.033,
            prompt_tokens=12_000,
            completion_tokens=3_000,
            estimated_cost_usd=0.105,
            first_seen=datetime(2026, 5, 1),
            last_seen=datetime(2026, 6, 1),
            is_active_version=True,
        )
        for attr in (
            "surface", "prompt_template_version", "total_responses",
            "total_hallucinations", "hallucination_rate", "prompt_tokens",
            "completion_tokens", "estimated_cost_usd", "first_seen",
            "last_seen", "is_active_version",
        ):
            assert hasattr(r, attr)
        assert r.is_active_version is True

    def test_surface_rollup_carries_all_admin_response_keys(self) -> None:
        r = SurfaceRollup(
            surface="rag_answer", versions_observed=2,
            active_version="v2", total_responses=240,
            total_hallucinations=9, hallucination_rate=0.0375,
            estimated_cost_usd=0.21,
        )
        for attr in (
            "surface", "versions_observed", "active_version",
            "total_responses", "total_hallucinations",
            "hallucination_rate", "estimated_cost_usd",
        ):
            assert hasattr(r, attr)

    def test_version_diff_carries_all_admin_response_keys(self) -> None:
        d = VersionDiff(
            surface="rag_answer",
            baseline_version="v1", candidate_version="v2",
            baseline_hallucination_rate=0.12,
            candidate_hallucination_rate=0.03,
            rate_delta=-0.09,
            baseline_responses=200, candidate_responses=200,
            verdict="candidate_better",
        )
        for attr in (
            "surface", "baseline_version", "candidate_version",
            "baseline_hallucination_rate", "candidate_hallucination_rate",
            "rate_delta", "baseline_responses", "candidate_responses",
            "verdict",
        ):
            assert hasattr(d, attr)
        # Negative delta = candidate's rate is lower than baseline's
        # = candidate is better (fewer hallucinations).
        assert d.rate_delta < 0
        assert d.verdict == "candidate_better"

    def test_active_version_flag_is_bool(self) -> None:
        """The frontend keys on `is_active_version` to render the
        "(active)" pill — must be a real bool, not a truthy string."""
        r = SurfaceVersionRollup(
            surface="rag_answer", prompt_template_version="v2",
            total_responses=0, total_hallucinations=0,
            hallucination_rate=0.0, prompt_tokens=0,
            completion_tokens=0, estimated_cost_usd=0.0,
            first_seen=None, last_seen=None,
            is_active_version=True,
        )
        assert isinstance(r.is_active_version, bool)


# ---------------------------------------------------------------------------
# Verdict string vocabulary lock
# ---------------------------------------------------------------------------


def test_verdict_string_vocabulary_is_stable() -> None:
    """The PromptQualityVersionDiffRow schema uses a Literal of these
    4 strings. Changing one without updating the schema → Pydantic
    validation crashes at response-serialization time. Pin it here."""
    seen = set()
    cases = [
        (0.10, 0.02, 200, 200),  # candidate_better
        (0.02, 0.10, 200, 200),  # candidate_worse
        (0.05, 0.06, 200, 200),  # tie
        (0.10, 0.02, 200, 1),    # insufficient_data
    ]
    for br, cr, bn, cn in cases:
        seen.add(_classify_verdict(br, cr, bn, cn))
    assert seen == {
        "candidate_better", "candidate_worse", "tie", "insufficient_data",
    }


# ---------------------------------------------------------------------------
# Admin endpoint wiring
# ---------------------------------------------------------------------------


def test_prompt_quality_endpoint_is_registered() -> None:
    """The admin router must expose GET /api/v1/admin/prompt-quality
    so the future FE admin tile can consume it. If the @router.get
    decorator disappears the FE silently 404s."""
    from app.routers.admin import router

    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/api/v1/admin/prompt-quality" in paths


def test_prompt_quality_response_schema_matches_dataclasses() -> None:
    """The Pydantic response model has fields the dataclass producer
    can supply — a smoke check that no field has drifted."""
    from app.schemas.admin import (
        PromptQualityResponse,
        PromptQualitySurfaceRow,
        PromptQualityVersionDiffRow,
        PromptQualityVersionRow,
    )

    sv = PromptQualityVersionRow(
        surface="rag_answer", prompt_template_version="v2",
        total_responses=10, total_hallucinations=1,
        hallucination_rate=0.1, prompt_tokens=100, completion_tokens=50,
        estimated_cost_usd=0.001, first_seen=None, last_seen=None,
        is_active_version=True,
    )
    sr = PromptQualitySurfaceRow(
        surface="rag_answer", versions_observed=1,
        active_version="v2", total_responses=10, total_hallucinations=1,
        hallucination_rate=0.1, estimated_cost_usd=0.001,
    )
    dr = PromptQualityVersionDiffRow(
        surface="rag_answer", baseline_version="v1",
        candidate_version="v2",
        baseline_hallucination_rate=0.2, candidate_hallucination_rate=0.1,
        rate_delta=-0.1, baseline_responses=200, candidate_responses=200,
        verdict="candidate_better",
    )
    resp = PromptQualityResponse(
        by_surface=[sr], by_version=[sv], version_diffs=[dr],
        window_days=30,
    )
    # The 4 verdicts in the Literal type — proven at construction.
    for v in ("candidate_better", "candidate_worse", "tie", "insufficient_data"):
        PromptQualityVersionDiffRow(
            surface="x", baseline_version="a", candidate_version="b",
            baseline_hallucination_rate=0.0,
            candidate_hallucination_rate=0.0,
            rate_delta=0.0, baseline_responses=0, candidate_responses=0,
            verdict=v,  # type: ignore[arg-type]
        )
    assert resp.window_days == 30
    assert len(resp.by_version) == 1
    assert resp.by_version[0].is_active_version is True
