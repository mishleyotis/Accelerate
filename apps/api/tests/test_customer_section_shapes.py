"""Two customer-body SHAPE rules from the 2026-10-02 SWBC redaction audit.

  c. platform.starters is withheld WHOLE (MEM-0081 / T-2): its openers are
     written for the seller, so key-stripping left a card list whose every
     surviving field was our talk track;
  d. the serve allowlist holds DICT-valued fields to their keys too —
     `_apply_allowlist` filtered only list-valued fields, so
     `heatmap.cell_evidence.linking_stats` served all seven reach counters
     while the allowlist names three.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import CUSTOMER_WITHHELD, redact_section  # noqa: E402


# ── c. platform.starters is withheld whole ────────────────────────────
def test_starters_is_withheld_whole_from_the_customer():
    assert ("platform", "starters") in CUSTOMER_WITHHELD
    st = {"starters": [{"rank": 1, "text": "Ask which system they use."}]}
    out, report = redact_section("platform", "starters", st, [], "customer")
    assert out is None and report["withheld"] is True


def test_starters_still_serves_internally():
    st = {"starters": [{"rank": 1, "text": "Ask which system they use."}]}
    out, _ = redact_section("platform", "starters", st, [], "internal")
    assert out["starters"][0]["rank"] == 1


# ── d. dict-valued fields are held to the allowlist ───────────────────
def test_linking_stats_serves_only_the_allowlisted_counters():
    data = {"cells": [], "linking_stats": {
        "cells_scored": 10, "cells_linked": 8, "cells_citable": 7,
        "rows_unlinkable": 2, "links_proposed": 4, "links_rejected": 1,
        "ladder_runs": 3}}
    out, report = redact_section("heatmap", "cell_evidence", data, [],
                                 "customer")
    assert set(out["linking_stats"]) == {"cells_scored", "cells_linked",
                                         "rows_unlinkable"}
    assert "linking_stats.ladder_runs" in report["allowlist_dropped"]


def test_the_internal_audience_keeps_every_counter():
    data = {"cells": [], "linking_stats": {"cells_scored": 1,
                                           "ladder_runs": 3}}
    out, _ = redact_section("heatmap", "cell_evidence", data, [], "internal")
    assert out["linking_stats"]["ladder_runs"] == 3


# ── d2. an id-keyed MAP and a wrapper dict are not filtered by their ids ──
# Measured on the SWBC re-check 2026-10-02: filtering dict KEYS against the
# item allowlist emptied heatmap.workbook_scores pillars/categories (their
# keys are pillar and category ids) and stripped platform.stairstep.ladder
# down to nothing (its keys are steps/theme/to_level/from_level).
def test_workbook_score_maps_keep_their_ids_and_allowlisted_values():
    data = {"pillars": {"P1": {"score": 1.9, "peer_median": None,
                               "source_cell": "Pillar_Summary!C2",
                               "basis_internal": "x"}},
            "categories": {"P1C1": {"score": 1.8, "peer_median": None,
                                    "source_cell": "Category_Detail!B2"}}}
    out, _ = redact_section("heatmap", "workbook_scores", data, [], "customer")
    assert out["pillars"]["P1"]["score"] == 1.9
    assert "basis_internal" not in out["pillars"]["P1"]
    assert out["categories"]["P1C1"]["source_cell"] == "Category_Detail!B2"


def test_stairstep_ladder_keeps_its_steps():
    data = {"ladder": {"theme": "Data foundation", "from_level": "Building",
                       "to_level": "Entry conditions met",
                       "steps": [{"label": "Step 1", "step_level": 1,
                                  "entry_condition": "x", "unlocks": "y",
                                  "current_position": True, "e_ids": [],
                                  "covered_subcap_ids": [], "effort_band": "M",
                                  "blocking_findings": [], "scratch": "drop me"}]}}
    out, _ = redact_section("platform", "stairstep", data, [], "customer")
    step = out["ladder"]["steps"][0]
    assert step["label"] == "Step 1" and "scratch" not in step
    assert out["ladder"]["theme"] == "Data foundation"


# ── e2. element paths are deleted highest index first ─────────────────
def test_ascending_element_paths_delete_the_named_items():
    from dma_api.redaction import strip_paths
    data = {"cells": [{"items": [{"e_id": "A"}, {"e_id": "B"},
                                 {"e_id": "C"}, {"e_id": "D"}]}]}
    stripped, unmatched = strip_paths(
        data, ["cells[0].items[0]", "cells[0].items[1]", "cells[0].items[3]"])
    assert [i["e_id"] for i in data["cells"][0]["items"]] == ["C"]
    assert unmatched == [] and len(stripped) == 3


# ── f. the producer may make an item's freshness more conservative ────
class _Cur:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchall(self): return self._rows


def test_producer_unverified_recency_survives_the_store_rebuild():
    from dma_api.computed import cell_items
    # store row: a fetch-day date stored as published -> CURRENT
    row = ("E-1", "E-1", "T2", "FACT", "CURRENT", "swbc.com", "swbc.com",
           "x" * 60, "https://swbc.com", "producer")
    data = {"cells": [{"subcap_id": "P1C1.1.1", "e_ids": ["E-1"],
                       "items": [{"e_id": "E-1", "recency": "UNVERIFIED"}]}]}
    cell_items(_Cur([row]), data, "ent")
    assert data["cells"][0]["items"][0]["recency"] == "UNVERIFIED"


def test_producer_cannot_upgrade_recency():
    from dma_api.computed import cell_items
    row = ("E-1", "E-1", "T2", "FACT", "UNVERIFIED", "s", "s",
           "x" * 60, "https://swbc.com", "producer")
    data = {"cells": [{"subcap_id": "P1C1.1.1", "e_ids": ["E-1"],
                       "items": [{"e_id": "E-1", "recency": "CURRENT"}]}]}
    cell_items(_Cur([row]), data, "ent")
    assert data["cells"][0]["items"][0]["recency"] == "UNVERIFIED"


# ── g. customer chips equal the items served, after element-path strips ──
def test_customer_e_ids_drop_items_removed_by_internal_only_paths():
    data = {"cells": [{"subcap_id": "P1C1.1.2", "synthesis": "s",
                       "e_ids": ["E-INT", "E-PUB"], "grounded_on": 2,
                       "items": [{"e_id": "E-INT", "excerpt": "x" * 60},
                                 {"e_id": "E-PUB", "excerpt": "y" * 60}]}]}
    out, _ = redact_section("heatmap", "cell_evidence", data,
                            ["cells[0].items[0]"], "customer")
    cell = out["cells"][0]
    assert cell["e_ids"] == ["E-PUB"]
    assert cell["grounded_on"] == 1
