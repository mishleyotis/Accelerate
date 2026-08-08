"""The silent-drop classes, each named for the package that exposed it.

Measured on 2026-08-08 against the 171 client folders under the production
intake tree (153 carry a workbook the classifier recognises). Every case here
is a real shape from that corpus, rebuilt synthetically — no client data lives
in the repo. The governing rule they all encode:

    a reader that does not recognise its input must produce a NAMED
    observation, never an empty result.

A parse that yields zero of something the tab plainly contains is a loud
failure. `test_no_workbook_can_parse_to_a_silent_zero` is the general form;
the rest are the specific spellings measured in the corpus.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.workbook_parser import EID_RE, parse_scoring_workbook


def _pillar_workbook(tmp_path, header, rows, tab="P1_Subcap_Scoring",
                     name="wb.xlsx"):
    """One general_dma pillar-scoring tab, header on row 1."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tab
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    path = tmp_path / name
    wb.save(path)
    return str(path)


_CANON = ["SubCap_ID", "SubCap_Name", "Category", "Score", "Confidence",
          "Evidence_IDs", "Source_URLs", "Evidence_Ceiling", "Caps_Applied",
          "Rationale", "Proxy_Searched"]


def _obs(parse, kind):
    return [o for o in parse.observations if o.kind == kind]


# ── class 6: cell-id format drift parsed to a totally silent zero ──────────
# American Homes - DMA and Wescom Financial - DMA both state CATEGORY ids in
# the SubCap_ID column of a subcapability tab. 1,401 populated rows across
# eight tabs matched nothing: no scores, no observations, not even a
# toggled_out entry — a record indistinguishable from an empty assessment.

def test_american_homes_category_grain_ids_name_themselves(tmp_path):
    path = _pillar_workbook(tmp_path, _CANON, [
        ["P1C1", "Digital Strategy & Vision", "P1C1", 3, "HIGH",
         "E-001,E-002", "https://x", "tier_ceil:5.0", "IR-cap:3.0",
         "[EVIDENCE]: E-001 — roadmap", "Yes"],
        ["P1C1", "Digital Roadmap", "P1C1", 2.5, "HIGH", "E-003", "https://x",
         "tier_ceil:5.0", "", "[EVIDENCE]: E-003 — board deck", "Yes"],
    ])
    p = parse_scoring_workbook(path)
    assert p.scores == []
    named = _obs(p, "unrecognised_cell_id_format")
    assert len(named) == 1
    d = named[0].detail
    assert d["tab"] == "P1_Subcap_Scoring"
    assert d["column"] == "subcap_id"
    assert d["rows_dropped"] == 2
    assert d["found_examples"] == ["P1C1"]
    assert "P" in d["expected"]          # the pattern it wanted, spelled out


def test_no_workbook_can_parse_to_a_silent_zero(tmp_path):
    """The general form: pillar tabs read, nothing came out, said so."""
    path = _pillar_workbook(tmp_path, _CANON, [])
    p = parse_scoring_workbook(path)
    assert not p.scores and not p.toggled_out
    assert p.observations, "an empty parse must name itself"
    assert _obs(p, "workbook_yielded_nothing")[0].detail["tabs_read"] == \
        ["P1_Subcap_Scoring"]


# ── class 5: the rationale column matched by prefix only ──────────────────
# `Scoring_Rationale` is used by 35 scoring tabs across nine clients (ATB,
# AmeriCU, Bell Bank, Cathay Bank, Compeer, Farm Credit Mid America, GESA,
# Wawanesa, Zions). It is the ONLY source of verbatim excerpt text in the
# general_dma generation, so every one of those clients reached the evidence
# drawer with nothing to quote.

@pytest.mark.parametrize("spelling", ["Rationale", "Scoring_Rationale",
                                      "Assessor_Rationale", "Justification",
                                      "Rationale (>=150 chars)"])
def test_zions_scoring_rationale_spelling_is_read(tmp_path, spelling):
    header = [h if h != "Rationale" else spelling for h in _CANON]
    path = _pillar_workbook(tmp_path, header, [
        ["P1C1.1.1", "Board packs", "P1C1", 3, "HIGH", "E-001", "https://x",
         "", "", "[E-001:F1] The board approved a three-year roadmap.", "Yes"],
    ])
    p = parse_scoring_workbook(path)
    assert len(p.scores) == 1
    assert p.scores[0].rationale.startswith("[E-001:F1]")
    assert not _obs(p, "column_not_found")


def test_a_column_the_parser_cannot_find_names_the_tab_and_the_spellings(tmp_path):
    header = [h for h in _CANON if h not in ("Rationale", "Evidence_IDs")]
    path = _pillar_workbook(tmp_path, header, [
        ["P1C1.1.1", "Board packs", "P1C1", 3, "HIGH", "https://x", "", "",
         "Yes"],
    ])
    p = parse_scoring_workbook(path)
    assert len(p.scores) == 1                      # the score still lands
    fields = {o.detail["field"]: o.detail for o in _obs(p, "column_not_found")}
    assert set(fields) == {"rationale", "evidence_ids"}
    for detail in fields.values():
        assert detail["tab"] == "P1_Subcap_Scoring"
        assert detail["expected_any_of"], "must name the spellings it accepts"
        assert detail["headers_present"], "must name what it actually found"


# ── class 4: internal INT- evidence ids silently discarded ────────────────
# The upstream dma-assessment skill's published column spec
# (references/workbook_specification.md, Column F) mandates
# `E-\d{3}` OR `INT-[DOC_ABBREV]-\d{3}`. One shipped package (ATB - DMA)
# carries 341 cells citing internal documents that way.

def test_atb_internal_int_evidence_ids_are_kept(tmp_path):
    path = _pillar_workbook(tmp_path, _CANON, [
        ["P1C1.1.1", "Board packs", "P1C1", 3, "HIGH",
         "E-001, INT-BOARD-003, INT-REQ-045", "https://x", "", "",
         "cited", "Yes"],
    ])
    p = parse_scoring_workbook(path)
    assert p.scores[0].evidence_refs == ["E-001", "INT-BOARD-003", "INT-REQ-045"]


def test_the_published_id_spec_is_what_the_regex_accepts():
    assert EID_RE.findall("E-001, INT-BOARD-002, E-015") == \
        ["E-001", "INT-BOARD-002", "E-015"]
    assert EID_RE.findall("[E-012:F1] and [INT-TECH-001:F2]") == \
        ["E-012:F1", "INT-TECH-001:F2"]


# ── class 7: no score-range check anywhere ────────────────────────────────
# Payments Canada - DMA states 0 in 38 cells. Zero is not a maturity level —
# the rubric is M1..M5 — but it banded as Activating and rendered as a real
# assessment of a barely-started capability.

@pytest.mark.parametrize("stated", [0, -1, 5.5, 7])
def test_payments_canada_score_outside_the_rubric_is_refused(tmp_path, stated):
    path = _pillar_workbook(tmp_path, _CANON, [
        ["P2C3.9.1", "Settlement", "P2C3", stated, "HIGH", "E-001", "", "",
         "", "cited", "No"],
    ])
    p = parse_scoring_workbook(path)
    assert p.scores == [], "an out-of-rubric value must never become a band"
    out = _obs(p, "score_out_of_range")
    assert len(out) == 1
    assert out[0].subcap_id == "P2C3.9.1"
    assert out[0].detail["stated"] == str(stated)
    assert out[0].detail["source_cell"] == "P1_Subcap_Scoring!D2"


@pytest.mark.parametrize("stated", [1, 2.5, 5])
def test_a_score_inside_the_rubric_still_lands(tmp_path, stated):
    path = _pillar_workbook(tmp_path, _CANON, [
        ["P2C3.9.1", "Settlement", "P2C3", stated, "HIGH", "E-001", "", "",
         "", "cited", "No"],
    ])
    p = parse_scoring_workbook(path)
    assert len(p.scores) == 1 and not _obs(p, "score_out_of_range")
