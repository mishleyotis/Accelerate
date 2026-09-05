"""GS-SCAN-DEPTH — the technographic scan looked at all four layers.

package_findings already refused a MISSING scan (GS-ING-SCAN). What it never
had was a depth floor: a scan that covered OPS and left DATA, CUST and INFRA
blank shipped as a complete estate picture, because nothing at the package
gate read the `layers_never_looked_at` the scan's own engine already computes
and the scan's own docx already prints in red as "a gap in the scan, not a
clean estate."

The floor enforces INVESTIGATION, not detections — a layer with an ABSENT row
was looked-at-and-empty and passes; a layer with no row at all was never
looked at and fails — so it cannot be satisfied by manufacturing detections,
and the reference's own four-layer scan clears it by construction.
"""
import json

from engine import gold_standard as GS, techscan

from fixtures import bank_evidence, new_run


def _three_layer_scan(tmp_path):
    """OPS · CUST · DATA recorded, INFRA never looked at — prelim=False so the
    scan is only what these three records write (close_prelim would cover all
    four)."""
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cells = wb.selected_subcaps()
    eids = bank_evidence(wb, cells[0])
    techscan.record(wb, product="Alkami Digital Banking", vendor="Alkami",
                    layer="CUST", status="CONFIRMED", method="public_document",
                    basis="named live in the 2025 annual report",
                    providers=["clay", "exa"], subcaps=[cells[0]],
                    evidence_ids=eids,
                    source_urls=["https://acme.example/ar25"])
    techscan.record(wb, product="Fiserv DNA", vendor="Fiserv", layer="OPS",
                    status="CONFIRMED", method="public_document",
                    basis="the core named on the member disclosures",
                    providers=["clay", "exa"], subcaps=[cells[0]],
                    evidence_ids=eids,
                    source_urls=["https://acme.example/core"])
    techscan.record(wb, product="Snowflake", vendor="Snowflake", layer="DATA",
                    status="INFERRED", method="job_posting",
                    providers=["indeed"],
                    basis="two 2026 postings name Snowflake administration")
    techscan.render(wb, run.deliverables)
    return run


def _four_layer_scan(tmp_path):
    """prelim=True — close_prelim records a baseline row on every one of the
    four layers (INFRA as an honest ABSENT), so nothing is unlooked."""
    run = new_run(tmp_path, n=3, prelim=True)
    wb = run.open()
    techscan.render(wb, run.deliverables, force=True)
    return run


def codes(findings):
    return [f["code"] for f in findings]


# ── the depth floor ───────────────────────────────────────────────────

def test_a_layer_never_looked_at_is_a_finding(tmp_path):
    run = _three_layer_scan(tmp_path)
    out = GS.scan_findings(run.deliverables)
    assert codes(out) == ["GS-SCAN-DEPTH"]
    assert "INFRA" in out[0]["detail"]
    assert "never looked at" in out[0]["detail"]


def test_all_four_layers_covered_is_clean(tmp_path):
    run = _four_layer_scan(tmp_path)
    assert GS.scan_findings(run.deliverables) == []


def test_an_absent_row_counts_as_looked_at(tmp_path):
    """The distinction the floor rests on: an ABSENT row is a layer looked at
    and found empty, and it must NOT read as an unscanned gap. close_prelim
    records INFRA as ABSENT, so a run that carries it passes."""
    run = _four_layer_scan(tmp_path)
    doc = json.loads((run.deliverables / "technographic_scan.json").read_text())
    infra = [d for d in doc["detections"] if d["layer"] == "INFRA"]
    assert infra and all(d["status"] == "ABSENT" for d in infra), \
        "the fixture must exercise the ABSENT-is-looked-at path"
    assert "INFRA" not in (doc["counts"]["layers_never_looked_at"])
    assert GS.scan_findings(run.deliverables) == []


# ── it reads the machine copy, and falls back to the docx ─────────────

def test_it_reads_the_json_counts(tmp_path):
    run = _three_layer_scan(tmp_path)
    doc = json.loads((run.deliverables / "technographic_scan.json").read_text())
    assert set(doc["counts"]["layers_never_looked_at"]) == {"INFRA"}
    out = GS.scan_findings(run.deliverables)
    assert {"INFRA"} == {l for f in out for l in ("INFRA",)
                         if l in f["detail"]}


def test_the_docx_fallback_reads_the_coverage_table(tmp_path):
    """With no machine copy in the folder, the docx Coverage table's per-layer
    Detections count is the same signal by another route."""
    run = _three_layer_scan(tmp_path)
    (run.deliverables / "technographic_scan.json").unlink()
    unlooked = GS._scan_layers_unlooked_from_docx(run.deliverables)
    assert unlooked == ["INFRA"]
    assert codes(GS.scan_findings(run.deliverables)) == ["GS-SCAN-DEPTH"]


# ── package_findings dispatches it ────────────────────────────────────

def test_package_findings_runs_the_depth_floor(tmp_path):
    """A folder carrying a three-layer scan makes package_findings emit
    GS-SCAN-DEPTH among its findings — the wiring, not just the function."""
    run = _three_layer_scan(tmp_path)
    folder = tmp_path / "pkg"
    folder.mkdir()
    for p in run.deliverables.glob("Technographic_Scan_*.docx"):
        (folder / p.name).write_bytes(p.read_bytes())
    (folder / "technographic_scan.json").write_text(
        (run.deliverables / "technographic_scan.json").read_text())
    out = GS.package_findings(folder)
    assert "GS-SCAN-DEPTH" in codes(out)


def test_a_scan_present_but_no_layers_missing_adds_no_depth_finding(tmp_path):
    run = _four_layer_scan(tmp_path)
    folder = tmp_path / "pkg"
    folder.mkdir()
    for p in run.deliverables.glob("Technographic_Scan_*.docx"):
        (folder / p.name).write_bytes(p.read_bytes())
    (folder / "technographic_scan.json").write_text(
        (run.deliverables / "technographic_scan.json").read_text())
    assert "GS-SCAN-DEPTH" not in codes(GS.package_findings(folder))
