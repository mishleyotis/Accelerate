#!/usr/bin/env python3
"""The evidence engine over Bash — for a lane that binds no MCP server.

Lean headless lanes run `claude -p --strict-mcp-config --setting-sources ""`
(`scripts/agent_run.py lean_command`): no MCP server at all, so the plugin's
`evidence` server is not in their tool list. This client speaks the same
streamable-HTTP JSON-RPC the proxy speaks, mints the same headers through
`scripts/evidence_auth_headers.sh` (never printing them), and gives
`engine.cli evidence-brief` its answer. The session path and the Bash path
reach ONE engine; a card is the same card either way.

    python3 -m engine.cli evidence-brief --run R --root ROOT \\
        --legal-name 'Example Federal Credit Union' --domain example-fcu.test \\
        --question 'How many members does it serve?' --facet value --json

No workbook write happens here (no lock is taken): the output is the cards
and, per card, the exact `evidence` line a lane puts in its batch file —
plus the `search` line that logs the engine call with `--tool evidence_engine`,
which is what the floors gate counts as a connector search.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or ENGINE_DIR.parents[2])
SECRET = "dmai-evidence-path-token"
DEFAULT_BASE = "https://dmai-evidence-dukrne5v4a-uc.a.run.app"
TIMEOUT_S = 180


def base_url() -> str:
    return (os.environ.get("DMA_EVIDENCE_HOST") or DEFAULT_BASE).rstrip("/")


def mint_headers(aud: str) -> dict:
    helper = PLUGIN_ROOT / "scripts" / "evidence_auth_headers.sh"
    try:
        out = subprocess.run(["bash", str(helper), aud, SECRET, "header"],
                             capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout.strip() or "{}")
    except Exception as exc:  # noqa: BLE001
        print(f"evidence_client: header mint failed: {exc}", file=sys.stderr)
        return {}


def _post(url: str, body: dict, headers: dict, opener=None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    for k, v in headers.items():
        req.add_header(k, v)
    open_ = opener or urllib.request.urlopen
    with open_(req, timeout=TIMEOUT_S) as r:
        raw = r.read().decode("utf-8", errors="replace")
    if "text/event-stream" in (getattr(r, "headers", {}).get("Content-Type", "") if hasattr(r, "headers") else ""):
        raw = [l[6:] for l in raw.splitlines() if l.startswith("data: ")][-1]
    return json.loads(raw) if raw.strip() else {}


def call(tool: str, arguments: dict, *, base: str | None = None, headers: dict | None = None,
         opener=None) -> dict:
    """One `tools/call`; returns the tool's structured result (or {"error"})."""
    base = (base or base_url()).rstrip("/")
    url = base if base.endswith("/mcp") else base + "/mcp"
    hdrs = headers if headers is not None else mint_headers(base)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "engine.cli evidence-brief", "version": "1"}}}
    try:
        _post(url, init, hdrs, opener)
        out = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": tool, "arguments": arguments}}, hdrs, opener)
    except urllib.error.HTTPError as e:
        return {"error": f"evidence engine HTTP {e.code} at {url.split('/mcp')[0]} — "
                         f"{'the capability token or audience is wrong' if e.code in (401, 403, 404) else e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"evidence engine unreachable: {type(e).__name__}: {str(e)[:120]}"}
    if "error" in out:
        return {"error": out["error"]}
    res = out.get("result") or {}
    if res.get("structuredContent"):
        sc = res["structuredContent"]
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    for c in res.get("content") or []:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return {"text": c["text"]}
    return res


def evidence_line(card: dict, subcaps: list[str], actor: str | None = None) -> list[str]:
    """The exact `evidence` batch line for a card's item (contract: a card's
    item IS the engine.cli evidence flag set), as argv tokens."""
    item = card["item"]
    argv = ["evidence", "--source", item["source_name"], "--url", item["source_url"],
            "--tier", item["tier"], "--excerpt", item["excerpt"],
            "--claim-type", item["claim_type"], "--origin", "public"]
    if item.get("published_date"):
        argv += ["--published", item["published_date"]]
    for s in subcaps:
        argv += ["--subcap", s]
    if actor:
        argv += ["--actor", actor]
    return argv


def search_line(question: str, facet: str | None, subcaps: list[str], hits: int, kept: int) -> list[str]:
    argv = ["search", "--query", question, "--tool", "evidence_engine", "--hits", str(hits), "--kept", str(kept)]
    if facet:
        argv += ["--facet", facet]
    for s in subcaps:
        argv += ["--subcap", s]
    return argv


def brief(*, run_id: str, legal_name: str, domains: list[str], questions: list[str],
          facet: str | None = None, sub_vertical: str | None = None, subcaps: list[str] | None = None,
          max_cards: int = 8, token_budget: int = 2400, reference_date: str | None = None,
          aliases: list[str] | None = None, charter: str | None = None, cik: str | None = None,
          actor: str | None = None, base: str | None = None, headers: dict | None = None,
          opener=None) -> dict:
    args = {"run_id": run_id, "entity": {"legal_name": legal_name, "domains": domains,
                                         "aliases": aliases or [], "charter": charter, "cik": cik},
            "questions": questions, "sub_vertical": sub_vertical, "facet": facet,
            "subcap_labels": list(subcaps or []), "max_cards": max_cards,
            "token_budget": token_budget, "provenance": "standard", "reference_date": reference_date}
    out = call("research_brief", args, base=base, headers=headers, opener=opener)
    if "error" in out or out.get("needs_spend_approval"):
        return out
    cells = list(subcaps or [])
    out["batch_lines"] = [search_line(" ".join(questions), facet, cells,
                                      out.get("search", {}).get("hits", 0), len(out.get("cards", [])))]
    out["batch_lines"] += [evidence_line(c, cells, actor) for c in out.get("cards", [])]
    return out
