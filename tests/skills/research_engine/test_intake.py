"""HYBRID / INTERNAL runs: internal documents are landed, briefed and gated.

Measured 2026-09-30 (SWBC, HYBRID): `01_intake` existed only in SKILL.md
prose — no code landed a document, no lane was told where one was, and no
gate asked whether one was read. These hold the three halves.
"""
from __future__ import annotations

from engine import intake

from fixtures import new_run


def _doc(tmp_path, text="Engagement write-up: HubSpot is being replaced; no MDM."):
    p = tmp_path / "write_up.md"
    p.write_text(text)
    return p


def test_add_lands_the_document_with_a_hashed_manifest(tmp_path):
    root = tmp_path / "run"
    row = intake.add(root, _doc(tmp_path), title="Write-up", source_url="https://x")
    assert (root / intake.INTAKE_DIR / "write_up.md").is_file()
    assert len(row["sha256"]) == 64 and row["bytes"] > 0
    assert [d["file"] for d in intake.docs(root)] == ["write_up.md"]


def test_an_empty_document_is_refused(tmp_path):
    try:
        intake.add(tmp_path / "run", _doc(tmp_path, "   "))
    except ValueError:
        return
    raise AssertionError("an empty document was accepted as evidence")


def test_preflight_refusal_is_only_for_modes_that_need_documents(tmp_path):
    root = tmp_path / "run"
    assert intake.missing_for_mode(root, "PUBLIC") is None
    assert "engine.intake add" in intake.missing_for_mode(root, "HYBRID")
    intake.add(root, _doc(tmp_path))
    assert intake.missing_for_mode(root, "HYBRID") is None


def test_every_lane_brief_lists_the_documents_in_hybrid_only(tmp_path):
    root = tmp_path / "run"
    intake.add(root, _doc(tmp_path), title="Write-up")
    assert intake.for_brief(root, "PUBLIC") is None
    b = intake.for_brief(root, "HYBRID")
    assert b["documents"][0]["title"] == "Write-up"
    assert "--origin internal" in b["instruction"]


def test_handoff_blocks_a_hybrid_run_that_read_nothing_internal(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    assert intake.handoff_blocker(wb, run.root) is None      # a PUBLIC fixture
    wb.set_metadata("evidence_mode", "HYBRID")
    assert "not one Evidence_Detail row has Origin=internal" in \
        intake.handoff_blocker(wb, run.root)
