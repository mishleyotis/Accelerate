"""Focus-area grounding / pillars_weight / financial_ref / KPI derivation
(Part 6.1 — migration 052 producers in focus_area_synthesizer).

Pure-helper tests: the audit measured synthesized focus rows grounding on
GENERATED paragraphs (page NULL, no E-IDs), a FE count-share pillars
proxy, and a 100%-manual KPI strip. These pin the deterministic engine
that fixes each defect.
"""
from __future__ import annotations

from app.services.focus_area_synthesizer import (
    _grounding_is_unhygienic,
    build_grounding,
    build_linked_insights,
    clean_representative_quote,
    compute_pillars_weight,
    derive_focus_area_kpis,
    deterministic_grounding_eids,
    extract_inline_eids,
    find_financial_ref,
    grounding_eid_supported,
    humanize_focus_title,
    kpi_current_disclosed,
    kpi_delta_label,
    kpi_fa_key,
    kpi_target_consistent,
    mine_disclosed_kpis,
    significant_tokens,
)


class TestPillarsWeight:
    def test_tier_weighted_share_sums_to_100(self) -> None:
        weights = compute_pillars_weight(
            ["P1C1.1.1", "P2C1.1.1", "P2C3.2.1"],
            {"P1C1.1.1": "T1", "P2C1.1.1": "T2", "P2C3.2.1": "T3"},
        )
        assert weights is not None
        assert sum(weights.values()) == 100
        # T1 (1.0) vs T2+T3 (1.25) → P2 leads.
        assert weights["P2"] > weights["P1"]

    def test_single_pillar_cluster_is_100(self) -> None:
        assert compute_pillars_weight(["P4C1.1.1", "P4C2.1.1"], {}) == {"P4": 100}

    def test_no_parsable_ids_returns_none(self) -> None:
        assert compute_pillars_weight(["weird-id"], {}) is None

    def test_unknown_tier_defaults_mid_weight(self) -> None:
        weights = compute_pillars_weight(
            ["P1C1.1.1", "P3C1.1.1"], {"P1C1.1.1": "T9"},
        )
        assert weights == {"P1": 50, "P3": 50}


class TestBuildGrounding:
    def test_mines_verbatim_quote_and_orders_eids(self) -> None:
        grounding = build_grounding(
            subcap_ids=["P1C1.1.1", "P1C1.1.2"],
            rationale_by_subcap={
                "P1C1.1.1": (
                    "Scored 3.1 on evidence E-022 and E-024: ANB Plaza "
                    "innovation and the Q2 Stablecore partnership signal a "
                    "multi-year digital direction across 115 branches."
                ),
            },
            evidence_by_subcap={
                "P1C1.1.1": [
                    {"e_id": "E-022", "excerpt": "Announced a $12M innovation budget for 2025.", "tier": 1},
                    {"e_id": "E-024", "excerpt": "", "tier": 3},
                ],
                "P1C1.1.2": [
                    {"e_id": "E-022", "excerpt": "dup id must not repeat", "tier": 1},
                ],
            },
            source_kind="heuristic",
        )
        assert grounding["source_kind"] == "heuristic"
        assert grounding["evidence_e_ids"] == ["E-022", "E-024"]
        # The representative quote is a VERBATIM substring of a source text.
        assert grounding["representative_quote"] is not None
        assert "Stablecore" in grounding["representative_quote"]

    def test_no_sources_yields_null_quote_not_fabrication(self) -> None:
        grounding = build_grounding(
            subcap_ids=["P1C1.1.1"], rationale_by_subcap={},
            evidence_by_subcap={}, source_kind="gemini",
        )
        assert grounding["representative_quote"] is None
        assert grounding["evidence_e_ids"] == []


class TestFinancialRef:
    def test_matches_highlight_by_label_tokens(self) -> None:
        ref = find_financial_ref(
            "Total assets grew to $52.2B in 2025",
            ["Total Assets ($B): 52.2 (2025)", "EPS ($): 9.17 (2025)"],
        )
        assert ref == "Total Assets ($B): 52.2 (2025)"

    def test_no_metrics_in_fa_text_returns_none(self) -> None:
        assert find_financial_ref(
            "Modernize the member experience",
            ["Total Assets ($B): 52.2 (2025)"],
        ) is None

    def test_no_highlights_returns_none(self) -> None:
        assert find_financial_ref("assets of $1.2B", []) is None


class TestDeriveKpis:
    def test_transition_yields_current_target_delta(self) -> None:
        kpis = derive_focus_area_kpis(
            ["Our loan cycle runs 12 days → 4 days once automated."],
        )
        assert kpis, "arrow transition must yield a KPI"
        kpi = kpis[0]
        assert kpi["source_mode"] == "public"
        assert kpi["current_value"] == "12 days"
        assert kpi["target_value"] == "4 days"
        assert kpi["delta"] == "-67%"

    def test_labelled_single_metric_is_current_only(self) -> None:
        kpis = derive_focus_area_kpis(["STP rate 18% today across channels."])
        assert kpis
        assert kpis[0]["current_value"] == "18%"
        assert kpis[0]["target_value"] is None

    def test_unlabelled_and_tiny_counts_are_dropped(self) -> None:
        # "5 members" (generic small count) must not become a KPI row.
        assert derive_focus_area_kpis(["serving 5 members at the branch"]) == []

    def test_no_numbers_no_rows(self) -> None:
        assert derive_focus_area_kpis(["Unify the customer data platform."]) == []

    def test_dedupes_labels_and_caps_rows(self) -> None:
        kpis = derive_focus_area_kpis(
            ["STP rate 18%.", "STP rate 18%.",
             "efficiency ratio 66.7%", "mobile adoption 44%",
             "digital share 21%"],
        )
        labels = [k["kpi_label"].lower() for k in kpis]
        assert len(labels) == len(set(labels))
        assert len(kpis) <= 3


class TestKpiFaKey:
    def test_uuid_becomes_32_char_hex(self) -> None:
        key = kpi_fa_key("3b241101-e2bb-4255-8caf-4136c566a962")
        assert key == "3b241101e2bb42558caf4136c566a962"
        assert len(key) == 32

    def test_non_uuid_truncates_to_32(self) -> None:
        assert kpi_fa_key("FA-01") == "FA-01"
        assert len(kpi_fa_key("x" * 60)) == 32

    def test_stable_roundtrip_read_write(self) -> None:
        raw = "3B241101-E2BB-4255-8CAF-4136C566A962"
        assert kpi_fa_key(raw) == kpi_fa_key(raw.lower())


class TestTitleAndQuoteHygiene:
    """2026-07 depth stress-test pins: no bare finding-ID titles; no raw
    table-row dumps as representative quotes; inline [E-###] citations
    always land in evidence_e_ids."""

    ROW_DUMP = (
        "F-002 | 🎯🎯 15,531 Well-Architected issues (9,700 P1, 56% "
        "low-effort) = $2.6-7.2M tractable services roadmap | Hubbl "
        "Diagnostics scan 2025-08-29 [E-286]: 62% P1 issues, Custom Code "
        "7,926 + Data Model 3,988"
    )

    def test_extract_inline_eids_all_shapes(self) -> None:
        assert extract_inline_eids(
            "No HubSpot [E-093]. Facet [E-018:F1]; internal [E-INT-002].",
        ) == ["E-093", "E-018", "E-INT-002"]
        assert extract_inline_eids("no citations here") == []

    def test_bare_finding_id_title_is_humanized(self) -> None:
        title = humanize_focus_title("F-002", self.ROW_DUMP)
        assert not title.startswith("F-002")
        assert len(title) >= 8
        # Derived from the finding's own headline cell.
        assert "issues" in title.lower() or "well-architected" in title.lower()

    def test_healthy_title_passes_through(self) -> None:
        assert humanize_focus_title(
            "Modernize member experience", self.ROW_DUMP,
        ) == "Modernize member experience"

    def test_bare_id_with_no_text_is_labelled_not_bare(self) -> None:
        import re
        title = humanize_focus_title("F-004", "")
        assert not re.match(r"^F-\d+$", title)

    def test_clean_quote_drops_id_cell_and_is_not_the_dump(self) -> None:
        quote = clean_representative_quote(self.ROW_DUMP)
        assert quote is not None
        assert not quote.startswith("F-002")
        assert " | " not in quote
        assert "🎯" not in quote

    def test_grounding_merges_inline_eids_from_texts(self) -> None:
        grounding = build_grounding(
            subcap_ids=["P1C1.1.1"],
            rationale_by_subcap={"P1C1.1.1": self.ROW_DUMP},
            evidence_by_subcap={"P1C1.1.1": [
                {"e_id": "E-001", "excerpt": "linked item", "tier": 2},
            ]},
            source_kind="docx",
        )
        # Inline citation from the finding text outranks the linked id.
        assert grounding["evidence_e_ids"][0] == "E-286"
        assert "E-001" in grounding["evidence_e_ids"]
        # The quote is cleaned, never the raw dump.
        rq = grounding["representative_quote"]
        assert rq is not None and " | " not in rq

    def test_unhygienic_detector(self) -> None:
        assert _grounding_is_unhygienic(None)
        # ANY bracketed citation markup in the quote needs repair —
        # post-fix quotes are prose (real E-IDs live in evidence_e_ids),
        # incl. malformed "[E-P4C4]" / "[E-{Juel}]" variants.
        assert _grounding_is_unhygienic(
            {"representative_quote": "cites [E-093] inline", "evidence_e_ids": []},
        )
        assert _grounding_is_unhygienic(
            {"representative_quote": "AWS/Azure migration [E-P4C4]",
             "evidence_e_ids": []},
        )
        assert _grounding_is_unhygienic(
            {"representative_quote": "F-002 | raw | dump", "evidence_e_ids": ["E-1"]},
        )
        assert not _grounding_is_unhygienic(
            {"representative_quote": "a clean sentence with 42 branches.",
             "evidence_e_ids": []},
        )
        # EMPTY grounding anchors nothing — repair (the all-94 rendered
        # sweep found 46 clients shipping heuristic rows in this state).
        assert _grounding_is_unhygienic(
            {"representative_quote": None, "evidence_e_ids": [],
             "source_kind": "heuristic"},
        )
        # …but quote-less rows that DO carry E-ID anchors are grounded.
        assert not _grounding_is_unhygienic(
            {"representative_quote": None, "evidence_e_ids": ["E-101"],
             "source_kind": "heuristic"},
        )

    def test_finalized_quotes_carry_no_citation_markup(self) -> None:
        grounding = build_grounding(
            subcap_ids=["P1C1.1.1"],
            rationale_by_subcap={"P1C1.1.1": (
                "Cloud-native Fusion Phoenix migration completed across "
                "AWS/Azure regions in 2025 [E-P4C4] with 42 branches live."
            )},
            evidence_by_subcap={},
            source_kind="heuristic",
        )
        rq = grounding["representative_quote"]
        assert rq is not None
        assert "[E-" not in rq
        assert "Fusion Phoenix" in rq


class TestKpiEvidenceTrace:
    """Migration 055 (2026-07-06): every derived KPI carries the E-ID of
    the evidence block its number was read from — drawer-traceable."""

    def test_tuple_attached_eid_inherited(self) -> None:
        kpis = derive_focus_area_kpis(
            [("Our loan cycle runs 12 days → 4 days once automated.", "E-062")],
        )
        assert kpis and kpis[0]["evidence_e_id"] == "E-062"

    def test_inline_citation_wins_over_attached_eid(self) -> None:
        kpis = derive_focus_area_kpis(
            [("STP rate 18% today across channels [E-014].", "E-062")],
        )
        assert kpis and kpis[0]["evidence_e_id"] == "E-014"

    def test_plain_string_block_yields_honest_none(self) -> None:
        kpis = derive_focus_area_kpis(
            ["STP rate 18% today across channels."],
        )
        assert kpis and kpis[0]["evidence_e_id"] is None


# ═══ Focus-enrichment wave (056): grounding fill, KPI reasoning, linking ═══


class TestSignificantTokens:
    def test_drops_stopwords_and_short_tokens(self) -> None:
        toks = significant_tokens("The bank will modernize loan origination")
        # 'the','will','bank' (FSI filler) dropped; content kept.
        assert "modernize" in toks and "origination" in toks and "loan" in toks
        assert "the" not in toks and "bank" not in toks


class TestGroundingValidator:
    def test_relevant_excerpt_supported(self) -> None:
        assert grounding_eid_supported(
            "Modernize the loan origination workflow decisioning speed",
            "Loan origination workflow now decisions in under 3 days",
        )

    def test_off_topic_excerpt_rejected(self) -> None:
        # < 3 shared significant tokens → the id does NOT ground the FA.
        assert not grounding_eid_supported(
            "Modernize the loan origination workflow",
            "The cafeteria refreshed its lunch menu on Tuesday",
        )


class TestDeterministicGroundingFallback:
    def test_ranks_top_overlap_above_floor(self) -> None:
        evidence = [
            ("E-1", "loan origination workflow automation speeds decisioning"),
            ("E-2", "an unrelated cafeteria lunch note"),
            ("E-3", "origination workflow cycle time for a loan"),
        ]
        got = deterministic_grounding_eids(
            "modernize loan origination workflow", evidence)
        assert got == ["E-1", "E-3"]           # E-2 below the floor, dropped

    def test_no_overlap_returns_empty_not_fabrication(self) -> None:
        assert deterministic_grounding_eids(
            "modernize loan origination",
            [("E-9", "the parking lot was repaved")]) == []


class TestKpiReasoningValidators:
    def test_current_must_be_disclosed(self) -> None:
        assert kpi_current_disclosed("18%", ["STP sits at 18% today"])
        # fabricated current — number absent from every cited excerpt.
        assert not kpi_current_disclosed("99%", ["STP sits at 18% today"])
        assert not kpi_current_disclosed("no number here", ["STP 18%"])

    def test_target_consistent_with_stated_value(self) -> None:
        assert kpi_target_consistent(
            "12 days", "4 days", ["automation cuts the cycle to 4 days"])

    def test_target_consistent_with_uplift_percent(self) -> None:
        # 100 → 130 is +30%, which the rec states.
        assert kpi_target_consistent(
            "100", "130", ["nCino drives a +30% uplift in STP"])

    def test_target_mismatch_rejected(self) -> None:
        # 12 → 2 days is -83%; the rec only states a 10% trim → reject.
        assert not kpi_target_consistent(
            "12 days", "2 days", ["automation trims cycle time 10%"])

    def test_delta_label_signed_percent(self) -> None:
        assert kpi_delta_label("12 days", "4 days") == "-67%"
        assert kpi_delta_label("18%", None or "") is None


class TestMineDisclosedKpisTopicalBinding:
    def test_only_topically_bound_excerpts_seed_kpis(self) -> None:
        fa_text = "Improve straight-through processing for digital lending"
        pairs = [
            # shares ≥2 significant tokens (processing/lending/straight) → kept
            ("E-1", "Straight-through processing for lending sits at 18%."),
            # off-topic (cafeteria) → its number never seeds a KPI
            ("E-2", "The cafeteria served 4200 lunches this quarter."),
        ]
        got = mine_disclosed_kpis(fa_text, pairs)
        assert got, "a topically-bound disclosed KPI must be mined"
        assert all(k["e_id"] == "E-1" for k in got)


_LI_CARDS = [
    {"id": "c1", "ic_id": "IC-1", "title": "No CRM blocks Member 360",
     "severity": "high", "what_text": "Salesforce gap across branches.",
     "linked_subcap_id": "P2C1.1.1", "affects": ["P4C3.1.1"],
     "linked_e_ids": ["E-9", "E-7"]},
    {"id": "c2", "ic_id": "IC-2", "title": "Cafeteria remodel",
     "severity": "low", "what_text": "Unrelated facilities note.",
     "linked_subcap_id": "P9C9.9.9", "affects": [],
     "linked_e_ids": ["E-100"]},
]


class TestBuildLinkedInsights:
    def test_subcap_and_cocitation_bases(self) -> None:
        li = build_linked_insights(
            fa_subcap_ids=["P2C1.1.1"], fa_evidence_e_ids=["E-9"],
            fa_text="modernize member experience crm", insight_cards=_LI_CARDS)
        assert len(li) == 1                   # c2 shares nothing → dropped
        row = li[0]
        assert row["ic_id"] == "IC-1"
        kinds = {b["kind"] for b in row["bases"]}
        assert "subcap" in kinds and "co_citation" in kinds
        assert row["e_ids"] == ["E-9"]        # the shared citation
        assert row["source"] == "deterministic"

    def test_prose_only_link(self) -> None:
        # No subcap/evidence overlap, but the FA text shares ≥3 content
        # tokens with the card title+what → prose basis carries the link.
        li = build_linked_insights(
            fa_subcap_ids=["P1C1.1.1"], fa_evidence_e_ids=[],
            fa_text="salesforce crm gap across branches member",
            insight_cards=[_LI_CARDS[0]])
        assert len(li) == 1
        assert [b["kind"] for b in li[0]["bases"]] == ["prose"]

    def test_no_basis_no_link(self) -> None:
        assert build_linked_insights(
            fa_subcap_ids=["P3C3.3.3"], fa_evidence_e_ids=["E-50"],
            fa_text="totally distinct subject matter here",
            insight_cards=[_LI_CARDS[1]]) == []
