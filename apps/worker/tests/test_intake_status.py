"""What has NOT been processed, by folder name.

Production, 2026-08-08: 170 client folders under the intake tree, 123 of
them with a run, and no query in the system could name the other 47 —
`runs` has no row for a folder that never ingested, and `import_files`
has no path. The routine's step 1 ("is there anything to synthesise?")
was unanswerable, which is how 129 ingested runs sat undrained for five
months without anyone being able to say which ones were stuck.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.intake_status import (NO_RUN, PARSED_UNSYNTHESISED,
                                      PROMOTED_CURRENT, PROMOTED_SUPERSEDED,
                                      RUN_UNPARSED, SYNTHESISED_UNPROMOTED,
                                      RunRow, as_json, fetch_package_failures,
                                      folder_states, intake_status, render,
                                      summary)

FOLDERS = ["Baxter Credit Union - DMA", "Zions Bancorporation - DMA",
           "Navy Federal Credit Union - DMA", "MidFirst Bank - DMA",
           "ATB - DMA", "Achieve - DMA", "Westland Insurance - DMA"]

ARTEFACTS = {
    "Baxter Credit Union - DMA": {"manifest", "workbook", "report"},
    "Zions Bancorporation - DMA": {"manifest", "workbook", "report"},
    "Navy Federal Credit Union - DMA": set(),
    "MidFirst Bank - DMA": {"workbook"},
    "ATB - DMA": {"workbook"},
    "Achieve - DMA": {"workbook", "report"},
    "Westland Insurance - DMA": {"workbook"},
}

RUNS = [
    RunRow("r-bcu", "Baxter Credit Union - DMA", "e-bcu", 1, "PROMOTED",
           True, "2026-08-05", "v7.0", 706),
    RunRow("r-mid", "MidFirst Bank - DMA", "e-mid", 1, "INGESTED",
           False, None, "v7.0", 0),
    RunRow("r-atb", "ATB - DMA", "e-atb", 1, "INGESTED", False, None, None, 640),
    RunRow("r-ach", "Achieve - DMA", "e-ach", 1, "INGESTED", False, None, "v7.0", 700),
    RunRow("r-wl1", "Westland Insurance - DMA", "e-wl", 1, "INGESTED",
           False, None, "v7.0", 690),
    RunRow("r-wl2", "Westland Insurance - DMA", "e-wl", 2, "INGESTED",
           False, None, "v7.0", 700),
]


def _by_folder(states):
    return {s.folder: s for s in states}


def test_every_intake_folder_is_named_in_exactly_one_state():
    states = folder_states(FOLDERS, ARTEFACTS, RUNS)
    assert len(states) == len(FOLDERS)
    assert {s.folder for s in states} == set(FOLDERS)
    assert summary(states)[NO_RUN] == 2       # Zions + Navy Federal


def test_a_folder_that_never_produced_a_run_is_named_with_its_reason():
    """This is the query that did not exist: `runs` cannot name a folder it
    has no row for, and 47 production folders were invisible for it."""
    s = _by_folder(folder_states(FOLDERS, ARTEFACTS, RUNS))

    nfcu = s["Navy Federal Credit Union - DMA"]
    assert nfcu.state == NO_RUN and nfcu.blocked
    assert "no scoring workbook artefact" in nfcu.reason

    zions = s["Zions Bancorporation - DMA"]
    assert zions.state == NO_RUN
    assert zions.reason == "scoring workbook present, never ingested"


def test_a_quarantined_package_carries_the_exception_that_stopped_it():
    failures = {"Zions Bancorporation - DMA": {
        "attempts": 3, "quarantined": True,
        "error": "ValueError: unrecognised scoring workbook generation: "
                 "tabs=['Scoring_Workbook', 'Calculation_Chain', 'Run_Metadata']"}}
    s = _by_folder(folder_states(FOLDERS, ARTEFACTS, RUNS, failures))["Zions Bancorporation - DMA"]
    assert s.state == NO_RUN
    assert "quarantined after 3 ingest attempt(s)" in s.reason
    assert "unrecognised scoring workbook generation" in s.reason


def test_the_five_pipeline_states_separate():
    s = _by_folder(folder_states(FOLDERS, ARTEFACTS, RUNS))
    assert s["MidFirst Bank - DMA"].state == RUN_UNPARSED
    assert "zero scored cells" in s["MidFirst Bank - DMA"].reason
    assert s["Achieve - DMA"].state == PARSED_UNSYNTHESISED
    assert s["Achieve - DMA"].reason is None, "a queued folder names no blocker"
    assert s["Baxter Credit Union - DMA"].state == PROMOTED_CURRENT
    assert s["Baxter Credit Union - DMA"].reason is None


def test_a_run_with_no_catalogue_version_is_blocked_not_queued():
    """Seven production runs carry no ccg_catalog_version. They read as
    'awaiting synthesis' in every count, and synthesis has nothing to score
    them against."""
    s = _by_folder(folder_states(FOLDERS, ARTEFACTS, RUNS))["ATB - DMA"]
    assert s.state == PARSED_UNSYNTHESISED and s.blocked
    assert "no catalogue version pinned" in s.reason


def test_a_folder_ingested_twice_is_judged_by_its_newest_run():
    s = _by_folder(folder_states(FOLDERS, ARTEFACTS, RUNS))["Westland Insurance - DMA"]
    assert s.run_id == "r-wl2" and s.run_seq == 2
    assert s.state == PARSED_UNSYNTHESISED
    assert s.reason is None, "the newest run is the one that is queued"


def test_the_older_of_two_ingests_is_reported_as_superseded():
    runs = list(RUNS)
    states = folder_states(["Westland Insurance - DMA"],
                           {"Westland Insurance - DMA": {"workbook"}},
                           [r for r in runs if r.run_id == "r-wl1"] +
                           [RunRow("r-wl2", "Westland 2026 - DMA", "e-wl", 2,
                                   "INGESTED", False, None, "v7.0", 700)])
    s = _by_folder(states)["Westland Insurance - DMA"]
    assert s.state == PARSED_UNSYNTHESISED and s.blocked
    assert "superseded by run_seq 2" in s.reason


def test_a_promoted_run_that_no_longer_serves_is_not_counted_as_current():
    runs = [RunRow("r-old", "Old Client - DMA", "e-o", 1, "SUPERSEDED",
                   False, "2026-05-01", "v7.0", 700)]
    s = _by_folder(folder_states(["Old Client - DMA"], {}, runs))["Old Client - DMA"]
    assert s.state == PROMOTED_SUPERSEDED
    assert summary([s])[PROMOTED_CURRENT] == 0


def test_a_claimed_run_reads_as_synthesised_but_unpromoted():
    runs = [RunRow("r-c", "In Flight - DMA", "e-c", 1, "STAGED",
                   False, None, "v7.0", 700)]
    s = _by_folder(folder_states(["In Flight - DMA"], {}, runs))["In Flight - DMA"]
    assert s.state == SYNTHESISED_UNPROMOTED
    assert "never promoted" in s.reason


def test_a_run_whose_folder_left_the_tree_is_still_reported():
    """Dropping it would repeat exactly the hole this query closes."""
    states = folder_states(["Kept - DMA"], {}, [
        RunRow("r-g", "Renamed Away - DMA", "e-g", 1, "INGESTED",
               False, None, "v7.0", 700)])
    s = _by_folder(states)["Renamed Away - DMA"]
    assert "no longer in the intake tree" in s.reason


def test_render_and_json_carry_the_counts_and_every_folder():
    states = folder_states(FOLDERS, ARTEFACTS, RUNS)
    text = render(states)
    for f in FOLDERS:
        assert f[:42] in text
    assert "no_run" in text and "promoted_current" in text
    blob = as_json(states)
    assert '"counts"' in blob and "Zions Bancorporation - DMA" in blob


# ----------------------------------------------------------- against the DB

def test_intake_status_reads_the_ingested_tier(fakedb):
    fakedb.runs = [
        {"id": "r-bcu", "source_folder_id": "Baxter Credit Union - DMA",
         "entity_id": "e-bcu", "run_seq": 1, "status": "PROMOTED",
         "is_active": True, "promoted_at": "2026-08-05",
         "ccg_catalog_version": "v7.0", "scored_cells": 706},
        {"id": "r-atb", "source_folder_id": "ATB - DMA", "entity_id": "e-atb",
         "run_seq": 1, "status": "INGESTED", "is_active": False,
         "promoted_at": None, "ccg_catalog_version": None, "scored_cells": 640},
    ]
    states = intake_status(fakedb, ["Baxter Credit Union - DMA", "ATB - DMA",
                                    "Zions Bancorporation - DMA"],
                           {"Zions Bancorporation - DMA": {"workbook"}})
    s = _by_folder(states)
    assert s["Baxter Credit Union - DMA"].state == PROMOTED_CURRENT
    assert s["ATB - DMA"].blocked
    assert s["Zions Bancorporation - DMA"].state == NO_RUN


def test_intake_status_is_reachable_as_a_job_mode(monkeypatch, fakedb, capsys):
    """INTAKE_STATUS=1 must answer without opening a scan row or ingesting
    anything — it is a question about the tree, not a firing against it."""
    import job_main
    from dma_worker.scan_diff import FileStat

    tree = [FileStat("w", ("Zions Bancorporation - DMA", "Scoring_Workbook.xlsx"),
                     "Scoring_Workbook.xlsx", "w1", 10, "")]
    monkeypatch.setenv("INTAKE_FOLDER_ID", "intake-root")
    monkeypatch.setenv("INTAKE_STATUS", "1")
    for k in ("DUMP_HEADERS", "LINK_PROPOSE_RUN_ID", "RESET_SCAN",
              "BACKFILL_SECTIONS", "BACKFILL_EVIDENCE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(job_main, "_connect", lambda: fakedb)
    monkeypatch.setattr(job_main.drive, "walk_tree", lambda _i: tree)
    monkeypatch.setattr(job_main, "_ingest_one",
                        lambda *a: pytest.fail("status mode must not ingest"))

    assert job_main.main() == 0
    out = capsys.readouterr().out
    assert "Zions Bancorporation - DMA" in out and "no_run" in out
    assert fakedb.import_scans == {}, "a question does not write a scan row"


def test_failures_from_a_superseded_upload_do_not_count(fakedb):
    """A workbook re-uploaded after a parser fix must not inherit the old
    file's quarantine."""
    fakedb.import_files["wb"] = {"artefact_id": "wb", "checksum": "NEW"}
    fakedb.observations = [
        {"artefact_id": "wb", "kind": "package_ingest_failed",
         "detail": {"folder": "X - DMA", "error": "ValueError: old",
                    "checksum": "OLD", "quarantined": True}, "occurred_at": 1},
    ]
    assert fetch_package_failures(fakedb) == {}
