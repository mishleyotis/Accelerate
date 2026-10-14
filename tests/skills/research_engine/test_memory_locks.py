"""The research notebooks are locked, capped and consolidated under the lock.

Measured 28-09-2026 (QA audit F-G05-017): `memory._append` and
`memory.consolidate` ran unlocked — consolidate read the file at one line
and rewrote it at another, and a note landing between the two was gone —
and no memory file stated a cap. These tests pin: concurrent notes all
survive; a note waits for a consolidation's lock; the cap refuses at the
line it states and `status` says consolidate at 80%; the workbook's own
transaction still takes the same lock.
"""
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from engine import memory as M
from engine import workbook as W
from fixtures import new_run

ENGINE = Path(W.__file__).resolve().parents[1]


def _note(run, i, category="P1C1"):
    return M.note(run, category=category, subcap="P1C1.1.1", kind="note",
                  actor="research-p1c1-producer", text=f"writer {i} says something worth keeping")


def test_concurrent_notes_all_survive(tmp_path):
    run = new_run(tmp_path, prelim=False)
    procs = [subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ENGINE)!r})
            from engine import memory, runstate
            run = runstate.locate({run.run_id!r}, {str(run.root)!r})
            memory.note(run, category="P1C1", subcap="P1C1.1.1", kind="note",
                        actor="research-p1c1-producer",
                        text="writer {i} says something worth keeping")
        """)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for i in range(8)]
    for p in procs:
        p.wait(timeout=180)
    fails = [p.stderr.read() for p in procs if p.returncode != 0]
    assert not fails, fails[:1]
    entries = M.parse(M.memory_path(run, "P1C1"))
    texts = {e["fields"].get("text") for e in entries}
    missing = [i for i in range(8) if f"writer {i} says something worth keeping" not in texts]
    assert not missing, f"{len(missing)} of 8 concurrent notes were lost: {missing}"
    head = M.memory_path(run, "P1C1").read_text().splitlines()[0]
    assert head.startswith("# P1C1"), "the header was written exactly once, first"


def test_a_note_waits_for_the_lock_a_consolidation_holds(tmp_path):
    run = new_run(tmp_path, prelim=False)
    _note(run, 0)
    lock = M.memory_path(run, "P1C1").with_name("P1C1.md.lock")
    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(ENGINE)!r})
            from engine.workbook import file_lock
            with file_lock({str(lock)!r}, why="test holder"):
                print("held", flush=True)
                time.sleep(1.5)
        """)], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    t = time.perf_counter()
    _note(run, 1)
    waited = time.perf_counter() - t
    holder.wait(timeout=30)
    assert waited >= 1.0, f"the note did not wait for the lock ({waited:.2f}s)"
    assert len(M.parse(M.memory_path(run, "P1C1"))) == 2


def test_the_cap_refuses_and_status_says_consolidate_at_eighty_percent(tmp_path):
    run = new_run(tmp_path, prelim=False)
    _note(run, 0)
    p = M.memory_path(run, "P1C1")
    filler = ("# filler line that is not an entry and only takes room\n" * 720)
    p.write_text(p.read_text() + filler)
    size = M.notebook_size(p)
    assert size["consolidate_due"] and not size["over_cap"], size
    st = M.status(run, "P1C1")["categories"]["P1C1"]
    assert st["consolidate_due"] is True and st["cap"] == M.NOTEBOOK_CAP_BYTES
    p.write_text(p.read_text() + filler)
    assert M.notebook_size(p)["over_cap"]
    with pytest.raises(ValueError, match="cap"):
        _note(run, 1)
    assert "consolidate" in str(pytest.raises(ValueError, _note, run, 2).value)


def test_the_workbook_transaction_takes_the_same_lock(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    src = (ENGINE / "engine" / "workbook.py").read_text()
    assert "with file_lock(self._lock_path()" in src
    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(ENGINE)!r})
            from engine.workbook import file_lock
            with file_lock({str(wb._lock_path())!r}, why="test holder"):
                print("held", flush=True)
                time.sleep(1.2)
        """)], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    t = time.perf_counter()
    with wb.transaction("test"):
        pass
    holder.wait(timeout=30)
    assert time.perf_counter() - t >= 0.8
