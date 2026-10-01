"""The citation floor never exceeds ~all of the evidence the run holds.

2026-10-01, Cross Insurance (owner-approved): a degraded public run held 70
evidence rows and its assessment cited 66; the density floor was 116, so no
rewrite could ever render the report. The floor is min(density, 0.9 x held).
"""
import math

from engine import gold_standard as GS
from engine import reports, report_spec as RS
from fixtures import new_run


def test_renderer_floor_never_exceeds_ninety_percent_of_held(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    held = len({r.get("E_ID") for r in wb.rows("Evidence_Detail") if r.get("E_ID")})
    floor = reports.citation_floor(wb, RS.SPECS["assessment"])
    assert floor >= 1
    if held:
        assert floor <= max(1, math.ceil(reports.EVIDENCE_BASE_SHARE * held))


def test_a_large_evidence_base_keeps_the_density_floor(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    density = max(1, math.ceil(115 / 690 * len(wb.selected_subcaps())))
    held = len({r.get("E_ID") for r in wb.rows("Evidence_Detail") if r.get("E_ID")})
    if math.ceil(0.9 * held) >= density:
        assert reports.citation_floor(wb, RS.SPECS["assessment"]) == density


def test_gold_floor_is_still_the_density_floor_without_a_workbook():
    full = GS.depth_floors("assessment", 694)["citations"]
    assert full > 63  # the cap applies only when evidence_held is given
