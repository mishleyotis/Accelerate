"""Phase 3 ingest router security + idempotency regression tests.

Covers:
  - test_project_ingest_missing_bearer_returns_401
  - test_project_ingest_wrong_bearer_constant_time_rejected
  - test_project_ingest_bearer_uses_constant_time_compare (source-shape)
  - test_rag_bearer_uses_constant_time_compare (source-shape, parity)
  - test_package_ingest_duplicate_request_id_idempotent (regex contract)
  - test_post_commit_pubsub_failure_is_best_effort
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_project_ingest_bearer_uses_constant_time_compare():
    """The 2026-05-28 audit identified that ingest.py compared the
    bearer with `==`, which short-circuits at the first mismatched
    byte and leaks the key one character at a time via response-
    latency. /rag/answer already used `hmac.compare_digest`; ingest
    must match (fixed in this commit batch)."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "ingest.py"
    ).read_text(encoding="utf-8")
    # The comparison MUST be via hmac.compare_digest.
    assert "hmac.compare_digest" in src, (
        "/api/v1/ingest/assessment must compare the bearer with "
        "hmac.compare_digest. Plain == leaks the key via timing."
    )
    # The actual comparison expression `if provided == expected:` must
    # be gone (a comment mentioning the historical pattern is fine
    # because it documents WHY hmac.compare_digest replaced it).
    code_lines = [
        line for line in src.splitlines()
        if "provided == expected" in line and not line.lstrip().startswith("#")
    ]
    assert not code_lines, (
        f"ingest.py still has live `provided == expected` code: "
        f"{code_lines}. Replace with hmac.compare_digest."
    )


def test_rag_bearer_uses_constant_time_compare():
    """Parity check: /rag/answer was already correct. This test pins
    the contract so a refactor doesn't accidentally regress."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "rag.py"
    ).read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src


def test_project_ingest_missing_bearer_returns_401():
    """Route-level: no Authorization header -> 401 when a bot key is
    configured. The dependency lives in ingest.py::_verify_project_token
    and we exercise it via the actual FastAPI app."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.database import get_session
    from app.main import app

    if not get_settings().dma_bot_api_key:
        pytest.skip("DMA_BOT_API_KEY unset -- bearer guard disabled in local dev")

    class _NoOp:
        async def execute(self, *a, **kw):
            raise RuntimeError("DB call blocked")
        async def commit(self): pass

    async def _override_session():
        yield _NoOp()

    app.dependency_overrides[get_session] = _override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/api/v1/ingest/assessment", json={})
            assert r.status_code == 401, (
                f"missing bearer + no cookie must 401, got {r.status_code}: {r.text}"
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_project_ingest_wrong_bearer_returns_401():
    """Route-level: wrong bearer -> 401 with `invalid bearer token`
    detail. Fall-through to cookie auth is explicitly disabled in the
    dependency (the audit pinned this contract: don't mask bearer
    mismatches when a valid cookie is present)."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.database import get_session
    from app.main import app

    if not get_settings().dma_bot_api_key:
        pytest.skip("DMA_BOT_API_KEY unset -- bearer guard disabled in local dev")

    class _NoOp:
        async def execute(self, *a, **kw):
            raise RuntimeError("DB call blocked")
        async def commit(self): pass

    async def _override_session():
        yield _NoOp()

    app.dependency_overrides[get_session] = _override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/v1/ingest/assessment",
                json={},
                headers={"Authorization": "Bearer wrong-key-here"},
            )
            assert r.status_code == 401, (
                f"wrong bearer must 401, got {r.status_code}: {r.text}"
            )
            assert "invalid bearer" in r.text.lower()
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_package_ingest_duplicate_request_id_idempotent_via_run_update():
    """The ingest handler upserts run rows by request_id: if a run
    with that request_id already exists, it UPDATEs in place rather
    than INSERTing a duplicate. Source-shape pinning so a refactor
    that swaps to plain INSERT (causing duplicate runs on bot retry)
    surfaces immediately."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "ingest.py"
    ).read_text(encoding="utf-8")
    # Either an explicit UPDATE on the existing run path OR an
    # ON CONFLICT DO UPDATE counts. We pin the former -- the current
    # handler walks the SELECT...FOR UPDATE / branch.
    assert "FOR UPDATE" in src, (
        "ingest handler must SELECT...FOR UPDATE the existing run by "
        "request_id, then UPDATE. Without this row-level lock, two "
        "concurrent bot retries would both create runs."
    )
    # And the subsequent UPDATE must be present.
    assert re.search(r"UPDATE runs[\s\S]+SET[\s\S]+status='ACTIVE'", src), (
        "ingest handler must UPDATE the existing run row after the "
        "SELECT FOR UPDATE lock. Otherwise the lock is wasted."
    )


def test_post_commit_pubsub_failure_is_best_effort():
    """The post-commit Pub/Sub fan-out + synthesis cache invalidation
    must be wrapped in try/except so an outage in either doesn't fail
    the user's request. Audit contract: ack the caller, then
    asynchronously reconcile via the embedder watermark."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "ingest.py"
    ).read_text(encoding="utf-8")
    # Must have the best-effort try/except around publish_post_commit.
    m = re.search(
        r"try:\s*\n[\s\S]+?from app\.services\.parsers\.package_persist "
        r"import publish_post_commit[\s\S]+?except Exception",
        src,
    )
    assert m, (
        "ingest handler's post-commit Pub/Sub publish must be wrapped "
        "in try/except. Without it a Pub/Sub outage would 5xx the "
        "ingest -- bots can't retry idempotently if the DB write "
        "already succeeded."
    )


def test_ingest_assessment_pubsub_swallow_logs_for_debugging():
    """The post-commit swallow must log a warning so operators have a
    structured signal when Pub/Sub stays down for an extended window.
    Silent swallow is the worst possible failure mode."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "ingest.py"
    ).read_text(encoding="utf-8")
    assert "log.warning(" in src and "post_commit_fanout_failed" in src, (
        "post-commit Pub/Sub swallow must log a structured warning "
        "with a typed event name for downstream alerting."
    )
