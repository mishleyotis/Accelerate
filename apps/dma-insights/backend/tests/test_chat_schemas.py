"""Tests for chat + enrichment + RAG /answer Pydantic schemas."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatMessageOut,
    PageContext,
    RagAnswerRequest,
    RagAnswerResponse,
)
from app.schemas.enrichment import (
    AiEnrichmentOut,
    ArchetypeMatch,
    ArchetypeResponse,
    PendingReviewItem,
    PendingReviewResponse,
    RunHistoryItem,
    RunHistoryResponse,
    VertexBudgetResponse,
)


class TestPageContext:
    def test_defaults(self) -> None:
        pc = PageContext()
        assert pc.user_role == "AE"
        assert pc.entity_id is None

    def test_full(self) -> None:
        pc = PageContext(
            route="/clients/x/heatmap",
            entity_id="e1", subcap_id="P1C1.1.1",
            user_role="ADMIN",
        )
        assert pc.subcap_id == "P1C1.1.1"
        assert pc.user_role == "ADMIN"


class TestRagAnswerRequest:
    def test_minimal(self) -> None:
        r = RagAnswerRequest(question="hi")
        assert r.response_style == "concise"
        assert r.surface == "rag_answer"
        assert r.max_paragraphs == 3

    def test_question_max_length_4000(self) -> None:
        with pytest.raises(ValidationError):
            RagAnswerRequest(question="x" * 4001)

    def test_question_min_length_1(self) -> None:
        with pytest.raises(ValidationError):
            RagAnswerRequest(question="")

    def test_max_paragraphs_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RagAnswerRequest(question="?", max_paragraphs=7)
        with pytest.raises(ValidationError):
            RagAnswerRequest(question="?", max_paragraphs=0)


class TestRagAnswerResponse:
    def test_valid(self) -> None:
        r = RagAnswerResponse(
            session_id="00000000-0000-0000-0000-000000000001",
            message_id="00000000-0000-0000-0000-000000000002",
            answer_markdown="Hi",
            cited_evidence_ids=["E-1"],
            cohort_mode="single",
            model="flash",
        )
        assert r.validators_passed is True
        assert r.fallback_used is False

    def test_invalid_cohort_mode(self) -> None:
        with pytest.raises(ValidationError):
            RagAnswerResponse(
                session_id="x", message_id="y", answer_markdown="z",
                cohort_mode="weird",  # type: ignore[arg-type]
                model="flash",
            )


class TestChatFeedback:
    def test_rating_must_be_minus_one_zero_or_one(self) -> None:
        ChatFeedbackRequest(rating=1)
        ChatFeedbackRequest(rating=0)
        ChatFeedbackRequest(rating=-1)
        with pytest.raises(ValidationError):
            ChatFeedbackRequest(rating=2)  # type: ignore[arg-type]

    def test_reason_enum(self) -> None:
        ChatFeedbackRequest(rating=-1, unhelpful_reason="hallucinated")
        with pytest.raises(ValidationError):
            ChatFeedbackRequest(
                rating=-1,
                unhelpful_reason="not_an_option",  # type: ignore[arg-type]
            )

    def test_better_answer_optional(self) -> None:
        f = ChatFeedbackRequest(rating=-1, better_answer="Try saying X instead.")
        assert f.better_answer is not None

    def test_better_answer_length_cap(self) -> None:
        with pytest.raises(ValidationError):
            ChatFeedbackRequest(rating=-1, better_answer="x" * 4001)


class TestChatMessageOut:
    def test_default_lists_are_empty(self) -> None:
        m = ChatMessageOut(
            id="x", role="user", content_markdown="hi",
            created_at=datetime.now(tz=UTC),
        )
        assert m.cited_evidence_ids == []
        assert m.cited_subcap_ids == []


class TestEnrichmentSchemas:
    def test_ai_enrichment_out(self) -> None:
        e = AiEnrichmentOut(
            id="x", target_kind="subcap_score", target_id="y",
            surface="subcap_narrative", enrichment_text="z",
            grounding_evidence_ids=["E-1"], grounding_subcap_ids=[],
            model="flash", catalogue_version="v7.0",
            validators_passed=True, created_at=datetime.now(tz=UTC),
        )
        assert e.target_kind == "subcap_score"

    def test_archetype_match(self) -> None:
        a = ArchetypeMatch(
            archetype_label="x", subvertical="CU",
            catalogue_version="v7.0", distance=1.0,
            sample_count=3,
        )
        assert a.distance == 1.0

    def test_archetype_response_insufficient_default(self) -> None:
        r = ArchetypeResponse()
        assert r.insufficient_data is False
        assert r.closest is None


class TestRunHistorySchema:
    def test_chain_field(self) -> None:
        r = RunHistoryResponse(
            entity_id="x", items=[
                RunHistoryItem(
                    request_id="REQ-12345678",
                    status="ACTIVE", catalogue_version="v7.0",
                ),
            ], parent_chain=["REQ-AAAAAAAA"],
        )
        assert r.parent_chain == ["REQ-AAAAAAAA"]


class TestVertexBudgetSchema:
    def test_defaults(self) -> None:
        v = VertexBudgetResponse(
            period="2026-05", spent_usd=1.0, budget_usd=100.0, pct_used=1.0,
        )
        assert v.top_surfaces == []
        assert v.top_users == []


class TestPendingReview:
    def test_kind_enum(self) -> None:
        with pytest.raises(ValidationError):
            PendingReviewItem(
                kind="weird",  # type: ignore[arg-type]
                id="x", title="y", created_at=datetime.now(tz=UTC),
            )

    def test_valid(self) -> None:
        r = PendingReviewResponse(
            items=[
                PendingReviewItem(
                    kind="run", id="x", title="y",
                    created_at=datetime.now(tz=UTC),
                ),
            ],
        )
        assert len(r.items) == 1
