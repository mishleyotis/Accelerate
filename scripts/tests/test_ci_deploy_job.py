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


def test_deploy_runs_the_evidence_gate_after_the_release_script():
    """The evidence engine rides the same merge-to-default release, behind
    its approval file; the gate step follows deploy.sh and runs under the
    same credential check."""
    steps = _wf()["jobs"]["deploy"]["steps"]
    runs = [s.get("run", "").strip() for s in steps]
    assert "bash infra/evidence-engine/ci_gate.sh" in runs
    assert runs.index("bash infra/evidence-engine/ci_gate.sh") > runs.index("bash infra/deploy.sh")
    gate = next(s for s in steps if s.get("run", "").strip() == "bash infra/evidence-engine/ci_gate.sh")
    assert gate.get("if") == "steps.cfg.outputs.ready == 'true'"


def test_the_evidence_approval_gate_refuses_until_recall_clears_the_threshold(tmp_path):
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("approval_check", ROOT / "infra" / "evidence-engine" / "approval_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert not ok and "absent" in why
    results = tmp_path / "r.json"; results.write_text("{}")
    base = {"approved_by": "owner", "date": "2026-10-11", "golden_version": "v1", "results": str(results)}
    low = dict(base, recall_url_tuning=0.95, recall_url_heldout=0.60)
    (tmp_path / "APPROVAL.json").write_text(json.dumps(low))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert not ok and "held-out 60.0%" in why
    good = dict(base, recall_url_tuning=0.92, recall_url_heldout=0.91)
    (tmp_path / "APPROVAL.json").write_text(json.dumps(good))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert ok and why.startswith("APPROVED")
    # the committed tree carries no approval unless it clears the bar
    live = ROOT / "infra" / "evidence-engine" / "APPROVAL.json"
    if live.exists():
        assert mod.check(live)[0], "an APPROVAL.json that does not clear the threshold must not be committed"
