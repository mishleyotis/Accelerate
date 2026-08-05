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


def main() -> int:
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
