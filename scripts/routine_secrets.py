#!/usr/bin/env python3
"""Load the scheduled routine's credentials from Secret Manager, at call time.

The app-scheduled synthesis session starts in a fresh container with a fresh
clone. It needs two credentials that the container does not carry:

  dma-routine-drive-sa-key   a service-account key that can read the DMA
                             package tree on Drive
  dma-routine-github-pat     a GitHub PAT for pushing the session's work

Neither is committed, neither is written to a dotfile, and neither is exported
into the environment where a later `env` dump or a subprocess inherits it.
This module fetches a secret when a call needs it and hands back the value to
that call only:

    from routine_secrets import drive_token, github_pat
    tok = drive_token()          # a Drive-scoped OAuth token, ~1h
    hdr = {"Authorization": f"Bearer {github_pat()}"}

Values are cached in memory for the life of the process and never logged.
`main()` is a preflight: it proves each credential resolves and works, and
prints only verdicts — never a secret, never a prefix of one.

Why a token and not the key: callers need Drive, and the key is the means.
`drive_token` signs a JWT with the key and exchanges it, so the key itself
never leaves this module. `gcloud auth activate-service-account` would not do
here — it mints cloud-platform scope only, and Drive returns 403 for it.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
DRIVE_KEY_SECRET = os.environ.get("DRIVE_KEY_SECRET", "dma-routine-drive-sa-key")
GITHUB_PAT_SECRET = os.environ.get("GITHUB_PAT_SECRET", "dma-routine-github-pat")
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# The identity the package scan already reads Drive as. The intake tree is
# shared with it, which is why the worker Job can walk it. Impersonating it
# beats a stored key on every axis that matters: no key material to leak, the
# grant is revocable in one IAM change, and every token mint is audited. The
# stored key stays as the fallback for an environment without the
# tokenCreator grant.
DRIVE_IMPERSONATE = os.environ.get(
    "DRIVE_IMPERSONATE", f"dmai-worker@{PROJECT}.iam.gserviceaccount.com")

_cache: dict[str, object] = {}


def _gcloud() -> str:
    """gcloud is not on PATH in every image this runs in."""
    for p in ("gcloud", "/root/google-cloud-sdk/bin/gcloud",
              "/usr/lib/google-cloud-sdk/bin/gcloud"):
        try:
            subprocess.run([p, "--version"], capture_output=True, check=True)
            return p
        except (OSError, subprocess.CalledProcessError):
            continue
    raise RuntimeError("gcloud not found — cannot reach Secret Manager")


def secret(name: str, *, project: str = PROJECT) -> str:
    # The doc is the user's source of record: a key defined there wins over
    # Secret Manager, so a rotation in the doc takes effect on the next run.
    _doc = doc_secrets()
    _k = name.upper().replace("-", "_")
    if _k in _doc:
        return _doc[_k]
    """One secret's latest version, as text. Cached; never logged.

    CLOUDSDK_AUTH_ACCESS_TOKEN is cleared for the child: a stale token in the
    environment overrides the activated account and fails with a 401 that
    reads like a permissions problem.
    """
    key = f"{project}/{name}"
    if key in _cache:
        return _cache[key]                                     # type: ignore[return-value]
    env = {k: v for k, v in os.environ.items()
           if k != "CLOUDSDK_AUTH_ACCESS_TOKEN"}
    r = subprocess.run(
        [_gcloud(), "secrets", "versions", "access", "latest",
         f"--secret={name}", f"--project={project}"],
        capture_output=True, env=env)
    if r.returncode != 0:
        # stderr may name the secret; it never contains the payload.
        raise RuntimeError(
            f"could not read secret {name}: {r.stderr.decode().strip()[:300]}")
    val = r.stdout.decode()
    _cache[key] = val
    return val


def github_pat() -> str:
    """The PAT, stripped of the trailing newline `secrets create` preserves."""
    return secret(GITHUB_PAT_SECRET).strip()


def _b64(b: bytes) -> bytes:
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def drive_token(scope: str = DRIVE_SCOPE) -> tuple[str, str]:
    """A Drive-scoped OAuth token, and how it was obtained.

    Impersonation first — no key material anywhere — falling back to the stored
    service-account key. Returns `(token, how)` so a caller and the preflight
    can report which path was taken rather than guessing.
    """
    ck = f"token:{scope}"
    hit = _cache.get(ck)
    if isinstance(hit, tuple) and hit[2] > time.time() + 120:
        return hit[0], hit[1]

    env = {k: v for k, v in os.environ.items()
           if k != "CLOUDSDK_AUTH_ACCESS_TOKEN"}
    r = subprocess.run(
        [_gcloud(), "auth", "print-access-token",
         f"--impersonate-service-account={DRIVE_IMPERSONATE}",
         f"--scopes={scope}"], capture_output=True, env=env)
    tok = r.stdout.decode().strip()
    if r.returncode == 0 and len(tok) > 100:
        how = f"impersonating {DRIVE_IMPERSONATE}"
        _cache[ck] = (tok, how, time.time() + 3000)
        return tok, how

    return _drive_token_from_key(scope, ck)


def _drive_token_from_key(scope: str, ck: str) -> tuple[str, str]:
    """Fallback: mint from the stored key.

    Signed with openssl rather than a library, because the images this runs in
    do not all carry google-auth and a preflight that fails on a missing
    dependency is a preflight that gets skipped. The key is written to a 0600
    file only for the length of one openssl call, then removed.
    """
    info = json.loads(secret(DRIVE_KEY_SECRET))
    now = int(time.time())
    hdr = _b64(json.dumps({"alg": "RS256", "typ": "JWT",
                           "kid": info["private_key_id"]}).encode())
    claims = _b64(json.dumps({"iss": info["client_email"], "scope": scope,
                              "aud": info["token_uri"], "iat": now,
                              "exp": now + 3600}).encode())
    import tempfile
    fd, pem = tempfile.mkstemp(prefix=".rk-", suffix=".pem")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(info["private_key"])
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", pem],
                             input=hdr + b"." + claims,
                             capture_output=True, check=True).stdout
    finally:
        try:
            os.unlink(pem)
        except OSError:
            pass

    jwt = (hdr + b"." + claims + b"." + _b64(sig)).decode()
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt}).encode()
    try:
        tok = json.load(urllib.request.urlopen(urllib.request.Request(
            info["token_uri"], data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )))["access_token"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"token exchange rejected the stored key: {e.code} "
            f"{e.read()[:200].decode(errors='replace')}") from None
    how = f"stored key for {info['client_email']}"
    _cache[ck] = (tok, how, now + 3000)
    return tok, how


def drive_get(path: str, **params) -> dict:
    """One Drive v3 GET with the routine's token. Shared-drive aware."""
    params.setdefault("supportsAllDrives", "true")
    params.setdefault("includeItemsFromAllDrives", "true")
    url = f"https://www.googleapis.com/drive/v3/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {drive_token()[0]}"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return {"error": {"code": e.code,
                          "message": e.read()[:300].decode(errors="replace")}}




# ── The secrets DOC, the user's stated source of record ─────────────────────
#
# The user maintains the routine's credentials in a Google Doc (Zennify-only).
# The routine reads it AT CALL TIME through the same impersonated dmai-worker
# identity it already uses for the intake tree, parses KEY: VALUE lines, and
# hands values to callers in memory only — nothing exported, nothing logged.
#
# Two failure modes, named precisely because one of them needs a human once:
#   404 — the doc is not shared with the service account. FIX (one click):
#         share it, view-only, with
#         dmai-worker@digital-maturity-assessor.iam.gserviceaccount.com.
#   any other error — transient; the Secret Manager values below stand in.
#
# Secret Manager remains the fallback so a doc outage never blocks a run; the
# doc wins wherever both define a key, so a rotation in the doc takes effect
# on the next firing with no redeploy.

SECRETS_DOC_ID = os.environ.get(
    "SECRETS_DOC_ID", "1z5cH44uOdAyrP5d8EoqK5airWQx2KjrqIf3jZHzhNuU")

_DOC_CACHE: dict | None = None


def doc_secrets() -> dict:
    """KEY -> value from the secrets doc; {} when unreachable (fallback: SM).

    Parses `KEY: value` / `KEY = value` lines; a KEY is upper-snake with 3+
    chars. Values live in this process only.
    """
    global _DOC_CACHE
    if _DOC_CACHE is not None:
        return _DOC_CACHE
    # Reentrancy guard: drive_token's key fallback calls secret(), which
    # consults this function. Mark in-progress as {} so the nested call reads
    # Secret Manager directly instead of recursing.
    _DOC_CACHE = {}
    import re
    try:
        tok, _how = drive_token("https://www.googleapis.com/auth/drive.readonly")
        url = (f"https://www.googleapis.com/drive/v3/files/{SECRETS_DOC_ID}"
               "/export?mimeType=text/plain")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        text = urllib.request.urlopen(req, timeout=30).read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("secrets doc         FAIL  404: the doc is not shared with the "
                  "routine's identity. Share it (view-only) with "
                  "dmai-worker@digital-maturity-assessor.iam.gserviceaccount.com "
                  "— falling back to Secret Manager values this run.")
        else:
            print(f"secrets doc         WARN  HTTP {e.code} — falling back to "
                  "Secret Manager values this run.")
        _DOC_CACHE = {}
        return _DOC_CACHE
    except Exception as e:
        print(f"secrets doc         WARN  {type(e).__name__} — falling back to "
              "Secret Manager values this run.")
        _DOC_CACHE = {}
        return _DOC_CACHE
    out = _parse_doc(text)
    print(f"secrets doc         OK    {len(out)} key(s) loaded at call time, "
          "values held in memory only")
    _DOC_CACHE = out
    return out


def _parse_doc(text: str) -> dict:
    """Parse the doc AS THE USER ACTUALLY WRITES IT, not as a spec imagines it.

    The live doc (inspected 2026-08-07, shapes only, values never printed)
    carries two things and neither is a `KEY: value` line:

      1. a bare GitHub fine-grained PAT on its own line (`github_pat_…`);
      2. the Drive service-account key as `field "value"` pairs — the JSON
         fields with the braces and colons lost to the Docs table export.

    Both are recognised here, alongside the `KEY: value` / `KEY = value` form
    the earlier parser expected, so any of the three notations works from now
    on. Recognised material maps onto the names the code already consults via
    `secret()`: DMA_ROUTINE_GITHUB_PAT and DMA_ROUTINE_DRIVE_SA_KEY.
    """
    import re
    out: dict[str, str] = {}
    sa: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.lstrip("﻿").strip()
        if not line:
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]{2,48})\s*[:=]\s*(\S.*?)$", line)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        # A bare GitHub token on its own line IS the PAT.
        if re.match(r"^(github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,})$",
                    line):
            out.setdefault("DMA_ROUTINE_GITHUB_PAT", line)
            continue
        # Service-account key fields: `field "value"` (quoted, no colon).
        m = re.match(r'^([a-z][a-z0-9_]{1,40})\s+"(.*)"$', line)
        if m:
            sa[m.group(1)] = m.group(2)
    if sa.get("type") == "service_account" and "private_key" in sa:
        # The doc holds the JSON-source form of the key, so the PEM's line
        # breaks arrive as literal backslash-n text. json.loads on the
        # reassembled document must yield REAL newlines — the PEM is written
        # to disk for one openssl call — so unescape before re-encoding.
        sa["private_key"] = sa["private_key"].replace("\\n", "\n")
        out.setdefault("DMA_ROUTINE_DRIVE_SA_KEY", json.dumps(sa))
    return out


def main() -> int:
    # The user's stated source of record first — its verdict line names the
    # one-click share fix on 404 and never prints a value.
    doc_secrets()
    """Preflight. Prints verdicts only — no secret and no prefix of one.

    Exit codes are graded, because the two failures need different responses:

      0  every credential resolves and the Drive tree is reachable
      2  credentials resolve, but the stored key cannot see the package tree —
         the session's own Drive connector has to supply it. Degraded, not
         blocked.
      1  a secret could not be read at all. Nothing downstream can work.
    """
    intake = os.environ.get("INTAKE_FOLDER_ID",
                            "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo")
    degraded = False

    try:
        pat = github_pat()
        print(f"github pat        OK   resolved, {len(pat)} chars, not echoed")
    except Exception as e:                                     # noqa: BLE001
        print(f"github pat        FAIL {e}")
        return 1

    try:
        _, how = drive_token()
        print(f"drive token       OK   {how}")
    except Exception as e:                                     # noqa: BLE001
        print(f"drive token       FAIL {e}")
        return 1

    # Authenticating is not the same as being able to READ the tree. The stored
    # key authenticated and still returned 404 on the intake folder, because the
    # folder is shared with the WORKER's identity and not with that key's. A
    # preflight that stopped at "token minted" would have called that green.
    meta = drive_get(f"files/{intake}", fields="id,name")
    if "error" in meta:
        who = json.loads(secret(DRIVE_KEY_SECRET))["client_email"]
        print(f"intake folder     WARN {meta['error']['code']} — this identity "
              f"cannot see the intake tree. Either grant "
              f"roles/iam.serviceAccountTokenCreator on {DRIVE_IMPERSONATE} "
              f"(preferred — no key material), or share the folder with {who}")
        degraded = True
    else:
        kids = drive_get("files", q=f"'{intake}' in parents",
                         fields="files(id,name)", pageSize=50)
        n = len(kids.get("files", []))
        print(f"intake folder     OK   {meta.get('name')!r}, {n} child folder(s)")
        if n == 0:
            print("intake folder     WARN readable but empty — nothing to scan")
    return 2 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
