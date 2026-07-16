"""Tests for intelligence_builder — pure logic + template rendering.

Live Vertex/DB calls are not tested here; those are exercised in
integration tests that require GCP credentials. This suite covers:
  - _SafeFormatMap never raises on missing keys
  - All template surfaces render without KeyError
  - _extract_e_ids finds E-NNN patterns
  - _build_context dispatches correctly per surface (arg parsing)
  - run_intelligence publishes fallback when surface is unknown
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.intelligence_builder import (
    _TEMPLATES,
    _extract_e_ids,
    _grounded_fallback,
    _SafeFormatMap,
    run_intelligence,
)

# ── _SafeFormatMap ────────────────────────────────────────────────────────────

def test_safe_format_map_returns_placeholder_for_missing_key() -> None:
    m = _SafeFormatMap({"a": "hello"})
    result = "{a} {b}".format_map(m)
    assert result == "hello {b}"


def test_safe_format_map_does_not_raise_on_all_missing() -> None:
    m = _SafeFormatMap({})
    result = "{x} {y} {z}".format_map(m)
    assert result == "{x} {y} {z}"


# ── Template rendering ────────────────────────────────────────────────────────

@pytest.mark.parametrize("surface", list(_TEMPLATES.keys()))
def test_template_renders_with_full_ctx(surface: str) -> None:
    """Every surface template renders without KeyError when ctx is saturated."""
    ctx = {
        # subcap_narrative
        "subcap_id": "P2C3.2.4",
        "subcap_name": "Digital Onboarding",
        "score": "3.2",
        "band": "M3",
        "peer_median": "3.5",
        "rationale": "Client is progressing well.",
        "ev_count": "2",
        "ev_summary": "E-001 (CFPB: brief excerpt); E-002 (Glassdoor)",
        # why_now
        "entity_name": "GESA Credit Union",
        "overall_score": "2.9",
        "scqa_situation": "Digital adoption lagging peers.",
        "why_now_signals": "MIGRATION, REGULATORY",
        # insight_explanation
        "title": "Low Omnichannel Score",
        "what_text": "The entity scores 2.1 on omnichannel readiness.",
        "why_text": "This limits cross-channel consistency.",
        "so_what_text": "Modernise the mobile app first.",
        # platform_story — scqa_situation reused from why_now block above
        "platform_id": "salesforce",
        "fit_score": "0.82",
        "top_gaps": "P2C3.2.4, P2C3.2.5",
        # meeting_prep
        "top_findings": "Low omnichannel (CRITICAL); Data gaps (HIGH)",
        "platform_summary": "salesforce (fit 0.82)",
    }
    tpl = _TEMPLATES[surface]["template"]
    rendered = tpl.format_map(_SafeFormatMap(ctx))
    assert len(rendered) > 30, f"Template for {surface} rendered too short"


@pytest.mark.parametrize("surface", list(_TEMPLATES.keys()))
def test_template_renders_with_empty_ctx(surface: str) -> None:
    """Templates render (with placeholder substitution) even on empty ctx."""
    tpl = _TEMPLATES[surface]["template"]
    rendered = tpl.format_map(_SafeFormatMap({}))
    # Should not raise; should contain literal braces for any missing keys
    assert isinstance(rendered, str)


# ── _extract_e_ids ────────────────────────────────────────────────────────────

def test_extract_e_ids_finds_standard_patterns() -> None:
    text = "As seen in E-123 and E-456, the evidence supports this."
    assert _extract_e_ids(text) == ["E-123", "E-456"]


def test_extract_e_ids_deduplicates() -> None:
    text = "E-100 is cited twice: E-100."
    assert _extract_e_ids(text) == ["E-100"]


def test_extract_e_ids_empty_on_no_match() -> None:
    assert _extract_e_ids("No evidence IDs here.") == []


def test_extract_e_ids_preserves_order() -> None:
    text = "E-300, then E-100, then E-200."
    assert _extract_e_ids(text) == ["E-300", "E-100", "E-200"]


# ── _grounded_fallback (deterministic cold fallback) ─────────────────────────

def test_grounded_fallback_subcap_fills_ctx_and_cites_real_eids() -> None:
    """Cold Vertex must NOT discard ctx: the deterministic body carries
    score, band, peer median, rationale and the retrieved evidence lines,
    and cites exactly the E-IDs that appear in the body."""
    ctx = {
        "subcap_id": "P2C3.2.4",
        "subcap_name": "Digital Onboarding",
        "score": "3.2",
        "band": "M3",
        "peer_median": "3.5",
        "rationale": "Scores held back by manual identity checks.",
        "_ev_lines": [
            "E-101 (CFPB): manual identity checks flagged",
            "E-102 (Annual Report): onboarding cited as a priority",
        ],
        "_retrieved_e_ids": ["E-101", "E-102"],
    }
    body, cited = _grounded_fallback("subcap_narrative", ctx)
    assert "Digital Onboarding" in body
    assert "P2C3.2.4" in body
    assert "3.2" in body and "M3" in body and "3.5" in body
    assert "manual identity checks" in body
    assert "Grounded evidence:" in body
    assert cited == ["E-101", "E-102"]


def test_grounded_fallback_never_echoes_placeholder_values() -> None:
    """Placeholder ctx values ('N/A', 'No rationale recorded.', …) must
    not be rendered as if they were facts."""
    ctx = {
        "subcap_id": "P1C1.1.1",
        "subcap_name": "P1C1.1.1",
        "score": "N/A",
        "band": "N/A",
        "peer_median": "N/A",
        "rationale": "No assessment data available.",
        "_ev_lines": [],
        "_retrieved_e_ids": [],
    }
    body, cited = _grounded_fallback("subcap_narrative", ctx)
    assert "N/A" not in body
    assert "No assessment data available." not in body
    assert "no score recorded" in body
    assert cited == []


def test_grounded_fallback_why_now_embeds_recent_evidence() -> None:
    ctx = {
        "entity_name": "GESA Credit Union",
        "overall_score": "2.9",
        "scqa_situation": "Digital adoption lagging peers.",
        "why_now_signals": "MIGRATION, REGULATORY",
        "recent_evidence": "- E-201 (T6, 3mo, 10-K): core migration in flight",
    }
    body, cited = _grounded_fallback("why_now", ctx)
    assert "GESA Credit Union" in body
    assert "2.9" in body
    assert "Digital adoption lagging peers." in body
    assert "MIGRATION, REGULATORY" in body
    assert cited == ["E-201"]


def test_grounded_fallback_platform_story_uses_gap_evidence() -> None:
    ctx = {
        "entity_name": "WSFS Bank",
        "platform_id": "salesforce",
        "fit_score": "0.82",
        "top_gaps": "P2C3.2.4, P2C3.2.5",
        "scqa_situation": "Mid-migration to nCino.",
        "gap_evidence": "- E-310 (T2, 5mo, Earnings call): data platform evaluation",
    }
    body, cited = _grounded_fallback("platform_story", ctx)
    assert "salesforce" in body and "WSFS Bank" in body
    assert "0.82" in body
    assert "P2C3.2.4" in body
    assert cited == ["E-310"]


def test_grounded_fallback_surface_without_template_stays_honest() -> None:
    """Surfaces with no deterministic template (e.g. the strict-JSON
    firmographics extractor) fall back to an honest message — never a
    fabricated body."""
    body, cited = _grounded_fallback(
        "firmographics_extraction",
        {"entity_name": "X", "report_excerpts": "some excerpt"},
    )
    assert cited == []
    assert "unavailable" in body.lower()


# ── run_intelligence ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_intelligence_publishes_fallback_for_unknown_surface() -> None:
    published: list[dict] = []

    async def fake_publish(channel: str, data: str) -> None:
        published.append({"channel": channel, "data": json.loads(data)})

    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock(side_effect=fake_publish)
    mock_session = MagicMock()

    await run_intelligence(
        surface="nonexistent_surface",
        ref="fce-001",
        session=mock_session,
        redis=mock_redis,
    )

    assert len(published) == 1
    assert published[0]["data"]["kind"] == "fallback"
    assert "nonexistent_surface" in str(published[0]["data"]["flags"])
    # Body ships under BOTH keys (served_text historical, text forward).
    assert published[0]["data"]["text"] == published[0]["data"]["served_text"]


@pytest.mark.asyncio
async def test_run_intelligence_publishes_fallback_on_context_error() -> None:
    """If context builder raises, we get a fallback event (not an unhandled exception)."""
    published: list[dict] = []

    async def fake_publish(channel: str, data: str) -> None:
        published.append(json.loads(data))

    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock(side_effect=fake_publish)
    mock_session = MagicMock()

    # subcap_narrative needs "display_id:subcap_id" — pass a malformed ref
    with patch(
        "app.services.intelligence_builder._ctx_subcap_narrative",
        side_effect=RuntimeError("DB unavailable"),
    ):
        await run_intelligence(
            surface="subcap_narrative",
            ref="fce-001:P2C3.2.4",
            session=mock_session,
            redis=mock_redis,
        )

    fb = [e for e in published if e["kind"] == "fallback"]
    assert fb
    assert "context_error" in fb[-1]["flags"]
    assert fb[-1]["text"] == fb[-1]["served_text"]
    assert fb[-1]["text"]  # honest non-empty body


@pytest.mark.asyncio
async def test_run_intelligence_publishes_fallback_on_vertex_error() -> None:
    """If Vertex stream raises, we get a fallback event."""
    published: list[dict] = []

    async def fake_publish(channel: str, data: str) -> None:
        published.append(json.loads(data))

    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock(side_effect=fake_publish)
    mock_session = MagicMock()

    ctx = {
        "subcap_id": "P2C3.2.4",
        "subcap_name": "Test Cap",
        "score": "3.0",
        "band": "M3",
        "peer_median": "3.5",
        "rationale": "Manual workflows keep the score below peer.",
        "ev_count": 2,
        "ev_summary": "E-101 (CFPB: brief…); E-102 (10-K: brief…)",
        "_ev_lines": [
            "E-101 (CFPB): manual workflows flagged",
            "E-102 (10-K): modernization budget line",
        ],
        "_retrieved_e_ids": ["E-101", "E-102"],
    }

    async def raise_immediately(call):
        raise RuntimeError("Vertex quota exceeded")
        yield  # pragma: no cover

    with (
        patch(
            "app.services.intelligence_builder._build_context",
            return_value=ctx,
        ) as _ctx_mock,
        patch(
            "app.services.intelligence_builder.get_vertex_client",
        ) as mock_vc,
    ):
        _ctx_mock  # noqa: B018 — suppress "not used" warning; it IS used via patch
        instance = MagicMock()
        instance.stream = raise_immediately
        mock_vc.return_value = instance

        await run_intelligence(
            surface="subcap_narrative",
            ref="fce-001:P2C3.2.4",
            session=mock_session,
            redis=mock_redis,
        )

    fb = [e for e in published if e["kind"] == "fallback"]
    assert fb
    payload = fb[-1]
    # Flags name the real reason — the frontend banner keys off this.
    assert "Vertex quota exceeded" in str(payload["flags"]["vertex_error"])
    assert payload["flags"]["deterministic"] is True
    # Grounded deterministic body: ctx is NOT discarded.
    assert payload["served_text"] == payload["text"]
    assert "Test Cap" in payload["text"]
    assert "3.0" in payload["text"] and "3.5" in payload["text"]
    assert "E-101" in payload["text"] and "E-102" in payload["text"]
    assert payload["cited_evidence_ids"] == ["E-101", "E-102"]


@pytest.mark.asyncio
async def test_run_intelligence_streams_tokens_and_done_on_clean_response() -> None:
    """Happy path: tokens arrive, validator passes, 'done' event published."""
    published: list[dict] = []

    async def fake_publish(channel: str, data: str) -> None:
        published.append(json.loads(data))

    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock(side_effect=fake_publish)
    mock_session = MagicMock()

    ctx = {
        "subcap_id": "P2C3.2.4",
        "subcap_name": "Test Cap",
        "score": "3.0",
        "band": "M3",
        "peer_median": "3.5",
        "rationale": "OK",
        "ev_count": 0,
        "ev_summary": "None",
    }

    async def fake_stream(call):
        for word in ["The ", "score ", "is ", "good."]:
            yield word

    from app.services.grounding_validator import ValidationFlags

    with (
        patch(
            "app.services.intelligence_builder._build_context",
            return_value=ctx,
        ),
        patch(
            "app.services.intelligence_builder.get_vertex_client",
        ) as mock_vc,
        patch(
            "app.services.intelligence_builder.validate_response",
            return_value=ValidationFlags(),
        ),
    ):
        instance = MagicMock()
        instance.stream = fake_stream
        mock_vc.return_value = instance

        await run_intelligence(
            surface="subcap_narrative",
            ref="fce-001:P2C3.2.4",
            session=mock_session,
            redis=mock_redis,
        )

    kinds = [e["kind"] for e in published]
    assert "token" in kinds
    assert kinds[-1] == "done"
    # Tokens arrive in order
    token_texts = [e["text"] for e in published if e["kind"] == "token"]
    assert "".join(token_texts) == "The score is good."


@pytest.mark.asyncio
async def test_run_intelligence_serves_grounded_floor_on_validator_reject() -> None:
    """Validator rejection must degrade to the GROUNDED deterministic floor
    (score/band + real E-IDs), NOT an 'Insight withheld' apology — the AE still
    sees the substantive summary (2026-07-03 resilience fix)."""
    published: list[dict] = []

    async def fake_publish(channel: str, data: str) -> None:
        published.append(json.loads(data))

    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock(side_effect=fake_publish)
    ctx = {
        "subcap_id": "P2C3.2.4", "subcap_name": "Test Cap", "score": "2.0",
        "band": "M2", "peer_median": "3.5", "rationale": "Legacy core caps it.",
        "ev_count": 1, "ev_summary": "Fiserv DNA core [E-042]",
        "_retrieved_e_ids": ["E-042"],
    }

    async def fake_stream(call):
        for w in ["Score ", "is ", "2 ", "[E-999]."]:  # E-999 not in bundle
            yield w

    from app.services.grounding_validator import ValidationFlags

    with (
        patch("app.services.intelligence_builder._build_context", return_value=ctx),
        patch("app.services.intelligence_builder.get_vertex_client") as mock_vc,
        patch("app.services.intelligence_builder.validate_response",
              return_value=ValidationFlags(fabricated_e_ids=["E-999"])),
    ):
        instance = MagicMock()
        instance.stream = fake_stream
        mock_vc.return_value = instance
        await run_intelligence(
            surface="subcap_narrative", ref="fce-001:P2C3.2.4",
            session=MagicMock(), redis=mock_redis,
        )

    fb = [e for e in published if e["kind"] == "fallback"]
    assert fb, "validator reject must publish a fallback event"
    body = fb[-1].get("served_text", "") + fb[-1].get("text", "")
    assert "withheld" not in body.lower(), "must not serve the apology stub"
    assert "2.0" in body or "M2" in body, "must carry the grounded score/band floor"
    # only real retrieved E-IDs are cited — never the fabricated E-999
    assert "E-999" not in body
