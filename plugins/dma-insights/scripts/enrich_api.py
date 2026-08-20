#!/usr/bin/env python3
"""Enrichment services by API key — no claude.ai connector, no per-session grant.

Owner instruction, 2026-08-20: "same should apply to all other required
connectors … The tools should be availed by all connectors accordingly"
(Clay, Exa, Tavily, Explorium). claude.ai connectors authenticate
interactively and do not load in trigger-fired sessions — measured
repeatedly — so a routine that depends on them degrades every scheduled
run. This module is the dependable path, the same shape as the connector
and Drive access: each service's API key lives in Secret Manager, readable
by the dmai-routine service account, fetched at call time with an access
token minted from the key the container already holds. Works in every
container; rotation is a new secret version, no client update.

One-time setup per service (Cloud Shell; the key value never appears in a
chat or a repo):

    printf '%s' 'THE-API-KEY' | gcloud secrets versions add \
      dmai-<service>-api-key --project=digital-maturity-assessor --data-file=-

Secrets (already created, accessor already granted): dmai-exa-api-key ·
dmai-tavily-api-key · dmai-clay-api-key · dmai-explorium-api-key.

A service with no stored key is CONFIGURED ABSENT: `check` names it and the
exact command that fixes it, calls against it fail with that same naming,
and the enrichment ledger records the facet as not-run (MEM-0082 — honest
absence, never fabricated technographics). When a claude.ai connector for
the same service happens to be present in an interactive session, it may be
used instead; this module is the floor every session can rely on.

No key value is ever printed, logged, or written to disk.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gcp_token  # noqa: E402

PROJECT = "digital-maturity-assessor"
SM = "https://secretmanager.googleapis.com/v1"

SERVICES = {
    "exa": {
        "secret": "dmai-exa-api-key",
        "search_url": "https://api.exa.ai/search",
        "auth": ("x-api-key", "{key}"),
        "body": lambda q, n: {"query": q, "numResults": n,
                              "contents": {"text": {"maxCharacters": 1500}}},
    },
    "tavily": {
        "secret": "dmai-tavily-api-key",
        "search_url": "https://api.tavily.com/search",
        "auth": ("Authorization", "Bearer {key}"),
        "body": lambda q, n: {"query": q, "max_results": n,
                              "include_answer": False},
    },
    "clay": {
        "secret": "dmai-clay-api-key",
        "base": "https://api.clay.com",
        "auth": ("Authorization", "Bearer {key}"),
    },
    "explorium": {
        "secret": "dmai-explorium-api-key",
        "base": "https://api.explorium.ai",
        "auth": ("api_key", "{key}"),
    },
}


def _access_token() -> str:
    key, source = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({source})")
    tok = gcp_token.exchange(gcp_token.mint_assertion(
        key, {"scope": gcp_token.DEFAULT_SCOPE})).get("access_token", "")
    if not tok:
        raise SystemExit("could not mint a Secret Manager access token")
    return tok


def _secret(name: str, access: str) -> tuple:
    """(key_or_None, state). States: ok · empty (no version) · unshared ·
    error:<code>."""
    url = f"{SM}/projects/{PROJECT}/secrets/{name}/versions/latest:access"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)["payload"]["data"]
        return base64.b64decode(data).decode().strip(), "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "empty"          # secret exists, no version yet
        if e.code == 403:
            return None, "unshared"
        return None, f"error:{e.code}"


def _post(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _headers(service: str, key: str) -> dict:
    h, template = SERVICES[service]["auth"]
    return {h: template.format(key=key)}


def _key_for(service: str, access: str) -> str:
    key, state = _secret(SERVICES[service]["secret"], access)
    if key:
        return key
    fix = (f"printf '%s' 'THE-API-KEY' | gcloud secrets versions add "
           f"{SERVICES[service]['secret']} --project={PROJECT} --data-file=-")
    raise SystemExit(f"{service}: no API key stored ({state}) — add one "
                     f"with: {fix}")


def search(service: str, query: str, num: int = 5) -> dict:
    cfg = SERVICES[service]
    if "search_url" not in cfg:
        raise SystemExit(f"{service} has no generic search — use `call` "
                         f"with a documented endpoint path")
    access = _access_token()
    key = _key_for(service, access)
    return _post(cfg["search_url"], _headers(service, key),
                 cfg["body"](query, num))


def call(service: str, path: str, payload: dict) -> dict:
    cfg = SERVICES[service]
    base = cfg.get("base")
    if not base:
        raise SystemExit(f"{service} is search-only here — use `search`")
    if not path.startswith("/"):
        raise SystemExit("path must start with /")
    access = _access_token()
    key = _key_for(service, access)
    return _post(base + path, _headers(service, key), payload)


def check() -> int:
    """Preflight: which enrichment services this container can actually use.
    Missing keys are named with their fix; they do not fail the preflight —
    enrichment degrades honestly (MEM-0082), it does not block production."""
    access = _access_token()
    missing = []
    for name, cfg in SERVICES.items():
        key, state = _secret(cfg["secret"], access)
        if key:
            print(f"  {name}: configured ({cfg['secret']})")
        else:
            missing.append(name)
            print(f"  {name}: NOT configured — {state}; store the key with: "
                  f"printf '%s' 'THE-API-KEY' | gcloud secrets versions add "
                  f"{cfg['secret']} --project={PROJECT} --data-file=-")
    if missing:
        print(f"enrichment degraded for: {', '.join(missing)} — facets "
              f"depending on them record as not-run, never fabricated")
    else:
        print("all enrichment services configured")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p_s = sub.add_parser("search")
    p_s.add_argument("--service", required=True,
                     choices=[s for s in SERVICES if "search_url" in SERVICES[s]])
    p_s.add_argument("--query", required=True)
    p_s.add_argument("--num", type=int, default=5)
    p_c = sub.add_parser("call")
    p_c.add_argument("--service", required=True, choices=list(SERVICES))
    p_c.add_argument("--path", required=True)
    p_c.add_argument("--payload", default="{}")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return check()
    if a.cmd == "search":
        print(json.dumps(search(a.service, a.query, a.num), indent=1)[:8000])
        return 0
    if a.cmd == "call":
        print(json.dumps(call(a.service, a.path, json.loads(a.payload)),
                         indent=1)[:8000])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
