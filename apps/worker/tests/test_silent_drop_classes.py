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


# ── class 1: the peer parser invents institutions ─────────────────────────
# Any header outside the fixed 33 spellings became a named peer. Measured
# across the corpus, 28 clients carried at least one peer that is not an
# institution: `Gap_vs_Median`, `Position`, `Peer_Name`, `Cat_ID`,
# `Unknown`, `Quality_Grade`, `ANB_vs_Median`, …

def _peer_tab(tmp_path, rows, name="peers.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Peer_Benchmarks"
    for r in rows:
        ws.append(list(r))
    path = tmp_path / name
    wb.save(path)
    return str(path)


def test_a_gap_column_is_a_statistic_not_a_bank(tmp_path):
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Category", "Fake Trust Bank", "Gap_vs_Median", "Position",
         "Unknown", "Quality_Grade", "Peer_Median"],
        ["P1C1", 2.8, -0.42, "Below", "n/a", "B+", 3.2],
        ["P1C2", 3.1, 0.10, "Above", "n/a", "A-", 3.0],
    ])
    obs = []
    out = parse_peer_benchmarks(path, obs)
    assert [n for n, _ in out[0]["peers"]] == ["Fake Trust Bank"]
    # Gap_vs_Median, Position and Unknown name statistics the parser knows.
    # Quality_Grade names nothing it knows AND holds no score, so it is
    # refused BY NAME instead of joining the cohort as an institution.
    refused = {c["column"] for o in obs
               if o.kind == "peer_column_unrecognised" for c in o.detail["columns"]}
    assert refused == {"Quality_Grade"}


def test_a_real_peer_whose_name_starts_with_delta_is_not_a_statistic(tmp_path):
    """Delta Community is a credit union. A name-only rule that swallowed it
    would drop a peer instead of inventing one — the same defect facing the
    other way, which is why the value on the maturity scale decides."""
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Category", "Delta_Community", "Peer_Median"],
        ["P1C1", 3.4, 3.2],
    ])
    assert [n for n, _ in parse_peer_benchmarks(path)[0]["peers"]] == \
        ["Delta_Community"]


def test_first_united_zero_filled_peer_grid_is_refused_by_name(tmp_path):
    """Five named peers, every score literally 0. Zero is not a maturity
    level; storing it puts five banks on the cohort at M1."""
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Category", "FUB_Score", "Fake Peer One", "Peer_Median"],
        ["P1C1", 1.77, 0, 2.5],
        ["P1C2", 1.86, 0, 2.5],
    ])
    obs = []
    out = parse_peer_benchmarks(path, obs)
    assert [n for n, _ in out[0]["peers"]] == ["FUB_Score"]
    refused = [c for o in obs if o.kind == "peer_column_unrecognised"
               for c in o.detail["columns"]]
    assert refused[0]["column"] == "Fake Peer One"
    assert refused[0]["outside_rubric"] == ["0", "0"]


def test_a_named_peer_nobody_scored_keeps_its_column_and_says_so(tmp_path):
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Category_ID", "Fake Corporate FCU", "Peer_Median"],
        ["P1C1", None, 2.8],
    ])
    obs = []
    out = parse_peer_benchmarks(path, obs)
    assert out[0]["peers"] == [("Fake Corporate FCU", None)]
    assert [o.detail["columns"] for o in obs if o.kind == "peer_column_unscored"] \
        == [["Fake Corporate FCU"]]


# ── class 2: the header is assumed to be physically row 1 ─────────────────
# Seven Peer_Benchmarks tabs and twenty Recommendations tabs put a title, a
# methodology note or a run id above the header. Reading row 1 as the header
# made every column a fragment of that sentence — one client's cohort was an
# institution called "Peer Benchmarks — 5 Locked Corporate-CU Peers".

def test_corporate_america_title_row_above_the_peer_header(tmp_path):
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Peer Benchmarks — 5 Locked Corporate-CU Peers"],
        [],
        ["Category_ID", "Category_Name", "Fake Corporate FCU",
         "Fake Central CU", "Median"],
        ["P1C1", "Digital Strategy", 2.8, 2.9, 2.8],
        ["P1C2", "Governance", 3.3, 3.4, 3.3],
    ])
    out = parse_peer_benchmarks(path)
    assert len(out) == 2
    assert [n for n, _ in out[0]["peers"]] == ["Fake Corporate FCU",
                                               "Fake Central CU"]
    assert out[0]["category_name"] == "Digital Strategy"


def test_payments_canada_category_label_rows_are_category_grain(tmp_path):
    """`P1C1: Digital Strategy & Roadmap` and `P1C1_digital_strategy` are the
    same grain as `P1C1`; requiring the bare id lost the whole cohort."""
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Category", "Fake Clearing House", "Peer_Median"],
        ["P1C1: Digital Strategy & Roadmap", 3.0, 3.1],
        ["P1C2_governance", 2.5, 2.6],
        ["P1C1.1", 2.0, 2.0],          # subcap grain — a different grain
    ])
    out = parse_peer_benchmarks(path)
    assert [r["category_id"] for r in out] == ["P1C1", "P1C2"]


def test_a_peer_tab_with_no_findable_header_refuses_with_a_reason(tmp_path):
    from dma_worker.workbook_parser import parse_peer_benchmarks
    path = _peer_tab(tmp_path, [
        ["Peer_Benchmarks — see Phase 6/7 for full population"],
    ])
    obs = []
    assert parse_peer_benchmarks(path, obs) == []
    assert [o.kind for o in obs] == ["peer_header_not_found"]


# ── class 10: recommendations de-duplicated on the raw first column ───────
# Amarillo National Bank's 29 rows became 0 and Cetera's 24 became 4, because
# the first column repeats a rank or a phase label rather than an id.

def _rec_tab(tmp_path, rows, name="recs.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Recommendations"
    for r in rows:
        ws.append(list(r))
    path = tmp_path / name
    wb.save(path)
    return str(path)


def test_amarillo_title_row_above_the_recommendations_header(tmp_path):
    from dma_worker.workbook_parser import parse_recommendations
    path = _rec_tab(tmp_path, [
        ["PHASE 5 — RECOMMENDATIONS"],
        ["Priority", "Title", "Category", "Horizon"],
        [1, "Unify the agent desktop", "P2C1", "0-6mo"],
        [2, "Retire the batch feed", "P3C2", "6-12mo"],
    ])
    out = parse_recommendations(path)
    assert [r["rec_id"] for r in out] == ["REC-1", "REC-2"]
    assert out[0]["payload"]["title"] == "Unify the agent desktop"


def test_cetera_repeating_first_column_keeps_every_row(tmp_path):
    from dma_worker.workbook_parser import parse_recommendations
    path = _rec_tab(tmp_path, [
        ["Priority", "Title", "Category"],
        ["High", "Unify the agent desktop", "P2C1"],
        ["High", "Retire the batch feed", "P3C2"],
        ["High", "Publish the data contract", "P4C1"],
    ])
    obs = []
    out = parse_recommendations(path, obs)
    assert len(out) == 3, "a repeating rank is not an id"
    assert len({r["rec_id"] for r in out}) == 3
    assert {r["payload"]["title"] for r in out} == {
        "Unify the agent desktop", "Retire the batch feed",
        "Publish the data contract"}
    named = [o for o in obs if o.kind == "recommendation_id_not_unique"]
    assert named[0].detail["rows_qualified_by_position"] == 2


def test_a_recommendations_tab_with_no_header_row_says_so(tmp_path):
    from dma_worker.workbook_parser import parse_recommendations
    path = _rec_tab(tmp_path, [
        [1, "FSC/Sales Cloud"],
        [2, "Data Cloud"],
    ])
    obs = []
    out = parse_recommendations(path, obs)
    assert [o.kind for o in obs] == ["recommendations_header_not_found"]
    assert len(out) == 2 and out[0]["payload"]["col_2"] == "FSC/Sales Cloud"


# ── class 8: the evidence ledger recognised under exactly one tab name ────
# 15 packages ship no `Evidence_Master`; eleven of them name the same tab
# `Evidence_Index`, `Evidence_Linkage_Matrix`, `Evidence_Linkage`,
# `Evidence_Detail` or `Evidence_Register`. Reading one spelling left every
# one of them with zero evidence rows and a NULL linked-evidence counter.

@pytest.mark.parametrize("tab", ["Evidence_Master", "Evidence_Index",
                                 "Evidence_Register", "Evidence_Detail",
                                 "Evidence_Linkage_Matrix"])
def test_zions_evidence_ledger_under_every_shipped_tab_name(tmp_path, tab):
    from dma_worker.workbook_parser import parse_evidence_master
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tab
    ws.append(["Evidence_ID", "Source", "URL", "Tier", "Claim_Type"])
    ws.append(["E-001", "Fake Bank 2026 annual report", "https://x", "T2", "FACT"])
    ws.append(["INT-BOARD-003", "Board minutes", None, "T2", "FACT"])
    path = tmp_path / "ev.xlsx"
    wb.save(path)
    obs = []
    out = parse_evidence_master(str(path), obs)
    assert [e["e_id"] for e in out] == ["E-001", "INT-BOARD-003"]
    assert obs == []


def test_a_package_with_no_evidence_tab_names_what_it_looked_for(tmp_path):
    from dma_worker.workbook_parser import parse_evidence_master
    wb = openpyxl.Workbook()
    wb.active.title = "Executive_Summary"
    path = tmp_path / "ev.xlsx"
    wb.save(path)
    obs = []
    assert parse_evidence_master(str(path), obs) == []
    assert obs[0].kind == "evidence_ledger_tab_not_found"
    assert "Evidence_Master" in obs[0].detail["expected_any_of"]
    assert obs[0].detail["tabs_present"] == ["Executive_Summary"]


def test_a_ledger_whose_ids_are_all_unrecognised_is_not_an_empty_ledger(tmp_path):
    from dma_worker.workbook_parser import parse_evidence_master
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evidence_Master"
    ws.append(["Evidence_ID", "Source", "Tier"])
    ws.append(["EV0001", "Fake source", "T2"])
    ws.append(["EV0002", "Fake source two", "T3"])
    path = tmp_path / "ev.xlsx"
    wb.save(path)
    obs = []
    assert parse_evidence_master(str(path), obs) == []
    assert obs[0].kind == "evidence_ledger_ids_unrecognised"
    assert obs[0].detail["rows_seen"] == 2
