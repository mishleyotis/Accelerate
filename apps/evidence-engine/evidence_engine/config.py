"""Runtime configuration, read once from the environment.

Every knob has a committed default so the engine runs offline in CI with
no environment at all; production sets the few that name a deployment
(the backend URLs, the bucket, the identity line SEC asks for).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # ── backends ────────────────────────────────────────────────────────
    #: SearXNG base URL (its JSON API: GET /search?format=json). Empty
    #: disables the source and the engine says so in `via` / `sources_down`.
    searxng_url: str = field(default_factory=lambda: _env("SEARXNG_URL", ""))
    #: SearXNG's door capability (`/searx-json/<token>/search`); deploy-evidence.sh
    #: mounts it from Secret Manager. Empty = a local SearXNG at the bare URL.
    searxng_path_token: str = field(default_factory=lambda: _env("SEARXNG_PATH_TOKEN", ""))
    #: Send a Cloud Run ID token to SearXNG (the backend is private). On by
    #: default on Cloud Run (K_SERVICE is set there), off everywhere else.
    searxng_id_token: bool = field(default_factory=lambda: _env(
        "EE_SEARXNG_ID_TOKEN", "1" if _env("K_SERVICE", "") else "0") == "1")
    #: Parallel Search MCP endpoint (free, anonymous, rate-limited).
    parallel_mcp_url: str = field(
        default_factory=lambda: _env("PARALLEL_MCP_URL", "https://search.parallel.ai/mcp"))
    #: Set to "0" to keep the engine off Parallel entirely.
    parallel_enabled: bool = field(
        default_factory=lambda: _env("PARALLEL_ENABLED", "1") != "0")
    #: What SEC's fair-access policy asks every automated client to declare.
    #: Form: "<Company> <contact>" — never a person's mailbox in a header.
    sec_user_agent: str = field(default_factory=lambda: _env(
        "SEC_EDGAR_USER_AGENT", "Zennify DMA-Insights evidence-engine (+https://www.zennify.com)"))
    #: The browser-shaped UA entity WAFs accept; identical to the connector's.
    browser_user_agent: str = field(default_factory=lambda: _env(
        "BROWSER_USER_AGENT",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"))

    # ── storage ─────────────────────────────────────────────────────────
    #: Local directory for cleaned text, caches and run state. In production
    #: a GCS bucket mirrors it (`gcs_bucket`); locally this is the whole store.
    data_dir: Path = field(default_factory=lambda: Path(_env("EE_DATA_DIR", "/tmp/evidence-engine")))
    gcs_bucket: str = field(default_factory=lambda: _env("EE_GCS_BUCKET", ""))
    #: edgartools local cache.
    edgar_data_dir: Path = field(default_factory=lambda: Path(_env("EDGAR_LOCAL_DATA_DIR", "/tmp/evidence-engine/edgar")))

    # ── limits (Section 6 of the brief) ─────────────────────────────────
    sec_rps: float = field(default_factory=lambda: _float("EE_SEC_RPS", 8.0))
    host_rps: float = field(default_factory=lambda: _float("EE_HOST_RPS", 1.0))
    #: The Wayback hosts (archive.org, web.archive.org) take a slower lane:
    #: the 403→snapshot path calls them far more often than any one site,
    #: and eval v1 iteration 2 opened web.archive.org's breaker once.
    archive_rps: float = field(default_factory=lambda: _float("EE_ARCHIVE_RPS", 0.5))
    archive_timeout_s: float = field(default_factory=lambda: _float("EE_ARCHIVE_TIMEOUT_S", 30.0))
    #: Parallel: measured ceiling × 0.7. The 2026-10-10 ramp (90 calls, 1/s
    #: then 2/s, p50 1.9 s) recorded no 429 up to 2/s ⇒ 2 × 0.7.
    parallel_rps: float = field(default_factory=lambda: _float("EE_PARALLEL_RPS", 1.4))
    searxng_rps: float = field(default_factory=lambda: _float("EE_SEARXNG_RPS", 4.0))
    # Per-upstream-engine rates behind SearXNG ("google cse:0.2,bing:0.5,…";
    # empty = search.ENGINE_RATES) and how many engines one query may use.
    searxng_engines: str = field(default_factory=lambda: os.environ.get("EE_SEARXNG_ENGINES", ""))
    searxng_engines_per_query: int = field(default_factory=lambda: int(os.environ.get("EE_SEARXNG_ENGINES_PER_QUERY", "3")))
    arxiv_rps: float = field(default_factory=lambda: _float("EE_ARXIV_RPS", 1 / 3))
    fetch_timeout_s: float = field(default_factory=lambda: _float("EE_FETCH_TIMEOUT_S", 12.0))
    #: Wall-clock budget for the fetch phase of ONE research_brief; stragglers
    #: are cancelled and reported, never waited for (measured 2026-10-10).
    fetch_phase_budget_s: float = field(default_factory=lambda: _float("EE_FETCH_PHASE_BUDGET_S", 30.0))
    # The search phase's twin (2026-10-11): queries still queued for a source
    # token at this point are cut and reported. A GUARD, not the pace: the
    # plugin's proxy admits heavy calls so a brief's search runs ~60-90 s, and
    # 120 s + the 30 s fetch phase + ranking stays inside Cloud Run's 300 s.
    search_phase_budget_s: float = field(default_factory=lambda: _float("EE_SEARCH_PHASE_BUDGET_S", 120.0))
    max_bytes: int = field(default_factory=lambda: _int("EE_MAX_BYTES", 20_000_000))
    breaker_min_s: float = field(default_factory=lambda: _float("EE_BREAKER_MIN_S", 30.0))
    breaker_max_s: float = field(default_factory=lambda: _float("EE_BREAKER_MAX_S", 600.0))

    # ── cache TTLs (seconds) ─────────────────────────────────────────────
    search_ttl_s: int = field(default_factory=lambda: _int("EE_SEARCH_TTL_S", 24 * 3600))
    #: Extraction/card TTL by recency class: a CURRENT page is re-read
    #: sooner than an ARCHIVAL one, which does not change.
    text_ttl_current_s: int = field(default_factory=lambda: _int("EE_TEXT_TTL_CURRENT_S", 7 * 86400))
    text_ttl_older_s: int = field(default_factory=lambda: _int("EE_TEXT_TTL_OLDER_S", 90 * 86400))
    text_ttl_undated_s: int = field(default_factory=lambda: _int("EE_TEXT_TTL_UNDATED_S", 14 * 86400))

    # ── ranking ─────────────────────────────────────────────────────────
    #: Dense + cross-encoder rerank is ON only when the models are bundled
    #: in the image (EE_MODELS_DIR set and present). CI runs BM25 only.
    models_dir: str = field(default_factory=lambda: _env("EE_MODELS_DIR", ""))
    embed_model: str = field(default_factory=lambda: _env("EE_EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    rerank_model: str = field(default_factory=lambda: _env("EE_RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2"))

    # ── crawl ───────────────────────────────────────────────────────────
    crawl_page_budget: int = field(default_factory=lambda: _int("EE_CRAWL_PAGE_BUDGET", 60))
    crawl_depth: int = field(default_factory=lambda: _int("EE_CRAWL_DEPTH", 2))

    # ── auth ────────────────────────────────────────────────────────────
    #: Capability token the plugin sends as X-DMA-Path-Token (same pattern
    #: as dmai-mcp). Empty = no header check (local dev / tests only).
    path_token: str = field(default_factory=lambda: _env("EE_PATH_TOKEN", ""))


_SETTINGS: Settings | None = None


def settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS


def reset_settings() -> None:
    """Tests: re-read the environment."""
    global _SETTINGS
    _SETTINGS = None
