"""Unit tests for the focus-area synthesizer's pure-logic primitives.

The end-to-end synthesizer (Gemini call + DB write) needs a live PG +
Vertex credentials and is covered by stage 2b live-PG. These tests pin
the deterministic pieces — validator, heuristic fallback, recommendation
matcher — that ship in every environment.
"""

from __future__ import annotations

import asyncio

from app.services.focus_area_synthesizer import (
    SynthesizedFocusArea,
    _heuristic_focus_areas,
    _load_existing_docx_focus_areas,
    _match_recommendations,
    _RunContext,
    _validate_and_dedupe,
)


def _ctx() -> _RunContext:
    """Build a `_RunContext` for the heuristic + validator tests."""
    return _RunContext(
        run_id="r-1",
        entity_id="e-1",
        entity_name="Test Bank",
        subvertical="RB",
        pillar_means={"P1": 2.6, "P2": 2.2, "P3": 2.8, "P4": 2.0},
        low_scoring_subcaps=[
            {"subcap_id": "P2C1.1.1", "score": 1.8, "rationale": "channels"},
            {"subcap_id": "P2C1.1.2", "score": 1.9, "rationale": "servicing"},
            {"subcap_id": "P2C2.1.1", "score": 2.0, "rationale": "personalization"},
            {"subcap_id": "P4C1.1.1", "score": 1.7, "rationale": "data foundation"},
            {"subcap_id": "P4C1.1.2", "score": 1.9, "rationale": "data integration"},
            {"subcap_id": "P1C1.1.1", "score": 2.3, "rationale": "strategy clarity"},
        ],
        recommendations=[
            {"rec_id": "IC-001", "title": "Customer 360",
             "description": "", "target_subcap_ids": ["P2C1.1.1", "P2C1.1.2"],
             "platform_id": "salesforce"},
            {"rec_id": "IC-002", "title": "Data Cloud",
             "description": "", "target_subcap_ids": ["P4C1.1.1"],
             "platform_id": "data-cloud"},
            {"rec_id": "IC-003", "title": "Unrelated rec",
             "description": "", "target_subcap_ids": ["P9C9.9.9"],
             "platform_id": None},
        ],
        all_subcap_ids={
            "P2C1.1.1", "P2C1.1.2", "P2C2.1.1",
            "P4C1.1.1", "P4C1.1.2",
            "P1C1.1.1", "P9C9.9.9",
        },
    )


def test_heuristic_clusters_by_pillar_and_drops_singletons() -> None:
    ctx = _ctx()
    out = _heuristic_focus_areas(ctx)
    titles = {a.title for a in out}
    # P2 (3 subcaps) and P4 (2 subcaps) cluster; P1 (1) drops; P3 (0) drops.
    assert "Modernize customer experience" in titles
    assert "Build the data foundation" in titles
    assert "Sharpen strategic posture" not in titles
    # Every area's involved_subcap_ids exists in the run.
    for area in out:
        assert area.data_source == "heuristic"
        for sid in area.involved_subcap_ids:
            assert sid in ctx.all_subcap_ids


def test_validator_drops_hallucinated_subcap_ids() -> None:
    ctx = _ctx()
    raw = [
        {
            "title": "Modernize member experience",
            "description": "Consolidate channels.",
            "involved_subcap_ids": [
                "P2C1.1.1",     # real
                "P2C1.1.2",     # real
                "P2C9.9.9",     # HALLUCINATED — must be dropped
            ],
        },
        {
            "title": "Build data foundation",
            "description": "Anchor on a modern lakehouse.",
            "involved_subcap_ids": ["P4C1.1.1", "P4C1.1.2"],
        },
        {
            "title": "Empty area",
            "description": "Should be dropped — <2 subcaps after validation.",
            "involved_subcap_ids": ["NOT_REAL"],
        },
    ]
    out = _validate_and_dedupe(raw, ctx.all_subcap_ids)
    assert len(out) == 2
    assert out[0].involved_subcap_ids == ["P2C1.1.1", "P2C1.1.2"]
    assert out[1].involved_subcap_ids == ["P4C1.1.1", "P4C1.1.2"]
    # All data_source labels stay "gemini-flash" through the validator.
    assert all(a.data_source == "gemini-flash" for a in out)


def test_validator_dedupes_subcaps_across_focus_areas() -> None:
    ctx = _ctx()
    raw = [
        {
            "title": "First area",
            "description": "Claims P2C1.1.1 + P2C1.1.2.",
            "involved_subcap_ids": ["P2C1.1.1", "P2C1.1.2"],
        },
        {
            "title": "Second area — claims overlap",
            "description": "Tries to re-claim P2C1.1.1.",
            "involved_subcap_ids": ["P2C1.1.1", "P2C2.1.1", "P4C1.1.1"],
        },
    ]
    out = _validate_and_dedupe(raw, ctx.all_subcap_ids)
    # First area keeps both. Second area has P2C1.1.1 stripped (already
    # claimed) — leaving P2C2.1.1 + P4C1.1.1 (still 2, so it survives).
    assert out[0].involved_subcap_ids == ["P2C1.1.1", "P2C1.1.2"]
    assert out[1].involved_subcap_ids == ["P2C2.1.1", "P4C1.1.1"]


def test_validator_caps_at_5_areas() -> None:
    valid = {f"P{p}C1.1.1" for p in range(1, 8)} | {f"P{p}C1.1.2" for p in range(1, 8)}
    raw = [
        {"title": f"Area {i}", "description": f"Cluster {i}",
         "involved_subcap_ids": [f"P{i}C1.1.1", f"P{i}C1.1.2"]}
        for i in range(1, 8)
    ]
    out = _validate_and_dedupe(raw, valid)
    assert len(out) == 5


def test_match_recommendations_attaches_overlap_only() -> None:
    ctx = _ctx()
    areas = [
        SynthesizedFocusArea(
            title="Modernize CX",
            description="",
            involved_subcap_ids=["P2C1.1.1", "P2C1.1.2", "P2C2.1.1"],
        ),
        SynthesizedFocusArea(
            title="Data foundation",
            description="",
            involved_subcap_ids=["P4C1.1.1", "P4C1.1.2"],
        ),
    ]
    _match_recommendations(areas, ctx.recommendations)
    # IC-001 targets P2C1.* → matches CX area only.
    assert areas[0].matched_recommendation_ids == ["IC-001"]
    # IC-002 targets P4C1.1.1 → matches Data area only.
    assert areas[1].matched_recommendation_ids == ["IC-002"]
    # IC-003 (targets P9C9.9.9) matches neither.


def test_match_recommendations_empty_when_no_overlap() -> None:
    areas = [SynthesizedFocusArea(
        title="P3 ops", description="",
        involved_subcap_ids=["P3C1.1.1"],
    )]
    recs = [
        {"rec_id": "REC-X", "target_subcap_ids": ["P9C9.9.9"]},
        {"rec_id": "REC-Y", "target_subcap_ids": []},
    ]
    _match_recommendations(areas, recs)
    assert areas[0].matched_recommendation_ids == []


# ── DOCX-first lookup (2026-06 operator mandate) ───────────────────


class _FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Records the last execute call + returns canned rows."""
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        return _FakeResult(self._rows)


def test_load_existing_docx_focus_areas_returns_strategic_rows() -> None:
    """Rows tagged `docx:strategic_section` come back labeled
    `data_source='docx-strategic'` so the FE chip distinguishes them."""
    rows = [
        _FakeRow(
            title="Modernize the mortgage origination workflow",
            verbatim_quote=(
                "Modernize the mortgage origination workflow "
                "within 18 months to lift P3 efficiency."
            ),
            involved_subcap_ids=["P3C2.1.1"],
            source_path="docx:strategic_section",
        ),
        _FakeRow(
            title="Build the unified data foundation",
            verbatim_quote=(
                "Bet 1 — Build a unified data foundation across "
                "all subsidiaries by 2028 (P4C1.1.1)."
            ),
            involved_subcap_ids=["P4C1.1.1"],
            source_path="docx:strategic_section",
        ),
    ]
    session = _FakeSession(rows)
    areas = asyncio.run(_load_existing_docx_focus_areas(
        session, run_id="r-1",
    ))
    assert len(areas) == 2
    assert areas[0].title.startswith("Modernize")
    assert areas[0].data_source == "docx-strategic"
    assert areas[1].involved_subcap_ids == ["P4C1.1.1"]
    # SQL filters out synthesized rows.
    sql_text = session.calls[0][0]
    assert "NOT LIKE 'synthesized:%'" in sql_text


def test_load_existing_docx_focus_areas_returns_findings_rows() -> None:
    """Rows from the Top Findings extractor (DOCX path-based source_path)
    come back labeled `data_source='docx'`."""
    rows = [
        _FakeRow(
            title="Branch network reach",
            verbatim_quote=(
                "Branch network spans 14 locations across NY-NJ. Loan "
                "growth +8% YoY (P3C1.2.1)."
            ),
            involved_subcap_ids=["P3C1.2.1"],
            source_path="04_reports/Foo_Client_Profile.docx",
        ),
    ]
    session = _FakeSession(rows)
    areas = asyncio.run(_load_existing_docx_focus_areas(
        session, run_id="r-1",
    ))
    assert len(areas) == 1
    assert areas[0].data_source == "docx"


def test_load_existing_docx_focus_areas_empty_when_none_persisted() -> None:
    session = _FakeSession([])
    areas = asyncio.run(_load_existing_docx_focus_areas(
        session, run_id="r-1",
    ))
    assert areas == []
