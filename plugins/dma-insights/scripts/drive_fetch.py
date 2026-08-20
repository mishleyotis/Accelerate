#!/usr/bin/env python3
"""Google Drive access for routine sessions — the SA credential, no connector.

Owner instruction, 2026-08-20: "Preflight should include access to the DMA
drive folder where the DMAs are stored … The connector should automatically
load without my intervention or use authentication to access the Google
drive and download the specific client folder."

Why not the claude.ai Drive connector: measured twice today, interactively-
authenticated connectors do not load in trigger-fired sessions
(enabledInChat: false), the organisation has the API's trigger-connectors
parameter disabled, and the connector's own account was refused permission
to share the folder onward. The dependable path is the one the plugin
already uses for everything else: the dmai-routine service-account key the
container holds mints a Drive-scoped access token (gcp_token.py, the same
rungs — key file, then DMA_ROUTINE_SA_KEY_B64), and this module speaks the
Drive REST API directly. Works in every container, no OAuth, no UI.

The ONE precondition, once, forever: the intake folder must be shared with
  dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com
as Editor (Editor rather than Viewer so the per-client memory file can be
written back). `check` names exactly this when it is missing — a 404 from
Drive for a real folder means "not shared with this identity".

Commands:
  check                       preflight: folder reachable, children listable
  pull  --client <name>       download the client's subfolder to
                              /root/.dma/packages/<slug>/
  push-memory --client <slug> upload/update "<slug> — synthesis memory.md"
                              into the client's subfolder
  push-bundle --client <id> --file <local.json> [--name <remote.json>]
                              upload/update a JSON bundle into the client's
                              "DMA Insights" folder — the structured resume
                              state (state.json + surfaces/<section>.json)
                              a resuming workflow reads instead of prose

No value of any token is ever printed. Errors name the layer and the fix.
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gcp_token  # noqa: E402

INTAKE_FOLDER_ID = "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo"   # "General DMAs"
SA_EMAIL = "dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
PACKAGES_DIR = Path("/root/.dma/packages")
MEMORY_DIR = Path("/root/.dma/clients")

# Google-native files cannot download as bytes; they export to a real format.
EXPORTS = {
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         ".xlsx"),
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}
FOLDER_MIME = "application/vnd.google-apps.folder"
MEMORY_SUFFIX = " — synthesis memory.md"


def _token() -> str:
    key, source = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({source}) — "
                         f"bootstrap_session.sh lands it, or set "
                         f"DMA_ROUTINE_SA_KEY_B64")
    tok = gcp_token.exchange(gcp_token.mint_assertion(
        key, {"scope": DRIVE_SCOPE})).get("access_token", "")
    if not tok:
        raise SystemExit("could not exchange a Drive-scoped access token")
    return tok


def _req(tok: str, url: str, data: bytes | None = None,
         method: str = "GET", ctype: str | None = None):
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {tok}")
    if ctype:
        r.add_header("Content-Type", ctype)
    return urllib.request.urlopen(r, timeout=120)


def _list_children(tok: str, folder_id: str) -> list:
    out, page = [], None
    while True:
        q = urllib.parse.urlencode({
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,size)",
            "pageSize": 200, **({"pageToken": page} if page else {}),
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        with _req(tok, f"{API}/files?{q}") as resp:
            d = json.load(resp)
        out += d.get("files", [])
        page = d.get("nextPageToken")
        if not page:
            return out


def _slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _norm(name: str) -> str:
    """Client identity slug: the intake tree names folders 'Client Name -
    DMA' (measured 2026-08-20, 178 folders), and serving display_ids carry
    legal-form tails the folder omits ('-group-inc'). Strip the DMA suffix
    tokens and the noise words, keep the identity."""
    toks = [t for t in _slug(name).split("-")
            if t not in ("dma", "v2", "inc", "group", "llc", "corp", "co")]
    return "-".join(toks)


def _find_client_folder(tok: str, client: str) -> dict:
    want = _norm(client)
    folders = [f for f in _list_children(tok, INTAKE_FOLDER_ID)
               if f["mimeType"] == FOLDER_MIME]
    exact = [f for f in folders if _norm(f["name"]) == want]
    partial = [f for f in folders
               if _norm(f["name"]).startswith(want + "-")
               or want.startswith(_norm(f["name"]) + "-")]
    hit = exact or partial
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        names = " | ".join(sorted(f["name"] for f in hit))
        raise SystemExit(
            f"multiple client folders matching {client!r}: {names} — "
            f"duplicate folders are adjudicated by a human, never guessed")
    names = ", ".join(sorted(f["name"] for f in folders)) or "none visible"
    raise SystemExit(
        f"no client folder matching {client!r} under the intake tree — "
        f"folders visible: {names}")


def check() -> int:
    """Preflight: the folder answers this identity and its children list."""
    tok = _token()
    try:
        with _req(tok, f"{API}/files/{INTAKE_FOLDER_ID}?fields=id,name"
                       f"&supportsAllDrives=true") as resp:
            meta = json.load(resp)
        kids = _list_children(tok, INTAKE_FOLDER_ID)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"DRIVE PREFLIGHT FAILED: the intake folder is NOT shared "
                  f"with {SA_EMAIL} — a 404 for a real folder means this "
                  f"identity cannot see it. Fix (one time): open the folder "
                  f"in Drive, Share, add that address as Editor.",
                  file=sys.stderr)
        else:
            print(f"DRIVE PREFLIGHT FAILED: HTTP {e.code} from the Drive "
                  f"API — {e.reason}", file=sys.stderr)
        return 1
    folders = sum(1 for k in kids if k["mimeType"] == FOLDER_MIME)
    print(f"drive preflight OK: {meta.get('name')!r} reachable as {SA_EMAIL}; "
          f"{len(kids)} children, {folders} client folders")
    return 0


def _download(tok: str, f: dict, into: Path) -> str:
    if f["mimeType"] in EXPORTS:
        mime, ext = EXPORTS[f["mimeType"]]
        url = (f"{API}/files/{f['id']}/export?"
               + urllib.parse.urlencode({"mimeType": mime}))
        name = f["name"] + ext
    else:
        url = f"{API}/files/{f['id']}?alt=media&supportsAllDrives=true"
        name = f["name"]
    with _req(tok, url) as resp, open(into / name, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return name


def _pull_tree(tok: str, folder_id: str, dest: Path, depth: int = 0) -> int:
    """Recursive: the intake packages keep their workbooks in subfolders
    (03_scoring_workbook/, 02_research_workbook/ — measured on the first
    live run, 2026-08-20, when a flat pull left both workbooks behind and
    the package could not be vetted). Depth-capped against cycles."""
    if depth > 6:
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    got = 0
    for f in _list_children(tok, folder_id):
        if f["mimeType"] == FOLDER_MIME:
            got += _pull_tree(tok, f["id"], dest / f["name"], depth + 1)
        else:
            _download(tok, f, dest)
            got += 1
    return got


def _find_memory_file(tok: str, folder_id: str, client: str) -> dict | None:
    """The client's memory file, whatever slug it was pushed under. One
    session pushed 't-rowe-price — synthesis memory.md' while the next
    looks for 't-rowe-price-group-inc — …'; identity, not spelling, must
    decide, or the client ends up with two diverging memories."""
    want = _norm(client)
    for f in _list_children(tok, folder_id):
        if f["mimeType"] == FOLDER_MIME or not f["name"].endswith(MEMORY_SUFFIX):
            continue
        have = _norm(f["name"][: -len(MEMORY_SUFFIX)])
        if have == want or have.startswith(want) or want.startswith(have):
            return f
    return None


def pull(client: str) -> int:
    tok = _token()
    folder = _find_client_folder(tok, client)
    dest = PACKAGES_DIR / _slug(folder["name"])
    got = _pull_tree(tok, folder["id"], dest)
    print(f"pulled {got} files from {folder['name']!r} -> {dest} (recursive)")
    # Land the client's memory beside the packages so the session never has
    # to guess the local path: canonical is /root/.dma/clients/<client>.md
    # under the slug of the NAME THE CALLER USED (the display_id).
    mem = _find_memory_file(tok, folder["id"], client)
    if mem:
        local = MEMORY_DIR / f"{_slug(client)}.md"
        if local.is_file():
            print(f"memory: local {local} already exists — kept; the Drive "
                  f"copy is in the package dir")
        else:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            pulled_copy = dest / mem["name"]
            if pulled_copy.is_file():
                local.write_bytes(pulled_copy.read_bytes())
            else:
                _download(tok, mem, MEMORY_DIR)
                (MEMORY_DIR / mem["name"]).rename(local)
            print(f"memory: landed {mem['name']!r} -> {local}")
    else:
        print("memory: none in the client folder yet — "
              "client_memory.py init creates the skeleton")
    return 0 if got else 1


def push_memory(client: str) -> int:
    slug = _slug(client)
    local = MEMORY_DIR / f"{slug}.md"
    if not local.is_file():
        raise SystemExit(f"no local memory file at {local} — "
                         f"drive_fetch.py pull lands an existing one there, "
                         f"client_memory.py init writes a new skeleton")
    tok = _token()
    folder = _find_client_folder(tok, client)
    remote_name = f"{slug}{MEMORY_SUFFIX}"
    existing = _find_memory_file(tok, folder["id"], client)
    body = local.read_bytes()
    if existing:
        url = (f"{UPLOAD}/files/{existing['id']}?uploadType=media"
               f"&supportsAllDrives=true")
        with _req(tok, url, data=body, method="PATCH",
                  ctype="text/markdown") as resp:
            json.load(resp)
        if existing["name"] != remote_name:
            # heal a file pushed under a variant slug: one client, one
            # memory file, canonical name = the display_id's slug
            meta = json.dumps({"name": remote_name}).encode()
            with _req(tok, f"{API}/files/{existing['id']}"
                           f"?supportsAllDrives=true", data=meta,
                      method="PATCH", ctype="application/json") as resp:
                json.load(resp)
            print(f"memory renamed in Drive: {existing['name']!r} -> "
                  f"{remote_name!r}")
        print(f"memory updated in Drive: {remote_name!r} in {folder['name']!r}")
    else:
        meta = json.dumps({"name": remote_name,
                           "parents": [folder["id"]]}).encode()
        boundary = "dma-memory-upload"
        payload = io.BytesIO()
        for part, ct in ((meta, "application/json; charset=UTF-8"),
                         (body, "text/markdown")):
            payload.write(f"--{boundary}\r\nContent-Type: {ct}\r\n\r\n".encode())
            payload.write(part + b"\r\n")
        payload.write(f"--{boundary}--".encode())
        url = f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true"
        with _req(tok, url, data=payload.getvalue(), method="POST",
                  ctype=f"multipart/related; boundary={boundary}") as resp:
            json.load(resp)
        print(f"memory created in Drive: {remote_name!r} in {folder['name']!r}")
    return 0


BUNDLE_FOLDER = "DMA Insights"             # legacy name, still recognised
LEDGER_FOLDER = "DMA Insights — ledgers"   # intake-root, cross-client
BUNDLE_CACHE = Path("/root/.dma/bundles")


def _insights_name(client_folder_name: str) -> str:
    """Owner taxonomy (2026-08-20): 'DMAI - <Client Name>' — the client name
    is the client Drive folder's own name minus its ' - DMA'-style suffix,
    e.g. 'T. Rowe Price - DMA' -> 'DMAI - T. Rowe Price'. Applied to every
    new client; existing folders are healed to it on preflight, the same
    one-name-forever rule push-memory applies to memory files."""
    base = re.sub(r"\s*[-–—]\s*DMA\s*$", "", client_folder_name).strip()
    return f"DMAI - {base or client_folder_name.strip()}"


def _bundle_cache_path(client: str) -> Path:
    return BUNDLE_CACHE / _slug(client) / "folder_ids.json"


def _insights_root(tok: str, client: str, pinned_id: str | None = None) -> tuple:
    """(client_folder, insights_folder) — found, healed to taxonomy, or
    created. With pinned_id the owner names the folder outright (preflight
    captures the id); it is validated as a folder and renamed to taxonomy."""
    folder = _find_client_folder(tok, client)
    want = _insights_name(folder["name"])
    chosen = None
    if pinned_id:
        with _req(tok, f"{API}/files/{pinned_id}"
                       f"?fields=id,name,mimeType&supportsAllDrives=true") as r:
            meta = json.load(r)
        if meta.get("mimeType") != FOLDER_MIME:
            raise SystemExit(f"pinned id {pinned_id} is not a folder "
                             f"(mimeType {meta.get('mimeType')!r})")
        chosen = {"id": meta["id"], "name": meta.get("name", "")}
    else:
        kids = [f for f in _list_children(tok, folder["id"])
                if f["mimeType"] == FOLDER_MIME]
        chosen = (next((f for f in kids if f["name"] == want), None)
                  or next((f for f in kids if f["name"] == BUNDLE_FOLDER), None)
                  or next((f for f in kids
                           if f["name"].startswith("DMAI - ")), None))
    if chosen is None:
        meta = json.dumps({"name": want, "mimeType": FOLDER_MIME,
                           "parents": [folder["id"]]}).encode()
        with _req(tok, f"{API}/files?supportsAllDrives=true", data=meta,
                  method="POST", ctype="application/json") as resp:
            chosen = {"id": json.load(resp)["id"], "name": want}
        print(f"insights folder created: {want!r} in {folder['name']!r}")
    elif chosen["name"] != want:
        with _req(tok, f"{API}/files/{chosen['id']}?supportsAllDrives=true",
                  data=json.dumps({"name": want}).encode(), method="PATCH",
                  ctype="application/json") as resp:
            json.load(resp)
        print(f"insights folder healed to taxonomy: {chosen['name']!r} "
              f"-> {want!r}")
        chosen = {"id": chosen["id"], "name": want}
    return folder, chosen


def ensure_insights(client: str, folder_id: str | None = None) -> int:
    """Preflight (owner, 2026-08-20): the client's insights folder exists
    BEFORE production starts and its id is captured locally, so every later
    snapshot push writes by id — resilient to renames, sibling ambiguity and
    a mid-session listing failure. Prints states and ids, never content."""
    tok = _token()
    folder, chosen = _insights_root(tok, client, folder_id)
    surf = _ensure_folder(tok, chosen["id"], "surfaces")
    cache = _bundle_cache_path(client)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "client": client,
        "client_folder_id": folder["id"],
        "client_folder_name": folder["name"],
        "insights_folder_id": chosen["id"],
        "insights_folder_name": chosen["name"],
        "surfaces_folder_id": surf,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=1))
    print(f"folder ids captured: {cache}")
    print(f"insights_folder_id={chosen['id']}")
    return 0


def _ensure_folder(tok: str, parent_id: str, name: str) -> str:
    """Find or create a child folder; returns its id."""
    for f in _list_children(tok, parent_id):
        if f["mimeType"] == FOLDER_MIME and f["name"] == name:
            return f["id"]
    meta = json.dumps({"name": name, "mimeType": FOLDER_MIME,
                       "parents": [parent_id]}).encode()
    with _req(tok, f"{API}/files?supportsAllDrives=true", data=meta,
              method="POST", ctype="application/json") as resp:
        return json.load(resp)["id"]


def push_bundle(client: str, file_path: str, name: str | None) -> int:
    """Owner instruction, 2026-08-20: per-client findings consolidate under
    one 'DMA Insights' folder as JSON bundles per surface, so a resuming
    workflow knows exactly what to look for. Convention: state.json for the
    run-level record (run id, vetter verdict + quarantine list, claim
    history, per-section status map, updated_at), surfaces/<page>.<section>.json
    for each produced surface (payload + challenge verdicts + citation-check
    state). These bundles are RESUME STATE, never a serving source — the
    connector's staged rows stay authoritative once submitted, and on any
    disagreement the connector wins."""
    local = Path(file_path)
    if not local.is_file():
        raise SystemExit(f"no such file: {local}")
    try:
        json.loads(local.read_bytes())
    except Exception as e:                                  # noqa: BLE001
        raise SystemExit(f"bundle must be valid JSON ({e}) — a resume "
                         f"reader that hits a parse error re-derives, which "
                         f"defeats the point")
    remote_name = name or local.name
    tok = _token()
    cache = _bundle_cache_path(client)
    if cache.is_file():
        ids = json.loads(cache.read_text())
        bundle_root = ids["insights_folder_id"]
        shown = ids.get("insights_folder_name") or BUNDLE_FOLDER
        holder = ids.get("client_folder_name", client)
    else:
        folder, chosen = _insights_root(tok, client)
        bundle_root, shown, holder = chosen["id"], chosen["name"], folder["name"]
    parent = bundle_root
    parts = remote_name.split("/")
    for sub in parts[:-1]:
        parent = _ensure_folder(tok, parent, sub)
    leaf = parts[-1]
    existing = [f for f in _list_children(tok, parent)
                if f["mimeType"] != FOLDER_MIME and f["name"] == leaf]
    body = local.read_bytes()
    if existing:
        url = (f"{UPLOAD}/files/{existing[0]['id']}?uploadType=media"
               f"&supportsAllDrives=true")
        with _req(tok, url, data=body, method="PATCH",
                  ctype="application/json") as resp:
            json.load(resp)
        print(f"bundle updated: {shown}/{remote_name} in {holder!r}")
    else:
        meta = json.dumps({"name": leaf, "parents": [parent]}).encode()
        boundary = "dma-bundle-upload"
        payload = io.BytesIO()
        for part, ct in ((meta, "application/json; charset=UTF-8"),
                         (body, "application/json")):
            payload.write(f"--{boundary}\r\nContent-Type: {ct}\r\n\r\n".encode())
            payload.write(part + b"\r\n")
        payload.write(f"--{boundary}--".encode())
        url = f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true"
        with _req(tok, url, data=payload.getvalue(), method="POST",
                  ctype=f"multipart/related; boundary={boundary}") as resp:
            json.load(resp)
        print(f"bundle created: {shown}/{remote_name} in {holder!r}")
    return 0


def push_ledger(file_path: str, session_tag: str) -> int:
    """Persist a session's learning-ledger snapshot (match_feedback.json,
    source_yield.json) to the intake root's shared ledger folder. Routine
    containers are ephemeral and their repo attach is READ-ONLY by design —
    a git push from a synthesis or drift firing fails at the boundary, and
    that is the boundary working. Durability instead: each session pushes
    its ledger files here under a session-stamped name; the weekly
    rectification (the ONE routine that opens PRs) merges the snapshots
    into the repo fixtures."""
    local = Path(file_path)
    if not local.is_file():
        raise SystemExit(f"no such file: {local}")
    try:
        json.loads(local.read_bytes())
    except Exception as e:                                  # noqa: BLE001
        raise SystemExit(f"ledger must be valid JSON ({e})")
    tok = _token()
    root = _ensure_folder(tok, INTAKE_FOLDER_ID, LEDGER_FOLDER)
    remote = f"{local.stem}.{session_tag}{local.suffix}"
    existing = [f for f in _list_children(tok, root)
                if f["mimeType"] != FOLDER_MIME and f["name"] == remote]
    body = local.read_bytes()
    if existing:
        url = (f"{UPLOAD}/files/{existing[0]['id']}?uploadType=media"
               f"&supportsAllDrives=true")
        with _req(tok, url, data=body, method="PATCH",
                  ctype="application/json") as resp:
            json.load(resp)
        print(f"ledger snapshot updated: {LEDGER_FOLDER}/{remote}")
    else:
        meta = json.dumps({"name": remote, "parents": [root]}).encode()
        boundary = "dma-ledger-upload"
        payload = io.BytesIO()
        for part, ct in ((meta, "application/json; charset=UTF-8"),
                         (body, "application/json")):
            payload.write(f"--{boundary}\r\nContent-Type: {ct}\r\n\r\n".encode())
            payload.write(part + b"\r\n")
        payload.write(f"--{boundary}--".encode())
        url = f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true"
        with _req(tok, url, data=payload.getvalue(), method="POST",
                  ctype=f"multipart/related; boundary={boundary}") as resp:
            json.load(resp)
        print(f"ledger snapshot created: {LEDGER_FOLDER}/{remote}")
    return 0


def pull_ledgers(dest_dir: str) -> int:
    """Download every ledger snapshot (rectification merges them)."""
    tok = _token()
    root = _ensure_folder(tok, INTAKE_FOLDER_ID, LEDGER_FOLDER)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in _list_children(tok, root):
        if f["mimeType"] != FOLDER_MIME:
            _download(tok, f, dest)
            n += 1
    print(f"pulled {n} ledger snapshots -> {dest}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p_pull = sub.add_parser("pull")
    p_pull.add_argument("--client", required=True)
    p_push = sub.add_parser("push-memory")
    p_push.add_argument("--client", required=True)
    p_b = sub.add_parser("push-bundle")
    p_b.add_argument("--client", required=True)
    p_b.add_argument("--file", required=True)
    p_b.add_argument("--name", default=None,
                     help="remote path inside 'DMA Insights/', e.g. "
                          "surfaces/heatmap.workbook_scores.json")
    p_l = sub.add_parser("push-ledger")
    p_l.add_argument("--file", required=True)
    p_l.add_argument("--session", required=True,
                     help="session tag for the snapshot name, e.g. "
                          "20260820-synthesis")
    p_pl = sub.add_parser("pull-ledgers")
    p_pl.add_argument("--dest", required=True)
    p_ei = sub.add_parser(
        "ensure-insights",
        help="preflight: find-or-create the client's 'DMAI - <Client>' "
             "folder, heal its name to taxonomy, capture ids locally")
    p_ei.add_argument("--client", required=True)
    p_ei.add_argument("--folder-id", default=None,
                      help="pin a known Drive folder id (owner-supplied); "
                           "validated and renamed to taxonomy")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return check()
    if a.cmd == "pull":
        return pull(a.client)
    if a.cmd == "push-memory":
        return push_memory(a.client)
    if a.cmd == "push-bundle":
        return push_bundle(a.client, a.file, a.name)
    if a.cmd == "push-ledger":
        return push_ledger(a.file, a.session)
    if a.cmd == "pull-ledgers":
        return pull_ledgers(a.dest)
    if a.cmd == "ensure-insights":
        return ensure_insights(a.client, a.folder_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
