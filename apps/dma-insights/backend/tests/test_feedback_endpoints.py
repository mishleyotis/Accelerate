"""Feedback-file refresh endpoints — glue logic (mocked session + service).

The Drive write itself (write_feedback_files) is covered by
test_drive_feedback.py; here we pin the endpoint glue: run resolution,
state passthrough, and the admin batch tally. Pure (no DB).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.drive_feedback import FeedbackWriteResult


def _actor():
    return SimpleNamespace(
        user_id="00000000-0000-0000-0000-000000000001",
        email="ae@zennify.com",
    )


async def test_refresh_entity_no_active_run():
    from app.routers.health import refresh_feedback_files

    session = AsyncMock()
    with patch("app.services.run_resolver.maybe_resolve_entity_run",
               new=AsyncMock(return_value=None)):
        res = await refresh_feedback_files(
            "acme-0001", session=session, actor=_actor())
    assert res.state == "no_active_run"
    assert res.run_request_id is None


async def test_refresh_entity_passes_through_upload_ok():
    from app.routers.health import refresh_feedback_files

    resolved = SimpleNamespace(
        id="run-uuid", entity_id="ent-uuid", request_id="REQ-ABCD1234",
        ccg_catalog_version="v7.0", status="ACTIVE",
    )
    exec_result = MagicMock()
    exec_result.mappings.return_value.first.return_value = {
        "drive_folder_id": "folder123"}
    session = AsyncMock()
    session.execute = AsyncMock(return_value=exec_result)
    session.commit = AsyncMock()

    wff = AsyncMock(return_value=FeedbackWriteResult(
        state="upload_ok", written=["thin_evidence_feedback.json"], failed=[]))
    with patch("app.services.run_resolver.maybe_resolve_entity_run",
               new=AsyncMock(return_value=resolved)), \
         patch("app.services.drive_feedback.write_feedback_files", new=wff), \
         patch("app.config.get_settings",
               return_value=SimpleNamespace(env="prod")):
        res = await refresh_feedback_files(
            "acme-0001", session=session, actor=_actor())

    assert res.state == "upload_ok"
    assert res.written == ["thin_evidence_feedback.json"]
    assert res.run_request_id == "REQ-ABCD1234"
    _, kwargs = wff.call_args
    assert kwargs["db_run_id"] == "run-uuid"
    assert kwargs["drive_folder_id"] == "folder123"
    assert kwargs["env"] == "prod"


async def test_refresh_all_tallies_by_state():
    from app.routers.admin import refresh_all_feedback_files

    ent1 = SimpleNamespace(eid="e1", display_id="alpha-0001", drive_folder_id="f1")
    ent2 = SimpleNamespace(eid="e2", display_id="beta-0001", drive_folder_id="f2")
    entities_result = MagicMock()
    entities_result.all.return_value = [ent1, ent2]
    run1_result = MagicMock()
    run1_result.first.return_value = SimpleNamespace(rid="r1")
    run2_result = MagicMock()
    run2_result.first.return_value = None  # no active run
    audit_result = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[entities_result, run1_result, run2_result, audit_result])
    session.commit = AsyncMock()

    wff = AsyncMock(return_value=FeedbackWriteResult(
        state="upload_ok", written=["x"], failed=[]))
    with patch("app.services.drive_feedback.write_feedback_files", new=wff), \
         patch("app.config.get_settings",
               return_value=SimpleNamespace(env="prod")):
        res = await refresh_all_feedback_files(actor=_actor(), session=session)

    assert res.total == 2
    assert res.by_state == {"upload_ok": 1, "no_active_run": 1}
    assert {r.entity_display_id for r in res.results} == {"alpha-0001", "beta-0001"}
