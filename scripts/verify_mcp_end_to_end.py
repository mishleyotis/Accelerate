#!/usr/bin/env python3
"""Run the ENTIRE MCP against a live deployment, not a piece of it.

    python3 scripts/verify_mcp_end_to_end.py [--base URL]

WHY THIS EXISTS. Three separate verification passes declared this connector
healthy and it could not be added to claude.ai any of those times, because
each pass tested a PIECE:

  * a `curl` probe of /authorize succeeded — but curl's User-Agent is not the
    one the server uses, so the CIMD fetch that actually runs was never
    exercised (fixed 2026-08-21; claude.ai answers `Python-urllib/*` with
    HTTP 403 / Cloudflare 1010);
  * `/register` was tested and worked — but claude.ai does not use dynamic
    registration, it passes a URL as the client_id;
  * unit tests covered the flow with every network call stubbed, so they
    passed against a deployment that was refusing real clients.

A piece passing means nothing here. This walks the whole path against the
running service and calls a real tool at the end of it.

THE ONE STUB, and it is unavoidable: the Google sign-in leg needs a human at
a browser. Everything after it is exercised for real by minting the code that
`callback()` mints once Google confirms a verified @zennify.com identity —
same signing key, same claims, same shape. What that cannot tell you is
whether GOOGLE will accept our client credentials, so the script asks Google
directly instead of assuming, and reports its answer verbatim.

Nothing secret is printed. Secrets are read into memory and used; lengths and
prefixes are reported, never values.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROD = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"
CIMD = "https://claude.ai/oauth/mcp-oauth-client-metadata"
CLAUDE_RU = "https://claude.ai/api/mcp/auth_callback"
PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
PROBE_RUN = os.environ.get("DMA_PROBE_RUN", "7a6ad71c-6225-4e0b-80fb-135cfd04b2dd")

_ok = _fail = 0
_failed: list = []


def step(name: str, good: bool, note: str = "") -> bool:
    global _ok, _fail
    print(f"  [{'PASS' if good else 'FAIL'}] {name}{(' — ' + note) if note else ''}")
    if good:
        _ok += 1
    else:
        _fail += 1
        _failed.append(name)
    return good


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def secret(name: str) -> str:
    r = subprocess.run(["gcloud", "secrets", "versions", "access", "latest",
                        f"--secret={name}", f"--project={PROJECT}"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def http(url: str, method="GET", data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)
    except Exception as e:                                   # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", {}


def no_redirect(url: str):
    """A 302 must be READ, not followed — the Location is the assertion."""
    op = urllib.request.build_opener(type("NR", (urllib.request.HTTPRedirectHandler,),
                                          {"redirect_request": lambda *a, **k: None}))
    try:
        with op.open(url, timeout=30) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)
    except Exception as e:                                   # noqa: BLE001
        return 0, {"x-error": f"{type(e).__name__}: {e}"}


def mcp_call(base: str, method: str, params: dict, token: str):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    s, raw, _ = http(base + "/mcp", "POST", body, {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}"})
    for line in raw.splitlines():                    # streamable HTTP may SSE
        if line.startswith("data:"):
            raw = line[5:].strip()
            break
    try:
        return s, json.loads(raw)
    except Exception:                                        # noqa: BLE001
        return s, {"raw": raw[:200]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("DMA_MCP_HOST", PROD))
    args = ap.parse_args()
    base = args.base.rstrip("/")
    print(f"Running the entire MCP against {base}\n")

    print("── 1 · discovery documents ──")
    for p in ("/.well-known/oauth-protected-resource",
              "/.well-known/oauth-protected-resource/mcp",
              "/.well-known/oauth-authorization-server",
              "/.well-known/openid-configuration"):
        s, body, _ = http(base + p)
        step(f"GET {p}", s == 200, f"http {s}")
    s, body, _ = http(base + "/.well-known/oauth-authorization-server")
    meta = json.loads(body) if s == 200 else {}
    step("PKCE S256 advertised", "S256" in (meta.get("code_challenge_methods_supported") or []))
    step("offline_access advertised", "offline_access" in (meta.get("scopes_supported") or []))

    print("── 2 · the unauthenticated challenge ──")
    s, _, h = http(base + "/mcp", "POST", b"{}", {"Content-Type": "application/json"})
    low = {k.lower(): v for k, v in h.items()}
    step("POST /mcp is 401", s == 401, f"http {s}")
    step("WWW-Authenticate present", "www-authenticate" in low)
    # Without this a browser client cannot READ the challenge it just got.
    step("CORS exposes WWW-Authenticate",
         "WWW-Authenticate" in low.get("access-control-expose-headers", ""))

    print("── 3 · client identity via CIMD (what claude.ai actually sends) ──")
    verifier = b64u(os.urandom(40))
    challenge = b64u(hashlib.sha256(verifier.encode()).digest())
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": CIMD, "redirect_uri": CLAUDE_RU,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "scope": "openid email profile offline_access", "state": "st123",
        "resource": base + "/mcp"})
    s, h = no_redirect(f"{base}/authorize?{q}")
    loc = {k.lower(): v for k, v in h.items()}.get("location", "")
    step("/authorize accepts a URL client_id", s == 302, f"http {s}")
    gq = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    step("redirects to Google", "accounts.google.com" in loc)
    step("domain-restricted (hd)", gq.get("hd", [""])[0].endswith("zennify.com"))
    step("carries a signed xstate", gq.get("state", [""])[0].count(".") == 1)
    step("google redirect_uri is our callback",
         gq.get("redirect_uri", [""])[0] == f"{base}/oauth/callback")

    print("── 4 · dynamic registration (the other identity path) ──")
    s, body, _ = http(base + "/register", "POST",
                      json.dumps({"redirect_uris": [CLAUDE_RU],
                                  "client_name": "e2e-probe"}).encode(),
                      {"Content-Type": "application/json"})
    reg = json.loads(body) if s in (200, 201) else {}
    step("/register issues a client_id",
         str(reg.get("client_id", "")).startswith("dmai."), f"http {s}")

    print("── 5 · will GOOGLE accept our client credentials? ──")
    cid, csec = secret("dmai-oauth-client-id"), secret("dmai-oauth-client-secret")
    step("client id readable", bool(cid), f"{len(cid)} chars")
    step("client secret readable", bool(csec),
         f"{len(csec)} chars, GOCSPX- prefix: {csec.startswith('GOCSPX-')}")
    if cid and csec:
        # A deliberately bogus code. invalid_grant means the SECRET is fine and
        # only the code was bad; invalid_client means the secret is wrong. This
        # is the one thing the stub below cannot tell you, so ask Google.
        s, body, _ = http("https://oauth2.googleapis.com/token", "POST",
                          urllib.parse.urlencode({
                              "code": "4/0AdeliberatelyBogusCode",
                              "client_id": cid, "client_secret": csec,
                              "redirect_uri": f"{base}/oauth/callback",
                              "grant_type": "authorization_code"}).encode(),
                          {"Content-Type": "application/x-www-form-urlencoded"})
        g = json.loads(body or "{}")
        err = g.get("error")
        step("Google accepts our client secret", err == "invalid_grant",
             f"google says {err!r}: {g.get('error_description', '')}")
        if err == "invalid_client":
            print("        >>> the human login leg WILL fail until the real "
                  "GOCSPX- secret is stored (scripts/set_oauth_secret.sh)")

    print("── 6 · post-Google leg (human sign-in stubbed, the rest is real) ──")
    key = secret("dmai-oauth-signing-key").encode()
    if not step("signing key readable", bool(key)):
        return _summary()

    def sign(payload: dict) -> str:
        b = b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        return f"{b}.{b64u(hmac.new(key, b.encode(), hashlib.sha256).digest())}"

    def mint(scope="openid email profile offline_access", cc=challenge):
        # Exactly what callback() mints once Google confirms the identity.
        return sign({"typ": "code", "sub": "dma@zennify.com", "ci": CIMD,
                     "ru": CLAUDE_RU, "cc": cc, "sc": scope,
                     "rs": base + "/mcp", "jti": b64u(os.urandom(9)),
                     "exp": int(time.time()) + 300})

    def token(form: dict):
        s, body, _ = http(base + "/token", "POST",
                          urllib.parse.urlencode(form).encode(),
                          {"Content-Type": "application/x-www-form-urlencoded"})
        try:
            return s, json.loads(body or "{}")
        except Exception:                                    # noqa: BLE001
            return s, {"raw": body[:200]}

    s, tok = token({"grant_type": "authorization_code", "code": mint(),
                    "redirect_uri": CLAUDE_RU, "client_id": CIMD,
                    "code_verifier": verifier})
    step("access_token issued", s == 200 and "access_token" in tok,
         f"http {s} {tok.get('error', '')}")
    step("refresh_token issued for offline_access", bool(tok.get("refresh_token")))
    at = tok.get("access_token", "")

    print("── 7 · the refusals ──")
    s, e = token({"grant_type": "authorization_code", "code": mint(),
                  "redirect_uri": CLAUDE_RU, "client_id": CIMD,
                  "code_verifier": "not-the-right-verifier"})
    step("wrong PKCE verifier refused", s != 200, f"http {s} {e.get('error', '')}")
    s, e = token({"grant_type": "authorization_code", "code": mint(),
                  "redirect_uri": "https://evil.example/steal",
                  "client_id": CIMD, "code_verifier": verifier})
    step("mismatched redirect_uri refused", s != 200, f"http {s} {e.get('error', '')}")
    s, e = token({"grant_type": "authorization_code",
                  "code": mint()[:-4] + "AAAA", "redirect_uri": CLAUDE_RU,
                  "client_id": CIMD, "code_verifier": verifier})
    step("tampered code refused", s != 200, f"http {s} {e.get('error', '')}")

    if not at:
        return _summary()

    print("── 8 · the whole point: drive the MCP with that token ──")
    s, init = mcp_call(base, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "e2e", "version": "1"}}, at)
    step("initialize", s == 200 and "result" in init, f"http {s}")
    s, tl = mcp_call(base, "tools/list", {}, at)
    tools = (tl.get("result") or {}).get("tools", [])
    step("tools/list answers", s == 200 and bool(tools), f"{len(tools)} tools")
    step("the full roster is advertised", len(tools) == 33, f"got {len(tools)}")
    for want in ("get_run_progress", "claim_run", "submit_page_payload",
                 "promote_run", "register_evidence", "get_memory_digest"):
        step(f"tool present: {want}", any(t.get("name") == want for t in tools))
    s, call = mcp_call(base, "tools/call", {
        "name": "get_run_progress", "arguments": {"run_id": PROBE_RUN}}, at)
    step("a real tool call answers", s == 200 and "result" in call, f"http {s}")

    print("── 9 · a forged bearer is refused ──")
    s, _ = mcp_call(base, "tools/list", {}, at[:-6] + "AAAAAA")
    step("tampered access token refused", s == 401, f"http {s}")
    s, _ = mcp_call(base, "tools/list", {}, "not.a.token")
    step("garbage bearer refused", s == 401, f"http {s}")

    print("── 10 · refresh rotation ──")
    if tok.get("refresh_token"):
        s, t2 = token({"grant_type": "refresh_token",
                       "refresh_token": tok["refresh_token"], "client_id": CIMD})
        step("refresh yields a token", s == 200 and "access_token" in t2, f"http {s}")
        step("the token actually rotated", t2.get("access_token") != at)
        if t2.get("access_token"):
            s, _ = mcp_call(base, "tools/list", {}, t2["access_token"])
            step("refreshed token drives /mcp", s == 200, f"http {s}")

    return _summary()


def _summary() -> int:
    print(f"\n  ══ {_ok} passed, {_fail} failed ══")
    if _failed:
        print("  failed:")
        for f in _failed:
            print(f"    - {f}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
