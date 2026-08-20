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

Local wiring gets the same posture: hooks must parse AND run — a handler that
dies on import fails only at the moment a submit needed it — component counts
are exact (a >= floor reported a clean install while seven agent files were
missing), and the tool names the hooks match on are reconciled against what
the deployed connector actually serves.

    python doctor.py                 # human; probes the manifest's default URL
    python doctor.py --json
    python doctor.py --no-probe      # offline: the network rows are skipped

Exit 0 when every check passes, 1 otherwise. Prints no token, ever — not the
identity token, not the capability-path segment: each check reports whether a
credential could be obtained, never what it was.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
DEFAULT_AUD = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"

# The plugin ships exactly these counts. A floor (agents >=5, skills >=6)
# reported a clean install while seven agent files were missing — a floor
# only catches total loss, equality catches partial packaging loss.
EXPECTED_SKILLS = 6
EXPECTED_AGENTS = 16   # 14 + insights-surface-producer + techstack-surface-producer, split out of context (2026-08-19)

#: Fed to `python3 <handler>` on stdin: an event that names no tool and
#: carries no payload. Every handler's contract is to fail open on it, so a
#: non-zero exit is a broken handler, not a refusal.
BENIGN_EVENT = b"{}\n"


def read_manifest() -> dict:
    try:
        return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return {}


def manifest_base_url() -> str | None:
    cfg = (read_manifest().get("userConfig") or {}).get("mcp_base_url") or {}
    default = cfg.get("default")
    return default.rstrip("/") if isinstance(default, str) and default else None


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
            "not probed (--no-probe)",
            "drop --no-probe (or pass --base-url) to check this")
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
            f"{aud} (--no-probe: nothing to compare it against)",
            "drop --no-probe (or pass --base-url) to check this")

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


def _load_hooks(plugin_root: Path):
    """(parsed hooks.json, error string) — exactly one is None."""
    hooks_file = plugin_root / "hooks" / "hooks.json"
    if not hooks_file.is_file():
        return None, f"{hooks_file} not found"
    try:
        return json.loads(hooks_file.read_text()), None
    except ValueError as exc:
        return None, f"hooks.json does not parse: {str(exc)[:120]}"


def _hook_entries(spec: dict):
    """Flatten hooks.json to (event, matcher, hook-dict) triples."""
    hooks = spec.get("hooks")
    for event, groups in (hooks if isinstance(hooks, dict) else {}).items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks") or []:
                if isinstance(hook, dict):
                    yield event, group.get("matcher"), hook


def hook_matchers(plugin_root: Path = PLUGIN) -> list:
    spec, err = _load_hooks(plugin_root)
    if err:
        return []
    return sorted({m for _, m, _ in _hook_entries(spec) if m})


def _handler_path(command: str, plugin_root: Path) -> Path | None:
    """The handler file a hook command runs. ${CLAUDE_PLUGIN_ROOT} resolves to
    `plugin_root`; hooks.json quotes it, so shlex sees one token."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for tok in tokens:
        if "${CLAUDE_PLUGIN_ROOT}" in tok:
            return Path(tok.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root)))
    for tok in tokens[1:]:
        if tok.endswith(".py"):
            return Path(tok) if os.path.isabs(tok) else plugin_root / tok
    return None


def hooks_wired_check(plugin_root: Path = PLUGIN) -> dict:
    """Parse hooks.json and RUN each handler once on a benign event.

    Existence is not wiring: a handler that dies on import, or an entry
    registered without a timeout, fails only at the moment a submit needed
    it — and a PreToolUse handler that cannot run is a precheck that never
    refuses anything.
    """
    spec, err = _load_hooks(plugin_root)
    if err:
        return _check("hooks wired", False, err,
                      "restore hooks/hooks.json from the plugin distribution")
    problems, ran = [], 0
    entries = list(_hook_entries(spec))
    if not entries:
        problems.append("hooks.json declares no hooks")
    for event, _, hook in entries:
        timeout = hook.get("timeout")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            problems.append(f"{event}: hook entry carries no numeric timeout")
        handler = _handler_path(hook.get("command") or "", plugin_root)
        if handler is None:
            problems.append(f"{event}: no handler path in command "
                            f"{str(hook.get('command'))[:60]!r}")
            continue
        if not handler.is_file():
            problems.append(f"{event}: handler {handler.name} does not exist")
            continue
        try:
            proc = subprocess.run([sys.executable, str(handler)],
                                  input=BENIGN_EVENT, capture_output=True,
                                  timeout=30)
        except subprocess.TimeoutExpired:
            problems.append(f"{event}: {handler.name} did not exit within 30s "
                            "on a benign event")
            continue
        if proc.returncode != 0:
            problems.append(f"{event}: {handler.name} exited {proc.returncode} "
                            "on a benign event")
        else:
            ran += 1
    return _check(
        "hooks wired", not problems,
        f"{ran} handler run(s): every entry parses, exists, has a numeric "
        "timeout and exits 0 on a benign event" if not problems
        else "; ".join(problems),
        "" if not problems else
        "in this state the hook never fires, or fires and dies — no submit "
        "is prechecked and no verdict reaches the ledger until it is repaired")


def inventory_checks(plugin_root: Path = PLUGIN) -> list:
    """Exact component counts, not floors — see EXPECTED_SKILLS/EXPECTED_AGENTS."""
    skills = sorted(p.name for p in (plugin_root / "skills").glob("*")
                    if p.is_dir() and not p.name.startswith(("_", ".")))
    agents = sorted(p.stem for p in (plugin_root / "agents").glob("*.md"))
    rows = []
    for label, found, expected in (("skills", skills, EXPECTED_SKILLS),
                                   ("agents", agents, EXPECTED_AGENTS)):
        ok = len(found) == expected
        rows.append(_check(
            f"{label} inventory", ok,
            f"{len(found)} of exactly {expected}: {', '.join(found) or 'none'}",
            "" if ok else f"the plugin ships exactly {expected} {label}; any "
            "other count means packaging dropped or leaked files — reinstall"))
    return rows


def enabled_state_check(manifest: dict) -> dict:
    """Informational only: defaultEnabled=false is the shipped state, not a
    defect, so this row reports and never fails."""
    enabled = manifest.get("defaultEnabled")
    return _check(
        "plugin enabled state", True,
        f"defaultEnabled={json.dumps(enabled)} — the plugin ships disabled and "
        "must be enabled per install (informational row, never fails)")


def deps_check(plugin_root: Path = PLUGIN) -> dict:
    """`scripts/dma-deps check` folded into one row: its exit is the verdict."""
    deps = plugin_root / "scripts" / "dma-deps"
    if not deps.is_file():
        return _check("skill script dependencies", False, f"{deps} not found",
                      "reinstall the plugin; scripts/dma-deps declares what "
                      "the bundled skill scripts import")
    try:
        proc = subprocess.run([sys.executable, str(deps), "check"],
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return _check("skill script dependencies", False,
                      "dma-deps check did not finish in 120s")
    summary = next((l.strip() for l in (proc.stdout or "").splitlines()
                    if l.startswith("declared:")), "")
    ok = proc.returncode == 0
    return _check("skill script dependencies", ok,
                  summary or f"dma-deps check exited {proc.returncode}",
                  "" if ok else "run: scripts/dma-deps install (or scripts/"
                  "dma-deps install --venv)")


def _keyfile() -> str | None:
    """The dmai-routine service-account key file, if this container has one.
    bootstrap_session.sh lands it from the DMA_ROUTINE_SA_KEY environment
    value; fresh routine containers have no gcloud, and this file is their
    entire identity."""
    path = os.environ.get("DMA_SA_KEY_FILE", "/root/.dma/sa.json")
    try:
        return path if os.path.getsize(path) > 0 else None
    except OSError:
        return None


def _mint_via_keyfile(mode: str, value: str | None = None) -> str | None:
    """Run the bundled gcp_token.py (same directory) — 'id' with an audience
    or 'access' with the default scope. Returns the token or None; the token
    is returned to be SENT, never printed."""
    keyfile = _keyfile()
    if not keyfile:
        return None
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "gcp_token.py"),
           mode, "--key", keyfile]
    if mode == "id" and value:
        cmd += ["--audience", value]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except Exception:
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _path_token(gcloud: str | None) -> tuple:
    """(capability-path token, source-or-reason). The plugin proper reads it
    from the OS keychain (user_config.mcp_path_token), which no subprocess can
    read portably; the doctor accepts the env override and falls back to the
    Secret Manager entry the manifest documents — via gcloud where it exists,
    else via Secret Manager REST with a key-file access token. The value is
    returned to be SENT, never printed."""
    token = (os.environ.get("DMA_MCP_PATH_TOKEN") or "").strip()
    if token:
        return token, "DMA_MCP_PATH_TOKEN"
    if not gcloud:
        access = _mint_via_keyfile("access")
        if access:
            import base64
            import json as _json
            import urllib.request
            req = urllib.request.Request(
                "https://secretmanager.googleapis.com/v1/projects/"
                "digital-maturity-assessor/secrets/dmai-mcp-path-token/"
                "versions/latest:access",
                headers={"Authorization": f"Bearer {access}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = _json.loads(resp.read())
                got = base64.b64decode(data["payload"]["data"]).decode().strip()
                if got:
                    return got, "secret manager (key-file identity)"
            except Exception:
                pass
        return None, ("path token unobtainable: DMA_MCP_PATH_TOKEN unset, "
                      "no gcloud, and the key-file Secret Manager read failed")
    env = dict(os.environ)
    env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
    try:
        proc = subprocess.run(
            [gcloud, "secrets", "versions", "access", "latest",
             "--secret=dmai-mcp-path-token"],
            capture_output=True, text=True, env=env, timeout=30)
    except Exception:
        proc = None
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip(), "secret manager"
    return None, ("path token unobtainable: DMA_MCP_PATH_TOKEN unset and the "
                  "Secret Manager read failed")


def _sse_or_json(raw: str, content_type: str):
    if "text/event-stream" in content_type:
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                msg = json.loads(line[len("data:"):].strip())
            except ValueError:
                continue
            if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                return msg
        return None
    try:
        return json.loads(raw) if raw.strip() else None
    except ValueError:
        return None


def _rpc(url: str, id_token: str, body: dict, session_id: str | None = None,
         timeout: float = 15.0):
    """One JSON-RPC POST over streamable HTTP. (payload, Mcp-Session-Id)."""
    import urllib.request
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Authorization": "Bearer " + id_token}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        return (_sse_or_json(raw, resp.headers.get("Content-Type") or ""),
                resp.headers.get("Mcp-Session-Id"))


def live_tool_names(base_url: str, path_token: str, id_token: str) -> list:
    """tools/list from the deployed connector, full initialize handshake first.

    Raises RuntimeError with a URL-free message on any failure: the request
    URL embeds the capability-path token, so neither the URL nor a library
    exception that might carry it may reach a row.
    """
    import urllib.error
    url = base_url.rstrip("/") + "/mcp/" + path_token
    try:
        init, session_id = _rpc(url, id_token, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "dma-doctor", "version": "0"}}})
        if isinstance(init, dict) and init.get("error"):
            raise RuntimeError("initialize refused: "
                               + str(init["error"].get("message"))[:120])
        try:
            _rpc(url, id_token,
                 {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 session_id)
        except urllib.error.HTTPError:
            pass  # servers that skip the notification step reject it; harmless
        listing, _ = _rpc(url, id_token,
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                          session_id)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from the connector") from None
    except OSError as exc:
        reason = str(getattr(exc, "reason", "") or type(exc).__name__)
        raise RuntimeError(f"connector unreachable: {reason[:80]}") from None
    if isinstance(listing, dict) and listing.get("error"):
        raise RuntimeError("tools/list refused: "
                           + str(listing["error"].get("message"))[:120])
    tools = ((listing or {}).get("result") or {}).get("tools") \
        if isinstance(listing, dict) else None
    if not isinstance(tools, list):
        raise RuntimeError("no tools array in the tools/list response")
    return [t["name"] for t in tools if isinstance(t, dict) and t.get("name")]


def _scoped_prefixes(manifest: dict) -> list:
    """`mcp__plugin_<plugin>_<server>__` for each server in .mcp.json — the
    fully scoped form the hook matchers use."""
    plugin_name = manifest.get("name") or PLUGIN.name
    try:
        servers = json.loads((PLUGIN / ".mcp.json").read_text()) \
            .get("mcpServers") or {}
    except (OSError, ValueError):
        servers = {"connector": None}
    return [f"mcp__plugin_{plugin_name}_{server}__" for server in servers]


def tool_roster_check(base_url, gcloud, id_token, manifest: dict) -> dict:
    """Reconcile hook matchers and the manifest's advertised tool count
    against what the deployed connector actually serves.

    A hook matching a tool the connector no longer serves is a precheck that
    silently stopped firing; a drifted '(N tools)' in the description is an
    install ad that lies. SKIPPED (never failed) when the tokens or the call
    are unobtainable — offline is not evidence of drift.
    """
    name = "live tool roster reconciles"
    if not base_url:
        return _check(name, True, "SKIPPED: not probed (--no-probe)",
                      "drop --no-probe (or pass --base-url) to check this")
    if not id_token:
        return _check(name, True,
                      "SKIPPED: no identity token to call the connector with")
    path_token, source = _path_token(gcloud)
    if not path_token:
        return _check(name, True, f"SKIPPED: {source}")
    try:
        live = live_tool_names(base_url, path_token, id_token)
    except RuntimeError as exc:
        return _check(name, True, f"SKIPPED: {exc}")

    prefixes = _scoped_prefixes(manifest)
    unresolved = []
    matchers = hook_matchers()
    for matcher in matchers:
        bare = next((matcher[len(p):] for p in prefixes
                     if matcher.startswith(p)), None)
        if bare is None:
            unresolved.append(f"{matcher} (not scoped to a server this "
                              "plugin defines)")
        elif bare not in live:
            unresolved.append(matcher)
    advertised = re.search(r"\((\d+) tools\)", manifest.get("description") or "")
    advertised = int(advertised.group(1)) if advertised else None
    problems = []
    if unresolved:
        problems.append("hook matcher(s) name tools the connector does not "
                        "serve: " + ", ".join(unresolved))
    if advertised is None:
        problems.append("manifest description advertises no '(N tools)' count")
    elif advertised != len(live):
        problems.append(f"manifest advertises {advertised} tools, the "
                        f"connector serves {len(live)}")
    if problems:
        return _check(name, False, "; ".join(problems),
                      "update the hooks and the manifest description's "
                      "'(N tools)' to match the deployed connector")
    return _check(name, True,
                  f"{len(live)} live tools == manifest's advertised "
                  f"{advertised}; all {len(matchers)} hook matcher(s) resolve "
                  f"(path token via {source}, value not shown)")


def run_checks(base_url: str | None) -> list:
    out = []
    manifest = read_manifest()

    # 1 — the plugin's own files
    manifest_path = PLUGIN / ".claude-plugin" / "plugin.json"
    out.append(_check(
        "plugin manifest", manifest_path.exists(),
        str(manifest_path) if manifest_path.exists() else "not found",
        "install the plugin from the marketplace: /plugin marketplace add "
        "mishleyotis/Accelerate, then /plugin install dma-insights@zennify-dma"))
    out.append(enabled_state_check(manifest))
    mcp_json = PLUGIN / ".mcp.json"
    out.append(_check("connector definition", mcp_json.exists(),
                      str(mcp_json) if mcp_json.exists() else "not found"))
    out.append(hooks_wired_check())
    out.extend(inventory_checks())
    out.append(deps_check())

    # 2 — an identity: gcloud where it exists, else the service-account key
    # file bootstrap_session.sh lands (fresh routine containers have no SDK).
    gcloud = _gcloud()
    keyfile = _keyfile()
    out.append(_check(
        "gcloud found", bool(gcloud or keyfile),
        gcloud or (f"absent — using service-account key file {keyfile}"
                   if keyfile else "not on PATH or in the usual install "
                   "locations, and no key file"),
        "" if (gcloud or keyfile) else "install the Google Cloud SDK, set "
        "GCLOUD_BIN, or land a key via DMA_ROUTINE_SA_KEY (bootstrap_session.sh)"))
    account = None
    if gcloud:
        env = dict(os.environ)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        proc = subprocess.run(
            [gcloud, "auth", "list", "--filter=status:ACTIVE",
             "--format=value(account)"], capture_output=True, text=True, env=env)
        account = (proc.stdout or "").strip().splitlines()
        account = account[0] if account else None
    elif keyfile:
        try:
            account = json.loads(Path(keyfile).read_text()).get("client_email")
        except (OSError, ValueError):
            account = None
    out.append(_check("active google account", account, account or "none active",
                      "gcloud auth login, activate a service account, or check "
                      "the key file parses as JSON"))

    # 3 — the audience the helper will use, against the URL being called
    aud = os.environ.get("DMA_MCP_HOST", DEFAULT_AUD)
    out.append(audience_check(aud, base_url))

    # 4 — can a token actually be minted for that audience
    id_token = None
    if gcloud and account:
        env = dict(os.environ)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        proc = subprocess.run(
            [gcloud, "auth", "print-identity-token", f"--audiences={aud}"],
            capture_output=True, text=True, env=env)
        minted = proc.returncode == 0 and bool(proc.stdout.strip())
        id_token = proc.stdout.strip() if minted else None
        out.append(_check(
            "identity token mints", minted,
            "yes (value not shown)" if minted else
            (proc.stderr or "").strip()[:160] or "empty token",
            "" if minted else "the active account may not be permitted to mint "
            "an ID token for this audience"))
    elif keyfile:
        id_token = _mint_via_keyfile("id", aud)
        out.append(_check(
            "identity token mints", bool(id_token),
            "yes, from the service-account key file (value not shown)"
            if id_token else "key file present but the token exchange failed",
            "" if id_token else "run gcp_token.py id --audience <url> by hand "
            "and read its stderr — a disabled key reports invalid_grant"))
    else:
        out.append(_check("identity token mints", False,
                          "skipped: no gcloud, no active account, no key file"))

    # 5 — is the identity token actually ENFORCED, or merely minted?
    out.append(enforcement_check(base_url))

    # 5b — the roster the hooks and the manifest describe, against the wire
    out.append(tool_roster_check(base_url, gcloud, id_token, manifest))

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
                    help="the connector base URL to probe; defaults to the "
                         "manifest's mcp_base_url default")
    ap.add_argument("--no-probe", action="store_true",
                    help="offline run: skip the network rows (audience "
                         "comparison, enforcement probe, tool roster)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # The audience and enforcement rows are the two SECURITY checks, and a
    # default of "not probed" made both pass vacuously on every plain run.
    # They probe the manifest's own default URL unless --no-probe says this
    # machine is offline.
    base_url = None if args.no_probe else (
        args.base_url or manifest_base_url() or DEFAULT_AUD)

    checks = run_checks(base_url)
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
