"""Regression: deploy-chain resilience contracts (R6 + R7 from the
combined plan).

R6 (deploy-two-phase.sh): the candidate revision name MUST be
re-fetched freshly via a `_get_latest_candidate_revision` helper, NOT
captured once and re-used. Without the helper, Phase 4's diagnostic
log capture pointed at a STALE revision whenever Cloud Run rolled the
candidate-${SHA} tag mid-Phase-4 (which the mid-deploy heal regularly
does), masking the real root cause of any 503.

R7 (migrate.sh standalone mode): when SHA env is unset (operator
running migrate.sh directly), the script MUST infer SHA from the
deployed backend image rather than running with whatever image
terraform last applied. Without the fallback, standalone heal ran a
stale migrations image and Phase 4 failed with the same
'permission denied for table alembic_version' pattern as if the pin
had been skipped.

This file pins both contracts as static-source assertions so any
future refactor that drops them fails CI loud at Stage 1 (no
infrastructure required).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INFRA_DIR = Path(__file__).parent.parent.parent / "infra"
DEPLOY_TWO_PHASE = INFRA_DIR / "deploy-two-phase.sh"
MIGRATE_SH = INFRA_DIR / "migrate.sh"


@pytest.fixture(scope="module")
def deploy_two_phase_src() -> str:
    if not DEPLOY_TWO_PHASE.exists():
        pytest.skip(f"{DEPLOY_TWO_PHASE} not present in this checkout")
    return DEPLOY_TWO_PHASE.read_text()


@pytest.fixture(scope="module")
def migrate_sh_src() -> str:
    if not MIGRATE_SH.exists():
        pytest.skip(f"{MIGRATE_SH} not present in this checkout")
    return MIGRATE_SH.read_text()


# ── R6: deploy-two-phase.sh fresh-fetch helper ────────────────────────


def test_r6_helper_function_is_defined(deploy_two_phase_src: str) -> None:
    """The `_get_latest_candidate_revision` helper must be defined."""
    assert re.search(
        r"^\s*_get_latest_candidate_revision\(\)\s*\{",
        deploy_two_phase_src,
        re.MULTILINE,
    ), (
        "deploy-two-phase.sh must define a `_get_latest_candidate_revision` "
        "shell function for fresh per-call revision lookup. Without it, "
        "Phase 4's diagnostic log capture binds to a stale revision after "
        "any mid-deploy tag roll."
    )


def test_r6_helper_uses_fresh_gcloud_describe(deploy_two_phase_src: str) -> None:
    """The helper body must call `gcloud run services describe` fresh
    (no caching of the result) and filter by the candidate tag.

    Bash function bodies contain nested `{...}` (Python dict literals
    in heredocs), so a naive `\\{...?\\}` regex won't capture the full
    body. We instead match by line proximity: both signals must appear
    in the ~30 lines following the function header."""
    lines = deploy_two_phase_src.splitlines()
    header_idx: int | None = None
    for i, line in enumerate(lines):
        if "_get_latest_candidate_revision()" in line:
            header_idx = i
            break
    assert header_idx is not None, "helper header not found"
    window = "\n".join(lines[header_idx:header_idx + 30])
    assert "gcloud run services describe" in window, (
        "the helper must consult `gcloud run services describe` each call "
        "(no caching). Window:\n" + window[:600]
    )
    assert (
        "candidate-${SHA}" in window
        or "candidate-$SHA" in window
        or "candidate-{SHA}" in window
    ), (
        "the helper must filter by the candidate-${SHA} tag to pick the "
        "live candidate revision (not just any latest revision)"
    )


def test_r6_capture_candidate_logs_calls_helper(deploy_two_phase_src: str) -> None:
    """`_capture_candidate_logs` must consume the fresh-fetch helper,
    not re-implement the lookup inline (drift risk)."""
    m = re.search(
        r"_capture_candidate_logs\(\)\s*\{(?P<body>.*?)\n\}",
        deploy_two_phase_src,
        re.DOTALL,
    )
    assert m, "could not find _capture_candidate_logs function body"
    body = m.group("body")
    assert "_get_latest_candidate_revision" in body, (
        "_capture_candidate_logs must call _get_latest_candidate_revision "
        "rather than open-coding the gcloud describe + python parse. "
        "Drift between the two paths is exactly how the anti-pattern A "
        "regression resurfaced."
    )


# ── R7: migrate.sh standalone SHA fallback ────────────────────────────


def test_r7_migrate_sh_has_standalone_sha_fallback(migrate_sh_src: str) -> None:
    """When SHA env is unset, migrate.sh must detect the SHA from the
    deployed backend image so standalone heal mode uses the SAME image
    as the live backend (instead of whatever terraform last applied)."""
    # The fallback block runs BEFORE the existing `if SHA && PROJECT_ID`
    # pin block. Look for the canonical `gcloud run services describe
    # dma-insights-backend ... --format='value(spec.template.spec.
    # containers[0].image)'` call near a `SHA env unset` log line.
    assert "SHA env unset" in migrate_sh_src, (
        "migrate.sh must log when SHA is unset so the operator knows the "
        "fallback path fired"
    )
    pattern = (
        r"gcloud run services describe\s+dma-insights-backend"
        r".*?--format='value\(spec\.template\.spec\.containers\[0\]\.image\)'"
    )
    assert re.search(pattern, migrate_sh_src, re.DOTALL), (
        "migrate.sh must call `gcloud run services describe "
        "dma-insights-backend --format='value(spec.template.spec."
        "containers[0].image)'` to detect the deployed image when SHA "
        "is unset. Without this fallback, standalone heal runs a stale "
        "migrations image and Phase 4 fails the same way as a missing-pin "
        "deploy."
    )
    # The fallback must also extract the SHA from the tag suffix.
    assert re.search(
        r"BASH_REMATCH\[1\]|sed.*':'|cut.*':'",
        migrate_sh_src,
    ), (
        "migrate.sh must extract the SHA from the deployed image's tag "
        "suffix after `:` (via BASH_REMATCH, sed, or cut)"
    )


def test_r7_fallback_keeps_explicit_sha_override_path(migrate_sh_src: str) -> None:
    """The fallback path must still ALLOW the operator to pass SHA
    explicitly. The existing `if [[ -n SHA && -n PROJECT_ID ]]` pin
    block must remain reachable AFTER the fallback runs."""
    # The pin block must come AFTER the fallback so an explicit SHA wins.
    fallback_pos = migrate_sh_src.find("SHA env unset")
    pin_pos = migrate_sh_src.find("Pinning $JOB_NAME image to")
    assert fallback_pos > 0 and pin_pos > 0
    assert fallback_pos < pin_pos, (
        "the standalone-fallback block must run BEFORE the canonical "
        "pin block, so an explicit operator-set SHA still wins"
    )


# ── R5: cloudbuild ↔ deploy-two-phase SHA contract (Phase 0.5) ────────


def test_r5_phase_0_5_image_existence_check_exists(deploy_two_phase_src: str) -> None:
    """Phase 0.5 must call `gcloud container images describe` to verify
    the pre-built images exist for the deploying SHA -- catches the
    recurring `_IMAGE_SHA != SHA` foot-gun directly."""
    assert "PHASE 0.5" in deploy_two_phase_src, (
        "deploy-two-phase.sh must have a labelled PHASE 0.5 check between "
        "Phase 0 (parameter validation) and Phase 1 (build images)"
    )
    assert "gcloud container images describe" in deploy_two_phase_src, (
        "Phase 0.5 must consult `gcloud container images describe` to "
        "verify the SHA-tagged image exists"
    )
    # Must check BOTH backend and frontend images (mismatched SHA on
    # either one breaks the deploy).
    assert "dma-insights-backend" in deploy_two_phase_src
    assert "dma-insights-frontend" in deploy_two_phase_src


def test_r5_phase_0_5_only_runs_under_skip_build(deploy_two_phase_src: str) -> None:
    """The check only matters when the operator is reusing pre-built
    images. Phase 1 itself produces fresh images, so guarding the
    check behind SKIP_BUILD=true avoids a redundant `gcloud describe`
    on the normal deploy path."""
    lines = deploy_two_phase_src.splitlines()
    # Find PHASE 0.5 marker
    p05_idx = next(
        (i for i, ln in enumerate(lines) if "PHASE 0.5" in ln),
        None,
    )
    assert p05_idx is not None
    # The 10 lines BEFORE the marker should include the SKIP_BUILD guard.
    window = "\n".join(lines[max(0, p05_idx - 10): p05_idx + 1])
    assert "SKIP_BUILD" in window, (
        "Phase 0.5 must be guarded by `if [[ \"$SKIP_BUILD\" == \"true\" ]];` "
        "so it doesn't run when Phase 1 will rebuild images fresh"
    )


def test_r5_phase_0_5_emits_actionable_diagnostic(deploy_two_phase_src: str) -> None:
    """The failure message must point the operator at the EXACT fix
    (3 options: re-run cloudbuild, re-run deploy with the right SHA,
    or drop --skip-build). A generic error message would leave the
    operator walking the deploy chain backwards."""
    # The failure block should mention all 3 fixes
    for fix_marker in (
        "Re-run cloudbuild",
        "SHA=",  # the explicit-SHA fix command
        "--skip-build",  # the drop-flag fix
    ):
        assert fix_marker in deploy_two_phase_src, (
            f"Phase 0.5 failure message missing '{fix_marker}' -- the "
            f"3-option fix list keeps the diagnostic actionable. "
            f"Without all 3 the operator may guess wrong."
        )


# ── Cross-script: simulate-all-deploy-stages.sh Stage 17 still passes ──


def test_stage_17_migrate_image_pin_contract_unchanged_shape() -> None:
    """Stage 17 of the simulate harness asserts the migrate.sh image-pin
    contract. It checks for the canonical `gcloud run jobs update
    --image=` call AND the error-exit on failure. Both must still be
    present after the R7 fallback addition."""
    if not MIGRATE_SH.exists():
        pytest.skip(f"{MIGRATE_SH} not present")
    src = MIGRATE_SH.read_text()
    assert "gcloud run jobs update" in src, (
        "Stage 17 contract: migrate.sh must call `gcloud run jobs update`"
    )
    assert "--image=" in src, "image-pin call must include --image=..."
    # The exit-1 path on failure stays intact.
    assert re.search(r"exit\s+1", src), (
        "image-pin failure must exit non-zero (Stage 17 contract)"
    )
