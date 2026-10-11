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
    others = set(jobs) - {"deploy", "deploy-evidence"}
    assert set(jobs["deploy"]["needs"]) == others


def test_the_evidence_deploy_is_its_own_job_after_the_release():
    """2026-10-11: deploy.sh used ~25 of the job's 45 minutes; the four source
    builds need a clock of their own. The job waits for the release, runs
    from the default branch only, is never cancelled part-way, and does not
    share the release's concurrency group (a newer run's pending release
    would cancel it while it waits)."""
    jobs = _wf()["jobs"]
    ev = jobs["deploy-evidence"]
    assert ev["needs"] == ["deploy"]
    assert ev["if"] == jobs["deploy"]["if"]
    assert ev["concurrency"]["cancel-in-progress"] is False
    assert ev["concurrency"]["group"] != jobs["deploy"]["concurrency"]["group"]
    assert ev["permissions"]["id-token"] == "write"
    auth = [s for s in ev["steps"] if str(s.get("uses", "")).startswith("google-github-actions/auth")]
    assert len(auth) == 1 and set(auth[0]["with"]) == {"workload_identity_provider", "service_account"}


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
    its approval file, in the job that runs after the release; the gate step
    runs under the same credential check."""
    jobs = _wf()["jobs"]
    release = [s.get("run", "").strip() for s in jobs["deploy"]["steps"]]
    assert "bash infra/evidence-engine/ci_gate.sh" not in release
    steps = jobs["deploy-evidence"]["steps"]
    gate = next(s for s in steps if s.get("run", "").strip() == "bash infra/evidence-engine/ci_gate.sh")
    assert gate.get("if") == "steps.cfg.outputs.ready == 'true'"


def _gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("approval_check", ROOT / "infra" / "evidence-engine" / "approval_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_evidence_approval_gate_refuses_until_the_metric_clears_the_threshold(tmp_path):
    """Two metrics, one bar. `recall_url` is the morning's rule (figures in
    the file); `question_coverage` is the owner's afternoon choice
    (2026-10-11, "Fix the above to ensure deploy happens") and is RECOMPUTED
    from the results file's per-call rows, never read from the approval."""
    import json
    mod = _gate()
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert not ok and "absent" in why
    results = tmp_path / "r.json"; results.write_text("{}")
    base = {"approved_by": "owner", "date": "2026-10-11", "golden_version": "v1", "results": str(results)}
    (tmp_path / "APPROVAL.json").write_text(json.dumps(dict(base, recall_url_tuning=0.95, recall_url_heldout=0.95)))
    assert not mod.check(tmp_path / "APPROVAL.json")[0], "no metric named: refused"
    low = dict(base, metric="recall_url", recall_url_tuning=0.95, recall_url_heldout=0.60)
    (tmp_path / "APPROVAL.json").write_text(json.dumps(low))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert not ok and "held-out 60.0%" in why
    good = dict(base, metric="recall_url", recall_url_tuning=0.92, recall_url_heldout=0.91)
    (tmp_path / "APPROVAL.json").write_text(json.dumps(good))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert ok and why.startswith("APPROVED")
    # coverage: recomputed from the rows, the figure in the file is ignored
    def rows(t_ok, t_n, h_ok, h_n):
        calls = []
        for split, k, n in (("tuning", t_ok, t_n), ("heldout", h_ok, h_n)):
            for i in range(n):
                em = {"confirmed": 1} if i < k else {"ambiguous": 2}
                calls.append({"split": split, "entity_match": em})
        return {"calls": calls}
    cov = dict(base, metric="question_coverage", recall_url_tuning=0.2, recall_url_heldout=0.2)
    results.write_text(json.dumps(rows(9, 10, 9, 10)))
    (tmp_path / "APPROVAL.json").write_text(json.dumps(cov))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert not ok and "90.0%" in why, why                       # 9/10 is AT the bar, not above it
    results.write_text(json.dumps(rows(10, 10, 9, 9)))
    ok, why = mod.check(tmp_path / "APPROVAL.json")
    assert ok and "question coverage tuning 100.0% (10/10)" in why and "same-URL recall reported 20.0%" in why
    results.write_text(json.dumps(rows(10, 10, 0, 0)))
    assert not mod.check(tmp_path / "APPROVAL.json")[0], "a split with no calls cannot clear anything"


def test_the_committed_approval_is_the_owners_and_clears_the_gate_it_names():
    """The tree carries an approval only while it clears the bar, and the
    one it carries names the owner's words and a results file in the tree."""
    import json
    mod = _gate()
    live = ROOT / "infra" / "evidence-engine" / "APPROVAL.json"
    if not live.exists():
        return
    ok, why = mod.check(live)
    assert ok, why
    d = json.loads(live.read_text())
    assert d["metric"] in mod.METRICS and "owner" in d["approved_by"]
    assert (ROOT / d["results"]).exists()
    if d["metric"] == "question_coverage":
        assert "owner_words" in d and "recall_url_tuning" in d, "the deviation from the 90 % wording is recorded"


def test_a_new_identity_is_bound_after_iam_sees_it(tmp_path):
    """2026-10-11, the first approved run: `service-accounts create` succeeded
    and the role binding one second later read "does not exist" (IAM is
    eventually consistent), so the release stopped at step 0. A binding is
    retried with backoff; anything else still runs once and stops the
    release on a real error. Driven through a fake gcloud on PATH."""
    import os
    import subprocess
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    state = tmp_path / "state"; state.mkdir()
    fake = bin_dir / "gcloud"
    fake.write_text(r'''#!/usr/bin/env bash
echo "$*" >> "$STATE/calls"
case "$*" in
  *"service-accounts describe"*)
    [ -f "$STATE/created" ] && exit 0 || exit 1 ;;
  *"service-accounts create"*)
    touch "$STATE/created"; exit 0 ;;
  *"projects add-iam-policy-binding"*)
    n=$(cat "$STATE/bind" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$STATE/bind"
    [ "$n" -ge 3 ] && exit 0
    echo "INVALID_ARGUMENT: Service account does not exist." >&2; exit 1 ;;
  *"secrets describe"*) exit 0 ;;
  *) exit 0 ;;
esac
''')
    fake.chmod(0o755)
    script = ROOT / "infra" / "evidence-engine" / "deploy-evidence.sh"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", STATE=str(state),
               EE_DEPLOY_APPROVED="1", EE_GRANT_PROJECT_ROLES="1",
               EE_BIND_SLEEP_S="0", EE_BIND_ATTEMPTS="4", EE_STATIC_EGRESS="0")
    # stop after the identities: the fake answers the rest, but only step 0 matters here
    src = script.read_text().split('say "1 · secrets')[0]
    cut = tmp_path / "step0.sh"; cut.write_text(src)
    r = subprocess.run(["bash", str(cut)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "retrying" in r.stderr, "the refused binding was retried, not fatal"
    calls = (state / "calls").read_text()
    assert calls.count("service-accounts create") == 1
    # a binding that never succeeds still stops the release
    (state / "bind").write_text("-100")
    for f in ("created", "calls"):
        (state / f).unlink()
    r = subprocess.run(["bash", str(cut)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "still refused after 4 attempts" in r.stderr
