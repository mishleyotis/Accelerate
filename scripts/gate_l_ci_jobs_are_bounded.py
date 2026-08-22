#!/usr/bin/env python3
"""Gate L — every CI job carries a clock.

WHAT THIS IS FOR, measured 2026-08-19. `npx playwright install --with-deps`
folds an apt-get run into the browser download, and apt on a fresh runner
queues behind unattended-upgrades holding the dpkg lock. Two independent runs
of the same commit sat on that one step for 33 minutes and were still sitting
there when they were found. GitHub's default job timeout is **six hours**, so
nothing was going to end them.

A hung check is the same defect this repo keeps paying for in a new costume: a
check that is not running, with nothing saying so. A skipped suite reports
green; a hung suite reports `in_progress`, which reads as diligence. Neither
tells a reader the check did not happen. A bound converts both into a red
build, which is the only outcome a person acts on.

So: every job in every workflow declares `timeout-minutes`, and no job may
declare one large enough to outlive the working day.

Deliberately dependency-free — the gates job runs bare `python3` with no pip
install, and a gate that cannot start is a gate that is not enforcing. The
line scan is guarded: a workflow that yields NO jobs is a refusal, never a
pass, because a parser that has drifted out of step with the file would
otherwise report success having examined nothing.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Long enough for the slowest honest job here (python-tests with a Postgres
# service, ~90s today), short enough that a stall is found the same hour.
CEILING_MINUTES = 45

JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$")
TIMEOUT = re.compile(r"^    timeout-minutes:\s*(\d+)\s*(?:#.*)?$")
# `jobs:` at column 0. Everything above it (on:, env:, concurrency:) is
# workflow-level and has no jobs to bound.
JOBS_KEY = re.compile(r"^jobs:\s*(?:#.*)?$")


def jobs_in(text):
    """(name, timeout|None) per job, in file order."""
    out, name, timeout, in_jobs = [], None, None, False
    for line in text.splitlines():
        if JOBS_KEY.match(line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" ") and not line.startswith("#"):
            break                      # a new top-level key ends the block
        m = JOB.match(line)
        if m:
            if name is not None:
                out.append((name, timeout))
            name, timeout = m.group(1), None
            continue
        m = TIMEOUT.match(line)
        if m and name is not None and timeout is None:
            timeout = int(m.group(1))
    if name is not None:
        out.append((name, timeout))
    return out


def main():
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not files:
        print("Gate L: no workflow files found — nothing to bound", file=sys.stderr)
        return 1

    failures, checked = [], 0
    for f in files:
        found = jobs_in(f.read_text())
        if not found:
            # THE VACUOUS PASS, refused. See the module docstring.
            failures.append(f"{f.relative_to(ROOT)}: parsed 0 jobs — this gate "
                            f"cannot confirm anything about this file")
            continue
        for name, timeout in found:
            checked += 1
            where = f"{f.relative_to(ROOT)}:{name}"
            if timeout is None:
                failures.append(
                    f"{where}: no timeout-minutes, so it inherits GitHub's "
                    f"6-hour default — a hang here outlives the day")
            elif timeout > CEILING_MINUTES:
                failures.append(
                    f"{where}: timeout-minutes: {timeout} exceeds the "
                    f"{CEILING_MINUTES}-minute ceiling")

    for msg in failures:
        print(f"Gate L FAIL — {msg}", file=sys.stderr)
    if failures:
        return 1
    print(f"Gate L: {checked} job(s) across {len(files)} workflow file(s) "
          f"are bounded at or under {CEILING_MINUTES} minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
