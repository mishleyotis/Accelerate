"""Customer intelligence profile endpoint.

GET /api/v1/entities/{display_id}/intelligence-profile — returns the
persistent per-customer rollup written by the customer_intelligence
service (recomputed automatically on every successful ingest via the
``dma.ingest.completed`` Pub/Sub topic).

Role gate: AE+ (anyone authenticated). Returns 404 when the entity
exists but no profile has been computed yet (e.g. first ingest still
in progress); the UI shows "Persistent intelligence pending" in that
case.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, ViewModeDep
from app.services.audience_strip import strip_internal

router = APIRouter(prefix="/api/v1", tags=["intelligence"])


@router.get("/entities/{display_id}/intelligence-profile")
async def get_intelligence_profile(
    display_id: str,
    user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
) -> dict:
    """Returns the entity's customer_intelligence_profiles row as JSON."""
    _ = user  # role gate handled at the dependency layer
    row = (
        await session.execute(
            text("""
                SELECT
                    cip.entity_id::text                     AS entity_id,
                    cip.first_dma_at, cip.latest_dma_at,
                    cip.total_runs,
                    cip.total_evidence_count,
                    cip.unique_evidence_count,
                    cip.median_evidence_age_months,
                    cip.stale_evidence_pct,
                    cip.maturity_history,
                    cip.maturity_velocity,
                    cip.archetype_history,
                    cip.recurring_themes,
                    cip.emerging_themes,
                    cip.persistent_gap_subcap_ids,
                    cip.closed_gap_subcap_ids,
                    cip.tech_stack_additions,
                    cip.tech_stack_removals,
                    cip.intelligence_summary_md,
                    cip.summary_grounding_evidence_ids,
                    cip.computed_at,
                    cip.computed_for_run_id::text           AS computed_for_run_id,
                    cip.catalogue_version,
                    e.display_id, e.name
                FROM customer_intelligence_profiles cip
                JOIN entities e ON e.id = cip.entity_id
                WHERE e.display_id = :did
                  AND e.status = 'ACTIVE'
            """),
            {"did": display_id},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="intelligence_profile_not_yet_computed",
        )
    # Audience-strip: customer view drops internal_notes / annotations_
    # internal / any future internal-only key surfaced via the profile.
    # `row` is a SQLAlchemy RowMapping → dict() materialises it before
    # the strip walks the structure.
    return strip_internal(dict(row), view.audience)
