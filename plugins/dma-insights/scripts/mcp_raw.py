#!/usr/bin/env python3
"""Raw connector bridge — the self-heal path when the session's MCP client dies.

Measured 2026-08-20 (T. Rowe Price production, 12:22Z): the CLI's persistent
HTTP MCP client can lose its auth mid-session (expired embedded token -> the
client falls back to OAuth Dynamic Client Registration -> the connector
rightly rejects /register -> every tool call 401s for the rest of the
session, unrecoverably, while the SERVER is healthy the whole time).

This bridge is how a session keeps working: it speaks to the connector over
plain HTTPS, minting a FRESH ID token per call from the same identity rungs
as everything else (gcloud, /root/.dma/sa.json, DMA_ROUTINE_SA_KEY_B64) and
carrying the path token from its usual rungs. Nothing persists, so nothing
expires.

THE SELF-HEAL LADDER (also in the routine prompts):
  1. A connector tool call fails 401 / "Dynamic Client Registration
     rejected" -> run `mcp_raw.py probe`.
  2. probe OK -> the server is UP; the broken layer is the session's MCP
     client, which cannot be reloaded mid-session. This bridge is a
     DIAGNOSTIC and a last resort, not a production channel: session
     harnesses may classifier-block direct credential-minting calls
     (measured 2026-08-20), and writes through it bypass the harness's
     audited tool path. HAND OFF instead: write the vetter verdict,
     per-section status and what remains into the client memory file, push
     it to Drive via drive_fetch, end the firing with the report — the
     next firing binds the 0.6.7 stdio transport at session start
     (ordinary audited tool calls) and resumes from the memory file,
     re-claiming after the lease lapses. Reads here for diagnosis are
     fine; WRITE actions only with the owner's explicit re-affirmation.
  3. probe FAILS -> re-run bootstrap_session.sh (re-lands key + path
     token), probe again. Still failing = a real outage: same handoff,
     plus the exact HTTP status in the report — never fabricate, never
     force a submission.

Usage:
  mcp_raw.py probe                      # tools/list; prints the tool count
  mcp_raw.py call <tool> --args '{"run_id": "..."}'
  mcp_raw.py call <tool> --args-file /tmp/payload.json   # big payloads
Result JSON on stdout; diagnostics on stderr; exit 0 only on success.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gcp_token  # noqa: E402

MCP = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"
PATHTOK_FILE = Path("/root/.dma/pathtok")


def _idt() -> str:
    key, source = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({source}) — run "
                         f"bootstrap_session.sh or set DMA_ROUTINE_SA_KEY_B64")
    tok = gcp_token.exchange(gcp_token.mint_assertion(
        key, {"target_audience": MCP})).get("id_token", "")
    if not tok:
        raise SystemExit("could not mint an ID token")
    return tok


def _pathtok() -> str:
    import os
    env = os.environ.get("DMA_MCP_PATH_TOKEN", "").strip()
    if env:
        return env
    if PATHTOK_FILE.is_file():
        return PATHTOK_FILE.read_text().strip()
    raise SystemExit(f"no connector path token at {PATHTOK_FILE} — "
                     f"bootstrap_session.sh lands it")


def rpc(method: str, params: dict | None = None) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       **({"params": params} if params is not None else {})
                       }).encode()
    req = urllib.request.Request(f"{MCP}/mcp", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {_idt()}")
    req.add_header("X-DMA-Path-Token", _pathtok())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
    m = re.search(r"data: (\{.*\})", raw)
    return json.loads(m.group(1) if m else raw)


def call(tool: str, args: dict) -> int:
    d = rpc("tools/call", {"name": tool, "arguments": args})
    if "error" in d:
        print(json.dumps(d["error"]), file=sys.stderr)
        return 1
    content = d.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        print(content[0]["text"])
    else:
        print(json.dumps(d.get("result", d)))
    return 1 if d.get("result", {}).get("isError") else 0


def probe() -> int:
    d = rpc("tools/list")
    tools = d.get("result", {}).get("tools", [])
    print(f"connector UP — {len(tools)} tools")
    return 0 if tools else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    p_c = sub.add_parser("call")
    p_c.add_argument("tool")
    p_c.add_argument("--args", default=None)
    p_c.add_argument("--args-file", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "probe":
        return probe()
    if a.args_file:
        args = json.loads(Path(a.args_file).read_text())
    elif a.args:
        args = json.loads(a.args)
    else:
        args = {}
    return call(a.tool, args)


if __name__ == "__main__":
    sys.exit(main())
