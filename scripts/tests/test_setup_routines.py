"""Reconciling the scheduled routines, and the blast radius of "duplicate".

The routines were provisioned once and after that there was no way to ASK
whether they were still right. A paused job, a drifted schedule and a second
job aimed at the same target all look identical from inside the app.

The dangerous part is deletion. This project hosts 28 scheduler jobs and only
FOUR are ours — the rest are PTO sync, out-of-office checks, digests and
pollers belonging to other systems. A duplicate rule that matched on name
prefix, or on "looks like ours", would reach them.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "setup_routines", ROOT / "plugins" / "dma-insights" / "scripts" / "setup_routines.py")
sr = importlib.util.module_from_spec(_spec)
sys.modules["setup_routines"] = sr
_spec.loader.exec_module(sr)

MANIFEST = {
    "project": "p", "location": "l",
    "routines": [
        {"name": "dmai-package-scan", "schedule": "*/30 * * * *",
         "target_job": "dmai-worker", "mandatory": True},
        {"name": "dmai-pack-exporter", "schedule": "0 2 * * *",
         "target_job": "dmai-pack-exporter", "mandatory": True},
    ],
}


def _job(job, schedule="*/30 * * * *", state="ENABLED", v2=True):
    uri = (f"https://run.googleapis.com/v2/projects/p/locations/l/jobs/{job}:run"
           if v2 else
           f"https://l-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/p/jobs/{job}:run")
    return {"schedule": schedule, "state": state, "uri": uri,
            "target": sr._canonical_target(uri)}


def _state(plan, name):
    return next(p["state"] for p in plan if p["name"] == name)


def test_a_healthy_project_reports_ok_and_nothing_else():
    jobs = {"dmai-package-scan": _job("dmai-worker"),
            "dmai-pack-exporter": _job("dmai-pack-exporter", "0 2 * * *")}
    plan = sr.reconcile(MANIFEST, jobs)
    assert {p["state"] for p in plan} == {sr.OK}


def test_missing_paused_and_drifted_are_each_named():
    jobs = {"dmai-pack-exporter": _job("dmai-pack-exporter", "0 5 * * *")}
    plan = sr.reconcile(MANIFEST, jobs)
    assert _state(plan, "dmai-package-scan") == sr.MISSING
    assert _state(plan, "dmai-pack-exporter") == sr.DRIFTED

    jobs["dmai-pack-exporter"]["state"] = "PAUSED"
    jobs["dmai-pack-exporter"]["schedule"] = "0 2 * * *"
    assert _state(sr.reconcile(MANIFEST, jobs), "dmai-pack-exporter") == sr.PAUSED


def test_paused_outranks_drifted():
    """A paused job never fires, so its schedule is beside the point. Report
    the thing that actually stops the work."""
    jobs = {"dmai-pack-exporter": _job("dmai-pack-exporter", "9 9 * * *", "PAUSED")}
    assert _state(sr.reconcile(MANIFEST, jobs), "dmai-pack-exporter") == sr.PAUSED


# ── the blast radius ──────────────────────────────────────────────────
def test_a_second_job_on_the_same_target_is_a_duplicate():
    jobs = {"dmai-package-scan": _job("dmai-worker"),
            "dmai-package-scan-old": _job("dmai-worker", "0 * * * *")}
    plan = sr.reconcile(MANIFEST, jobs)
    assert _state(plan, "dmai-package-scan-old") == sr.DUPLICATE
    assert _state(plan, "dmai-package-scan") == sr.OK


def test_ANOTHER_SYSTEMS_JOB_IS_NEVER_A_DUPLICATE():
    """The one that matters. 24 of the 28 jobs in this project are not ours,
    and several are named `dma-*`, one character from `dmai-*`."""
    jobs = {"dmai-package-scan": _job("dmai-worker"),
            "dma-pto-sync": _job("pto-sync", "*/30 8-18 * * 1-5"),
            "dma-ooo-check": _job("ooo-check", "0 8 * * 1-5"),
            "dma-drive-probe": _job("drive-probe", "*/2 * * * 1-5"),
            "dma-insights-sheet-poller-5min": _job("dma-insights-sheet-poller")}
    plan = sr.reconcile(MANIFEST, jobs)
    dups = [p["name"] for p in plan if p["state"] == sr.DUPLICATE]
    assert dups == [], f"would have deleted another system's job: {dups}"


def test_a_name_that_merely_looks_like_ours_is_not_touched():
    jobs = {"dmai-package-scan": _job("dmai-worker"),
            "dmai-package-scan-canary": _job("some-other-job")}
    plan = sr.reconcile(MANIFEST, jobs)
    assert [p["name"] for p in plan if p["state"] == sr.DUPLICATE] == []


def test_two_api_spellings_of_one_target_are_the_same_target():
    """`dmai-enrich-loop` uses the v1 namespaces URI while the others use v2.
    Comparing raw URIs would call two spellings of one job different, and a
    real duplicate would go unreported."""
    v2 = _job("dmai-worker", v2=True)["target"]
    v1 = _job("dmai-worker", v2=False)["target"]
    assert v1 == v2 == "dmai-worker:run"
    jobs = {"dmai-package-scan": _job("dmai-worker", v2=True),
            "legacy-scan": _job("dmai-worker", "0 * * * *", v2=False)}
    assert _state(sr.reconcile(MANIFEST, jobs), "legacy-scan") == sr.DUPLICATE


def test_the_shipped_manifest_is_loadable_and_complete():
    import json
    m = json.loads((ROOT / "plugins" / "dma-insights" / "routines.json").read_text())
    assert m["project"] and m["location"]
    names = {r["name"] for r in m["routines"]}
    assert {"dmai-package-scan", "dmai-corpus-gate-scanner",
            "dmai-pack-exporter"} <= names, "the charter's mandatory three"
    for r in m["routines"]:
        assert r["schedule"] and r["target_job"] and r["why"], r
        assert len(r["schedule"].split()) == 5, f"{r['name']}: not a 5-field cron"
    mandatory = [r["name"] for r in m["routines"] if r.get("mandatory")]
    assert len(mandatory) == 3, mandatory
