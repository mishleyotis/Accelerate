#!/usr/bin/env python3
"""stdio -> streamable-HTTP bridge for the DMA Insights connector.

Why this exists (measured 2026-08-20, T. Rowe Price production, 12:22Z):
the CLI's HTTP MCP client invokes headersHelper ONCE per connection and, on
the first 401 after that, falls back to OAuth Dynamic Client Registration —
which this connector rightly rejects — so a session loses every connector
tool roughly when its first ID token ages out, mid-run, unrecoverably.
Google ID tokens live ~1 hour; production runs live longer.

This proxy makes token age irrelevant: the CLI speaks stdio to this
process, and every outbound request carries headers minted at most
REFRESH_S seconds ago by the SAME mcp_auth_headers.sh rungs (gcloud, key
file, DMA_ROUTINE_SA_KEY_B64; path token by env/cache/Secret Manager). On
a 401 it re-mints once and retries; on a lost streamable-HTTP session it
replays initialize and retries once. There is no OAuth fallback because
stdio has no OAuth.

Wired by .claude-plugin/../.mcp.json:
  {"command": "python3", "args": [".../mcp_proxy.py", "<base_url>"]}

No token value is ever printed; stderr carries diagnostics only.
"""
from __future__ import annotations

import json
import subprocess
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFRESH_S = 45 * 60          # ID tokens live ~60 min; re-mint well before
TIMEOUT_S = 120

_state = {"headers": None, "minted": 0.0, "session_id": None,
          "init_params": None}


def _mint_headers() -> dict:
    try:
        out = subprocess.run(
            ["bash", str(HERE / "mcp_auth_headers.sh")],
            capture_output=True, text=True, timeout=60)
        hdrs = json.loads(out.stdout.strip() or "{}")
    except Exception as e:                                  # noqa: BLE001
        print(f"mcp_proxy: header mint failed: {e}", file=sys.stderr)
        hdrs = {}
    _state["headers"] = hdrs
    _state["minted"] = time.time()
    return hdrs


def _headers() -> dict:
    if (_state["headers"] is None
            or time.time() - _state["minted"] > REFRESH_S):
        _mint_headers()
    h = dict(_state["headers"] or {})
    h["Content-Type"] = "application/json"
    h["Accept"] = "application/json, text/event-stream"
    if _state["session_id"]:
        h["Mcp-Session-Id"] = _state["session_id"]
    return h


def _post(url: str, body: bytes, headers: dict):
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=TIMEOUT_S)


def _parse_payload(resp) -> list:
    """Streamable HTTP answers as raw JSON or as an SSE event stream; a 202
    (notification accepted) carries nothing."""
    sid = resp.headers.get("Mcp-Session-Id")
    if sid:
        _state["session_id"] = sid
    if resp.status == 202:
        return []
    raw = resp.read().decode("utf-8", errors="replace")
    ctype = resp.headers.get("Content-Type", "")
    out = []
    if "text/event-stream" in ctype:
        for line in raw.splitlines():
            if line.startswith("data: "):
                chunk = line[6:].strip()
                if chunk:
                    try:
                        out.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
    elif raw.strip():
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            print(f"mcp_proxy: unparseable response ({raw[:120]!r})",
                  file=sys.stderr)
    return out


def forward(url: str, msg: dict) -> list:
    body = json.dumps(msg).encode()
    if msg.get("method") == "initialize":
        _state["init_params"] = msg
        _state["session_id"] = None
    for attempt in (1, 2, 3):
        try:
            with _post(url, body, _headers()) as resp:
                return _parse_payload(resp)
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                print("mcp_proxy: 401 — re-minting headers", file=sys.stderr)
                _mint_headers()
                continue
            if e.code in (400, 404) and attempt < 3 \
                    and _state["init_params"] \
                    and msg.get("method") != "initialize":
                # streamable-HTTP session lost (instance restart): replay
                # initialize with fresh headers, then retry the message
                print(f"mcp_proxy: {e.code} — replaying initialize",
                      file=sys.stderr)
                _state["session_id"] = None
                try:
                    with _post(url, json.dumps(_state["init_params"]).encode(),
                               _headers()) as r2:
                        _parse_payload(r2)
                except Exception:                            # noqa: BLE001
                    pass
                continue
            err_id = msg.get("id")
            if err_id is None:
                return []
            return [{"jsonrpc": "2.0", "id": err_id,
                     "error": {"code": -32000,
                               "message": f"connector HTTP {e.code}: "
                                          f"{e.reason}"}}]
        except Exception as e:                               # noqa: BLE001
            err_id = msg.get("id")
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            if err_id is None:
                return []
            return [{"jsonrpc": "2.0", "id": err_id,
                     "error": {"code": -32000,
                               "message": f"connector unreachable: {e}"}}]
    return []


def main() -> int:
    # The arg comes from plugin config (${user_config.mcp_base_url}); when
    # that config never landed — a restored container, an install whose
    # --config did not persist (measured 2026-08-20: no mcp_base_url
    # anywhere in the config store, proxy handed the unresolved
    # placeholder, no tools bound) — the placeholder arrives VERBATIM.
    # Anything unresolved or empty falls back to the production URL, then
    # the DMA_MCP_HOST environment override, so the binding never depends
    # on install-time config being present.
    raw = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if not raw or "${" in raw:
        raw = os.environ.get(
            "DMA_MCP_HOST", "https://dmai-mcp-dukrne5v4a-uc.a.run.app")
    base = raw.rstrip("/")
    if not base.endswith("/mcp"):
        base = base + "/mcp"
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        for reply in forward(base, msg):
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
