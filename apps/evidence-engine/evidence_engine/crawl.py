"""Entity site crawl — brief §1 (Entity site crawl) and §6 (rate limits).

WHY. The entity's own site is rung 1 of the proxy ladder: newsroom,
careers, investor relations, disclosures and about pages state what the
institution runs, hires for, reports and promises. Search engines surface
a fraction of it; a bounded crawl reads the rest.

THE RULE. A deterministic, bounded breadth-first crawl, inside the
entity's own registrable domains only, that spends at most `page_budget`
page fetches (a fetch that returned 200 HTML or PDF; robots.txt and
sitemaps are free) to at most `depth` hops, and visits focus paths
(newsroom, careers, ir, disclosures, about) before anything else. Every
fetch goes through the injected `types.Fetcher`, which owns robots.txt
(`FetchResult.error == "robots_disallowed"` is recorded, never retried),
and awaits `bucket_wait(host)` first so the per-host bucket (1 request/s
by default, §6) is honoured — this module holds no clock and no socket.
Traps (calendars, deep pagination, long query strings), binary assets,
fragments, off-domain and duplicate URLs are skipped and SAID so in the
manifest; a page whose `<meta name="robots">` says noindex/nofollow is not
followed and is marked `meta-robots`. `rel="nofollow"` on a link is a
ranking hint, not a crawl rule, and is ignored. Two runs over the same
site give the same pages in the same order.
"""
from __future__ import annotations

import heapq
import re
from typing import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .types import CrawlManifest, EntityRef, Fetcher, FetchResult

BucketWait = Callable[[str], Awaitable[None]]

#: Committed focus path lists (brief §1). Order inside a focus is the
#: seed order; order across focuses is the caller's `path_focus`.
FOCUS_PATHS: dict[str, tuple[str, ...]] = {
    "newsroom": ("/news", "/newsroom", "/press", "/press-releases", "/media", "/blog", "/insights"),
    "careers": ("/careers", "/jobs", "/about/careers", "/join-us"),
    "ir": ("/investors", "/investor-relations", "/annual-report", "/annual-reports",
           "/financials", "/financial-reports", "/sec-filings"),
    "disclosures": ("/disclosures", "/privacy", "/terms", "/accessibility", "/security",
                    "/fees", "/rates", "/regulatory"),
    "about": ("/about", "/about-us", "/leadership", "/our-story", "/community"),
}
DEFAULT_FOCUS: tuple[str, ...] = tuple(FOCUS_PATHS.keys())

SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
MAX_NESTED_SITEMAPS = 5
MAX_SITEMAP_URLS = 2_000
MAX_QUERY_LEN = 100
MAX_PAGE_NUMBER = 3
#: Fetch attempts (any status) are bounded too, so a site of 404s cannot
#: spin: the page budget bounds successes, this bounds everything.
ATTEMPT_MULTIPLIER = 4

_BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif",
               ".tiff", ".css", ".js", ".mjs", ".map", ".woff", ".woff2", ".ttf", ".eot",
               ".otf", ".zip", ".gz", ".tar", ".rar", ".7z", ".mp3", ".mp4", ".mov", ".avi",
               ".wmv", ".m4a", ".wav", ".exe", ".dmg", ".pkg", ".msi", ".apk", ".xml", ".rss",
               ".atom", ".json", ".csv", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx")
_TRACKING = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "_ga")
_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>]+))""", re.I)
_META_ROBOTS = re.compile(
    r"""<meta\s+[^>]*name\s*=\s*["']?robots["']?[^>]*content\s*=\s*["']([^"']*)["']""", re.I)
_META_ROBOTS_REV = re.compile(
    r"""<meta\s+[^>]*content\s*=\s*["']([^"']*)["'][^>]*name\s*=\s*["']?robots["']?""", re.I)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_PAGE_SEG = re.compile(r"/page/(\d+)(?:/|$)", re.I)


# ── URL hygiene ────────────────────────────────────────────────────────────

def registrable(domain: str) -> str:
    """`https://www.Example.test/x` → `example.test`."""
    d = (domain or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/", 1)[0].split(":", 1)[0].rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    return d


def in_scope(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains if d)


def url_key(url: str) -> str:
    """Canonical identity of a URL for dedupe: scheme and host lower-cased,
    default ports and fragments dropped, tracking params dropped, remaining
    query sorted, trailing slash removed (except the root)."""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower().rstrip(".")
    port = p.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    q = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
               if k.lower() not in _TRACKING)
    return urlunsplit((scheme, host, path, urlencode(q), ""))


def skip_reason(url: str, domains: list[str]) -> str | None:
    """Why this URL is not crawled, or None when it is eligible."""
    raw = (url or "").strip()
    if not raw or raw.startswith("#"):
        return "fragment_only"
    low = raw.lower()
    if low.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:")):
        return "non_http"
    p = urlsplit(raw)
    if p.scheme.lower() not in ("http", "https"):
        return "non_http"
    if not p.hostname:
        return "non_http"
    if not in_scope(raw, domains):
        return "off_domain"
    path = (p.path or "/").lower()
    if path.endswith(_BINARY_EXT):
        return "binary_asset"
    if len(p.query) > MAX_QUERY_LEN:
        return "query_too_long"
    qs = {k.lower(): v for k, v in parse_qsl(p.query, keep_blank_values=True)}
    if "date" in qs or "month" in qs or "calendar" in qs or "/calendar/" in path:
        return "calendar_trap"
    page = qs.get("page") or qs.get("paged")
    if page is not None and (not page.isdigit() or int(page) > MAX_PAGE_NUMBER):
        return "pagination_trap"
    m = _PAGE_SEG.search(path)
    if m and int(m.group(1)) > MAX_PAGE_NUMBER:
        return "pagination_trap"
    return None


def focus_priority(url: str, focus: list[str]) -> int:
    """0 for a root page, 1 + index of the first focus whose path list
    prefixes this URL's path, len(focus) + 1 otherwise."""
    path = (urlsplit(url).path or "/").lower().rstrip("/") or "/"
    if path == "/":
        return 0
    for i, f in enumerate(focus):
        for prefix in FOCUS_PATHS.get(f, ()):
            if path == prefix or path.startswith(prefix + "/"):
                return 1 + i
    return 1 + len(focus)


def extract_links(markup: str, base: str) -> list[str]:
    """Every href, resolved against `base`, in document order, deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _HREF.finditer(markup):
        href = next((g for g in m.groups() if g is not None), "")
        href = href.strip()
        if not href:
            continue
        if href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            resolved = href
        else:
            resolved = urljoin(base, href)
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def meta_robots(markup: str) -> set[str]:
    """{'noindex', 'nofollow'} ∩ what the page's robots meta declares."""
    head = markup[:20_000]
    found: set[str] = set()
    for rx in (_META_ROBOTS, _META_ROBOTS_REV):
        for m in rx.finditer(head):
            for tok in re.split(r"[,\s]+", m.group(1).lower()):
                if tok in ("noindex", "nofollow", "none"):
                    found.add(tok)
    if "none" in found:
        found |= {"noindex", "nofollow"}
        found.discard("none")
    return found


def _is_html(r: FetchResult) -> bool:
    ct = (r.content_type or "").lower()
    if ct:
        return "html" in ct  # text/html, application/xhtml+xml
    head = r.body[:2048].lower()
    return b"<html" in head or b"<!doctype html" in head or b"<body" in head


def _is_pdf(r: FetchResult) -> bool:
    ct = (r.content_type or "").lower()
    return "pdf" in ct or (not ct and r.body[:5] == b"%PDF-")


def parse_sitemap(xml: str) -> tuple[list[str], list[str]]:
    """(nested sitemap locs, page locs) from a <sitemapindex> / <urlset>."""
    nested: list[str] = []
    pages: list[str] = []
    for block in re.finditer(r"(?is)<(sitemap|url)\b[^>]*>(.*?)</\1>", xml):
        kind, inner = block.group(1).lower(), block.group(2)
        m = _LOC.search(inner)
        if not m:
            continue
        (nested if kind == "sitemap" else pages).append(m.group(1).strip())
    if not nested and not pages:  # tolerate a bare list of <loc>s
        pages = [m.group(1).strip() for m in _LOC.finditer(xml)]
    return nested, pages


# ── the crawl ──────────────────────────────────────────────────────────────

class _Crawl:
    def __init__(self, entity: EntityRef, fetcher: Fetcher, *, page_budget: int, depth: int,
                 path_focus: list[str], bucket_wait: BucketWait | None) -> None:
        self.fetcher = fetcher
        self.budget = max(0, int(page_budget))
        self.depth = max(0, int(depth))
        self.focus = [f for f in (path_focus or []) if f in FOCUS_PATHS] or list(DEFAULT_FOCUS)
        self.bucket_wait = bucket_wait
        self.domains: list[str] = []
        for d in entity.domains or []:
            r = registrable(d)
            if r and r not in self.domains:
                self.domains.append(r)
        self.manifest = CrawlManifest(budget=self.budget, depth=self.depth)
        self.pages: list[dict] = []
        self._seen_keys: set[str] = set()
        self._fetched_keys: set[str] = set()
        self._skipped_urls: set[str] = set()
        self._queue: list[tuple[int, int, int, str]] = []
        self._discovered = 0
        self._page_fetches = 0
        self._attempts = 0
        self._sitemap_fetches = 0
        #: apex → www (or the reverse) learned from the root redirect, so a
        #: focus seed on the other host is a duplicate, not a second fetch.
        self._host_alias: dict[str, str] = {}

    # -- bookkeeping -----------------------------------------------------
    def _skip(self, url: str, reason: str) -> None:
        if url in self._skipped_urls:
            return
        self._skipped_urls.add(url)
        self.manifest.skipped.append({"url": url, "reason": reason})

    def _discover(self, url: str, depth: int) -> None:
        """Record a URL as seen and queue it when eligible and new."""
        if url not in self.manifest.seen:
            self.manifest.seen.append(url)
        reason = skip_reason(url, self.domains)
        if reason:
            self._skip(url, reason)
            return
        key = url_key(url)
        if key in self._seen_keys:
            return
        self._seen_keys.add(key)
        if depth > self.depth:
            self._skip(url, "beyond_depth")
            return
        self._discovered += 1
        heapq.heappush(self._queue, (focus_priority(url, self.focus), depth, self._discovered, url))

    def _aliased(self, url: str) -> str:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        target = self._host_alias.get(host)
        if not target or target == host:
            return url
        netloc = target if p.port is None else f"{target}:{p.port}"
        return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))

    def _learn_alias(self, requested: str, final: str) -> None:
        a, b = urlsplit(requested), urlsplit(final)
        ha, hb = (a.hostname or "").lower(), (b.hostname or "").lower()
        if ha and hb and ha != hb and registrable(ha) == registrable(hb) \
                and (a.path or "/").rstrip("/") == (b.path or "/").rstrip("/"):
            self._host_alias.setdefault(ha, hb)

    async def _get(self, url: str) -> FetchResult:
        if self.bucket_wait is not None:
            await self.bucket_wait((urlsplit(url).hostname or "").lower())
        self._attempts += 1
        try:
            return await self.fetcher.get(url, accept_pdf=True)
        except Exception as e:  # noqa: BLE001 — a fetcher that raises is a transport failure
            return FetchResult(url=url, final_url=url, status=None, error=f"fetch_raised:{type(e).__name__}")

    # -- seeds -----------------------------------------------------------
    async def seed(self) -> None:
        roots: list[str] = []
        for d in self.domains:
            roots += [f"https://{d}/", f"https://www.{d}/"]
        for r in roots:
            self._discover(r, 0)
        for d in self.domains:
            await self._harvest_sitemaps(d)
        for f in self.focus:
            for prefix in FOCUS_PATHS[f]:
                for d in self.domains:
                    self._discover(f"https://{d}{prefix}", 0)

    async def _harvest_sitemaps(self, domain: str) -> None:
        candidates: list[str] = []
        robots = await self._get(f"https://{domain}/robots.txt")
        if robots.ok:
            for line in robots.body.decode("utf-8", "replace").splitlines():
                k, _, v = line.partition(":")
                if k.strip().lower() == "sitemap" and v.strip():
                    candidates.append(v.strip())
        for p in SITEMAP_PATHS:
            candidates.append(f"https://{domain}{p}")
        harvested = 0
        nested_budget = MAX_NESTED_SITEMAPS
        pending = list(dict.fromkeys(candidates))
        visited: set[tuple[str, str]] = set()

        def vkey(u: str) -> tuple[str, str]:
            q = urlsplit(u)
            return registrable(q.hostname or ""), (q.path or "/").rstrip("/")

        while pending and harvested < MAX_SITEMAP_URLS:
            sm = pending.pop(0)
            if vkey(sm) in visited or not in_scope(sm, self.domains):
                continue
            visited.add(vkey(sm))
            r = await self._get(sm)
            self._sitemap_fetches += 1
            if r.error == "robots_disallowed":
                self.manifest.robots_blocked.append(sm)
                continue
            if not r.ok:
                continue
            nested, pages = parse_sitemap(r.body.decode("utf-8", "replace"))
            for n in nested:
                if nested_budget > 0 and vkey(n) not in visited:
                    nested_budget -= 1
                    pending.append(n)
            for u in pages:
                if harvested >= MAX_SITEMAP_URLS:
                    break
                harvested += 1
                self._discover(u, 0)
        self.manifest.sitemap_urls += harvested

    # -- BFS -------------------------------------------------------------
    async def run(self) -> None:
        max_attempts = self.budget * ATTEMPT_MULTIPLIER + 10
        while self._queue and self._page_fetches < self.budget and self._attempts < max_attempts:
            _prio, depth, _idx, url = heapq.heappop(self._queue)
            url = self._aliased(url)
            if url_key(url) in self._fetched_keys:
                self._skip(url, "duplicate_final_url")
                continue
            r = await self._get(url)
            if r.error == "robots_disallowed":
                self.manifest.robots_blocked.append(url)
                continue
            if not r.ok:
                self._skip(url, f"http_{r.status}" if r.status else (r.error or "fetch_failed"))
                continue
            html, pdf = _is_html(r), _is_pdf(r)
            if not (html or pdf):
                self._skip(url, f"content_type:{r.content_type or 'unknown'}")
                continue
            self._page_fetches += 1
            final = r.final_url or url
            self._learn_alias(url, final)
            final_key = url_key(final)
            self._fetched_keys.add(url_key(url))
            if final_key in self._fetched_keys and final_key != url_key(url):
                self._skip(url, "duplicate_final_url")
                continue
            self._fetched_keys.add(final_key)
            if final not in self.manifest.seen:
                self.manifest.seen.append(final)
            robots = meta_robots(r.body.decode("utf-8", "replace")) if html else set()
            if "noindex" in robots:
                self._skip(url, "meta-robots:noindex")
                continue
            self.manifest.fetched.append(url)
            self.pages.append({"url": url, "final_url": final, "status": r.status,
                               "content_type": r.content_type, "body": r.body,
                               "retrieved": r.retrieved_at})
            if "nofollow" in robots:
                self._skip(url, "meta-robots:nofollow")
                continue
            if html:  # every link is SEEN; _discover says why one is not crawled
                for link in extract_links(r.body.decode("utf-8", "replace"), final):
                    self._discover(link, depth + 1)


async def crawl_entity(entity: EntityRef, fetcher: Fetcher, *, page_budget: int, depth: int,
                       path_focus: list[str] | None = None,
                       bucket_wait: BucketWait | None = None
                       ) -> tuple[list[dict], CrawlManifest]:
    """Crawl the entity's own domains. Returns (pages, manifest).

    pages: [{url, final_url, status, content_type, body, retrieved}] in
    fetch order — at most `page_budget` of them, each a 200 HTML or PDF.
    manifest: every URL discovered (`seen`), the ones fetched, the ones
    skipped with a reason, the ones the fetcher's robots.txt refused, the
    count of sitemap URLs harvested, and the budget/depth used.
    """
    c = _Crawl(entity, fetcher, page_budget=page_budget, depth=depth,
               path_focus=list(path_focus or DEFAULT_FOCUS), bucket_wait=bucket_wait)
    if not c.domains:
        return [], c.manifest
    await c.seed()
    await c.run()
    return c.pages, c.manifest
