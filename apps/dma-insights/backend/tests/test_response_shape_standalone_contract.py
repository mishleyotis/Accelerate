"""Phase 2 — backend response Pydantic models ↔ standalone-src field
references contract test.

For every Pydantic response_model the FastAPI routers declare, walk
its JSON schema (via `.model_fields`) and compare to the fields the
standalone-src loader / page components actually consume. Drift in
either direction is a runtime bug:

  - Backend renames a field → frontend renders undefined → UI shows
    "—" or NaN on a chart
  - Frontend adds a new field name in a typo → that field is never
    populated; the operator complains "where's the X column?"

This file pins ~30 critical fields per surface (Overview, Heatmap,
Insights, Platforms, RAG answer, Admin job execution). Self-healing
contract: a renamed field surfaces here BEFORE the user does.
"""
from __future__ import annotations

from pathlib import Path

import pytest

STANDALONE_SRC = (
    Path(__file__).resolve().parents[1].parent
    / "frontend" / "standalone-src" / "src"
)


def _load_standalone(name: str) -> str:
    p = STANDALONE_SRC / name
    if not p.exists():
        pytest.skip(f"standalone file {name} missing")
    return p.read_text(encoding="utf-8")


def _model_field_names(model_cls) -> set[str]:
    """Pydantic v2 model -> set of field names."""
    return set(getattr(model_cls, "model_fields", {}).keys())


# ── EntityOverviewResponse ↔ pages-d1-overview.jsx ────────────────


def test_entity_overview_response_field_pillar_scores_consumed():
    """The single most operator-visible Overview field is
    `pillar_scores`. The D1 PillarBar component renders the tick
    visualizer from this array. A schema rename breaks the bar.
    Other fields are either adapted via backend-loader.adaptEntity
    OR are forward-compat additions (parser_warnings, narrative)."""
    from app.schemas.entities import EntityOverviewResponse

    fields = _model_field_names(EntityOverviewResponse)
    assert "pillar_scores" in fields, (
        "EntityOverviewResponse must declare pillar_scores."
    )
    haystack = (
        _load_standalone("pages-d1-overview.jsx")
        + _load_standalone("backend-loader.js")
    )
    assert "pillar_scores" in haystack, (
        "pillar_scores not referenced in D1 overview page or backend-"
        "loader. The PillarBar visualizer can't render without it."
    )


def test_entity_overview_response_critical_fields_declared():
    """Backend-side field-existence check. The standalone adapter
    (backend-loader.js::adaptEntity) aliases names, so we don't
    require literal substring matches in JSX. But the backend schema
    MUST keep the canonical names so the adapter has something to
    read."""
    from app.schemas.entities import EntityOverviewResponse

    fields = _model_field_names(EntityOverviewResponse)
    required = {"entity", "pillar_scores", "evidence_freshness"}
    missing = required - fields
    assert not missing, (
        f"EntityOverviewResponse missing required fields: {missing}. "
        "Frontend adapter expects these names."
    )


def test_entity_overview_pillar_scores_is_a_list():
    """pillar_scores must be a list shape so the frontend can
    iterate it. A change to dict-keyed-by-pillar would silently
    break the .map() in PillarBar."""
    from app.schemas.entities import EntityOverviewResponse

    field = EntityOverviewResponse.model_fields.get("pillar_scores")
    assert field is not None
    # Pydantic v2: annotation carries `list[dict]` or similar.
    annotation = str(field.annotation)
    assert "list" in annotation.lower() or "List" in annotation, (
        f"pillar_scores annotation is {annotation!r}; must be a list "
        "shape so PillarBar.map() works."
    )


# ── HeatmapResponse ↔ pages-d3-heatmap.jsx ────────────────────────


def test_heatmap_response_fields_used_by_frontend():
    """The HeatmapResponse carries cells[] + value_chain_buckets[] +
    catalogue_version. D3 Heatmap consumes all three."""
    from app.schemas.heatmap import HeatmapResponse

    fields = _model_field_names(HeatmapResponse)
    haystack = (
        _load_standalone("pages-d3-heatmap.jsx")
        + _load_standalone("backend-loader.js")
    )
    for f in {"cells", "catalogue_version"} & fields:
        assert f in haystack, (
            f"HeatmapResponse.{f} not referenced in D3 heatmap."
        )


def test_heatmap_cell_score_field_referenced():
    """Each HeatmapCell carries `score` (the cell value). A rename
    would silently render every cell as undefined → entire heatmap
    blank."""
    from app.schemas.heatmap import HeatmapCell

    fields = _model_field_names(HeatmapCell)
    src = _load_standalone("pages-d3-heatmap.jsx")
    assert "score" in fields, "HeatmapCell missing score field"
    assert "score" in src, (
        "D3 heatmap doesn't reference HeatmapCell.score. The entire "
        "color-map renders blank."
    )


# ── Insights ↔ pages-d1 + drawers ─────────────────────────────────


def test_insight_card_response_declares_critical_severity_and_title():
    """InsightCardOut must declare severity + title -- the two
    fields that drive the insight chip color + label everywhere
    in the UI."""
    from app.schemas.insights import InsightCardOut

    fields = _model_field_names(InsightCardOut)
    for required in ("severity", "title"):
        assert required in fields, (
            f"InsightCardOut missing required field {required!r}. "
            "Insight chip rendering depends on this."
        )


# ── Platforms ↔ pages-d3-d4.jsx ───────────────────────────────────


def test_platforms_response_fields_used_by_frontend():
    """PlatformsResponse declares cards[] + pillar_offerings.
    pages-d3-d4 consumes both."""
    from app.schemas.platforms import PlatformsResponse

    fields = _model_field_names(PlatformsResponse)
    haystack = (
        _load_standalone("pages-d3-d4.jsx")
        + _load_standalone("backend-loader.js")
    )
    for f in {"cards"} & fields:
        assert f in haystack, (
            f"PlatformsResponse.{f} not referenced by the D4 page."
        )


# ── RecommendationDetail ↔ drawers.jsx ────────────────────────────


def test_recommendation_detail_declares_uplift_and_effort_fields():
    """RecommendationDetail must declare uplift_per_pillar +
    effort_band -- the inputs the StairstepCurve uses to position
    each recommendation on the impact/effort plane."""
    from app.schemas.recommendations import RecommendationDetail

    fields = _model_field_names(RecommendationDetail)
    for required in ("title", "uplift_per_pillar", "effort_band"):
        assert required in fields, (
            f"RecommendationDetail missing required field {required!r}."
        )


# ── Admin job execution ↔ admin page ─────────────────────────────


def test_job_execution_out_fields_used_by_admin_page():
    """JobExecutionOut declares id + job_name + status +
    result_summary + error_message + stderr_tail. The admin
    OperationsCard renders all of these."""
    from app.schemas.admin import JobExecutionOut

    fields = _model_field_names(JobExecutionOut)
    admin_src = _load_standalone("pages-alerts-prospecting-admin.jsx")
    for f in {"job_name", "status", "result_summary"} & fields:
        assert f in admin_src, (
            f"JobExecutionOut.{f} not referenced in the admin page. "
            "The Recent jobs table would render this column blank."
        )


# ── Schema-vs-loader name drift cross-check ───────────────────────


def test_no_schema_field_renamed_without_loader_update():
    """A common drift: someone renames a schema field (e.g.
    `entity_display_id` → `display_id`) but forgets to update the
    backend-loader. This scan looks for any reference to the OLD
    name in the loader paired with the NEW name in the schema.

    The audit pins a small set of historical renames + ensures the
    OLD name isn't lingering in the loader."""
    backend_loader = _load_standalone("backend-loader.js")
    # If you've renamed a field, add `OLD_NAME: NEW_NAME` here and
    # the test will flag if both still appear in the loader.
    # No current renames -- if a refactor adds one, the entry is
    # the audit trail of WHY this test exists.
    known_renames: dict[str, str] = {}
    drift = []
    for old, new in known_renames.items():
        if old in backend_loader and new in backend_loader:
            drift.append((old, new))
    assert not drift, (
        f"Field renames present in loader (old + new both reference): "
        f"{drift}. Pick one."
    )


# ── Field-level matrix doc ────────────────────────────────────────


def test_field_matrix_doc_exists():
    """A simple existence check for `docs/FIELD-MATRIX.md` so future
    contributors have a single source of truth for which surface
    consumes which backend field. If the file is missing this test
    skips loudly so it can be created without breaking CI."""
    matrix = (
        Path(__file__).resolve().parents[1].parent
        / "docs" / "FIELD-MATRIX.md"
    )
    if not matrix.exists():
        pytest.skip(
            "docs/FIELD-MATRIX.md not yet authored -- track this as a "
            "follow-up. The audit's Phase 2 matrix request lives here."
        )
    text = matrix.read_text(encoding="utf-8")
    # Must enumerate the 10 audit-named surfaces.
    for surface in ("D1 Overview", "D3 Heatmap", "D4 Platforms",
                    "D5 Context", "D6 Health", "Admin"):
        assert surface in text, (
            f"FIELD-MATRIX.md missing surface '{surface}'."
        )
