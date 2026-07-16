"""Durable AE-notes persistence — D4 RecommendationModal "AE notes".

Covers the per-recommendation, team-shared note backed by migration
``057_recommendation_notes`` and the two endpoints on the recommendations
router:

  GET /api/v1/entities/{display_id}/recommendations/{rec_id}/note
  PUT /api/v1/entities/{display_id}/recommendations/{rec_id}/note

Follows the repo's write-surface test convention (test_write_surfaces.py):
a static contract that ALWAYS runs (so the file is never a no-op) plus a
live persistence path that exercises the real endpoints against the local
Postgres. The live path self-skips when the DB is unreachable.

Live path runs against the local DB configured via DATABASE_URL /
DATABASE_URL_SYNC / ENV=local (see the task runbook).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


# ── DB availability probe (evaluated at import for the skip guard) ─────────
def _sync_engine():
    from app.config import get_settings

    return create_engine(get_settings().database_url_sync, future=True)


def _db_up() -> bool:
    try:
        eng = _sync_engine()
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


_live = pytest.mark.skipif(
    not _db_up(),
    reason="local Postgres not reachable — AE-notes live tests skipped",
)


# ── static contract (always runs) ──────────────────────────────────────────
def test_migration_057_declares_recommendation_notes() -> None:
    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "057_recommendation_notes.py"
    ).read_text()
    assert 'revision = "057_recommendation_notes"' in mig
    # Chains off the current head (056_focus_enrich).
    assert 'down_revision = "056_focus_enrich"' in mig
    assert '"recommendation_notes"' in mig
    # One shared team note per (client, recommendation).
    assert "uq_recommendation_notes_entity_rec" in mig
    assert 'ForeignKey("entities.id", ondelete="CASCADE")' in mig


def test_schema_shape() -> None:
    """RecommendationNoteOut is the {note, author_email, updated_at} shape
    the frontend is being built to; the empty default is {note:""}."""
    from app.schemas.recommendations import (
        RecommendationNoteIn,
        RecommendationNoteOut,
    )

    empty = RecommendationNoteOut()
    assert empty.note == ""
    assert empty.author_email is None
    assert empty.updated_at is None
    assert RecommendationNoteIn().note == ""
    assert RecommendationNoteIn(note="hi").note == "hi"


# ── live persistence path ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ae_client():
    """TestClient carrying an AE session cookie + a freshly-seeded entity.

    Seeds/cleans up via a SYNC psycopg engine so the seeding never fights
    the TestClient's event loop. TestClient is constructed WITHOUT the
    context manager (so app lifespan/startup diagnostics don't run — same
    as tests/test_e2e_routes.py).

    ``get_session`` is overridden with a NullPool async engine: Starlette's
    TestClient runs each request in its own event loop, so the app's
    default pooled asyncpg connection (bound to the first request's loop)
    raises "Event loop is closed" on the second request. NullPool opens +
    closes a fresh connection per request on the current loop, which is the
    loop-safe way to drive endpoints over a live DB."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings
    from app.database import get_session
    from app.main import app
    from app.services.jwt_service import issue_token

    eng = _sync_engine()
    display_id = "rec-note-test-" + uuid.uuid4().hex[:8]
    entity_id = str(uuid.uuid4())
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO entities (id, name, display_id) "
                "VALUES (CAST(:i AS uuid), :n, :d)"
            ),
            {"i": entity_id, "n": "Rec Note Test Bank", "d": display_id},
        )

    async_engine = create_async_engine(
        get_settings().database_url, poolclass=NullPool,
    )
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async def _override_get_session():
        async with session_factory() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session

    client = TestClient(app)
    token = issue_token(
        user_id=str(uuid.uuid4()), email="dma@zennify.com",
        role="AE", name="DMA AE",
    )
    client.cookies.set("dma_session", token)
    try:
        yield client, display_id
    finally:
        app.dependency_overrides.pop(get_session, None)
        # ON DELETE CASCADE clears any notes, but be explicit.
        with eng.begin() as c:
            c.execute(
                text(
                    "DELETE FROM recommendation_notes "
                    "WHERE entity_id = CAST(:i AS uuid)"
                ),
                {"i": entity_id},
            )
            # A DB trigger (protect_active_entity_delete) blocks deleting an
            # ACTIVE entity — archive it first.
            c.execute(
                text(
                    "UPDATE entities SET status='ARCHIVED' "
                    "WHERE id = CAST(:i AS uuid)"
                ),
                {"i": entity_id},
            )
            c.execute(
                text("DELETE FROM entities WHERE id = CAST(:i AS uuid)"),
                {"i": entity_id},
            )
        eng.dispose()


def _url(display_id: str, rec_id: str) -> str:
    return f"/api/v1/entities/{display_id}/recommendations/{rec_id}/note"


@_live
def test_get_empty_note_returns_empty_object(ae_client) -> None:
    """No persisted note → 200 with the empty note object (NOT 404)."""
    client, display_id = ae_client
    resp = client.get(_url(display_id, "REC-01"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"note": "", "author_email": None, "updated_at": None}


@_live
def test_put_then_get_roundtrip_and_author_stamp(ae_client) -> None:
    """PUT persists; GET round-trips the exact text; author_email is
    stamped from the current user + updated_at is set."""
    client, display_id = ae_client
    note = "Push loan-origination first — CFO cited it as the FY26 priority."

    put = client.put(_url(display_id, "REC-02"), json={"note": note})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["note"] == note
    assert body["author_email"] == "dma@zennify.com"
    assert body["updated_at"] is not None

    got = client.get(_url(display_id, "REC-02"))
    assert got.status_code == 200, got.text
    got_body = got.json()
    assert got_body["note"] == note
    assert got_body["author_email"] == "dma@zennify.com"
    assert got_body["updated_at"] is not None


@_live
def test_put_upsert_overwrites_shared_note(ae_client) -> None:
    """Second PUT on the same (entity, rec_id) UPDATEs the shared row —
    one note per (client, recommendation), not a duplicate."""
    client, display_id = ae_client
    client.put(_url(display_id, "REC-05"), json={"note": "first"})
    second = client.put(_url(display_id, "REC-05"), json={"note": "second"})
    assert second.status_code == 200, second.text
    assert second.json()["note"] == "second"
    assert client.get(_url(display_id, "REC-05")).json()["note"] == "second"


@_live
def test_put_blank_clears_the_note(ae_client) -> None:
    """A blank/whitespace note DELETEs the row; GET then returns empty."""
    client, display_id = ae_client
    client.put(_url(display_id, "REC-03"), json={"note": "temporary"})
    assert client.get(_url(display_id, "REC-03")).json()["note"] == "temporary"

    cleared = client.put(_url(display_id, "REC-03"), json={"note": "   "})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"note": "", "author_email": None, "updated_at": None}
    assert client.get(_url(display_id, "REC-03")).json()["note"] == ""


@_live
def test_unknown_entity_404(ae_client) -> None:
    """Resolving an unknown display_id → 404 on both read and write."""
    client, _ = ae_client
    missing = "no-such-entity-" + uuid.uuid4().hex[:8]
    assert client.get(_url(missing, "REC-01")).status_code == 404
    assert client.put(_url(missing, "REC-01"), json={"note": "x"}).status_code == 404
