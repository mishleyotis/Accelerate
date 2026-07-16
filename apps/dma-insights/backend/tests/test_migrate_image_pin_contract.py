"""Regression: deploy-two-phase.sh + migrate.sh must pin the migrations
Cloud Run Job's image to the DEPLOYING SHA before executing the job.

The bug shape this guards against:

  - deploy-two-phase.sh Phase 2 updates the BACKEND SERVICE to
    gcr.io/$PROJECT_ID/dma-insights-backend:$SHA.
  - deploy-two-phase.sh Phase 3 calls migrate.sh which does
    `gcloud run jobs execute dma-insights-migrations` -- but Cloud Run
    JOBS are NOT updated by `gcloud run services update`. The
    migrations job's image is whatever terraform last applied -- often
    many deploys behind.
  - The OLD migrations image runs OLD alembic + OLD post_migrate.py.
    OLD post_migrate may lack the GRANT chain the NEW backend's
    /readyz expects (e.g. the 2026-06-06 explicit alembic_version
    GRANT) -> Phase 4 503s with
        "InsufficientPrivilegeError: permission denied for table
         alembic_version"
    and the deploy aborts. Operator sees the recurring symptom every
    time post_migrate.py changes.

Fix shape this test enforces:

  - migrate.sh must contain a block that runs
    `gcloud run jobs update dma-insights-migrations --image=...:$SHA`
    when both SHA and PROJECT_ID are set in the env.
  - deploy-two-phase.sh must export SHA + PROJECT_ID to migrate.sh's
    environment before invoking it (otherwise the block above is a
    no-op on every CI deploy).
"""
from __future__ import annotations

import re
from pathlib import Path


def _find_infra_dir() -> Path:
    """Locate apps/dma-insights/infra by walking up from this file.
    parents[N] is fragile under CI runners that mount the repo at
    arbitrary depth -- walk up until we find a recognisable marker."""
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "infra" / "migrate.sh"
        if candidate.exists():
            return candidate.parent
        canonical = ancestor / "apps" / "dma-insights" / "infra" / "migrate.sh"
        if canonical.exists():
            return canonical.parent
    raise RuntimeError(f"could not locate infra/migrate.sh walking up from {here}")


INFRA = _find_infra_dir()
MIGRATE = INFRA / "migrate.sh"
DEPLOY_TWO_PHASE = INFRA / "deploy-two-phase.sh"


def test_migrate_sh_pins_migrations_job_image_to_sha() -> None:
    """The script must update the migrations job's container image to
    `gcr.io/<project>/dma-insights-backend:<sha>` before executing the
    job, so the SAME code path that built the NEW backend image also
    runs alembic + post_migrate."""
    src = MIGRATE.read_text()
    # Strip comment lines so docstring references to `gcloud run jobs
    # execute` (used for context) don't confuse the ordering check.
    non_comment = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    # Image expression must reference both PROJECT_ID and SHA.
    assert re.search(
        r'gcr\.io/\$\{?PROJECT_ID\}?/dma-insights-backend:\$\{?SHA\}?',
        non_comment,
    ), "migrate.sh missing the gcr.io/.../dma-insights-backend:$SHA image expression"
    # And it must be passed to a `gcloud run jobs update --image=...`
    # before the `gcloud run jobs execute` call (i.e. the ACTUAL
    # invocation line, not a comment reference).
    image_flag_idx = non_comment.find('--image="$MIGRATIONS_IMAGE"')
    execute_match = re.search(
        r'^\s*if\s+!\s+gcloud run jobs execute "\$JOB_NAME"',
        non_comment,
        flags=re.MULTILINE,
    )
    assert image_flag_idx > 0, "migrate.sh missing --image= flag on the migrations job update"
    assert execute_match is not None, (
        "migrate.sh missing the actual `gcloud run jobs execute \"$JOB_NAME\"` "
        "invocation"
    )
    assert image_flag_idx < execute_match.start(), (
        "migrate.sh pins the image AFTER execute -- the update needs to "
        "happen first so execute runs the NEW image."
    )


def test_migrate_sh_idempotent_when_already_at_target_image() -> None:
    """When the migrations job is already at the target image SHA,
    migrate.sh must skip the gcloud update call (saves an unnecessary
    revision roll + the gcloud rate-limit hit). Asserted by source
    inspection -- the script must early-return on equality."""
    src = MIGRATE.read_text()
    assert 'if [[ "$current_image" == "$MIGRATIONS_IMAGE" ]]' in src, (
        "migrate.sh missing the idempotent same-image short-circuit"
    )
    assert "already at" in src, (
        "migrate.sh idempotent branch missing the operator-visible log line"
    )


def test_migrate_sh_skips_image_pin_when_sha_unset() -> None:
    """Standalone heal mode -- operator runs migrate.sh without a deploy
    SHA in scope -- must NOT call `gcloud run jobs update --image`,
    because that would point the migrations job at gcr.io/.../backend:
    (empty) which Cloud Run rejects + leaves the job in an unusable
    state. The script must gate the image-pin on `SHA + PROJECT_ID set`."""
    src = MIGRATE.read_text()
    assert 'if [[ -n "${SHA:-}" && -n "${PROJECT_ID:-}" ]]' in src, (
        "migrate.sh missing the SHA/PROJECT_ID guard around the image-pin block"
    )
    assert "Standalone heal mode" in src, (
        "migrate.sh standalone-mode log line is the operator's signal that "
        "image-pinning was intentionally skipped"
    )


def test_deploy_two_phase_exports_sha_and_project_id_to_migrate() -> None:
    """deploy-two-phase.sh must invoke migrate.sh with SHA + PROJECT_ID
    + REGION explicitly in the child env -- otherwise migrate.sh's
    image-pin block above silently falls through the standalone-heal
    branch on every CI run and the bug recurs.

    Both invocation sites must pass the env:
      (a) Phase 3 primary call
      (b) Phase 4 retry-on-drift call (_retry_migrate_on_drift). The
          retry is the exact path Phase 4 tries when the alembic_version
          503 fires for the first time; if it runs without env vars
          it just executes the OLD migrations image again.
    """
    src = DEPLOY_TWO_PHASE.read_text()
    # Collapse `\\\n` line continuations so the regex doesn't have to
    # know about bash's continuation syntax.
    collapsed = re.sub(r"\\\s*\n\s*", " ", src)
    # Pattern: each invocation line must prefix `${SCRIPT_DIR}/migrate.sh`
    # with at least SHA + PROJECT_ID + REGION exports.
    invocations = re.findall(
        r'(?P<env>(?:[A-Z_]+="[^"]*"\s+){2,})"\$\{SCRIPT_DIR\}/migrate\.sh"',
        collapsed,
    )
    assert invocations, (
        "deploy-two-phase.sh has NO migrate.sh invocation with an env-var "
        "prefix -- the image-pin block in migrate.sh will fall through "
        "to standalone-heal mode on every deploy."
    )
    for env_prefix in invocations:
        assert 'SHA="$SHA"' in env_prefix, (
            f"migrate.sh invocation missing SHA export: {env_prefix!r}"
        )
        assert 'PROJECT_ID="$PROJECT_ID"' in env_prefix, (
            f"migrate.sh invocation missing PROJECT_ID export: {env_prefix!r}"
        )
        assert 'REGION="$REGION"' in env_prefix, (
            f"migrate.sh invocation missing REGION export: {env_prefix!r}"
        )
    # And both expected invocation sites are present (Phase 3 primary +
    # Phase 4 retry).
    assert len(invocations) >= 2, (
        f"expected >= 2 env-prefixed migrate.sh invocations (Phase 3 + "
        f"Phase 4 retry); found {len(invocations)}: {invocations}"
    )


def test_phase4_failure_message_documents_post_migrate_link() -> None:
    """The image-pin failure message in migrate.sh must reference the
    Phase 4 alembic_version 503 symptom by name -- so when the gcloud
    update fails, the operator immediately understands the downstream
    consequence (not just a generic 'gcloud update failed')."""
    src = MIGRATE.read_text()
    assert "permission denied for table alembic_version" in src, (
        "migrate.sh image-pin failure path must reference the Phase 4 "
        "alembic_version symptom so operators recognize the connection"
    )
    assert "OLD post_migrate.py" in src, (
        "migrate.sh image-pin failure path must explain the code-version "
        "skew that drives the alembic_version 503"
    )
