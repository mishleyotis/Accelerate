"""CG-18e — the firmographics strip and the regulatory card name one regulator
set and one charter.

RC-06 (SWBC gold audit, 2026-10-04; D-04, D-26; slices OH-04, XC-02). SWBC's
O2 held `charter` ("not a chartered depository") and `primary_regulator` ("no
single primary regulator") while context.regulatory_standing STATED both
("Not chartered. Licensed and registered by line ..." and "No single
prudential regulator ... FINRA"). The two pages also named different
regulator sets. Nothing compared them.

The check runs at submit on whichever page lands second (the sibling's live
submission is read, the AG-05 pattern): when C3 states license_type or
primary_regulator, O2 may not hold charter or primary_regulator, and every
regulator O2 names must be one C3 names (primary or additional), and C3's
primary regulator(s) must appear on O2.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dma_mcp.validation2 import _check_o2_c3_agreement as check  # noqa: E402
from test_cg18_held_ceiling import SWBC, _f  # noqa: E402

C3 = {
    "primary_regulator": "No single prudential regulator: privately held "
                         "group, supervised line by line. Broker-dealer SWBC "
                         "Investment Services answers to the Financial "
                         "Industry Regulatory Authority.",
    "license_type": "Not chartered. Licensed and registered by line.",
    "additional_regulators": [
        "Securities and Exchange Commission: registered investment adviser",
        "Texas Department of Savings and Mortgage Lending: mortgage licence",
        "Texas Department of Insurance: the insurers"],
}


def _o2(fields):
    return {"firmographics": {"fields": fields}}


def test_swbc_held_charter_beside_a_stated_license_type_is_refused():
    out = check("overview", _o2(SWBC), {"regulatory_standing": C3})
    paths = {r["path"] for r in out}
    assert "firmographics.fields[charter]" in paths
    assert "firmographics.fields[primary_regulator]" in paths
    assert all(r["gate_id"] == "CG-18e" for r in out)


def test_the_same_check_fires_when_context_lands_second():
    out = check("context", {"regulatory_standing": C3}, _o2(SWBC))
    assert {r["gate_id"] for r in out} == {"CG-18e"}
    assert len(out) == 2


def test_agreeing_pages_pass():
    fields = [_f("charter", "None — non-depository; licensed by line"),
              _f("primary_regulator", "By line: Financial Industry "
                 "Regulatory Authority (broker-dealer); Securities and "
                 "Exchange Commission (adviser); Texas Department of Savings "
                 "and Mortgage Lending (mortgage)")]
    assert check("overview", _o2(fields), {"regulatory_standing": C3}) == []


def test_a_regulator_on_o2_that_c3_does_not_name_is_refused():
    fields = [_f("charter", "None — non-depository"),
              _f("primary_regulator", "Financial Industry Regulatory "
                 "Authority; Office of the Comptroller of the Currency")]
    out = check("overview", _o2(fields), {"regulatory_standing": C3})
    assert len(out) == 1 and "Comptroller" in out[0]["message"]


def test_c3_primary_regulator_missing_from_o2_is_refused():
    fields = [_f("charter", "None"),
              _f("primary_regulator", "Securities and Exchange Commission")]
    out = check("overview", _o2(fields), {"regulatory_standing": C3})
    assert len(out) == 1
    assert "Financial Industry Regulatory Authority" in out[0]["message"]


def test_nothing_to_compare_when_the_sibling_is_not_staged():
    assert check("overview", _o2(SWBC), None) == []
    assert check("context", {"regulatory_standing": C3}, None) == []


def test_it_is_wired_into_pass2():
    import inspect
    from dma_mcp import validation2
    assert "_check_o2_c3_agreement(" in inspect.getsource(
        validation2.validate_pass2)
