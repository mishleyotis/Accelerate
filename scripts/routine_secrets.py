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
import datetime as _dt
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
DRIVE_KEY_SECRET = os.environ.get("DRIVE_KEY_SECRET", "dma-routine-drive-sa-key")
GITHUB_PAT_SECRET = os.environ.get("GITHUB_PAT_SECRET", "dma-routine-github-pat")
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

GITHUB_API = os.environ.get("GITHUB_API", "https://api.github.com")
# The routine's cron is `50 */3 * * *`. A PAT that dies inside the next three
# hours is a PAT this firing cannot rely on: the run outlives it and the push
# at the end — the routine's only durable output — fails after the work is
# done. So the horizon is the firing interval, not zero.
PAT_MIN_SECONDS = int(os.environ.get("PAT_MIN_SECONDS", 3 * 3600))

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


def _parse_gh_expiry(raw: str) -> _dt.datetime | None:
    """GitHub reports fine-grained PAT expiry as e.g. `2026-08-08 10:15:28 UTC`
    (and, on some routes, an ISO-8601 offset form). Returns an aware datetime,
    or None when the header is a shape this does not know."""
    s = (raw or "").strip()
    if s.upper().endswith(" UTC"):
        s = s[:-4] + " +0000"
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S"):
        try:
            d = _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    return None


def github_pat_status(min_seconds: int = PAT_MIN_SECONDS) -> dict:
    """Prove the PAT WORKS, by spending it on `GET /user`.

    Length is not validity: an expired token is exactly as many characters as
    a live one, and a revoked one is too. The only check that distinguishes
    them is a call. GitHub answers it with the token's real expiry in the
    `github-authentication-token-expiration` response header, so one request
    settles both "is it accepted" and "will it survive this run".

    Returns {ok, verdict, detail, login, expires_at, seconds_left}. The token
    never appears in the return value, in `detail`, or in anything printed —
    not in full and not as a prefix.
    """
    out: dict = {"login": None, "expires_at": None, "seconds_left": None}
    try:
        pat = github_pat()
    except Exception as e:                                     # noqa: BLE001
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": f"could not be read: {e}"}
    if not pat:
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": "resolved to an empty value"}

    # ── Control probe: is anything between us and GitHub substituting a
    #    credential?
    #
    # An egress proxy that injects its own GitHub identity answers /user
    # identically whatever token is presented — same login, same expiry
    # header, 200 every time. A validity check running behind one measures
    # the PROXY's credential and reports it as the PAT's. That is not a
    # hypothetical: it happened here, and the expiry it reported sent a
    # human to regenerate a perfectly good token three times before the
    # tell was noticed — three different secrets cannot share an expiry to
    # the second.
    #
    # So spend one request on a token that CANNOT be valid. If GitHub
    # accepts it, this check can no longer distinguish a live PAT from a
    # dead one, and the honest verdict is UNKNOWN. A check that cannot tell
    # must say so rather than return the answer it would have given anyway.
    probe = urllib.request.Request(
        f"{GITHUB_API}/user",
        headers={"Authorization": "Bearer github_pat_11INVALID"
                                  "0000000000000000000000000000000000000000",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "dma-routine-preflight"})
    try:
        urllib.request.urlopen(probe, timeout=30)
    except urllib.error.HTTPError:
        pass                      # refused, as it must be — the check is sound
    except Exception:             # noqa: BLE001
        pass                      # unreachable; the real call below decides
    else:
        return {**out, "ok": True, "verdict": "UNKNOWN",
                "detail": "an invalid token is also accepted here, so "
                          "something between this process and GitHub is "
                          "substituting a credential — this check cannot "
                          "read the PAT's real state. Validate it where the "
                          "routine actually runs."}

    req = urllib.request.Request(
        f"{GITHUB_API}/user",
        headers={"Authorization": f"Bearer {pat}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "dma-routine-preflight"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            headers, body = r.headers, r.read()
    except urllib.error.HTTPError as e:
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": f"GitHub rejected it: HTTP {e.code} on GET /user "
                          f"(expired, revoked or wrongly scoped)"}
    except Exception as e:                                     # noqa: BLE001
        # Not proof the token is bad — but the routine's only durable output is
        # a push, so an unreachable GitHub is not a workable state either.
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": f"could not reach GitHub to validate it "
                          f"({type(e).__name__}); the run's only output is a push"}

    try:
        out["login"] = json.loads(body).get("login")
    except Exception:                                          # noqa: BLE001
        pass
    who = out["login"] or "the token's account"

    raw = headers.get("github-authentication-token-expiration")
    if not raw:
        return {**out, "ok": True, "verdict": "OK",
                "detail": f"accepted by GitHub for {who}; no expiry set"}
    out["expires_at"] = raw.strip()
    exp = _parse_gh_expiry(raw)
    if exp is None:
        return {**out, "ok": True, "verdict": "WARN",
                "detail": f"accepted by GitHub for {who}; expiry header "
                          f"{raw.strip()!r} is in an unrecognised shape"}
    left = exp.timestamp() - time.time()
    out["seconds_left"] = int(left)
    if left <= 0:
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": f"EXPIRED at {out['expires_at']}"}
    if left < min_seconds:
        return {**out, "ok": False, "verdict": "FAIL",
                "detail": f"expires at {out['expires_at']} — {left / 3600:.1f}h "
                          f"left, inside the {min_seconds / 3600:.0f}h firing "
                          f"interval; this run would outlive it"}
    return {**out, "ok": True, "verdict": "OK",
            "detail": f"accepted by GitHub for {who}; {left / 3600:.1f}h until "
                      f"{out['expires_at']}"}


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
        _remember_identity(DRIVE_IMPERSONATE)
        return tok, how

    return _drive_token_from_key(scope, ck)


# Which identity the live Drive token belongs to. Remediation has to name THIS
# one: a 404 taken while impersonating dmai-worker and a 404 taken with the
# stored key need different fixes, and telling an operator to share a folder
# with an account that already has it wastes the one action they were told to
# take.
_DRIVE_IDENTITY: str | None = None


def _remember_identity(email: str) -> None:
    global _DRIVE_IDENTITY
    _DRIVE_IDENTITY = email


def drive_identity() -> str:
    """The account the routine's Drive calls are actually made as."""
    if _DRIVE_IDENTITY is None:
        drive_token()
    return _DRIVE_IDENTITY or "(unknown identity)"


class DriveError(RuntimeError):
    """A Drive read that did not happen.

    Raised rather than returned so it cannot be mistaken for a successful read
    of an empty folder — the failure mode this replaces was
    `drive_get(...).get("files", [])` yielding `[]` from an error body and the
    routine concluding there was nothing to scan.
    """

    def __init__(self, path: str, code: int, message: str, identity: str):
        self.path, self.code, self.message, self.identity = (
            path, code, message, identity)
        super().__init__(f"Drive {code} on {path} as {identity}: {message}")


_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"


def _key_token(scope: str) -> str | None:
    """An access token for `scope`, signed with the stored service-account key.

    Split out of the Drive fallback because the fallback needs TWO tokens at
    two different scopes: one at cloud-platform to ask IAM Credentials for an
    impersonated token, and the impersonated one at the Drive scope to
    actually read. Signing is openssl rather than google-auth, because the
    images this runs in do not all carry it and a preflight that fails on a
    missing dependency is a preflight that gets skipped. The key is written
    to a 0600 file for exactly one openssl call, then removed.

    Returns None rather than raising: every caller has a degraded path, and a
    raise here turns a working-but-degraded run into no run at all.
    """
    try:
        info = json.loads(secret(DRIVE_KEY_SECRET))
    except Exception:
        return None
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
    except Exception:
        return None
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
        return json.load(urllib.request.urlopen(urllib.request.Request(
            info["token_uri"], data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )))["access_token"]
    except Exception:
        return None


def _drive_token_from_key(scope: str, ck: str) -> tuple[str, str]:
    """Fallback: mint from the stored key, then upgrade to the shared identity.

    The minting itself lives in `_key_token` — this function is about WHICH
    account the resulting token belongs to, which is the part that was wrong.
    """
    info = json.loads(secret(DRIVE_KEY_SECRET))
    now = int(time.time())
    tok = _key_token(scope)
    if not tok:
        raise RuntimeError("the stored key could not be exchanged for a token")
    # One more step before settling for the key's own identity: use this token
    # to impersonate the SAME account the primary path uses. Otherwise the two
    # paths read Drive as two different accounts, and everything shared with
    # one of them — the secrets doc, the intake tree — is invisible to the
    # other. That is the measured failure: gcloud impersonation is unavailable
    # in the scheduled session, the loader falls back here, and the doc 404s
    # for an identity nobody ever shared it with, so the run reports "not
    # retrieving the keys" while the doc is correctly shared all along.
    #
    # Requires roles/iam.serviceAccountTokenCreator on DRIVE_IMPERSONATE for
    # the stored key's account. When that is absent this still returns the
    # key's own token — degraded, but honestly labelled, and the caller's
    # remediation names the identity the read was actually made as.
    # Minted at cloud-platform scope, NOT the Drive scope of `tok`:
    # iamcredentials.googleapis.com refuses a token scoped only to Drive, so
    # passing `tok` here fails silently and the upgrade never happens. The
    # DRIVE scope is what we ask generateAccessToken to issue, not what we
    # authenticate the call with — two different scopes, one call apart.
    imp = None
    admin = _key_token(_CLOUD_PLATFORM)
    if admin:
        imp = _impersonate_with(admin, DRIVE_IMPERSONATE, scope)
    if imp:
        how = f"impersonating {DRIVE_IMPERSONATE} via the stored key"
        _cache[ck] = (imp, how, now + 3000)
        _remember_identity(DRIVE_IMPERSONATE)
        return imp, how

    how = f"stored key for {info['client_email']}"
    _cache[ck] = (tok, how, now + 3000)
    _remember_identity(info["client_email"])
    return tok, how


def _impersonate_with(token: str, target: str, scope: str) -> str | None:
    """Exchange `token` for one belonging to `target`, or None.

    None on any failure, deliberately: this is a best-effort upgrade on the
    fallback path, and a raise here would turn a degraded-but-working run into
    no run at all.
    """
    url = ("https://iamcredentials.googleapis.com/v1/projects/-/"
           f"serviceAccounts/{target}:generateAccessToken")
    body = json.dumps({"scope": scope.split(), "lifetime": "3600s"}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"})
    try:
        out = json.load(urllib.request.urlopen(req, timeout=60))
    except Exception:
        return None
    tok = out.get("accessToken")
    return tok if tok and len(tok) > 100 else None


def drive_get(path: str, **params) -> dict:
    """One Drive v3 GET with the routine's token. Shared-drive aware.

    Raises DriveError on any failure — HTTP or transport. It used to return
    `{"error": {...}}`, which every caller then read with `.get("files", [])`,
    so a permissions failure and an empty folder produced the same `[]` and the
    routine treated "I could not look" as "there is nothing there". A read that
    did not happen must not be answerable.
    """
    params.setdefault("supportsAllDrives", "true")
    params.setdefault("includeItemsFromAllDrives", "true")
    url = f"https://www.googleapis.com/drive/v3/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {drive_token()[0]}"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise DriveError(path, e.code,
                         e.read()[:300].decode(errors="replace"),
                         drive_identity()) from None
    except Exception as e:                                     # noqa: BLE001
        raise DriveError(path, 0, f"{type(e).__name__}: {e}",
                         drive_identity()) from None




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
    who = "(identity not established)"
    try:
        tok, _how = drive_token("https://www.googleapis.com/auth/drive.readonly")
        who = drive_identity()
        url = (f"https://www.googleapis.com/drive/v3/files/{SECRETS_DOC_ID}"
               "/export?mimeType=text/plain")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        text = urllib.request.urlopen(req, timeout=30).read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Name the identity that took THIS 404. Impersonation and the
            # stored-key fallback are different accounts, and the fallback is
            # exactly the case where the hardcoded worker address is wrong.
            print(f"secrets doc         FAIL  404: the doc is not shared with "
                  f"{who}, the identity this read was made as. Share it "
                  f"(view-only) with that account — falling back to Secret "
                  f"Manager values this run.")
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
    """Preflight. Prints verdicts only — no secret and no prefix of one.

    Exit codes, and the line between them:

      0  FAIL-free. Every credential resolves, works, and outlives this run.
      2  WARN — degraded but workable: something is not as intended, and the
         run can still complete correctly. The secrets doc being unreachable
         (Secret Manager carries the values) and an intake tree that is
         genuinely, verifiably empty both qualify.
      1  FAIL — the run cannot complete correctly. A secret that will not
         read, a PAT GitHub rejects or that dies inside this firing interval,
         a Drive tree that cannot be READ. "Could not read" is a FAIL and not
         a WARN precisely because it is indistinguishable, from the outside,
         from the state the routine treats as "nothing to do".
    """
    # The user's stated source of record first — its verdict line names the
    # identity that took the 404 and never prints a value.
    doc_secrets()

    intake = os.environ.get("INTAKE_FOLDER_ID",
                            "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo")
    degraded = False

    # Length is not validity. Spend the token on GET /user and read the expiry
    # GitHub reports back.
    st = github_pat_status()
    # Padded to the longest verdict word, not to the shortest: at 5 wide
    # UNKNOWN overflowed its own column and printed "UNKNOWNan invalid token
    # is also accepted here" — the one verdict whose text most needs reading,
    # run together with the word before it.
    print(f"github pat        {st['verdict']:<8}{st['detail']}")
    if not st["ok"]:
        return 1
    # UNKNOWN is degraded, not fine. It means the check could not read the
    # token's real state — which is exactly the condition under which a
    # silent OK would send the routine off to discover the truth by failing.
    if st["verdict"] in ("WARN", "UNKNOWN"):
        degraded = True

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
    try:
        meta = drive_get(f"files/{intake}", fields="id,name")
    except DriveError as e:
        print(f"intake folder     FAIL {e.code} — {e.identity} cannot READ the "
              f"intake tree (this is not the same as the tree being empty). "
              f"Either grant roles/iam.serviceAccountTokenCreator on "
              f"{DRIVE_IMPERSONATE} (preferred — no key material), or share "
              f"the folder with {e.identity}")
        return 1

    try:
        kids = drive_get("files", q=f"'{intake}' in parents",
                         fields="files(id,name)", pageSize=50)
    except DriveError as e:
        print(f"intake children   FAIL {e.code} — the folder resolves but its "
              f"children could not be listed as {e.identity}; this run cannot "
              f"tell an empty tree from an unreadable one")
        return 1

    n = len(kids.get("files", []))
    print(f"intake folder     OK   {meta.get('name')!r}, {n} child folder(s)")
    if n == 0:
        print("intake folder     WARN listed successfully and is genuinely "
              "empty — nothing to scan")
        degraded = True
    return 2 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
