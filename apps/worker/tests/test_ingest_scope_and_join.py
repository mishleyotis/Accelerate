"""Ingestion tells scope from emptiness, and reads the column it censuses.

Two findings with the same shape: a fact the parser HAD and did not use.
Both are exercised against a workbook the research engine actually produced,
because a synthetic fixture proves the code path and not the contract."""
import json
import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # apps/worker
sys.path.insert(0, str(REPO / "plugins" / "dma-insights" / "skills"
                       / "dma-research"))

from dma_worker import workbook_parser as wp   # noqa: E402


def _engine_workbook(tmp_path, *, n=6, synthesise=2):
    from engine import ledger as L, runstate, contract as C
    tax = C.taxonomy()
    selected = list(tax.cells_in("P1C1"))[:n]
    run = runstate.start(run_id="ING-1", entity_name="Acme Credit Union",
                         entity_id="acme-cu", sub_vertical="CU",
                         scope_mode="T1_CORE", reference_date="2026-08-29",
                         root=tmp_path / "run", selected=selected)
    wb = run.open()
    for cell in wb.selected_subcaps()[:synthesise]:
        eids = [L.append_evidence(
            wb, source_name=f"Annual report {i}",
            source_url=f"https://acme.example/ar#{i}", tier="T2",
            excerpt=("Alkami digital banking went live in Q3 2024 and reached "
                     "47 percent member adoption within ninety days."),
            subcaps=[cell], published="2025-03-01") for i in range(3)]
        L.append_synthesis(wb, cell, {
            "Dominant_Claim": (
                "Acme Credit Union runs member-facing digital banking on "
                "Alkami with measured adoption."),
            "Claim_Label": "FACT",
            "What_We_Found": (
                f"Alkami went live in Q3 2024 [{eids[0]}:F1] and the 2025 "
                "annual report restates member adoption at 52 percent, up "
                "from 47 percent at ninety days, reported quarterly to the "
                "board of Acme Credit Union."),
            "Facet_Coverage": "works, value",
            "DQ_Works": (
                "Alkami went live in Q3 2024; adoption 47 percent at ninety "
                "days and 52 percent in the 2025 report."),
            "DQ_Fails": "NOT_RUN: no descoped programme found in four queries.",
            "DQ_Value": (
                "Adoption is reported quarterly to the board and is tied to "
                "the 2025 cost-to-serve target."),
            "DQ_Corroborates": (
                "The 2025 NCUA call report names the same digital channel "
                "volumes for this institution."),
            "DQ_Contradicts": "NOT_RUN: no enforcement or complaint found.",
            "Triangulation": (
                f"Two independent sources agree on the launch date and the "
                f"adoption figure [{eids[0]}:F1] [{eids[1]}:F1]."),
            "Ceiling_Reasoning": (
                "Deployment plus measured utilisation supports a Competing "
                "ceiling for Acme Credit Union, not Differentiating."),
            "Why_It_Matters": (
                "Adoption at this level changes which channel the 2026 "
                "cost-to-serve programme can lean on."),
            "DMA_Impact": (
                "Lifts the digital channel from Building to Competing on "
                "measured utilisation, not on deployment alone."),
            "Ceiling_Band": "Competing", "Uncertainty": 0.3,
            "Challenge_Verdict": "PASS",
        })
    return run


# ── AUD-0014 · in scope and unscored is not out of scope ─────────────────

def test_a_research_stage_workbook_is_not_reported_as_inapplicable(tmp_path):
    """The measured defect: 0 of 49 scores, 44 of 49 rows reclassified
    `toggled_out` — 'variant cells excluded by the toggle cascade' — on a
    workbook whose empty scores ARE the contract."""
    run = _engine_workbook(tmp_path, n=6, synthesise=2)
    p = wp.parse_scoring_workbook(str(run.workbook_path))
    assert p.scores == []
    assert p.toggled_out == [], "no universal cell may be called inapplicable"
    assert len(p.in_scope_unscored) == 6


def test_the_stage_is_reported_once_not_once_per_row(tmp_path):
    run = _engine_workbook(tmp_path, n=6)
    p = wp.parse_scoring_workbook(str(run.workbook_path))
    stages = [o for o in p.observations if o.kind == "workbook_stage"]
    assert len(stages) == 1
    d = stages[0].detail
    assert d["stage"].startswith("research")
    assert d["in_scope_unscored"] == "6" and d["scored"] == "0"
    assert [o for o in p.observations if o.kind == "missing_score"] == []


def test_a_sub_vertical_variant_is_still_toggled_out(tmp_path):
    """The control: `toggled_out` keeps its documented meaning. A fix that
    emptied the bucket would delete the toggle cascade instead of the bug.

    Built with openpyxl rather than through the engine ON PURPOSE. The
    engine now REFUSES to seed another sub-vertical's variants
    (contract.Taxonomy.selected / AUD-0077), so this shape can only arrive
    from a package the engine did not produce — which is exactly the case
    the parser exists for, and the case this test has to cover."""
    import openpyxl
    from engine import contract as C
    tax = C.taxonomy()
    universal = list(tax.cells_in("P1C1"))[:2]
    variants = [c for c in tax.variants if c.startswith("P1C1")][:2]
    assert variants, "the catalogue must carry P1C1 variants for this to bind"

    path = tmp_path / "foreign_package.xlsx"
    book = openpyxl.Workbook()
    ws = book.active
    ws.title = "P1_Subcap_Scoring"
    ws.append(["SubCap_ID", "SubCap_Name", "Category", "Score", "Confidence",
               "Evidence_IDs", "Source_URLs", "Evidence_Ceiling",
               "Caps_Applied", "Rationale", "Proxy_Searched"])
    for cell in universal + variants:
        ws.append([cell, "name", cell.split(".")[0], None, None, None, None,
                   None, None, None, None])
    book.save(path)

    p = wp.parse_scoring_workbook(str(path))
    assert sorted(p.toggled_out) == sorted(variants)
    assert sorted(p.in_scope_unscored) == sorted(universal)


# ── AUD-0067 · the column that was censused and never read ───────────────

def test_every_evidence_row_keeps_its_capability_linkage(tmp_path):
    """4 of 4 ledger rows returned `subcaps: []` while Evidence_Detail
    carried "P1C1.1.1, P1C1.1.5" in 4 of 4 — because the read used a
    hardcoded two-name lookup while the contract column is `SubCap_IDs`,
    and the module's own alias table already knew the third name."""
    run = _engine_workbook(tmp_path, n=4, synthesise=2)
    r = wp.parse_research_workbook(str(run.workbook_path))
    rows = r["ledger"]
    assert rows, "the research reader found no ledger rows at all"
    unlinked = [x["e_id"] for x in rows if not x.get("subcaps")]
    assert unlinked == [], unlinked


def test_the_alias_table_and_the_read_cannot_disagree_again():
    """The defect was that the census used the alias table and the read did
    not. Asserting the contract column IS in the table is what keeps the two
    together."""
    assert "subcap_ids" in wp._EV_ALIASES["subcaps"]


# ── AUD-0091 · the package evidence index is read, and only fills gaps ───

def _index(tmp_path, items):
    p = tmp_path / "evidence_index.json"
    p.write_text(json.dumps({"items": items}))
    return p


def test_the_package_evidence_index_is_parsed(tmp_path):
    p = _index(tmp_path, [{
        "evidence_id": "E-001", "url": "https://x.example/a", "tier": "T2",
        "date_published": "2025-03-01", "subcaps_supported": "P1C1.1.1",
        "excerpt": "A verbatim span of at least fifty characters, taken "
                   "from the source document itself."}])
    obs = []
    rows = wp.parse_evidence_index(str(p), obs)
    assert len(rows) == 1
    assert rows[0]["source_url"] == "https://x.example/a"
    assert rows[0]["subcaps"] == ["P1C1.1.1"]


def test_the_index_fills_a_url_the_workbook_left_blank(tmp_path):
    """Gate M exists because a client shipped 85% unURLed while this file
    carried 752 items and 748 URLs."""
    p = _index(tmp_path, [{"id": "E-001", "url": "https://x.example/a"}])
    obs = []
    wbrows = [{"e_id": "E-001", "source_url": None, "source_name": "AR",
               "tier": "T2", "ers": None, "published_date": None,
               "stated_recency": None, "claim_type": "FACT",
               "fact_count": 1, "excerpt": None, "subcaps": ["P1C1.1.1"]}]
    merged = wp.merge_evidence_sources(
        wbrows, wp.parse_evidence_index(str(p), obs), obs)
    assert merged[0]["source_url"] == "https://x.example/a"
    assert any(o.kind == "evidence_index_merged" for o in obs)


def test_the_index_never_overwrites_what_the_workbook_stated(tmp_path):
    """The workbook is the artefact under assessment. A disagreement is
    recorded, never resolved in the index's favour."""
    p = _index(tmp_path, [{"id": "E-001", "url": "https://index.example/z"}])
    obs = []
    wbrows = [{"e_id": "E-001", "source_url": "https://workbook.example/a",
               "source_name": "AR", "tier": "T2", "ers": None,
               "published_date": None, "stated_recency": None,
               "claim_type": "FACT", "fact_count": 1, "excerpt": None,
               "subcaps": []}]
    merged = wp.merge_evidence_sources(
        wbrows, wp.parse_evidence_index(str(p), obs), obs)
    assert merged[0]["source_url"] == "https://workbook.example/a"
    dis = [o for o in obs if o.kind == "evidence_index_disagreement"]
    assert dis and dis[0].detail["count"] == "1"


def test_an_unreadable_index_is_reported_not_silently_empty(tmp_path):
    p = tmp_path / "evidence_index.json"
    p.write_text("{not json")
    obs = []
    assert wp.parse_evidence_index(str(p), obs) == []
    assert [o.kind for o in obs] == ["evidence_index_unreadable"]


def test_an_unrecognised_shape_is_reported(tmp_path):
    p = tmp_path / "evidence_index.json"
    p.write_text(json.dumps({"something_else": {}}))
    obs = []
    assert wp.parse_evidence_index(str(p), obs) == []
    assert [o.kind for o in obs] == ["evidence_index_shape_unrecognised"]


def test_the_classifier_now_admits_the_evidence_index():
    """It was classified `package_structured` by classification.py, recorded
    by the scanner, and then dropped because the artefact grouper accepted
    nothing but manifest.json and the Office formats."""
    sys.path.insert(0, str(REPO / "apps" / "worker"))
    import job_main
    assert job_main._classify_artefact(
        type("F", (), {"name": "evidence_index.json", "path_segments":
                       ["client", "01_evidence"]})()) == ("evidence_index", 0)


# ── AUD-0042 · a peer store with no feeder says so ──────────────────────

def test_a_workbook_with_no_peer_tab_records_the_absence(tmp_path):
    """The missing-tab path returned [] in silence, so a package with no
    peer tab was indistinguishable from one whose peers all parsed — and
    every peer median served for it then had nothing to reconcile against."""
    import openpyxl
    path = tmp_path / "no_peers.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "P1_Subcap_Scoring"
    book.save(path)
    obs = []
    assert wp.parse_peer_benchmarks(str(path), obs) == []
    kinds = [o.kind for o in obs]
    assert "peer_tab_absent" in kinds
    detail = [o for o in obs if o.kind == "peer_tab_absent"][0].detail
    assert "ET-09" in detail["consequence"]


def test_the_engine_writes_a_peer_tab_the_app_can_read(tmp_path):
    """AUD-0042's other half: nothing produced the tab. The engine's
    contract now carries it, under the app's own column spellings."""
    from engine import contract as C
    run = _engine_workbook(tmp_path, n=2, synthesise=0)
    wb = run.open()
    wb.append("Peer_Benchmarks", {
        "Category_ID": "P1C1", "Category_Name": "Digital Strategy",
        "Entity_Score": None, "Peer_Median": 2.4, "Peer_N": 5,
        "Peer_Basis": "table", "Source_Cell": "Peer_Benchmarks!D2",
        "Peer_Names": "Alpha CU|Beta CU", "As_Of": "2026-08-29"})
    obs = []
    rows = wp.parse_peer_benchmarks(str(run.workbook_path), obs)
    assert [o.kind for o in obs if o.kind == "peer_tab_absent"] == []
    assert rows or [o.kind for o in obs], (
        "the tab exists, so the reader must either return rows or say why not")
