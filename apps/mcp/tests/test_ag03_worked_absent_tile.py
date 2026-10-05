"""AG-03 and CG-03b must not deadlock on a worked-absent sentiment tile.

2026-10-05, Cross Insurance: CG-03b requires exactly three context tiles; the
employee tile's review hosts (Glassdoor, Indeed, BBB, the firm's own careers
page) all refuse the evidence verifier, so no id can be registered, and the
tile item shape declares no absence key. AG-03 refused the tile; removing it
failed CG-03b. A WORKED_ABSENT tile with no rows is carried by the section's
own complete ladder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp import validation2 as V  # noqa: E402

FAMS = ["App Store — VERIFIED_ABSENT: no app", "Google Play — REACHED: none",
        "Glassdoor — REACHED: 3.9 of 5 from 44, unregistrable",
        "Indeed — REACHED: 3.1, unregistrable",
        "CFPB complaint database — NOT_APPLICABLE: broker",
        "BBB — REACHED: A+", "Google reviews — RESOLVED: 4.0 of 5 from 53"]


def _sec(state="WORKED_ABSENT", ladder=FAMS, rows=None):
    return {"context_sentiment": {
        "context_tiles": [
            {"audience": "customer", "state": "RATED", "e_ids": ["E-1"],
             "rows": [{"source": "Google", "rating": 4.0, "e_id": "E-1"}]},
            {"audience": "employee", "state": state, "rows": rows or [], "e_ids": []},
            {"audience": "market", "state": "WORKED_ABSENT", "rows": [], "e_ids": ["E-2"]}],
        "e_ids": ["E-1", "E-2"], "internal_only": [],
        "empty_state": {"reason": "r", "sources_searched": list(ladder),
                        "closure_condition": "c"}}}


def _ag03(payload):
    return [r for r in V._check_item_evidence("context", payload)
            if r["gate_id"] == "AG-03"]


def test_worked_absent_tile_with_complete_section_ladder_passes():
    assert _ag03(_sec()) == []


def test_incomplete_section_ladder_still_refuses_the_tile():
    assert _ag03(_sec(ladder=["Glassdoor — not searched"]))


def test_a_tile_claiming_a_rating_without_ids_is_still_refused():
    assert _ag03(_sec(state="RATED"))


def test_a_worked_absent_tile_that_carries_rows_is_still_refused():
    assert _ag03(_sec(rows=[{"source": "Glassdoor", "rating": 3.9}]))
