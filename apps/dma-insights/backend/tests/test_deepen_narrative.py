"""D2: deepen_narrative insight cards are opportunity-framed AND
evidence-content-first.

The `_deep_card` template (and `_compose_insight` with no Vertex explainer
injected) must never emit the deficit language the UI/UX brief forbids
("Left unaddressed", "slipping behind", "erodes", "trails", "widens the
gap", "holding back"), must keep the numbers (score + peer delta), and
must stay jargon-free (no P#C#, M-bands, "subcap").

2026-07-06 mandate: when the card's linked evidence carries real excerpts,
the composed WHAT/WHY/SO-WHAT must ANALYZE that evidence content (systems
named, practices observed, quantified findings) with the score as
supporting context — never a score paraphrase; and a document/evidence
title ("Digital Marketing Strategy Document") must never occupy the
capability-name slot.
"""
from __future__ import annotations

import re

from app.scripts.deepen_narrative import (
    _card_facts,
    _compose_insight,
    _deep_card,
    _is_template_prose,
    _wn_audit_containment,
    dedupe_why_now_by_containment,
    set_insight_explainer,
    thread_scqa_citations,
)
from app.services import startup_enrich as se
from app.services.nlp.quality import proofread

# Mirror qa_deploy_review_audit's defect regexes VERBATIM so these tests assert
# against the exact contract the 2026-07-06 deploy-review audit enforces.
_AUDIT_PUNCT_DEBRIS = re.compile(
    r"\(\s*[,;]|\[\s*[,;]|,\s*\)|,\s*\]|\s[.,;]\s|\.\.(?!\.)|,,")
_AUDIT_EXEC_EID_RE = re.compile(
    r"\b(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}\b|\bE\d{3,4}\b")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF]")

_DEFICIT = (
    "left unaddressed", "slipping behind", "erodes", "erode", "eroding",
    "trails", "trail ", "widens the gap", "holding back", "falls behind",
    "falling behind",
)
_JARGON_RE = re.compile(r"P[1-4]C\d|\bM[1-5]\b|sub-?cap", re.I)


def _assert_clean(triple: tuple[str, str, str]) -> None:
    blob = " ".join(triple)
    low = blob.lower()
    for bad in _DEFICIT:
        assert bad not in low, f"deficit phrase {bad!r} survived: {low}"
    assert not _JARGON_RE.search(blob), f"jargon survived: {blob}"


def test_scored_below_peer_is_opportunity_framed() -> None:
    what, why, sowhat = _deep_card(
        "AAFCU", "Model Performance Monitoring", "P2", 2.5, 3.3, "",
    )
    _assert_clean((what, why, sowhat))
    combined = " ".join((what, why, sowhat))
    # operator mandate (2026-07-14): ONE score reading per card (the anchor,
    # in the WHAT), peer standing described in words — no second number.
    assert "2.5 out of 5" in what
    assert combined.count("out of 5") == 1
    assert "3.3" not in combined
    assert "comparable institutions" in what.lower() and "below" in what.lower()
    # framed as an opportunity, not a threat.
    assert "would" in why.lower()
    assert "parity with peers" in sowhat.lower() or "best practice" in sowhat.lower()


def test_all_pillars_and_bands_are_clean() -> None:
    for pillar in ("P1", "P2", "P3", "P4"):
        for sc, pr in [(1.4, 3.0), (2.6, 3.1), (3.5, 3.2), (4.4, 3.6), (3.0, None)]:
            _assert_clean(_deep_card("Client", "Some Capability", pillar, sc, pr, ""))


def test_no_score_branch_is_clean() -> None:
    _assert_clean(
        _deep_card("Client", "Some Capability", "P3", None, None,
                   "An existing description of the capability."),
    )


def test_compose_insight_without_explainer_is_template() -> None:
    # No explainer injected → byte-identical to the deterministic template.
    set_insight_explainer(None)
    args = ("Client", "Cap", "P1", 2.0, 3.0, "")
    assert _compose_insight(*args) == _deep_card(*args)


# ── Evidence-content-first composition (2026-07-06 mandate) ──────────────────

_FACTS = (
    ("E-004", "Marketing relies on a single shared inbox; campaign lists are "
              "exported manually from the core each month"),
    ("E-011", "No marketing automation platform is in place; segmentation is "
              "a static annual spreadsheet exercise"),
    ("E-061", "Website analytics are limited to page counts, with no "
              "attribution of digital campaigns to account openings"),
)


def test_deep_card_with_facts_analyzes_evidence_content() -> None:
    what, why, sowhat = _deep_card(
        "Interactive Brokers", "Digital Marketing Strategy", "P2",
        1.4, 3.2, "", _FACTS)
    _assert_clean((what, why, sowhat))
    # WHAT leads with what the evidence documents, cited — never the score.
    assert "shared inbox" in what
    assert "[E-004]" in what
    assert "out of 5" not in what
    # operator mandate (2026-07-14): AT MOST ONE score reading per card, and
    # the peer benchmark is described in words, never a second number.
    combined = " ".join((what, why, sowhat))
    assert combined.count("out of 5") == 1
    assert "3.2" not in combined            # peer median rendered qualitatively
    assert "1.4 out of 5" in why            # the single anchor lives in the WHY
    # WHY cites the second observed gap; SO-WHAT grounds the action in the
    # observed state and cites the third finding.
    assert "[E-011]" in why and "spreadsheet" in why
    assert "[E-061]" in sowhat
    assert "observed" in sowhat.lower()
    # depth floors (completeness contract)
    assert len(what) >= 160 and len(why) >= 100 and len(sowhat) >= 100


def test_deep_card_with_facts_and_no_score_stays_honest() -> None:
    what, why, sowhat = _deep_card(
        "Client", "Digital Marketing Strategy", "P2", None, None, "",
        _FACTS[:1])
    _assert_clean((what, why, sowhat))
    assert "[E-004]" in what
    assert "out of 5" not in what          # no invented score
    assert "working strength" not in why   # unscored is never framed a strength


def test_deep_card_facts_prose_is_regenerable_template() -> None:
    # Every evidence-woven field must be recognized as OUR template family so
    # a later deepen run can regenerate it (never mistaken for analyst prose).
    triple = _deep_card("Client", "Cap Name Here", "P2", 1.4, 3.2, "", _FACTS)
    for field in triple:
        assert _is_template_prose(field), field
    # …and so must the legacy score-paraphrase WHAT (production screenshot
    # class: it was previously undetected and therefore kept forever).
    legacy_what = _deep_card("Client", "Cap Name Here", "P2", 1.4, 3.2, "")[0]
    assert _is_template_prose(legacy_what)


def test_card_facts_filters_junk_and_rejects_unquotable_jargon() -> None:
    eids = ["E-1", "E-2", "E-3", "E-4"]
    excerpts = [
        "BI/Analytics: Tableau, Looker, PowerBI, Qlik, Sisense",  # label+list dump
        "The subcap P2C1.1.1 maturity for marketing automation remains basic "
        "across the retail franchise",           # jargon → cannot quote verbatim
        "(no excerpt)",
        "The 10-K discloses three production core systems retained through "
        "acquisitions, reconciled by a nightly batch process",
    ]
    facts = _card_facts(eids, excerpts)
    # The label-colon dump and the placeholder are rejected. The jargon row
    # is rejected TOO (2026-07-06 verbatim-quote mandate): the card renders
    # facts inside “…”, and scrubbing a quote would silently misquote the
    # researcher — so an excerpt that needs rewriting is never quoted.
    assert [e for e, _ in facts] == ["E-4"]
    blob = " ".join(f for _, f in facts)
    assert not re.search(r"P[1-4]C\d|sub-?cap", blob, re.I)
    assert "three production core systems" in blob


def test_card_facts_are_verbatim_spans_of_the_excerpt() -> None:
    # Verbatim-quote mandate: what lands inside “…” must be a contiguous
    # span of the (whitespace-normalized) source excerpt — no rewriting.
    long_excerpt = (
        "The bank runs three parallel loan origination systems retained "
        "through acquisitions, reconciled in spreadsheets by a nine-person "
        "operations team every month-end close. Customer data is mastered "
        "separately in the core and the CRM, with no golden record and no "
        "automated reconciliation between the two estates."
    )
    facts = _card_facts(["E-9"], [long_excerpt])
    assert facts and facts[0][0] == "E-9"
    fact = facts[0][1]
    # truncation is claim-safe: ends with an ellipsis at a sentence end
    assert fact.endswith("…")
    core = fact[:-1].strip()
    assert core.endswith(".")                      # sentence boundary, not mid-claim
    norm = re.sub(r"\s+", " ", long_excerpt)
    assert core in norm                            # verbatim contiguous span
    # a short excerpt passes through whole — verbatim, no ellipsis
    short = ("Marketing relies on a single shared inbox and campaign lists "
             "are exported manually from the core each month")
    f2 = _card_facts(["E-8"], [short])
    assert f2 and f2[0][1] == short


def test_weavable_fact_rejects_unquotable_run_on_text() -> None:
    from app.scripts.deepen_narrative import _weavable_fact
    # >200 chars with NO sentence/clause boundary anywhere — quoting would
    # force a mid-claim cut, so the fact is rejected (staple fallback).
    run_on = ("the institution continues expanding its branch light "
              "footprint while gradually consolidating operational "
              "functions into regional hubs that increasingly depend on "
              "shared services staffing models across every market it "
              "serves without any dedicated digital leadership in place")
    assert len(re.sub(r"\s+", " ", run_on)) > 200
    assert _weavable_fact(run_on) is None


def test_weavable_fact_keeps_dated_finding_leads() -> None:
    from app.scripts.deepen_narrative import _weavable_fact
    dated = ("April 2022: Odlum Brown launched a Client Insights program in "
             "partnership with an independent consultant, surveying over "
             "12,000 clients about their experience with the firm.")
    assert _weavable_fact(dated) is not None    # a dated FINDING, not a header
    # a genuine data-label header is still rejected
    assert _weavable_fact(
        "BI/Analytics: strong coverage across the analytics estate today") is None


def test_compose_insight_passes_facts_to_explainer() -> None:
    seen: dict = {}

    def _explainer(**kw):
        seen.update(kw)
        return None  # invalid → template fallback

    try:
        set_insight_explainer(_explainer)
        out = _compose_insight("Client", "Cap", "P2", 1.4, 3.2, "", _FACTS)
    finally:
        set_insight_explainer(None)
    assert seen["facts"] == _FACTS
    assert out == _deep_card("Client", "Cap", "P2", 1.4, 3.2, "", _FACTS)


# ── Capability-name leak regression (doc title in the capability slot) ───────

def test_document_title_never_occupies_the_capability_slot() -> None:
    # The catalogue names P2C1.1.1 after the ARTIFACT the researchers look
    # for. The resolver strips the artifact suffix before composition…
    resolved = se.capability_phrase("Digital Marketing Strategy Document")
    assert resolved == "Digital Marketing Strategy"
    what = _deep_card("Interactive Brokers", resolved, "P2", 1.4, 3.2, "")[0]
    # …so the WHAT never presents a document title as the capability.
    assert "Document is one of" not in what
    assert "Digital Marketing Strategy is one of" in what


def test_capability_phrase_unrecoverable_names_fall_back() -> None:
    # a pure artifact noun (or a 1-word remainder) is unrecoverable → '' and
    # the caller falls back exactly as for a missing name.
    assert se.capability_phrase("Documentation") == ""
    assert se.capability_phrase("Board Document") == ""
    # names without an artifact suffix pass through untouched
    assert se.capability_phrase("Data Foundation") == "Data Foundation"
    assert se.capability_phrase("Regulatory Reporting") == "Regulatory Reporting"


# ── polarity-safe evidence framing (2026-07-06 sample review) ────────────────

_POS_FACT = ("The bank was awarded a record partnership and launched a "
             "redesigned mobile banking experience across all branches this year")
_NEG_FACT = ("Complaints about reconciliation deficiencies persist and the "
             "manual exception queue keeps growing across operations teams")


def test_card_facts_prefers_polarity_aligned_facts_for_gap_cards() -> None:
    eids = ["E-1", "E-2"]
    excerpts = [_POS_FACT, _NEG_FACT]
    facts = _card_facts(eids, excerpts, prefer="negative")
    assert facts[0][0] == "E-2"            # documented shortfall leads
    assert _card_facts(eids, excerpts, prefer="positive")[0][0] == "E-1"
    # no preference → tier order preserved
    assert _card_facts(eids, excerpts)[0][0] == "E-1"


def test_deep_card_never_frames_positive_fact_as_observed_gap() -> None:
    # Only positive facts are linked (Alma Bank P4C3 class): the WHY must
    # acknowledge the working practice and still state the gap — never
    # narrate a positive milestone as "observed gaps".
    facts = (("E-006", _POS_FACT), ("E-007", _POS_FACT))
    _what, why, _sw = _deep_card("Alma Bank", "Technology Architecture",
                                 "P4", 1.0, 2.5, "", facts)
    assert "observed gaps" not in why.lower()
    assert "Even with that working practice on record" in why
    # ONE score reading (the anchor), peer relation in words — the "1.5 points
    # below the 2.5" double-number recital was cut per the 2026-07-14 mandate.
    assert "1.0 out of 5" in why
    assert "below the level comparable institutions" in why
    assert "2.5" not in why
    # with a documented shortfall in slot 2, the framing argues from it
    facts2 = (("E-006", _POS_FACT), ("E-007", _NEG_FACT))
    _what2, why2, _sw2 = _deep_card("Alma Bank", "Technology Architecture",
                                    "P4", 1.0, 2.5, "", facts2)
    assert "That documented state is why" in why2


def test_deep_card_positive_lead_fact_gets_bright_spot_bridge() -> None:
    # A positive fact leading a below-peer card is framed as the bright
    # spot the capability sits behind — never as the cause of the low score.
    what = _deep_card("Alma Bank", "Technology Architecture", "P4",
                      1.0, 2.5, "", (("E-006", _POS_FACT),))[0]
    assert "bright spot on record" in what
    assert "the rest of the capability sits behind it" in what
    assert "out of 5" not in what          # no score in the WHAT (anchor is WHY)
    # a neutral/negative lead keeps the direct bridge
    what2 = _deep_card("Alma Bank", "Technology Architecture", "P4",
                       1.0, 2.5, "", (("E-006", _NEG_FACT),))[0]
    assert "That observed state is what the assessment's reading reflects" in what2


def test_weavable_fact_rejects_researcher_scaffolding_lead() -> None:
    from app.scripts.deepen_narrative import _weavable_fact
    assert _weavable_fact(
        "DIRECT QUOTE from Investment Executive 2024 Brokerage Report Card: "
        "'Odlum Brown uses client onboarding tools from Broadridge'") is None


# ── 2026-07-06 deploy-review defect families (narr.punct_debris,
#    why_now.dup_pairs, exec_summary.under_cited) ─────────────────────────

def test_finding_ellipsis_and_emoji_proofread_clean() -> None:
    """narr.punct_debris=0: the finding-persist proofread pass strips the ASCII
    "..." clip artifact AND the leaked emoji the audit's _PUNCT_DEBRIS / emoji
    checks flag (the alliant / fisher / onedigital offenders)."""
    finding = {
        "what": "\U0001f3af QUBIE: ML+CV auto-underwriting for residential RE "
                "(PropTech Innovation... platform) — the deepest gap.",
        "why": "The assessment found the data governance gap... 1 of 12,191 "
               "fields classified [E-277].",
        "so_what": "Prioritize \U0001f6a8 Data Governance in the next phase.",
    }
    # exact loop the deepen_narrative findings-persist step runs
    for k in ("what", "why", "so_what"):
        finding[k] = proofread(str(finding[k])) or str(finding[k])
    blob = " ".join(finding[k] for k in ("what", "why", "so_what"))
    assert not _AUDIT_PUNCT_DEBRIS.search(finding["what"]), finding["what"]
    assert not _AUDIT_PUNCT_DEBRIS.search(finding["why"]), finding["why"]
    assert not _AUDIT_PUNCT_DEBRIS.search(finding["so_what"]), finding["so_what"]
    assert not _EMOJI_RE.search(blob), f"emoji survived: {blob!r}"
    # grounding citation is preserved (proofread never drops [E-###]).
    assert "[E-277]" in finding["why"]
    # idempotent — a second pass is a no-op.
    assert proofread(finding["what"]) == finding["what"]


def test_near_duplicate_why_now_signals_collapse_to_one() -> None:
    """why_now.dup_pairs=0: two write-ups of ONE trigger (Peoples Bank
    acquisition, completed ~ announced) at >=0.5 containment collapse to the
    stronger survivor, and the returned strip carries NO pair at/above 0.5."""
    strong = {
        "label": "Peoples Bank acquisition completed $1.5B assets",
        "strength": "STRONG", "category": "market",
        "detail": "Peoples Bank acquisition completed ($1.5B assets); combined "
                  "$3.4B. Integration planning window is open now.",
    }
    weak = {
        "label": "Peoples Bank acquisition announced",
        "strength": "SUPPORTING", "category": "market",
        "detail": "Peoples Bank acquisition announced; the combined bank "
                  "integration planning window is open now.",
    }
    distinct = {
        "label": "CEO commits to AI/ML investment",
        "strength": "STRONG", "category": "core_migration",
        "detail": "Active LLM deployment in the contact center; the CEO commits "
                  "to AI and ML process automation investment.",
    }
    # sanity: the pair really is a >=0.5 audit duplicate; the third is not.
    assert _wn_audit_containment(strong["detail"], weak["detail"]) >= 0.5
    assert _wn_audit_containment(strong["detail"], distinct["detail"]) < 0.5

    out = dedupe_why_now_by_containment([strong, weak, distinct])
    assert len(out) == 2, [s["label"] for s in out]
    labels = [s["label"] for s in out]
    assert "Peoples Bank acquisition completed $1.5B assets" in labels
    assert "Peoples Bank acquisition announced" not in labels  # weaker dropped
    # invariant: no surviving pair reaches the audit's 0.5 bar.
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            assert _wn_audit_containment(
                out[i].get("detail"), out[j].get("detail")) < 0.5


def test_scqa_threads_two_distinct_eids_from_bundle() -> None:
    """exec_summary.under_cited=0: a summary that resolves to a single cited row
    is topped up to >=2 DISTINCT E-IDs drawn ONLY from the client's own grounding
    pool — the audit's _EXEC_EID_RE count — without fabricating."""
    md = ("Bell Bank runs at 1.7/5. The pattern is corroborated across the "
          "assessment's evidence index [E-001].")
    assert len(set(_AUDIT_EXEC_EID_RE.findall(md))) < 2   # under-cited to start
    pool = ["E-100", "E-101", "E-500"]                    # real evidence rows
    out = thread_scqa_citations(md, pool)
    cited = set(_AUDIT_EXEC_EID_RE.findall(out))
    assert len(cited) >= 2, out
    # every cited id is real (existing chip or drawn from the pool) — no invention
    assert cited <= ({"E-001"} | set(pool))
    assert len(out) <= 4000
    # idempotent + honest floor: a pool that cannot supply a 2nd id is a no-op.
    assert thread_scqa_citations(out, pool) == out
    assert thread_scqa_citations("Only cites [E-001] once.", []) == \
        "Only cites [E-001] once."
