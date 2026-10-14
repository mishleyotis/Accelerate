"""The deployed engine reaches its private SearXNG: the door path carries the
capability token and every request carries a Cloud Run ID token for the
backend's URL (2026-10-11: the engine called the bare `/search`, which the
door 404s, so it would have searched Parallel alone)."""
from __future__ import annotations

import asyncio

import httpx

from evidence_engine import gcp_auth as G
from evidence_engine import search as S


def test_the_base_carries_the_door_path_only_when_a_token_is_set():
    assert G.searxng_base("https://sx.run.app/", "tok") == "https://sx.run.app/searx-json/tok"
    assert G.searxng_base("http://127.0.0.1:8080", "") == "http://127.0.0.1:8080"
    assert G.searxng_base("", "tok") == ""


def test_a_search_goes_through_the_door_with_an_id_token_minted_once():
    seen = {"meta": 0, "paths": [], "auth": []}

    def metadata(req: httpx.Request) -> httpx.Response:
        seen["meta"] += 1
        assert req.headers["Metadata-Flavor"] == "Google"
        assert req.url.params["audience"] == "https://sx.run.app"
        return httpx.Response(200, text="ID-TOKEN-1\n")

    def searx(req: httpx.Request) -> httpx.Response:
        seen["paths"].append(req.url.path)
        seen["auth"].append(req.headers.get("Authorization"))
        return httpx.Response(200, json={"results": [{"url": "https://a.test/x", "title": "t", "content": "c"}]},
                              headers={"content-type": "application/json"})

    auth = G.MetadataIdTokenAuth("https://sx.run.app/", transport=httpx.MockTransport(metadata))
    client = S.SearxClient(G.searxng_base("https://sx.run.app", "tok"),
                           httpx.AsyncClient(transport=httpx.MockTransport(searx), auth=auth))

    async def go():
        a = await client.search("acme credit union members")
        b = await client.search("acme digital banking")
        return a, b

    a, b = asyncio.run(go())
    assert a and b
    assert seen["paths"] == ["/searx-json/tok/search", "/searx-json/tok/search"]
    assert seen["auth"] == ["Bearer ID-TOKEN-1", "Bearer ID-TOKEN-1"]
    assert seen["meta"] == 1, "the token is cached, not minted per request"


def test_a_refused_token_is_minted_again_once():
    tokens = iter(["OLD", "NEW"])
    calls = []

    def metadata(req):
        return httpx.Response(200, text=next(tokens))

    def backend(req):
        calls.append(req.headers["Authorization"])
        return httpx.Response(401 if req.headers["Authorization"] == "Bearer OLD" else 200, json={"results": []},
                              headers={"content-type": "application/json"})

    auth = G.MetadataIdTokenAuth("https://sx.run.app", transport=httpx.MockTransport(metadata))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(backend), auth=auth) as c:
            return await c.get("https://sx.run.app/searx-json/tok/search")

    r = asyncio.run(go())
    assert r.status_code == 200 and calls == ["Bearer OLD", "Bearer NEW"]


def test_the_identity_token_is_on_by_default_only_on_cloud_run(monkeypatch):
    from evidence_engine import config
    monkeypatch.delenv("EE_SEARXNG_ID_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert config.Settings().searxng_id_token is False
    monkeypatch.setenv("K_SERVICE", "dmai-evidence")
    assert config.Settings().searxng_id_token is True
    monkeypatch.setenv("EE_SEARXNG_ID_TOKEN", "0")
    assert config.Settings().searxng_id_token is False
