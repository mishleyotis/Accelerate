"""Chat persistence + RAG /answer + feedback Pydantic schemas.

State transitions:
  RagAnswerRequest.page_context.entity_id is None
    → service treats the chat as a global walkthrough; cohort_mode is
      catalogue-only and no per-entity grounding is fetched.
  RagAnswerRequest.session_id is None
    → router creates a new chat_sessions row before persisting the turn.
  RagAnswerRequest.session_id refers to a session the requesting user
  does not own
    → router 403s before any Vertex call.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------
# RAG /answer
# --------------------------------------------------------------------

PageContextRoute = str  # free-form for now; e.g. "/clients/:id/heatmap"


class PageContext(BaseModel):
    route: PageContextRoute = "/"
    entity_id: str | None = None
    subcap_id: str | None = None
    run_id: str | None = None
    user_role: Literal["AE", "ANALYST", "ADMIN", "CUSTOMER"] = "AE"


class RagAnswerRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    page_context: PageContext = Field(default_factory=PageContext)
    response_style: Literal["concise", "deeper"] = "concise"
    max_paragraphs: int = Field(3, ge=1, le=6)
    require_citations: bool = True
    session_id: str | None = None
    # AE+ surfaces (meeting_prep) gate via this — frontend passes the
    # surface explicitly so role gating is uniform server-side.
    surface: str = "rag_answer"


class CitationChip(BaseModel):
    e_id: str
    source_name: str | None = None
    excerpt: str | None = None
    # When kind == "section" the chip opens a section drawer (not the
    # EvidenceDrawer). The frontend renders a book icon prefix for
    # section citations vs. a bookmark icon for evidence.
    kind: Literal["evidence", "section"] = "evidence"
    section_kind: str | None = None
    section_pillar: str | None = None


class RagAnswerResponse(BaseModel):
    session_id: str
    message_id: str
    answer_markdown: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
    cited_subcap_ids: list[str] = Field(default_factory=list)
    cited_section_ids: list[str] = Field(default_factory=list)
    citations: list[CitationChip] = Field(default_factory=list)
    confidence: float | None = None
    cohort_mode: Literal["single", "multi_lob", "cross_vertical", "catalogue_only"]
    insufficient_cohort: bool = False
    validators_passed: bool = True
    fallback_used: bool = False
    cache_hit: bool = False
    model: str
    latency_ms: int = 0
    # Adversarial-learning re-rank metadata (see rag_answer.py docstring).
    # Always present; `applied=false` with a reason when no boost happened.
    learning_signal: dict | None = None
    # Percentage of retrieved evidence rows whose freshness_band is
    # 'stale' (>3 years old). When > 40 the frontend surfaces a
    # "Most evidence is dated" disclaimer above the response body.
    bundle_stale_pct: float = 0.0
    # User-facing disclaimer string when bundle_stale_pct > 40, else "".
    stale_disclaimer: str = ""
    # Percentage of the retrieval bundle made up of document section
    # rows (vs. evidence rows). Lets the UI render "Grounded on:
    # N evidence + M sections" in the response footer.
    bundle_section_pct: float = 0.0


# --------------------------------------------------------------------
# Sessions + history
# --------------------------------------------------------------------

class ChatMessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content_markdown: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
    cited_subcap_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    validators_passed: bool | None = None
    created_at: datetime


class ChatSessionSummary(BaseModel):
    id: str
    surface: str
    entity_id: str | None = None
    page_context: dict = Field(default_factory=dict)
    started_at: datetime
    last_message_at: datetime
    message_count: int = 0
    last_question: str | None = None


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionSummary]


class ChatSessionDetailResponse(BaseModel):
    id: str
    surface: str
    entity_id: str | None = None
    page_context: dict = Field(default_factory=dict)
    started_at: datetime
    last_message_at: datetime
    messages: list[ChatMessageOut]


# --------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------

UnhelpfulReason = Literal[
    "too_verbose", "hallucinated", "wrong_subcap",
    "no_evidence", "irrelevant", "other",
]


class ChatFeedbackRequest(BaseModel):
    rating: Literal[-1, 0, 1]
    unhelpful_reason: UnhelpfulReason | None = None
    free_text: str | None = Field(None, max_length=4000)
    better_answer: str | None = Field(None, max_length=4000)


class ChatFeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: int
    created_at: datetime
