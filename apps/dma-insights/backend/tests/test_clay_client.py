"""Clay enrichment connector tests."""
from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

from app.config import get_settings
from app.services.clay_client import (
    ClayAck,
    ClayDisabled,
    ClayError,
    normalize_payload,
    trigger_enrichment,
    verify_signature,
)


def test_trigger_returns_disabled_when_url_unset(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "")
    get_settings.cache_clear()

    import asyncio
    result = asyncio.run(trigger_enrichment(
        entity_id="e1", domain="x.com", name="X",
    ))
    assert isinstance(result, ClayDisabled)


def test_trigger_posts_and_returns_ack(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "https://clay.test/hook")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "secret123")
    get_settings.cache_clear()

    captured = {}

    import json as _json

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = _json.loads(request.content)
        return httpx.Response(200, json={"table_run_id": "tr_42"})

    transport = httpx.MockTransport(handler)
    import asyncio

    async def _run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await trigger_enrichment(
                entity_id="e1", domain="x.com", name="X", ticker="XX",
                client=client,
            )

    result = asyncio.run(_run())
    assert isinstance(result, ClayAck)
    assert result.table_run_id == "tr_42"
    assert captured["json"] == {
        "entity_id": "e1", "domain": "x.com", "name": "X", "ticker": "XX",
    }


def test_trigger_raises_on_5xx(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "https://clay.test/hook")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "secret123")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    transport = httpx.MockTransport(handler)
    import asyncio

    async def _run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await trigger_enrichment(
                entity_id="e1", domain="x.com", name="X", client=client,
            )

    with pytest.raises(ClayError):
        asyncio.run(_run())


def test_verify_signature_happy_path(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "secret123")
    get_settings.cache_clear()
    body = b'{"entity_id":"e1"}'
    sig = hmac.new(b"secret123", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, f"sha256={sig}") is True


def test_verify_signature_rejects_when_secret_missing(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    assert verify_signature(b'{}', "sha256=anything") is False


def test_verify_signature_rejects_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "secret123")
    get_settings.cache_clear()
    assert verify_signature(b'{}', "sha256=deadbeef") is False


def test_verify_signature_rejects_wrong_algo(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "secret123")
    get_settings.cache_clear()
    assert verify_signature(b'{}', "sha512=xxx") is False


def test_normalize_payload_maps_leadership_aliases() -> None:
    raw = {
        "entity_id": "e1",
        "aum": "1500000000",
        "employees": "1200",
        "headquarters": "NYC",
        "leadership": [
            {"name": "Alice", "title": "CEO"},
            {"name": "Bob", "role": "CIO", "years_in_role": "3"},
            {},  # discarded
        ],
    }
    out = normalize_payload(raw)
    assert out["aum_usd"] == 1_500_000_000.0
    assert out["headcount"] == 1200
    assert out["hq_address"] == "NYC"
    names = [p["name"] for p in out["leadership"]]
    assert names == ["Alice", "Bob"]
