"""POST /api/v1/runs/new — outbound bot loop.

Per plan ④:
  1. AE clicks "Request DMA" in /clients (or "Re-run" on an entity).
  2. Frontend uploads any materials to GCS, gets gs:// URLs.
  3. We POST to this endpoint with the materials_gs_urls + entity + notes.
  4. Backend derives evidence_mode (hybrid if any materials/urls, else public).
  5. Backend POSTs to the bot's /run endpoint; bot returns
     { request_id, sheet_row_url, eta_min }.
  6. Backend persists dma_runs_requested + ops_requests + runs (IN_PROGRESS).
  7. Returns { request_id, state, evidence_mode } to the AE.

The bot's own `request_id` (REQ-{8 hex}) is the canonical cross-system ID.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.config import get_settings
from app.deps import CurrentUserDep, SessionDep
from app.schemas.runs_new import NewRunRequest, NewRunResponse

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("/new", response_model=NewRunResponse)
async def request_new_run(
    body: NewRunRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> NewRunResponse:
    settings = get_settings()
    evidence_mode = (
        "hybrid"
        if (body.materials_gs_urls or body.urls)
        else "public"
    )

    bot_payload = {
        "entity": body.entity_name,
        "domain": body.entity_domain,
        "notes": body.notes,
        "urls": body.urls,
        "materials_gs_urls": body.materials_gs_urls,
        "mode": evidence_mode,
        "requester_email": user.email,
        "priority": body.priority,
        "parent_request_id": body.parent_request_id,
        "is_rerun": body.is_rerun,
    }

    bot_response_payload: dict = {}
    eta_minutes: int | None = None
    sheet_row_url: str | None = None
    request_id: str | None = None

    if not settings.dma_bot_api_key:
        # Local dev / test mode: synthesize a fake request_id without round-trip.
        # This path is exercised by unit tests; production sets the bot API key
        # via Secret Manager and the synthetic branch is never taken.
        import secrets
        request_id = f"REQ-{secrets.token_hex(4).upper()}"
        bot_response_payload = {
            "request_id": request_id,
            "sheet_row_url": None,
            "eta_min": None,
            "mode": evidence_mode,
            "synthetic": True,
        }
    else:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.dma_bot_url.rstrip('/')}/run",
                    json=bot_payload,
                    headers={"Authorization": f"Bearer {settings.dma_bot_api_key}"},
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"bot unreachable: {exc}",
            ) from exc
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"bot returned {resp.status_code}: {resp.text[:200]}",
            )
        bot_response_payload = resp.json() or {}
        request_id = bot_response_payload.get("request_id")
        sheet_row_url = bot_response_payload.get("sheet_row_url")
        eta_minutes = bot_response_payload.get("eta_min")
        if not request_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="bot did not return a request_id",
            )

    # Persist envelope on our side.
    await session.execute(
        text(
            """
            INSERT INTO dma_runs_requested (
                request_id, requester_user_id, evidence_mode, is_rerun,
                parent_request_id, materials_gs_urls, bot_payload,
                bot_response, ops_sheet_row_url, state
            ) VALUES (
                :rid, CAST(:uid AS uuid), :mode, :rerun, :prid,
                CAST(:mat AS jsonb), CAST(:bp AS jsonb),
                CAST(:br AS jsonb), :url, :state
            )
            ON CONFLICT (request_id) DO NOTHING
            """
        ),
        {
            "rid": request_id,
            "uid": user.user_id,
            "mode": evidence_mode,
            "rerun": body.is_rerun,
            "prid": body.parent_request_id,
            "mat": _to_json_array(body.materials_gs_urls),
            "bp": _to_json(bot_payload),
            "br": _to_json(bot_response_payload),
            "url": sheet_row_url,
            "state": "BOT_ACCEPTED" if settings.dma_bot_api_key else "SUBMITTED",
        },
    )
    await session.commit()
    return NewRunResponse(
        request_id=request_id,
        sheet_row_url=sheet_row_url,
        eta_minutes=eta_minutes,
        evidence_mode=evidence_mode,  # type: ignore[arg-type]
        state="BOT_ACCEPTED" if settings.dma_bot_api_key else "SUBMITTED",
    )


def _to_json(obj: object) -> str:
    import json
    return json.dumps(obj, default=str)


def _to_json_array(items: list[str]) -> str:
    import json
    return json.dumps(items)
