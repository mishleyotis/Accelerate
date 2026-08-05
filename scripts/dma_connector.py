"""Thin client for the deployed DMA Insights MCP connector (streamable HTTP,
stateless). This is transport only — the connector is the sole writer of
serving content (charter invariant 2); nothing here bypasses its validation,
gates or atomic promote. A scheduled synthesis session (the app-scheduled
Cowork counterpart, per the build charter) uses this to reach the same 12
tools a native connector would expose.

usage:
    python3 scripts/dma_connector.py <tool> '<json-args>'
    from scripts.dma_connector import call
    call("get_run_progress", run_id=...)

The capability-path token is read from Secret Manager at call time (never
committed, never echoed); the URL rotates when the secret rotates.
"""
import json
import os
import subprocess
import sys
import urllib.request

_GCLOUD = os.environ.get("GCLOUD_BIN", "gcloud")
_MCP_HOST = os.environ.get(
    "DMA_MCP_HOST", "https://dmai-mcp-306195530103.us-central1.run.app")
_PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
_URL = None


def _url():
    global _URL
    if _URL is None:
        tok = os.environ.get("MCP_PATH_TOKEN")
        if not tok:
            tok = subprocess.run(
                [_GCLOUD, "secrets", "versions", "access", "latest",
                 "--secret=dmai-mcp-path-token", f"--project={_PROJECT}"],
                capture_output=True, text=True,
                env={**os.environ, "CLOUDSDK_AUTH_ACCESS_TOKEN": ""},
            ).stdout.strip()
        _URL = f"{_MCP_HOST}/mcp/{tok}"
    return _URL


def _rpc(method, params, rid=1):
    req = urllib.request.Request(
        _url(), data=json.dumps({"jsonrpc": "2.0", "id": rid,
                                 "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=900) as r:
        body = r.read().decode()
    if body.startswith("event:") or "\ndata:" in body or body.startswith("data:"):
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[5:].strip()
                break
    return json.loads(body)


def call(tool, **arguments):
    out = _rpc("tools/call", {"name": tool, "arguments": arguments})
    if "error" in out:
        raise RuntimeError(out["error"])
    res = out["result"]
    if res.get("isError"):
        raise RuntimeError(res["content"][0]["text"][:2000])
    for c in res.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return c["text"]
    return res.get("structuredContent")


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(tool, **args), indent=2, default=str))
