"""Schemas for the 2026-06 wireframe's net-new write surfaces (B-7/B-8/B-9).

- insight annotations (D2 InsightModal "Annotations" tab)
- focus-area KPI overrides (D3 focus-area CustomizableKpiStrip)
- notifications feed (TopBar NotificationsPopover)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AnnotationStatus = Literal["ACTIONED", "PENDING", "SUPERSEDED"]
KpiSourceMode = Literal["public", "client", "hidden"]
NotificationKind = Literal["alert", "completion", "system"]


# ── B-7 insight annotations ───────────────────────────────────────────────
class AnnotationIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    status: AnnotationStatus = "PENDING"
    sf_opp_id: str | None = Field(default=None, max_length=64)


class AnnotationOut(BaseModel):
    id: str
    ic_id: str
    author: str
    role: str
    body: str
    status: AnnotationStatus
    sf_opp_id: str | None = None
    created_at: datetime


class AnnotationListResponse(BaseModel):
    entity_display_id: str
    ic_id: str
    items: list[AnnotationOut] = Field(default_factory=list)


# ── B-8 focus-area KPI overrides ──────────────────────────────────────────
class KpiOverrideIn(BaseModel):
    kpi_label: str = Field(min_length=1, max_length=255)
    source_mode: KpiSourceMode = "public"
    current_value: str | None = None
    target_value: str | None = None


class KpiOverridePut(BaseModel):
    """PUT body — the full set of overrides for a focus area's KPI strip."""

    overrides: list[KpiOverrideIn] = Field(default_factory=list)


class KpiOverrideOut(BaseModel):
    fa_id: str
    kpi_label: str
    source_mode: KpiSourceMode
    current_value: str | None = None
    target_value: str | None = None
    # Migration 055 (2026-07-06): the E-ID of the evidence row the KPI's
    # number was read from — opens the evidence drawer straight from the
    # KPI strip. None for AE-entered rows and legacy pre-055 rows.
    evidence_e_id: str | None = None
    updated_at: datetime


class KpiOverrideListResponse(BaseModel):
    entity_display_id: str
    fa_id: str
    items: list[KpiOverrideOut] = Field(default_factory=list)


# ── B-9 notifications ─────────────────────────────────────────────────────
class NotificationOut(BaseModel):
    id: str
    kind: NotificationKind
    title: str
    body: str | None = None
    entity_id: str | None = None
    route: str | None = None
    seen_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationOut] = Field(default_factory=list)
    unseen_count: int


class MarkReadRequest(BaseModel):
    # When empty, marks ALL of the user's notifications read.
    ids: list[str] = Field(default_factory=list)
