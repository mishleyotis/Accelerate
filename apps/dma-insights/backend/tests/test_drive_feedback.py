"""F4 — Drive feedback loop (PRD §17).

Tests cover:
  - 5 payload-shape schemas (valid + populated + state branches)
  - state-branch matrix for write_feedback_files:
      drive_folder_unknown / dev_skip / dry_run /
      upload_ok / upload_failed / drive_perms_missing
  - the orchestrator (write_drive_feedback) — best-effort,
    swallows errors, writes audit row

Pure-logic tests where possible; SQL paths are mocked. The compute_*
helpers are independently tested against synthetic row dicts so we
don't need a live DB.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.drive_feedback import (
    EvidenceFreshnessAlerts,
    FeedbackWriteResult,
    FreshnessAlertRow,
    NarrativeOverrides,
    TechInferenceHandoff,
    ThinEvidenceFeedback,
    ThinEvidenceRow,
    WaiverDecisions,
)
from app.services.drive_feedback import (
    _suggest_action,
    write_feedback_files,
)


def _empty_session():
    """Plain sentinel — the compute_* helpers are patched so this
    session is never actually queried. Tests that DO go through SQL
    use the dedicated `_session_with_rows` builder below."""
    return MagicMock()


def _make_empty_envelopes(*, run_id: str = "r1", entity_id: str = "e1"):
    """Build the 5 empty envelopes that compute_* would return when
    a run has zero thin-evidence / freshness-alert / tech-inference
    / override / waiver rows."""
    now = datetime.now(tz=UTC)
    return {
        "thin": ThinEvidenceFeedback(
            run_id=run_id, entity_id=entity_id,
            completed_at=now, state="empty",
        ),
        "fresh": EvidenceFreshnessAlerts(
            run_id=run_id, entity_id=entity_id,
            completed_at=now, state="empty",
        ),
        "tech": TechInferenceHandoff(
            run_id=run_id, entity_id=entity_id,
            completed_at=now, state="empty",
        ),
        "overrides": NarrativeOverrides(
            entity_id=entity_id, completed_at=now, state="empty",
        ),
        "waivers": WaiverDecisions(
            entity_id=entity_id, completed_at=now, state="empty",
        ),
    }


def _patch_computes(envs: dict):
    """Stub out the 5 SQL helpers so write_feedback_files goes
    straight to upload without needing a real DB."""
    return [
        patch("app.services.drive_feedback.compute_thin_evidence",
              new=AsyncMock(return_value=envs["thin"])),
        patch("app.services.drive_feedback.compute_freshness_alerts",
              new=AsyncMock(return_value=envs["fresh"])),
        patch("app.services.drive_feedback.compute_tech_handoff",
              new=AsyncMock(return_value=envs["tech"])),
        patch("app.services.drive_feedback.compute_narrative_overrides",
              new=AsyncMock(return_value=envs["overrides"])),
        patch("app.services.drive_feedback.compute_waiver_decisions",
              new=AsyncMock(return_value=envs["waivers"])),
    ]


# ── Schema sanity ──────────────────────────────────────────────────────


def test_schemas_round_trip_via_model_dump_by_alias():
    """All 5 schemas must accept their populated form AND serialise
    with `$schema` (alias)."""
    now = datetime.now(tz=UTC)
    eid = "00000000-0000-0000-0000-000000000001"
    rid = "00000000-0000-0000-0000-000000000002"

    thin = ThinEvidenceFeedback(
        run_id=rid, entity_id=eid, completed_at=now,
        state="generated",
        items=[ThinEvidenceRow(
            subcap_id="P1C1.1.1", category_id="P1C1", pillar_id="P1",
            score=3.0, evidence_count=1,
            suggested_action="research_deeper",
            rationale="test",
        )],
    )
    payload = thin.model_dump(by_alias=True, mode="json")
    assert payload["$schema"] == "thin_evidence_feedback_v1"
    assert payload["state"] == "generated"
    assert payload["items"][0]["suggested_action"] == "research_deeper"

    fresh = EvidenceFreshnessAlerts(
        run_id=rid, entity_id=eid, completed_at=now,
        state="generated",
        items=[FreshnessAlertRow(
            evidence_id="E001", source_name="Annual Report 2020",
            tier=1, freshness_band="stale",
        )],
    )
    payload = fresh.model_dump(by_alias=True, mode="json")
    assert payload["$schema"] == "evidence_freshness_alerts_v1"
    assert payload["items"][0]["freshness_band"] == "stale"

    tech = TechInferenceHandoff(
        run_id=rid, entity_id=eid, completed_at=now, state="empty",
    )
    assert tech.model_dump(by_alias=True, mode="json")["state"] == "empty"

    overrides = NarrativeOverrides(
        entity_id=eid, completed_at=now, state="empty",
    )
    assert overrides.model_dump(by_alias=True, mode="json")["state"] == "empty"

    waivers = WaiverDecisions(
        entity_id=eid, completed_at=now, state="empty",
    )
    assert waivers.model_dump(by_alias=True, mode="json")["state"] == "empty"


def test_suggest_action_matrix():
    """Bot-guidance mapping must be deterministic + cover edge cases."""
    # No evidence at all → ask client for an artifact.
    assert _suggest_action(3.0, 0, "HIGH") == "request_client_artifact"
    # High score with thin evidence → most suspicious; deeper research.
    assert _suggest_action(4.5, 1, "HIGH") == "research_deeper"
    # Low confidence → downgrade rather than dig.
    assert _suggest_action(2.5, 1, "LOW") == "downgrade_confidence"
    assert _suggest_action(2.5, 1, "MEDIUM") == "downgrade_confidence"
    # Default catch-all.
    assert _suggest_action(2.5, 1, "HIGH") == "mark_as_proxy"
    assert _suggest_action(None, 1, None) == "mark_as_proxy"


# ── State-branch matrix for write_feedback_files ───────────────────────


@pytest.mark.asyncio
async def test_drive_folder_unknown_short_circuits():
    """No source folder → drive_folder_unknown; no DB calls, no IO."""
    session = MagicMock()
    res = await write_feedback_files(
        session=session,
        db_run_id="r1", entity_id="e1",
        drive_folder_id=None, env="prod",
    )
    assert isinstance(res, FeedbackWriteResult)
    assert res.state == "drive_folder_unknown"
    assert res.written == []
    assert res.failed == []


@pytest.mark.asyncio
async def test_dev_env_short_circuits_to_dev_skip():
    """env=local must not reach Drive."""
    session = MagicMock()
    for env in ("local", "test", "dev"):
        res = await write_feedback_files(
            session=session,
            db_run_id="r1", entity_id="e1",
            drive_folder_id="folder123", env=env,
        )
        assert res.state == "dev_skip", f"env={env} should skip"


@pytest.mark.asyncio
async def test_dry_run_builds_envelopes_but_skips_upload():
    """dry_run=True: build but don't upload."""
    envs = _make_empty_envelopes()
    patches = _patch_computes(envs)
    for p in patches:
        p.start()
    try:
        res = await write_feedback_files(
            session=_empty_session(),
            db_run_id="r1", entity_id="e1",
            drive_folder_id="folder123", env="prod", dry_run=True,
        )
    finally:
        for p in patches:
            p.stop()
    assert res.state == "dry_run"
    assert set(res.written) == {
        "thin_evidence_feedback.json",
        "evidence_freshness_alerts.json",
        "tech_inference_handoff.json",
        "narrative_overrides.json",
        "waiver_decisions.json",
    }


@pytest.mark.asyncio
async def test_upload_ok_when_all_files_accepted():
    """Mock uploader accepts every call → state=upload_ok."""
    envs = _make_empty_envelopes()
    patches = _patch_computes(envs)
    for p in patches:
        p.start()
    try:
        upserter = AsyncMock(return_value="drive-file-id")
        res = await write_feedback_files(
            session=_empty_session(),
            db_run_id="r1", entity_id="e1",
            drive_folder_id="folder123", env="prod",
            drive_upserter=upserter,
        )
    finally:
        for p in patches:
            p.stop()
    assert res.state == "upload_ok"
    assert len(res.written) == 5
    assert upserter.call_count == 5


@pytest.mark.asyncio
async def test_upload_failed_when_partial_failure():
    """Some files fail → state=upload_failed; partial `written` preserved."""
    envs = _make_empty_envelopes()
    patches = _patch_computes(envs)
    for p in patches:
        p.start()
    try:
        calls = {"n": 0}

        async def flaky(folder_id, name, body):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("simulated 500 from Drive")
            return "drive-file-id"

        res = await write_feedback_files(
            session=_empty_session(),
            db_run_id="r1", entity_id="e1",
            drive_folder_id="folder123", env="prod",
            drive_upserter=flaky,
        )
    finally:
        for p in patches:
            p.stop()
    assert res.state == "upload_failed"
    assert len(res.written) == 4
    assert len(res.failed) == 1
    assert res.error_kind == "RuntimeError"


@pytest.mark.asyncio
async def test_drive_perms_missing_when_403_blocks_everything():
    """Every upload raises with 'permission' in message → state=drive_perms_missing."""
    envs = _make_empty_envelopes()
    patches = _patch_computes(envs)
    for p in patches:
        p.start()
    try:
        async def perms(folder_id, name, body):
            raise RuntimeError("HttpError 403 — permission denied for folder")

        res = await write_feedback_files(
            session=_empty_session(),
            db_run_id="r1", entity_id="e1",
            drive_folder_id="folder123", env="prod",
            drive_upserter=perms,
        )
    finally:
        for p in patches:
            p.stop()
    assert res.state == "drive_perms_missing"
    assert res.written == []
    assert len(res.failed) == 5
    assert "permission denied" in (res.error_message or "")


@pytest.mark.asyncio
async def test_compute_failure_surfaces_as_upload_failed():
    """If the SQL helpers raise (DB blip) before any IO, we still
    return a typed state — never propagate the exception."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("connection reset")
    res = await write_feedback_files(
        session=session,
        db_run_id="r1", entity_id="e1",
        drive_folder_id="folder123", env="prod",
    )
    assert res.state == "upload_failed"
    assert res.error_kind == "RuntimeError"


# ── Orchestrator best-effort contract ──────────────────────────────────


@pytest.mark.asyncio
async def test_write_drive_feedback_swallows_outer_errors():
    """The orchestrator that publish_post_commit calls must NEVER
    raise — ingest is already committed, we cannot escalate."""
    from app.services.parsers.package_persist import write_drive_feedback

    session = AsyncMock()
    # Force the compute path to raise mid-flight.
    session.execute.side_effect = RuntimeError("boom")
    # Set env to prod via the settings mock so we exercise the IO path.
    with patch(
        "app.config.get_settings",
        return_value=MagicMock(env="prod"),
    ):
        result = await write_drive_feedback(
            session=session, db_run_id="r1",
            entity_id="e1", drive_folder_id="folder123",
        )
    assert "state" in result


@pytest.mark.asyncio
async def test_write_drive_feedback_writes_audit_row_on_success():
    """Successful upload → audit row INSERTed with state in after_json."""
    from app.services.parsers.package_persist import write_drive_feedback

    session = MagicMock()
    session.execute = AsyncMock()
    envs = _make_empty_envelopes()
    patches = [
        *_patch_computes(envs),
        patch("app.config.get_settings",
              return_value=MagicMock(env="prod")),
    ]
    for p in patches:
        p.start()
    try:
        upserter = AsyncMock(return_value="drive-file-id")
        result = await write_drive_feedback(
            session=session, db_run_id="r1",
            entity_id="e1", drive_folder_id="folder123",
            drive_upserter=upserter,
        )
    finally:
        for p in patches:
            p.stop()
    assert result["state"] == "upload_ok"
    # The audit_log INSERT was issued. SQLAlchemy TextClause hides the
    # actual SQL behind a __repr__, so we check via the bound params
    # dict (which carries the state payload as `after` JSON).
    audit_calls = []
    for c in session.execute.call_args_list:
        args, kwargs = c
        # call(stmt, params_dict) — args[0] is the TextClause, args[1]
        # is the params dict.
        params = args[1] if len(args) >= 2 else kwargs
        if isinstance(params, dict) and "after" in params:
            after = params.get("after", "")
            if "upload_ok" in after or "drive_feedback" in str(args[0]).lower():
                audit_calls.append(c)
    assert audit_calls, (
        f"no audit_log INSERT issued; calls={[str(c)[:150] for c in session.execute.call_args_list]}"
    )


# ── 2026-05-28 hotfix regressions ─────────────────────────────────────


def test_package_persist_uses_drive_folder_id_not_source_folder_id():
    """`package_persist.persist_package` selects from the entity row to
    resolve the Drive folder for post-commit feedback. The actual column
    is `drive_folder_id` (entities table INSERT uses that exact name on
    line ~230). A historical typo used `source_folder_id`, which caused
    every post-commit Drive feedback to fail with:

        column "source_folder_id" does not exist

    The 2026-05-28 backfill log surfaced this 26 times — once per
    persisted package.

    Guard the SQL string here so a future edit can't reintroduce the
    drift without flipping this test red.
    """
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "parsers" / "package_persist.py"
    ).read_text()
    # The post-commit feedback block SELECTs the entity's Drive folder.
    # The column name in the live schema is `drive_folder_id`.
    assert "SELECT drive_folder_id FROM entities" in src, (
        "package_persist.py must SELECT drive_folder_id (not "
        "source_folder_id) when resolving the post-commit feedback "
        "target — see entities table INSERT for the canonical column "
        "name."
    )
    # And the symmetric read on the mapping result.
    assert 'mapping["drive_folder_id"]' in src, (
        "package_persist.py must read mapping['drive_folder_id'] (the "
        "alias of the SELECT above). Mixing source_folder_id here "
        "would surface as a KeyError after a successful SELECT."
    )
    # And, defensively, no stale source_folder_id reference remains in
    # the executable SQL (comments noting the historical name are fine
    # — we only flag actual SQL strings).
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "source_folder_id" in line:
            # The only acceptable executable use would be a string
            # literal inside an error message — call that out so the
            # author has to justify it.
            raise AssertionError(
                f"non-comment reference to source_folder_id in "
                f"package_persist.py: {line.strip()!r}"
            )


def test_job_executions_db_derives_sync_dsn_from_async(monkeypatch):
    """`job_executions_db._get_engine` must fall back to deriving a
    sync DSN from `DATABASE_URL` (the asyncpg form) when the explicit
    `DATABASE_URL_SYNC` env var is missing. The infra/terraform job
    spec for historical_backfill / drive_crawler / ccg_loader /
    embedder injects DATABASE_URL but NOT DATABASE_URL_SYNC, so
    without this fallback every job_executions write raises and the
    admin UI shows "running" forever (or nothing at all for CLI runs).
    """

    from app.services import job_executions_db as je

    # Force lazy-engine re-creation so we test the resolution path.
    monkeypatch.setattr(je, "_engine", None, raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:pw@/db?host=/cloudsql/proj:reg:inst",
    )

    # We don't want to actually open a pool against a non-existent
    # socket — just verify the URL the engine factory was called with.
    captured: dict[str, str] = {}

    def _fake_create_engine(url, **_kwargs):
        captured["url"] = url
        # Return a sentinel — the test never USES the engine.
        return object()

    monkeypatch.setattr(je, "create_engine", _fake_create_engine)
    je._get_engine()

    assert captured["url"].startswith("postgresql+psycopg://"), (
        f"expected derived sync DSN to start with postgresql+psycopg:// "
        f"but got {captured['url']!r} — fallback in _get_engine isn't "
        f"rewriting +asyncpg → +psycopg."
    )
    assert "+asyncpg" not in captured["url"], (
        "derived DSN still contains +asyncpg driver suffix — "
        "the rewrite is wrong."
    )


def test_job_executions_db_raises_when_both_dsns_missing(monkeypatch):
    """Belt-and-braces: if neither DATABASE_URL_SYNC nor a usable
    DATABASE_URL is set, we must raise loudly (not no-op) so the
    misconfiguration doesn't hide behind _safe_* warnings in the
    runner. Local dev should run with DMA_JOB_EXECUTION_ID unset so
    the runner skips lifecycle calls entirely.

    Test isolation: resolve_sync_dsn falls back to Secret Manager when
    both env vars are unset. In Cloud Build the worker SA has Secret
    Manager access so the fallback fires — masking the "both missing"
    contract. Force the fallback off via DMA_DISABLE_SECRET_DSN_FALLBACK
    AND reset the module's cache so a prior test that warmed the
    cache doesn't return a stale value.
    """
    import pytest

    from app.services import job_executions_db as je
    from app.services import sync_dsn as sd

    monkeypatch.setattr(je, "_engine", None, raising=False)
    monkeypatch.setattr(sd, "_CACHED_SECRET_DSN", None, raising=False)
    monkeypatch.setattr(sd, "_SECRET_LOOKUP_ATTEMPTED", False, raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DMA_DISABLE_SECRET_DSN_FALLBACK", "1")

    with pytest.raises(RuntimeError, match="sync DSN"):
        je._get_engine()
