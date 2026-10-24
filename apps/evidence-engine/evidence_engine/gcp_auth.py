"""Calling a private Cloud Run backend from the engine.

The research backends run with `--no-allow-unauthenticated`, so every request
needs an ID token minted for the backend's URL, and SearXNG's door answers only
at `/searx-json/<path token>/search` (infra/evidence-engine/searxng/proxy.js);
anything else is a 404. Measured 2026-10-11 before the first live deploy: the
engine called `<SEARXNG_URL>/search` bare, which the door refuses, so the
deployed engine would have searched Parallel alone.

`MetadataIdTokenAuth` asks the Cloud Run metadata server for an ID token with
the backend's URL as audience and caches it short of its one-hour life. It
never logs or returns a token. Off Cloud Run (tests, a laptop) it is not
installed, and `searxng_base` keeps the bare URL for a local SearXNG.
"""
from __future__ import annotations

import time

import httpx

METADATA_URL = ("http://metadata.google.internal/computeMetadata/v1/instance/"
                "service-accounts/default/identity")
#: ID tokens live an hour; refresh well before.
TOKEN_TTL_S = 45 * 60


def searxng_base(url: str, path_token: str) -> str:
    """The base the engine's SearXNG client appends `/search` to."""
    url = (url or "").rstrip("/")
    return f"{url}/searx-json/{path_token}" if (url and path_token) else url


class MetadataIdTokenAuth(httpx.Auth):
    """httpx auth flow: `Authorization: Bearer <ID token for audience>`."""

    def __init__(self, audience: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 clock=time.monotonic):
        self.audience = audience.rstrip("/")
        self._transport = transport
        self._clock = clock
        self._token: str | None = None
        self._expires = 0.0

    async def _fresh(self) -> str:
        if self._token and self._clock() < self._expires:
            return self._token
        async with httpx.AsyncClient(transport=self._transport, timeout=5) as c:
            r = await c.get(METADATA_URL, params={"audience": self.audience, "format": "full"},
                            headers={"Metadata-Flavor": "Google"})
        r.raise_for_status()
        self._token = r.text.strip()
        self._expires = self._clock() + TOKEN_TTL_S
        return self._token

    async def async_auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {await self._fresh()}"
        response = yield request
        if response.status_code in (401, 403) and self._token:
            # a revoked or rotated identity: mint once more, then give up
            self._token = None
            request.headers["Authorization"] = f"Bearer {await self._fresh()}"
            yield request
