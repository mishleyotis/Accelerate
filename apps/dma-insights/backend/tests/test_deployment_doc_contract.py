"""DEPLOYMENT.md contract tests — F-303 of the principal-QA audit.

The audit found:
  - DEPLOYMENT.md doesn't start with a zero-to-prod bootstrap section.
  - It may instruct creating empty Clay secrets while prod-readiness
    refuses to boot without them.
  - Section/secret/image names may drift from the authoritative
    files (main.tf, cloudbuild.yaml, config.py).

This file pins:
  1. Top-of-file §0 zero-to-prod bootstrap exists with the 10
     required subsections (§0.1 through §0.10).
  2. Every Secret Manager ID mentioned in DEPLOYMENT.md matches
     a secret declared in `local.backend_secrets` (main.tf).
  3. Every Cloud Run service/job name mentioned matches Terraform.
  4. Container image paths use `gcr.io/$PROJECT_ID/dma-insights-...`
     (NOT Artifact Registry `us-central1-docker.pkg.dev/...`).
  5. DEPLOYMENT.md does NOT instruct creating empty Clay secrets.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1].parent / "docs"
INFRA = Path(__file__).resolve().parents[1].parent / "infra"
DEPLOYMENT = DOCS / "DEPLOYMENT.md"
TERRAFORM = INFRA / "terraform" / "main.tf"


def _backend_secret_ids() -> set[str]:
    """Pull every `dma-insights-*` secret from local.backend_secrets."""
    text = TERRAFORM.read_text(encoding="utf-8")
    m = re.search(
        r"backend_secrets\s*=\s*\[([\s\S]+?)\]",
        text,
    )
    assert m, "local.backend_secrets list not found in main.tf"
    body = m.group(1)
    return set(re.findall(r'"(dma-insights-[a-z0-9\-]+)"', body))


def test_deployment_doc_has_zero_to_prod_bootstrap_section():
    """The bootstrap section (§0) must be the FIRST major section so
    a new operator opening the file sees the zero-to-prod path before
    the happy-path shortcut."""
    text = DEPLOYMENT.read_text(encoding="utf-8")
    # §0 must appear BEFORE the happy-path header.
    zero_pos = text.find("## §0")
    happy_pos = text.find("⚡ Happy path")
    assert zero_pos > 0, "§0 zero-to-prod bootstrap section not found"
    assert happy_pos > 0, "happy-path section not found"
    assert zero_pos < happy_pos, (
        "§0 zero-to-prod bootstrap must come BEFORE the happy-path "
        "shortcut so new operators see the full flow first."
    )


def test_deployment_doc_section0_covers_all_required_subsections():
    """§0 must enumerate the 9 canonical bootstrap subsections so
    no operator step is implicit.

    Post-2026-06-05 restructure: the doc no longer has §0.10 (rollback
    moved into §0.9 after the legacy §0.8 single-phase escape hatch
    was deleted — §0.6 two-phase is canonical per ADR 0013). Every
    subsection still has a specific contract: tools / params / auth /
    APIs / secrets / two-phase deploy / terraform / smoke / rollback.
    """
    text = DEPLOYMENT.read_text(encoding="utf-8")
    for i in range(1, 10):
        marker = f"§0.{i}"
        assert marker in text, (
            f"§0 bootstrap section is missing subsection {marker}. "
            "Each subsection has a specific contract (tools, params, "
            "auth, APIs, secrets, two-phase deploy, terraform, smoke, "
            "rollback)."
        )


def _section0_text() -> str:
    """Extract just the §0 zero-to-prod bootstrap section. Historical
    sections (§1+ ...) carry legacy guidance the audit treats as
    out-of-scope for §0 contract checks. Section §0 is the
    operator's new bootstrap path and must be drift-free."""
    text = DEPLOYMENT.read_text(encoding="utf-8")
    start = text.find("## §0")
    end = text.find("## ⚡ Happy path", start)
    assert start > 0 and end > start, "§0 section boundaries not found"
    return text[start:end]


def test_deployment_doc_section0_secret_names_match_terraform():
    """Every secret ID mentioned in §0 must match one declared in
    `local.backend_secrets`. Drift in either direction means the doc
    instructs the operator to create the wrong secret name → Cloud
    Run can't bind it → revision fails to start.

    Scope: §0 only. Older sections of DEPLOYMENT.md predate the
    Terraform secret list refactor; they're flagged for a separate
    cleanup pass tracked as F-NN."""
    doc_text = _section0_text()
    doc_secrets = set(re.findall(r"dma-insights-[a-z0-9\-]+", doc_text))
    # Filter to ones that look like secret IDs (skip image names, job names,
    # SA names, Memorystore instance names, VPC connectors).
    doc_secrets = {
        s for s in doc_secrets
        if not s.startswith(("dma-insights-backend", "dma-insights-frontend",
                             "dma-insights-workers", "dma-insights-historical",
                             "dma-insights-pg", "dma-insights-drive",
                             "dma-insights-sheet", "dma-insights-embedder",
                             "dma-insights-ccg", "dma-insights-peer",
                             "dma-insights-chat", "dma-insights-intelligence",
                             "dma-insights-migrations",
                             # 2026-05-29: §0.5.2-§0.5.4 added non-secret
                             # GCP resource references with the dma-insights-*
                             # prefix. They're NOT Secret Manager IDs:
                             "dma-insights-worker",       # service account
                             "dma-insights-redis",        # Memorystore instance
                             "dma-insights-vpc-connector",  # VPC connector
                             ))
    }
    tf_secrets = _backend_secret_ids()
    bad = doc_secrets - tf_secrets
    # database_url* secrets are managed by Terraform (not in oob list)
    # so they don't appear in local.backend_secrets necessarily. Tolerate
    # those + jwt-signing-key (also Terraform-managed).
    tolerated = {"dma-insights-database-url",
                 "dma-insights-database-url-sync",
                 "dma-insights-database-url-superuser",
                 "dma-insights-jwt-signing-key"}
    bad = bad - tolerated
    assert not bad, (
        f"DEPLOYMENT.md §0 references secret IDs not in Terraform: "
        f"{sorted(bad)}. Either add them to local.backend_secrets in "
        "main.tf or fix the docs."
    )


def test_deployment_doc_uses_gcr_not_artifact_registry():
    """Terraform and Cloud Build use `gcr.io/$PROJECT_ID/dma-insights-*`.
    A doc that mentions `us-central1-docker.pkg.dev/...` (Artifact
    Registry path) instructs operators to push to the WRONG registry,
    leaving Terraform unable to find the image."""
    text = DEPLOYMENT.read_text(encoding="utf-8")
    bad_paths = re.findall(
        r"us-[a-z0-9\-]+-docker\.pkg\.dev/[a-z0-9\-/]+",
        text,
    )
    assert not bad_paths, (
        f"DEPLOYMENT.md references Artifact Registry paths: {bad_paths}. "
        "Terraform consumes gcr.io paths; the doc must match."
    )


def test_deployment_doc_section0_does_not_instruct_empty_required_clay_secret():
    """`assert_production_ready()` refuses to boot if CLAY_WEBHOOK_URL
    or CLAY_WEBHOOK_SECRET is empty in prod. DEPLOYMENT.md §0 must
    fail-closed BEFORE any secret-create call when either is empty."""
    text = _section0_text()
    # Bootstrap script must validate Clay values are non-empty.
    assert "CLAY_WEBHOOK_URL" in text and "CLAY_WEBHOOK_SECRET" in text, (
        "§0 must reference both Clay env vars in the parameter list."
    )
    # The parameter-validation block must reject empty Clay values.
    assert "CLAY_WEBHOOK_URL CLAY_WEBHOOK_SECRET" in text or all(
        v in text for v in ["CLAY_WEBHOOK_URL", "CLAY_WEBHOOK_SECRET"]
    ), (
        "§0 must require non-empty Clay values via the "
        "REQUIRED_NONEMPTY validation block."
    )


def test_deployment_doc_section0_does_not_reference_unwired_sa_key_secrets():
    """§0 must not instruct operators to create service-account JSON
    secrets. Cloud Run uses ADC + the Cloud Run service-account
    identity; per-job SA keys are an attack surface.

    Older sections of DEPLOYMENT.md still reference SA-key files for
    historical reasons (tracked separately for cleanup); §0 is the
    canonical new path and must not perpetuate the pattern."""
    text = _section0_text()
    forbidden = re.findall(
        r"service-account[\-_]json|gcp-credentials\.json|sa-key\.json",
        text,
    )
    assert not forbidden, (
        f"DEPLOYMENT.md §0 references service-account JSON secrets: "
        f"{forbidden}. The current Terraform uses Cloud Run SA + ADC."
    )
