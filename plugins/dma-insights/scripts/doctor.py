#!/usr/bin/env python3
"""Is this install actually able to do the work? Checked, not assumed.

Installing the plugin is five things that fail independently and look the same
from the outside — the connector's tools are simply absent, and "absent"
carries no reason:

  1. the plugin is enabled and its components loaded
  2. `mcp_path_token` is set, so the capability URL resolves to a connector
  3. a Google identity token can be minted, so Cloud Run lets the call through
  4. the token's AUDIENCE matches the URL being called
  5. the deployment actually ENFORCES that token

(4) hides. The audience is baked into the auth helper's default while the URL
comes from `user_config.mcp_base_url`, so pointing the plugin at a different
deployment silently mints a token for the wrong service and every call returns
403 — which reads as a permissions problem, not a configuration one.
`DMA_MCP_HOST` is what reconciles them, and this says so by name.

(5) hid worse, and is why it is checked here at all: checks 1-4 each measure
that a credential EXISTS, and a green row on all four is consistent with a
service that accepts anonymous calls. That was the real state of `dmai-mcp`
until 2026-08-16. See `classify_enforcement`.

    python doctor.py                 # human
    python doctor.py --json

Exit 0 when every check passes, 1 otherwise. Prints no token, ever: each check
reports whether a credential could be obtained, never what it was.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
DEFAULT_AUD = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"


def _gcloud() -> str | None:
    found = shutil.which("gcloud")
    if found:
        return found
    for c in (f"{os.environ.get('HOME','')}/google-cloud-sdk/bin/gcloud",
              "/root/google-cloud-sdk/bin/gcloud",
              "/usr/local/google-cloud-sdk/bin/gcloud",
              "/opt/google-cloud-sdk/bin/gcloud"):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


#: `<svc>-<hash>-<region2>.a.run.app` and `<svc>-<projnum>.<region>.run.app`
#: are the two URLs Cloud Run gives one service.
_RUN_HOST = (re.compile(r"^(?P<svc>.+)-[a-z0-9]+-[a-z]{2}\.a\.run\.app$"),
             re.compile(r"^(?P<svc>.+)-\d+\.[a-z0-9-]+\.run\.app$"))


def _cloud_run_service(host: str) -> str | None:
    """The service a Cloud Run hostname names, in either URL form."""
    for pattern in _RUN_HOST:
        m = pattern.match(host or "")
        if m:
            return m.group("svc")
    return None


def _check(name, ok, detail, fix=""):
    return {"check": name, "ok": bool(ok), "detail": detail, "fix": fix}


def classify_enforcement(status: int | None, error: str = "") -> dict:
    """Does Cloud Run actually REJECT a call carrying no identity?

    THE CHECK THIS FILE WAS MISSING, and the reason it is worth its own
    function. Until 2026-08-16 `dmai-mcp` granted `roles/run.invoker` to
    `allUsers`: the plugin minted an identity token on every connection, sent
    it, and nothing on the other side ever looked at it. Every check above
    passed — a token *minted*, its audience *matched* — because each measures
    that a credential EXISTS, and none measured that anything ENFORCES it.
    Authentication rested entirely on a 32-character path token in a URL, on
    a service with ingress `all`. `dmai-api` and `dmai-web` were locked down
    correctly; the connector, the only component permitted to write serving
    content, was the one that was open.

    The probe needs NO SECRET, which is what makes it safe to ship. Send an
    unauthenticated POST to a deliberately bogus path token and read where
    the request died:

        403 / 401  IAM rejected it before routing        -> enforced
        404        it reached the application, which did
                   not recognise the path                -> service is PUBLIC

    A 404 here is the finding. It means anyone who learns the path token can
    call the connector.
    """
    if status is None:
        return _check(
            "connector rejects an unauthenticated call", False,
            f"could not reach the connector: {error[:120]}",
            "check the base URL and network egress; an unreachable connector "
            "is not evidence that it is protected")
    if status in (401, 403):
        return _check(
            "connector rejects an unauthenticated call", True,
            f"HTTP {status} — IAM rejected it before the request was routed")
    if status == 404:
        return _check(
            "connector rejects an unauthenticated call", False,
            f"HTTP {status} — an ANONYMOUS request reached the application. "
            "The service is public: the identity token is minted, sent, and "
            "never checked, so the path token is the only thing protecting it",
            "remove the public grant, after granting the principals that must "
            "keep working:\n"
            "         gcloud run services add-iam-policy-binding dmai-mcp "
            "--member=domain:YOURDOMAIN --role=roles/run.invoker …\n"
            "         gcloud run services remove-iam-policy-binding dmai-mcp "
            "--member=allUsers --role=roles/run.invoker …")
    return _check(
        "connector rejects an unauthenticated call", False,
        f"HTTP {status} — unexpected; neither an IAM rejection (401/403) nor "
        "the application's own not-found (404), so what enforced it is unclear",
        "investigate before trusting this deployment")


def enforcement_check(base_url: str | None, timeout: float = 10.0) -> dict:
    """Run the token-free enforcement probe against `base_url`."""
    if not base_url:
        return _check(
            "connector rejects an unauthenticated call", True,
            "not probed (no --base-url given)",
            "pass --base-url $(the plugin's mcp_base_url) to check this")
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        base_url.rstrip("/") + "/mcp/probe-no-such-path-token",
        data=b"{}", method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return classify_enforcement(resp.status)
    except urllib.error.HTTPError as exc:
        return classify_enforcement(exc.code)
    except Exception as exc:  # network, DNS, TLS
        return classify_enforcement(None, str(exc))


def audience_check(aud: str, base_url: str | None) -> dict:
    """Does the token's audience name the service the URL calls?

    A separate function because this is the check that can cry wolf, and a
    check nothing can import is a check nobody re-examines. COMPARE THE
    SERVICE, NOT THE HOSTNAME: Cloud Run gives one service two URLs —
    `<svc>-<hash>-<region2>.a.run.app` and `<svc>-<projnum>.<region>.run.app`
    — and comparing hosts calls those a mismatch. Measured 2026-08-16, all
    four combinations of {audience A, audience B} x {called at A, at B}
    returned HTTP 200, so a token minted for either form is accepted at
    either URL. A check that failed on this would fail on the default install.
    """
    if not base_url:
        return _check(
            "token audience", True,
            f"{aud} (no --base-url given, so nothing to compare it against)",
            "pass --base-url $(the plugin's mcp_base_url) to check this")

    a_host, b_host = urlparse(aud).netloc, urlparse(base_url).netloc
    a_svc, b_svc = _cloud_run_service(a_host), _cloud_run_service(b_host)
    # Neither parsed as a Cloud Run hostname — a custom domain or a local
    # deployment. Fall back to host equality rather than passing by default:
    # an unrecognised shape is not evidence that the audience is right.
    same = (a_svc == b_svc) if (a_svc and b_svc) else (a_host == b_host)
    two_forms = same and a_host != b_host
    return _check(
        "token audience matches the connector service", same,
        ((a_svc or a_host) +
         (" (same service, two Cloud Run URL forms — interchangeable)"
          if two_forms else "")) if same else
        f"audience is service {a_svc or a_host!r}, "
        f"configured URL is {b_svc or b_host!r}",
        "" if same else
        "export DMA_MCP_HOST to the same SERVICE as mcp_base_url. Cloud Run "
        "checks the audience before the request reaches the connector, so a "
        "genuine mismatch is a 403 that reads like a permissions problem.")


def run_checks(base_url: str | None) -> list:
    out = []

    # 1 — the plugin's own files
    manifest = PLUGIN / ".claude-plugin" / "plugin.json"
    out.append(_check(
        "plugin manifest", manifest.exists(),
        str(manifest) if manifest.exists() else "not found",
        "install the plugin from the marketplace: /plugin marketplace add "
        "mishleyotis/Accelerate, then /plugin install dma-insights@zennify-dma"))
    mcp_json = PLUGIN / ".mcp.json"
    out.append(_check("connector definition", mcp_json.exists(),
                      str(mcp_json) if mcp_json.exists() else "not found"))
    skills = sorted(p.name for p in (PLUGIN / "skills").glob("*") if p.is_dir())
    out.append(_check("skills present", len(skills) >= 6,
                      f"{len(skills)}: {', '.join(skills)}" if skills else "none"))
    agents = sorted(p.stem for p in (PLUGIN / "agents").glob("*.md"))
    out.append(_check("agents present", len(agents) >= 5,
                      f"{len(agents)}: {', '.join(agents)}" if agents else "none"))

    # 2 — gcloud and an identity
    gcloud = _gcloud()
    out.append(_check("gcloud found", gcloud, gcloud or "not on PATH or in the "
                      "usual install locations",
                      "install the Google Cloud SDK, or set GCLOUD_BIN"))
    account = None
    if gcloud:
        env = dict(os.environ)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        proc = subprocess.run(
            [gcloud, "auth", "list", "--filter=status:ACTIVE",
             "--format=value(account)"], capture_output=True, text=True, env=env)
        account = (proc.stdout or "").strip().splitlines()
        account = account[0] if account else None
    out.append(_check("active google account", account, account or "none active",
                      "gcloud auth login, or activate a service account"))

    # 3 — the audience the helper will use, against the URL being called
    aud = os.environ.get("DMA_MCP_HOST", DEFAULT_AUD)
    out.append(audience_check(aud, base_url))

    # 4 — can a token actually be minted for that audience
    if gcloud and account:
        env = dict(os.environ)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        proc = subprocess.run(
            [gcloud, "auth", "print-identity-token", f"--audiences={aud}"],
            capture_output=True, text=True, env=env)
        minted = proc.returncode == 0 and bool(proc.stdout.strip())
        out.append(_check(
            "identity token mints", minted,
            "yes (value not shown)" if minted else
            (proc.stderr or "").strip()[:160] or "empty token",
            "" if minted else "the active account may not be permitted to mint "
            "an ID token for this audience"))
    else:
        out.append(_check("identity token mints", False,
                          "skipped: no gcloud or no active account"))

    # 5 — is the identity token actually ENFORCED, or merely minted?
    out.append(enforcement_check(base_url))

    # 6 — the path token, which is a SEPARATE credential from the ID token
    token_set = bool(os.environ.get("DMA_MCP_PATH_TOKEN"))
    out.append(_check(
        "connector path token", True,
        "set in this environment" if token_set else
        "not in this environment — expected: the plugin stores it in the OS "
        "keychain as user_config.mcp_path_token, not as an env var",
        "if the connector 404s, read it with: gcloud secrets versions access "
        "latest --secret=dmai-mcp-path-token"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=None,
                    help="the plugin's configured mcp_base_url")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    checks = run_checks(args.base_url)
    if args.json:
        print(json.dumps({"checks": checks}, indent=1))
    else:
        print("DMA Insights — install doctor\n")
        for c in checks:
            print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['check']:42} {c['detail']}")
            if not c["ok"] and c["fix"]:
                print(f"         -> {c['fix']}")
        bad = [c for c in checks if not c["ok"]]
        print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed."
              if bad else "\nall checks passed.")
    return 1 if any(not c["ok"] for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
