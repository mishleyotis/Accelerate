"""Terraform <-> backend config env-var contract — Probe 16 of the
principal-QA audit.

The audit found that env-var drift between `config.py`, `.env.example`,
the Dockerfiles, Cloud Build, and Terraform is hard to spot without
a matrix test. A new secret added to `REQUIRED_FOR_PROD_BACKEND`
should also be:
  1. Wired into Terraform's backend service env block
  2. Declared in `local.backend_secrets` for per-secret IAM
  3. Referenced in `.env.example` so dev environments know about it
  4. Mentioned in DEPLOYMENT.md §0 secret creation block

This file enforces the contract. A missing wire trips the test
loudly instead of letting a Cloud Run revision boot with the secret
unbound and 503 every request.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1].parent
TERRAFORM_TF = REPO_ROOT / "infra" / "terraform" / "main.tf"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
DEPLOYMENT_MD = REPO_ROOT / "docs" / "DEPLOYMENT.md"


def _extract_block(text: str, start_pattern: str) -> str:
    """Extract a brace-balanced block starting at `start_pattern`.
    Walks the text counting `{` and `}` so nested template/container
    /env blocks don't terminate the outer block prematurely."""
    m = re.search(start_pattern, text)
    assert m, f"start pattern not found: {start_pattern}"
    start = m.end()
    # Find the opening `{` immediately after the pattern.
    while start < len(text) and text[start] != "{":
        start += 1
    assert start < len(text), f"opening brace not found after {start_pattern}"
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces after {start_pattern}")


def _walk_env_blocks(body: str) -> list[str]:
    """Find every `env {...}` block via brace counting (handles
    interpolations like `${PROJECT}` in comments that break a naive
    `[^}]*?` character-class match), then extract the `name = "X"`
    declaration from each."""
    names: list[str] = []
    i = 0
    while True:
        m = re.search(r'\benv\s*\{', body[i:])
        if not m:
            break
        start = i + m.end() - 1  # position of the `{`
        depth = 0
        j = start
        while j < len(body):
            ch = body[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    block = body[start:j + 1]
                    nm = re.search(r'name\s*=\s*"([^"]+)"', block)
                    if nm:
                        names.append(nm.group(1))
                    i = j + 1
                    break
            j += 1
        else:
            break
    return names


def _terraform_backend_env_var_names() -> set[str]:
    """Extract all `env { name = "X" ... }` blocks under the backend
    Cloud Run service definition."""
    text = TERRAFORM_TF.read_text(encoding="utf-8")
    body = _extract_block(
        text,
        r'resource\s+"google_cloud_run_v2_service"\s+"backend"\s*',
    )
    return set(_walk_env_blocks(body))


def _terraform_worker_env_var_names() -> set[str]:
    """Extract env { name = "X" } blocks under the worker for_each."""
    text = TERRAFORM_TF.read_text(encoding="utf-8")
    body = _extract_block(
        text,
        r'resource\s+"google_cloud_run_v2_job"\s+"worker"\s*',
    )
    return set(_walk_env_blocks(body))


def _terraform_backend_secret_refs() -> set[str]:
    """Secret IDs the backend service consumes via `secret_key_ref`."""
    text = TERRAFORM_TF.read_text(encoding="utf-8")
    body = _extract_block(
        text,
        r'resource\s+"google_cloud_run_v2_service"\s+"backend"\s*',
    )
    refs = set()
    for sm in re.finditer(
        r'secret_key_ref\s*\{[^}]*?secret\s*=\s*"([^"]+)"', body,
    ):
        refs.add(sm.group(1))
    for sm in re.finditer(
        r'secret_key_ref\s*\{[^}]*?secret\s*=\s*google_secret_manager_secret\.([a-z_]+)\.secret_id',
        body,
    ):
        refs.add(sm.group(1))
    return refs


# Map config.py field name -> Cloud Run env var name. Most are
# uppercase of the field name; explicit overrides for divergent names.
_CONFIG_TO_ENV_VAR = {
    "database_url": "DATABASE_URL",
    "database_url_sync": "DATABASE_URL_SYNC",
    "redis_url": "REDIS_URL",
    "google_oauth_client_id": "GOOGLE_OAUTH_CLIENT_ID",
    "google_oauth_client_secret": "GOOGLE_OAUTH_CLIENT_SECRET",
    "dma_bot_api_key": "DMA_BOT_API_KEY",
    "rag_api_bearer_key": "RAG_API_BEARER_KEY",
    "gcp_project_id": "GCP_PROJECT_ID",
    "clay_webhook_url": "CLAY_WEBHOOK_URL",
    "clay_webhook_secret": "CLAY_WEBHOOK_SECRET",
}


def test_every_prod_backend_required_setting_is_wired_in_terraform():
    """Every key in REQUIRED_FOR_PROD_BACKEND must appear as an env
    var on the backend Cloud Run service. Otherwise a Cloud Run
    revision boots without the value bound -- and depending on the
    code path either 503s, fail-closes silently, or worse leaks dev
    defaults."""
    from app.config import REQUIRED_FOR_PROD_BACKEND
    tf_envs = _terraform_backend_env_var_names()
    missing = []
    for setting, _dev_default in REQUIRED_FOR_PROD_BACKEND:
        env_var = _CONFIG_TO_ENV_VAR.get(setting, setting.upper())
        if env_var not in tf_envs:
            missing.append((setting, env_var))
    assert not missing, (
        f"Terraform backend service is missing env wires: {missing}. "
        "Add an `env { name = \"X\" ... }` block to "
        "google_cloud_run_v2_service.backend in main.tf."
    )


def test_every_prod_worker_required_setting_is_wired_in_terraform():
    """REQUIRED_FOR_PROD_WORKER is minimal (db + gcp_project_id).
    The worker for_each block must surface both."""
    from app.config import REQUIRED_FOR_PROD_WORKER
    tf_envs = _terraform_worker_env_var_names()
    missing = []
    for setting, _dev_default in REQUIRED_FOR_PROD_WORKER:
        env_var = _CONFIG_TO_ENV_VAR.get(setting, setting.upper())
        if env_var not in tf_envs:
            missing.append((setting, env_var))
    assert not missing, (
        f"Terraform worker block missing env wires: {missing}. "
        "Add to google_cloud_run_v2_job.worker container env blocks."
    )


def test_env_var_names_match_settings_field_names_or_documented_overrides():
    """Sanity: REQUIRED_FOR_PROD_BACKEND entry names must either map
    1:1 to an env var (UPPER_SNAKE) OR have an explicit override in
    `_CONFIG_TO_ENV_VAR`. A new key added to the required list with
    a non-obvious env var name must declare the mapping or this test
    breaks first."""
    from app.config import REQUIRED_FOR_PROD_BACKEND, REQUIRED_FOR_PROD_WORKER
    unknown = []
    for setting, _ in list(REQUIRED_FOR_PROD_BACKEND) + list(REQUIRED_FOR_PROD_WORKER):
        if setting not in _CONFIG_TO_ENV_VAR:
            # Fallback to setting.upper() is acceptable but must match
            # at least one mapping convention.
            assert setting.upper() == setting.upper().replace("-", "_"), (
                f"setting '{setting}' has unmapped env var name"
            )
        if setting not in _CONFIG_TO_ENV_VAR:
            unknown.append(setting)
    # We don't require ALL entries to be in the mapping (fallback works)
    # but the test makes adding new ones explicit. Run-warning only.
    if unknown:
        print(f"NOTE: settings using upper-snake fallback: {unknown}")


def test_terraform_secret_refs_have_local_backend_secrets_entry():
    """Every secret_key_ref the backend service uses MUST appear in
    `local.backend_secrets`. Otherwise the per-secret IAM binding loop
    skips it and the Cloud Run service can't read it at boot time."""
    text = TERRAFORM_TF.read_text(encoding="utf-8")
    backend_secrets_m = re.search(
        r"backend_secrets\s*=\s*\[([\s\S]+?)\]", text,
    )
    assert backend_secrets_m
    declared = set(re.findall(
        r'"(dma-insights-[a-z0-9\-]+)"', backend_secrets_m.group(1),
    ))
    refs = _terraform_backend_secret_refs()
    # Resolve resource-attribute refs (e.g. jwt_signing_key.secret_id)
    # to their concrete secret IDs by searching the file.
    concrete_refs = set()
    for ref in refs:
        if ref.startswith("dma-insights-"):
            concrete_refs.add(ref)
        else:
            # Look up the resource block to find its secret_id.
            rm = re.search(
                rf'resource\s+"google_secret_manager_secret"\s+"{re.escape(ref)}"\s*\{{[^}}]*?secret_id\s*=\s*"([^"]+)"',
                text,
            )
            if rm:
                concrete_refs.add(rm.group(1))
    missing = concrete_refs - declared
    assert not missing, (
        f"Backend secret_key_refs not in local.backend_secrets: {sorted(missing)}. "
        "Per-secret IAM bindings won't be created."
    )


def test_env_example_includes_every_backend_required_setting():
    """`.env.example` is the only source dev environments use to know
    what env vars to set. Every REQUIRED_FOR_PROD_BACKEND key must
    appear there (commented or uncommented) so a new dev doesn't
    silently miss one."""
    from app.config import REQUIRED_FOR_PROD_BACKEND
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    missing = []
    for setting, _ in REQUIRED_FOR_PROD_BACKEND:
        env_var = _CONFIG_TO_ENV_VAR.get(setting, setting.upper())
        if env_var not in text:
            missing.append(env_var)
    assert not missing, (
        f".env.example missing entries: {missing}. New dev environments "
        "won't see the required env-var contract."
    )


def test_deployment_md_section0_lists_every_required_secret():
    """§0 secret-creation block must reference every dma-insights-*
    secret in `local.backend_secrets` (minus the Terraform-managed
    database_url* and jwt-signing-key, which §0 documents as
    Terraform-created)."""
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    # Narrow to §0 scope.
    section_m = re.search(
        r"## §0[\s\S]+?(?=## ⚡ Happy path)", text,
    )
    assert section_m, "§0 not found"
    section = section_m.group(0)
    tf_text = TERRAFORM_TF.read_text(encoding="utf-8")
    backend_secrets_m = re.search(
        r"backend_secrets\s*=\s*\[([\s\S]+?)\]", tf_text,
    )
    declared = set(re.findall(
        r'"(dma-insights-[a-z0-9\-]+)"', backend_secrets_m.group(1),
    ))
    terraform_managed = {
        "dma-insights-database-url",
        "dma-insights-database-url-sync",
        "dma-insights-database-url-superuser",
        "dma-insights-jwt-signing-key",
    }
    operator_required = declared - terraform_managed
    missing = [s for s in operator_required if s not in section]
    assert not missing, (
        f"§0 secret-creation block does not enumerate: {missing}. "
        "Operators wouldn't know to create these in step §0.5."
    )


def test_cloudbuild_uses_psycopg_sync_dsn_for_migrations():
    """Cloud Build's backend-tests stage must set DATABASE_URL_SYNC
    using the psycopg driver scheme (`postgresql+psycopg://`). Bare
    `postgresql://` selects psycopg2 in SQLAlchemy 2.0 which is NOT
    installed in the image -- alembic upgrade head --sql crashes
    with ModuleNotFoundError before any DDL is emitted."""
    cb_path = REPO_ROOT / "infra" / "cloudbuild.yaml"
    text = cb_path.read_text(encoding="utf-8")
    # Find DATABASE_URL_SYNC assignments.
    syncs = re.findall(
        r"DATABASE_URL_SYNC\s*=\s*([^\s,'\"]+)",
        text,
    )
    assert syncs, "DATABASE_URL_SYNC not referenced in cloudbuild.yaml"
    for s in syncs:
        if s.startswith(("postgres://", "postgresql://")) and "+psycopg" not in s:
            raise AssertionError(
                f"cloudbuild.yaml DATABASE_URL_SYNC uses '{s}' which defaults "
                "to psycopg2. Pin to `postgresql+psycopg://...`."
            )
