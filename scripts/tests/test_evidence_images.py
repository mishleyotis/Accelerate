"""The research-layer images are reproducible and proved before a release.

2026-10-11: the first approved evidence release failed at step 4 building
dmai-searxng. `FROM searxng/searxng:latest` had become Void Linux (no `apk`,
no bash, no curl), `mcp-searxng@0.11.3` had never been published, and
`supercorp/supergateway:uvx` had moved to 4.1.0 under fetch and edgar. These
tests keep each of those from recurring without docker; the CI job
`evidence-images` (image_smoke.sh) builds the images and probes each door.
"""
from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EE = ROOT / "infra" / "evidence-engine"
BACKENDS = ("searxng", "fetch", "edgar")


def test_every_backend_base_is_pinned_by_digest():
    for b in BACKENDS:
        froms = [ln.split()[1] for ln in (EE / b / "Dockerfile").read_text().splitlines()
                 if ln.startswith("FROM ")]
        assert froms, b
        for ref in froms:
            assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"{b}: {ref} is not digest-pinned"
            assert ":latest" not in ref and not ref.split("@")[0].endswith(":uvx"), f"{b}: {ref} floats"


def test_the_searxng_image_uses_no_package_manager_and_exact_npm_pins():
    df = (EE / "searxng" / "Dockerfile").read_text()
    run_lines = " ".join(ln for ln in df.splitlines() if not ln.lstrip().startswith("#"))
    for pm in ("apk add", "apt-get", "xbps-install"):
        assert pm not in run_lines, f"{pm}: the SearXNG base ships no package manager"
    pins = re.findall(r"\b(mcp-searxng|supergateway)@(\S+)", run_lines)
    assert {p for p, _ in pins} == {"mcp-searxng", "supergateway"}
    for pkg, ver in pins:
        assert re.fullmatch(r"\d+\.\d+\.\d+", ver), f"{pkg}@{ver} is not an exact version"


def test_the_searxng_entrypoint_is_posix_sh_on_busybox():
    ep = (EE / "searxng" / "entrypoint.sh").read_text()
    body = "\n".join(ln for ln in ep.splitlines() if not ln.lstrip().startswith("#"))
    assert ep.startswith("#!/bin/sh\n")
    for bashism in ("[[", "wait -n", "=(", "${GW_ARGS", "pipefail", "curl "):
        assert bashism not in body, f"{bashism!r} does not run on the image's busybox sh"
    assert "GRANIAN_HOST=127.0.0.1" in body, "SearXNG must bind loopback; granian ignores SEARXNG_BIND_ADDRESS"
    r = subprocess.run(["sh", "-n", str(EE / "searxng" / "entrypoint.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_ci_builds_and_probes_the_images_before_any_deploy():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    job = jobs["evidence-images"]
    assert "if" not in job, "the image job runs on every pull request, not only on release"
    assert any("image_smoke.sh" in (s.get("run") or "") for s in job["steps"])
    diag = [s for s in job["steps"] if "image_diag.sh" in (s.get("run") or "")]
    assert diag and diag[0].get("if") == "failure()", "the diagnostics run when the smoke fails, and only then"
    assert "evidence-images" in jobs["deploy"]["needs"]


# --- the probe itself, against an in-process door ---------------------------

#: a throwaway door segment, fresh per run
SEGMENT = secrets.token_hex(8)


def _door(tools: list[str], *, json_ok: bool = True):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            if self.path.startswith(f"/searx-json/{SEGMENT}/search") and json_ok:
                return self._send(200, json.dumps({"results": []}).encode())
            return self._send(404)

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            msg = json.loads(self.rfile.read(n) or b"{}")
            if self.path != f"/mcp-{SEGMENT}":
                return self._send(404)
            if "id" not in msg:
                return self._send(202)
            result = ({"tools": [{"name": t} for t in tools]} if msg["method"] == "tools/list"
                      else {"serverInfo": {"name": "fake"}})
            sse = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result})}\n\n"
            return self._send(200, sse.encode(), "text/event-stream")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _probe(kind, base, token=None):
    return subprocess.run([sys.executable, str(EE / "image_probe.py"), kind, base],
                          env={"PROBE_TOKEN": token or SEGMENT, "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=60)


def test_the_probe_passes_a_good_door_and_fails_a_wrong_token_or_missing_tool():
    four = ["searxng_web_search", "searxng_search_suggestions", "searxng_instance_info", "web_url_read"]
    srv, base = _door(four)
    try:
        ok = _probe("searxng", base)
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert "PASS searxng tools/list: 4 tool(s)" in ok.stdout and "FAIL" not in ok.stdout
        other = secrets.token_hex(8)
        bad = _probe("searxng", base, token=other)
        assert bad.returncode == 1 and "FAIL searxng tools/list" in bad.stdout
        assert other not in bad.stdout and SEGMENT not in ok.stdout, "the token is never printed"
    finally:
        srv.shutdown()
    srv, base = _door(four[:2], json_ok=False)
    try:
        r = _probe("searxng", base)
        assert r.returncode == 1
        assert "missing ['searxng_instance_info', 'web_url_read']" in r.stdout
        assert "FAIL searxng engine JSON door" in r.stdout
    finally:
        srv.shutdown()


def test_the_probe_holds_edgar_to_the_tools_the_plugin_binds():
    """Agents bind the SURFACED names (references/research_tool_surface.json);
    each maps to an upstream sec-edgar-mcp tool, and the image probe must
    find exactly those upstream tools."""
    sys.path.insert(0, str(EE))
    sys.path.insert(0, str(ROOT / "plugins" / "dma-insights" / "scripts"))
    import image_probe  # noqa: PLC0415
    import research_tool_surface as surface  # noqa: PLC0415
    bound = set()
    for f in (ROOT / "plugins" / "dma-insights" / "agents").rglob("*.md"):
        bound |= set(re.findall(r"mcp__plugin_dma-insights_edgar__(\w+)", f.read_text()))
    assert bound and {surface.upstream_of("edgar", n) for n in bound} == image_probe.TOOLS["edgar"]


def test_every_gateway_stdio_command_parses_as_sh():
    """Supergateway runs --stdio through `sh -c`. 2026-10-11: fetch's user
    agent carried an unquoted "(" and the server never started (image_diag.sh:
    `sh: syntax error: unexpected "("`, on both gateway bases)."""
    for b in ("fetch", "edgar"):
        ep = (EE / b / "entrypoint.sh").read_text()
        m = re.search(r'--stdio "([^"]+)"', ep)
        assert m, b
        r = subprocess.run(["sh", "-n", "-c", m.group(1)], capture_output=True, text=True)
        assert r.returncode == 0, f"{b}: {r.stderr.strip()}"
