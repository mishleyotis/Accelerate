"""Gate J at ROW grain — RC-02, SWBC gold audit 2026-10-04.

Gate J compared section keys and treated any non-empty list as "filled". Three
gaps the owner could see on a promoted run passed it silently:

  · firmographics: the gold states 15 of 16 fields and holds one; the run
    served 10 with 6 held (quarantined, value null)
  · sentiment: the reference carries seven rated bars; the run carried one
  · platform cards: every reference card carries `peer_deployments`; six of
    the run's eight did not

Each case below was green before the change and must report its kind now.
Values are never read: every row here is placeholder text.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gate_j_surface_parity import compare_page  # noqa: E402


def page(**sections):
    return {"sections": {k: {"data": v} for k, v in sections.items()}}


def field(stated=True):
    return {"field": "f", "value": "v" if stated else None,
            "quarantined": not stated,
            "quarantine_reason": None if stated else "held",
            "as_of": "2025" if stated else None, "source_e_id": "E-1"}


def kinds(gaps):
    return sorted((g["kind"], g["section"], g["key"]) for g in gaps)


def test_firmographics_ten_fields_six_held_reports_stated_share():
    ref = page(firmographics={"fields": [field()] * 14 + [field(False)]})
    tgt = page(firmographics={"fields": [field()] * 4 + [field(False)] * 6})
    got = kinds(compare_page("overview", ref, tgt))
    assert ("stated_share", "firmographics", "fields") in got, got


def test_one_sentiment_bar_against_seven_reports_list_len():
    bar = {"source": "s", "rating": 4.1, "scale": "1-5", "n": 10}
    ref = page(sentiment={"bars": [bar] * 7, "themes": [{"theme": "t"}]})
    tgt = page(sentiment={"bars": [bar], "themes": [{"theme": "t"}]})
    got = kinds(compare_page("overview", ref, tgt))
    assert ("list_len", "sentiment", "bars") in got, got


def test_platform_cards_lacking_peer_rows_report_item_key_missing():
    card = {"platform": "p", "fit_score": 50.0,
            "peer_deployments": [{"peer": "x", "deployed": None}]}
    bare = {"platform": "p", "fit_score": 50.0}
    ref = page(platform_story={"platforms": [card] * 5})
    tgt = page(platform_story={"platforms": [card] * 2 + [bare] * 6})
    got = kinds(compare_page("platform", ref, tgt))
    assert ("item_key_missing", "platform_story",
            "platforms[].peer_deployments") in got, got


def test_a_null_member_inside_a_row_is_unfilled():
    """The half the old gate never saw: the key is there, the value is not."""
    ref = page(leadership={"roster": [{"name": "a", "appointed_on": "2020"}] * 6})
    tgt = page(leadership={"roster": [{"name": "a", "appointed_on": None}] * 6})
    got = kinds(compare_page("overview", ref, tgt))
    assert ("item_fill", "leadership", "roster[].appointed_on") in got, got


def test_nested_lists_are_compared_per_parent_row():
    deep = {"platform": "p", "gaps": [{"subcap_id": "s", "e_ids": ["E"]}] * 4}
    shallow = {"platform": "p", "gaps": [{"subcap_id": "s", "e_ids": []}]}
    ref = page(platform_story={"platforms": [deep] * 3})
    tgt = page(platform_story={"platforms": [shallow] * 3})
    got = kinds(compare_page("platform", ref, tgt))
    assert ("list_len", "platform_story", "platforms[].gaps") in got, got
    assert ("item_fill", "platform_story", "platforms[].gaps[].e_ids") in got, got


def test_a_null_with_its_reason_beside_it_is_a_stated_absence():
    """Owner decision 2 (2026-10-04): a held field renders as a stated
    absence with its reason. A member whose row carries `<member>_basis` is
    that, not a gap."""
    ref = page(techstack={"layers": [{"layer": "OPS", "expected": 9}] * 4})
    tgt = page(techstack={"layers": [{"layer": "OPS", "expected": None,
                                      "expected_basis": "why"}] * 4})
    assert compare_page("techstack", ref, tgt) == []


def test_thinness_is_excused_only_by_a_terminal_ladder():
    """RC-05: a bare reason was accepted in place of a search never run."""
    bar = {"source": "s", "rating": 4.0}
    ref = page(sentiment={"bars": [bar] * 6})
    said = page(sentiment={"bars": [bar],
                           "empty_state": {"reason": "searched widely"}})
    laddered = page(sentiment={"bars": [bar], "empty_state": {
        "reason": "r", "sources_searched": [
            {"source": "Indeed", "outcome": "VERIFIED_ABSENT"},
            {"source": "CFPB", "outcome": "RESOLVED"}]}})
    unfinished = page(sentiment={"bars": [bar], "empty_state": {
        "reason": "r", "sources_searched": [
            {"source": "Indeed", "outcome": "VERIFIED_ABSENT"},
            {"source": "Glassdoor", "outcome": "not retrieved"}]}})
    assert ("list_len", "sentiment", "bars") in kinds(
        compare_page("overview", ref, said))
    assert compare_page("overview", ref, laddered) == []
    assert ("list_len", "sentiment", "bars") in kinds(
        compare_page("overview", ref, unfinished))


def test_withheld_by_audience_is_still_reported_separately():
    """The CLI names a withheld section on its own line and never counts it."""
    import json
    import tempfile
    ref = page(sentiment={"bars": [{"source": "s"}]})
    tgt = {"sections": {"sentiment": {"data": None, "withheld": True}}}
    with tempfile.TemporaryDirectory() as d:
        rp, tp = Path(d) / "r.json", Path(d) / "t.json"
        rp.write_text(json.dumps(ref))
        tp.write_text(json.dumps(tgt))
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gate_j_surface_parity.py"),
             "--reference-file", str(rp), "--target-file", str(tp)],
            capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout
    assert "withheld by audience" in r.stdout and "sentiment" in r.stdout


def test_the_committed_gold_meets_its_own_standard():
    """Every gold run, checked against the OTHER gold runs (leave-one-out),
    has no structural gap — a floor the reference fails is not a standard
    (GOLD-STANDARD.md). Compared with itself a gold run could show nothing,
    which is why it is left out (owner decision B, 2026-10-04)."""
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp import parity
    gold = parity.load_gold(ROOT / "fixtures" / "surface_gold.json")
    for label, pages in parity.gold_runs(gold).items():
        meta = gold["runs"][label]
        res = parity.check_run(
            pages, gold, run_id=meta["run_id_prefix"],
            sub_vertical=meta["sub_vertical"])
        assert res["left_out"] == [label], res["left_out"]
        assert res["blocking"] == [], (label, res["blocking"][:3])
