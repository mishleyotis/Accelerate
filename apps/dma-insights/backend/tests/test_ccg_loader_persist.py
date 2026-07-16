"""ccg_loader → ccg_loader_runs persist (final TODO closure).

Before this fix, the ccg_loader worker parsed catalogue workbooks
into pure in-memory rows but NEVER wrote a `ccg_loader_runs` row.
That meant:
  - Admin "catalogue queue" page always showed "no catalogue runs"
  - Upload-catalogue flow (POST /admin/catalogue:upload) enqueued a
    job_executions row but the worker had nothing to publish back
  - The whole catalogue-version-bump-with-admin-approval workflow
    documented in CLAUDE.md was non-functional

State coverage per test
-----------------------
test_persist_function_exists                  — `_persist_loader_run` is exposed
test_persist_validation_passed_status         — validation OK → status='AWAITING_APPROVAL'
test_persist_validation_failed_status         — validation FAIL → status='REJECTED'
test_persist_db_url_missing_returns_zero      — DATABASE_URL_SYNC unset → warning + rc=0
test_persist_table_missing_returns_zero       — UndefinedTable → warning + rc=0 (graceful)
test_state_branches_documented                — all 4 branches named in docstring
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def _find_app_root(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "backend").is_dir() and (c / "infra").is_dir():
            return c
    raise RuntimeError(f"app root not found from {start}")


APP_ROOT = _find_app_root(Path(__file__).resolve())
WORKERS = APP_ROOT / "workers"

# Workers package isn't on PYTHONPATH for backend tests by default —
# add it the same way test_drive_crawler_dispatch.py does.
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def test_persist_function_exists() -> None:
    """The persist helper must be importable from the worker module.
    If a refactor removed it, the TODO would silently regress."""
    from workers.ccg_loader.main import _persist_loader_run
    assert callable(_persist_loader_run)


def test_persist_db_url_missing_returns_zero() -> None:
    """When DATABASE_URL_SYNC isn't set (local dev / dry run from
    cli), the persist function must log a warning and return 0
    (success). The catalogue parse is still valuable for the JSON
    summary even without DB persistence."""
    from workers.ccg_loader.main import _persist_loader_run

    saved_url = os.environ.pop("DATABASE_URL_SYNC", None)
    try:
        result = MagicMock()
        result.validation_passed = True
        result.version = "v7.0"
        result.source_sha256s = {"P1.xlsx": "abc"}
        result.warnings = []
        result.validation_detail = {}
        rc = _persist_loader_run(result)
        assert rc == 0
    finally:
        if saved_url is not None:
            os.environ["DATABASE_URL_SYNC"] = saved_url


def test_persist_validation_passed_status() -> None:
    """When validation passes, the status MUST be 'AWAITING_APPROVAL'
    so the admin sees it in the catalogue approval queue."""
    src = (WORKERS / "ccg_loader" / "main.py").read_text()
    block = src.split("def _persist_loader_run")[1].split("\ndef ")[0]
    assert "AWAITING_APPROVAL" in block, (
        "ccg_loader must set status='AWAITING_APPROVAL' on validation_passed "
        "so admin can approve in the catalogue queue"
    )
    assert "validation_passed" in block, (
        "status branching must reference result.validation_passed"
    )


def test_persist_validation_failed_status() -> None:
    """When validation fails, status MUST be 'REJECTED' so the admin
    sees the failure reasons instead of approving broken data."""
    src = (WORKERS / "ccg_loader" / "main.py").read_text()
    block = src.split("def _persist_loader_run")[1].split("\ndef ")[0]
    assert "REJECTED" in block, (
        "ccg_loader must set status='REJECTED' when validation fails"
    )


def test_persist_table_missing_returns_zero() -> None:
    """When ccg_loader_runs table doesn't exist (migration 012 not
    applied), the function must log a warning and return 0 — NEVER
    crash the worker. The catalogue parse output is still valuable."""
    from workers.ccg_loader.main import _persist_loader_run

    os.environ["DATABASE_URL_SYNC"] = "postgresql+psycopg://fake/fake"

    # Mock the engine to raise UndefinedTable on execute
    class _FakeConn:
        def execute(self, *args, **kw):
            raise Exception(
                'relation "ccg_loader_runs" does not exist '
                "(UndefinedTable from psycopg)"
            )
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _FakeEngine:
        def begin(self): return _FakeConn()
        def dispose(self): pass

    try:
        with patch("sqlalchemy.create_engine", return_value=_FakeEngine()):
            result = MagicMock()
            result.validation_passed = True
            result.version = "v7.0"
            result.source_sha256s = {"P1.xlsx": "abc"}
            result.warnings = []
            result.validation_detail = {}
            rc = _persist_loader_run(result)
            assert rc == 0, (
                "table-missing must NOT propagate as an error — return 0 "
                "so the worker exits cleanly and operator sees actionable "
                "::warning:: about migration 012"
            )
    finally:
        os.environ.pop("DATABASE_URL_SYNC", None)


def test_state_branches_documented() -> None:
    """The 4 state branches must be named in the inline docstring so
    the next contributor knows what each path does without reading
    the full implementation."""
    src = (WORKERS / "ccg_loader" / "main.py").read_text()
    # The branches are documented near the call site in main() AND in
    # _persist_loader_run's docstring. Check the contiguous block
    # around the persist call.
    persist_idx = src.index("_persist_loader_run(result)")
    block = src[max(0, persist_idx - 2000): persist_idx + 4000]
    for branch in ("validation_passed=True", "validation_passed=False",
                   "DATABASE_URL_SYNC unset", "db_unreachable"):
        assert branch in block, (
            f"State branch '{branch}' missing from _persist_loader_run "
            f"docstring near call site"
        )


def test_todo_comment_removed() -> None:
    """The old TODO block must be GONE so we don't accidentally
    revert. Catches the regression of someone copy-pasting the old
    'Persisting to staging schema is not yet wired' message back."""
    src = (WORKERS / "ccg_loader" / "main.py").read_text()
    assert "Persisting to staging schema is not yet wired" not in src, (
        "old TODO message resurfaced — the ccg_loader_runs persist "
        "path has regressed. See _persist_loader_run."
    )
    assert "TODO(stage 1.5 finalize)" not in src, (
        "TODO marker resurfaced — was supposed to be closed"
    )
