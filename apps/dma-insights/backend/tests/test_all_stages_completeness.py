"""Pure-logic contract tests for the all-stages self-healing layer.

Covers the deterministic pieces (no DB): subvertical classification, the
recommendation effort-band inference, and the render-auditor strict-mode
emptiness promotion. The end-to-end gate (inject emptiness → verify exits 1 →
heal → exits 0) and idempotency are exercised against live PG in the deploy
harness; these keep the logic honest in CI without a database.
"""
from __future__ import annotations

import re
import typing

from app.scripts.deepen_narrative import (
    _compose_insight,
    _deep_card,
    _pct,
    _plain,
    _usd,
    _valid_insight,
    set_insight_explainer,
)
from app.scripts.derive_financials import _extract as _fin_extract
from app.scripts.derive_financials import _ratio, _year_series
from app.scripts.derive_peers import _name_tokens, _parse_peer, _prefix
from app.scripts.derive_recommendations import _effort_band
from app.scripts.derive_sentiment import _extract
from app.scripts.qa_render_validation import (
    _STRICT_REQUIRED,
    _validate_insights,
    _validate_platforms,
    _validate_roadmap,
)
from app.services.completeness_contract import _SURFACE_GAP_SQL, scrub_insight_jargon
from app.services.entity_healing import (
    _clean_hq_for_prose,
    _clean_reg_for_prose,
    classify_subvertical,
    compose_about_narrative,
)
from app.services.parsers.package_persist import _recency_months


class TestClassifySubvertical:
    def test_explicit_sv_code_wins(self):
        assert classify_subvertical("Whatever", "classified SV6 Asset Management") == "AM"
        assert classify_subvertical("X", "SV2 Credit Unions only") == "CU"

    def test_name_keywords(self):
        assert classify_subvertical("Consumers Credit Union", "") == "CU"
        assert classify_subvertical("Elliott Investment Management", "") == "AM"
        assert classify_subvertical("Vornado Realty Trust", "") == "AM"  # REIT → AM
        assert classify_subvertical("Travel Insurance International", "") == "IC"
        assert classify_subvertical("Interactive Brokers", "") == "RIA"
        assert classify_subvertical("Payments Canada", "") == "CIB"
        assert classify_subvertical("Frost Bank", "") == "RB"

    def test_package_text_when_name_ambiguous(self):
        # name alone is not classifiable; the package classification carries it
        assert classify_subvertical("CI Financials", "Subvertical Name: Asset Management") == "AM"
        assert classify_subvertical("IMA Financial Group", "insurance broker / brokerage") == "IB"

    def test_no_guess_returns_none(self):
        assert classify_subvertical("Acme Widgets", "") is None


class TestComposeAboutNarrative:
    """The grounded "About" narrative composer (entity_healing): every clause is
    a stored fact, it always clears the 120-char contract floor, and it never
    emits parse-junk (a bad regulator / dict-string HQ is dropped, not printed)."""

    def test_core_facts_clear_the_120_floor(self):
        # Worst case: long name but ONLY name + subvertical + scale + regulator
        # + maturity (no headcount/branches/members/founded).
        n = compose_about_narrative(
            name="Wintrust Financial Corporation", subvertical="RB",
            aum_usd=71_100_000_000.0, aum_basis="total_assets",
            regulator="Federal Reserve", headcount=None, facts={}, overall=2.93, hq="",
        )
        assert n and len(n) >= 120
        assert "Wintrust Financial Corporation is a regional bank." in n
        assert "$71.1 billion in total assets" in n
        assert "regulated by Federal Reserve" in n
        assert "2.9 out of 5" in n

    def test_junk_regulator_is_dropped(self):
        # Sunflower's primary_regulator parsed as the literal "Role" — must NOT
        # appear; the paragraph still clears the floor on the other facts.
        n = compose_about_narrative(
            name="Sunflower Bank, N.A.", subvertical="RB", aum_usd=20_400_000_000.0,
            aum_basis="total_assets", regulator="Role", headcount=2500,
            facts={"founded": "1892", "branches": "73"}, overall=1.93, hq="",
        )
        assert n and "Role" not in n
        assert "regulated by" not in n  # no clean regulator available
        assert "employs approximately 2,500 people across 73 branches" in n
        assert "has operated since 1892" in n

    def test_credit_union_uses_members(self):
        n = compose_about_narrative(
            name="Langley Federal Credit Union", subvertical="CU",
            aum_usd=5_600_000_000.0, aum_basis="total_assets",
            regulator="NCUA, GCU is member-owned with operations", headcount=None,
            facts={"members": "402059", "branches": "20"}, overall=2.5, hq="",
        )
        assert n and "credit union" in n
        assert "serves approximately 402,059 members through 20 branches" in n
        assert "regulated by NCUA" in n  # trailing prose trimmed

    def test_dict_string_hq_is_skipped(self):
        n = compose_about_narrative(
            name="PenderFund Capital Management Ltd.", subvertical="AM",
            aum_usd=3_000_000_000.0, aum_basis="aum", regulator="BCSC", headcount=51,
            facts={"founded": "2003"}, overall=1.52, hq="{'address': 'Suite 1830'}",
        )
        assert n and "headquartered in" not in n
        assert "assets under management" in n

    def test_clean_city_state_hq_is_used(self):
        n = compose_about_narrative(
            name="Cathay Bank", subvertical="RB", aum_usd=24_230_000_000.0,
            aum_basis="total_assets", regulator="FDIC (state-chartered, FDIC-insured)",
            headcount=None, facts={"branches": "60"}, overall=1.73, hq="Los Angeles, CA",
        )
        assert n and "headquartered in Los Angeles, CA" in n
        assert "regulated by FDIC" in n  # parenthetical kept only when balanced+short

    def test_no_name_returns_none(self):
        assert compose_about_narrative(
            name="", subvertical="RB", aum_usd=1e9, aum_basis="total_assets",
            regulator="FDIC", headcount=10, facts={}, overall=2.0,
        ) is None

    def test_reg_cleaner_drops_dangling_paren_and_junk(self):
        assert _clean_reg_for_prose("FDIC (state-chartered, FDIC-insured, non-Fed)") == "FDIC"
        assert _clean_reg_for_prose("NCUA, GCU is member-owned") == "NCUA"
        assert _clean_reg_for_prose("FDIC + CA DFPI (dual)") == "FDIC"
        assert _clean_reg_for_prose("Role") is None
        assert _clean_reg_for_prose("N/A") is None
        assert _clean_reg_for_prose("OSC (Ontario Securities Commission)") == \
            "OSC (Ontario Securities Commission)"

    def test_hq_cleaner_accepts_only_city_state(self):
        assert _clean_hq_for_prose("Los Angeles, CA") == "Los Angeles, CA"
        assert _clean_hq_for_prose("Sun Prairie, Wisconsin") == "Sun Prairie, Wisconsin"
        assert _clean_hq_for_prose("National FOM (effective Jan 2, 2026); HQ: NY") is None
        assert _clean_hq_for_prose("{'address': 'x'}") is None
        assert _clean_hq_for_prose("2605 Washington Blvd, Ogden, UT 84401") is None


class TestEffortBand:
    def test_gap_to_band(self):
        assert _effort_band(2.0) == "LARGE"
        assert _effort_band(1.0) == "MEDIUM"
        assert _effort_band(0.3) == "SMALL"


class TestNarrativeDepth:
    def test_usd_compact(self):
        assert _usd(10_230_000_000) == "$10.2B"
        assert _usd(529_000_000_000) == "$529.0B"
        assert _usd(3_000_000) == "$3M"
        assert _usd(None) is None

    def test_pct(self):
        assert _pct(1.52) == "1.52%"
        assert _pct(None) is None

    def test_shallow_why_now_is_gated(self):
        # the anti-one-liner gate must exist and require full-sentence signals
        sql = _SURFACE_GAP_SQL["why_now_depth"]
        assert "jsonb_array_length" in sql and "< 60" in sql and "< 3" in sql


class TestInsightCardDepthAndJargon:
    def test_plain_strips_codes_and_consultant_speak(self):
        dirty = ("Financial Wellness Scoring (P2C4) scores 1.6, a priority lever for the "
                 "pillar's maturity and its cross-pillar dependencies; see E-025_CF_P3C3.")
        clean = _plain(dirty)
        for bad in ("P2C4", "P3C3", "E-025", "priority lever", "the pillar", "cross-pillar"):
            assert bad not in clean, f"{bad!r} survived sanitisation: {clean!r}"

    def test_deep_card_is_thorough_and_jargon_free(self):
        what, why, sowhat = _deep_card(
            "Exchange Bank", "Financial Wellness Scoring", "P2", 1.6, 2.5, "")
        # no one-/two-liners
        assert len(what) >= 160 and len(why) >= 100 and len(sowhat) >= 100
        blob = " ".join((what, why, sowhat))
        # grounded + plain-language
        assert "out of 5" in what
        assert "Exchange Bank" in what and "Financial Wellness Scoring" in what
        assert not re.search(r"P[1-4]C\d", blob)
        for bad in ("m5", "the pillar", "peer-cohort", "priority lever", "cross-pillar", "subcap"):
            assert bad not in blob.lower(), f"jargon {bad!r} leaked: {blob!r}"

    def test_deep_card_handles_missing_score_without_fabrication(self):
        what, why, sowhat = _deep_card("Acme CU", "this capability", "P3", None, None, "x")
        assert len(what) >= 120 and len(why) >= 80 and len(sowhat) >= 80
        # no invented numeric score when none is known
        assert "out of 5" not in why

    def test_insight_depth_gate_requires_both_what_and_why(self):
        sql = _SURFACE_GAP_SQL["insight_depth"]
        assert "what_text" in sql and "< 160" in sql
        assert "why_text" in sql and "< 100" in sql

    def test_insight_jargon_gate_blocks_codes_and_consultant_speak(self):
        sql = _SURFACE_GAP_SQL["insight_jargon"]
        assert "P[1-4]C[0-9]" in sql
        assert "priority lever" in sql and "the pillar" in sql and "sub-?cap" in sql


class TestInsightExplainerSeam:
    """D2.7 — `_compose_insight` routes through an injected Vertex
    explainer with a validator + TEMPLATE FALLBACK. Offline (no explainer)
    it must be byte-identical to `_deep_card`."""

    _ARGS = ("Exchange Bank", "Financial Wellness Scoring", "P2", 1.6, 2.5, "")

    def teardown_method(self):
        # never leak the global explainer into other tests
        set_insight_explainer(None)

    def test_offline_is_byte_identical_to_deep_card(self):
        set_insight_explainer(None)
        assert _compose_insight(*self._ARGS) == _deep_card(*self._ARGS)

    def test_valid_explainer_output_is_used_and_scrubbed(self):
        good = (
            "Financial Wellness Scoring is an emerging strength that the bank "
            "can build on across its retail franchise over the coming year.",
            "Investing here compounds because it underpins the customer "
            "relationships the rest of the franchise depends on.",
            "Make it a near-term focus and fund a focused programme to extend "
            "the lead before competitors close the gap.",
        )

        def _explainer(**_kw):
            return good

        set_insight_explainer(_explainer)
        what, why, sowhat = _compose_insight(*self._ARGS)
        assert what.startswith("Financial Wellness Scoring is an emerging")
        assert (what, why, sowhat) != _deep_card(*self._ARGS)

    def test_thin_explainer_output_falls_back_to_template(self):
        set_insight_explainer(lambda **_kw: ("too short", "x", "y"))
        assert _compose_insight(*self._ARGS) == _deep_card(*self._ARGS)

    def test_jargon_leaking_explainer_output_falls_back(self):
        leaky = (
            "Financial Wellness Scoring P2C4 is weak and needs the M3 maturity "
            "band lifted across every sub-cap in the portfolio this year now.",
            "It trails peers and the gap widens each quarter without action "
            "from the leadership team and the wider organisation right away.",
            "Prioritise it now and resource a programme to close the maturity "
            "gap before the next assessment cycle begins in earnest soon.",
        )
        set_insight_explainer(lambda **_kw: leaky)
        assert _compose_insight(*self._ARGS) == _deep_card(*self._ARGS)
        assert not _valid_insight(leaky)

    def test_raising_explainer_falls_back_to_template(self):
        def _boom(**_kw):
            raise RuntimeError("vertex unreachable")

        set_insight_explainer(_boom)
        assert _compose_insight(*self._ARGS) == _deep_card(*self._ARGS)


class TestSentimentExtraction:
    def test_extracts_grounded_rating_from_prose(self):
        prose = ("Employee sentiment is solid. Glassdoor shows a rating of 3.9/5 across "
                 "540 reviews and remains stable year over year.")
        out = _extract(prose)
        gd = [s for s in out if s["source"] == "Glassdoor"]
        assert gd and gd[0]["rating"] == "3.9/5"
        assert len(gd[0]["signal"]) >= 24

    def test_rejects_incidental_regulator_mention(self):
        # CFPB named only as a regulator (no rating, no opinion words) → not sentiment
        prose = ("As an OCC-chartered national bank, the firm maintains compliance "
                 "infrastructure spanning CFPB, FDIC, and Fed oversight.")
        assert not any(s["source"] == "CFPB complaints" for s in _extract(prose))

    def test_extracts_nps(self):
        prose = "Customer advocacy is strong, with a Net Promoter Score of 42 reported this year."
        nps = [s for s in _extract(prose) if s["source"] == "Net Promoter Score"]
        assert nps and nps[0]["rating"] == "42"


class TestFinancialsExtraction:
    REGIONS_TABLE = (
        "Net Income\tTotal Assets\tKey Driver\tTrend\n"
        "2020\t$0.99B\t$155.2B\tCOVID provisioning\tVariable\n"
        "2021\t$2.40B\t$162.8B\tpost-COVID peak\tPeak\n"
        "2024\t$1.77B\t$157.3B\tefficiency focus\tRecovering")

    def test_year_series_assigns_columns_by_magnitude(self):
        # net income is the smaller column even though "Total Assets" heads first
        year_ni, latest_ta = _year_series("Total Assets review. " + self.REGIONS_TABLE)
        assert year_ni[2020] == 990_000_000.0 and year_ni[2021] == 2_400_000_000.0
        assert latest_ta == "$157.3B"   # latest year, larger column, compact

    def test_full_extract_builds_chartable_series(self):
        fh = _fin_extract(self.REGIONS_TABLE)
        # year-keyed entries (drive the multi-year chart) + a total_assets metric
        assert fh["2020"] == 990_000_000.0 and fh["2024"] == 1_770_000_000.0
        assert fh["total_assets"] == "$157.3B"

    def test_ratio_word_boundaries_block_false_matches(self):
        # "ROADMAP … 5%" must NOT yield an ROA; "minimum … 3%" must NOT yield NIM
        assert _ratio("ROADMAP confirmed at 5%", r"ROAA|ROA|return on (?:average )?assets", 0.0, 5.0) is None
        assert _ratio("minimum threshold of 3%", r"NIM|net interest margin", 0.5, 8.0) is None
        # but a real mention parses
        assert _ratio("ROA of 1.52% in 2024", r"ROAA|ROA|return on (?:average )?assets", 0.0, 5.0) == 1.52

    def test_ratio_sanity_bounds_reject_outliers(self):
        assert _ratio("efficiency ratio 250%", r"efficiency ratio", 20.0, 99.0) is None

    def test_prose_sentence_form_extracts(self):
        fh = _fin_extract("The bank reported ROA of 1.10%, efficiency ratio 58.3%, "
                          "and total assets of $24.2 billion.")
        assert fh["roa_pct"] == 1.10 and fh["efficiency_ratio_pct"] == 58.3
        assert fh["total_assets"] == "$24.2B"

    def test_financials_gate_present(self):
        sql = _SURFACE_GAP_SQL["financials"]
        assert "financial_highlights" in sql and "{}" in sql


class TestRecencyMonths:
    def test_months_between_published_and_assessment(self):
        from datetime import date
        assert _recency_months(date(2023, 1, 1), date(2024, 7, 1)) == 18
        assert _recency_months(date(2024, 6, 1), date(2024, 6, 15)) == 0
        assert _recency_months(None, date(2024, 1, 1)) is None

    def test_ref_string_is_coerced_and_future_clamped(self):
        from datetime import date
        assert _recency_months(date(2022, 3, 1), "2024-03-01") == 24
        # published after the reference → clamp to 0, never negative
        assert _recency_months(date(2025, 1, 1), date(2024, 1, 1)) == 0


class TestPeerDerive:
    def test_run_id_prefix_collapses_sequence_drift(self):
        # '…-001' (package) and '…-0001' (ingested) must collide
        assert _prefix("DMA-ASM-GFCS-20260323-001") == _prefix("DMA-ASM-GFCS-20260323-0001")
        assert _prefix("DMA-ASM-ACUI-20260309-0001") == "DMA-ASM-ACUI-20260309"

    def test_name_tokens_drop_stopwords(self):
        toks = _name_tokens("Acuity, A Mutual Insurance Company")
        assert "acuity" in toks and "insurance" not in toks and "company" not in toks

    def test_parse_peer_handles_category_scores_shape(self, tmp_path):
        import json
        f = tmp_path / "peer_scores_Westfield.json"
        f.write_text(json.dumps({
            "peer_name": "Westfield Insurance Group", "role": "Scale Comparator",
            "scoring_date": "2026-03-09",
            "category_scores": {"P1C1": {"score": 3.5, "confidence": "HIGH"},
                                "P2C1": {"score": 2.5}},
            "evidence_sources": ["IBM case study"],
        }))
        p = _parse_peer(str(f))
        assert p is not None
        assert p["peer_name"] == "Westfield Insurance Group" and p["role"] == "Scale Comparator"
        assert p["category_scores"] == {"P1C1": 3.5, "P2C1": 2.5}
        assert p["overall"] == 3.0   # mean of 3.5, 2.5

    def test_parse_peer_rejects_scoreless(self, tmp_path):
        import json
        f = tmp_path / "peer_scores_empty.json"
        f.write_text(json.dumps({"peer_name": "X", "category_scores": {}}))
        assert _parse_peer(str(f)) is None


class TestRenderValidatorEmptiness:
    def test_empty_required_surfaces_flag_empty(self):
        # empty list → PARTIAL + counts.empty marker so --strict can promote
        st, _obs, counts = _validate_insights({"items": []})
        assert st == "PARTIAL" and counts.get("empty") == 1
        st, _obs, counts = _validate_platforms({"cards": []})
        assert st == "PARTIAL" and counts.get("empty") == 1
        st, _obs, counts = _validate_roadmap({"phases": []})
        assert st == "PARTIAL" and counts.get("empty") == 1

    def test_populated_surfaces_ok(self):
        st, _obs, _c = _validate_insights({"items": [{"what_text": "x"}]})
        assert st == "OK"
        st, _obs, _c = _validate_platforms({"cards": [{"platform_id": "salesforce"}]})
        assert st == "OK"

    def test_required_set_covers_synthesized_surfaces(self):
        # the surfaces we now deterministically fill must be gated
        for s in ("insights", "platforms", "recommendations", "platforms_roadmap",
                  "intelligence", "context", "heatmap"):
            assert s in _STRICT_REQUIRED


class TestInsightJargonScrub:
    """The deterministic remedy for the insight_jargon gate: output must
    never match the detector, must not fabricate facts, and must never
    shrink a floor-sitting field in prefer_fallback mode."""

    _DETECTOR = re.compile(
        r"P[1-4]C\d|\bM5\b|peer[- ]cohort|priority lever|cross[- ]pillar"
        r"|the pillar|sub-?cap",
        re.IGNORECASE,
    )
    _NAMES: typing.ClassVar[dict[str, str]] = {
        "P2C4": "Customer Experience Foundations",
        "P1C1.5.1": "API Integration Coverage",
    }

    def test_exact_subcap_code_resolves_to_catalogue_name(self):
        out = scrub_insight_jargon(
            "Coverage in P1C1.5.1 lags the market.", self._NAMES)
        assert "API Integration Coverage" in out
        assert not self._DETECTOR.search(out)

    def test_subcap_code_falls_back_to_category_prefix_name(self):
        out = scrub_insight_jargon(
            "A scoped investment lifts P2C4.1.2 outcomes.", self._NAMES)
        assert "Customer Experience Foundations" in out
        assert not self._DETECTOR.search(out)

    def test_unresolved_code_uses_neutral_fallback(self):
        out = scrub_insight_jargon("P3C3 trails peers.", {})
        assert out == "this capability trails peers."
        assert not self._DETECTOR.search(out)

    def test_consultant_speak_is_replaced_case_insensitively(self):
        src = ("Sequence the lowest-scoring SubCaps first; the Peer-Cohort "
               "view shows a Priority Lever across the pillars at M5.")
        out = scrub_insight_jargon(src, {})
        assert not self._DETECTOR.search(out)
        assert "capability areas" in out
        assert "peer group" in out.lower()
        assert "priority initiative" in out.lower()
        assert "the assessment areas" in out

    def test_real_pack_samples_come_out_clean(self):
        samples = (
            "The research report pins the maturity impact at: averages 1.3/5 "
            "across P4C3 and P2C4.",
            "Close the gap: sequence the lowest-scoring subcaps here first.",
            "A competitive maturity gap that compounds across the pillars.",
        )
        for s in samples:
            assert not self._DETECTOR.search(scrub_insight_jargon(s, self._NAMES))

    def test_idempotent(self):
        src = "P2C4 needs work across the pillars and every sub-cap."
        once = scrub_insight_jargon(src, self._NAMES)
        assert scrub_insight_jargon(once, self._NAMES) == once

    def test_prefer_fallback_never_shrinks(self):
        # every code and phrase replacement is >= its source length
        src = ("P1C1.5.1 and P2C4 lag; the sub-cap view and peer-cohort "
               "trend show a priority lever across the pillar at M5.")
        out = scrub_insight_jargon(src, self._NAMES, prefer_fallback=True)
        assert len(out) >= len(src)
        assert not self._DETECTOR.search(out)

    def test_no_numbers_invented(self):
        src = "Scores average 1.3/5 across P4C3; peers sit at 2.5."
        out = scrub_insight_jargon(src, {})
        for token in re.findall(r"\d+(?:\.\d+)?", out):
            assert token in src

    def test_evidence_anchor_spans_are_preserved_verbatim(self):
        src = ("Progress here compounds across the business "
               "[E-P1C5-003, E-Digital Strategy-012]. P2C4 lags the peers.")
        out = scrub_insight_jargon(src, self._NAMES)
        assert "[E-P1C5-003, E-Digital Strategy-012]" in out
        # prose code outside the anchor is still rewritten
        assert "P2C4 lags" not in out
        assert "Customer Experience Foundations" in out

    def test_identity_catalogue_name_is_rejected(self):
        # v7 carries a category whose name IS its code (P1C5) — using it
        # would make the scrub a no-op on exactly the rows that need it.
        out = scrub_insight_jargon("P1C5 needs work.", {"P1C5": "P1C5"})
        assert out == "this capability needs work."

    def test_jargon_bearing_catalogue_name_is_rejected(self):
        out = scrub_insight_jargon(
            "P3C2 needs work.", {"P3C2": "Cross-Pillar Analytics"})
        assert out == "this capability needs work."

    def test_detector_sql_ignores_codes_inside_anchor_spans(self):
        sql = _SURFACE_GAP_SQL["insight_jargon"]
        assert r"regexp_replace" in sql and r"\[E-[^\]]*\]" in sql
