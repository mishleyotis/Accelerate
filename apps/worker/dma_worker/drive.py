"""Drive traversal for the package scan (TRD §07 step 1-3).

Lists the intake tree with the worker's own service-account identity —
no key file, no OAuth dance: on Cloud Run the metadata server vends the
token; locally GOOGLE_APPLICATION_CREDENTIALS or an injected token_fn
does. Read-only scope; the worker never writes to Drive.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .scan_diff import FileStat

_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_FIELDS = "nextPageToken,files(id,name,mimeType,md5Checksum,size,modifiedTime)"


def metadata_token(scope: str = _SCOPE) -> str:
    return _mint(scope)[0]


def _mint(scope: str) -> tuple[str, float]:
    """The token and the epoch second it stops being usable."""
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/token?scopes={urllib.parse.quote(scope)}",
        headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.load(r)
    # The metadata server states the lifetime; trust it rather than assuming
    # 3600, and fall back short rather than long — erring towards re-minting
    # costs one cheap call, erring the other way costs the rest of the run.
    ttl = float(body.get("expires_in") or 1800)
    return body["access_token"], time.time() + ttl


def token_provider(scope: str = _SCOPE, margin: float = 300.0):
    """A callable that returns a live token, re-minting before it expires.

    The scan used to mint ONE token at the top of `main()` and pass that
    string to every download for the whole execution. A Drive token lives an
    hour; a full-tree scan of 154 packages does not fit in one. Measured
    2026-08-08: `40 ingested, 114 failed, 1 quarantined`, and every single
    failure was `HTTPError 401: Unauthorized` — not a permissions problem, an
    expiry the run outlived. The requeue path then rescheduled all 114 to try
    again on the next firing, where a long run would expire again at the same
    point.

    Same defect the connector's identity token had, in a different file:
    minted once per process, with no expiry check. Fixed there first; this is
    the other half.
    """
    state: dict = {"tok": None, "exp": 0.0}

    def get(force: bool = False) -> str:
        now = time.time()
        if not force and state["tok"] and state["exp"] - margin > now:
            return state["tok"]
        state["tok"], state["exp"] = _mint(scope)
        return state["tok"]

    return get


def _bearer(token, force: bool = False) -> str:
    """Accept either a token string or a provider callable.

    Both shapes exist because every call site passed a string and the fix is
    at the top of the run; a provider threads through untouched call sites
    this way, and a plain string still works for tests and local use.
    """
    if callable(token):
        try:
            return token(force)
        except TypeError:
            return token()
    return token


def _get(token, url: str, timeout: int) -> bytes:
    """One authenticated GET, re-minting once on a 401.

    A refresh margin removes almost every expiry, but not one that lands
    between the check and the call, and not clock skew. A 401 is the
    server telling us the token is dead: ask for a new one and try once
    more, rather than surfacing it as a failed package.
    """
    for attempt in (0, 1):
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {_bearer(token, bool(attempt))}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0 and callable(token):
                continue
            raise
    raise AssertionError("unreachable")


def _list_children(token, folder_id: str) -> list:
    out, page = [], None
    while True:
        q = urllib.parse.quote(f"'{folder_id}' in parents and trashed=false")
        url = (f"https://www.googleapis.com/drive/v3/files?q={q}"
               f"&fields={urllib.parse.quote(_FIELDS)}&pageSize=1000"
               "&includeItemsFromAllDrives=true&supportsAllDrives=true")
        if page:
            url += f"&pageToken={page}"
        body = json.loads(_get(token, url, 30))
        out.extend(body.get("files", []))
        page = body.get("nextPageToken")
        if not page:
            return out


def walk_tree(intake_folder_id: str, token_fn=token_provider,
              max_depth: int = 6) -> list:
    """Every file under the intake tree as FileStat rows, path segments
    from the intake root down — the classification and test-exclusion
    rules run on those segments."""
    # The provider itself, not a token it vended: an 8,000-file walk
    # can outlive one token just as a 154-package download pass can.
    token = token_fn() if token_fn is not token_provider else token_provider()
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


def download(token, file_id: str) -> bytes:
    return _get(
        token,
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        "?alt=media&supportsAllDrives=true", 120)
