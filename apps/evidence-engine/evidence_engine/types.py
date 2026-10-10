"""Shared dataclasses — the seams between the engine's modules.

Kept dependency-free so every module (and every test) can build them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FetchResult:
    url: str                      # the URL asked for (canonical)
    final_url: str = ""           # after redirects
    status: int | None = None     # HTTP status, None on transport failure
    content_type: str = ""
    body: bytes = b""
    error: str | None = None      # why it failed, in words a producer can act on
    via: str = "live"             # live | archived | cache
    archive_timestamp: str | None = None   # Wayback snapshot ts when via=archived
    retrieved_at: str = ""        # ISO date
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 300 and bool(self.body)


class Fetcher(Protocol):
    async def get(self, url: str, *, accept_pdf: bool = True) -> FetchResult: ...


@dataclass
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""              # searxng | parallel | crawl | edgar
    engine: str = ""              # upstream engine name when known
    rank: int = 0
    query_id: str = ""
    facet: str = ""
    published: str | None = None  # a date the result carried, if any


@dataclass
class Document:
    """A fetched and cleaned source, ready for ranking and excerpting."""
    url: str
    final_url: str
    text: str                     # trafilatura main-content text (ranking/selection)
    verify_text: str              # connector-identical extraction (verification)
    content_hash: str             # sha256 of `text`
    title: str = ""
    published: str | None = None
    published_basis: str | None = None
    content_type: str = ""
    url_status: str = "live"
    original_url: str | None = None
    archive_timestamp: str | None = None
    retrieved: str = ""
    hits: list = field(default_factory=list)   # SearchHit(s) that led here
    via: str = ""


@dataclass
class EntityRef:
    legal_name: str
    domains: list = field(default_factory=list)
    aliases: list = field(default_factory=list)
    location: str | None = None
    charter: str | None = None
    cik: str | None = None
    ticker: str | None = None
    sub_vertical: str | None = None


@dataclass
class CrawlManifest:
    seen: list = field(default_factory=list)
    fetched: list = field(default_factory=list)
    skipped: list = field(default_factory=list)       # [{url, reason}]
    robots_blocked: list = field(default_factory=list)
    sitemap_urls: int = 0
    budget: int = 0
    depth: int = 0
