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
SHOULD be loaded; what IS loaded is MEASURED from the session itself
(`bound_root`: CLAUDE_PLUGIN_ROOT in a hook, the session's own connector
process, the SessionStart record), with `~/.claude/plugins/installed_plugins.json`
plus the cache directory as the fallback and the record of what the CLI
installed; every number is read from one of those at call time.

  4. (2026-09-16) The record is not the session. On a `directory`
     marketplace the CLI loads the plugin from the checkout IN PLACE, and
     the versioned cache copy the record names is not what runs. A record
     restored from a five-day-old snapshot said 1.19.0/73 while the
     session had bound 1.20.0/74 — and every caller of `compare()`,
     reading the record, refused work and went into recovery mode against
     a stale roster the session did not have.

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

#: Where the SessionStart hook records the tree THIS session bound — one
#: file per session process, beside the provisioning record. See
#: `bound_root` for why a record is needed at all and why it is keyed by pid.
BOUND_DIR = Path(os.environ.get("DMA_BOUND_PLUGIN_DIR", str(PROV_FILE.parent)))

#: The components a session reads ONCE, at start, and never reloads: agents,
#: hooks, commands, the manifest, the MCP definition and the skill entry
#: files. Scripts under `scripts/` and the rest of a skill are read when they
#: are invoked, so a change to them reaches a running session and is not a
#: mid-session bind problem. `bound_components_changed_at` reads exactly this
#: set, which is what keeps a `__pycache__` write or a test fixture from
#: reading as "the roster moved under the session".
BOUND_AT_START = ("agents", "hooks", "commands", ".claude-plugin", ".mcp.json")

#: How long after the session process is created a component write still
#: counts as provisioning rather than a mid-session change. Measured
#: 2026-09-16 on a cloud container: the checkout's HEAD was written 34 ms
#: BEFORE the session process existed (the harness clones, then launches), so
#: the true margin is tens of milliseconds and positive; a `git pull` inside a
#: session cannot land before the model's first turn, seconds later at the
#: earliest. Two seconds separates the two by two orders of magnitude.
MID_SESSION_GRACE_S = 2.0

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


def _plugin_root_of(path) -> Path | None:
    """`path` as a root of THIS plugin, or None.

    A root is a directory holding `.claude-plugin/plugin.json` whose `name`
    is PLUGIN_NAME. The name check is not pedantry: CLAUDE_PLUGIN_ROOT is per
    plugin — another plugin's hook or MCP server carries ITS root, not ours
    (measured 2026-09-16 with a probe plugin whose SessionStart hook printed
    its own directory).
    """
    if not path:
        return None
    try:
        p = Path(str(path)).resolve()
    except (OSError, RuntimeError):
        return None
    manifest = _load(p / ".claude-plugin" / "plugin.json")
    return p if manifest.get("name") == PLUGIN_NAME else None


def _environ_of(pid) -> dict:
    """Another process's environment, from /proc — {} when unreadable."""
    try:
        raw = Path("/proc", str(pid), "environ").read_bytes()
    except OSError:
        return {}
    out = {}
    for item in raw.split(b"\0"):
        key, sep, val = item.partition(b"=")
        if sep:
            out[key.decode("utf-8", "replace")] = val.decode("utf-8", "replace")
    return out


def _ppid_of(pid) -> int | None:
    try:
        for line in Path("/proc", str(pid), "status").read_text().splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _proc_candidates() -> list:
    """(pid, ppid, CLAUDE_PLUGIN_ROOT) for every readable process carrying
    the variable. Overridable in tests; reads /proc for real."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return []
    out = []
    for name in names:
        if not name.isdigit():
            continue
        root = _environ_of(name).get("CLAUDE_PLUGIN_ROOT")
        if root:
            out.append((int(name), _ppid_of(name), root))
    return out


def _bound_record_path(pid) -> Path:
    return BOUND_DIR / f"bound_plugin-{pid}.json"


def record_bound_root(plugin_root, pid: str | None = None,
                      session_id: str | None = None) -> Path | None:
    """Write, from inside a plugin hook, which tree THIS session bound.

    Called by the SessionStart hook, which runs with CLAUDE_PLUGIN_ROOT in its
    environment and is itself a file inside the bound tree. Keyed by the
    session's process id and stamped, so a record left in a restored
    snapshot by an earlier container's session — pids repeat across
    containers — is rejected by `bound_root`, which requires the record to
    postdate this process. Returns the path written, or None (fail open:
    a hook that cannot write a breadcrumb must not cost the session).
    """
    pid = pid if pid is not None else os.environ.get("CLAUDE_PID")
    if not pid or not str(pid).isdigit():
        return None
    root = _plugin_root_of(plugin_root)
    if root is None:
        return None
    import time                                             # noqa: PLC0415
    rec = {"pid": int(pid),
           "session_id": session_id or os.environ.get("CLAUDE_CODE_SESSION_ID"),
           "plugin_root": str(root),
           "recorded_at": time.time(),
           "process_started_at": session_started_at()}
    path = _bound_record_path(pid)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec))
        tmp.replace(path)
    except OSError:
        return None
    return path


def bound_root(session_pid: str | None = None) -> dict:
    """The plugin tree THIS session actually loaded — MEASURED, never read off
    the install record.

    WHY THE RECORD IS NOT THE ANSWER, measured 2026-09-16 on a cloud
    container (Claude Code 2.1.273): `installed_plugins.json` recorded 1.19.0
    at `~/.claude/plugins/cache/.../1.19.0` (73 agents), restored from a
    five-day-old snapshot, while the checkout published 1.20.0 (74). Every
    caller of `compare()` said STALE, the SessionStart hook told the session
    it was "NOT running what the checkout publishes", research and scoring
    work was refused, and the firing went into RECOVERY MODE — dispatching
    every stage through child processes to escape a stale roster. The
    session's own connector process carried
    `CLAUDE_PLUGIN_ROOT=/home/user/Accelerate/plugins/dma-insights`: it had
    bound the CHECKOUT, in place, all 74 agents. For a marketplace registered
    as a `directory` source the CLI loads the plugin from that directory and
    the versioned cache copy the record names is not what runs. The record
    was five days behind; the session was not. Everything downstream — the
    refusals, the heal, the recovery mode, the "restored snapshot"
    diagnosis — was built on reading the wrong tree, which is the same
    mistake this file was written to remove from the doctor in August.

    So the bind is measured, from evidence the CLI itself produces:

      env       CLAUDE_PLUGIN_ROOT in THIS process's environment. The CLI
                exports it to hook, MCP and LSP subprocesses, so a hook
                (session_brief.py) measures its own session directly.
      process   a plugin subprocess the session process spawned directly —
                the connector's mcp_proxy.py runs for the session's whole
                life with the variable in its environment, and its parent is
                CLAUDE_PID. Direct children only: a child `claude -p` session
                started after a heal binds a different tree, and its MCP
                server must not answer for the parent.
      record    what the SessionStart hook wrote for this pid, if it
                postdates this process (snapshots carry old records).

    Filtered to THIS plugin by manifest name at every rung. Unmeasured is
    reported as unmeasured — with the reason — never manufactured from the
    record: {"path": None, "source": None, "reason": ...}.
    """
    pid = session_pid if session_pid is not None else os.environ.get("CLAUDE_PID")
    env_root = _plugin_root_of(os.environ.get("CLAUDE_PLUGIN_ROOT"))
    if env_root is not None:
        return {"path": str(env_root), "source": "env",
                "reason": "CLAUDE_PLUGIN_ROOT in this process's environment "
                          "(the CLI exports it to plugin hooks and servers)"}
    why = ["CLAUDE_PLUGIN_ROOT is not in this process's environment (only "
           "a plugin's hook and MCP subprocesses carry it)"]
    if not pid or not str(pid).isdigit():
        why.append("CLAUDE_PID is unset — not inside a Claude Code session, "
                   "so there is no bind to measure")
        return {"path": None, "source": None, "reason": "; ".join(why)}
    pid_i = int(pid)
    direct = []
    for cpid, ppid, root in _proc_candidates():
        r = _plugin_root_of(root)
        if r is not None and ppid == pid_i:
            direct.append(str(r))
    if direct:
        out = {"path": direct[0], "source": "process",
               "reason": f"CLAUDE_PLUGIN_ROOT of a plugin subprocess that "
                         f"session process {pid_i} spawned"}
        if len(set(direct)) > 1:
            out["reason"] += (f"; NOTE: {len(set(direct))} different roots "
                              f"among them: {sorted(set(direct))}")
        return out
    why.append(f"no plugin subprocess of session process {pid_i} is readable "
               f"in /proc (the connector's mcp_proxy.py did not start, or "
               f"/proc is not this user's to read)")
    rec = _load(_bound_record_path(pid_i))
    began = session_started_at()
    if rec.get("pid") == pid_i and rec.get("plugin_root"):
        stamp = rec.get("recorded_at")
        fresh = (isinstance(stamp, (int, float)) and began is not None
                 and stamp >= began - MID_SESSION_GRACE_S)
        r = _plugin_root_of(rec.get("plugin_root")) if fresh else None
        if r is not None:
            return {"path": str(r), "source": "record",
                    "reason": f"the SessionStart hook's record for pid {pid_i} "
                              f"({_bound_record_path(pid_i)})"}
        why.append(f"a record for pid {pid_i} exists but "
                   + ("predates this process — left by an earlier container "
                      "that reused the pid (a restored snapshot carries "
                      "old records), so it is not this session's"
                      if not fresh else
                      "names a tree that is not this plugin's root any more"))
    else:
        why.append(f"no SessionStart record at {_bound_record_path(pid_i)} — "
                   f"the plugin's hook did not run, or ran from a revision "
                   f"before it wrote one")
    return {"path": None, "source": None, "reason": "; ".join(why)}


def bound_components_changed_at(root: Path) -> float | None:
    """When the parts a session binds at start last changed, or None.

    Reads only BOUND_AT_START plus each skill's SKILL.md — the files the CLI
    reads once. A tree loaded in place (a checkout) is written to constantly
    by things that do not change the roster: `__pycache__`, run logs, a test
    fixture. Measuring the whole tree would call each of those a mid-session
    rebind; measuring these files measures the claim actually being made.
    """
    root = Path(root)
    latest = None
    candidates = [root / part for part in BOUND_AT_START]
    skills = root / "skills"
    if skills.is_dir():
        candidates += [p / "SKILL.md" for p in skills.iterdir() if p.is_dir()]
    for c in candidates:
        if not c.exists():
            continue
        files = [c] if c.is_file() else [p for p in c.rglob("*") if p.is_file()]
        for f in files:
            rel = f.as_posix()
            if any(sk in rel for sk in _SKIP):
                continue
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            latest = m if latest is None else max(latest, m)
    return latest


def _under_plugin_cache(path) -> bool:
    """Whether `path` is a copy in the CLI's versioned plugin cache — the
    tree `claude plugin update` rewrites — as opposed to a tree loaded in
    place, which an update does not touch."""
    cache = Path(os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
                 or (Path(os.environ.get("CLAUDE_CONFIG_DIR",
                                         Path.home() / ".claude")) / "plugins"))
    try:
        Path(str(path)).resolve().relative_to(cache.resolve())
        return True
    except (ValueError, OSError):
        return False


def installed(state_path: Path | None = None) -> dict:
    """What the running session loads — version, install path, and the
    components actually present in that path.

    THE TREE IS THE ONE THE SESSION BOUND, measured by `bound_root`, and the
    install record is consulted for what it is: a record. Until 2026-09-16
    this read the record's `installPath` and counted THAT tree, which is the
    cache copy — and on a `directory` marketplace the CLI does not load the
    cache copy, it loads the checkout in place. The record was five days
    stale, the session was current, and every verdict built here said the
    opposite (see `bound_root`). Where the bind cannot be measured — a CI
    runner, a workstation shell — the record is what there is, and the
    result says so in `bound_reason` rather than dressing the record up as
    the session.

    The count is taken from the tree that runs, never from the repo. A
    version number can match while the packaged tree is short (a partial
    unpack, an interrupted update), and the roster is what the session
    dispatches against, so it is measured where the session reads it.
    """
    path = Path(state_path) if state_path else INSTALL_STATE
    state = _load(path)
    records = (state.get("plugins") or {}).get(
        f"{PLUGIN_NAME}@{MARKETPLACE_NAME}") or []
    bound = bound_root()
    bound_path = Path(bound["path"]) if bound.get("path") else None
    if not records and bound_path is None:
        exists = path.exists()
        # "No install state on this machine" and "installed, but not this
        # plugin" are different facts and must not collapse. A CI runner and
        # a bare checkout have no state file at all; there is no drift to
        # measure there and nothing is wrong. A state file that EXISTS and
        # does not list the plugin IS a defect — and the CLI is not consulted
        # in that case, because the file is the more specific truth and a
        # fallback that overrides it would paper over exactly that defect.
        fallback = {} if exists else _from_cli()
        return {"version": None, **fallback, "state_file": str(path),
                "state_file_exists": exists,
                "bound_path": None, "bound_source": None,
                "bound_reason": bound.get("reason"), "in_place": False}
    # SEVERAL SCOPES CAN CARRY THE SAME PLUGIN, and a routine session hit
    # exactly that on 2026-08-23: user scope at 0.8.1, project scope still at
    # 0.6.2. It had to reason its way to "the project entry is probably a
    # stale duplicate, not what's loaded" — a guess, in the one place the
    # routine is supposed to be certain. So the extras are RETURNED, named
    # and counted, rather than quietly dropped by the max().
    best = max(records, key=lambda r: (_tuple(r.get("version")) or (0, 0, 0))) \
        if records else {}
    shadowed = [{"scope": r.get("scope"), "version": r.get("version")}
                for r in records if r is not best]
    install_path = Path(best.get("installPath") or "")
    try:
        record_tree = install_path.resolve() if install_path.name else None
    except (OSError, RuntimeError):
        record_tree = None
    # IN PLACE: the session binds a tree that is not the record's copy (or
    # there is no record at all). Then the record's version, timestamps and
    # cache tree describe something this session does not run.
    in_place = bound_path is not None and bound_path != record_tree
    tree = bound_path if bound_path is not None else install_path
    agents = (len(list((tree / "agents").rglob("*.md")))
              if (tree / "agents").is_dir() else 0)
    skills = (len([p for p in (tree / "skills").glob("*") if p.is_dir()])
              if (tree / "skills").is_dir() else 0)
    declared = _load(tree / ".claude-plugin" / "plugin.json")
    began = session_started_at()
    if in_place:
        version = declared.get("version")
        # The question "did the tree change under a running session" is
        # asked of the components the session reads once, not of a record
        # that describes a copy it does not load.
        changed_at = bound_components_changed_at(tree)
        loaded_this = None if (began is None or changed_at is None) \
            else changed_at <= began + MID_SESSION_GRACE_S
        updated_at = _stamp(changed_at) if changed_at is not None else None
    else:
        version = best.get("version")
        # `lastUpdated` moves on every update; `installedAt` is the first
        # install and stays put. The question here is "did the tree change
        # under a running session", so the later of the two is the one that
        # answers it.
        changed_at = _epoch(best.get("lastUpdated")) or _epoch(best.get("installedAt"))
        loaded_this = None if (began is None or changed_at is None) \
            else changed_at <= began
        updated_at = best.get("lastUpdated") or best.get("installedAt")
    return {
        "version": version,
        "state_file_exists": path.exists(),
        "scope": best.get("scope"),
        "install_path": str(install_path) if install_path.name else None,
        "commit": best.get("gitCommitSha"),
        "installed_at": best.get("installedAt"),
        "updated_at": updated_at,
        "tree_changed_at": changed_at,
        "session_started_at": began,
        # True: the bound tree predates this session, so this session loaded
        # it. False: it changed after this session bound its agents.
        # None: no measurable session start — do not judge either way.
        "loaded_by_this_session": loaded_this,
        "agents": agents,
        "skills": skills,
        "declared_agents": len(declared.get("agents") or []),
        "digest": digest(tree),
        "enabled": enabled_state(),
        "shadowed": shadowed,
        "state_file": str(path),
        "source": ("bound tree" if in_place else "installed_plugins.json"),
        # The bind, and how it was measured — or why it was not.
        "bound_path": str(bound_path) if bound_path is not None else None,
        "bound_source": bound.get("source"),
        "bound_reason": bound.get("reason"),
        "in_place": in_place,
        "record_version": best.get("version"),
    }


#: The line that wires the setup script, quoted so a report can be acted on
#: without anyone going to look it up.
SETUP_CURL = (
    "curl -sfL https://raw.githubusercontent.com/mishleyotis/Accelerate/"
    "claude/dma-insights-onboarding-0ryrd0/plugins/dma-insights/scripts/"
    "bootstrap_session.sh | bash")


def provisioning(prov_path: Path | None = None,
                 in_place: bool | None = None) -> dict:
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
    # this container's was 17.8 hours old. Setup runs when the environment's
    # SNAPSHOT is built, not at session start, so every session on that
    # image inherits whatever plugin was current whenever setup last ran.
    #
    # Under the old `ok` the report said a stale bind here "is a genuinely
    # new fact, and ending the firing is the right answer". For a restored
    # snapshot that is precisely backwards: it recurs on every session until
    # the environment changes, which is the livelock this function exists to
    # name. It is also why opening a FRESH SESSION does not reliably help —
    # the staleness is in the image, not the session, so a new session on
    # the same image binds the same old roster.
    age = provisioning_age_h(rec)
    if age is not None and age > SNAPSHOT_AGE_H and in_place:
        # THE SNAPSHOT IS REAL AND THE ROSTER IS NOT SHORT. Measured
        # 2026-09-16: a record 119 hours old, the cache copy at 1.19.0, and
        # the session bound the checkout — cloned fresh for this session —
        # in place, at 1.20.0. The snapshot's age describes the install
        # RECORD and the credentials the setup script landed (which the
        # connector's own auth helper re-lands at session start). It does
        # not describe what this session runs. Saying "the roster binds
        # short" here was the false diagnosis every firing acted on.
        return {
            "state": "snapshot_record_only",
            "recurs": False,
            "record": str(path),
            "age_hours": round(age, 1),
            "reason": (
                f"the setup script ran {age:.0f} hours ago "
                f"({rec.get('bootstrap_ran_at')}) — this container is a "
                f"RESTORED SNAPSHOT (Claude Code on the web runs the setup "
                f"script once, snapshots the filesystem, and reuses the "
                f"snapshot until the script or the allowed hosts change or "
                f"about seven days pass). The install RECORD is that old; "
                f"the session is not: it binds the checkout in place, and "
                f"the checkout is cloned fresh for every session"),
            "fix": "",
        }
    if age is not None and age > SNAPSHOT_AGE_H:
        return {
            "state": "stale_snapshot",
            "recurs": True,
            "record": str(path),
            "age_hours": round(age, 1),
            "reason": (
                f"the setup script ran {age:.0f} hours ago "
                f"({rec.get('bootstrap_ran_at')}) and installed "
                f"{rec.get('plugin_installed') or 'nothing'}. A container "
                f"that provisions at session start carries a record minutes "
                f"old, so this one is a RESTORED SNAPSHOT: setup is not "
                f"re-running per session, and every session on this image "
                f"begins on the plugin that was current {age:.0f} hours ago. "
                f"That is why the roster binds short and why a fresh session "
                f"on the same image does not fix it"),
            # NOT "run the setup script at session start": Claude Code on the
            # web does not offer that — the setup script runs once, the
            # filesystem is snapshotted, and the snapshot is reused (rebuilt
            # when the script or the allowed hosts change, or after about
            # seven days). This line prescribed an impossible setting for
            # two weeks. The reachable fixes are the two below.
            "fix": ("the setup script runs ONCE per environment snapshot, so "
                    "it cannot refresh the cache copy per session. Either "
                    "(a) register the marketplace as a DIRECTORY source at the "
                    "checkout — the CLI then binds the checkout in place "
                    "(measured 2026-09-16, Claude Code 2.1.273) and the "
                    "checkout is cloned fresh per session, so the snapshot's "
                    "age stops mattering; or (b) rebuild the snapshot (any "
                    "edit to the environment's setup script rebuilds it) so "
                    "the cache copy is current. Until one lands, `doctor.py "
                    "--heal` repairs the DISK every firing and the session "
                    f"still binds the roster it started with: {SETUP_CURL}"),
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
        if inst.get("in_place"):
            reasons.append(
                f"{inst['version']} at {inst.get('bound_path')} matches the "
                f"checkout, and this session binds that tree in place — but "
                f"its agents, hooks, commands or manifest were written "
                f"{inst.get('updated_at')} and this session's process started "
                f"{_stamp(inst.get('session_started_at'))} (a pull or checkout "
                f"moved the tree under a running session, which read those "
                f"once at start and does not reload them)")
        else:
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
    # WHICH TREE THIS VERDICT IS ABOUT. The bind is measured (`bound_root`)
    # and named at every status, because the one time it was assumed — the
    # record's cache path taken for the session's tree — every verdict here
    # was wrong for five days of sessions and nothing in the output could
    # have shown it (2026-09-16).
    if inst.get("in_place"):
        reasons.append(
            f"MEASURED BIND: this session loads {inst.get('bound_path')} in "
            f"place (via {inst.get('bound_source')}), not the cache copy the "
            f"install record names"
            + (f"; the record still says {inst.get('record_version')} — a "
               f"cosmetic lag: it describes a copy this session does not "
               f"run, so no heal is needed for it and `claude plugin update` "
               f"would change nothing this session executes"
               if inst.get("record_version")
               and inst.get("record_version") != inst.get("version") else ""))
    elif inst.get("bound_source"):
        reasons.append(f"MEASURED BIND: this session loads the install "
                       f"record's tree {inst.get('bound_path')} "
                       f"(via {inst.get('bound_source')})")
    elif os.environ.get("CLAUDE_PID") and status not in ("OK", "NOT_INSTALLED"):
        reasons.append(
            f"BIND NOT MEASURED — this verdict is about the install RECORD, "
            f"not proven about this session: {inst.get('bound_reason')}")
    # Reported at every status, including OK: a shadowed record is not a
    # failure — the highest version is what loads — but leaving it unnamed is
    # what made a session spend a paragraph guessing about it.
    for extra in inst.get("shadowed") or []:
        if inst.get("in_place"):
            reasons.append(f"also recorded: {extra['version']} at "
                           f"{extra['scope']} scope — a second install "
                           f"record; neither record's copy is what this "
                           f"session loads (it binds in place), safe to ignore")
        else:
            reasons.append(f"also recorded: {extra['version']} at "
                           f"{extra['scope']} scope — shadowed by the "
                           f"{inst.get('scope')}-scope {inst['version']} that "
                           f"loads, and safe to ignore")

    fix = ""
    if (status in ("STALE", "INCOMPLETE", "DIVERGED") and inst.get("in_place")
            and not _under_plugin_cache(inst.get("bound_path"))):
        # `claude plugin update` rewrites the CACHE copy. A session that binds
        # a tree outside the cache — a marketplace directory, a --plugin-dir
        # — is not running that copy, so the update would report success and
        # change nothing the session executes. The tree itself has to move.
        fix = (f"this session binds {inst.get('bound_path')} IN PLACE, and "
               f"that tree is behind this checkout ({pub.get('tree')}). "
               f"`claude plugin update` refreshes only the cache copy, which "
               f"this session does not load — bring the bound tree to the "
               f"branch tip instead (it is a checkout: fetch and reset it, or "
               f"register the marketplace at THIS checkout), then start a "
               f"fresh session. If the bound tree is the checkout a RESTORED "
               f"SNAPSHOT carries (a trigger-fired container with no "
               f"repository attached), a fresh session inherits the same old "
               f"checkout: rebuild the snapshot (any edit to the environment's "
               f"setup script rebuilds it) or attach the repository to the "
               f"Routine so it is cloned fresh per session. Until then "
               f"{SESSION_NOTE}")
    elif status in ("STALE", "MISSING", "INCOMPLETE"):
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
    prov = provisioning(prov_path, in_place=inst.get("in_place"))
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
    line = (f"{verdict['status']}: installed {inst.get('version') or 'none'} "
            f"({inst.get('agents', 0)} agents) vs published "
            f"{pub.get('version') or 'unreadable'} ({pub.get('agents', 0)} agents)")
    if inst.get("in_place"):
        line += (f" — bound in place at {inst.get('bound_path')} "
                 f"[{inst.get('bound_source')}]")
        if inst.get("record_version") and inst.get("record_version") != inst.get("version"):
            line += f"; install record says {inst.get('record_version')} (cosmetic)"
    return line


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
    inst = verdict.get("installed") or {}
    if inst.get("in_place") and not _under_plugin_cache(inst.get("bound_path")):
        # EVERY COMMAND IN THE PLAN REWRITES THE CACHE COPY, and this session
        # does not load the cache copy. Running them would print four exit-0
        # lines and change nothing the session executes — the shape of
        # success with none of it — so the heal declines and says what would
        # actually move the bound tree.
        return verdict, [
            f"heal: declined — this session binds {inst.get('bound_path')} in "
            f"place, and the plugin update rewrites only the cache copy it "
            f"does not load; bring that checkout to the branch tip instead"]
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
        prov = v.get("provisioning") or {}
        if prov.get("recurs") and prov.get("fix"):
            print(f"  => ROOT CAUSE, RECURS EVERY FIRING: {prov['fix']}")
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
