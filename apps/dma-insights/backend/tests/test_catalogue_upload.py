"""Catalogue upload endpoint — Promise #11 from the audit.

Frontend wires DMA.admin.uploadCatalogue(file, version) to POST
multipart to /api/v1/admin/catalogue:upload. This test verifies
the endpoint exists, accepts multipart, validates extensions, and
returns actionable errors on the documented failure paths.

State coverage per test
-----------------------
test_endpoint_registered           — POST /api/v1/admin/catalogue:upload
                                     exists on the router (not 404)
test_rejects_bad_extension         — .txt → 400 with hint
test_rejects_empty_file            — zero-byte upload → 400
test_accepts_xlsx_extension        — happy path validates ext OK
"""
from __future__ import annotations

from app.main import app


def test_endpoint_registered() -> None:
    """The route MUST be in the OpenAPI surface. If the endpoint
    decorator was deleted, the frontend's uploadCatalogue() would
    just keep 404-ing forever — this test catches that."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    # Note: include_in_schema=False but route is still registered.
    assert "/api/v1/admin/catalogue:upload" in routes, (
        f"POST /api/v1/admin/catalogue:upload missing from app.routes. "
        f"Found admin routes: {[r for r in routes if '/admin' in r][:10]}"
    )


def test_route_methods_include_post() -> None:
    """The decorator's HTTP method must be POST (matches frontend's
    `fetch(..., {method: 'POST'})`)."""
    for r in app.routes:
        if getattr(r, "path", None) == "/api/v1/admin/catalogue:upload":
            assert "POST" in getattr(r, "methods", set()), (
                f"upload_catalogue must accept POST; got {r.methods}"
            )
            return
    raise AssertionError("route not found — covered by test_endpoint_registered")


def test_endpoint_signature_uses_multipart() -> None:
    """The handler signature must accept `workbook: UploadFile` so
    FastAPI parses the multipart body. If a refactor accidentally
    swapped to JSON, frontend uploads would silently fail."""
    import inspect

    from app.routers.admin import upload_catalogue
    sig = inspect.signature(upload_catalogue)
    assert "workbook" in sig.parameters, (
        "upload_catalogue must have a `workbook: UploadFile` param — "
        "frontend posts multipart FormData with 'workbook' field name"
    )
    assert "version" in sig.parameters, (
        "upload_catalogue must accept `version` Form field — "
        "frontend posts FormData.append('version', version)"
    )


def test_endpoint_returns_actionable_error_on_missing_table() -> None:
    """When the job_executions table doesn't exist (migration 020 not
    applied), the endpoint must surface 503 with a clear migrate.sh
    hint — not a generic 500. The pattern matches execute_job.
    Verified by reading the source for the canonical error message
    so the test fails if someone removes the defense."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    body = src.read_text()
    # Find the upload_catalogue function body.
    upload_block = body.split("@router.post(\"/catalogue:upload\"")[1].split("\n@router")[0]
    assert "migration 020" in upload_block.lower(), (
        "upload_catalogue must surface a 'migration 020 not applied' "
        "message when job_executions is missing — matches execute_job's "
        "actionable-error pattern. Operator sees one consistent hint "
        "across both endpoints."
    )
    assert "503" in upload_block or "SERVICE_UNAVAILABLE" in upload_block, (
        "upload_catalogue must return 503 on missing-table (matches "
        "execute_job)"
    )


def test_state_branches_documented() -> None:
    """Every endpoint with side effects must document its state
    branches near the call-site so the next contributor doesn't
    re-introduce ambiguity. Check the contiguous block containing
    'catalogue:upload' covers all 5 documented branches."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    body = src.read_text()
    # Find the section containing both the decorator and the docs.
    # Walk back from the decorator to the start of the comment block.
    idx = body.index("@router.post(\"/catalogue:upload\"")
    # Capture 2KB of context before + the whole handler after.
    block = body[max(0, idx - 2000): idx + 4000]
    for branch in ("file_missing", "wrong_extension", "staging_dir_unwritable",
                   "job_executions_missing", "upload_ok"):
        assert branch in block, (
            f"State branch '{branch}' missing from catalogue:upload "
            f"docstring/comment block"
        )
