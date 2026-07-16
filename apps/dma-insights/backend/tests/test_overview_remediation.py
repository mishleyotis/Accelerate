"""Unit stress-tests for the 2026-06-25 Overview content-quality remediation
helpers (app/services/startup_enrich). Each case uses a VERIFIED real defect
string from the deep audit as an adversarial fixture. Stdlib-only, no DB.
"""
from __future__ import annotations

from app.services import startup_enrich as se


# ── E. Leadership junk (tightened is_person_name) ────────────────────────────
def test_is_person_name_rejects_audit_junk_rows():
    for junk in ("CEO: Brandon", "Leadership Gap:", "PRIMARY: Kevin",
                 "GOVERNANCE: Betsy", "⚠️ CISO Akerberg", "❌ CDO ABSENT",
                 "CDO ABSENT", "Leadership Gaps:", "Tech Team:"):
        assert not se.is_person_name(junk), junk


def test_is_person_name_still_accepts_real_names():
    for ok in ("Kurt MacAlpine", "Marc-André Lewis", "Douglas J. Jamieson",
               "Michael P. Psyllos", "Rachel Dodson"):
        assert se.is_person_name(ok), ok


# ── C. Why-now boilerplate + methodology-only ────────────────────────────────
def test_strip_boilerplate_methodology_fragments():
    s = ("2 Top Findings: Each finding is grounded in evidence and framed through "
         "the Salesforce Account Executive lens. The Zennify Relevance column "
         "identifies the specific net-new Salesforce solution.")
    out = se.strip_boilerplate(s)
    assert "grounded in evidence" not in out
    assert "Salesforce Account Executive lens" not in out
    assert "Zennify Relevance column" not in out

    g = ("3 Critical Gaps: The following gaps affect assessment accuracy and "
         "flow directly into the Handoff Package (Appendix B).")
    og = se.strip_boilerplate(g)
    assert "Handoff Package" not in og and "assessment accuracy" not in og


def test_is_methodology_only():
    assert se.is_methodology_only("2 Top Findings:")
    assert se.is_methodology_only("3 Critical Gaps:")
    assert se.is_methodology_only("")
    assert not se.is_methodology_only(
        "nCino core migration in flight, target completion Q2 2026.")


# ── A. Findings coherence: leading_capability / is_true_gap / placeholder ─────
def test_leading_capability_extracts_body_subject():
    assert se.leading_capability(
        "Data Virtualization & Federation is one of 1st Security Bank's least "
        "developed data and technology capabilities, scoring 1.6 out of 5."
    ) == "Data Virtualization & Federation"
    assert se.leading_capability(
        "AI/ML Model Performance Monitoring is the most material capability gap "
        "in customer experience, at 1.4 against a peer median of 2.0."
    ) == "AI/ML Model Performance Monitoring"
    assert se.leading_capability("") is None


def test_is_true_gap_direction():
    assert se.is_true_gap(1.5, 2.0) is True       # below peer → gap
    assert se.is_true_gap(3.02, 2.0) is False      # above peer → strength
    assert se.is_true_gap(2.5, 2.5) is False        # at peer → not a gap
    assert se.is_true_gap(None, 2.0) is None        # unknown


def test_is_placeholder_name():
    for bad in ("capability dimension 54", "capability dimension 35", "— Subcap 6",
                "Subcap 7", "P4C2.1", "Dimension 12"):
        assert se.is_placeholder_name(bad), bad
    for ok in ("Data Warehouse & Data Lake", "Journey Orchestration", "Fraud Investigation"):
        assert not se.is_placeholder_name(ok), ok


# ── B. SCQA scaffolding + citation repair ────────────────────────────────────
def test_scqa_scaffolding_detection_and_strip():
    alma = ("Alma Bank Digital Maturity Assessment — May 19, 2026\n"
            "PRE-WRITE INPUT ONLY — Do NOT render in chat\n\n"
            "Q1: What story does the DATA tell?\n\n"
            "Alma Bank is a $1.1B regional bank mid-way through a multi-year "
            "transformation. The data substrate is the binding constraint.\n\n"
            "Validation pre-write checklist: ✅ report_analysis.json exists on disk")
    assert se.scqa_has_scaffolding(alma)
    out = se.strip_scqa_scaffolding(alma)
    assert "PRE-WRITE INPUT" not in out and "Do NOT render" not in out
    assert "Q1:" not in out and "Validation pre-write" not in out
    assert "report_analysis.json exists" not in out  # footer cut
    assert "binding constraint" in out               # narrative kept
    assert not se.scqa_has_scaffolding(out)

    beacon = ("DMA Assessment Report Synthesis\nRun ID: DMA-ASM-BBT-20260511-0001\n"
              "READ ONLY FROM THIS FILE WHEN WRITING THE REPORT. NO AD HOC DATA.\n\n"
              "Beacon Bank's overall maturity is developing.")
    assert se.scqa_has_scaffolding(beacon)
    assert "READ ONLY FROM THIS FILE" not in se.strip_scqa_scaffolding(beacon)


def test_repair_citations_keeps_valid_drops_junk():
    s = ("Recommendation: lead with Salesforce Data Cloud [E-047] [E-089]. "
         "Strategy tied to growth [::F1] and data [, T2] with Evidence:,, "
         "and [E--001] doubled-dash.")
    out = se.repair_citations(s)
    assert "[E-047]" in out and "[E-089]" in out       # valid kept
    assert "[E-001]" in out                              # de-double-dashed
    assert "[::F1]" not in out and "[, T2]" not in out and "Evidence:,," not in out


def test_dedupe_prefix_and_clip_clean():
    assert se.dedupe_prefix("F-001: F-001 | Teradata to Databricks modernization") \
        == "F-001 — Teradata to Databricks modernization"
    assert se.dedupe_prefix("No duplicate here") == "No duplicate here"
    clipped = se.clip_clean("Real-time analytics to support in-flight integration "
                            "decisions across the data platform " * 4, 80)
    # served prose is complete sentences: clip_clean never emits an ellipsis
    # and never severs a word (2026-07-13 doctrine — '…' reads as truncation)
    assert "…" not in clipped and "..." not in clipped
    assert not clipped.rstrip(".").endswith("in-")
    assert clipped.endswith((".", "!", "?"))
    assert len(clipped) <= 82


# ── D. Firmographics sanitisation ────────────────────────────────────────────
def test_plausible_aum():
    assert not se.plausible_aum(1.03e14, "CIB")     # $103T payments FMI
    assert not se.plausible_aum(20969194, "RB")      # $21M "regional bank"
    assert se.plausible_aum(1.1e9, "RB")             # $1.1B regional bank OK
    assert se.plausible_aum(2.24e11, "AM")           # $224B asset manager OK


def test_subvertical_label_overrides():
    assert se.subvertical_label("SL Green Realty Corp", "AM") == "real-estate investment trust"
    assert se.subvertical_label("Interactive Brokers Group, Inc.", "RIA") == "brokerage"
    assert se.subvertical_label("Travel Insured International", "IC") == "insurance MGA"
    assert se.subvertical_label("Payments Canada", "CIB") == "payments system operator"
    assert se.subvertical_label("Alma Bank", "RB") == "regional bank"


def test_sanitize_firmographics_nulls_garbage():
    firm = {
        "aum_usd": 1.03e14, "size_tier": "Large (>$500B AUM)",
        "primary_regulator": "Role", "headcount": 16,
        "hq_address": "{'address': 'Suite 1830', 'city': 'Vancouver'}",
        "footprint": ["2026)", "HQ: Poughkeepsie", "NY", "Thurston County)"],
    }
    n = se.sanitize_firmographics(firm, "RB")
    assert firm["aum_usd"] is None              # $103T nulled
    assert firm["size_tier"] is None            # contradicts (now-null) aum / >$500B
    assert firm["primary_regulator"] is None    # "Role" sentinel
    assert firm["headcount"] is None            # 16 out of bounds for a bank
    assert firm["hq_address"] is None           # dict-repr
    assert "NY" in (firm["footprint"] or [])    # real token kept
    assert "2026)" not in (firm["footprint"] or [])  # year fragment dropped
    assert n >= 5


def test_sanitize_firmographics_units_recovery():
    # tristate: $20.97M logged for a ~$21B bank — a 1000x units error → recover.
    firm = {"aum_usd": 20969194.0}
    se.sanitize_firmographics(firm, "RB")
    assert firm["aum_usd"] == 20969194000.0          # x1000 → ~$21B
    # payments-canada: $103T is unsalvageable (clearing value, not assets) → null.
    firm2 = {"aum_usd": 1.03e14}
    se.sanitize_firmographics(firm2, "CIB")
    assert firm2["aum_usd"] is None


def test_sanitize_firmographics_keeps_good_values():
    firm = {"aum_usd": 1.1e9, "primary_regulator": "FDIC", "headcount": 158,
            "footprint": ["Washington", "Oregon"]}
    se.sanitize_firmographics(firm, "RB")
    assert firm["aum_usd"] == 1.1e9 and firm["primary_regulator"] == "FDIC"
    assert firm["headcount"] == 158 and firm["footprint"] == ["Washington", "Oregon"]


# ── A (canonical). Top-findings composed via the SHARED helpers ──────────────
# The same logic the offline patcher runs is what deepen_narrative now calls,
# so these lock the canonical report-extraction path the DB pipeline can't run
# in this env.
def test_compose_finding_body_gap_vs_strength():
    # Frame pools vary the surface (anti-template 2026-07-13); the polarity
    # contract is invariant: a gap reads as a priority, a strength never does.
    gap = se.compose_finding_body("Journey Orchestration", "P2C3.1", 1.6, 2.4, True)
    assert "priority" in gap and "customer experience" in gap
    assert "1.6/5" in gap and "peer median of 2.4" in gap
    strength = se.compose_finding_body("Data Warehouse & Data Lake", "P4C1.2", 3.4, 2.6, False)
    assert "at or ahead" in strength or "clears its peer line" in strength
    assert "strength" in strength and "data and technology" in strength
    assert "priority" not in strength
    # deterministic per inputs; client_key spreads frames across the corpus
    assert gap == se.compose_finding_body("Journey Orchestration", "P2C3.1", 1.6, 2.4, True)
    alts = {se.compose_finding_body("Journey Orchestration", "P2C3.1", 1.6, 2.4,
                                    True, client_key=f"c{i}") for i in range(8)}
    assert len(alts) >= 2


def test_reframe_non_gap_only_rewrites_gap_language():
    body = ("Cloud Platform Strategy is the lowest-scoring capability and the "
            "binding constraint on the data agenda.")
    out = se.reframe_non_gap(body, "Cloud Platform Strategy", "P4C2.1", 3.1, 2.5)
    assert "lowest-scoring" not in out and "binding constraint" not in out
    assert "at or ahead" in out or "clears its peer line" in out
    neutral = "Cloud Platform Strategy is well established and broadly adopted."
    assert se.reframe_non_gap(neutral, "Cloud Platform Strategy", "P4C2.1", 3.1, 2.5) == neutral


def test_build_finding_from_focus_extracts_report_finding():
    # An analyst observation (verbatim quote) → a coherent, gap-aware finding.
    f = se.build_finding_from_focus(
        title="Data foundation",
        quote=("Data Virtualization & Federation is one of the bank's least developed "
               "data and technology capabilities, scoring 1.6 out of 5 [E-047]."),
        subcap_id="P4C2.1", score=1.6, peer=2.3)
    assert f is not None
    assert f["name"] == "Data Virtualization & Federation"   # from the body, not the title
    assert f["is_gap"] is True and "[E-047]" in f["body"]


def test_build_finding_from_focus_reframes_non_gap():
    f = se.build_finding_from_focus(
        title="A strength",
        quote=("Fraud Investigation is the lowest-scoring capability area for the firm, "
               "anchoring the operations agenda."),
        subcap_id="P3C2.1", score=3.4, peer=2.6)   # above peer → NOT a gap
    assert f is not None and f["is_gap"] is False
    assert "lowest-scoring" not in f["body"]
    assert "at or ahead" in f["body"] or "clears its peer line" in f["body"]


def test_build_finding_from_focus_drops_methodology_and_placeholder():
    assert se.build_finding_from_focus("x", "2 Top Findings:", "P1C1") is None
    assert se.build_finding_from_focus("Subcap 7", "capability dimension 54 is weak.",
                                       "P4C2.1") is None
    assert se.build_finding_from_focus("x", "too short") is None


# ── Wrong-entity (source-misattribution) contamination ───────────────────────
def test_contamination_tier_a_beacon_bank():
    # Identity 'Beacon Bank' but ticker/run-id/prose are BB&T / Berkshire.
    blob = ('{"ticker": "NYSE: BBT", "request_id": "DMA-ASM-BBT-20260511-0001", '
            '"body": "Berkshire Bank scores 2.8/5. Berkshire Bank Indeed rating. '
            'Berkshire Bank merger integration anxiety."}')
    sig = se.contamination_signals(blob, "Beacon Bank")
    assert sig["tier"] == "A"
    assert sig["foreign_tickers"] == ["BBT"] and sig["foreign_runid_tokens"] == ["BBT"]
    assert "Berkshire" in sig["foreign_entities"]


def test_contamination_tier_b_holding_company_ticker_not_suppressed():
    # SouthState Corporation's real ticker IS SSB (SouthState Bank) — no foreign
    # company in the prose → review-only, never auto-suppressed.
    blob = '{"ticker": "NASDAQ: SSB", "request_id": "DMA-ASM-SSB-20260511-0001"}'
    sig = se.contamination_signals(blob, "SouthState Corporation")
    assert sig["tier"] == "B"
    assert not sig["foreign_entities"]


def test_contamination_clean_own_ticker_and_acquiree_mention():
    # Own ticker (subsequence of name) + a single legitimate acquiree mention
    # must NOT flag — guards against nuking 53 legit entities.
    blob = ('{"ticker": "NASDAQ: AMH", "request_id": "DMA-ASM-AMH-20260511-0001", '
            '"body": "Acquired Republic First Bank assets in 2024."}')
    assert se.contamination_signals(blob, "American Homes 4 Rent, LP")["tier"] is None
    assert se.contamination_signals("clean narrative, no tickers", "Alma Bank")["tier"] is None
