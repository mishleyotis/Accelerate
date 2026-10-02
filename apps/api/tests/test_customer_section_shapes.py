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
