"""Unit tests for the pure enrichment helpers (app/services/startup_enrich).

Stdlib-only logic — these run without a DB and pin the deterministic,
grounded behaviour the derive scripts and the no-DB regenerator share.
"""
from __future__ import annotations

from app.services import startup_enrich as se


def test_is_person_name_accepts_real_names():
    assert se.is_person_name("Kurt MacAlpine")
    assert se.is_person_name("Marc-André Lewis")
    assert se.is_person_name("Douglas J. Jamieson")


def test_is_person_name_rejects_subcap_ids_and_junk():
    assert not se.is_person_name("P4C2.1, P4C2.2, P4C2.6")
    assert not se.is_person_name("P1C3.1.1")
    assert not se.is_person_name("-")
    assert not se.is_person_name("No confirmed CISO")
    assert not se.is_person_name("123 456")


def test_pillar_and_category():
    assert se.pillar_of("P2C1.1.2") == "P2"
    assert se.pillar_of("garbage") is None
    assert se.category_of("P4C1.2.1") == "P4C1"
    assert se.category_of("P4C1") == "P4C1"


def test_flag_from_severity():
    assert se.flag_from_severity("high") == "CRITICAL"
    assert se.flag_from_severity("medium") == "OPPORTUNITY"
    assert se.flag_from_severity("low") == "MONITOR"
    assert se.flag_from_severity(None) == "MONITOR"


def test_derive_trend():
    assert se.derive_trend({"lines": ["Classification: ACCELERATING | CAGR ~8.4%"]}) == "ACCELERATING"
    assert se.derive_trend({"lines": ["Net income stable at ~$700M"]}) == "STABLE"
    assert se.derive_trend({"lines": ["no growth signal here"]}) is None
    assert se.derive_trend({}) is None


def test_derive_cagr():
    assert se.derive_cagr({"lines": ["CAGR est. ~8.4%"]}) == 0.084
    assert se.derive_cagr({"lines": ["The 14.6% three-year CAGR outpaces peers"]}) == 0.146
    assert se.derive_cagr({"lines": ["no rate"]}) is None


def test_derive_footprint():
    fp = se.derive_footprint("Canada (primary) + United States + EMEA")
    assert fp == ["Canada", "United States", "EMEA"]
    assert se.derive_footprint("") is None
    assert se.derive_footprint(None) is None


def test_derive_branches():
    assert se.derive_branches({"lines": ["Operates 198 branches across PA"]}) == 198
    assert se.derive_branches({"lines": ["no branch count"]}) is None


def test_leadership_flags():
    f = se.leadership_flags("SVP, Chief Information Security Officer", 2, "Raj Sivarajah")
    assert f["critical_role"] and f["recent_hire"] and not f["gap_flag"]
    g = se.leadership_flags("CISO", None, "-")
    assert g["critical_role"] and g["gap_flag"] and not g["recent_hire"]
    n = se.leadership_flags("CEO", 38, "Mark Hochberg")
    assert not n["critical_role"] and not n["recent_hire"] and not n["gap_flag"]


def test_strip_boilerplate():
    s = ("Event-Driven Data Architecture scores 1.20 out of 5. Each finding "
         "includes a quantified observation, maturity implication, and Zennify "
         "solution relevance.")
    out = se.strip_boilerplate(s)
    assert "Each finding includes" not in out
    assert "Event-Driven Data Architecture scores 1.20 out of 5." in out


def test_subcap_evidence_map_and_eids_for():
    items = [{"linked_subcap_id": "P1C1", "linked_e_ids": ["E-005", "E-006"]},
             {"linked_subcap_id": "P4C1.2.1", "linked_e_ids": ["E-100"]}]
    em = se.subcap_evidence_map(items, ["growth driven, Evidence: E-002, E-003"])
    assert em["P1C1"] == ["E-005", "E-006"]
    assert "E-100" in em["P4C1"]  # leaf rolled up to its category
    assert em["__financial__"] == ["E-002", "E-003"]
    # parent-category broadening: a leaf query resolves via its P#C# category
    assert se.eids_for(["P1C1.9.9"], em) == ["E-005", "E-006"]


def test_compose_scqa_no_none_for_scoreless_finding():
    # A report-extracted finding with no numeric subcap score must NOT render the
    # literal "(None)" in the executive summary.
    firm = {"aum_usd": 7.0e9}
    findings = [{"name": "Integration Stall", "score": None, "peer_median": None},
                {"name": "Change Management Void", "score": 1.36, "peer_median": 2.5}]
    scqa = se.compose_scqa("CI Segall", firm, 2.2, "AM", findings)
    assert "(None)" not in scqa and "None" not in scqa
    assert "Integration Stall" in scqa  # name still present, just no score paren
    assert "Change Management Void (1.36 vs a peer median of 2.5)" in scqa


def test_repair_citations_collapses_leading_empty_fields_one_pass():
    # Multiple dropped leading fields must clean in ONE pass (apply runs once).
    assert se.repair_citations("BBB complaints (, Tier 3), creating") == \
        "BBB complaints (Tier 3), creating"
    assert se.repair_citations("story (, , T2, April 2025), nCino") == \
        "story (T2, April 2025), nCino"
    assert se.repair_citations("rating (, AM Best, T1) held") == \
        "rating (AM Best, T1) held"
    # a valid citation is untouched.
    assert se.repair_citations("strong (AM Best, T1) posture") == \
        "strong (AM Best, T1) posture"


def test_compose_scqa_multi_paragraph():
    firm = {"aum_usd": 2.24e11, "primary_regulator": "OSC", "headcount": 2932}
    findings = [{"name": "Event-Driven Data Architecture", "score": 1.2, "peer_median": 2.5},
                {"name": "A/B Testing", "score": 1.24, "peer_median": 2.5}]
    scqa = se.compose_scqa("CI Financial Corp.", firm, 2.0, "AM", findings)
    assert scqa.count("\n\n") >= 1 and len(scqa) >= 400
    assert "(2." not in scqa  # never the broken placeholder form
    assert "Event-Driven Data Architecture" in scqa


def test_compose_opportunity_md_and_insufficient():
    card = {"display_name": "Salesforce", "platform_id": "salesforce", "fit_score": 91,
            "pillar": "P2", "state": "READY", "addressable_subcap_ids": ["P2C1.1.1"],
            "prereq_checks": [{"label": "Customer data foundation", "status": "UNMET",
                               "current": 2.0, "threshold": 3.0}]}
    md = se.compose_opportunity_md(card)
    # S13 (user mandate): lead with the OPPORTUNITY, not the fit score — the
    # score renders as its own stat on the card, so it stays OUT of the prose.
    assert "Salesforce" in md and "91/100" not in md
    # QA-GLB-07 iron rule: the first clause is the client's outcome; the
    # vendor names itself second.
    assert "strongest fit" in md and "priorities" in md
    assert "Salesforce" not in md.split(" is where ")[0]
    assert "Customer data foundation" in md and "3.0 threshold" in md
    assert se.compose_opportunity_md({"state": "INSUFFICIENT_EVIDENCE"}) is None


def test_reparagraph():
    one = ("Sentence one is here. Sentence two follows. Third sentence. Fourth "
           "sentence here. Fifth one closes it out.")
    out = se.reparagraph(one, target=3)
    assert out.count("\n\n") >= 1


def test_reparagraph_never_breaks_inside_a_legal_name():
    # 2026-07-14 prose audit: the naive splitter treated "N.A."/"Inc." as
    # sentence ends and landed a served paragraph break MID-NAME
    # ("EverBank, N.A.¶¶can put TCFD Alignment first").
    one = ("The assessment says EverBank, N.A. can put TCFD Alignment first "
           "and hold the line on governance. Guaranteed Rate, Inc. runs the "
           "origination stack on legacy tooling today. The peer set holds a "
           "meaningful lead on data foundations. Closing that spread is the "
           "next phase's core work. The register carries two open items.")
    out = se.reparagraph(one, target=3)
    assert out.count("\n\n") >= 1
    for para in out.split("\n\n"):
        p = para.strip()
        assert not p.startswith(("can put", "runs the")), out
        assert not p.endswith(("N.A.", "Inc.")), out


def test_finding_headline_first_sentence_survives_abbreviations():
    # The regenerated headline clips the WHAT's first sentence with the
    # guarded splitter — an "Inc." must not truncate it mid-name.
    head = se.finding_headline(
        "Tiffany Smith (CSO) quoted", "P2C1.1.1", 2.0, 3.0,
        what=("Guaranteed Rate, Inc. still routes lead scoring through "
              "manual spreadsheets. The peer set automated this in 2024."))
    assert "Inc" not in head or "routes" in head  # not cut at "Inc."
    assert "spreadsheets" in head or head.startswith("The ")


def test_ensure_why_now_depth_pads_thin_entity_to_floor():
    # A strong / non-bank entity composed only ONE grounded signal.
    existing = [{"kind": "POSITIONING", "text": "X" * 80, "subcap_id": None}]
    cats = [
        ("P4C1", "Data Foundation", 2.1, ["E-001"]),
        ("P2C1", "Digital Channels", 2.4, []),
        ("P3C2", "Loan Origination", 2.6, []),
    ]
    out = se.ensure_why_now_depth(existing, cats, 2.8, "Acuity Mutual")
    assert len(out) >= 3
    assert all(len(s["text"]) >= 60 for s in out)
    assert any(s["kind"] == "PRIORITY" for s in out)
    # grounded in real categories (subcap_id carried) + no duplicate category
    ids = [s.get("subcap_id") for s in out if s.get("subcap_id")]
    assert ids and len(ids) == len(set(ids))


def test_ensure_why_now_depth_noop_when_already_deep():
    existing = [
        {"kind": "GAP", "text": "A" * 70, "subcap_id": "P4C1"},
        {"kind": "FINANCIAL", "text": "B" * 70},
        {"kind": "STRATEGY", "text": "C" * 70},
    ]
    out = se.ensure_why_now_depth(existing, [], 3.0, "Strong Bank")
    assert out == existing  # already >=3 long signals -> unchanged


def test_ensure_why_now_depth_drops_short_then_reaches_floor_via_trajectory():
    existing = [{"kind": "POSITIONING", "text": "short"}]  # <60 -> dropped
    cats = [("P1C1", "Strategy", 3.0, []), ("P2C1", "Customer", 3.1, [])]
    out = se.ensure_why_now_depth(existing, cats, 3.4, "Elliott")
    assert len(out) >= 3
    assert all(len(s["text"]) >= 60 for s in out)
    assert any(s["kind"] == "TRAJECTORY" for s in out)
    # nothing fabricated beyond scores: every padded signal cites subcap_scores
    assert all(s.get("derived_from") == "subcap_scores"
               for s in out if s["kind"] in {"PRIORITY", "TRAJECTORY"})


def test_finding_subject_phrase():
    # F-NNN label stripped; subject up to the first finding verb/connector.
    assert se.finding_subject_phrase(
        "F-004: Salesforce multi-org fragmentation creates risk"
    ) == "Salesforce multi-org fragmentation"
    assert se.finding_subject_phrase(
        "Active GenAI investment signals a cloud-first model"
    ) == "Active GenAI investment"
    # a bare section header has no clean subject → None (drops, never a name).
    assert se.finding_subject_phrase("2 Top Findings") is None


def test_build_finding_rejects_section_header_title():
    # The analyst "Top Findings" section repeats its header as every focus-area
    # title; the finding name must come from the statement, never "2 Top Findings".
    f = se.build_finding_from_focus(
        "2 Top Findings",
        "F-002: Claims straight-through processing via CCC Smart Estimate cuts cycle time.",
    )
    assert f is not None
    assert f["name"] == "Claims straight-through processing"


def test_build_finding_keeps_real_title():
    # a genuine capability title is still used when the body has no leading cap.
    f = se.build_finding_from_focus(
        "Data Foundation",
        "The data layer fragments across three cores with no canonical profile yet.",
    )
    assert f is not None and "Data Foundation" in f["name"]


def test_methodology_intro_preamble_is_dropped_not_named():
    # Beacon Bank's VERBATIM focus-area preamble (plural + "(evidence IDs)"
    # parenthetical, trailing "alignment" not "relevance") must be recognised as
    # methodology — never become the "7 findings" finding the corpus-regen surfaced.
    preamble = ("7 findings with quantified observations (evidence IDs), "
                "maturity implications, and Zennify solution alignment.")
    assert se.is_methodology_only(preamble)
    assert se.build_finding_from_focus("2 Top Findings", preamble) is None
    # the "relevance" wording (the strip_boilerplate fixture) is caught too.
    assert se.is_methodology_only(
        "3 findings with quantified observation, maturity implication, "
        "and Zennify solution relevance")
    # and it is excised when embedded in otherwise-real prose.
    mixed = ("Core modernization stalls. " + preamble + " Cycle time lags peers.")
    out = se.strip_boilerplate(mixed)
    assert "quantified observation" not in out.lower()
    assert "Core modernization stalls" in out


def test_suffixed_section_header_titles_are_methodology():
    # The header carries a trailing qualifier so it slips the end-anchored label —
    # verified corpus leaks: CalPrivate / Elliott / Sound CU.
    for t in ("2 Top Findings (with Zennify Relevance)",
              "3 Top Findings with Zennify Relevance",
              "2 Top Findings (REVISED)",
              "3 Critical Gaps (REVISED)"):
        assert se._METHODOLOGY_LABEL.match(t), t
    # a real capability title that merely contains the word is NOT a header.
    assert not se._METHODOLOGY_LABEL.match("Findings Workbench platform adoption")


def test_methodology_intro_BODIES_drop_the_whole_finding():
    # Section-intro / revision-note bodies the extractor captured from the report's
    # "Top Findings" preamble — each must drop, never be named after its header.
    bodies = [
        "Seven headline findings — each tied to a triple-validated opportunity.",
        "Each finding is cross-referenced to confirmed evidence and carries a "
        "direct Salesforce engagement implication.",
        "[Revised with Explorium T1 technographic validation. Changes marked ⚠️]",
        "[Updated: 1 gap RESOLVED (BI platform), 1 REDUCED (open banking).]",
        "Elliott's current strategy is defined by five objectives that frame this "
        "assessment:",
    ]
    for b in bodies:
        assert se.is_methodology_only(b), b
        assert se.build_finding_from_focus(
            "2 Top Findings (with Zennify Relevance)", b) is None, b


def test_is_nonfinding_name_rejects_headers_and_annotations_keeps_real():
    # Verified corpus-regen survivors that must be REJECTED as a finding name.
    reject = [
        "4 Critical Gaps & Active Blockers",          # header + "&" suffix
        "2 Critical Gaps1.2 Critical Gaps",           # garbled run-on header
        "3 Critical Gaps (REVISED)",                  # header + parenthetical
        "2 Top Findings (with Zennify Relevance)",    # header + parenthetical
        "Zennify relevance",                          # annotation label
        "Zennify Implication: Service Cloud + Agentforce",   # annotation prefix
        "Zennify Relevance: Salesforce FSC enables Towne",   # annotation prefix
        "Implications for Zennify Engagement Timing: SO-01",  # subsection header
        "Each finding combines a quantified observation",     # methodology preamble
        "capability dimension 54",                    # catalogue placeholder
        "a lower-scoring capability area",            # placeholder-scrub filler
    ]
    for n in reject:
        assert se.is_nonfinding_name(n), n
    # Real finding names (some lead with a digit) must be KEPT.
    keep = [
        "4 fragmented CRMs perceived as none by frontline",
        "6 vendors, zero middleware",
        "Data Foundation",
        "11.5pp Operating Efficiency Gap",
        "Marshall Ponzi Case — BSA/AML Re-Architecture",
        "Claims straight-through processing",
    ]
    for n in keep:
        assert not se.is_nonfinding_name(n), n


def test_labeled_gap_findings_recover_real_names():
    # CI Segall ships content-rich "GAP-N — Name (subcap, severity): detail"
    # findings under a repeated "4 Critical Gaps & Active Blockers" header. The
    # header title drops, but the per-gap NAME must be recovered (depth kept).
    header = "4 Critical Gaps & Active Blockers"
    assert se.build_finding_from_focus(
        header,
        "The following issues represent immediate risks to the active "
        "Zennify engagement and longer-term maturity development:") is None
    for body, exp in [
        ("GAP-1 — Integration Stall (P4C3, CRITICAL): Two full sprints elapsed "
         "with zero integration stories completed.", "Integration Stall"),
        ("GAP-4 — Budget Exhaustion Risk (MEDIUM): 905 total hours, 409 "
         "consumed.", "Budget Exhaustion Risk"),
    ]:
        f = se.build_finding_from_focus(header, body)
        assert f is not None and f["name"] == exp, (body, f)
        # the rich detail survives in the body (traceability/depth preserved).
        assert len(f["body"]) >= 40


def test_pipe_delimited_finding_names():
    # "<LABEL> | NAME | DETAIL" — the bare label must never be the name; the
    # middle field is. Verified: First Citizens, Bank of Utah.
    assert se.is_nonfinding_name("1") and se.is_nonfinding_name("F-001")
    assert se.is_nonfinding_name("GAP-3")
    f = se.build_finding_from_focus(
        "F-001", "F-001 | CRM Platform Absence | No CRM identified across 294 "
        "evidence items and 4 cores.")
    assert f is not None and f["name"] == "CRM Platform Absence"
    f = se.build_finding_from_focus(
        "1", "1 | FDIC Consent Order (Feb 2024) for BSA/AML, TPR, Reg E/DD "
        "deficiencies | CAPS rating downgrade risk.")
    # long descriptive middle field → leading headline only.
    assert f is not None and f["name"] == "FDIC Consent Order"
    f = se.build_finding_from_focus(
        "F-003", "F-003 | 500-Person CISO Org | CISO Marco Maiurano grew team.")
    assert f is not None and f["name"] == "500-Person CISO Org"
    # long descriptive middle field → trimmed at the first clause boundary.
    for q, exp in [
        # subject before the first verb is the cleanest name.
        ("F-005 | Analytical AI is real; customer-facing AI is absent | Enterprise BI",
         "Analytical AI"),
        ("3 | Loan origination is manual/semi-automated. Servicing only | nCino",
         "Loan origination"),
        ("F-001 | No sales CRM — but structured relationship banking exists | No CRM",
         "No sales CRM"),
        ("#1 | CRA Outstanding + Bauer 5-Star | Regulatory compliance exemplary",
         "CRA Outstanding + Bauer 5-Star"),
    ]:
        f = se.build_finding_from_focus(q.split(" | ")[0], q)
        assert f is not None and f["name"] == exp, (q, f)
    # "#4" bare hash-label is a non-finding name.
    assert se.is_nonfinding_name("#4")
    # a section-intro listing objectives drops entirely.
    assert se.build_finding_from_focus(
        "Objectives", "The following seven strategic objectives have been "
        "independently verified and flow into the handoff package.") is None
    # a normal em-dash / decimal name is preserved by the cleaner.
    assert se._clean_finding_name(
        "Marshall Ponzi Case — BSA/AML Re-Architecture"
    ) == "Marshall Ponzi Case — BSA/AML Re-Architecture"
    assert se._clean_finding_name(
        "11.5pp Operating Efficiency Gap") == "11.5pp Operating Efficiency Gap"
    # a decimal leading the body must NOT be eaten as a "11." number-label.
    f = se.build_finding_from_focus(
        "1", "11.5pp Operating Efficiency Gap is 2026's #1 priority for the bank.")
    assert f is not None and f["name"] == "11.5pp Operating Efficiency Gap"
    # a leading quote is stripped from the name.
    assert se._clean_finding_name("'Help From Actual Humans'") == "Help From Actual Humans"
    # section-intro fragments drop entirely.
    assert se.is_methodology_only("All gaps below are material to the 2026 roadmap.")
    assert se.is_methodology_only(
        "Five evidence-anchored gaps frame the land-and-expand thesis for Elliott.")


def test_extract_eids_inline_citations():
    assert se.extract_eids("via CCC Smart Estimate [E-085, E-074] and [E-12]") == [
        "E-085", "E-074", "E-12"]
    assert se.extract_eids("no citations here") == []
    # de-duped, first-seen order, capped.
    assert se.extract_eids("E-1 E-2 E-1 E-3", limit=2) == ["E-1", "E-2"]


def test_evidence_by_overlap_relinks_acuity_supporting_paragraph():
    # The analyst's finding and its evidence sit in SEPARATE focus paragraphs;
    # topical token overlap re-links them (Acuity verified strings).
    candidates = [
        (["E-005", "E-019"],
         se.significant_tokens("Acuity has built the most connected agent "
                               "technology platform among P&C mutuals.")),
        (["E-085", "E-074"],
         se.significant_tokens("Acuity deployed photo-based auto-estimation "
                               "through CCC Smart Estimate.")),
        (["E-057", "E-058"],
         se.significant_tokens("Acuity is hiring a Senior GenAI Engineer and "
                               "Data Scientist for Strategic Analytics.")),
    ]
    # finding about the agent ecosystem → the agent-platform evidence.
    assert se.evidence_by_overlap(
        "Acuity's agent-centric digital ecosystem leads the P&C mutual segment",
        candidates) == ["E-005", "E-019"]
    # finding about claims STP via CCC Smart Estimate → that paragraph's E-IDs.
    assert se.evidence_by_overlap(
        "Claims straight-through processing via CCC Smart Estimate reveals "
        "unexpected maturity", candidates) == ["E-085", "E-074"]
    # an unrelated finding shares too few tokens → no (wrong) evidence attached.
    assert se.evidence_by_overlap(
        "Branch network rationalization in rural markets", candidates) == []


# ── finalize_finding_body — sentence-boundary clip + 80-char floor (2026-07-02) ──

def test_finalize_finding_body_strips_ellipsis_and_dangling_clip():
    # trailing ellipsis / dangling hyphenated word are the truncation class
    b = se.finalize_finding_body("fying CRM across all eight business units...",
                                 "CRM Consolidation", "P2C1", 2.0, 3.0)
    assert not b.endswith("...") and "…" not in b
    assert len(b) >= 80
    b2 = se.finalize_finding_body("Data quality remains uneve—", "Data Quality",
                                  "P4C2", 1.5, 2.5)
    import re as _re
    assert not _re.search(r"[A-Za-z][—–-]$", b2)  # noqa: RUF001


def test_finalize_finding_body_floors_short_fragment_with_score_fact():
    b = se.finalize_finding_body("Salesforce-Native Platform CONFIRMED LIVE",
                                 "Salesforce Platform", "P4C1", 1.8, 2.6)
    assert len(b) >= 80
    assert "1.8/5" in b  # grounded score fact appended, not fabricated


def test_finalize_finding_body_keeps_a_clean_body_unchanged():
    good = ("A complete finding body that already reads as clean prose and ends "
            "with a real terminal period here.")
    assert se.finalize_finding_body(good, "X", "P1C1", 2.0, 3.0) == good


def test_finalize_finding_body_honest_when_no_score():
    # no score to append — a short body is returned as-is (never fabricated)
    out = se.finalize_finding_body("Short bit", "X", None, None, None)
    assert out.rstrip(".") == "Short bit"


# ── enforce_overall_maturity_claim — SCQA overall == run overall_score ───────

def test_enforce_overall_maturity_rewrites_only_entity_claim():
    md = ("Zennify's assessment places overall digital maturity at 1.8/5. "
          "The deepest capability gap is AI Financial Advisor at 1.2/5.")
    out = se.enforce_overall_maturity_claim(md, 2.06)
    assert "overall digital maturity at 2.1/5" in out
    assert "AI Financial Advisor at 1.2/5" in out  # gap score untouched


def test_enforce_overall_maturity_variants_and_noop():
    assert "maturity of 2.4 out of 5" in se.enforce_overall_maturity_claim(
        "composite maturity of 3.9 out of 5.", 2.4)
    # a bare subcap claim with no overall context is never rewritten
    assert se.enforce_overall_maturity_claim(
        "Data governance scores 1.5 out of 5", 2.4) == "Data governance scores 1.5 out of 5"
    # non-numeric overall → no-op
    assert se.enforce_overall_maturity_claim("digital maturity at 1.8/5", None) == \
        "digital maturity at 1.8/5"


# ── apply_contamination_badge — the SHARED pack-patcher ⇄ live-route twin ────

_CONTAMINATED_OV = {
    "entity": {"name": "Beacon Bank"},
    "firmographics": {"ticker": "BBT", "stock_ticker": None},
    # Foreign ticker + run-id token + a foreign FI name dominating prose
    # (>=3 mentions) — the tier-A recipe from contamination_signals.
    "narrative": {"scqa_md": (
        "NYSE: BBT. Run DMA-ASM-BBT-20260101-0001. Berkshire Bank expanded. "
        "Berkshire Bank also grew deposits. Berkshire Bank hired a CTO.")},
}


def test_apply_contamination_badge_tier_a_stamps_and_nulls_ticker():
    ov = {k: (dict(v) if isinstance(v, dict) else v)
          for k, v in _CONTAMINATED_OV.items()}
    tier = se.apply_contamination_badge(ov)
    assert tier == "A"
    dq = ov["data_quality"]
    assert dq["source_misattribution"] == "A"
    assert "BBT" in dq["misattribution_markers"]["foreign_tickers"]
    assert ov["firmographics"]["ticker"] is None  # tier-A nulling


def test_apply_contamination_badge_handles_explicit_none_data_quality():
    # The LIVE route serializes the schema's `data_quality: None` BEFORE
    # applying the badge — setdefault would return that existing None and
    # crash (the 2026-07-04 parity sim's one live_err). Key present+None
    # must behave exactly like key absent.
    ov = {k: (dict(v) if isinstance(v, dict) else v)
          for k, v in _CONTAMINATED_OV.items()}
    ov["data_quality"] = None
    assert se.apply_contamination_badge(ov) == "A"
    assert ov["data_quality"]["source_misattribution"] == "A"


def test_apply_contamination_badge_clean_snapshot_no_op():
    ov = {"entity": {"name": "Clean Bank"},
          "firmographics": {"ticker": None},
          "data_quality": None,
          "narrative": {"scqa_md": "A tidy grounded story with no foreign ids."}}
    assert se.apply_contamination_badge(ov) is None
    assert ov["data_quality"] is None  # untouched — stays honest-null


# ── run/request IDs are pipeline artifacts, never client issues ──────────────
# 2026-07-14 verbatim vet: a HAPO exec summary wove a run-id in as an issue
# title ("The compliance file is live — DMA-ASM-HAPO-20260324-0001 and
# DMA-RES-HAPO-2026…"). The leak filter must drop those as issue candidates
# while leaving genuine client-facing prose untouched.

def test_pipeline_leak_title_filters_run_and_request_ids():
    assert se._is_pipeline_leak_title("DMA-ASM-HAPO-20260324-0001")
    assert se._is_pipeline_leak_title("DMA-RES-HAPO-20260324-0002")
    assert se._is_pipeline_leak_title(
        "The compliance file is live — DMA-ASM-HAPO-20260324-0001")
    assert se._is_pipeline_leak_title("REQ-A1B2C3D4")


def test_pipeline_leak_title_keeps_genuine_client_issues():
    # ordinary prose that merely mentions the DMA program is NOT a leak
    assert not se._is_pipeline_leak_title(
        "Commercial lending onboarding is manual and error-prone")
    assert not se._is_pipeline_leak_title(
        "The digital maturity assessment surfaced fragmented data")
    assert not se._is_pipeline_leak_title("Fragmented customer data across channels")


# ── capability_phrase (artifact-title leak, 2026-07-06) ──────────────────────

def test_capability_phrase_strips_artifact_suffixes():
    assert se.capability_phrase("Digital Marketing Strategy Document") == \
        "Digital Marketing Strategy"
    assert se.capability_phrase("Customer Journey Mapping Workbook") == \
        "Customer Journey Mapping"
    assert se.capability_phrase("Model Governance Checklist") == "Model Governance"


def test_capability_phrase_keeps_real_capability_names():
    for name in ("Data Foundation", "Regulatory Reporting",
                 "Digital Marketing & Acquisition", "Omnichannel Orchestration"):
        assert se.capability_phrase(name) == name


def test_capability_phrase_unrecoverable_returns_empty():
    # a pure artifact noun, or a strip that would leave a single word, is
    # unrecoverable as a capability phrase → '' (caller falls back).
    assert se.capability_phrase("Documentation") == ""
    assert se.capability_phrase("Document") == ""
    assert se.capability_phrase("Board Document") == ""
    assert se.capability_phrase("") == ""
    assert se.capability_phrase(None) == ""


# ── why-now near-duplicate suppression (2026-07-06 mandate) ──────────────────

def _gap_sig(text, **over):
    base = {"kind": "GAP", "strength": "SUPPORTING", "text": text,
            "detail": text, "evidence": []}
    base.update(over)
    return base


def test_dedupe_why_now_keeps_distinct_signals():
    sigs = [
        _gap_sig("Data Foundation scores 1.4/5 vs a typical 2.8 at similar "
                 "institutions — the deepest open gap in Data & Technology."),
        {"kind": "LEADERSHIP", "text": "Jane Roe is newly in seat as Chief "
         "Data Officer — new executives set platform direction in their "
         "first two quarters.", "evidence": ["E-9"]},
        {"kind": "MIGRATION", "text": "The core banking conversion to "
         "Fiserv DNA goes live in Q2 2027; integration decisions lock at "
         "go-live.", "evidence": ["E-4"]},
    ]
    assert se.dedupe_why_now_signals(sigs) == sigs


def test_dedupe_why_now_suppresses_near_identical_weaker_signal():
    a = _gap_sig("Digital Marketing Strategy scores 1.4/5 vs a typical 3.2 at "
                 "similar institutions — the deepest open gap in Customer "
                 "Experience and the constraint the other investments inherit.")
    b = _gap_sig("Digital Marketing Strategy scores 1.5/5 vs a typical 3.2 at "
                 "similar institutions — the deepest open gap in Customer "
                 "Experience and the constraint the other investments inherit.")
    c = {"kind": "LEADERSHIP",
         "text": "Jane Roe is newly in seat as Chief Data Officer at the bank "
                 "— new executives set platform direction in their first two "
                 "quarters.", "evidence": []}
    d = {"kind": "MIGRATION",
         "text": "The core conversion to Fiserv DNA goes live in Q2 2027; "
                 "integration and data-architecture decisions lock at "
                 "go-live.", "evidence": ["E-4"]}
    out = se.dedupe_why_now_signals([a, b, c, d])
    # b adds nothing distinct → suppressed; floor already satisfied (3 left)
    assert out == [a, c, d]


def test_dedupe_why_now_differentiates_via_own_facts_when_possible():
    a = _gap_sig("Deposit gathering trails the cohort across retail and "
                 "commercial books, the deepest open gap this assessment "
                 "found in operations at the institution today overall.")
    b = _gap_sig("Deposit gathering trails the cohort across retail and "
                 "commercial books, the deepest open gap this assessment "
                 "found in operations at the institution today overall.",
                 metric="brokered deposits 38% of funding",
                 window="closes Q2 2027", evidence=["E-77"])
    c = {"kind": "LEADERSHIP", "text": "L" * 80}
    d = {"kind": "MIGRATION", "text": "M" * 80}
    out = se.dedupe_why_now_signals([a, b, c, d])
    assert len(out) == 4
    diff = next(s for s in out if s.get("metric"))
    # differentiated with ITS OWN facts, cited on its own evidence …
    assert "brokered deposits 38% of funding" in diff["text"]
    assert "[E-77]" in diff["text"]
    # … and the input dict was never mutated
    assert "What sets this signal apart" not in b["text"] or b is not diff


def test_dedupe_why_now_honors_min_keep_floor():
    dup = "Same capability gap text repeated verbatim across every card " \
          "on the page, communicating nothing distinct to the reader."
    sigs = [_gap_sig(dup), _gap_sig(dup), _gap_sig(dup)]
    out = se.dedupe_why_now_signals(sigs, min_keep=3)
    assert len(out) == 3  # the depth floor beats suppression


def test_ensure_why_now_depth_fillers_communicate_differently():
    cats = [
        ("P4C1", "Data Foundation", 2.1, ["E-001"]),
        ("P2C1", "Digital Channels", 2.4, []),
        ("P3C2", "Loan Origination", 2.6, []),
    ]
    out = se.ensure_why_now_depth([], cats, 2.8, "Acuity Mutual")
    texts = [s["text"] for s in out if s["kind"] == "PRIORITY"]
    assert len(texts) >= 3
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            assert not se.texts_near_identical(t1, t2), (t1, t2)


def test_ensure_why_now_depth_filler_never_uses_artifact_title():
    cats = [("P2C1", "Digital Marketing Strategy Document", 1.4, [])]
    out = se.ensure_why_now_depth([], cats, None, "IBKR", min_count=1)
    assert out and "Digital Marketing Strategy" in out[0]["text"]
    assert "Strategy Document" not in out[0]["text"]


# ── quote_span (verbatim-quote mandate, 2026-07-06) ──────────────────────────

def test_quote_span_short_text_passes_through_verbatim():
    s = "Marketing relies on a single shared inbox for all campaigns"
    assert se.quote_span(s, 200) == s
    # whitespace normalization is the ONLY permitted transformation
    assert se.quote_span("a  b\n c   d " + "x" * 40, 200) == \
        "a b c d " + "x" * 40


def test_quote_span_truncates_at_sentence_boundary_with_ellipsis():
    s = ("The credit union processes all wire transfers manually through a "
         "shared spreadsheet. Staff re-key the same request into three "
         "systems, and the audit trail lives in email attachments that "
         "compliance reviews quarterly.")
    out = se.quote_span(s, 120)
    assert out.endswith(" …")
    core = out[:-2]
    assert core.endswith(".")           # claim boundary, never mid-claim
    assert core in s                     # contiguous verbatim span
    assert len(core) <= 121


def test_quote_span_falls_back_to_clause_seam():
    s = ("Deposit growth outpaced the technology budget for six straight "
         "years; the platform roadmap was deferred at every planning cycle "
         "since the merger closed and headcount stayed flat throughout")
    out = se.quote_span(s, 100)
    assert out.endswith(" …")
    assert out[:-2].rstrip() in s        # verbatim up to the ';' seam


def test_quote_span_refuses_a_mid_claim_cut():
    s = ("a continuous stream of words with no sentence ending or clause "
         "seam anywhere in range that would let a truncation land cleanly "
         "on a complete claim rather than slicing through the middle")
    assert se.quote_span(s, 100) == ""


def test_quote_span_never_rewrites_numbers_or_qualifiers():
    s = ("Roughly 60% of loan files, but not consumer cards, still require "
         "wet signatures. The exception queue averages 11 days.")
    out = se.quote_span(s, 90)
    assert out == "Roughly 60% of loan files, but not consumer cards, still " \
                  "require wet signatures. …"


# ── why-now FEATURED strip: 4 tiles when material exists (2026-07-06) ────────

def test_ensure_why_now_depth_min_count_4_fills_the_featured_strip():
    # The D1 prototype strip features 4 tiles (g4 grid, slice(0,4)) — with
    # min_count=4 the composer pads to 4 from the entity's own scored
    # categories, all texts distinct (no near-duplicates).
    cats = [
        ("P4C1", "Data Foundation", 2.1, ["E-001"]),
        ("P2C1", "Digital Channels", 2.4, []),
        ("P3C2", "Loan Origination", 2.6, []),
        ("P1C2", "Innovation Governance", 2.7, []),
    ]
    out = se.ensure_why_now_depth([], cats, 2.8, "Acuity Mutual", min_count=4)
    assert len(out) >= 4
    texts = [s["text"] for s in out]
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            assert not se.texts_near_identical(t1, t2), (t1, t2)


def test_dedupe_then_refill_never_leaves_a_featured_slot_empty():
    # dedupe suppresses one of four near-identical-pair signals → 3; the
    # refill pass pads back to 4 from an UNUSED category — a distinct
    # rotating filler, never a re-admitted duplicate.
    dup = ("Digital Marketing Strategy scores 1.4/5 vs a typical 3.2 at "
           "similar institutions — the deepest open gap in Customer "
           "Experience and the constraint the other investments inherit.")
    sigs = [
        {"kind": "GAP", "strength": "STRONG", "text": dup, "detail": dup,
         "evidence": [], "subcap_id": "P2C1"},
        {"kind": "GAP", "strength": "SUPPORTING", "text": dup, "detail": dup,
         "evidence": [], "subcap_id": "P2C2"},
        {"kind": "LEADERSHIP", "text": "Jane Roe is newly in seat as Chief "
         "Data Officer — new executives set platform direction in their "
         "first two quarters.", "evidence": ["E-9"]},
        {"kind": "MIGRATION", "text": "The core conversion to Fiserv DNA "
         "goes live in Q2 2027; integration decisions lock at go-live.",
         "evidence": ["E-4"]},
    ]
    deduped = se.dedupe_why_now_signals(sigs)
    assert len(deduped) == 3                      # duplicate suppressed
    cats = [("P4C1", "Data Foundation", 2.1, ["E-001"]),
            ("P2C1", "Digital Channels", 2.4, [])]  # P2C1 used; P4C1 free
    refilled = se.ensure_why_now_depth(deduped, cats, 2.8, "Acuity",
                                       min_count=4)
    assert len(refilled) >= 4
    texts = [s.get("text") or "" for s in refilled]
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            assert not se.texts_near_identical(t1, t2), (t1, t2)


def test_why_now_filler_rotation_continues_across_refill_passes():
    # A refill pass after dedupe must use the NEXT phrasing variant, never
    # restart at template 0 and recreate the near-duplicate it replaces.
    first = se.ensure_why_now_depth(
        [], [("P4C1", "Data Foundation", 2.1, [])], None, "Alma", min_count=1)
    assert len(first) == 1 and first[0]["kind"] == "PRIORITY"
    refill = se.ensure_why_now_depth(
        first, [("P4C1", "Data Foundation", 2.1, []),
                ("P1C3", "Innovation Culture", 1.5, [])],
        None, "Alma", min_count=2)
    assert len(refill) == 2
    assert not se.texts_near_identical(refill[0]["text"], refill[1]["text"]), \
        (refill[0]["text"], refill[1]["text"])


def test_deficit_shorthand_softened_in_composed_copy() -> None:
    """2026-07-13 vetting: 'no iPaaS' in the SCQA issue weave reads as an
    accusation — composed copy reframes forward; verification vocabulary
    ('no evidence of') is exempt (it is a researcher absence statement)."""
    from app.services.startup_enrich import (
        finalize_title_text,
        soften_deficit_phrases,
    )
    assert soften_deficit_phrases(
        "4 mergers; 20+ platforms; no iPaaS"
    ) == "4 mergers; 20+ platforms; iPaaS not yet in place"
    assert soften_deficit_phrases("no evidence of enforcement actions") == \
        "no evidence of enforcement actions"
    assert soften_deficit_phrases("fails to reconcile daily") == \
        "does not yet reconcile daily"
    assert finalize_title_text("No unified agent desktop / case management") \
        == "unified agent desktop / case management not yet in place"
