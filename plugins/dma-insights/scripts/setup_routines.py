#!/usr/bin/env python3
"""Reconcile a project's scheduled routines against `routines.json`.

WHY THIS EXISTS. The routines were provisioned once by `infra/provision.sh` and
after that there was no way to ASK whether they were still right. A paused job,
a drifted schedule, and a second job aimed at the same Cloud Run target all
look identical from inside the app: nothing happens, or something happens
twice, and neither announces itself.

WHAT IT DOES, in one pass:

    missing     the routine is not there            -> create
    paused      it exists and will never fire       -> resume
    drifted     its schedule is not the declared one -> correct
    duplicate   ANOTHER job aims at the same target -> delete
    ok          nothing to do

DRY RUN BY DEFAULT. Nothing is created, changed or deleted without `--apply`.
A tool that provisions on sight is one typo away from rewriting a schedule
somebody chose deliberately.

THE DUPLICATE RULE IS NARROW ON PURPOSE. A duplicate is a job whose target URI
matches a declared routine's target and whose name is not that routine's name.
This project hosts around two dozen scheduler jobs belonging to other systems —
PTO sync, out-of-office checks, digests — and a rule that matched on name
prefix or on "looks like ours" would reach them. Target identity is the only
evidence that two jobs do the same work.

    python setup_routines.py                 # report only
    python setup_routines.py --apply         # create/resume/correct
    python setup_routines.py --apply --delete-duplicates
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / "routines.json"

OK, MISSING, PAUSED, DRIFTED, DUPLICATE = (
    "ok", "missing", "paused", "drifted", "duplicate")


def _gcloud() -> str:
    """gcloud, wherever it is. The same search the auth helper makes, for the
    same reason: on the container this ships in it lives outside PATH."""
    found = shutil.which("gcloud")
    if found:
        return found
    for candidate in (f"{os.environ.get('HOME', '')}/google-cloud-sdk/bin/gcloud",
                      "/root/google-cloud-sdk/bin/gcloud",
                      "/usr/local/google-cloud-sdk/bin/gcloud",
                      "/opt/google-cloud-sdk/bin/gcloud"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("gcloud not found on PATH or in the usual install "
                     "locations; this reconciles Cloud Scheduler and cannot "
                     "run without it")


def _run(args: list) -> str:
    env = dict(os.environ)
    # A stale token in the environment overrides the activated account and
    # fails with a 401 that reads like a permissions problem.
    env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])}…: {proc.stderr.strip()[:300]}")
    return proc.stdout


def target_uri(project: str, location: str, job: str) -> str:
    return (f"https://run.googleapis.com/v2/projects/{project}/locations/"
            f"{location}/jobs/{job}:run")


def _canonical_target(uri: str) -> str:
    """Two API shapes name one job.

    Cloud Scheduler jobs in this project use both the v2 form and the older
    `namespaces/.../jobs/x:run` form — `dmai-enrich-loop` is on the old one.
    Comparing the raw URI would call two spellings of the same target
    different, and then a duplicate check reports nothing while a real
    duplicate sits there. Reduced to `<job>:run`, which is the part that
    identifies the work.
    """
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail.endswith(":run") else uri


def survey(gcloud: str, project: str, location: str) -> dict:
    out = _run([gcloud, "scheduler", "jobs", "list", "--location", location,
                "--project", project, "--format",
                "value(name.basename(),schedule,state,httpTarget.uri)"])
    jobs = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, schedule, state, uri = parts[0], parts[1], parts[2], parts[3]
        jobs[name] = {"schedule": schedule, "state": state, "uri": uri,
                      "target": _canonical_target(uri)}
    return jobs


def reconcile(manifest: dict, jobs: dict) -> list:
    """What each declared routine needs, plus any duplicates found."""
    project, location = manifest["project"], manifest["location"]
    plan = []
    declared_targets = {}
    for r in manifest["routines"]:
        want_target = _canonical_target(
            target_uri(project, location, r["target_job"]))
        declared_targets[want_target] = r["name"]
        have = jobs.get(r["name"])
        if have is None:
            plan.append({**r, "state": MISSING, "detail":
                         "not present; nothing fires this work"})
        elif have["state"] != "ENABLED":
            plan.append({**r, "state": PAUSED, "detail":
                         f"state is {have['state']}; it will never fire"})
        elif have["schedule"] != r["schedule"]:
            plan.append({**r, "state": DRIFTED, "detail":
                         f"schedule is {have['schedule']!r}, declared "
                         f"{r['schedule']!r}"})
        else:
            plan.append({**r, "state": OK, "detail": "enabled, on schedule"})

    for name, job in sorted(jobs.items()):
        owner = declared_targets.get(job["target"])
        if owner and owner != name:
            plan.append({"name": name, "state": DUPLICATE,
                         "schedule": job["schedule"],
                         "target_job": job["target"],
                         "detail": f"aims at the same target as {owner!r}; "
                                   "two jobs doing one job's work"})
    return plan


def apply(gcloud: str, manifest: dict, plan: list, delete_duplicates: bool,
          service_account: str | None) -> list:
    project, location = manifest["project"], manifest["location"]
    done = []
    for item in plan:
        name, state = item["name"], item["state"]
        base = [gcloud, "scheduler", "jobs", "--location", location,
                "--project", project]
        try:
            if state == MISSING:
                if not service_account:
                    done.append(f"SKIP  {name}: --service-account is required "
                                "to create a routine (Cloud Scheduler must "
                                "present an identity Cloud Run will accept)")
                    continue
                _run([gcloud, "scheduler", "jobs", "create", "http", name,
                      "--location", location, "--project", project,
                      "--schedule", item["schedule"],
                      "--uri", target_uri(project, location, item["target_job"]),
                      "--http-method", "POST",
                      "--oauth-service-account-email", service_account])
                done.append(f"CREATED  {name}  {item['schedule']}")
            elif state == PAUSED:
                _run(base[:4] + ["resume", name] + base[4:])
                done.append(f"RESUMED  {name}")
            elif state == DRIFTED:
                _run([gcloud, "scheduler", "jobs", "update", "http", name,
                      "--location", location, "--project", project,
                      "--schedule", item["schedule"]])
                done.append(f"CORRECTED  {name} -> {item['schedule']}")
            elif state == DUPLICATE and delete_duplicates:
                _run([gcloud, "scheduler", "jobs", "delete", name,
                      "--location", location, "--project", project, "--quiet"])
                done.append(f"DELETED  {name}  (duplicate)")
        except RuntimeError as exc:
            done.append(f"FAILED   {name}: {exc}")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delete-duplicates", action="store_true")
    ap.add_argument("--service-account", default=None,
                    help="identity Cloud Scheduler presents to Cloud Run; "
                         "needs roles/run.invoker on the target")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    gcloud = _gcloud()
    jobs = survey(gcloud, manifest["project"], manifest["location"])
    plan = reconcile(manifest, jobs)

    if args.json:
        print(json.dumps({"plan": plan}, indent=1))
    else:
        print(f"{len(jobs)} scheduler job(s) in "
              f"{manifest['project']}/{manifest['location']}; "
              f"{len(manifest['routines'])} declared\n")
        for item in plan:
            mark = {OK: "ok      ", MISSING: "MISSING ", PAUSED: "PAUSED  ",
                    DRIFTED: "DRIFTED ", DUPLICATE: "DUPLICATE"}[item["state"]]
            star = "*" if item.get("mandatory") else " "
            print(f"  {mark}{star} {item['name']:32} {item['detail']}")
        print("\n  * mandatory per the build charter")

    todo = [p for p in plan if p["state"] != OK]
    if not args.apply:
        if todo:
            print(f"\n{len(todo)} routine(s) need attention. Re-run with "
                  "--apply to create, resume and correct; add "
                  "--delete-duplicates to remove a job that duplicates a "
                  "declared target.")
        else:
            print("\nevery declared routine is present, enabled and on schedule.")
        return 1 if any(p["state"] == MISSING and p.get("mandatory")
                        for p in plan) else 0

    for line in apply(gcloud, manifest, plan, args.delete_duplicates,
                      args.service_account):
        print(f"  {line}")
    after = reconcile(manifest, survey(gcloud, manifest["project"],
                                       manifest["location"]))
    left = [p for p in after if p["state"] not in (OK, DUPLICATE)]
    print(f"\nafter: {len(left)} routine(s) still need attention"
          if left else "\nafter: every declared routine is present, enabled "
                       "and on schedule.")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
