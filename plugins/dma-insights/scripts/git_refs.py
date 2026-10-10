#!/usr/bin/env python3
"""Keep the LOCAL default-branch ref current without touching the worktree.

WHY (Interac, 2026-10-10 — and every DMA session run from a restored
snapshot). The harness clones the session's own branch fresh, so HEAD is
current; but the snapshot also carries a local `claude/dma-insights-
onboarding-0ryrd0` ref from the day the setup script last ran — 122 commits
behind on Interac. A session told to work on the default branch ran
`git checkout <default>`, which rewound every agent, hook and command file
122 commits under the running session; it then fast-forwarded back. The
doctor read the rewrites as UPDATED_MID_SESSION and the owner was asked
about it.

The fix is to never let the stale ref exist by the time anyone checks it
out: the SessionStart hook starts `freshen` DETACHED (it must not delay the
session), which fetches the default branch and moves the local ref with a
compare-and-swap `update-ref` — only when it is a strict ancestor of the
remote tip, and NEVER when it is the checked-out branch (moving that would
be the very mid-session rewrite this prevents). A ref holding commits the
remote lacks is somebody's work and is left alone, reported.

The branch is the session's base ref (CLAUDE_CODE_BASE_REF, set by the
harness), else DMA_REPO_BRANCH, else the default `bootstrap_session.sh`
writes down — read from that file, never retyped here.

    git_refs.py freshen [--repo DIR] [--branch NAME] [--no-fetch] [--json]
    git_refs.py spawn   # what the hook calls: freshen, detached, logged
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def default_branch() -> str | None:
    for var in ("CLAUDE_CODE_BASE_REF", "DMA_REPO_BRANCH"):
        v = (os.environ.get(var) or "").strip()
        if v:
            return v.removeprefix("refs/heads/")
    try:
        src = (HERE / "bootstrap_session.sh").read_text()
    except OSError:
        return None
    m = re.search(r'^BRANCH="\$\{DMA_REPO_BRANCH:-([^}]+)\}"', src, re.M)
    return m.group(1) if m else None


def _git(repo, *args, timeout=30):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, timeout=timeout)


def repo_of(path: Path) -> Path | None:
    try:
        p = _git(path, "rev-parse", "--show-toplevel", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None


def freshen(repo: Path, branch: str, fetch: bool = True) -> dict:
    """Move refs/heads/<branch> to origin/<branch> when that is a pure
    fast-forward and the branch is not checked out. Returns what it did."""
    out = {"repo": str(repo), "branch": branch, "action": None, "reason": ""}
    head = _git(repo, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    if head == branch:
        out.update(action="skipped", reason="the branch is checked out — "
                   "moving it would rewrite the worktree under the session")
        return out
    if fetch:
        try:
            f = _git(repo, "fetch", "--quiet", "origin",
                     f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
                     timeout=60)
        except subprocess.TimeoutExpired:
            out.update(action="fetch_failed", reason="fetch timed out")
            return out
        if f.returncode != 0:
            out.update(action="fetch_failed",
                       reason=(f.stderr or "").strip()[:200])
            return out
    remote = _git(repo, "rev-parse", "-q", "--verify",
                  f"refs/remotes/origin/{branch}").stdout.strip()
    local = _git(repo, "rev-parse", "-q", "--verify",
                 f"refs/heads/{branch}").stdout.strip()
    if not remote:
        out.update(action="no_remote", reason=f"origin/{branch} is unknown")
        return out
    if not local:
        out.update(action="absent", reason="no local ref; a checkout creates "
                   "it from the freshly fetched origin ref")
        return out
    if local == remote:
        out.update(action="current", sha=local)
        return out
    if _git(repo, "merge-base", "--is-ancestor", local, remote).returncode != 0:
        out.update(action="diverged", reason="the local ref holds commits the "
                   "remote does not — somebody's work, left alone")
        return out
    behind = _git(repo, "rev-list", "--count", f"{local}..{remote}").stdout.strip()
    u = _git(repo, "update-ref", "-m", "dma-insights: fast-forward stale ref",
             f"refs/heads/{branch}", remote, local)
    if u.returncode != 0:
        out.update(action="update_failed", reason=(u.stderr or "").strip()[:200])
        return out
    out.update(action="fast_forwarded", behind=int(behind or 0),
               old=local, new=remote)
    return out


def log_path() -> Path:
    base = Path(os.environ.get("DMA_BOUND_PLUGIN_DIR")
                or Path(os.environ.get("DMA_SA_KEY_FILE", "/root/.dma/sa.json")).parent)
    return base / "git_refs.log"


def spawn(repo: Path | None = None) -> bool:
    """Start `freshen` detached and return at once. Fails open."""
    if os.environ.get("DMA_FRESHEN_REFS", "1") == "0":
        return False
    try:
        args = [sys.executable, str(Path(__file__).resolve()), "freshen",
                "--json", "--log"]
        if repo:
            args += ["--repo", str(repo)]
        subprocess.Popen(args, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, close_fds=True)
        return True
    except OSError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freshen")
    f.add_argument("--repo", default=None)
    f.add_argument("--branch", default=None)
    f.add_argument("--no-fetch", action="store_true")
    f.add_argument("--json", action="store_true")
    f.add_argument("--log", action="store_true")
    sp = sub.add_parser("spawn")
    sp.add_argument("--repo", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "spawn":
        return 0 if spawn(Path(a.repo) if a.repo else None) else 1
    repo = repo_of(Path(a.repo) if a.repo else HERE)
    branch = a.branch or default_branch()
    if repo is None or not branch:
        out = {"action": "skipped", "reason": "no git checkout or no branch"}
    else:
        out = freshen(repo, branch, fetch=not a.no_fetch)
    out["at"] = time.time()
    if a.log:
        try:
            lp = log_path()
            lp.parent.mkdir(parents=True, exist_ok=True)
            with open(lp, "a") as fh:
                fh.write(json.dumps(out) + "\n")
        except OSError:
            pass
    print(json.dumps(out) if a.json else f"{out['action']}: "
          f"{out.get('reason') or out.get('behind', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
