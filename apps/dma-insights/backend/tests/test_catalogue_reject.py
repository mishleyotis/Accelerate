"""Catalogue reject endpoint — pairs with approve.

When admin reviews an AWAITING_APPROVAL ccg_loader_runs row and
finds problems they don't trust, they REJECT instead of approve.
The rejected row stays in the table for audit but is excluded from
the active queue surface.

State coverage per test
-----------------------
test_endpoint_registered           — route exists
test_route_method_post             — POST verb
test_state_branches_documented     — all 5 branches named
test_requires_reason               — empty reason → 400
test_already_rejected_409          — idempotent
test_cant_reject_applied           — 409 — can't reject already-applied
test_writes_audit_log              — audit_log INSERT fires
test_appends_to_parse_warnings     — rejection reason captured in JSONB
"""
from __future__ import annotations

from pathlib import Path

from app.main import app


def test_endpoint_registered() -> None:
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    found = any("/api/v1/admin/catalogue/" in p and ":reject" in p for p in routes)
    assert found, (
        f"POST /api/v1/admin/catalogue/{{run_id}}:reject missing. "
        f"Found admin catalogue routes: "
        f"{[r for r in routes if '/admin/catalogue' in r]}"
    )


def test_route_method_post() -> None:
    for r in app.routes:
        p = getattr(r, "path", "")
        if "/admin/catalogue/" in p and ":reject" in p:
            assert "POST" in getattr(r, "methods", set())
            return
    raise AssertionError("route not found")


def test_state_branches_documented() -> None:
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[max(0, idx - 2000): idx + 6000]
    for branch in (
        "row_missing", "already_rejected", "already_applied",
        "wrong_status", "reject_ok",
    ):
        assert branch in block, (
            f"State branch '{branch}' missing from catalogue reject "
            f"docstring/comment block"
        )


def test_requires_reason() -> None:
    """Reject must require a free-text reason — admins must justify
    rejections for audit. Without the reason check, accidental
    clicks could reject runs with no rationale."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[idx: idx + 6000]
    assert "reason required" in block.lower() or "reason.*required" in block.lower(), (
        "reject must reject empty-reason bodies with 400 — admins must "
        "provide rationale for the audit trail"
    )
    assert "HTTP_400_BAD_REQUEST" in block


def test_already_rejected_409() -> None:
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[idx: idx + 6000]
    assert 'row.status == "REJECTED"' in block, (
        "must check status == REJECTED → 409 idempotent"
    )
    assert "already REJECTED" in block, (
        "Error message must say 'already REJECTED' for the UI toast"
    )


def test_cant_reject_applied() -> None:
    """Applied catalogues are LIVE in production. Rejecting them
    would silently undo a deploy with no audit. Block with 409."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[idx: idx + 6000]
    assert 'row.status == "APPLIED"' in block, (
        "must check status == APPLIED + 409"
    )
    assert "cannot reject" in block.lower()


def test_writes_audit_log() -> None:
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[idx: idx + 6000]
    assert "INSERT INTO audit_log" in block
    assert "'catalogue_reject'" in block, (
        "audit_log.action must be 'catalogue_reject' so filtering works"
    )


def test_appends_to_parse_warnings() -> None:
    """The rejection reason must persist where the queue view will
    show it. parse_warnings JSONB is the existing surface — append
    a structured {kind:'admin_rejection', actor_email, reason, …}
    so the admin queue UI renders it alongside validator warnings."""
    src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    ).read_text()
    idx = src.index("@router.post(\"/catalogue/{run_id}:reject\"")
    block = src[idx: idx + 6000]
    assert "parse_warnings" in block, (
        "rejection reason must be appended to parse_warnings JSONB so "
        "the admin queue view shows both validator warnings AND the "
        "admin's rejection rationale"
    )
    assert "admin_rejection" in block, (
        "rejection entry must use kind='admin_rejection' so the UI "
        "can pattern-match + render with the right styling"
    )
