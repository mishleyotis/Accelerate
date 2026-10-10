"""Search backends (SearXNG JSON API, Parallel Search MCP) and the fan-out.

WHY. Two discovery sources, several queries each; taking one list wastes
the rest and concatenating rewards the chattiest source. The plugin
already fuses with Reciprocal Rank Fusion, k=60 (engine/retrieval.rrf —
Cormack, Clarke & Buettcher 2009), so the engine fuses the same way: a URL
ranked by both sources and several facet queries outranks a URL one list
put first. The card then records which queries and which source found a
page (`provenance.query_ids`, `facet_hints`, `via` — CARD-CONTRACT.md §3;
DISCOVERY.md §4 for the two backends' contracts).

THE RULE.
  - SearxClient: GET {base}/search?q=…&format=json&categories=general&
    language=en-US[&engines=…][&pageno=n]. A 429, a 5xx or a captcha-shaped
    answer raises SourceError(kind) so a breaker can record it.
  - ParallelClient: tool `web_search` {objective, search_queries[≤3],
    session_id=run_id}; the result's results[].{url,title,excerpts[]}
    (structured content, or JSON in a text block) -> SearchHit with the
    first excerpt as snippet. The client object is injectable.
  - fan_out: every query to every enabled source, concurrently under a
    Semaphore(4); (source, query text) cached through the injected cache;
    a source whose breaker is open is skipped and recorded as
    `rerouted_from:<source>`; lists fused by RRF over url_key; ties broken
    by earliest position, then lexical url_key; every origin hit kept on
    the merged record.

No model. The network is reached only through the injected httpx client /
MCP client, so every test runs on a MockTransport and a fake client.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from urllib.parse import urlsplit

import httpx

from .types import SearchHit

RRF_K = 60
CONCURRENCY = 4
PARALLEL_BATCH = 3

_TRACKING_PREFIX = ("utm_",)
_TRACKING = {"gclid", "fbclid", "mc_cid", "mc_eid"}


class SourceError(Exception):
    """A backend answered in a way the breaker should count: kind ∈
    429 | 5xx | captcha | transport | bad_json."""

    def __init__(self, kind: str, source: str = "", detail: str = ""):
        super().__init__(f"{source or 'source'}: {kind}{(' — ' + detail) if detail else ''}")
        self.kind = kind
        self.source = source
        self.detail = detail


# ── URL identity ───────────────────────────────────────────────────────────

def _local_url_key(url: str) -> str:
    """lowercase host, strip www., drop fragment, drop utm_* / click ids,
    strip trailing slash; scheme dropped so http/https are one page."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return str(url or "").strip().lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    query = "&".join(sorted(
        p for p in parts.query.split("&")
        if p and not p.split("=")[0].lower().startswith(_TRACKING_PREFIX)
        and p.split("=")[0].lower() not in _TRACKING))
    path = re.sub(r"/+$", "", parts.path) or ""
    key = host + path
    return key + ("?" + query if query else "")


def url_key(url: str) -> str:
    """The fetch module's canonical key when it exists, else the local one
    with the same rules."""
    try:
        from .fetch import url_key as _fk  # type: ignore
        return _fk(url)
    except Exception:  # noqa: BLE001 — absent or not yet written
        return _local_url_key(url)


# ── SearXNG ────────────────────────────────────────────────────────────────

_CAPTCHA = re.compile(r"captcha|access denied|unusual traffic", re.I)


class SearxClient:
    source = "searxng"

    def __init__(self, base_url: str, http: httpx.AsyncClient):
        self.base_url = base_url.rstrip("/")
        self.http = http

    async def search(self, q: str, *, engines: list[str] | None = None, pageno: int = 1,
                     query_id: str = "", facet: str = "") -> list[SearchHit]:
        params = {"q": q, "format": "json", "categories": "general", "language": "en-US"}
        if engines:
            params["engines"] = ",".join(engines)
        if pageno and pageno > 1:
            params["pageno"] = str(pageno)
        try:
            r = await self.http.get(f"{self.base_url}/search", params=params)
        except httpx.HTTPError as e:
            raise SourceError("transport", self.source, type(e).__name__) from e
        if r.status_code == 429:
            raise SourceError("429", self.source)
        ctype = r.headers.get("content-type", "")
        # captcha-shaped: a 403, or any non-JSON body that asks for a challenge
        # (SearXNG's own ban pages come back 503 with an HTML challenge)
        if r.status_code == 403 or ("json" not in ctype and _CAPTCHA.search(r.text or "")):
            raise SourceError("captcha", self.source, str(r.status_code))
        if r.status_code >= 500:
            raise SourceError("5xx", self.source, str(r.status_code))
        try:
            data = r.json()
        except ValueError as e:
            raise SourceError("bad_json", self.source, str(e)) from e
        hits: list[SearchHit] = []
        for i, item in enumerate(data.get("results") or [], start=1):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            hits.append(SearchHit(
                url=url, title=str(item.get("title") or ""),
                snippet=str(item.get("content") or ""), source=self.source,
                engine=str(item.get("engine") or ""), rank=i, query_id=query_id,
                facet=facet, published=_date_or_none(item.get("publishedDate"))))
        return hits


def _date_or_none(v) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else s or None


# ── Parallel Search MCP ────────────────────────────────────────────────────

class ParallelClient:
    """`client_factory(url)` returns an async context manager with
    `call_tool(name, arguments)`; the default is fastmcp.Client."""
    source = "parallel"

    def __init__(self, url: str, client_factory=None):
        self.url = url
        self._factory = client_factory or _fastmcp_factory

    async def search(self, objective: str, queries: list[str], *, run_id: str,
                     query_id: str = "", facet: str = "") -> list[SearchHit]:
        args = {"objective": objective, "search_queries": list(queries)[:PARALLEL_BATCH],
                "session_id": run_id}
        try:
            async with self._factory(self.url) as client:
                result = await client.call_tool("web_search", args)
        except SourceError:
            raise
        except Exception as e:  # noqa: BLE001 — transport / protocol
            kind = "429" if "429" in str(e) or "rate" in str(e).lower() else "transport"
            raise SourceError(kind, self.source, type(e).__name__) from e
        payload = parse_parallel_result(result)
        hits: list[SearchHit] = []
        for i, item in enumerate(payload.get("results") or [], start=1):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            excerpts = item.get("excerpts") or []
            snippet = str(excerpts[0]) if excerpts else str(item.get("snippet") or item.get("content") or "")
            hits.append(SearchHit(url=url, title=str(item.get("title") or ""), snippet=snippet,
                                  source=self.source, engine="parallel", rank=i,
                                  query_id=query_id, facet=facet,
                                  published=_date_or_none(item.get("publish_date") or item.get("published"))))
        return hits


def _fastmcp_factory(url: str):
    from fastmcp import Client  # imported lazily: tests inject a fake
    return Client(url)


def parse_parallel_result(result) -> dict:
    """Structured content when the server gave it; else the first text block
    that parses as JSON; else {results: []}."""
    if isinstance(result, dict):
        return result if "results" in result else {"results": result.get("results", [])}
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict) and sc.get("results") is not None:
        return sc
    data = getattr(result, "data", None)
    if isinstance(data, dict) and data.get("results") is not None:
        return data
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "results" in parsed:
            return parsed
        if isinstance(parsed, list):
            return {"results": parsed}
    return {"results": []}


# ── fan-out + RRF ──────────────────────────────────────────────────────────

#: SourceError kinds -> the breaker vocabulary in ratelimit.FAILURE_KINDS;
#: a shape the breaker does not count is reported as a 5xx-class failure.
_BREAKER_KIND = {"429": "429", "captcha": "captcha", "5xx": "5xx",
                 "transport": "5xx", "bad_json": "5xx", "exception": "5xx"}


def _breaker_for(breakers, source: str):
    """A per-source breaker when `breakers` is keyed (ratelimit.PerKeyBreakers
    or anything with .get(source)), else None."""
    get = getattr(breakers, "get", None)
    if callable(get) and not hasattr(breakers, "is_open"):
        try:
            return get(source)
        except Exception:  # noqa: BLE001
            return None
    return None


def _breaker_open(breakers, source: str) -> bool:
    """Two shapes: a registry with is_open(source) (tests, simple stores) or
    a keyed set of ratelimit.CircuitBreaker with allow()."""
    if breakers is None:
        return False
    fn = getattr(breakers, "is_open", None)
    if callable(fn):
        return bool(fn(source))
    b = _breaker_for(breakers, source)
    if b is not None and callable(getattr(b, "allow", None)):
        return not b.allow()
    return False


def _breaker_record(breakers, source: str, kind: str | None) -> None:
    if breakers is None:
        return
    b = _breaker_for(breakers, source)
    if b is not None:
        target, args = (b, (_BREAKER_KIND.get(kind, "5xx"),)) if kind else (b, ())
    else:
        target, args = (breakers, (source, kind)) if kind else (breakers, (source,))
    fn = getattr(target, "record_failure" if kind else "record_success", None)
    if not callable(fn):
        return
    try:
        fn(*args)
    except TypeError:
        if kind:
            fn(args[0])
    except ValueError:
        pass                                   # a kind this breaker does not count


def _hit_dicts(hits: list[SearchHit]) -> list[dict]:
    return [asdict(h) for h in hits]


def _hits_from(dicts: list[dict], *, query_id: str, facet: str) -> list[SearchHit]:
    out = []
    for d in dicts:
        h = SearchHit(**{k: d.get(k) for k in SearchHit.__dataclass_fields__ if k in d})
        h.query_id, h.facet = query_id, facet
        out.append(h)
    return out


async def fan_out(queries: list[dict], *, searx: SearxClient | None = None,
                  parallel: ParallelClient | None = None, run_id: str = "",
                  bucket_wait=None, cache=None, breakers=None,
                  question: str | None = None, concurrency: int = CONCURRENCY) -> dict:
    """-> {hits: [merged], per_source: {source: {count, calls, cached, error}},
    rerouted: ['rerouted_from:<source>', …], lists: n}.

    A merged hit: {url, url_key, title, snippet, score, lists_ranking_it,
    best_rank, sources, query_ids, facets, published, via, hits: [SearchHit]}."""
    sem = asyncio.Semaphore(max(1, concurrency))
    per_source: dict[str, dict] = {}
    rerouted: list[str] = []
    lists: dict[tuple[str, str], list[SearchHit]] = {}
    tasks = []

    def ps(source: str) -> dict:
        return per_source.setdefault(source, {"count": 0, "calls": 0, "cached": 0, "error": None})

    async def run_one(source: str, list_key: str, cache_key: str, query_id: str, facet: str, call):
        async with sem:
            rec = ps(source)
            if cache is not None:
                try:
                    cached = cache.get(cache_key)
                except Exception:  # noqa: BLE001
                    cached = None
                if cached is not None:
                    rec["cached"] += 1
                    hits = _hits_from(list(cached), query_id=query_id, facet=facet)
                    rec["count"] += len(hits)
                    lists[(source, list_key)] = hits
                    return
            if bucket_wait is not None:
                await bucket_wait(source)
            rec["calls"] += 1
            try:
                # Request coalescing (brief §6a): identical in-flight queries
                # from parallel agents share ONE upstream call.
                from . import ratelimit as _rl
                hits = await _rl.coalescer().get((source, cache_key), call)
            except SourceError as e:
                rec["error"] = e.kind
                _breaker_record(breakers, source, e.kind)
                return
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"exception:{type(e).__name__}"
                _breaker_record(breakers, source, "exception")
                return
            _breaker_record(breakers, source, None)
            rec["count"] += len(hits)
            lists[(source, list_key)] = hits
            if cache is not None:
                try:
                    cache.put(cache_key, _hit_dicts(hits))
                except Exception:  # noqa: BLE001
                    pass

    enabled = [(c.source, c) for c in (searx, parallel) if c is not None]
    for source, client in enabled:
        if _breaker_open(breakers, source):
            tag = f"rerouted_from:{source}"
            if tag not in rerouted:
                rerouted.append(tag)
            ps(source)["error"] = "breaker_open"
            continue
        if source == "searxng":
            for q in queries:
                qid, text, facet = q.get("query_id", ""), q["text"], q.get("facet", "")
                tasks.append(run_one(source, qid, f"{source}|{text}", qid, facet,
                                     lambda text=text, qid=qid, facet=facet, client=client:
                                     client.search(text, query_id=qid, facet=facet)))
        else:
            # Parallel takes up to three queries per call; batch within a facet
            # so the facet attribution of a hit stays exact.
            by_facet: dict[str, list[dict]] = {}
            for q in queries:
                by_facet.setdefault(q.get("facet", ""), []).append(q)
            for facet, qs in by_facet.items():
                for i in range(0, len(qs), PARALLEL_BATCH):
                    batch = qs[i:i + PARALLEL_BATCH]
                    texts = [b["text"] for b in batch]
                    qid = "+".join(b.get("query_id", "") for b in batch)
                    objective = question or texts[0]
                    tasks.append(run_one(source, qid, f"{source}|{' || '.join(texts)}", qid, facet,
                                         lambda texts=texts, qid=qid, facet=facet, objective=objective, client=client:
                                         client.search(objective, texts, run_id=run_id,
                                                       query_id=qid, facet=facet)))
    if tasks:
        await asyncio.gather(*tasks)
    return {"hits": rrf_merge(lists), "per_source": per_source, "rerouted": rerouted,
            "lists": len(lists)}


def rrf_merge(lists: dict[tuple[str, str], list[SearchHit]], *, k: int = RRF_K) -> list[dict]:
    """Fuse (source, list) ranked lists into one consensus list by url_key.
    Deterministic: lists are visited in sorted key order and the kept URL
    spelling is the shortest (then lexical), so nothing depends on arrival
    order."""
    scores: dict[str, float] = {}
    recs: dict[str, dict] = {}
    for (source, list_key) in sorted(lists):
        for hit in lists[(source, list_key)]:
            key = url_key(hit.url)
            if not key:
                continue
            rank = hit.rank or 1
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            rec = recs.get(key)
            if rec is None:
                rec = recs[key] = {"url": hit.url, "url_key": key, "title": hit.title,
                                   "snippet": hit.snippet, "score": 0.0, "lists_ranking_it": 0,
                                   "best_rank": rank, "sources": [], "query_ids": [],
                                   "facets": [], "published": hit.published, "via": [],
                                   "hits": []}
            rec["lists_ranking_it"] += 1
            rec["best_rank"] = min(rec["best_rank"], rank)
            # the fetchable spelling: shortest, then lexical — a tracking-param
            # variant is longer by construction, so the clean URL is kept
            # whichever list arrived first
            if (len(hit.url), hit.url) < (len(rec["url"]), rec["url"]):
                rec["url"] = hit.url
            if len(hit.snippet or "") > len(rec["snippet"] or ""):
                rec["snippet"] = hit.snippet
            if not rec["title"] and hit.title:
                rec["title"] = hit.title
            if not rec["published"] and hit.published:
                rec["published"] = hit.published
            if hit.source and hit.source not in rec["sources"]:
                rec["sources"].append(hit.source)
            for qid in (hit.query_id or "").split("+"):
                if qid and qid not in rec["query_ids"]:
                    rec["query_ids"].append(qid)
            if hit.facet and hit.facet not in rec["facets"]:
                rec["facets"].append(hit.facet)
            rec["hits"].append(hit)
    out = []
    for key in sorted(scores, key=lambda kk: (-scores[kk], recs[kk]["best_rank"], kk)):
        rec = recs[key]
        rec["score"] = round(scores[key], 6)
        rec["sources"].sort()
        rec["query_ids"].sort()
        rec["facets"].sort()
        rec["via"] = list(rec["sources"])
        out.append(rec)
    return out
