"""DMA Insights Clay relay — Cloud Functions Gen2 HMAC-signing proxy.

Clay sends webhook events to this Function (`/`); the Function signs the
body with the shared secret (`dma-insights-clay-webhook-secret`) and
forwards it to the backend's `/api/v1/clay/webhook` endpoint. The
backend's Clay client fails-closed when the signature is invalid (per
ADR 0010) so this relay is the only Clay-authorized entry point.

Deploy via DEPLOYMENT.md §14c. The deploy step copies this directory
to `/tmp/clay-relay` (or any cwd) and invokes
`gcloud functions deploy dma-insights-clay-relay --gen2 ...`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import urllib.error
import urllib.request

import functions_framework
from google.cloud import secretmanager

_CACHE: dict[str, bytes] = {}


def _secret(name: str) -> bytes:
    if name in _CACHE:
        return _CACHE[name]
    sm = secretmanager.SecretManagerServiceClient()
    project = os.environ["GCP_PROJECT"]
    v = sm.access_secret_version(
        name=f"projects/{project}/secrets/{name}/versions/latest"
    ).payload.data
    _CACHE[name] = v
    return v


@functions_framework.http
def relay(request):
    body = request.get_data() or b""
    secret = _secret("dma-insights-clay-webhook-secret")
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    backend = os.environ["DMA_BACKEND_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{backend}/api/v1/clay/webhook",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Clay-Signature": sig},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return ("", r.status, dict(r.headers))
    except urllib.error.HTTPError as e:
        return (e.read().decode(), e.code)
