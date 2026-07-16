"""Phase 7 Terraform variable validation tests.

Per the audit Phase 7:
  - test_terraform_region_and_project_validation_reject_latest_or_branch_image_sha

Every `variable` block in main.tf must carry validation conditions
that reject obvious operator typos:
  - project_id must look like a real GCP project name
  - image_sha must be a real git SHA (NOT 'latest' or 'main')
  - region must be a known Cloud Run region

Without these guards, a `terraform apply -var "image_sha=latest"`
silently deploys whatever the registry's `:latest` tag points at --
removing the per-deploy traceability contract.
"""
from __future__ import annotations

import re
from pathlib import Path

TERRAFORM = (
    Path(__file__).resolve().parents[1].parent
    / "infra" / "terraform" / "main.tf"
).read_text(encoding="utf-8")


def _extract_variable_block(name: str) -> str:
    """Extract the body of `variable "X" { ... }` via brace counting."""
    m = re.search(rf'variable\s+"{re.escape(name)}"\s*\{{', TERRAFORM)
    assert m, f"variable {name!r} not declared in main.tf"
    start = m.end() - 1  # position of `{`
    depth = 0
    i = start
    while i < len(TERRAFORM):
        ch = TERRAFORM[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return TERRAFORM[start: i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces in variable {name!r}")


def test_project_id_variable_has_regex_validation():
    """project_id must look like a real GCP project name (lowercase
    letters + digits + hyphens). A typo'd project ID silently
    submits the build to the wrong project."""
    body = _extract_variable_block("project_id")
    assert "validation {" in body, (
        "variable project_id must declare validation { condition = ... }."
    )
    # The regex must enforce the GCP project naming rule.
    assert "regex(" in body
    # GCP project IDs are 6-30 chars; the validation should reflect that.
    assert "[a-z" in body  # lowercase enforcement


def test_image_sha_variable_rejects_latest_and_branch_names():
    """image_sha must be a 7-40 char lowercase hex git SHA -- NOT
    'latest', 'main', 'master', or any branch name. The audit
    pinned this as a P1 deployment safety: rolling back requires
    a SHA, not a floating tag."""
    body = _extract_variable_block("image_sha")
    assert "validation {" in body, "variable image_sha lacks validation"
    # The regex must enforce hex-only.
    assert "[0-9a-f]" in body, (
        "image_sha validation regex must enforce hex digits only. "
        "Without that, `latest` / `main` slip through."
    )
    # And must have a length bound (7-40 is the documented range).
    assert "7," in body or "{7," in body or "{7,40}" in body or "7,40" in body


def test_image_sha_validation_actually_rejects_latest():
    """Behaviour-check: build the regex from the validation block
    and confirm it rejects the canonical bad values."""
    body = _extract_variable_block("image_sha")
    m = re.search(r'regex\("([^"]+)"', body)
    assert m, "image_sha regex pattern not found"
    pattern = m.group(1)
    # Convert Terraform regex to Python regex (mostly compatible).
    compiled = re.compile(pattern)
    # MUST reject:
    for bad in ("latest", "main", "master", "HEAD", "branch-name"):
        assert not compiled.match(bad), (
            f"image_sha regex {pattern!r} accepts {bad!r} -- "
            "deployment safety contract broken."
        )
    # MUST accept:
    for good in ("abcdef0", "deadbeef", "a" * 40):
        assert compiled.match(good), (
            f"image_sha regex {pattern!r} rejects valid SHA {good!r}."
        )


def test_project_id_validation_actually_rejects_obvious_typos():
    """Behaviour-check: the project_id regex must accept real GCP
    project names + reject typos / URL-shaped inputs."""
    body = _extract_variable_block("project_id")
    m = re.search(r'regex\("([^"]+)"', body)
    assert m
    pattern = m.group(1)
    compiled = re.compile(pattern)
    # Real GCP project names:
    for good in ("digital-maturity-assessor", "dma-prod-2026"):
        assert compiled.match(good), (
            f"project_id regex rejects valid project {good!r}: {pattern!r}"
        )
    # Typos / URL-shaped inputs:
    for bad in ("Digital-Maturity", "dma_underscore", "x"):
        assert not compiled.match(bad), (
            f"project_id regex accepts invalid input {bad!r}"
        )


def test_required_variables_declared_in_terraform():
    """The audit's bootstrap contract requires these variables to
    exist in main.tf. A refactor that drops one silently breaks
    terraform plan with 'variable not declared'."""
    for var in ("project_id", "region", "image_sha", "google_oauth_client_id"):
        assert re.search(rf'variable\s+"{var}"\s*\{{', TERRAFORM), (
            f"required Terraform variable {var!r} missing from main.tf. "
            "Operators following DEPLOYMENT.md §0 will hit 'variable "
            "not declared' errors."
        )


def test_cloud_run_resources_pin_image_via_image_sha_variable():
    """Every Cloud Run service/job image reference MUST use
    `${var.image_sha}` -- NOT a hardcoded tag or `:latest`. The
    audit pinned this as the rollback-safety contract."""
    # Find every image = "..." assignment.
    image_refs = re.findall(r'image\s*=\s*"([^"]+)"', TERRAFORM)
    bad = []
    for ref in image_refs:
        # Acceptable: gcr.io/$X/dma-insights-Y:${var.image_sha}
        if (
            "${var.image_sha}" not in ref
            and "var.image_sha" not in ref
            and ("gcr.io" in ref or "dma-insights" in ref)
        ):
            bad.append(ref)
    assert not bad, (
        f"Cloud Run resources reference images without var.image_sha: "
        f"{bad}. Rollback contract broken -- no per-deploy SHA tag."
    )


def test_terraform_does_not_reference_latest_tag_anywhere():
    """A `:latest` tag anywhere in Cloud Run resource config defeats
    the per-deploy traceability + rollback contract. The audit pinned
    this as a P1: NEVER deploy a floating tag in prod."""
    # Cloud Run resource blocks must not include `:latest`. We allow
    # `:latest` in operator-facing scripts (tag-after-push) since
    # those are immediate. But the resource definitions themselves
    # must use a real SHA.
    cloud_run_blocks = re.findall(
        r'resource\s+"google_cloud_run_v2_(?:service|job)"[\s\S]+?(?=\nresource |\n\Z)',
        TERRAFORM,
    )
    bad = []
    for block in cloud_run_blocks:
        if ':latest"' in block:
            # Extract the resource name for the error message.
            name_m = re.search(r'resource\s+"google_cloud_run_v2_\w+"\s+"([^"]+)"', block)
            bad.append(name_m.group(1) if name_m else "unknown")
    assert not bad, (
        f"Cloud Run resources reference :latest tag: {bad}. Use "
        "var.image_sha instead so rollbacks work."
    )


def test_terraform_validation_messages_are_actionable():
    """When validation fires, the error_message must tell the
    operator what to do. A generic message wastes the deploy cycle
    on guessing."""
    for var in ("project_id", "image_sha"):
        body = _extract_variable_block(var)
        # Must have an error_message line.
        assert "error_message" in body, (
            f"variable {var!r} validation lacks error_message. "
            "Operators won't know what shape the value should take."
        )
        # And the error_message must be more than a single word.
        m = re.search(r'error_message\s*=\s*<<-?EOT([\s\S]+?)EOT', body)
        if m:
            msg = m.group(1).strip()
        else:
            m2 = re.search(r'error_message\s*=\s*"([^"]+)"', body)
            msg = m2.group(1) if m2 else ""
        assert len(msg) > 20, (
            f"variable {var!r} error_message too short ({len(msg)} chars). "
            "Be specific so the operator can fix the typo."
        )
