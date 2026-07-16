"""POST /api/v1/runs/new — outbound bot loop request schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NewRunRequest(BaseModel):
    entity_name: str = Field(..., min_length=1)
    entity_domain: str | None = None
    notes: str | None = None
    urls: list[str] = Field(default_factory=list)
    materials_gs_urls: list[str] = Field(
        default_factory=list,
        description="GCS paths to AE-uploaded internal docs (already uploaded by frontend)",
    )
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    parent_request_id: str | None = Field(None, pattern=r"^REQ-[0-9A-F]{8}$")
    is_rerun: bool = False


class NewRunResponse(BaseModel):
    request_id: str = Field(..., pattern=r"^REQ-[0-9A-F]{8}$")
    sheet_row_url: str | None = None
    eta_minutes: int | None = None
    evidence_mode: Literal["public", "hybrid"]
    state: Literal["SUBMITTED", "BOT_ACCEPTED"]
