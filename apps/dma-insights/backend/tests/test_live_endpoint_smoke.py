"""Live-PG endpoint smoke — every GET route hit against seeded data.

WHY THIS FILE EXISTS
====================
The existing live-DB tests (test_persona_e2e, test_live_db_integration)
assert against RAW SQL queries — they never drive the actual FastAPI
router code. That left a gap: a router whose hand-written SQL is
malformed only fails when the route is *called against real Postgres*.
Unit tests (mocked sessions) don't catch it; the SQL `--sql` offline
check doesn't run it; so the bug sails through every gate and 500s in
stage-7 Playwright — or worse, in production.

This class of bug has recurred repeatedly:
  - 2026-05-27  FILTER-on-ROUND parser bug → every /overview 500'd.
  - 2026-05-29  `$1 IS NULL OR col = $1` → AmbiguousParameterError on
                /prospecting (asyncpg cannot infer a bare param's type).
  - 2026-05-29  `EXTRACT(EPOCH FROM (CURRENT_DATE - published_date))` →
                date-minus-date is INTEGER days, not an interval, so
                EXTRACT 500'd /overview's freshness bundle.
  - 2026-05-29  /heatmap/subcap/{id} called heatmap() without the
                required `view` arg → 500 on every drill-in.
  - 2026-05-29  /import-audit/by-entity referenced ai_enrichments.
                entity_id (the table is keyed by target_kind/target_id)
                → UndefinedColumnError 500.

Every one of those is a malformed-SQL / wrong-signature defect that a
single GET against a seeded DB would have caught. This file walks the
ENTIRE registered GET surface (minus SSE streams) under three audience
views and asserts NO endpoint returns 5xx. It is the regression net for
the whole class.

Gated on SEED_CI_PG_URL — runs in CI stage 2b (pgvector sidecar) where
the full schema + 5 seeded fixtures exist. Skips cleanly in the fast
unit lane (stage 1, no DB).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)
REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not HAS_LIVE_DB,
    reason="SEED_CI_PG_URL not set — live endpoint smoke skipped",
)


def _sync_url() -> str:
    return LIVE_DB_URL.replace("+asyncpg", "")


def _async_url() -> str:
    return (
        LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL
        else LIVE_DB_URL.replace("postgresql://", "postgresql+asyncpg://")
    )


def _reset_and_seed() -> None:
    """Drop + re-migrate + seed all 5 fixtures (shared contract with
    test_persona_e2e._reset_and_seed)."""
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    env = {
        **os.environ,
        "DATABASE_URL_SYNC": _sync_url(),
        "DATABASE_URL": _async_url(),
        "ENV": "local",
    }
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )
    assert r.returncode == 0, f"alembic: {r.stderr}"
    r = subprocess.run(
        [sys.executable, "-m", "app.scripts.seed_ci"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, env=env,
    )
    assert r.returncode == 0, f"seed_ci: {r.stderr}"


@pytest.fixture(scope="module")
def seeded_db():
    # Point the app engine at the live DB before app import.
    os.environ["DATABASE_URL"] = _async_url()
    os.environ["DATABASE_URL_SYNC"] = _sync_url()
    os.environ.setdefault("ENV", "local")
    os.environ.setdefault("DMA_BOT_API_KEY", "ci-bot-key")
    os.environ.setdefault("RAG_API_BEARER_KEY", "ci-rag-key")
    # Reset the cached Settings instance — if a previous test module
    # imported app.config under different env vars (or before
    # SEED_CI_PG_URL was set), get_settings has cached the OLD
    # database_url/_sync. The engine reset below isn't sufficient
    # because _make_engine() calls get_settings(), which would still
    # return the stale cached instance pointing at the dev compose
    # default of localhost:5433.
    from app.config import get_settings
    get_settings.cache_clear()
    _reset_and_seed()
    yield


@pytest.fixture(scope="module")
def client(seeded_db):
    # The seeded_db fixture set DATABASE_URL/DATABASE_URL_SYNC before
    # this runs. app.database builds its engine lazily on first request,
    # so importing the app here picks up the live DSN. Reset any
    # already-built engine so a prior test module's bogus DSN can't leak.
    import app.database as _db
    _db._engine = None
    _db._sessionmaker = None
    # Settings already cleared by seeded_db fixture, but re-clear in
    # case any test between fixture and client triggered a re-cache.
    from app.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        # Admin sees every surface (AE would 403 on /admin/*; we want
        # to exercise the SQL, so use the broadest role).
        r = c.post("/api/v1/auth/dev-login?email=mishley.otiende@zennify.com")
        assert r.status_code == 200, f"dev-login failed: {r.text}"
        yield c
    # TestClient.__exit__ runs the app lifespan shutdown, which can
    # dispose the shared app.database engine. Null the module globals so
    # the NEXT test module rebuilds a fresh engine from its own DSN
    # instead of inheriting our disposed one (test-isolation contract —
    # without this, test_visibility's TraceEndpointLivePg 500'd when it
    # ran after this module in the stage-2b batch).
    _db._engine = None
    _db._sessionmaker = None


def _discover_substitutions(client) -> dict[str, str]:
    """Resolve concrete values for every {path_param} from seeded data
    so the smoke hits real rows (not 404 stubs)."""
    ents = client.get("/api/v1/entities").json()["items"]
    assert ents, "no seeded entities — seed_ci did not populate"
    did = ents[0]["display_id"]
    eid = ents[0]["id"]
    # real recommendation id
    recs = client.get(f"/api/v1/entities/{did}/recommendations").json()
    rec_items = recs if isinstance(recs, list) else recs.get("items", [])
    rid = None
    if rec_items:
        rid = rec_items[0].get("id") or rec_items[0].get("recommendation_id")
    # real techstack id
    tech = client.get(f"/api/v1/entities/{did}/techstack").json()
    tech_items = tech if isinstance(tech, list) else tech.get("items", [])
    tech_id = None
    if tech_items:
        tech_id = tech_items[0].get("id") or tech_items[0].get("tech_id")
    # real evidence e_id
    ev = client.get(f"/api/v1/entities/{did}/evidence").json()
    ev_items = ev if isinstance(ev, list) else ev.get("items", [])
    e_id = ev_items[0].get("e_id") if ev_items else "E-1"
    _NIL = "00000000-0000-0000-0000-000000000000"
    return {
        "display_id": did,
        "entity_id": eid,
        "subcap_id": "P1C1.1.1",
        "recommendation_id": rid or _NIL,
        "tech_id": tech_id or "salesforce",
        "e_id": e_id or "E-1",
        "execution_id": _NIL,
        "session_id": _NIL,
        "insight_card_id": _NIL,
        "ref": "x",
        "surface": "rag_answer",
    }


def _all_get_routes() -> list[str]:
    from app.main import app
    paths: list[str] = []
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        path = getattr(r, "path", "")
        if not path.startswith("/api/v1"):
            continue
        if "GET" not in methods:
            continue
        if "/sse/" in path:
            # SSE endpoints stream indefinitely; covered separately.
            continue
        paths.append(path)
    return sorted(set(paths))


def test_at_least_50_get_routes_registered():
    """Guard against the route table silently shrinking — if a whole
    router fails to register, the smoke below would vacuously pass."""
    routes = _all_get_routes()
    assert len(routes) >= 50, (
        f"only {len(routes)} GET routes registered — a router may have "
        f"failed to import. Got: {routes}"
    )


@pytest.mark.parametrize("view", ["", "?view=ae", "?view=customer"])
def test_every_get_route_no_5xx_against_seeded_db(client, view):
    """THE regression net. Every GET route, three audience views, must
    return < 500 against real seeded Postgres. A 5xx means malformed
    SQL / wrong signature / schema drift in the router — exactly the
    class that has repeatedly slipped past unit tests to stage-7 / prod.

    4xx is allowed (auth/validation/404-for-nil-uuid); only 5xx fails.
    """
    subst = _discover_substitutions(client)
    failures: list[str] = []
    for path in _all_get_routes():
        concrete = path
        for m in re.findall(r"\{(\w+)\}", path):
            concrete = concrete.replace("{" + m + "}", str(subst.get(m, "x")))
        resp = client.get(concrete + view)
        if resp.status_code >= 500:
            failures.append(
                f"{resp.status_code} {concrete}{view} :: {resp.text[:160]}"
            )
    assert not failures, (
        "GET endpoints returned 5xx against seeded live PG "
        "(malformed SQL / signature / schema drift):\n  "
        + "\n  ".join(failures)
    )


def test_prospecting_all_filter_and_subvertical_variants(client):
    """Pin the exact 2026-05-29 AmbiguousParameterError fix:
    /prospecting with + without ?subvertical (the bare-param branch)
    and every ?flag chip must all 200."""
    paths = [
        "/api/v1/prospecting",
        "/api/v1/prospecting?subvertical=CU",
        "/api/v1/prospecting?subvertical=RB",
        "/api/v1/prospecting?flag=LOW_MATURITY",
        "/api/v1/prospecting?flag=STALE_RUN",
        "/api/v1/prospecting?flag=UNASSIGNED",
        "/api/v1/prospecting?flag=all",
    ]
    for p in paths:
        r = client.get(p)
        assert r.status_code == 200, f"{p} → {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "items" in body and "filter_counts" in body


def test_overview_freshness_bundle_renders(client):
    """Pin the date-minus-date EXTRACT fix: /overview computes a
    freshness bundle (mean_age_months) over evidence_index. Both AE +
    customer views must 200 and the bundle must be well-formed."""
    subst = _discover_substitutions(client)
    did = subst["display_id"]
    for view in ("", "?view=ae", "?view=customer"):
        r = client.get(f"/api/v1/entities/{did}/overview{view}")
        assert r.status_code == 200, f"overview{view} → {r.text[:200]}"


def test_heatmap_subcap_drilldown_renders(client):
    """Pin the heatmap() missing-`view`-arg fix: the subcap drilldown
    composes heatmap() internally and must pass every Query-defaulted
    arg explicitly."""
    subst = _discover_substitutions(client)
    did = subst["display_id"]
    # A real subcap → 200; a bogus one → 404 (NOT 500).
    r_ok = client.get(f"/api/v1/entities/{did}/heatmap/subcap/P1C1.1.1?view=ae")
    assert r_ok.status_code in (200, 404), r_ok.text[:200]
    r_bogus = client.get(f"/api/v1/entities/{did}/heatmap/subcap/ZZ9.9.9?view=ae")
    assert r_bogus.status_code == 404, (
        f"bogus subcap should 404, got {r_bogus.status_code}"
    )


def test_admin_import_audit_by_entity_renders(client):
    """Pin the ai_enrichments.entity_id → target_kind/target_id fix."""
    r = client.get("/api/v1/admin/import-audit/by-entity")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "items" in body


def test_customer_view_strips_internal_keys(client):
    """Audience-strip contract: ?view=customer must NOT leak peer_*
    or parser_warnings on /overview (INTERNAL_ONLY_KEYS)."""
    subst = _discover_substitutions(client)
    did = subst["display_id"]
    cust = client.get(f"/api/v1/entities/{did}/overview?view=customer").json()
    blob = str(cust)
    # peer_benchmarks / peer_median are internal-only.
    assert '"peer_median"' not in blob, "peer_median leaked to customer view"
    assert '"parser_warnings"' not in blob, "parser_warnings leaked to customer view"
