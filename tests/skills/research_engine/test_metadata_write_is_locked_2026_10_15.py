"""Run_Metadata writes hold the workbook lock like every other write.

Verus, 2026-10-15: `engine.narrative thaw` (ledger.thaw → set_metadata)
cleared the freeze key with no lock held while a report writer, mid-
transaction on a copy loaded earlier, saved over it. The register read
frozen again under the old reason and the next registration was refused.
"""
from __future__ import annotations

import threading
import time

from fixtures import new_run  # noqa: E501

from engine import ledger as L
from engine.workbook import RunWorkbook


def test_a_metadata_write_waits_for_a_writer_holding_the_lock(tmp_path):
    run = new_run(tmp_path, n=2)
    a = run.open()
    L.freeze(a, "REPORTS in progress (test)")
    assert L.is_frozen(a)

    b = RunWorkbook(a.path)          # a second writer, loaded while frozen
    b.rows("Run_Metadata")
    entered = threading.Event()
    released = threading.Event()

    def writer():
        with b.transaction("slow report write"):
            entered.set()
            released.wait(5)
            b.append("Gate_Log", {"Timestamp": "2026-10-15T00:00:00Z", "Gate": "T",
                                  "Scope": "run", "Verdict": "PASS", "Blocking": "no",
                                  "Detail": "a row written while the lock was held"})

    t = threading.Thread(target=writer); t.start()
    assert entered.wait(5)
    t0 = time.monotonic()
    done = threading.Event()

    def thaw():
        L.thaw(a, "test thaw while another writer holds the lock")
        done.set()

    u = threading.Thread(target=thaw); u.start()
    time.sleep(0.5)
    assert not done.is_set(), "the thaw wrote without waiting for the lock"
    released.set(); t.join(10); u.join(10)
    assert done.is_set() and time.monotonic() - t0 >= 0.4

    fresh = RunWorkbook(a.path)
    assert not L.is_frozen(fresh), "the thaw was lost to the other writer's save"
    assert any(r.get("Detail") == "a row written while the lock was held"
               for r in fresh.rows("Gate_Log"))
