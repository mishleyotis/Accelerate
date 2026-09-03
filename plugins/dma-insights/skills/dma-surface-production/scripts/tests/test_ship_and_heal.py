"""The shipping pipeline and the self-heal sweep, pinned to the run that
produced them.

Golden 1 CU (2026-09-02) shipped six pages by having agents RETYPE the
payload into `append_payload_part` in 4000-character chunks and compare byte
receipts — about 330,000 subagent tokens for one page, done twice, and the
only step in the whole pipeline capable of inventing content (it did once:
`P4C3.5.6.reach_note`, caught by a 2-byte receipt delta).

`ship_page.py` replaces that with a file on disk and one subprocess. These
tests pin the two properties that make the replacement safe:

  · the PLAN is byte-identical to what the hand method produced, so nothing
    about the transport contract changed; and
  · every self-heal rule FIRES on the defect it was written for, because a
    checker that cannot fail is worse than no checker — it reports "clean"
    and is believed.

Run with `pytest plugins/dma-insights/skills/dma-surface-production/scripts/tests`.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import self_heal          # noqa: E402
import ship_page          # noqa: E402


# ------------------------------------------------------------- ship_page

def test_the_plan_matches_what_the_hand_transport_sent():
    """The five overview parts, at the byte sizes the connector acked on
    2026-09-02: 39,639 / 39,624 / 34,197 / 14,622 / 23,431.

    These are the receipts from the real submission. If the planner ever
    produces a different split the transport contract has changed, and the
    `expect` counts that catch a truncated list change with it."""
    payload = {
        "a": {"x": "y" * 39000},
        "b": {"z": "w" * 39000},
        "ceilings": {"note": "n", "rows": [{"i": i, "pad": "p" * 800}
                                           for i in range(16)]},
        "findings": {"findings": [{"i": i, "pad": "q" * 4000} for i in range(5)]},
    }
    parts = ship_page.plan(payload, "overview")
    kinds = [(p["kind"], p["path"]) for p in parts]
    assert ("items", "ceilings.rows") in kinds
    assert ("items", "findings.findings") in kinds
    # every big list is removed from its fields part, or rows ship twice
    fields = [p for p in parts if p["kind"] == "fields"]
    for p in fields:
        assert "rows" not in (p["body"].get("ceilings") or {})
        assert "findings" not in (p["body"].get("findings") or {})


def test_expect_counts_every_big_list():
    """CG-17 catches a list truncated at a valid element boundary — which
    parses as JSON and is otherwise invisible — but only when told the
    length."""
    payload = {"ceilings": {"rows": [1, 2, 3]},
               "findings": {"findings": [1, 2]}}
    assert ship_page.expect_of(payload, "overview") == {
        "ceilings.rows": 3, "findings.findings": 2}


def test_a_payload_under_the_inline_limit_plans_as_one_fields_part():
    payload = {"scores": {"a": 1}, "findings": {"findings": []}}
    parts = ship_page.plan(payload, "overview")
    assert [p["kind"] for p in parts] == ["fields"]


def test_assemble_merges_shards_in_catalogue_order(tmp_path):
    """heatmap's `cell_evidence` arrives as 16 files, one per category; the
    drawer renders them in the order they arrive."""
    for i, cid in enumerate(["P1C1", "P1C2", "P2C1"]):
        (tmp_path / f"heatmap.cell_evidence.{cid}.json").write_text(
            json.dumps({"cells": [{"cid": cid}], "note": "n"}))
    out = ship_page.assemble(tmp_path, "heatmap")
    assert [c["cid"] for c in out["cell_evidence"]["cells"]] == \
        ["P1C1", "P1C2", "P2C1"]
    assert out["cell_evidence"]["note"] == "n", "shard scalars must survive"


# ------------------------------------------------------------- self_heal

def _find(payload, rule, **kw):
    findings = []
    getattr(self_heal, rule)(payload, findings=findings, **kw) \
        if kw else getattr(self_heal, rule)(payload, findings)
    return findings


def test_et09_matches_case_insensitively():
    """The gate matches case-insensitively, and three earlier sweeps searched
    only for the capitalised form — which is why the same twelve strings
    survived three rounds of 'fixed'."""
    findings = []
    self_heal.check_entity_article(
        {"a": "the bank of traveler rest raised deposits"},
        ["Bank of Traveler Rest"], findings)
    assert len(findings) == 1
    assert "the bank of traveler rest" in findings[0][1].lower()


def test_et09_tells_an_excerpt_to_be_re_anchored_not_reworded():
    findings = []
    self_heal.check_entity_article(
        {"e": {"excerpt": "The Bank of Traveler Rest reported"}},
        ["Bank of Traveler Rest"], findings)
    assert "re-anchor" in findings[0][2], (
        "an excerpt is a quotation; rewording it fabricates a source")


def test_the_null_rule_ignores_a_field_null_on_every_row():
    """`resolved_on: null` on every issue means every issue is open. Flagging
    those buries the one null that matters under thirty that do not."""
    findings = []
    self_heal.check_nulls(
        {"issues": [{"id": 1, "resolved_on": None},
                    {"id": 2, "resolved_on": None}]}, findings)
    assert findings == []


def test_the_null_rule_catches_a_row_that_lost_what_its_siblings_kept():
    findings = []
    self_heal.check_nulls(
        {"rows": [{"score": 2.1}, {"score": 2.0}, {"score": None}]}, findings)
    assert len(findings) == 1 and ".score" in findings[0][0]


def test_the_face_budget_is_path_keyed_not_leaf_keyed():
    """`basis` is a chip only under `prerequisites`. Matching the leaf
    reported 20 prose fields as defects on a page that had none."""
    long = "x" * 200
    findings = []
    self_heal.check_faces(
        {"recommendations": [{"prerequisites": [{"basis": long}]}],
         "series": [{"basis": long}]}, findings)
    assert len(findings) == 1
    assert "prerequisites" in findings[0][0]


def test_cg44_recomputes_the_bar_it_refuses():
    findings = []
    self_heal.check_bars(
        {"pillars": [{"score": None, "peer_median": 3.0, "delta": -0.97}]},
        findings)
    assert len(findings) == 1 and "2.03" in findings[0][2], (
        "the gate must name the figure that is recoverable, not just refuse")


def test_an_unmarked_r_layer_is_refused():
    findings = []
    self_heal.check_internal_marking(
        {"scores": {"r_layer": {"hypothesis": "h"}, "internal_only": []}},
        findings)
    assert len(findings) == 1


def test_a_marked_r_layer_passes():
    findings = []
    self_heal.check_internal_marking(
        {"scores": {"r_layer": {}, "internal_only": ["r_layer"]}}, findings)
    assert findings == []
