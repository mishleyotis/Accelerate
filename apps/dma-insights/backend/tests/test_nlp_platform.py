"""Shared NLP platform (`app/services/nlp/`) — unit tests, no DB.

Every module gets direct coverage plus the regression cases lifted
straight from the 2026-06 QA audits: the "Q3 2025" quarter anchor, the
"NEGATIVE SEARCH RESULT" negation miss, the 213-char mid-word title cut,
the JavaScript/Various tech-stack noise rows, the [2022, 2025] →
[2023, 87.5] year-series harvest, and the "(: 1.68" SCQA artifact.

Both tiers are exercised: the spaCy path (model installed in this env)
and the regex fallback via the ``degraded`` fixture, which simulates a
failed model load — the toolkit must keep working, never raise.
"""
from __future__ import annotations

from datetime import date

import pytest

import app.services.nlp as nlp_pkg
from app.services.nlp import (
    LexicalIndex,
    NlpToolkit,
    causal,
    dates,
    entities,
    get_nlp,
    patterns,
    polarity,
    quality,
    quantities,
    quotes,
    segment,
    similarity,
    taxonomy,
    titlecraft,
)

# --- fixtures -------------------------------------------------------------


@pytest.fixture()
def degraded(monkeypatch: pytest.MonkeyPatch):
    """Simulate a failed spaCy load — every function must fall back to regex."""
    monkeypatch.setattr(nlp_pkg, "_NLP", None)
    monkeypatch.setattr(nlp_pkg, "_LOAD_ATTEMPTED", True)
    monkeypatch.setattr(nlp_pkg, "NLP_DEGRADED", True)


@pytest.fixture()
def clean_registry():
    patterns.reset()
    yield
    patterns.reset()


# --- facade / singleton ---------------------------------------------------


def test_get_nlp_is_a_singleton() -> None:
    first = get_nlp()
    second = get_nlp()
    assert first is second
    assert first is not None  # model installed in this environment
    assert nlp_pkg.is_degraded() is False


def test_degraded_flag_and_regex_tier_never_raise(degraded) -> None:
    assert nlp_pkg.is_degraded() is True
    assert get_nlp() is None
    # Every prose function still works on its regex tier.
    assert segment.sentences("One. Two.") == ["One.", "Two."]
    assert entities.extract("Jane Doe, CTO joined Acme Bank Corp. in 2024")["titles"]
    assert titlecraft.make_title("P1C1.1.1: Core migration completed in 2024")


def test_toolkit_facade_delegates_to_module_functions() -> None:
    toolkit = NlpToolkit()
    assert toolkit.sentences("A one. B two.") == ["A one.", "B two."]
    assert toolkit.resolve_event_date("Q3 2025") == (date(2025, 8, 1), "quarter")
    assert toolkit.classify("nCino")["kind"] == "platform"
    assert toolkit.degraded is False
    assert toolkit.LexicalIndex is LexicalIndex


# --- segment ---------------------------------------------------------------


def test_sentences_basic_split() -> None:
    out = segment.sentences("The bank grew. Deposits rose 4%. Margins held.")
    assert out == ["The bank grew.", "Deposits rose 4%.", "Margins held."]


def test_sentences_empty_input() -> None:
    assert segment.sentences("") == []
    assert segment.sentences("   ") == []


def test_sentences_regex_tier_abbreviation_guard(degraded) -> None:
    out = segment.sentences("Fiserv Inc. runs the core. The bank uses Q2 e.g. daily.")
    assert out[0] == "Fiserv Inc. runs the core."
    assert len(out) == 2


def test_clip_sentences_never_cuts_mid_sentence() -> None:
    text = "First sentence here. Second sentence follows. Third one closes."
    out = segment.clip_sentences(text, 50)
    assert out == "First sentence here. Second sentence follows."


def test_clip_sentences_appends_nothing_and_never_cuts_mid_word() -> None:
    text = "Enterprise modernization programme spanning fourteen distinct workstreams"
    out = segment.clip_sentences(text, 30)
    assert "…" not in out and "..." not in out
    assert len(out) <= 30
    # Every emitted word is a whole word from the source.
    assert all(w in text.split() for w in out.split())


def test_clip_sentences_returns_short_text_unchanged() -> None:
    assert segment.clip_sentences("Short.", 100) == "Short."
    assert segment.clip_sentences("anything", 0) == ""


def test_clip_excerpt_verbatim_drops_whole_sentences_with_ellipsis() -> None:
    text = ("Assets grew from $2.286B in 2021 to $3.209B in 2025. "
            "Deposits rose 9%. Margins held.")
    out = segment.clip_excerpt_verbatim(text, 60)
    # First sentence intact — numbers/qualifiers never cut mid-claim;
    # the dropped tail is marked with an ellipsis.
    assert out == "Assets grew from $2.286B in 2021 to $3.209B in 2025. …"


def test_clip_excerpt_verbatim_keeps_oversize_first_sentence_whole() -> None:
    # Even when the FIRST sentence exceeds the budget it ships whole:
    # an over-budget verbatim claim beats a truncated one.
    text = ("Net income increased from $164.9 million in 2022 to $268.5 "
            "million in 2024 while the efficiency ratio improved.")
    out = segment.clip_excerpt_verbatim(text, 40)
    assert out.startswith("Net income increased from $164.9 million")
    assert "$268.5" in out            # the claim's second number survives
    assert not out.endswith("…")      # nothing was dropped — no marker


def test_clip_excerpt_verbatim_short_text_unchanged() -> None:
    assert segment.clip_excerpt_verbatim("Short.", 100) == "Short."
    assert segment.clip_excerpt_verbatim("", 100) == ""
    assert "…" not in segment.clip_excerpt_verbatim("One. Two.", 100)


# ── clip_quote (2026-07-06 verbatim-quote mandate) ──────────────────────────
# Quoted evidence must stay verbatim: truncation lands on a sentence/word
# boundary, an ellipsis marks it, and a number is never stranded from its
# unit/qualifier (a mid-claim cut changes what the evidence says).


def test_clip_quote_fits_returns_verbatim_no_ellipsis() -> None:
    text = "CFTC ordered a $20M penalty in 2023."
    assert segment.clip_quote(text, 100) == text


def test_clip_quote_sentence_boundary_truncation_gets_ellipsis() -> None:
    text = ("FINRA censured the firm for complaint-reporting failures. "
            "A remediation certification is due within 180 days of the AWC.")
    out = segment.clip_quote(text, 70)
    assert out == "FINRA censured the firm for complaint-reporting failures. …"
    # the kept span is verbatim source text
    assert out.rstrip(" …") in text


def test_clip_quote_word_boundary_truncation_gets_ellipsis() -> None:
    text = ("Enterprise modernization programme spanning fourteen distinct "
            "workstreams across the retail bank")
    out = segment.clip_quote(text, 40)
    assert out.endswith("…")
    body = out.rstrip("…").rstrip()
    assert body and all(w in text.split() for w in body.split())


def test_clip_quote_never_strands_a_number_mid_claim() -> None:
    # A cut right after "$20" (dropping "million penalty") would change
    # the claim — the clip must retreat past the number.
    text = "The CFTC ordered the firm to pay a penalty of $20 million to settle"
    for budget in range(20, len(text)):
        out = segment.clip_quote(text, budget)
        body = out.rstrip("…").rstrip()
        assert not body or not body.split()[-1].lstrip("$€£~≈<>").replace(
            ",", "").replace(".", "").isdigit(), (budget, out)


def test_clip_quote_empty_and_zero_budget() -> None:
    assert segment.clip_quote("", 50) == ""
    assert segment.clip_quote("anything", 0) == ""


def test_clauses_split_on_semicolons_and_connectives() -> None:
    out = segment.clauses(
        "The bank grew deposits; however, margins compressed because rates fell."
    )
    assert len(out) >= 2
    assert all(c.strip() for c in out)
    assert any("rates fell" in c for c in out)


def test_clauses_regex_tier(degraded) -> None:
    out = segment.clauses("Deposits grew 4%, but efficiency lagged; costs rose.")
    assert len(out) == 3


# --- entities ---------------------------------------------------------------


def test_extract_person_and_title_via_apposition() -> None:
    out = entities.extract("Jane Doe, CTO of Acme Bank, launched the program.")
    assert any(p["norm"] == "Jane Doe" for p in out["persons"])
    assert any(t["norm"] == "CTO" for t in out["titles"])


def test_extract_money_norms_to_float_usd() -> None:
    out = entities.extract("Revenue of $2.4M against a $9B market and $2,400,000 spend.")
    norms = [m["norm"] for m in out["money"]]
    assert 2_400_000.0 in norms
    assert 9_000_000_000.0 in norms
    assert norms.count(2_400_000.0) == 2


def test_extract_percent_norm_signed() -> None:
    out = entities.extract("Growth of +23.8% against -3% attrition.")
    norms = {p["norm"] for p in out["percents"]}
    assert 23.8 in norms
    assert -3.0 in norms


def test_extract_dates_carry_iso_norm() -> None:
    out = entities.extract("The migration completed on March 12, 2025.")
    assert any(d["norm"] == "2025-03-12" for d in out["dates"])


def test_extract_chief_star_officer_title_canonicalized() -> None:
    out = entities.extract("She serves as Chief Risk Officer for the group.")
    assert any(t["norm"] == "CRO" for t in out["titles"])


def test_extract_offsets_point_back_into_text() -> None:
    text = "Jane Doe, CTO, cut costs by 12% ($3.5M) in 2024."
    out = entities.extract(text)
    for family in out.values():
        for item in family:
            assert text[item["start"] : item["end"]] == item["text"]


def test_extract_empty_returns_all_keys() -> None:
    out = entities.extract("")
    assert set(out) == {"persons", "orgs", "titles", "money", "percents", "dates", "cardinals"}
    assert all(v == [] for v in out.values())


def test_extract_regex_tier_orgs_and_cardinals(degraded) -> None:
    out = entities.extract("Acme Bank partnered with Fiserv Inc. across 905 branches.")
    assert any("Acme Bank" in o["text"] for o in out["orgs"])
    assert any(c["norm"] == 905.0 for c in out["cardinals"])


# --- dates ------------------------------------------------------------------


def test_resolve_full_date_day_precision() -> None:
    assert dates.resolve_event_date("Announced March 12, 2025 at the summit") == (
        date(2025, 3, 12),
        "day",
    )
    assert dates.resolve_event_date("effective 2024-11-03") == (date(2024, 11, 3), "day")


def test_resolve_month_precision() -> None:
    assert dates.resolve_event_date("completed in March 2025") == (date(2025, 3, 1), "month")


def test_resolve_quarter_regression_q3_2025_middle_month() -> None:
    # Audit regression: "Q3 2025" must anchor on the quarter's MIDDLE month.
    assert dates.resolve_event_date("Q3 2025") == (date(2025, 8, 1), "quarter")
    assert dates.resolve_event_date("targeted for Q1 2026") == (date(2026, 2, 1), "quarter")


def test_resolve_fiscal_and_bare_year() -> None:
    assert dates.resolve_event_date("FY2024 results") == (date(2024, 7, 1), "year")
    assert dates.resolve_event_date("expected in 2025") == (date(2025, 7, 1), "year")


def test_resolve_early_mid_late_year() -> None:
    assert dates.resolve_event_date("early 2025") == (date(2025, 2, 15), "year")
    assert dates.resolve_event_date("mid-2025") == (date(2025, 6, 15), "year")
    assert dates.resolve_event_date("late 2025") == (date(2025, 10, 15), "year")


def test_resolve_publish_fallback_is_last_resort() -> None:
    published = date(2026, 1, 15)
    assert dates.resolve_event_date("no dates here", published) == (
        published,
        "publish_fallback",
    )
    # Textual evidence always wins over publish_date.
    assert dates.resolve_event_date("in March 2025", published) == (date(2025, 3, 1), "month")


def test_resolve_none_when_undated_and_unpublished() -> None:
    assert dates.resolve_event_date("no temporal signal") == (None, "none")
    assert dates.resolve_event_date("") == (None, "none")


def test_windows_by_quarter() -> None:
    out = dates.extract_windows("The core migration must complete by Q2 2026.")
    assert out == [
        {"kind": "quarter", "text": "by Q2 2026", "date": date(2026, 5, 1), "months": None}
    ]


def test_windows_within_months_clock() -> None:
    out = dates.extract_windows("The consent order requires remediation within 18 months.")
    assert out[0]["kind"] == "clock"
    assert out[0]["months"] == 18
    assert dates.extract_windows("within 2 years")[0]["months"] == 24


def test_windows_deadline_cues() -> None:
    golive = dates.extract_windows("Branch consolidation go-live is targeted for March 2026.")
    assert golive[0]["kind"] == "deadline"
    assert golive[0]["date"] == date(2026, 3, 1)

    closes = dates.extract_windows("The RFP closes on March 12, 2026.")
    assert closes[0] == {
        "kind": "deadline",
        "text": "The RFP closes on March 12, 2026.",
        "date": date(2026, 3, 12),
        "months": None,
    }

    completion = dates.extract_windows("Target completion is Q4 2025 per the roadmap.")
    assert completion[0]["kind"] == "deadline"
    assert completion[0]["date"] == date(2025, 11, 1)

    deadline = dates.extract_windows("The regulatory deadline has not been disclosed.")
    assert deadline[0]["kind"] == "deadline"
    assert deadline[0]["date"] is None


def test_windows_empty() -> None:
    assert dates.extract_windows("Nothing time-bound here.") == []
    assert dates.extract_windows("") == []


# --- quantities ---------------------------------------------------------------


def test_metrics_money_with_growth_companion() -> None:
    # Audit regression: "$2.35B (+23.8%)" is one usd metric + one pct change.
    out = quantities.extract_metrics("$2.35B revenue (+23.8%)")
    usd = next(m for m in out if m["unit"] == "usd")
    pct = next(m for m in out if m["unit"] == "pct")
    assert usd["value"] == 2_350_000_000.0
    assert usd["metric"] == "revenue"
    assert pct["value"] == 23.8
    assert pct["direction"] == "up"


def test_metrics_cagr_with_period() -> None:
    out = quantities.extract_metrics("CAGR ~35% (2021–2024)")  # noqa: RUF001
    assert out[0]["metric"] == "CAGR"
    assert out[0]["value"] == 35.0
    assert out[0]["unit"] == "pct"
    assert out[0]["period"] == "2021–2024"  # noqa: RUF001


def test_metrics_efficiency_ratio_pct() -> None:
    out = quantities.extract_metrics("efficiency ratio 58.20%")
    assert out[0]["metric"] == "efficiency ratio"
    assert out[0]["value"] == 58.2
    assert out[0]["unit"] == "pct"


def test_metrics_cycle_time_improvement() -> None:
    out = quantities.extract_metrics("loan cycle 12 days → 4 days")
    assert out[0]["metric"] == "loan cycle"
    assert out[0]["value"] == 4.0
    assert out[0]["unit"] == "days"
    assert out[0]["direction"] == "improvement"
    assert out[0]["raw"] == "12 days → 4 days"


def test_metrics_stars_below_peer() -> None:
    out = quantities.extract_metrics("0.8 stars below peer median")
    assert out[0]["value"] == 0.8
    assert out[0]["unit"] == "stars"
    assert out[0]["direction"] == "down"


def test_metrics_counts() -> None:
    out = quantities.extract_metrics("905 branches and 1,800 users")
    by_metric = {m["metric"]: m for m in out}
    assert by_metric["branches"]["value"] == 905.0
    assert by_metric["branches"]["unit"] == "count"
    assert by_metric["users"]["value"] == 1800.0


def test_metrics_empty() -> None:
    assert quantities.extract_metrics("") == []
    assert quantities.extract_metrics("no numbers at all") == []


def test_year_series_never_harvests_years_from_value_prose() -> None:
    # THE audit bug class: a VALUE mentioning FY2024-FY2025 must yield nothing.
    pairs = [("Net Income Growth", "7.0% | Net Income Growth (FY2024–FY2025)")]  # noqa: RUF001
    assert quantities.extract_year_series(pairs) == {}
    # Same guard for raw strings.
    assert quantities.extract_year_series("7.0% | Net Income Growth (FY2024–FY2025)") == {}  # noqa: RUF001


def test_year_series_accepts_standalone_year_keys() -> None:
    out = quantities.extract_year_series({"FY2023": "87.5", "2024": "$1.2B"})
    assert out == {2023: 87.5, 2024: 1_200_000_000.0}


def test_year_series_string_rows_and_range_rejection() -> None:
    out = quantities.extract_year_series("2022: 1.1\n2023: 1.4\n2021–2024")  # noqa: RUF001
    assert out == {2022: 1.1, 2023: 1.4}  # "2021-2024" is a range label, not a point


def test_year_series_rejects_year_valued_pairs() -> None:
    assert quantities.extract_year_series({"2023": 2024}) == {}
    assert quantities.extract_year_series({"2023": 87.5}) == {2023: 87.5}


# --- causal ---------------------------------------------------------------


def test_decompose_because_splits_what_why() -> None:
    out = causal.decompose("Loan approval times lag peers because underwriting remains manual.")
    assert out["what"] == "Loan approval times lag peers."
    assert out["why"] == "Underwriting remains manual."
    assert out["so_what"] == ""


def test_decompose_driven_by_regression() -> None:
    out = causal.decompose(
        "Deposit growth slowed to 2.1%, driven by rate competition from digital banks."
    )
    assert out["what"] == "Deposit growth slowed to 2.1%."
    assert out["why"] == "Rate competition from digital banks."


def test_decompose_routes_actions_to_so_what() -> None:
    out = causal.decompose(
        "Efficiency trails the cohort. The bank should deploy nCino to automate credit workflows."
    )
    assert out["what"] == "Efficiency trails the cohort."
    assert "should deploy nCino" in out["so_what"]


def test_decompose_is_non_destructive_verbatim() -> None:
    text = "Attrition rose 14% because two regional banks poached staff."
    out = causal.decompose(text)
    assert "14%" in out["what"]
    # Verbatim words survive; only the leading letter is sentence-cased.
    assert out["why"] == "Two regional banks poached staff."


def test_decompose_empty_blocks_are_empty_strings() -> None:
    out = causal.decompose("")
    assert out == {"what": "", "why": "", "so_what": ""}


# --- polarity ---------------------------------------------------------------


NEGATIVE_SEARCH = (
    "NEGATIVE SEARCH RESULT: No formal enforcement orders were identified "
    "for the bank as of March 2025."
)


def test_negative_search_regression_is_absence_not_event() -> None:
    # Audit regression: this row rendered as a red regulatory EVENT.
    assert polarity.is_negated_absence(NEGATIVE_SEARCH) is True
    assert polarity.is_event(NEGATIVE_SEARCH) is False


def test_negated_absence_variants() -> None:
    for text in (
        "no evidence of a core modernization program",
        "The CISO is NOT NAMED in any public source.",
        "no formal enforcement actions on record",
        "absence of any public API strategy",
        "no record of prior Salesforce usage",
        "The bank is not party to the consent order.",
        "no publicly named data leadership",
        "INTERNAL ALTERNATIVE — homegrown CRM in use",
        "We could not identify a digital banking vendor.",
        "None identified in the review period.",
    ):
        assert polarity.is_negated_absence(text) is True, text
    assert polarity.is_negated_absence("The bank named a new CTO.") is False


def test_signal_polarity_lexicon() -> None:
    assert polarity.signal("The credit union launched a record partnership program.") == "positive"
    assert polarity.signal("Regulators fined the bank after a data breach.") == "negative"
    assert polarity.signal("The bank operates twelve locations in Ohio.") == "neutral"


def test_signal_negated_absence_of_bad_thing_is_clean_standing() -> None:
    assert polarity.signal(NEGATIVE_SEARCH) == "positive"


def test_signal_regulatory_resolution_is_positive_clean_standing() -> None:
    # 2026-07 pack audit: 12 consent-order RESOLUTION events across 8 clients
    # rendered signal='negative'. 'consent order + resolution verb' is a
    # positive clean-standing signal.
    for text in (
        "Federal Reserve System has terminated a consent order requiring it "
        "to fix deficiencies in BSA/AML compliance",
        "OCC consent order for mortgage servicing remediated — 91/95 items "
        "completed, order terminated, $1.6M borrower payments made",
        "Regions Bank fully resolved 2022 CFPB Consent Order on overdraft "
        "fees (July 2025 termination, $50M penalty paid)",
        "CFPB Consent Order FULLY RESOLVED July 2025 per E-001",
        "The 2019 written agreement with the Federal Reserve was lifted",
    ):
        assert polarity.signal(text) == "positive", text


def test_signal_resolution_requires_a_completed_verb() -> None:
    # ISSUED orders / open obligations must stay negative — 'requiring
    # remediation' is not 'remediated'.
    for text in (
        "OCC issued a consent order in February 2024 requiring remediation "
        "within 18 months",
        "Fined $4.5M under an AML consent order announced December 2024",
        "The consent order has not been terminated as of the 2025 exam",
    ):
        assert polarity.signal(text) == "negative", text


def test_signal_background_regulatory_context_does_not_taint_a_hire() -> None:
    # 2026-07 pack audit (bank-of-utah verbatim): compliance/risk hires made
    # AFTER a consent order read negative from the context phrase alone.
    for text in (
        "VP Compliance Manager (Sept 2025) hired AFTER consent order (Feb "
        "2024) — likely remediation-driven hire to strengthen compliance "
        "function",
        "SVP Strategic Risk Officer (July 2024) hired 5 months after consent "
        "order — risk governance response to enforcement action",
    ):
        assert polarity.signal(text) == "positive", text


def test_absence_covers_no_actions_database_phrasing() -> None:
    # 2026-07 pack audit (apg-federal verbatim): 'NO actions' wasn't covered.
    text = ("NCUA Enforcement Actions database search: NO actions, consent "
            "orders, or prohibitions found — clean regulatory record")
    assert polarity.is_negated_absence(text) is True
    assert polarity.signal(text) == "positive"
    assert polarity.is_event(text) is False


def test_court_appointed_is_not_a_positive_appointment() -> None:
    assert polarity.signal(
        "Stevens (court-appointed administrator) + class refiled lawsuit "
        "in N.D.N.Y. with stronger evidence"
    ) == "negative"


def test_is_event_true_for_dated_occurrence() -> None:
    assert polarity.is_event("Acme Bank launched its new digital platform in March 2025.")
    assert polarity.is_event("The company acquired Riverstone Insurance in Q2 2024.")


def test_is_event_false_for_baselines_and_obligations() -> None:
    assert not polarity.is_event(
        "The bank must maintain BSA/AML compliance under the 2023 consent order."
    )


def test_is_event_false_for_hypotheticals_and_analyst_notes() -> None:
    assert not polarity.is_event("The platform would enable faster onboarding in 2026.")
    assert not polarity.is_event("We believe the bank migrated its core in 2024.")


def test_is_event_false_when_undated_or_negated() -> None:
    assert not polarity.is_event("The bank launched a new app.")  # no date
    assert not polarity.is_event("The bank has not launched a mobile app as of 2025.")


# --- similarity ---------------------------------------------------------------


def test_lexical_index_top_k_ranks_relevant_doc_first() -> None:
    index = LexicalIndex()
    index.fit([
        ("crm", "Salesforce CRM deployment across retail branches"),
        ("data", "Databricks lakehouse for analytics workloads"),
        ("hr", "Employee onboarding handbook policies"),
    ])
    hits = index.top_k("CRM deployed in branches", k=2)
    assert hits and hits[0][0] == "crm"
    assert hits[0][1] > 0.3


def test_lexical_index_min_score_filters_noise() -> None:
    index = LexicalIndex()
    index.fit([("a", "Salesforce CRM deployment"), ("b", "Databricks lakehouse")])
    assert index.top_k("zzz unrelated query qqq", k=5) == []


def test_lexical_index_empty_corpus_is_safe() -> None:
    index = LexicalIndex()
    index.fit([])
    assert index.top_k("anything", k=3) == []


def test_similarity_degrades_when_scikit_learn_absent(monkeypatch) -> None:
    """The SHIPPED-image scenario: scikit-learn not installed. `fit`,
    `top_k` and `near_duplicates` must DEGRADE (return []), never raise —
    otherwise derive_context / link_evidence_subcaps / derive_insights /
    ingest hard-fail in prod (audit 2026-07-03). Simulated by forcing the
    sklearn import to raise inside _build_matrix."""
    import builtins
    real_import = builtins.__import__

    def _no_sklearn(name, *a, **k):
        if name.startswith("sklearn"):
            raise ModuleNotFoundError("No module named 'sklearn'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_sklearn)
    idx = LexicalIndex()
    idx.fit([("s1", "Fiserv DNA core banking platform"),
             ("s2", "Salesforce Financial Services Cloud CRM")])
    assert idx.top_k("core banking", k=2) == []          # no crash
    assert similarity.near_duplicates(["a core system",
                                       "a core system too"]) == []


def test_near_duplicates_finds_reworded_pair() -> None:
    pairs = similarity.near_duplicates([
        "Bank launched mobile app in March",
        "The bank launched its mobile app in March",
        "Quarterly dividend increased",
    ])
    assert [(i, j) for i, j, _score in pairs] == [(0, 1)]
    assert pairs[0][2] >= 0.85


def test_near_duplicates_trivial_inputs() -> None:
    assert similarity.near_duplicates([]) == []
    assert similarity.near_duplicates(["only one"]) == []


def test_near_duplicates_key_extractor() -> None:
    items = [{"title": "Core migration completed in 2024"},
             {"title": "Core migration completed in 2024"},
             {"title": "New CFO appointed"}]
    pairs = similarity.near_duplicates(items, key=lambda d: d["title"])
    assert [(i, j) for i, j, _s in pairs] == [(0, 1)]


# --- titlecraft ---------------------------------------------------------------

LONG_EXCERPT = (
    "Salesforce ecosystem deployment: FSC as core CRM across 905 branches; "
    "Marketing Cloud for campaign orchestration; MuleSoft integration layer "
    "connecting legacy systems; Tableau dashboards for executive reporting [E-214]"
)


def test_make_title_213_char_regression_no_mid_word_cut() -> None:
    title = titlecraft.make_title(LONG_EXCERPT)
    assert len(title) <= 60
    assert "[E-" not in title
    body = title.rstrip("…")
    # Every word is complete — the last token is a whole source word.
    assert body.split()[-1] in LONG_EXCERPT.split()


def test_make_title_strips_subcap_and_allcaps_prefixes() -> None:
    title = titlecraft.make_title(
        "P3C2.1.4: NEGATIVE SEARCH RESULT: No formal enforcement orders identified"
    )
    assert not title.startswith("P3C2")
    assert "NEGATIVE SEARCH" not in title
    assert title.startswith("No formal enforcement")


def test_make_title_svo_compression() -> None:
    title = titlecraft.make_title(
        "The bank hired Jane Doe as Chief Technology Officer in March 2025 to "
        "lead the modernization program across all four regions."
    )
    assert len(title) <= 60
    assert "hired" in title


def test_make_title_short_excerpt_untruncated() -> None:
    title = titlecraft.make_title("Core migration completed. Second phase begins.")
    assert title == "Core migration completed"
    assert "…" not in title


def test_make_title_empty() -> None:
    assert titlecraft.make_title("") == ""
    assert titlecraft.make_title("   ") == ""


# --- quotes ---------------------------------------------------------------


QUOTE_TEXT = (
    'The CEO said "we will migrate all 905 branches to the new core by 2026" during '
    "the call. Efficiency ratio reached 58.2% in Q3 2025, ahead of the cohort median. "
    "Is this sustainable? Fine."
)


def test_mine_quotes_pulls_quoted_span_verbatim() -> None:
    out = quotes.mine_quotes(QUOTE_TEXT, source_path="report.docx", page=12)
    assert {"quote": "we will migrate all 905 branches to the new core by 2026",
            "page": 12, "source_path": "report.docx"} in out


def test_mine_quotes_includes_salient_declaratives_only() -> None:
    out = quotes.mine_quotes(QUOTE_TEXT)
    joined = [q["quote"] for q in out]
    assert any("58.2%" in q for q in joined)
    assert not any(q.endswith("?") for q in joined)  # questions excluded
    assert not any(q == "Fine." for q in joined)  # too short / not salient


def test_mine_quotes_are_verbatim_substrings() -> None:
    for item in quotes.mine_quotes(QUOTE_TEXT, source_path="x", page=1):
        assert item["quote"] in QUOTE_TEXT


def test_mine_quotes_empty() -> None:
    assert quotes.mine_quotes("") == []


# --- taxonomy ---------------------------------------------------------------


def test_classify_javascript_is_engineering_signal() -> None:
    assert taxonomy.classify("JavaScript")["kind"] == "engineering_signal"


def test_classify_various_is_noise() -> None:
    assert taxonomy.classify("Various")["kind"] == "noise"


def test_classify_ncino_is_platform() -> None:
    out = taxonomy.classify("nCino")
    assert out["kind"] == "platform"
    assert out["canonical"] == "nCino"
    assert out["vendor"] == "nCino"
    assert out["confidence"] == 1.0


def test_split_cell_language_dump_regression() -> None:
    parts = taxonomy.split_cell("Angular, React, Java, Python, NodeJS, PHP, .NET")
    assert len(parts) == 7
    assert all(taxonomy.classify(p)["kind"] == "engineering_signal" for p in parts)


def test_classify_os_family() -> None:
    assert taxonomy.classify("Windows Server 2019")["kind"] == "engineering_signal"
    assert taxonomy.classify("macOS")["kind"] == "engineering_signal"
    assert taxonomy.classify("Linux")["kind"] == "engineering_signal"


def test_classify_generic_labels_are_noise() -> None:
    for label in ("CRM", "Core Banking", "Unspecified Vendor", "Analytics/BI",
                  "Security", "Payments", "Internal", "Mobile App"):
        assert taxonomy.classify(label)["kind"] == "noise", label


def test_classify_prose_guards() -> None:
    prose = ("Salesforce ecosystem deployment: FSC as core CRM across 905 branches "
             "with Marketing Cloud for campaign orchestration")
    assert taxonomy.classify(prose)["kind"] == "noise"  # len > 60
    assert taxonomy.classify("Jane Smith, CTO")["kind"] == "noise"  # person+title
    assert taxonomy.classify("2024")["kind"] == "noise"  # bare date
    assert taxonomy.classify("Vendor: unknown per latest scan")["kind"] == "noise"


def test_classify_alias_resolution() -> None:
    fsc = taxonomy.classify("FSC")
    assert (fsc["canonical"], fsc["vendor"]) == ("Financial Services Cloud", "Salesforce")
    assert taxonomy.classify("Jack Henry & Associates")["canonical"] == "Jack Henry"
    assert taxonomy.classify("Episys")["vendor"] == "Jack Henry"
    assert taxonomy.classify("GCP")["canonical"] == "Google Cloud"
    assert taxonomy.classify("Azure AD")["canonical"] == "Microsoft Entra ID"


def test_classify_fuzzy_match_over_90() -> None:
    out = taxonomy.classify("Salesorce")  # misspelled
    assert out["kind"] == "platform"
    assert out["canonical"] == "Salesforce"
    assert 0.9 <= out["confidence"] < 1.0


def test_classify_unknown_vendor_is_kept_not_dropped() -> None:
    out = taxonomy.classify("Quantum Metric")
    assert out["kind"] == "unknown_vendor"
    assert out["vendor"] == "Quantum Metric"
    assert out["confidence"] < 0.5


def test_classify_layer_hints() -> None:
    assert taxonomy.classify("Fiserv")["layer_hint"] == "foundation"
    assert taxonomy.classify("Power BI")["layer_hint"] == "intelligence"
    assert taxonomy.classify("MuleSoft")["layer_hint"] == "platform"
    assert taxonomy.classify("Q2")["layer_hint"] == "application"


def test_split_cell_strips_parentheticals_and_plus() -> None:
    parts = taxonomy.split_cell("Salesforce (FSC since 2021), nCino; Databricks + Tableau")
    assert parts == ["Salesforce", "nCino", "Databricks", "Tableau"]
    assert taxonomy.split_cell("") == []


# --- patterns ---------------------------------------------------------------


def test_register_and_match_by_headers(clean_registry) -> None:
    patterns.register({"headers": ["e_id", "tier", "claim_type"]}, "evidence_csv")
    key, confidence = patterns.match_artifact(
        "evidence_index.csv", headers=["E_ID", "Tier", "Claim_Type", "Extra"]
    )
    assert key == "evidence_csv"
    assert confidence == 1.0


def test_match_by_filename_and_keys(clean_registry) -> None:
    patterns.register(
        {"filename_regex": r"peer_scores_.*\.json", "keys": ["peer_median"]}, "peer_json"
    )
    key, confidence = patterns.match_artifact(
        "/pkg/01_evidence/peer_scores_banks.json", keys=["peer_median", "cohort"]
    )
    assert (key, confidence) == ("peer_json", 1.0)


def test_match_below_threshold_returns_none_with_confidence(clean_registry) -> None:
    patterns.register({"headers": ["alpha", "beta", "gamma", "delta"]}, "abcd")
    key, confidence = patterns.match_artifact("whatever.csv", headers=["alpha"])
    assert key is None
    assert 0.0 < confidence < 0.5


def test_register_rejects_empty_fingerprint(clean_registry) -> None:
    with pytest.raises(ValueError):
        patterns.register({}, "nothing")
    with pytest.raises(ValueError):
        patterns.register({"headers": ["a"]}, "")


def test_record_pattern_gap_appends_structured_entry() -> None:
    warnings: list = []
    entry = patterns.record_pattern_gap(warnings, "odd_file.xlsx", "no fingerprint matched")
    assert warnings == [entry]
    assert entry["code"] == "PATTERN_GAP"
    assert entry["path"] == "odd_file.xlsx"
    assert entry["reason"] == "no fingerprint matched"
    assert entry["recorded_at"]  # ISO timestamp present


# --- quality ---------------------------------------------------------------


GOOD_NARRATIVE = (
    "Acme Bank's efficiency ratio of 58.2% trails the 52% peer median [E-101]. "
    "Deposit costs rose 40 bps in Q3 2025 [E-102]. "
    "The bank should deploy Salesforce FSC to consolidate onboarding."
)


def test_rubric_passes_specific_grounded_actionable_prose() -> None:
    out = quality.rubric_score(GOOD_NARRATIVE, evidence_ids=("E-101", "E-102"))
    assert out["pass"] is True
    assert all(v >= 0.5 for v in out["scores"].values())
    assert not any(f.startswith("filler:") for f in out["flags"])


def test_rubric_filler_blacklist_fails_the_gate() -> None:
    out = quality.rubric_score(
        "This points to meaningful room and a binding constraint on growth."
    )
    assert out["pass"] is False
    assert any(f.startswith("filler:") for f in out["flags"])
    assert out["scores"]["filler"] < 1.0


def test_rubric_flags_out_of_scope_citations() -> None:
    out = quality.rubric_score(
        "Deposits rose 4% [E-999]. The bank should expand.", evidence_ids=("E-101",)
    )
    assert "unknown_evidence_id:E-999" in out["flags"]


def test_rubric_coherence_checks_numbers_against_scope() -> None:
    out = quality.rubric_score(
        "The efficiency ratio is 58.2%. It should improve.", numbers_in_scope=(95.0,)
    )
    assert out["scores"]["coherence"] < 0.5
    assert any(f.startswith("incoherent_number:") for f in out["flags"])
    within = quality.rubric_score(
        "The efficiency ratio is 58.2%. It should improve.", numbers_in_scope=(58.0,)
    )
    assert within["scores"]["coherence"] == 1.0


def test_rubric_requires_actionability() -> None:
    out = quality.rubric_score("Assets total $4.2B across 905 branches [E-3].",
                               evidence_ids=("E-3",))
    assert out["scores"]["actionability"] == 0.0
    assert "no_action" in out["flags"]
    assert out["pass"] is False


def test_markdown_lint_catches_paren_colon_artifact_regression() -> None:
    flags = quality.markdown_lint("Scores (: 1.68 versus peers.")
    assert "paren_colon_artifact" in flags


def test_markdown_lint_artifact_flags() -> None:
    flags = quality.markdown_lint("Leaked ::F1 marker and text ## not a heading.  Two spaces **odd")
    assert "f_marker_leak" in flags
    assert "stray_heading_mid_text" in flags
    assert "double_space" in flags
    assert "unbalanced_emphasis" in flags


def test_markdown_lint_bullet_dump_and_length() -> None:
    dump = "\n".join(f"- item {i}" for i in range(10))
    assert any(f.startswith("bullet_dump:") for f in quality.markdown_lint(dump))
    assert any(f.startswith("too_long:") for f in quality.markdown_lint("x" * 4001))


def test_markdown_lint_clean_text_and_real_headings_pass() -> None:
    assert quality.markdown_lint("## Heading\n\nOne paragraph. **Bold** works.") == []
    assert quality.markdown_lint("") == []


# ── extract_metric_year_pairs (2026-07-04 evidence-mining refinement) ──────

class TestExtractMetricYearPairs:
    def test_thousands_denominated_with_paren_date_and_vs_form(self):
        from app.services.nlp.quantities import extract_metric_year_pairs
        t = ("Total assets $9,066,879K (Dec 31, 2024); net loans $5,399,147K. "
             "Net income $34.9M (2024) vs $50.3M (2023) — 30.6% decline.")
        got = extract_metric_year_pairs(t, entity_name="AAFCU")
        assert got["total_assets"][2024] == 9_066_879_000.0
        # nearest-keyword binding: the assets value is NOT credited to net income
        assert got["net_income"] == {2024: 34.9e6, 2023: 50.3e6}

    def test_date_first_line_and_from_to_prose(self):
        from app.services.nlp.quantities import extract_metric_year_pairs
        t = ("Sep 30, 2025 NCUA data: 46 branches, ~$9.24B total assets.\n"
             "Total assets grew from $2.286B in 2021 to $3.209B in 2025.")
        got = extract_metric_year_pairs(t)
        assert got["total_assets"][2025] in (9.24e9, 3.209e9)
        assert got["total_assets"][2021] == 2.286e9

    def test_peer_institution_lines_are_excluded(self):
        from app.services.nlp.quantities import extract_metric_year_pairs
        t = "Wings Credit Union: total assets $9.6B in 2024, 371,000+ members."
        assert extract_metric_year_pairs(t, entity_name="Frost Bank") == {}
        # …but the entity's OWN line (name token overlap) is kept
        t2 = "Frost Bank total assets $53.0B in 2024 and $50.1B in 2023."
        got = extract_metric_year_pairs(t2, entity_name="Frost Bank")
        assert got["total_assets"] == {2024: 53.0e9, 2023: 50.1e9}

    def test_magnitude_cluster_drops_mixed_sources(self):
        from app.services.nlp.quantities import extract_metric_year_pairs
        # a $34.9M figure sneaking into a $9B assets series is a different
        # statement — the cluster filter keeps the dominant magnitude
        t = ("total assets $9.1B in 2024; total assets $9.4B in 2025; "
             "total assets $34.9M in 2020")
        got = extract_metric_year_pairs(t)
        assert 2020 not in got["total_assets"]
        assert set(got["total_assets"]) == {2024, 2025}


def test_absence_gate_clean_verification_conventions() -> None:
    """2026-07-13 UFCU sample vetting: researcher clean-verification notes
    became timeline EVENTS and then a false live-order why-now signal."""
    from app.services.nlp.polarity import is_negated_absence
    assert is_negated_absence(
        "VALIDATED CLEAN (Jun 2026): United Federal Credit Union does NOT "
        "appear in NCUA Administrative Orders / Prohibitions for 2025-2026, "
        "and no UFCU-specific data breach appears in current breach trackers.")
    assert is_negated_absence(
        "No UFCU-specific Salesforce/CRM posting indexed on Dice")
    # real events must not trip the gate
    assert not is_negated_absence(
        "Synchrony completed its acquisition of Ally Lending on March 4, 2024.")
    assert not is_negated_absence(
        "The OCC issued a consent order requiring remediation within 18 months.")


def test_clause_shaped_finding_name_never_spliced() -> None:
    from app.services.startup_enrich import finding_wwsw
    r = finding_wwsw(
        "Proven in-app personalization, but no enterprise journey orchestration",
        "Engagement tripled via the composable dashboard; no journey platform "
        "is publicly named and engagement remains campaign/manual,",
        "P2C4.5.1", 2.0, 3.0)
    for field in ("why", "so_what"):
        assert "personalization, but no enterprise" not in r[field], field
    # the mid-clause trailing comma is healed into a sentence end
    assert not r["what"].rstrip().endswith(",")
