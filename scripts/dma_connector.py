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

Two credentials, and they are not the same thing:

  * the capability-path token — env, then the file bootstrap lands, then
    Secret Manager (never committed, never echoed); the URL rotates when the
    secret rotates. It proves which connector you meant.
  * a Google-signed ID token for the Cloud Run service — minted per call from
    the routine service-account key. It proves who you are. Cloud Run enforces
    `roles/run.invoker` on the audience before the request ever reaches the
    MCP server, so a call without this header is a 403 no matter how good the
    path token is.

NEITHER CREDENTIAL MAY DEPEND ON gcloud, and until 2026-08-24 both did.
Measured on a routine container that day: `gcloud` is not on PATH and
/opt/google-cloud-sdk does not exist, so `gcloud auth print-identity-token`
raised and every call through this module failed before it reached the wire.
The watchdog routine is told in its own prompt that it carries no mcp__*
tools and must reach the connector "over HTTP through scripts/dma_connector.py"
— so a gcloud-only minter meant that routine could never do its job on the
image it actually runs on, and said so as a token error rather than as a
missing SDK.

`plugins/dma-insights/scripts/gcp_token.py` already mints both tokens in pure
Python from the service-account key (JWT-bearer exchange, stdlib only), which
is the same key bootstrap_session.sh lands and the same identity every other
consumer uses. That is now the FIRST rung here; gcloud remains as a fallback
for a workstation that has it and no key, so nothing that worked before
stops working.

Identity tokens live one hour. A synthesis run outlives that easily, so the
cache below is expiry-aware — it re-mints when the token it holds is inside
the refresh margin — rather than "mint once per process", which loses the
connector mid-flight. This mirrors `routine_secrets.drive_token`.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

def _find_gcloud() -> str:
    """gcloud, wherever it is.

    A bare "gcloud" assumes PATH, which does not survive between shell
    invocations in this harness — `export PATH=...` in one Bash call is gone
    in the next, so every fresh call silently fell back to a bare name and
    died with `FileNotFoundError`. Measured 2026-08-16: a call that had
    worked minutes earlier failed this way as soon as a new shell picked it
    up. The same search `doctor.py` and `setup_routines.py` already make, for
    the same reason: on this container gcloud lives outside PATH by default.
    """
    import shutil
    env_bin = os.environ.get("GCLOUD_BIN")
    if env_bin:
        return env_bin
    found = shutil.which("gcloud")
    if found:
        return found
    for candidate in (f"{os.environ.get('HOME', '')}/google-cloud-sdk/bin/gcloud",
                      "/root/google-cloud-sdk/bin/gcloud",
                      "/usr/local/google-cloud-sdk/bin/gcloud",
                      "/opt/google-cloud-sdk/bin/gcloud"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "gcloud"  # let it fail with gcloud's own error, not ours


_GCLOUD = _find_gcloud()
#: The plugin's pure-Python token minter, imported by path rather than by
#: package name: this script is run as `python3 scripts/dma_connector.py` from
#: the repo root, where `plugins/dma-insights/scripts` is not importable and
#: the directory name is not a legal identifier anyway.
#: `_UNSET` distinguishes "not looked yet" from "looked, not there" — without
#: it a missing plugin tree is re-imported on every single call.
_UNSET = object()
_GCP_TOKEN = _UNSET


def _gcp_token():
    """The gcp_token module, or None when the plugin tree is not beside us.

    None is a real answer — a bare checkout of scripts/ without the plugin is
    a machine where gcloud is the only route left — so callers fall back
    rather than crash on the import.
    """
    global _GCP_TOKEN
    if _GCP_TOKEN is not _UNSET:
        return _GCP_TOKEN
    _GCP_TOKEN = None
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "plugins", "dma-insights", "scripts",
                        "gcp_token.py")
    try:
        import importlib.util                                # noqa: PLC0415
        spec = importlib.util.spec_from_file_location("dma_gcp_token", path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _GCP_TOKEN = mod
    except Exception:                                        # noqa: BLE001
        _GCP_TOKEN = None
    return _GCP_TOKEN


_MCP_HOST = os.environ.get(
    "DMA_MCP_HOST", "https://dmai-mcp-dukrne5v4a-uc.a.run.app")
_PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
_REGION = os.environ.get("REGION", "us-central1")
_SERVICE = os.environ.get("DMA_MCP_SERVICE", "dmai-mcp")
_URL = None

# Re-mint when fewer than this many seconds remain. Two minutes covers a slow
# promote that starts just under the wire.
TOKEN_REFRESH_MARGIN = int(os.environ.get("MCP_TOKEN_REFRESH_MARGIN", 120))

# (token, unix expiry). Never logged, never written to disk.
_idtok_cache: "tuple[str, float] | None" = None


class _NoGcloud:
    """What a gcloud call returns on an image that has no gcloud.

    A missing binary is a RESULT, not an exception. `_find_gcloud` already
    falls back to the bare name "so it fails with gcloud's own error" — but a
    bare name that is not on PATH does not produce gcloud's error, it produces
    `FileNotFoundError` from Popen, which is not a returncode any caller was
    written to read. Measured 2026-08-24 on the routine image: that exception
    escaped the fallback ladder in `_mint_identity_token`, so a container with
    no SDK crashed with a stack trace instead of reporting which credentials
    it had tried and what to set.
    """
    returncode = 127
    stdout = ""

    def __init__(self, exc):
        self.stderr = f"gcloud is not installed on this image ({exc})"


def _gcloud(args):
    """Run gcloud with a cleared CLOUDSDK_AUTH_ACCESS_TOKEN: a stale token in
    the environment overrides the activated account and fails with a 401 that
    reads like a permissions problem.

    Never raises for a missing or unrunnable binary — see `_NoGcloud`.
    """
    try:
        return subprocess.run(
            [_GCLOUD, *args], capture_output=True, text=True,
            env={**os.environ, "CLOUDSDK_AUTH_ACCESS_TOKEN": ""})
    except OSError as exc:
        return _NoGcloud(exc)


def _url():
    """The connector URL, path token included. Never logged.

    `gcp_token.path_token` is the same three-rung ladder every other consumer
    climbs — env, the file bootstrap lands, then Secret Manager — so a
    container missing any one of them still answers. The bare gcloud read that
    used to be the only route past the env var is kept last, for a machine
    with the SDK and no plugin tree.
    """
    global _URL
    if _URL is None:
        tok = os.environ.get("MCP_PATH_TOKEN")
        mod = _gcp_token()
        if not tok and mod is not None:
            try:
                tok = mod.path_token(_PROJECT)
            except SystemExit:
                # path_token exits with the routes it tried; here that is one
                # rung of several, so it is caught and the next rung runs.
                tok = ""
            except Exception:                                # noqa: BLE001
                tok = ""
        if not tok:
            tok = _gcloud(["secrets", "versions", "access", "latest",
                           "--secret=dmai-mcp-path-token",
                           f"--project={_PROJECT}"]).stdout.strip()
        if not tok:
            raise RuntimeError(
                "no connector path token: MCP_PATH_TOKEN is unset, "
                "/root/.dma/pathtok is absent or empty, and neither the "
                "service-account key nor gcloud could read Secret Manager "
                "(dmai-mcp-path-token). bootstrap_session.sh lands the file; "
                "DMA_ROUTINE_SA_KEY_B64 is what lets it.")
        _URL = f"{_MCP_HOST}/mcp/{tok}"
    return _URL


def _claims(token):
    """The JWT payload, or {} if it is not one. Claims are not secret — the
    token is, and no part of it is returned here."""
    try:
        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:                                          # noqa: BLE001
        return {}


def _expiry(token, default_ttl=3300):
    exp = _claims(token).get("exp")
    try:
        return float(exp)
    except (TypeError, ValueError):
        # Unreadable expiry: assume the shortest plausible life so the cache
        # errs towards re-minting rather than towards serving a dead token.
        return time.time() + default_ttl


def principal(token=None):
    """The identity a call is made as, taken from the token itself rather than
    from `gcloud config` — a config read names an account that may have no
    working credential behind it."""
    who = _claims(token or "").get("email")
    if who:
        return who
    r = _gcloud(["auth", "list", "--filter=status:ACTIVE",
                 "--format=value(account)"])
    return r.stdout.strip().splitlines()[0] if r.stdout.strip() else "(unknown)"


def _member(who):
    kind = "serviceAccount" if who.endswith(".gserviceaccount.com") else "user"
    return f"{kind}:{who}"


def _mint_identity_token():
    """A fresh Google-signed ID token whose audience is the connector host.

    Two rungs, and the ORDER is the fix. The service-account key is what a
    routine container actually has; gcloud is what a workstation has. Trying
    the key first means the scheduled sessions — the ones with nobody watching
    — stop depending on an SDK that is not in their image.
    """
    tried = []
    mod = _gcp_token()
    if mod is not None:
        try:
            key, source = mod.load_key()
            if key is None:
                tried.append(f"service-account key: {source}")
            else:
                tok = mod.exchange(mod.mint_assertion(
                    key, {"target_audience": _MCP_HOST})).get("id_token", "")
                if tok:
                    return tok
                tried.append("service-account key: exchange carried no "
                             "id_token")
        except Exception as exc:                             # noqa: BLE001
            # The message names the failure class, never the key or a token.
            tried.append(f"service-account key: {type(exc).__name__}: "
                         f"{str(exc)[:200]}")
    else:
        tried.append("service-account key: gcp_token.py not found beside "
                     "this checkout")

    r = _gcloud(["auth", "print-identity-token", f"--audiences={_MCP_HOST}"])
    tok = r.stdout.strip()
    if r.returncode == 0 and tok:
        return tok
    tried.append(f"gcloud: {r.stderr.strip()[:200] or 'empty token'}")
    raise RuntimeError(
        f"could not mint an identity token for {_MCP_HOST}. "
        + "; ".join(tried)
        + ". The routine fix is DMA_ROUTINE_SA_KEY_B64 in the claude.ai/code "
          "environment settings (one line, base64 of Secret Manager secret "
          "dmai-routine-sa-key); bootstrap_session.sh materialises the key "
          "from it.")


def identity_token():
    """The ID token for the connector, minted on first use and re-minted
    before it expires. Never returned to a log or a print."""
    global _idtok_cache
    if _idtok_cache and _idtok_cache[1] > time.time() + TOKEN_REFRESH_MARGIN:
        return _idtok_cache[0]
    tok = _mint_identity_token()
    _idtok_cache = (tok, _expiry(tok))
    return tok


def invoker_grant_command(who):
    return (f"gcloud run services add-iam-policy-binding {_SERVICE} "
            f"--region={_REGION} --project={_PROJECT} "
            f"--member={_member(who)} --role=roles/run.invoker")


def _rpc(method, params, rid=1):
    tok = identity_token()
    req = urllib.request.Request(
        _url(), data=json.dumps({"jsonrpc": "2.0", "id": rid,
                                 "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {tok}",
                 "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Cloud Run refused before the MCP server saw the request. Name the
            # identity that actually took the refusal, not the one someone
            # assumed was in play, and hand over the exact grant.
            who = principal(tok)
            raise RuntimeError(
                f"connector refused the call: HTTP {e.code} for {who} on "
                f"service {_SERVICE}. This principal needs roles/run.invoker "
                f"on the service:\n  {invoker_grant_command(who)}") from None
        raise
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


def _cli_args(rest: list) -> dict:
    """Tool arguments from the CLI tail (everything after the tool name):
    `--file path.json`, a JSON string, or nothing (`{}`).

    THE FILE FORM EXISTS BECAUSE OF A MEASURED COST, not for symmetry. A
    contract-complete page payload runs 1-1.6MB, and a positional JSON string
    means the model authoring a submission has to RE-TYPE the entire payload
    into a shell argument on every attempt — on one heatmap page, ~12 of the
    50 minutes a producer spent went to exactly this, and a one-field repair
    after a verdict cost a full re-transmission because there was no cheaper
    way to resubmit. `--file` lets the payload be written once with a normal
    file-editing tool and referenced by path from then on: the repair is an
    edit plus one CLI call, not a retype.
    """
    if not rest:
        return {}
    if rest[0] == "--file":
        if len(rest) < 2:
            raise SystemExit("--file requires a path")
        with open(rest[1]) as f:
            return json.load(f)
    return json.loads(rest[0])


#: Exceptions that mean "the answer did not come back", NOT "it failed".
#: Deliberately narrow: a RuntimeError raised by `call` is the SERVER
#: speaking — a verdict, a refusal — and must never be retried as though the
#: request had been lost.
TRANSPORT_ERRORS = (ConnectionError, TimeoutError, OSError)

PAGES = ("overview", "insights", "heatmap", "platform", "context", "techstack")


def _submission_id(run_id: str, page: str):
    prog = call("get_run_progress", run_id=run_id)
    return ((prog.get("pages") or {}).get(page) or {}).get("submission_id")


def submit_confirmed(run_id: str, page: str, *, attempts: int = 3, **kwargs):
    """`submit_page_payload`, with a dropped connection resolved rather than guessed.

    Measured 2026-08-22 submitting the 2.7MB T. Rowe Price heatmap: the 35
    parts were accepted, the submit call died with

        http.client.RemoteDisconnected: Remote end closed connection
        without response

    and the submission HAD SUCCEEDED — `get_run_progress` showed heatmap PASS
    at submission 8203526d, written while the client was reading a socket
    that was no longer there. The Cloud Run service allows 900s and the
    client waits 900s, so neither is the ceiling; something in between gave
    up during a validation pass that runs V4 embeddings over 876 evidence
    rows and 595 cells.

    The danger is not the drop, it is what a caller does next. A dropped
    connection is indistinguishable from a failure, and the obvious response
    — send it again — re-opens an upload, re-sends every part, and re-runs
    the most expensive validation in the system to produce a second
    submission of a payload that was already accepted. Worse on a page whose
    sections APPEND: the same script that duplicated three thought-leadership
    entries into six did it by being run twice after what looked like a
    failure.

    So a transport error resolves to a QUESTION — did the submission id
    change? — and the connector answers it. Only an unchanged id across every
    attempt is a real failure.
    """
    before = _submission_id(run_id, page)
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return call("submit_page_payload", run_id=run_id, page=page, **kwargs)
        except TRANSPORT_ERRORS as exc:            # the answer was lost
            last = exc
            after = _submission_id(run_id, page)
            if after and after != before:
                # It landed. Fetch the verdict the dropped response carried.
                return call("get_validation_verdict", run_id=run_id, page=page)
            # It did not land; the payload is still assembled server-side, so
            # resending is the same upload_id and costs no re-transmission.
    raise RuntimeError(
        f"{page} submission did not land after {attempts} attempts and the "
        f"submission id never moved from {before!r} — this is a real failure, "
        f"not a dropped response. Last transport error: {last}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: dma_connector.py <tool> ['<json-args>' | --file path.json]")
    tool, args = sys.argv[1], _cli_args(sys.argv[2:])
    print(json.dumps(call(tool, **args), indent=2, default=str))
