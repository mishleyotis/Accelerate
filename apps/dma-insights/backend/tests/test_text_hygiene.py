"""Narrative hygiene — `plain` (single-line) + `scrub_md` (markdown-safe).

Pins the D2.6 contract: every user-facing narrative is stripped of
internal jargon (P#C# codes, E-IDs, M-band shorthand, "subcap", the
"Severity-to-Maturity Cap Matrix" label, the "*Derived from extracted
scores*" provenance footer) — and `scrub_md` does so WITHOUT flattening
the markdown structure that `plain` collapses.
"""
from __future__ import annotations

import re

from app.services.text_hygiene import plain, scrub_md

# --- plain (single-line) -------------------------------------------------

def test_plain_strips_codes_and_consultant_speak() -> None:
    dirty = (
        "Financial Wellness Scoring (P2C4) scores 1.6, a priority lever for "
        "the pillar's maturity and its cross-pillar dependencies; see "
        "E-025_CF_P3C3."
    )
    clean = plain(dirty)
    for bad in ("P2C4", "P3C3", "E-025", "priority lever", "the pillar",
                "cross-pillar"):
        assert bad not in clean, f"{bad!r} survived plain(): {clean!r}"


def test_plain_collapses_whitespace_to_single_line() -> None:
    assert plain("a\n\n  b   c") == "a b c"


# --- scrub_md (markdown-safe) -------------------------------------------

def test_scrub_md_preserves_paragraph_structure() -> None:
    """`scrub_md` must NOT flatten newlines — markdown headings/paragraphs
    survive so a multi-section body still renders."""
    md = "## Heading\n\nFirst para.\n\nSecond para."
    out = scrub_md(md)
    assert out is not None
    assert "## Heading" in out
    assert out.count("\n\n") == 2  # both paragraph breaks intact


def test_scrub_md_dejargons_per_pillar_pipe_stub() -> None:
    """The real per_pillar leak: 'Pillar Weight: 25% | Pillar Score: 2.71
    | Level: M3' — band shorthand + pillar labels stripped to plain."""
    out = scrub_md("Pillar Weight: 25% | Pillar Score: 2.71 | Level: M3")
    assert out is not None
    assert "M3" not in out
    assert "Pillar Score" not in out and "Pillar Weight" not in out
    assert "maturity level 3" in out
    assert "Score: 2.71" in out  # the real number is retained


def test_scrub_md_replaces_severity_to_maturity_cap_matrix() -> None:
    """issue_register leak: the internal methodology label is replaced
    with plain language."""
    out = scrub_md(
        "Findings may impact scores through the Severity-to-Maturity "
        "Cap Matrix."
    )
    assert out is not None
    assert "Severity-to-Maturity Cap Matrix" not in out
    assert "scoring methodology" in out


def test_scrub_md_strips_derived_provenance_footer() -> None:
    """The DERIVED-tier SCQA footer is internal provenance — never shown."""
    md = (
        "## 1. Situation\nAcme scores well.\n\n"
        "*Derived from extracted scores + recommendations (no analyst "
        "synthesis shipped).*"
    )
    out = scrub_md(md)
    assert out is not None
    assert "Derived from extracted scores" not in out
    assert "Acme scores well." in out


def test_scrub_md_strips_codes_and_evidence_ids() -> None:
    out = scrub_md("Capability P1C1.1 is weak; see E-012_AB and sub-cap X.")
    assert out is not None
    assert "P1C1.1" not in out
    assert "E-012" not in out
    assert "sub-cap" not in out.lower()
    assert "capability" in out.lower()


def test_scrub_md_preserves_parenthetical_report_citations() -> None:
    # assessment-report SCQAs cite as "(E-002, AM Best, T1)" — grounding, not
    # jargon; the E-id must survive so the narrative stays evidenced.
    out = scrub_md("A+ rating for 23 years (E-002, AM Best, T1) across 32 states.")
    assert out is not None
    assert "E-002" in out
    assert "AM Best" in out
    # …but the digit guard must not swallow real "(E-word)" prose
    assert scrub_md("an (E-commerce) platform") == "an (E-commerce) platform"


def test_scrub_md_preserves_connector_form_eids() -> None:
    # 2026-07-06 deploy review: brackets citing the EV-/INT- CONNECTOR grammar
    # (EV-P2C4-013, EV-CONN-001) went unprotected because the protect regex
    # only knew "\bE-", so the subcap-id jargon sub stripped the middle segment
    # ("EV-P2C4-013" → "EV--013"), corrupting a real citation into a dead chip
    # (empower's exec-summary under-cited traced here).
    out = scrub_md(
        "the balance sheet to fund transformation "
        "[EV-P2C4-013, EV-P1C1-007]. Reference [EV-CONN-001].")
    assert out is not None
    assert "EV-P2C4-013" in out and "EV-P1C1-007" in out
    assert "EV-CONN-001" in out
    assert "EV--" not in out  # no double-dash corruption


def test_scrub_md_cleans_stripped_id_list_comma_debris() -> None:
    # A focus quote weaving bare subcap IDs ("Priority 1 — P3C4.2.1, P3C4.3.1,
    # P3C4.4.1") strips to comma debris ("— , ,") the jargon subs don't own —
    # scrub_md must collapse it, not ship "Priority 1 —,," (empower orphan_punct).
    out = scrub_md(
        'The analyst frames the priority as "No DR runbook — Priority 1 — '
        'P3C4.2.1, P3C4.3.1, P3C4.4.1" which is the case for sequencing.')
    assert out is not None
    assert ",," not in out
    assert "— ," not in out and "—," not in out
    assert "Priority 1" in out


def test_scrub_md_none_and_empty_pass_through() -> None:
    assert scrub_md(None) is None
    assert scrub_md("") == ""
    assert scrub_md("   \n  ") is None  # whitespace-only → None


def test_plain_citation_protection_and_repair() -> None:
    """2026-07-06 deploy review: card WHAT/WHY shipped "[, ]" / "(, " / ".."
    debris because plain() stripped E-IDs with none of scrub_md's citation
    protection or repair passes. Bracketed/paren citations must survive;
    stripping bare tokens must never leave separator shells."""
    # deliberate grounding survives verbatim
    assert "[E-012]" in plain("The assessment found: “X” [E-012]. Next.")
    assert "(E-037, E-036)" in plain("Gap compounds (E-037, E-036).")
    # bare-token stripping leaves no shells or doubled stops
    out = plain("Weak area (REC-02, REQ-11). Scores M2. . Trails.")
    assert "(, " not in out and "(,)" not in out and ". ." not in out
    out2 = plain("Trails peers REC-04, . Next step E-runway.")
    assert ", ." not in out2 and "REC-04" not in out2


# --- scrubber ⊇ contract parity (systemic guard) -------------------------

# Mirror of the completeness_contract `insight_jargon` gate
# (`app/services/completeness_contract.py::_SURFACE_GAP_SQL["insight_jargon"]`).
# The qa-gates self-healing audit FAILS the deploy if any served insight-card
# field matches this. `plain()` (and `scrub_md`) MUST be a SUPERSET of it — so
# any text the scrubber passes also passes the gate. Keep these two in lockstep:
# a token added to the SQL must get a matching sub in text_hygiene._JARGON_SUBS,
# and this test proves it. (2026-07-07 deploy: "the pillars" (PLURAL) slipped
# the singular `\bthe pillar\b` sub while the SQL substring `the pillar` flagged
# it, FAILing insight_jargon on 8 clients.)
_CONTRACT_JARGON_CODE = re.compile(r"(^|[^-A-Za-z0-9])P[1-4]C[0-9]")
_CONTRACT_JARGON_PHRASE = re.compile(
    r"peer[- ]cohort|priority lever|cross[- ]pillar|the pillar|\bM5\b", re.I)


def test_plain_output_never_matches_insight_jargon_contract() -> None:
    dirty_inputs = [
        # the exact 2026-07-07 offender — PLURAL "pillars"
        "Digital Channels trails the peer cohort by 1.3 points — a competitive "
        "maturity gap that compounds across the pillars it feeds [E-032].",
        # every other contract token, in prose
        "This priority lever has cross-pillar dependencies at the pillar level.",
        "It clears the M5 best-in-class bar for P3C4 maturity.",
        "The peer-cohort median trails; a cross-pillar story anchors the pillar.",
    ]
    for dirty in dirty_inputs:
        out = plain(dirty)
        assert not _CONTRACT_JARGON_CODE.search(out), (
            f"scrubber left a raw taxonomy code the contract flags: {out!r}")
        assert not _CONTRACT_JARGON_PHRASE.search(out), (
            f"scrubber left consultant-speak the contract flags: {out!r}")
    # a legitimate E-P#C#-### / EV-P#C#-### citation is GROUNDING, not jargon —
    # it must survive intact (the contract's `[^-A-Za-z0-9]` guard skips it).
    kept = plain("Grounded in the balance-sheet evidence [E-P3C4-008] "
                 "and [EV-P2C1-010].")
    assert "E-P3C4-008" in kept and "EV-P2C1-010" in kept


# ── process-scaffolding drop belt (2026-07-14 verbatim vet) ──────────────────
# Analyst DOCX section bodies leak pipeline-internal process notes: run-id
# provenance citations, QA-protocol banners, data-borrowing disclaimers,
# structural labels. scrub_md drops the scaffolding, keeps the substance.

def test_scrub_md_strips_run_id_provenance_but_keeps_substance() -> None:
    md = ("Peer set of 5 institutions locked in research Phase 0 "
          "(DMA-RES-ACCU-MB-20260504-0001). This set spans the digital "
          "maturity spectrum — from sector-leading Meridian to sector-lagging "
          "Servus.")
    out = scrub_md(md) or ""
    assert "DMA-RES" not in out
    assert "research Phase 0" not in out
    assert "Peer set of 5 institutions" in out          # substance kept
    assert "digital maturity spectrum" in out            # substance kept
    assert "Meridian" in out and "Servus" in out


def test_scrub_md_drops_qa_protocol_banner_keeps_recommendation() -> None:
    md = ("Anti-Generic Protocol: Each recommendation is grounded in specific "
          "E-IDs. No recommendation uses forbidden phrases. Deploy Agentforce "
          "AI at Scale to resolve licence saturation.")
    out = scrub_md(md) or ""
    assert "Anti-Generic" not in out and "forbidden phrase" not in out
    assert "Deploy Agentforce AI at Scale" in out


def test_scrub_md_drops_internal_structural_label() -> None:
    md = ("[ROOT CAUSE — SITUATION] The core operates without an integration "
          "orchestration layer.")
    out = scrub_md(md) or ""
    assert "ROOT CAUSE" not in out
    assert "integration orchestration layer" in out


def test_scrub_md_all_process_body_collapses_to_none() -> None:
    # a body that is ENTIRELY provenance disclaimer → None (skeleton served)
    md = ("Borrowed from DMA-RES-CCUIL-20260504-0001 Research Report §3 per "
          "Phase 7 Data Borrowing Protocol. Assessment-layer maturity "
          "annotations added.")
    assert scrub_md(md) is None


def test_scrub_md_keeps_evidence_citations_and_legit_per() -> None:
    # run-id strip must not touch E-ID grounding chips or a legitimate "per"
    assert "E-002" in (scrub_md("Digital banking is strong (E-002, AM Best, T1).") or "")
    assert "E-059" in (scrub_md("Core is legacy [E-059, E-079].") or "")
    assert "per annum" in (scrub_md("Revenue grew 12% per annum.") or "")
    # ordinary prose mentioning the DMA program is NOT a run-id
    keep = scrub_md("A DMA-driven roadmap could raise it two levels.") or ""
    assert "DMA-driven roadmap" in keep


def test_scrub_md_drops_recommendation_methodology_preambles() -> None:
    # the analyst's own methodology/QA preamble that precedes a rec table is
    # pure process — it must not reach a client (2026-07-14 vet, 6 clients).
    preambles = [
        "ANTI-GENERIC RECOMMENDATION PROTOCOL APPLIED\nAll 8 recommendations "
        "satisfy: (1) Specific E-IDs confirm the gap; (2) Proxy searches "
        "exhausted (220+ web searches + LeadIQ technographic + Vibe entity "
        "match); (3) Maps to a named Zennify solution from the 12-solution "
        "catalog.",
        "The following recommendations are prioritized based on the 6-factor "
        "scoring framework. All recommendations have been validated via proxy "
        "searches (Clay, Explorium, web). No investment amounts per assessment "
        "policy.",
        "Each recommendation traces from evidence-grounded root cause to a "
        "Zennify solution. No investment amounts per R6 rule.",
        "All 7 recommendations confirmed absent from the tech stack. Each maps "
        "to a named Zennify solution from the 12-solution catalog.",
    ]
    for p in preambles:
        assert scrub_md(p) is None, f"preamble survived: {scrub_md(p)!r}"


def test_scrub_md_keeps_genuine_recommendation_content() -> None:
    # a real recommendation must survive the methodology-preamble belt
    keep = [
        "Deploy Agentforce AI at Scale to resolve licence saturation.",
        "This capability is confirmed absent from the tech stack — greenfield.",
        "All recommendations should be sequenced across an 18-month roadmap.",
        "The bank maps its lending workflow to Salesforce FSC today.",
    ]
    for k in keep:
        out = scrub_md(k) or ""
        assert len(out) > 20, f"real content over-stripped: {out!r}"


def test_scrub_md_drops_gap_and_peer_methodology_variants() -> None:
    # more preamble wording variants (2026-07-14 vet round 3)
    assert scrub_md(
        "Gaps were prioritized using the 6-factor priority framework: "
        "Business Impact (25%), Risk Severity (20%).") is None
    # peer-set provenance clause stripped, the peer list itself kept
    out = scrub_md(
        "Four peers were selected and locked in Research Phase (Batch 1): "
        "Auto-Owners, West Bend Mutual. Peer set is immutable per protocol.") or ""
    assert "Research Phase" not in out and "immutable" not in out
    assert "Auto-Owners" in out and "West Bend Mutual" in out


def test_scrub_md_factor_and_maps_negatives_survive() -> None:
    # a 3-factor AUTH framework and a capability-maps-to-platform sentence are
    # substance, not methodology — they must survive
    assert "authentication framework" in (
        scrub_md("The bank uses a 3-factor authentication framework.") or "")
    assert "Salesforce platform" in (
        scrub_md("Each capability maps to a Salesforce platform surface.") or "")
