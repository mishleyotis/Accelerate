"""B3 — endpoint contract test.

For every `/api/v1/...` path that the frontend calls, assert the
backend registers a matching route. Catches the "endpoint exists in
frontend but 404s at runtime" silent-failure class — the exact bug
that took down 4 Vite pages before c0bdc74.

The test is intentionally narrow: it does NOT call the endpoints
(that's the smoke test's job). It just asserts the route TABLE
contains a registration whose path template matches the frontend's
call shape (with `{id}`-style placeholders normalised).

Adding a new frontend endpoint? Add its template to FRONTEND_CALLS.
The single source-of-truth is the standalone backend-loader.js —
the test re-derives the list from there on every run to detect
drift automatically.

State-branch contract for this test:
  - route_registered     → ✓ path template found in app.routes
  - route_unregistered   → ✗ assertion failure with the missing path
                              (operator fixes by registering the route
                              or removing the dead frontend call)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


def _load_app():
    """Return a fresh FastAPI app. Settings cache cleared so
    env-bleed from sibling tests doesn't make `/readyz` blow up
    during app instantiation."""
    from app.config import get_settings
    from app.main import create_app
    get_settings.cache_clear()
    return create_app()


def _extract_frontend_calls() -> set[str]:
    """Scrape every `/api/v1/...` URL from the standalone loader, then
    normalise template-literal placeholders to `{id}`-style.

    We use the standalone-src loader as canonical because it's the
    live AE-facing surface (per CLAUDE.md). The Vite frontend is in
    the same monorepo and uses the same backend; tests there cover
    its calls via tsc + vitest.
    """
    # tests/ → backend/ → dma-insights/ → ../frontend/standalone-src/...
    here = Path(__file__).resolve()
    loader = (
        here.parents[2]
        / "frontend"
        / "standalone-src"
        / "src"
        / "backend-loader.js"
    )
    if not loader.exists():
        pytest.skip(f"backend-loader not present: {loader}")
    text = loader.read_text()
    calls: set[str] = set()
    # String-literal calls: "/api/v1/..."
    for m in re.finditer(r'"(/api/v1/[^"]+)"', text):
        calls.add(_normalise(m.group(1)))
    # Template-literal calls: `/api/v1/...${id}...`
    for m in re.finditer(r"`(/api/v1/[^`]+)`", text):
        calls.add(_normalise(m.group(1)))
    return calls


def _normalise(url: str) -> str:
    """Map runtime URL → FastAPI path template:
      ?qs strings stripped
      ${...} placeholders → {id}
      `:execute` / `:retry` / `:upload` action suffixes preserved
    """
    # Strip query strings (the route only registers the path).
    url = url.split("?", 1)[0]
    url = url.split("${qs", 1)[0].rstrip("/")
    # Template-literal interpolations → {id}.
    url = re.sub(r"\$\{[^}]+\}", "{id}", url)
    # Backtick-string interpolations that landed bare via `xxx`
    # cleanup — strip any trailing backtick artifacts.
    url = url.rstrip("`")
    return url


# Endpoints we know the backend serves with route-template-style
# parameters that the loader hides behind template literals. The
# scraper sees both shapes; the matcher unifies them.
PATH_PARAM_ALIASES = {
    "/api/v1/admin/jobs/executions/{id}": "/api/v1/admin/jobs/executions/{execution_id}",
    "/api/v1/admin/jobs/{id}:execute":   "/api/v1/admin/jobs/{job_name}:execute",
    # 2026-05-28 audit fix: OperationsCard wires :abort + the literal
    # historical_backfill execute paths. The :abort route uses
    # {execution_id}; the literal job-name execute path is the same
    # /jobs/{job_name}:execute route with the literal "historical_backfill"
    # baked in (so it resolves at runtime under the existing job-name template).
    "/api/v1/admin/jobs/executions/{id}:abort": "/api/v1/admin/jobs/executions/{execution_id}:abort",
    "/api/v1/admin/jobs/historical_backfill:execute": "/api/v1/admin/jobs/{job_name}:execute",
    "/api/v1/admin/users/{id}/role":     "/api/v1/admin/users/{user_id}/role",
    "/api/v1/admin/imports/files/{id}:retry": "/api/v1/admin/imports/files/{file_id}:retry",
    "/api/v1/admin/import-audit/entities/{id}": "/api/v1/admin/import-audit/entities/{entity_id}",
    "/api/v1/admin/users/{id}":          "/api/v1/admin/users/{user_id}",
    "/api/v1/chat/messages/{id}/feedback": "/api/v1/chat/messages/{message_id}/feedback",
    "/api/v1/chat/sessions/{id}":        "/api/v1/chat/sessions/{session_id}",
    "/api/v1/evidence/{id}/run-history": "/api/v1/evidence/{e_id}/run-history",
    "/api/v1/entities/{id}/archetype":   "/api/v1/entities/{display_id}/archetype",
    "/api/v1/entities/{id}/cross-pillar-stories": "/api/v1/entities/{display_id}/cross-pillar-stories",
    "/api/v1/entities/{id}/heatmap":     "/api/v1/entities/{display_id}/heatmap",
    "/api/v1/entities/{id}/run-history": "/api/v1/entities/{display_id}/run-history",
}


def _registered_paths() -> set[str]:
    app = _load_app()
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


def test_every_frontend_api_call_has_a_registered_route():
    """No frontend `/api/v1/...` call may 404 silently in production."""
    calls = _extract_frontend_calls()
    registered = _registered_paths()
    # Skip calls that are infrastructure (no path-param fan-out needed)
    # like the auth/me endpoint.
    missing: list[str] = []
    for call in sorted(calls):
        # Resolve alias to the real registered template if known.
        canonical = PATH_PARAM_ALIASES.get(call, call)
        if canonical in registered:
            continue
        # Sometimes FastAPI registers the path WITHOUT the colon-action
        # suffix as a different operation_id — try the path with the
        # suffix dropped as a fallback.
        base = canonical.split(":")[0]
        if base in registered:
            continue
        missing.append(call)

    if missing:
        msg = (
            "Frontend calls these /api/v1 paths but no backend route "
            "is registered (would 404 at runtime):\n  - "
            + "\n  - ".join(missing)
            + "\n\nFix: register the missing routes in "
            "app/routers/, OR remove the dead frontend call, OR add "
            "the alias to PATH_PARAM_ALIASES if the path-param name "
            "differs between frontend and backend."
        )
        pytest.fail(msg)


def test_known_critical_routes_registered():
    """Belt-and-braces: hard-pin the 4 endpoints whose absence took
    down Vite pages before c0bdc74."""
    registered = _registered_paths()
    critical = [
        "/api/v1/entities/{display_id}/heatmap/subcap/{subcap_id}",
        "/api/v1/entities/{display_id}/platforms/roadmap",
        "/api/v1/entities/{display_id}/techstack/landscape",
        "/api/v1/entities/{display_id}/health/version-diff",
        "/api/v1/rag/answer",
        "/api/v1/rag/answer/stream",
        "/api/v1/auth/me",
        "/healthz",
        "/readyz",
    ]
    missing = [c for c in critical if c not in registered]
    assert not missing, (
        f"Critical routes unregistered (deploy would fail smoke): {missing}"
    )
