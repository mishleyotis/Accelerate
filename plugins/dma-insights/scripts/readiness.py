#!/usr/bin/env python3
"""Is this system ready to run in production — measured, lane by lane.

    python3 scripts/readiness.py [--triggers FILE] [--tests] [--lifecycle]
                                 [--json] [--strict]

WHY THIS EXISTS. "Production ready" is not one boolean, and asking for it as
one is how this project has repeatedly been told yes by something that never
looked. The doctor counted the CHECKOUT's forty-seven files and printed green
on a container carrying five agents. `classification.py` classified the
client profile, the scanner recorded the kind, and nothing read it. Two of six
Routines were unhealthy for days with no alert, because the thing that watches
runs does not watch Routines. Each of those was a green report standing in
front of an unmeasured lane.

So this reports three verdicts, and the third one is the point:

    READY                 measured here, passed
    BLOCKED               measured here, failed — the row names the fix
    NOT_MEASURABLE_HERE   the lane is real, this container cannot see it,
                          and the row names who can and how

NOT_MEASURABLE_HERE IS NEVER COUNTED AS READY. A lane nobody measured is
exactly the lane that fails, and a summary that folds it into the green count
is the defect this file exists to refuse. `--strict` makes it exit non-zero
too, which is what CI should use.

WHAT IT DOES NOT DO. It does not re-derive any verdict. Every measured lane
shells out to the check that owns it — audit_coverage, audit_skills,
check_taxonomy_drift, plugin_version, doctor, routine_health,
stress_run_lifecycle, pytest — so this file cannot drift into disagreeing with
them. If a lane's rule changes, it changes in one place and this reads the new
answer.

The standing OPEN items at the bottom are not checks. They are the things no
script in this repository can close — an account spend limit, a connector
grant on a Routine's own edit screen, a Slack surface that is specified and
not built — carried here with the document that specifies each, so a
readiness answer cannot read as complete while they are open.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PLUGIN))

READY = "READY"
BLOCKED = "BLOCKED"
UNMEASURED = "NOT_MEASURABLE_HERE"

#: What a lane's verdict is a property OF. A blocked lane is not one thing:
#: a coverage hole is true of the checkout wherever it is read, a stale
#: install is true of the container the check ran in, and an unhealthy
#: Routine is true of the live system and of neither. Callers that need to
#: act on one class and not another — `goal_status.py` asks only about the
#: repository — read this rather than re-deriving the split, which is how two
#: readers of one answer start disagreeing about it.
REPOSITORY = "repository"      # true of this checkout, anywhere it is read
CONTAINER = "container"        # true of the machine the check ran on
EXTERNAL = "external"          # true of the live system, measured elsewhere

#: Lanes that no script here can close, with the document that specifies each
#: and the person or screen that can. Carried in the report so "ready" cannot
#: be claimed over them. Each is a MEASURED open item, not a worry.
STANDING_OPEN = [
    ("routine spend limit",
     "dma-rectification-weekly has failed on 'You've hit your individual "
     "spend limit' (five_hour rate limit, rejected) since 2026-08-24. No "
     "change to this repository can fix it.",
     "the account owner, at claude.ai/settings/usage",
     "docs/ROUTINES.md"),
    ("stale install on a trigger-fired container",
     "dma-refresh-drift-daily reaches a permission prompt the plugin's "
     "autoapprove hook allows, which means the hook did not run — a stale "
     "install. plugin_version.py --heal fixes the DISK; hooks bind once at "
     "session start, so the firing that found it cannot heal itself.",
     "the environment owner: bootstrap_session.sh must run before the "
     "session starts (claude.ai/code environment settings)",
     "docs/ROUTINES.md"),
    ("owner-names-the-client channel",
     "There is no interface through which the owner can say which client to "
     "assess next: `run_gate.py pick` has no --client, and no Slack surface "
     "exists. Specified against the interfaces that do exist; NOT BUILT.",
     "whoever builds it — the contract is section 3 of the doc",
     "docs/CLIENT-SELECTION.md"),
    ("connector authorisation",
     "Atlassian, Zapier and Zennify_Brains require OAuth, and lane B "
     "(trig_01NXSfaTVuWEubFAcA4mbbeL) carries no claude.ai connectors. A "
     "Routine that reaches its enrichment preflight without them stops "
     "without producing, by design.",
     "the account owner, on each Routine's own edit screen in the claude.ai "
     "routines UI (the connector browse list's Use buttons enable a "
     "connector for the ORG, not for a Routine)",
     "docs/CONNECTORS.md"),
]


def _run(argv, cwd=REPO, timeout=900):
    """Run a check and return (exit_code, combined output). A check that is
    absent or unrunnable returns None rather than a zero — the difference
    between 'passed' and 'never ran' is the whole subject of this file."""
    try:
        p = subprocess.run(argv, cwd=cwd, timeout=timeout,
                           capture_output=True, text=True)
    except FileNotFoundError as e:
        return None, str(e)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


#: How each composed check spells "this row did not pass". Matched against
#: whole lines, so a summary that merely mentions the word does not qualify.
_FAIL_MARKERS = ("[FAIL]", "[fail]", "✗", "FAILED", "REFUSED", "STALE",
                 "MISSING", "INCOMPLETE", "missing:", "HOLE", "NOT_RUN")


def _failing_lines(text) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines()
            if any(m in ln for m in _FAIL_MARKERS)]


def _gist(text, n=2) -> str:
    """The DECISIVE lines, not the last three.

    Every check composed here prints a headline and then rows, so the last
    three lines of a fifteen-row report are whichever rows happened to sort
    last. That is how a stale-INSTALL failure first came back from this file
    described as a missing credential: the tail contained the word `token`
    because most of the doctor's passing rows do. Failing rows first; a clean
    run falls back to its headline and its summary.
    """
    fails = _failing_lines(text)
    if fails:
        return " · ".join(fails[:n])[:400]
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    gist = list(dict.fromkeys(lines[:1] + lines[-1:]))
    return " … ".join(gist)[:400]


def lane(name, what, code, output, fix, unmeasured_reason=None,
         scope=REPOSITORY):
    if code is None:
        return {"lane": name, "what": what, "scope": scope,
                "verdict": UNMEASURED,
                "detail": unmeasured_reason or _gist(output), "fix": fix}
    return {"lane": name, "what": what, "scope": scope,
            "verdict": READY if code == 0 else BLOCKED,
            "detail": _gist(output), "fix": fix}


def check_coverage():
    code, out = _run([sys.executable, f"{PLUGIN}/scripts/audit_coverage.py",
                      "--strict"])
    return lane("coverage",
                "every workbook tab, report section, deliverable and derived "
                "field has an owner that writes it",
                code, out,
                "audit_coverage.py names each HOLE; a hole is a contract "
                "requiring an artefact that no agent and no command writes")


def check_skills():
    code, out = _run([sys.executable, f"{PLUGIN}/scripts/audit_skills.py"])
    return lane("skills",
                "every bundled script answers --help, and every reference "
                "into the skill tree resolves",
                code, out,
                "the failing rows name the script or the dead link")


def check_taxonomy():
    code, out = _run([sys.executable,
                      f"{PLUGIN}/scripts/check_taxonomy_drift.py"])
    return lane("taxonomy",
                "no stale catalogue literal, and no fifth maturity band the "
                "charter says must not exist",
                code, out,
                "each hit names file and line; a line deliberately teaching "
                "v5.0 recognition carries a lineage marker and is allowed")


def check_install():
    code, out = _run([sys.executable, f"{PLUGIN}/scripts/plugin_version.py"])
    return lane("install",
                "what this session loads is what the checkout publishes",
                code, out,
                "plugin_version.py --heal updates the container-local install "
                "cache and re-checks; hooks still bind at session start",
                scope=CONTAINER)


#: A doctor row whose failure means "this container holds no credential",
#: as opposed to one that means "the deployment is wrong".
_NO_CREDENTIAL_HERE = ("identity token", "google account", "gcloud",
                       "audience", "credential", "path token", "network",
                       "connection", "timed out", "unreachable")


def check_connector(offline=False):
    if offline:
        return lane("connector",
                    "the MCP deployment is reachable, the token audience "
                    "matches the URL, and the service enforces the token",
                    None, "",
                    "drop --offline where the connector is reachable",
                    unmeasured_reason="--offline: the doctor reaches the "
                                      "live service, and this run was told "
                                      "not to.",
                    scope=CONTAINER)
    code, out = _run([sys.executable, f"{PLUGIN}/scripts/doctor.py"],
                     timeout=180)
    row = lane("connector",
               "the MCP deployment is reachable, the token audience matches "
               "the URL, and the service enforces the token",
               code, out,
               "doctor.py names which of the five independent failures it is",
               scope=CONTAINER)
    if row["verdict"] == BLOCKED:
        # A container with no credentials has not measured the deployment; it
        # has measured its own emptiness, and saying BLOCKED there reports a
        # serving system as broken. But the test is the FAILING ROWS, not the
        # whole output: keyed on the whole output this downgraded a stale
        # install — a row the `install` lane already owns — into "no live
        # credential path", which is a check inventing a reason for its own
        # verdict. Every failing row must be about OBTAINING a credential.
        fails = _failing_lines(out)
        if fails and all(any(k in ln.lower() for k in _NO_CREDENTIAL_HERE)
                         for ln in fails):
            row["verdict"] = UNMEASURED
            row["detail"] = ("no live credential path from this container: "
                             + row["detail"])
    return row


def check_routines(path):
    if not path:
        return lane("routines",
                    "every enabled Routine's last firing succeeded",
                    None, "",
                    "call list_triggers, save the response, and pass "
                    "--triggers <file>",
                    unmeasured_reason=(
                        "a script cannot call list_triggers; a session can. "
                        "Pass --triggers with a saved response."),
                    scope=EXTERNAL)
    code, out = _run([sys.executable, f"{PLUGIN}/scripts/routine_health.py",
                      "--file", path, "--strict"])
    return lane("routines",
                "every enabled Routine's last firing succeeded",
                code, out,
                "routine_health.py gives each unhealthy Routine its next "
                "move; FAILED and ABANDONED need different responses",
                scope=EXTERNAL)


def check_tests(run):
    if not run:
        return lane("tests",
                    "the contract, engine, worker, api and mcp suites pass",
                    None, "",
                    "python3 -m pytest tests/ plugins/dma-insights/scripts/"
                    "tests/ scripts/tests/ apps/worker/tests apps/api/tests "
                    "apps/mcp/tests -q",
                    unmeasured_reason=(
                        "not run: pass --tests. It takes minutes, so it is "
                        "opt-in here and mandatory in CI."))
    code, out = _run([sys.executable, "-m", "pytest",
                      "tests/", f"{PLUGIN}/scripts/tests/", "scripts/tests/",
                      "apps/worker/tests", "apps/api/tests", "apps/mcp/tests",
                      "-q", "--tb=line", "-p", "no:cacheprovider"],
                     timeout=3600)
    return lane("tests",
                "the contract, engine, worker, api and mcp suites pass",
                code, out,
                "the summary line names the failures")


def check_lifecycle(run):
    if not run:
        return lane("lifecycle",
                    "the five lifecycle requirements walk through the real "
                    "command line, in order",
                    None, "",
                    "python3 plugins/dma-insights/scripts/"
                    "stress_run_lifecycle.py",
                    unmeasured_reason="not run: pass --lifecycle.")
    code, out = _run([sys.executable,
                      f"{PLUGIN}/scripts/stress_run_lifecycle.py"],
                     timeout=1800)
    return lane("lifecycle",
                "the five lifecycle requirements walk through the real "
                "command line, in order",
                code, out,
                "any step that cannot run says NOT_RUN with its reason "
                "rather than being skipped")


def assess(triggers=None, tests=False, lifecycle=False,
           offline=False) -> dict:
    lanes = [check_coverage(), check_skills(), check_taxonomy(),
             check_install(), check_connector(offline),
             check_routines(triggers),
             check_tests(tests), check_lifecycle(lifecycle)]
    return {
        "lanes": lanes,
        "ready": [r for r in lanes if r["verdict"] == READY],
        "blocked": [r for r in lanes if r["verdict"] == BLOCKED],
        "unmeasured": [r for r in lanes if r["verdict"] == UNMEASURED],
        # The subset a reader of the CHECKOUT can act on without knowing
        # which machine this ran on.
        "blocked_in_repository": [r for r in lanes
                                  if r["verdict"] == BLOCKED
                                  and r["scope"] == REPOSITORY],
        "standing_open": [
            {"item": i, "detail": d, "owner": o, "specified_in": s}
            for i, d, o, s in STANDING_OPEN],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--triggers", help="a saved list_triggers response")
    ap.add_argument("--tests", action="store_true",
                    help="run the full test suite (minutes)")
    ap.add_argument("--lifecycle", action="store_true",
                    help="walk the run lifecycle through the real CLI")
    ap.add_argument("--offline", action="store_true",
                    help="skip the lane that reaches the live service; it "
                         "reports NOT_MEASURABLE_HERE rather than passing")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any lane is unmeasured as well as "
                         "when one is blocked — what CI should use")
    a = ap.parse_args(argv)

    out = assess(a.triggers, a.tests, a.lifecycle, a.offline)
    rc = 1 if out["blocked"] else 0
    if a.strict and out["unmeasured"]:
        rc = 1

    if a.json:
        print(json.dumps(out, indent=2))
        return rc

    print(f"{len(out['ready'])}/{len(out['lanes'])} lane(s) READY · "
          f"{len(out['blocked'])} BLOCKED · "
          f"{len(out['unmeasured'])} NOT MEASURABLE HERE\n")
    for r in out["lanes"]:
        mark = {READY: "✓", BLOCKED: "✗"}.get(r["verdict"], "?")
        print(f"  {mark} {r['lane']:12s} {r['verdict']}")
        print(f"      {r['what']}")
        if r["verdict"] != READY:
            print(f"      ({r['scope']}) {r['detail']}")
            print(f"      → {r['fix']}")
    print(f"\n{len(out['standing_open'])} standing item(s) no script here "
          f"can close:")
    for s in out["standing_open"]:
        print(f"  · {s['item']} — {s['owner']} ({s['specified_in']})")

    if out["blocked"]:
        print(f"\nNOT READY: {len(out['blocked'])} lane(s) blocked.")
    elif out["unmeasured"]:
        print(f"\nNo lane is blocked, and {len(out['unmeasured'])} was never "
              f"measured from here. That is not the same as ready, and this "
              f"exits 0 only because --strict was not asked for.")
    else:
        print("\nEvery lane measured here is READY. The standing items above "
              "are still open.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
