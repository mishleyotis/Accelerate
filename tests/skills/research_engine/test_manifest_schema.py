"""One run manifest, in one shape, from one writer.

Measured 28-09-2026 (QA audit F-N01-019): three incompatible manifests
coexisted — `engine.assemble.manifest_doc`'s nested one, a `run_manifest_v2`
the assessment skill's governance exporter built from CLI flags (versions
defaulting to "5.0"), and a flat shape the governance auditor's IV-02 demanded
that nothing wrote — so every real run failed IV-02 as CRITICAL. Now the
engine owns `schemas/run_manifest.schema.json`, `write_manifest` validates
before it writes, and everything in the document is read from the workbook
or computed from the run.
"""
import json

import pytest

from engine import assemble
from engine import contract as C
from engine import ledger as L
from fixtures import CAT, new_run


def _cell():
    return list(C.taxonomy().cells_in(CAT))[0]


def test_the_manifest_validates_and_carries_only_computed_facts(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    L.append_evidence(wb, source_name="x", source_url="https://x.example",
                      tier="T2", subcaps=[_cell()], published="2025-01-01",
                      excerpt="A" * 80)
    run.qa_dir.mkdir(parents=True, exist_ok=True)
    (run.qa_dir / "approvals.json").write_text(json.dumps({"approvals": [
        {"tool": "enrich-business", "cost_line": "2 credits/row",
         "approved_by": "owner@example.com", "at": "2026-09-28T09:00:00Z"}]}))
    doc = assemble.manifest_doc(wb, status="IN_PROGRESS", stage="OPENED", run=run)
    assert assemble.validate_manifest(doc) == []
    assert doc["schema_version"] == assemble.MANIFEST_SCHEMA_VERSION
    assert doc["run_id"] == run.run_id
    assert doc["institution"]["name"] == "Acme Credit Union"
    assert doc["scores"] is None, "unscored: null, never zeros that look like scores"
    assert doc["evidence_metrics"]["total_items"] == len(wb.rows("Evidence_Detail"))
    assert doc["evidence_metrics"]["tier_distribution"]["T2"] >= 1
    assert doc["approvals"] == [{"tool": "enrich-business", "cost_line": "2 credits/row",
                                 "approved_by": "owner@example.com",
                                 "at": "2026-09-28T09:00:00Z", "expires": None}]
    assert doc["catalogue_hash"] == C.catalogue_hash()
    assert doc["workbook_contract"] == C.WORKBOOK_CONTRACT
    assert doc["packets"] == {}          # no handoff written yet: nothing claimed


@pytest.mark.parametrize("mutate, why", [
    (lambda d: d.pop("scores"), "a required key removed"),
    (lambda d: d.__setitem__("schema_version", "run_manifest_v2"), "the retired version"),
    (lambda d: d.__setitem__("institution_name", "flat"), "a flat key nobody reads"),
    (lambda d: d.__setitem__("status", "DONE"), "a status outside the enum"),
    (lambda d: d.__setitem__("run_id", "{{RUN_ID}}"), "an unresolved template token"),
])
def test_a_manifest_off_its_schema_is_not_written(tmp_path, mutate, why):
    run = new_run(tmp_path)
    doc = assemble.manifest_doc(run.open(), run=run)
    bad = json.loads(json.dumps(doc))
    mutate(bad)
    p = tmp_path / "m.json"
    with pytest.raises(assemble.ManifestInvalid):
        assemble.write_manifest(p, bad)
    assert not p.exists(), why
    assemble.write_manifest(p, doc)
    assert json.loads(p.read_text())["schema_version"] == "run_manifest_v3"


def test_the_builtin_check_holds_without_jsonschema(tmp_path, monkeypatch):
    """CI runners that never installed jsonschema still cannot write a
    manifest with a missing or an unknown key."""
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "jsonschema":
            raise ImportError("no jsonschema here")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    run = new_run(tmp_path)
    doc = assemble.manifest_doc(run.open(), run=run)
    assert assemble.validate_manifest(doc) == []
    bad = dict(doc)
    bad.pop("gates")
    bad["stage_reached"] = "SCORING_PASS"
    probs = assemble.validate_manifest(bad)
    assert any("'gates' is a required" in x for x in probs)
    assert any("unexpected keys" in x for x in probs)


def test_the_client_folder_is_opened_with_the_same_shape(tmp_path):
    run = new_run(tmp_path, folder=False)
    out = assemble.open_folder(run, tmp_path / "client", push=False)
    man = json.loads(next((tmp_path / "client").glob("*/run_manifest.json")).read_text())
    assert out["status"] == "IN_PROGRESS"
    assert assemble.validate_manifest(man) == []
    assert man["stage"] == "OPENED" and man["status"] == "IN_PROGRESS"
    assert man["deliverables_expected"] and man["deliverables_present"] == []
