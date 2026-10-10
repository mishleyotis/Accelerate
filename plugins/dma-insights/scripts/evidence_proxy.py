#!/usr/bin/env python3
"""stdio -> streamable-HTTP bridge for the research-layer services.

Reuses `mcp_proxy.py`'s forward loop unchanged (header refresh, 401 re-mint,
session replay) and swaps only the header minter: `evidence_auth_headers.sh`
with THIS service's audience and secret. The connector's own proxy and its
headers helper are not modified (brief §7.1).

    evidence_proxy.py <base_url> --secret <secret-name> [--segment]

`--segment`: the service's capability is a URL path segment (/mcp-<token>,
the Supergateway backends), so the token the helper returns under the
pseudo-header X-DMA-Path-Segment is placed in the path and never sent as a
header. Without it the token travels as X-DMA-Path-Token (the engine).

Unresolved `${user_config...}` placeholders fall back to the
DMA_<SERVICE>_HOST environment variable, then to the service's production
URL, exactly as mcp_proxy does. No token value is ever printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_proxy  # noqa: E402

#: Cloud Run URLs in one project share the project's hash suffix; the
#: defaults are what deploy-evidence.sh will produce for each new service.
DEFAULTS = {
    "dmai-evidence-path-token": "https://dmai-evidence-dukrne5v4a-uc.a.run.app",
    "dmai-searxng-path-token": "https://dmai-searxng-dukrne5v4a-uc.a.run.app",
    "dmai-fetch-path-token": "https://dmai-fetch-dukrne5v4a-uc.a.run.app",
    "dmai-edgar-path-token": "https://dmai-edgar-dukrne5v4a-uc.a.run.app",
}

_cfg = {"aud": "", "secret": "", "segment": False, "path_token": None}


def _mint_headers() -> dict:
    """The one function swapped: same shape as mcp_proxy._mint_headers."""
    mode = "segment" if _cfg["segment"] else "header"
    try:
        out = subprocess.run(
            ["bash", str(HERE / "evidence_auth_headers.sh"), _cfg["aud"], _cfg["secret"], mode],
            capture_output=True, text=True, timeout=60)
        hdrs = json.loads(out.stdout.strip() or "{}")
    except Exception as e:  # noqa: BLE001
        print(f"evidence_proxy: header mint failed: {e}", file=sys.stderr)
        hdrs = {}
    seg = hdrs.pop("X-DMA-Path-Segment", None)
    if seg:
        _cfg["path_token"] = seg
    mcp_proxy._state["headers"] = hdrs
    mcp_proxy._state["minted"] = time.time()
    return hdrs


def resolve_base(raw: str, secret: str) -> str:
    raw = (raw or "").strip()
    env_key = "DMA_" + secret.replace("-path-token", "").replace("dmai-", "").upper() + "_HOST"
    if not raw or "${" in raw:
        raw = os.environ.get(env_key, DEFAULTS.get(secret, ""))
    return raw.rstrip("/")


def endpoint(base: str) -> str:
    """The URL to POST to; in segment mode the token is part of it."""
    if _cfg["segment"]:
        if _cfg["path_token"] is None:
            _mint_headers()
        tok = _cfg["path_token"] or "missing"
        return f"{base}/mcp-{tok}"
    return base if base.endswith("/mcp") else base + "/mcp"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_url")
    ap.add_argument("--secret", required=True)
    ap.add_argument("--segment", action="store_true")
    a = ap.parse_args(argv)
    base = resolve_base(a.base_url, a.secret)
    _cfg.update(aud=base, secret=a.secret, segment=a.segment)
    mcp_proxy._mint_headers = _mint_headers           # the swap
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        for reply in mcp_proxy.forward(endpoint(base), msg):
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
