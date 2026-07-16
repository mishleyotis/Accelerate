"""Lean-worker import contract (2026-06-10 live incident).

The workers image (infra/docker/worker.Dockerfile) deliberately does
NOT install fastapi — workers have no HTTP surface. But the ingest path
used to runtime-import from `app.routers.*` (which imports fastapi):

    historical_backfill._extract_zips  → app.routers.ingest_package
    package_persist (platform persist) → app.routers.platforms

On the live Cloud Run drive-crawler job this crashed EVERY folder with
`ModuleNotFoundError: No module named 'fastapi'` and the deploy-time
backfill stalled at 45/124 with zero packages ingested.

This test walks the import graph of every worker-reachable module
(workers/** entrypoints + the backfill script + the parser/persist
services) via static AST and FAILS if any module in that closure
imports `fastapi` or `app.routers.*` at module OR function scope.
Function-scope (lazy) imports are just as fatal — they fire at ingest
time on the worker.

Shared ingest logic belongs in `app.services.*` (framework-free); the
routers import from services, never the other way around.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND.parent  # apps/dma-insights

# Worker-reachable entrypoints. The closure below follows their app.*
# imports transitively, so listing the entrypoints is enough.
ENTRYPOINTS = [
    *sorted((APP_ROOT / "workers").glob("*/main.py")),
    APP_ROOT / "workers" / "_runner.py",
    BACKEND / "app" / "scripts" / "historical_backfill.py",
]

BANNED_PREFIXES = ("fastapi", "app.routers")


def _module_imports(path: Path) -> list[str]:
    """Every imported module name in the file — module scope AND inside
    function bodies (lazy imports fire at runtime on the worker)."""
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
        elif isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
    return out


def _resolve(module: str) -> Path | None:
    """app.* / workers.* dotted module → file path (else None)."""
    rel = module.replace(".", "/")
    if module.startswith("app."):
        roots = [BACKEND]
    elif module.startswith("workers"):
        roots = [APP_ROOT]
    else:
        return None
    for root in roots:
        for cand in (root / f"{rel}.py", root / rel / "__init__.py"):
            if cand.exists():
                return cand
    return None


def test_worker_reachable_modules_never_import_fastapi_or_routers() -> None:
    offenders: list[str] = []
    seen: set[Path] = set()
    stack: list[tuple[Path, tuple[str, ...]]] = [
        (p, (str(p.relative_to(APP_ROOT)),)) for p in ENTRYPOINTS if p.exists()
    ]
    assert stack, "no worker entrypoints found — layout changed?"
    while stack:
        path, chain = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for mod in _module_imports(path):
            if mod.startswith(BANNED_PREFIXES):
                offenders.append(" -> ".join(chain) + f" imports {mod!r}")
                continue
            child = _resolve(mod)
            if child is not None:
                stack.append((child, (*chain, mod)))
    assert not offenders, (
        "worker-reachable module(s) import fastapi/app.routers — the "
        "workers image has NO fastapi, so these crash at ingest time on "
        "the live drive-crawler job (2026-06-10 incident). Move shared "
        "logic into app.services.* instead:\n  " + "\n  ".join(offenders)
    )


def test_zip_guard_and_platform_display_live_in_services() -> None:
    """The two helpers that caused the incident must stay importable
    WITHOUT fastapi: their home modules import neither fastapi nor any
    app.routers module."""
    for rel in ("app/services/zip_guard.py", "app/services/platform_display.py"):
        path = BACKEND / rel
        assert path.exists(), f"{rel} missing — incident fix regressed"
        for mod in _module_imports(path):
            assert not mod.startswith(BANNED_PREFIXES), (
                f"{rel} imports {mod!r} — must stay framework-free"
            )
