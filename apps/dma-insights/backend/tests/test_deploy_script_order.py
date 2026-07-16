"""deploy.sh order regression — F-304 of the principal-QA audit.

Pre-fix the script printed "Deploy fully live" BEFORE running
migrations + verify-deploy. That meant the new backend image was
already serving traffic against the OLD schema during the migration
window -- a P1 risk window of 10-60s on every deploy.

The fix moves migrations + verify-deploy BEFORE the final success
message. Traffic still shifts on Terraform apply (P1 deferral
documented in DEPLOYMENT.md §11) but at least the success signal
no longer lies.

This file pins the contract:
  1. The migration run must appear in the script BEFORE the final
     success message ("Deploy fully live...").
  2. verify-deploy.sh must be invoked after migrations.
  3. Both failure paths must surface exit codes the caller can act on.
"""
from __future__ import annotations

import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1].parent / "infra"
DEPLOY = INFRA / "deploy.sh"
VERIFY = INFRA / "verify-deploy.sh"
MIGRATE = INFRA / "migrate.sh"


def test_deploy_script_invokes_migrate_before_final_success_message():
    """The final 'Deploy fully live' echo must come AFTER the migrate.sh
    invocation, NOT before. Pre-fix the order was reversed -- the
    operator saw success even though migrations were pending."""
    text = DEPLOY.read_text(encoding="utf-8")
    # Find positions of the migrate call + the final success message.
    migrate_match = re.search(
        r'"\$\{SCRIPT_DIR\}/migrate\.sh"', text,
    )
    success_match = re.search(
        r'"✓ Deploy fully live[^"]*at SHA=\$\{SHA\}"', text,
    )
    assert migrate_match, "migrate.sh invocation not found in deploy.sh"
    assert success_match, "final 'Deploy fully live' message not found"
    assert migrate_match.start() < success_match.start(), (
        f"Order is reversed: migrate.sh at offset {migrate_match.start()} "
        f"comes AFTER the success message at offset {success_match.start()}. "
        "The success message must be the LAST thing printed."
    )


def test_deploy_script_invokes_verify_deploy_after_migration():
    """F-304 companion: verify-deploy.sh must be called after
    migrations succeed so the operator's success signal reflects an
    actually-healthy live revision (alembic head matches code head)."""
    text = DEPLOY.read_text(encoding="utf-8")
    assert "verify-deploy.sh" in text, (
        "deploy.sh must invoke verify-deploy.sh to confirm the live "
        "revision is healthy after migrations."
    )
    # And it must come after the migrate call.
    migrate_pos = text.find("migrate.sh")
    verify_pos = text.find("verify-deploy.sh")
    success_pos = text.rfind("Deploy fully live")
    assert migrate_pos < verify_pos < success_pos, (
        f"Expected order: migrate ({migrate_pos}) → verify "
        f"({verify_pos}) → success ({success_pos}). Got reversed."
    )


def test_deploy_script_migration_failure_emits_actionable_exit_code():
    """A migration failure after traffic shifted is the WORST possible
    failure mode -- the operator must know to roll back immediately.
    The error message must spell out the rollback command."""
    text = DEPLOY.read_text(encoding="utf-8")
    # Find the post-migrate failure branch.
    m = re.search(
        r'if ! "\$\{SCRIPT_DIR\}/migrate\.sh"; then([\s\S]+?)exit \d',
        text,
    )
    assert m, "migrate.sh failure handler not found"
    handler = m.group(1)
    assert "ROLLBACK" in handler.upper(), (
        "Migration-failure handler must surface the rollback command "
        "because the new image is already serving traffic against an "
        "incompatible schema."
    )
    assert "update-traffic" in handler, (
        "Rollback instructions must reference `gcloud run services "
        "update-traffic`."
    )


def test_deploy_script_verify_failure_emits_actionable_exit_code():
    """Same contract for verify-deploy failures -- the live revision
    is unhealthy AFTER traffic shifted, so rollback or investigation
    is required."""
    text = DEPLOY.read_text(encoding="utf-8")
    m = re.search(
        r'if ! "\$\{SCRIPT_DIR\}/verify-deploy\.sh"; then([\s\S]+?)exit \d',
        text,
    )
    assert m, "verify-deploy.sh failure handler not found"
    handler = m.group(1)
    assert (
        "ROLLBACK" in handler.upper() or "investigate" in handler.lower()
    ), (
        "verify-deploy failure handler must direct the operator to "
        "rollback or investigate."
    )


def test_required_scripts_exist():
    """Sanity: migrate.sh + verify-deploy.sh must exist as files. The
    deploy.sh contract above is meaningless if either is missing."""
    assert DEPLOY.exists()
    assert MIGRATE.exists(), "migrate.sh referenced by deploy.sh is missing"
    assert VERIFY.exists(), "verify-deploy.sh referenced by deploy.sh is missing"
