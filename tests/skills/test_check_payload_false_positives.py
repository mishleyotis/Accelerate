"""The local pre-submit checker may not be stricter than the gate it stands in for.

`check_agreement.py` states the rule the skill's scripts are held to:

    LOCAL ⊆ SERVER, on the classes both of them police.

    A local BLOCK the server does not raise is a FALSE ALARM — it costs a
    producer a repair cycle on content that would have passed.

Measured 2026-08-18 on a promoted-candidate run whose six pages all PASS the
connector's gates, `check_payload.py` was charging 723 blocking findings and 38
warnings against content the server accepts:

    heatmap  629 blocks · server 0      platform  64 blocks · server 0
    context   30 blocks · server 0      overview   0 blocks · 38 warnings

Four rules produced all of it. Every test below comes in a pair — the false
alarm is gone, AND the defect the rule exists for still fires — because a rule
that has stopped costing repair cycles by having stopped working is not a fix.

    A · AG-03 on cell_evidence.cells[*].e_ids .... 629 blocks
    B · raw taxonomy code in client-visible prose ... 94 blocks
    C · CG-09 on context.timeline.arc_shape ........ 1 block
    D · prose does not end in terminal punctuation .. the warnings
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "plugins" / "dma-insights" /
          "skills" / "dma-surface-production" / "scripts" / "check_payload.py")


def _load():
    spec = importlib.util.spec_from_file_location("dma_check_payload", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load()


def run(check, page, payload):
    """Findings from one check, isolated from the module-level accumulator."""
    cp.problems.clear()
    check(page, payload)
    return list(cp.problems)


def blocks(findings):
    return [(p, m) for sev, p, m in findings if sev == "BLOCK"]


def warns(findings):
    return [(p, m) for sev, p, m in findings if sev == "WARN"]


def matching(findings, needle):
    return [(p, m) for p, m in findings if needle in m]


# ─────────────────────────────────────────────────────────────────────
# A · AG-03 exempts a recorded absence carrying its ladder
#
# AG-03's own registry text (apps/mcp/dma_mcp/gates.py): "A null-valued row and
# a recorded absence carrying its ladder assert nothing and are exempt; a state
# claiming a find with an empty id list is a contradiction, not an empty
# state." Both halves are tested — the exemption and its limit.
# ─────────────────────────────────────────────────────────────────────

LADDER = [
    "examplecu.example and blog.examplecu.example — requested; the institution's "
    "own site does not serve its pages to a non-browser client",
    "vendor case studies naming the institution — fetched and mined in full",
    "the prudential regulator's charter record and call-report data — fetched",
    "the app stores' listings for the institution's mobile estate — fetched",
    "a legislative committee transcript (E-CC-188) — retrieved and read in full; "
    "its span was not read across to Digital Strategy Document",
    'Targeted web search: "<institution>" "Digital Strategy Document" — run '
    '17 August 2026, no public account at this grain',
]


def absent_cell(**over):
    """The shape 629 of one run's 705 cells actually take."""
    cell = {
        "subcap_id": "P1C1.1.1",
        "e_ids": [],
        "items": [],
        "thin": True,
        "grounded_on": 0,
        "provenance": "declared",
        "reach_note": "Kept in place with its ladder rather than dropped: the "
                      "searches below are what this run reached.",
        "sources_searched": list(LADDER),
        "synthesis": "The cell is served with its score, its linkage and the "
                     "search, and without a claim it cannot support.",
    }
    cell.update(over)
    return cell


def heatmap_with(cells):
    return {"cell_evidence": {"produced_at": "2026-08-17T00:00:00Z",
                              "producer_version": "1.0.0",
                              "e_ids": ["E-CC-188"],
                              "internal_only": [],
                              "cells": cells}}


def test_a_recorded_absence_with_its_ladder_is_not_an_AG_03_block():
    found = run(cp.check_item_citations, "heatmap", heatmap_with([absent_cell()]))
    assert matching(blocks(found), "AG-03") == []


def test_the_whole_run_of_absences_is_exempt_not_just_one():
    cells = [absent_cell(subcap_id=f"P1C1.1.{i}") for i in range(1, 30)]
    found = run(cp.check_item_citations, "heatmap", heatmap_with(cells))
    assert matching(blocks(found), "AG-03") == []
    assert matching(warns(found), "AG-03") == []


# ── negative controls: the exemption has a floor ──


def test_an_empty_id_list_with_NO_ladder_still_blocks():
    """"Nobody looked" is a research failure, not a finding."""
    naked = absent_cell()
    del naked["sources_searched"]
    found = run(cp.check_item_citations, "heatmap", heatmap_with([naked]))
    hits = matching(blocks(found), "AG-03")
    assert len(hits) == 1
    assert hits[0][0] == "heatmap.cell_evidence.cells[0].e_ids"


def test_an_empty_ladder_list_is_no_ladder_at_all():
    found = run(cp.check_item_citations, "heatmap",
                heatmap_with([absent_cell(sources_searched=[])]))
    assert len(matching(blocks(found), "AG-03")) == 1


def test_a_find_claimed_with_an_empty_id_list_still_blocks():
    """AG-03's own words: a contradiction, not an empty state."""
    claiming = absent_cell(items=[{"excerpt": "The credit union completed a "
                                              "core migration during 2025."}])
    found = run(cp.check_item_citations, "heatmap", heatmap_with([claiming]))
    hits = matching(blocks(found), "AG-03")
    assert len(hits) == 1
    assert hits[0][0] == "heatmap.cell_evidence.cells[0].e_ids"


def test_grounded_on_above_zero_with_an_empty_id_list_still_blocks():
    """Invariant 8 — grounded_on is the LENGTH of the citation list."""
    found = run(cp.check_item_citations, "heatmap",
                heatmap_with([absent_cell(grounded_on=3)]))
    assert len(matching(blocks(found), "AG-03")) == 1


def test_the_ladder_does_not_excuse_a_cell_that_does_cite_badly():
    """A cell that cites is unaffected by the exemption either way."""
    found = run(cp.check_item_citations, "heatmap",
                heatmap_with([absent_cell(e_ids=["E-CC-188"], grounded_on=1)]))
    assert matching(blocks(found), "AG-03") == []


# ─────────────────────────────────────────────────────────────────────
# B · the taxonomy-code rule is about PROSE
#
# 94 blocks on one passing run were `subcap_id`, `catalogue_path`,
# `linked_subcap_ids` and `capped_subcap_ids` — fields that exist to carry ids.
# ─────────────────────────────────────────────────────────────────────

ID_FIELDS = ("subcap_id", "catalogue_path", "linked_subcap_ids",
             "capped_subcap_ids", "capability_ids", "anchor_subcap_id")


@pytest.mark.parametrize("key", ID_FIELDS)
def test_a_taxonomy_code_in_a_field_that_carries_ids_does_not_block(key):
    value = "P2C3.2.1" if key.endswith("_id") or key == "catalogue_path" \
        else ["P2C3.2.1", "P1C1.3.CU1"]
    payload = {"platform_story": {"produced_at": "2026-08-17T00:00:00Z",
                                  "producer_version": "1.0.0",
                                  "e_ids": [], "internal_only": [],
                                  key: value}}
    found = run(cp.check_scalars, "platform", payload)
    assert matching(blocks(found), "raw taxonomy code") == []


@pytest.mark.parametrize("key", ID_FIELDS)
def test_id_bearing_fields_stay_exempt_even_if_the_prose_gate_widens(key, monkeypatch):
    """The exemption is a property of the FIELD, not of today's hint list.

    The 94 blocks came from a prose test wide enough to reach `subcap_id` and
    `catalogue_path`; today's narrower one does not reach them, so the two
    guards agree and neither alone can be seen to work. Widening the gate to
    its limit is what makes the id-bearing exemption observable — and the next
    real widening is exactly when it has to hold.
    """
    monkeypatch.setattr(cp, "is_prose_key", lambda k: True)
    value = "P2C3.2.1" if key.endswith("_id") or key == "catalogue_path" \
        else ["P2C3.2.1", "P1C1.3.CU1"]
    payload = {"cell_evidence": {"produced_at": "2026-08-17T00:00:00Z",
                                 "producer_version": "1.0.0",
                                 "e_ids": [], "internal_only": [], key: value}}
    found = run(cp.check_scalars, "heatmap", payload)
    assert matching(blocks(found), "raw taxonomy code") == []


def test_the_widened_gate_still_blocks_a_code_in_prose(monkeypatch):
    """The control on the control: widening is not itself the exemption."""
    monkeypatch.setattr(cp, "is_prose_key", lambda k: True)
    payload = {"cell_evidence": {"produced_at": "2026-08-17T00:00:00Z",
                                 "producer_version": "1.0.0",
                                 "e_ids": [], "internal_only": [],
                                 "reach_note": "The capability above this cell, "
                                               "P2C2.1, carries one linked row."}}
    found = run(cp.check_scalars, "heatmap", payload)
    assert len(matching(blocks(found), "raw taxonomy code")) == 1


@pytest.mark.parametrize("key", ("body", "synthesis", "rationale", "story_md"))
def test_a_taxonomy_code_inside_genuine_prose_still_blocks(key):
    prose = ("The strongest counter rests on P2C3.2, the capability above this "
             "cell, which carries two citable sources on this run.")
    payload = {"platform_story": {"produced_at": "2026-08-17T00:00:00Z",
                                  "producer_version": "1.0.0",
                                  "e_ids": [], "internal_only": [],
                                  key: prose}}
    found = run(cp.check_scalars, "platform", payload)
    hits = matching(blocks(found), "raw taxonomy code")
    assert len(hits) == 1
    assert hits[0][0] == f"platform.platform_story.{key}"


def test_a_variant_cell_id_in_prose_still_blocks():
    payload = {"platform_story": {"produced_at": "2026-08-17T00:00:00Z",
                                  "producer_version": "1.0.0",
                                  "e_ids": [], "internal_only": [],
                                  "body": "Member onboarding sits at P1C1.3.CU1 "
                                          "on the credit-union workbook."}}
    found = run(cp.check_scalars, "platform", payload)
    assert len(matching(blocks(found), "raw taxonomy code")) == 1


# ─────────────────────────────────────────────────────────────────────
# C · CG-09 on arc_shape is a LEADING vocabulary
#
# The connector marks the field `"leading": True`
# (apps/mcp/dma_mcp/validation.py, `_CONTRACT_VOCABULARIES["context.timeline"]`):
# the badge must be one of five values and the sentence of evidence follows it.
# ─────────────────────────────────────────────────────────────────────

def timeline_with(arc_shape):
    return {"timeline": {"produced_at": "2026-08-17T00:00:00Z",
                         "producer_version": "1.0.0",
                         "e_ids": [], "internal_only": [],
                         "arc_shape": arc_shape, "events": []}}


LEADING_OK = (
    "STEADY_INVESTMENT — six dated events across three years show one "
    "continuous build rather than a restart.",
    "STOP_START — the 2019 programme paused and resumed in 2023.",
    "POST_EVENT_CATCHUP — the 2022 examination is what the roadmap answers.",
    "LEGACY_ANCHORED — every dated event lands on the same 1999 core.",
    "RECENT_ACCELERATION — four of the six events fall inside eighteen months.",
    "STEADY_INVESTMENT",
)


@pytest.mark.parametrize("value", LEADING_OK)
def test_arc_shape_leading_with_its_sentence_of_evidence_does_not_block(value):
    found = run(cp.check_contract_vocabularies, "context", timeline_with(value))
    assert matching(blocks(found), "CG-09") == []


def test_a_coined_arc_shape_still_blocks():
    """The real historical defect: prose in a five-value slot."""
    found = run(cp.check_contract_vocabularies, "context",
                timeline_with("strategy-first, substrate-later"))
    hits = matching(blocks(found), "CG-09")
    assert len(hits) == 1
    assert hits[0][0] == "context.timeline.arc_shape"
    assert "STEADY_INVESTMENT" in hits[0][1]


def test_a_near_miss_badge_still_blocks():
    """The leading token is the badge — 'STEADYISH' is not one of the five."""
    found = run(cp.check_contract_vocabularies, "context",
                timeline_with("STEADYISH_INVESTMENT — a continuous build."))
    assert len(matching(blocks(found), "CG-09")) == 1


def test_a_non_leading_vocabulary_is_still_exact():
    """`signal` is not marked leading, on the server or here."""
    payload = {"timeline": {"produced_at": "2026-08-17T00:00:00Z",
                            "producer_version": "1.0.0",
                            "e_ids": [], "internal_only": [],
                            "events": [{"signal": "POSITIVE — the core landed"}]}}
    found = run(cp.check_contract_vocabularies, "context", payload)
    assert len(matching(blocks(found), "CG-09")) == 1


# ─────────────────────────────────────────────────────────────────────
# D · the terminal-punctuation rule reads the KEY, not the path
#
# The rule asked whether the whole JSON PATH contained "text", "summary" or
# "story", so every leaf on the `context` page matched (via "con-TEXT"), every
# leaf under `exec_summary` matched, and every leaf under `platform_story`
# matched. Ids, enums, timestamps and the r_layer argument record all read as
# clipped prose.
# ─────────────────────────────────────────────────────────────────────

CONTEXT_SECTION = {
    "produced_at": "2026-08-17T00:00:00Z",
    "producer_version": "dma-surface-production/2026-08-17",
    "e_ids": ["E-CC-188", "E-CC-199"],
    "internal_only": ["r_layer", "events[*].internal_note"],
    "claim_label": "FACT",
    "r_layer": {"verdict": "ACCEPT", "confidence": "MEDIUM",
                "probes_run": ["regulator series", "audited year-ends"]},
    "events": [{"event_date": "2026-06-30", "kind": "REGULATORY",
                "signal": "NEUTRAL", "source_title": "US House Committee on "
                                                     "Financial Services"}],
}


def test_ids_enums_and_metadata_on_the_context_page_are_not_read_as_prose():
    found = run(cp.check_scalars, "context", {"timeline": dict(CONTEXT_SECTION)})
    clipped = matching(warns(found), "terminal punctuation")
    assert clipped == [], f"still reading metadata as prose: {clipped}"


def test_the_same_holds_under_exec_summary_and_platform_story():
    """The other two path collisions: 'summary' and 'story' in a SECTION name."""
    for page, section in (("overview", "exec_summary"),
                          ("platform", "platform_story")):
        found = run(cp.check_scalars, page, {section: dict(CONTEXT_SECTION)})
        assert matching(warns(found), "terminal punctuation") == [], (page, section)


def test_a_card_face_label_owes_no_terminal_stop():
    """The contract gives `consequence` 6-14 words — a label, not a paragraph."""
    payload = {"findings": {"produced_at": "2026-08-17T00:00:00Z",
                            "producer_version": "1.0.0",
                            "e_ids": [], "internal_only": [],
                            "findings": [{"consequence": "About $4m a year held "
                                                         "against an unreached "
                                                         "crossing"}]}}
    found = run(cp.check_scalars, "overview", payload)
    assert matching(warns(found), "terminal punctuation") == []


# ── negative control: a clipped paragraph still warns ──


def test_a_genuinely_clipped_prose_field_still_warns():
    clipped = ("The compliance programme is specific and funded: exam-readiness "
               "reviews at $517,000, compliance software at $300,000, and a "
               "staffing step of at least thirty people, all itemised from the "
               "institution's own internal analysis and")
    payload = {"findings": {"produced_at": "2026-08-17T00:00:00Z",
                            "producer_version": "1.0.0",
                            "e_ids": [], "internal_only": [],
                            "findings": [{"body": clipped}]}}
    found = run(cp.check_scalars, "overview", payload)
    hits = matching(warns(found), "terminal punctuation")
    assert len(hits) == 1
    assert hits[0][0] == "overview.findings.findings[0].body"


@pytest.mark.parametrize("key", ("body", "synthesis", "narrative_thread",
                                 "story_md", "rationale"))
def test_every_prose_key_still_gets_the_clipped_check(key):
    clipped = ("The regulator's record puts total assets at $9.688 billion in "
               "June 2026 and the audited year-ends move less than one per cent "
               "across three years which means the trigger has not")
    payload = {"exec_summary": {"produced_at": "2026-08-17T00:00:00Z",
                                "producer_version": "1.0.0",
                                "e_ids": [], "internal_only": [], key: clipped}}
    found = run(cp.check_scalars, "overview", payload)
    assert len(matching(warns(found), "terminal punctuation")) == 1


# ─────────────────────────────────────────────────────────────────────
# The whole-payload claim: on a run the connector passes, the local
# checker raises no block of any of the four repaired classes.
# ─────────────────────────────────────────────────────────────────────

STAGED = Path("/tmp/claude-0/-home-user-Accelerate/"
              "b6f97535-828b-5567-bb3f-29ccb7385dc7/scratchpad/LX_STAGED")
REPAIRED = ("AG-03", "raw taxonomy code", "CG-09", "terminal punctuation")


@pytest.mark.skipif(not STAGED.is_dir(), reason="the staged run is not present")
@pytest.mark.parametrize("page", ["overview", "insights", "heatmap",
                                  "platform", "context", "techstack"])
def test_the_passing_run_raises_none_of_the_four_repaired_classes(page):
    import json
    path = STAGED / f"{page}.json"
    if not path.exists():
        pytest.skip(f"{page}.json not staged")
    payload = json.loads(path.read_text())
    cp.problems.clear()
    for check in (cp.check_scalars, cp.check_item_citations,
                  cp.check_contract_vocabularies):
        check(page, payload)
    found = list(cp.problems)
    for needle in REPAIRED:
        assert matching(blocks(found), needle) == [], needle
        assert matching(warns(found), needle) == [], needle
