"""The door: /mcp + X-DMA-Path-Token (or /mcp/<token>) serves six tools;
anything else is a 404; /healthz is open. Exercised in-process over ASGI."""
from __future__ import annotations

import asyncio
import json

import httpx

import evidence_server as server

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
HDR = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _body(r: httpx.Response) -> dict:
    text = r.text
    if "data:" in text:
        text = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")][-1]
    return json.loads(text)


def test_door():
    app = server.build_app(token="sekrit")

    async def go():
        async with app.lifespan():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                assert (await c.get("/healthz")).status_code == 200
                assert (await c.post("/mcp-not", json=INIT, headers=HDR)).status_code == 404
                assert (await c.post("/mcp", json=INIT, headers=HDR)).status_code == 404
                assert (await c.post("/mcp/wrong", json=INIT, headers=HDR)).status_code == 404
                ok = await c.post("/mcp", json=INIT, headers={**HDR, "X-DMA-Path-Token": "sekrit"})
                assert ok.status_code == 200, ok.text
                seg = await c.post("/mcp/sekrit", json=INIT, headers=HDR)
                assert seg.status_code == 200, seg.text
                tools = await c.post("/mcp", json=LIST, headers={**HDR, "X-DMA-Path-Token": "sekrit"})
                names = sorted(t["name"] for t in _body(tools)["result"]["tools"])
                assert names == ["coverage_report", "crawl_entity", "expand_context", "filings_evidence",
                                 "research_brief", "verify_cards"]
                root = await c.get("/")
                assert root.status_code == 200 and b"open-source" in root.content.lower()
    asyncio.run(go())


def test_no_token_configured_is_local_only_and_still_hides_other_paths(capsys):
    app = server.build_app(token="")
    assert "DISABLED" in capsys.readouterr().err

    async def go():
        async with app.lifespan():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                assert (await c.post("/anything", json=INIT, headers=HDR)).status_code == 404
                assert (await c.post("/mcp", json=INIT, headers=HDR)).status_code == 200
    asyncio.run(go())


def test_instructions_name_the_stop_rule_and_the_division_of_labour():
    assert "saturation" in server.INSTRUCTIONS and "never links cells" in server.INSTRUCTIONS
    assert server.mcp.instructions == server.INSTRUCTIONS
