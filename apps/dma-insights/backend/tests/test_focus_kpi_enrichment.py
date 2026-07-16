"""Rich-context Gemini KPI enrichment for the focus-area drilldown
(services/focus_kpi_enrichment). Verifies the prompt is grounded in the FULL
per-client DMA context, that KPIs without both a baseline and a target are
rejected, the iterative re-ask on a thin set, and offline-safety — all with a
scripted stub client (no live Vertex).
"""
from __future__ import annotations

import asyncio
import json

from app.services.focus_kpi_enrichment import (
    KpiContext,
    build_kpi_prompt,
    enrich_focus_kpis,
    parse_kpis,
)


def _ctx(**kw) -> KpiContext:
    base = {
        "entity_name": "Kitsap Credit Union", "subvertical": "CU", "fa_id": "FA-03",
        "focus_title": "Digital Lending Modernization",
        "focus_quote": "Manual underwriting adds 9 days to loan decisions.",
        "focus_pillar": "P4", "focus_subcaps": ["P4C2.1.1", "P3C1.2.1"],
        "overall_score": 2.6, "pillar_scores": {"P2": 3.0, "P4": 1.9},
        "dma_narrative": "Kitsap should modernize its data foundation to unlock "
                         "faster, member-centric lending before the 2026 core "
                         "conversion locks the roadmap.",
        "deepest_gaps": ["HTAP lakehouse 1.0 vs 2.5 peer"],
        "financials_line": "$2.5B assets, +8.7% YoY", "region": "Western WA",
        "assets": "$2.5B", "regulator": "NCUA"}
    base.update(kw)
    return KpiContext(**base)


class _ScriptedClient:
    def __init__(self, responses: list) -> None:
        self._responses = responses
        self.prompts: list[str] = []
        self.calls = 0

    async def stream(self, call):
        self.prompts.append(call.prompt)
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        for i in range(0, len(r), 24):
            yield r[i:i + 24]


def test_prompt_is_grounded_in_full_client_context() -> None:
    p = build_kpi_prompt(_ctx())
    # WHO + WHERE-THEY-STAND
    assert "Kitsap Credit Union" in p and "2.60/5" in p and "NCUA" in p
    assert "Data & Technology 1.9" in p and "Customer Experience 3.0" in p
    # the DMA narrative (thesis) is handed to the model
    assert "before the 2026 core conversion" in p
    # the specific focus area + its evidence + capabilities
    assert "Digital Lending Modernization" in p
    assert "Manual underwriting adds 9 days" in p and "P4C2.1.1" in p
    # safeguards: baseline + target + anti-hallucination + schema
    assert "BASELINE" in p and "TARGET" in p and "NO HALLUCINATION" in p
    assert '"kpis"' in p


def test_parse_kpis_requires_baseline_and_target_and_dedupes() -> None:
    raw = json.dumps({"kpis": [
        {"label": "Loan decision time", "baseline": "9 days", "target": "2 days",
         "unit": "days", "rationale": "manual underwriting", "confidence": 0.8},
        {"label": "Loan decision time", "baseline": "9 days", "target": "3 days"},  # dup
        {"label": "No target here", "baseline": "50%"},                            # dropped
        {"label": "Digital adoption", "baseline": "40%", "target": "75%"},
    ]})
    out = parse_kpis(raw, _ctx())
    assert out is not None and len(out) == 2                 # dup + no-target removed
    first = out[0]
    assert first["kpi_label"] == "Loan decision time"
    assert first["current_value"] == "9 days" and first["target_value"] == "2 days"
    assert first["delta"] == "-78%"                          # 9 → 2 days
    assert {k["kpi_label"] for k in out} == {"Loan decision time", "Digital adoption"}


def test_parse_kpis_none_on_garbage() -> None:
    assert parse_kpis("not json", _ctx()) is None
    assert parse_kpis(json.dumps({"kpis": []}), _ctx()) is None
    assert parse_kpis("", _ctx()) is None


def test_enrich_reasks_when_too_few_then_succeeds() -> None:
    thin = json.dumps({"kpis": [
        {"label": "Loan decision time", "baseline": "9 days", "target": "2 days"}]})
    full = json.dumps({"kpis": [
        {"label": "Loan decision time", "baseline": "9 days", "target": "2 days"},
        {"label": "Digital adoption", "baseline": "40%", "target": "75%"},
        {"label": "Straight-through processing", "baseline": "20%", "target": "60%"}]})
    client = _ScriptedClient([thin, full])
    out = asyncio.run(enrich_focus_kpis(_ctx(min_kpis=3), client=client, max_rounds=2))
    assert out is not None and len(out) == 3
    assert "rejected" in client.prompts[1]                    # a follow-up re-ask fired


def test_enrich_is_offline_safe() -> None:
    assert asyncio.run(enrich_focus_kpis(_ctx(), client=None)) is None
    assert asyncio.run(enrich_focus_kpis(
        _ctx(), client=_ScriptedClient([RuntimeError("cold")]))) is None


# ── persisted focus-area cleanup (clean_persisted_focus_areas) ──────────────
# The read path filtered scaffolding at render, but the STORED title/quote
# stayed raw (so the KPI enricher + evidence drawer saw "2 Top Findings" /
# "F-003 | …"). These verify the salvage-or-drop + quote-clean contract via the
# pure helpers it composes (no DB).

def test_finding_row_quote_cleans_to_human_sentence() -> None:
    from app.services.focus_area_synthesizer import clean_representative_quote
    out = clean_representative_quote(
        "F-003 | Data Quality Crisis Confirmed | Internal RTM documents 26 pain points")
    assert out and not out.startswith("F-003") and "|" not in out
    assert "pain points" in out


def test_scaffolding_title_with_real_quote_is_salvageable() -> None:
    # a "2 Top Findings" row whose quote is a real finding → a headline is
    # derivable (salvage), NOT dropped.
    from app.services.focus_area_sanity import clean_focus_area
    from app.services.nlp.titlecraft import make_title
    keep, _ = clean_focus_area("2 Top Findings",
                               "Acuity runs IBM AIX on-premises as its core system", [])
    assert keep is False                                   # scaffolding title dropped by filter
    # but the quote is substantive → a headline salvages it
    quote_keep, _ = clean_focus_area(
        "Strategic priority", "Acuity runs IBM AIX on-premises as its core system", [])
    assert quote_keep is True
    assert len(make_title("Acuity runs IBM AIX on-premises as its core system")) >= 6


def test_true_scaffolding_quote_is_not_salvageable() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    # a meta/instruction quote → not a real finding → correctly unsalvageable
    quote_keep, _ = clean_focus_area(
        "Strategic priority", "Each finding includes a quantified observation.", [])
    assert quote_keep is False
