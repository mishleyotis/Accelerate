#!/usr/bin/env python3
"""Doctor rows for the research layer: is each of the six connectors
declared, reachable, and serving tools? (brief §5F "Docs and doctor")

Verdicts, by the brief's rule:
  * a raw fallback (searxng, fetch, edgar, parallel, alphaxiv) that is
    missing or unreachable is a WARNING — the engine is the path;
  * the evidence engine missing or unreachable is a WARNING while a working
    search fallback exists (searxng or parallel reachable, or Exa/Tavily in
    the session's connector baseline), and a BLOCKER (fail) when none does.

Probing is read-only: one `initialize` POST per server. Credentials are
minted by `evidence_auth_headers.sh` (never printed); an anonymous `http`
server is probed bare. Under --no-probe only the declaration rows run.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent

RESEARCH_SERVERS = ("evidence", "searxng", "fetch", "edgar", "parallel", "alphaxiv")
PRIMARY = "evidence"
SEARCH_FALLBACKS = ("searxng", "parallel")
SESSION_SEARCH_FAMILIES = ("exa", "tavily")

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "dma-insights doctor", "version": "0"}}}


def declared(plugin_root: Path = PLUGIN) -> dict:
    try:
        return json.loads((plugin_root / ".mcp.json").read_text()).get("mcpServers") or {}
    except (OSError, ValueError):
        return {}


def _check(name, ok, detail, fix="", warn=False):
    return {"check": name, "ok": bool(ok), "detail": detail, "fix": fix, "warn": warn}


def _secret_and_mode(args: list) -> tuple[str | None, str]:
    secret = args[args.index("--secret") + 1] if "--secret" in args else None
    return secret, ("segment" if "--segment" in args else "header")


def _headers(aud: str, secret: str, mode: str) -> dict:
    try:
        out = subprocess.run(["bash", str(HERE / "evidence_auth_headers.sh"), aud, secret, mode],
                             capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout.strip() or "{}")
    except Exception:  # noqa: BLE001
        return {}


def probe(url: str, headers: dict, timeout: float = 10.0) -> tuple[int | None, str]:
    """(status, note) for one initialize POST; tokens never appear in `note`."""
    req = urllib.request.Request(url, data=json.dumps(INIT).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(4000).decode("utf-8", errors="replace")
            name = ""
            try:
                j = json.loads(body if not body.startswith("event") else body.split("data: ", 1)[1].splitlines()[0])
                name = ((j.get("result") or {}).get("serverInfo") or {}).get("name", "")
            except Exception:  # noqa: BLE001
                pass
            return r.status, f"initialize OK{(' — ' + name) if name else ''}"
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:80]}"


def resolve_url(server: str, spec: dict) -> tuple[str | None, dict]:
    """(endpoint, headers) for a probe, or (None, {}) when it cannot be built."""
    if spec.get("type") == "http" and spec.get("url"):
        return spec["url"], {}
    args = list(spec.get("args") or [])
    secret, mode = _secret_and_mode(args)
    if not secret:
        return None, {}
    sys.path.insert(0, str(HERE))
    import evidence_proxy  # noqa: WPS433
    raw = next((a for a in args if a.startswith("http") or "${" in a), "")
    base = evidence_proxy.resolve_base(raw, secret)
    hdrs = _headers(base, secret, mode)
    if mode == "segment":
        seg = hdrs.pop("X-DMA-Path-Segment", None)
        if not seg:
            return None, {}
        return f"{base}/mcp-{seg}", hdrs
    return f"{base}/mcp", hdrs


def checks(*, probe_network: bool, baseline_families: set[str] | None = None,
           plugin_root: Path = PLUGIN, prober=probe) -> list[dict]:
    rows = []
    servers = declared(plugin_root)
    reachable: dict[str, bool] = {}
    for s in RESEARCH_SERVERS:
        name = f"research layer: {s}"
        spec = servers.get(s)
        if not spec:
            rows.append(_check(name, s != PRIMARY,
                               "not declared in .mcp.json",
                               "declare it in plugins/dma-insights/.mcp.json", warn=(s != PRIMARY)))
            reachable[s] = False
            continue
        if not probe_network:
            rows.append(_check(name, True, "declared; SKIPPED probe (--no-probe)"))
            continue
        url, hdrs = resolve_url(s, spec)
        if not url:
            rows.append(_check(name, s != PRIMARY,
                               "declared, but no capability token could be obtained (env, cache or Secret "
                               "Manager) — the service may not be deployed yet (Phase E)",
                               "deploy the research layer (infra/evidence-engine/deploy-evidence.sh) and "
                               "grant the identity secretAccessor on its token", warn=(s != PRIMARY)))
            reachable[s] = False
            continue
        status, note = prober(url, hdrs)
        ok = status == 200 or (s == "alphaxiv" and status == 401)
        reachable[s] = bool(ok)
        detail = f"{note} (token value not shown)" if hdrs else note
        if s == "alphaxiv" and status == 401:
            detail += " — reachable; OAuth is per user, sign in from the session to list its tools"
        rows.append(_check(name, True if ok else s != PRIMARY, detail,
                           "" if ok else "check the deploy and the invoker grant; a raw fallback down is a "
                                         "warning, the engine down is a stop only without a search fallback",
                           warn=not ok and s != PRIMARY))
    if probe_network and PRIMARY in servers and not reachable.get(PRIMARY, False):
        fallback = [s for s in SEARCH_FALLBACKS if reachable.get(s)] + \
                   [f for f in SESSION_SEARCH_FAMILIES if f in (baseline_families or set())]
        idx = next(i for i, r in enumerate(rows) if r["check"] == f"research layer: {PRIMARY}")
        if fallback:
            rows[idx]["ok"], rows[idx]["warn"] = True, True
            rows[idx]["detail"] += f" — WARNING: engine unreachable, search fallback present ({', '.join(fallback)})"
        else:
            rows[idx]["ok"], rows[idx]["warn"] = False, False
            rows[idx]["detail"] += " — BLOCKER: engine unreachable and no working search fallback"
    return rows


if __name__ == "__main__":
    for r in checks(probe_network="--no-probe" not in sys.argv):
        flag = "ok " if r["ok"] else "FAIL"
        if r["warn"]:
            flag = "warn"
        print(f"{flag:4s} {r['check']}: {r['detail']}")
