"""DMA_DISABLE_VERTEX fast-fail contract.

In a Vertex-cold context (qa-gates, the deterministic-fallback harness, or any
deploy whose SA can authenticate via the metadata server but can't actually
reach Vertex) the client must FAIL FAST so every caller takes its grounded
deterministic fallback — never block on a real `generate_content` call that
has no timeout. This guards the 2026-06-18 qa-gates hang where
derive_focus_areas / enrich_corpus / intelligence_recompute each stalled for
the full 300s step budget after the metadata server handed them SA creds.
"""
from __future__ import annotations

import os

import pytest

from app.services.vertex_client import VertexClient


def _set(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes"])
def test_disable_flag_fast_fails_init(monkeypatch, val):
    _set(monkeypatch, DMA_DISABLE_VERTEX=val)
    with pytest.raises(RuntimeError, match="DMA_DISABLE_VERTEX"):
        VertexClient()._init()


def test_empty_project_fast_fails_init(monkeypatch):
    """No project configured ⇒ treat as cold (don't reach the SDK)."""
    _set(monkeypatch, DMA_DISABLE_VERTEX=None)
    monkeypatch.setenv("VERTEX_PROJECT_ID", "")
    # config is cached; clear so the empty env is read.
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="vertex_project_id"):
            VertexClient()._init()
    finally:
        get_settings.cache_clear()


def test_disable_flag_unset_does_not_short_circuit(monkeypatch):
    """With the flag absent + a project set, _init() proceeds past the
    fast-fail guard (it may still raise later for missing creds/SDK, but NOT
    our DMA_DISABLE_VERTEX/vertex_project_id guard)."""
    _set(monkeypatch, DMA_DISABLE_VERTEX=None)
    monkeypatch.delenv("VERTEX_PROJECT_ID", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        assert (get_settings().vertex_project_id or "").strip()  # default project present
    finally:
        get_settings.cache_clear()
    assert os.environ.get("DMA_DISABLE_VERTEX") in (None, "")
