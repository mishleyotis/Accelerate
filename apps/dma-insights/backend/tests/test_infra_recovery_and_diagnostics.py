"""Infra parity + diagnostic regression tests.

Closes audit findings F-301 (recover-db-passwords job list parity)
and F-302 (Cloud Build E2E failure trap).

Each test enforces an exact-match contract between two files so
adding a new worker / job to one without the other trips the test.
"""
from __future__ import annotations

import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1].parent / "infra"
TERRAFORM = INFRA / "terraform" / "main.tf"
RECOVER = INFRA / "recover-db-passwords.sh"
CLOUDBUILD = INFRA / "cloudbuild.yaml"


def _terraform_job_names() -> set[str]:
    """Extract Cloud Run Job names that Terraform creates via the
    `worker` for_each + the standalone job resources (migrations,
    historical_backfill). Returns the exact resource names used by
    `gcloud run jobs <name>` calls."""
    text = TERRAFORM.read_text(encoding="utf-8")
    jobs: set[str] = set()
    # locals.jobs map keys → dma-insights-<key-with-dashes>. Brace-balanced
    # extraction so it tolerates comments between `locals {` and `jobs =` AND
    # per-job object values (`name = { args = [...], timeout = ..., max_retries
    # = ... }`, 2026-06 cost safeguard). Each job key is the only `<key> = {`
    # at the top level of the map (the object fields use `= [`, `= "`, `= N`).
    start = text.find("jobs = {")
    assert start != -1, "locals.jobs map not found in main.tf"
    open_idx = text.index("{", start)
    depth = 0
    body = ""
    for j in range(open_idx, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                body = text[open_idx + 1:j]
                break
    assert body, "could not brace-balance the locals.jobs map"
    for m2 in re.finditer(r"^\s+([a-z_][a-z0-9_]*)\s*=\s*\{", body, re.M):
        jobs.add(f"dma-insights-{m2.group(1).replace('_', '-')}")
    # Standalone job resources by literal name attribute. Skip the
    # `worker` for_each resource whose name uses Terraform interpolation
    # (`${replace(each.key, "_", "-")}`) -- its concrete names are
    # already covered by the locals.jobs map walk above.
    for m3 in re.finditer(
        r'resource\s+"google_cloud_run_v2_job"\s+"[^"]+"\s*\{[^}]*?name\s*=\s*"([^"]+)"',
        text,
    ):
        name = m3.group(1)
        if "${" in name:
            continue
        jobs.add(name)
    return jobs


def _recover_script_job_names() -> set[str]:
    """Extract the job names rolled by recover-db-passwords.sh."""
    text = RECOVER.read_text(encoding="utf-8")
    # The recover loop reads `for job in dma-insights-... ; do`.
    m = re.search(
        r"for job in\s+([^\n]+(?:\n[^\n]+)*?);\s*do",
        text,
    )
    assert m, "for-job loop not found in recover-db-passwords.sh"
    raw = m.group(1)
    # Strip backslash-continuations and split on whitespace.
    cleaned = raw.replace("\\\n", " ").replace("\\", " ")
    return {tok for tok in cleaned.split() if tok.startswith("dma-insights-")}


def test_recover_db_passwords_rolls_every_terraform_cloud_run_job():
    """F-301: when Terraform creates a new Cloud Run Job, the
    recover-db-passwords.sh force-revision-roll loop MUST include it.
    Otherwise a password rotation leaves cached creds in the
    omitted job until its next manual deploy."""
    terraform_jobs = _terraform_job_names()
    rolled_jobs = _recover_script_job_names()
    missing = terraform_jobs - rolled_jobs
    assert not missing, (
        f"recover-db-passwords.sh does not roll these Terraform-"
        f"defined jobs: {sorted(missing)}. Add them to the for-loop "
        "around line 230, or document why they shouldn't be rolled."
    )


def test_recover_script_does_not_roll_phantom_jobs():
    """Inverse of the parity check: if recover-db-passwords.sh lists
    a job that no longer exists in Terraform, `gcloud run jobs update`
    will fail and the operator sees a misleading 'job not found'
    error during a rotation. Keep the list tight."""
    terraform_jobs = _terraform_job_names()
    rolled_jobs = _recover_script_job_names()
    phantom = rolled_jobs - terraform_jobs
    assert not phantom, (
        f"recover-db-passwords.sh rolls these jobs that don't exist "
        f"in Terraform: {sorted(phantom)}. Remove from the for-loop "
        "or restore them to main.tf."
    )


def test_cloudbuild_e2e_stage_has_failure_trap():
    """F-302: the e2e-personas stage MUST install a bash `trap` that
    dumps backend + PG logs on failure. Without it a Playwright
    selector-timeout shows up in the build log with no actionable
    context (the original /admin admin-page bug took >5 days to
    diagnose for exactly this reason)."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    # Find the e2e-personas stage block.
    m = re.search(
        r"- id: e2e-personas[\s\S]+?(?=^  - id:)",
        text,
        re.MULTILINE,
    )
    assert m, "e2e-personas stage not found in cloudbuild.yaml"
    stage = m.group(0)
    assert "trap" in stage, (
        "e2e-personas stage must install a bash trap to dump "
        "backend / PG logs on failure."
    )
    assert "docker logs" in stage, (
        "e2e-personas trap must dump container logs (docker logs ...)."
    )


def test_cloudbuild_e2e_stage_cleans_up_on_both_success_and_failure():
    """The trap must run cleanup unconditionally so containers don't
    leak between Cloud Build runs."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    m = re.search(
        r"- id: e2e-personas[\s\S]+?(?=^  - id:)",
        text,
        re.MULTILINE,
    )
    assert m
    stage = m.group(0)
    assert "docker rm -f dma-ci-e2e-backend dma-ci-e2e-pg" in stage, (
        "e2e-personas trap must rm the containers on cleanup so they "
        "don't accumulate across builds."
    )


def test_cloudbuild_e2e_stage_has_no_advisory_swallow():
    """No `|| true` or `|| echo '::warning::'` on the Playwright
    invocation itself -- the audit insists the e2e suite is BLOCKING
    not advisory."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    m = re.search(
        r"- id: e2e-personas[\s\S]+?(?=^  - id:)",
        text,
        re.MULTILINE,
    )
    assert m
    stage = m.group(0)
    # Match the playwright command line + its `pnpm test:e2e` invocation.
    pnpm_lines = [
        line for line in stage.splitlines()
        if "pnpm test:e2e" in line or "pnpm test:visual" in line
    ]
    assert pnpm_lines, "pnpm test:e2e / test:visual invocation not found"
    for line in pnpm_lines:
        assert "|| true" not in line, (
            f"e2e invocation has advisory swallow: {line.strip()}"
        )
        assert "::warning::" not in line, (
            f"e2e invocation downgraded to warning: {line.strip()}"
        )
