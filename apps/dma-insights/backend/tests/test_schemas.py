"""Tests for the Pydantic v2 schemas — ingest contract + RAG response."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ingest import (
    AppPayloadV1,
    EvidenceItemIn,
    SubcapScoreIn,
)
from app.schemas.rag import RagEvidenceItem, RagEvidenceResponse

# ---------- SubcapScoreIn ----------

class TestSubcapScoreIn:
    def test_t1_id_accepted(self) -> None:
        m = SubcapScoreIn(subcap_id="P1C1.1.1", score=3.5, band="M3")
        assert m.subcap_id == "P1C1.1.1"

    def test_t2_id_accepted(self) -> None:
        m = SubcapScoreIn(subcap_id="P2C3.4.2-T2-CIB", score=2.0, band="M2")
        assert m.subcap_id == "P2C3.4.2-T2-CIB"

    def test_invalid_pillar_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubcapScoreIn(subcap_id="P5C1.1.1", score=3.5, band="M3")

    def test_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubcapScoreIn(subcap_id="P1C1.1.1", score=5.5, band="M5")

    def test_band_must_be_valid(self) -> None:
        with pytest.raises(ValidationError):
            SubcapScoreIn(subcap_id="P1C1.1.1", score=3.5, band="M9")


class TestEvidenceItemIn:
    def test_minimal(self) -> None:
        m = EvidenceItemIn(
            e_id="E-1",
            source_name="ABA Banking Journal",
            excerpt="They launched digital onboarding in 2024.",
            claim_type="strategic_signal",
            tier=3,
        )
        assert m.e_id == "E-1"
        assert m.tier == 3

    def test_tier_bounds(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItemIn(e_id="E-1", source_name="x", excerpt="x",
                           claim_type="x", tier=9)
        with pytest.raises(ValidationError):
            EvidenceItemIn(e_id="E-1", source_name="x", excerpt="x",
                           claim_type="x", tier=0)

    def test_eid_format_enforced(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItemIn(e_id="E12", source_name="x", excerpt="x",
                           claim_type="x", tier=2)


class TestAppPayloadV1:
    def _minimal(self) -> dict:
        return {
            "payload_version": "v1",
            "request_id": "REQ-A6654887",
            "ccg_catalog_version": "v7.0",
            "entity_name": "Farm Credit East",
            "entity_subvertical": "FC",
            "scqa": {
                "situation": "Federal credit cooperative serving ag lending in NE US",
                "complication": "Margin pressure from non-bank competitors",
                "question": "Where to invest in digital next?",
                "answer": "Modernize loan origination + member servicing",
            },
            "subcap_scores": [
                {"subcap_id": "P1C1.1.1", "score": 3.2, "band": "M3"},
            ],
            "evidence": [
                {
                    "e_id": "E-1",
                    "source_name": "FCE 2024 annual report",
                    "excerpt": "AUM grew 8% YoY",
                    "claim_type": "financial_signal",
                    "tier": 2,
                }
            ],
            "insights": [
                {
                    "ic_id": "IC-1",
                    "severity": "high",
                    "title": "Loan origination is paper-driven",
                    "what_text": "Mostly PDF intake.",
                    "why_text": "Investments lagged peers by 3 years.",
                    "so_what_text": "Member experience suffers.",
                    "linked_subcap_id": "P1C1.1.1",
                    "linked_e_ids": ["E-1"],
                }
            ],
            "recommendations": [
                {
                    "rec_id": "REC-1",
                    "title": "Adopt nCino loan origination",
                    "description": "Replaces 14 manual steps.",
                    "target_subcap_ids": ["P1C1.1.1"],
                    "platform_id": "ncino",
                    "uplift_per_pillar": {"P1": 0.8},
                    "effort_band": "large",
                }
            ],
        }

    def test_round_trip(self) -> None:
        payload = AppPayloadV1.model_validate(self._minimal())
        assert payload.request_id == "REQ-A6654887"
        assert payload.entity_subvertical == "FC"
        assert payload.subcap_scores[0].band == "M3"

    def test_request_id_must_match_pattern(self) -> None:
        bad = self._minimal()
        bad["request_id"] = "REQ-lowercase"
        with pytest.raises(ValidationError):
            AppPayloadV1.model_validate(bad)

    def test_request_id_must_be_8_hex(self) -> None:
        bad = self._minimal()
        bad["request_id"] = "REQ-123"
        with pytest.raises(ValidationError):
            AppPayloadV1.model_validate(bad)

    def test_parent_request_id_optional_but_pattern_when_present(self) -> None:
        ok = self._minimal() | {"parent_request_id": "REQ-DEADBEEF"}
        payload = AppPayloadV1.model_validate(ok)
        assert payload.parent_request_id == "REQ-DEADBEEF"

        bad = self._minimal() | {"parent_request_id": "REQ-zzz"}
        with pytest.raises(ValidationError):
            AppPayloadV1.model_validate(bad)


class TestRagEvidenceResponse:
    def test_round_trip(self) -> None:
        resp = RagEvidenceResponse(
            cohort_mode="single",
            n=12,
            insufficient_cohort=False,
            items=[
                RagEvidenceItem(
                    e_id="E-9",
                    entity_name="Anchor FCU",
                    subcap_id="P2C3.4.2",
                    source_name="Annual report",
                    excerpt="...",
                    tier=2,
                    claim_type="strategic_signal",
                    cohort_match=1.0,
                )
            ],
        )
        assert resp.items[0].cohort_match == 1.0
        assert resp.cohort_mode == "single"

    def test_cohort_match_bounded(self) -> None:
        with pytest.raises(ValidationError):
            RagEvidenceItem(
                e_id="E-1",
                entity_name="X",
                subcap_id="P1C1.1.1",
                source_name="X",
                excerpt="X",
                tier=1,
                claim_type="X",
                cohort_match=1.5,
            )
