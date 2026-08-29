#!/usr/bin/env python3
"""Where a run lives, and what of it survives the container.

WHY THIS EXISTS. AUD-0010: `$RUN` was container-local with no persistence and
no scheduled driver, and the documented cross-conversation resume was three
steps of which one command did not exist, one was a person, and one read a
checkpoint no script wrote. `grep -rn 'checkpoints/'` returned 0 writers
against 1 reader.

The fix is not a new sidecar file. It is that the WORKBOOK is the checkpoint:
one artefact, already durable, already the thing the assessment reads, with
`run_id` and `catalogue_hash` resolved in it at creation. Resume opens the
workbook and reads its own state. `$RUN` is a scratch directory for byte
artefacts, and losing it costs nothing that was not already in the sheet.

`persist()` copies the workbook out of the container. It reports what it
actually did — including NOT_RUN with a reason — because AUD-0034 records a
producer fabricating an enrichment it never ran, and a persistence layer that
claims success it did not have is the same defect with worse consequences.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import contract as C
from .workbook import RunWorkbook

RUN_ROOT = Path(os.environ.get("DMA_RUN_ROOT", "/home/claude/dma_output"))

SUBDIRS = ("00_entity_profile", "01_evidence", "02_search", "07_qa",
           "09_deliverables")

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


@dataclass
class Run:
    run_id: str
    root: Path
    workbook_path: Path

    @property
    def qa_dir(self) -> Path:
        return self.root / "07_qa"

    @property
    def deliverables(self) -> Path:
        return self.root / "09_deliverables"

    def open(self) -> RunWorkbook:
        return RunWorkbook(self.workbook_path)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "entity"


def locate(run_id: str, root: Path | None = None) -> Run:
    """The run's directory and workbook, without creating anything."""
    if not _RUN_ID_RE.match(run_id or ""):
        raise ValueError(f"run_id {run_id!r} is not a usable identifier")
    base = Path(root) if root else RUN_ROOT / run_id
    wbs = sorted(base.glob("*.xlsx"))
    wb = wbs[0] if wbs else base / f"DMA_Scoring_Workbook_{run_id}.xlsx"
    return Run(run_id=run_id, root=base, workbook_path=wb)


#: Tokens that mark a "rationale" written to satisfy the flag rather than to
#: record a decision. Case-insensitive; matched on whole words where it
#: matters ("n/a") and substrings where it cannot false-positive.
_BASIS_BANNED = ("tbd", "todo", "placeholder", "lorem", "xxx", "n/a")
_BASIS_MIN = 20


def vet_basis(flag: str, text: str) -> str:
    """A binding rationale is a recorded decision, or it is refused.

    The sub-vertical choice selects 165 variant cells and withdraws their
    superseded bases; the evidence mode decides every DQ's askability. Both
    are the cheapest mistakes in the pipeline to make and the most expensive
    to discover — a run bound RB when the entity's dominant line of business
    is a credit union researches the wrong 851 cells to completion. So the
    CLI requires the reason, and this refuses a reason-shaped token."""
    t = " ".join((text or "").split())
    low = t.lower()
    if len(t) < _BASIS_MIN or any(b in low for b in _BASIS_BANNED):
        raise ValueError(
            f"{flag} = {text!r} is not a binding rationale. Name the evidence "
            f"the choice rests on — the charter/regulator/LOB census for the "
            f"sub-vertical, the engagement terms for the mode (>= {_BASIS_MIN} "
            f"chars, no filler tokens). An entity with several plausible "
            f"sub-verticals is a question for the engagement owner, not a "
            f"guess: stop and ask rather than binding.")
    return t


def start(*, run_id: str, entity_name: str, entity_id: str,
          sub_vertical: str | None, scope_mode: str, reference_date: str,
          root: Path | None = None, overwrite: bool = False,
          selected: list[str] | None = None,
          evidence_mode: str = "PUBLIC",
          sv_basis: str | None = None, mode_basis: str | None = None,
          lob_census: str | None = None) -> Run:
    """Create the run tree and its workbook, metadata already resolved."""
    if sv_basis is not None:
        sv_basis = vet_basis("--sv-basis", sv_basis)
    if mode_basis is not None:
        mode_basis = vet_basis("--mode-basis", mode_basis)
    base = Path(root) if root else RUN_ROOT / run_id
    for d in SUBDIRS:
        (base / d).mkdir(parents=True, exist_ok=True)
    name = (f"DMA_Scoring_Workbook_{_slug(entity_name)}_"
            f"{reference_date[:10]}.xlsx")
    path = base / name
    RunWorkbook.create(path, run_id=run_id, entity_name=entity_name,
                       entity_id=entity_id, sub_vertical=sub_vertical,
                       scope_mode=scope_mode, reference_date=reference_date,
                       overwrite=overwrite, selected=selected,
                       evidence_mode=evidence_mode, sv_basis=sv_basis,
                       mode_basis=mode_basis, lob_census=lob_census)
    run = Run(run_id=run_id, root=base, workbook_path=path)
    (base / "00_entity_profile" / "context.json").write_text(json.dumps({
        "entity": entity_name, "entity_id": entity_id,
        "sub_vertical": sub_vertical, "scope_mode": scope_mode,
        "reference_date": reference_date, "run_id": run_id,
        "sv_basis": sv_basis, "mode_basis": mode_basis,
        "lob_census": lob_census,
    }, indent=2))
    return run


def resume(run_id: str, root: Path | None = None) -> tuple[Run, dict]:
    """Reopen a run and say honestly what was recovered.

    The documented resume needed a human at step 4 ('confirm entity +
    position with user'). Nothing here needs one: the entity is in
    Run_Metadata, the position is the checkpoint, and both are read, not
    asked."""
    run = locate(run_id, root)
    if not run.workbook_path.exists():
        raise FileNotFoundError(
            f"no workbook for {run_id} at {run.workbook_path}. The workbook IS "
            f"the run; without it there is nothing to resume and saying "
            f"otherwise would be the AUD-0010 failure.")
    wb = run.open()
    md = wb.metadata()
    drift = wb.verify_handoff_lock()
    return run, {
        "run_id": md.get("run_id"), "entity": md.get("entity_name"),
        "evidence_mode": md.get("evidence_mode"),
        "kg_built": bool(str(md.get("kg_checksum") or "").strip()),
        "sub_vertical": md.get("sub_vertical"),
        "binding_stated": not str(md.get("sv_basis") or "").startswith(
            "UNSTATED"),
        "scope_mode": md.get("scope_mode"),
        "checkpoint": md.get("checkpoint") or None,
        "subcaps_selected": md.get("subcaps_selected"),
        "catalogue_drift": drift,
        "recovered_from": str(run.workbook_path),
    }


def checkpoint(wb: RunWorkbook, position: str) -> None:
    """Record where the run got to, in the artefact that survives."""
    wb.set_metadata("checkpoint", json.dumps(
        {"at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "position": position}, separators=(",", ":")))


# ── getting the workbook out of an ephemeral container ───────────────────

def persist(run: Run, dest: str | None = None) -> dict:
    """Copy the workbook somewhere that outlives this container.

    `dest` may be a local directory, a `gs://` prefix, or None. None is not a
    silent no-op: it returns NOT_RUN with the reason, so a caller cannot read
    an absent destination as a successful push."""
    dest = dest or os.environ.get("DMA_RUN_PERSIST")
    if not dest:
        return {"outcome": "NOT_RUN",
                "reason": "no destination configured (DMA_RUN_PERSIST unset); "
                          "the workbook exists only in this container"}
    if not run.workbook_path.exists():
        return {"outcome": "FAILED", "reason": "no workbook to persist"}
    if dest.startswith("gs://"):
        target = dest.rstrip("/") + "/" + run.workbook_path.name
        try:
            subprocess.run(["gcloud", "storage", "cp",
                            str(run.workbook_path), target],
                           check=True, capture_output=True, timeout=300)
        except FileNotFoundError:
            return {"outcome": "FAILED",
                    "reason": "gcloud is absent from this container "
                              "(the AUD-0140 condition), so gs:// cannot be used"}
        except subprocess.CalledProcessError as e:
            return {"outcome": "FAILED",
                    "reason": e.stderr.decode(errors="replace")[:400]}
        return {"outcome": "RESOLVED", "target": target}
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    target = d / run.workbook_path.name
    shutil.copy2(run.workbook_path, target)
    return {"outcome": "RESOLVED", "target": str(target)}


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
