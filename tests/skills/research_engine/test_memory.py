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

#: The page every evidence note below quotes.
PAGE = ("Acme Credit Union annual report 2025.\n"
        + EXCERPT +
        "\nThe board approved a three-year core conversion programme.")

#: The URLs those notes carry. Since 2026-09-14 consolidation verifies every
#: excerpt against the text `engine.cli fetch` cached for its URL, so a note
#: quoting a page nothing in the run has read is BLOCKED with
#: `excerpt_unverified` — correct, and NOT what these tests are about: the
#: subject here is the notebook -> ledger hop. `_read` puts the page where a
#: lane's `engine.cli fetch` would have left it. The two deliberately-thin
#: notes below keep their own URLs out of this list, and are refused on
#: length before verification is reached anyway.
_PAGES_READ = ("https://acme.example/ar25", "https://acme.example/pr",
               "https://a.example/x", "https://acme.example/0",
               "https://acme.example/1", "https://acme.example/2")


def _read(run, url, text=PAGE):
    from engine import fetch as F
    F.store_text(run, url, text, content_type="test-fixture")


def _noted_run(tmp_path):
    # prelim=False: these tests count the evidence register that
    # consolidation fills, and PRELIM banks the institution profile of its
    # own. The subject here is the notebook -> ledger hop, not the run.
    run = new_run(tmp_path, n=3, prelim=False)
    for url in _PAGES_READ:
        _read(run, url)
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
    wb2 = run.open()
    row = wb2.scoring_row(cells[0])
    # STAGED, NOT DECLARED (2026-09-03): the notebook may carry the ladder
    # into Proxy_Log, and only `engine.cli absence` may set the flag — a
    # consolidation that declared an absence closed a cell nobody searched.
    assert "proxy:" in str(row["Proxy_Log"])
    assert str(row.get("Absence_Claimed") or "").upper() != "YES"
    from engine import ledger as L
    assert L.is_declared_absent(row, wb2) is False


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

    calls, pushed = [], []
    monkeypatch.setattr(M, "_drive_fetch", lambda: Path("/x/drive_fetch.py"))

    def fake_run(cmd, **kw):
        calls.append(cmd)
        pushed.extend(Path(f).name for f in cmd[cmd.index("--many") + 1:])
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
    monkeypatch.setattr(M.subprocess, "run", fake_run)

    out = M.backup(run)
    assert out["outcome"] == "RESOLVED"
    names = set(pushed)
    assert f"{CAT}.md" in names, "the noted category's notebook must be backed up"
    assert "P9C9.md" in names, "every category notebook must be backed up, not just one"
    assert run.workbook_path.name in names, "the durable workbook must be backed up too"
    assert len(calls) == 1, (
        "every file goes in ONE push-backup --many; a process per notebook "
        "is sixteen token exchanges and sixteen folder lookups per round")


# ═══════════════════════════════════════════════════════════════════════════
# backup is called at EVERY round end: cheap, idempotent, and never fatal
# ═══════════════════════════════════════════════════════════════════════════

def _counting_drive(monkeypatch, *, returncode=0, raises=None):
    """Fake the subprocess boundary and COUNT the invocations.

    The improvement being pinned is arithmetic — one process per round
    instead of one per notebook — so it is measured, not asserted about."""
    from pathlib import Path as _P
    calls = []
    monkeypatch.setattr(M, "_drive_fetch", lambda: _P("/x/drive_fetch.py"))

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if raises is not None:
            raise raises
        return type("R", (), {"returncode": returncode,
                              "stdout": "ok" if not returncode else "",
                              "stderr": "drive said no"})()
    monkeypatch.setattr(M.subprocess, "run", fake_run)
    return calls


def _sixteen_notebooks(run):
    mem = run.root / M.MEMORY_DIR
    mem.mkdir(parents=True, exist_ok=True)
    for i in range(16):
        (mem / f"P1C{i}.md").write_text(f"# P1C{i}\n- a lane's notebook\n")


def test_a_round_of_sixteen_lanes_costs_one_push_call(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    _sixteen_notebooks(run)
    calls = _counting_drive(monkeypatch)
    out = M.backup(run)
    assert out["outcome"] == "RESOLVED"
    assert len(calls) == 1, f"one call per round, not one per file: {len(calls)}"
    assert len(out["pushed"]) == 17, out            # sixteen notebooks + workbook
    assert calls[0][2] == "push-backup" and "--many" in calls[0]


def test_a_second_backup_with_nothing_changed_does_no_work(tmp_path, monkeypatch):
    """The driver calls this at every round end for the life of the run.
    Re-uploading sixteen unchanged notebooks every round is work nobody
    asked for, so an unchanged tree is a NOT_RUN that spends no process."""
    run, wb, cells = _noted_run(tmp_path)
    _sixteen_notebooks(run)
    calls = _counting_drive(monkeypatch)
    assert M.backup(run)["outcome"] == "RESOLVED"
    assert len(calls) == 1
    out = M.backup(run)
    assert out["outcome"] == "NOT_RUN", out
    assert out["pushed"] == [] and len(out["unchanged"]) == 17
    assert "nothing changed" in out["reason"]
    assert len(calls) == 1, "the second call must not spend a subprocess at all"


def test_the_next_round_pushes_only_what_changed(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    _sixteen_notebooks(run)
    calls = _counting_drive(monkeypatch)
    M.backup(run)
    (run.root / M.MEMORY_DIR / "P1C3.md").write_text("# P1C3\n- round two\n")
    out = M.backup(run)
    assert out["outcome"] == "RESOLVED"
    assert out["pushed"] == ["P1C3.md"], out
    assert len(calls) == 2
    from pathlib import Path as _P
    assert [_P(f).name for f in calls[1][calls[1].index("--many") + 1:]] \
        == ["P1C3.md"]


def test_a_failed_push_is_a_status_and_is_retried_next_round(tmp_path, monkeypatch):
    """A backup that fails must not fail the round — and must not record a
    push that did not happen, or the next round would skip the file."""
    run, wb, cells = _noted_run(tmp_path)
    _sixteen_notebooks(run)
    calls = _counting_drive(monkeypatch, returncode=2)
    out = M.backup(run)
    assert out["outcome"] == "PARTIAL", out
    assert out["pushed"] == [] and len(out["failed"]) == 17
    assert "drive said no" in out["reason"]
    monkeypatch.setattr(M.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or
                        type("R", (), {"returncode": 0, "stdout": "ok",
                                       "stderr": ""})())
    assert M.backup(run)["outcome"] == "RESOLVED", "nothing was recorded pushed"


def test_a_raising_backup_is_a_status_not_an_exception(tmp_path, monkeypatch):
    """Timeouts, a missing interpreter, a Drive outage mid-call: the round
    already succeeded, and losing it to a safety copy would be absurd."""
    run, wb, cells = _noted_run(tmp_path)
    _sixteen_notebooks(run)
    _counting_drive(monkeypatch,
                    raises=M.subprocess.TimeoutExpired(cmd="push", timeout=600))
    out = M.backup(run)
    assert out["outcome"] == "FAILED", out
    assert "TimeoutExpired" in out["reason"]


def test_cleanup_forgets_what_it_deleted(tmp_path, monkeypatch):
    """cleanup removes the Drive folder those digests describe. A backup
    after it must not read `already pushed` off a copy that is gone."""
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works",
           kind="evidence", claim="x", excerpt=EXCERPT,
           url="https://a.example/x", source_name="AR", tier="T2",
           published="2025-03-01")
    M.consolidate(run, CAT)
    _counting_drive(monkeypatch)
    assert M.backup(run)["outcome"] == "RESOLVED"
    assert M.backup(run)["outcome"] == "NOT_RUN"      # state is live
    assert M.cleanup(run, apply=True)["outcome"] == "RESOLVED"
    assert M.backup(run)["outcome"] == "RESOLVED", "the state must be forgotten"


def test_backup_says_so_when_there_is_nothing_to_back_up(tmp_path, monkeypatch):
    import shutil as _sh
    run, wb, cells = _noted_run(tmp_path)
    _sh.rmtree(run.root / M.MEMORY_DIR, ignore_errors=True)
    run.workbook_path.unlink()
    calls = _counting_drive(monkeypatch)
    out = M.backup(run)
    assert out["outcome"] == "NOT_RUN" and calls == []
    assert "nothing to back up" in out["reason"]


# ── one find, several cells (E3, 2026-09-13) ─────────────────────────────
#
# `append_evidence(subcaps=[...])` and `engine.cli evidence --subcap A
# --subcap B` have always been multi-cell and validated per cell. The
# NOTEBOOK was the one link in the chain that could not say so, so a lane
# working a capability — measured at 5.32 cells each across the 686 T1_CORE
# cells — had to register the same source once per cell or drop the others.
# That is the write half of capability-grain research: one discovery pass
# grounds the group, and `evidence_smear` still caps shared evidence at half
# of any cell's citations, so each cell earns its own bearing source too.


def _cap_siblings(cells):
    """Cells of one capability — what a single source plausibly bears on."""
    from engine.brief import capability_of
    cap = capability_of(cells[0])
    return [c for c in cells if capability_of(c) == cap]


def test_a_note_may_name_several_cells(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    sibs = _cap_siblings(cells)
    assert len(sibs) >= 2, "the fixture must give this test a capability group"
    p = M.note(run, category=CAT, subcap=sibs, facet="works", kind="evidence",
               claim="Alkami live", excerpt=EXCERPT,
               url="https://acme.example/ar25", source_name="Annual Report 2025",
               tier="T2", published="2025-03-01")
    entry = M.parse(p)[0]
    assert entry["subcap"] == ",".join(sibs), (
        "the entry head stores the group comma-joined — the parser's (\\S+) "
        "already accepts it, which is why this needed no format change")


def test_a_scalar_subcap_still_works(tmp_path):
    """Every existing caller passes a string. The sequence form is additive."""
    run, wb, cells = _noted_run(tmp_path)
    p = M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
               text="a lead worth chasing")
    assert M.parse(p)[0]["subcap"] == cells[0]


def test_a_note_naming_no_cell_is_refused(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    with pytest.raises(ValueError):
        M.note(run, category=CAT, subcap=[], facet="works", kind="note",
               text="bears on nothing")
    with pytest.raises(ValueError):
        M.note(run, category=CAT, subcap=["  "], facet="works", kind="note",
               text="bears on nothing")


def test_one_source_grounds_every_cell_it_names(tmp_path):
    """ONE evidence row, and the link is bidirectional on every cell — the
    cell cites the id AND the row names the cell. `run_density` counts only
    bidirectional links (D3), so a one-way registration would read as
    unevidenced however honestly it was made."""
    run, wb, cells = _noted_run(tmp_path)
    sibs = _cap_siblings(cells)
    M.note(run, category=CAT, subcap=sibs, facet="works", kind="evidence",
           claim="Alkami live", excerpt=EXCERPT,
           url="https://acme.example/ar25", source_name="Annual Report 2025",
           tier="T2", published="2025-03-01")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1 and out["blocked"] == 0

    fresh = run.open()
    rows = fresh.rows("Evidence_Detail")
    assert len(rows) == 1, "one find is one registration, not one per cell"
    eid = str(rows[0]["E_ID"])
    named = {s.strip() for s in str(rows[0]["SubCap_IDs"]).split(",") if s.strip()}
    assert named == set(sibs)
    for cell in sibs:
        assert eid in str(fresh.scoring_row(cell)["Evidence_IDs"]), (
            f"{cell} must cite {eid} back")


def test_provenance_is_written_for_every_cell_the_note_names(tmp_path):
    """The scalar sites in `_consolidate_one` recorded provenance for the
    first cell only. A group registration that leaves four cells with no
    provenance row is a trail that stops naming who did the work."""
    run, wb, cells = _noted_run(tmp_path)
    sibs = _cap_siblings(cells)
    M.note(run, category=CAT, subcap=sibs, facet="works", kind="evidence",
           claim="Alkami live", excerpt=EXCERPT,
           url="https://acme.example/ar25", source_name="AR", tier="T2",
           published="2025-03-01")
    M.consolidate(run, CAT)
    fresh = run.open()
    marked = [str(r["SubCap_ID"]) for r in fresh.rows("Provenance")
              if "memory consolidation" in str(r.get("Detail") or "")]
    assert set(marked) == set(sibs)


def test_a_contradiction_opens_its_disposition_on_every_cell(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    sibs = _cap_siblings(cells)
    M.note(run, category=CAT, subcap=sibs, facet="contradicts",
           kind="contradiction", claim="the press release and the filing disagree",
           excerpt=EXCERPT, url="https://acme.example/pr",
           source_name="Press release", tier="T3", published="2025-04-01")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1
    fresh = run.open()
    for cell in sibs:
        assert str(fresh.scoring_row(cell)["Contradiction_Disposition"]
                   ).startswith("OPEN:"), f"{cell} kept no disposition"


def test_a_refused_group_note_is_blocked_whole(tmp_path):
    """The gates do not soften for a group: a note the ledger refuses stays
    BLOCKED in the notebook and registers nothing, for every cell it named."""
    run, wb, cells = _noted_run(tmp_path)
    sibs = _cap_siblings(cells)
    M.note(run, category=CAT, subcap=sibs, facet="works", kind="evidence",
           claim="thin", excerpt="too short",
           url="https://acme.example/x", source_name="blog", tier="T5")
    out = M.consolidate(run, CAT)
    assert out["blocked"] == 1 and out["consolidated"] == 0
    assert len(run.open().rows("Evidence_Detail")) == 0
    fresh = run.open()
    for cell in sibs:
        # a seeded row reads NO_EVIDENCE, not blank — the property is that no
        # id was written to it, which is what E- prefixes would show
        assert "E-" not in str(fresh.scoring_row(cell)["Evidence_IDs"] or "")


def test_the_cli_takes_the_group_as_repeated_subcaps(tmp_path):
    """`engine.cli evidence` already repeated `--subcap`; the notebook CLI
    was the asymmetry. Read the parser rather than driving a run."""
    import inspect
    text = inspect.getsource(M.main)
    assert '"--subcap", action="append"' in text
    assert "--entries-file" in text, "the batch path is on the same verb"


# ═══════════════════════════════════════════════════════════════════════════
# many entries, ONE call (C3-4)
#
# A lane writing forty notes paid forty Bash round-trips — forty turns, forty
# context re-reads, on a layer whose whole reason to exist is that it is
# cheap. `--entries-file` is the same validation, once.
# ═══════════════════════════════════════════════════════════════════════════

def _entries_file(tmp_path, entries, name="entries.json"):
    p = tmp_path / name
    p.write_text(json.dumps(entries))
    return p


def test_many_entries_land_in_one_call_in_file_order(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    entries = [{"subcap": cells[0], "facet": "works", "kind": "note",
                "claim": f"finding {i}"} for i in range(5)]
    out = M.note(run, category=CAT,
                 entries_file=_entries_file(tmp_path, entries))
    assert out["noted"] == 5 and out["failed"] == []
    got = M.parse(M.memory_path(run, CAT))
    assert [e["fields"]["claim"] for e in got] == [f"finding {i}" for i in range(5)]


def test_an_entry_may_name_several_cells_like_the_flag_does(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    out = M.note(run, category=CAT, entries_file=_entries_file(tmp_path, [
        {"subcap": [cells[0], cells[1]], "facet": "works", "kind": "note",
         "claim": "one source, two cells"}]))
    assert out["noted"] == 1
    assert M.parse(M.memory_path(run, CAT))[0]["subcap"] == f"{cells[0]},{cells[1]}"


def test_a_batch_writes_exactly_what_the_flags_would_have(tmp_path):
    """The batch path and the flag path are one vocabulary: forty notes in
    one call must land byte-for-byte as forty calls would, or the cheap
    path is a second, subtly different writer."""
    run, wb, cells = _noted_run(tmp_path)
    entries = [
        {"subcap": cells[0], "facet": "works", "kind": "evidence",
         "claim": "Alkami live", "excerpt": EXCERPT,
         "url": "https://acme.example/ar25", "source_name": "AR 2025",
         "tier": "T2", "published": "2025-03-01"},
        {"subcap": [cells[0], cells[1]], "facet": "value", "kind": "lead",
         "claim": "the IR deck may carry adoption figures"},
        {"subcap": cells[1], "facet": "works", "kind": "note",
         "text": "a provenance note"},
    ]
    M.note(run, category=CAT, entries_file=_entries_file(tmp_path, entries))
    batched = M.parse(M.memory_path(run, CAT))

    one_at_a_time = new_run(tmp_path / "again", n=3, prelim=False)
    for e in entries:
        f = dict(e)
        M.note(one_at_a_time, category=CAT, subcap=f.pop("subcap"),
               facet=f.pop("facet"), kind=f.pop("kind"), **f)
    singly = M.parse(M.memory_path(one_at_a_time, CAT))

    def shape(es):
        return [(e["status"], e["subcap"], e["facet"], e["fields"]) for e in es]
    assert shape(batched) == shape(singly)


def test_a_bad_entry_refuses_the_whole_batch_and_writes_nothing(tmp_path):
    """ALL OR NOTHING. The notebook is append-only: a batch that wrote
    thirty-nine and refused one leaves a file that cannot be resubmitted
    without duplicating the thirty-nine into the workbook. The index and
    the reason are what the researcher needs; a half-written notebook is
    not."""
    run, wb, cells = _noted_run(tmp_path)
    out = M.note(run, category=CAT, entries_file=_entries_file(tmp_path, [
        {"subcap": cells[0], "facet": "works", "kind": "note", "claim": "a"},
        {"subcap": "P9C9.1.1", "facet": "works", "kind": "note", "claim": "b"},
        {"subcap": cells[0], "facet": "nonsense", "kind": "note", "claim": "c"},
        {"subcap": cells[0], "facet": "works", "kind": "note", "claim": "d"},
    ]))
    assert out["noted"] == 0 and out["written"] is False
    assert [f["index"] for f in out["failed"]] == [1, 2]
    assert "P9C9.1.1" in out["failed"][0]["error"]
    assert "nonsense" in out["failed"][1]["error"]
    assert not M.memory_path(run, CAT).exists(), (
        "a refused batch must not even create the notebook")


def test_a_refused_batch_leaves_an_existing_notebook_untouched(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="already here")
    before = M.memory_path(run, CAT).read_text()
    out = M.note(run, category=CAT, entries_file=_entries_file(tmp_path, [
        {"subcap": cells[0], "facet": "works", "kind": "note", "claim": "a"},
        {"subcap": cells[0], "facet": "works", "kind": "hunchy", "claim": "b"},
    ]))
    assert out["noted"] == 0 and [f["index"] for f in out["failed"]] == [1]
    assert M.memory_path(run, CAT).read_text() == before


def test_an_entries_file_that_is_not_a_list_is_refused(tmp_path):
    run, wb, cells = _noted_run(tmp_path)
    with pytest.raises(ValueError):
        M.note(run, category=CAT,
               entries_file=_entries_file(tmp_path, {"subcap": cells[0]}))


def test_the_cli_takes_an_entries_file(tmp_path, capsys):
    run, wb, cells = _noted_run(tmp_path)
    p = _entries_file(tmp_path, [
        {"subcap": cells[0], "facet": "works", "kind": "note", "claim": "cli one"},
        {"subcap": cells[0], "facet": "works", "kind": "note", "claim": "cli two"}])
    rc = M.main(["note", "--run", run.run_id, "--root", str(run.root),
                 "--category", CAT, "--entries-file", str(p)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["noted"] == 2
    assert len(M.parse(M.memory_path(run, CAT))) == 2


def test_the_cli_reads_entries_from_stdin(tmp_path, capsys, monkeypatch):
    import io
    run, wb, cells = _noted_run(tmp_path)
    monkeypatch.setattr(M.sys, "stdin", io.StringIO(json.dumps(
        [{"subcap": cells[0], "facet": "works", "kind": "note", "claim": "piped"}])))
    rc = M.main(["note", "--run", run.run_id, "--root", str(run.root),
                 "--category", CAT, "--entries-file", "-"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["noted"] == 1


def test_the_cli_exits_nonzero_when_an_entry_failed(tmp_path, capsys):
    run, wb, cells = _noted_run(tmp_path)
    p = _entries_file(tmp_path, [{"subcap": "P9C9.1.1", "facet": "works",
                                  "kind": "note", "claim": "stray"}])
    rc = M.main(["note", "--run", run.run_id, "--root", str(run.root),
                 "--category", CAT, "--entries-file", str(p)])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["failed"][0]["index"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# restore: the lifecycle stops being push-only
# ═══════════════════════════════════════════════════════════════════════════

_FAKE_DRIVE = '''\
import argparse, os, shutil, sys
from pathlib import Path
d = Path(os.environ["FAKE_DRIVE_DIR"]); d.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
b = sub.add_parser("push-backup"); b.add_argument("--client"); b.add_argument("--file")
b.add_argument("--many", nargs="+"); b.add_argument("--name")
{pull}
a = ap.parse_args()
if a.cmd == "push-backup":
    for f in (a.many or [a.file]):
        shutil.copy2(f, d / Path(f).name)
    print("backup created")
else:
    dest = Path(a.dest); dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(d.glob("*.md")):
        shutil.copy2(f, dest / f.name); n += 1
    print(f"pulled {{n}}")
'''
_PULL = ('p = sub.add_parser("pull-backup"); p.add_argument("--client"); '
         'p.add_argument("--dest")')


def _fake_drive(tmp_path, monkeypatch, *, with_pull=True):
    script = tmp_path / "fake_drive_fetch.py"
    script.write_text(_FAKE_DRIVE.format(pull=_PULL if with_pull else ""))
    monkeypatch.setenv("FAKE_DRIVE_DIR", str(tmp_path / "drive"))
    monkeypatch.setattr(M, "_drive_fetch", lambda: script)
    return script


def test_a_notebook_survives_a_dead_container(tmp_path, monkeypatch):
    """Push, lose the container, pull back: the round trip the lifecycle
    advertised and only had one half of."""
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="the reasoning trail nobody wants to pay for twice")
    before = M.memory_path(run, CAT).read_text()
    _fake_drive(tmp_path, monkeypatch)
    assert M.backup(run)["outcome"] == "RESOLVED"

    import shutil
    shutil.rmtree(run.root / M.MEMORY_DIR)
    out = M.restore(run)
    assert out["outcome"] == "RESOLVED", out
    assert f"{CAT}.md" in out["restored"]
    assert M.memory_path(run, CAT).read_text() == before


def test_restore_never_overwrites_a_local_notebook(tmp_path, monkeypatch):
    """The local copy is the live one; the backup is older by construction."""
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="backed up")
    _fake_drive(tmp_path, monkeypatch)
    M.backup(run)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="written after the backup")
    out = M.restore(run)
    assert out["kept"] == [f"{CAT}.md"] and out["restored"] == []
    assert "written after the backup" in M.memory_path(run, CAT).read_text()


def test_restore_with_nothing_backed_up_is_a_not_run_with_a_reason(tmp_path,
                                                                   monkeypatch):
    """The install CAN pull; this client simply has no backup yet. That is a
    NOT_RUN naming the reason — never a crash, and never a RESOLVED over an
    empty directory, which is how a researcher concludes the notes were
    never written."""
    import shutil as _sh
    run, wb, cells = _noted_run(tmp_path)
    _fake_drive(tmp_path, monkeypatch)          # pull works, drive is empty
    _sh.rmtree(run.root / M.MEMORY_DIR, ignore_errors=True)
    out = M.restore(run)
    assert out["outcome"] == "NOT_RUN", out
    assert out["restored"] == [] and out["kept"] == []
    assert "no notebook for this client" in out["reason"]
    assert not (run.qa_dir / "restore_staging").exists(), (
        "the staging directory is the restore's own scratch; it must not "
        "be left behind in 07_qa")


def test_restore_reports_honestly_when_drive_is_absent(tmp_path, monkeypatch):
    run, wb, cells = _noted_run(tmp_path)
    monkeypatch.setattr(M, "_drive_fetch", lambda: None)
    out = M.restore(run)
    assert out["outcome"] == "NOT_RUN" and "drive_fetch.py" in out["reason"]


def test_restore_says_so_when_this_install_cannot_pull(tmp_path, monkeypatch):
    """An install whose drive_fetch.py has no `pull-backup` verb cannot
    restore. That is a NOT_RUN naming the missing verb, never a silent
    RESOLVED over an empty directory."""
    run, wb, cells = _noted_run(tmp_path)
    _fake_drive(tmp_path, monkeypatch, with_pull=False)
    out = M.restore(run)
    assert out["outcome"] == "NOT_RUN" and "pull-backup" in out["reason"]


def test_the_cli_restores(tmp_path, monkeypatch, capsys):
    run, wb, cells = _noted_run(tmp_path)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="note",
           claim="x")
    _fake_drive(tmp_path, monkeypatch)
    M.backup(run)
    import shutil
    shutil.rmtree(run.root / M.MEMORY_DIR)
    rc = M.main(["restore", "--run", run.run_id, "--root", str(run.root)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "RESOLVED"


# ═══════════════════════════════════════════════════════════════════════════
# the real drive_fetch.py, not the fake: the verb restore calls must exist
# ═══════════════════════════════════════════════════════════════════════════
#
# Every restore test above fakes the subprocess boundary, which is right for
# testing restore's own logic and blind to the thing that actually broke the
# lifecycle: `pull-backup` did not exist in the shipped script, so restore
# reported NOT_RUN on every real container while its tests were green.
# These two run the REAL parser.

def _drive_fetch_script():
    from pathlib import Path as _P
    here = _P(__file__).resolve()
    for up in here.parents:
        cand = up / "plugins" / "dma-insights" / "scripts" / "drive_fetch.py"
        if cand.is_file():
            return cand
    pytest.skip("drive_fetch.py not in this checkout")


def _drive_fetch_help(*argv):
    import subprocess
    import sys
    return subprocess.run([sys.executable, str(_drive_fetch_script()), *argv,
                           "--help"], capture_output=True, text=True,
                          timeout=120)


def test_the_installed_drive_fetch_has_the_verb_restore_calls():
    r = _drive_fetch_help(M.PULL_VERB)
    assert r.returncode == 0, (
        f"engine.memory restore shells out to `drive_fetch.py {M.PULL_VERB}`; "
        f"without it every real container's restore is a NOT_RUN: {r.stderr}")
    assert "--client" in r.stdout and "--dest" in r.stdout, (
        "restore passes --client and --dest; the verb must take them")


def test_the_installed_push_backup_takes_a_batch():
    r = _drive_fetch_help("push-backup")
    assert r.returncode == 0, r.stderr
    assert "--many" in r.stdout, (
        "backup sends one call per round with every changed file; without "
        "--many that is seventeen processes and seventeen token exchanges")


# ═══════════════════════════════════════════════════════════════════════════
# the docstring is a contract too
# ═══════════════════════════════════════════════════════════════════════════

def _cli_flags():
    import contextlib
    import io
    import re
    flags = set()
    for cmd in ("note", "status", "consolidate", "backup", "cleanup", "restore"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
            M.main([cmd, "--help"])
        flags |= set(re.findall(r"--[a-z][a-z0-9-]*", buf.getvalue()))
    return flags


def test_the_docstring_names_only_flags_that_exist():
    """It advertised `--stdin` from the day it was written and no such flag
    ever existed. A usage block nobody can run is worse than none: it costs
    a turn to discover."""
    import re
    have = _cli_flags()
    doc = set(re.findall(r"--[a-z][a-z0-9-]*", M.__doc__))
    assert doc, "the module docstring still carries a usage block"
    assert doc <= have, f"the docstring names flags that do not exist: {sorted(doc - have)}"


def test_the_docstring_names_every_verb():
    for verb in ("note", "status", "consolidate", "backup", "restore", "cleanup"):
        assert f"engine.memory {verb}" in M.__doc__, verb
    assert "--entries-file" in M.__doc__
