"""check_consistency.py reads the sub-vertical binding from the bundle, not
from a flag the producer must remember (MEM-0559).

MEM-0559 (resolved by REF-0111 as a --supplementary flag): on SWBC (primary
IB; supplementary IC, CL, RIA) the checker blocked 54 legitimately cited
IC/RIA variant cells. The flag fixed the measurement and left the mechanism:
a second copy of the binding that a producer can omit, and omitting it
reproduces the exact false block. The connector already serves the binding
in `get_report_bundle` (`sub_vertical`, `supplementary_sub_verticals`, 0061)
— the checker reads it there, the same place the gates read it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _consistency as cc  # noqa: E402

SWBC_BUNDLE = {"display_id": "swbc", "sub_vertical": "IB",
               "supplementary_sub_verticals": ["IC", "CL", "RIA"]}


def _overview(cells):
    return {"overview": {"findings": {"findings": [
        {"f_id": "F-1", "linked_subcap_ids": cells}]}}}


def test_the_supplementary_binding_is_read_from_the_bundle(tmp_path):
    d = cc.rundir(tmp_path, _overview(["P3C1.8.IC1", "P2C2.5.IB1", "P3C3.4.RIA1"]),
                  bundle=SWBC_BUNDLE)
    _, out = cc.run(d)
    assert not cc.blocks(out, "sub-vertical scope"), out
    assert "binding: IB+CL,IC,RIA (bundle)" in out


def test_a_variant_outside_the_bundle_binding_still_blocks(tmp_path):
    d = cc.rundir(tmp_path, _overview(["P3C3.8.RB1"]), bundle=SWBC_BUNDLE)
    _, out = cc.run(d)
    msgs = cc.blocks(out, "sub-vertical scope")
    assert msgs and "RB variants on a IB run" in msgs[0]


def test_the_supplementary_flag_is_refused(tmp_path):
    """The flag was the second copy of the binding. It is gone: passing it
    says where the binding is read from instead of silently trusting it."""
    d = cc.rundir(tmp_path, _overview(["P3C1.8.IC1"]), bundle=SWBC_BUNDLE)
    rc, out = cc.run(d, "--supplementary", "IC,CL,RIA")
    assert rc == 2 and "read from the bundle" in out


def test_a_typed_subvertical_that_disagrees_with_the_bundle_blocks(tmp_path):
    d = cc.rundir(tmp_path, _overview(["P3C1.8.IC1"]), bundle=SWBC_BUNDLE)
    _, out = cc.run(d, "--subvertical", "CU")
    assert cc.blocks(out, "binding"), out


def test_an_explicit_bundle_path_is_honoured(tmp_path):
    d = cc.rundir(tmp_path, _overview(["P3C1.8.IC1"]))
    b = tmp_path / "elsewhere.json"
    import json
    b.write_text(json.dumps({"data": SWBC_BUNDLE}))   # mcp_raw's wrapper too
    _, out = cc.run(d, "--bundle", str(b))
    assert not cc.blocks(out, "sub-vertical scope"), out


def test_no_bundle_and_no_code_says_the_binding_is_unknown(tmp_path):
    d = cc.rundir(tmp_path, _overview(["P3C1.8.IC1", "P3C3.8.RB1"]))
    _, out = cc.run(d)
    assert "binding unknown" in out
