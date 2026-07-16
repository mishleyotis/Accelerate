"""Focus-area mandate (operator 2026-07-08): focus areas / strategic objectives
are NEVER deterministic — verbatim from the report or Gemini-extracted — and are
re-validated + refreshed half-yearly once loaded.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.focus_area_synthesizer import (
    FOCUS_REFRESH_DAYS,
    focus_needs_refresh,
)


def test_half_yearly_refresh_window() -> None:
    assert FOCUS_REFRESH_DAYS == 182
    now = datetime(2026, 7, 8, tzinfo=UTC)
    fresh = now - timedelta(days=30)
    stale = now - timedelta(days=200)
    assert focus_needs_refresh(fresh, now) is False
    assert focus_needs_refresh(stale, now) is True
    assert focus_needs_refresh(None, now) is True            # never loaded → refresh
    assert focus_needs_refresh("2026-01-01T00:00:00Z", now) is True   # >182d, iso string


def test_synthesize_defaults_to_no_deterministic_heuristic() -> None:
    """allow_heuristic defaults to False — the deterministic clustering is off."""
    import inspect

    from app.services.focus_area_synthesizer import synthesize_focus_areas
    sig = inspect.signature(synthesize_focus_areas)
    assert sig.parameters["allow_heuristic"].default is False
