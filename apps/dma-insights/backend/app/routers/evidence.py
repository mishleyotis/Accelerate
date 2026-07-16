"""Evidence-scoped endpoints.

GET /api/v1/evidence/{e_id}/run-history — returns the list of runs that
referenced this specific evidence_index row, via the
``evidence_run_links`` many-to-many populated by the dedup-aware
package_persist._persist_evidence path.

State branches (3):
  evidence_not_found   → 404. The :e_id token did not resolve to any
                          evidence_index row.
  first_seen_only      → exactly one row in evidence_run_links, with
                          first_seen_in_run=True. The frontend renders
                          "First seen" in muted color (chip variant
                          ``first-seen``).
  seen_in_n_runs       → ≥ 2 rows. Frontend renders "Seen in N runs"
                          chip; click opens a popover listing each
                          run with its surfaces_in_run array.

The endpoint is AE+ — anyone with a valid session JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep

router = APIRouter(prefix="/api/v1", tags=["evidence"])


@router.get("/evidence/{e_id}/run-history")
async def evidence_run_history(
    e_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Return every run that cites this evidence row.

    `e_id` may be either:
      - the human-friendly evidence ID (`E-001` etc.) on evidence_index,
        in which case we resolve to the canonical evidence_index.id and
        walk evidence_run_links for THAT row. When multiple
        evidence_index rows share an e_id (cross-entity case) the
        endpoint returns history for the lexicographically first row;
        the frontend should preferentially pass the UUID.
      - the canonical UUID (evidence_index.id) — preferred form.
    """
    _ = user
    # Resolve to canonical row.
    if len(e_id) > 30 and "-" in e_id and e_id.count("-") >= 4:
        # Looks like a UUID; resolve directly.
        row = (
            await session.execute(
                text(
                    """
                    SELECT id::text       AS id,
                           e_id            AS e_id,
                           entity_id::text AS entity_id,
                           tier,
                           freshness_band
                    FROM evidence_index
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": e_id},
            )
        ).first()
    else:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id::text       AS id,
                           e_id            AS e_id,
                           entity_id::text AS entity_id,
                           tier,
                           freshness_band
                    FROM evidence_index
                    WHERE e_id = :e
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                ),
                {"e": e_id},
            )
        ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evidence {e_id} not found",
        )

    runs = (
        await session.execute(
            text(
                """
                SELECT erl.run_id::text          AS run_id,
                       erl.first_seen_in_run     AS first_seen_in_run,
                       erl.surfaces_in_run       AS surfaces_in_run,
                       r.request_id              AS request_id,
                       r.completed_at            AS completed_at,
                       r.status                  AS status
                FROM evidence_run_links erl
                JOIN runs r ON r.id = erl.run_id
                WHERE erl.evidence_id = CAST(:eid AS uuid)
                ORDER BY r.completed_at DESC NULLS LAST
                """
            ),
            {"eid": row.id},
        )
    ).all()

    items = [
        {
            "run_id": r.run_id,
            "request_id": r.request_id,
            "completed_at": r.completed_at,
            "status": r.status,
            "first_seen_in_run": bool(r.first_seen_in_run),
            "surfaces_in_run": list(r.surfaces_in_run or []),
        }
        for r in runs
    ]
    return {
        "evidence_id": row.id,
        "e_id": row.e_id,
        "entity_id": row.entity_id,
        # NULL tier stays null in the payload — the source stated no
        # canonical tier; the old `or 8` fabricated one for display.
        "tier": int(row.tier) if row.tier is not None else None,
        "freshness_band": row.freshness_band,
        "runs": items,
        "n_runs": len(items),
        "is_first_seen": len(items) <= 1,
    }
