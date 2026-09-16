#!/usr/bin/env python3
"""What this session ACTUALLY loads, measured against what the repo publishes.

WHY THIS EXISTS. Every routine prompt used to carry a version floor written
as a literal — ">= 0.6.0", ">= 0.8.0", "0.6.7+". Three problems, all of them
measured on this container on 2026-08-23:

  1. A literal goes stale the moment the plugin is bumped, and nobody
     rewrites four trigger prompts to match. The floors said 0.6.0 while the
     repo published 0.8.1, so a container carrying **0.2.0** passed the
     floor's intent ("recent enough") in exactly none of the ways it was
     supposed to and nothing said so.
  2. `doctor.py` counts the files in the REPO checkout — `HERE.parent` — so
     it reported 47 agents green while the session was loading the 5 agents
     in the install cache. The doctor was measuring the wrong tree, which is
     the worst kind of green.
  3. "The 47-agent roster" is the same literal wearing a different hat. The
     count is already in the manifest's `agents` array; anything that
     re-types it can disagree with it.

So nothing here is hardcoded. The repo is the source of truth for what
SHOULD be loaded, and every number is read from a manifest or the install
state at call time.

WHAT "IS LOADED" MEANS, corrected 2026-09-16. Until then the truth about
what a session runs was taken from `~/.claude/plugins/installed_plugins.json`
and the cache copy it points at. Measured on a cloud container that day:
the record said 1.19.0 at a cache path holding 73 agents, while the
session's connector process, its PreToolUse hooks and its Agent roster all
ran from the CHECKOUT (`CLAUDE_PLUGIN_ROOT=<repo>/plugins/dma-insights`,
74 agents, 1.20.0). For a plugin whose marketplace is a directory source
with a relative plugin path, this CLI loads the plugin in place and the
record is bookkeeping. The record is also written once — by the setup
script, when the cloud environment's filesystem snapshot is built — and
restored for every later session, so a check that read it called every
session STALE for as long as the snapshot outlived a version bump, and every
`--heal` rewrote a copy nothing loads from, on a disk discarded at session
end. That is the recurring false alarm this file no longer raises: the root
the session actually loaded is MEASURED (see `loaded_root()`), compared to
the checkout, and the record is reported beside it as what it is.

    python3 plugin_version.py            # one line per fact, exit 0 only when OK
    python3 plugin_version.py --json

Exit 0 means the installed plugin is the one this repo publishes, whole.
Exit 1 names which of the two it is not, and the command that fixes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parent                    # plugins/dma-insights
REPO_ROOT = PLUGIN_DIR.parent.parent        # the checkout
PLUGIN_NAME = "dma-insights"
MARKETPLACE_NAME = "zennify-dma"

#: Where the CLI records what it installed. Structured, so it is read rather
#: than parsed out of human output — `claude plugin list` is the fallback,
#: not the source.
INSTALL_STATE = Path(
    os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")
) / "plugins" / "installed_plugins.json"

#: WHERE ENABLEMENT LIVES, which is not the install state file. Measured
#: 2026-08-31: `claude plugin install` lands a plugin DISABLED ("This plugin
#: is disabled by default — enable it with: claude plugin enable"), and the
#: install record carries no flag saying so. A container can therefore hold a
#: correct, current install that loads nothing, and every check that read only
#: installed_plugins.json called that OK.
SETTINGS_FILES = (
    Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    / "settings.json",
    Path(os.environ.get("CLAUDE_PROJECT_DIR", REPO_ROOT))
    / ".claude" / "settings.json",
)

#: What the environment setup script recorded about this container, written by
#: bootstrap_session.sh section 4b before the session existed. Absence is
#: itself a reading — see `provisioning()`.
PROV_FILE = Path(os.environ.get(
    "DMA_PROVISIONING_FILE",
    Path(os.environ.get("DMA_SA_KEY_FILE", "/root/.dma/sa.json")).parent
    / "provisioning.json"))

#: Where the SessionStart hook records the root THIS session's hooks ran
#: from — see `record_loaded_root()`. Hooks receive `CLAUDE_PLUGIN_DATA` from
#: the CLI; a Bash-run script does not, so the same directory is derived the
#: way the CLI derives it (`~/.claude/plugins/data/<plugin>-<marketplace>/`).
LOADED_ROOT_FILE = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or (
    Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    / "plugins" / "data" / f"{PLUGIN_NAME}-{MARKETPLACE_NAME}")
) / "loaded_root.json"

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _tuple(version: str | None) -> tuple[int, int, int] | None:
    """A comparable version, or None when the string is not one. Never
    guesses: an unparseable version compares as unknown, not as zero."""
    m = _SEMVER.search(version or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


#: Never shipped, never compared — build artefacts, not plugin content.
_SKIP = ("__pycache__", ".pyc", ".DS_Store", ".git/")


def tree_files(root: Path) -> dict:
    """`relpath -> sha256` for everything the plugin ships.

    The packager copies the plugin directory whole (measured 2026-08-23:
    357 files in the install cache against 357 shippable in the checkout,
    tests included), so the two trees are comparable file for file.
    """
    out = {}
    if not root or not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(s in rel for s in _SKIP):
            continue
        h = hashlib.sha256()
        try:
            h.update(p.read_bytes())
        except OSError:
            continue
        out[rel] = h.hexdigest()
    return out


def digest(root: Path) -> str | None:
    """One hash for a whole plugin tree, or None when there is no tree.

    WHY A VERSION NUMBER IS NOT ENOUGH, measured on this container within an
    hour of writing the version check: the repo published 0.8.2, the install
    was 0.8.2, and `compare` said OK — while three files differed, including
    the very rule a vetter agent needed to stop refusing packages. A plugin
    edited after its version was built is stale in the way that matters and
    invisible to every check that only reads a number.
    """
    files = tree_files(root)
    if not files:
        return None
    h = hashlib.sha256()
    for rel, fh in sorted(files.items()):
        h.update(f"{rel}\0{fh}\n".encode())
    return h.hexdigest()


def diverged_paths(a: Path, b: Path, limit: int = 6) -> list:
    """Which files differ, so the report is actionable rather than a hash."""
    fa, fb = tree_files(a), tree_files(b)
    out = [f"{p} (only in the checkout)" for p in sorted(set(fa) - set(fb))]
    out += [f"{p} (only in the install)" for p in sorted(set(fb) - set(fa))]
    out += [p for p in sorted(set(fa) & set(fb)) if fa[p] != fb[p]]
    return out[:limit]


def published(repo_root: Path | None = None) -> dict:
    """What this checkout publishes: version, and the component counts its
    own manifest declares.

    Two manifests carry the version — the marketplace entry the CLI reads
    when installing, and the plugin's own `plugin.json`. They are supposed
    to be the same number. When they are not, the install is ambiguous by
    construction, so that disagreement is reported rather than resolved
    here: picking one silently is how a plugin ships as two versions.
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    plugin_manifest = _load(root / "plugins" / PLUGIN_NAME /
                            ".claude-plugin" / "plugin.json")
    market = _load(root / ".claude-plugin" / "marketplace.json")
    entry = next((p for p in market.get("plugins", [])
                  if p.get("name") == PLUGIN_NAME), {})
    return {
        "version": plugin_manifest.get("version"),
        "marketplace_version": entry.get("version"),
        "agents": len(plugin_manifest.get("agents") or []),
        "skills": len([p for p in (root / "plugins" / PLUGIN_NAME /
                                   "skills").glob("*") if p.is_dir()])
        if (root / "plugins" / PLUGIN_NAME / "skills").is_dir() else 0,
        "manifest": str(root / "plugins" / PLUGIN_NAME /
                        ".claude-plugin" / "plugin.json"),
        "tree": str(root / "plugins" / PLUGIN_NAME),
        "digest": digest(root / "plugins" / PLUGIN_NAME),
    }


def _from_cli() -> dict:
    """`claude plugin list`, when the state file is unreadable. Human output,
    so it is a fallback and says so — the state file carries the install path
    and the commit, which this cannot."""
    exe = shutil.which("claude")
    if not exe:
        return {}
    try:
        proc = subprocess.run([exe, "plugin", "list"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    block = re.search(rf"{re.escape(PLUGIN_NAME)}@\S+\s*\n\s*Version:\s*(\S+)",
                      proc.stdout or "")
    return {"version": block.group(1), "source": "claude plugin list"} if block else {}


def session_started_at() -> float | None:
    """When THIS session's process began, as a POSIX timestamp, or None.

    The one fact that separates "the install is current" from "this session
    is running the current install". Everything else here reads the disk, and
    the disk changes the instant `claude plugin update` returns — but a
    session binds its agents, skills and hooks once, at start, from whatever
    the cache held then. Those two facts were conflated in this file's own
    guidance until 2026-08-23, when a session updated the plugin, re-ran this
    check inside the same firing, saw OK, and reported the note here as wrong
    because the update had "taken effect without a restart". Half right: the
    STATE FILE had. The session had not.

    `/proc/<pid>` is created when the process is, so its ctime is the start
    time. Absent /proc, or absent CLAUDE_PID (a CI runner, a non-Linux box),
    this returns None and the comparison is simply not made — an unknown
    start time must not manufacture either verdict.
    """
    pid = os.environ.get("CLAUDE_PID")
    if not pid or not pid.isdigit():
        return None
    try:
        return Path("/proc", pid).stat().st_ctime
    except OSError:
        return None


def _epoch(stamp: str | None) -> float | None:
    """An ISO-8601 install timestamp as POSIX seconds, or None."""
    if not stamp:
        return None
    try:
        import datetime as _dt                             # noqa: PLC0415
        return _dt.datetime.fromisoformat(
            stamp.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _stamp(epoch: float | None) -> str:
    """A POSIX timestamp back as UTC, so a reason line can be checked rather
    than believed."""
    if epoch is None:
        return "unknown"
    import datetime as _dt                                 # noqa: PLC0415
    return _dt.datetime.fromtimestamp(
        epoch, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled_state(paths=None) -> bool | None:
    """Whether the plugin is ENABLED, or None when no settings file says.

    Enablement is a separate fact from installation and lives in a separate
    file: `enabledPlugins["<plugin>@<marketplace>"]` in settings.json, user
    scope and project scope. True at either scope is enough — that is the
    scope the session loads from.

    None rather than False when nothing is readable, because "no settings
    file on this machine" is not "someone disabled the plugin", and a check
    that manufactured the second from the first would red-flag every CI
    runner and bare checkout.
    """
    seen = None
    for f in (paths if paths is not None else SETTINGS_FILES):
        block = (_load(Path(f)) or {}).get("enabledPlugins")
        if not isinstance(block, dict):
            continue
        v = block.get(f"{PLUGIN_NAME}@{MARKETPLACE_NAME}")
        if v is True:
            return True
        if v is False:
            seen = False
    return seen


# ── the loaded root: what the CLI actually bound ─────────────────────────
#
# MEASURED 2026-09-16, and it inverts the assumption every check here was
# built on. The CLI records what it INSTALLED in installed_plugins.json and
# keeps a copy under plugins/cache/<marketplace>/<plugin>/<version>. For a
# plugin whose marketplace is a DIRECTORY source with a relative plugin path
# — this repo: `.claude/settings.json` registers zennify-dma as the checkout
# and marketplace.json points at ./plugins/dma-insights — the CLI does not
# LOAD from that copy. It resolves the plugin against the marketplace
# directory and runs it in place: the connector process (mcp_proxy.py), every
# PreToolUse hook and the Agent roster all carried
# CLAUDE_PLUGIN_ROOT=<repo>/plugins/dma-insights while the record named a
# cache path that did not contain the agent the session was dispatching.
#
# The record is written once, when the environment's setup script runs, and
# the cloud environment snapshots the filesystem after that and restores the
# snapshot for every later session (documented: setup runs the first time,
# then is skipped until the script or network settings change or the cache
# expires, roughly seven days). The harness refreshes the checkout to the
# branch tip before the CLI starts. So the record froze at the version the
# snapshot was built from, the checkout moved, and a check that read the
# record called the session STALE every time — while the session was running
# exactly what the checkout published. Every `--heal` then rewrote a cache
# copy nothing loads from, on a disk discarded at session end, and the next
# session did it again. This section ends that loop: the root the session
# actually loaded is measured, and the record is reported as bookkeeping.
#
# Three measurements, in order of directness. Each is a fact about this
# container read at call time; none is an expectation about the CLI.


def _same_tree(a, b) -> bool:
    """Two paths naming one directory, symlinks and `..` resolved."""
    try:
        return bool(a) and bool(b) and Path(a).resolve() == Path(b).resolve()
    except (OSError, TypeError, ValueError):
        return False


def _env_root() -> dict | None:
    """Rung 1: this process was started by the CLI as part of the plugin
    (a hook, the connector, a child of either), so the CLI told it."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root and Path(root).is_dir():
        return {"root": root,
                "source": "CLAUDE_PLUGIN_ROOT (this process was started by "
                          "the CLI from the plugin it loaded)"}
    return None


def _recorded_root(path: Path | None = None) -> dict | None:
    """Rung 2: the SessionStart hook recorded the root it ran from.

    A Bash-run script (doctor.py, engine.cli start) has no
    CLAUDE_PLUGIN_ROOT, but the hook that opened its session did, and wrote
    it down keyed by the session id the hook event carries — which is the
    CLAUDE_CODE_SESSION_ID a Bash tool call sees. A record whose CLI process
    is gone describes a session that is over, and is not trusted for this
    one: the tree may have moved since.
    """
    target = Path(path) if path else LOADED_ROOT_FILE
    recs = (_load(target) or {}).get("records")
    if not isinstance(recs, list):
        return None
    recs = [r for r in recs if isinstance(r, dict) and r.get("root")]
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    pid = os.environ.get("CLAUDE_PID")

    def alive(r) -> bool:
        cp = str(r.get("cli_pid") or "")
        return cp.isdigit() and Path("/proc", cp).exists()

    mine = [r for r in recs if sid and r.get("session_id") == sid]
    if not mine and pid:
        mine = [r for r in recs if str(r.get("cli_pid")) == pid and alive(r)]
    pool = mine or [r for r in recs if alive(r)]
    if not pool:
        return None
    pool.sort(key=lambda r: str(r.get("recorded_at") or ""), reverse=True)
    r = pool[0]
    if not Path(r["root"]).is_dir():
        return None
    return {"root": r["root"], "record": r,
            "source": (f"{'this session' if mine else 'the newest live session'}"
                       f"'s {r.get('hook') or 'SessionStart'} hook, recorded "
                       f"{r.get('recorded_at')} in {target}")}


def _connector_process_root() -> dict | None:
    """Rung 3: the plugin's own connector process is alive for the whole
    session, and the CLI started it with CLAUDE_PLUGIN_ROOT set."""
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    marker = f"/{PLUGIN_NAME}/scripts/mcp_proxy.py"
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ")
        except OSError:
            continue
        if marker.encode() not in cmd:
            continue
        try:
            env = (p / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        for kv in env:
            if kv.startswith(b"CLAUDE_PLUGIN_ROOT="):
                root = kv.split(b"=", 1)[1].decode(errors="replace")
                if Path(root).is_dir():
                    return {"root": root,
                            "source": (f"the running connector process "
                                       f"(pid {p.name}, mcp_proxy.py), whose "
                                       f"CLAUDE_PLUGIN_ROOT the CLI set when "
                                       f"it started it")}
    return None


def loaded_root() -> dict | None:
    """The root this session's plugin actually runs from, or None when no
    measurement is available (a CI runner, a bare checkout, a laptop with
    no session up) — in which case the install record is all there is."""
    for probe in (_env_root, _recorded_root, _connector_process_root):
        try:
            hit = probe()
        except Exception:                                   # noqa: BLE001
            hit = None
        if hit:
            return hit
    return None


def record_loaded_root(event: dict | None = None,
                       path: Path | None = None) -> dict | None:
    """Called by the session hooks: write down the root THIS session loaded.

    The hook is the one place the fact is certain — the CLI set
    CLAUDE_PLUGIN_ROOT on it — and nothing else in the session can read that
    variable, so the hook leaves it where `_recorded_root()` looks. One
    record per session id, the newest eight kept (child sessions and
    `agent_run.py` dispatches open sessions of their own on the same
    machine). Fails open: a record that cannot be written costs nothing but
    this measurement, and the next rung still runs.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return None
    event = event if isinstance(event, dict) else {}
    import time                                                # noqa: PLC0415
    rec = {
        "session_id": event.get("session_id"),
        "hook": event.get("hook_event_name") or event.get("hookEventName"),
        "cli_pid": os.getppid(),
        "root": root,
        "realpath": str(Path(root).resolve()),
        "recorded_at": _stamp(time.time()),
    }
    target = Path(path) if path else LOADED_ROOT_FILE
    try:
        cur = (_load(target) or {}).get("records") or []
        cur = [r for r in cur if isinstance(r, dict)
               and r.get("session_id") != rec["session_id"]]
        cur.append(rec)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps({"records": cur[-8:]}, indent=1))
        tmp.replace(target)
    except OSError:
        return None
    return rec


def _tree_facts(root: Path) -> dict:
    """Agents, skills, declared agents and digest of one plugin tree."""
    agents = (len(list((root / "agents").rglob("*.md")))
              if (root / "agents").is_dir() else 0)
    skills = (len([p for p in (root / "skills").glob("*") if p.is_dir()])
              if (root / "skills").is_dir() else 0)
    declared = _load(root / ".claude-plugin" / "plugin.json")
    return {"agents": agents, "skills": skills,
            "declared_agents": len(declared.get("agents") or []),
            "declared_version": declared.get("version"),
            "digest": digest(root)}


def installed(state_path: Path | None = None) -> dict:
    """What the running session loads — version, root, and the components
    actually present in that root.

    The count is taken from the LOADED tree, never from the repo. A version
    number can match while the tree is short (a partial unpack, an
    interrupted update), and the roster is what the session dispatches
    against, so it is measured where the session reads it.

    Which tree is "loaded" is measured too (`loaded_root()`); the install
    record is consulted for the tree only when no measurement exists, and is
    otherwise reported beside the measurement as `record_version` and
    `record_path`, because the two disagreeing is the false alarm this file
    used to raise.
    """
    path = Path(state_path) if state_path else INSTALL_STATE
    state = _load(path)
    records = (state.get("plugins") or {}).get(
        f"{PLUGIN_NAME}@{MARKETPLACE_NAME}") or []
    live = loaded_root()
    if not records:
        exists = path.exists()
        if live:
            # No record, but a running session says which tree it loaded —
            # a --plugin-dir load, or a record wiped while the session ran.
            # The tree is what the session runs; report it.
            root = Path(live["root"])
            facts = _tree_facts(root)
            return {"version": facts.pop("declared_version"),
                    "state_file_exists": exists, "scope": None,
                    "install_path": str(root), "load_source": live["source"],
                    "record_version": None, "record_path": None,
                    "commit": None, "installed_at": None, "updated_at": None,
                    "session_started_at": session_started_at(),
                    "loaded_by_this_session": True, **facts,
                    "enabled": enabled_state(), "shadowed": [],
                    "state_file": str(path), "source": "loaded root"}
        # "No install state on this machine" and "installed, but not this
        # plugin" are different facts and must not collapse. A CI runner and
        # a bare checkout have no state file at all; there is no drift to
        # measure there and nothing is wrong. A state file that EXISTS and
        # does not list the plugin IS a defect — and the CLI is not consulted
        # in that case, because the file is the more specific truth and a
        # fallback that overrides it would paper over exactly that defect.
        fallback = {} if exists else _from_cli()
        return {"version": None, **fallback, "state_file": str(path),
                "state_file_exists": exists}
    # SEVERAL SCOPES CAN CARRY THE SAME PLUGIN, and a routine session hit
    # exactly that on 2026-08-23: user scope at 0.8.1, project scope still at
    # 0.6.2. It had to reason its way to "the project entry is probably a
    # stale duplicate, not what's loaded" — a guess, in the one place the
    # routine is supposed to be certain. So the extras are RETURNED, named
    # and counted, rather than quietly dropped by the max().
    best = max(records, key=lambda r: (_tuple(r.get("version")) or (0, 0, 0)))
    shadowed = [{"scope": r.get("scope"), "version": r.get("version")}
                for r in records if r is not best]
    record_path = Path(best.get("installPath") or "")
    began = session_started_at()
    if live:
        # THE MEASUREMENT WINS. The record says what was installed and where
        # the copy went; the session says what it runs. When they name
        # different trees the session is right by definition — it is the one
        # dispatching — and the record is reported beside it, not believed
        # over it.
        install_path = Path(live["root"])
        facts = _tree_facts(install_path)
        version = facts.pop("declared_version") or best.get("version")
        loaded_this = True
        load_source = live["source"]
    else:
        install_path = record_path
        facts = _tree_facts(install_path)
        facts.pop("declared_version", None)
        version = best.get("version")
        # `lastUpdated` moves on every update; `installedAt` is the first
        # install and stays put. The question here is "did the tree change
        # under a running session", so the later of the two answers it.
        changed_at = (_epoch(best.get("lastUpdated"))
                      or _epoch(best.get("installedAt")))
        loaded_this = None if (began is None or changed_at is None) \
            else changed_at <= began
        load_source = ("installed_plugins.json (no running session measured "
                       "— the record is all there is)")
    return {
        "version": version,
        "state_file_exists": True,
        "scope": best.get("scope"),
        "install_path": str(install_path) if install_path.name else None,
        "load_source": load_source,
        "record_version": best.get("version"),
        "record_path": str(record_path) if record_path.name else None,
        "commit": best.get("gitCommitSha"),
        "installed_at": best.get("installedAt"),
        "updated_at": best.get("lastUpdated") or best.get("installedAt"),
        "session_started_at": began,
        # True: this session runs the tree named (measured), or the install
        #       predates this session, so this session loaded it.
        # False: the tree changed after this session bound its agents.
        # None: no measurable session start — do not judge either way.
        "loaded_by_this_session": loaded_this,
        **facts,
        "enabled": enabled_state(),
        "shadowed": shadowed,
        "state_file": str(path),
        "source": "installed_plugins.json",
    }


#: The line that wires the setup script, quoted so a report can be acted on
#: without anyone going to look it up.
SETUP_CURL = (
    "curl -sfL https://raw.githubusercontent.com/mishleyotis/Accelerate/"
    "claude/dma-insights-onboarding-0ryrd0/plugins/dma-insights/scripts/"
    "bootstrap_session.sh | bash")


def provisioning(prov_path: Path | None = None) -> dict:
    """What happened BEFORE this session started, and whether the next
    session will differ.

    WHY THIS IS PART OF A VERSION CHECK. Every status below is a fact about
    one container, and the routines' answer to the two commonest ones —
    STALE and UPDATED_MID_SESSION — is "end the firing and let the next one
    pick it up". That answer is only true when the staleness was a one-off.
    When the container reproduces it, the next firing repeats the same three
    steps and the routine reports the same clean non-failure forever while
    producing nothing. Two synthesis lanes did exactly that, which is what
    this function exists to make sayable.

    The verdict has three shapes and they have different fixes:

      not_run        no record — the setup script did not run before this
                     session, so the plugin came from whatever the image or
                     a restored snapshot carried. RECURS every firing.
      stale_checkout it ran and could not bring the checkout to the branch
                     tip, and the checkout IS the marketplace, so it
                     installed an old plugin on purpose. RECURS every firing
                     until the checkout is fixed.
      ok             it ran and the checkout was current — a stale bind here
                     is a genuinely new fact, and ending the firing is the
                     right answer.
    """
    path = Path(prov_path) if prov_path else PROV_FILE
    rec = _load(path)
    if not rec:
        # AN ABSENT RECORD HAS TWO CAUSES AND THEY HAVE DIFFERENT FIXES, so
        # it is not reported as one. The setup script also lands the
        # service-account key and the connector path token beside this file;
        # if THOSE are present and this is not, the script ran — from a
        # revision built before it wrote a record. Saying "it did not run"
        # there sends someone to check a setting that is already correct,
        # which is the same class of mistake as the loop this diagnoses.
        siblings = [p.name for p in (path.parent / "sa.json",
                                     path.parent / "pathtok") if p.exists()]
        if siblings:
            return {
                "state": "not_run",
                "recurs": True,
                "record": str(path),
                "reason": (
                    f"no provisioning record at {path}, but "
                    f"{' and '.join(siblings)} are there — the setup script "
                    "DID run, from a revision that predates the record it "
                    "now writes. What it provisioned is therefore unknown, "
                    "including whether the checkout it installed the plugin "
                    "from was on this branch. THE NEXT FIRING WILL DO THE "
                    "SAME until the pinned revision moves"),
                "fix": ("re-point the Setup script in the claude.ai/code "
                        "environment settings at the current branch, so it "
                        "runs the version that resets the checkout before "
                        f"installing and records what it did:  {SETUP_CURL}"),
            }
        return {
            "state": "not_run",
            "recurs": True,
            "record": str(path),
            "reason": (
                "no provisioning record at "
                f"{path}, and neither the service-account key nor the path "
                "token is beside it — the environment setup script did not "
                "run before this session, so the plugin bound here came from "
                "the container image or a restored snapshot rather than from "
                "this branch. THE NEXT FIRING WILL DO THE SAME"),
            "fix": ("wire bootstrap_session.sh in the claude.ai/code "
                    "environment settings (Setup script), alongside the "
                    f"DMA_ROUTINE_SA_KEY_B64 variable:  {SETUP_CURL}"),
        }
    have, want = rec.get("plugin_installed"), rec.get("plugin_expected")
    if have and want and have != want:
        # The setup script ran, brought the checkout to the tip, tried the
        # install twice and STILL could not land the version the branch
        # ships. Nothing in the session can fix that, and every firing on
        # this image will reproduce it.
        return {
            "state": "stale_install",
            "recurs": True,
            "record": str(path),
            "reason": (
                f"the setup script ran at {rec.get('bootstrap_ran_at')} and "
                f"could not install the version the branch ships: it left "
                f"{have} installed where origin/{rec.get('branch')} ships "
                f"{want}, after a retry. The session bound {have}. THE NEXT "
                "FIRING WILL DO THE SAME"),
            "fix": ("the plugin install on this image is not taking the "
                    "update — check the setup script's log for the `claude "
                    "plugin update` step, and whether the container's plugin "
                    "cache is restored read-only or from a snapshot that "
                    "post-dates it"),
        }
    if rec.get("checkout_current") is False:
        return {
            "state": "stale_checkout",
            "recurs": True,
            "record": str(path),
            "reason": (
                f"the setup script ran at {rec.get('bootstrap_ran_at')} and "
                f"left the checkout OFF {rec.get('branch')} "
                f"({rec.get('checkout_state')}: {rec.get('checkout_note')}) "
                "— .claude/settings.json registers the marketplace as that "
                "directory, so the plugin was installed from a stale tree. "
                "THE NEXT FIRING WILL DO THE SAME"),
            "fix": (f"make {rec.get('repo_dir')} reach "
                    f"origin/{rec.get('branch')} before the session starts; "
                    "a working tree with local modifications is never reset "
                    "by the setup script, by design"),
        }
    # THE FOURTH STATE, and the one that was costing a firing a day.
    #
    # `ok` says the setup script ran, brought the checkout to the tip, and
    # installed the version it expected — all true, and all true LAST TIME
    # IT RAN. It says nothing about when that was. Measured 2026-08-31: a
    # firing's record was stamped 2026-08-27, four days before it fired, and
    # this container's was 17.8 hours old.
    #
    # WHY, established 2026-09-16 from the cloud-environment documentation
    # rather than inferred: a setup script runs the first time a session
    # starts in an environment, the filesystem is then SNAPSHOTTED, and every
    # later session starts from that snapshot with the setup step skipped —
    # until the script text or the network settings change, or the cache
    # expires after roughly seven days. There is no per-session mode. So the
    # install record and the cache copy are always the snapshot's, and an
    # old record is the environment working as designed, not a defect.
    #
    # Whether that MATTERS turns on one measured fact, which `compare()`
    # now reads before it ever gets here: which tree the session loads. This
    # CLI loads a directory-marketplace plugin in place from the checkout,
    # which the harness refreshes before the CLI starts, so the snapshot's
    # record is bookkeeping and this verdict is never reached. It is reached
    # only when the loaded root is the snapshot's cache copy — an older CLI,
    # or a marketplace that is not a directory — and then it does recur on
    # every session, because a new session restores the same snapshot.
    age = provisioning_age_h(rec)
    if age is not None and age > SNAPSHOT_AGE_H:
        return {
            "state": "stale_snapshot",
            "recurs": True,
            "record": str(path),
            "age_hours": round(age, 1),
            "reason": (
                f"the setup script ran {age:.0f} hours ago "
                f"({rec.get('bootstrap_ran_at')}) and installed "
                f"{rec.get('plugin_installed') or 'nothing'}. Setup runs "
                f"once per environment cache build and the filesystem is "
                f"snapshotted and restored for every later session, so this "
                f"container's install record and cache copy are that "
                f"snapshot's — {age:.0f} hours old by design. The session "
                f"is loading from that COPY rather than in place from the "
                f"checkout (the loaded root above is what says so), so every "
                f"session on this snapshot binds the plugin that was current "
                f"{age:.0f} hours ago: a fresh session does not fix it, and "
                f"neither does a heal, which repairs a disk the next session "
                f"does not keep"),
            "fix": ("rebuild the environment cache so the snapshot carries "
                    "the current install — edit the Setup script text in the "
                    "claude.ai/code environment settings (any change re-runs "
                    "it and re-snapshots), or wait for the cache to expire — "
                    "and check why this CLI is loading the cache copy instead "
                    "of the checkout in place (installed_plugins.json "
                    "installPath vs the loaded root); the durable state is "
                    "the in-place load, which needs no rebuild at all. Setup "
                    f"script line, for reference: {SETUP_CURL}"),
        }

    return {
        "state": "ok",
        "recurs": False,
        "record": str(path),
        "reason": (
            f"the setup script ran at {rec.get('bootstrap_ran_at')} with the "
            f"checkout at origin/{rec.get('branch')} and installed "
            f"{rec.get('plugin_installed') or 'nothing'} against an expected "
            f"{rec.get('plugin_expected') or 'unknown'}"),
        "fix": "",
    }


#: How old a provisioning record may be before the container it describes is
#: a RESTORED SNAPSHOT rather than a freshly provisioned machine. Setup that
#: runs per session leaves a record minutes old; two hours is far outside
#: that and far inside the days actually observed.
SNAPSHOT_AGE_H = 2.0


def provisioning_age_h(rec: dict) -> float | None:
    """Hours since the setup script ran, or None when it cannot be read."""
    began = _epoch(rec.get("bootstrap_ran_at"))
    if began is None:
        return None
    import time
    return max(0.0, (time.time() - began) / 3600.0)


UPDATE = (f"claude plugin marketplace update {MARKETPLACE_NAME} && "
          f"claude plugin update {PLUGIN_NAME}@{MARKETPLACE_NAME}")

#: The DIVERGED command, and it is deliberately not UPDATE. Measured on this
#: container 2026-08-31: with the checkout and the install both at 1.13.0 and
#: their trees differing, `plugin update` answered "already at the latest
#: version (1.13.0)" and `plugin install` answered "already installed" — both
#: exit 0, neither copying a byte. Uninstalling first took the same tree from
#: DIVERGED to OK in one pass.
REINSTALL = (f"claude plugin uninstall {PLUGIN_NAME}@{MARKETPLACE_NAME} "
             f"--scope user && claude plugin install "
             f"{PLUGIN_NAME}@{MARKETPLACE_NAME} --scope user && "
             f"claude plugin enable {PLUGIN_NAME}@{MARKETPLACE_NAME}")

#: Every install path ends here. A fresh install lands DISABLED by default
#: (the CLI says so on the way out), so an install that is not followed by an
#: enable leaves a container holding the right plugin and loading none of it.
ENABLE = f"claude plugin enable {PLUGIN_NAME}@{MARKETPLACE_NAME}"
#: WHAT AN UPDATE ACTUALLY DOES, and the correction that produced this text.
#: Until 2026-08-23 this note read "the update applies at NEXT session start,
#: so re-check there" — and a session that ran the update, re-checked in the
#: SAME firing and got OK reported the note as contradicted by observation.
#: Both halves were real, and they are about different things:
#:
#:   * The install cache and installed_plugins.json change IMMEDIATELY. This
#:     script reads exactly those, so re-running it in the same firing does
#:     work and does flip to OK. That is a true reading of the DISK.
#:   * Agents, skills, hooks and the MCP roster were bound when the session
#:     started, from whatever the cache held then. Those do NOT change. A
#:     session that began stale keeps dispatching the old agents no matter
#:     what the state file now says.
#:
#: So the re-check is worth running — it proves the install landed — and its
#: OK is not permission to produce. `loaded_by_this_session` is the field
#: that separates them, and it is measured, not assumed.
UPDATE_NOTE = (
    "then run this check again in the same firing — it reads the state file "
    "and the cache tree at call time, so it flips as soon as the install "
    "lands (or pass --heal and this script runs the update and the re-check "
    "itself, one command). The post-update verdict proves the DISK is "
    "current, not this session — bound agents, skills and hooks load once at "
    "start — which is RECOVERY MODE, not an ending: see that verdict's own "
    "instructions")

#: Said when the tree changed under a running session. THIS SENTENCE IS THE
#: ONE EVERY ROUTINE OBEYS, so it must prescribe the productive path itself:
#: it used to say "end the firing; the next session picks it up", and on
#: 2026-08-24 a firing whose PROMPT said to produce trusted this script's
#: freshly-read output over the stored prompt — reasonably, a prompt can be
#: stale or manipulated and this file cannot — and ended a healthy firing on
#: this sentence's say-so. Three firings that morning ended the same way and
#: the next container reproduced the state every time: the environment's
#: base snapshot carries the old install, so "the next session" inherits the
#: problem, never the fix. The script and the Routine prompts now say the
#: same thing, and where they ever disagree, THIS output is the current one.
SESSION_NOTE = (
    "the install on disk is correct and THIS SESSION IS NOT RUNNING IT: the "
    "tree changed after this session started, and agents, skills and hooks "
    "load once at start. THIS IS RECOVERY MODE, NOT AN ENDING — produce "
    "this firing anyway: dispatch every routed stage via `python3 "
    "plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file "
    "<file>` (fresh child processes bind the just-updated install at their "
    "own start, so they run the CURRENT agents where the in-process Agent "
    "tool would dispatch the stale roster this session bound), follow skill "
    "files from the current checkout rather than the Skill tool, and use "
    "the Routine-attached connectors normally — they are not plugin-bound. "
    "Report both versions and name RECOVERY MODE in the report. The one "
    "true ending is STALE that survives the update: a disk that will not "
    "come current. (Until 2026-08-24 this sentence said 'end the firing; "
    "the next session picks it up' — three firings ended on it that morning "
    "and the next container reproduced the state every time, because the "
    "environment's base snapshot carries the old install. Ending produces "
    "nothing and fixes nothing.)")


def compare(repo_root: Path | None = None,
            state_path: Path | None = None,
            prov_path: Path | None = None) -> dict:
    """The verdict, with the arithmetic shown. Statuses:

      OK              installed is what the repo publishes, and whole, and
                      this session is the one running it
      UPDATED_MID_SESSION
                      the DISK is correct and this session is not running it
                      — the tree changed after the session bound its agents
      MISSING         no plugin installed at all
      STALE           installed is older than published — the common case
      AHEAD           installed is newer than the checkout — the CHECKOUT is
                      the stale half; updating the plugin would downgrade it
      INCOMPLETE      versions agree, the packaged tree does not
      MANIFEST_SPLIT  the repo's two manifests publish different versions
      UNREADABLE      a version string that is not a version
    """
    pub, inst = published(repo_root), installed(state_path)
    pv, iv = _tuple(pub.get("version")), _tuple(inst.get("version"))
    mv = _tuple(pub.get("marketplace_version"))
    reasons: list[str] = []
    # IN PLACE: the tree the session runs IS the checkout's plugin directory.
    # Nothing can be stale between a tree and itself, whatever the install
    # record says — and the record saying something else is exactly the
    # recurring false alarm measured 2026-09-16 (see `loaded_root`).
    in_place = _same_tree(inst.get("install_path"), pub.get("tree"))
    inst["in_place"] = in_place

    if pv is None:
        status = "UNREADABLE"
        reasons.append(f"the repo manifest carries no readable version "
                       f"({pub['manifest']})")
    elif mv is not None and mv != pv:
        status = "MANIFEST_SPLIT"
        reasons.append(
            f"the repo publishes {pub['version']} in plugin.json and "
            f"{pub['marketplace_version']} in marketplace.json — an install "
            f"resolves one of them and nothing says which")
    elif in_place:
        status = "OK"
        note = (f"loaded IN PLACE from the checkout ({inst['install_path']}), "
                f"measured from {inst.get('load_source')}")
        rv = inst.get("record_version")
        if rv and rv != pub.get("version"):
            note += (f"; the install record says {rv} at "
                     f"{inst.get('record_path')}, which is the CLI's "
                     f"bookkeeping and not what it loads from — nothing to "
                     f"heal, and healing it changes nothing this session runs")
        reasons.append(note)
    elif iv is None and not inst.get("state_file_exists"):
        # Nothing to drift FROM. A CI runner and a bare checkout land here,
        # and neither is a defect: the repo-inventory rows already say
        # whether the checkout is whole.
        status = "NOT_INSTALLED"
        reasons.append(f"no plugin install on this machine "
                       f"({inst['state_file']} does not exist) — nothing to "
                       f"compare the checkout against")
    elif iv is None:
        status = "MISSING"
        reasons.append(f"no {PLUGIN_NAME} install recorded in "
                       f"{inst['state_file']}, which lists other plugins")
    elif iv < pv:
        status = "STALE"
        reasons.append(f"the session loads {inst['version']}, the repo "
                       f"publishes {pub['version']}")
    elif iv > pv:
        status = "AHEAD"
        reasons.append(f"the session loads {inst['version']}, newer than the "
                       f"{pub['version']} this checkout publishes — the "
                       f"checkout is behind, not the plugin")
    elif inst.get("declared_agents") and inst["agents"] != inst["declared_agents"]:
        status = "INCOMPLETE"
        reasons.append(f"{inst['version']} is installed but carries "
                       f"{inst['agents']} agent files where its own manifest "
                       f"declares {inst['declared_agents']}")
    elif (pub.get("digest") and inst.get("digest")
            and pub["digest"] != inst["digest"]):
        # Same number, different content. The version check's own blind spot,
        # found within an hour of writing it.
        status = "DIVERGED"
        changed = diverged_paths(Path(pub["tree"]), Path(inst["install_path"]))
        reasons.append(
            f"{pub['version']} is installed and {pub['version']} is published, "
            f"but the two trees differ — the plugin was edited after this "
            f"version was built. Differing: {', '.join(changed)}")
    elif inst.get("enabled") is False:
        # AFTER the tree checks and before the session check. A disabled
        # plugin loads nothing at all, which sounds like it should come
        # first — but the heal for a wrong tree (uninstall, install) lands
        # the plugin disabled anyway and re-enables it on the way out, so
        # naming the tree problem first is what gets both fixed in one pass.
        # Reached only once the tree is right, which is when "is it switched
        # on" is the whole remaining question.
        status = "DISABLED"
        reasons.append(
            f"{inst['version']} is installed at {inst.get('scope')} scope and "
            f"matches the checkout, but enabledPlugins says it is switched "
            f"off — the session loads none of its {inst.get('agents', 0)} "
            f"agents, {inst.get('skills', 0)} skills or its connector. A "
            f"fresh `claude plugin install` lands disabled by default, so "
            f"this is the state an install leaves behind when nothing "
            f"enables it")
    elif inst.get("loaded_by_this_session") is False:
        # LAST, deliberately. Every branch above is a disagreement about what
        # is ON DISK, and those are worse: a session running a stale tree that
        # the disk also disagrees with needs the disk fixed first. This branch
        # is only reached once the disk is right, which is exactly when the
        # remaining question is whether this session is running it.
        status = "UPDATED_MID_SESSION"
        reasons.append(
            f"{inst['version']} on disk matches the checkout, but the install "
            f"was last written {inst.get('updated_at')} and this session's "
            f"process started {_stamp(inst.get('session_started_at'))} — the "
            f"tree changed under a running session, which loaded its agents, "
            f"skills and hooks before that and does not reload them")
    else:
        status = "OK"

    if status == "STALE" and inst.get("agents") and pub.get("agents"):
        reasons.append(f"the session dispatches against {inst['agents']} "
                       f"agents; {pub['version']} carries {pub['agents']}")
    # Reported at every status, including OK: a shadowed record is not a
    # failure — the highest version is what loads — but leaving it unnamed is
    # what made a session spend a paragraph guessing about it.
    for extra in inst.get("shadowed") or []:
        reasons.append(f"also recorded: {extra['version']} at "
                       f"{extra['scope']} scope — shadowed by the "
                       f"{inst.get('scope')}-scope {inst['version']} that "
                       f"loads, and safe to ignore")

    fix = ""
    if status in ("STALE", "MISSING", "INCOMPLETE"):
        fix = f"{UPDATE}  ({UPDATE_NOTE})"
    elif status == "UPDATED_MID_SESSION":
        fix = f"nothing to install — {SESSION_NOTE}"
    elif status == "DIVERGED":
        fix = (REINSTALL + "  (measured 2026-08-31: `plugin update` and "
               "`plugin install` both short-circuit on an equal version "
               "number — 'already at the latest version' — so only an "
               "uninstall first replaces the tree. The version number then "
               "describes contents it was not built from, which is why the "
               "durable fix is still to bump it in BOTH manifests)")
    elif status == "DISABLED":
        fix = ENABLE
    elif status == "AHEAD":
        fix = ("pull the branch — the checkout, not the plugin, is what needs "
               "to move")
    elif status == "MANIFEST_SPLIT":
        fix = ("set the same version in both .claude-plugin/marketplace.json "
               "and plugins/dma-insights/.claude-plugin/plugin.json")
    # WHY THE DRIFT HAPPENED, not just that it did. Only asked when there IS
    # drift: on a healthy container the provisioning record is noise, and a
    # check that narrates a working machine trains people to skim it.
    prov = provisioning(prov_path)
    if status in ("STALE", "MISSING", "INCOMPLETE", "UPDATED_MID_SESSION",
                  "DIVERGED", "DISABLED"):
        reasons.append(f"cause: {prov['reason']}")
        if prov["recurs"]:
            # The correction that matters. Both prompts and this script have
            # told sessions that ending the firing hands the problem to the
            # next one; when provisioning reproduces the state, that is false
            # and the routine loops reporting a clean non-failure.
            reasons.append(
                "ENDING THE FIRING WILL NOT FIX THIS — the next container "
                "reproduces the same state, so every following firing "
                "repeats this verdict and produces nothing. This is a "
                "provisioning defect to report, not a transient to wait out")

    # UPDATED_MID_SESSION is deliberately NOT ok. The install is fine and the
    # session is not, and the caller's next act — produce, or end the firing —
    # depends on the session, not the disk. An exit 0 there would send a
    # routine to work on the very agents it was trying to stop using.
    return {"status": status, "ok": status in ("OK", "NOT_INSTALLED"),
            "reasons": reasons, "fix": fix, "published": pub,
            "installed": inst, "provisioning": prov}


def summary(verdict: dict) -> str:
    """One line, quotable into a routine report."""
    pub, inst = verdict["published"], verdict["installed"]
    tail = " — loaded in place from the checkout" if inst.get("in_place") else ""
    return (f"{verdict['status']}: installed {inst.get('version') or 'none'} "
            f"({inst.get('agents', 0)} agents) vs published "
            f"{pub.get('version') or 'unreadable'} ({pub.get('agents', 0)} agents)"
            f"{tail}")


#: What each healable status actually needs run, as data. Split because the
#: commands are NOT interchangeable — see REINSTALL: an update is a no-op on
#: a tree that diverged without a version bump, and an install is a no-op on
#: a plugin already recorded at that version. Every path ends in ENABLE,
#: because an install lands the plugin switched off. The placeholders are
#: filled by `_plan_for`, which records why the scope is what it is.
_HEAL_PLAN: dict[str, tuple[tuple[str, ...], ...]] = {
    "STALE": (
        ("claude", "plugin", "marketplace", "update", MARKETPLACE_NAME),
        ("claude", "plugin", "update", "{plugin}", "--scope", "{scope}"),
        ("claude", "plugin", "install", "{plugin}", "--scope", "{scope}"),
        ("claude", "plugin", "enable", "{plugin}", "--scope", "{scope}"),
    ),
    "DIVERGED": (
        ("claude", "plugin", "marketplace", "update", MARKETPLACE_NAME),
        ("claude", "plugin", "uninstall", "{plugin}", "--scope", "{scope}"),
        ("claude", "plugin", "install", "{plugin}", "--scope", "{scope}"),
        ("claude", "plugin", "enable", "{plugin}", "--scope", "{scope}"),
    ),
    "DISABLED": (
        ("claude", "plugin", "enable", "{plugin}", "--scope", "{scope}"),
    ),
}
_HEAL_PLAN["MISSING"] = _HEAL_PLAN["STALE"]
_HEAL_PLAN["INCOMPLETE"] = _HEAL_PLAN["DIVERGED"]   # a short tree, same cure


def _plan_for(verdict: dict) -> list:
    """The healable status's commands, bound to the plugin identifier.

    WHY EVERY COMMAND SAYS `--scope user`, measured on a live container
    2026-08-31 rather than assumed:

    * All scopes share ONE cache directory —
      `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>` — keyed by
      version, not by scope. Scope is a registration, not a copy. So a
      user-scope uninstall releases the tree the project-scope record also
      points at, and the following install re-copies it for both. That is
      what took this container from DIVERGED to OK.
    * `install --scope project` records `projectPath` as the CURRENT WORKING
      DIRECTORY. Run from anywhere but the repo root it writes a third,
      wrong registration — observed, then cleaned up by hand. A repair must
      not depend on where it was invoked from.
    * `enable` and `uninstall` exit 1 for "already enabled" and "not
      installed at this scope". Those are the states the repair wants, so
      the exit codes are logged and never treated as a failure; the re-check
      afterwards is what judges the outcome.

    bootstrap_session.sh installs at user scope for the same reasons.
    """
    plan = _HEAL_PLAN.get(verdict["status"])
    if not plan:
        return []
    ident = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
    return [[a.format(plugin=ident, scope="user") for a in argv]
            for argv in plan]


def heal(verdict: dict) -> tuple:
    """Run the repair this verdict prescribes, then let the caller re-measure.

    THE SELF-HEALING LOOP (owner, 2026-08-24: "It should be a self healing
    loop"; again 2026-08-31: "Plugin version should always pick the most
    recent bump and self heal"). Before this, a stale verdict printed a
    command and left a judgment point: the session had to choose to run it,
    choose to re-check, and choose what the re-check's answer meant — and
    every one of those choices was made wrongly at least once in a single
    morning. --heal collapses them: the check runs the repair itself, and
    hands back ONE final verdict whose fix text already says what to do.

    WHAT EACH STATUS NEEDS IS DIFFERENT, and running the wrong commands
    looks exactly like running the right ones — every command here exits 0
    whether or not it copied anything. Measured on a live container
    2026-08-31, with the checkout and the install both at 1.13.0 and their
    trees differing:

        plugin update  -> exit 0, "already at the latest version (1.13.0)"
        plugin install -> exit 0, "already installed (scope: user)"
        AFTER: still DIVERGED, not one byte replaced

        plugin uninstall -> exit 0
        plugin install   -> exit 0, "This plugin is disabled by default"
        AFTER: OK — and switched off

    So DIVERGED reinstalls rather than updates, and EVERY path ends with an
    enable. That last line is why the plan is a table: an earlier heal ran
    `install` on a MISSING container and left it holding a complete, current
    plugin that loaded nothing, which every version check called OK.

    The commands mutate only this container's local install cache (~/.claude
    on an ephemeral VM); the marketplace is the repo checkout on this disk.
    Returns (final_verdict, heal_log_lines) — (None, log) when something ran
    and the caller must re-measure, (verdict, log) when nothing could.
    """
    plan = _plan_for(verdict)
    if not plan:
        return verdict, []
    log = []
    for argv_ in plan:
        try:
            r = subprocess.run(argv_, capture_output=True, text=True,
                               timeout=180)
            log.append(f"heal: {' '.join(argv_[1:4])} -> exit {r.returncode}")
        except OSError as exc:
            # No claude CLI is a result to report, not a crash: the caller
            # sees the unchanged verdict and its provisioning cause.
            log.append(f"heal: {argv_[0]} unavailable ({exc})")
            return verdict, log
        except subprocess.TimeoutExpired:
            log.append(f"heal: {' '.join(argv_[1:4])} timed out")
    return None, log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=None,
                    help="the checkout to read as the source of truth "
                         "(default: the one this script lives in)")
    ap.add_argument("--state", default=None,
                    help="path to installed_plugins.json (default: the CLI's)")
    ap.add_argument("--provisioning", default=None,
                    help="path to the setup script's provisioning record "
                         "(default: beside the service-account key)")
    ap.add_argument("--heal", action="store_true",
                    help="on STALE/MISSING/INCOMPLETE/DIVERGED/DISABLED, run "
                         "the repair that status needs (container-local "
                         "install cache only) and re-check, printing one "
                         "final verdict")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    v = compare(a.repo_root, a.state, a.provisioning)
    if a.heal:
        healed, heal_log = heal(v)
        if healed is None:                    # update ran — re-measure
            pre = summary(v)
            v = compare(a.repo_root, a.state, a.provisioning)
            v.setdefault("reasons", []).insert(0, f"before --heal: {pre}")
            v["reasons"][1:1] = heal_log
        elif heal_log:                        # heal attempted, could not run
            v.setdefault("reasons", []).extend(heal_log)
    if a.json:
        print(json.dumps(v, indent=1))
    else:
        print(summary(v))
        for r in v["reasons"]:
            print(f"  - {r}")
        if v["fix"]:
            print(f"  -> {v['fix']}")
        # LAST AND SEPARATE, because it is a different kind of instruction:
        # everything above is for the session, this is for whoever owns the
        # environment. Folding it into `fix` produced one unreadable line
        # ending in nested parentheses, and the part that recurs every firing
        # was buried in the middle of it.
        # Only on a verdict that is NOT ok. An old provisioning record is
        # the cloud environment's snapshot working as designed; it becomes a
        # cause only when the session is loading the snapshot's copy, which
        # is what the verdict above has already judged.
        prov = v.get("provisioning") or {}
        if not v["ok"] and prov.get("recurs") and prov.get("fix"):
            print(f"  => ROOT CAUSE, RECURS EVERY FIRING: {prov['fix']}")
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
