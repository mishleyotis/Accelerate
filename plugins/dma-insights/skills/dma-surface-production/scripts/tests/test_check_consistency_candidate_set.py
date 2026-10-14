"""The "P1 candidate set" check strips the catalogue's " (count: N)" tally.

A catalogue L3 area reads e.g. `[L3-SF-DC-CORE] Data Cloud (count: 3)` — the
"(count: N)" is a vote tally welded onto the label (apps/mcp fit.py,
validation.py CG-42 both strip it). The candidate-set check keyed the label
WITH the tally, so a tile named "Data Cloud" never matched "data cloud count
3" and the check blocked a run whose candidate set was complete.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_consistency.py"


def _module():
    spec = importlib.util.spec_from_file_location("_cc_candidates", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _blocks(m, tiles, areas, discards=()):
    m.issues.clear()
    P = {"platform": {"platform_story": {"platforms": tiles,
                                         "discarded": list(discards)}}}
    catalogue = {"subcaps": [{"subcap_id": f"P1C1.{i}",
                              "l3_platform_areas": [a]}
                             for i, a in enumerate(areas, 1)]}
    bundle = {"scores": [{"subcap_id": f"P1C1.{i}", "score": 2.5}
                         for i in range(1, len(areas) + 1)]}
    m.check_platform_states_and_areas(P, bundle, catalogue, None, set())
    return [i for i in m.issues if i[1] == "P1 candidate set"]


def test_a_tallied_catalogue_label_matches_its_tile():
    m = _module()
    tiles = [{"platform": "Data Cloud", "state": "READY"},
             {"platform": "Tableau Pulse", "state": "READY"}]
    areas = ["Data Cloud (count: 3)", "Tableau Pulse (count: 78)"]
    assert _blocks(m, tiles, areas) == []


def test_a_tallied_coded_label_matches_a_named_tile():
    m = _module()
    tiles = [{"platform": "Data Cloud", "state": "READY"}]
    areas = ["[L3-SF-DC-CORE] Data Cloud (count: 3)"]
    assert _blocks(m, tiles, areas) == []


def test_a_genuinely_missing_area_still_blocks_without_the_tally():
    m = _module()
    tiles = [{"platform": "Data Cloud", "state": "READY"}]
    areas = ["Data Cloud (count: 3)", "Flow (count: 58)"]
    got = _blocks(m, tiles, areas)
    assert len(got) == 1, got
    msg = got[0][2]
    assert "Flow (1 cells)" in msg and "count:" not in msg, msg
    assert "Data Cloud" not in msg, msg
