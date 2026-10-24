"""The stair-step's order agrees with the roadmap and the platform order of
work (SWBC gold audit 2026-10-04, RC-12(b), D-20, slice PL-07).

P4.md's CONSISTENCY line — "step order == roadmap phase order ==
recommendation sequencing_reason" — had no implementation. On SWBC (run
7968492e, platform submission 45a861d1) step 2 is "One governed customer
record across the lines" (P4C1.4.x / P4C1.1.x — the Data Cloud tile's gap
cells) and step 3 is "One integration route" (P4C3.3.x — the MuleSoft
tile's). The Data Cloud tile `depends_on` MuleSoft, the platform narrative
says "MuleSoft first ... Data Cloud second", and roadmap phase 2's rationale
says "the integration build leads". `to_level` read "Step three entry
conditions met: ...", a condition rather than a level.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _consistency as cc  # noqa: E402


def _step(level, label, cells, **kw):
    return {"step_level": level, "label": label, "covered_subcap_ids": cells,
            "e_ids": [], "entry_condition": "x", "current_position": level == 1,
            **kw}


def _tile(name, l3, rank, gaps, depends_on=()):
    return {"platform": name, "l3_area": l3, "rank": rank, "state": "READY",
            "fit_score": 50.0 - rank, "gaps": [{"subcap_id": g} for g in gaps],
            "depends_on": list(depends_on)}


def _rec(rec_id, phase, l3, cells):
    return {"rec_id": rec_id, "phase": str(phase), "l3_area": l3,
            "dma_impact": [{"subcap_id": c} for c in cells]}


MULE = "[L3-MS-ANYPOINT] MuleSoft Anypoint Platform"
DC = "[L3-SF-DATA-CLOUD] Salesforce Data Cloud"


def _swbc(steps, to_level="Step three entry conditions met: Data Management & "
                         "Governance, integration and BI asset inventory each at 2.0 or above"):
    platform = {
        "stairstep": {"ladder": {"from_level": "Building (data pillar stated 2.0209)",
                                 "to_level": to_level, "theme": "Data foundation",
                                 "steps": steps}},
        "platform_story": {"platforms": [
            _tile("MuleSoft Anypoint Platform", MULE, 1,
                  ["P4C3.3.1", "P4C3.3.2", "P4C3.3.5", "P4C1.4.2"]),
            _tile("Salesforce Data Cloud", DC, 2,
                  ["P4C1.1.1", "P4C1.4.2", "P4C1.4.1", "P4C1.2.2", "P4C1.4.3"],
                  depends_on=["MuleSoft Anypoint Platform"]),
        ]},
        "recommendations": {"recommendations": [
            _rec("REC-11", 1, "Data Governance Workshop (advisory engagement, no platform area)",
                 ["P4C1.1.1", "P4C1.4.1"]),
            _rec("REC-12", 2, DC, ["P4C2.2.6", "P4C2.5.1"]),
            _rec("REC-13", 2, MULE, ["P4C3.3.1", "P4C3.3.2"]),
            _rec("REC-06", 3, DC, ["P2C4.1.1"]),
        ]},
        "roadmap": {"phases": [
            {"phase": 1, "phase_id": "PH-1", "rec_ids": ["REC-11"]},
            {"phase": 2, "phase_id": "PH-2", "rec_ids": ["REC-12", "REC-13"]},
            {"phase": 3, "phase_id": "PH-3", "rec_ids": ["REC-06"]},
        ]},
    }
    return {"platform": platform}


SWBC_STEPS = [
    _step(1, "A warehouse each line can query",
          ["P4C1.3.1", "P4C1.3.2", "P4C2.6.1", "P4C2.6.3", "P4C2.2.1"]),
    _step(2, "One governed customer record across the lines",
          ["P4C1.4.1", "P4C1.4.2", "P4C1.4.3", "P4C1.1.1", "P4C1.1.2"]),
    _step(3, "One integration route and shared analytics on that record",
          ["P4C3.3.1", "P4C3.3.2", "P4C3.3.3", "P4C3.3.5", "P4C3.3.7", "P4C2.2.6"]),
]


def test_swbc_stairstep_against_the_platform_order_is_reported(tmp_path):
    _, out = cc.run(cc.rundir(tmp_path, _swbc(SWBC_STEPS)))
    msgs = cc.blocks(out, "P4 ↔ P1 order")
    assert msgs, out
    assert "Salesforce Data Cloud" in msgs[0] and "MuleSoft" in msgs[0]


def test_swbc_to_level_holding_a_condition_is_reported(tmp_path):
    _, out = cc.run(cc.rundir(tmp_path, _swbc(SWBC_STEPS)))
    assert "to_level" in out and "band" in out


def test_the_reordered_ladder_passes(tmp_path):
    steps = [SWBC_STEPS[0],
             dict(SWBC_STEPS[2], step_level=2),
             dict(SWBC_STEPS[1], step_level=3)]
    _, out = cc.run(cc.rundir(tmp_path, _swbc(
        steps, to_level="Building, near 2.55 after phase two (illustrative)")))
    assert not cc.blocks(out, "P4 ↔ P1 order"), out
    assert not cc.blocks(out, "P4 ↔ P3 order"), out
    assert "to_level" not in out


def test_a_step_whose_cells_are_lifted_later_on_the_roadmap_blocks(tmp_path):
    """The rule as rca RC-12(b) states it: the earliest roadmap phase whose
    recommendations' dma_impact intersects a step's covered cells is
    non-decreasing across steps. Advisory recommendations (no platform area
    — SWBC's REC-11 governance workshop) are preconditions that may precede
    any step, so the order is argued against the platform recommendations."""
    pages = _swbc([
        _step(1, "A", ["P2C4.1.1"]),          # REC-06 (Data Cloud), phase 3
        _step(2, "B", ["P4C3.3.1"]),          # REC-13 (MuleSoft), phase 2
    ], to_level="Building")
    pages["platform"]["platform_story"]["platforms"] = []
    _, out = cc.run(cc.rundir(tmp_path, pages))
    msgs = cc.blocks(out, "P4 ↔ P3 order")
    assert msgs and "phase 3" in msgs[0] and "phase 2" in msgs[0], out
    # an advisory recommendation lifting a later step's cells earlier is not
    # an inversion
    pages = _swbc([_step(1, "A", ["P4C3.3.1"]),   # REC-13, phase 2
                   _step(2, "B", ["P4C1.4.1"])],  # REC-11 (advisory), phase 1
                  to_level="Building")
    pages["platform"]["platform_story"]["platforms"] = []
    _, out = cc.run(cc.rundir(tmp_path, pages, name="run2"))
    assert not cc.blocks(out, "P4 ↔ P3 order"), out
