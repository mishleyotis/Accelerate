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

The default key path (/root/.dma/sa.json) is where bootstrap_session.sh
lands the DMA_ROUTINE_SA_KEY environment value; override with --key or the
DMA_SA_KEY_FILE environment variable. Signing shells out to openssl rather
than importing a crypto package so the script runs on the stock container
with zero pip installs.
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

    try:
        with open(args.key) as fh:
            key = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"gcp_token: cannot read key file {args.key}: {exc}",
              file=sys.stderr)
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
