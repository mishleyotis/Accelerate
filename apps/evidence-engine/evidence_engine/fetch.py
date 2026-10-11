"""The one HTTP door: polite, identified, fail-closed, archive-aware.

Why this module exists
----------------------
Every byte the engine reads from the web comes through `HttpFetcher`, so
the brief's section 6 rules are applied once and cannot be skipped by a
search client or a crawler: the per-host bucket (1 req/s) before every
request, the global SEC bucket (8 req/s) for `sec.gov` hosts, the per-host
circuit breaker, robots.txt, and the retry policy — **retry once on
429/503, never on 403**. It also carries the connector's two fetch habits
that are measured facts, not taste (DISCOVERY §4,
`plugins/.../engine/fetch.py`): SEC EDGAR answers 403 to a browser UA and
200 to a declared one, so `sec.gov` hosts get `settings.sec_user_agent`;
entity sites behind WAFs refuse bare library UAs, so everything else gets
`settings.browser_user_agent`.

The rules
---------
- A URL is fetched only when robots.txt allows it for both the UA token
  we send and `*`; a robots.txt that cannot be fetched (404, timeout)
  means allowed — the standard reading. Robots files are cached per host
  for an hour.
- A 403 is answered, never retried, and reported in words a producer can
  act on ("find another source"); a 404 means the URL is wrong or the page
  is gone; DNS failure means the URL is wrong; a timeout means retry.
- A body is streamed and reading stops past `settings.max_bytes`
  (`too_large`), so a 2 GB PDF cannot take the service down.
- A dead page is looked up on the Wayback Machine and, when a snapshot
  exists, served from the raw `id_` form — the original bytes without the
  toolbar, which is also what the card's `source_url` must carry for an
  archived page because the connector will fetch and verify against it
  (CARD-CONTRACT §2). When neither works the failed `FetchResult` is
  returned and the caller emits no card: unsourced evidence does not exist.
- `canonical_url` is the URL the card carries (scheme and host
  lower-cased, fragment and tracking parameters dropped); `url_key` is the
  stricter dedupe key (no scheme, no `www.`, no trailing slash).

Everything is injectable for tests: the transport (`httpx.MockTransport`),
the clock, the sleep coroutine and the calendar date. No model, no disk.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import email.utils
import importlib.util
import json
import re
import socket
import ssl
import time
import urllib.robotparser
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit, quote

import httpx

from . import ratelimit
from .tls import trust_context
from .config import settings
from .types import FetchResult

ACCEPT_WITH_PDF = "text/html,application/xhtml+xml,application/pdf,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_NO_PDF = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_ENCODING = "gzip, deflate"
ACCEPT_LANGUAGE = "en-US,en;q=0.9"

#: Suffix-matched like the connector: `data.sec.gov` is covered, `notsec.gov` is not.
DECLARE_HOSTS = ("sec.gov",)
ROBOTS_TTL_S = 3600.0
#: The inline retry sleeps at most this long for a Retry-After; a longer one
#: is left to the breaker (the request is not retried inline).
RETRY_INLINE_MAX_S = 30.0
RETRY_DEFAULT_S = 2.0
WAYBACK_AVAILABLE = "https://archive.org/wayback/available"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"

_TRACKING_EXACT = frozenset({"fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_cid",
                             "mc_eid", "ref", "igshid", "_hsenc", "_hsmi", "_ga"})
_TRACKING_PREFIX = ("utm_",)
_DEFAULT_PORT = {"http": "80", "https": "443"}
_DNS_RE = re.compile(r"getaddrinfo|Name or service not known|nodename nor servname|"
                     r"No address associated|Temporary failure in name resolution|"
                     r"Errno -[235]\b|Name does not resolve", re.I)
_TLS_RE = re.compile(r"\bssl\b|tls|certificate", re.I)
_WAYBACK_URL_RE = re.compile(r"^https?://web\.archive\.org/web/(\d{14})(?:[a-z_]+)?/(.+)$", re.I)


# ── URL canonicalisation ──────────────────────────────────────────────────

def _split(url: str):
    u = (url or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    elif not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", u):
        u = "https://" + u
    return urlsplit(u)


def _host_port(netloc: str, scheme: str) -> str:
    host = netloc.rsplit("@", 1)[-1]           # drop userinfo
    port = ""
    if host.startswith("["):                    # IPv6 literal
        end = host.find("]")
        port_part = host[end + 1:]
        host = host[:end + 1]
        if port_part.startswith(":"):
            port = port_part[1:]
    elif ":" in host:
        host, port = host.rsplit(":", 1)
    host = host.lower().rstrip(".")
    if port and port != _DEFAULT_PORT.get(scheme):
        return f"{host}:{port}"
    return host


def _is_tracking(name: str) -> bool:
    n = name.lower()
    return n in _TRACKING_EXACT or any(n.startswith(p) for p in _TRACKING_PREFIX)


def canonical_url(url: str) -> str:
    """The URL a card carries: scheme + host lower-cased, default port and
    fragment dropped, `utm_*` / click ids / `ref` dropped (other query
    parameters kept in their order and encoding), `https` added when the
    scheme is missing, an empty path made `/`. The host is kept as given
    (`www.` stays) — `url_key` is the comparison form."""
    p = _split(url)
    scheme = p.scheme.lower()
    netloc = _host_port(p.netloc, scheme)
    path = p.path or "/"
    path = quote(path, safe="/%:@!$&'()*+,;=~-._")
    query = "&".join(seg for seg in p.query.split("&")
                     if seg and not _is_tracking(seg.split("=", 1)[0]))
    return urlunsplit((scheme, netloc, path, query, ""))


def url_key(url: str) -> str:
    """The dedupe key: `canonical_url` without the scheme, a leading `www.`
    or a trailing slash, so `http://www.example.test/a/` and
    `https://example.test/a` are one key."""
    p = urlsplit(canonical_url(url))
    host = p.netloc
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    key = host + path
    if p.query:
        key += "?" + p.query
    return key


def host_of(url: str) -> str:
    return urlsplit(canonical_url(url)).hostname or ""


def is_declared_host(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    return any(h == s or h.endswith("." + s) for s in DECLARE_HOSTS)


def user_agent_for(host: str) -> str:
    s = settings()
    return s.sec_user_agent if is_declared_host(host) else s.browser_user_agent


def _ua_token(ua: str) -> str:
    """The product token robots.txt entries are matched against."""
    return ua.split("/", 1)[0].split(" ", 1)[0].strip() or "*"


# ── errors in a producer's words ──────────────────────────────────────────

def describe_status(status: int, host: str, server: str = "") -> str:
    via = f" (served by {server})" if server else ""
    if status in (401, 403):
        return (f"http {status} from {host}{via} (WAF or access denied) — the host answered "
                "and refused; the fact is likely still there, so find another source")
    if status == 404:
        return f"http 404 from {host} — the host does not have this path; the URL is wrong or the page is gone"
    if status == 410:
        return f"http 410 from {host} — the page has been removed"
    if status == 429:
        return f"http 429 from {host} — rate limited; retry later"
    if status >= 500:
        return f"http {status} from {host}{via} — server error; retry later"
    return f"http {status} from {host}{via}"


def describe_exception(exc: BaseException, host: str, timeout_s: float) -> str:
    msg = str(exc)
    cause = exc.__cause__ or exc.__context__
    if isinstance(exc, httpx.TimeoutException):
        return f"timed out fetching {host} after {timeout_s:g}s — retry"
    if isinstance(cause, socket.gaierror) or _DNS_RE.search(msg):
        return f"dns failure for {host} — the URL is wrong or the domain is gone"
    if isinstance(cause, ssl.SSLError) or (isinstance(exc, httpx.ConnectError) and _TLS_RE.search(msg)):
        return f"tls failure talking to {host}: {msg[:120] or type(exc).__name__}"
    if isinstance(exc, httpx.TooManyRedirects):
        return f"too many redirects from {host}"
    if isinstance(exc, httpx.TransportError):
        return f"could not connect to {host}: {msg[:120] or type(exc).__name__}"
    return f"{type(exc).__name__} fetching {host}: {msg[:120]}"


def parse_retry_after(value: str | None, now_wall: float | None = None) -> float | None:
    """Seconds from a Retry-After header (delta-seconds or HTTP-date)."""
    if not value:
        return None
    v = value.strip()
    if re.fullmatch(r"\d+", v):
        return float(v)
    try:
        when = email.utils.parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    now = now_wall if now_wall is not None else time.time()
    return max(0.0, when.timestamp() - now)


def _http2_available() -> bool:
    return importlib.util.find_spec("h2") is not None


# ── the fetcher ────────────────────────────────────────────────────────────

class HttpFetcher:
    """`types.Fetcher`: `await fetcher.get(url)` → `FetchResult`.

    Parameters are for tests and composition: `transport` (an
    `httpx.MockTransport`), `clock` (monotonic seconds), `sleep` (the
    coroutine the retry waits with), `today` (the calendar date stamped on
    `retrieved_at`), `limits` / `breakers` (default: the `ratelimit`
    registry).
    """

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Callable[[], float] | None = None,
                 sleep: Callable[[float], Awaitable[None]] | None = None,
                 today: Callable[[], _dt.date] | None = None,
                 limits: ratelimit.Limits | None = None,
                 breakers: ratelimit.PerKeyBreakers | None = None,
                 http2: bool | None = None,
                 robots_ttl_s: float = ROBOTS_TTL_S) -> None:
        s = settings()
        self._settings = s
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._today = today or _dt.date.today
        self._limits = limits
        self._breakers = breakers
        self._robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, float]] = {}
        self._robots_ttl = robots_ttl_s
        use_http2 = http2 if http2 is not None else _http2_available()
        self._client = httpx.AsyncClient(
            http2=use_http2, follow_redirects=True,
            timeout=httpx.Timeout(s.fetch_timeout_s, connect=min(5.0, s.fetch_timeout_s)), transport=transport,
            max_redirects=10, verify=trust_context())
        self.requests_made = 0

    # composition --------------------------------------------------------
    @property
    def limits(self) -> ratelimit.Limits:
        return self._limits if self._limits is not None else ratelimit.limits()

    @property
    def breakers(self) -> ratelimit.PerKeyBreakers:
        return self._breakers if self._breakers is not None else ratelimit.breakers()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HttpFetcher":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    def _headers(self, host: str, accept_pdf: bool) -> dict[str, str]:
        return {"User-Agent": user_agent_for(host),
                "Accept": ACCEPT_WITH_PDF if accept_pdf else ACCEPT_NO_PDF,
                "Accept-Encoding": ACCEPT_ENCODING,
                "Accept-Language": ACCEPT_LANGUAGE}

    async def _politeness(self, host: str) -> None:
        """Brief §6: the per-host bucket before every request; SEC hosts
        also take from the global `sec` bucket."""
        await self.limits.host(host).acquire()
        if is_declared_host(host):
            await self.limits.source("sec").acquire()

    # robots.txt ---------------------------------------------------------
    async def _robots_for(self, scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        now = self._clock()
        cached = self._robots.get(host)
        if cached is not None and now - cached[1] < self._robots_ttl:
            return cached[0]
        rp: urllib.robotparser.RobotFileParser | None = None
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            await self._politeness(host)
            self.requests_made += 1
            r = await self._client.get(robots_url, headers=self._headers(host, False))
            if r.status_code == 200:
                rp = urllib.robotparser.RobotFileParser(robots_url)
                rp.parse(r.text.splitlines())
            # any other status (404, 403, 5xx): the standard reading is "allowed"
        except (httpx.HTTPError, ValueError):
            rp = None
        self._robots[host] = (rp, now)
        return rp

    async def robots_allowed(self, url: str) -> bool:
        p = urlsplit(canonical_url(url))
        host = p.hostname or ""
        rp = await self._robots_for(p.scheme, p.netloc)
        if rp is None:
            return True
        token = _ua_token(user_agent_for(host))
        return rp.can_fetch(token, url) and rp.can_fetch("*", url)

    # the request --------------------------------------------------------
    async def _request(self, url: str, host: str, accept_pdf: bool, *,
                       first_chunk_only: bool) -> tuple[FetchResult, dict[str, str]]:
        """One request, streamed; the body stops past `max_bytes`. Returns
        the result and the lower-cased response headers."""
        s = self._settings
        res = FetchResult(url=url, retrieved_at=self._today().isoformat())
        headers: dict[str, str] = {}
        t0 = self._clock()
        self.requests_made += 1
        try:
            # Wayback serves a snapshot slowly and honestly; a 12 s clock reads
            # it as dead and opens its breaker (eval v1 iteration 3).
            req_timeout = httpx.Timeout(settings().archive_timeout_s) if ratelimit._is_archive_host(host) else None
            async with self._client.stream("GET", url, headers=self._headers(host, accept_pdf),
                                           timeout=req_timeout) as r:
                res.status = r.status_code
                res.final_url = str(r.url)
                res.content_type = r.headers.get("content-type", "")
                headers = {k.lower(): v for k, v in r.headers.items()}
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > s.max_bytes:
                        res.error = f"too_large: >{s.max_bytes} bytes from {host}"
                        break
                    if first_chunk_only:
                        break
                res.body = bytes(buf[:s.max_bytes])
        except httpx.HTTPError as exc:
            res.error = describe_exception(exc, host, s.fetch_timeout_s)
            res.status = None
        res.elapsed_ms = int((self._clock() - t0) * 1000)
        return res, headers

    async def _get(self, url: str, *, accept_pdf: bool, first_chunk_only: bool) -> FetchResult:
        url = canonical_url(url)
        p = urlsplit(url)
        host = p.hostname or ""
        if not host:
            return FetchResult(url=url, error="invalid url: no host", retrieved_at=self._today().isoformat())
        breaker = self.breakers.get(host)
        if not breaker.allow():
            return FetchResult(url=url, error=f"breaker_open:{host}",
                               retrieved_at=self._today().isoformat())
        if not await self.robots_allowed(url):
            return FetchResult(url=url, error="robots_disallowed", status=None,
                               retrieved_at=self._today().isoformat())

        retried = False
        while True:
            await self._politeness(host)
            res, headers = await self._request(url, host, accept_pdf, first_chunk_only=first_chunk_only)
            status = res.status
            if res.error and res.error.startswith("too_large"):
                breaker.record_success()
                return res
            if status is None:
                # a host that times out, refuses or drops the connection is
                # the same host for the breaker: the 2nd opens it (eval v1
                # iteration 4: 45 "Server disconnected" answers from one site
                # spent the slice, call after call)
                if res.error and (res.error.startswith("timed out") or res.error.startswith("could not connect")
                                  or res.error.startswith("dns failure")):
                    breaker.record_failure("timeout")
                return res                                   # transport failure, described
            if 200 <= status < 400:
                breaker.record_success()
                return res
            server = headers.get("server", "")
            res.error = describe_status(status, host, server)
            if status in (429, 503):
                # retry ONCE after Retry-After (or 2 s); the breaker trips
                # when the retry fails too, or when Retry-After is too long
                # to wait inline — then the host's own figure is honoured
                retry_after = parse_retry_after(headers.get("retry-after"))
                wait = retry_after if retry_after is not None else RETRY_DEFAULT_S
                if not retried and wait <= RETRY_INLINE_MAX_S:
                    retried = True
                    await self._sleep(wait)
                    continue
                breaker.record_failure("429" if status == 429 else "5xx", retry_after)
                return res
            if status in (401, 403):
                breaker.record_failure("403")                # never retried
                return res
            if status >= 500:
                breaker.record_failure("5xx")
                return res
            return res                                       # 404/410/other 4xx: the URL, not the host

    async def get(self, url: str, *, accept_pdf: bool = True) -> FetchResult:
        """Fetch a page politely. `error` is set in a producer's words when
        the page could not be read; `ok` is the one-word verdict."""
        return await self._get(url, accept_pdf=accept_pdf, first_chunk_only=False)

    async def liveness(self, url: str) -> FetchResult:
        """Is the URL alive? A GET that stops after the headers and the
        first chunk — HEAD is answered wrongly by WAFs and many CDNs."""
        return await self._get(url, accept_pdf=True, first_chunk_only=True)

    # Wayback ------------------------------------------------------------
    async def wayback_snapshot(self, url: str, before: str | None = None) -> tuple[str, str] | None:
        """The closest Wayback snapshot of `url` (optionally at or before the
        `YYYYMMDD[hhmmss]` timestamp `before`), as `(raw_snapshot_url,
        timestamp)` with the URL in the `id_` form that serves the original
        bytes. None when there is none or the API could not be read."""
        params = {"url": canonical_url(url)}
        if before:
            params["timestamp"] = before
        host = "archive.org"
        try:
            await self._politeness(host)
            self.requests_made += 1
            r = await self._client.get(WAYBACK_AVAILABLE, params=params,
                                       headers=self._headers(host, False))
            if r.status_code != 200:
                return None
            data = r.json()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            return None
        closest = ((data or {}).get("archived_snapshots") or {}).get("closest") or {}
        if not closest.get("available") or not closest.get("url"):
            return None
        ts = str(closest.get("timestamp") or "")
        m = _WAYBACK_URL_RE.match(str(closest["url"]))
        if m:
            ts = ts or m.group(1)
            original = m.group(2)
        else:
            original = params["url"]
        if not ts:
            return None
        return WAYBACK_RAW.format(ts=ts, url=original), ts

    def _is_dead(self, res: FetchResult, host: str) -> bool:
        if res.error is None:
            return False
        if res.status in (404, 410):
            return True
        if res.status is not None and res.status >= 500:
            return True
        if res.status in (401, 403):
            # A WAF's 403 does not change on a retry and the connector's own
            # fetch would refuse the same live URL; the snapshot is the only
            # path to that page (measured 2026-10-10: 5 of 35 golden URLs were
            # surfaced and then lost to a single 403). The host breaker still
            # opens on the streak.
            return True
        if res.status is None:
            return (res.error.startswith("dns failure") or res.error.startswith("timed out")
                    or res.error.startswith("could not connect") or res.error.startswith("breaker_open"))
        return False

    async def get_or_archive(self, url: str, *, accept_pdf: bool = True) -> FetchResult:
        """Live first; when the page is dead (404/410, DNS, a timeout, an open host breaker,
        5xx after the retry, or a 401/403) serve the
        closest Wayback snapshot with `via="archived"`, `archive_timestamp`
        and `final_url` = the `id_` snapshot URL. Neither: the live failure
        is returned and the caller emits no card."""
        url = canonical_url(url)
        host = host_of(url)
        res = await self.get(url, accept_pdf=accept_pdf)
        if res.ok:
            return res
        # No second live attempt on a timeout (measured 2026-10-10: it doubled
        # a 30 s stall to 60 s per URL on a host that never answered); the
        # host breaker remembers the first and the snapshot is the fallback.
        if not self._is_dead(res, host):
            return res
        snap = await self.wayback_snapshot(url)
        if snap is None:
            return res
        snapshot_url, ts = snap
        arch = await self.get(snapshot_url, accept_pdf=accept_pdf)
        if not arch.ok:
            return res
        arch.url = url
        arch.final_url = snapshot_url
        arch.via = "archived"
        arch.archive_timestamp = ts
        return arch
