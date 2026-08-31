#!/usr/bin/env python3
"""Is this install actually able to do the work? Checked, not assumed.

Installing the plugin is five things that fail independently and look the same
from the outside — the connector's tools are simply absent, and "absent"
carries no reason:

  1. the plugin is enabled and its components loaded
  2. the capability-path token is obtainable (header architecture: the
     headers helper fetches it — env, cache file, or Secret Manager)
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

# The two sibling modules that own facts this file only reports. Imported at
# module level rather than inside a check so that a broken sibling fails the
# doctor loudly at import, where it is one obvious traceback, instead of
# silently skipping the row that was supposed to catch the problem.
sys.path.insert(0, str(HERE))
import connector_contract                                       # noqa: E402
import plugin_version                                           # noqa: E402
DEFAULT_AUD = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"

# The plugin ships exactly these counts. A floor (agents >=5, skills >=6)
# reported a clean install while seven agent files were missing — a floor
# only catches total loss, equality catches partial packaging loss.
EXPECTED_SKILLS = 6

def expected_agents(manifest: dict | None = None) -> int:
    """How many agents this plugin ships — READ FROM THE MANIFEST, not typed.

    This was `EXPECTED_AGENTS = 47` for three days, and 47 was correct for
    all of them. The problem is not the number, it is that a second copy of
    it exists: `plugin.json` already lists every agent path, and the two can
    disagree the moment one is edited. Deriving it makes the manifest the
    only place the roster is stated, which is also why the routine prompts
    stopped saying "the 47-agent roster" — see `plugin_version.py`.
    """
    listed = len(((manifest if manifest is not None else read_manifest())
                  .get("agents")) or [])
    return listed

#: Fed to `python3 <handler>` on stdin: an event that names no tool and
#: carries no payload. Every handler's contract is to fail open on it, so a
#: non-zero exit is a broken handler, not a refusal.
BENIGN_EVENT = b"{}\n"


def _load_manifest(plugin_root: Path) -> dict:
    try:
        return json.loads(
            (plugin_root / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return {}


def read_manifest() -> dict:
    return _load_manifest(PLUGIN)


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


#: `${CLAUDE_PLUGIN_ROOT}/scripts/hooks/<name>.py`, wherever it appears in a
#: command. Matched on the PATH rather than on token position, because the
#: command is no longer a bare `python3 <path>`: each hook is wrapped in a
#: presence test so a missing handler degrades to a loud allow instead of
#: blocking every Bash call in the session (see hooks/hooks.json).
_HOOK_PATH_RE = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}(/scripts/hooks/[A-Za-z0-9_.-]+\.py)")


def _handler_path(command: str, plugin_root: Path) -> Path | None:
    """The handler file a hook command runs, wrapped or bare."""
    m = _HOOK_PATH_RE.search(command or "")
    if m:
        return Path(str(plugin_root) + m.group(1))
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

    # THE HOOK A SCHEDULED FIRING CANNOT RUN WITHOUT, checked here because a
    # session that is missing it does not fail — it HANGS, on a permission
    # prompt no human will ever see (measured 2026-08-21: three firings died
    # exactly this way, two on the connector and one on an enrichment
    # lookup).
    #
    # Instructions in the routine prompt cannot help that case: a session
    # blocked mid-tool-call is not reading anything. The check has to happen
    # BEFORE work starts, and STEP 0 already requires this doctor fully
    # green — so putting it here is what makes an old plugin fail loudly at
    # the gate instead of silently burning a twelve-hour slot.
    approver = plugin_root / "scripts" / "hooks" / "autoapprove_connector.py"
    if not approver.is_file():
        problems.append("scripts/hooks/autoapprove_connector.py is missing — "
                        "an unattended session will hang on a permission "
                        "prompt nobody can answer")
    else:
        wired = any("autoapprove_connector.py" in (h.get("command") or "")
                    for ev, _, h in entries if ev == "PreToolUse")
        if not wired:
            problems.append("autoapprove_connector.py exists but no PreToolUse "
                            "entry runs it — an unattended session will hang "
                            "on a permission prompt nobody can answer")

    return _check(
        "hooks wired", not problems,
        f"{ran} handler run(s): every entry parses, exists, has a numeric "
        "timeout and exits 0 on a benign event; the connector auto-approver "
        "is present and wired" if not problems
        else "; ".join(problems),
        "" if not problems else
        "in this state the hook never fires, or fires and dies — no submit "
        "is prechecked and no verdict reaches the ledger until it is repaired")


def inventory_checks(plugin_root: Path = PLUGIN) -> list:
    """Exact component counts, not floors — see EXPECTED_SKILLS/expected_agents.

    CAVEAT THIS ROW CANNOT ESCAPE, and the reason `installed_plugin_check`
    sits beside it: `plugin_root` defaults to the checkout this file lives
    in, so these counts describe the REPO. A session dispatches against the
    install cache, and on 2026-08-23 that cache held 5 agents while this row
    read 47 and passed. Green here means "the checkout is whole", never "the
    session can reach them".
    """
    skills = sorted(p.name for p in (plugin_root / "skills").glob("*")
                    if p.is_dir() and not p.name.startswith(("_", ".")))
    agents = sorted(p.stem for p in (plugin_root / "agents").rglob("*.md")
                    if p.name != "README.md")
    manifest = read_manifest() if plugin_root == PLUGIN else _load_manifest(plugin_root)
    rows = []
    for label, found, expected in (("skills", skills, EXPECTED_SKILLS),
                                   ("agents", agents, expected_agents(manifest))):
        ok = len(found) == expected
        rows.append(_check(
            f"{label} inventory", ok,
            f"{len(found)} of exactly {expected}: {', '.join(found) or 'none'}",
            "" if ok else f"the plugin ships exactly {expected} {label}; any "
            "other count means packaging dropped or leaked files — reinstall"))
    return rows


def installed_plugin_check(heal: bool = False) -> dict:
    """Is the plugin the session LOADS the one this checkout publishes?

    The row `inventory_checks` cannot be. Those counts come from the repo;
    this one comes from the install cache, and on 2026-08-23 they read 47
    and 5 on the same container. Everything it compares is read at call
    time from a manifest or the install state — no version literal lives in
    this file, which is the whole point (see plugin_version.py).

    WHY THIS ROW CAN HEAL ITSELF (owner, 2026-08-31: "Plugin version should
    always pick the most recent bump and self heal"). It could not, and the
    consequence was measured the same day: a firing whose STEP 0a read
    "doctor.py — not green, STOP" met `STALE: installed 0.9.12 (47 agents)
    vs published 1.13.0 (68 agents)` and stopped, having done nothing. STALE
    is the one verdict an update fixes without a judgment call, and
    `plugin_version.heal()` has run that update since 2026-08-24 — but this
    row only ever called `compare()`, so the doctor could NEVER go green on
    a stale container and every caller that required a green doctor was
    requiring something unreachable. A gate whose pass condition cannot be
    reached is not a gate, it is a stop.

    So `--heal` threads through to the same self-healing loop
    `plugin_version.py --heal` runs: update, re-measure, one final verdict.
    It is opt-in because a plain `doctor.py` must stay a pure measurement —
    a check that mutates the machine it is measuring cannot be trusted to
    report what it found.
    """
    try:
        v = plugin_version.compare()
        if heal and not v["ok"]:
            healed, heal_log = plugin_version.heal(v)
            if healed is None:                  # the update ran — re-measure
                before = plugin_version.summary(v)
                v = plugin_version.compare()
                v.setdefault("reasons", []).insert(0, f"before --heal: {before}")
                v["reasons"][1:1] = heal_log
            elif heal_log:                      # heal attempted, could not run
                v.setdefault("reasons", []).extend(heal_log)
    except Exception as exc:                                    # noqa: BLE001
        return _check("installed plugin", False,
                      f"could not be determined: {exc}",
                      "run plugins/dma-insights/scripts/plugin_version.py "
                      "directly for the reason")
    detail = plugin_version.summary(v)
    if v["reasons"]:
        detail += " — " + "; ".join(v["reasons"])
    fix = v["fix"]
    if not v["ok"] and not heal:
        fix = (f"{fix}  |  or re-run this doctor as `doctor.py --heal`, which "
               "runs that update and re-checks in one command")
    return _check("installed plugin", v["ok"], detail, fix)


def enabled_state_check(manifest: dict) -> dict:
    """What the manifest ships as, and what this container actually has.

    Informational only, and deliberately: `defaultEnabled=false` is the
    shipped state rather than a defect, and the LIVE reading — measured from
    `enabledPlugins` in settings.json, which is where a switched-off plugin
    is actually recorded — already fails the installed-plugin row above as
    DISABLED, where the heal that fixes it lives. Reporting it twice would
    give one fact two verdicts.
    """
    enabled = manifest.get("defaultEnabled")
    live = plugin_version.enabled_state()
    live_txt = {True: "enabled", False: "DISABLED — loads nothing",
                None: "no settings file says either way"}[live]
    return _check(
        "plugin enabled state", True,
        f"defaultEnabled={json.dumps(enabled)} — the plugin ships disabled and "
        f"must be enabled per install; this container: {live_txt} "
        "(informational row, never fails)")


def concurrent_writers_check() -> dict:
    """Whether THIS install's engine can survive two writers on one workbook.

    WHY A CHECK AND NOT A DOCSTRING. Until 2026-08-31 `next_evidence_id`
    ended with "two writers to one workbook is not a supported topology and
    never was". That was a statement of scope; it was read as a guarantee,
    and it was read again AFTER the lock landed — a session on a stale
    install quoted the deleted sentence as authority and began building a
    shard-and-merge harness with disjoint evidence-id ranges to work around
    a defect that no longer existed. Prose in a file cannot tell you which
    version of the file you are running. A capability check can.

    Answered from the INSTALLED tree rather than the checkout, because the
    installed tree is what a session's agents actually execute.
    """
    name = "concurrent workbook writers"
    try:
        v = plugin_version.compare()
        root = (v.get("installed") or {}).get("install_path")
        eng = (Path(root) / "skills" / "dma-research" / "engine" /
               "workbook.py") if root else None
        if not eng or not eng.is_file():
            return _check(name, True,
                          "SKIPPED: no installed engine to read "
                          f"({eng or 'no install path'})")
        src = eng.read_text()
        # `fcntl` OR `flock`: the marker is the LOCK, not one spelling
        # of it. Pinning a single token would make this check fail on
        # a correct engine that acquired the lock another way, which
        # is the false alarm that sends someone back to sharding.
        safe = ("def transaction(" in src
                and ("flock" in src or "fcntl" in src))
        stale_claim = "not a supported topology and never was" in src
        detail = (
            "SAFE: the installed engine takes an exclusive lock across "
            "reload-mutate-save, so concurrent writers to one workbook do "
            "not lose each other's rows"
            if safe else
            "UNSAFE: the installed engine has no cross-process lock, so two "
            "writers to one workbook silently clobber each other. Shard onto "
            "separate workbooks, or update the plugin")
        if stale_claim:
            detail += (". This install still carries the docstring saying "
                       "two writers are 'not a supported topology' — that "
                       "sentence was deleted when the lock landed, so a "
                       "session reading it here is reading a STALE install")
        return _check(name, True, detail,
                      "" if safe else "doctor.py --heal, then re-dispatch: "
                      "a running session keeps the engine it started with")
    except Exception as exc:                                # noqa: BLE001
        return _check(name, True, f"SKIPPED: {exc}")


def connector_contract_check() -> dict:
    """Which connector families a firing REQUIRES, derived not typed.

    THE HALF A SCRIPT CAN CHECK. A session's bound MCP tools live in the
    model's context and no subprocess can enumerate them (MEM-0112), so this
    row proves the other half: that every family the contract stops a firing
    for is one the agents are actually provisioned with. On 2026-08-31 a
    Routine prompt required "Firecrawl" — named in no agent's tools, in no
    role in the provisioner, and nowhere in docs/CONNECTORS.md — which would
    have stopped every firing on a connector the pipeline cannot call. A
    requirement written as prose is never compared to anything.
    """
    name = "connector contract"
    try:
        c = connector_contract.contract()
    except connector_contract.ContractBroken as exc:
        return _check(name, False, str(exc),
                      "reconcile the required set in "
                      "plugins/dma-insights/scripts/connector_contract.py "
                      "with EXTERNAL in scripts/provision_agent_tools.py — "
                      "one of them is wrong, and the registry is the one the "
                      "agents are built from")
    anyof = "; ".join(" or ".join(g) for g in c["required_any"])
    return _check(
        name, True,
        f"required {', '.join(c['required'])}"
        + (f"; at least one of {anyof}" if anyof else "")
        + f"; optional {', '.join(c['optional'])} — derived from EXTERNAL, so "
        "no firing stops on a family no agent declares. A session's OWN bound "
        "tools cannot be read from here: pipe them to "
        "`connector_contract.py check --tools -`")


def deps_check(plugin_root: Path = PLUGIN, offline: bool = False) -> dict:
    """`scripts/dma-deps check` folded into one row: its exit is the verdict.

    Under --no-probe the wheel resolution is skipped, because it reaches
    PyPI and this row is otherwise a network check wearing a local row's
    name — the defect that made an offline doctor report red with
    "missing: 0" in its own detail text.
    """
    deps = plugin_root / "scripts" / "dma-deps"
    if not deps.is_file():
        return _check("skill script dependencies", False, f"{deps} not found",
                      "reinstall the plugin; scripts/dma-deps declares what "
                      "the bundled skill scripts import")
    try:
        proc = subprocess.run(
            [sys.executable, str(deps), "check"] + (["--offline"] if offline else []),
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
    bootstrap_session.sh lands it; a container that never ran bootstrap has
    no file and reaches its identity through the environment instead."""
    path = os.environ.get("DMA_SA_KEY_FILE", "/root/.dma/sa.json")
    try:
        return path if os.path.getsize(path) > 0 else None
    except OSError:
        return None


def _identity_source() -> str | None:
    """How this container can prove who it is, without gcloud — the key file
    if bootstrap landed one, else the environment variable the connector's
    auth helper reads at session start. Reporting only the file was a
    false negative: a fired routine authenticates from the environment with
    no file on disk anywhere (measured 2026-08-20)."""
    keyfile = _keyfile()
    if keyfile:
        return f"key file {keyfile}"
    for var in ("DMA_ROUTINE_SA_KEY_B64", "DMA_ROUTINE_SA_KEY"):
        if (os.environ.get(var) or "").strip():
            return var
    return None


def _mint_via_keyfile(mode: str, value: str | None = None) -> str | None:
    """Run the bundled gcp_token.py (same directory) — 'id' with an audience
    or 'access' with the default scope. Passes --key only when a file exists;
    with no file, gcp_token.py's own load_key reaches the environment. Returns
    the token or None; the token is returned to be SENT, never printed."""
    if not _identity_source():
        return None
    keyfile = _keyfile()
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "gcp_token.py"),
           mode]
    if keyfile:
        cmd += ["--key", keyfile]
    if mode == "id" and value:
        cmd += ["--audience", value]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except Exception:
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _path_token(gcloud: str | None) -> tuple:
    """(capability-path token, source-or-reason). Same rungs as
    mcp_auth_headers.sh, which now owns the token (it travels as the
    X-DMA-Path-Token header on a static /mcp URL — no plugin config): the
    env override, the cache file bootstrap lands, then Secret Manager — via
    gcloud where it exists, else via REST with a key-file access token. The
    value is returned to be SENT, never printed."""
    token = (os.environ.get("DMA_MCP_PATH_TOKEN") or "").strip()
    if token:
        return token, "DMA_MCP_PATH_TOKEN"
    cache = Path(os.environ.get("DMA_PATHTOK_FILE", "/root/.dma/pathtok"))
    try:
        cached = cache.read_text().strip()
    except OSError:
        cached = ""
    if cached:
        return cached, f"cache file {cache}"
    if gcloud:
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
    # gcloud's PRESENCE is not its capability: an installed SDK with no active
    # account reads exactly like no SDK at all, and a fired container has
    # neither. Fall through to the key/environment identity rather than
    # reporting the token unobtainable while a working credential sits in the
    # environment (measured 2026-08-20).
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
                return got, "secret manager (service-account identity)"
        except Exception:
            pass
    return None, ("path token unobtainable: DMA_MCP_PATH_TOKEN unset, gcloud "
                  "absent or unauthenticated, and the service-account Secret "
                  "Manager read failed")


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
    # WHAT THIS ROW IS FOR, and what it is not.
    #
    # The drift worth catching is a matcher that NAMES one connector tool
    # which the connector has stopped serving — that hook silently never
    # fires again. Two other kinds of matcher are legitimate and were being
    # failed as though they were that:
    #
    #   * a matcher on a non-MCP tool. `Bash` has matched deny_credential_ops
    #     since that guard was written; it is not a connector tool and never
    #     was.
    #   * a PATTERN rather than a name. `mcp__.*` is how autoapprove_connector
    #     reaches the enrichment connectors, whose server segment is an opaque
    #     per-attachment UUID that no exact matcher can name. Its scoping is
    #     enforced inside the script and by its own tests, not here.
    #
    # Failing those made the row red for a correct configuration — and the
    # synthesis routine's STEP 0 requires a fully green doctor, so this row
    # alone would have stopped every scheduled firing. A check that fails a
    # correct config is worse than no check: it trains people to skip the row.
    _META = set(".*+?[]{}()|^$\\")
    named = patterns = foreign = 0
    for matcher in matchers:
        if set(matcher) & _META:
            patterns += 1
            continue
        bare = next((matcher[len(p):] for p in prefixes
                     if matcher.startswith(p)), None)
        if bare is None:
            foreign += 1          # a tool this plugin's connector never served
            continue
        named += 1
        if bare not in live:
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
    # Say what was RECONCILED and what was merely counted — a row that reports
    # "all N resolve" while silently skipping most of them is the kind of
    # comfortable half-truth this build keeps removing.
    return _check(name, True,
                  f"{len(live)} live tools == manifest's advertised "
                  f"{advertised}; {named} named connector matcher(s) resolve "
                  f"({patterns} pattern, {foreign} non-connector matcher(s) "
                  f"not name-checked) "
                  f"(path token via {source}, value not shown)")


def run_checks(base_url: str | None, heal: bool = False) -> list:
    out = []
    manifest = read_manifest()

    # 1 — the plugin's own files
    manifest_path = PLUGIN / ".claude-plugin" / "plugin.json"
    out.append(_check(
        "plugin manifest", manifest_path.exists(),
        str(manifest_path) if manifest_path.exists() else "not found",
        "install the plugin from the marketplace: /plugin marketplace add "
        "mishleyotis/Accelerate, then /plugin install dma-insights@zennify-dma"))
    out.append(installed_plugin_check(heal))
    out.append(enabled_state_check(manifest))
    mcp_json = PLUGIN / ".mcp.json"
    out.append(_check("connector definition", mcp_json.exists(),
                      str(mcp_json) if mcp_json.exists() else "not found"))
    out.append(connector_contract_check())
    out.append(concurrent_writers_check())
    out.append(hooks_wired_check())
    out.extend(inventory_checks())
    out.append(deps_check(offline=base_url is None))

    # 2 — an identity: gcloud where it exists, else the service-account key
    # file bootstrap_session.sh lands (fresh routine containers have no SDK).
    gcloud = _gcloud()
    keyfile = _identity_source()
    out.append(_check(
        "gcloud found", bool(gcloud or keyfile),
        gcloud or (f"absent — identity from {keyfile}"
                   if keyfile else "not on PATH or in the usual install "
                   "locations, and no key file or key in the environment"),
        "" if (gcloud or keyfile) else "install the Google Cloud SDK, set "
        "GCLOUD_BIN, or set DMA_ROUTINE_SA_KEY_B64 in the environment"))
    account = None
    if gcloud:
        env = dict(os.environ)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        proc = subprocess.run(
            [gcloud, "auth", "list", "--filter=status:ACTIVE",
             "--format=value(account)"], capture_output=True, text=True, env=env)
        account = (proc.stdout or "").strip().splitlines()
        account = account[0] if account else None
    gcloud_account = account          # only gcloud can mint with THIS one
    # An SDK with no active account is not an identity. Fall through to the
    # key or the environment instead of failing next to a working credential.
    if not account and keyfile:
        kf = _keyfile()
        try:
            if kf:
                account = json.loads(Path(kf).read_text()).get("client_email")
            else:
                import base64 as _b64
                raw = (os.environ.get("DMA_ROUTINE_SA_KEY_B64") or "").strip()
                blob = _b64.b64decode(raw) if raw else (
                    os.environ.get("DMA_ROUTINE_SA_KEY") or "").strip()
                account = json.loads(blob).get("client_email") if blob else None
        except (OSError, ValueError, Exception):
            account = None
    out.append(_check("active google account", account, account or "none active",
                      "gcloud auth login, activate a service account, or check "
                      "the key file parses as JSON"))

    # 3 — the audience the helper will use, against the URL being called
    aud = os.environ.get("DMA_MCP_HOST", DEFAULT_AUD)
    out.append(audience_check(aud, base_url))

    # 4 — can a token actually be minted for that audience
    #
    # MINTING REACHES GOOGLE, so under --no-probe it is skipped rather than
    # attempted and failed: an offline doctor that reports "identity token
    # mints: ERROR ... Max retries exceeded" is describing the network, not
    # the install, and it turned every offline run red (measured
    # 2026-08-20). The rows above still state WHICH identity was found,
    # which is the part that is knowable without a network.
    id_token = None
    if base_url is None:
        out.append(_check(
            "identity token mints", True,
            "SKIPPED: not probed (--no-probe) — minting reaches Google",
            "drop --no-probe (or pass --base-url) to check this"))
    elif gcloud and gcloud_account:
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
            f"yes, from {keyfile} (value not shown)"
            if id_token else f"{keyfile} present but the token exchange failed",
            "" if id_token else "run gcp_token.py id --audience <url> by hand "
            "and read its stderr — a deleted key reports invalid_grant"))
    else:
        out.append(_check("identity token mints", False,
                          "skipped: no gcloud identity, no key file, and no "
                          "key in the environment"))

    # 5 — is the identity token actually ENFORCED, or merely minted?
    out.append(enforcement_check(base_url))

    # 5b — the roster the hooks and the manifest describe, against the wire
    out.append(tool_roster_check(base_url, gcloud, id_token, manifest))

    # 6 — the path token, which is a SEPARATE credential from the ID token
    token_set = bool(os.environ.get("DMA_MCP_PATH_TOKEN"))
    out.append(_check(
        "connector path token", True,
        "set in this environment" if token_set else
        "not in this environment — expected: the headers helper fetches it "
        "itself (cache file, then Secret Manager) and sends it as the "
        "X-DMA-Path-Token header on the static /mcp URL",
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
    ap.add_argument("--heal", action="store_true",
                    help="on a STALE/MISSING/INCOMPLETE install, run the "
                         "plugin update itself (container-local cache only) "
                         "and re-check, so one command can reach green")
    args = ap.parse_args()

    # The audience and enforcement rows are the two SECURITY checks, and a
    # default of "not probed" made both pass vacuously on every plain run.
    # They probe the manifest's own default URL unless --no-probe says this
    # machine is offline.
    base_url = None if args.no_probe else (
        args.base_url or manifest_base_url() or DEFAULT_AUD)

    checks = run_checks(base_url, args.heal)
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
