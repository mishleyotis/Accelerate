#!/usr/bin/env python3
"""Freeze a client's package once its run is promoted, so nothing edits it after.

## The instruction

Owner, 2026-09-03: "The client folders maintains multiple versions of reports
and scoring workbooks instead of 1 only; the versions should be inspected and
be made immutable after editing the last time."

The scan-side fixes (copy directories excluded, equal-ranked candidates broken
on modified time, a workbook with no scores falling through to a sibling that
has them) make the ingest CHOOSE correctly among copies. They do not stop the
copies being made, and they do not stop an agent rewriting a workbook whose
run has already been promoted — which is the loop itself: the surface a client
is looking at stops matching the artefact it was built from, nobody can tell
which is current, and the next pass re-does work that was already done.

Drive can say this properly. `files.update` with

    contentRestrictions: [{readOnly: true, reason: "..."}]

makes a file un-editable until the restriction is lifted, and carries the
reason with it, so the next person to try gets told why rather than finding a
mystery. That is the mechanism this uses.

## What it freezes, and when

ONLY the artefacts of a run that is already PROMOTED, and only the copies the
scan would actually read. A package still being worked on is left alone —
freezing it would break the work rather than protect it — and a copy in
`memory-backup/` is not frozen because it is not the package.

## Safe by default

DRY RUN unless `--apply` is passed. It reports exactly which files it would
freeze and why, and freezing someone's Drive files is not something to
discover after the fact. `--unfreeze` lifts a restriction this tool set, for
a package that genuinely needs another edit — the reason string is how it
tells its own restrictions from someone else's.

    freeze_package.py --client "<name>" [--apply]
    freeze_package.py --client "<name>" --unfreeze --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcp_token                                            # noqa: E402

DRIVE = "https://www.googleapis.com/drive/v3/files"
INTAKE = os.environ.get("INTAKE_FOLDER_ID", "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo")
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER = "application/vnd.google-apps.folder"

#: Written into every restriction this tool sets, and the only way it can
#: tell its own from one a person set by hand. `--unfreeze` lifts nothing
#: that does not carry it.
REASON = "DMA Insights: package promoted; frozen so the served surface and the artefact stay the same document."


def _token() -> str:
    key, src = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({src})")
    return gcp_token.exchange(gcp_token.mint_assertion(
        key, {"scope": SCOPE}))["access_token"]


def _api(token: str, url: str, method="GET", body=None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def _list(token: str, parent: str) -> list[dict]:
    out, page = [], None
    fields = ("nextPageToken,files(id,name,mimeType,size,modifiedTime,"
              "md5Checksum,contentRestrictions)")
    while True:
        q = urllib.parse.urlencode({
            "q": f"'{parent}' in parents and trashed = false",
            "fields": fields, "pageSize": "200",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            **({"pageToken": page} if page else {})})
        d = _api(token, f"{DRIVE}?{q}")
        out.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            return out


def _walk(token: str, root: str, depth: int = 6) -> list[dict]:
    out: list[dict] = []

    def rec(fid, segs, d):
        if d > depth:
            return
        for f in _list(token, fid):
            if f["mimeType"] == FOLDER:
                rec(f["id"], segs + [f["name"]], d + 1)
            else:
                f["_path"] = "/".join(segs + [f["name"]])
                f["_segs"] = tuple(segs + [f["name"]])
                out.append(f)

    rec(root, [], 0)
    return out



def _served_pages(display_id: str) -> int | None:
    """How many pages this client is currently SERVING, or None if the
    connector could not be read.

    This is the gate's whole question. A first draft asked
    `list_pending_runs` and keyed on `source_folder_id` — a field that tool
    does not return — so the lookup silently produced an empty set and the
    gate refused everything. `get_client_state` answers directly: a client
    with served pages has a promoted run, and its package is finished being
    edited.

    None is NOT zero. It means the answer is unknown, and the caller refuses
    rather than guessing, because a wrongly-frozen package is a person
    blocked from their own file.
    """
    import subprocess
    import tempfile

    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"display_id": display_id}, fh)
            path = fh.name
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "mcp_raw.py"),
             "call", "get_client_state", "--args-file", path],
            capture_output=True, text=True, timeout=300)
        d = json.loads(out.stdout)
    except Exception:                          # noqa: BLE001
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    pages = d.get("served_pages")
    return len(pages) if isinstance(pages, list) else None


def _frozen(f: dict) -> dict | None:
    for r in f.get("contentRestrictions") or []:
        if r.get("readOnly"):
            return r
    return None


def _set_readonly(token: str, file_id: str, on: bool) -> None:
    body = {"contentRestrictions": [
        {"readOnly": True, "reason": REASON} if on else {"readOnly": False}]}
    _api(token, f"{DRIVE}/{file_id}?supportsAllDrives=true",
         method="PATCH", body=body)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--intake", default=INTAKE)
    ap.add_argument("--client", required=True,
                    help="substring of the intake FOLDER name")
    ap.add_argument("--display-id", required=True,
                    help="the client's display id, e.g. golden1-cu — the "
                         "connector is asked whether it serves any page, and "
                         "only a client that does is freezable")
    ap.add_argument("--apply", action="store_true",
                    help="actually change Drive; without it, report only")
    ap.add_argument("--unfreeze", action="store_true",
                    help="lift restrictions THIS tool set (matched on its reason)")
    a = ap.parse_args(argv)

    # The worker's own classifier AND grouping, imported. A first draft
    # re-implemented the tie-break here and immediately chose the wrong
    # workbook — the copy at 15:35:02 rather than the newest at 15:36:52 —
    # reproducing, in a tool written to fix that exact defect, the bug it
    # was written to fix. Nothing about which file the scan reads is decided
    # in this file any more.
    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..",
                                                    "apps", "worker")))
    from job_main import _package_groups                    # noqa: E402
    from dma_worker.scan_diff import FileStat               # noqa: E402

    token = _token()
    folders = [f for f in _list(token, a.intake)
               if f["mimeType"] == FOLDER
               and a.client.lower() in f["name"].lower()]
    if not folders:
        print(f"no client folder matches {a.client!r}")
        return 1

    planned: list[tuple[dict, str]] = []
    for folder in folders:
        print(f"\n{folder['name']}")
        files = _walk(token, folder["id"])
        by_id = {f["id"]: f for f in files}
        stats = [FileStat(file_id=f["id"], path_segments=f["_segs"],
                          name=f["name"], checksum=f.get("md5Checksum") or "",
                          size_bytes=int(f.get("size") or 0),
                          mime_type=f.get("mimeType") or "",
                          modified_time=f.get("modifiedTime") or "")
                 for f in files]
        groups = _package_groups(stats)
        # `_package_groups` keys on the package root, which for a client
        # folder walked from its own id is the top segment.
        best = {}
        for g in groups.values():
            for kind, stat in g.items():
                if kind == "folder" or kind.endswith("__alt"):
                    continue
                best[kind] = by_id[stat.file_id]

        if not a.unfreeze:
            n = _served_pages(a.display_id)
            if n is None:
                print("  SKIPPED — could not read this client's state from "
                      "the connector. Refusing to freeze on an assumption: a "
                      "wrongly-frozen package is a person locked out of their "
                      "own file.")
                continue
            if n == 0:
                print(f"  SKIPPED — {a.display_id} serves no page yet, so this "
                      "package is still being produced. The instruction is "
                      "'immutable after editing the LAST time', and this is "
                      "not that time.")
                continue
            print(f"  {a.display_id} serves {n} page(s) — package is finished")

        for kind, f in sorted(best.items()):
            state = _frozen(f)
            if a.unfreeze:
                if state and state.get("reason") == REASON:
                    planned.append((f, "unfreeze"))
                    print(f"  UNFREEZE {kind:12s} {f['_path'][:64]}")
                elif state:
                    print(f"  skip     {kind:12s} restricted by someone else — "
                          f"{state.get('reason', '')[:40]!r}")
                continue
            if state:
                print(f"  already  {kind:12s} {f['_path'][:64]}")
            else:
                planned.append((f, "freeze"))
                print(f"  FREEZE   {kind:12s} {f['modifiedTime']}  {f['_path'][:64]}")

    if not planned:
        print("\nnothing to do")
        return 0
    if not a.apply:
        print(f"\nDRY RUN — {len(planned)} file(s) would change. Re-run with "
              "--apply to write to Drive.")
        return 0

    done = failed = 0
    for f, what in planned:
        try:
            _set_readonly(token, f["id"], what == "freeze")
            done += 1
        except urllib.error.HTTPError as exc:   # noqa: PERF203
            failed += 1
            print(f"  FAILED {what} {f['name'][:50]}: {exc.code} "
                  f"{exc.read().decode()[:160]}")
    print(f"\n{done} changed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
