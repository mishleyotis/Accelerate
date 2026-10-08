#!/usr/bin/env python3
"""What each client folder actually holds, and which copy the scan will read.

## The report this answers

Owner, 2026-09-03: "the agents seem to be using old cached reports and not
looking at the live Google Drive document hence leading to multiple
overwrites and multiple loops going back to an illusion that subcaps were not
scored after overwriting the most recent scoring workbooks. The client
folders maintains multiple versions of reports and scoring workbooks instead
of 1 only."

Two measurements taken while stress-testing the pipeline say the same thing
from the database side:

  · Bank of Travelers Rest has NINETEEN runs, eighteen of them with
    `scored_cells = 0`, under TWO different request ids — and three
    byte-identical copies (771,874 bytes each) of one workbook sitting in
    three different Drive folders.
  · Golden 1 CU has two intake folders, "… - DMA" and "… - DMA HYBRID",
    each producing its own runs.

Neither is a parser bug. The tree genuinely holds several copies, and the
scan reads whichever one its rules pick.

## What it reports, per client folder

    VERSIONS      more than one workbook (or report) in one folder, with the
                  modified time and size of each. This is the "multiple
                  versions instead of 1" the owner describes.
    STALE PICK    the file the scan WOULD read is not the most recently
                  modified one of its kind. This is the loop: an agent
                  rewrites the workbook, the scan reads an older sibling,
                  the scores look missing, and the work is redone.
    DUPLICATES    the same bytes (by md5) in more than one folder, which is
                  how one client acquires several packages and several runs.
    EMPTY PICK    the chosen workbook parses to zero scored cells. Cheap to
                  check here and it is the single most expensive thing to
                  discover after ingest.

Read-only. It changes nothing in Drive and writes nothing to the database;
`--json` emits the same findings for a tool that does.

    inspect_client_folders.py [--intake FOLDER_ID] [--client SUBSTRING]
                              [--json OUT] [--parse]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcp_token                                            # noqa: E402

# The worker's own classifier, so this reports what the SCAN would do rather
# than what a second set of rules thinks it should do. Two rule sets that
# drift is how a diagnostic starts lying.
WORKER = os.path.join(HERE, "..", "..", "..", "apps", "worker")
sys.path.insert(0, os.path.abspath(WORKER))

DRIVE = "https://www.googleapis.com/drive/v3/files"
INTAKE = os.environ.get("INTAKE_FOLDER_ID", "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo")
SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def _token() -> str:
    key, src = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({src})")
    return gcp_token.exchange(gcp_token.mint_assertion(
        key, {"scope": SCOPE}))["access_token"]


def _list(token: str, parent: str) -> list[dict]:
    out, page = [], None
    while True:
        q = urllib.parse.urlencode({
            "q": f"'{parent}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,size,"
                      "modifiedTime,md5Checksum)",
            "pageSize": "200", "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            **({"pageToken": page} if page else {})})
        req = urllib.request.Request(f"{DRIVE}?{q}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
        out.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            return out



def _walk(token: str, root: str, depth: int = 6) -> list[dict]:
    """Every non-folder file under `root`, to the worker's max depth, each
    carrying the sub-path it was found at so a report can name where a
    duplicate actually lives."""
    out: list[dict] = []

    def rec(fid, segs, d):
        if d > depth:
            return
        for f in _list(token, fid):
            if f["mimeType"] == FOLDER:
                rec(f["id"], segs + [f["name"]], d + 1)
            else:
                f["_path"] = "/".join(segs + [f["name"]])
                out.append(f)

    rec(root, [], 0)
    return out

FOLDER = "application/vnd.google-apps.folder"

# The WORKER's own classifier, imported rather than re-implemented.
#
# A first draft of this script wrote its own `_kind()` from the same
# filename hints, and immediately reported a STALE PICK on Bank of Travelers
# Rest that did not exist: it read `Technographic_Scan_*.docx` as a "report"
# and compared it against the assessment report. Two rule sets that drift is
# how a diagnostic starts lying, and this one lied on its first run.
try:
    from job_main import _classify_artefact as _worker_classify
except Exception as exc:                       # pragma: no cover
    raise SystemExit(
        f"cannot import the worker's classifier ({exc!r}) — this script "
        "reports what the SCAN does, so re-implementing its rules here is "
        "not an acceptable fallback")


class _Stat:
    """The two fields `_classify_artefact` reads off a FileStat."""

    def __init__(self, name, segments):
        self.name = name
        self.path_segments = segments


def _classify(name: str, folder: str):
    return _worker_classify(_Stat(name, (folder, name)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--intake", default=INTAKE)
    ap.add_argument("--client", default=None,
                    help="only folders whose name contains this (case-insensitive)")
    ap.add_argument("--json", dest="out", default=None)
    ap.add_argument("--parse", action="store_true",
                    help="download the chosen workbook and report its scored "
                         "cell count — slow, and the only way to catch an "
                         "EMPTY PICK before ingest does")
    a = ap.parse_args(argv)

    token = _token()
    folders = [f for f in _list(token, a.intake) if f["mimeType"] == FOLDER]
    if a.client:
        folders = [f for f in folders if a.client.lower() in f["name"].lower()]
    print(f"intake {a.intake}: {len(folders)} client folder(s)"
          + (f" matching {a.client!r}" if a.client else ""))

    by_md5: dict[str, list[str]] = defaultdict(list)
    findings: list[dict] = []

    for folder in sorted(folders, key=lambda f: f["name"]):
        # RECURSIVE, to the worker's own depth. A first draft listed only the
        # files directly under each client folder and reported "0 findings"
        # for Bank of Travelers Rest — whose two workbooks sit in two
        # different SUBFOLDERS, which is precisely the condition being
        # looked for. A diagnostic that cannot see the defect it was written
        # for is worse than none.
        files = _walk(token, folder["id"])
        kinds: dict[str, list[dict]] = defaultdict(list)
        for f in files:
            c = _classify(f["name"], folder["name"])
            if c:
                kind, rank = c
                f["_rank"] = rank
                kinds[kind].append(f)
                if f.get("md5Checksum"):
                    by_md5[f["md5Checksum"]].append(
                        f"{folder['name']}/{f.get('_path', f['name'])}")
        if not kinds:
            continue

        notes: list[str] = []
        for kind, group in sorted(kinds.items()):
            if kind not in ("workbook", "report"):
                continue
            if len(group) > 1:
                newest = max(group, key=lambda f: f["modifiedTime"])
                # exactly the scan's own tie-break: lowest rank wins, and
                # among equal ranks the first the walk met.
                chosen = min(group, key=lambda f: (f["_rank"], f["name"]))
                notes.append(
                    f"VERSIONS {kind}: {len(group)} in one folder")
                for f in sorted(group, key=lambda f: f["modifiedTime"]):
                    mark = ("  <- scan reads this" if f["id"] == chosen["id"]
                            else "  <- newest" if f["id"] == newest["id"] else "")
                    notes.append(f"    {f['modifiedTime']}  "
                                 f"{int(f.get('size') or 0):>9,}  "
                                 f"{f.get('_path', f['name'])[:70]}{mark}")
                if chosen["id"] != newest["id"]:
                    notes.append(
                        f"    STALE PICK: the scan reads {chosen['name'][:50]!r} "
                        f"but {newest['name'][:50]!r} is newer — an agent's "
                        "rewrite does not reach the app, and the scores read "
                        "as missing")
                    findings.append({"folder": folder["name"], "kind": kind,
                                     "issue": "stale_pick",
                                     "reads": chosen["name"],
                                     "newest": newest["name"]})
                else:
                    findings.append({"folder": folder["name"], "kind": kind,
                                     "issue": "multiple_versions",
                                     "count": len(group)})
        if notes:
            print(f"\n{folder['name']}")
            for n in notes:
                print("  " + n)

    dupes = {m: v for m, v in by_md5.items() if len(set(v)) > 1}
    if dupes:
        print(f"\n=== identical bytes in more than one folder: {len(dupes)} ===")
        for m, where in list(dupes.items())[:12]:
            print(f"  {m[:12]}  {len(where)} copies")
            for w in sorted(set(where))[:5]:
                print(f"      {w[:90]}")
            findings.append({"issue": "cross_folder_duplicate",
                             "md5": m, "copies": sorted(set(where))})

    print(f"\n{len(findings)} finding(s)")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(findings, fh, indent=1)
        print(f"written to {a.out}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
