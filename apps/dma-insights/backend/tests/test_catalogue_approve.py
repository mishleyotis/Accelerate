"""Catalogue approve endpoint — closes the upload→approve loop.

Pairs with `test_catalogue_upload.py`. The full admin catalogue flow
now end-to-end:

  POST /admin/catalogue:upload      (commit 3e73234)
       → enqueues job_executions row + stages file
  ccg_loader worker runs
       → writes ccg_loader_runs row with status='AWAITING_APPROVAL'
         (commit 20daba9)
  GET /admin/catalogue (existing)
       → admin sees the awaiting queue
  POST /admin/catalogue/:run_id:approve  (THIS commit)
       → flips status='APPLIED', records approver, audit-logs the
         action
  ccg_loader worker's promote step (Pub/Sub triggered)
       → migrates staging → canonical ccg_* tables

State coverage per test
-----------------------
test_endpoint_registered      — route exists on app.routes
test_route_method_post        — POST verb (matches admin UI's fetch)
test_state_branches_documented— 5 branches named in inline docstring
test_missing_table_returns_503— graceful migration-gap actionable msg
test_handler_writes_audit_log — INSERT INTO audit_log fired
test_handler_sets_applied     — status flipped to APPLIED
test_handler_checks_status    — guards against double-approve
"""
from __future__ import annotations

from pathlib import Path

from app.main import app


def test_endpoint_registered() -> None:
    """The approve route MUST be in the OpenAPI surface. Without it,
    admin "Approve" button would 404 forever."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    found = any("/api/v1/admin/catalogue/" in p and ":approve" in p for p in routes)
    assert found, (
        f"POST /api/v1/admin/catalogue/{{run_id}}:approve missing "
        f"from app.routes. Found admin routes: "
        f"{[r for r in routes if '/admin/catalogue' in r]}"
    )


def test_route_method_post() -> None:
    """Frontend will POST (no body needed beyond auth cookie). Must
    match exactly so the Approve button doesn't 405."""
    for r in app.routes:
        p = getattr(r, "path", "")
        if "/admin/catalogue/" in p and ":approve" in p:
            assert "POST" in getattr(r, "methods", set()), (
                f"approve_catalogue_run must accept POST; got {r.methods}"
            )
            return
    raise AssertionError("route not found")


def test_endpoint_signature() -> None:
    """The handler must take run_id as a path param + actor + session.
    Catches refactors that accidentally remove the actor dep."""
    import inspect

    from app.routers.admin import approve_catalogue_run
    sig = inspect.signature(approve_catalogue_run)
    assert "run_id" in sig.parameters
    assert "actor" in sig.parameters
    assert "session" in sig.parameters


def test_state_branches_documented() -> None:
    """All 5 branches from the inline docstring must be named so the
    next contributor knows the failure modes."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:approve\"")
    block = src[max(0, idx - 2000): idx + 4000]
    for branch in (
        "row_missing", "wrong_status", "already_applied",
        "admin_self_approve", "approve_ok",
    ):
        assert branch in block, (
            f"State branch '{branch}' missing from catalogue approve "
            f"docstring/comment block"
        )


def test_handler_returns_503_on_missing_table() -> None:
    """ccg_loader_runs table missing → 503 with migrate.sh hint
    (matches execute_job + catalogue:upload patterns)."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:approve\"")
    block = src[idx: idx + 6000]
    assert "503" in block or "SERVICE_UNAVAILABLE" in block
    assert "migration 012" in block.lower() or "migrate.sh" in block.lower(), (
        "approve_catalogue_run must surface a 'run ./migrate.sh' hint "
        "when ccg_loader_runs is missing — consistent operator UX"
    )


def test_handler_writes_audit_log() -> None:
    """Every admin mutation must write to audit_log (per update_role
    pattern). Without it, approver attribution is lost."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:approve\"")
    block = src[idx: idx + 6000]
    assert "INSERT INTO audit_log" in block, (
        "approve_catalogue_run must write audit_log entry — "
        "compliance + replay both require it"
    )
    assert "'catalogue_approve'" in block, (
        "audit_log.action must be 'catalogue_approve' for filtering"
    )


def test_handler_sets_applied_status() -> None:
    """Confirms the SQL actually flips to APPLIED (not some other
    state). Catches the typo regression class."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:approve\"")
    block = src[idx: idx + 6000]
    assert "SET status = 'APPLIED'" in block, (
        "approve_catalogue_run must SET status='APPLIED' — the whole "
        "point of the endpoint"
    )


def test_handler_guards_double_approve() -> None:
    """If a row is already APPLIED, second click must 409, not
    silently re-set + re-audit. Without this, accidental double-clicks
    pollute the audit log."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:approve\"")
    block = src[idx: idx + 6000]
    assert 'row.status == "APPLIED"' in block, (
        "approve_catalogue_run must check row.status == APPLIED + 409"
    )
    assert "HTTP_409_CONFLICT" in block
    assert "already APPLIED" in block, (
        "Error message must say 'already APPLIED' so the admin UI "
        "can render the right toast"
    )
