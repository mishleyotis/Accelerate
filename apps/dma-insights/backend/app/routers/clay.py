"""Clay enrichment endpoints.

Two surfaces:

POST /api/v1/clay/enrich/{entity_id}    (analyst+)
  Fires the outbound Clay table trigger for one entity. Returns
  ClayAck or 503 if the connector is disabled (local dev).

POST /api/v1/clay/webhook               (public, HMAC-verified)
  Inbound callback Clay invokes when the table run finishes. We verify
  the signature, normalize the payload, and upsert into firmographics.
  Returns 204 on success, 401 on signature mismatch, 422 on payload
  shape errors.

State-branch contract:
  - clay_webhook_secret unset → ALL inbound webhook calls return 401.
    Live-deploy must populate `dma-insights-clay-webhook-secret` from
    Secret Manager before the connector is usable.
  - entity_id not found       → 404 (admin must create entity first
    via /api/v1/ingest/package or manual create)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.deps import SessionDep, require_analyst
from app.services.clay_client import (
    ClayAck,
    ClayDisabled,
    normalize_payload,
    trigger_enrichment,
    verify_signature,
)

router = APIRouter(prefix="/api/v1/clay", tags=["clay"])


class ClayTriggerAck(BaseModel):
    entity_id: str
    status: str
    table_run_id: str | None = None
    note: str | None = None


@router.post(
    "/enrich/{entity_id}",
    response_model=ClayTriggerAck,
    dependencies=[Depends(require_analyst)],
)
async def trigger(entity_id: str, session: SessionDep) -> ClayTriggerAck:
    row = (await session.execute(
        text("SELECT id::text AS id, name, domain FROM entities WHERE id = :eid"),
        {"eid": entity_id},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    result = await trigger_enrichment(
        entity_id=row.id, domain=row.domain, name=row.name,
    )
    if isinstance(result, ClayDisabled):
        return ClayTriggerAck(
            entity_id=row.id, status="disabled", note=result.reason,
        )
    assert isinstance(result, ClayAck)
    return ClayTriggerAck(
        entity_id=row.id, status=result.status, table_run_id=result.table_run_id,
    )


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    session: SessionDep,
    x_clay_signature: str | None = Header(default=None, alias="X-Clay-Signature"),
) -> Response:
    body = await request.body()
    if not verify_signature(body, x_clay_signature):
        raise HTTPException(status_code=401, detail="invalid clay signature")
    try:
        raw = json.loads(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"malformed json: {e!s}") from e
    payload = normalize_payload(raw)
    eid = payload.get("entity_id")
    if not eid:
        raise HTTPException(status_code=422, detail="entity_id required")
    # Confirm entity exists.
    row = (await session.execute(
        text("SELECT id FROM entities WHERE id = :eid"), {"eid": eid},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # leadership + thought_leadership are JSONB; asyncpg requires a
    # string (it calls .encode() on the bound value). Pre-serialize +
    # CAST AS JSONB to avoid the "'list' object has no attribute 'encode'"
    # DataError, mirroring the firmographics pattern in
    # parsers/package_persist.py.
    ldr = payload.get("leadership") or None
    tl = payload.get("thought_leadership") or None
    await session.execute(
        text("""
            INSERT INTO firmographics (
                entity_id, aum_usd, revenue_usd, headcount, hq_address,
                primary_regulator, leadership, thought_leadership,
                clay_synced_at
            ) VALUES (
                :eid, :aum, :rev, :hc, :hq, :reg,
                CAST(:ldr AS JSONB), CAST(:tl AS JSONB), NOW()
            )
            ON CONFLICT (entity_id) DO UPDATE SET
                aum_usd       = COALESCE(EXCLUDED.aum_usd,       firmographics.aum_usd),
                revenue_usd   = COALESCE(EXCLUDED.revenue_usd,   firmographics.revenue_usd),
                headcount     = COALESCE(EXCLUDED.headcount,     firmographics.headcount),
                hq_address    = COALESCE(EXCLUDED.hq_address,    firmographics.hq_address),
                primary_regulator = COALESCE(EXCLUDED.primary_regulator,
                                              firmographics.primary_regulator),
                leadership    = COALESCE(EXCLUDED.leadership,    firmographics.leadership),
                thought_leadership = COALESCE(EXCLUDED.thought_leadership,
                                                firmographics.thought_leadership),
                clay_synced_at = NOW(),
                updated_at    = NOW()
        """),
        {
            "eid": eid,
            "aum": payload.get("aum_usd"),
            "rev": payload.get("revenue_usd"),
            "hc": payload.get("headcount"),
            "hq": payload.get("hq_address"),
            "reg": payload.get("primary_regulator"),
            "ldr": json.dumps(ldr) if ldr is not None else None,
            "tl": json.dumps(tl) if tl is not None else None,
        },
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
