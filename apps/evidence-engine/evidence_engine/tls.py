"""One trust store for every outbound TLS connection the engine makes.

Measured 2026-10-11 in a proxied container: with SSL_CERT_FILE pointing at
the proxy's CA bundle, OpenSSL drops the system roots, and the moment the
proxy tunnels instead of terminating TLS every fetch fails with
"unable to get local issuer certificate" — the whole slice, the Parallel
client too. The engine therefore verifies against certifi's roots, the
platform's default store AND whatever bundle the environment names
(SSL_CERT_FILE, REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE), so a terminated and a
tunnelled connection both verify. Verification is never disabled.
"""
from __future__ import annotations

import os
import ssl
from functools import lru_cache

_ENV_BUNDLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


@lru_cache(maxsize=1)
def trust_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi  # noqa: WPS433 — optional; the platform store stands without it
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        pass
    try:
        ctx.load_default_certs()
    except Exception:  # noqa: BLE001
        pass
    for var in _ENV_BUNDLES:
        path = os.environ.get(var)
        if path and os.path.isfile(path):
            try:
                ctx.load_verify_locations(cafile=path)
            except (ssl.SSLError, OSError):
                pass
    return ctx


def reset() -> None:
    """Tests: re-read the environment."""
    trust_context.cache_clear()
