"""A second run for the same client does not get a second folder, and does
not quietly eat the first one.

WHY THIS EXISTS. Measured 2026-08-30: `folder_name()` is a pure function of
the entity name and `default_folder_root()` is the shared run root, so two
runs of the same client resolved to ONE directory and nothing noticed.
`open_folder` reported `created: false` and overwrote `run_manifest.json`
with the second run's identity; `package` copied the second run's
deliverables in beside the first's and overwrote all three fixed-name machine
extras. The deliverables carry the reference date, so a second run on a
different date left TWO scoring workbooks in one folder — and the app's
package scan keeps exactly one artefact per kind, chosen by rank and then by
iteration order. The client folder became a mix of two runs with an arbitrary
winner.

THE SHAPE IS THE ONE THIS SYSTEM ALREADY USES. Server-side an entity has N
runs, exactly one active (`runs_active_uq`), and promotion demotes its
predecessor to SUPERSEDED and RETAINS it — which is the charter's own default
for superseded runs. This mirrors that on the folder rather than inventing a
second scheme: the current package at the root where every reader already
looks, each previous one whole inside `_superseded/<run_id>/`.

And the folder KEEPS ITS NAME. `runs.source_folder_id` keys on the folder, so
renaming or forking it orphans every run that came before.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from engine import assemble, runstate

from .fixtures import small_selection

sys.path.insert(0, "/home/user/Accelerate/apps/worker")


def _run(tmp_path, run_id, date):
    return runstate.start(
        run_id=run_id, entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE", reference_date=date,
        root=tmp_path / run_id, selected=small_selection(4))


def test_a_second_run_shares_the_folder_and_supersedes_the_first(tmp_path):
    root = tmp_path / "client"
    first = assemble.open_folder(_run(tmp_path, "R-ONE", "2026-01-15"),
                                 root, push=False)
    assert first["created"] is True
    assert first["superseded"]["archived"] is None

    second = assemble.open_folder(_run(tmp_path, "R-TWO", "2026-08-30"),
                                  root, push=False)
    assert second["created"] is False, "the folder is reused, never forked"
    assert Path(second["folder"]) == Path(first["folder"])
    assert len(list(root.iterdir())) == 1, "exactly one client folder"

    folder = Path(second["folder"])
    # the CURRENT package is at the root, which is where every reader looks
    assert json.loads(
        (folder / "run_manifest.json").read_text())["run_id"] == "R-TWO"

    # and the first is retained, whole, with its own manifest intact
    home = Path(second["superseded"]["archived"])
    assert home.parent.name == assemble.ARCHIVE_DIR
    assert home.is_dir() and "R-ONE" in home.name
    assert json.loads(
        (home / "run_manifest.json").read_text())["run_id"] == "R-ONE"

    note = json.loads((home / "SUPERSEDED.json").read_text())
    assert note["run_id"] == "R-ONE" and note["superseded_by"] == "R-TWO"
    assert "RETAINED" in note["note"]


def test_reopening_the_same_run_is_idempotent_and_archives_nothing(tmp_path):
    """`open_folder` is called at run START and may be called again on a
    resume. A resume is not a supersede."""
    root = tmp_path / "client"
    run = _run(tmp_path, "R-ONE", "2026-01-15")
    assemble.open_folder(run, root, push=False)
    again = assemble.open_folder(run, root, push=False)
    assert again["superseded"]["archived"] is None
    assert again["superseded"]["reason"] == "same run"
    assert not (Path(again["folder"]) / assemble.ARCHIVE_DIR).exists()


def test_a_third_run_keeps_both_predecessors(tmp_path):
    root = tmp_path / "client"
    for rid, date in (("R-ONE", "2026-01-15"), ("R-TWO", "2026-05-01"),
                      ("R-THREE", "2026-08-30")):
        out = assemble.open_folder(_run(tmp_path, rid, date), root,
                                   push=False)
    folder = Path(out["folder"])
    kept = sorted(p.name for p in (folder / assemble.ARCHIVE_DIR).iterdir())
    assert len(kept) == 2, kept
    assert any("R-ONE" in k for k in kept) and any("R-TWO" in k for k in kept)
    assert json.loads(
        (folder / "run_manifest.json").read_text())["run_id"] == "R-THREE"


def test_an_archived_package_is_invisible_to_the_apps_scan():
    """The retention would otherwise create the ambiguity it exists to
    remove: the scan reads the whole tree at any depth and keeps ONE artefact
    per kind, chosen by rank then iteration order, so a superseded workbook
    would be a candidate to beat the current one."""
    import job_main as J

    class F:
        def __init__(self, name, segs=()):
            self.name = name
            self.path_segments = list(segs)

    live = ("Acme Credit Union - DMA",)
    dead = ("Acme Credit Union - DMA", assemble.ARCHIVE_DIR, "R-ONE")
    assert J._classify_artefact(F("DMA_Scoring_Workbook_x.xlsx", live))
    assert J._classify_artefact(F("DMA_Scoring_Workbook_x.xlsx", dead)) is None
    assert J._classify_artefact(F("run_manifest.json", dead)) is None
    assert J.ARCHIVE_SEGMENT == assemble.ARCHIVE_DIR, (
        "the engine and the scan must name the same folder")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
