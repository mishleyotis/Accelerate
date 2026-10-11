"""dmai-evidence — the evidence engine over streamable HTTP (FastMCP 4.1).

Six tools, one health resource. Auth follows dmai-mcp exactly: Cloud Run
enforces the Google ID token (run.invoker) before a request reaches this
process, and the capability token travels as the `X-DMA-Path-Token`
header on the static `/mcp` path (or as `/mcp/<token>`); any other path or
a wrong token is a 404 — never a hint. Stateless HTTP with JSON responses,
because Cloud Run may serve consecutive requests from different instances.
"""
from __future__ import annotations

import hmac
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP  # noqa: E402

from evidence_engine import __version__  # noqa: E402
from evidence_engine import ratelimit as RL  # noqa: E402
from evidence_engine.config import settings  # noqa: E402
from evidence_engine.tools import Engine  # noqa: E402

INSTRUCTIONS = (
    "Gold-standard evidence cards for DMA research. Call research_brief first; "
    "stop a facet when coverage.saturation is true; register card['item'] through "
    "register_evidence (or engine.cli evidence) unchanged; use expand_context only "
    "for disambiguation or a challenge; verify_cards before promotion. The engine "
    "never links cells, labels claims beyond the licensed default, or resolves a "
    "conflict.")

mcp = FastMCP("dmai-evidence", version=__version__, instructions=INSTRUCTIONS)

_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


@mcp.tool()
async def research_brief(run_id: str, entity: dict, questions: list[str],
                         sub_vertical: str | None = None, facet: str | None = None,
                         subcap_labels: list[str] | None = None, max_cards: int = 8,
                         token_budget: int = 2400, provenance: str = "standard",
                         reference_date: str | None = None,
                         allow_names_from_cards: dict | None = None) -> dict:
    """Ranked evidence cards for one or more questions about an entity, plus
    a coverage block (novelty, saturation, conflict candidates, the ladder
    rungs searched). One call replaces a search → open → read → excerpt loop.
    `entity`: {legal_name, domains[], aliases[], location, charter, cik,
    ticker}. `facet` ∈ works|fails|value|contradicts|corroborates (omit for
    all five). `subcap_labels` are opaque labels for logging only. A vendor
    name in a question is refused unless `allow_names_from_cards` maps it to
    the card_id it came from. `provenance` ∈ minimal|standard|full."""
    return await engine().research_brief(run_id=run_id, entity=entity, questions=questions,
                                         sub_vertical=sub_vertical, facet=facet, subcap_labels=subcap_labels,
                                         max_cards=max_cards, token_budget=token_budget, provenance=provenance,
                                         reference_date=reference_date, allow_names_from_cards=allow_names_from_cards)


@mcp.tool()
async def crawl_entity(run_id: str, entity: dict, page_budget: int | None = None, depth: int | None = None,
                       path_focus: list[str] | None = None, question: str = "", max_cards: int = 12,
                       token_budget: int = 1500, reference_date: str | None = None) -> dict:
    """Cards from the institution's OWN pages (sitemap + newsroom, press,
    careers, investor relations, disclosures; robots honoured; budget and
    depth capped) with a crawl manifest (seen, fetched, skipped,
    robots-blocked). `path_focus` ⊆ newsroom|careers|ir|disclosures|about."""
    return await engine().crawl_entity(run_id=run_id, entity=entity, page_budget=page_budget, depth=depth,
                                       path_focus=path_focus, question=question, max_cards=max_cards,
                                       token_budget=token_budget, reference_date=reference_date)


@mcp.tool()
async def filings_evidence(run_id: str, cik_or_ticker: str, forms: list[str] | None = None,
                           years: list[int] | None = None, topics: list[str] | None = None,
                           max_cards: int = 10, token_budget: int = 1500, reference_date: str | None = None,
                           entity: dict | None = None) -> dict:
    """Cards anchored in 10-K/10-Q/8-K sections and XBRL facts with exact
    values and filing URLs (edgartools in-process, cached, 8 req/s global)."""
    return await engine().filings_evidence(run_id=run_id, cik_or_ticker=cik_or_ticker, forms=forms, years=years,
                                           topics=topics, max_cards=max_cards, token_budget=token_budget,
                                           reference_date=reference_date, entity=entity)


@mcp.tool()
async def expand_context(context_handle: str, window: int = 2, run_id: str | None = None) -> dict:
    """The sentences around a card's span, ON DEMAND only — for
    disambiguation, a challenger check or a contradiction review."""
    return await engine().expand_context(context_handle=context_handle, window=window, run_id=run_id)


@mcp.tool()
async def verify_cards(run_id: str, card_ids: list[str], recheck_liveness: bool = True) -> dict:
    """Re-run liveness, verbatim-offset integrity, contract and date checks
    on cards. Used by the adversarial verifier and before promotion.
    Confidence only moves down."""
    return await engine().verify_cards(run_id=run_id, card_ids=card_ids, recheck_liveness=recheck_liveness)


@mcp.tool()
async def coverage_report(run_id: str) -> dict:
    """Per-facet and per-label card counts, source diversity, single-source
    concentration (flag > 40%), recency distribution, open conflict
    candidates, saturation by facet, and the ladder rungs searched."""
    return await engine().coverage_report(run_id=run_id)


@mcp.resource("health://sources", name="source health", mime_type="application/json")
def source_health() -> str:
    return json.dumps({"version": __version__, "limits": RL.health(),
                       "backends": {"searxng": bool(settings().searxng_url),
                                    "parallel": settings().parallel_enabled}}, indent=1)


class HeaderPathToken:
    """ASGI wrapper: /mcp with X-DMA-Path-Token, or /mcp/<token>, else 404.
    /healthz is open (Cloud Run's probe). With no token configured (local
    dev, tests) the header check is skipped and said so on stderr once."""

    def __init__(self, inner, token: str):
        self.inner, self.token = inner, token
        # uvicorn delivers the lifespan scope through __call__ (forwarded to
        # the inner Starlette app below); an in-process test client does
        # not, so it enters this instead.
        self.lifespan = lambda: inner.router.lifespan_context(inner)
        if not token:
            print("dmai-evidence: EE_PATH_TOKEN unset — header check DISABLED (local only)", file=sys.stderr)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        path = scope.get("path", "")
        if path == "/healthz":
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            return await send({"type": "http.response.body", "body": b"ok"})
        if path == "/":
            body = (b"dmai-evidence: the DMA Insights evidence engine. Open-source stack: FastMCP, "
                    b"trafilatura, htmldate, pypdfium2, rank-bm25, datasketch, edgartools, fastembed.")
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            return await send({"type": "http.response.body", "body": body})
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if self.token:
            given = headers.get("x-dma-path-token", "")
            if path.startswith("/mcp/"):
                seg = path[len("/mcp/"):].split("/", 1)[0]
                if hmac.compare_digest(seg, self.token):
                    given = self.token
                    scope = dict(scope, path="/mcp" + path[len("/mcp/") + len(seg):], raw_path=b"/mcp")
            if not hmac.compare_digest(given, self.token) or not scope["path"].startswith("/mcp"):
                await send({"type": "http.response.start", "status": 404, "headers": []})
                return await send({"type": "http.response.body", "body": b""})
        elif not path.startswith("/mcp"):
            await send({"type": "http.response.start", "status": 404, "headers": []})
            return await send({"type": "http.response.body", "body": b""})
        return await self.inner(scope, receive, send)


def build_app(token: str | None = None):
    app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)
    return HeaderPathToken(app, settings().path_token if token is None else token)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
