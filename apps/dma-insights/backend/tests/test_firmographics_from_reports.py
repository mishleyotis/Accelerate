"""Firmographics come from the CLIENT RESEARCH / CLIENT PROFILE reports
(operator mandate 2026-06-10 — Clay is NOT in prod for this version),
with Gemini filling only the gaps, grounded + quote-verified.

Three contracts:

1. STRICT prose mining: a narrative can cite an ACQUIRED bank's assets
   alongside the entity's own (FNBO: "$2.2B assets" for Country Club
   Bank vs FNBO's $35B). In strict mode, disagreeing amounts yield
   NOTHING — a wrong number must never reach the panel; the field is
   left for the grounded Gemini extractor.
2. entity_profile `financials` wrapper: FNBO-style nested numerics
   ({"total_assets_2024": 30780000000, "employees": 5000}) format to
   human strings.
3. Gemini gap-fill acceptance: a field is persisted ONLY when its
   verbatim quote appears in the grounding excerpts.
"""
from __future__ import annotations

from app.scripts.enrich_corpus import _accept_firmo_fields
from app.services.parsers.client_profile import _extract_firmographics_facts
from app.services.parsers.entity_profile import _format_total_assets


def test_strict_mining_rejects_disagreeing_asset_amounts() -> None:
    text = (
        "FNBO holds $35B in assets and acquired Country Club Bank "
        "(Kansas City, $2.2B assets) in Oct 2025."
    )
    strict = _extract_firmographics_facts(text, strict=True)
    assert "total_assets" not in strict, strict
    # non-strict (legacy single-source callers) still returns something
    loose = _extract_firmographics_facts(text)
    assert "total_assets" in loose


def test_strict_mining_accepts_agreeing_amounts() -> None:
    text = "Total assets: $4.5B. The bank manages $4.5B in assets."
    strict = _extract_firmographics_facts(text, strict=True)
    assert strict.get("total_assets") == "$4.5B"


def test_financials_wrapper_numeric_formatting() -> None:
    fb = {"total_assets_2024": 30_780_000_000, "employees": 5000}
    assert _format_total_assets(fb) == "$30.8B"
    assert _format_total_assets({"total_assets": 450_000_000}) == "$450M"
    assert _format_total_assets({"total_assets": "$12.3B (est)"}) == "$12.3B (est)"


def test_gemini_fields_accepted_only_with_verbatim_quote() -> None:
    excerpts = (
        "FNBO is headquartered in Omaha, Nebraska. "
        "Total assets: $30.78B (FDIC 2024). Runs 120 branches."
    )
    out = (
        '{"total_assets": {"value": "$30.78B",'
        ' "quote": "Total assets: $30.78B (FDIC 2024)"},'
        ' "branches": {"value": "999", "quote": "fabricated line"},'
        ' "hq": {"value": "Omaha, Nebraska",'
        ' "quote": "headquartered in Omaha, Nebraska"}}'
    )
    accepted = _accept_firmo_fields(out, excerpts)
    assert accepted == {
        "total_assets": "$30.78B",
        "hq": "Omaha, Nebraska",
    }


def test_gemini_acceptance_tolerates_json_fences_and_garbage() -> None:
    excerpts = "Total assets: $1B."
    fenced = '```json\n{"total_assets": {"value": "$1B", "quote": "Total assets: $1B."}}\n```'
    assert _accept_firmo_fields(fenced, excerpts)["total_assets"] == "$1B"
    assert _accept_firmo_fields("not json at all", excerpts) == {}
    assert _accept_firmo_fields('["a","list"]', excerpts) == {}
