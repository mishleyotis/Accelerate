"""evidence_crawler live IO: fetch cited pages, extract a cross-encoder-grounded
excerpt, and fill the empty evidence_index.excerpt in place (+ an ai_enrichments
provenance row). Idempotent and additive — only rows that are still
excerpt-empty are ever touched.

Resilience layers (all here; the pure gates/scorers are in service.py):
  • SSRF: scheme/host gate + resolved-IP must be public (blocks metadata/internal)
  • politeness: robots.txt honored (cached per host), per-host min-interval, an
    identifying User-Agent
  • fault tolerance: connect+read timeouts, capped redirects, response-size cap,
    content-type allowlist, per-host circuit breaker
  • deploy safety: a global wall-clock budget so the job can never overrun its
    Cloud Run timeout — it stops early and reports, same idea as the
    cross-encoder budget guard
"""
from __future__ import annotations

import asyncio
import time
from urllib import robotparser

from sqlalchemy import text

from app.database import get_sessionmaker
from workers.evidence_crawler import service as S

_UA = "DMA-EvidenceBot/1.0 (+https://dma-insights; grounded evidence excerpt backfill)"
_CONNECT_TIMEOUT = 8.0
_READ_TIMEOUT = 15.0
_MAX_BYTES = 3_000_000       # 3 MB cap — refuse to slurp huge pages
_MAX_REDIRECTS = 5
_PER_HOST_MIN_INTERVAL = 1.0  # seconds between requests to the same host
_DEFAULT_BUDGET_SEC = 900.0


async def run(
    *, limit: int | None = None, budget_sec: float = _DEFAULT_BUDGET_SEC,
    min_support: float = S.SUPPORT_FLOOR, dry_run: bool = False,
) -> dict:
    import httpx

    sm = get_sessionmaker()
    rows = await _fetch_targets(sm, limit)
    summary = {
        "targets": len(rows), "fetched": 0, "filled": 0,
        "skipped_ssrf": 0, "skipped_robots": 0, "skipped_host_tripped": 0,
        "fetch_failed": 0, "no_supported_passage": 0, "budget_exhausted": False,
        "dry_run": dry_run,
    }
    if not rows:
        print("# evidence_crawler: no excerpt-empty rows with a fetchable URL")
        return summary

    breaker = S.HostBreaker()
    robots: dict[str, robotparser.RobotFileParser | None] = {}
    last_hit: dict[str, float] = {}
    t0 = time.monotonic()

    timeout = httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    async with httpx.AsyncClient(
        timeout=timeout, limits=limits, follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for row in rows:
            if time.monotonic() - t0 >= budget_sec:
                summary["budget_exhausted"] = True
                print(f"# evidence_crawler: wall-clock budget {budget_sec:.0f}s "
                      f"spent — stopping early (deploy safeguard)", flush=True)
                break

            url = row["source_url"]
            host = S.host_of(url)
            ok, reason = S.url_scheme_host_ok(url)
            if not ok:
                summary["skipped_ssrf"] += 1
                continue
            if breaker.should_skip(host):
                summary["skipped_host_tripped"] += 1
                continue

            html = await _fetch_one(
                client, url, host, robots, last_hit, breaker, summary)
            if html is None:
                continue
            summary["fetched"] += 1

            capability = S.build_capability_query(
                row["source_name"], row["subcap_texts"], row["claim_type"])
            passages = S.extract_passages(html)
            hit = S.best_excerpt(capability, passages, floor=min_support)
            if hit is None:
                summary["no_supported_passage"] += 1
                continue
            excerpt, score = hit
            summary["filled"] += 1
            if not dry_run:
                await _write_back(sm, row, excerpt, score)

    summary["elapsed_sec"] = round(time.monotonic() - t0, 1)
    summary["hosts_tripped"] = breaker.tripped_hosts
    print("# evidence_crawler summary:", flush=True)
    for k, v in summary.items():
        print(f"#   {k}: {v}", flush=True)
    return summary


async def _fetch_one(client, url, host, robots, last_hit, breaker, summary):
    """One resilient fetch: robots → SSRF resolved-IP → per-host throttle →
    GET with size/content-type caps. Returns HTML text or None (reason counted
    into ``summary``). Never raises."""
    import httpx

    # robots.txt (best-effort, cached; fail-open on robots fetch error so a
    # missing/broken robots doesn't block a legitimate public page).
    rp = await _robots_for(client, host, robots)
    if rp is not None and not rp.can_fetch(_UA, url):
        summary["skipped_robots"] += 1
        return None

    # SSRF: every resolved IP must be public (blocks DNS-rebind to internal).
    ok, _reason = await asyncio.to_thread(S.resolve_public_ips, host)
    if not ok:
        summary["skipped_ssrf"] += 1
        return None

    # per-host politeness throttle
    now = time.monotonic()
    wait = _PER_HOST_MIN_INTERVAL - (now - last_hit.get(host, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    last_hit[host] = time.monotonic()

    try:
        r = await client.get(url)
        if r.status_code != 200:
            breaker.record_fail(host)
            summary["fetch_failed"] += 1
            return None
        if not S.acceptable_content_type(r.headers.get("content-type")):
            breaker.record_ok(host)  # reachable, just not text — not a host fault
            summary["fetch_failed"] += 1
            return None
        content = r.content[:_MAX_BYTES]
        breaker.record_ok(host)
        return content.decode(r.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, OSError):
        breaker.record_fail(host)
        summary["fetch_failed"] += 1
        return None


async def _robots_for(client, host, cache):
    if host in cache:
        return cache[host]
    rp: robotparser.RobotFileParser | None = None
    try:
        import httpx
        resp = await client.get(f"https://{host}/robots.txt")
        if resp.status_code == 200 and resp.text:
            rp = robotparser.RobotFileParser()
            rp.parse(resp.text.splitlines())
    except (httpx.HTTPError, OSError):
        rp = None   # fail-open: no usable robots → allow
    cache[host] = rp
    return rp


async def _fetch_targets(sm, limit: int | None) -> list[dict]:
    """Excerpt-empty rows on ACTIVE runs that carry a fetchable http(s) URL,
    with their linked subcap capability text aggregated for the CE query.
    Round-robin across clients so one big client doesn't starve the budget."""
    lim_sql = "LIMIT :lim" if limit else ""
    async with sm() as s:
        rows = (await s.execute(text(f"""
            WITH tgt AS (
              SELECT ei.run_id, ei.e_id, ei.entity_id, ei.source_url,
                     ei.source_name, ei.claim_type, r.ccg_catalog_version AS cv,
                     e.display_id,
                     COALESCE(array_agg(DISTINCT (sc.name || '. ' ||
                        COALESCE(sc.description, '')))
                        FILTER (WHERE sc.name IS NOT NULL), '{{}}') AS subcap_texts,
                     ROW_NUMBER() OVER (PARTITION BY e.display_id
                                        ORDER BY ei.e_id) AS rn
                FROM evidence_index ei
                JOIN runs r ON r.id = ei.run_id
                JOIN entities e ON e.id = r.entity_id
                LEFT JOIN LATERAL unnest(ei.linked_subcap_ids) l(sid) ON TRUE
                LEFT JOIN ccg_subcaps sc ON sc.subcap_id = l.sid
                                        AND sc.version = r.ccg_catalog_version
               WHERE e.status = 'ACTIVE'
                 AND (ei.excerpt IS NULL OR ei.excerpt = '(no excerpt)'
                      OR length(ei.excerpt) < 40)
                 AND ei.source_url ~ '^https?://'
               GROUP BY ei.run_id, ei.e_id, ei.entity_id, ei.source_url,
                        ei.source_name, ei.claim_type, r.ccg_catalog_version,
                        e.display_id
            )
            SELECT * FROM tgt ORDER BY rn, display_id {lim_sql}
        """), ({"lim": limit} if limit else {}))).all()
    return [{
        "run_id": str(r.run_id), "e_id": r.e_id, "entity_id": str(r.entity_id),
        "source_url": r.source_url, "source_name": r.source_name,
        "claim_type": r.claim_type, "cv": r.cv,
        "subcap_texts": list(r.subcap_texts or []),
    } for r in rows]


async def _write_back(sm, row: dict, excerpt: str, score: float) -> None:
    """Fill the excerpt in place (only if still empty — idempotent) + write an
    ai_enrichments provenance row recording the crawl + its support score."""
    async with sm() as s:
        await s.execute(text("""
            UPDATE evidence_index SET excerpt = :exc
             WHERE run_id = CAST(:rid AS uuid) AND e_id = :eid
               AND (excerpt IS NULL OR excerpt = '(no excerpt)'
                    OR length(excerpt) < 40)
        """), {"exc": excerpt[:2000], "rid": row["run_id"], "eid": row["e_id"]})
        await s.execute(text("""
            INSERT INTO ai_enrichments (target_kind, target_id, surface, model,
                enrichment_text, grounding_evidence_ids, grounding_subcap_ids,
                confidence, validators_passed, catalogue_version, created_at)
            VALUES ('entity', CAST(:eid AS uuid), 'evidence_excerpt_crawl',
                'crawler+cross_encoder', :txt, ARRAY[:e], '{}', :conf, TRUE,
                :cv, NOW())
        """), {"eid": row["entity_id"], "txt": excerpt[:2000], "e": row["e_id"],
               "conf": round(float(score), 3), "cv": row["cv"] or "v7.0"})
        await s.commit()
