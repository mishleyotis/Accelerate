"""Two writers to one workbook, which is now a supported topology.

THE INCIDENT, 2026-08-31. REV Federal Credit Union's `thought_leadership`
PRELIM row was silently overwritten by a concurrent write from the
technographic scanner. Real work, really lost, nothing raised.

WHY THE OBVIOUS FIX WOULD NOT HAVE WORKED, and this is what these tests
exist to keep true. `RunWorkbook.__init__` loads the ENTIRE workbook into
memory and `save()` writes that whole copy back, so the lost-update window
opens at LOAD, not inside `save()`. A lock around `save()` alone serialises
the writes and still loses data: a process that opened at t=0 and appends at
t=30min writes back a t=0 snapshot plus its row. The critical section has to
span RELOAD -> MUTATE -> SAVE.

`next_evidence_id` had the same shape one level down: read the maximum, add
one. Two processes both see E-006 and both mint E-007, and the second append
overwrites the first in every surface that later resolves that id.

These spawn REAL processes. A threaded test would pass on a GIL artefact and
prove nothing about the topology that actually broke.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import ledger as L, prelim, workbook as W  # noqa: E402
from fixtures import new_run  # noqa: E402


def _child(script: str, wb_path: Path, *args) -> subprocess.CompletedProcess:
    prog = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ENGINE)!r})
        from engine.workbook import RunWorkbook
        from engine import ledger as L
        wb = RunWorkbook({str(wb_path)!r})
        {script}
    """)
    return subprocess.run([sys.executable, "-c", prog, *map(str, args)],
                          capture_output=True, text=True, timeout=180)


def test_concurrent_appends_all_survive(tmp_path):
    """THE LOST UPDATE, reproduced as a race and then not lost."""
    run = new_run(tmp_path, prelim=False)
    wb_path = run.open().path

    procs = [subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ENGINE)!r})
            from engine.workbook import RunWorkbook
            wb = RunWorkbook({str(wb_path)!r})
            wb.append("Search_Log", {{"SubCap_ID": "P1C1.{i}",
                                      "Query": "writer {i}"}})
        """)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for i in range(8)]
    for p in procs:
        p.wait(timeout=180)
    fails = [p.stderr.read() for p in procs if p.returncode != 0]
    assert not fails, fails[:1]

    queries = {str(r.get("Query")) for r in
               W.RunWorkbook(wb_path).rows("Search_Log")}
    missing = [f"writer {i}" for i in range(8) if f"writer {i}" not in queries]
    assert not missing, (
        f"{len(missing)} of 8 concurrent appends were lost: {missing}")


def test_concurrent_evidence_ids_are_never_duplicated(tmp_path):
    """The E-007 collision. Each child registers one fact; every id must be
    distinct, or two facts share an id and one is unresolvable forever."""
    run = new_run(tmp_path, prelim=False)
    wb_path = run.open().path
    n = 6
    procs = [subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ENGINE)!r})
            from engine.workbook import RunWorkbook
            from engine import ledger as L
            wb = RunWorkbook({str(wb_path)!r})
            eid = L.append_evidence(
                wb, source_name="Source {i}",
                source_url="https://example.test/{i}", tier="T2",
                excerpt=("Writer {i} registered this fact and it must keep "
                         "its own identity in the register no matter how "
                         "many other writers were registering at once."),
                subcaps=[], published="2025-06-01")
            print(eid)
        """)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for i in range(n)]
    ids = []
    for p in procs:
        out, err = p.communicate(timeout=240)
        assert p.returncode == 0, err
        ids.append(out.strip().splitlines()[-1])

    assert len(set(ids)) == n, f"duplicate evidence ids minted: {sorted(ids)}"
    rows = W.RunWorkbook(wb_path).rows("Evidence_Detail")
    registered = {str(r["E_ID"]) for r in rows if r.get("E_ID")}
    assert set(ids) <= registered, (
        "an id was returned to a caller but its row is not in the register")
    assert len(registered) >= n


def test_a_narrative_section_is_not_clobbered_by_a_scanner(tmp_path):
    """THE REV INCIDENT ITSELF: a PRELIM narrative write and a Tech_Register
    write landing together. Both must survive."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = L.append_evidence(
        wb, source_name="Call Report 2025",
        source_url="https://ncua.example/cr", tier="T1",
        excerpt=("The institution reports 1.1 million members across 72 "
                 "branches with 1,850 full-time employees as at year end."),
        subcaps=[], published="2025-12-31")
    wb_path = wb.path

    body = ("Maria Alvarez has spoken twice on moving decisioning off the "
            "core, and the 2025 report repeats that framing, so the stated "
            "direction is consistent across both sources.")
    a = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ENGINE)!r})
        from engine.workbook import RunWorkbook
        from engine import prelim
        wb = RunWorkbook({str(wb_path)!r})
        prelim.narrate(wb, "thought_leadership", heading=None,
                       evidence=[{eid!r}], body={body!r})
    """)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    b = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ENGINE)!r})
        from engine.workbook import RunWorkbook
        from engine import techscan
        wb = RunWorkbook({str(wb_path)!r})
        techscan.record(wb, product="Fiserv DNA", vendor="Fiserv", layer="OPS",
                        status="CONFIRMED", method="public_document",
                        basis="named as the core processor in the filing",
                        providers=["web"], subcaps=[], evidence_ids=[{eid!r}],
                        source_urls=["https://ncua.example/cr"],
                        as_of="2025-12-31")
    """)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for p in (a, b):
        out, err = p.communicate(timeout=240)
        assert p.returncode == 0, err

    fresh = W.RunWorkbook(wb_path)
    narr = [r for r in fresh.rows("Report_Narrative")
            if str(r.get("Section_ID")) == "PRELIM-THOUGHT"]
    tech = [r for r in fresh.rows("Tech_Register")
            if str(r.get("Product")) == "Fiserv DNA"]
    assert narr, "the PRELIM narrative was clobbered — the REV incident"
    assert tech, "the technographic row was clobbered"


def test_a_transaction_never_releases_the_lock_holding_unsaved_edits(
        tmp_path):
    """The invariant that makes the stale-writer case unreachable.

    This test first asserted that a writer holding unsaved edits REFUSES
    when the file moves underneath it. It did not raise — and the reason is
    better than the assertion: `transaction()` commits pending edits before
    releasing, so no lock is ever dropped over unsaved state and the stale
    window cannot open through the public API at all. `save=False` now means
    "not on this call"; the transaction boundary is the commit point.

    So what is pinned is the stronger property, plus the guard itself at
    unit level, because the guard still protects anyone manipulating `_wb`
    directly.
    """
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    wb.append("Search_Log", {"SubCap_ID": "P1C1.1", "Query": "batched"},
              save=False)
    assert not getattr(wb, "_dirty", False), (
        "the transaction released while edits were pending")
    assert "batched" in {str(r.get("Query")) for r in
                         W.RunWorkbook(wb.path).rows("Search_Log")}


def test_the_reload_guard_refuses_to_choose_which_writer_loses(tmp_path):
    """Directly: pending edits plus a moved file is unresolvable, and both
    resolutions lose somebody's work. It must raise, naming the cure."""
    run = new_run(tmp_path, prelim=False)
    wb_path = run.open().path
    stale = W.RunWorkbook(wb_path)
    stale._dirty = True                       # as a mid-transaction mutator is
    W.RunWorkbook(wb_path).append(
        "Search_Log", {"SubCap_ID": "P1C1.2", "Query": "theirs"})

    with pytest.raises(W.WorkbookError) as e:
        stale._reload_if_changed()
    msg = str(e.value)
    assert "unsaved edits" in msg
    assert "transaction()" in msg, "the error must name the cure"


def test_the_lock_is_reentrant_so_nested_writes_do_not_deadlock(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with wb.transaction("outer"):
        wb.append("Search_Log", {"SubCap_ID": "P1C1.1", "Query": "inner one"})
        wb.append("Search_Log", {"SubCap_ID": "P1C1.2", "Query": "inner two"})
    got = {str(r.get("Query")) for r in W.RunWorkbook(wb.path).rows("Search_Log")}
    assert {"inner one", "inner two"} <= got


def test_the_docstring_no_longer_claims_one_writer_is_the_only_topology():
    """It said 'two writers to one workbook is not a supported topology and
    never was'. That was scope, read as a guarantee, and it cost a PRELIM
    section when two writers happened anyway."""
    src = (ENGINE / "engine" / "workbook.py").read_text()
    assert "is not a supported topology and never was" not in src
    assert "transaction" in src and "flock" in src
