#!/usr/bin/env python3
"""Probe one research-layer backend through its door, the way production does.

    image_probe.py searxng|fetch|edgar BASE_URL   (path token in $PROBE_TOKEN, never argv)

`fetch` / `edgar`: /healthz is 200, a wrong secret path is 404, and an MCP
`tools/list` at /mcp-<token> names the tools the plugin binds.
`searxng`: the same for its four tools, plus the engine's JSON door
/searx-json/<token>/search answers JSON with a `results` list.

Written 2026-10-11 after the first approved release failed building
dmai-searxng: the image had never been built before production. image_smoke.sh
builds every backend in CI and runs this against the running container, so an
upstream base or package change fails a pull request, not a release. Exit 0 on
pass; one line per check; the token is never printed. Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

TOOLS = {
    "searxng": {"searxng_web_search", "searxng_search_suggestions", "searxng_instance_info", "web_url_read"},
    "fetch": {"fetch"},
    # the fourteen upstream tools the plugin's tool surface exposes
    # (plugins/dma-insights/references/research_tool_surface.json; sec-edgar-mcp
    # serves 21 — the insider-trading reads are not exposed; read 2026-10-11)
    "edgar": {"get_cik_by_ticker", "get_company_info", "get_recent_filings",
              "get_filing_sections", "get_filing_content", "analyze_8k", "get_financials",
              "get_key_metrics", "get_segment_data", "compare_periods", "get_company_facts",
              "discover_company_metrics", "discover_xbrl_concepts", "get_xbrl_concepts"},
}
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _req(url: str, *, data: bytes | None = None, headers: dict | None = None, timeout: float = 30):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with NO_PROXY.open(r, timeout=timeout) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace")


def _rpc_payload(body: str) -> list[dict]:
    """JSON or SSE (`data: {...}` lines) -> the JSON-RPC messages it carries."""
    out = []
    for chunk in ([body] if body.lstrip().startswith(("{", "[")) else
                  [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]):
        try:
            d = json.loads(chunk)
        except ValueError:
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


def wait_healthy(base: str, budget_s: float = 120) -> bool:
    end = time.time() + budget_s
    while time.time() < end:
        try:
            if _req(base + "/healthz", timeout=5)[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(2)
    return False


#: a stateless gateway starts its stdio server per request; edgar's is a uvx
#: Python start, seconds on a cold runner
RPC_TIMEOUT_S = 120


def tools_list(base: str, token: str) -> set[str]:
    url = f"{base}/mcp-{token}"
    h = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "image-probe", "version": "1"}}}
    status, _, body = _req(url, data=json.dumps(init).encode(), headers=h, timeout=RPC_TIMEOUT_S)
    if status != 200:
        raise RuntimeError(f"initialize answered HTTP {status}")
    # the gateways run stateless (STATEFUL unset): each POST stands alone
    _req(url, data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(), headers=h,
         timeout=RPC_TIMEOUT_S)
    status, _, body = _req(url, data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode(),
                           headers=h, timeout=RPC_TIMEOUT_S)
    if status != 200:
        raise RuntimeError(f"tools/list answered HTTP {status}")
    for m in _rpc_payload(body):
        if m.get("id") == 2 and "result" in m:
            return {t["name"] for t in m["result"].get("tools", [])}
    raise RuntimeError("tools/list carried no result")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in TOOLS:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    kind, base = argv[0], argv[1].rstrip("/")
    token = os.environ.get("PROBE_TOKEN") or ""
    if not token:
        print("FAIL PROBE_TOKEN is not set", file=sys.stderr)
        return 2
    fails = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {kind} {name}{(': ' + detail) if detail else ''}")

    check("healthz", wait_healthy(base))
    check("a wrong path is 404", _req(base + "/mcp-not-the-token")[0] == 404)
    check("the bare search path is 404", _req(base + "/search?q=x")[0] == 404)
    try:
        names = tools_list(base, token)
        want = TOOLS[kind]
        check("tools/list", bool(names) and want <= names,
              f"{len(names)} tool(s)" + (f", missing {sorted(want - names)}" if want - names else ""))
    except (RuntimeError, OSError) as e:
        check("tools/list", False, str(e))
    if kind == "searxng":
        status, ctype, body = _req(f"{base}/searx-json/{token}/search?q=credit+union+digital+banking")
        try:
            ok = status == 200 and isinstance(json.loads(body).get("results"), list)
        except ValueError:
            ok = False
        check("engine JSON door", ok, f"HTTP {status} {ctype.split(';')[0]}")
        check("a wrong JSON-door token is 404", _req(f"{base}/searx-json/not-the-token/search?q=x")[0] == 404)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
