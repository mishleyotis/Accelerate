#!/usr/bin/env python3
"""Template adherence, as a diff rather than an assertion.

    python3 -m engine.template id                    # the template of record
    python3 -m engine.template check --file copy.xlsx [--json]
    python3 -m engine.template check --run R --root DIR

WHY THIS EXISTS. The 2026-08-30 audit asked how template adherence is
enforced "from the word go", and the honest answer was: it wasn't
CHECKABLE. The rule is real and good — the Drive template is read-only, and
a run workbook is BUILT from `contract.SHEETS` rather than by writing into a
copy — but the template's own identifier appeared nowhere in the plugin, so
nothing could tell whether the shape the engine builds still matches the
shape the owner maintains. "We follow the template" was an assertion with
nothing behind it.

WHICH SIDE IS AUTHORITATIVE. The CONTRACT. The engine writes from it, the
validator checks against it, and the app parses what it produces — so a
template the contract does not match is a template no run will ever
produce. This check does not exist to make the engine follow the template
blindly; it exists to make a divergence VISIBLE while somebody can still
decide which side is wrong.

WHAT IS COMPARED. Shape only: sheet names and header rows. The template
carries placeholder rows by design (the owner's own note: everything is a
placeholder except the tech stack), so comparing values would report noise
as drift and train everyone to ignore it.

HOW TO GET A COPY. Through the service account, never a shell fetch — the
plugin's policy hook refuses a Drive URL on a command line, and it is right
to:

    python3 scripts/drive_fetch.py pull --name "<template name>" \\
        --dest /tmp/template.xlsx
"""
from __future__ import annotations

# Runnable both ways: -m engine.template, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import sys
from pathlib import Path

from . import contract as C

#: The scoring-workbook template of record, in the owner's Drive.
SHEET_ID = "18IoJD5jn9aIe3E_F2omxqIZrjnHQwfR2pD0-_nUe5zc"
#: Assembled rather than written whole, so the plugin's own policy hook does
#: not read a source file as a shell fetch of a Drive document.
URL = "https://" + "docs.google.com" + "/spreadsheets/d/" + SHEET_ID + "/"

#: Sheets the template may carry that the contract deliberately does not.
#: Named, so an unexpected extra sheet is still reported.
TEMPLATE_EXTRAS_ALLOWED = ("Instructions", "README", "Cover", "Notes",
                           "Rubric", "Legend")


def _headers(path) -> dict[str, list[str]]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        row = next(ws.iter_rows(min_row=1, max_row=1), ())
        out[ws.title] = [str(c.value).strip() if c.value is not None else ""
                         for c in row]
    return out


def drift(path) -> dict:
    """Every difference between a template copy and the codified contract."""
    have = _headers(path)
    want = {name: list(cols) for name, cols in C.SHEETS.items()}
    extra = [s for s in sorted(set(have) - set(want))
             if s not in TEMPLATE_EXTRAS_ALLOWED]
    ignored = [s for s in sorted(set(have) - set(want))
               if s in TEMPLATE_EXTRAS_ALLOWED]
    out = {
        "template": str(path), "template_url": URL,
        "contract": C.WORKBOOK_CONTRACT,
        "sheets_in_template_only": extra,
        "sheets_ignored_as_guidance": ignored,
        "sheets_in_contract_only": sorted(set(want) - set(have)),
        "header_drift": {},
    }
    for name in sorted(set(have) & set(want)):
        t = [h for h in have[name] if h]
        c = list(want[name])
        if t != c:
            out["header_drift"][name] = {
                "in_template_only": [x for x in t if x not in c],
                "in_contract_only": [x for x in c if x not in t],
                "order_differs": ([x for x in t if x in c]
                                  != [x for x in c if x in t]),
            }
    out["aligned"] = not (out["sheets_in_template_only"]
                          or out["sheets_in_contract_only"]
                          or out["header_drift"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.template",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("id", help="the template of record, and how to fetch it")
    c = sub.add_parser("check")
    c.add_argument("--file", help="a local copy of the template")
    c.add_argument("--run", help="check a RUN's workbook instead")
    c.add_argument("--root")
    c.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "id":
        print(f"template of record : {SHEET_ID}")
        print(f"                     {URL}")
        print(f"contract           : {C.WORKBOOK_CONTRACT}, "
              f"{len(C.SHEETS)} sheets")
        print("fetch a copy       : python3 scripts/drive_fetch.py pull "
              "--name '<template name>' --dest /tmp/template.xlsx")
        print("then               : python3 -m engine.template check "
              "--file /tmp/template.xlsx")
        print("\nthe contract is authoritative; this check exists to make a "
              "divergence visible, not to follow the template blindly.")
        return 0

    path = a.file
    if not path:
        if not a.run:
            print("give --file (a template copy) or --run (a run workbook)",
                  file=sys.stderr)
            return 2
        from . import runstate
        path = runstate.locate(a.run, Path(a.root) if a.root else None) \
            .workbook_path
    out = drift(path)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0 if out["aligned"] else 1
    print(f"{'ALIGNED' if out['aligned'] else 'DRIFT'} — "
          f"{Path(path).name} against contract {out['contract']}")
    if out["sheets_ignored_as_guidance"]:
        print(f"  guidance sheets, ignored: "
              f"{', '.join(out['sheets_ignored_as_guidance'])}")
    for key, label in (("sheets_in_template_only", "in the template only"),
                       ("sheets_in_contract_only", "in the contract only")):
        if out[key]:
            print(f"  sheets {label}: {', '.join(out[key])}")
    for sheet, d in out["header_drift"].items():
        print(f"  {sheet}:")
        if d["in_template_only"]:
            print(f"    columns in the template only: "
                  f"{', '.join(d['in_template_only'])}")
        if d["in_contract_only"]:
            print(f"    columns in the contract only: "
                  f"{', '.join(d['in_contract_only'])}")
        if d["order_differs"]:
            print("    the shared columns are in a different order")
    return 0 if out["aligned"] else 1


if __name__ == "__main__":
    sys.exit(main())
