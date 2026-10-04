"""check_consistency's sub-vertical scope honours the supplementary binding.

An entity bound to a primary sub-vertical plus supplementary ones serves the
variant cells of all of them (entities.supplementary_sub_verticals, 0061), so
citing one is in scope. A variant of a sub-vertical outside the binding still
blocks. Measured on SWBC 2026-10-02: IB primary with IC, CL, RIA supplementary
blocked on 54 legitimately cited IC/RIA cells before this option existed.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_consistency.py"


def _rundir(tmp_path, cells):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "overview.json").write_text(json.dumps(
        {"findings": {"findings": [{"f_id": "F-1", "linked_subcap_ids": cells}]}}))
    return tmp_path


def _run(rundir, *args):
    out = subprocess.run([sys.executable, str(SCRIPT), str(rundir), *args],
                         capture_output=True, text=True)
    return out.stdout + out.stderr


def test_supplementary_variant_is_in_scope(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1", "P2C2.5.IB1"])
    out = _run(d, "--subvertical", "IB", "--supplementary", "IC,CL,RIA")
    assert "variants on a IB run" not in out


def test_variant_outside_the_binding_still_blocks(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C3.8.RB1"])
    out = _run(d, "--subvertical", "IB", "--supplementary", "IC,CL,RIA")
    assert "RB variants on a IB run" in out


def test_without_supplementary_the_old_rule_holds(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1"])
    out = _run(d, "--subvertical", "IB")
    assert "IC variants on a IB run" in out


def test_unknown_supplementary_code_is_refused(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1"])
    out = _run(d, "--subvertical", "IB", "--supplementary", "XX")
    assert "unknown supplementary" in out
