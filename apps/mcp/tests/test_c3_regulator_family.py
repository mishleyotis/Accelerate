"""ET-05b — the regulatory card searches its OWN sub-vertical's regulators.

RC-06 (SWBC gold audit, 2026-10-04; D-26, slices CTX-07, CTX-09). SWBC is an
Insurance Brokers (SV7) primary run. Its C3 ladder searched FINRA, the SEC
adviser registry, the California and Texas mortgage regulators and NMLS — and
recorded the state insurance departments as "BLOCKED ... the Texas Department
of Insurance orders were not searched". The one regulator family the primary
sub-vertical answers to was the one left open, and the card promoted with
`verified: false` and nothing refusing it. The contract (C3 primary_regulator
doc) already maps sub-vertical to regulator family: SV7-SV8 State DOIs/NAIC.

The rule: the ladder (absence_of_enforcement.sources_searched and the
section's empty_state.sources_searched) carries a rung naming a regulator of
the primary sub-vertical's family whose outcome is not open (not NOT_RUN /
BLOCKED / not searched). The family map is contract data
(`regulator_family_by_subvertical`). Gold runs (SV2: NCUA rungs) pass.

Jurisdiction provenance (RC-06(e): each item cites a T1 registry or carries
"(self-described)") is NOT enforced: all three gold runs serve bare
jurisdiction strings, so it needs an owner call first (residual).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation2 import _check_c3_regulator_family as check  # noqa: E402

SWBC_LADDER = [
    "FINRA BrokerCheck firm report, CRD 133715: two disclosures found",
    "Securities and Exchange Commission adviser registry: summary page "
    "identified; disciplinary page not reached",
    "Texas Department of Savings and Mortgage Lending: the regulator's order "
    "list was not fetched, so this is a search miss, not a verified absence",
    "State insurance department registries for SWBC Life Insurance Company "
    "and SWBC Property and Casualty Insurance Company: BLOCKED, the Missouri "
    "Department of Insurance page returned access denied; the Texas "
    "Department of Insurance orders were not searched",
]


def _c3(ladder):
    return {"regulatory_standing": {
        "absence_of_enforcement": {"verified": False,
                                   "sources_searched": ladder}}}


def test_ib_primary_with_no_completed_doi_rung_is_refused():
    out = check("context", _c3(SWBC_LADDER), "IB")
    assert len(out) == 1 and out[0]["gate_id"] == "ET-05b"
    assert "insurance" in out[0]["message"].lower()


def test_ib_primary_with_a_worked_doi_rung_passes():
    ladder = SWBC_LADDER + [
        "Texas Department of Insurance commissioner orders, searched by name "
        "for SWBC Life and SWBC P&C: no order recorded — VERIFIED ABSENT"]
    assert check("context", _c3(ladder), "IB") == []


def test_the_sv2_gold_shape_passes():
    """Baxter's rung names the regulator and states no outcome token; it is
    not OPEN, and the family rule asks only that the family's rung was not
    left open."""
    ladder = ["National Credit Union Administration administrative orders "
              "and enforcement actions index",
              "the credit union's own newsroom, last 24 months"]
    assert check("context", _c3(ladder), "CU") == []


def test_a_ladder_that_never_names_the_family_is_refused():
    out = check("context", _c3(["FINRA BrokerCheck — RESOLVED"]), "CU")
    assert len(out) == 1


def test_the_family_map_is_contract_data():
    rs = sections("context")["regulatory_standing"]
    fam = rs["regulator_family_by_subvertical"]
    assert set(fam) == {"RB", "CU", "CL", "CIB", "RIA", "AM", "IB", "IC", "FC"}


def test_unknown_sub_vertical_and_other_pages_are_untouched():
    assert check("context", _c3(SWBC_LADDER), None) == []
    assert check("overview", _c3(SWBC_LADDER), "IB") == []
