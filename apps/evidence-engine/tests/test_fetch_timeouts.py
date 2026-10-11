"""Measured 2026-10-10 (golden-set run 1): an own-domain host that times out
cost 60 s per URL and a brief 70-170 s. A timeout now trips the host breaker
on the second occurrence, the archive fallback is tried at once, and the
fetch phase of a brief has a wall-clock budget."""
import asyncio

import httpx

from evidence_engine import ratelimit as RL
from evidence_engine.fetch import HttpFetcher

PRESS = "<html><head><title>T</title></head><body><p>Members grew 4.2 percent to 212,000 in 2025.</p></body></html>"


def _fetcher(handler, t):
    async def fake_sleep(s):
        t["now"] += s
    RL.reset()
    RL.configure(clock=lambda: t["now"], sleep=fake_sleep)
    return HttpFetcher(transport=httpx.MockTransport(handler), clock=lambda: t["now"], sleep=fake_sleep, http2=False)


def test_second_timeout_opens_the_host_and_archive_is_tried_at_once():
    t = {"now": 0.0}
    calls = {"slow": 0, "archive": 0, "snap": 0}

    def handler(req):
        h = req.url.host
        if h == "slow.example.test":
            if req.url.path == "/robots.txt":
                return httpx.Response(404)
            calls["slow"] += 1
            raise httpx.ReadTimeout("slow", request=req)
        if h == "archive.org":
            calls["snap"] += 1
            return httpx.Response(200, json={"archived_snapshots": {"closest": {
                "available": True, "status": "200", "timestamp": "20260101000000",
                "url": "http://web.archive.org/web/20260101000000/" + req.url.params["url"]}}})
        if h == "web.archive.org":
            calls["archive"] += 1
            return httpx.Response(200, text=PRESS, headers={"content-type": "text/html"})
        return httpx.Response(404)
    f = _fetcher(handler, t)

    async def go():
        a = await f.get_or_archive("https://slow.example.test/a")
        b = await f.get_or_archive("https://slow.example.test/b")
        c = await f.get_or_archive("https://slow.example.test/c")
        return a, b, c
    a, b, c = asyncio.run(go())
    assert calls["slow"] == 2, "one live attempt per URL, and none after the breaker opened"
    assert a.via == "archived" and b.via == "archived" and c.via == "archived"
    assert c.archive_timestamp == "20260101000000"
    assert RL.breakers().get("slow.example.test").state == "open"
    assert RL.breakers().get("slow.example.test").snapshot()["streak_timeout"] == 2
    RL.reset()


def test_fetch_phase_budget_cancels_stragglers(monkeypatch):
    from evidence_engine import tools as T
    from evidence_engine.store import Store
    import tempfile, pathlib
    monkeypatch.setenv("EE_FETCH_PHASE_BUDGET_S", "0.3")
    from evidence_engine import config
    config.reset_settings()

    class Slow:
        async def get_or_archive(self, url, accept_pdf=True):
            if "hang" in url:
                await asyncio.sleep(5)
            from evidence_engine.types import FetchResult
            return FetchResult(url=url, final_url=url, status=200, content_type="text/html",
                               body=PRESS.encode(), retrieved_at="2026-10-10")
    eng = T.Engine(fetcher=Slow(), store=Store(pathlib.Path(tempfile.mkdtemp())), searx=None, parallel=None)
    hits = [{"url": "https://ok.example.test/p", "url_key": "ok.example.test/p"},
            {"url": "https://hang.example.test/p", "url_key": "hang.example.test/p"}]
    docs, failures = asyncio.run(eng._documents_for_hits(hits, limit=5, reference=None,
                                                         hits_by_key={h["url_key"]: [] for h in hits}))
    assert [d.url for d in docs] == ["https://ok.example.test/p"]
    assert any("fetch_phase_budget" in f["reason"] for f in failures)
    config.reset_settings()


def test_a_refused_connection_counts_like_a_timeout_and_is_dead_at_page_level(monkeypatch):
    """eval v1 iteration 4: one site answered "Server disconnected" 45 times;
    neither the breaker nor the snapshot path had treated that as dead."""
    import httpx
    from evidence_engine import ratelimit as RL
    from evidence_engine.fetch import HttpFetcher, FetchResult
    RL.reset()
    def handler(req):
        raise httpx.ConnectError("Server disconnected without sending a response.", request=req)
    f = HttpFetcher(transport=httpx.MockTransport(handler), http2=False)
    r1 = asyncio.run(f.get("https://down.example.test/a"))
    assert r1.error.startswith("could not connect") and f._is_dead(r1, "down.example.test")
    assert RL.breakers().get("down.example.test").snapshot()["streak_timeout"] == 1
    r2 = asyncio.run(f.get("https://down.example.test/b"))
    assert RL.breakers().get("down.example.test").state == "open"
    RL.reset()
