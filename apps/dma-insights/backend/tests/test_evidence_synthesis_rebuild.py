"""Evidence-first deep-synthesis rebuild (2026-07-06 anti-shallow family).

Pins the diagnosis fix plan: every deep surface must READ its evidence and
re-express it as an argued, data-rich fact — never a verbatim quote-dump
followed by a score template. Pure logic, no DB, real evidence excerpts taken
VERBATIM from tests/fixtures/dma_packages_batches/**/01_evidence/*.json.

Coverage:
  1. normalize_excerpt_fact — cleans label-colon headers, ALL-CAPS/"=" scoring
     metadata, inline E-ID refs, markup; rejects bare headers / meta-notes.
  2. compose_evidence_why / finding_wwsw — excerpt → interpretation tied to the
     subcap's maturity impact (not "The linked evidence records: <raw note>").
  3. _rank_card_excerpts — TOPICAL overlap beats tier-alone (AM-Best quote never
     wins a Cyber-Risk card when a topical excerpt is cited).
  4. Insight-card composition + the HARD rubric/lint gate (score-echo +
     incorporation), evidence-first WHAT/WHY.
  5. quality score-echo rejects the diagnosis's VERBATIM bad card whys;
     incorporation kills citation-washing.
  6. compose_scqa_deep — argued (fused) Complication, not a score ladder;
     pipeline-leak issue titles filtered; analyst-quote punctuation repaired.
  7. subcap rationale — evidence-framed readable prose (markdown_lint clean).
"""
from __future__ import annotations

import re

from app.scripts.deepen_narrative import (
    _evidence_first_what,
    _rank_card_excerpts,
)
from app.services import startup_enrich as se
from app.services.nlp.quality import (
    _is_score_restatement,
    markdown_lint,
    proofread,
    rubric_score,
)
from app.services.subcap_synthesis import SubcapFacts, compose_subcap_narrative

# ── Real evidence excerpts (VERBATIM from the fixture packages) ─────────────
# batch_14/Acuity Insurance - DMA/01_evidence/evidence_index.json
ACUITY_NAIC = ("NAIC complaint index 0.66 — roughly 1/3 fewer complaints than "
               "expected for size (average 1.0)")
ACUITY_SEMCI = ("SEMCI (Single Entry Multiple Company Interface) support for "
                "commercial lines — enables agents to submit to multiple "
                "carriers from one entry")
ACUITY_HIRE = "Planning to hire 200+ in 2025"
ACUITY_CLAIMS = "96% claims satisfaction rating from customers"
# batch_14/Greenstone - DMA/01_evidence/01_evidence_P4.json (scoring_impact)
GREENSTONE_CDO = ("No CDO = M1-M2 for executive data ownership. CIO role is "
                  "traditionally framed (IT operations), not data-centric.")
GREENSTONE_TEAM = ("Centralized data team within IT (not federated, not "
                   "C-suite sponsored) = M2 for data governance organizational "
                   "maturity.")
# The diagnosis's verbatim aafcu quote-dump excerpt (label-colon + '=' + E-refs)
AAFCU_DUMP = ("P4C1 DATA GOVERNANCE BASELINE: NCUA GLBA compliance (E-147) "
              "mandates data governance. ARCU data warehouse (E-137) = "
              "enterprise data architecture with consistent business "
              "definitions")


# ── 1. normalize_excerpt_fact ───────────────────────────────────────────────

class TestNormalizeExcerptFact:
    def test_clean_prose_is_preserved_verbatim(self) -> None:
        assert se.normalize_excerpt_fact(ACUITY_NAIC) == ACUITY_NAIC
        assert se.normalize_excerpt_fact(ACUITY_SEMCI) == ACUITY_SEMCI

    def test_score_band_metadata_stripped(self) -> None:
        out = se.normalize_excerpt_fact(GREENSTONE_CDO)
        assert out and "M1-M2" not in out and "M2" not in out
        assert "CIO role" in out                     # the real content survives

    def test_trailing_equals_band_dropped(self) -> None:
        out = se.normalize_excerpt_fact(GREENSTONE_TEAM)
        assert out and "= M2" not in out and "organizational maturity" not in out
        assert "Centralized data team" in out

    def test_label_header_and_inline_eids_stripped(self) -> None:
        out = se.normalize_excerpt_fact(AAFCU_DUMP)
        assert out is not None
        assert not out.startswith("P4C1")            # ALL-CAPS label header gone
        assert "DATA GOVERNANCE BASELINE" not in out
        assert "(E-147)" not in out and "(E-137)" not in out
        assert "NCUA GLBA" in out                    # acronyms preserved
        assert " = " not in out                      # note-syntax converted

    def test_bare_header_and_meta_notes_reject(self) -> None:
        assert se.normalize_excerpt_fact("BI/Analytics:") is None
        assert se.normalize_excerpt_fact(
            "NEGATIVE SEARCH RESULT: no podcast appearances found for "
            "any executive") is None
        assert se.normalize_excerpt_fact("short") is None

    def test_markup_tags_removed(self) -> None:
        out = se.normalize_excerpt_fact(
            "[ERS: 2.20] [FACT] SR 11-7 requires model risk management for "
            "all supervised banks over $10B")
        assert out is not None and "[ERS" not in out and "[FACT]" not in out
        assert "SR 11-7" in out


# ── 2. compose_evidence_why / finding_wwsw ─────────────────────────────────

class TestEvidenceInterpretation:
    def test_why_reads_the_excerpt_then_ties_to_the_gap(self) -> None:
        why = se.compose_evidence_why("Data Foundation", GREENSTONE_CDO,
                                      "P4C1", 1.8, 2.6)
        assert why is not None
        # the fact is stated…
        assert "CIO role" in why
        # …then interpreted against the subcap's maturity standing
        assert "1.8/5" in why
        assert "peer median" in why
        # NOT the old verbatim-dump lead
        assert "The linked evidence records" not in why

    def test_finding_wwsw_why_is_interpreted_not_dumped(self) -> None:
        out = se.finding_wwsw(
            "Claims Experience", "Claims handling is strong.", "P2C3.1.3",
            2.4, 3.0, evidence_excerpt=ACUITY_NAIC)
        assert "The linked evidence records" not in out["why"]
        assert "NAIC complaint index 0.66" in out["why"]     # read the evidence
        assert out["why"].rstrip()[-1] in ".!?\"”')]"        # terminal punctuation

    def test_above_peer_excerpt_gets_protect_framing(self) -> None:
        why = se.compose_evidence_why("Claims Satisfaction", ACUITY_CLAIMS,
                                      "P2C3", 3.6, 2.9)
        assert why is not None
        assert "96% claims satisfaction" in why
        # polarity contract, frame-pool tolerant: reads as strength, not gap
        assert re.search(r"at or ahead|level with or ahead|proof|asset", why)
        assert "holding" not in why and "under the" not in why

    def test_no_usable_fact_returns_none(self) -> None:
        assert se.compose_evidence_why("X", "BI/Analytics:", "P4C2", 2.0, 3.0) is None


# ── 3. topical ranking beats tier-alone ─────────────────────────────────────

class TestTopicalRanking:
    def test_topical_excerpt_beats_higher_tier_offtopic(self) -> None:
        # SQL delivers tier-first order: the AM-Best row (a higher-tier award)
        # arrives BEFORE the on-topic cyber row. Topical ranking must still pick
        # the cyber excerpt for a Cyber-Risk card (the diagnosed mismatch).
        pairs = [
            ("E-002", "AM Best Financial Strength Rating A+ Superior for 23rd "
                      "consecutive year, top 19 carriers nationally"),
            ("E-118", "Cyber insurance sublimit and board-reviewed risk "
                      "appetite statement updated annually"),
        ]
        ranked = _rank_card_excerpts("Cyber Risk Appetite", pairs)
        assert ranked[0][0] == "E-118"               # topical wins over tier

    def test_header_only_rows_are_dropped(self) -> None:
        pairs = [("E-1", "BI/Analytics:"), ("E-2", ACUITY_SEMCI)]
        ranked = _rank_card_excerpts("Agent Interface", pairs)
        assert [e for e, _x, _f in ranked] == ["E-2"]

    def test_ties_fall_back_to_tier_order(self) -> None:
        # neither excerpt shares tokens with the name → the SQL (tier) order,
        # i.e. the first pair, is preserved.
        pairs = [("E-1", ACUITY_HIRE + " across the enterprise workforce"),
                 ("E-2", ACUITY_CLAIMS)]
        ranked = _rank_card_excerpts("Board Governance Cadence", pairs)
        assert ranked[0][0] == "E-1"


# ── 4. evidence-first card WHAT + the HARD gate ────────────────────────────

class TestEvidenceFirstCard:
    def test_what_leads_with_fact_score_is_trailing_context(self) -> None:
        fact = se.normalize_excerpt_fact(ACUITY_SEMCI)
        what = _evidence_first_what("Acuity", "Agent Interface", "P2", 2.1, 2.8, fact)
        assert what.startswith("SEMCI")             # evidence leads, not the score
        # score present but as trailing context (last sentence)
        assert "2.1 out of 5" in what
        assert what.index("SEMCI") < what.index("2.1 out of 5")
        assert not re.search(r"P[1-4]C\d", what)    # jargon-free

    def test_full_card_blob_passes_the_hard_gate(self) -> None:
        name, sid, sc, pr = "Cyber Risk Appetite", "P1C2.1", 2.0, 3.5
        ex = ("Cyber insurance sublimit and board-reviewed risk appetite "
              "statement updated annually")
        fact = se.normalize_excerpt_fact(ex)
        what = _evidence_first_what("Acuity", name, "P1", sc, pr, fact) + " [E-002]."
        why = se.compose_evidence_why(name, ex, sid, sc, pr)
        why = why.rstrip(".") + " [E-118]."
        sowhat = ("Make Cyber Risk Appetite a near-term focus for Acuity: invest "
                  "to lift it toward the 3.5 peer benchmark [E-002].")
        blob = f"{what}\n\n{why}\n\n{sowhat}"
        v = rubric_score(blob, evidence_ids=["E-002", "E-118"],
                         evidence_excerpts={"E-118": ex}, enforce_score_echo=True)
        assert v["pass"], v
        assert v["scores"]["incorporation"] == 1.0
        assert v["scores"]["score_echo"] >= 0.5
        assert markdown_lint(blob) == []


# ── 5. score-echo + incorporation gates ────────────────────────────────────

# The diagnosis's VERBATIM shipped card whys (a33fe499 confirmed_symptoms).
BAD_ECHO_1 = ("At 1.5 out of 5, Privacy-Preserving Analytics sits 1.8 points "
              "below the 3.3 typically seen at comparable institutions — an "
              "early-stage capability with the widest distance to close, so "
              "progress here compounds across the rest of the business "
              "[E-110, E-136].")
BAD_ECHO_2 = ("At 3.0 out of 5, capability dimension 13 sits 0.3 points below "
              "the 3.3 typically seen at comparable institutions, so progress "
              "here compounds across the rest of the business [E-085, E-074].")


class TestScoreEchoGate:
    def test_detector_flags_the_diagnosis_template_sentences(self) -> None:
        assert _is_score_restatement(BAD_ECHO_2) is True
        assert _is_score_restatement(
            "At 1.5 out of 5, Privacy-Preserving Analytics sits 1.8 points "
            "below the 3.3 typically seen at comparable institutions.") is True

    def test_detector_passes_evidence_tied_score_prose(self) -> None:
        # the SAME score facts, but tied to a concrete finding → not an echo.
        assert _is_score_restatement(
            "That is the substance behind Data Foundation's 1.8/5, 0.8 points "
            "under the 2.6 peer median.") is False

    def test_enforced_gate_rejects_the_bad_whys(self) -> None:
        for bad in (BAD_ECHO_1, BAD_ECHO_2):
            v = rubric_score(bad, evidence_ids=["E-110", "E-136", "E-085",
                                                "E-074"], enforce_score_echo=True)
            assert v["pass"] is False, bad

    def test_unenforced_callers_are_unaffected(self) -> None:
        # existing rubric callers (no enforce flag) never newly fail on echo.
        v = rubric_score(BAD_ECHO_2, evidence_ids=["E-085", "E-074"])
        assert not any(f.startswith("score_echo") for f in v["flags"])

    def test_incorporation_kills_citation_washing(self) -> None:
        # an AM-Best excerpt stapled onto a Cyber-Risk score sentence: the
        # cited E-ID shares no tokens with its sentence.
        washed = ("At 2.0 out of 5, Cyber Risk Appetite sits 1.5 points below "
                  "the 3.5 peer median [E-002].")
        v = rubric_score(washed, evidence_ids=["E-002"], evidence_excerpts={
            "E-002": "AM Best Financial Strength Rating A+ Superior for 23rd "
                     "consecutive year top 19 carriers nationally"})
        assert v["scores"]["incorporation"] == 0.0
        assert any(f == "citation_washing:E-002" for f in v["flags"])
        assert v["pass"] is False


# ── 6. compose_scqa_deep argued Complication ───────────────────────────────

def _scqa_bundle(**over) -> dict:
    b = {
        "name": "Acuity Insurance", "label": "mutual insurer", "aum_usd": 5.2e9,
        "aum_basis": "premium_volume", "regulator": "NAIC", "headcount": 1700,
        "founded": 1925, "overall": 2.4, "trend": "ACCELERATING", "cagr_pct": 8.2,
        "ratio_bits": ["combined ratio 92.0%"], "fin_eids": ["E-004"],
        "gaps": [
            {"name": "Data Foundation", "cat": "P4C1", "score": 1.9, "peer": 2.8,
             "eids": ["E-141", "E-047"],
             "excerpt": "Three production core systems retained through "
                        "acquisitions with no member 360 view"},
            {"name": "AI & Decisioning", "cat": "P4C3", "score": 2.0, "peer": 2.7,
             "eids": ["E-283"]},
        ],
        "strengths": [{"name": "Claims Experience", "score": 3.6, "peer": 2.9}],
        "issues": [
            {"title": "Open AML consent order remediation through Q4 2026",
             "severity": "high", "eids": ["E-218"]},
            {"title": "run_manifest.json missing 'evidence_mode' key",
             "severity": "high", "eids": ["E-9"]},
        ],
        "leadership": {"new_hires": [("Dana Field", "Chief Data Officer")],
                       "gap_roles": [], "n": 7},
        "platforms": [{"name": "Salesforce", "fit": 82.0,
                       "top_subcap": "Omnichannel Orchestration"},
                      {"name": "Databricks", "fit": 74.0, "top_subcap": None}],
        "focus_quote": "Unify the customer data layer ahead of the core go-live.",
        "base_eids": ["E-001", "E-002", "E-003"],
    }
    b.update(over)
    return b


class TestScqaArgumentStructure:
    def test_complication_fuses_gap_with_its_evidence_fact(self) -> None:
        out = se.compose_scqa_deep(_scqa_bundle())
        md = out["md"]
        # score + the concrete finding that explains it + [E-ID]
        assert "Data Foundation" in md and "1.9/5" in md
        assert "Three production core systems retained through acquisitions" in md
        assert "E-141" in md
        # the old score-ladder lead-ins are gone
        assert "The deepest capability gap is" not in md
        assert "Next is" not in md and "Third is" not in md

    def test_pipeline_leak_issue_titles_filtered(self) -> None:
        out = se.compose_scqa_deep(_scqa_bundle())
        assert "run_manifest" not in out["md"]
        assert "evidence_mode" not in out["md"]
        # the real client issue still lands
        assert "AML consent order" in out["md"]

    def test_analyst_quote_no_double_punctuation_and_tied(self) -> None:
        out = se.compose_scqa_deep(_scqa_bundle())
        assert '.".' not in out["md"] and '."."' not in out["md"]
        # the quote is followed by an interpretive clause, not left bare
        assert "sequencing" in out["md"].split("\n\n")[-1]

    def test_scqa_stays_lint_clean_and_rubric_passes(self) -> None:
        out = se.compose_scqa_deep(_scqa_bundle())
        assert markdown_lint(out["md"]) == []
        v = rubric_score(out["md"], evidence_ids=out["eids"],
                         numbers_in_scope=out["numbers"])
        assert v["pass"], v

    def test_w6_sequencing_reason_names_second_platform_prerequisite(self) -> None:
        # W6: the exec summary answers "which comes first, and why" — when the
        # #2 platform waits on #1 in the DAG AND carries an unmet prerequisite,
        # that prerequisite is named (provider-neutral: #2 "follows once its …
        # prerequisite is in place", never "#1 supplies it").
        b = _scqa_bundle(platforms=[
            {"name": "Salesforce", "fit": 82.0, "top_subcap": "Omnichannel",
             "seq_after": [], "gate": None},
            {"name": "Databricks", "fit": 74.0, "top_subcap": "Lakehouse",
             "seq_after": ["Salesforce"], "gate": "a governed data foundation"},
        ])
        md = se.compose_scqa_deep(b)["md"]
        assert "Databricks follows once its a governed data foundation " \
               "prerequisite is in place" in md or \
               ("Databricks follows once its" in md and "prerequisite is in place" in md)

    def test_w6_extra_facts_weave_a_fieldwork_sentence(self) -> None:
        # W6: mined fieldwork themes weave in as a corroborating fact — but as
        # a GROUNDING FLOOR only, when the gaps themselves carried no concrete
        # excerpt. The 2026-07-14 anti-stapling cap fires the extra fact only
        # then: a second "from the file" lead-in stacked on top of gap facts is
        # the fact-dump the operator flagged.
        b = _scqa_bundle(
            gaps=[
                {"name": "Data Foundation", "cat": "P4C1", "score": 1.9,
                 "peer": 2.8, "eids": ["E-141"]},
                {"name": "AI & Decisioning", "cat": "P4C3", "score": 2.0,
                 "peer": 2.7, "eids": ["E-283"]},
            ],
            extra_facts=[
                {"fact": "Fitch affirmed the entity at BBB with a stable outlook "
                         "in December 2025 on strong asset quality",
                 "eids": ["E-777"]}])
        md = se.compose_scqa_deep(b)["md"]
        assert "Fitch affirmed the entity at BBB" in md
        assert "E-777" in md

    def test_gap_without_excerpt_is_argued_not_laddered(self) -> None:
        b = _scqa_bundle()
        b["gaps"][0].pop("excerpt")
        out = se.compose_scqa_deep(b)
        md = out["md"]
        assert "The deepest capability gap is" not in md
        assert "Data Foundation" in md and "1.9/5" in md


# ── 7. subcap rationale readability ────────────────────────────────────────

class TestSubcapRationale:
    def _facts(self, **over) -> SubcapFacts:
        base = {
            "subcap_id": "P4C1.1.1", "name": "Data Governance Baseline",
            "score": 1.9, "band": "M2", "peer_median": 2.8,
            "evidence_count": 3, "evidence_e_ids": ["E-137", "E-141"],
            "evidence_excerpts": [
                "ARCU data warehouse provides enterprise data architecture "
                "with consistent business definitions and automated reporting",
                "Oracle Siebel CRM holds the customer master data"],
            "insight_titles": [], "rec_titles": [],
        }
        base.update(over)
        return SubcapFacts(**base)

    def test_rationale_is_framed_prose_not_a_quote_dump(self) -> None:
        out = compose_subcap_narrative(self._facts())
        assert "Grounding [E-" not in out            # the old quote-dump form
        assert "ARCU data warehouse" in out          # the substance is read in
        assert "E-137" in out
        # tied to the cell's standing (interpretation)
        assert "the M2 score rests on" in out

    def test_rationale_is_markdown_lint_clean(self) -> None:
        assert markdown_lint(compose_subcap_narrative(self._facts())) == []


# ── 8. W8 verbatim-vet residuals (exec-summary hygiene) ─────────────────────

class TestW8ExecSummaryHygiene:
    def test_proofread_heals_label_strip_paren_husk(self) -> None:
        # "(: 1.66" — a paren whose leading label resolved away — heals to
        # a clean "(1.66" (2026-07-14 vet, 1 client kept summary).
        out = proofread("Digital Marketing and Acquisition (: 1.66 vs. 2.25 "
                        "peer median) is the lowest-scoring category here.")
        assert "(: " not in out and "(1.66" in out

    def test_strip_scqa_scaffolding_drops_framework_banner(self) -> None:
        # a bare "SCQA FRAMEWORK" heading the analyst placed above the prose
        # must not lead the exec summary (2026-07-14 vet, 1 client).
        body = ("SCQA FRAMEWORK\n\nThe institution is mid-transformation with "
                "real room to grow across its data foundation this year.")
        out = se.strip_scqa_scaffolding(body)
        assert not out.lstrip().startswith("SCQA")
        assert not se.scqa_has_scaffolding(out)
        # the existing Situation/Complication label strip still fires
        assert se.strip_scqa_scaffolding(
            "Situation: the bank is mid-transformation with room to grow.") == ""
