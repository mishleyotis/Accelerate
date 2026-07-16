"""Global quick-search response schemas (TopBar ⌘K palette)."""
from __future__ import annotations

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    kind: str   # "entity" | "insight" | "evidence"
    title: str
    sub: str
    route: str
    icon: str


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultOut]
