"""Tests for the customer_intelligence service.

State-transition coverage matrix (per scope §5 — all 5 branches):

  - first_run                 → test_single_run_velocity_is_null
  - incremental_update        → test_two_runs_velocity_per_year
  - re_ingest_same_request_id → test_re_ingest_same_request_id_state
  - gemini_unavailable        → test_state_classified_gemini_unavailable
  - validator_rejected        → test_state_classified_validator_rejected
"""
from __future__ import annotations

from datetime import datetime

from app.services.customer_intelligence import (
    RunSnapshot,
    build_summary_prompt,
    classify_state,
    compute_archetype_history,
    compute_gaps,
    compute_profile,
    compute_tech_drift,
    compute_themes,
    compute_velocity,
)


def _snap(
    *, run_id="R", request_id=None, when="2025-01-01T00:00:00+00:00",
    score=3.0, archetype=None, silhouette=None, themes=None,
    below=None, tech=None,
) -> RunSnapshot:
    return RunSnapshot(
        run_id=run_id, request_id=request_id,
        completed_at=datetime.fromisoformat(when),
        overall_score=score,
        pillar_scores={"P1": score, "P2": score, "P3": score, "P4": score},
        archetype=archetype, archetype_silhouette=silhouette,
        theme_tags=themes or [], below_median_subcap_ids=below or [],
        tech_stack=tech or [],
    )


class TestVelocity:
    def test_single_run_velocity_is_null(self) -> None:
        snaps = [_snap(score=3.0)]
        assert compute_velocity(snaps) is None

    def test_two_runs_velocity_per_year(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00", score=3.0),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00", score=3.4),
        ]
        v = compute_velocity(snaps)
        assert v is not None
        # 0.4 score / 1 year → 0.4 ± rounding
        assert abs(v - 0.4) < 0.02

    def test_six_month_gap_yields_doubled_yearly_velocity(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00", score=3.0),
            _snap(run_id="R2", when="2025-07-02T00:00:00+00:00", score=3.4),
        ]
        v = compute_velocity(snaps)
        assert v is not None
        # 0.4 / 0.5 year ≈ 0.8
        assert 0.75 <= v <= 0.85

    def test_too_close_returns_none(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00", score=3.0),
            _snap(run_id="R2", when="2025-01-10T00:00:00+00:00", score=3.4),
        ]
        assert compute_velocity(snaps) is None


class TestArchetypeAndThemes:
    def test_archetype_history_records_both_runs(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00",
                  archetype="compliance-first", silhouette=0.42),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00",
                  archetype="experience-first", silhouette=0.55),
        ]
        hist = compute_archetype_history(snaps)
        assert [h["archetype"] for h in hist] == [
            "compliance-first", "experience-first",
        ]
        assert hist[0]["silhouette"] == 0.42
        assert hist[1]["silhouette"] == 0.55

    def test_recurring_themes_appear_in_two_runs(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00",
                  themes=["aml", "data-governance"]),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00",
                  themes=["aml", "wealth-mgmt"]),
        ]
        recurring, emerging = compute_themes(snaps)
        assert recurring == ["aml"]
        assert emerging == ["wealth-mgmt"]


class TestGaps:
    def test_persistent_only_when_in_all_runs(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00",
                  below=["P1C1.1.1", "P2C2.1.1"]),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00",
                  below=["P1C1.1.1", "P3C1.1.1"]),
        ]
        persistent, closed = compute_gaps(snaps)
        assert persistent == ["P1C1.1.1"]
        # P2C2.1.1 was below-median in R1 but NOT in R2 → closed.
        assert closed == ["P2C2.1.1"]


class TestTechDrift:
    def test_additions_and_removals(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00",
                  tech=["FIS-IBS", "HubSpot"]),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00",
                  tech=["FIS-IBS", "Salesforce-FSC"]),
        ]
        adds, rems = compute_tech_drift(snaps)
        assert adds == ["Salesforce-FSC"]
        assert rems == ["HubSpot"]


class TestProfile:
    def test_full_profile_aggregation(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00",
                  score=3.0, archetype="compliance-first", silhouette=0.40,
                  themes=["aml"], below=["P1C1.1.1"]),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00",
                  score=3.4, archetype="experience-first", silhouette=0.55,
                  themes=["aml", "wealth"], below=["P1C1.1.1"]),
        ]
        p = compute_profile(snaps)
        assert p.total_runs == 2
        assert p.maturity_velocity is not None
        assert abs(p.maturity_velocity - 0.4) < 0.02
        assert p.recurring_themes == ["aml"]
        assert "wealth" in p.emerging_themes
        assert p.persistent_gap_subcap_ids == ["P1C1.1.1"]


class TestStateClassifier:
    def test_state_classified_first_run(self) -> None:
        assert classify_state(
            existing_profile=None, incoming_request_id="REQ-X",
            gemini_available=True, validator_passed=True,
        ) == "first_run"

    def test_state_classified_incremental(self) -> None:
        existing = {"maturity_history": [{"request_id": "REQ-A"}]}
        assert classify_state(
            existing_profile=existing, incoming_request_id="REQ-B",
            gemini_available=True, validator_passed=True,
        ) == "incremental_update"

    def test_re_ingest_same_request_id_state(self) -> None:
        existing = {"maturity_history": [{"request_id": "REQ-A"}]}
        assert classify_state(
            existing_profile=existing, incoming_request_id="REQ-A",
            gemini_available=True, validator_passed=True,
        ) == "re_ingest_same_request_id"

    def test_state_classified_gemini_unavailable(self) -> None:
        assert classify_state(
            existing_profile=None, incoming_request_id="REQ-X",
            gemini_available=False, validator_passed=True,
        ) == "gemini_unavailable"

    def test_state_classified_validator_rejected(self) -> None:
        assert classify_state(
            existing_profile=None, incoming_request_id="REQ-X",
            gemini_available=True, validator_passed=False,
        ) == "validator_rejected"


class TestPrompt:
    def test_prompt_includes_evidence_ids(self) -> None:
        snaps = [_snap(when="2025-01-01T00:00:00+00:00")]
        profile = compute_profile(snaps)
        prompt = build_summary_prompt(
            entity_name="Alma Bank", profile=profile,
            evidence_excerpts=[
                {"e_id": "E-001", "tier": 2, "excerpt": "10-K text"},
                {"e_id": "E-002", "tier": 3, "excerpt": "press release"},
            ],
        )
        assert "Alma Bank" in prompt
        assert "[E-001]" in prompt
        assert "[E-002]" in prompt
        assert "Do not invent E-IDs" in prompt

    def test_prompt_demands_synthesis_not_score_recap(self) -> None:
        # 2026-07-06 mandate: the executive summary must argue from the
        # evidence (systems/practices observed, gaps cited by E-ID, then the
        # recommended focus) — never recap scores or dump quotes.
        snaps = [_snap(when="2025-01-01T00:00:00+00:00")]
        prompt = build_summary_prompt(
            entity_name="Alma Bank", profile=compute_profile(snaps),
            evidence_excerpts=[{"e_id": "E-001", "tier": 2, "excerpt": "x"}],
        )
        assert "never a score recap" in prompt
        assert "name the systems and practices" in prompt
        assert "recommended focus" in prompt
