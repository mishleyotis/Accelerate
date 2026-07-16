#!/usr/bin/env python3
"""Static server for the standalone visual regression suite.

The standalone build is a self-contained HTML bundle with mock data
inlined — there's no real backend running during these tests. But the
React app still hits a few `/api/*` paths on mount:

  - `GET /api/v1/auth/me`              auth init hook on every page load
  - `GET /api/v1/notifications`        topbar bell badge
  - `GET /api/v1/dashboard`            home tile fetch

Vanilla `python3 -m http.server` returns **404** for every one of those,
which dumps a wall of red-flag-looking entries into the cloudbuild log:

  [WebServer] 127.0.0.1 - - [05/Jun/2026] code 404, message File not found
  [WebServer] 127.0.0.1 - - [05/Jun/2026] "GET /api/v1/auth/me HTTP/1.1" 404 -

The visual tests still pass (the app gracefully handles "no session" by
rendering the login screen), but the noise distracts deploy auditors
and looks like a real failure. This wrapper stubs `/api/v1/*` with the
exact responses the real backend would return:

  - `/api/v1/auth/me`         → 401 with `{"detail":"Not authenticated"}`
                                 (FastAPI's canonical "no session" reply,
                                  silently absorbed by `useCurrentUser`)
  - any other `/api/v1/*`     → 200 with `{}` (empty-state friendly)

Static files outside `/api/*` fall through to the normal directory
handler, so the standalone bundle's HTML + assets serve unchanged.

Run with:
  python3 dist-standalone-server.py 8081 dist-standalone

Or via the playwright.visual.standalone.config.ts webServer block.
"""
from __future__ import annotations

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class StubbingHandler(SimpleHTTPRequestHandler):
    def _stub_response(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — http.server contract
        if self.path == "/api/v1/auth/me" or self.path.startswith("/api/v1/auth/me?"):
            self._stub_response(401, b'{"detail":"Not authenticated"}')
            return
        if self.path.startswith("/api/v1/"):
            # Empty-shape 200 for everything else — every queries.ts
            # hook handles `{}` as an empty state without throwing.
            self._stub_response(200, b'{"items":[],"data":null}')
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/v1/"):
            self._stub_response(200, b'{"ok":true}')
            return
        self.send_response(405)
        self.end_headers()

    # Silence the "code 404, message File not found" prefix from
    # send_error — we never actually 404 on /api/* anymore, and the
    # static fallthrough handles missing-file logging itself.
    def log_error(self, fmt: str, *args: object) -> None:  # noqa: ANN401
        return


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    directory = sys.argv[2] if len(sys.argv) > 2 else "dist-standalone"
    if not os.path.isdir(directory):
        sys.stderr.write(f"::error::directory not found: {directory}\n")
        sys.exit(2)
    handler_cls = partial(StubbingHandler, directory=directory)
    # ThreadingHTTPServer so concurrent Playwright workers (the visual
    # suite runs `workers: 4` in CI) don't serialise on a single-threaded
    # server — each browser fetches the 2.4 MB bundle + brand assets, and
    # a blocking server would bottleneck the run and risk navigation
    # timeouts under load.
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    sys.stdout.write(
        f"Serving {directory}/ on 127.0.0.1:{port} "
        f"(stubbing /api/v1/*; static fallthrough for everything else)\n"
    )
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
