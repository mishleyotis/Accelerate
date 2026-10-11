"""search: SearXNG parsing, breaker-shaped errors, Parallel parsing, fan-out RRF."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from evidence_engine import search
from evidence_engine.search import (ParallelClient, SearchHit, SearxClient, SourceError,
                                    fan_out, rrf_merge, url_key)

QUERIES = [
    {"query_id": "Q-01", "text": '"Example Federal Credit Union" onboarding launched', "facet": "works", "kind": "facet"},
    {"query_id": "Q-02", "text": '"Example Federal Credit Union" onboarding complaint', "facet": "fails", "kind": "facet"},
]


def _searx_json(results):
    return {"query": "x", "number_of_results": len(results), "results": results}


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_searx_parses_json():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_searx_json([
            {"url": "https://www.cutimes.com/2026/01/01/example/", "title": "Example launches",
             "content": "Example Federal Credit Union launched digital onboarding.", "engine": "duckduckgo",
             "publishedDate": "2026-01-01T00:00:00"},
            {"url": "https://example-fcu.test/news/x", "title": "News", "content": "", "engine": "bing"},
        ]), headers={"content-type": "application/json"})

    async def go():
        async with _client(handler) as http:
            return await SearxClient("http://searx.test", http).search("q", query_id="Q-01", facet="works", engines=["bing"], pageno=2)

    hits = _run(go())
    assert "format=json" in seen["url"] and "categories=general" in seen["url"] and "language=en-US" in seen["url"]
    assert "engines=bing" in seen["url"] and "pageno=2" in seen["url"]
    assert [h.rank for h in hits] == [1, 2]
    assert hits[0] == SearchHit(url="https://www.cutimes.com/2026/01/01/example/", title="Example launches",
                                snippet="Example Federal Credit Union launched digital onboarding.", source="searxng",
                                engine="duckduckgo", rank=1, query_id="Q-01", facet="works", published="2026-01-01")


@pytest.mark.parametrize("status,body,ctype,kind", [
    (429, "", "text/plain", "429"),
    (500, "", "text/plain", "5xx"),
    (503, "<html>captcha</html>", "text/html", "captcha"),
    (200, "<html>Please solve this CAPTCHA</html>", "text/html", "captcha"),
])
def test_searx_raises_source_error(status, body, ctype, kind):
    def handler(request):
        return httpx.Response(status, text=body, headers={"content-type": ctype})

    async def go():
        async with _client(handler) as http:
            await SearxClient("http://searx.test", http).search("q")

    with pytest.raises(SourceError) as ei:
        _run(go())
    assert ei.value.kind == kind and ei.value.source == "searxng"


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Result:
    def __init__(self, content=None, structured=None):
        self.content = content or []
        self.structured_content = structured
        self.data = None
        self.is_error = False


class FakeMCP:
    """Stands in for fastmcp.Client: an async context manager with call_tool."""
    calls: list = []

    def __init__(self, url, *, payload=None, as_text=True, raise_exc=None):
        self.url, self.payload, self.as_text, self.raise_exc = url, payload, as_text, raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def call_tool(self, name, arguments):
        FakeMCP.calls.append((name, arguments))
        if self.raise_exc:
            raise self.raise_exc
        if self.as_text:
            return _Result(content=[_Block(json.dumps(self.payload))])
        return _Result(structured=self.payload)


PARALLEL_PAYLOAD = {"results": [
    {"url": "https://www.americanbanker.com/news/example-core", "title": "Example picks core",
     "excerpts": ["Example Federal Credit Union selected a new core.", "Second excerpt."]},
    {"url": "https://cutimes.com/2026/01/01/example", "title": "CU Times", "excerpts": []},
]}


@pytest.mark.parametrize("as_text", [True, False])
def test_parallel_parses_text_and_structured(as_text):
    FakeMCP.calls.clear()
    pc = ParallelClient("https://parallel.test/mcp",
                        client_factory=lambda url: FakeMCP(url, payload=PARALLEL_PAYLOAD, as_text=as_text))
    hits = _run(pc.search("objective", ["q1", "q2", "q3", "q4"], run_id="RUN-TEST", query_id="Q-01+Q-02", facet="works"))
    assert FakeMCP.calls == [("web_search", {"objective": "objective", "search_queries": ["q1", "q2", "q3"],
                                             "session_id": "RUN-TEST"})]
    assert [h.url for h in hits] == ["https://www.americanbanker.com/news/example-core", "https://cutimes.com/2026/01/01/example"]
    assert hits[0].snippet == "Example Federal Credit Union selected a new core."
    assert hits[1].snippet == "" and hits[0].source == "parallel" and hits[0].rank == 1


def test_parallel_transport_error_is_a_source_error():
    pc = ParallelClient("https://parallel.test/mcp",
                        client_factory=lambda url: FakeMCP(url, raise_exc=RuntimeError("HTTP 429 Too Many Requests")))
    with pytest.raises(SourceError) as ei:
        _run(pc.search("o", ["q"], run_id="R"))
    assert ei.value.kind == "429" and ei.value.source == "parallel"


def test_url_key_rules():
    assert url_key("HTTPS://WWW.Example-FCU.test/News/x/?utm_source=a&b=1#frag") == "example-fcu.test/News/x?b=1"
    assert url_key("http://example-fcu.test/news/x") == url_key("https://www.example-fcu.test/news/x/")


# ── fan-out ───────────────────────────────────────────────────────────────

class Cache:
    def __init__(self):
        self.d = {}
        self.gets = 0

    def get(self, k):
        self.gets += 1
        return self.d.get(k)

    def put(self, k, v):
        self.d[k] = v


class Breakers:
    def __init__(self, open_sources=()):
        self.open = set(open_sources)
        self.failures = []

    def is_open(self, source):
        return source in self.open

    def record_failure(self, source, kind):
        self.failures.append((source, kind))

    def record_success(self, source):
        pass


CONSENSUS = "https://www.cutimes.com/2026/01/01/example/"
SOLO = "https://springfield-daily.test/example-top"


def _searx_handler_factory(counter):
    def handler(request):
        counter["n"] += 1
        q = request.url.params.get("q", "")
        if "complaint" in q:
            results = [{"url": SOLO, "title": "solo"}, {"url": CONSENSUS, "title": "c"}]
        else:
            results = [{"url": CONSENSUS, "title": "c", "content": "longer snippet here"},
                       {"url": "https://example-fcu.test/news/x", "title": "own"}]
        return httpx.Response(200, json=_searx_json(results), headers={"content-type": "application/json"})
    return handler


def test_fan_out_rrf_consensus_outranks_solo_number_one():
    counter = {"n": 0}
    parallel_payload = {"results": [{"url": "https://cutimes.com/2026/01/01/example?utm_campaign=x", "title": "c", "excerpts": ["p"]}]}

    async def go():
        async with _client(_searx_handler_factory(counter)) as http:
            sx = SearxClient("http://searx.test", http)
            pc = ParallelClient("https://parallel.test/mcp", client_factory=lambda url: FakeMCP(url, payload=parallel_payload))
            return await fan_out(QUERIES, searx=sx, parallel=pc, run_id="RUN-TEST", question="the question")

    out = _run(go())
    hits = out["hits"]
    assert hits[0]["url_key"] == url_key(CONSENSUS)
    assert hits[0]["lists_ranking_it"] == 4                       # 2 searx lists + 2 parallel batches
    assert hits[0]["sources"] == ["parallel", "searxng"]
    assert hits[0]["query_ids"] == ["Q-01", "Q-02"] and hits[0]["facets"] == ["fails", "works"]
    assert hits[0]["snippet"] == "longer snippet here"
    assert hits[0]["url"] == CONSENSUS                              # shortest spelling wins over the utm_ variant
    assert len(hits[0]["hits"]) == 4 and all(isinstance(h, SearchHit) for h in hits[0]["hits"])
    assert hits[0]["score"] > hits[1]["score"]
    solo = next(h for h in hits if h["url_key"] == url_key(SOLO))
    assert solo["best_rank"] == 1 and solo["lists_ranking_it"] == 1
    assert out["per_source"]["searxng"] == {"count": 4, "calls": 2, "cached": 0, "error": None}
    assert out["per_source"]["parallel"]["calls"] == 2 and out["rerouted"] == []
    assert out["lists"] == 4


def test_fan_out_cache_hit_avoids_second_upstream_call():
    counter = {"n": 0}
    cache = Cache()

    async def go():
        async with _client(_searx_handler_factory(counter)) as http:
            sx = SearxClient("http://searx.test", http)
            a = await fan_out(QUERIES[:1], searx=sx, parallel=None, run_id="R", cache=cache)
            b = await fan_out(QUERIES[:1], searx=sx, parallel=None, run_id="R", cache=cache)
            return a, b

    a, b = _run(go())
    assert counter["n"] == 1
    assert a["per_source"]["searxng"]["calls"] == 1 and b["per_source"]["searxng"]["calls"] == 0
    assert b["per_source"]["searxng"]["cached"] == 1
    assert [h["url_key"] for h in a["hits"]] == [h["url_key"] for h in b["hits"]]
    assert b["hits"][0]["hits"][0].query_id == "Q-01"


def test_fan_out_open_breaker_reroutes_and_records():
    counter = {"n": 0}
    br = Breakers(open_sources={"searxng"})
    pl = {"results": [{"url": SOLO, "title": "s", "excerpts": ["e"]}]}

    async def go():
        async with _client(_searx_handler_factory(counter)) as http:
            sx = SearxClient("http://searx.test", http)
            pc = ParallelClient("https://parallel.test/mcp", client_factory=lambda url: FakeMCP(url, payload=pl))
            return await fan_out(QUERIES, searx=sx, parallel=pc, run_id="R", breakers=br)

    out = _run(go())
    assert counter["n"] == 0
    assert out["rerouted"] == ["rerouted_from:searxng"]
    assert out["per_source"]["searxng"]["error"] == "breaker_open"
    assert [h["sources"] for h in out["hits"]] == [["parallel"]]


def test_fan_out_source_error_is_recorded_on_breaker_not_raised():
    br = Breakers()
    waited = []

    def handler(request):
        return httpx.Response(429)

    async def wait(source):
        waited.append(source)

    async def go():
        async with _client(handler) as http:
            return await fan_out(QUERIES, searx=SearxClient("http://searx.test", http), parallel=None,
                                 run_id="R", breakers=br, bucket_wait=wait)

    out = _run(go())
    assert out["hits"] == [] and out["per_source"]["searxng"]["error"] == "429"
    assert br.failures == [("searxng", "429"), ("searxng", "429")]
    assert waited == ["searxng", "searxng"]


def test_rrf_merge_is_order_independent_and_tie_broken_lexically():
    a = [SearchHit(url="https://b.test/1", source="searxng", rank=1, query_id="Q-01"),
         SearchHit(url="https://a.test/1", source="searxng", rank=2, query_id="Q-01")]
    b = [SearchHit(url="https://a.test/1", source="parallel", rank=1, query_id="Q-01"),
         SearchHit(url="https://b.test/1", source="parallel", rank=2, query_id="Q-01")]
    x = rrf_merge({("searxng", "Q-01"): a, ("parallel", "Q-01"): b})
    y = rrf_merge({("parallel", "Q-01"): b, ("searxng", "Q-01"): a})
    assert [h["url_key"] for h in x] == [h["url_key"] for h in y] == ["a.test/1", "b.test/1"]
    assert x[0]["score"] == x[1]["score"] == round(1 / 61 + 1 / 62, 6)
    assert search.RRF_K == 60


def test_fan_out_drives_the_real_per_key_breakers():
    """The sibling ratelimit.PerKeyBreakers shape: get(source).allow() /
    record_failure(kind). A 429 opens it; the next fan-out reroutes."""
    ratelimit = pytest.importorskip("evidence_engine.ratelimit")
    br = ratelimit.PerKeyBreakers()

    def handler(request):
        return httpx.Response(429)

    async def go():
        async with _client(handler) as http:
            sx = SearxClient("http://searx.test", http)
            first = await fan_out(QUERIES[:1], searx=sx, parallel=None, run_id="R", breakers=br)
            second = await fan_out(QUERIES[:1], searx=sx, parallel=None, run_id="R", breakers=br)
            return first, second

    first, second = _run(go())
    assert first["per_source"]["searxng"]["error"] == "429"
    assert br.get("searxng").state == "open"
    assert second["rerouted"] == ["rerouted_from:searxng"] and second["per_source"]["searxng"]["calls"] == 0
