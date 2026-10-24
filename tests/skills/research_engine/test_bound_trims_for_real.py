"""`brief._bound` must actually shrink a packet when it trims.

Measured 2026-10-01 (Cross Insurance): the trimmed rows were appended to
packet["dropped"] INSIDE the packet being measured, so trimming never made
it smaller and every list halved down to the floor. Each scoring lane got
3 rows a round; SCORING failed after 10 rounds with ~490 cells unscored.
"""
import json

from engine import brief


def _packet(n):
    return {"agent": "scoring-p2-producer", "shared": {"run_id": "R"},
            "rows_to_score": [{"subcap": f"P2C1.{i}.1", "name": "x" * 60,
                               "label": "HYPOTHESIS", "absent": True}
                              for i in range(n)]}


def test_trim_keeps_as_many_rows_as_fit_not_the_floor():
    p = brief._bound(_packet(200), "rows_to_score", ceiling=6400, floor=3)
    kept = len(p["rows_to_score"])
    assert kept > 3, kept
    measured = {k: v for k, v in p.items() if k != "dropped"}
    assert len(json.dumps(measured, default=str)) <= 6400 or kept == 3
    assert kept + len(p["dropped"]) == 200


def test_a_packet_that_fits_is_untouched():
    p = brief._bound(_packet(5), "rows_to_score", ceiling=6400, floor=3)
    assert len(p["rows_to_score"]) == 5 and "dropped" not in p


def test_dropped_rows_render_as_a_count_not_a_list():
    p = brief._bound(_packet(200), "rows_to_score", ceiling=6400, floor=3)
    md = brief._md("Scoring", p)
    assert "held for a later round" in md
    assert "P2C1.199.1" not in md
