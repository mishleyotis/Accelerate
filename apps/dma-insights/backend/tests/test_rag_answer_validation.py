r"""DB-backed grounding-validator (V1-V3) wiring on the /rag/answer path.

CONTEXT
-------
`/api/v1/rag/answer` historically validated citations only by *bundle
membership* — `extract_citations` (E-\d+) + `extract_section_citations`
checked against the retrieved bundle. That catches a fabricated bare
`E-`/`SEC-` *citation*, but a model that fabricates a subcap / IC / REC /
agent ID in *prose* (an ID that is NOT a bare E-/SEC- citation) slipped
through. The full validator
`app.services.grounding_validator.validate_response` (V1 cited⊆retrieved,
V2 mentioned E-/P#C#.#.#/IC-/REC- IDs must exist in the DB for the entity,
V3 AF-agent IDs must exist) is now wired into the live answer path AFTER
the bundle-membership check.

These tests drive the REAL `rag_answer` coroutine against the REAL
Postgres DB (so V1-V3 actually execute their SQL), with only the Vertex
generation seam (`_generate_via_vertex`) and Redis stubbed. They assert:

  - fabricated_subcap_in_prose  → fail-closed + gemini_hallucination_alerts
  - fabricated_ic_in_prose      → fail-closed + alert (offending ID logged)
  - fabricated_rec_in_prose     → fail-closed + alert
  - fully_grounded_answer       → passes (validators_passed, no fallback)
  - validator_error             → fail-closed, never 500 (deterministic)

DB binding: like tests/test_e2e_docx_only_ingest.py, each test builds its
OWN async engine bound to the running event loop and disposes it on exit
(the shared app.database engine pool is bound to whichever loop first
touched it, which trips "Event loop is closed" under pytest-asyncio's
per-function loops). DATABASE_URL must point at the local PG; the test
skips cleanly when it's unset/unreachable.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.deps import CurrentUser
from app.schemas.chat import PageContext, RagAnswerRequest

# A subcap pattern the validator's RE_SUBCAP recognises but that we never
# seed into ccg_subcaps → fabricated when it appears in prose.
FABRICATED_SUBCAP = "P3C9.9.9"
# IC-/REC- the validator checks against the entity's rows; never seeded.
FABRICATED_IC = "IC-99999"
FABRICATED_REC = "REC-99999"


def _async_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return ""
    if "+asyncpg" in url:
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://")


@asynccontextmanager
async def _engine_ctx():
    """A dedicated async engine + sessionmaker bound to the running loop."""
    url = _async_url()
    if not url:
        pytest.skip("DATABASE_URL not set — DB-backed validator test skipped")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        # Probe connectivity up front so an unreachable DB skips rather
        # than errors (the container can be mid-restart).
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            pytest.skip("local Postgres unreachable — DB-backed test skipped")
        Session = async_sessionmaker(engine, expire_on_commit=False)
        yield Session
    finally:
        await engine.dispose()


class _SeededEntity:
    """A users + entities + runs + evidence_index island, torn down on exit.

    Everything is suffixed with a random token so concurrent / repeated
    runs never collide; DELETE on entities cascades to runs +
    evidence_index, DELETE on users cascades to chat_sessions +
    chat_messages.
    """

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sm = sessionmaker
        self.token = uuid.uuid4().hex[:10]
        self.user_id: str = ""
        self.entity_id: str = ""
        self.run_id: str = ""
        self.real_e_id: str = ""

    async def __aenter__(self) -> _SeededEntity:
        async with self._sm() as s:
            self.user_id = str(
                (
                    await s.execute(
                        text(
                            "INSERT INTO users (email, name, role) "
                            "VALUES (:e, :n, 'AE') RETURNING id"
                        ),
                        {"e": f"val-{self.token}@example.com",
                         "n": f"Validator Test {self.token}"},
                    )
                ).scalar_one()
            )
            self.entity_id = str(
                (
                    await s.execute(
                        text(
                            "INSERT INTO entities (name, display_id, subvertical) "
                            "VALUES (:n, :d, 'CU') RETURNING id"
                        ),
                        {"n": f"Val Bank {self.token}",
                         "d": f"val-bank-{self.token}"},
                    )
                ).scalar_one()
            )
            self.run_id = str(
                (
                    await s.execute(
                        text(
                            "INSERT INTO runs "
                            "  (entity_id, request_id, data_source, status, "
                            "   ccg_catalog_version) "
                            "VALUES (CAST(:eid AS uuid), :rid, 'PROJECT_API', "
                            "        'ACTIVE', 'v7.0') RETURNING id"
                        ),
                        {"eid": self.entity_id,
                         "rid": f"REQ-{self.token.upper()[:8]}"},
                    )
                ).scalar_one()
            )
            # Deterministic, unique-ish real E-ID for this entity.
            self.real_e_id = f"E-{int(self.token, 16) % 90000 + 1000}"
            await s.execute(
                text(
                    "INSERT INTO evidence_index "
                    "  (run_id, entity_id, e_id, source_name, excerpt, "
                    "   claim_type, tier, linked_subcap_ids) "
                    "VALUES (CAST(:rid AS uuid), CAST(:eid AS uuid), :e, "
                    "        :src, :exc, 'observed', 1, :subs)"
                ),
                {
                    "rid": self.run_id, "eid": self.entity_id,
                    "e": self.real_e_id, "src": "ACME Annual Report 2025",
                    "exc": "The bank migrated core banking to a cloud platform.",
                    "subs": ["P1C1.1.1"],
                },
            )
            await s.commit()
        return self

    async def __aexit__(self, *exc) -> None:
        async with self._sm() as s:
            await s.execute(
                text("DELETE FROM gemini_hallucination_alerts "
                     "WHERE entity_id = CAST(:eid AS uuid)"),
                {"eid": self.entity_id},
            )
            # entities has a trg_protect_active_entity_delete guard — an
            # ACTIVE entity cannot be deleted. Archive first, then delete
            # (which cascades to runs → evidence_index).
            await s.execute(
                text("UPDATE entities SET status='ARCHIVED' "
                     "WHERE id = CAST(:eid AS uuid)"),
                {"eid": self.entity_id},
            )
            await s.execute(
                text("DELETE FROM entities WHERE id = CAST(:eid AS uuid)"),
                {"eid": self.entity_id},
            )
            await s.execute(
                text("DELETE FROM users WHERE id = CAST(:uid AS uuid)"),
                {"uid": self.user_id},
            )
            await s.commit()

    async def alert_count(self) -> int:
        async with self._sm() as s:
            return int(
                (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM gemini_hallucination_alerts "
                            "WHERE entity_id = CAST(:eid AS uuid)"
                        ),
                        {"eid": self.entity_id},
                    )
                ).scalar_one()
            )

    async def latest_alert_flags(self) -> dict:
        async with self._sm() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT flags FROM gemini_hallucination_alerts "
                        "WHERE entity_id = CAST(:eid AS uuid) "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"eid": self.entity_id},
                )
            ).first()
        if row is None:
            return {}
        flags = row.flags
        if isinstance(flags, str):
            import json
            return json.loads(flags)
        return dict(flags or {})


async def _run_answer(seed: _SeededEntity, sessionmaker, *, model_text: str):
    """Drive the real rag_answer with the Vertex seam + Redis stubbed.

    Uses a fresh real session from the per-test sessionmaker (the same
    object the validator queries through), exactly as the FastAPI
    dependency would supply one.
    """
    from unittest.mock import patch

    from app.routers import rag as rag_mod

    async def _fake_vertex(*, prompt, model_alias, max_paragraphs):
        # (text, tokens_in, tokens_out) — same contract as the live call.
        return model_text, 10, 20

    async def _no_redis():
        return None

    user = CurrentUser(
        user_id=seed.user_id, email=f"val-{seed.token}@example.com",
        role="AE", name="Validator Test",
    )
    body = RagAnswerRequest(
        question="What is the bank's core banking posture?",
        page_context=PageContext(
            route="/clients/x/heatmap", entity_id=seed.entity_id,
            user_role="AE",
        ),
        response_style="concise",
        require_citations=True,
        surface="rag_answer",
    )
    with patch.object(rag_mod, "get_redis", _no_redis), \
            patch.object(rag_mod, "_generate_via_vertex", _fake_vertex):
        async with sessionmaker() as session:
            resp = await rag_mod.rag_answer(body, user, session)
    return resp


# --------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------


async def test_fabricated_subcap_in_prose_fails_closed():
    """A subcap ID that exists in NO ccg_subcaps row, mentioned in prose
    (while the answer still cites a REAL E-ID so it passes V0 + the
    zero-citation gate), must fail closed via the DB-backed V2 check.
    This is precisely the gap bundle-membership alone did NOT catch."""
    async with _engine_ctx() as sm, _SeededEntity(sm) as seed:
        body_text = (
            f"The bank shows strong cloud adoption [{seed.real_e_id}]. "
            f"This maps directly to subcap {FABRICATED_SUBCAP}, which is "
            f"a clear strength."
        )
        resp = await _run_answer(seed, sm, model_text=body_text)

        assert resp.fallback_used is True
        assert resp.validators_passed is False
        # The real E-ID citation is dropped on fallback.
        assert resp.cited_evidence_ids == []
        # Alert persisted with the offending subcap ID under V2's bucket.
        assert await seed.alert_count() == 1
        flags = await seed.latest_alert_flags()
        assert FABRICATED_SUBCAP in flags.get("fabricated_subcap_ids", [])


async def test_fabricated_ic_in_prose_fails_closed():
    """A fabricated IC-#### (not owned by the entity) in prose fails closed."""
    async with _engine_ctx() as sm, _SeededEntity(sm) as seed:
        body_text = (
            f"Per the evidence [{seed.real_e_id}], the gap is captured in "
            f"insight card {FABRICATED_IC}."
        )
        resp = await _run_answer(seed, sm, model_text=body_text)

        assert resp.fallback_used is True
        assert resp.validators_passed is False
        flags = await seed.latest_alert_flags()
        assert FABRICATED_IC in flags.get("fabricated_ic_ids", [])


async def test_fabricated_rec_in_prose_fails_closed():
    """A fabricated REC-#### (not owned by the entity) in prose fails closed."""
    async with _engine_ctx() as sm, _SeededEntity(sm) as seed:
        body_text = (
            f"We recommend {FABRICATED_REC} as the next step, grounded in "
            f"[{seed.real_e_id}]."
        )
        resp = await _run_answer(seed, sm, model_text=body_text)

        assert resp.fallback_used is True
        assert resp.validators_passed is False
        flags = await seed.latest_alert_flags()
        assert FABRICATED_REC in flags.get("fabricated_rec_ids", [])


async def test_fully_grounded_answer_passes():
    """An answer that cites ONLY the real E-ID and mentions no fabricated
    subcap/IC/REC/agent ID must pass: validators_passed=True, no fallback,
    no alert row."""
    async with _engine_ctx() as sm, _SeededEntity(sm) as seed:
        body_text = (
            f"The bank has migrated its core banking platform to the "
            f"cloud [{seed.real_e_id}], indicating solid infrastructure "
            f"maturity."
        )
        resp = await _run_answer(seed, sm, model_text=body_text)

        assert resp.fallback_used is False, (
            f"fully-grounded answer should pass; got fallback. "
            f"answer={resp.answer_markdown!r}"
        )
        assert resp.validators_passed is True
        assert seed.real_e_id in resp.cited_evidence_ids
        assert await seed.alert_count() == 0


async def test_validator_error_fails_closed_not_500():
    """If the validator raises (DB hiccup, etc.), the request must fall
    back deterministically — never 500. We force validate_response to
    raise and assert the fail-closed path is taken with a validator_error
    alert flag."""
    from unittest.mock import patch

    async def _boom(**kwargs):
        raise RuntimeError("validator backend unavailable")

    # rag_answer does a local `from app.services.grounding_validator import
    # validate_response`, which resolves to the source-module attribute at
    # call time — patch it there. (patch() is a *sync* CM, so it can't ride
    # in the async-with; nest it as a plain `with`.)
    async with _engine_ctx() as sm, _SeededEntity(sm) as seed:
        with patch("app.services.grounding_validator.validate_response", _boom):
            body_text = f"Clean-looking answer citing [{seed.real_e_id}] only."
            resp = await _run_answer(seed, sm, model_text=body_text)

        assert resp.fallback_used is True
        assert resp.validators_passed is False
        flags = await seed.latest_alert_flags()
        assert flags.get("validator_error") is True
