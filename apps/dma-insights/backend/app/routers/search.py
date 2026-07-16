"""Global quick-search endpoint — powers the TopBar ⌘K palette.

GET /api/v1/search?q=  — one query, three surfaces (entities, insight
cards, evidence), each routed to a real page. Mirrors the prototype
`chrome.jsx` SearchPopover, which searched all three client-side against
mock data; here the surfaces live in Postgres so the router fans out
three small ILIKE lookups and hands the rows to the pure shaper.

Scope: any authenticated user, matching the entity directory
(`GET /api/v1/entities`, owner=all) — both surface every ACTIVE entity,
so search is no broader than the directory the user already browses.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep
from app.schemas.search import SearchResponse, SearchResultOut
from app.services.search import (
    ENTITY_LIMIT,
    EVIDENCE_LIMIT,
    INSIGHT_LIMIT,
    build_search_results,
)

router = APIRouter(prefix="/api/v1", tags=["search"])

# Below this the popover shows static "Quick links" instead, so the API
# never runs a `%a%` scan that returns half the corpus.
_MIN_QUERY_LEN = 2


@router.get("/search", response_model=SearchResponse)
async def global_search(
    user: CurrentUserDep,  # auth gate (401s unauthenticated); scope mirrors the directory
    session: SessionDep,
    q: str = Query(default="", description="free text — entity name, IC-id, or E-id"),
) -> SearchResponse:
    """Multi-surface quick search across entities + insights + evidence.

    `user` is intentionally unreferenced — its presence runs the auth
    dependency so anonymous callers get 401, same as the directory.
    """
    del user  # auth side-effect only
    term = q.strip()
    if len(term) < _MIN_QUERY_LEN:
        return SearchResponse(query=term, total=0, results=[])

    like = {"q": f"%{term}%"}

    entities = [
        (r.display_id, r.name, r.subvertical)
        for r in (
            await session.execute(
                text(
                    """
                    SELECT e.display_id, e.name, e.subvertical
                    FROM entities e
                    WHERE e.status = 'ACTIVE'
                      AND (e.name ILIKE :q OR e.display_id ILIKE :q)
                    ORDER BY e.name
                    LIMIT :lim
                    """
                ),
                {**like, "lim": ENTITY_LIMIT},
            )
        ).all()
    ]

    insights = [
        (r.ic_id, r.title, r.severity, r.display_id)
        for r in (
            await session.execute(
                text(
                    """
                    SELECT ic.ic_id, ic.title, ic.severity, e.display_id
                    FROM insight_cards ic
                    JOIN entities e ON e.id = ic.entity_id
                    WHERE e.status = 'ACTIVE'
                      AND (ic.title ILIKE :q OR ic.ic_id ILIKE :q)
                    ORDER BY ic.ic_id
                    LIMIT :lim
                    """
                ),
                {**like, "lim": INSIGHT_LIMIT},
            )
        ).all()
    ]

    evidence = [
        (r.e_id, r.title, r.tier, r.display_id)
        for r in (
            await session.execute(
                text(
                    """
                    SELECT ev.e_id, ev.title, ev.tier, e.display_id
                    FROM evidence_index ev
                    JOIN entities e ON e.id = ev.entity_id
                    WHERE e.status = 'ACTIVE'
                      AND (ev.title ILIKE :q OR ev.e_id ILIKE :q)
                    ORDER BY ev.e_id
                    LIMIT :lim
                    """
                ),
                {**like, "lim": EVIDENCE_LIMIT},
            )
        ).all()
    ]

    hits = build_search_results(entities, insights, evidence)
    return SearchResponse(
        query=term,
        total=len(hits),
        results=[
            SearchResultOut(
                kind=h.kind, title=h.title, sub=h.sub, route=h.route, icon=h.icon
            )
            for h in hits
        ],
    )
