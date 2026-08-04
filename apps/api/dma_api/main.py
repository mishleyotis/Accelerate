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

from fastapi import FastAPI

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


@app.get("/v1/catalogue")
def catalogue():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM ccg_versions WHERE is_current")
        version = cur.fetchone()[0]
        cur.execute(
            """SELECT DISTINCT category_id, pillar_id
                 FROM ccg_subcaps WHERE version = %s ORDER BY category_id""",
            (version,))
        # Category display names load with the ccg_categories migration;
        # until then the id is the label (never a guessed name).
        categories = [{"id": c, "pillar": p, "name": c, "weight": None}
                      for c, p in cur.fetchall()]
        pillars = [{"id": pid, "name": n, "short": s}
                   for pid, (n, s) in _PILLAR_NAMES.items()]
        return {"version": version, "pillars": pillars, "categories": categories}
    finally:
        conn.close()


@app.get("/v1/directory")
def directory():
    """Promoted entities only — the serving tier is the only source the
    directory may read (stage 4 replaces this with the materialised
    view). Empty until the first promote is the correct state."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM overview_scores")
        promoted_rows = cur.fetchone()[0]
        return {"entities": [] if not promoted_rows else [],
                "active_runs": [], "pending_review": [],
                "note": "directory fills as runs promote"}
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
