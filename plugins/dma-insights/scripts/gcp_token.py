#!/usr/bin/env python3
"""Mint Google tokens from a service-account key file — no gcloud required.

Fresh routine containers carry python3, openssl and curl, and nothing else
(measured 2026-08-19: no SDK, no active account, no proxy credential
injection). This is the identity path for those containers: RS256-sign a
JWT with the key file and exchange it at Google's token endpoint, exactly
what gcloud does under its hood.

Two modes, matching the two credentials a routine session needs:

    gcp_token.py id     --audience <url> [--key <file>]   # OIDC ID token:
        Cloud Run IAM (roles/run.invoker) checks this. The audience must be
        the SERVICE URL — the same audience trap doctor.py documents.
    gcp_token.py access [--scope <scope>] [--key <file>]  # OAuth2 access
        token, for Secret Manager REST (fetching the connector path token).

Contract, same as mcp_auth_headers.sh: the token goes to stdout because
stdout is the transport — it is never logged, never written to disk, never
echoed to stderr. Diagnostics go to stderr; any failure exits non-zero with
an empty stdout so callers can fail closed or fail open as THEY choose.

The key is found by `load_key` — a key file if one exists (default
/root/.dma/sa.json, where bootstrap_session.sh lands it; override with
--key or DMA_SA_KEY_FILE), otherwise straight from the environment. See
that function for why the environment rung is what makes scheduled routines
work. Signing shells out to openssl rather than importing a crypto package
so the script runs on the stock container with zero pip installs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_KEY = os.environ.get("DMA_SA_KEY_FILE", "/root/.dma/sa.json")
DEFAULT_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def _b64url(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def build_unsigned_jwt(claims: dict) -> bytes:
    """header.payload — deterministic input to the signature."""
    header = _b64url(json.dumps(
        {"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    return header + b"." + payload


def sign_rs256(signing_input: bytes, private_key_pem: str) -> bytes:
    """RS256 via the openssl CLI. The key touches disk only as a 0600 temp
    file that is unlinked in finally — the same lifetime a library would
    give it in memory pages, and the container is single-tenant."""
    fd, path = tempfile.mkstemp(prefix="dma-sa-", suffix=".pem")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(private_key_pem)
        out = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", path],
            input=signing_input, capture_output=True, check=True)
        return out.stdout
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def load_key(path: str | None = None) -> tuple:
    """(key dict, source) — the key file if one exists, else the environment.

    THE ENVIRONMENT RUNG IS WHY ROUTINES WORK AT ALL. A plugin's MCP servers
    register at session START, and mcp_auth_headers.sh is invoked at that
    moment; bootstrap_session.sh, if it runs as a step inside the session,
    lands /root/.dma/sa.json minutes too late — the connector has already
    failed to authenticate and its 33 tools never resolve into the session
    (measured 2026-08-20: a firing bootstrapped successfully, the doctor went
    14/14 green over direct HTTP, and the connector's tools were still absent
    because the session had already started). Reading the key straight from
    the environment removes the ordering problem: the credential is present
    before the first tool registration, with nothing to run beforehand.

    Order: an explicit key file (a bootstrapped container, or a developer's
    own path), then DMA_ROUTINE_SA_KEY_B64 (base64 of the key JSON on one
    line — the shape the .env-format settings field accepts), then raw
    DMA_ROUTINE_SA_KEY for contexts that carry newlines. Nothing is written
    to disk on the environment rungs; the key is parsed in memory.
    """
    path = path or DEFAULT_KEY
    try:
        if os.path.getsize(path) > 0:
            with open(path) as fh:
                return json.load(fh), f"key file {path}"
    except (OSError, ValueError):
        pass
    raw = os.environ.get("DMA_ROUTINE_SA_KEY_B64", "").strip()
    if raw:
        try:
            return json.loads(base64.b64decode(raw)), "DMA_ROUTINE_SA_KEY_B64"
        except Exception as exc:
            return None, f"DMA_ROUTINE_SA_KEY_B64 set but unusable: {exc}"
    raw = os.environ.get("DMA_ROUTINE_SA_KEY", "").strip()
    if raw:
        try:
            return json.loads(raw), "DMA_ROUTINE_SA_KEY"
        except Exception as exc:
            return None, f"DMA_ROUTINE_SA_KEY set but unusable: {exc}"
    return None, (f"no key file at {path} and neither DMA_ROUTINE_SA_KEY_B64 "
                  "nor DMA_ROUTINE_SA_KEY is set")


def mint_assertion(key: dict, extra_claims: dict) -> str:
    now = int(time.time())
    claims = {
        "iss": key["client_email"],
        "sub": key["client_email"],
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
        **extra_claims,
    }
    unsigned = build_unsigned_jwt(claims)
    sig = sign_rs256(unsigned, key["private_key"])
    return (unsigned + b"." + _b64url(sig)).decode()


def exchange(assertion: str) -> dict:
    body = urllib.parse.urlencode(
        {"grant_type": JWT_GRANT, "assertion": assertion}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    p_id = sub.add_parser("id", help="OIDC ID token for a Cloud Run audience")
    p_id.add_argument("--audience", required=True)
    p_id.add_argument("--key", default=DEFAULT_KEY)
    p_ac = sub.add_parser("access", help="OAuth2 access token")
    p_ac.add_argument("--scope", default=DEFAULT_SCOPE)
    p_ac.add_argument("--key", default=DEFAULT_KEY)
    args = ap.parse_args(argv)

    key, source = load_key(args.key)
    if key is None:
        print(f"gcp_token: no usable key — {source}", file=sys.stderr)
        return 2

    extra = ({"target_audience": args.audience} if args.mode == "id"
             else {"scope": args.scope})
    field = "id_token" if args.mode == "id" else "access_token"
    try:
        token = exchange(mint_assertion(key, extra)).get(field, "")
    except urllib.error.HTTPError as exc:
        # Google's error body names the cause (invalid_grant on a disabled
        # key, invalid_scope, clock skew); the token itself is never in it.
        print(f"gcp_token: token exchange failed HTTP {exc.code}: "
              f"{exc.read()[:300]!r}", file=sys.stderr)
        return 3
    except Exception as exc:  # network, openssl, malformed key
        print(f"gcp_token: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    if not token:
        print("gcp_token: exchange succeeded but response carried no "
              f"{field}", file=sys.stderr)
        return 3
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
