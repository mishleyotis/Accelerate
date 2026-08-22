"""W6 — what a source may be used to establish.

Every case here is drawn from one promoted run that reached a regulated
client's dashboard, and every one of these rules existed in prose in the
assessment method while nothing enforced it. The negative controls are
therefore not synthetic: they are the exact shapes that shipped.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import source_rules as SR


# ── tier discipline ───────────────────────────────────────────────────
def test_the_fortinet_page_cannot_be_t1():
    """Five cells in the run's only Differentiating category took their
    only evidence from a vendor customer-story page registered T1 at ERS
    4.20, where the tier table makes vendor collateral T5, ceiling L2."""
    url = "https://www.fortinet.com/customers/odlum-brown"
    assert SR.vendor_collateral(url) == "a vendor's customer-story page"
    for tier in ("T1", "T2", "T3", "T4"):
        flaw = SR.tier_violation(url, tier)
        assert flaw and flaw.startswith("tier_too_high:"), tier
        assert "T5" in flaw and "L2" in flaw, "the refusal names the ceiling"
    assert SR.tier_violation(url, "T5") is None, \
        "the source is legitimate evidence AT ITS OWN TIER"


@pytest.mark.parametrize("url,kind", [
    ("https://vendor.com/case-studies/big-bank", "a vendor case study"),
    ("https://vendor.com/success-stories/cu", "a vendor success story"),
    ("https://vendor.com/press-releases/2026/launch", "a press release"),
    ("https://vendor.com/newsroom/partnership", "a newsroom item"),
    ("https://vendor.com/products/core-banking", "a vendor product or solution page"),
    ("https://vendor.com/blog/why-modernise", "vendor-published marketing content"),
])
def test_the_collateral_shapes(url, kind):
    assert SR.vendor_collateral(url) == kind


def test_an_institutions_own_artefact_is_untouched():
    """The rule is shape-based on the PATH, not a vendor allowlist — a
    list is wrong about every vendor not on it. But it must not catch a
    regulator's register or a filing."""
    for url in ("https://www.ciro.ca/about-ciro/board-directors/x",
                "https://www.sec.gov/Archives/edgar/data/1/0001.htm",
                "https://ncua.gov/analysis/credit-union-corporate-call-report",
                "https://odlumbrown.com/annual-report-2025.pdf"):
        assert SR.vendor_collateral(url) is None, url
        assert SR.tier_violation(url, "T1") is None, url


# ── an absence is not a capability ────────────────────────────────────
def test_e112_the_clean_record_scored_as_a_control():
    """`E-112` turned 'a search returned NO disciplinary actions' into a
    4.0-4.5 capability score on four cells."""
    span = ("A search of the regulator's disciplinary database returned no "
            "disciplinary actions against the firm or its registrants over "
            "the review period.")
    assert SR.absence_span(span) is True
    flaw = SR.absence_as_capability(span, "FACT")
    assert flaw and flaw.startswith("absence_is_not_capability:")
    # …and it registers happily as what it IS.
    assert SR.absence_as_capability(span, "INFERENCE") is None


def test_the_positive_rephrasing_of_the_same_absence():
    """The adversarial pass defeated a negation rule by moving the negation
    into a noun: 'records a clean supervisory history' is the same finding
    as 'no disciplinary actions' and scored the same way."""
    assert SR.absence_span(
        "The firm records a clean supervisory history across the period.") is True
    assert SR.absence_span(
        "No records were found in the enforcement database.") is True
    assert SR.absence_span(
        "A review of filings disclosed nothing of note.") is True


def test_a_real_control_description_is_not_an_absence():
    """The false-positive control: prose DESCRIBING a control must pass."""
    for span in ("The firm operates automated trade surveillance with daily "
                 "exception review by the compliance team.",
                 "Communications surveillance covers email and chat, with "
                 "lexicon-based alerting and quarterly tuning.",
                 "No fewer than three independent reviews are performed each "
                 "quarter under the documented policy."):
        assert SR.absence_span(span) is False, span
        assert SR.absence_as_capability(span, "FACT") is None, span


# ── a relation is not a capability ────────────────────────────────────
def test_the_form_adv_subsidiary_span_is_noted_not_refused():
    """Thirty of fifty-two top-band cells rested on a subsidiary's officer
    list. The plan's first proposal was an entity-SIZE gate; the stress
    test refuted it — no field carries entity size, and parent and
    subsidiary share a name, so the domain check passes. What is
    checkable is the CLAIM the relation can carry."""
    span = ("OB USA was formed in 2005 and is wholly owned by Odlum Brown "
            "Limited, an investment dealer incorporated in British Columbia.")
    assert SR.relation_span(span) is True
    note = SR.relation_note(span)
    assert note and note.startswith("relation_scope:")
    assert "ownership" in note and "operational capability" in note
    # A NOTE, never a refusal: this span is the right evidence for ownership.
    assert SR.tier_violation("https://adviserinfo.sec.gov/firm/1", "T1") is None


def test_prose_about_the_assessed_entity_carries_no_relation_note():
    assert SR.relation_note(
        "The firm operates a documented incident response plan reviewed "
        "annually by its technology committee.") is None


# ── one document, many cells ──────────────────────────────────────────
def test_the_document_key_survives_a_split_filing():
    """A per-EVIDENCE-ID cap was defeated in the adversarial pass by
    splitting one filing into eight registered ids with eight verbatim
    spans and one URL. The key is the canonicalised document."""
    same = ("https://www.sec.gov/Archives/edgar/data/1/f.htm",
            "http://sec.gov/Archives/edgar/data/1/f.htm",
            "https://sec.gov/Archives/edgar/data/1/f.htm?page=4",
            "https://sec.gov/Archives/edgar/data/1/f.htm#item1a",
            "https://www.sec.gov/Archives/edgar/data/1/f.htm/")
    keys = {SR.canonical_document(u) for u in same}
    assert len(keys) == 1, keys
    assert SR.canonical_document(
        "https://sec.gov/Archives/edgar/data/2/g.htm") not in keys


class _Cur:
    """scored cells, then the sole-evidence count — in call order."""

    def __init__(self, scored, sole):
        self.answers = [(scored,), (sole,)]

    def execute(self, *_a, **_k):
        pass

    def fetchone(self):
        return self.answers.pop(0)


def test_the_line_is_sole_evidence_and_not_reach():
    """The measurement that changed this rule. Capping total REACH at 30%
    refuses the reference client's broadest document (411 of 765 cells,
    53.7%, a legitimate call report) and passes the run the rule exists
    for (186 of 709, 26.2%). Counting cells for which a document is the
    ONLY citable source separates them: Baxter's worst is 49 of 765
    (6.4%), Odlum's 74 of 709 (10.4%), the corpus p99 13.3% and its worst
    85.0%. 20% sits above p99 and clear of both clients."""
    assert SR.SOLE_EVIDENCE_PCT == 20.0
    # Baxter's broadest document: reaches 411, sole for 49 — passes.
    assert SR.sole_evidence_reach(_Cur(765, 49), "run", "E-1",
                                  "https://x.com/callreport", ["P1C1.1.1"]) is None
    # Odlum's worst: sole for 74 of 709 — passes, and is not what this
    # rule was ever able to catch. Recorded rather than pretended.
    assert SR.sole_evidence_reach(_Cur(709, 74), "run", "E-046",
                                  "https://x.com/10k.htm", ["P1C1.1.1"]) is None
    # The adversarial payload: one Form ADV the sole voice for 82%.
    flaw = SR.sole_evidence_reach(_Cur(709, 581), "run", "E-1",
                                  "https://adviserinfo.sec.gov/firm/1",
                                  ["P1C1.1.1"])
    assert flaw and flaw.startswith("sole_evidence_reach:")
    assert "581 of 709" in flaw and "81.9%" in flaw
    # the refusal says the mint survives — a producer never loses a
    # verified span to this rule, only the further cells
    assert "the registration stands" in flaw.lower()
    # …and it says breadth is not the defect, so the repair is corroboration
    assert "53.7%" in flaw and "legitimate" in flaw


def test_a_run_with_no_scored_cells_has_no_line():
    """0 of 0 is not 100%: with no denominator the rule abstains rather
    than refusing everything (invariant 9)."""
    assert SR.sole_evidence_reach(_Cur(0, 0), "run", "E-1",
                                  "https://x.com/a", ["P1C1.1.1"]) is None


def test_a_registration_with_no_new_links_is_not_measured():
    assert SR.sole_evidence_reach(_Cur(709, 700), "run", "E-1",
                                  "https://x.com/a", []) is None


# ── the publisher class the path cannot express ────────────────────────
#
# The vendor rule reads the path and throws the host away. `/newsroom/`
# and `/press-release/` are also how a REGULATOR publishes, and measured
# 2026-08-16 a producer was refused at T1 and again at T2 on
# `ncua.gov/newsroom/press-release/…` — the prudential regulator of the
# credit union being assessed — with "a vendor's own page is evidence of
# what the VENDOR says". The only way past was to register a T1 regulator
# at T5, understating the tier and depressing the rank score: the
# score-suppression the tier rules exist to prevent, running backwards.

REGULATOR_PRESS = ("https://ncua.gov/newsroom/press-release/2025/"
                   "credit-union-system-performance-data")


def test_A_REGULATORS_PRESS_RELEASE_IS_NOT_VENDOR_COLLATERAL():
    assert SR.vendor_collateral(REGULATOR_PRESS) is None
    assert SR.tier_violation(REGULATOR_PRESS, "T1") is None
    assert SR.tier_violation(REGULATOR_PRESS, "T2") is None


def test_the_regulator_exemption_covers_the_shapes_that_caught_it():
    for url in ("https://ncua.gov/newsroom/press-release/2025/x",
                "https://www.fdic.gov/news/press-releases/2025/x.html",
                "https://occ.gov/newsroom/news-releases/2025/x.html",
                "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
                "https://osfi-bsif.gc.ca/en/news/x",
                "https://www.fca.org.uk/news/press-releases/x"):
        assert SR.vendor_collateral(url) is None, url


def test_A_VENDOR_IS_STILL_A_VENDOR():
    """The exemption must not become a hole. Everything the rule was
    written for keeps failing exactly as before."""
    for url in ("https://fortinet.com/customers/some-credit-union",
                "https://engageware.com/case-studies/some-cu",
                "https://vendor.com/newsroom/2025/partnership",
                "https://vendor.com/press-releases/2025/launch",
                "https://vendor.com/success-stories/x",
                "https://vendor.com/products/scheduling"):
        assert SR.vendor_collateral(url) is not None, url
        assert SR.tier_violation(url, "T1") is not None, url


def test_a_lookalike_host_does_not_buy_the_exemption():
    """Matching is on the registrable suffix, not a substring: a rule that
    accepted `ncua.gov.example.com` would hand any vendor the exemption
    for the price of a subdomain."""
    for url in ("https://ncua.gov.example.com/newsroom/x",
                "https://notgov/newsroom/x",
                "https://mygov.com/press-releases/x",
                "https://fake-fca.org.uk.evil.com/news/press-releases/x"):
        assert not SR.regulatory_publisher(url), url
    assert SR.vendor_collateral("https://ncua.gov.example.com/newsroom/x")


def test_a_regulator_subdomain_qualifies():
    assert SR.regulatory_publisher("https://www.ncua.gov/newsroom/x")
    assert SR.regulatory_publisher("https://data.fdic.gov/press-releases/x")


def test_no_url_is_not_a_regulator():
    assert not SR.regulatory_publisher(None)
    assert not SR.regulatory_publisher("")
    assert not SR.regulatory_publisher("not-a-url")


# ── A machine technographic scan is T1 (MEM-0087) ──────────────────────
#
# The mirror image of the Fortinet case above. That one is a weak source
# claimed strong and it reads like a defect on sight. This one is a STRONG
# source filed weak, and it reads like a thin client — which is why it sat
# in four documents as a warning and in no code as a check.

def test_the_scan_that_was_filed_t4():
    """The exact registration that shipped: T4 on a technographic scan."""
    name = "Company technographic scan of logixbanking.com, third pass 2026-08-18"
    flaw = SR.scan_tier_violation(name, "T4")
    assert flaw and flaw.startswith("tier_too_low:"), flaw
    # The refusal has to name the ceiling, not just the tier, because the
    # consequence is what the producer needs in order to act.
    assert "CONFIRMED" in flaw and "T1" in flaw


@pytest.mark.parametrize("name", [
    "Explorium enrich-business-technographics for logixbanking.com",
    "BuiltWith technology profile, retrieved 2026-08-18",
    "Wappalyzer scan of the client domain",
    "HG Insights technographic enrichment",
    "Clay technographic data point",
    "webstack scan of www.example.com",
])
def test_the_scan_shapes(name):
    assert SR.scan_tier_violation(name, "T3"), name
    assert SR.scan_tier_violation(name, "T1") is None, name


def test_a_document_about_a_scan_is_not_a_scan():
    """The escape hatch the refusal itself names, and it has to work.

    A vendor's blog post discussing technographic data is a T5 marketing
    page; refusing it for being filed below T1 would be the rule inverting
    into the very error it exists to prevent.
    """
    for name in ("Siemens case study naming the client's data preparation stack",
                 "NCUA call report, 2026 Q1",
                 "Logix Federal Credit Union job description, Programmer Analyst IV",
                 "CUInsight press release on fraud operations"):
        assert SR.scan_tier_violation(name, "T5") is None, name
        assert SR.scan_tier_violation(name, "T3") is None, name


def test_the_rule_reads_origin_when_the_name_is_silent():
    assert SR.scan_tier_violation("logixbanking.com", "T4",
                                  origin="explorium") is not None
    assert SR.scan_tier_violation("logixbanking.com", "T4") is None


def test_no_tier_and_no_name_are_not_violations():
    assert SR.scan_tier_violation(None, "T4") is None
    assert SR.scan_tier_violation("BuiltWith profile", None) is None
    assert SR.scan_tier_violation("", "") is None
