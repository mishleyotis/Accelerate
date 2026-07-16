"""Clay enrichment connector.

Clay (https://clay.com) is the firmographics + leadership enrichment
source. The integration uses Clay's **Table Webhook** pattern:

1. Each Zennify entity has a domain (or institution name + ticker).
2. Backend POSTs `{entity_id, domain, name, ticker}` to a Clay table
   webhook URL configured in Secret Manager (`clay_webhook_url`).
3. Clay's table runs its enrichment chain (Apollo / LinkedIn / Crunchbase
   sources, leadership pull, firmographics, ICP scoring).
4. Clay calls back to `POST /api/v1/clay/webhook` with the enrichment
   payload, signed with `X-Clay-Signature: sha256=<hex hmac>` using the
   shared `clay_webhook_secret`.
5. We upsert `firmographics.leadership / thought_leadership / hq_address
   / aum_usd / headcount / clay_synced_at`.

This module owns only steps 2 + the HMAC verifier for step 4. The
webhook receiver router (`app/routers/clay.py`) wires the request
parsing + persistence.

State-branch contract:
  - Settings empty → `trigger_enrichment` returns ClayDisabled
                     (no network call; pages render with empty leadership)
  - Settings set   → POST with 8s timeout; raises ClayError on non-2xx
  - bad signature  → `verify_signature` returns False; router 401s
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Literal

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger()


class ClayError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClayDisabled:
    """Sentinel returned when Clay is not configured (local dev)."""
    reason: str = "clay_webhook_url not configured"


@dataclass(frozen=True)
class ClayAck:
    """Returned by `trigger_enrichment` on a successful outbound POST."""
    status: Literal["accepted"]
    table_run_id: str | None = None


async def trigger_enrichment(
    *, entity_id: str, domain: str | None,
    name: str, ticker: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> ClayAck | ClayDisabled:
    """POSTs the enrichment trigger to Clay. Returns ClayDisabled when
    the connector is unconfigured (local dev / pre-deploy)."""
    settings = get_settings()
    if not settings.clay_webhook_url:
        return ClayDisabled()
    payload = {
        "entity_id": entity_id,
        "domain": domain,
        "name": name,
        "ticker": ticker,
    }
    timeout = httpx.Timeout(settings.clay_request_timeout_seconds)
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await client.post(settings.clay_webhook_url, json=payload)
        if resp.status_code >= 300:
            raise ClayError(
                f"clay returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            body = resp.json()
        except ValueError:
            body = {}
        log.info("clay.enrichment_triggered", entity_id=entity_id,
                 table_run_id=body.get("table_run_id"))
        return ClayAck(status="accepted", table_run_id=body.get("table_run_id"))
    finally:
        if owns_client:
            await client.aclose()


def verify_signature(body_bytes: bytes, signature_header: str | None) -> bool:
    """Verifies the `X-Clay-Signature: sha256=<hex>` header. Returns False
    when the secret is unconfigured (defense-in-depth: reject all signed
    payloads if we don't have a secret to compare against)."""
    settings = get_settings()
    secret = settings.clay_webhook_secret
    if not secret:
        return False
    if not signature_header or "=" not in signature_header:
        return False
    algo, _, hexsig = signature_header.partition("=")
    if algo != "sha256":
        return False
    mac = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, hexsig.strip())


def normalize_payload(raw: dict) -> dict:
    """Maps Clay's enrichment payload onto our firmographics columns.

    Clay's response shape (per their docs) is a dict of `{column_name:
    cell_value}` matching the table's schema. We accept a flexible set
    of key aliases so changing the Clay table doesn't break ingest.
    """
    def first(*keys):
        for k in keys:
            if raw.get(k) not in (None, ""):
                return raw[k]
        return None

    leadership_raw = first(
        "leadership", "executives", "leadership_team", "key_people"
    ) or []
    leaders: list[dict] = []
    if isinstance(leadership_raw, str):
        try:
            leadership_raw = json.loads(leadership_raw)
        except ValueError:
            leadership_raw = []
    for p in leadership_raw:
        if not isinstance(p, dict):
            continue
        leaders.append({
            "name": p.get("name") or p.get("full_name") or "",
            "title": p.get("title") or p.get("role"),
            "tenure": p.get("tenure") or p.get("years_in_role"),
            "background": p.get("background") or p.get("summary"),
            "linkedin": p.get("linkedin") or p.get("linkedin_url"),
        })

    return {
        "entity_id": first("entity_id"),
        "aum_usd": _to_float(first("aum_usd", "aum", "assets_under_management")),
        "revenue_usd": _to_float(first("revenue_usd", "revenue", "annual_revenue")),
        "headcount": _to_int(first("headcount", "employees", "employee_count")),
        "hq_address": first("hq_address", "headquarters", "address"),
        "primary_regulator": first("primary_regulator", "regulator"),
        "leadership": [p for p in leaders if p["name"]],
        "thought_leadership": first("thought_leadership", "publications"),
    }


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    f = _to_float(v)
    return int(f) if f is not None else None
