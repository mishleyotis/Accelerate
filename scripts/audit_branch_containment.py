#!/usr/bin/env python3
"""Is a branch's work already in this tree — or would deleting it lose something?

WHY THIS EXISTS, AND WHY THE OBVIOUS VERSION IS WRONG.

On 2026-08-30 eleven branches sat ahead of the default branch and the question
was which of them still carried work. The first answer was built on two
signals that both look reasonable and are both unsound:

  "files only on the branch"  — misses every ENHANCEMENT to a file that
                                exists on both sides, which is most of them.
  "which side touched it last" — recency is not containment. A branch that
                                added a feature to a file on the 18th, and a
                                default that reformatted the same file on the
                                28th, reads as "default is newer" while the
                                feature was never incorporated at all.

The owner caught exactly that: "it is not about new files but the enhancements
that could get lost."

WHAT THIS DOES INSTEAD, in three passes, cheapest first:

  1. PATCH-EQUIVALENCE — `git log --cherry-pick --right-only`. Commits whose
     patch-id already appears in the target are merged even when the hashes
     differ (cherry-picks, rebases, a re-landed PR). This is the pass that
     tells you WHICH commits to look at.
  2. LINE CONTAINMENT — for the commits that survive pass 1, every
     substantive line the commit ADDED is checked for presence in the
     target's current version of that same file. A commit at 100% is fully
     absorbed however it got there.
  3. FILE SUPERSET — for whole files, whether the branch holds substantive
     lines the target's version does not.

WHAT IT CANNOT DECIDE, AND WILL NOT PRETEND TO.

A line present on a branch and absent here is EITHER lost work OR a
deliberate deletion. Only reading tells you which, and the difference is
total: on the same run, one branch's 287 extra lines in a page component
looked like a lost feature and turned out to be the pre-deletion state of
code removed on purpose the following day — the removal rationale was
sitting in the file, 144 lines of it, explaining that the API's NEVER_SERVED
allowlist had left those cards with nothing to render.

So this prints CANDIDATES and the evidence for each. It never merges, never
writes, and never says "safe to delete".
"""
from __future__ import annotations

import argparse
import collections
import subprocess
import sys

TRIVIAL_PREFIX = ("#", "//", "*", "/*", "{/*")
MIN_LEN = 12


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def unmerged_commits(target: str, branch: str) -> list[tuple[str, str]]:
    """Commits on `branch` with no patch-equivalent on `target`."""
    out = sh("git", "log", "--oneline", "--cherry-pick", "--right-only",
             f"{target}...{branch}")
    rows = []
    for line in out.splitlines():
        sha, _, subject = line.partition(" ")
        if sha:
            rows.append((sha, subject))
    return rows


def added_by(commit: str) -> dict:
    """{path: [substantive added lines]} for one commit."""
    out: dict = collections.defaultdict(list)
    path = None
    for ln in sh("git", "show", "--format=", "--unified=0", commit).splitlines():
        if ln.startswith("+++ b/"):
            path = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++") and path:
            s = ln[1:].strip()
            if len(s) > MIN_LEN and not s.startswith(TRIVIAL_PREFIX):
                out[path].append(s)
    return out


def _tree_paths(target: str) -> dict:
    """basename -> [paths] in the target tree, for relocation fallback."""
    idx: dict = collections.defaultdict(list)
    for p in sh("git", "ls-tree", "-r", "--name-only", target).splitlines():
        idx[p.rsplit("/", 1)[-1]].append(p)
    return idx


def containment(commit: str, target: str, index: dict | None = None) -> tuple:
    """(total, missing, {path: n_missing}) for one commit against a tree.

    A file ABSENT at its original path is looked up again by basename before
    being called missing. Work is moved as often as it is deleted — the
    audits recovered on 2026-08-30 went from `.qa/x` to
    `.qa/audits/<dated>/x`, and without this every line of them reported as
    lost, which is the same false alarm this tool exists to stop.
    """
    total = missing = 0
    by_file: collections.Counter = collections.Counter()
    index = _tree_paths(target) if index is None else index
    for path, lines in added_by(commit).items():
        current = sh("git", "show", f"{target}:{path}")
        if not current:
            for alt in index.get(path.rsplit("/", 1)[-1], []):
                current = sh("git", "show", f"{target}:{alt}")
                if current:
                    break
        for line in lines:
            total += 1
            if line not in current:
                missing += 1
                by_file[path] += 1
    return total, missing, by_file


def tree_containment(target: str, branch: str) -> tuple:
    """Every substantive line the BRANCH TIP holds, tested against the target.

    Pass 2 walks commits, which answers "was this commit absorbed". It does
    not answer the question you actually have when deciding whether a branch
    can go: does the branch's CURRENT tree hold a line this one does not? A
    commit can read as a CANDIDATE because a later commit on its own branch
    rewrote those lines — the intermediate version is genuinely absent here
    and genuinely not lost. On 2026-08-30 that shape produced 155 "absent"
    lines in one ledger file that the branch tip did not carry either.

    So this compares tip to tip. It is also far cheaper on a long branch:
    one pass over the differing files instead of one per commit. A file the
    target lacks at that path is looked up by basename first, for the same
    relocation reason as `containment`.
    """
    index = _tree_paths(target)
    total = missing = 0
    by_file: collections.Counter = collections.Counter()
    changed = sh("git", "diff", "--name-only", "--diff-filter=AM",
                 target, branch).splitlines()
    for path in changed:
        theirs = sh("git", "show", f"{branch}:{path}")
        if not theirs:
            continue
        ours = sh("git", "show", f"{target}:{path}")
        if not ours:
            for alt in index.get(path.rsplit("/", 1)[-1], []):
                ours = sh("git", "show", f"{target}:{alt}")
                if ours:
                    break
        for line in theirs.splitlines():
            s = line.strip()
            if len(s) <= MIN_LEN or s.startswith(TRIVIAL_PREFIX):
                continue
            total += 1
            if s not in ours:
                missing += 1
                by_file[path] += 1
    return total, missing, by_file, len(changed)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("branches", nargs="+")
    ap.add_argument("--target", default="HEAD",
                    help="the tree to test containment against (default HEAD)")
    ap.add_argument("--threshold", type=int, default=100,
                    help="percent of added lines that must be present for a "
                         "commit to count as absorbed (default 100)")
    ap.add_argument("--tree", action="store_true",
                    help="compare BRANCH TIP to target tree instead of "
                         "walking commits: does the branch hold a line this "
                         "tree does not? Cheap on long branches, and immune "
                         "to the intermediate-version false alarm")
    a = ap.parse_args(argv)

    if a.tree:
        rows = []
        for branch in a.branches:
            if not sh("git", "rev-parse", "--verify", branch).strip():
                print(f"### {branch}: no such ref", file=sys.stderr)
                rows.append((branch, None, 0))
                continue
            total, missing, by_file, nfiles = tree_containment(a.target, branch)
            pct = 100 if not total else 100 * (total - missing) // total
            print(f"### {branch}")
            print(f"    {nfiles} file(s) differ; {total} substantive line(s) "
                  f"on the branch tip, {pct}% present in {a.target}")
            for path, n in by_file.most_common(12):
                print(f"        {n:6d} absent in {path}")
            rows.append((branch, missing, total))
            print()
        print("== summary (tip vs tip) ==")
        for branch, missing, total in rows:
            state = ("unreadable" if missing is None else
                     "holds nothing this tree lacks" if missing == 0 else
                     f"{missing} of {total} line(s) to read")
            print(f"  {branch:52s} {state}")
        print("\nA line absent here is EITHER lost work OR a deliberate "
              "deletion. Read it before restoring it.")
        return 0

    verdicts = []
    for branch in a.branches:
        if not sh("git", "rev-parse", "--verify", branch).strip():
            print(f"### {branch}: no such ref", file=sys.stderr)
            verdicts.append((branch, None))
            continue
        commits = unmerged_commits(a.target, branch)
        print(f"### {branch}")
        if not commits:
            print("    fully merged — every commit has a patch-equivalent "
                  f"in {a.target}\n")
            verdicts.append((branch, 0))
            continue
        print(f"    {len(commits)} commit(s) with no patch-equivalent; "
              f"testing line containment")
        candidates = 0
        index = _tree_paths(a.target)
        for sha, subject in commits:
            total, missing, by_file = containment(sha, a.target, index)
            pct = 100 if not total else 100 * (total - missing) // total
            if pct >= a.threshold:
                mark = "absorbed"
            else:
                mark = "CANDIDATE"
                candidates += 1
            print(f"    [{mark:9s}] {sha} {pct:3d}% of {total:5d} added lines "
                  f"present — {subject[:58]}")
            if mark == "CANDIDATE":
                for path, n in by_file.most_common(5):
                    print(f"                  {n:5d} absent in {path}")
        print(f"    -> {candidates} commit(s) need a human to read them\n")
        verdicts.append((branch, candidates))

    print("== summary ==")
    for branch, n in verdicts:
        state = ("unreadable" if n is None else
                 "nothing outstanding" if n == 0 else
                 f"{n} commit(s) to read")
        print(f"  {branch:52s} {state}")
    print("\nA CANDIDATE is not a loss. It is a diff nobody has read yet, and "
          "it is as likely to be a deliberate deletion as a missing feature — "
          "read the file before restoring anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
