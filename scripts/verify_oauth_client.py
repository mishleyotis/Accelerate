#!/usr/bin/env python3
"""Prove the connector's Google OAuth client works — without a browser.

Google validates the client id, the client secret AND the redirect URI at its
token endpoint, so a deliberately invalid authorization code is enough to tell
the three apart:

    invalid_grant          the client and secret are RIGHT and the redirect
                           URI is REGISTERED; only the code was bad — this is
                           the PASS we are looking for
    invalid_client         the id/secret pair is wrong (a placeholder, a
                           rotated secret, a mismatched pair)
    redirect_uri_mismatch  the URI is not on the client's authorized list

Run it after storing the secret. It prints verdicts, never values.
"""
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

PROJECT = "digital-maturity-assessor"
SERVICE = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"
CALLBACK = f"{SERVICE}/oauth/callback"


def _gcloud() -> str:
    """gcloud is not always on PATH (measured: absent from the Bash tool's
    PATH on a machine where it is installed under /opt), so look where it
    actually lives before giving up."""
    from shutil import which
    found = which("gcloud")
    if found:
        return found
    import os
    for c in ("/opt/google-cloud-sdk/bin/gcloud",
              os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
              "/usr/local/google-cloud-sdk/bin/gcloud",
              "/snap/bin/gcloud"):
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit("gcloud not found. Install the SDK or run this where it lives.")


def _rest_secret(name: str) -> str:
    """Read the secret over REST when the gcloud CLI cannot.

    Measured 2026-08-20: behind a TLS-inspecting proxy the bundled gcloud
    fails certificate verification while ordinary Python does not, so a
    verifier that only knew how to shell out would be unusable exactly where
    it was needed. Uses application-default or the local gcloud credential.
    """
    import glob
    import os

    import google.auth
    import google.auth.transport.requests
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        # A machine with gcloud authenticated but no ADC still holds a usable
        # key under the legacy credential store; using it beats telling the
        # operator to run one more login they do not need.
        legacy = sorted(glob.glob(os.path.expanduser(
            "~/.config/gcloud/legacy_credentials/*/adc.json")))
        if legacy:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = legacy[0]
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    url = (f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/"
           f"secrets/{name}/versions/latest:access")
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {creds.token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return base64.b64decode(json.load(r)["payload"]["data"]).decode().strip()


def secret(name: str) -> str:
    try:
        out = subprocess.run(
            [_gcloud(), "secrets", "versions", "access", "latest",
             "--secret", name, "--project", PROJECT],
            capture_output=True, text=True, timeout=90)
        if out.returncode == 0:
            return out.stdout.strip()
        reason = out.stderr.strip()[:160]
    except Exception as e:                                   # noqa: BLE001
        reason = f"{type(e).__name__}: {e}"
    try:
        return _rest_secret(name)
    except Exception as e:                                   # noqa: BLE001
        sys.exit(f"could not read {name} via gcloud ({reason}) "
                 f"nor REST ({type(e).__name__}: {e})")


def probe(cid: str, csec: str, redirect_uri: str) -> tuple:
    body = urllib.parse.urlencode({
        "code": "deliberately-invalid-probe-code", "client_id": cid,
        "client_secret": csec, "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("error", "none"), ""
    except urllib.error.HTTPError as e:
        d = json.loads(e.read() or b"{}")
        return d.get("error", "?"), (d.get("error_description") or "")[:80]


def main() -> int:
    cid, csec = secret("dmai-oauth-client-id"), secret("dmai-oauth-client-secret")
    print(f"client id  : …{cid[-32:]}")
    print(f"secret     : {len(csec)} chars, prefix ok = {csec.startswith('GOCSPX-')}")
    if not csec.startswith("GOCSPX-"):
        print("\nFAIL: the stored secret is not a Google client secret.")
        print("Fix with: bash scripts/set_oauth_secret.sh")
        return 1
    err, desc = probe(cid, csec, CALLBACK)
    print(f"\nredirect URI tested: {CALLBACK}")
    if err == "invalid_grant":
        print("PASS: client id, client secret and redirect URI are all accepted "
              "by Google.\nThe connector is ready to add in claude.ai.")
        return 0
    if err == "invalid_client":
        print("FAIL: Google rejects the id/secret pair (invalid_client).")
        print("Fix with: bash scripts/set_oauth_secret.sh")
        return 1
    if err == "redirect_uri_mismatch":
        print("FAIL: the callback is not on the client's authorized list.")
        print(f"Add EXACTLY this to Authorized redirect URIs:\n  {CALLBACK}")
        return 1
    print(f"UNEXPECTED: {err} — {desc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
