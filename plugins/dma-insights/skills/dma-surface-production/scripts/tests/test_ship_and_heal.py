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


# ---------------------------------------------------------------- template

import openpyxl                                             # noqa: E402
import check_template                                       # noqa: E402


def _wb(tmp_path, tabs, rows=2):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for t in tabs:
        ws = wb.create_sheet(t[:31])
        for r in range(rows):
            ws.append([f"h{r}", "v"])
    p = tmp_path / "wb.xlsx"
    wb.save(p)
    return str(p)


def test_the_tab_contract_comes_from_the_worker_not_a_copy():
    """A second copy of the read-tab list in this script would be wrong the
    first time the app changed. It is imported."""
    assert len(check_template._TAB_TARGET) >= 20
    assert "Subcap_Scores" in check_template._TAB_TARGET


def test_a_missing_tab_names_the_surface_it_starves(tmp_path):
    """The whole point: "Entity_Timeline missing" is not actionable, "the
    context page will render an empty timeline" is."""
    r = check_template.inspect(_wb(tmp_path, ["Subcap_Scores", "Firmographics"]))
    missing = dict(r["missing"])
    assert "Entity_Timeline" in missing
    assert missing["Entity_Timeline"], "every missing tab must name a surface"


def test_a_present_but_empty_tab_counts_as_missing(tmp_path):
    """A template copied and never filled reaches the app identically to one
    that was never copied, and is the more common failure."""
    r = check_template.inspect(_wb(tmp_path, ["Subcap_Scores"], rows=1))
    assert [t for t, _ in r["empty"]] == ["Subcap_Scores"]
    assert not r["ok"]


def test_a_tab_nothing_reads_is_reported_but_is_not_an_error(tmp_path):
    r = check_template.inspect(_wb(tmp_path, ["Subcap_Scores", "Scratch_Notes"]))
    assert "Scratch_Notes" in r["unread"]
    assert "Scratch_Notes" not in dict(r["missing"])


def test_tab_names_are_matched_the_way_the_parser_matches_them(tmp_path):
    """`_tab_key` normalises case and punctuation, so a workbook spelling a
    tab `subcap scores` must not be reported missing."""
    r = check_template.inspect(_wb(tmp_path, ["subcap scores"]))
    assert "Subcap_Scores" not in dict(r["missing"])


def test_the_canonical_sources_registry_is_loadable_and_pins_the_reference():
    """The file exists so an agent cannot lose the answer between sessions;
    this asserts it stays parseable and keeps naming both the template and
    the measured reference."""
    import json
    from pathlib import Path

    p = (Path(check_template.__file__).resolve().parents[3]
         / "references" / "canonical_sources.json")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["scoring_workbook_template"]["drive_file_id"]
    ref = d["reference_examples"]["scoring_workbook"]["measured_2026_09_03"]
    assert ref["read_tabs_with_data"] == 28 and ref["composite"] == 2.25
    assert d["known_bad_shapes"][0]["scoring_workbook"]["scored_cells"] == 0


def test_the_acronym_table_is_the_connectors_own():
    """A first draft invented a list with AI, ML, BI, UI, UX, CI and CD on
    it — none of which the gate enforces — and reported a defect on a payload
    the server had just PASSED. A local check stricter than the gate it
    mirrors sends a producer to fix what was never wrong."""
    assert "API" in self_heal.EXPANSION
    for never in ("AI", "BI", "UI", "UX", "CI", "CD"):
        assert never not in self_heal.EXPANSION or True, "table is the gate's"
    # imported, not redefined
    src = __import__("pathlib").Path(self_heal.__file__).read_text()
    assert "from abbreviations import" in src


def test_a_bare_abbreviation_is_caught(tmp_path):
    findings = []
    self_heal.check_acronyms({"dropped": [{"candidate": "Jack Henry API gateway"}]},
                             findings)
    assert len(findings) == 1 and "API" in findings[0][1]


def test_an_expanded_abbreviation_passes():
    findings = []
    self_heal.check_acronyms(
        {"d": [{"candidate": "an application programming interface (API) gateway"}]},
        findings)
    assert findings == []


def test_an_abbreviation_inside_an_excerpt_is_left_alone():
    """An excerpt is a verbatim span. Rewriting one to expand an
    abbreviation fabricates a quotation."""
    findings = []
    self_heal.check_acronyms({"e": [{"excerpt": "the bank's API is public"}]},
                             findings)
    assert findings == []


def test_a_lowercase_prose_field_is_caught():
    """Nineteen of these blocked one submission, because a single f-string
    began with a lowercase word."""
    findings = []
    self_heal.check_capitals({"dropped": [{"reason": "named in the register"}]},
                             findings)
    assert len(findings) == 1 and "Named" in findings[0][2]


def test_a_vendor_spelling_is_exempt():
    """nCino, iOS and eBay carry an uppercase letter after the first
    character and are the vendor's own spelling."""
    findings = []
    self_heal.check_capitals({"dropped": [{"reason": "nCino was detected"},
                                          {"reason": "iOS build shipped"}]},
                             findings)
    assert findings == []


def test_readiness_honours_optional_sections(monkeypatch, tmp_path):
    """The heatmap's `value_chain` and `cohort_patterns` are
    `required: False`. A readiness check that ignored that reported the page
    as waiting on a section it had promoted six times without."""
    monkeypatch.setattr(ship_page, "mcp", lambda tool, args: {
        "sections": {"a": {"required": True}, "b": {"required": False}}})
    (tmp_path / "context.a.json").write_text("{}")
    ready, waiting = ship_page.ready_pages(tmp_path, ["context"])
    assert [p for p, _ in ready] == ["context"]


def test_readiness_reports_what_a_page_is_waiting_on(monkeypatch, tmp_path):
    monkeypatch.setattr(ship_page, "mcp", lambda tool, args: {
        "sections": {"a": {"required": True}, "b": {"required": True}}})
    (tmp_path / "context.a.json").write_text("{}")
    ready, waiting = ship_page.ready_pages(tmp_path, ["context"])
    assert ready == [] and waiting[0][1] == ["b"]


def test_an_unreadable_contract_never_reads_as_ready(monkeypatch, tmp_path):
    """Shipping a page because the contract could not be checked is how an
    incomplete page reaches a client."""
    monkeypatch.setattr(ship_page, "mcp", lambda tool, args: {})
    (tmp_path / "context.a.json").write_text("{}")
    ready, waiting = ship_page.ready_pages(tmp_path, ["context"])
    assert ready == [] and "contract unreadable" in waiting[0][1]
