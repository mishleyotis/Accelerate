"""The content detectors, measured against the batteries that condemned them.

Each battery is the one the audit used. The assertions are on RECALL and
PRECISION, not on "it runs" — a detector whose miss rate is unstated is a
detector that gets waived away the first time it is inconvenient."""
import pytest

from engine import quality as Q


# ── AUD-0079 · absence detection ──────────────────────────────────────────
#
# The old pattern was \b(no |not evidenced|absent|does not exist|
# nothing (was )?found|zero ) and scored 4/14 recall with 3/3 false
# positives on these exact sentences.

ABSENCE_BATTERY = [
    "The institution has no documented segment-strategy artefact.",
    "A refresh cadence is not evidenced in any public filing.",
    "A chief data officer is absent from the published leadership roster.",
    "A published API catalogue does not exist for this institution.",
    "Nothing was found describing a model-risk committee.",
    "Zero disclosures were found naming a data-governance owner.",
    "The institution lacks any documented segment-strategy artefact.",
    "We found nothing on a formal architecture review board.",
    "A board-level technology charter is missing from the governance pack.",
    "A cloud migration programme does not appear in any annual report.",
    "The claim is unevidenced across every tier searched.",
    "Neither the annual report nor the proxy statement names a CDO.",
    "There is an absence of any published data-quality standard.",
    "A refresh cadence was never established in public disclosure.",
    "The filings are silent on third-party model validation.",
    "Nothing in the filings describes a customer-data platform.",
    "A digital operating model could not be established from public sources.",
    "We did not find a published cyber-incident playbook.",
    "We were unable to locate a technology risk appetite statement.",
]

PRESENCE_DECOYS = [
    "The programme has run for no fewer than six consecutive quarters.",
    "There is no doubt that the migration completed on schedule.",
    "An absent-minded reviewer approved the change, which was later corrected.",
    "The platform is no longer on the legacy stack, having migrated in 2024.",
    "Delivery is expected no later than the third quarter of 2026.",
    "The board reviews the roadmap no more than twice a year, and did so in 2025.",
    "The institution is second to none on mobile adoption in its peer set.",
]


def test_absence_recall_is_total_on_the_battery_that_condemned_the_old_one():
    missed = [s for s in ABSENCE_BATTERY if not Q.claims_absence(s)]
    assert missed == [], f"missed {len(missed)} of {len(ABSENCE_BATTERY)}: {missed}"


def test_absence_does_not_fire_on_presence_sentences():
    false_pos = [s for s in PRESENCE_DECOYS if Q.claims_absence(s)]
    assert false_pos == [], f"false positives: {false_pos}"


def test_the_two_phrasings_the_gate_used_to_disagree_about_now_agree():
    """'has no documented artefact' fired the gate; 'lacks any documented
    artefact' did not, and the same claim shipped undeclared."""
    a = "The institution has no documented segment-strategy artefact."
    b = "The institution lacks any documented segment-strategy artefact."
    assert Q.claims_absence(a) is Q.claims_absence(b) is True


# ── AUD-0009 / 0016 / 0019 / 0026 · form-filling ─────────────────────────

SKELETON_FIELDS = {
    "dominant_claim": "STUB_CLAIM: what this subcapability establishes",
    "triangulation": "STUB_TRIANGULATION across sources [E-000] and [E-000]",
    "ceiling_reasoning": "STUB_CEILING reasoning goes here",
    "why_it_matters": "STUB_WHY this matters to the client",
    "dma_impact": "STUB_IMPACT on the maturity assessment result",
}


def test_every_field_of_the_skeleton_is_caught():
    """AUD-0009 measured 5 of 6 skeleton fields satisfying their minLength,
    and the sixth simply dropped because it was not in `required`."""
    for name, text in SKELETON_FIELDS.items():
        assert Q.is_boilerplate(text), f"{name} passed as substantive"


@pytest.mark.parametrize("text", [
    "", "   ", "n/a", "-", "TBD", "TODO: write this up",
    "placeholder", "lorem ipsum dolor sit amet consectetur adipiscing elit",
    "evidence evidence evidence evidence evidence evidence evidence evidence",
])
def test_the_cheap_ways_through_the_old_gate_are_all_refused(text):
    assert Q.is_boilerplate(text)


def test_fluent_prose_that_names_nothing_checkable_is_refused():
    """AUD-0026: gate output byte-identical to the golden fixture on a
    synthesis with no content."""
    fluent = ("The organization demonstrates capabilities in this area and "
              "further research is needed to determine the extent to which "
              "these capabilities are embedded across the enterprise.")
    assert Q.is_fluent_but_empty(fluent)


def test_a_real_synthesis_passes():
    real = ("Alkami digital banking went live in Q3 2024 and reached 47% "
            "member adoption within 90 days [E-015:F3]; the 2025 annual "
            "report restates the figure at 52%.")
    assert Q.is_boilerplate(real) is None
    assert Q.is_fluent_but_empty(real) is None


def test_a_synthesis_that_does_not_name_its_subject_is_refused():
    real = ("Digital banking went live in Q3 2024 and reached 47% adoption "
            "within 90 days [E-015:F3].")
    assert Q.is_fluent_but_empty(real, must_name=["Alkami"])


# ── AUD-0073 · the contradicts probe, read from the query ────────────────

SHIPPED_CONTRADICTS_QUERY = (
    '"Acme Credit Union" digital strategy enforcement OR lawsuit OR '
    '"yet to" OR delayed OR criticism OR abandoned'
)


def test_the_shipped_contradicts_query_is_recognised():
    """0 of 851 shipped contradicts queries contain the substring
    'contradict', which is the only thing the old detector looked for."""
    assert "contradict" not in SHIPPED_CONTRADICTS_QUERY.lower()
    assert Q.probes_contradicts(SHIPPED_CONTRADICTS_QUERY, facet="contradicts")


def test_an_empty_query_wearing_the_right_label_is_not_recognised():
    """The inverse failure: an agent that fired nothing and wrote
    facet:'contradicts' used to pass."""
    assert not Q.probes_contradicts('"Acme Credit Union" digital strategy',
                                    facet="contradicts")


# ── AUD-0080 · ladders are counted, not attested ─────────────────────────

def test_a_two_rung_ladder_is_reported_as_two_rungs():
    searches = [{"Query": "acme cdo appointment"},
                {"Query": "acme data governance owner"}]
    ladder = [{"rung": "direct", "query": "acme cdo appointment"},
              {"rung": "proxy", "query": "acme data governance owner"}]
    r = Q.ladder_report(ladder, searches)
    assert r["rungs_established"] == 2
    assert r["label"] == "2-rung ladder"


def test_a_rung_whose_query_was_never_fired_is_named_not_counted():
    searches = [{"Query": "acme cdo appointment"}]
    ladder = [{"rung": "direct", "query": "acme cdo appointment"},
              {"rung": "peer", "query": "peer credit unions cdo"},
              {"rung": "regulatory", "query": "ncua cdo guidance"}]
    r = Q.ladder_report(ladder, searches)
    assert r["rungs_established"] == 1
    assert [u["rung"] for u in r["claimed_not_fired"]] == ["peer", "regulatory"]


# ── AUD-0076 · evidence smearing ─────────────────────────────────────────

def test_one_document_cited_across_a_capability_is_reported():
    rows = [{"SubCap_ID": f"P1C1.1.{i}", "Evidence_IDs": "E-001"}
            for i in range(1, 5)]
    hits = Q.evidence_smear(rows)
    assert hits and hits[0]["capability"] == "P1C1.1"
    assert hits[0]["subcaps"] == ["P1C1.1.1", "P1C1.1.2", "P1C1.1.3", "P1C1.1.4"]


def test_the_golden_fixtures_own_smear_pair_is_below_the_sibling_threshold():
    """AUD-0076 named P1C1.1.2 / P1C1.1.5 sharing {E-001}. Two siblings is
    below the >=3 threshold R22 states, so this must NOT fire — the check
    has to be the specified one, not a stricter one that cries wolf."""
    rows = [{"SubCap_ID": "P1C1.1.2", "Evidence_IDs": "E-001"},
            {"SubCap_ID": "P1C1.1.5", "Evidence_IDs": "E-001"},
            {"SubCap_ID": "P1C1.1.1", "Evidence_IDs": "E-007,E-008,E-009"}]
    assert Q.evidence_smear(rows) == []


def test_genuinely_distinct_evidence_does_not_report():
    rows = [{"SubCap_ID": f"P1C1.1.{i}", "Evidence_IDs": f"E-00{i},E-01{i}"}
            for i in range(1, 5)]
    assert Q.evidence_smear(rows) == []


# ── AUD-0021 · proxy-only evidence is not a fact ─────────────────────────

def test_proxy_only_cannot_be_labelled_fact():
    row = {"Evidence_IDs": "NO_EVIDENCE", "Proxy_Searched": "YES",
           "Claim_Label": "FACT"}
    assert Q.proxy_only(row)
    assert "proxy" in Q.claim_label_supported(row)


def test_fact_with_no_evidence_is_refused():
    row = {"Evidence_IDs": "NO_EVIDENCE", "Proxy_Searched": "NOT_RUN",
           "Claim_Label": "FACT"}
    assert Q.claim_label_supported(row) == "FACT with no resolvable evidence id"


def test_a_cited_fact_is_accepted():
    row = {"Evidence_IDs": "E-001,E-002", "Proxy_Searched": "NOT_RUN",
           "Claim_Label": "FACT"}
    assert Q.claim_label_supported(row) is None
