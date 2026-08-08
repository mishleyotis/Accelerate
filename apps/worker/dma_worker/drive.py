"""Drive traversal for the package scan (TRD §07 step 1-3).

Lists the intake tree with the worker's own service-account identity —
no key file, no OAuth dance: on Cloud Run the metadata server vends the
token; locally GOOGLE_APPLICATION_CREDENTIALS or an injected token_fn
does. Read-only scope; the worker never writes to Drive.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .scan_diff import FileStat

_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_FIELDS = "nextPageToken,files(id,name,mimeType,md5Checksum,size,modifiedTime)"


def metadata_token(scope: str = _SCOPE) -> str:
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/token?scopes={urllib.parse.quote(scope)}",
        headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["access_token"]


def _list_children(token: str, folder_id: str) -> list:
    out, page = [], None
    while True:
        q = urllib.parse.quote(f"'{folder_id}' in parents and trashed=false")
        url = (f"https://www.googleapis.com/drive/v3/files?q={q}"
               f"&fields={urllib.parse.quote(_FIELDS)}&pageSize=1000"
               "&includeItemsFromAllDrives=true&supportsAllDrives=true")
        if page:
            url += f"&pageToken={page}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        out.extend(body.get("files", []))
        page = body.get("nextPageToken")
        if not page:
            return out


def walk_tree(intake_folder_id: str, token_fn=metadata_token,
              max_depth: int = 6) -> list:
    """Every file under the intake tree as FileStat rows, path segments
    from the intake root down — the classification and test-exclusion
    rules run on those segments."""
    token = token_fn()
    stats: list = []

    def rec(folder_id, segments, ids, depth):
        if depth > max_depth:
            return
        for f in _list_children(token, folder_id):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                rec(f["id"], segments + [f["name"]], ids + [f["id"]], depth + 1)
            else:
                stats.append(FileStat(
                    f["id"], tuple(segments + [f["name"]]), f["name"],
                    f.get("md5Checksum") or f.get("modifiedTime") or "",
                    int(f.get("size") or 0), f.get("mimeType") or "",
                    tuple(ids)))

    rec(intake_folder_id, [], [], 0)
    return stats


def download(token: str, file_id: str) -> bytes:
    req = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()
