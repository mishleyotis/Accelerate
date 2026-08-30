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
     rejected" — or a CONTINUED session finds no mcp__* connector tool
     bound at all (bindings are made once at process start and never
     return mid-session; a session resumed after its budget reset comes
     back without one) -> run `mcp_raw.py revive --run <run_id>`, or
     bare `mcp_raw.py probe` when no run is in hand.
  2. REVIVE: OK -> the server is UP and a fresh identity minted. NOTHING
     SERVER-SIDE WAS LOST: identity re-mints per call from the key, and
     claims, staged pages and verdicts live in the connector's database,
     answering this session, the next one, or one thirty days out alike
     — the "lost" tools are a per-process BINDING, never the work. The
     broken layer is only this session's MCP client, which cannot be
     reloaded mid-session. STANDING AUTHORIZATION (owner, 2026-08-24,
     after continued sessions declared the tools "lost mid-session and
     unrecoverable" and abandoned unpromoted claims): when the binding
     is absent or dead, the server is UP, and this session holds — or
     held — the claim on an UNPROMOTED run, this bridge IS the
     production channel for that run: reads AND writes via
     `mcp_raw.py call`, each one an ordinary audited Bash tool call.
     Finish the run; do not declare the tools lost, do not abandon the
     claim. HAND OFF instead (resume bundles + memory pushed to Drive
     via drive_fetch, report, end — the next firing binds the stdio
     transport at session start and resumes, re-claiming after the
     lease lapses) ONLY when the session harness refuses the bridge
     itself (classifier-blocked credential minting — measured
     2026-08-20; one refused call is that measurement) or the budget is
     genuinely spent.
  3. REVIVE: IDENTITY_MISSING or SERVER_DOWN -> re-run
     bootstrap_session.sh (re-lands key + path token), revive again.
     Still failing = a real outage: same handoff, plus the exact HTTP
     status in the report — never fabricate, never force a submission.

Usage:
  mcp_raw.py probe                      # tools/list; prints the tool count
  mcp_raw.py revive [--run <run_id>]    # identity + server + run state,
                                        #   one verdict, exit 0 only on OK
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
    """One ladder, shared with run_gate and the doctor — env, then file,
    then Secret Manager. Three copies of this drifted to three different
    numbers of rungs, which is why it lives in gcp_token now."""
    return gcp_token.path_token()


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


def revive(run_id: str | None) -> int:
    """One verdict for a session whose MCP binding died or never bound.

    Checks the three layers a resumed session cannot see from inside —
    identity, server, run state — and prints what is banked so nothing
    already staged is produced twice. Read-only: the one tool it calls
    is get_run_progress.
    """
    key, source = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        print(f"REVIVE: IDENTITY_MISSING — {source}. Run "
              f"bootstrap_session.sh or set DMA_ROUTINE_SA_KEY_B64, then "
              f"revive again; still failing is a real outage: hand off.")
        return 1
    try:
        tools = rpc("tools/list").get("result", {}).get("tools", [])
    except SystemExit as e:
        print(f"REVIVE: IDENTITY_MISSING — {e}. Run bootstrap_session.sh, "
              f"then revive again.")
        return 1
    except urllib.error.HTTPError as e:
        print(f"REVIVE: SERVER_DOWN — HTTP {e.code} {e.reason}. Re-run "
              f"bootstrap_session.sh and revive again; still down is a real "
              f"outage: hand off with this exact status in the report.")
        return 1
    except Exception as e:                                   # noqa: BLE001
        print(f"REVIVE: SERVER_DOWN — {e}. Re-run bootstrap_session.sh and "
              f"revive again; still down is a real outage: hand off with "
              f"this exact error in the report.")
        return 1
    if not tools:
        print("REVIVE: SERVER_DOWN — tools/list answered with no tools.")
        return 1
    lines = [f"server UP ({len(tools)} tools), identity minted fresh "
             f"({source})"]
    if run_id:
        try:
            d = rpc("tools/call", {"name": "get_run_progress",
                                   "arguments": {"run_id": run_id}})
            content = d.get("result", {}).get("content", [])
            prog = json.loads(content[0]["text"]) if content else {}
            pages = prog.get("pages", {}) or {}
            staged = sorted(k for k, v in pages.items()
                            if (v or {}).get("status") != "missing")
            claim = prog.get("claim") or {}
            lines.append(
                f"run {run_id}: {len(staged)}/{len(pages) or 6} pages "
                f"present ({', '.join(staged) or 'none'}), "
                f"promotable={prog.get('promotable')}, claim "
                f"held_by={claim.get('held_by')} live={claim.get('live')} "
                f"expires_at={claim.get('expires_at')}")
        except Exception as e:                               # noqa: BLE001
            lines.append(f"run {run_id}: get_run_progress failed ({e}) — "
                         f"read it before producing anything")
    print("REVIVE: OK — " + "; ".join(lines))
    print("The MCP binding is per-process and will not return mid-session; "
          "nothing server-side was lost. For a claimed, UNPROMOTED run, "
          "production continues in THIS session through `mcp_raw.py call "
          "<tool> --args/--args-file` under the standing owner "
          "authorization (2026-08-24). Hand off only if the harness "
          "refuses the bridge itself or the budget is spent.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    p_r = sub.add_parser("revive")
    p_r.add_argument("--run", default=None)
    p_c = sub.add_parser("call")
    p_c.add_argument("tool")
    p_c.add_argument("--args", default=None)
    p_c.add_argument("--args-file", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "probe":
        return probe()
    if a.cmd == "revive":
        return revive(a.run)
    if a.args_file:
        args = json.loads(Path(a.args_file).read_text())
    elif a.args:
        args = json.loads(a.args)
    else:
        args = {}
    return call(a.tool, args)


if __name__ == "__main__":
    sys.exit(main())
