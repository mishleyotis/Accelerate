"""The governance scripts read the v7 workbook the engine writes.

Measured 28-09-2026 (QA audit F-J01-006): `generate_governance_outputs.py`
looked for v3-era tabs (Evidence_Index, P1_Scoring_Detail, Summary) and on
every v7 workbook produced an EMPTY evidence_index.csv with a warning and a
`run_manifest_v2` built from CLI flags; `gov_auditor.py`'s IV-02 then failed
as CRITICAL on a flat manifest shape nothing writes. Now both resolve tabs
through `engine.contract.resolve_tab`, the exporter writes the engine's
manifest through `engine.assemble`, and an empty evidence export is a
refusal.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

from engine import assemble
from engine import contract as C
from engine import ledger as L
from fixtures import CAT, new_run

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
EXPORTER = PLUGIN / "skills" / "dma-assessment" / "scripts" / "generate_governance_outputs.py"
AUDITOR = PLUGIN / "skills" / "dma-governance" / "scripts" / "gov_auditor.py"
VALIDATOR = PLUGIN / "skills" / "dma-assessment" / "scripts" / "validate_contracts.py"


def _run(*argv):
    return subprocess.run([sys.executable, *map(str, argv)], capture_output=True, text=True)


def _evidenced_run(tmp_path, n_rows=3):
    run = new_run(tmp_path)
    wb = run.open()
    cells = list(C.taxonomy().cells_in(CAT))[:n_rows]
    for i, cell in enumerate(cells):
        L.append_evidence(wb, source_name=f"src{i}", source_url=f"https://x{i}.example",
                          tier="T2", subcaps=[cell], published="2025-01-01",
                          excerpt=f"Excerpt {i} " + "A" * 70)
    return run, wb


def test_the_exporter_reads_v7_tabs_and_writes_the_engines_manifest(tmp_path):
    run, wb = _evidenced_run(tmp_path)
    out = tmp_path / "gov"
    r = _run(EXPORTER, "--workbook", run.workbook_path, "--output-dir", out)
    assert r.returncode == 0, r.stderr[-800:]
    rows = list(csv.DictReader((out / "evidence_index.csv").open()))
    assert len(rows) == len(wb.rows("Evidence_Detail")) >= 3, "no longer empty"
    # PRELIM banks the profile's own T1 rows first; the three appended here
    # follow, and every row carries an id, a tier and a url from v7 columns
    assert all(r["evidence_id"] and r["tier"] and r["url"] for r in rows)
    assert sum(1 for r in rows if r["tier"] == "T2") >= 3
    man = json.loads((out / "run_manifest.json").read_text())
    assert man["schema_version"] == assemble.MANIFEST_SCHEMA_VERSION
    assert man["stage"] == "GOVERNANCE_EXPORT"
    assert man["evidence_metrics"]["total_items"] == len(rows)
    assert assemble.validate_manifest(man) == []
    assert "$schema" not in man and "institution_name" not in man


def test_the_exporter_ignores_typed_facts_and_says_so(tmp_path):
    run, wb = _evidenced_run(tmp_path)
    out = tmp_path / "gov"
    r = _run(EXPORTER, "--workbook", run.workbook_path, "--output-dir", out,
             "--institution-name", "Someone Else", "--rubric-version", "5.0")
    assert r.returncode == 0, r.stderr[-800:]
    assert "ignored --institution-name" in r.stderr
    man = json.loads((out / "run_manifest.json").read_text())
    assert man["institution"]["name"] == "Acme Credit Union"


def test_an_empty_evidence_sheet_is_a_refusal_not_an_export(tmp_path):
    run = new_run(tmp_path, prelim=False)         # PRELIM open: nothing banked yet
    assert not run.open().rows("Evidence_Detail")
    out = tmp_path / "gov"
    r = _run(EXPORTER, "--workbook", run.workbook_path, "--output-dir", out)
    assert r.returncode != 0
    assert "REFUSED" in (r.stderr + r.stdout) and "no rows" in (r.stderr + r.stdout)
    assert not (out / "evidence_index.csv").exists()


def test_the_auditor_and_the_contract_validator_accept_the_engines_manifest(tmp_path):
    run, wb = _evidenced_run(tmp_path)
    out = tmp_path / "gov"
    assert _run(EXPORTER, "--workbook", run.workbook_path, "--output-dir", out).returncode == 0
    v = _run(VALIDATOR, "--dir", out)
    assert v.returncode in (0, 2), v.stdout[-600:] + v.stderr[-600:]   # notes allowed
    assert "Missing field" not in v.stdout + v.stderr
    (out / run.workbook_path.name).write_bytes(run.workbook_path.read_bytes())
    a = _run(AUDITOR, out, "--output-dir", out / "audit")
    results = json.loads((out / "audit" / "check_results.json").read_text())
    rows = results if isinstance(results, list) else results.get("results", [])
    by = {r["check_id"]: r for r in rows}
    assert by["IV-02"]["status"] == "PASS", by["IV-02"]
    assert by["IV-08"]["status"] == "PASS", by["IV-08"]
    assert by["IV-03"]["status"] == "NOT_RUN", "unscored: not run, not failed"
    assert by["IV-04"]["status"] == "PASS", by["IV-04"]
    assert a.returncode in (0, 1)   # the audit verdict is its own business here
