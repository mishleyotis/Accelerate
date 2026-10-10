"""CG-18b — a held must-present member is a last resort, capped and routed.

RC-04 (SWBC gold audit, 2026-10-04; defects D-04, D-06; slices OH-01, OH-07,
XC-02, XC-03). CG-18 accepted a quarantined member with any non-blank reason
as present and set no ceiling on the held share, so SWBC's firmographics
promoted with 6 of its 10 must-present members held: revenue, assets, CAGR,
branches, primary regulator and charter. The renderer then hid every held
row, so the strip showed four facts and nothing said six were missing.

Owner decision 2 (2026-10-04, binding):
  * held fields are capped at 2 or 25% of the must-present set, whichever is
    smaller;
  * known registry answers (charter, primary regulator, branches) are STATED
    — "not chartered", "regulated line by line", "no retail branches" are
    values, never absences;
  * a held reason names the registry route that was searched.

The fixtures are SHAPE-ONLY (field names, the stated/held pattern, the reason
shape); values are placeholders. SWBC is the refused shape, Baxter (1 of 15
held, the founding year, with the newsroom and the regulator record named)
the passing one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_must_present, validate_pass1  # noqa: E402

SPEC = sections("overview")["firmographics"]["fields"]["fields"]


def _f(field, value=None, reason=None):
    held = value is None
    return {"field": field, "value": value, "unit": None,
            "as_of": None if held else "2026-01-01",
            "source_e_id": "E-CC-1", "confidence": "LOW" if held else "HIGH",
            "quarantined": held, "quarantine_reason": reason}


# SWBC as promoted (run 7968492e): 4 stated, 6 held.
SWBC = [
    _f("employees", "2300"),
    _f("revenue", None, "Privately held; publishes no consolidated revenue. "
       "The one figure stated belongs to one division alone; current "
       "industry ranking tables do not list the group."),
    _f("assets", None, "No consolidated balance sheet is published; the rated "
       "insurance subsidiaries are rated by AM Best but a subsidiary's size "
       "is not the enterprise's."),
    _f("cagr", None, "Headcount is not a growth rate and no revenue or asset "
       "series is published, so no rate is computed."),
    _f("hq", "San Antonio, Texas"),
    _f("branches", None, "No branch count is stated on any page reached, so "
       "no integer is carried."),
    _f("founded", "1976"),
    _f("primary_regulator", None, "SWBC has no single primary regulator: the "
       "mortgage line is licensed by a state department, the broker-dealer is "
       "overseen by FINRA and the payments line is registered under NMLS."),
    _f("charter", None, "SWBC is not a chartered depository: each regulated "
       "line holds its own licence or registration, such as the NMLS "
       "payment-facilitator registration."),
    _f("website", "swbc.com"),
]

# Baxter Credit Union (SV2), shape as promoted: 15 fields, one held.
BAXTER = [_f(n, "x") for n in (
    "branches", "loans", "roa", "charter", "primary_regulator", "shares",
    "total_assets", "member_count", "employees", "net_worth_ratio", "hq",
    "cagr", "revenue", "website")] + [
    _f("founded", None, "Three dated records give three different years: the "
       "regulator's charter record, a registry row and the institution's own "
       "newsroom, which names the founding officer and states no year.")]


def _run(items):
    return _check_must_present("firmographics", "fields", SPEC, items, False)


def test_swbc_firmographics_are_refused_for_their_held_share():
    out = [r for r in _run(SWBC) if r["gate_id"] == "CG-18b"]
    ceiling = [r for r in out if "6 of" in r["message"]]
    assert ceiling, [r["message"] for r in out]
    assert "2" in ceiling[0]["message"]


def test_baxter_firmographics_pass():
    assert _run(BAXTER) == []


def test_two_held_is_the_ceiling_and_passes():
    """Ten must-present members: 25% is 2.5, so two held pass and three do
    not, whichever two they are."""
    items = [_f(n, "x") for n in ("employees", "hq", "founded", "website",
                                  "primary_regulator", "charter", "branches",
                                  "total_assets")]
    items += [_f("revenue", None, "Absent from the SEC EDGAR index and the "
                 "trade-press ranking tables."),
              _f("cagr", None, "No second dated asset point in the call "
                 "report history.")]
    assert [r for r in _run(items) if r["gate_id"] == "CG-18b"] == []
    items[-3] = _f("total_assets", None, "Not in the call report.")
    assert any("3 of" in r["message"] for r in _run(items)
               if r["gate_id"] == "CG-18b")


def test_a_structural_answer_must_be_stated_not_held():
    """'Not chartered' and 'no single regulator' are the answers. Holding
    them hid two true facts that context.regulatory_standing stated."""
    paths = {r["path"] for r in _run(SWBC) if r["gate_id"] == "CG-18b"}
    assert "firmographics.fields[charter]" in paths
    assert "firmographics.fields[primary_regulator]" in paths


def test_a_held_reason_must_name_the_route_searched():
    paths = {r["path"]: r["message"] for r in _run(SWBC)
             if r["gate_id"] == "CG-18b"}
    assert "firmographics.fields[cagr]" in paths
    assert "route" in paths["firmographics.fields[cagr]"]
    # revenue names the ranking tables and assets names AM Best: routed.
    assert "firmographics.fields[revenue]" not in paths
    assert "firmographics.fields[assets]" not in paths


def test_the_ceiling_is_contract_data_not_code():
    """The cap lives beside the must-present set it governs, so a section
    that gains a member gains the arithmetic in the same edit."""
    hc = SPEC["held_ceiling"]
    assert hc["max_count"] == 2 and hc["max_share"] == 0.25
    assert set(SPEC["stated_not_held"]) >= {"charter", "primary_regulator",
                                            "branches"}


def test_cg18b_reaches_the_verdict_through_pass1():
    body = {"fields": SWBC, "undated_pct": 0, "sub_vertical_undefined": False,
            "e_ids": [], "internal_only": [], "produced_at": "x",
            "producer_version": "x"}
    out = validate_pass1("overview", {"firmographics": body})
    assert any(r["gate_id"] == "CG-18b" for r in out)


def test_cg18b_is_registered():
    from dma_mcp.gates import GATES
    assert GATES["CG-18b"][4] == "block"
