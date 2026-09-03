"""One run, start to ingest — the chain the audit said could not finish.

AUD-0003: "An unattended run to the owner's specification cannot currently
finish: one of its three mandatory deliverables has nothing that produces it,
a second is produced in a format the ingest classifier rejects, and the third
is produced once at the end from a substrate the agents never wrote."

This test is that sentence, inverted and executed. It drives the engine's own
command line — no private helpers — from `start` to two .docx files, then
hands the artefacts to the app's classifier and parser."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "plugins" / "dma-insights" / "skills" / "dma-research"
sys.path.insert(0, str(REPO / "apps" / "worker"))

from engine import contract as C, ledger as L, report_spec as RS   # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import (close_prelim, fire_volleys, make_shippable,  # noqa: E402
                      sign_off_sections, synthesise)
from engine import floors_gate, runstate                           # noqa: E402


def cli(*args):
    r = subprocess.run([sys.executable, "-m", "engine.cli", *args],
                       cwd=str(SKILL), capture_output=True, text=True,
                       timeout=600)
    return r


CATS = ("P1C1", "P2C1")


@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    """A small but COMPLETE run: two categories, gate-passing, reported."""
    root = tmp_path_factory.mktemp("e2e")
    tax = C.taxonomy()
    # The CU engagement set, then narrowed to two categories — not
    # `cells_in`, which returns every sub-vertical's variants and would seed
    # a CU run with AM and CL cells.
    engagement = set(tax.selected("CU", "T1_CORE"))
    selected = [c for cat in CATS
                for c in [x for x in tax.cells_in(cat) if x in engagement][:9]]
    run = runstate.start(
        run_id="E2E-1", entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=root / "run", selected=selected)
    # The three phases a real run does before any category: the binding
    # preflight (which banks the financial review), the client folder, and
    # PRELIM. Without them `orient` withholds every card and the handoff
    # refuses a workbook with empty tabs — both correctly.
    from engine import assemble as _asm
    _asm.open_folder(run, root / "client", push=False)
    close_prelim(run)
    wb = run.open()

    ev = {}
    for i, cell in enumerate(wb.selected_subcaps()):
        # All five volleys per cell — the gate counts them (2026-09-03).
        fire_volleys(wb, cell, n=2)
        # Two source identities per subcap: single_source_fact (a blocking
        # gate term since the 2026-08-29 calibration) refuses a FACT whose
        # whole base is one host, and the synthesis below claims two
        # independent sources agree.
        eids = [L.append_evidence(
            wb,
            source_name=("NCUA Call Report 2025 — digital channel volumes"
                         if j == 2 else f"Acme 2025 annual report p{j}"),
            source_url=(f"https://ncua.example/callreport/2025#{cell}"
                        if j == 2 else
                        f"https://acme.example/ar25#{cell}-{j}"),
            tier="T2",
            excerpt=("Alkami digital banking went live in Q3 2024 and reached "
                     f"47 percent member adoption within ninety days, "
                     f"restated at {50 + j} percent in the 2025 report."),
            subcaps=[cell], published="2025-03-01") for j in range(3)]
        ev[cell] = eids
        synthesise(wb, cell, _synthesis(cell, eids))

    from fixtures import client_facts, score_stage, write_both_reports
    client_facts(wb, wb.selected_subcaps(), ev)
    for cat in CATS:
        wb.append("Entity_Timeline", {
            "Event_Date": "2024-09-01",
            "Title": "Alkami digital banking go-live",
            "Kind": "PLATFORM", "Signal": "POSITIVE",
            "Signal": "EXPANSION",
            "SubCap_IDs": ", ".join(
                c for c in wb.selected_subcaps() if c.startswith(cat)),
            "Evidence_IDs": "E-001"})
        v = floors_gate.run(wb, cat, require_synthesis=True, qa_dir=run.qa_dir)
        assert v["gate"] == "PASS", (cat, v["blocking"])

    # Then the SCORING stage — column D, critic, rollup, gate — and both
    # reports through the writer under the stage preconditions (2026-09-03:
    # no report before scoring). The render itself is the `report` test.
    make_shippable(wb)
    score_stage(run, wb, wb.selected_subcaps(), ev)
    write_both_reports(run, wb, wb.selected_subcaps(), ev, render=False)
    return run


def _synthesis(cell, eids):
    cite = " ".join(f"[{e}:F1]" for e in eids[:2])
    return {
        "Dominant_Claim": ("Acme Credit Union runs member-facing digital "
                           "banking on Alkami with measured adoption."),
        "Claim_Label": "FACT",
        "What_We_Found": (
            f"Alkami digital banking went live in Q3 2024 {cite} and the 2025 "
            "annual report restates member adoption at 52 percent, up from 47 "
            "percent at ninety days. The board reviews the figure quarterly "
            "and it is owned by the Chief Digital Officer of Acme Credit "
            "Union."),
        "Facet_Coverage": "works, value, corroborates",
        "DQ_Works": ("Alkami went live in Q3 2024; adoption 47 percent at "
                     "ninety days and 52 percent in the 2025 report."),
        "DQ_Fails": ("NOT_RUN: four adversarial queries across 2023-2026 "
                     "surfaced no delayed or descoped programme."),
        "DQ_Value": ("Adoption is reported quarterly to the board and is tied "
                     "to the 2025 cost-to-serve target."),
        "DQ_Corroborates": ("The 2025 NCUA call report names the same digital "
                            "channel volumes for this institution."),
        "DQ_Contradicts": ("NOT_RUN: no enforcement action, complaint or "
                           "abandoned programme found for Acme in 2023-2026."),
        "Triangulation": (f"Two independent sources agree on the launch date "
                          f"and the adoption figure {cite}."),
        "Ceiling_Reasoning": ("Deployment plus measured utilisation supports a "
                              "Competing ceiling for this cell, not "
                              "Differentiating."),
        "Why_It_Matters": ("Adoption at this level changes which channel the "
                           "2026 cost-to-serve programme can lean on."),
        "DMA_Impact": ("Lifts the digital channel from Building to Competing "
                       "on measured utilisation, not on deployment alone."),
        "Ceiling_Band": "Competing", "Uncertainty": 0.3,
        "Challenge_Verdict": "PASS",
    }


def test_the_workbook_carries_the_whole_run(finished_run):
    wb = finished_run.open()
    assert len(wb.rows("Search_Log")) == 90       # 18 subcaps x 5 volleys
    assert len(wb.rows("Evidence_Detail")) == 56  # 18 x 3, + 2 profile rows
    gates = wb.rows("Gate_Log")
    assert [g["Scope"] for g in gates if g["Gate"] == "FLOORS"] == list(CATS)
    # then the scoring stage: opened, a critic per pillar, the gate itself
    assert [g["Gate"] for g in gates if g["Gate"].startswith("SCORING")] == \
        ["SCORING_OPENED", "SCORING_CRITIC", "SCORING_CRITIC", "SCORING"]
    assert gates[-1]["Gate"] == "SCORING" and gates[-1]["Verdict"] == "PASS"
    assert all(r["Dominant_Claim"] for r in wb.scoring_rows())
    assert wb.verify_handoff_lock() == []


def test_the_run_carries_its_institution_not_only_its_capabilities(finished_run):
    """Requirement 3, on the substrate: a run that profiled nobody has an
    empty Entity_Timeline, Peer_Benchmarks and Tech_Register — the Golden 1
    shape. These are the tabs PRELIM fills."""
    wb = finished_run.open()
    assert len(wb.rows("Entity_Timeline")) >= 3
    assert len(wb.rows("Peer_Benchmarks")) >= 1
    assert len(wb.rows("Tech_Register")) >= 1
    prelim_rows = {r["Section_ID"] for r in wb.rows("Report_Narrative")
                   if str(r.get("Section_ID") or "").startswith("PRELIM-")}
    assert {"PRELIM-FIN", "PRELIM-FIRM", "PRELIM-LEAD"} <= prelim_rows
    md = wb.metadata()
    assert md["prelim_status"] == "COMPLETE"
    assert md["preflight_sha"] and md["client_folder"]


def test_the_run_validates_against_its_own_contract(finished_run):
    r = cli("validate", "--run", "E2E-1", "--root", str(finished_run.root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAILS=0" in r.stdout


def test_orient_reports_the_run_clean_only_when_it_is(finished_run):
    r = cli("orient", "--run", "E2E-1", "--root", str(finished_run.root),
            "--category", "P1C1")
    out = json.loads(r.stdout)
    assert out["clean"] is True
    assert out["gate"]["P1C1"]["gate"] == "PASS"


# ── 2 · three artefacts, each with a producer ───────────────────────────

def test_the_handoff_is_built_and_names_the_workbook_as_authority(finished_run):
    r = cli("handoff", "--run", "E2E-1", "--root", str(finished_run.root))
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads((finished_run.deliverables / "research_handoff.json")
                     .read_text())
    assert doc["_contract"]["authority"] == "the scoring workbook"
    assert doc["counts"]["cells"] == 851
    assert all(rec["research_synthesis"]["triangulation"]
               for rec in doc["subcap_records"])


def test_both_reports_render(finished_run):
    r = cli("report", "--run", "E2E-1", "--root", str(finished_run.root))
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert len(out) == 2
    for row in out:
        assert row["unresolved"] == [] and row["problems"] == []
        assert Path(row["path"]).exists()


def test_the_three_artefacts_exist_and_are_the_named_three(finished_run):
    names = sorted(p.name for p in finished_run.root.rglob("*")
                   if p.suffix in (".xlsx", ".docx"))
    assert any(n.startswith("DMA_Scoring_Workbook_") for n in names)
    assert any(n.startswith("Client_Profile_Research_") for n in names)
    assert any(n.startswith("DMA_Assessment_Report_") for n in names)


# ── 3 · the app can ingest all three ────────────────────────────────────

def test_every_artefact_is_classified_by_the_app(finished_run):
    from dma_worker.classification import classify
    kinds = {}
    for p in finished_run.root.rglob("*"):
        if p.suffix not in (".xlsx", ".docx", ".json"):
            continue
        c = classify(p.name)
        if c:
            kinds[c.kind] = p.name
    for kind in ("scoring_workbook", "assessment_report", "client_profile"):
        assert kind in kinds, f"{kind} is unclassifiable; got {sorted(kinds)}"


def test_the_artefact_grouper_takes_the_workbook_and_the_report(finished_run):
    sys.path.insert(0, str(REPO / "apps" / "worker"))
    import job_main

    class F:
        def __init__(self, name):
            self.name = name
            self.path_segments = ["Acme Credit Union - DMA", "09_deliverables"]

    got = {}
    for p in sorted(finished_run.root.rglob("*")):
        if p.suffix not in (".xlsx", ".docx", ".json"):
            continue
        c = job_main._classify_artefact(F(p.name))
        if c:
            got[c[0]] = p.name
    assert "workbook" in got and got["workbook"].startswith("DMA_Scoring_")
    assert "report" in got and got["report"].startswith("DMA_Assessment_Report_")


def test_the_app_parses_the_workbook_and_keeps_every_linkage(finished_run):
    from dma_worker import workbook_parser as wp
    p = wp.parse_scoring_workbook(str(finished_run.workbook_path))
    # a FINISHED run is scored: eighteen scores in column D, nothing left
    # unscored, and the workbook says so
    assert len(p.scores) == 18 and p.toggled_out == []
    assert p.in_scope_unscored == []
    stage = [o for o in p.observations if o.kind == "workbook_stage"][0]
    assert stage.detail["stage"].startswith("assessment")

    r = wp.parse_research_workbook(str(finished_run.workbook_path))
    # 18 subcaps x 3 sources, plus the two PRELIM profile rows (the binding
    # preflight's financial statement and the institution profile). Those
    # two support the CLIENT, not a capability cell, so they carry no
    # subcap — and the app tolerates that per row, which this pins.
    ledger = r["ledger"]
    assert len(ledger) == 56
    unmapped = [x["e_id"] for x in ledger if not x["subcaps"]]
    assert len(unmapped) == 2, unmapped
    assert all(x["source_url"] and x["published_date"] for x in ledger)


def test_the_report_the_app_reads_carries_the_workbooks_own_figures(finished_run):
    from dma_worker.report_parser import parse_report
    wb = finished_run.open()
    path = next(finished_run.deliverables.glob("DMA_Assessment_Report_*.docx"))
    sections = parse_report(str(path))
    assert sections, "the app's report parser found no sections"
    doc = Document(str(path))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    # the Doc's §10 carries the Coverage_Map, curated from the sheet
    cov = wb.rows("Coverage_Map")[0]
    assert cov["category_id"] in cells
    assert str(cov["subcaps"]) in cells
    roll = {r["pillar_id"]: r for r in wb.rows("Pillar_Rollup")}
    assert str(roll["P1"]["score"]) in cells


# ── 4 · the strip, last, and only once the analysis has survived ────────

def test_the_working_area_strips_only_after_the_handoff_carries_it(finished_run):
    import openpyxl
    r = cli("strip", "--run", "E2E-1", "--root", str(finished_run.root))
    assert r.returncode == 0, r.stdout + r.stderr
    book = openpyxl.load_workbook(finished_run.workbook_path)
    assert book["P1_Subcap_Scoring"].max_column == 11
    doc = json.loads((finished_run.deliverables / "research_handoff.json")
                     .read_text())
    rec = doc["subcap_records"][0]["research_synthesis"]
    for f in ("triangulation", "why_it_matters", "dma_impact"):
        assert rec[f], f"{f} did not survive the strip"
