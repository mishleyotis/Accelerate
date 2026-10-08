"""The deploy-on-merge job: it ships only what every check passed, only from
the default branch, and never with a stored key.

A merge to the default branch runs infra/deploy.sh. Three ways that goes
wrong without anyone noticing, each pinned here: a new CI job is added and the
deploy does not wait for it; the job is widened to pull requests or other
branches; or someone "fixes" the auth with a service-account key secret.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _wf():
    return yaml.safe_load(CI.read_text())


def test_deploy_waits_for_every_other_job():
    jobs = _wf()["jobs"]
    others = set(jobs) - {"deploy"}
    assert set(jobs["deploy"]["needs"]) == others


def test_deploy_runs_only_on_a_push_to_the_default_branch():
    cond = _wf()["jobs"]["deploy"]["if"]
    assert "github.event_name == 'push'" in cond
    assert "github.event.repository.default_branch" in cond


def test_deploy_is_never_cancelled_part_way():
    wf = _wf()
    assert wf["jobs"]["deploy"]["concurrency"]["cancel-in-progress"] is False
    # The workflow-level group must not cancel a default-branch run either.
    assert "default_branch" in str(wf["concurrency"]["cancel-in-progress"])


def test_deploy_authenticates_without_a_key():
    text = CI.read_text()
    assert "credentials_json" not in text
    deploy = _wf()["jobs"]["deploy"]
    assert deploy["permissions"]["id-token"] == "write"
    auth = [s for s in deploy["steps"]
            if str(s.get("uses", "")).startswith("google-github-actions/auth")]
    assert len(auth) == 1
    assert set(auth[0]["with"]) == {"workload_identity_provider", "service_account"}


def test_deploy_runs_the_release_script():
    steps = _wf()["jobs"]["deploy"]["steps"]
    assert any(s.get("run", "").strip() == "bash infra/deploy.sh" for s in steps)
