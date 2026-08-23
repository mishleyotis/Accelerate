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
    return {
        "version": best.get("version"),
        "state_file_exists": True,
        "scope": best.get("scope"),
        "install_path": str(install_path) if install_path.name else None,
        "commit": best.get("gitCommitSha"),
        "installed_at": best.get("installedAt"),
        "agents": agents,
        "skills": skills,
        "declared_agents": len(declared.get("agents") or []),
        "digest": digest(install_path),
        "shadowed": shadowed,
        "state_file": str(path),
        "source": "installed_plugins.json",
    }


UPDATE = (f"claude plugin marketplace update {MARKETPLACE_NAME} && "
          f"claude plugin update {PLUGIN_NAME}@{MARKETPLACE_NAME}")
UPDATE_NOTE = ("the update applies at NEXT session start, so re-check there "
               "and end the firing cleanly rather than producing on stale skills")


def compare(repo_root: Path | None = None,
            state_path: Path | None = None) -> dict:
    """The verdict, with the arithmetic shown. Statuses:

      OK              installed is what the repo publishes, and whole
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
    elif status == "DIVERGED":
        fix = ("bump the version in BOTH manifests, then " + UPDATE +
               f" — reinstalling without a bump leaves the cache on a "
               f"version number that no longer describes its contents")
    elif status == "AHEAD":
        fix = ("pull the branch — the checkout, not the plugin, is what needs "
               "to move")
    elif status == "MANIFEST_SPLIT":
        fix = ("set the same version in both .claude-plugin/marketplace.json "
               "and plugins/dma-insights/.claude-plugin/plugin.json")
    return {"status": status, "ok": status in ("OK", "NOT_INSTALLED"),
            "reasons": reasons, "fix": fix, "published": pub,
            "installed": inst}


def summary(verdict: dict) -> str:
    """One line, quotable into a routine report."""
    pub, inst = verdict["published"], verdict["installed"]
    return (f"{verdict['status']}: installed {inst.get('version') or 'none'} "
            f"({inst.get('agents', 0)} agents) vs published "
            f"{pub.get('version') or 'unreadable'} ({pub.get('agents', 0)} agents)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=None,
                    help="the checkout to read as the source of truth "
                         "(default: the one this script lives in)")
    ap.add_argument("--state", default=None,
                    help="path to installed_plugins.json (default: the CLI's)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    v = compare(a.repo_root, a.state)
    if a.json:
        print(json.dumps(v, indent=1))
    else:
        print(summary(v))
        for r in v["reasons"]:
            print(f"  - {r}")
        if v["fix"]:
            print(f"  -> {v['fix']}")
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
