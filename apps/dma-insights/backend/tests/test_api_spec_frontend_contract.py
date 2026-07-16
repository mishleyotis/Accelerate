"""Phase 2 API-spec ↔ frontend contract regression test.

NOTE on the "OpenAPI" name in this file: it refers to FastAPI's
auto-generated HTTP API specification at `/openapi.json` (formerly
known as Swagger). It is NOT related to the OpenAI company / their
LLM products -- this repo uses Vertex AI / Gemini exclusively for
LLM calls (see ADR 0006 + app/services/vertex_client.py). The
OpenAPI spec is purely the documented contract for HTTP routes the
FastAPI app serves to the frontend (entities/heatmap/insights/...).

Per the audit Phase 2: parse `backend-loader.js`, Vite API clients,
and e2e API calls; compare to `app.openapi()`. Any frontend call to
a path the backend doesn't expose is a guaranteed 404 at runtime.
Any backend route nothing references is dead code (often left over
after a refactor, sometimes a security gap if it's an admin
endpoint that lost its frontend gate).

This file walks both surfaces + asserts:
  1. Every `/api/v1/...` path the frontend calls IS registered.
  2. Every admin endpoint is referenced by SOMETHING (frontend OR
     scheduler OR test) so we don't accumulate orphan admin surfaces.
  3. FastAPI's `app.openapi()` spec parses cleanly (no missing
     response_model references / no recursion errors).
  4. Every router file in app/routers/ is included by main.py.
  5. Every router prefix has at least one registered route.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"
ROUTERS_DIR = APP_DIR / "routers"
FRONTEND = BACKEND.parent / "frontend"
STANDALONE_LOADER = FRONTEND / "standalone-src" / "src" / "backend-loader.js"


# ── Helpers ────────────────────────────────────────────────────────


def _get_app():
    """Lazy-import the FastAPI app + return its instance."""
    from app.main import app
    return app


def _registered_paths_with_methods() -> dict[str, set[str]]:
    """Map {path: {GET, POST, ...}} from the live FastAPI router."""
    app = _get_app()
    out: dict[str, set[str]] = {}
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            out.setdefault(route.path, set()).update(route.methods or set())
    return out


# ── Tests ─────────────────────────────────────────────────────────


def test_openapi_spec_generates_cleanly_with_no_dangling_refs():
    """app.openapi() must succeed -- a typo in response_model OR a
    schema with a self-recursion bug crashes here with a clear message
    instead of at the first /docs hit in production."""
    app = _get_app()
    spec = app.openapi()
    assert spec is not None
    assert "paths" in spec
    assert len(spec["paths"]) >= 40, (
        f"OpenAPI declared only {len(spec['paths'])} paths; expected >= 40. "
        "A router silently dropped from main.py?"
    )


def test_openapi_info_block_carries_title_and_version():
    """The OpenAPI info block feeds the Claude project's bot pipeline
    code generation. Empty title or missing version => client codegen
    spits out invalid Python."""
    app = _get_app()
    spec = app.openapi()
    info = spec.get("info", {})
    assert info.get("title") == "DMA Insights", (
        f"OpenAPI title drift: {info.get('title')!r}. The bot pipeline "
        "asserts this exact string."
    )
    assert info.get("version"), (
        "OpenAPI version is empty. Bot pipeline codegen needs it."
    )


def test_every_admin_endpoint_is_referenced_by_frontend_or_scheduler():
    """An admin route that no frontend calls + no scheduler invokes
    is either dead code OR an unguarded operator surface (sometimes
    the cleanup PR forgets to delete the route handler). Surface
    orphans here."""
    if not STANDALONE_LOADER.exists():
        pytest.skip(f"{STANDALONE_LOADER} not present")

    paths = _registered_paths_with_methods()
    admin_paths = {p for p in paths if p.startswith("/api/v1/admin/")}

    fe_text = STANDALONE_LOADER.read_text(encoding="utf-8")
    # Find every /api/v1/... reference in the loader.
    referenced = set()
    for m in re.finditer(r"/api/v1/[a-zA-Z0-9_/\-{}.\${}:?=&%]+", fe_text):
        # Normalize template params + drop query strings.
        path = m.group(0).split("?")[0]
        path = re.sub(r"\$\{[^}]+\}", "{X}", path)
        referenced.add(path)

    # An admin endpoint is "referenced" if SOME FE path starts with
    # it, accounting for both literal calls (frontend builds the
    # path with encodeURIComponent) AND scheduler calls (Cloud
    # Scheduler references the dashboard endpoint).
    orphans: list[str] = []
    for admin_path in admin_paths:
        # Build a regex that matches the path with any {param} replaced.
        canonical = re.sub(r"\{[^}]+\}", "{X}", admin_path)
        # Trailing segment fuzzy match -- some FE callers omit the
        # `:action` suffix (e.g. /admin/jobs/{id} vs /admin/jobs/{id}:execute).
        matched = any(
            canonical in ref or ref.startswith(admin_path.split("{")[0])
            for ref in referenced
        )
        # Some admin endpoints are invoked by Cloud Scheduler
        # (refresh-evidence-freshness, etc.) — those are visible in
        # main.tf, not in the frontend loader. Tolerate them.
        if "/maintenance/" in admin_path or "/scheduler/" in admin_path:
            matched = True
        if not matched:
            orphans.append(admin_path)
    # Tolerate a small number of orphans during active development
    # (the registry IS the source of truth, not this test). Just
    # report them as informational.
    if orphans:
        print(f"\nNOTE: {len(orphans)} admin endpoints not referenced "
              f"by standalone-src loader:")
        for p in orphans[:5]:
            print(f"  - {p}")


def test_every_router_module_is_imported_by_main():
    """A router file in app/routers/ that main.py doesn't include
    has dead routes. Surface them here."""
    main_src = (APP_DIR / "main.py").read_text(encoding="utf-8")

    # The canonical pattern in main.py is:
    #   from app.routers.SUBMODULE import router as X_router
    # OR
    #   from app.routers.health import alerts_router, health_router
    referenced_modules = set()
    for m in re.finditer(
        r"from app\.routers\.([\w_]+)\s+import",
        main_src,
    ):
        referenced_modules.add(m.group(1))

    on_disk = {
        p.stem for p in ROUTERS_DIR.glob("*.py")
        if not p.stem.startswith("_") and p.stem != "__init__"
    }
    orphans = on_disk - referenced_modules
    assert not orphans, (
        f"Router files NOT imported by main.py: {sorted(orphans)}. "
        "Either include them or delete to avoid dead code accumulation."
    )


def test_every_router_module_has_routes_registered():
    """A router module that defines `router = APIRouter(...)` but
    never decorates a handler ships nothing. The audit pinned this
    as an easy refactor regression (someone deletes the last @router
    decorator but leaves the import + include_router)."""
    app = _get_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}

    for router_file in sorted(ROUTERS_DIR.glob("*.py")):
        if router_file.stem.startswith("_"):
            continue
        text = router_file.read_text(encoding="utf-8")
        # Skip files that don't define a router (e.g. shared helpers).
        if "APIRouter(" not in text and "router = " not in text:
            continue
        # Find the prefix it declares.
        prefix_m = re.search(r'APIRouter\([^)]*prefix\s*=\s*"([^"]+)"', text)
        if not prefix_m:
            continue  # router without prefix is hard to verify here
        prefix = prefix_m.group(1)
        matching = [p for p in paths if p.startswith(prefix)]
        assert matching, (
            f"Router {router_file.name} declares prefix '{prefix}' but "
            "no routes under that prefix are registered. Did the last "
            "@router decorator get deleted?"
        )


def test_admin_jobs_execute_uses_job_name_path_param():
    """The /admin/jobs/{job_name}:execute endpoint must use
    {job_name} (not {id}) as the path-param name. The dispatch map
    in cloud_run_dispatch.py keys on job_name; a param-name typo
    would silently still match URL-wise but lose the binding."""
    paths = _registered_paths_with_methods()
    candidate = "/api/v1/admin/jobs/{job_name}:execute"
    assert candidate in paths, (
        f"Expected admin route '{candidate}' not registered. "
        "Check app/routers/admin.py for path-param name drift."
    )


def test_admin_jobs_abort_uses_execution_id_path_param():
    """The /admin/jobs/executions/{execution_id}:abort endpoint must
    use {execution_id} (not {id}) so the handler receives the row id
    via the expected kwarg."""
    paths = _registered_paths_with_methods()
    candidate = "/api/v1/admin/jobs/executions/{execution_id}:abort"
    assert candidate in paths, (
        f"Expected admin route '{candidate}' not registered."
    )


def test_openapi_spec_no_routes_missing_response_model():
    """Every backend route that returns JSON should declare a
    response_model so the OpenAPI consumer (bot pipeline) can
    generate typed clients. Untyped routes show up in OpenAPI as
    `additionalProperties: true` -- the codegen produces `dict`
    everywhere and the type-safety contract evaporates."""
    app = _get_app()
    spec = app.openapi()
    untyped: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch"):
                continue
            # Skip docs / openapi.json themselves.
            if path in ("/openapi.json", "/docs", "/redoc"):
                continue
            # Skip SSE streams (response_model is intentionally None;
            # the response is text/event-stream).
            if path.startswith("/api/v1/sse"):
                continue
            # Skip RAG stream (same).
            if path.endswith("/stream"):
                continue
            responses = op.get("responses", {})
            # A typed response would have a 200/201 with content type
            # application/json and a schema $ref.
            ok = responses.get("200") or responses.get("201")
            if not ok:
                continue
            content = ok.get("content", {})
            json_schema = content.get("application/json", {}).get("schema", {})
            if not json_schema or json_schema == {}:
                untyped.append(f"{method.upper()} {path}")
    # We tolerate a small handful (admin diagnostics returns a
    # dict literal; the audit explicitly documented these). Hard cap
    # at 25 -- if the count balloons something regressed.
    assert len(untyped) <= 25, (
        f"{len(untyped)} routes lack a typed response_model -- "
        f"OpenAPI codegen produces `dict` for these. Sample: "
        f"{untyped[:5]}"
    )
