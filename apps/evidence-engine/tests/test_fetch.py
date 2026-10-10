"""The one HTTP door, offline: UA per host, robots, the retry policy
(once on 429/503, never on 403), per-host politeness, Wayback fallback,
URL canonicalisation. Every request goes to an httpx.MockTransport; the
clock and the sleeps are fake. Institutions are invented."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from evidence_engine import config, ratelimit
from evidence_engine.fetch import (HttpFetcher, canonical_url, describe_exception, host_of,
                                   parse_retry_after, url_key)
from evidence_engine.ratelimit import Limits, PerKeyBuckets, TokenBucket

ENTITY = "example-fcu.test"


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t
        self.slept: list[float] = []          # bucket pacing (robots → page is 1 s)
        self.retry_slept: list[float] = []    # the fetcher's retry waits only

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s

    async def retry_sleep(self, s: float) -> None:
        self.retry_slept.append(s)
        self.t += s


class Web:
    """A tiny fake web: routes by (host, path) to a list of responses that
    are consumed in order (the last one repeats); records every request."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list] = {}
        self.log: list[httpx.Request] = []

    def route(self, host: str, path: str, *responses) -> None:
        self.routes[(host, path)] = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.log.append(request)
        key = (request.url.host, request.url.path)
        seq = self.routes.get(key)
        if not seq:
            return httpx.Response(404, text="not here")
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, BaseException):
            if isinstance(item, httpx.HTTPError):
                item.request = request
            raise item
        if callable(item):
            return item(request)
        return item

    def requests_for(self, host: str, path: str | None = None) -> list[httpx.Request]:
        return [r for r in self.log if r.url.host == host and (path is None or r.url.path == path)]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def html(body: str, status: int = 200, **headers) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8", **headers})


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def web():
    w = Web()
    # robots.txt is absent (404 ⇒ allowed) unless a test routes one
    return w


@pytest.fixture(autouse=True)
def _registry(clock):
    ratelimit.reset()
    ratelimit.configure(clock=clock, sleep=clock.sleep)
    yield
    ratelimit.reset()


def make(web: Web, clock: FakeClock, **kw) -> HttpFetcher:
    return HttpFetcher(transport=web.transport(), clock=clock, sleep=clock.retry_sleep,
                       today=lambda: __import__("datetime").date(2026, 10, 10), **kw)


def run(coro):
    return asyncio.run(coro)


# ── UA and headers ─────────────────────────────────────────────────────────

def test_user_agent_declared_for_sec_hosts_and_browser_elsewhere(web, clock):
    for host in ("www.sec.gov", "data.sec.gov", "sec.gov", "notsec.gov", ENTITY):
        web.route(host, "/p", html("<p>Example Federal Credit Union serves its members.</p>"))
    f = make(web, clock)
    s = config.settings()

    async def go():
        for host in ("www.sec.gov", "data.sec.gov", "sec.gov", "notsec.gov", ENTITY):
            r = await f.get(f"https://{host}/p")
            assert r.ok, r.error
        await f.aclose()

    run(go())
    ua = {r.url.host: r.headers["user-agent"] for r in web.log if r.url.path == "/p"}
    assert ua["www.sec.gov"] == s.sec_user_agent
    assert ua["data.sec.gov"] == s.sec_user_agent
    assert ua["sec.gov"] == s.sec_user_agent
    assert ua["notsec.gov"] == s.browser_user_agent
    assert ua[ENTITY] == s.browser_user_agent
    page = web.requests_for(ENTITY, "/p")[0]
    assert page.headers["accept"].startswith("text/html,application/xhtml+xml,application/pdf")
    assert page.headers["accept-encoding"] == "gzip, deflate"
    assert page.headers["accept-language"].startswith("en-US")


def test_accept_without_pdf(web, clock):
    web.route(ENTITY, "/p", html("<p>ok</p>"))
    f = make(web, clock)
    run(f.get(f"https://{ENTITY}/p", accept_pdf=False))
    assert "application/pdf" not in web.requests_for(ENTITY, "/p")[0].headers["accept"]


# ── robots ─────────────────────────────────────────────────────────────────

def test_robots_disallow_blocks_and_never_requests_the_page(web, clock):
    web.route(ENTITY, "/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /private\n"))
    web.route(ENTITY, "/private/report", html("secret"))
    web.route(ENTITY, "/public", html("<p>Annual report of Example Federal Credit Union.</p>"))
    f = make(web, clock)

    async def go():
        r = await f.get(f"https://{ENTITY}/private/report")
        assert r.error == "robots_disallowed" and r.status is None and r.body == b""
        r2 = await f.get(f"https://{ENTITY}/private/report?x=1")
        assert r2.error == "robots_disallowed"
        r3 = await f.get(f"https://{ENTITY}/public")
        assert r3.ok

    run(go())
    assert web.requests_for(ENTITY, "/private/report") == []
    assert len(web.requests_for(ENTITY, "/robots.txt")) == 1       # cached per host
    assert len(web.requests_for(ENTITY, "/public")) == 1


def test_robots_disallow_for_the_browser_token_alone_blocks(web, clock):
    web.route(ENTITY, "/robots.txt", httpx.Response(200, text="User-agent: Mozilla\nDisallow: /\n\nUser-agent: *\nAllow: /\n"))
    web.route(ENTITY, "/p", html("x"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.error == "robots_disallowed"
    assert web.requests_for(ENTITY, "/p") == []


def test_robots_unfetchable_means_allowed(web, clock):
    web.route(ENTITY, "/robots.txt", httpx.ReadTimeout("slow"))
    web.route(ENTITY, "/p", html("<p>Example Federal Credit Union, member-owned since 1952.</p>"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.ok and r.status == 200
    # a 404 robots.txt is the default route: also allowed
    web.route("other.test", "/p", html("<p>ok</p>"))
    assert run(f.get("https://other.test/p")).ok


def test_robots_cache_expires_after_ttl(web, clock):
    web.route(ENTITY, "/robots.txt", httpx.Response(200, text="User-agent: *\nAllow: /\n"))
    web.route(ENTITY, "/p", html("ok"))
    f = make(web, clock)
    run(f.get(f"https://{ENTITY}/p"))
    run(f.get(f"https://{ENTITY}/p"))
    assert len(web.requests_for(ENTITY, "/robots.txt")) == 1
    clock.t += 3601
    run(f.get(f"https://{ENTITY}/p"))
    assert len(web.requests_for(ENTITY, "/robots.txt")) == 2


# ── retry policy ───────────────────────────────────────────────────────────

def test_retry_once_on_503_then_success(web, clock):
    web.route(ENTITY, "/p", html("busy", 503), html("<p>Example Federal Credit Union annual report.</p>"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.ok and r.status == 200
    assert len(web.requests_for(ENTITY, "/p")) == 2
    assert clock.retry_slept == [2.0]
    assert ratelimit.breakers().get(ENTITY).state == "closed"


def test_503_twice_is_reported_and_trips_the_breaker(web, clock):
    web.route(ENTITY, "/p", html("busy", 503))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert not r.ok and r.status == 503
    assert r.error.startswith(f"http 503 from {ENTITY}")
    assert len(web.requests_for(ENTITY, "/p")) == 2                  # exactly one retry
    assert ratelimit.breakers().get(ENTITY).state == "open"
    # the open breaker refuses without a request
    r2 = run(f.get(f"https://{ENTITY}/p"))
    assert r2.error == f"breaker_open:{ENTITY}"
    assert len(web.requests_for(ENTITY, "/p")) == 2


def test_no_retry_on_403_and_the_wording(web, clock):
    web.route(ENTITY, "/p", html("denied", 403, server="cloudflare"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.status == 403 and not r.ok
    assert r.error.startswith(f"http 403 from {ENTITY} (served by cloudflare) (WAF or access denied)")
    assert "find another source" in r.error
    assert len(web.requests_for(ENTITY, "/p")) == 1
    assert clock.retry_slept == []
    br = ratelimit.breakers().get(ENTITY)
    assert br.state == "closed" and br.snapshot()["streak_403"] == 1


def test_429_retry_after_honoured(web, clock):
    web.route(ENTITY, "/p", html("slow down", 429, **{"Retry-After": "7"}),
              html("<p>Example Federal Credit Union annual report.</p>"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.ok
    assert clock.retry_slept == [7.0]
    assert len(web.requests_for(ENTITY, "/p")) == 2


def test_429_twice_opens_the_breaker_with_retry_after(web, clock):
    web.route(ENTITY, "/p", html("slow down", 429, **{"Retry-After": "120"}))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p"))
    assert r.status == 429 and "rate limited" in r.error
    assert clock.retry_slept == []                                    # 120 s is not waited inline
    assert len(web.requests_for(ENTITY, "/p")) == 1
    snap = ratelimit.breakers().get(ENTITY).snapshot()
    assert snap["state"] == "open" and snap["retry_in_s"] == 120.0 and snap["last_kind"] == "429"


def test_404_is_the_url_not_the_host(web, clock):
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/missing"))
    assert r.status == 404 and r.error.startswith(f"http 404 from {ENTITY}")
    assert ratelimit.breakers().get(ENTITY).state == "closed"


# ── politeness ─────────────────────────────────────────────────────────────

class CountingBucket(TokenBucket):
    def __init__(self, name: str) -> None:
        super().__init__(1000.0, 1000, name=name)
        self.calls = 0

    async def acquire(self) -> float:
        self.calls += 1
        return 0.0


class CountingBuckets(PerKeyBuckets):
    def __init__(self) -> None:
        super().__init__(lambda _k: (1.0, 1))

    def get(self, key: str) -> TokenBucket:
        key = key.lower()
        if key not in self._buckets:
            self._buckets[key] = CountingBucket(key)
        return self._buckets[key]


def test_per_host_bucket_acquired_before_every_request_and_sec_bucket_too(web, clock):
    web.route(ENTITY, "/p", html("ok"))
    web.route("www.sec.gov", "/f", html("ok"))
    buckets = CountingBuckets()
    sec = CountingBucket("sec")
    limits = Limits(sources={"sec": sec, "parallel": CountingBucket("parallel"),
                             "searxng": CountingBucket("searxng"), "arxiv": CountingBucket("arxiv")},
                    hosts=buckets)
    f = make(web, clock, limits=limits)

    async def go():
        await f.get(f"https://{ENTITY}/p")                 # robots.txt + page
        await f.get(f"https://{ENTITY}/p")                 # page only (robots cached)
        await f.get("https://www.sec.gov/f")               # robots.txt + page, each also from `sec`

    run(go())
    assert buckets.get(ENTITY).calls == 3
    assert buckets.get("www.sec.gov").calls == 2
    assert sec.calls == 2


def test_host_bucket_paces_two_fetches_one_second_apart(web, clock):
    web.route(ENTITY, "/a", html("a"))
    web.route(ENTITY, "/b", html("b"))
    f = make(web, clock)
    stamps = []

    async def go():
        await f.get(f"https://{ENTITY}/a")
        stamps.append(clock())
        await f.get(f"https://{ENTITY}/b")
        stamps.append(clock())

    run(go())
    assert stamps[1] - stamps[0] >= 1.0                              # 1 req/s per host


# ── transport failures in a producer's words ──────────────────────────────

def test_dns_timeout_and_tls_wording(web, clock):
    web.route("gone.test", "/p", httpx.ConnectError("[Errno -2] Name or service not known"))
    web.route("slow.test", "/p", httpx.ReadTimeout("read timed out"))
    web.route("badcert.test", "/p", httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
    f = make(web, clock)

    async def go():
        a = await f.get("https://gone.test/p")
        b = await f.get("https://slow.test/p")
        c = await f.get("https://badcert.test/p")
        return a, b, c

    a, b, c = run(go())
    assert a.status is None and a.error == "dns failure for gone.test — the URL is wrong or the domain is gone"
    assert b.error == "timed out fetching slow.test after 12s — retry"   # EE_FETCH_TIMEOUT_S default, 2026-10-10
    assert c.error.startswith("tls failure talking to badcert.test")
    assert clock.retry_slept == []                                    # none of these is retried


def test_describe_exception_generic():
    e = httpx.ConnectError("connection refused")
    assert describe_exception(e, "h.test", 30) == "could not connect to h.test: connection refused"


def test_too_large_body_is_cut_and_reported(web, clock, monkeypatch):
    monkeypatch.setenv("EE_MAX_BYTES", "100")
    config.reset_settings()
    web.route(ENTITY, "/big", html("x" * 1000))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/big"))
    assert not r.ok and r.status == 200
    assert r.error == f"too_large: >100 bytes from {ENTITY}"
    assert len(r.body) <= 100


def test_liveness_is_a_get_that_reads_one_chunk(web, clock):
    async def chunks():
        yield b"<html><body>first chunk"
        yield b" second chunk</body></html>"

    web.route(ENTITY, "/p", lambda req: httpx.Response(200, stream=_AsyncStream(chunks()),
                                                       headers={"content-type": "text/html"}))
    f = make(web, clock)
    r = run(f.liveness(f"https://{ENTITY}/p"))
    assert r.status == 200 and r.ok
    assert r.body == b"<html><body>first chunk"
    assert web.requests_for(ENTITY, "/p")[0].method == "GET"


class _AsyncStream(httpx.AsyncByteStream):
    def __init__(self, it) -> None:
        self._it = it

    async def __aiter__(self):
        async for chunk in self._it:
            yield chunk


# ── Wayback fallback ───────────────────────────────────────────────────────

ORIGINAL = f"https://{ENTITY}/news/2024/old-release"
TS = "20240115123456"
RAW = f"https://web.archive.org/web/{TS}id_/{ORIGINAL}"
ARCHIVED_BODY = "<html><body><p>Example Federal Credit Union opened its tenth branch in 2024.</p></body></html>"


def _wayback_available(web: Web, available: bool) -> None:
    payload = {"url": ORIGINAL, "archived_snapshots": (
        {"closest": {"status": "200", "available": True, "timestamp": TS,
                     "url": f"http://web.archive.org/web/{TS}/{ORIGINAL}"}} if available else {})}
    web.route("archive.org", "/wayback/available", httpx.Response(200, json=payload))
    if available:
        web.route("web.archive.org", f"/web/{TS}id_/{ORIGINAL}",
                  html(ARCHIVED_BODY, **{"x-archive-orig-date": "Mon, 15 Jan 2024 12:34:56 GMT"}))


def test_get_or_archive_on_404_returns_archived_id_url_and_body(web, clock):
    _wayback_available(web, True)
    f = make(web, clock)
    r = run(f.get_or_archive(ORIGINAL))
    assert r.ok
    assert r.via == "archived" and r.archive_timestamp == TS
    assert r.url == ORIGINAL
    assert r.final_url == RAW and "id_/" in r.final_url
    assert r.body.decode() == ARCHIVED_BODY
    avail = web.requests_for("archive.org", "/wayback/available")
    assert len(avail) == 1 and avail[0].url.params["url"] == ORIGINAL
    assert web.requests_for("web.archive.org", f"/web/{TS}id_/{ORIGINAL}")


def test_get_or_archive_both_dead_returns_the_failure_and_no_body(web, clock):
    _wayback_available(web, False)
    f = make(web, clock)
    r = run(f.get_or_archive(ORIGINAL))
    assert not r.ok and r.status == 404 and r.via == "live"
    assert r.body == b"not here" or r.error.startswith("http 404")
    assert r.archive_timestamp is None
    assert len(web.requests_for("archive.org", "/wayback/available")) == 1


def test_get_or_archive_live_page_is_not_archived(web, clock):
    web.route(ENTITY, "/news/2024/old-release", html(ARCHIVED_BODY))
    f = make(web, clock)
    r = run(f.get_or_archive(ORIGINAL))
    assert r.ok and r.via == "live"
    assert web.requests_for("archive.org") == []


def test_get_or_archive_403_only_on_a_streak(web, clock):
    web.route(ENTITY, "/news/2024/old-release", html("denied", 403))
    _wayback_available(web, True)
    f = make(web, clock)

    async def go():
        first = await f.get_or_archive(ORIGINAL)                   # streak 1: not dead
        assert first.status == 403 and first.via == "live"
        assert web.requests_for("archive.org") == []
        await f.get(ORIGINAL)                                       # streak 2
        third = await f.get_or_archive(ORIGINAL)                   # streak 3: dead ⇒ archive
        return third

    r = run(go())
    assert r.via == "archived" and r.ok


def test_get_or_archive_timeout_once_then_archive(web, clock):
    """One live attempt, not two (measured 2026-10-10: the retry doubled a
    30 s stall to 60 s per URL on a host that never answered)."""
    web.route(ENTITY, "/news/2024/old-release", httpx.ReadTimeout("slow"))
    _wayback_available(web, True)
    f = make(web, clock)
    r = run(f.get_or_archive(ORIGINAL))
    assert r.via == "archived"
    assert len(web.requests_for(ENTITY, "/news/2024/old-release")) == 1


def test_wayback_snapshot_with_before_timestamp(web, clock):
    _wayback_available(web, True)
    f = make(web, clock)
    snap = run(f.wayback_snapshot(ORIGINAL, before="20240601"))
    assert snap == (RAW, TS)
    assert web.requests_for("archive.org")[0].url.params["timestamp"] == "20240601"


def test_wayback_snapshot_unreadable_api_is_none(web, clock):
    web.route("archive.org", "/wayback/available", httpx.Response(200, text="<html>oops"))
    f = make(web, clock)
    assert run(f.wayback_snapshot(ORIGINAL)) is None


# ── URL canonicalisation ───────────────────────────────────────────────────

@pytest.mark.parametrize("raw, want", [
    ("HTTPS://WWW.Example-FCU.test/About/Us?utm_source=x&utm_medium=y#top",
     "https://www.example-fcu.test/About/Us"),
    ("https://example-fcu.test/a?b=1&fbclid=abc&c=2&gclid=z&mc_cid=q&ref=home",
     "https://example-fcu.test/a?b=1&c=2"),
    ("https://example-fcu.test/a?utm_campaign=only", "https://example-fcu.test/a"),
    ("example-fcu.test/path", "https://example-fcu.test/path"),
    ("//example-fcu.test/path", "https://example-fcu.test/path"),
    ("https://example-fcu.test:443/x", "https://example-fcu.test/x"),
    ("http://example-fcu.test:80/x", "http://example-fcu.test/x"),
    ("https://example-fcu.test:8443/x", "https://example-fcu.test:8443/x"),
    ("https://example-fcu.test", "https://example-fcu.test/"),
    ("https://example-fcu.test/a?", "https://example-fcu.test/a"),
    ("https://example-fcu.test/a?q=1&q=2", "https://example-fcu.test/a?q=1&q=2"),
    ("https://example-fcu.test/docs/Annual%20Report.pdf", "https://example-fcu.test/docs/Annual%20Report.pdf"),
])
def test_canonical_url(raw, want):
    assert canonical_url(raw) == want


@pytest.mark.parametrize("a, b", [
    ("http://www.example-fcu.test/a/", "https://example-fcu.test/a"),
    ("HTTPS://Example-FCU.test/a?x=1#frag", "https://www.example-fcu.test/a?x=1"),
    ("https://example-fcu.test/", "https://www.example-fcu.test"),
    ("https://example-fcu.test/a?utm_source=s", "https://example-fcu.test/a"),
])
def test_url_key_equivalences(a, b):
    assert url_key(a) == url_key(b)


def test_url_key_keeps_distinct_pages_distinct():
    assert url_key("https://example-fcu.test/a") != url_key("https://example-fcu.test/b")
    assert url_key("https://example-fcu.test/a?x=1") != url_key("https://example-fcu.test/a?x=2")
    assert url_key("https://example-fcu.test/a") == "example-fcu.test/a"
    assert url_key("https://www.example-fcu.test/") == "example-fcu.test"
    assert host_of("HTTPS://WWW.Example-FCU.test/x") == "www.example-fcu.test"


def test_parse_retry_after():
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("soon") is None
    secs = parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT", now_wall=1792567680.0 - 60)
    assert secs == pytest.approx(60.0)


def test_invalid_url_has_no_host(web, clock):
    f = make(web, clock)
    r = run(f.get("https:///nohost"))
    assert r.error.startswith("invalid url")
    assert web.log == []


def test_result_carries_retrieval_date_and_final_url(web, clock):
    web.route(ENTITY, "/p", httpx.Response(301, headers={"location": f"https://{ENTITY}/q"}))
    web.route(ENTITY, "/q", html("<p>moved</p>"))
    f = make(web, clock)
    r = run(f.get(f"https://{ENTITY}/p?utm_source=mail"))
    assert r.ok and r.url == f"https://{ENTITY}/p" and r.final_url == f"https://{ENTITY}/q"
    assert r.retrieved_at == "2026-10-10"
    assert json.loads(json.dumps(r.content_type)) == "text/html; charset=utf-8"
