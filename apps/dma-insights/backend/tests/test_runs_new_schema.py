"""Tests for the runs-new request/response schema contracts."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.runs_new import NewRunRequest, NewRunResponse


class TestNewRunRequest:
    def test_minimal_valid(self) -> None:
        r = NewRunRequest(entity_name="Farm Credit East")
        assert r.priority == "normal"
        assert r.is_rerun is False
        assert r.materials_gs_urls == []

    def test_parent_request_id_pattern(self) -> None:
        r = NewRunRequest(entity_name="X", parent_request_id="REQ-DEADBEEF")
        assert r.parent_request_id == "REQ-DEADBEEF"
        with pytest.raises(ValidationError):
            NewRunRequest(entity_name="X", parent_request_id="REQ-lower")

    def test_rejects_blank_entity_name(self) -> None:
        with pytest.raises(ValidationError):
            NewRunRequest(entity_name="")

    def test_priority_must_be_enum(self) -> None:
        with pytest.raises(ValidationError):
            NewRunRequest(entity_name="X", priority="emergency")  # type: ignore[arg-type]


class TestNewRunResponse:
    def test_round_trip(self) -> None:
        r = NewRunResponse(
            request_id="REQ-A6654887",
            evidence_mode="hybrid",
            state="BOT_ACCEPTED",
            eta_minutes=30,
        )
        assert r.request_id == "REQ-A6654887"

    def test_request_id_pattern_enforced(self) -> None:
        with pytest.raises(ValidationError):
            NewRunResponse(
                request_id="REQ-123",
                evidence_mode="public",
                state="SUBMITTED",
            )

    def test_evidence_mode_enum(self) -> None:
        with pytest.raises(ValidationError):
            NewRunResponse(
                request_id="REQ-A6654887",
                evidence_mode="strict",  # type: ignore[arg-type]
                state="BOT_ACCEPTED",
            )

    def test_state_enum(self) -> None:
        with pytest.raises(ValidationError):
            NewRunResponse(
                request_id="REQ-A6654887",
                evidence_mode="hybrid",
                state="LAUNCHED",  # type: ignore[arg-type]
            )
