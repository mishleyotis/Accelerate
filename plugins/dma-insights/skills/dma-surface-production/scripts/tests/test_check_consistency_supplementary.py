"""check_consistency's sub-vertical scope honours the supplementary binding.

An entity bound to a primary sub-vertical plus supplementary ones serves the
variant cells of all of them (entities.supplementary_sub_verticals, 0061), so
citing one is in scope. A variant of a sub-vertical outside the binding still
blocks. Measured on SWBC 2026-10-02: IB primary with IC, CL, RIA supplementary
blocked on 54 legitimately cited IC/RIA cells before the binding was read.

MEM-0559 (2026-10-04): the binding is read from the bundle (get_report_bundle
-> sub_vertical, supplementary_sub_verticals), never typed. The flag this file
used to exercise, --supplementary, is retired; tests/skills/
test_check_consistency_binding.py carries the full regression.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_consistency.py"
SWBC = {"sub_vertical": "IB", "supplementary_sub_verticals": ["IC", "CL", "RIA"]}


def _rundir(tmp_path, cells, bundle=SWBC):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "overview.json").write_text(json.dumps(
        {"findings": {"findings": [{"f_id": "F-1", "linked_subcap_ids": cells}]}}))
    if bundle is not None:
        (tmp_path / "bundle.json").write_text(json.dumps(bundle))
    return tmp_path


def _run(rundir, *args):
    out = subprocess.run([sys.executable, str(SCRIPT), str(rundir), *args],
                         capture_output=True, text=True)
    return out.stdout + out.stderr


def test_supplementary_variant_is_in_scope(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1", "P2C2.5.IB1"])
    assert "variants on a IB run" not in _run(d)


def test_variant_outside_the_binding_still_blocks(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C3.8.RB1"])
    assert "RB variants on a IB run" in _run(d)


def test_without_supplementary_the_old_rule_holds(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1"], bundle={"sub_vertical": "IB"})
    assert "IC variants on a IB run" in _run(d)


def test_the_supplementary_flag_is_retired(tmp_path):
    d = _rundir(tmp_path / "r", ["P3C1.8.IC1"])
    assert "read from the bundle" in _run(d, "--supplementary", "IC,CL,RIA")
