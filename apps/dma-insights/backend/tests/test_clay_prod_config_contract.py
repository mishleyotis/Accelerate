"""Clay connector deferred-in-prod contract (2026-06-10 supersedes F-306).

Operator mandate: "Clay is not yet in prod for this version. Ensure the
details are drawn from the client research or client profile report.
The rest can be enriched using gemini models first."

The contract therefore FLIPPED from the F-306 resolution:

  1. REQUIRED_FOR_PROD_BACKEND must NOT include the Clay keys — a prod
     revision boots with both empty (deferred).
  2. assert_production_ready PASSES with empty Clay values under
     env=prod (everything else populated).
  3. The Clay client fail-closes on the empty URL (ADR 0010's
     'disabled' branch) — no outbound call, typed disabled reason —
     so deferred deploys never half-fire enrichment.
  4. ADR 0010 carries the dated deferral amendment so the next reader
     knows required-in-prod was deliberately suspended for this
     version (re-add the keys + flip these tests when Clay ships).
  5. Firmographics provenance in the deferred world: ingest extracts
     from the client research / Client Profile reports; the Gemini
     `firmographics_extraction` surface (quote-grounded) fills gaps.
"""
from __future__ import annotations

from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1].parent / "docs"
ADR = DOCS / "decisions" / "0010-clay-connector.md"


def test_required_for_prod_backend_excludes_clay_secrets():
    """Clay deferred: the readiness guard must NOT block a prod boot
    on Clay secrets this version."""
    from app.config import REQUIRED_FOR_PROD_BACKEND

    required = {name for name, _ in REQUIRED_FOR_PROD_BACKEND}
    assert "clay_webhook_url" not in required, (
        "clay_webhook_url re-added to REQUIRED_FOR_PROD_BACKEND — Clay "
        "is deferred this version (operator 2026-06-10); flip this test "
        "deliberately when Clay ships."
    )
    assert "clay_webhook_secret" not in required


def _prod_settings(**overrides):
    from app.config import Settings

    base = {
        "env": "prod",
        "database_url": "postgresql+asyncpg://user:pass@10.0.0.5/dma_insights",
        "redis_url": "redis://prod-redis.example.com:6379/0",
        "google_oauth_client_id": "real-client.apps.googleusercontent.com",
        "google_oauth_client_secret": "GOCSPX-real-secret",
        "dma_bot_api_key": "prod-bot-key",
        "rag_api_bearer_key": "prod-rag-key",
        "gcp_project_id": "digital-maturity-assessor",
    }
    base.update(overrides)
    return Settings(**base)


def test_prod_boots_with_both_clay_secrets_empty(monkeypatch):
    """Deferred semantics: empty Clay values must NOT fail the boot."""
    from app.config import assert_production_ready

    monkeypatch.setenv(
        "JWT_PRIVATE_KEY_PEM",
        "-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n",
    )
    # Keep the test offline — the 2026-07 Vertex startup probe would
    # otherwise attempt a real network call under env=prod.
    monkeypatch.setenv("DMA_DISABLE_VERTEX", "1")
    s = _prod_settings(clay_webhook_url="", clay_webhook_secret="")
    assert_production_ready(s)  # must not raise


def test_clay_client_fail_closes_when_url_unset():
    """The 'disabled' branch is now the PROD behavior while deferred:
    no outbound call, typed disabled reason. Pin the marker string so
    a refactor that drops the fail-closed path surfaces here."""
    from app.services.clay_client import trigger_enrichment  # noqa: F401

    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "clay_client.py"
    ).read_text(encoding="utf-8")
    assert "clay_webhook_url not configured" in src, (
        "Clay client must surface a typed disabled reason — while Clay "
        "is deferred this IS the production code path."
    )


def test_adr_0010_documents_the_deferral():
    """ADR 0010 must carry the dated deferral amendment so the
    requirement flip is discoverable from the decision record."""
    if not ADR.exists():
        pytest.skip(f"ADR 0010 not present at {ADR}")
    text = ADR.read_text(encoding="utf-8").lower()
    assert "deferred" in text and "2026-06-10" in text, (
        "ADR 0010 lacks the 2026-06-10 deferral amendment — document "
        "the suspension of required-in-prod before shipping."
    )


def test_firmographics_provenance_chain_without_clay():
    """While Clay is deferred, firmographics provenance is reports →
    Gemini gap-fill. Pin the load-bearing pieces by import + marker."""
    from app.scripts.enrich_corpus import (
        _SURFACE_MODEL,
        _accept_firmo_fields,  # noqa: F401
    )
    from app.services.intelligence_builder import _TEMPLATES

    assert "firmographics_extraction" in _TEMPLATES
    assert _SURFACE_MODEL.get("firmographics_extraction") == "flash"
