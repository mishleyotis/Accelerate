"""CG-18c — the sub-vertical decides WHICH firmographics, in the machine
contract and not only in prose.

RC-06 (SWBC gold audit, 2026-10-04; D-04, slices OH-02, OH-04). The SV7
(Insurance Brokers) set — premium placed, commission revenue, producer count,
acquisitions — lived only in the O2 doc string and the rulebook. The machine
`must_present` was the generic ten, and `must_present_any` put `revenue` in
the same alias group as `commission_revenue` and `premium_placed`, so SWBC's
QUARANTINED generic revenue satisfied the insurance-broker requirement and no
SV7 field was ever asked for.

`must_present_by_subvertical` now carries one set per sub-vertical code; pass 2
reads the run's primary sub-vertical and enforces it (generic `revenue` is an
alias of nothing in SV7). Farm Credit has no defined set and must declare
`sub_vertical_undefined: true`. Shape-only fixtures; the gold runs (Baxter,
Golden 1, Logix — all SV2) pass on the aliases they actually used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation2 import _check_subvertical_must_present as check  # noqa: E402
from test_cg18_held_ceiling import BAXTER, SWBC, _f  # noqa: E402

SPEC = sections("overview")["firmographics"]["fields"]["fields"]


def _run(fields, code, **extra):
    return check("overview", {"firmographics": {"fields": fields, **extra}},
                 code)


def test_an_ib_run_with_only_generic_fields_is_refused():
    out = _run(SWBC, "IB")
    assert {r["gate_id"] for r in out} == {"CG-18c"}
    msg = " ".join(r["message"] for r in out)
    for want in ("premium_placed", "producer_count", "acquisitions"):
        assert want in msg, want


def test_generic_revenue_does_not_satisfy_sv7():
    held_rev = [f for f in SWBC if f["field"] == "revenue"]
    out = _run(held_rev, "IB")
    assert any("premium_placed" in r["message"] for r in out)


def test_an_ib_run_stating_its_sv7_set_passes():
    fields = SWBC[:1] + [_f("commission_revenue", "250"),
                         _f("producer_count", "120"),
                         _f("acquisitions", "4")]
    assert _run(fields, "IB") == []


def test_the_sv2_gold_shapes_pass():
    assert _run(BAXTER, "CU") == []
    golden1 = [_f(n, "x") for n in ("total_assets", "member_count",
                                    "member_shares", "loans",
                                    "net_worth_ratio", "roa")]
    logix = [_f(n, "x") for n in ("total_assets", "shares_and_deposits",
                                  "loans_and_leases", "net_worth_ratio",
                                  "member_count", "roa")]
    assert _run(golden1, "CU") == []
    assert _run(logix, "CU") == []


def test_held_sv_members_count_against_the_ceiling():
    """Two generic members held passes CG-18b in pass 1; adding a held SV7
    member makes three held of the union, which pass 2 refuses."""
    fields = [_f(n, "x") for n in ("employees", "hq", "founded", "website",
                                   "primary_regulator", "charter",
                                   "total_assets", "commission_revenue",
                                   "acquisitions")]
    fields += [_f("branches", None, "Not stated in the NMLS licence record."),
               _f("cagr", None, "No second point in the annual report."),
               _f("producer_count", None, "Not in the NAIC producer "
                                          "database for the group.")]
    out = _run(fields, "IB")
    assert [r["gate_id"] for r in out] == ["CG-18b"], out


def test_farm_credit_declares_itself_undefined():
    assert len(_run(BAXTER, "FC")) == 1
    assert _run(BAXTER, "FC", sub_vertical_undefined=True) == []


def test_every_code_has_a_set_and_sv7_has_no_generic_revenue():
    by = SPEC["must_present_by_subvertical"]
    assert set(by) == {"RB", "CU", "CL", "CIB", "RIA", "AM", "IB", "IC", "FC"}
    flat = [a for m in by["IB"] for a in (m if isinstance(m, list) else [m])]
    assert "revenue" not in flat


def test_sub_vertical_undefined_is_a_required_boolean():
    f = sections("overview")["firmographics"]["fields"]["sub_vertical_undefined"]
    assert f["required"] is True and f["type"] == "boolean"


def test_an_unknown_sub_vertical_is_left_alone():
    assert _run(SWBC, None) == []
