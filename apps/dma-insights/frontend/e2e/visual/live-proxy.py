"""Same-origin static+API proxy for live-backend visual capture.

Serves the production Vite `dist/` build and reverse-proxies every
`/api/*`, `/healthz`, `/readyz` request to the uvicorn backend on :8000,
so the relative-URL production bundle talks to the live Postgres-backed
API on a single origin (cookies + SameSite=lax intact). Hash routing
means the browser only ever fetches `/` + assets, so the static side is
a plain file server with index.html fallback.

Usage:  python e2e/visual/live-proxy.py <listen_port> <dist_dir> <backend_port>
"""
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
DIST = Path(sys.argv[2] if len(sys.argv) > 2 else "dist").resolve()
BACKEND = f"http://127.0.0.1:{sys.argv[3] if len(sys.argv) > 3 else '8000'}"

_PROXY_PREFIXES = ("/api/", "/healthz", "/readyz", "/metrics")
_TYPES = {
    ".html": "text/html", ".js": "application/javascript",
    ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".woff2": "font/woff2", ".woff": "font/woff",
    ".ico": "image/x-icon", ".map": "application/json",
}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        url = BACKEND + self.path
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() in ("host", "content-length", "connection"):
                continue
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in ("transfer-encoding", "connection", "content-length"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() in ("transfer-encoding", "connection", "content-length"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # noqa: BLE001
            self.send_error(502, f"proxy error: {e}")

    def _serve_static(self) -> None:
        rel = self.path.split("?", 1)[0].lstrip("/")
        fp = (DIST / rel).resolve()
        if not str(fp).startswith(str(DIST)) or not fp.is_file():
            fp = DIST / "index.html"  # SPA fallback
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _TYPES.get(fp.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith(_PROXY_PREFIXES):
            self._proxy("GET")
        else:
            self._serve_static()

    def do_POST(self):
        self._proxy("POST")

    def do_PUT(self):
        self._proxy("PUT")

    def do_PATCH(self):
        self._proxy("PATCH")

    def do_DELETE(self):
        self._proxy("DELETE")


if __name__ == "__main__":
    print(f"live-proxy: :{PORT} -> static {DIST}  +  /api -> {BACKEND}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
