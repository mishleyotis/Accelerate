"""The enrichment register's thin floor and CG-40's depth floor agree.

RC-05 (SWBC gold audit, 2026-10-04; D-06). enrichment_register.json set
overview.sentiment `thin_below: 1` while DEPTH_FLOORS held the same section to
2 — so one bar rendered "not thin" on the page while the gate's own floor said
it was below depth. The two numbers describe one fact about one section and
were written in two files that nothing compared (RULE_HELD_IN_TWO_PLACES_
DRIFTS, MEM-0084).

The invariant is one-directional on purpose: a section the gate calls below
floor must render thin (register floor >= depth floor). Equality is not
required where the register's floor was set higher by corpus measurement —
techstack is thin below 20 but refused below 15 (owner, 2026-08-23) — and
sentiment, the section RC-05 measured, is pinned equal.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import DEPTH_FLOORS  # noqa: E402

REGISTER = (Path(__file__).resolve().parents[3] / "packages" / "shared"
            / "enrichment_register.json")


def _register():
    return json.loads(REGISTER.read_text())["surfaces"]


def test_a_section_below_its_depth_floor_always_renders_thin():
    reg = _register()
    for (page, section), (floor, _unit, _why) in DEPTH_FLOORS.items():
        spec = reg.get(f"{page}.{section}")
        if spec is None:
            continue
        assert spec["thin_below"] >= floor, (
            f"{page}.{section}: register thin_below {spec['thin_below']} < "
            f"CG-40 floor {floor} — a section the gate refuses as below depth "
            f"would render as not thin")


def test_sentiment_floors_are_equal():
    assert _register()["overview.sentiment"]["thin_below"] == \
        DEPTH_FLOORS[("overview", "sentiment")][0] == 2
