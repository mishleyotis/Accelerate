"""Entity site crawl (brief §1 Entity site crawl, §6 rate limits) — offline.

A fake fetcher serves the committed fixture site under tests/fixtures/site
(an invented institution) on www.example-fcu.test; the apex host redirects
to www; one host is foreign and must never be asked for; /internal/* is
what the fetcher's robots.txt refuses.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from evidence_engine import crawl
from evidence_engine.types import CrawlManifest, EntityRef, FetchResult

SITE = Path(__file__).resolve().parent / "fixtures" / "site"
APEX = "example-fcu.test"
WWW = "www.example-fcu.test"


class FakeFetcher:
    """Serves the fixture tree by path; apex → www redirect; robots.txt
    enforced the way the real fetcher does (error == robots_disallowed)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _file(self, path: str) -> Path | None:
        rel = path.strip("/")
        for cand in ([SITE / "index.html"] if rel == "" else
                     [SITE / rel, SITE / f"{rel}.html", SITE / rel / "index.html"]):
            if cand.is_file():
                return cand
        return None

    async def get(self, url: str, *, accept_pdf: bool = True) -> FetchResult:
        self.calls.append(url)
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if host not in (APEX, WWW):
            return FetchResult(url=url, final_url=url, status=None, error="unserved_host")
        final = url if host == WWW else url.replace(f"://{APEX}", f"://{WWW}", 1)
        if p.path.startswith("/internal") or p.path.startswith("/events"):
            return FetchResult(url=url, final_url=final, status=None, error="robots_disallowed")
        f = self._file(p.path)
        if f is None:
            return FetchResult(url=url, final_url=final, status=404, content_type="text/html",
                               body=b"<html><body>Not found</body></html>", retrieved_at="2026-10-10")
        body = f.read_bytes()
        if f.suffix == ".pdf":
            ct = "application/pdf"
        elif f.suffix == ".xml":
            ct = "application/xml"
        elif f.suffix == ".txt":
            ct = "text/plain"
        else:
            ct = "text/html; charset=utf-8"
        return FetchResult(url=url, final_url=final, status=200, content_type=ct, body=body,
                           retrieved_at="2026-10-10")


def entity() -> EntityRef:
    return EntityRef(legal_name="Example Federal Credit Union", domains=[APEX])


def run(**kw):
    fetcher = FakeFetcher()
    waits: list[str] = []

    async def bucket_wait(host: str) -> None:
        waits.append(host)

    kw.setdefault("page_budget", 40)
    kw.setdefault("depth", 2)
    pages, manifest = asyncio.run(crawl.crawl_entity(entity(), fetcher, bucket_wait=bucket_wait, **kw))
    return pages, manifest, fetcher, waits


def paths(pages) -> list[str]:
    return [urlsplit(p["url"]).path for p in pages]


def test_budget_is_exact_and_counts_only_200_pages():
    pages, manifest, fetcher, _ = run(page_budget=6, path_focus=["newsroom"])
    assert len(pages) == 6
    assert len(manifest.fetched) == 6
    assert manifest.budget == 6
    # the 404 focus seeds (/newsroom, /press, …) cost an attempt but no budget
    assert any(s["reason"] == "http_404" for s in manifest.skipped)
    assert all(p["status"] == 200 for p in pages)


def test_depth_is_respected():
    # /news is a seed (sitemap, depth 0), so its press pages are one hop;
    # /about is one hop from the home page and /about/draft-leadership two
    pages1, m1, f1, _ = run(depth=1, path_focus=["newsroom"])
    assert "/news" in paths(pages1) and "/about" in paths(pages1)
    assert sum(1 for p in paths(pages1) if p.startswith("/news/20")) == 4
    assert not any("/about/draft-leadership" in u for u in f1.calls)
    assert {"url": f"https://{WWW}/about/draft-leadership", "reason": "beyond_depth"} in m1.skipped
    pages2, _, f2, _ = run(depth=2, path_focus=["newsroom"])
    assert any("/about/draft-leadership" in u for u in f2.calls)
    pages0, _, _, _ = run(depth=0, path_focus=["newsroom"])
    assert paths(pages0)[0] == "/" and all(p in ("/", "/news", "/careers", "/investors", "/disclosures/privacy")
                                           for p in paths(pages0))


def test_off_domain_is_never_fetched():
    _, manifest, fetcher, _ = run()
    hosts = {urlsplit(u).hostname for u in fetcher.calls}
    assert hosts <= {APEX, WWW}
    off = [s for s in manifest.skipped if s["reason"] == "off_domain"]
    assert {s["url"] for s in off} >= {"https://external.example.org/partner",
                                       "https://partner.example.org/example-fcu"}
    assert "https://external.example.org/partner" in manifest.seen


def test_focus_ordering_newsroom_before_community():
    pages, _, _, _ = run(page_budget=12, path_focus=["newsroom"])
    ps = paths(pages)
    assert "/community" in ps
    news = [i for i, p in enumerate(ps) if p.startswith("/news")]
    assert news and max(news) < ps.index("/community")
    # the root is always first
    assert ps[0] == "/"


def test_focus_default_is_all_five_and_about_focus_reorders():
    pages, _, _, _ = run(page_budget=12, path_focus=["about"])
    ps = paths(pages)
    assert ps.index("/about") < ps.index("/news")
    assert ps.index("/community") < ps.index("/news")


def test_robots_blocked_recorded_not_retried():
    _, manifest, fetcher, _ = run()
    assert f"https://{WWW}/internal/portal" in manifest.robots_blocked
    assert fetcher.calls.count(f"https://{WWW}/internal/portal") == 1
    assert not any("/internal" in p for p in [urlsplit(u).path for u in manifest.fetched])


def test_sitemap_urls_harvested_and_crawled():
    pages, manifest, fetcher, _ = run(path_focus=["newsroom"])
    assert manifest.sitemap_urls == 6
    # /disclosures/privacy is linked from no page the newsroom focus reaches in
    # its first hops, but the sitemap names it
    assert "/disclosures/privacy" in paths(pages)
    # sitemaps and robots were fetched but are not pages
    assert any(u.endswith("/robots.txt") for u in fetcher.calls)
    assert any(u.endswith("/sitemap.xml") for u in fetcher.calls)
    assert not any(p.endswith((".xml", "robots.txt")) for p in paths(pages))


def test_traps_and_assets_are_skipped_with_reasons():
    _, manifest, fetcher, _ = run()
    reasons = {s["url"]: s["reason"] for s in manifest.skipped}
    assert reasons[f"https://{WWW}/news/page/9"] == "pagination_trap"
    assert reasons[f"https://{WWW}/news?page=12"] == "pagination_trap"
    assert reasons[f"https://{WWW}/events?date=2026-03"] == "calendar_trap"
    assert reasons[f"https://{WWW}/assets/brand.css"] == "binary_asset"
    assert reasons["mailto:memberservices@example-fcu.test"] == "non_http"
    assert reasons["tel:+15555550100"] == "non_http"
    assert any(r == "query_too_long" for r in reasons.values())
    assert not any("/news/page/9" in u or "page=12" in u or "/assets/" in u for u in fetcher.calls)
    # a short, in-bounds pagination query is allowed
    assert f"https://{WWW}/news?page=2" in fetcher.calls


def test_meta_robots_noindex_page_is_marked_and_not_followed():
    pages, manifest, fetcher, _ = run()
    assert f"https://{WWW}/about/draft-leadership" in fetcher.calls
    assert "/about/draft-leadership" not in paths(pages)
    assert {"url": f"https://{WWW}/about/draft-leadership", "reason": "meta-robots:noindex"} in manifest.skipped
    assert not any("/about/secret-page" in u for u in fetcher.calls)


def test_pdf_counts_as_a_page_and_has_no_links_followed():
    pages, _, _, _ = run(path_focus=["ir"])
    pdf = [p for p in pages if p["url"].endswith(".pdf")]
    assert len(pdf) == 1 and pdf[0]["content_type"] == "application/pdf"
    assert pdf[0]["body"].startswith(b"%PDF-")


def test_apex_redirect_to_www_is_one_page_not_two():
    pages, manifest, fetcher, _ = run(page_budget=3, path_focus=["newsroom"])
    page_calls = [u for u in fetcher.calls if not u.endswith(("robots.txt", ".xml"))]
    assert page_calls[0] == f"https://{APEX}/"
    assert pages[0]["url"] == f"https://{APEX}/" and pages[0]["final_url"] == f"https://{WWW}/"
    assert f"https://{WWW}/" not in fetcher.calls, "the www seed is a duplicate of the redirect target"
    assert any(s["reason"] == "duplicate_final_url" for s in manifest.skipped)
    # focus seeds on the apex host are rewritten to www, so /news is fetched once
    assert sum(1 for u in fetcher.calls if urlsplit(u).path == "/news") == 1


def test_deterministic_across_runs():
    p1, m1, f1, _ = run(page_budget=9)
    p2, m2, f2, _ = run(page_budget=9)
    assert [p["url"] for p in p1] == [p["url"] for p in p2]
    assert f1.calls == f2.calls
    assert m1 == m2
    assert isinstance(m1, CrawlManifest)


def test_bucket_wait_called_before_every_fetch_with_the_host():
    _, _, fetcher, waits = run(page_budget=8)
    assert len(waits) == len(fetcher.calls)
    assert waits == [urlsplit(u).hostname for u in fetcher.calls]
    assert set(waits) <= {APEX, WWW}


def test_without_bucket_wait_still_runs():
    fetcher = FakeFetcher()
    pages, manifest = asyncio.run(crawl.crawl_entity(entity(), fetcher, page_budget=2, depth=1))
    assert len(pages) == 2 and manifest.depth == 1


def test_no_domains_crawls_nothing():
    fetcher = FakeFetcher()
    pages, manifest = asyncio.run(crawl.crawl_entity(
        EntityRef(legal_name="Nobody", domains=[]), fetcher, page_budget=5, depth=1))
    assert pages == [] and fetcher.calls == [] and manifest.seen == []


def test_manifest_fields_are_complete():
    pages, m, _, _ = run(page_budget=5)
    assert m.budget == 5 and m.depth == 2
    assert set(m.fetched) == {p["url"] for p in pages}
    assert set(m.fetched) <= set(m.seen)
    assert all({"url", "reason"} == set(s) for s in m.skipped)
    for p in pages:
        assert set(p) == {"url", "final_url", "status", "content_type", "body", "retrieved"}
        assert p["retrieved"] == "2026-10-10"


@pytest.mark.parametrize("url,reason", [
    ("https://www.example-fcu.test/x.PNG", "binary_asset"),
    ("ftp://www.example-fcu.test/x", "non_http"),
    ("https://www.example-fcu.test/cal/?month=3", "calendar_trap"),
    ("https://www.example-fcu.test/news/page/3", None),
    ("https://www.example-fcu.test/news/page/4", "pagination_trap"),
    ("https://sub.example-fcu.test/news", None),
    ("https://example-fcu.test.evil.example/news", "off_domain"),
    ("#top", "fragment_only"),
])
def test_skip_reason_rules(url, reason):
    assert crawl.skip_reason(url, [APEX]) == reason


def test_url_key_canonicalises():
    k = crawl.url_key
    assert k("HTTPS://WWW.Example-FCU.test/News/?utm_source=x#frag") == "https://www.example-fcu.test/News"
    assert k("https://www.example-fcu.test/") == "https://www.example-fcu.test/"
    assert k("https://www.example-fcu.test/a?b=2&a=1") == "https://www.example-fcu.test/a?a=1&b=2"


def test_parse_sitemap_index_and_urlset():
    nested, pages = crawl.parse_sitemap(
        "<sitemapindex><sitemap><loc>https://www.example-fcu.test/s1.xml</loc></sitemap></sitemapindex>")
    assert nested == ["https://www.example-fcu.test/s1.xml"] and pages == []
    nested, pages = crawl.parse_sitemap((SITE / "sitemap.xml").read_text())
    assert nested == [] and len(pages) == 6


def test_nested_sitemaps_bounded_and_harvest_capped():
    class SitemapOnly(FakeFetcher):
        async def get(self, url, *, accept_pdf=True):
            self.calls.append(url)
            p = urlsplit(url)
            if p.path == "/robots.txt":
                return FetchResult(url=url, final_url=url, status=200, content_type="text/plain",
                                   body=b"Sitemap: https://www.example-fcu.test/sitemap_index.xml\n")
            if p.path == "/sitemap_index.xml":
                body = "".join(f"<sitemap><loc>https://www.example-fcu.test/sm{i}.xml</loc></sitemap>"
                               for i in range(20))
                return FetchResult(url=url, final_url=url, status=200, content_type="application/xml",
                                   body=f"<sitemapindex>{body}</sitemapindex>".encode())
            if p.path.startswith("/sm"):
                body = "".join(f"<url><loc>https://www.example-fcu.test/p/{p.path}/{i}</loc></url>"
                               for i in range(1000))
                return FetchResult(url=url, final_url=url, status=200, content_type="application/xml",
                                   body=f"<urlset>{body}</urlset>".encode())
            return FetchResult(url=url, final_url=url, status=404, content_type="text/html", body=b"x")

    fetcher = SitemapOnly()
    pages, manifest = asyncio.run(crawl.crawl_entity(entity(), fetcher, page_budget=0, depth=0))
    nested = [u for u in fetcher.calls if "/sm" in u]
    assert len(nested) <= crawl.MAX_NESTED_SITEMAPS
    assert manifest.sitemap_urls == crawl.MAX_SITEMAP_URLS
    assert pages == []
