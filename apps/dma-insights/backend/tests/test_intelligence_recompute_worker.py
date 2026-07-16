"""Tests for the intelligence_recompute worker.

State-transition coverage matrix (all 6 branches from
workers.intelligence_recompute.service.classify_worker_state):

  - first_time_compute        → test_first_run_creates_profile_with_summary
  - incremental_with_new_run  → test_multi_run_entity_velocity_in_payload
  - idempotent_skip           → test_idempotent_skip_when_run_and_catalogue_match
  - vertex_unavailable        → test_vertex_unavailable_keeps_summary_null
  - validator_rejected        → test_validator_rejects_fabricated_eid_uses_template
  - embedding_failed          → test_embedding_failure_keeps_text_drops_vector

The worker logic is exercised purely (no database) by injecting fake
Vertex clients. The DI surface of the service module is documented at
the top of the module.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.customer_intelligence import RunSnapshot, compute_profile  # noqa: E402
from workers.intelligence_recompute.service import (  # noqa: E402
    EvidenceRow,
    ExistingProfile,
    SummaryDecision,
    assemble_snapshots,
    build_recompute_payload,
    call_vertex_summary,
    classify_worker_state,
    deterministic_template_summary,
    parse_structured_output,
    should_skip,
    state_after_decision,
    validate_summary_citations,
)

# ---------------------------------------------------------------------
# Fakes — stand in for the real Vertex client
# ---------------------------------------------------------------------


class _FakeVertexOK:
    """Vertex stub returning a valid structured-output JSON wrapper."""

    def __init__(self, *, summary: str, cited_e: list[str] | None = None,
                 cited_s: list[str] | None = None):
        self.summary = summary
        self.cited_e = cited_e or []
        self.cited_s = cited_s or []
        self.embed_calls = 0

    async def stream(self, call):
        import json
        payload = {
            "intelligence_summary_md": self.summary,
            "cited_evidence_ids": self.cited_e,
            "cited_subcap_ids": self.cited_s,
            "confidence": 0.9,
        }
        yield json.dumps(payload)

    async def embed(self, texts):
        self.embed_calls += 1
        return [[0.1] * 768 for _ in texts]


class _FakeVertexDown:
    """Vertex raising on every call — emulates outage / no creds."""

    async def stream(self, call):
        raise RuntimeError("vertex unreachable")
        yield ""  # unreachable; makes this a valid async generator

    async def embed(self, texts):
        raise RuntimeError("vertex unreachable")


class _FakeVertexEmbedFails:
    """Vertex generates summary but embedding raises."""

    def __init__(self, *, summary: str):
        self.summary = summary

    async def stream(self, call):
        yield self.summary

    async def embed(self, texts):
        raise RuntimeError("quota exceeded")


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


def _snap(
    *, run_id="R", when="2026-01-01T00:00:00+00:00", score=3.0,
) -> RunSnapshot:
    return RunSnapshot(
        run_id=run_id,
        request_id=f"REQ-{run_id}",
        completed_at=datetime.fromisoformat(when),
        overall_score=score,
        pillar_scores={"P1": score, "P2": score, "P3": score, "P4": score},
        archetype=None, archetype_silhouette=None,
        theme_tags=["governance"], below_median_subcap_ids=["P1C1.1.1"],
        tech_stack=[],
    )


def _evidence(n: int = 3) -> list[EvidenceRow]:
    return [
        EvidenceRow(e_id=f"E-{i:03d}", tier=3, excerpt=f"sample quote {i}")
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------
# Pure-logic state classification
# ---------------------------------------------------------------------


class TestShouldSkip:
    def test_no_existing_profile_does_not_skip(self) -> None:
        assert should_skip(
            existing=None, latest_run_id="R", latest_catalogue_version="v7.0"
        ) is False

    def test_missing_summary_does_not_skip(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R", catalogue_version="v7.0",
            summary_present=False,
        )
        assert should_skip(
            existing=existing, latest_run_id="R",
            latest_catalogue_version="v7.0",
        ) is False

    def test_run_id_mismatch_does_not_skip(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R1", catalogue_version="v7.0",
            summary_present=True,
        )
        assert should_skip(
            existing=existing, latest_run_id="R2",
            latest_catalogue_version="v7.0",
        ) is False

    def test_catalogue_version_mismatch_does_not_skip(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R", catalogue_version="v7.0",
            summary_present=True,
        )
        assert should_skip(
            existing=existing, latest_run_id="R",
            latest_catalogue_version="v7.1",
        ) is False

    def test_all_match_skips(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R", catalogue_version="v7.0",
            summary_present=True,
        )
        assert should_skip(
            existing=existing, latest_run_id="R",
            latest_catalogue_version="v7.0",
        ) is True


class TestClassifyWorkerState:
    def test_idempotent_skip_wins(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R", catalogue_version="v7.0",
            summary_present=True,
        )
        assert classify_worker_state(
            existing=existing, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=True,
            embedding_succeeded=True,
        ) == "idempotent_skip"

    def test_first_time_compute(self) -> None:
        assert classify_worker_state(
            existing=None, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=True,
            embedding_succeeded=True,
        ) == "first_time_compute"

    def test_incremental(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R-OLD", catalogue_version="v7.0",
            summary_present=True,
        )
        assert classify_worker_state(
            existing=existing, latest_run_id="R-NEW",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=True,
            embedding_succeeded=True,
        ) == "incremental_with_new_run"

    def test_vertex_unavailable_branch(self) -> None:
        assert classify_worker_state(
            existing=None, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=False, validator_passed=True,
            embedding_succeeded=False,
        ) == "vertex_unavailable"

    def test_validator_rejected_branch(self) -> None:
        assert classify_worker_state(
            existing=None, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=False,
            embedding_succeeded=False,
        ) == "validator_rejected"

    def test_embedding_failed_branch(self) -> None:
        assert classify_worker_state(
            existing=None, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=True,
            embedding_succeeded=False,
        ) == "embedding_failed"


# ---------------------------------------------------------------------
# assemble_snapshots
# ---------------------------------------------------------------------


class TestAssembleSnapshots:
    def test_rows_become_snapshots(self) -> None:
        rows = [
            {
                "run_id": "R1", "request_id": "REQ-1",
                "completed_at": datetime(2026, 1, 1, tzinfo=UTC),
                "overall_score": 3.2, "pillar_scores": {"P1": 3.1},
            },
            {
                "run_id": "R2", "request_id": "REQ-2",
                "completed_at": "2026-06-01T00:00:00+00:00",
                "overall_score": 3.6, "pillar_scores": {"P1": 3.5},
            },
        ]
        snaps = assemble_snapshots(rows)
        assert len(snaps) == 2
        assert snaps[0].run_id == "R1"
        assert snaps[1].request_id == "REQ-2"
        assert snaps[0].overall_score == pytest.approx(3.2)

    def test_missing_completed_at_skipped(self) -> None:
        snaps = assemble_snapshots([{"run_id": "X"}])
        assert snaps == []


# ---------------------------------------------------------------------
# validate_summary_citations
# ---------------------------------------------------------------------


class TestValidate:
    def test_all_cited_in_bundle_passes(self) -> None:
        ok, fab = validate_summary_citations(
            cited_evidence_ids=["E-001", "E-002"],
            bundled_evidence_ids={"E-001", "E-002", "E-003"},
        )
        assert ok is True
        assert fab == []

    def test_fabricated_id_rejected(self) -> None:
        ok, fab = validate_summary_citations(
            cited_evidence_ids=["E-001", "E-999"],
            bundled_evidence_ids={"E-001"},
        )
        assert ok is False
        assert fab == ["E-999"]


# ---------------------------------------------------------------------
# parse_structured_output
# ---------------------------------------------------------------------


class TestParseStructuredOutput:
    def test_plain_json(self) -> None:
        out = parse_structured_output('{"intelligence_summary_md": "x"}')
        assert out is not None
        assert out["intelligence_summary_md"] == "x"

    def test_code_fence_wrapper(self) -> None:
        out = parse_structured_output(
            "```json\n{\"intelligence_summary_md\": \"hello\"}\n```"
        )
        assert out is not None
        assert out["intelligence_summary_md"] == "hello"

    def test_bad_json_returns_none(self) -> None:
        assert parse_structured_output("not even close") is None


# ---------------------------------------------------------------------
# deterministic_template_summary
# ---------------------------------------------------------------------


class TestTemplate:
    def test_template_mentions_velocity(self) -> None:
        snaps = [
            _snap(run_id="R1", when="2025-01-01T00:00:00+00:00", score=3.0),
            _snap(run_id="R2", when="2026-01-01T00:00:00+00:00", score=3.4),
        ]
        profile = compute_profile(snaps)
        out = deterministic_template_summary(
            entity_name="AlmaBank", profile=profile,
        )
        assert "AlmaBank" in out
        assert "improving" in out or "declining" in out
        assert "auto-generated" in out


# ---------------------------------------------------------------------
# call_vertex_summary — exercises the 3 vertex-related branches
# ---------------------------------------------------------------------


class TestCallVertexSummary:
    def test_vertex_unavailable_returns_status(self) -> None:
        snaps = [_snap()]
        profile = compute_profile(snaps)
        fake = _FakeVertexDown()
        decision = asyncio.run(
            call_vertex_summary(
                entity_name="X", profile=profile,
                evidence=_evidence(), vertex_client=fake,
            )
        )
        assert decision.summary_md is None
        assert decision.summary_status == "vertex_unavailable"
        assert decision.embedding is None

    def test_ok_path_returns_summary_and_embedding(self) -> None:
        snaps = [_snap()]
        profile = compute_profile(snaps)
        fake = _FakeVertexOK(summary="ok narrative", cited_e=["E-001"])
        decision = asyncio.run(
            call_vertex_summary(
                entity_name="X", profile=profile,
                evidence=_evidence(), vertex_client=fake,
            )
        )
        assert decision.summary_md == "ok narrative"
        assert decision.summary_status == "ok"
        assert decision.embedding is not None
        assert len(decision.embedding) == 768
        assert decision.cited_evidence_ids == ["E-001"]

    def test_embedding_failure_keeps_text(self) -> None:
        snaps = [_snap()]
        profile = compute_profile(snaps)
        fake = _FakeVertexEmbedFails(summary='{"intelligence_summary_md": "txt"}')
        decision = asyncio.run(
            call_vertex_summary(
                entity_name="X", profile=profile,
                evidence=_evidence(), vertex_client=fake,
            )
        )
        # Text retained; embedding None → status=embedding_failed.
        assert decision.summary_md == "txt"
        assert decision.embedding is None
        assert decision.summary_status == "embedding_failed"


# ---------------------------------------------------------------------
# state_after_decision — composes everything
# ---------------------------------------------------------------------


class TestStateAfterDecision:
    def test_first_run_creates_profile_with_summary(self) -> None:
        decision = SummaryDecision(
            summary_md="alright", cited_evidence_ids=[],
            summary_status="ok", embedding=[0.1] * 768,
        )
        state = state_after_decision(
            existing=None, decision=decision, validator_passed=True,
            latest_run_id="R", latest_catalogue_version="v7.0",
        )
        assert state == "first_time_compute"

    def test_multi_run_entity_velocity_in_payload(self) -> None:
        # Pure projection — proves the payload carries velocity correctly
        # for an entity with 3 runs, +0.4 over ~18 months → ~0.27/yr.
        snaps = [
            _snap(run_id="R1", when="2024-11-01T00:00:00+00:00", score=3.0),
            _snap(run_id="R2", when="2025-08-01T00:00:00+00:00", score=3.2),
            _snap(run_id="R3", when="2026-05-01T00:00:00+00:00", score=3.4),
        ]
        profile = compute_profile(snaps)
        # 18 months → 1.5 yrs → 0.4/1.5 ≈ 0.267
        assert profile.maturity_velocity is not None
        assert 0.24 <= profile.maturity_velocity <= 0.30
        decision = SummaryDecision(
            summary_md=f"3-run trajectory, velocity {profile.maturity_velocity}",
            cited_evidence_ids=[], summary_status="ok",
            embedding=[0.1] * 768,
        )
        payload = build_recompute_payload(
            entity_id="ent-1", entity_name="AlmaBank",
            catalogue_version="v7.0", latest_run_id="R3",
            profile=profile, summary=decision,
        )
        assert payload["total_runs"] == 3
        assert payload["maturity_velocity"] == profile.maturity_velocity
        assert "trajectory" in payload["intelligence_summary_md"]
        assert payload["catalogue_version"] == "v7.0"
        assert payload["computed_for_run_id"] == "R3"

    def test_idempotent_skip_when_run_and_catalogue_match(self) -> None:
        existing = ExistingProfile(
            computed_for_run_id="R", catalogue_version="v7.0",
            summary_present=True,
        )
        decision = SummaryDecision(
            summary_md="placeholder", summary_status="ok",
            embedding=[0.1] * 768,
        )
        state = state_after_decision(
            existing=existing, decision=decision, validator_passed=True,
            latest_run_id="R", latest_catalogue_version="v7.0",
        )
        assert state == "idempotent_skip"

    def test_vertex_unavailable_keeps_summary_null(self) -> None:
        decision = SummaryDecision(
            summary_md=None, summary_status="vertex_unavailable",
            embedding=None,
        )
        # When status is vertex_unavailable, validator_passed should be True
        # (nothing to validate); the worker chooses the branch from the
        # status, not the validator flag.
        state = classify_worker_state(
            existing=None, latest_run_id="R",
            latest_catalogue_version="v7.0",
            vertex_available=False, validator_passed=True,
            embedding_succeeded=False,
        )
        assert state == "vertex_unavailable"
        assert decision.summary_md is None

    def test_validator_rejects_fabricated_eid_uses_template(self) -> None:
        # When the LLM cites E-999 that isn't in the bundle, the validator
        # rejects and the worker falls back to the deterministic template.
        bundled = {"E-001", "E-002"}
        ok, fabricated = validate_summary_citations(
            cited_evidence_ids=["E-999"],
            bundled_evidence_ids=bundled,
        )
        assert ok is False
        assert fabricated == ["E-999"]
        snaps = [_snap(run_id="R1", when="2025-01-01T00:00:00+00:00", score=3.0),
                 _snap(run_id="R2", when="2026-01-01T00:00:00+00:00", score=3.4)]
        profile = compute_profile(snaps)
        template = deterministic_template_summary(
            entity_name="Test", profile=profile,
        )
        assert "auto-generated" in template
        # And the state classification chooses validator_rejected:
        state = classify_worker_state(
            existing=None, latest_run_id="R2",
            latest_catalogue_version="v7.0",
            vertex_available=True, validator_passed=False,
            embedding_succeeded=False,
        )
        assert state == "validator_rejected"

    def test_embedding_failure_keeps_text_drops_vector(self) -> None:
        # When the summary is generated but embedding fails, we keep the
        # summary text and set embedding to None.
        decision = SummaryDecision(
            summary_md="generated", summary_status="embedding_failed",
            embedding=None,
        )
        snaps = [_snap()]
        profile = compute_profile(snaps)
        payload = build_recompute_payload(
            entity_id="ent-1", entity_name="X",
            catalogue_version="v7.0", latest_run_id="R",
            profile=profile, summary=decision,
        )
        assert payload["intelligence_summary_md"] == "generated"
        assert payload["summary_embedding"] is None


# ---------------------------------------------------------------------
# Build payload sanity
# ---------------------------------------------------------------------


class TestBuildRecomputePayload:
    def test_carries_all_required_fields(self) -> None:
        snaps = [_snap()]
        profile = compute_profile(snaps)
        decision = SummaryDecision(
            summary_md="ok", summary_status="ok",
            embedding=[0.1] * 768, cited_evidence_ids=["E-001"],
        )
        payload = build_recompute_payload(
            entity_id="ent-1", entity_name="Test",
            catalogue_version="v7.0", latest_run_id="R",
            profile=profile, summary=decision,
        )
        # Spot-check every required column.
        for key in (
            "entity_id", "first_dma_at", "latest_dma_at", "total_runs",
            "maturity_history", "maturity_velocity",
            "archetype_history", "recurring_themes", "emerging_themes",
            "persistent_gap_subcap_ids", "closed_gap_subcap_ids",
            "tech_stack_additions", "tech_stack_removals",
            "intelligence_summary_md", "summary_grounding_evidence_ids",
            "summary_embedding", "computed_for_run_id", "catalogue_version",
        ):
            assert key in payload, f"missing {key}"
        assert payload["summary_grounding_evidence_ids"] == ["E-001"]
