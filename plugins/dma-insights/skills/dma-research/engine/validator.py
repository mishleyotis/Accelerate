#!/usr/bin/env python3
"""The seven contract rules, and the three of them that never fired.

WHY THIS EXISTS.

  AUD-0064  rule 2 ("the 11 headers differ in name or order, OR A COLUMN IS
      ADDED") never enforced its third clause, because the header slice
      stopped at column 11: a workbook with 22 extra columns returned
      FAILS=0, exit 0. Rule 5 was guarded by `if fv and ...`, so a row with
      Evidence_IDs blank skipped every content check — and on the real golden
      workbook, 44 of 49 rows were blank, so a 10%-coverage workbook was
      certified clean.
  AUD-0014  the row-count rule compared `max_row-1` to a length and never
      the ID SET, so a workbook carrying entirely the wrong subcaps passed.
  AUD-0012 / AUD-0061  the required sheet set was one the pinned template had
      already retired, so the authority artefact could not pass the gate meant
      to admit it. Here the required set IS the contract's set (one object,
      `contract.REQUIRED_SHEETS`), so the two cannot disagree.
  AUD-0013  and none of it ran in production. `validate()` is called by the
      gate, by the handoff builder and by the CLI; a workbook cannot reach the
      handoff without passing it.

Every rule below has a test that FIRES it and a test that does not.
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
import re
import sys
from pathlib import Path

import openpyxl

from . import contract as C

URL_RE = re.compile(r"https?://", re.I)


class Failure(dict):
    def __init__(self, rule: int, name: str, detail: str, **kw):
        super().__init__(rule=rule, name=name, detail=detail, **kw)

    def __str__(self):
        return f"rule {self['rule']} ({self['name']}): {self['detail']}"


def validate(path, *, run_id: str | None = None,
             expect_scores: bool = False) -> list[Failure]:
    """Every rule, against one workbook. An empty list is a pass."""
    path = Path(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    fails: list[Failure] = []
    try:
        fails += _rule1_sheets(wb)
        if any(f["rule"] == 1 for f in fails):
            return fails            # nothing else is meaningful without sheets
        fails += _rule2_headers(wb)
        fails += _rule3_rows(wb)
        fails += _rule4_scores(wb, expect_scores)
        fails += _rule5_evidence_and_urls(wb)
        fails += _rule6_placeholders(wb)
        fails += _rule7_run_id(wb, run_id)
    finally:
        wb.close()
    return fails


# ── rule 1 · the sheet set ───────────────────────────────────────────────

def _rule1_sheets(wb) -> list[Failure]:
    have = set(wb.sheetnames)
    missing = [s for s in C.REQUIRED_SHEETS if s not in have]
    if missing:
        return [Failure(1, "sheets", f"missing: {sorted(missing)}")]
    return []


# ── rule 2 · headers, INCLUDING an added column ──────────────────────────

def _rule2_headers(wb) -> list[Failure]:
    """The whole header row is compared, not a slice of it.

    The old validator read `range(1, 12)`, so appending a 12th column was
    invisible — which is precisely how an unstripped 33-column working area
    passed the only gate that guards the file."""
    out = []
    for sheet, cols in C.SHEETS.items():
        ws = wb[sheet]
        row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        got = tuple(str(c).strip() for c in row if c is not None
                    and str(c).strip())
        if got == tuple(cols):
            continue
        extra = [c for c in got if c not in cols]
        missing = [c for c in cols if c not in got]
        bits = []
        if extra:
            bits.append(f"added column(s) {extra}")
        if missing:
            bits.append(f"absent column(s) {missing}")
        if not bits:
            bits.append(f"order differs: {list(got)}")
        out.append(Failure(2, "headers", f"{sheet}: " + "; ".join(bits),
                           sheet=sheet))
    return out


# ── rule 3 · the ROWS ARE THE ENGAGEMENT SET, by id ──────────────────────

def _rule3_rows(wb) -> list[Failure]:
    """Compared as a SET OF IDS, not as a count.

    AUD-0014 forced this: swapping an in-scope subcap for an out-of-scope one
    while holding the count constant returned FAILS=0. A count is not an
    identity."""
    tax = C.taxonomy()
    out = []
    seen: set[str] = set()
    for sheet in C.PILLAR_SHEETS:
        pillar = sheet[:2]
        ws = wb[sheet]
        ids = []
        for r in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
            v = r[0] if r else None
            if v is None or not str(v).strip():
                continue
            ids.append(str(v).strip())
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            out.append(Failure(3, "rows", f"{sheet}: duplicate ids {dupes}",
                               sheet=sheet))
        unknown = sorted({i for i in ids if i not in tax.tier})
        if unknown:
            out.append(Failure(
                3, "rows",
                f"{sheet}: {len(unknown)} id(s) are not in catalogue "
                f"{tax.version}: {unknown[:8]}", sheet=sheet))
        wrong = sorted({i for i in ids if i in tax.tier
                        and not i.startswith(pillar)})
        if wrong:
            out.append(Failure(
                3, "rows", f"{sheet}: id(s) belonging to another pillar: "
                           f"{wrong[:8]}", sheet=sheet))
        seen |= set(ids)
    if not seen:
        out.append(Failure(3, "rows",
                           "no scoring rows at all — the engagement set is "
                           "the workbook's scope declaration and it is empty"))
    return out


# ── rule 4 · scores at the research stage ────────────────────────────────

def _rule4_scores(wb, expect_scores: bool) -> list[Failure]:
    out = []
    for sheet in C.PILLAR_SHEETS:
        ws = wb[sheet]
        col = C.PILLAR_COLUMNS.index("Score") + 1
        scored = []
        for r in range(2, ws.max_row + 1):
            v = ws.cell(row=r, column=col).value
            if v is not None and str(v).strip() != "":
                scored.append((ws.cell(row=r, column=1).value, v))
        if expect_scores and not scored:
            out.append(Failure(4, "scores",
                               f"{sheet}: assessment stage, no scores present",
                               sheet=sheet))
        if not expect_scores and scored:
            out.append(Failure(
                4, "scores",
                f"{sheet}: {len(scored)} scored row(s) at the research stage, "
                f"first {scored[0]}. Column D is the assessment's to write.",
                sheet=sheet))
    return out


# ── rule 5 · evidence and URLs, with no vacuous branch ───────────────────

def _rule5_evidence_and_urls(wb) -> list[Failure]:
    """Every row is checked. There is no blank that skips the check.

    The contract says Evidence_IDs must be an E-id list or the literal
    NO_EVIDENCE — blank is neither, and the old guard `if fv and ...` turned
    every blank into a silent pass."""
    out = []
    for sheet in C.PILLAR_SHEETS:
        ws = wb[sheet]
        fi = C.PILLAR_COLUMNS.index("Evidence_IDs") + 1
        gi = C.PILLAR_COLUMNS.index("Source_URLs") + 1
        blank, unurled = [], []
        for r in range(2, ws.max_row + 1):
            sub = ws.cell(row=r, column=1).value
            if sub is None or not str(sub).strip():
                continue
            f = str(ws.cell(row=r, column=fi).value or "").strip()
            g = str(ws.cell(row=r, column=gi).value or "").strip()
            if not f:
                blank.append(str(sub))
                continue
            if f == C.NO_EVIDENCE:
                continue
            if not URL_RE.search(g):
                unurled.append(str(sub))
        if blank:
            out.append(Failure(
                5, "evidence", f"{sheet}: {len(blank)} row(s) with a blank "
                f"Evidence_IDs — the contract admits an E-id list or the "
                f"literal {C.NO_EVIDENCE}, and blank is neither: {blank[:8]}",
                sheet=sheet))
        if unurled:
            out.append(Failure(
                5, "evidence", f"{sheet}: {len(unurled)} row(s) cite evidence "
                f"with no URL in Source_URLs: {unurled[:8]}", sheet=sheet))
    return out


# ── rule 6 · banned placeholders ─────────────────────────────────────────

def _rule6_placeholders(wb) -> list[Failure]:
    out = []
    for sheet in C.PILLAR_SHEETS:
        ws = wb[sheet]
        gi = C.PILLAR_COLUMNS.index("Source_URLs") + 1
        hits = []
        for r in range(2, ws.max_row + 1):
            g = str(ws.cell(row=r, column=gi).value or "").strip().lower()
            if not g:
                continue
            for bad in C.BANNED_URL_PLACEHOLDERS:
                if bad in g:
                    hits.append((str(ws.cell(row=r, column=1).value), bad))
                    break
        if hits:
            out.append(Failure(
                6, "placeholders",
                f"{sheet}: {len(hits)} Source_URLs cell(s) hold a placeholder "
                f"instead of a link: {hits[:5]}", sheet=sheet))
    return out


# ── rule 7 · run_id equality, and the catalogue lock ─────────────────────

def _rule7_run_id(wb, run_id: str | None) -> list[Failure]:
    md = {}
    ws = wb["Run_Metadata"]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r and r[0]:
            md[str(r[0])] = r[1]
    out = []
    have = str(md.get("run_id") or "").strip()
    if not have:
        out.append(Failure(7, "run_id", "Run_Metadata carries no run_id"))
    elif "{{" in have:
        out.append(Failure(7, "run_id",
                           f"run_id is an unresolved token: {have!r}"))
    elif run_id and have != run_id:
        out.append(Failure(7, "run_id",
                           f"workbook says {have!r}, caller says {run_id!r}"))
    lock = {}
    for r in wb["Handoff_Lock"].iter_rows(min_row=2, values_only=True):
        if r and r[0]:
            lock[str(r[0])] = r[1]
    if not lock:
        out.append(Failure(7, "handoff_lock",
                           "Handoff_Lock is empty — the catalogue lock the "
                           "assessment compares against does not exist"))
    else:
        if str(lock.get("catalogue_hash") or "") != C.catalogue_hash():
            out.append(Failure(
                7, "handoff_lock",
                f"catalogue has moved since this run was locked: workbook "
                f"{lock.get('catalogue_hash')} vs current {C.catalogue_hash()}"))
        if str(lock.get("run_id") or "") != have:
            out.append(Failure(7, "handoff_lock",
                               "Handoff_Lock.run_id disagrees with "
                               "Run_Metadata.run_id"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--run-id")
    ap.add_argument("--expect-scores", action="store_true",
                    help="assessment stage: column D must be POPULATED")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    fails = validate(a.workbook, run_id=a.run_id, expect_scores=a.expect_scores)
    if a.json:
        print(json.dumps({"fails": len(fails), "failures": fails}, indent=2))
    else:
        for f in fails:
            print(f"FAIL {f}")
        print(f"validate_workbook: FAILS={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
