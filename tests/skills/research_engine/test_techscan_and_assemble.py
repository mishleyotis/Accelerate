"""The fourth deliverable, and the folder that ships all four."""
import json

import pytest
from docx import Document

from engine import assemble, contract as C, techscan
from engine.techscan import ScanRefused

from fixtures import (CAT, bank_evidence, good_synthesis,  # noqa: E501
                      make_shippable, new_run,
                      sign_off_sections, synthesise)

EXCERPT = ("Alkami digital banking went live in Q3 2024 and reached 47 "
           "percent member adoption within ninety days of launch.")


def _run_with_scan(tmp_path, n=3, prelim=False):
    # prelim=False by default: PRELIM records a technology baseline of its
    # own, and the register tests count the rows they write themselves. The
    # PACKAGE tests pass prelim=True, because a package that ships without
    # PRELIM is the shape requirement 3 was raised about.
    run = new_run(tmp_path, n=n, prelim=prelim)
    wb = run.open()
    cells = wb.selected_subcaps()
    eids = bank_evidence(wb, cells[0])
    techscan.record(wb, product="Alkami Digital Banking", vendor="Alkami",
                    layer="CUST", status="CONFIRMED",
                    method="public_document",
                    basis="named live in the 2025 annual report with an "
                          "adoption figure",
                    providers=["clay", "exa"],
                    subcaps=[cells[0]], evidence_ids=eids,
                    source_urls=["https://acme.example/ar25"])
    techscan.record(wb, product="Snowflake Data Cloud", vendor="Snowflake",
                    layer="DATA", status="INFERRED", method="job_posting",
                    providers=["indeed"],
                    basis="two 2026 postings name Snowflake administration")
    techscan.record(wb, product="nCino Bank Operating System", vendor="nCino", layer="OPS",
                    status="ABSENT", method="technographic_scan",
                    providers=["explorium"],
                    basis="scan of acme.example plus 4 searches for nCino "
                          "deployment returned 0 hits")
    return run, wb, cells


# ── the register's vocabulary is enforced at the write ────────────────────

def test_layer_and_status_vocabulary(tmp_path):
    run, wb, cells = _run_with_scan(tmp_path)
    with pytest.raises(ScanRefused, match="L2-L5"):
        techscan.record(wb, product="X", vendor="Y", layer="L3",
                        status="CONFIRMED", method="public_document",
                        providers=["web"],
                        basis="a fifteen character basis clause")
    with pytest.raises(ScanRefused, match="status"):
        techscan.record(wb, product="X", vendor="Y", layer="OPS",
                        status="MAYBE", method="public_document",
                        providers=["web"],
                        basis="a fifteen character basis clause")


def test_confirmed_requires_resolvable_evidence(tmp_path):
    """A confirmation nobody can open is a claim wearing a stronger word."""
    run, wb, cells = _run_with_scan(tmp_path)
    with pytest.raises(ScanRefused, match="CONFIRMED requires evidence"):
        techscan.record(wb, product="Q2 Digital Banking", vendor="Q2", layer="CUST",
                        status="CONFIRMED", method="vendor_announcement",
                        providers=["web"],
                        basis="the vendor's own press release names Acme")
    with pytest.raises(ScanRefused, match="do not resolve"):
        techscan.record(wb, product="Q2 Digital Banking", vendor="Q2", layer="CUST",
                        status="CONFIRMED", method="vendor_announcement",
                        providers=["web"],
                        basis="the vendor's own press release names Acme",
                        evidence_ids=["E-999"])


def test_absent_must_state_the_search_that_establishes_it(tmp_path):
    """AUD-0115: 'no register row' and 'confirmed absent' are different
    facts, and conflating them over-recommended by 28 fit points."""
    run, wb, cells = _run_with_scan(tmp_path)
    with pytest.raises(ScanRefused, match="AUD-0115"):
        techscan.record(wb, product="Salesforce Financial Services Cloud", vendor="Salesforce",
                        layer="CUST", status="ABSENT",
                        method="technographic_scan", providers=["explorium"],
                        basis="we did not see it anywhere around")


# ── the render curates from the register ─────────────────────────────────

def test_the_scan_renders_docx_and_json(tmp_path):
    run, wb, cells = _run_with_scan(tmp_path)
    out = techscan.render(wb, run.deliverables)
    assert out["detections"] == 3
    doc = json.loads((run.deliverables / techscan.JSON_NAME).read_text())
    assert doc["artefact"] == "technographic_scan"
    assert doc["counts"]["by_status"]["CONFIRMED"] == 1
    assert "INFRA" in doc["counts"]["layers_never_looked_at"]
    text = "\n".join(p.text for p in Document(out["docx"]).paragraphs)
    assert "NOT SCANNED: INFRA" in text


def test_an_empty_register_refuses_unless_forced_and_then_says_not_run(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)     # an EMPTY register
    wb = run.open()
    with pytest.raises(ScanRefused, match="blank scan that looks like a "
                                          "clean scan"):
        techscan.render(wb, run.deliverables)
    out = techscan.render(wb, run.deliverables, force=True)
    assert out["forced"] is True
    doc = json.loads((run.deliverables / techscan.JSON_NAME).read_text())
    assert doc["not_run"]


# ── assembly: the four outputs, in the defined folder ────────────────────

def _full_package(tmp_path):
    """The whole real path: researched, gated, SCORED, both reports through
    the writer under the stage preconditions, the scan rendered, every tab
    filled or stated."""
    from engine import floors_gate
    from fixtures import client_facts, score_stage, write_both_reports
    run, wb, cells = _run_with_scan(tmp_path, n=8, prelim=True)
    ev = {}
    for cell in cells:
        ev[cell] = bank_evidence(wb, cell)
        synthesise(wb, cell, good_synthesis(cell, ev[cell]))
    wb.append("Entity_Timeline", {
        "Event_Date": "2024-09-01", "Title": "Alkami go-live",
        "Kind": "PLATFORM", "Signal": "POSITIVE",
        "Signal": "EXPANSION", "SubCap_IDs": ", ".join(cells),
        "Evidence_IDs": "E-001"})
    client_facts(wb, cells, ev)
    v = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    score_stage(run, wb, cells, ev)
    write_both_reports(run, wb, cells, ev)
    techscan.render(wb, run.deliverables)
    make_shippable(wb)      # every tab filled or stated — the package gate
    return run, wb


def test_the_package_builds_the_defined_folder_with_all_four(tmp_path):
    run, wb = _full_package(tmp_path)
    out = assemble.package(run, tmp_path / "packages")
    assert out["verified"] is True, out["verification"]
    folder = tmp_path / "packages" / "Acme Credit Union - DMA"
    assert folder.is_dir()
    for _, pattern, _k in assemble.DELIVERABLES:
        assert list(folder.glob(pattern)), pattern
    assert (folder / "run_manifest.json").is_file()
    assert (folder / "01_evidence" / "evidence_index.json").is_file()


def test_the_folder_name_is_the_intake_conventions(tmp_path):
    assert assemble.folder_name("Baxter Credit Union") == \
        "Baxter Credit Union - DMA"
    assert assemble.folder_name("Baxter Credit Union - DMA") == \
        "Baxter Credit Union - DMA"


def test_a_missing_deliverable_refuses_and_names_the_producing_command(tmp_path):
    """A complete run MINUS one report: the refusal must name the renderer,
    not stop at some earlier gate."""
    run, wb = _full_package(tmp_path)
    for stale in run.deliverables.glob("Client_Profile_Research_*.docx"):
        stale.unlink()
    with pytest.raises(SystemExit, match="engine.cli report"):
        assemble.package(run, tmp_path / "packages")


def test_the_evidence_index_speaks_the_apps_own_aliases(tmp_path):
    """AUD-0091's other half: the package carries the URL-bearing index in
    the spellings the app's parse_evidence_index already reads."""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "apps"
                            / "worker"))
    from dma_worker.workbook_parser import parse_evidence_index
    run, wb = _full_package(tmp_path)
    out = assemble.package(run, tmp_path / "packages")
    ei = _P(out["folder"]) / "01_evidence" / "evidence_index.json"
    obs = []
    rows = parse_evidence_index(str(ei), obs)
    assert rows, obs
    assert all(r["source_url"] for r in rows)
    # Every row that CLAIMS a subcap mapping carries it through the alias.
    # Not every row claims one: PRELIM banks the institution profile, whose
    # sources support the client, not a capability cell.
    mapped = [r for r in rows if r["subcaps"]]
    assert mapped, "no evidence row reached a subcap at all"
    assert all(all(s.startswith("P") for s in r["subcaps"]) for r in mapped)


def test_every_final_output_is_classified_by_the_app(tmp_path):
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "apps"
                            / "worker"))
    from dma_worker.classification import classify
    run, wb = _full_package(tmp_path)
    out = assemble.package(run, tmp_path / "packages")
    folder = _P(out["folder"])
    for key, pattern, kind in assemble.DELIVERABLES:
        f = sorted(folder.glob(pattern))[-1]
        c = classify(f.name)
        assert c is not None, f"{f.name} unclassifiable"
        assert c.kind == kind, (f.name, c.kind, kind)


def test_verify_refuses_an_incomplete_folder(tmp_path):
    d = tmp_path / "Broken Client - DMA"
    d.mkdir()
    (d / "run_manifest.json").write_text("{}")
    out = assemble.verify(d)
    assert out["complete"] is False
    missing = [c for c in out["checks"] if not c["ok"]]
    assert any("scoring_workbook" in c["check"] for c in missing)


def test_verify_flags_the_gate_m_shape(tmp_path):
    """Over 15% unURLed evidence in the shipped index is the exact incident
    gate M was built after — the verifier names it before the package ships."""
    run, wb = _full_package(tmp_path)
    out = assemble.package(run, tmp_path / "packages")
    ei = (tmp_path / "packages" / "Acme Credit Union - DMA"
          / "01_evidence" / "evidence_index.json")
    doc = json.loads(ei.read_text())
    for item in doc["items"]:
        item["url"] = None
    ei.write_text(json.dumps(doc))
    v = assemble.verify(tmp_path / "packages" / "Acme Credit Union - DMA")
    assert v["complete"] is False
    assert any("gate-M" in c["detail"] for c in v["checks"] if not c["ok"])


# ── a vendor's own case study is the vendor's claim (owner, 2026-10-06) ──

def _claimed_pipeline_row(wb, cells):
    from engine import ledger as L
    vendor = L.append_evidence(
        wb, source_name="Pipewise case study: Acme Credit Union",
        source_url="https://www.pipewise.example/case-study-acme.pdf", tier="T3",
        excerpt=("Acme Credit Union adopted the Pipewise Loan Pipeline module to "
                 "track and manage every new loan in its commercial pipeline."),
        subcaps=[cells[0]], published="2025-06-01")
    techscan.record(wb, product="Pipewise Loan Pipeline", vendor="Pipewise",
                    layer="OPS", status="CLAIMED", method="vendor_announcement",
                    providers=["web"], evidence_ids=[vendor],
                    basis="named only in the vendor's own case study about the client")
    return vendor


def test_a_vendor_hosted_case_study_does_not_contradict_a_claimed_row(tmp_path):
    """Susser Bank: four more excerpts of BankPoint's own Susser PDF made the
    reconcile check demand CONFIRMED while the validator refused it."""
    from engine import ledger as L
    run, wb, cells = _run_with_scan(tmp_path)
    _claimed_pipeline_row(wb, cells)
    L.append_evidence(
        wb, source_name="Pipewise case study: Acme Credit Union (quote)",
        source_url="https://www.pipewise.example/case-study-acme.pdf", tier="T3",
        excerpt=("Pipewise is what makes large parts of our lending operation at "
                 "Acme Credit Union scalable, the chief lending officer said."),
        subcaps=[cells[0]], published="2025-06-01")
    assert not [c for c in techscan.contradictions(wb) if c["token"] == "Pipewise"]


def test_the_banks_own_page_still_contradicts_a_claimed_row(tmp_path):
    from engine import ledger as L
    run, wb, cells = _run_with_scan(tmp_path)
    _claimed_pipeline_row(wb, cells)
    own = L.append_evidence(
        wb, source_name="Acme Credit Union careers: loan officer",
        source_url="https://www.acmecu.example/careers/loan-officer", tier="T2",
        excerpt=("Acme Credit Union loan officers manage their pipeline daily in "
                 "Pipewise and keep every commercial deal current there."),
        subcaps=[cells[0]], published="2026-01-10")
    hits = [c for c in techscan.contradictions(wb) if c["token"] == "Pipewise"]
    assert hits and own in hits[0]["evidence_ids"], hits
