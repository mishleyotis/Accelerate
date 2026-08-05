"""svc_api — walking-skeleton read API.

Serves live build state from the tables svc_api may read (catalogue +
serving tier). This skeleton exists so the production URL is real from
stage 2 onward; stage 4 replaces the internals with the full read API
(SQLAlchemy asyncpg, cursor pagination, ETag/304, Brotli) per TRD §19.
It performs no inference, writes nothing, and serves only promoted or
catalogue rows — never staging, never ingested client material.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .pages import ApiError, build_page, etag_for

_pool = {}


def _connect():
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        url = os.environ["LOCAL_DATABASE_URL"]
        host = url.split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(user="postgres", password="local",
                                    host=host, port=5432, database="dma_insights")
    from google.cloud.sql.connector import Connector
    connector = _pool.setdefault("connector", Connector())
    return connector.connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


@asynccontextmanager
async def _lifespan(app):
    yield
    if "connector" in _pool:
        _pool["connector"].close()


app = FastAPI(title="DMA Insights API", lifespan=_lifespan)

# The serving tables the walking skeleton reports on. Counts are computed
# at request time from the tables themselves — never stored (invariant 8).
_PAGE_TABLES = {
    "overview": "overview_scores",
    "heatmap": "heatmap_workbook_scores",
    "insights": "insight_cards",
    "platform": "platform_story",
    "context": "context_timeline",
    "techstack": "techstack_items",
}


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "dmai-api", "stage": "walking-skeleton"}


"""Pillar display names as shipped in every assessment package's
Pillar_Summary tab (P2 varies by audience wording per sub-vertical; this
is the corpus default, overridden per run once run-scoped naming lands).
The catalogue itself carries no pillar display names."""
_PILLAR_NAMES = {
    "P1": ("Strategy, Governance & Culture", "Strategy"),
    "P2": ("Client Experience", "Client"),
    "P3": ("Operations, Risk & Compliance", "Operations"),
    "P4": ("Data, Analytics & Technology", "Data & Tech"),
}


# The sub-vertical vocabulary, as the Surface Specification names it. The
# serving tier stores the code (SV2), not the label, so the label has to come
# from the contract rather than from a code echoed back at the reader.
_SUBVERTICAL_NAMES = {
    "SV1": "Regional Banks", "SV2": "Credit Unions",
    "SV3": "Commercial Lending", "SV4": "CIB & Capital Markets",
    "SV5": "RIAs & Broker-Dealers", "SV6": "Asset Management",
    "SV7": "Insurance Brokers", "SV8": "Insurance Carriers",
    "SV9": "Farm Credit",
}


@app.get("/v1/catalogue")
def catalogue():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM ccg_versions WHERE is_current")
        version = cur.fetchone()[0]
        cur.execute(
            """SELECT category_id, pillar_id, name FROM ccg_categories
                WHERE version = %s ORDER BY category_id""", (version,))
        rows = cur.fetchall()
        # v7.0's capability map puts the ID in its Category column, so the
        # catalogue ships no display names and the loader stored NULL rather
        # than an id masquerading as a name. The names DO exist — every
        # promoted run states them on its ceilings rows — so take the most
        # frequently stated name per category. That is a count over real
        # promoted data, not a guess, and it stops a grid of bare ids.
        cur.execute("""SELECT category_id, category_name, count(*) AS n
                         FROM overview_ceilings
                        WHERE category_name IS NOT NULL
                        GROUP BY category_id, category_name
                        ORDER BY category_id, n DESC, category_name""")
        stated: dict = {}
        for cid, cname, _n in cur.fetchall():
            stated.setdefault(cid, cname)
        categories = [{"id": c, "pillar": p, "name": n or stated.get(c) or c,
                       "name_source": ("catalogue" if n
                                       else ("stated" if stated.get(c) else None)),
                       "weight": None}
                      for c, p, n in rows]
        pillars = [{"id": pid, "name": n, "short": s}
                   for pid, (n, s) in _PILLAR_NAMES.items()]
        return {"version": version, "pillars": pillars, "categories": categories}
    finally:
        conn.close()


@app.get("/v1/directory")
def directory():
    """Promoted entities from the one materialised view the directory is
    allowed to read (invariant 8; 0013). Shaped for the front-end's
    entity rows; anything the serving tier does not carry is null, never
    invented. Empty until the first promote is the correct state."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_id, display_id, legal_name, sub_vertical, size_tier,
                   run_id, request_id, run_seq, is_active, run_status,
                   composite, scored_cells, completed_at, promoted_at,
                   pillars, open_alerts
              FROM serving_directory
             ORDER BY entity_id, run_seq DESC""")
        by_entity: dict = {}
        labels: dict = {}
        for (eid, display_id, name, sub_vertical, size_tier, run_id,
             request_id, run_seq, is_active, run_status, composite,
             scored_cells, completed_at, promoted_at, pillars,
             open_alerts) in cur.fetchall():
            key = (sub_vertical or "UNKNOWN").upper().replace(" ", "_")
            labels[key] = _SUBVERTICAL_NAMES.get(key, sub_vertical or "Unknown")
            ent = by_entity.setdefault(str(eid), {
                "id": display_id, "slug": display_id, "name": name,
                "domain": None, "subvertical": key,
                "size_tier": (size_tier or "").upper() or None,
                "hq": None, "status": "ACTIVE",
                "data_source": "DRIVE_PARSE",
                "open_alerts": 0, "runs": [],
            })
            if is_active:
                ent["overall"] = float(composite) if composite is not None else None
                ent["assessment_id"] = request_id
                ent["assessment_date"] = (completed_at.date().isoformat()
                                          if completed_at else None)
                ent["open_alerts"] = open_alerts or 0
                ent["pillar_scores"] = {
                    p["pillar_id"]: p.get("score")
                    for p in (pillars or []) if p.get("pillar_id")}
            ent["runs"].append({
                "id": request_id, "run_id": str(run_id),
                "date": (completed_at.date().isoformat() if completed_at else None),
                "status": "ACTIVE" if is_active else run_status,
                "data_source": "DRIVE_PARSE",
                "overall": float(composite) if composite is not None else None,
                "subcap_count": scored_cells,
                "promoted_at": promoted_at.isoformat() if promoted_at else None,
            })
        return {"entities": list(by_entity.values()),
                "subvertical_labels": labels,
                "active_runs": [], "pending_review": []}
    finally:
        conn.close()


@app.get("/v1/entities/{display_id}/{page}")
def entity_page(display_id: str, page: str, request: Request,
                response: Response, audience: str = "internal",
                run: str | None = None, role: str | None = None,
                history: bool = False):
    """One promoted page for one entity, redacted for the audience.
    ETag is run_id.promoted_epoch.audience; a matching If-None-Match gets
    304 with no body (TRD §19)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = build_page(cur, page, display_id, audience=audience,
                              run=run, role=role, allow_history=history)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        tag = etag_for(body["run"], body["audience"])
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag,
                                                      "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


@app.get("/v1/ops/import-scans")
def import_scans(limit: int = 20):
    """Recent package-scan executions — the REAL job history the admin
    Import & jobs page renders (counts come from the scan ledger itself;
    nothing here is narrative content)."""
    limit = max(1, min(int(limit), 100))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, started_at, finished_at, status, folders_seen,
                      files_seen, files_new, files_changed, runs_created
                 FROM import_scans ORDER BY id DESC LIMIT %s""", (limit,))
        scans = [{
            "id": r[0],
            "started_at": r[1].isoformat() if r[1] else None,
            "finished_at": r[2].isoformat() if r[2] else None,
            "status": r[3],
            "folders_seen": r[4], "files_seen": r[5],
            "files_new": r[6], "files_changed": r[7],
            "runs_created": r[8],
        } for r in cur.fetchall()]
        return {"scans": scans}
    finally:
        conn.close()


@app.get("/v1/meta")
def meta():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT version, cell_count, category_count, is_current
                         FROM ccg_versions ORDER BY version""")
        catalogues = [{"version": v, "cells": c, "categories": g,
                       "current": bool(cur_flag)}
                      for v, c, g, cur_flag in cur.fetchall()]
        pages = {}
        promoted = set()
        for page, table in _PAGE_TABLES.items():
            cur.execute(f"SELECT count(*), count(DISTINCT run_id) FROM {table}")
            rows, runs = cur.fetchone()
            pages[page] = {"rows": rows, "runs": runs}
            if runs:
                cur.execute(f"SELECT DISTINCT run_id FROM {table}")
                promoted.update(str(r[0]) for r in cur.fetchall())
        return {"catalogues": catalogues,
                "serving": {"pages": pages, "promoted_runs": len(promoted)},
                "note": ("empty serving tables are correct until the first "
                         "run promotes — content enters only through the "
                         "connector")}
    finally:
        conn.close()
