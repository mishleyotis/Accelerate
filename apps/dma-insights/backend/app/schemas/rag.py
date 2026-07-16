"""RAG read-API schemas — what the Claude project sees when querying."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RagEvidenceItem(BaseModel):
    e_id: str
    entity_name: str
    subcap_id: str
    source_name: str
    excerpt: str
    # None = source stated no canonical tier (honest-absent; migration
    # 055). Known tiers stay bounded to the canonical taxonomy.
    tier: int | None = Field(None, ge=1, le=8)
    claim_type: str
    published_date: date | None = None
    source_url: str | None = None
    cohort_match: float = Field(..., ge=0.0, le=1.0)


class RagEvidenceResponse(BaseModel):
    cohort_mode: Literal["single", "multi_lob", "cross_vertical"]
    n: int
    insufficient_cohort: bool = False
    items: list[RagEvidenceItem]


class RagPeerBandResponse(BaseModel):
    insufficient_cohort: bool = False
    n: int
    median: float | None = None
    p25: float | None = None
    p75: float | None = None
    fallback: str | None = None
    n_xv: int | None = None


class RagEmbedRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    texts: list[str] = Field(..., min_length=1, max_length=64)
    model_version: str = "text-embedding-005"


class RagEmbedResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_version: str
    embeddings: list[list[float]]
