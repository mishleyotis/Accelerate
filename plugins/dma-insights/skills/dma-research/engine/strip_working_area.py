#!/usr/bin/env python3
"""The script the pinned workbook mandates and that existed nowhere.

    strip_working_area.py --workbook WB.xlsx [--handoff research_handoff.json]
                          [--out STRIPPED.xlsx] [--force]

WHY THIS EXISTS. AUD-0011: the workbook's own BEFORE HANDOFF block says "Run
scripts/strip_working_area.py, or by hand: on each of the four pillar sheets
select columns L through the last, delete, and save." `grep -rl
strip_working_area` returned one hit in the whole filesystem — the audit
prompt. With the named automation absent and no human to do the four-sheet
manual delete, every headless handoff either shipped unstripped and failed one
stage later against an eleven-column reader, or did not ship.

AUD-0065 is why this refuses by default. The workbook claims stripping costs
"nothing that matters downstream", and that is true of seven fields and false
of three: `Triangulation`, `Why_It_Matters` and `DMA_Impact` are gate-required
and the handoff carried none of them. So the strip PROVES the three survive
somewhere before it deletes them, and refuses if they do not. Deleting
analysis that has no surviving copy is not a formatting step.
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

import argparse
import json
import shutil
import sys
from pathlib import Path

import openpyxl

from . import contract as C

#: The three the strip used to destroy silently. Named here so the reason
#: this script can refuse is legible from the source.
MUST_SURVIVE = ("Triangulation", "Why_It_Matters", "DMA_Impact")


def survives_elsewhere(workbook: Path, handoff: Path | None) -> list[str]:
    """Which of the three the handoff does NOT carry.

    An empty list means the strip is safe. Anything else is the AUD-0065
    condition and the strip refuses."""
    if handoff is None or not Path(handoff).exists():
        return list(MUST_SURVIVE)
    try:
        doc = json.loads(Path(handoff).read_text())
    except (ValueError, OSError):
        return list(MUST_SURVIVE)
    blob = json.dumps(doc).lower()
    return [f for f in MUST_SURVIVE if f.lower() not in blob]


def strip(workbook, *, handoff=None, out=None, force: bool = False) -> dict:
    workbook = Path(workbook)
    missing = survives_elsewhere(workbook, Path(handoff) if handoff else None)
    if missing and not force:
        raise SystemExit(
            "REFUSED: the working area carries analysis with no surviving "
            f"copy — {', '.join(missing)} are not in the handoff. These are "
            "gate-required (floors_gate reads all three) and the handoff is "
            "the only artefact that outlives the strip. Build the handoff "
            "first (engine/handoff.py), or pass --force and own the loss.")
    target = Path(out) if out else workbook
    if target != workbook:
        shutil.copy2(workbook, target)
    wb = openpyxl.load_workbook(target)
    first_working = len(C.CORE_COLUMNS) + 1          # column L
    removed = 0
    for sheet in C.PILLAR_SHEETS:
        ws = wb[sheet]
        n = ws.max_column - len(C.CORE_COLUMNS)
        if n > 0:
            ws.delete_cols(first_working, n)
            removed += n
    wb.save(target)
    wb.close()
    return {"workbook": str(target), "columns_removed_per_sheet":
            removed // len(C.PILLAR_SHEETS) if removed else 0,
            "core_columns_kept": len(C.CORE_COLUMNS),
            "analysis_preserved_in": str(handoff) if handoff else None,
            "forced": bool(missing and force)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--handoff")
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true",
                    help="strip even though the analysis has no surviving copy")
    a = ap.parse_args(argv)
    print(json.dumps(strip(a.workbook, handoff=a.handoff, out=a.out,
                           force=a.force), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
