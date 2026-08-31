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
SHOULD be loaded, `~/.claude/plugins/installed_plugins.json` plus the cache
directory are the truth about what IS, and every number is read from one of
those two at call time.

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


def installed(state_path: Path | None = None) -> dict:
    """What the running session loads — version, install path, and the
    components actually present in that path.

    The count is taken from the INSTALLED tree, never from the repo. A
    version number can match while the packaged tree is short (a partial
    unpack, an interrupted update), and the roster is what the session
    dispatches against, so it is measured where the session reads it.
    """
    path = Path(state_path) if state_path else INSTALL_STATE
    state = _load(path)
    records = (state.get("plugins") or {}).get(
        f"{PLUGIN_NAME}@{MARKETPLACE_NAME}") or []
    if not records:
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
    install_path = Path(best.get("installPath") or "")
    agents = (len(list((install_path / "agents").rglob("*.md")))
              if (install_path / "agents").is_dir() else 0)
    skills = (len([p for p in (install_path / "skills").glob("*") if p.is_dir()])
              if (install_path / "skills").is_dir() else 0)
    declared = _load(install_path / ".claude-plugin" / "plugin.json")
    # `lastUpdated` moves on every update; `installedAt` is the first install
    # and stays put. The question here is "did the tree change under a running
    # session", so the later of the two is the one that answers it.
    changed_at = _epoch(best.get("lastUpdated")) or _epoch(best.get("installedAt"))
    began = session_started_at()
    loaded_this = None if (began is None or changed_at is None) \
        else changed_at <= began
    return {
        "version": best.get("version"),
        "state_file_exists": True,
        "scope": best.get("scope"),
        "install_path": str(install_path) if install_path.name else None,
        "commit": best.get("gitCommitSha"),
        "installed_at": best.get("installedAt"),
        "updated_at": best.get("lastUpdated") or best.get("installedAt"),
        "session_started_at": began,
        # True: the install predates this session, so this session loaded it.
        # False: the tree changed after this session bound its agents.
        # None: no measurable session start — do not judge either way.
        "loaded_by_this_session": loaded_this,
        "agents": agents,
        "skills": skills,
        "declared_agents": len(declared.get("agents") or []),
        "digest": digest(install_path),
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
    return (f"{verdict['status']}: installed {inst.get('version') or 'none'} "
            f"({inst.get('agents', 0)} agents) vs published "
            f"{pub.get('version') or 'unreadable'} ({pub.get('agents', 0)} agents)")


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
        prov = v.get("provisioning") or {}
        if prov.get("recurs") and prov.get("fix"):
            print(f"  => ROOT CAUSE, RECURS EVERY FIRING: {prov['fix']}")
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
