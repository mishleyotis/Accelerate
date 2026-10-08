"""The research handoff packet says what version it is, what bytes it had
when the engine wrote it, and whether the workbook behind it was complete.

Measured 28-09-2026 (QA audit F-J01-018): the packet carried no version
field, the skill required `assessment_id`, `evidence_mode` and a
`locked_peer_set[]` the engine never emitted, and the pipeline's HANDOFF
check asked only whether the file existed. A consumer could not tell this
engine's packet from an older or hand-edited one.
"""
import json

from engine import assemble, handoff
from fixtures import new_run


def _packet(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    doc = handoff.build(wb, qa_dir=run.qa_dir, strict=False)
    out = run.deliverables / handoff.HANDOFF_NAME
    written = handoff.write_packet(doc, out)
    return run, wb, doc, out, written


def test_the_packet_is_versioned_hashed_and_carries_its_completeness(tmp_path):
    run, wb, doc, out, written = _packet(tmp_path)
    assert doc["_contract"]["schema_version"] == handoff.HANDOFF_SCHEMA_VERSION
    assert doc["completeness"]["verdict"] in ("PASS", "FAIL")
    if doc["completeness"]["verdict"] == "FAIL":
        assert doc["completeness"]["reason"], "a FAIL names its reason"
    assert handoff.verify_packet(out) == []
    sidecar = out.with_name(out.name + handoff.SIDECAR_SUFFIX)
    assert sidecar.read_text().split()[0] == written["sha256"]
    man = assemble.manifest_doc(wb, run=run)
    assert man["packets"]["research_handoff"] == {
        "path": handoff.HANDOFF_NAME, "sha256": written["sha256"],
        "schema_version": handoff.HANDOFF_SCHEMA_VERSION, "verified": True}
    assert assemble.validate_manifest(man) == []


def test_an_edited_older_or_missing_packet_is_named(tmp_path):
    run, wb, doc, out, written = _packet(tmp_path)
    edited = json.loads(out.read_text())
    edited["subcap_records"] = []
    out.write_text(json.dumps(edited))
    probs = handoff.verify_packet(out)
    assert probs and "changed after it was written" in probs[0]
    assert assemble.manifest_doc(wb, run=run)["packets"]["research_handoff"]["verified"] is False

    edited["_contract"]["schema_version"] = "research_handoff_v1"
    out.write_text(json.dumps(edited))
    assert any("this engine reads" in p for p in handoff.verify_packet(out))

    assert handoff.verify_packet(tmp_path / "nope.json") == ["nope.json missing"]
    out.with_name(out.name + handoff.SIDECAR_SUFFIX).unlink()
    assert any("sidecar" in p for p in handoff.verify_packet(out))
