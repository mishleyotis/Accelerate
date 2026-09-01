"""The .md memory layer: notebook, consolidation through the gates, cleanup.

The notebook is a NOTEBOOK, never a record: nothing downstream reads it, and
every entry reaches the workbook only through the same ledger refusals the
direct path enforces. These tests hold both halves — the cheap write AND the
strict consolidation — plus the cleanup that refuses while it could cost."""
import json

import pytest

from engine import memory as M
from engine.workbook import RunWorkbook

from fixtures import CAT, new_run

EXCERPT = ("Alkami digital banking went live in Q3 2024 and reached 47 "
           "percent member adoption within ninety days of launch.")


def _noted_run(tmp_path):
    # prelim=False: these tests count the evidence register that
    # consolidation fills, and PRELIM banks the institution profile of its
    # own. The subject here is the notebook -> ledger hop, not the run.
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cells = wb.selected_subcaps()
    return run, wb, cells


# ── noting is cheap; the vocabulary is the only gate ─────────────────────

def test_a_note_lands_in_the_category_file(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    p = M.note(run, category=CAT, subcap=cells[0], facet="works",
               kind="evidence", claim="Alkami live since Q3 2024",
               url="https://acme.example/ar25", excerpt=EXCERPT,
               source_name="Annual Report 2025", tier="T2",
               published="2025-03-01")
    assert p == M.memory_path(run, CAT)
    entries = M.parse(p)
    assert len(entries) == 1
    assert entries[0]["status"] == "NOTED"
    assert entries[0]["subcap"] == cells[0]


def test_the_notebook_says_what_it_is(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           text="promising lead")
    head = M.memory_path(run, CAT).read_text().splitlines()[0:6]
    assert any("NOTEBOOK, never a record" in l for l in head)


def test_an_unknown_kind_or_facet_is_refused(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    with pytest.raises(ValueError):
        M.note(run, category=CAT, subcap=cells[0], facet="works",
               kind="hunchy")
    with pytest.raises(ValueError):
        M.note(run, category=CAT, subcap=cells[0], facet="vibes")


def test_a_half_formed_hunch_is_still_notable(tmp_path):
    """The reason the notebook exists: mid-flight material that the strict
    path would refuse must have somewhere durable to live."""
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="contradicts",
           kind="lead", claim="a 2023 complaint may exist",
           url="https://cfpb.example/search")
    assert M.status(run)["unconsolidated"] == 1


# ── consolidation goes through the real gates ────────────────────────────

def test_a_complete_evidence_note_consolidates_into_the_workbook(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="Alkami live", excerpt=EXCERPT,
           url="https://acme.example/ar25", source_name="Annual Report 2025",
           tier="T2", published="2025-03-01")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1 and out["blocked"] == 0
    fresh = run.open()
    assert len(fresh.rows("Evidence_Detail")) == 1
    row = fresh.scoring_row(cells[0])
    assert "E-001" in str(row["Evidence_IDs"])


def test_an_incomplete_note_is_blocked_in_place_with_the_ledgers_reason(tmp_path):
    """The whole honesty property: a note the gates refuse stays VISIBLE in
    the notebook with the refusal text — never silently dropped, never
    laundered into the workbook around the gate."""
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="thin", excerpt="too short",
           url="https://acme.example/x", source_name="blog", tier="T5")
    out = M.consolidate(run, CAT)
    assert out["blocked"] == 1 and out["consolidated"] == 0
    text = M.memory_path(run, CAT).read_text()
    assert "[BLOCKED]" in text
    assert "50-500" in text            # the ledger's own excerpt refusal
    assert len(run.open().rows("Evidence_Detail")) == 0


def test_consolidation_is_idempotent(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="x", excerpt=EXCERPT,
           url="https://acme.example/ar25", source_name="AR", tier="T2",
           published="2025-03-01")
    M.consolidate(run, CAT)
    again = M.consolidate(run, CAT)
    assert again["consolidated"] == 0 and again["blocked"] == 0
    assert len(run.open().rows("Evidence_Detail")) == 1


def test_a_lead_becomes_a_discovery_question_not_evidence(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="value", kind="lead",
           claim="the 2026 investor deck may carry adoption figures",
           url="https://acme.example/ir")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1
    fresh = run.open()
    assert len(fresh.rows("Evidence_Detail")) == 0
    assert "LEAD:" in str(fresh.scoring_row(cells[0])["Discovery_Questions"])


def test_an_absence_note_needs_its_ladder(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="absence",
           claim="no CDO found")
    out = M.consolidate(run, CAT)
    assert out["blocked"] == 1
    assert "ladder" in out["results"][0]["blocked"]


def test_an_absence_with_a_ladder_binds_the_row_obligations(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="absence",
           claim="no CDO found",
           ladder="direct: 'Acme CU' CDO appointment — 0 hits; "
                  "proxy: 'Acme CU' data governance owner — 0 hits")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1
    row = run.open().scoring_row(cells[0])
    assert str(row["Absence_Claimed"]) == "YES"
    assert "proxy:" in str(row["Proxy_Log"])


def test_multiple_entries_consolidate_in_order_and_marks_stay_aligned(tmp_path):
    """_mark inserts a line per entry; the offset accounting must keep the
    later entries' heads pointed at the right lines."""
    run, wb, cells = _noted_run(tmp_path)
    for i, cell in enumerate(cells):
        M.note(run, category=CAT, subcap=cell, facet="works",
               kind="evidence", claim=f"claim {i}", excerpt=EXCERPT,
               url=f"https://acme.example/{i}", source_name="AR", tier="T2",
               published="2025-03-01")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 3
    entries = M.parse(M.memory_path(run, CAT))
    assert [e["status"] for e in entries] == ["CONSOLIDATED"] * 3
    assert [e["subcap"] for e in entries] == list(cells)


# ── cleanup refuses while it could cost ──────────────────────────────────

def test_cleanup_refuses_while_anything_is_unconsolidated(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="x", excerpt=EXCERPT,
           url="https://a.example/x", source_name="AR", tier="T2")
    out = M.cleanup(run, apply=True)
    assert out["outcome"] == "REFUSED"
    assert any("NOTED" in r for r in out["reasons"])


def test_cleanup_refuses_while_anything_is_blocked(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="thin", excerpt="short",
           url="https://a.example/x", source_name="AR", tier="T5")
    M.consolidate(run, CAT)
    out = M.cleanup(run, apply=True)
    assert out["outcome"] == "REFUSED"
    assert any("BLOCKED" in r for r in out["reasons"])


def test_cleanup_without_apply_never_deletes(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="x", excerpt=EXCERPT,
           url="https://a.example/x", source_name="AR", tier="T2",
           published="2025-03-01")
    M.consolidate(run, CAT)
    calls = []
    monkeypatch.setattr(M.subprocess, "run",
                        lambda *a, **k: calls.append(a) or
                        type("R", (), {"returncode": 0, "stdout": "",
                                       "stderr": ""})())
    out = M.cleanup(run, apply=False)
    assert out["outcome"] == "WOULD_DELETE"
    assert calls == [], "dry-run must not touch Drive at all"


def test_cleanup_pushes_the_final_workbook_before_deleting(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="x", excerpt=EXCERPT,
           url="https://a.example/x", source_name="AR", tier="T2",
           published="2025-03-01")
    M.consolidate(run, CAT)
    seq = []

    def fake_run(cmd, **kw):
        seq.append(cmd[2])       # the drive_fetch subcommand
        return type("R", (), {"returncode": 0, "stdout": "ok",
                              "stderr": ""})()
    monkeypatch.setattr(M.subprocess, "run", fake_run)
    out = M.cleanup(run, apply=True)
    assert out["outcome"] == "RESOLVED"
    assert seq == ["push-final", "cleanup-backup"], (
        "the durable copy must land OUTSIDE the folder being deleted, and "
        "before the deletion")


def test_backup_reports_honestly_when_drive_is_absent(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    monkeypatch.setattr(M, "_drive_fetch", lambda: None)
    out = M.backup(run)
    assert out["outcome"] == "NOT_RUN"
    assert "only in this container" in out["reason"]


def test_backup_pushes_every_category_notebook_and_the_workbook(tmp_path, monkeypatch):
    # The per-category guarantee: a category's reasoning trail is durable only
    # once it is off-container, so backup must carry EVERY 03_memory notebook
    # plus the workbook. A backup that silently skipped a category's notebook
    # would leave that category with no backup at all — the gap that prompted
    # this test. (goeasy/BoTR: back up per category, not just at the end.)
    from pathlib import Path
    run, wb, cells = _noted_run(tmp_path)
    # one real notebook via a note, plus a second category's notebook on disk
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="a provenance note for this category")
    mem = run.root / M.MEMORY_DIR
    mem.mkdir(exist_ok=True)
    (mem / "P9C9.md").write_text("# P9C9\n- [NOTED] a second category notebook\n")

    pushed = []
    monkeypatch.setattr(M, "_drive_fetch", lambda: Path("/x/drive_fetch.py"))

    def fake_run(cmd, **kw):
        pushed.append(Path(cmd[cmd.index("--file") + 1]).name)
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
    monkeypatch.setattr(M.subprocess, "run", fake_run)

    out = M.backup(run)
    assert out["outcome"] == "RESOLVED"
    names = set(pushed)
    assert f"{CAT}.md" in names, "the noted category's notebook must be backed up"
    assert "P9C9.md" in names, "every category notebook must be backed up, not just one"
    assert run.workbook_path.name in names, "the durable workbook must be backed up too"
