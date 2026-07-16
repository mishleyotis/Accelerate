"""Render-harness classification contract (app/scripts/qa_render_validation).

Locks the deploy-resilience semantics introduced after the 2026-06-08
qa-gates failure: a sparse / non-canonical SOURCE package (zero parsed
subcap scores) must render fail-closed (HTTP 200 + empty contract) and be
classified PARTIAL — NOT a hard FAIL that blocks the deploy. A *systemic*
zero-score regression is still caught by the aggregate ZERO_SCORE_FLOOR.

Genuine render breakage (out-of-range scores, non-dict body) must stay
FAIL so a real contract violation still blocks the build.
"""

from app.scripts.qa_render_validation import (
    RENDER_ENDPOINTS,
    ZERO_SCORE_FLOOR,
    _validate_context,
    _validate_heatmap,
    _validate_overview,
    _validate_platforms,
)


def test_overview_zero_scores_is_partial_not_fail() -> None:
    """An empty overview (no pillar scores) is a sparse-source render, not
    a failure — it must be PARTIAL and tagged zero_score for the floor."""
    status, obs, counts = _validate_overview({"pillar_scores": [], "scqa": None})
    assert status == "PARTIAL", f"zero-score overview should be PARTIAL, got {status}"
    assert counts.get("zero_score") == 1
    assert any("sparse source" in o for o in obs)


def test_overview_full_scores_ok() -> None:
    body = {"pillar_scores": [{"pillar_id": f"P{i}", "score": 3.0} for i in range(1, 5)]}
    status, _obs, counts = _validate_overview(body)
    assert status == "OK"
    assert counts["pillars"] == 4
    assert "zero_score" not in counts


def test_overview_non_dict_still_fails() -> None:
    status, _obs, _counts = _validate_overview([])  # type: ignore[arg-type]
    assert status == "FAIL"


def test_heatmap_zero_cells_is_partial_not_fail() -> None:
    status, obs, counts = _validate_heatmap({"cells": []})
    assert status == "PARTIAL", f"zero-cell heatmap should be PARTIAL, got {status}"
    assert counts.get("zero_score") == 1
    assert any("sparse source" in o for o in obs)


def test_heatmap_populated_ok() -> None:
    cells = [{"subcap_id": f"S{i}", "score": 3} for i in range(120)]
    status, _obs, counts = _validate_heatmap({"cells": cells})
    assert status == "OK"
    assert counts["cells"] == 120
    assert "zero_score" not in counts


def test_platforms_reads_cards_key() -> None:
    """PlatformsResponse exposes the 5 platforms under `cards` — the
    validator must read that key, not the never-present `platforms`/
    `items`. Regression for the field-name false negative that reported
    'no platform scores' for every populated entity."""
    body = {"cards": [{"platform_id": p} for p in
                      ("salesforce", "databricks", "tableau", "twilio", "ncino")]}
    status, _obs, counts = _validate_platforms(body)
    assert status == "OK", f"5 platform cards should be OK, got {status}"
    assert counts["platforms"] == 5


def test_platforms_empty_is_partial() -> None:
    status, obs, counts = _validate_platforms({"cards": []})
    assert status == "PARTIAL"
    assert counts["platforms"] == 0
    assert any("no platform scores" in o for o in obs)


def test_heatmap_endpoint_probes_subcap_zoom() -> None:
    """The cell-count floor (>= 100) only measures data presence at the
    deepest zoom; the default zoom=pillar yields ~4 cells. The harness
    must probe ?zoom=subcap so a populated grid isn't a false negative."""
    heatmap_url = dict(RENDER_ENDPOINTS)["heatmap"]
    assert "zoom=subcap" in heatmap_url, heatmap_url


def test_context_credits_leadership_and_narrative() -> None:
    """Context page richness is leadership / narrative_md / regulator /
    issue_register — NOT the absent scalar firmographic keys (hq /
    employees / total_assets). An entity with a leadership roster + a
    narrative must read OK, not PARTIAL."""
    body = {
        "firmographics": {
            "leadership": [{"name": "A"}, {"name": "B"}],
            "narrative_md": "Company context prose...",
            "primary_regulator": "OCC",
        },
        "issue_register": [{"id": "I1"}],
        "timeline_events": [],
        "acquisitions": [],
    }
    status, _obs, counts = _validate_context(body)
    assert status == "OK", f"rich context should be OK, got {status}"
    assert counts["renderable_signals"] >= 2


def test_context_empty_is_partial() -> None:
    status, obs, counts = _validate_context(
        {"firmographics": {}, "issue_register": []}
    )
    assert status == "PARTIAL"
    assert counts["renderable_signals"] == 0
    assert any("context empty" in o for o in obs)


def test_zero_score_floor_is_sane() -> None:
    """Strict-ingest-gate era (2026-06-10): unscored packages never
    persist, so a healthy corpus has ~0% zero-score entities. The floor
    must be a small transient headroom — NOT an allowance for partial
    ingests (the old 0.20 floor masked 8-9 hollow entities on the live
    directory)."""
    assert 0.0 < ZERO_SCORE_FLOOR <= 0.10
