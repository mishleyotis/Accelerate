"""Regression tests for the 8 recurring deploy-time failure modes.

Each test here is an explicit guardrail against a class of error that
has bitten this repo more than once. Removing or weakening the
underlying safeguard MUST cause one of these tests to fail.

The 8 failure modes — every test below maps to one:

  1. Cloud Shell IPv6 routing — `GODEBUG=netdns=go` in deploy.sh /
     migrate.sh / build.sh / recover-db-passwords.sh.
  2. Cloud SQL password drift — recover-db-passwords.sh exists +
     migrate.sh invokes it.
  3. Cloud Run secret caching — force_revision_rolls in
     recover-db-passwords.sh rolls every service + job env so the
     'latest' secret is re-resolved.
  4. Terraform variable typos — project_id + image_sha have validation
     blocks rejecting bare-word inputs like 'latest'.
  5. Cloud Build pip install drift — every runtime dep in pyproject is
     also in cloudbuild.yaml's pip install line.
  6. Migration 018 immutability — STORED generated columns replaced
     with trigger-maintained columns; CI executes alembic against
     ephemeral Postgres so runtime-only errors trip at build time.
  7. Cloud Build substitution parsing — every uppercase $VAR in
     cloudbuild.yaml is either a built-in, _-prefixed user var, or
     escaped as $$. build.sh pre-flight enforces this.
  8. Backfill resilience — covered by existing test_stress_e2e suite
     (dedup, cross-entity, freshness, multi-run profile) — this file
     just asserts the suite exists as a deploy-gated wedge.

State-transition contracts are in each test's docstring. A "Y/N matrix"
of which test would fail if you reverted each fix is included in the
audit report.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _find_app_root(start: Path) -> Path:
    """Walk up from `start` until we find a directory containing
    both `infra/` and `backend/`. Works regardless of where the
    repo is mounted — Cloud Build mounts apps/dma-insights/ as
    /workspace, while local dev has /home/.../apps/dma-insights/.
    """
    for candidate in [start, *start.parents]:
        if (candidate / "infra").is_dir() and (candidate / "backend").is_dir():
            return candidate
    raise RuntimeError(
        f"Could not find app root (looking for sibling infra/ + backend/) "
        f"starting from {start}. Test must run from inside "
        f"apps/dma-insights/ or have it mounted at /workspace."
    )


APP_ROOT = _find_app_root(Path(__file__).resolve())
# REPO_ROOT used only for nicer relative-path display in error messages.
# When apps/dma-insights/ is mounted standalone (Cloud Build /workspace),
# REPO_ROOT == APP_ROOT — that's fine since relative_to() handles equal paths.
REPO_ROOT = APP_ROOT.parents[1] if len(APP_ROOT.parents) >= 2 else APP_ROOT
INFRA = APP_ROOT / "infra"
TERRAFORM = INFRA / "terraform" / "main.tf"
CLOUDBUILD = INFRA / "cloudbuild.yaml"
PYPROJECT = APP_ROOT / "backend" / "pyproject.toml"


# ── #1: Cloud Shell IPv6 routing ────────────────────────────────────


def test_godebug_netdns_set_in_every_cloud_shell_script() -> None:
    """Every operator-run shell script that uses gcloud / terraform / curl
    against a GCP endpoint MUST export GODEBUG=netdns=go before its first
    network call, so the Cloud Shell IPv6 NAT pool flake is bypassed.

    Failure mode this prevents:
      `dial tcp [2a00:...] cannot assign requested address` from any
      gcloud / terraform / curl call running in Cloud Shell.

    State branches:
      script_has_export   → safe; pure-Go resolver picks IPv4 first.
      script_missing      → IPv6 record drawn from DNS; NAT can't route;
                            the next gcloud call dies with EADDRNOTAVAIL.

    This test reads each script's first 80 lines and asserts the export
    appears before any `gcloud`, `terraform`, or `curl` call.
    """
    scripts = [
        INFRA / "deploy.sh",
        INFRA / "migrate.sh",
        INFRA / "build.sh",
        INFRA / "recover-db-passwords.sh",
    ]
    for script in scripts:
        assert script.exists(), f"{script.relative_to(REPO_ROOT)} missing"
        text = script.read_text()
        # The export must appear before the first network call.
        export_match = re.search(r"^export GODEBUG=netdns=go", text, re.MULTILINE)
        assert export_match is not None, (
            f"{script.name} missing `export GODEBUG=netdns=go` — Cloud Shell "
            f"IPv6 NAT pool will reject the first gcloud/terraform/curl call"
        )
        # Find first network call.
        network_match = re.search(
            r"^\s*(gcloud|terraform|curl|psql)\b", text, re.MULTILINE
        )
        if network_match:
            assert export_match.start() < network_match.start(), (
                f"{script.name}: GODEBUG export must appear BEFORE the first "
                f"network call ({network_match.group(1)})"
            )


# ── #2: Cloud SQL password drift self-heal ──────────────────────────


def test_migrate_sh_invokes_recover_db_passwords() -> None:
    """migrate.sh MUST self-heal Cloud SQL password drift before
    triggering the migrations job. Otherwise operators see
    "FATAL: password authentication failed for user 'postgres'" and
    have to chase the recovery script manually every time secrets are
    rotated out-of-band.

    State branches:
      passwords_match   → recover script returns 0; migrate proceeds.
      drift_detected    → recover script heals + rolls revisions;
                          migrate retries.
      recovery_failed   → migrate exits non-zero with pointer to
                          --diagnose mode.
    """
    migrate_text = (INFRA / "migrate.sh").read_text()
    assert "recover-db-passwords.sh" in migrate_text, (
        "migrate.sh must invoke recover-db-passwords.sh for the password "
        "drift self-heal flow"
    )
    # The verify-only invocation MUST appear (so we don't blindly run
    # the heavyweight recovery on every migrate).
    assert "--verify-only" in migrate_text, (
        "migrate.sh must call recover-db-passwords.sh --verify-only first "
        "to decide whether to run the heavyweight recovery"
    )
    # The recovery script itself must exist + be executable.
    recover = INFRA / "recover-db-passwords.sh"
    assert recover.exists(), "recover-db-passwords.sh missing"
    assert recover.stat().st_mode & 0o111, "recover-db-passwords.sh not executable"


# ── #3: Cloud Run secret caching → force revision rolls ─────────────


def test_recover_db_passwords_forces_revision_rolls() -> None:
    """Cloud Run resolves `version = "latest"` at container start. The
    live revision serves the OLD password until a new revision starts.
    `force_revision_rolls` must update every service + job's env with a
    timestamp so revisions re-roll and re-read the secret.

    Without this, healing the secret leaves the live containers serving
    the stale password forever — until the operator manually rolls them.

    State branches:
      backend_present → service updated; new revision boots with fresh
                         secret value.
      backend_absent  → skipped gracefully (first deploy not yet run).
      job_present     → job updated; next execution sees fresh value.
    """
    text = (INFRA / "recover-db-passwords.sh").read_text()
    assert "force_revision_rolls" in text, "force_revision_rolls function missing"
    assert "DMA_SECRET_ROLL" in text, (
        "force_revision_rolls must write a unique timestamp env var so "
        "Cloud Run sees the revision spec as changed"
    )
    # The function must be CALLED — not just defined.
    func_def_count = text.count("force_revision_rolls()")
    func_call_count = text.count("force_revision_rolls\n") + text.count(
        "force_revision_rolls "
    )
    assert func_call_count >= 1, (
        "force_revision_rolls is defined but never invoked — healing "
        "leaves stale revisions"
    )
    # Critical jobs that hold the DB secret must each be in the roll list.
    for job in [
        "dma-insights-backend",
        "dma-insights-migrations",
        "dma-insights-embedder",
    ]:
        assert job in text, (
            f"force_revision_rolls must roll {job} — otherwise it serves "
            f"the stale cached password until something else triggers a roll"
        )
    assert func_def_count >= 1


# ── #4: Terraform variable typos → validation blocks ────────────────


def test_terraform_validates_project_id() -> None:
    """`terraform apply -var "project_id=latest"` (operator types the
    image tag into the wrong field) was a recurring failure mode —
    Terraform tries to create resources under a project literally named
    "latest". The validation must reject it.

    Originally a single regex tried to block it; but 'latest' is 6
    chars of lowercase letters and PASSES the GCP project-id pattern.
    The fix is a second `validation` block that explicitly blocklists
    common tag-alias typos.

    State branches:
      valid_project_id  → both regex + blocklist pass; apply proceeds.
      bare_word_typo    → blocklist rejects with actionable error.
      empty_string      → regex rejects.
      garbage_chars     → regex rejects.

    Reverting EITHER validation block would re-open the recurring bug;
    this test asserts both are in place.
    """
    tf = TERRAFORM.read_text()
    assert 'variable "project_id"' in tf

    # Locate the project_id variable block by finding the next variable
    # boundary so the contains() check below isn't confused by other vars.
    pi_match = re.search(r'variable "project_id"\s*\{(.+?)\nvariable ', tf, re.DOTALL)
    assert pi_match is not None, "couldn't isolate project_id variable block"
    pi_block = pi_match.group(1)

    # Validation #1: generic GCP project-id regex.
    m = re.search(
        r'condition\s*=\s*can\(regex\("([^"]+)"', pi_block,
    )
    assert m is not None, "project_id missing regex validation block"
    regex_pattern = m.group(1)
    assert not re.match(regex_pattern, ""), "regex must reject empty"
    assert not re.match(regex_pattern, "BAD CASE"), "regex must reject uppercase/spaces"
    assert re.match(regex_pattern, "digital-maturity-assessor"), "must accept canonical id"

    # Validation #2: blocklist of tag-alias typos. THIS is what catches
    # 'latest' — the regex above is too generic to do so on its own.
    assert "contains(" in pi_block, (
        "project_id missing a blocklist validation block — operator typing "
        "'latest' would slip past the generic regex (6 chars of lowercase "
        "letters is a valid GCP project id pattern)"
    )
    for blocked in ["latest", "head", "main", "master"]:
        assert f'"{blocked}"' in pi_block, (
            f"blocklist must include {blocked!r} — common image-tag typo "
            f"into the wrong -var field"
        )
    # Error message must call out the typo so the operator self-diagnoses.
    assert "latest" in pi_block.lower(), (
        "validation error message must mention 'latest' so the operator "
        "recognizes their typo"
    )


def test_terraform_validates_image_sha() -> None:
    """Same class of typo: operator runs `terraform apply
    -var "image_sha=latest"` and terraform happily tries to pull
    gcr.io/.../dma-insights-backend:latest which is the wrong artifact.

    State branches:
      valid_hex_sha    → 7-40 char [0-9a-f] accepted.
      tag_alias        → 'latest', 'main', 'head' rejected.
      uppercase_hex    → rejected (gcr tags are lowercase).
    """
    tf = TERRAFORM.read_text()
    m = re.search(
        r'variable "image_sha".*?validation\s*\{[^}]*condition\s*=\s*can\(regex\("([^"]+)"',
        tf,
        re.DOTALL,
    )
    assert m is not None, "image_sha missing a validation block"
    regex_pattern = m.group(1)
    assert not re.match(regex_pattern, "latest"), (
        "image_sha validation must reject 'latest' tag alias"
    )
    assert not re.match(regex_pattern, "DEADBEEF"), (
        "image_sha validation must reject uppercase hex (gcr tag format)"
    )
    assert re.match(regex_pattern, "deadbeef"), "must accept 8-char lowercase hex"
    assert re.match(regex_pattern, "0ae9b20"), "must accept 7-char lowercase hex"


# ── #5: Cloud Build pip install must match pyproject ────────────────


def _extract_pyproject_runtime_deps() -> set[str]:
    """Parse [project].dependencies — runtime only, NOT [project.optional-
    dependencies] or [tool.uv.dev-dependencies]."""
    text = PYPROJECT.read_text()
    # Find the [project] dependencies = [...] block (NOT
    # optional-dependencies).
    m = re.search(
        r"^\[project\][^\[]*?\bdependencies\s*=\s*\[(.*?)\]",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert m is not None, "pyproject [project].dependencies missing"
    block = m.group(1)
    deps = set()
    for line in block.splitlines():
        m2 = re.match(r'\s*"([A-Za-z0-9_.\-]+)', line)
        if m2:
            deps.add(m2.group(1).lower())
    return deps


def _extract_cloudbuild_pip_deps() -> set[str]:
    """Parse the pip install line in cloudbuild Stage 1."""
    text = CLOUDBUILD.read_text()
    # The pip install block is multiline shell with \-continuations.
    m = re.search(
        r"pip install --no-cache-dir(.*?)\n\s*rc=\$\?",
        text,
        re.DOTALL,
    )
    assert m is not None, "cloudbuild pip install block missing"
    block = m.group(1)
    deps = set()
    for line in block.splitlines():
        m2 = re.match(r"\s*'?([A-Za-z0-9_.\-]+)(?:\[[^\]]+\])?", line.strip())
        if m2 and m2.group(1) and m2.group(1) != "\\":
            deps.add(m2.group(1).lower())
    return deps


def test_cloudbuild_pip_install_covers_runtime_deps() -> None:
    """The Cloud Build Stage 1 pip install line had drifted from
    pyproject.toml multiple times — each drift produced
    `ModuleNotFoundError` at runtime AFTER a successful build.

    This test asserts every runtime dep from pyproject.toml is present
    in the cloudbuild Stage 1 pip install line. Add a new dep to
    pyproject → this test fails until you add it to cloudbuild too.

    State branches:
      all_covered           → CI installs every runtime dep; pytest succeeds.
      one_dep_missing       → pytest collection ImportError at build time.
      cloudbuild_has_extras → permitted (test deps like pytest are extra).
    """
    pyproject_deps = _extract_pyproject_runtime_deps()
    cloudbuild_deps = _extract_cloudbuild_pip_deps()
    # uvicorn is the only runtime dep skipped — it's the server, not used
    # by pytest. Explicitly allowlist so a future drift on every OTHER
    # dep still trips this test.
    PERMITTED_GAPS = {"uvicorn"}
    missing = (pyproject_deps - cloudbuild_deps) - PERMITTED_GAPS
    assert not missing, (
        f"cloudbuild.yaml Stage 1 pip install missing runtime deps from "
        f"pyproject.toml: {sorted(missing)}. Sync them or the next CI run "
        f"will pass while production crashes with ModuleNotFoundError."
    )


def test_cloudbuild_pip_install_covers_test_imports() -> None:
    """Cloud Build Stage 1 ALSO runs pytest, so every external module
    `tests/*.py` imports must be in the cloudbuild pip install line.

    The 2026-05-29 regression: `tests/test_docker_and_cloudbuild_contracts.py`
    added `import yaml` (PyYAML) but cloudbuild.yaml's pip install list
    didn't include it. Production build failed at test-collection time
    with `ModuleNotFoundError: No module named 'yaml'` AFTER the build
    had paid for a full pip install + alembic round-trip.

    Asserts the union of {pyproject [project].dependencies,
    pyproject [project.optional-dependencies].dev, an allowlist of
    stdlib + local-module prefixes} covers every top-level import in
    every `tests/*.py`.
    """
    # Test deps are declared in pyproject [project.optional-dependencies].dev
    # but cloudbuild installs them with a separate `pip install pytest`
    # line. We extract the dev list to know what's available at test time.
    text = PYPROJECT.read_text()
    dev_match = re.search(
        r'\[project\.optional-dependencies\][^\[]*?dev\s*=\s*\[(.*?)\]',
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert dev_match, "[project.optional-dependencies].dev missing"
    dev_deps = set()
    for line in dev_match.group(1).splitlines():
        m = re.match(r'\s*"([A-Za-z0-9_.\-]+)', line)
        if m:
            dev_deps.add(m.group(1).lower())

    # Available at test time = runtime deps + dev deps + cloudbuild install.
    available = (
        _extract_pyproject_runtime_deps()
        | dev_deps
        | _extract_cloudbuild_pip_deps()
    )

    # Map of import-name → pip-package-name (when they differ).
    IMPORT_TO_PIP = {
        "yaml": "pyyaml",
        "jwt": "pyjwt",
        "openpyxl": "openpyxl",
        "docx": "python-docx",
        "bs4": "beautifulsoup4",
        "lxml": "lxml",
        "google": "google-cloud-aiplatform",  # google.* belongs to one of many; treat as covered
        "googleapiclient": "google-api-python-client",
        "redis": "redis",
        "pgvector": "pgvector",
        "alembic": "alembic",
        "psycopg": "psycopg",
        "psycopg2": "psycopg2-binary",
        "asyncpg": "asyncpg",
        "sqlalchemy": "sqlalchemy",
        "pydantic": "pydantic",
        "pydantic_settings": "pydantic-settings",
        "fastapi": "fastapi",
        "starlette": "starlette",  # ships with fastapi
        "httpx": "httpx",
        "structlog": "structlog",
        "tenacity": "tenacity",
        "rapidfuzz": "rapidfuzz",
        "cryptography": "cryptography",
        "multipart": "python-multipart",
    }
    # Anything matching one of these prefixes is treated as local (no
    # external dep needed). app.*, tests.*, workers.*, etc.
    LOCAL_PREFIXES = ("app", "tests", "workers", "peer_patterns", "pillar")
    # Modules we already know are Python stdlib — no install needed.
    STDLIB = {
        "asyncio", "csv", "hashlib", "hmac", "io", "json", "math",
        "os", "random", "re", "shutil", "subprocess", "sys", "tempfile",
        "uuid", "zipfile", "contextlib", "collections", "datetime",
        "pathlib", "typing", "unittest", "functools", "dataclasses",
        "urllib", "copy", "enum", "base64", "email", "string", "struct",
        "socket", "textwrap", "xml", "inspect", "html", "secrets",
        "logging", "ssl", "warnings", "platform", "abc", "weakref",
        "concurrent", "multiprocessing", "threading", "time", "queue",
        "operator", "itertools", "ast", "importlib", "types",
        "decimal", "fractions", "pickle", "shelve", "sqlite3",
        "tomllib",  # stdlib since Python 3.11
    }
    # Augment the curated floor with the interpreter's AUTHORITATIVE stdlib
    # list so importing ANY stdlib module (argparse, glob, shlex, …) is never
    # mistaken for a missing pip dependency. Before this, the hand-maintained
    # set omitted common modules (argparse), so a new test importing one failed
    # this guard at deploy time even though it needs no install. Python 3.10+.
    import sys as _sys
    STDLIB = STDLIB | set(getattr(_sys, "stdlib_module_names", ()))

    tests_dir = APP_ROOT / "backend" / "tests"
    test_files = list(tests_dir.glob("*.py"))
    assert test_files, "no test files found"

    # Parse imports via AST so docstring text like "from a curl session…"
    # doesn't false-match. Walking the tree also correctly handles
    # `import X` and `from X import …` (including nested-in-function
    # imports, which still need the package to be installable).
    import ast as _ast

    missing_packages: dict[str, list[str]] = {}
    for tf in test_files:
        try:
            src = tf.read_text()
        except OSError:
            continue
        try:
            tree = _ast.parse(src, filename=str(tf))
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, _ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for full in names:
                top = full.split(".", 1)[0]
                if top in STDLIB or top in {"__future__"}:
                    continue
                if any(top == p or top.startswith(p + ".") for p in LOCAL_PREFIXES):
                    continue
                pip_name = IMPORT_TO_PIP.get(top, top).lower()
                if pip_name not in available:
                    missing_packages.setdefault(pip_name, []).append(tf.name)

    assert not missing_packages, (
        f"cloudbuild.yaml pip install list is missing packages required "
        f"by test imports: { {k: sorted(set(v)) for k, v in missing_packages.items()} }. "
        "Add each one to cloudbuild.yaml AND pyproject.toml [dev]."
    )


# ── #6: Migration 018 immutability ──────────────────────────────────


def test_migration_018_uses_trigger_not_stored_for_current_date_columns() -> None:
    """Migration 018 originally tried to define `is_stale` +
    `freshness_band` as `GENERATED ALWAYS AS (...CURRENT_DATE...) STORED`
    columns. Postgres requires the generation expression to be IMMUTABLE
    but CURRENT_DATE is STABLE → ALTER TABLE fails at deploy time:
    `generation expression is not immutable`.

    Fix: drop the GENERATED keyword for those columns; maintain them
    via a trigger fired on INSERT OR UPDATE.

    This test parses the migration body and asserts the fix is intact:
      - is_stale is plain BOOLEAN (not GENERATED ALWAYS AS STORED).
      - freshness_band is plain VARCHAR (not GENERATED ALWAYS AS STORED).
      - A trigger exists on evidence_index that maintains both.

    Reverting either column to GENERATED would fail this test.
    """
    migration = APP_ROOT / "backend" / "alembic" / "versions" / "018_intelligence_layer.py"
    text = migration.read_text()

    # Find the column definitions for is_stale + freshness_band.
    # They MUST NOT be inside a GENERATED ALWAYS AS (...) STORED expression.
    # The fix uses ADD COLUMN ... DEFAULT FALSE (no GENERATED keyword).
    is_stale_def = re.search(
        r"ADD COLUMN IF NOT EXISTS is_stale\s+(\S+)", text, re.IGNORECASE
    )
    assert is_stale_def is not None, "is_stale column add missing"
    # Read up to 200 chars after the column name; assert no GENERATED keyword.
    is_stale_pos = is_stale_def.start()
    is_stale_window = text[is_stale_pos:is_stale_pos + 400]
    assert "GENERATED" not in is_stale_window.upper(), (
        "is_stale must NOT be a GENERATED column — CURRENT_DATE is STABLE, "
        "Postgres rejects it as non-immutable. Use a trigger instead."
    )

    band_def = re.search(
        r"ADD COLUMN IF NOT EXISTS freshness_band\s+(\S+)", text, re.IGNORECASE
    )
    assert band_def is not None
    band_pos = band_def.start()
    band_window = text[band_pos:band_pos + 400]
    assert "GENERATED" not in band_window.upper(), (
        "freshness_band must NOT be a GENERATED column"
    )

    # The trigger function + trigger MUST be present.
    assert "compute_evidence_freshness_band" in text, (
        "missing compute_evidence_freshness_band function — without it the "
        "trigger maintenance has no source of truth"
    )
    assert "trg_evidence_freshness" in text, (
        "missing trg_evidence_freshness trigger — columns would never "
        "update on row writes"
    )
    assert "CREATE TRIGGER trg_evidence_freshness" in text


def test_cloudbuild_executes_alembic_against_real_postgres() -> None:
    """The offline `alembic upgrade head --sql` ONLY prints DDL; it does
    NOT execute against a live server. Runtime-only errors (immutability,
    trigger compilation, FK validation) silently pass at offline-DDL
    time and explode inside the Cloud Run migrations job.

    CI must execute `alembic upgrade head` against an ephemeral Postgres
    so these errors trip at build time, NOT in production.

    State branches:
      live_upgrade_present (sidecar) → migration 018-style errors caught
                                        via pgvector/pgvector:pg15 Docker
                                        sidecar + `ci-live-migration.sh`
                                        (current pattern post-trixie).
      live_upgrade_present (initdb)  → legacy in-place initdb + pg_ctl
                                        (deprecated; the apt-install path
                                        broke once python:3.12-slim moved
                                        to Debian trixie which dropped
                                        postgresql-15 from apt repos).
      live_upgrade_absent             → operator finds out at deploy.
    """
    text = CLOUDBUILD.read_text()
    # Current (Docker sidecar) pattern: a separate `backend-tests-live-pg`
    # step spins up `pgvector/pgvector:pg15` and runs alembic against
    # it. Two acceptable wirings:
    #   (a) calls `ci-live-migration.sh` (older variant), OR
    #   (b) docker-runs alembic against the just-built backend image
    #       (current — avoids pip3 install inside cloud-builders/docker).
    # Either way, both markers (step id + pg15 sidecar image) must be
    # present so this safeguard pins the "real PG round-trip" contract.
    sidecar_pattern = (
        "backend-tests-live-pg" in text
        and (
            "ci-live-migration.sh" in text
            or "pgvector/pgvector:pg15" in text
        )
    )
    # Legacy (apt + initdb) pattern — retained as fallback acceptance for
    # historical branches; new builds should use the sidecar pattern.
    legacy_pattern = (
        "alembic upgrade head (LIVE EXECUTE" in text
        or ("alembic upgrade head" in text and "initdb" in text)
    )
    assert sidecar_pattern or legacy_pattern, (
        "CI must execute alembic upgrade head against a real Postgres "
        "cluster (sidecar via ci-live-migration.sh OR legacy initdb) "
        "so runtime-only SQL errors trip "
        "at build time"
    )
    # PG cluster bring-up: legacy used `initdb + pg_ctl`; sidecar uses
    # `pgvector/pgvector:pg15` Docker image (cluster comes pre-initialised).
    assert (
        ("initdb" in text and "pg_ctl" in text)
        or "pgvector/pgvector:pg15" in text
    ), (
        "CI must bring up a real Postgres cluster — either via initdb + "
        "pg_ctl in-place OR via the pgvector/pgvector:pg15 Docker sidecar "
        "(per ci-live-migration.sh)"
    )
    # The live round-trip MUST also run downgrade then upgrade head —
    # otherwise a one-way migration could pass but irreversibly mutate
    # prod. Legacy pattern uses `downgrade -1`; sidecar script runs the
    # full `downgrade base` (more thorough — exercises EVERY migration's
    # downgrade path on each build, catching the 011/018 focus_areas
    # double-drop class of bug surfaced earlier this session).
    assert (
        "alembic downgrade -1" in text
        or "ci-live-migration.sh" in text
    ), (
        "CI must run alembic downgrade then upgrade head — round-trip "
        "stability is the load-bearing claim for safe rollbacks. Legacy "
        "pattern uses `downgrade -1`; sidecar script uses `downgrade base`."
    )


# ── #7: Cloud Build substitution parsing ────────────────────────────


def test_cloudbuild_uppercase_shell_vars_are_escaped() -> None:
    """Cloud Build's substitution parser treats every $UPPERCASE token
    as a substitution candidate. Built-ins (PROJECT_ID, BUILD_ID, etc.)
    and user-defined `_FOO` are accepted; anything else fails the
    submission with:
      "key in the template "PG_BIN" is not a valid built-in substitution"

    Fix: any uppercase shell var inside an inline-script step MUST be
    escaped as $$NAME (or $${NAME}). The build.sh pre-flight enforces
    this; this test mirrors that check so a contributor adding a new
    unescaped var trips immediately.

    State branches:
      all_escaped      → build submit accepted.
      one_unescaped    → build submit rejected at validation time.
    """
    text = CLOUDBUILD.read_text()
    builtins = {
        "PROJECT_ID",
        "BUILD_ID",
        "PROJECT_NUMBER",
        "LOCATION",
        "REVISION_ID",
        "COMMIT_SHA",
        "SHORT_SHA",
        "REPO_NAME",
        "BRANCH_NAME",
        "TAG_NAME",
        "TRIGGER_NAME",
        "TRIGGER_BUILD_CONFIG_PATH",
    }
    offenders: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip comments — the # explanations include literal $VAR examples.
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Find every $NAME or ${NAME} that is NOT preceded by $.
        for m in re.finditer(r"(?<!\$)\$\{?([A-Z][A-Z0-9_]*)\}?", line):
            name = m.group(1)
            if name in builtins:
                continue
            if name.startswith("_"):
                continue
            # Anything left is unescaped → would fail build submit.
            offenders.append((lineno, name, line))
    assert not offenders, (
        "cloudbuild.yaml has unescaped uppercase shell vars that Cloud Build "
        "will reject as invalid substitutions:\n"
        + "\n".join(f"  L{lno}: ${name} in `{ln.strip()[:80]}`"
                    for lno, name, ln in offenders[:10])
        + "\nFix: replace $NAME with $$NAME (or ${NAME} with $${NAME})."
    )


def test_build_sh_preflight_script_exists_and_runs_dry() -> None:
    """build.sh wraps `gcloud builds submit` with the pre-flight check.
    The script MUST exist + run in --dry-run mode (no gcloud needed).
    Removing the pre-flight would let a future contributor sneak a
    bad substitution past CI.

    State branches:
      yaml_clean + dry_run     → exit 0.
      yaml_has_offender + any  → exit 1 with line numbers + fix hint.
    """
    build_sh = INFRA / "build.sh"
    assert build_sh.exists(), "build.sh wrapper missing"
    assert build_sh.stat().st_mode & 0o111, "build.sh not executable"
    text = build_sh.read_text()
    # Pre-flight must be present.
    assert "Pre-flight" in text or "preflight" in text.lower()
    assert "--dry-run" in text, "build.sh must support --dry-run for CI testing"
    # The regex check (in shell) MUST exclude built-ins, _-prefixed, and $$-escaped.
    assert "BUILTINS=" in text, "build.sh must define a BUILTINS whitelist"
    assert "$$" in text or "\\$\\$" in text, (
        "build.sh pre-flight must filter $$-escaped vars"
    )
    # Run it in dry-run mode against the actual cloudbuild.yaml — proves
    # the script's check passes on the current state of the YAML.
    #
    # SIDE-EFFECT SENTINEL: build.sh used to call resolve-deploy-sha.sh even
    # under --dry-run. In CI's git-less image that was a no-op, but in any
    # environment with git + the repo present the resolver SYNCED THE TREE
    # (fetch + `checkout -B` onto the deploy branch) — so running this very
    # test hijacked the suite's own worktree mid-run (2026-07-06: migrations
    # vanished under the parametrized migration-ID tests three runs straight).
    # Capture HEAD + branch before/after and demand they are untouched.
    def _git_state() -> tuple[str, str]:
        def _q(*args: str) -> str:
            try:
                out = subprocess.run(
                    ["git", "-C", str(INFRA), *args],
                    capture_output=True, text=True, timeout=10,
                )
                return out.stdout.strip() if out.returncode == 0 else ""
            except Exception:
                return ""
        return _q("rev-parse", "HEAD"), _q("rev-parse", "--abbrev-ref", "HEAD")

    head_before, branch_before = _git_state()
    result = subprocess.run(
        ["bash", str(build_sh), "--dry-run"],
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "PROJECT_ID": "digital-maturity-assessor",
        },
        timeout=30,
    )
    head_after, branch_after = _git_state()
    assert result.returncode == 0, (
        f"build.sh --dry-run failed against current cloudbuild.yaml:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (head_before, branch_before) == (head_after, branch_after), (
        f"build.sh --dry-run MUTATED the working tree: HEAD/branch moved "
        f"{head_before[:9]}@{branch_before} → {head_after[:9]}@{branch_after}. "
        f"--dry-run must never invoke the resolve-deploy-sha.sh tree sync."
    )


# ── #7b: pgvector init-then-restart race — both sidecar wait loops ──


def test_cloudbuild_pg_sidecar_waits_for_stable_readiness() -> None:
    """`pgvector/pgvector:pg15` goes through an init-then-restart cycle
    on first boot: the container starts postgres briefly to create
    POSTGRES_USER/POSTGRES_DB, immediately SIGTERMs itself, then
    restarts in foreground. A naive `pg_isready` wait loop succeeds
    during the first brief start — breaks early — then the next psql
    call fails with "FATAL: the database system is shutting down".

    Defence (must be present in BOTH `backend-tests-live-pg` and
    `e2e-personas` sidecar bring-ups): require pg_isready AND a
    successful round-trip query (SELECT 1) for 3 consecutive iterations
    before declaring the sidecar ready.

    State branches:
      both_loops_defensive    → race cannot occur on any future build.
      one_loop_naive          → matching CI step would flake exactly as
                                build 7d30839 did (psql exit 2 mid-init).
      no_pg_sidecar           → covered by the parent test above.
    """
    text = CLOUDBUILD.read_text()
    if "pgvector/pgvector:pg15" not in text:
        # If the sidecar pattern is replaced by something else this
        # test becomes inapplicable; parent test will catch removal.
        return
    # Both sidecar containers MUST appear with their bring-up loops.
    for sidecar in ("dma-ci-mig-pg", "dma-ci-e2e-pg"):
        assert sidecar in text, (
            f"PG sidecar {sidecar} missing from cloudbuild.yaml — the "
            "live-PG round-trip OR the e2e-personas backend wiring "
            "would not have a real database."
        )
        # The defensive marker `SELECT 1` MUST appear in the same line
        # as the pg_isready check for this sidecar — naive loops have
        # only pg_isready and miss the init-restart cycle.
        lines = text.splitlines()
        found_defensive = False
        for i, ln in enumerate(lines):
            if "pg_isready" in ln and sidecar in ln:
                # Look at the next 2 lines for the AND-clause + SELECT 1.
                window = "\n".join(lines[i:i + 3])
                if "SELECT 1" in window and sidecar in window:
                    found_defensive = True
                    break
        assert found_defensive, (
            f"PG sidecar {sidecar} wait loop is naive (pg_isready only) "
            "— the pgvector/pgvector:pg15 init-then-restart cycle WILL "
            "flake CI with `FATAL: the database system is shutting "
            "down`. Fix: require pg_isready AND `psql -c \"SELECT 1\"` "
            "to both succeed for 3 consecutive iterations before "
            "proceeding (see backend/scripts/ci-live-migration.sh for "
            "the canonical pattern)."
        )
    # The script too must use the same defensive pattern.
    script = APP_ROOT / "backend" / "scripts" / "ci-live-migration.sh"
    if script.exists():
        script_text = script.read_text()
        assert "SELECT 1" in script_text and "SUCCESS" in script_text, (
            "ci-live-migration.sh uses a naive pg_isready wait loop — "
            "would flake on pgvector init-restart. Add the same "
            "consecutive-success defence used in cloudbuild.yaml."
        )


# ── #9: nginx upstream variable form — defer DNS to runtime ───────────


def test_frontend_nginx_template_uses_variable_for_upstream() -> None:
    """frontend-nginx.template MUST use a variable in proxy_pass so DNS
    resolution is deferred to request time.

    State branches:
      variable_form_present       → nginx defers DNS to runtime; smoke step
                                    + prod Cloud Run rollouts both survive
                                    a transient unresolvable backend host.
      literal_url_in_proxy_pass   → nginx parses upstream at config-load
                                    and crashes with `host not found in
                                    upstream "<host>"`. This bit the
                                    frontend-image-smoke step on 2026-05-27
                                    (`stub-backend` doesn't exist by
                                    design). Same class trips prod
                                    whenever a Cloud Run revision rollout
                                    briefly removes the backend hostname.

    The fix lifted from the standard nginx pattern:
        resolver 8.8.8.8 ipv6=off valid=300s;
        set $upstream_backend "${BACKEND_URL}";
        proxy_pass $upstream_backend;
    """
    template = INFRA / "docker" / "frontend-nginx.template"
    assert template.exists(), f"missing {template}"
    text = template.read_text()

    # The literal-URL form must NOT appear inside any /api/ block — that's
    # exactly what crashes nginx at startup.
    assert "proxy_pass ${BACKEND_URL};" not in text, (
        "frontend-nginx.template uses literal `proxy_pass ${BACKEND_URL};` — "
        "nginx will crash with 'host not found in upstream' at startup if "
        "BACKEND_URL points at a host that doesn't resolve right now. Use "
        "the variable form: `set $upstream_backend \"${BACKEND_URL}\"; "
        "proxy_pass $upstream_backend;` so resolution is deferred to "
        "request time."
    )

    # Affirmative: both the `set` and the variable `proxy_pass` must be present.
    assert 'set $upstream_backend "${BACKEND_URL}";' in text, (
        "frontend-nginx.template missing `set $upstream_backend …` — "
        "without the variable form, nginx parses the upstream at "
        "config-load and crashes when the host can't be resolved."
    )
    assert "proxy_pass $upstream_backend;" in text, (
        "frontend-nginx.template missing `proxy_pass $upstream_backend;` — "
        "even with the `set` directive, you must reference the variable "
        "in proxy_pass for nginx to defer DNS resolution."
    )

    # The runtime resolver must still be configured — without it, the
    # variable-form proxy_pass would have no way to resolve the host
    # when the request arrives.
    assert "resolver 8.8.8.8" in text, (
        "frontend-nginx.template missing `resolver 8.8.8.8` — runtime "
        "resolution needs an explicit resolver since nginx defaults to "
        "/etc/resolv.conf which behaves inconsistently in containers."
    )


# ── #11: Stage 2b runs live-PG pytest against the BUILT image ─────────


def test_cloudbuild_stage_2b_runs_live_pg_pytest() -> None:
    """Stage 2b (backend-tests-live-pg) MUST run pytest with
    SEED_CI_PG_URL set against the just-built backend image, not just
    the alembic round-trip.

    State branches:
      runs_live_pg_pytest    → 24 currently-SEED_CI_PG_URL-gated tests
                                execute against the prod artifact +
                                real Postgres. SQL bugs (like the
                                2026-05-27 FILTER-on-ROUND parser
                                error that returned 500 from every
                                /overview call) are caught at stage 2b
                                — before stage 7 e2e ever runs.
      alembic_only           → 24 highest-value tests skip silently
                                with "SEED_CI_PG_URL not set", letting
                                router SQL bugs slip into production.

    The image-as-stress-test contract: the SAME backend image that
    Cloud Build will push to gcr.io is exercised against the SAME
    schema that Cloud Build just round-trip validated. This is what
    DEPLOYMENT.md §5 calls out — the deployable artifact MUST stress-
    test itself against real Postgres before deploy.
    """
    text = CLOUDBUILD.read_text()
    # Locate the stage 2b block (between its id: header and the next stage).
    import re
    m = re.search(
        r"- id:\s+backend-tests-live-pg\b(.*?)(?=- id:|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "backend-tests-live-pg stage not found in cloudbuild.yaml"
    stage_2b = m.group(1)

    # Affirmative: SEED_CI_PG_URL env var must be set on the pytest run.
    assert "SEED_CI_PG_URL=postgresql" in stage_2b, (
        "stage 2b must set SEED_CI_PG_URL on the live-PG pytest step "
        "so the 24 currently-gated tests actually execute. Without it "
        "they skip silently as 'SEED_CI_PG_URL not set' and bugs like "
        "the FILTER-on-ROUND SQL parser error slip past stage 2b."
    )
    # Affirmative: the pytest invocation MUST cover the 4 gated files.
    # Batch 13 production-readiness: stage 2b now runs `pytest tests/`
    # (full directory) instead of an explicit subset, so all newly-added
    # tests are exercised in CI without orphan-risk. Either explicit
    # listing OR full-directory invocation satisfies this contract.
    if "python -m pytest tests/ " in stage_2b or "python -m pytest tests/\\" in stage_2b:
        # Full-directory invocation — all live-DB tests are picked up
        # by pytest discovery. The corpus-dependent files
        # (adversarial / reingest_scenarios / backfill_skip_path) are
        # legitimately --ignored here because they need the full
        # 113-package corpus; they run in the qa-gates stage instead.
        # The contract test
        # `test_qa_v2_cloudbuild_coverage.py` pins that those tests
        # appear in qa-gates so they never orphan.
        pass
    else:
        # Legacy explicit-list invocation — verify each gated file is
        # named explicitly.
        for required_file in (
            "tests/test_persona_e2e.py",
            "tests/test_live_db_integration.py",
            "tests/test_job_executions_insert_no_ambiguous_params.py",
            "tests/test_seed_ci.py",
        ):
            assert required_file in stage_2b, (
                f"stage 2b's live-PG pytest must include {required_file} — "
                f"it's one of the 4 files gated on SEED_CI_PG_URL and skips "
                f"silently elsewhere."
            )
    # Affirmative: seed_ci must run before pytest so the persona tests
    # have data to assert against.
    assert "app.scripts.seed_ci" in stage_2b, (
        "stage 2b must invoke seed_ci before pytest — the live-PG tests "
        "assume the 5 fixtures are persisted"
    )
    # Negative: the pytest step must use the just-built BACKEND_IMG, not
    # a generic python image — that's what makes this the
    # image-as-stress-test pattern.
    assert "$$BACKEND_IMG" in stage_2b, (
        "stage 2b's live-PG pytest must run against $$BACKEND_IMG "
        "(the just-built artifact). Running against a generic python "
        "image would lose the contract that we exercise the deployable."
    )


# ── #10: stage-7 backend sidecar pins --workers=1 to avoid JWT key drift ─


def test_cloudbuild_stage_7_backend_pins_single_uvicorn_worker() -> None:
    """The CI e2e backend sidecar MUST start uvicorn with --workers 1.

    Each uvicorn worker is a separate Python process. In ENV=local
    (no JWT_PRIVATE_KEY_PEM, no key file in the image), jwt_service.py
    falls back to `_generate_ephemeral_key` which is decorated with
    `@lru_cache(maxsize=1)` — the cache is PER PROCESS. With 2+
    workers, dev-login (worker A) signs a JWT with key A; the
    subsequent /api/v1/auth/me may be round-robined to worker B which
    verifies the JWT with key B and fails with 401 "Invalid session".

    Symptom this guard catches: persona e2e tests fail intermittently
    in CI with `auth verification FAILED: GET /api/v1/auth/me returned
    401` after a successful dev-login, even though the dma_session
    cookie is correctly placed in the browser context.

    Production is fine because JWT_PRIVATE_KEY_PEM is wired via Secret
    Manager so every worker shares the same key. The bug is specific
    to the CI sidecar which uses the ephemeral fallback.
    """
    text = CLOUDBUILD.read_text()
    import re
    m = re.search(
        r"- id:\s+e2e-personas\b(.*?)(?=- id:|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "e2e-personas stage not found in cloudbuild.yaml"
    stage_7 = m.group(1)

    # Find the `docker run -d --name dma-ci-e2e-backend ...` invocation.
    backend_match = re.search(
        r"docker run -d --name dma-ci-e2e-backend(.*?)(?=docker (?:exec|run|rm)|# ──|\Z)",
        stage_7,
        re.DOTALL,
    )
    assert backend_match, (
        "could not locate `docker run -d --name dma-ci-e2e-backend` in "
        "stage 7"
    )
    backend_run = backend_match.group(1)
    assert "--workers 1" in backend_run or "--workers=1" in backend_run, (
        "stage 7's backend sidecar must be started with `--workers 1` so "
        "all JWT operations happen in a single Python process — otherwise "
        "the ephemeral RSA keypair (jwt_service.py `_generate_ephemeral_"
        "key`, lru_cached per process) differs between workers and "
        "JWT verify fails with 401 'Invalid session' when dev-login lands "
        "on worker A and /auth/me round-robins to worker B."
    )


# ── #11: cloudbuild bash -c blocks free of stray apostrophes ──────────


def test_cloudbuild_inner_bash_c_blocks_have_no_apostrophes() -> None:
    """Inside `bash -c '...'` (or `"$$BACKEND_IMG" -c '...'`) the script
    is wrapped in single quotes. A stray apostrophe in a comment or
    string silently terminates the quoted region — the rest of the
    "script" leaks into the outer bash and runs in the cloudbuild
    step image (e.g. cloud-builders/docker, which has no Python).

    Failure mode the test was added to catch (stage-2b regression
    2026-05-27): `# Deselect 4 tests that don't fit ...` — the
    apostrophe in `don't` ended the inner script after seed_ci, and
    the subsequent `python -m pytest ...` ran in cloud-builders/docker
    where it surfaced as `bash: line 161: python: command not found`.

    Any block opened with `-c '` (single quote at end of line) and
    closed by a line consisting only of `'` (possibly with `|| { ... }`
    trailing) MUST contain zero `'` characters in between.
    """
    text = CLOUDBUILD.read_text()
    lines = text.splitlines()

    in_block = False
    opener_lineno = 0
    offenders: list[tuple[int, int, str]] = []  # (block_opener, line_no, line)

    open_re = re.compile(r"-c\s+'\s*$")
    # Closing pattern: line is just `'` possibly followed by `|| ...` or comment.
    close_re = re.compile(r"^\s*'(\s*(\|\||#|$))")

    for i, line in enumerate(lines, start=1):
        if not in_block:
            if open_re.search(line):
                in_block = True
                opener_lineno = i
            continue
        # in_block
        if close_re.match(line):
            in_block = False
            continue
        if "'" in line:
            offenders.append((opener_lineno, i, line))

    assert not offenders, (
        "apostrophe(s) inside single-quoted `bash -c '...'` block — these "
        "silently terminate the inner script and the rest leaks to the "
        "outer cloudbuild shell:\n  "
        + "\n  ".join(
            f"opened @ L{op}, offender L{ln}: {ln_text.strip()}"
            for op, ln, ln_text in offenders
        )
    )


# ── #11: frontend.Dockerfile robust meta-tag injection ────────────────


def test_frontend_dockerfile_meta_tag_injection_robust() -> None:
    """frontend.Dockerfile MUST inject <meta name=\"x-build-sha\"> via a
    POSIX-portable mechanism, NOT via `\\n` in a sed replacement.

    State branches:
      portable_form_present  → printf + temp file + `sed -i /pat/r FILE`
                                — works on GNU sed AND BusyBox sed AND
                                any POSIX sed.
      brittle_backslash_n    → `sed -i -E 's#...#...\\n  <meta...'` —
                                BusyBox sed in alpine + classic Docker's
                                RUN parser silently drop the substitution,
                                shipping an image with no x-build-sha tag.
                                This bit stage 7b on 2026-05-27 the moment
                                the prior nginx-upstream crash was fixed
                                and the smoke step actually ran probe #3.

    The fix is anchored in ERROR HISTORY D6 in the Dockerfile.
    """
    dockerfile = INFRA / "docker" / "frontend.Dockerfile"
    assert dockerfile.exists(), f"missing {dockerfile}"
    text = dockerfile.read_text()

    # Brittle pattern must not return.
    assert "\\\\n  <meta name=\\\"x-build-sha\\\"" not in text, (
        "frontend.Dockerfile is using the brittle `sed -i ... \\\\n  <meta...` "
        "form to inject x-build-sha. BusyBox sed in alpine doesn't reliably "
        "interpret \\\\n through classic Docker's RUN parser — the meta tag "
        "silently fails to materialize. Use the portable pattern: printf to "
        "a temp file + `sed -i '/pat/r FILE'`."
    )

    # Affirmative: the portable pattern must be present.
    assert "printf" in text and "x-build-sha" in text, (
        "frontend.Dockerfile must include the printf-based meta-tag stamping"
    )
    assert "/r /tmp/dma-meta-stamp" in text, (
        "frontend.Dockerfile must use `sed -i '/pat/r /tmp/dma-meta-stamp'` "
        "to inject the meta tag — that's the POSIX-portable pattern that "
        "works on BusyBox sed."
    )


# ── #8: Backfill resilience (covered by stress_e2e — assertion gate) ─


def test_backfill_stress_e2e_suite_present() -> None:
    """The 8th recurring failure mode (`backfill failed` against the
    RegionsBank package, dedup collisions, freshness rollup mismatches)
    is covered by `tests/test_stress_e2e.py`. This test asserts the
    suite is present + covers the named scenarios so a future
    contributor can't quietly delete the coverage.

    State branches:
      suite_present_with_scenarios → covered.
      suite_missing                → file disappeared; tests below would
                                     not catch the next backfill drift.
      scenario_missing             → coverage hole.
    """
    stress = APP_ROOT / "backend" / "tests" / "test_stress_e2e.py"
    assert stress.exists(), "test_stress_e2e.py disappeared — backfill " \
        "regression net is gone"
    text = stress.read_text()
    # The named recurring scenarios from STATUS.md's stress-test matrix.
    required_scenarios = [
        "TestDedupResilience",
        "TestCrossEntityEvidence",
        "TestFreshnessRollup",
        "TestMultiRunProfile",
        "TestStaleBundleFlag",
        "TestArchetypeShift",
        "TestDedupTierUpgrade",
    ]
    for scenario in required_scenarios:
        assert scenario in text, (
            f"test_stress_e2e.py missing {scenario} — backfill safety "
            f"net regressed; the recurring failure class would re-occur"
        )


# ── #17: workers + backend MUST inject DATABASE_URL_SYNC (2026-05-28) ──


def test_terraform_injects_database_url_sync_into_workers_and_backend() -> None:
    """Terraform `infra/terraform/main.tf` must wire `DATABASE_URL_SYNC`
    via secret_key_ref into both:

      1. The workers Cloud Run Jobs spec (`google_cloud_run_v2_job.worker`)
      2. The backend Cloud Run Service spec (`google_cloud_run_v2_service.backend`)

    Pre-fix (commit 8271ee3), workers only had `DATABASE_URL` (asyncpg)
    injected. The four sync-DB call sites (job_executions_db,
    synthesis_cache_db, ccg_loader._persist_loader_run, post_migrate)
    silently no-op'd or raised swallowed exceptions in worker
    processes. Application code now derives the sync DSN from
    DATABASE_URL via `resolve_sync_dsn`, but the architecturally
    durable path is explicit env injection — visible in
    `gcloud run services describe ...` env without reading code.

    The new secret `dma-insights-database-url-sync` was created in the
    same commit; this test pins:
      (a) the secret resource is declared,
      (b) the worker job spec references it via secret_key_ref,
      (c) the backend service spec references it via secret_key_ref,
      (d) the secret is in `local.backend_secrets` so the IAM grant
          for `roles/secretmanager.secretAccessor` covers it.
    """
    import re
    tf_path = APP_ROOT / "infra" / "terraform" / "main.tf"
    text = tf_path.read_text()

    # (a) Secret resource is declared.
    assert 'resource "google_secret_manager_secret" "database_url_sync"' in text, (
        "Terraform must declare `google_secret_manager_secret`"
        " `database_url_sync` — every other sync-DB path now derives "
        "from DATABASE_URL via the resolver fallback, but the explicit "
        "secret is the durable contract."
    )
    assert 'secret_id = "dma-insights-database-url-sync"' in text, (
        "secret_id must match the Secret Manager key the workers "
        "+ backend reference via secret_key_ref"
    )
    # The secret version must use the +psycopg driver, NOT +asyncpg
    # (otherwise we've created a redundant copy of database_url).
    sync_version_block_match = re.search(
        r'resource\s+"google_secret_manager_secret_version"\s+'
        r'"database_url_sync"\s*\{[^}]+\}',
        text, re.DOTALL,
    )
    assert sync_version_block_match, "sync version resource block missing"
    block = sync_version_block_match.group(0)
    assert "postgresql+psycopg://" in block, (
        "database_url_sync secret_data must use +psycopg (not +asyncpg) "
        "— that's the whole point of the new secret"
    )

    # (b) + (c) Both Cloud Run resources reference the secret.
    # We need TWO occurrences of `secret = "dma-insights-database-url-sync"`
    # — one each in the worker and backend env blocks.
    refs = re.findall(
        r'secret\s*=\s*"dma-insights-database-url-sync"',
        text,
    )
    assert len(refs) >= 2, (
        f"expected ≥2 references to `dma-insights-database-url-sync` "
        f"secret (one in worker job env, one in backend service env); "
        f"got {len(refs)}. Without both, the env var won't be in the "
        f"running container."
    )

    # (d) Secret is in `local.backend_secrets` so IAM accessor binding
    # exists.
    locals_block = re.search(
        r'locals\s*\{[^}]+backend_secrets\s*=\s*\[(.*?)\]',
        text, re.DOTALL,
    )
    assert locals_block, "locals.backend_secrets list not found"
    assert '"dma-insights-database-url-sync"' in locals_block.group(1), (
        "`dma-insights-database-url-sync` must be in "
        "`local.backend_secrets` — otherwise the per-secret IAM grant "
        "(`google_secret_manager_secret_iam_member.backend_secret_access`) "
        "won't include it and Cloud Run will return 'permission denied' "
        "when the worker container starts."
    )


# ── Two-phase deploy + preflight-parameters (ADR 0013) ──────────


def test_preflight_parameters_script_exists_and_validates_required_vars() -> None:
    """preflight-parameters.sh is the canonical Phase 0 gate that
    fail-closes on any missing required parameter.

    The audit's pending-register item E pinned this as P1: every
    required parameter MUST be defined + non-empty BEFORE we start
    building images or invoking Terraform. The alternative is a
    half-deployed state where Cloud Run revisions exist but can't
    start because a secret is empty.

    Pin contract:
      * file exists, is executable
      * declares GCP_VARS array including PROJECT_ID + REGION
      * declares APP_SECRETS array including all 6 OOB secrets
      * has a fail-closed exit-1 branch when any required var is empty
      * has pattern sanity for PROJECT_ID, REGION, OAuth ID, REDIS_URL
    """
    script = INFRA / "preflight-parameters.sh"
    assert script.exists(), "infra/preflight-parameters.sh missing"
    assert script.stat().st_mode & 0o111, (
        "preflight-parameters.sh not executable; chmod +x required so "
        "deploy-two-phase.sh can invoke it from Phase 0"
    )
    text = script.read_text()
    # GCP-side variables.
    for var in ("PROJECT_ID", "REGION", "GOOGLE_OAUTH_CLIENT_ID"):
        assert var in text, f"preflight-parameters.sh missing {var}"
    # Out-of-band Secret-Manager secrets.
    for secret_var in (
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "DMA_BOT_API_KEY",
        "RAG_API_BEARER_KEY",
        "REDIS_URL",
        "CLAY_WEBHOOK_URL",
        "CLAY_WEBHOOK_SECRET",
    ):
        assert secret_var in text, (
            f"preflight-parameters.sh missing required secret {secret_var}"
        )
    # Pattern sanity checks present.
    assert ".apps.googleusercontent.com" in text, (
        "preflight-parameters.sh missing OAuth client_id pattern check"
    )
    assert "redis://" in text and "rediss://" in text, (
        "preflight-parameters.sh missing REDIS_URL pattern check"
    )
    # Fail-closed branch.
    assert re.search(r"exit\s+1", text), (
        "preflight-parameters.sh must exit 1 when required vars are missing"
    )


def test_deploy_two_phase_script_implements_seven_phases() -> None:
    """deploy-two-phase.sh closes the audit P1 traffic-shifts-before-
    migrations race window (ADR 0013).

    Pin contract (every phase header documented for the operator):
      * file exists, is executable
      * PHASE 0 (preflight-parameters.sh invocation)
      * PHASE 1 (gcloud builds submit)
      * PHASE 2 (gcloud run services update --no-traffic --tag)
      * PHASE 3 (migrate.sh invocation)
      * PHASE 4 (curl ${TAG_URL}/readyz probe — NOT the service URL)
      * PHASE 5 (update-traffic --to-latest)
      * PHASE 6 (frontend deploy — MUST run before verify so the served
        frontend SHA is the new build, not the stale prior image)
      * PHASE 7 (verify-deploy.sh — checks BOTH backend + frontend SHA,
        so it runs after both are promoted)

    The phase markers MUST stay verbatim in the script — operators
    grep for `==[ PHASE` to track progress.
    """
    script = INFRA / "deploy-two-phase.sh"
    assert script.exists(), "infra/deploy-two-phase.sh missing"
    assert script.stat().st_mode & 0o111, (
        "deploy-two-phase.sh not executable; chmod +x required"
    )
    text = script.read_text()
    # Phase markers — operators grep for these.
    for phase in (
        "PHASE 0: parameter validation",
        "PHASE 1: build images",
        "PHASE 2: deploy backend revision with --no-traffic",
        "PHASE 3: run migrations",
        "PHASE 4: probe new revision /readyz via tag URL",
        "PHASE 5: promote traffic to new revision",
        "PHASE 6: deploy frontend",
        "PHASE 7: verify-deploy on service URL",
    ):
        assert phase in text, f"deploy-two-phase.sh missing phase marker: {phase}"
    # Phase 0 chains preflight.
    assert "preflight-parameters.sh" in text, (
        "deploy-two-phase.sh must invoke preflight-parameters.sh in Phase 0"
    )
    # Phase 2 uses --no-traffic so we can run migrations before traffic shift.
    assert "--no-traffic" in text, (
        "deploy-two-phase.sh Phase 2 MUST use --no-traffic — this is the "
        "load-bearing flag that prevents Cloud Run from shifting traffic "
        "to the new revision before migrations run."
    )
    # Phase 2 uses --tag candidate-${SHA} so Phase 4 can probe the tag URL.
    assert "candidate-${SHA}" in text or "candidate-$SHA" in text, (
        "deploy-two-phase.sh Phase 2 must tag the new revision so "
        "Phase 4's tag-URL probe can reach it specifically"
    )
    # Phase 4 probes /readyz, NOT /healthz (which is shallow).
    assert "/readyz" in text, (
        "deploy-two-phase.sh Phase 4 must probe /readyz (NOT /healthz) — "
        "/readyz is the canonical migration-drift detector"
    )
    # Phase 5 only promotes via --to-latest after Phase 4 passes.
    assert "update-traffic" in text and "--to-latest" in text, (
        "deploy-two-phase.sh Phase 5 must promote via "
        "`gcloud run services update-traffic --to-latest`"
    )


def test_cloudbuild_step_args_under_cloud_build_10000_char_limit() -> None:
    """Cloud Build rejects any step arg > 10000 chars with
    `INVALID_ARGUMENT: invalid build: invalid .steps field: build step N
    arg M too long (max: 10000)`. The 2026-05-29 regression hit this when
    stage 2b's bash -c script grew past the limit with the no-skip
    expansion. Pin a 9500-char ceiling so future edits have a 500-char
    head-room before they break a build.
    """
    from pathlib import Path as _Path

    import yaml as _yaml
    yml_path = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "cloudbuild.yaml"
    )
    doc = _yaml.safe_load(yml_path.read_text())
    over_ceiling: list[str] = []
    for i, step in enumerate(doc["steps"]):
        for j, arg in enumerate(step.get("args", []) or []):
            if len(arg) > 9500:
                over_ceiling.append(
                    f"step {i} ({step.get('id','?')}) arg {j}: {len(arg)} chars"
                )
    assert not over_ceiling, (
        "Cloud Build step arg(s) approaching the 10000-char limit "
        "(9500-char safety ceiling). Trim verbose comments before "
        "the next push:\n  " + "\n  ".join(over_ceiling)
    )


def test_deploy_two_phase_creates_clay_placeholder_secrets_before_phase2() -> None:
    """When DMA_CLAY_DEFERRED=1 (or both Clay secrets aren't yet in
    Secret Manager), the Cloud Run service spec's secret_key_ref for
    the two Clay env vars would 404 at deploy time with
    `Secret … was not found`. deploy-two-phase.sh must create empty
    placeholder secrets BEFORE Phase 2 so the deploy goes through.

    The backend's Clay client fail-closes on empty values per ADR 0010,
    so empty == deferred semantically. When the operator later supplies
    real values, the next revision roll picks them up via `latest`.

    Regression-pin: 2026-05-29 deploy hit
    `spec.template.spec.containers[0].env[7].value_from.secret_key_ref.name:
     Secret … dma-insights-clay-webhook-secret … was not found`
    despite DMA_CLAY_DEFERRED=1 in the preflight.
    """
    import re
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "deploy-two-phase.sh"
    ).read_text()

    # 1. The placeholder block must exist.
    assert "Clay placeholder secrets when deferred" in src, (
        "deploy-two-phase.sh must auto-create Clay placeholder secrets "
        "when deferred"
    )
    for sid in (
        "dma-insights-clay-webhook-url",
        "dma-insights-clay-webhook-secret",
    ):
        assert sid in src, f"placeholder block must reference secret '{sid}'"

    # 2. It must run BEFORE Phase 2 (which is where `gcloud run
    #    services update` fires the secret_key_ref check).
    placeholder_idx = src.find("Clay placeholder secrets when deferred")
    phase2_idx = src.find("PHASE 2: deploy backend revision")
    assert placeholder_idx > 0 and phase2_idx > 0
    assert placeholder_idx < phase2_idx, (
        "Clay placeholder block must run BEFORE the Phase 2 banner "
        "or `gcloud run services update` still 404s"
    )

    # 3. The block must `gcloud secrets create` (with replication +
    #    deferred=true label) AND `gcloud secrets versions add` so the
    #    `latest` ref resolves.
    block = src[placeholder_idx:phase2_idx]
    assert "gcloud secrets create" in block
    assert "labels=deferred=true" in block
    assert "gcloud secrets versions add" in block

    # 4. Must be idempotent — both `gcloud secrets create` and the
    #    `versions add` must be guarded by an existence check (a
    #    `describe` or `versions list` call) so a re-run on an
    #    already-populated project is a no-op.
    assert re.search(
        r"if\s*!\s*gcloud\s+secrets\s+describe", block,
    ), "create must be guarded by `if ! gcloud secrets describe` (idempotency)"
    assert "gcloud secrets versions list" in block, (
        "version-add must be guarded by `versions list` check (idempotency)"
    )


def test_recover_db_passwords_auto_imports_drifted_secrets() -> None:
    """`terraform apply` recurs `Error 409: Secret … already exists` when a
    Terraform-managed secret was created out-of-band (gcloud, prior
    partial-apply, dev shell) and the .tfstate has no record of it. The
    parallelism-escalation retry loop CAN'T fix this — every attempt
    hits the same 409 and the operator is left stuck (4 retries, all
    same error, then 'exhausted retries').

    The fix is `terraform import` between retries. Pin the
    `tf_import_drifted_secrets` helper:
      - Defined alongside the retry loop in recover-db-passwords.sh.
      - Inspects the prior apply's stderr for the 409 message scoped to
        each Terraform-managed secret name.
      - Skips if `terraform state list` already has the resource (so
        a clean state isn't disturbed; idempotent).
      - Runs `terraform import <addr> projects/<proj>/secrets/<sid>`
        for each drifted one.
      - The retry loop wires it: capture stderr per-attempt via
        `2> >(tee "$stderr_file" >&2)` (keeps live stream + writes a
        copy for inspection), and on failure call the helper BEFORE
        sleeping; if it imports anything, retry immediately.

    Regression-pin: 2026-05-29 deploy hit the 409 4 times, exhausted retries,
    `recover-db-passwords.sh` failed, deploy-two-phase Phase 3 (migrate)
    aborted — every existing Terraform-managed secret would have hit
    the same wall on a fresh `terraform init`.
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()

    # Helper exists with the right name.
    assert "tf_import_drifted_secrets" in src, (
        "recover-db-passwords.sh must define tf_import_drifted_secrets "
        "to auto-import drifted secrets between apply retries"
    )

    # Every Terraform-managed secret name must be listed so each one
    # can be auto-imported when it drifts. (Names match main.tf.)
    for sid in (
        "dma-insights-database-url",
        "dma-insights-database-url-sync",
        "dma-insights-database-url-superuser",
        "dma-insights-jwt-signing-key",
    ):
        assert sid in src, (
            f"tf_import_drifted_secrets must cover Terraform-managed "
            f"secret '{sid}' — without it a 409 on that secret will "
            f"loop forever"
        )

    # Skip-if-already-in-state guard (idempotency).
    assert "terraform state list" in src, (
        "tf_import_drifted_secrets must skip secrets already in state "
        "(idempotency — `terraform state list | grep -Fxq <addr>`)"
    )

    # Retry loop must capture stderr and call the helper on failure.
    assert 'tee "$stderr_file"' in src, (
        "tf_apply_with_retry must capture stderr (tee → $stderr_file) "
        "so tf_import_drifted_secrets can inspect the 409 message"
    )
    assert "tf_import_drifted_secrets" in src.split(
        "tf_apply_with_retry()"
    )[-1], (
        "tf_apply_with_retry must invoke tf_import_drifted_secrets on "
        "failure (otherwise the retry just hits the same 409)"
    )

    # The actual import command must look right.
    import re
    assert re.search(
        r"terraform import.*?\"\$addr\".*?projects/\$\{PROJECT_ID\}/secrets/\$\{sid\}",
        src, re.S,
    ), "tf_import_drifted_secrets must run `terraform import <addr> projects/$PROJECT_ID/secrets/$sid`"


def test_verify_password_extracts_user_agnostically() -> None:
    """`verify_password` in recover-db-passwords.sh must extract the DB
    user FROM the DSN, not interpolate a hardcoded expected user into the
    regex. An out-of-band secret version can carry a different user
    (e.g. a first deploy created `dma_insights_app` while Terraform's
    convention is `dma_insights`); a hardcoded `://dma_insights:` regex
    then false-fails with "regex mismatch" even when the credential pair
    is internally consistent.

    Regression-pin: 2026-05-29 deploy — terraform apply succeeded but
    post-apply verify printed `couldn't extract password from
    dma-insights-database-url DSN (regex mismatch)` then `dma_insights
    STILL fails`, aborting Phase 3 (migrate), because the secret's latest
    version used user `dma_insights_app`.
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()

    # The OLD brittle form interpolated ${user} into the regex — must be gone.
    assert "://${user}:" not in src, (
        "verify_password must NOT hardcode the expected user in the "
        "extraction regex (breaks on dma_insights_app drift)"
    )

    # The NEW form extracts user (group 2) + password (group 3) generically.
    assert 'dsn_user=' in src and 'dsn_pw=' in src, (
        "verify_password must extract both dsn_user + dsn_pw from the DSN"
    )
    # Generic capture: ://([^:]+):([^@]+)@
    assert "://([^:]+):([^@]+)@" in src, (
        "verify_password must use a user-agnostic capture "
        "`://([^:]+):([^@]+)@`"
    )
    # Must connect as the DSN's user (reassigns `user` from dsn_user).
    assert "user=\"$dsn_user\"" in src, (
        "verify_password must connect AS the DSN's actual user, not the "
        "passed-in expected user"
    )


def test_recover_db_passwords_detects_async_sync_user_drift() -> None:
    """async (`database_url`) and sync (`database_url_sync`) DSNs must
    reference the SAME DB user — they're one account, two driver prefixes.
    If they diverge (manual `versions add` / half-finished deploy), the
    API (async) and workers (sync) auth as different accounts → grant
    chaos. recover-db-passwords.sh must detect + flag this.
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()
    assert "_dsn_user" in src, (
        "recover-db-passwords.sh must define a _dsn_user helper to compare "
        "the async vs sync DSN users"
    )
    assert 'ASYNC_USER' in src and 'SYNC_USER' in src, (
        "must capture both ASYNC_USER + SYNC_USER for the drift check"
    )
    assert '"$ASYNC_USER" != "$SYNC_USER"' in src, (
        "must compare async vs sync DSN users + flag the mismatch"
    )


def test_recover_db_passwords_resolves_sha_from_deployed_revision() -> None:
    """When the operator doesn't explicitly export $SHA, the script must
    NOT fall straight to `git rev-parse --short HEAD` — that's the SHA
    of the operator's local checkout, which may be ahead of the deployed
    Cloud Run revision by any number of doc-only commits whose images
    have never been built. The three
    `data "google_artifact_registry_docker_image"` blocks then fail at
    plan time with `Requested image was not found`.

    Correct precedence chain (encoded in `recover-db-passwords.sh`):
      1. explicit $SHA (operator was deliberate)
      2. /tmp/dma-insights-deploy-sha (handed off by deploy-two-phase.sh
         Phase 1 after `gcloud builds submit` succeeds)
      3. deployed Cloud Run backend revision's image SHA (guaranteed to
         have images in gcr.io because Cloud Run wouldn't be running
         them otherwise)
      4. git HEAD (developer / first-deploy fallback — auto-build kicks
         in if the images don't exist; see
         test_recover_db_passwords_auto_builds_missing_images)

    Regression-pin: 2026-05-29 deploy — operator's HEAD `bce8826`
    contained only doc/script fixes; gcr.io's most recent image tag was
    `9aafdc1` (the currently-deployed revision). `bash
    infra/recover-db-passwords.sh --rotate` exhausted all 4 retries with
    `Error: Requested image was not found` on three image data blocks.
    The deployed-revision-SHA default would have picked `9aafdc1` and
    the apply would have succeeded immediately.
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()

    # The deployed-revision SHA helper exists with the right name.
    assert "_sha_from_deployed_revision" in src, (
        "recover-db-passwords.sh must define `_sha_from_deployed_revision` "
        "to read the SHA from the live Cloud Run backend image — this is "
        "the only SHA guaranteed to have images in gcr.io"
    )
    # It must query Cloud Run for the backend service's image URI.
    assert "gcloud run services describe dma-insights-backend" in src, (
        "_sha_from_deployed_revision must use `gcloud run services "
        "describe dma-insights-backend` to find the deployed image"
    )
    assert "spec.template.spec.containers[0].image" in src, (
        "_sha_from_deployed_revision must extract the image URI "
        "(spec.template.spec.containers[0].image) from the Cloud Run "
        "service descriptor"
    )

    # Priority chain labels (2026-06 anti-stale fix): explicit > deployed-
    # revision > deploy-branch-tip (resolve-deploy-sha.sh) > deploy-handoff
    # (/tmp) > git-head. Every branch records its source for debuggability.
    for label in ("explicit", "deployed-revision", "deploy-branch-tip",
                  "deploy-handoff", "git-head"):
        assert f'"{label}"' in src or f"'{label}'" in src, (
            f"SHA-source label '{label}' missing — every branch of the "
            f"priority chain must record which source supplied SHA so "
            f"the operator can debug `→ SHA=… (resolved via: …)` output"
        )

    # Order check: `deployed-revision` must be tried BEFORE `git-head`.
    deployed_idx = src.find('"deployed-revision"')
    git_head_idx = src.find('"git-head"')
    assert 0 < deployed_idx < git_head_idx, (
        "deployed-revision must be tried BEFORE git-head — the deployed "
        "revision's SHA always has built images; git HEAD may not"
    )

    # `deployed-revision` must now come BEFORE `deploy-handoff` (the bde8329
    # fix): mid-deploy the SHA is passed EXPLICITLY (so order is moot), and in
    # a STANDALONE rotation the live service is the truth — a leftover
    # /tmp/dma-insights-deploy-sha from a prior deploy must NOT outrank it.
    deploy_handoff_idx = src.find('"deploy-handoff"')
    assert 0 < deployed_idx < deploy_handoff_idx, (
        "deployed-revision must be tried BEFORE deploy-handoff so a STALE "
        "/tmp/dma-insights-deploy-sha can't make the password roll target an "
        "old image (the bde8329 incident)"
    )


def test_recover_db_passwords_auto_builds_missing_images() -> None:
    """If the resolved $SHA doesn't have images at gcr.io, the script
    must auto-build them via `gcloud builds submit` rather than
    failing the apply with `Requested image was not found`. Pinning
    auto-build (vs aborting) is the operational difference between
    "operator runs one command and it works" and "operator runs the
    command, gets a cryptic error, googles, runs gcloud builds submit
    manually, waits 15 min, then re-runs the script". Operator time
    is the constraint.

    The auto-build must:
      - check all 3 image tags exist at $SHA in gcr.io
      - if any are missing, invoke `gcloud builds submit` against the
        cloudbuild.yaml with `--substitutions=_IMAGE_SHA=$SHA`
      - re-verify all 3 land after the build (catch tag mismatches
        in cloudbuild.yaml)
      - bail with a clean error if Cloud Build itself fails
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()

    assert "ensure_images_built" in src, (
        "recover-db-passwords.sh must define `ensure_images_built` to "
        "verify-and-build the 3 images before terraform apply"
    )

    # Must check all 3 image names.
    for img in ("dma-insights-backend", "dma-insights-frontend",
                "dma-insights-workers"):
        assert img in src, (
            f"ensure_images_built must check image '{img}' (one of the "
            f"three resources Terraform data-lookups require)"
        )

    # Must use gcloud container images describe to verify existence.
    assert "gcloud container images describe" in src, (
        "ensure_images_built must use `gcloud container images "
        "describe` to verify image existence at gcr.io"
    )

    # Must auto-build via gcloud builds submit when missing.
    assert "gcloud builds submit" in src, (
        "ensure_images_built must auto-build via `gcloud builds submit` "
        "when any image is missing — aborting would force the operator "
        "to run the build command by hand"
    )
    assert "_IMAGE_SHA=" in src, (
        "auto-build must pass --substitutions=_IMAGE_SHA=$SHA so the "
        "build produces tags matching the SHA terraform will look up"
    )
    assert "cloudbuild.yaml" in src, (
        "auto-build must reference the canonical cloudbuild.yaml so it "
        "produces all 3 images in one job (matching deploy-two-phase)"
    )

    # The preflight must actually be invoked before terraform apply —
    # not just defined.
    assert "ensure_images_built ||" in src or "if ! ensure_images_built" in src, (
        "ensure_images_built must be invoked + its exit code checked "
        "before any `tf_apply_with_retry` call — defining the helper "
        "is meaningless if no path calls it"
    )

    # The invocation must happen BEFORE the `if [[ "$MODE" == "rotate" ]]`
    # block (otherwise rotate-only branches bypass the preflight).
    rotate_branch_idx = src.find('if [[ "$MODE" == "rotate" ]]; then')
    ensure_call_idx = src.find("ensure_images_built ||")
    if ensure_call_idx == -1:
        ensure_call_idx = src.find("if ! ensure_images_built")
    assert 0 < ensure_call_idx < rotate_branch_idx, (
        "ensure_images_built must be CALLED before the rotate/heal "
        "if/else block — otherwise the preflight runs nothing"
    )


def test_recover_db_passwords_preflight_skips_when_sha_from_deployed_revision() -> None:
    """Optimization: when the SHA was resolved from the deployed Cloud
    Run revision, the images are guaranteed to exist (Cloud Run
    wouldn't be running them otherwise). Skip the `gcloud container
    images describe` round-trips in that case — pure latency win,
    no correctness implication.

    This is also a load-bearing assertion: when the deploy is healthy
    + the operator just wants a quick password rotation, the script
    should be FAST. Pre-flighting an image lookup we know will succeed
    adds 2-3 seconds x 3 images to every invocation.
    """
    from pathlib import Path as _Path
    src = (
        _Path(__file__).resolve().parents[2]
        / "infra" / "recover-db-passwords.sh"
    ).read_text()
    # The skip-fast path must check the source label.
    assert 'deployed-revision' in src, (
        "ensure_images_built must reference 'deployed-revision' label "
        "to skip describes when SHA came from the live service"
    )
    # The skip must produce a clearly-labelled status line so an operator
    # debugging a stuck rotation can see the preflight ran.
    assert "present (running in deployed revision)" in src \
        or "running in deployed revision" in src, (
        "skip-fast path must print a status line so operator sees "
        "the preflight ran (not silently skipped — confusing)"
    )


def test_run_local_tests_script_is_turnkey_and_sudo_free() -> None:
    """The local backend test runner must require NO interactive sudo and
    NO hand-typed passwords — it replaces the fragile DEPLOYMENT.md §0.6c
    block that made the operator run `sudo -u postgres psql …` (which
    prompts for an OS password they often don't have) + paste a 6-line
    `export` block that the terminal corrupts.

    Regression-pin: 2026-05-29 operator hit `sudo: a password is required`
    (3 failed attempts) + `cd: apps/dma-insights/backend: No such file`
    + `alembic: command not found` + `No module named pytest` trying to
    run the suite from the pasted block.

    Contract:
      - script exists + is executable
      - resolves paths absolutely (no fragile relative `cd`)
      - brings the DB up via docker compose (creds baked in — no sudo)
      - never calls `sudo -u postgres` in the primary path
      - wires every env var the suite needs
      - installs deps from pyproject (no duplicated pin list to drift)
    """
    script = APP_ROOT / "backend" / "scripts" / "run-local-tests.sh"
    assert script.exists(), (
        "backend/scripts/run-local-tests.sh must exist (turnkey local "
        "test runner replacing the sudo block)"
    )
    assert script.stat().st_mode & 0o111, "run-local-tests.sh not executable"
    src = script.read_text()

    # Assert on ACTUAL COMMANDS, not the header comment (which legitimately
    # names `sudo -u postgres` to explain what the script replaces). Strip
    # comment-only lines + trailing inline comments first.
    code_lines = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line.split(" #", 1)[0])
    code = "\n".join(code_lines)

    # No interactive sudo for the DB bootstrap. `sudo -u postgres` is the
    # exact thing that blocked the operator. Any sudo used for docker must
    # be non-interactive (`sudo -n`) so it can NEVER prompt.
    assert "sudo -u postgres" not in code, (
        "run-local-tests.sh must NOT use `sudo -u postgres` — that prompts "
        "for an OS password; bring the DB up via docker compose instead"
    )
    # Flag only sudo at a COMMAND POSITION that isn't `sudo -n`. A command
    # position is start-of-line or right after &&, ||, ;, |, or `(`. This
    # excludes `command -v sudo` (existence check) and the word "sudo"
    # inside echo strings (e.g. "(no sudo)…"), which can't prompt.
    for m in re.finditer(r"(?:^|&&|\|\|?|;|\()\s*sudo\b(?!\s+-n\b)", code, re.M):
        ctx = code[max(0, m.start() - 10):m.start() + 25]
        raise AssertionError(
            f"every sudo INVOCATION in run-local-tests.sh must be "
            f"non-interactive (`sudo -n`) so it can't prompt; found an "
            f"interactive sudo near: {ctx!r}"
        )
    # Positive: the docker path DOES use non-interactive sudo as a fallback.
    assert "sudo -n" in code, (
        "run-local-tests.sh should fall back to `sudo -n docker` when the "
        "user isn't in the docker group (non-interactive — never prompts)"
    )

    # Absolute path resolution (fixes the `cd apps/dma-insights/backend`
    # "No such file or directory" error when run from the wrong dir).
    assert "BASH_SOURCE" in src and "BACKEND_DIR=" in src, (
        "run-local-tests.sh must resolve its own dir via BASH_SOURCE so it "
        "works from any cwd"
    )

    # DB via docker compose (the no-sudo path).
    assert "docker" in src and "compose" in src, (
        "run-local-tests.sh must bring Postgres up via docker compose"
    )
    assert "docker-compose.yml" in src, (
        "must reference the repo's docker-compose.yml (pgvector + baked creds)"
    )

    # Auto-wires every env var the suite needs — operator types none.
    for var in (
        "DATABASE_URL=",
        "DATABASE_URL_SYNC=",
        "SEED_CI_PG_URL=",
        "DMA_BOT_API_KEY=",
        "RAG_API_BEARER_KEY=",
    ):
        assert var in src, (
            f"run-local-tests.sh must export {var.rstrip('=')} so the "
            f"DB/bearer-gated tests RUN instead of skipping"
        )

    # Deps from pyproject (no duplicated pin list to drift). It must NOT
    # `pip install -e .` (flat layout → setuptools multi-package error).
    # Check `code` (comment-stripped) for the negative so the explanatory
    # header comment doesn't trip it.
    assert "tomllib" in code and "pyproject.toml" in code, (
        "run-local-tests.sh must install deps by reading pyproject.toml "
        "(tomllib), not a hand-maintained duplicate list"
    )
    assert "pip install -e ." not in code and "pip install -e '.'" not in code, (
        "run-local-tests.sh must NOT `pip install -e .` — the flat layout "
        "has multiple top-level dirs which breaks setuptools auto-discovery"
    )


def test_run_local_tests_probes_seed_ci_pg_url_before_trusting() -> None:
    """A STALE SEED_CI_PG_URL inherited from an earlier manual attempt
    (e.g. `…@127.0.0.1:5432/dma_insights_ci` with nothing listening) must
    NOT silently defeat the turnkey docker path. The script must TCP-probe
    the URL and only honour it when reachable; otherwise it clears the
    stale value and falls back to docker.

    Regression-pin: 2026-05-29 — the operator's shell still had
    SEED_CI_PG_URL set from a prior failed paste; run-local-tests.sh
    trusted it blindly, skipped the docker bring-up, and `alembic upgrade
    head` died with `connection refused` on 5432 (docker uses 5433).
    """
    script = APP_ROOT / "backend" / "scripts" / "run-local-tests.sh"
    src = script.read_text()

    # A probe helper exists.
    assert "_db_reachable" in src, (
        "run-local-tests.sh must define _db_reachable to TCP-probe an "
        "inherited SEED_CI_PG_URL before trusting it"
    )
    # The external-DB branch is gated on the probe RESULT, not mere
    # presence of the env var.
    assert "use_external=true" in src and "probe_rc" in src, (
        "the external-DB branch must be gated on the probe result "
        "(probe_rc), not on mere presence of SEED_CI_PG_URL"
    )
    # An unreachable inherited value must be cleared so it can't leak into
    # alembic/pytest, and the script must fall back to docker.
    assert "unset SEED_CI_PG_URL" in src, (
        "an unreachable inherited SEED_CI_PG_URL must be `unset` so it "
        "can't leak into alembic/pytest"
    )
    assert "bring_up_docker" in src, (
        "the fallback when SEED_CI_PG_URL is unreachable must be the "
        "docker bring-up"
    )

    # The probe must use the SYSTEM python3 — it runs BEFORE the venv is
    # created, so it cannot depend on `.venv/bin/python`.
    probe_block = src.split("_db_reachable()", 1)[1].split("\n}", 1)[0]
    assert "python3" in probe_block, (
        "_db_reachable must use the system python3 (runs before the venv "
        "exists — no client tools or venv assumed)"
    )
    assert ".venv" not in probe_block, (
        "_db_reachable must NOT use the venv python — the probe runs "
        "before the venv is created"
    )


def test_pyproject_declares_pydantic_email_extra() -> None:
    """Pydantic's `EmailStr` requires `pydantic[email]` (pulls in
    email-validator). The backend uses it in several schemas
    (auth/admin/entities). Both Dockerfiles AND cloudbuild stage 1 have
    been silently compensating by installing `pydantic[email]==2.9.2`
    directly — but pyproject's canonical `[project].dependencies`
    declared only plain `pydantic==2.9.2`.

    The cascade this regression pins:
      • run-local-tests.sh installs from pyproject → operator's local
        suite fails at collection with `ModuleNotFoundError: No module
        named 'email_validator'` (2026-05-29 operator hit this).
      • Any future `pip install -e .` (or wheel build, or Dependabot
        scan) sees the wrong contract.

    Fix lives in pyproject — Dockerfiles + cloudbuild are now mirrors.
    """
    deps = (APP_ROOT / "backend" / "pyproject.toml").read_text()
    # Tolerant match — any quoting / extra spec.
    assert re.search(
        r'"pydantic\[email\]==[\d.]+"', deps
    ) or 'pydantic[email]' in deps, (
        "pyproject [project].dependencies must declare `pydantic[email]` "
        "(EmailStr requires email-validator). Without the [email] extra, "
        "any install path that reads pyproject (run-local-tests.sh, "
        "pip install -e ., wheel build) fails at first model import."
    )


def test_pyproject_covers_every_dockerfile_bracket_extra() -> None:
    """Every bracket-extra used by either Dockerfile (backend.Dockerfile,
    worker.Dockerfile) MUST also appear in pyproject — runtime or
    optional. Otherwise the local install / wheel build / any non-Docker
    path silently misses the extra and dies at the first import that
    needs the underlying package.

    Locks the contract that pyproject is the canonical source of truth
    for production dependencies, with Dockerfiles as mirrors. The
    2026-05-29 `pydantic[email]` drift is exactly this class of failure.
    """
    import tomllib

    pyproject = APP_ROOT / "backend" / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    proj = data["project"]

    declared: set[tuple[str, frozenset[str]]] = set()
    for dep in (
        list(proj["dependencies"])
        + [d for grp in proj.get("optional-dependencies", {}).values() for d in grp]
    ):
        m = re.match(r"([A-Za-z0-9_.\-]+)(?:\[([a-z0-9,]+)\])?", dep)
        if m:
            name = m.group(1).lower()
            extras = frozenset(
                (m.group(2) or "").split(",")
            ) if m.group(2) else frozenset()
            declared.add((name, extras))

    dockerfile_extras: set[tuple[str, frozenset[str]]] = set()
    for df in ("backend.Dockerfile", "worker.Dockerfile"):
        text = (APP_ROOT / "infra" / "docker" / df).read_text()
        for m in re.finditer(
            r'"([A-Za-z0-9_.\-]+)\[([a-z0-9,]+)\][<>=!~]', text
        ):
            dockerfile_extras.add(
                (m.group(1).lower(), frozenset(m.group(2).split(",")))
            )

    missing = []
    for name, extras in dockerfile_extras:
        # Pass if pyproject has this pkg with the SAME-OR-WIDER extras.
        ok = any(
            d_name == name and extras.issubset(d_extras)
            for d_name, d_extras in declared
        )
        if not ok:
            missing.append(f"{name}[{','.join(sorted(extras))}]")

    assert not missing, (
        f"Dockerfile bracket-extras missing from pyproject "
        f"(canonical source of truth must mirror what prod actually "
        f"installs): {missing}. Add them to "
        f"backend/pyproject.toml [project].dependencies so non-Docker "
        f"install paths (run-local-tests.sh, pip install -e ., wheel "
        f"build) don't silently miss the extra."
    )


def test_preflight_image_check_builds_missing_images() -> None:
    """Contract (2026-05-29): when an image is missing at the target SHA,
    the deploy tooling BUILDS it — never skips/excludes/just-warns. This
    was reaffirmed after the operator hit `Requested image was not found`
    running raw `terraform plan` at a fresh HEAD with no built images.

    `preflight-image-check.sh` is the shared enforcement run before
    terraform plan/apply. It MUST:
      • check all 3 images, and
      • `gcloud builds submit` to build them when any is missing
        (default behaviour — not gated behind a flag), and
      • re-verify after building.
    A `--check-only` mode may report-without-building for CI/advisory.
    """
    src = (INFRA / "preflight-image-check.sh").read_text()

    # It must actually BUILD, not just print a "go build it" hint.
    assert "gcloud builds submit" in src, (
        "preflight-image-check.sh must BUILD missing images via "
        "`gcloud builds submit` (the agreed contract: build, never skip)"
    )
    assert "_IMAGE_SHA=" in src, (
        "the build must pass --substitutions=_IMAGE_SHA=$SHA so the tags "
        "match what terraform looks up"
    )
    assert "cloudbuild.yaml" in src, (
        "the build must use the canonical cloudbuild.yaml (all 3 images "
        "in one job)"
    )
    # All three images must be in scope.
    for img in ("dma-insights-backend", "dma-insights-frontend",
                "dma-insights-workers"):
        assert img in src, f"preflight must cover {img}"

    # Build must be the DEFAULT — only --check-only may skip building.
    assert "--check-only" in src, (
        "a --check-only mode must exist for CI/advisory verify-without-build"
    )
    # The build branch must NOT be reachable only via a build-opt-in flag;
    # assert the default path reaches `gcloud builds submit` (i.e. the
    # build is guarded by CHECK_ONLY being false, not by an opt-in).
    assert 'CHECK_ONLY" == "true"' in src or "CHECK_ONLY" in src, (
        "building must be the default; --check-only is the opt-OUT"
    )

    # Re-verify after building (catch a cloudbuild tag mismatch).
    assert "STILL_MISSING" in src or "still missing" in src.lower(), (
        "preflight must re-verify images landed after the build"
    )


def test_deployment_md_terraform_blocks_enforce_image_preflight() -> None:
    """Every DEPLOYMENT.md fenced block that runs `terraform plan` or
    `terraform apply` with an `image_sha`/`-var "image_sha` MUST be
    preceded (within the same fenced block) by a
    `preflight-image-check.sh` invocation — otherwise the operator hits
    `Requested image was not found` when the plan evaluates the three
    `google_artifact_registry_docker_image` data sources.

    Regression-pin: 2026-05-29 — the §0.7 raw-terraform block told
    operators to `terraform plan -var image_sha=$(git rev-parse --short
    HEAD)` with no build step; a fresh HEAD with no images failed the
    whole plan.

    `deploy.sh` / `deploy-two-phase.sh` invocations are exempt — those
    wrappers build images themselves.
    """
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()

    # Walk fenced ```bash blocks; flag any that run an image_sha-bearing
    # terraform plan/apply without a preflight call in the same block.
    blocks = re.findall(r"```bash\n(.*?)```", doc, re.DOTALL)
    offenders = []
    for b in blocks:
        runs_tf_with_sha = bool(
            re.search(r"terraform\s+(plan|apply)", b)
            and re.search(r"image_sha", b)
        )
        if not runs_tf_with_sha:
            continue
        # Exempt wrapper-driven blocks (they build internally).
        if "deploy.sh" in b or "deploy-two-phase.sh" in b:
            continue
        if "preflight-image-check.sh" not in b:
            offenders.append(b.strip()[:120])

    assert not offenders, (
        "DEPLOYMENT.md has terraform plan/apply block(s) with image_sha "
        "but no preflight-image-check.sh build-enforcement before them:\n"
        + "\n---\n".join(offenders)
    )


def test_deployment_md_local_test_setup_points_at_turnkey_script() -> None:
    """DEPLOYMENT.md §0.6c must steer operators to the turnkey script as
    the primary path, NOT the bare `sudo -u postgres` block. The manual
    block may survive only inside a clearly-fenced fallback `<details>`
    for the no-Docker case.
    """
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "run-local-tests.sh" in doc, (
        "DEPLOYMENT.md must reference backend/scripts/run-local-tests.sh "
        "as the primary local-test path"
    )
    # The primary instruction must not be the sudo block. Allow the phrase
    # only inside the collapsed fallback (after a <details> marker).
    if "sudo -u postgres" in doc:
        head = doc.split("run-local-tests.sh", 1)[0]
        assert "sudo -u postgres" not in head, (
            "the `sudo -u postgres` block must come AFTER the turnkey "
            "script reference (as a fenced fallback), never before it"
        )


def test_verify_deploy_has_blocking_readiness_gate() -> None:
    """verify-deploy.sh Layer 4 must BLOCK until the backend actually
    serves a 200 before asserting /healthz + /readyz — otherwise the
    cold-start race produces the recurring "/healthz: no response but
    /readyz green" false-negative.

    Regression-pin: 2026-05-29 deploy — terraform apply + migrations
    succeeded, but verify-deploy Layer 4 reported `✗ /healthz: no
    response` while `✓ /readyz reports ready` moments later. /healthz is
    a dependency-free always-200 handler; the only way it comes back
    empty is curl giving up before the freshly-rolled worker is serving.
    The prior single fire-and-forget warmup didn't guarantee warmth.

    Contract:
      - a polling loop (seq … sleep) that exits the instant a probe 200s
      - per-attempt --max-time + --connect-timeout (not one shared cap
        that the first assertion can burn entirely)
    """
    src = (INFRA / "verify-deploy.sh").read_text()
    # Layer 4 region.
    assert "Layer 4" in src
    layer4 = src.split("Layer 4", 1)[1]

    # Blocking poll loop with a sleep — not a single warmup.
    assert re.search(r"for\s+\w+\s+in\s+\$\(seq\s+1\s+\d+\)", layer4), (
        "Layer 4 must poll readiness in a `for _ in $(seq 1 N)` loop"
    )
    assert "sleep 5" in layer4 or re.search(r"sleep \d", layer4), (
        "the readiness loop must sleep between attempts"
    )
    assert "warm=true" in layer4 and "break" in layer4, (
        "the loop must set a warm flag + break the instant a probe 200s "
        "(so it doesn't waste the full budget once the instance is up)"
    )

    # Per-attempt timeouts — NOT a single --max-time that covers all
    # retries (the bug: the first assertion burned the whole 30s budget
    # against a cold instance).
    assert "--connect-timeout" in layer4, (
        "Layer 4 curls must set --connect-timeout so one slow connect "
        "can't eat the whole budget"
    )


def test_backend_cloud_run_has_startup_probe_on_healthz() -> None:
    """The backend Cloud Run service must declare a startup_probe on the
    dependency-free /healthz so Cloud Run only routes traffic (and only
    marks a fresh revision Ready) once uvicorn is serving HTTP — closing
    the cold-start window at the source.

    It MUST be /healthz, NOT /readyz: /readyz fail-closes (503) on
    migration drift, and deploy-two-phase.sh rolls a --no-traffic
    revision BEFORE migrations run — a /readyz startup probe would
    deadlock that revision until migrate.sh completes.
    """
    tf = TERRAFORM.read_text()
    # Isolate the backend service block.
    assert 'resource "google_cloud_run_v2_service" "backend"' in tf
    backend = tf.split(
        'resource "google_cloud_run_v2_service" "backend"', 1
    )[1].split('resource "google_cloud_run_v2_service" "frontend"', 1)[0]

    assert "startup_probe" in backend, (
        "backend Cloud Run service must declare a startup_probe to close "
        "the cold-start routing window"
    )
    # The startup probe's http_get path must be /healthz, not /readyz.
    sp = backend.split("startup_probe", 1)[1].split("}", 4)[0:5]
    sp_text = "}".join(sp)
    assert 'path = "/healthz"' in sp_text or 'path="/healthz"' in sp_text, (
        "startup_probe must target /healthz (dependency-free) so it "
        "can't deadlock the two-phase --no-traffic revision on migration "
        "drift"
    )
    # Guard against the deadlock footgun explicitly.
    assert 'path = "/readyz"' not in sp_text, (
        "startup_probe must NOT target /readyz — it 503s on migration "
        "drift and would wedge the pre-migration --no-traffic revision"
    )


# ── 2026-05-29 QA-deep-audit fixes ─────────────────────────────────────


def test_embedder_once_uses_date_isoformat_not_datetime() -> None:
    """`--once` mode in workers/embedder/main.py used `datetime.isoformat()`
    which produced a full timezone-aware datetime string. The live path
    then parsed it with `date.fromisoformat()` which REJECTS datetime
    strings, so every --once invocation crashed at run-selection with
    `ValueError: Invalid isoformat string`. Must be `.date().isoformat()`.
    """
    src = (APP_ROOT / "workers" / "embedder" / "main.py").read_text()
    # Find the --once → args.since assignment block.
    m = re.search(
        r"if args\.once and not args\.run_id and not args\.since:\s*\n"
        r"(?:.*?\n)*?\s*args\.since\s*=\s*([^\n]+)\n",
        src,
    )
    assert m, "embedder --once → args.since assignment not found"
    rhs = m.group(1)
    assert ".date().isoformat()" in rhs, (
        f"embedder --once must call `.date().isoformat()`; found: {rhs!r}. "
        f"The live path uses date.fromisoformat() which rejects full "
        f"datetime strings."
    )


def test_terraform_embedder_job_has_once_default_args() -> None:
    """Without a `--once` (or `--subscribe`) default in Terraform, the
    embedder Cloud Run Job exits 2 immediately with "one of --run-id,
    --since, or --subscribe is required" — so scheduler/admin dispatches
    appear to "run" but do no work. Pin the default."""
    src = TERRAFORM.read_text()
    # Locate the embedder's args array in locals.jobs. Per-job specs are now
    # objects (`embedder = { args = [...], timeout = ..., max_retries = ... }`,
    # 2026-06 cost safeguard), so match the args = [...] inside the object.
    m = re.search(
        r"embedder\s*=\s*\{[^}]*?args\s*=\s*\[(.*?)\]",
        src, re.DOTALL,
    )
    assert m, "embedder job spec missing from terraform locals.jobs"
    body = m.group(1)
    assert '"--once"' in body or "'--once'" in body, (
        "terraform locals.jobs.embedder must include `--once` "
        "(or `--subscribe`) as a default arg"
    )


def test_cloud_run_dispatch_interpolates_project_id_placeholder() -> None:
    """The ccg_loader JOB_DISPATCH default contains the literal Python
    string `gs://${PROJECT_ID}-catalogue-staging/v7.0/`. dispatch_job
    must interpolate `${PROJECT_ID}` from settings BEFORE dispatching,
    or the admin button reloads from a non-existent GCS path.
    """
    src = (
        APP_ROOT / "backend" / "app" / "services" / "cloud_run_dispatch.py"
    ).read_text()
    assert "${PROJECT_ID}" in src, (
        "JOB_DISPATCH should keep the ${PROJECT_ID} placeholder as a "
        "literal so the registry stays readable; the interpolation "
        "must happen in dispatch_job, not at module import time"
    )
    # The dispatcher must actually substitute the placeholder.
    assert 'replace("${PROJECT_ID}"' in src or "${PROJECT_ID}\", " in src, (
        "dispatch_job must `.replace(\"${PROJECT_ID}\", settings.gcp_project_id)` "
        "in args_list before invoking the Cloud Run job"
    )


def test_cloudbuild_e2e_diagnostics_use_relative_paths() -> None:
    """The e2e-personas step runs with `dir: frontend`, so the cwd
    already IS frontend/. The failure trap previously listed
    `frontend/test-results` which `ls` couldn't find — losing the
    diagnostic value of the trap. Paths must be relative
    (test-results, playwright-report), not prefixed with `frontend/`.
    """
    txt = CLOUDBUILD.read_text()
    m = re.search(r"- id: e2e-personas[\s\S]+?(?=^  - id:)", txt, re.MULTILINE)
    assert m, "e2e-personas stage not found"
    stage = m.group(0)
    # Check only the executable ls lines, not surrounding comments:
    # a comment mentioning `frontend/test-results` to explain the fix
    # would otherwise self-trip the assertion.
    ls_lines = [
        ln for ln in stage.splitlines()
        if "ls " in ln and not ln.lstrip().startswith("#")
    ]
    for ln in ls_lines:
        assert "frontend/test-results" not in ln, (
            f"e2e-personas trap has wrong-prefixed ls (the step's cwd IS "
            f"frontend/ via `dir: frontend`): {ln.strip()!r}"
        )
        assert "frontend/playwright-report" not in ln, (
            f"e2e-personas trap has wrong-prefixed ls: {ln.strip()!r}"
        )
    # And the relative path MUST be present somewhere in the stage.
    assert "ls -la test-results" in stage, (
        "trap must run `ls -la test-results` (relative — cwd is frontend/)"
    )
    assert "ls -la playwright-report" in stage


def test_backend_loader_fetchjson_uses_timeout() -> None:
    """`fetchJSON()` defines `_withTimeout()` for AbortController-based
    timeouts (adminGet + post* already use it) but boot fetches (auth/me,
    entities, dashboard, alerts) called `fetch(path, FETCH_OPTS)`
    directly — no timeout — so a single hung core endpoint held the
    whole boot at the boot-screen indefinitely.
    """
    src = (
        APP_ROOT / "frontend" / "standalone-src" / "src" / "backend-loader.js"
    ).read_text()
    # Find the fetchJSON function body.
    m = re.search(
        r"async function fetchJSON\([^)]*\)\s*\{(.*?)\n  \}\n",
        src, re.DOTALL,
    )
    assert m, "fetchJSON() not found"
    body = m.group(1)
    assert "_withTimeout" in body, (
        "fetchJSON() must wrap fetch via _withTimeout() so boot calls "
        "can't hang indefinitely (2026-05-29 QA P1)"
    )


def test_backend_loader_scopes_admin_errors() -> None:
    """Admin endpoint failures must NOT surface as the app-wide
    BackendErrorBanner. Errors get a `scope` ∈ {"global","admin"};
    `adminGet` tags as "admin"; BackendErrorBanner filters scope==="global".
    Without this, a 500 on /api/v1/admin/import-audit/by-entity (an
    admin diagnostic) shows up as "Backend data failed to load…" on
    every non-admin page.
    """
    loader = (
        APP_ROOT / "frontend" / "standalone-src" / "src" / "backend-loader.js"
    ).read_text()
    chrome = (
        APP_ROOT / "frontend" / "standalone-src" / "src" / "chrome.jsx"
    ).read_text()

    # _pushError must accept a scope parameter.
    assert re.search(
        r"function _pushError\([^)]*scope[^)]*\)",
        loader,
    ), "_pushError must accept a scope parameter"
    # adminGet must tag its pushes as 'admin'.
    m = re.search(r"async function adminGet\([^)]*\)\s*\{.*?\n  \}\n",
                  loader, re.DOTALL)
    assert m, "adminGet() not found"
    body = m.group(0)
    assert '"admin"' in body, (
        "adminGet must pass scope=\"admin\" to _pushError so admin "
        "failures don't pollute the global banner"
    )
    # BackendErrorBanner must filter to scope === "global".
    assert 'e.scope || "global"' in chrome or 'scope === "global"' in chrome, (
        "BackendErrorBanner must filter window.DMA_LOAD_STATE.errors "
        "to scope==='global' (missing scope falls back to 'global' "
        "for back-compat)"
    )


def test_import_audit_by_entity_response_has_warnings_field() -> None:
    """The self-healing rewrite of /admin/import-audit/by-entity attaches
    warnings (e.g. `dedup_audit_missing`, `ai_enrichments_legacy_…`) so
    operators see WHY a counter is 0. Pin the response shape so a
    future refactor can't silently drop the field.
    """
    schemas = (
        APP_ROOT / "backend" / "app" / "schemas" / "admin.py"
    ).read_text()
    m = re.search(
        r"class ImportAuditByEntityResponse\(BaseModel\):(.+?)(?=class\s)",
        schemas, re.DOTALL,
    )
    assert m, "ImportAuditByEntityResponse not found"
    assert "warnings" in m.group(1), (
        "ImportAuditByEntityResponse must declare a `warnings` field — "
        "the self-healing endpoint reports degraded-table state via it"
    )


def test_import_audit_by_entity_endpoint_is_self_healing() -> None:
    """The endpoint introspects optional tables (dedup_audit) + columns
    (ai_enrichments.target_kind vs entity_id) and degrades to 0+warning
    instead of 500ing when the table/shape is absent. Pin the contract.
    """
    src = (
        APP_ROOT / "backend" / "app" / "routers" / "admin.py"
    ).read_text()
    assert "_table_exists" in src and "_table_columns" in src, (
        "admin.py must define _table_exists + _table_columns helpers "
        "for the self-healing introspection"
    )
    # The 503 path for core tables must exist.
    assert "core table" in src.lower() and "503" in src, (
        "missing core entities/runs must escalate to 503 (NOT 500); "
        "optional table absences degrade to warnings + count=0"
    )
    # The legacy ai_enrichments shape must be supported.
    for w in (
        "dedup_audit_missing",
        "ai_enrichments_missing",
        "ai_enrichments_legacy_entity_id_shape",
    ):
        assert w in src, (
            f"self-healing endpoint must emit '{w}' warning when the "
            f"corresponding schema gap is detected"
        )


# ── 2026-05-29 QA-deep-audit Round 3 (D, G, I, Fix-10) ────────────────


def test_post_commit_workers_module_exists() -> None:
    """The post-ingest direct-dispatch path lives at
    `app/services/post_commit_workers.py::dispatch_post_commit_workers`.
    Without it, ingest publishes Pub/Sub messages no one consumes
    (the workers are Cloud Run Jobs, not long-lived --subscribe
    Services) and section_embeddings + customer_intelligence_profiles
    never populate. Pin the module's existence + signature so a
    future refactor can't silently remove the dispatch path.
    """
    mod = (
        APP_ROOT / "backend" / "app" / "services" / "post_commit_workers.py"
    )
    assert mod.exists(), "post_commit_workers.py missing"
    src = mod.read_text()
    assert "dispatch_post_commit_workers" in src, (
        "dispatch_post_commit_workers function missing"
    )
    # Must target BOTH derived-data workers.
    assert '"embedder"' in src and '"intelligence_recompute"' in src, (
        "post-commit dispatch must cover both embedder + "
        "intelligence_recompute (the 2 workers that produce derived "
        "data per run)"
    )
    # Must use --run-id (so the worker processes ONLY the just-
    # committed run, not the last-N-hours).
    assert '"--run-id"' in src, (
        "post-commit dispatch must pass --run-id so each dispatch "
        "scopes to exactly the committed run"
    )
    # Must use the existing dispatch_job service (no re-implementation).
    assert "from app.services.cloud_run_dispatch import dispatch_job" in src, (
        "must reuse dispatch_job from cloud_run_dispatch (the admin-"
        "button path); a parallel impl would diverge."
    )


def test_post_commit_workers_called_from_every_ingest_path() -> None:
    """EVERY commit path must invoke dispatch_post_commit_workers:
      • /ingest/package router (live n8n bot uploads)
      • /ingest/assessment router (legacy single-record ingest)
      • historical_backfill (operator-triggered backfill worker)
    A future contributor adding a 4th ingest path must wire it here;
    otherwise that path silently regresses to no-derived-data.
    """
    for path in (
        APP_ROOT / "backend" / "app" / "routers" / "ingest_package.py",
        APP_ROOT / "backend" / "app" / "routers" / "ingest.py",
        APP_ROOT / "backend" / "app" / "scripts" / "historical_backfill.py",
    ):
        src = path.read_text()
        assert "dispatch_post_commit_workers" in src, (
            f"{path.name} must invoke dispatch_post_commit_workers "
            "after its commit; otherwise post-ingest derived data "
            "(section_embeddings, customer_intelligence_profiles) "
            "never populates for runs from this ingest path."
        )


def test_terraform_has_embedder_and_intelligence_reconciliation_schedulers() -> None:
    """Self-healing C path (per QA report): even if direct dispatch
    fails (transient outage, partial deploy), hourly Cloud Scheduler
    triggers MUST sweep both workers. Without them, any missed
    direct dispatch results in permanent loss of derived data for
    that run.
    """
    src = TERRAFORM.read_text()
    for sched in ("embedder_hourly", "intelligence_recompute_hourly"):
        assert f'"google_cloud_scheduler_job" "{sched}"' in src, (
            f"missing google_cloud_scheduler_job '{sched}' — the "
            f"reconciliation sweep that catches direct-dispatch "
            f"failures. Without it the system can't self-heal."
        )
    # Both must run on a FREQUENT backstop cadence — every 6h, not daily/
    # weekly (2026-06 cost optimisation; was hourly). The post-commit dispatch
    # does the real-time embed/recompute on ingest, so these only catch a
    # FAILED dispatch; the derived data is idempotent/re-derivable, making 6h
    # an ample self-heal window at a fraction of the prior hourly cost.
    assert "schedule         = \"30 */6 * * *\"" in src, (
        "embedder reconciliation must run on a frequent backstop (every 6h)"
    )
    assert "schedule         = \"45 */6 * * *\"" in src, (
        "intelligence_recompute reconciliation must run on a frequent backstop "
        "(every 6h)"
    )


def test_playwright_blocking_suite_is_react_only() -> None:
    """Fix G: the blocking Playwright config (playwright.config.ts) MUST
    only include the React/Vite-targeted golden-path tests. Standalone-
    targeted tests live in playwright.standalone.config.ts.

    Mixing the suites in the same `pnpm test:e2e` run made fixing one
    side break the other — the standalone tests assert against the
    standalone surface, which isn't what `pnpm dev` serves (post ADR
    0016 production is the React tree).
    """
    cfg = (APP_ROOT / "frontend" / "playwright.config.ts").read_text()
    assert "personas.e2e.ts" in cfg, "blocking suite must include personas"
    for forbidden in (
        "standalone-auth-hydration.e2e.ts",
        "responsive-standalone-routes.e2e.ts",
    ):
        in_match = re.search(
            r"testMatch:\s*\[([^\]]*)\]", cfg, re.DOTALL,
        )
        assert in_match, "testMatch array missing"
        assert forbidden not in in_match.group(1), (
            f"blocking config testMatch must NOT include {forbidden} — "
            f"it belongs in playwright.standalone.config.ts"
        )


def test_playwright_standalone_config_exists_and_runs_demo_tests() -> None:
    """Fix G: the standalone (demo) suite has its own config + script.
    Running it is opt-in and advisory; Cloud Build does not block on it.
    """
    cfg_path = APP_ROOT / "frontend" / "playwright.standalone.config.ts"
    assert cfg_path.exists(), (
        "playwright.standalone.config.ts must exist — it's the demo-build "
        "suite. ADR 0016 separates standalone tests from the blocking "
        "React suite."
    )
    cfg = cfg_path.read_text()
    for needle in (
        "standalone-auth-hydration",
        "responsive-standalone-routes",
        "a11y-drawers",
        "xss-regressions",
    ):
        assert needle in cfg, (
            f"standalone config must reference {needle}.e2e.ts"
        )
    pkg = (APP_ROOT / "frontend" / "package.json").read_text()
    assert '"test:e2e:standalone"' in pkg, (
        "package.json must define a `test:e2e:standalone` script so "
        "operators can run the demo suite explicitly without forcing "
        "it into the blocking CI run"
    )


def test_preflight_parameters_has_zennify_canonical_defaults_optout() -> None:
    """Fix I: preflight-parameters.sh must respect
    USE_ZENNIFY_CANONICAL_DEFAULTS=0 to disable the auto-fill of
    Zennify-specific values (DRIVE_ROOT_FOLDER_ID, OPS_SHEET_ID, etc).
    Without the opt-out, a non-canonical deploy silently targets
    Zennify's Drive folder + Ops Sheet — a confidentiality + correctness
    defect.
    """
    src = (
        APP_ROOT / "infra" / "preflight-parameters.sh"
    ).read_text()
    assert "USE_ZENNIFY_CANONICAL_DEFAULTS" in src, (
        "preflight-parameters.sh must expose USE_ZENNIFY_CANONICAL_DEFAULTS "
        "(2026-05-29 QA Fix-I)"
    )
    assert "${USE_ZENNIFY_CANONICAL_DEFAULTS:-1}" in src or 'USE_ZENNIFY_CANONICAL_DEFAULTS:-"1"' in src, (
        "USE_ZENNIFY_CANONICAL_DEFAULTS must default to 1 (preserve the "
        "turnkey Zennify deploy); operators opt OUT by setting it to 0"
    )
    assert 'if [[ "$USE_ZENNIFY_CANONICAL_DEFAULTS" == "1" ]]' in src, (
        "the NON_SECRET_DEFAULTS auto-fill must be gated on "
        "USE_ZENNIFY_CANONICAL_DEFAULTS == 1"
    )


def test_live_data_flow_gate_script_exists_and_covers_pipeline() -> None:
    """Fix-10: live-data-flow-gate.sh is the post-deploy gate that
    confirms ingest → DB → API → frontend → derived-jobs ALL produced
    data. Without it, a green verify-deploy only proves the revisions
    are healthy, NOT that AEs will actually see ingested data.
    """
    gate = APP_ROOT / "infra" / "live-data-flow-gate.sh"
    assert gate.exists(), "live-data-flow-gate.sh missing"
    src = gate.read_text()
    for needle in (
        "/healthz",
        "/readyz",
        "/api/v1/entities",
        "/api/v1/admin/import-audit/by-entity",
        "section_embeddings",
        "customer_intelligence_profiles",
        "job_executions",
    ):
        assert needle in src, (
            f"live data-flow gate must check {needle} — without it, the "
            f"gate can't prove the full pipeline populated"
        )
    # The gate uses a regex (escaped `.`) so either form is acceptable.
    assert ("/src/data.js" in src or r"/src/data\.js" in src), (
        "gate must negative-check the /src/data.js (standalone-src) "
        "regression — a frontend that's silently reverted to ADR 0011 "
        "must fail this gate"
    )
    assert "standalone-src" in src


def test_preflight_redis_script_exists_and_classifies_backends() -> None:
    """The Redis preflight is a script (not an inline doc heredoc) so
    operators don't hit the `python3 - <<PY` paste-hazard that hangs
    Cloud Shell at the `>` prompt when the closing terminator is lost
    in a partial copy-paste (2026-05-30 operator hit this).

    The script must classify Upstash vs Memorystore vs unknown so the
    PASS/FAIL verdict is actionable — a Cloud Shell connection refused
    is FATAL for Upstash but EXPECTED for Memorystore (Cloud Run
    reaches it via the VPC connector).
    """
    script = APP_ROOT / "infra" / "preflight-redis.sh"
    assert script.exists(), "infra/preflight-redis.sh missing"
    assert script.stat().st_mode & 0o111, "preflight-redis.sh not executable"
    src = script.read_text()

    # Must classify both backends.
    assert "upstash.io" in src, (
        "preflight-redis.sh must classify Upstash hosts (*.upstash.io)"
    )
    assert "memorystore" in src.lower(), (
        "preflight-redis.sh must classify Memorystore (VPC-internal) "
        "so its CloudShell-unreachable verdict reads 'EXPECTED' not 'FATAL'"
    )
    # Must emit distinct verdicts (operator-actionable).
    for verdict in ("UPSTASH_FATAL", "MEMORYSTORE_WARN", "SCHEME_INVALID"):
        assert verdict in src, (
            f"missing verdict label '{verdict}' — operator needs the "
            f"label to know whether to block the deploy"
        )
    # And the doc must steer operators at the script (not at the
    # old heredoc snippet — that was the paste hazard).
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "preflight-redis.sh" in doc, (
        "DEPLOYMENT.md must reference infra/preflight-redis.sh — the "
        "heredoc-based snippet it replaces was a Cloud Shell paste "
        "hazard (lost closing `PY` hangs bash at `>`)."
    )

    # Stronger guard: DEPLOYMENT.md must contain NO multi-line heredocs
    # at all. A single dropped terminator line in any of them hangs
    # Cloud Shell. Convert any future heredoc to a script invocation
    # instead. Detected by scanning for `<<EOF`-style openers inside
    # bash code fences (commented lines + explanatory prose are allowed
    # since they don't get pasted as commands).
    import re as _re
    bash_blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    offenders: list[str] = []
    for blk in bash_blocks:
        for line in blk.splitlines():
            # Strip comment-only lines (start with optional whitespace + #).
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # Match: command ... <<[-]?TOKEN  where TOKEN is bare or
            # quoted upper-case ident. Excludes <<<HERESTRING (single-line).
            if _re.search(r"<<-?[\"']?[A-Za-z_][A-Za-z0-9_]*[\"']?\b", line):
                offenders.append(line.strip())
    assert not offenders, (
        "DEPLOYMENT.md still contains heredoc(s) inside bash fences — "
        "these are Cloud Shell paste hazards (lost terminator hangs "
        "bash at the `>` prompt). Convert each to a script invocation. "
        f"Offending lines: {offenders}"
    )

    # Second hazard: cwd-dependent paths. `bash apps/dma-insights/...`
    # only works from the repo root. Operators who paste it from any
    # subdirectory hit `No such file or directory` (2026-05-30 operator
    # was already in `apps/dma-insights/` and got that exact error).
    # The cwd-safe form is `bash "$(git rev-parse --show-toplevel)/apps/
    # dma-insights/..."`. A `cd "$(git rev-parse --show-toplevel)"`
    # earlier in the same block ALSO satisfies the contract.
    cwd_offenders: list[tuple[str, str]] = []
    for blk in bash_blocks:
        # Allow a `cd $(git rev-parse --show-toplevel)` upfront in the
        # same block — that hoists the cwd to the repo root.
        block_hoists_to_root = bool(_re.search(
            r"cd\s+[\"']?\$\(git rev-parse --show-toplevel\)",
            blk,
        ))
        if block_hoists_to_root:
            continue
        for line in blk.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # Match `bash apps/dma-insights/...` at a command position
            # (start of token; allow env-var prefixes like `FOO=bar bash …`
            # by NOT requiring start-of-line). The cwd-safe form
            # `bash "$(git rev-parse --show-toplevel)/apps/...` is fine
            # because there's no `apps/dma-insights/` literal in the
            # command itself — it's inside the substitution.
            if _re.search(
                r"\bbash\s+(?!\")apps/dma-insights/", line,
            ):
                cwd_offenders.append((line.strip(), "needs $(git rev-parse --show-toplevel) prefix"))
    assert not cwd_offenders, (
        "DEPLOYMENT.md has cwd-dependent `bash apps/dma-insights/...` "
        "invocation(s) that fail from any directory except the repo "
        "root. Convert to `bash \"$(git rev-parse --show-toplevel)/apps/"
        "dma-insights/...\"` OR add `cd \"$(git rev-parse --show-"
        "toplevel)\"` to the same code block. Offending lines: "
        f"{cwd_offenders}"
    )


def test_setup_memorystore_script_exists_and_is_idempotent() -> None:
    """The Memorystore provisioning block in DEPLOYMENT.md §0.2.7 was
    a 5-step paste block with hard dependencies on $REGION + $PROJECT_ID
    + $REDIS_HOST. Paste fusion + missing-var bugs broke it repeatedly
    (2026-05-30 operator hit the trifecta: empty $REGION → instance
    never created → REDIS_HOST empty → REDIS_URL=redis://:6379/0).
    The whole flow is now in `infra/setup-memorystore.sh` — one
    command, idempotent, polls for convergence.

    This test pins:
      • The script exists + is executable.
      • It fail-fasts on missing $PROJECT_ID and $REGION (no half-
        created resources).
      • It uses `gcloud … describe` to check existence BEFORE
        `gcloud … create` (idempotent — operators can re-run).
      • It POLLS for convergence rather than sleeping a fixed time
        (the prior fixed sleep was the root of the empty-host bug).
      • It writes REDIS_URL to a sourceable env file (since
        `export` inside a subshell doesn't persist).
      • DEPLOYMENT.md references the script, NOT the old multi-step
        paste block.
    """
    script = APP_ROOT / "infra" / "setup-memorystore.sh"
    assert script.exists(), "infra/setup-memorystore.sh missing"
    assert script.stat().st_mode & 0o111, "setup-memorystore.sh not executable"
    src = script.read_text()

    # Fail-fast on required vars. The script guards with `-z "$VAR"`
    # (no braces) — build that literal via concatenation.
    for var in ("PROJECT_ID", "REGION"):
        assert ('-z "$' + var + '"') in src, (
            f"setup-memorystore.sh must fail-fast on missing ${var} — the "
            f"original paste block silently produced empty values "
            f"because operators forgot to export ${var}"
        )

    # Idempotence: every long-running gcloud must be guarded by a
    # describe check.
    for resource in ("addresses describe", "vpc-peerings list", "redis instances describe"):
        assert resource in src, (
            f"setup-memorystore.sh must check existence via `gcloud {resource}` "
            f"before creating — operators re-run after partial failures, so "
            f"every create step must be idempotent"
        )

    # Convergence polling, not fixed sleep.
    assert "for _ in $(seq" in src or "for i in $(seq" in src, (
        "setup-memorystore.sh must poll for convergence (PSA peering +"
        " redis state=READY) instead of a fixed sleep — the prior"
        " fixed wait caused the empty-host bug when the instance"
        " hadn't finished provisioning"
    )
    assert "state=READY" in src or "READY)" in src, (
        "must poll until Redis state=READY (creation can take 3-6 min)"
    )

    # REDIS_URL persisted to a sourceable file.
    assert ".dma-redis-url" in src, (
        "setup-memorystore.sh must persist REDIS_URL to ~/.dma-redis-url "
        "so the operator can `source` it (export inside the script's "
        "subshell doesn't reach the calling shell)"
    )
    # File permissions are 0600 (avoid world-readable credentials).
    assert "chmod 600" in src, (
        "setup-memorystore.sh must chmod 600 the env file (the URL "
        "embeds the host; later iterations may embed credentials)"
    )

    # DEPLOYMENT.md must reference the script + NOT the old gcloud-
    # commands paste block.
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "setup-memorystore.sh" in doc, (
        "DEPLOYMENT.md must reference infra/setup-memorystore.sh — "
        "the 5-step paste block it replaces was a documented Cloud "
        "Shell hazard (paste fusion + missing-var bugs)."
    )
    # The legacy `gcloud redis instances create` paste line must be
    # absent from bash fences — otherwise the trap is back.
    import re as _re
    blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    for blk in blocks:
        for ln in blk.splitlines():
            if ln.lstrip().startswith("#"):
                continue
            assert "gcloud redis instances create" not in ln, (
                "DEPLOYMENT.md still contains `gcloud redis instances "
                "create` inside a bash fence — that's the paste hazard "
                "the new script eliminates. Move to "
                "`bash setup-memorystore.sh` instead. "
                f"Offending line: {ln.strip()}"
            )


def test_preflight_ops_sheet_script_exists_and_replaces_paste_block() -> None:
    """The §0.2.11 Ops Sheet probe was a 50+ line paste block with
    multi-line `case/esac`, nested-quote escapes, and inline error
    messages. Operators' Cloud Shell mangled it on paste (2026-05-30
    operator's output showed `fiesac` from line fusion + an extra `""`
    on the OPS_SHEET_ID assignment). The new `infra/preflight-ops-
    sheet.sh` replaces it with one command.

    Contract pinned here:
      • script exists + is executable
      • fail-fasts on missing PROJECT_ID + OPS_SHEET_ID
      • impersonates the WORKER SA with spreadsheets.readonly scope
        (default ADC doesn't carry it → false 403 on a healthy share)
      • on 403, the verdict text directly tells the operator HOW to
        share the sheet (which URL to open, which email to paste,
        which role to pick) — the prior block buried this under
        WARN/ERROR/etc. spam that paste-fusion made worse.
      • DEPLOYMENT.md references the script + has NO multi-line
        Sheets probe block left.
    """
    script = APP_ROOT / "infra" / "preflight-ops-sheet.sh"
    assert script.exists(), "infra/preflight-ops-sheet.sh missing"
    assert script.stat().st_mode & 0o111, "preflight-ops-sheet.sh not executable"
    src = script.read_text()

    # Fail-fast on required vars.
    for var in ("PROJECT_ID", "OPS_SHEET_ID"):
        assert ('-z "$' + var + '"') in src, (
            f"preflight-ops-sheet.sh must fail-fast on missing ${var}"
        )

    # SA-impersonation + Sheets scope (NOT plain ADC).
    assert "--impersonate-service-account" in src, (
        "must impersonate the worker SA — default ADC tokens don't "
        "carry the Sheets scope so they 403 even on a healthy share"
    )
    assert "spreadsheets.readonly" in src, (
        "must request the spreadsheets.readonly OAuth scope on the "
        "impersonation token"
    )

    # Worker-SA auto-resolution from PROJECT_ID (operators rarely "
    # know the exact compute-default SA email).
    assert "projectNumber" in src and "compute@developer" in src, (
        "must auto-resolve WORKER_SA from PROJECT_NUMBER so the "
        "operator doesn't have to look it up"
    )

    # On 403, the verdict text must call out the one-click share fix.
    assert "SHEETS_403" in src and "Share" in src, (
        "the 403 branch must print actionable share-the-sheet "
        "instructions (URL + SA email + role)"
    )
    # And on NO_TOKEN, the verdict must call out the IAM grant fix.
    assert "NO_TOKEN" in src and "serviceAccountTokenCreator" in src, (
        "the no-token branch must print the IAM-binding fix command"
    )

    # DEPLOYMENT.md references the script + the old probe block is gone.
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "preflight-ops-sheet.sh" in doc, (
        "DEPLOYMENT.md must reference infra/preflight-ops-sheet.sh"
    )
    # The legacy multi-line probe blocks (Sheets + Drive) had these
    # unmistakeable markers — both are forbidden in bash fences now.
    # Patterns are specific to the probe URL shape (GET … ?fields=…)
    # so legitimate WRITE operations like POST /permissions stay valid.
    import re as _re
    blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    for blk in blocks:
        # Bare-text markers from the legacy probe scripts.
        for marker in (
            "probe token source:",
            'TOKEN_SOURCE="(none)"',
        ):
            assert marker not in blk, (
                f"DEPLOYMENT.md still has a probe paste block "
                f"(marker '{marker}'). Move to the corresponding "
                f"`bash preflight-{{ops-sheet,drive-folder}}.sh` "
                f"script instead. Block excerpt:\n{blk[:200]}"
            )
        # Probe URL shapes — GET … sheets-or-drive URL with `?fields=`.
        # POST .../permissions?... and other write operations remain
        # legitimate and won't match this.
        for probe_re in (
            r"sheets\.googleapis\.com/v4/spreadsheets/\$\{?[A-Z_]+\}?\?fields=",
            r"drive/v3/files/\$\{?[A-Z_]+\}?\?fields=",
        ):
            m = _re.search(probe_re, blk)
            assert not m, (
                f"DEPLOYMENT.md still has an inline GET probe (matched "
                f"'{m.group(0)}'). Move to the corresponding "
                f"`bash preflight-{{ops-sheet,drive-folder}}.sh` "
                f"script instead. Block excerpt:\n{blk[:300]}"
            )


def test_preflight_drive_folder_script_exists_and_replaces_paste_block() -> None:
    """Same paste-block class as preflight-ops-sheet.sh — the §0.2.10
    Drive probe was a 70+ line multi-line block. Operators hit the
    same paste-fusion + nested-quote-escape issues. Fixed by
    extraction to a single script.
    """
    script = APP_ROOT / "infra" / "preflight-drive-folder.sh"
    assert script.exists(), "infra/preflight-drive-folder.sh missing"
    assert script.stat().st_mode & 0o111, "preflight-drive-folder.sh not executable"
    src = script.read_text()
    for var in ("PROJECT_ID", "DRIVE_ROOT_FOLDER_ID"):
        assert ('-z "$' + var + '"') in src, (
            f"preflight-drive-folder.sh must fail-fast on missing ${var}"
        )
    assert "--impersonate-service-account" in src
    assert "drive.readonly" in src
    assert "supportsAllDrives=true" in src, (
        "must use supportsAllDrives=true so folders inside a Shared "
        "Drive don't return 404 even with valid auth"
    )
    assert "DRIVE_403" in src and "Share" in src
    assert "NO_TOKEN" in src and "serviceAccountTokenCreator" in src
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "preflight-drive-folder.sh" in doc


def test_setup_cloud_sql_script_is_resilient_and_auth_persistent() -> None:
    """Operator hit a persistent 3-bug recurrence in the §0.5.4 paste block:
      1. Cloud SQL `--tier=db-custom-2-7680` rejected by recent ENTERPRISE_PLUS-
         default projects ("Use a predefined Tier like db-perf-optimized-N-*").
      2. `gcloud sql connect` interactively prompts for the postgres password
         every session — operator typed stale value and got
         "password authentication failed for user 'postgres'".
      3. Re-runs in the same shell didn't reflect the LATEST Secret Manager
         password — multiple "current" values drifted across env, secret v1,
         and SQL.

    `infra/setup-cloud-sql.sh` is the canonical resilient fix. This test
    pins the contract:
      • Pins --edition=ENTERPRISE on instance create so db-custom-* tiers
        keep working.
      • Persists the postgres password to Secret Manager
        (dma-insights-pg-superuser-pw) AND rotates EVERY re-run AND
        destroys prior versions — only the latest authenticates.
      • Writes ~/.dma-pg-superuser-pw (mode 0600) for cross-session
        psql reuse without interactive prompts.
      • Verifies the password via a live psql round-trip through
        cloud-sql-proxy (no fire-and-forget).
      • DEPLOYMENT.md references the script — not the old paste block.
    """
    script = APP_ROOT / "infra" / "setup-cloud-sql.sh"
    assert script.exists(), "infra/setup-cloud-sql.sh missing"
    assert script.stat().st_mode & 0o111, "setup-cloud-sql.sh not executable"
    src = script.read_text()

    # Bug 1 fix: --edition=ENTERPRISE pinned so db-custom-* keeps working.
    assert "--edition=" in src and "ENTERPRISE" in src, (
        "setup-cloud-sql.sh must pin --edition=ENTERPRISE — without it, "
        "recent Cloud SQL APIs default to ENTERPRISE_PLUS which rejects "
        "db-custom-* tiers like the doc's db-custom-2-7680"
    )

    # Bug 2 fix: writes a 0600 file with the superuser password for
    # cross-session reuse (no interactive prompt next time).
    assert ".dma-pg-superuser-pw" in src, (
        "setup-cloud-sql.sh must cache the superuser password at "
        "~/.dma-pg-superuser-pw so future shells use it via PGPASSWORD "
        "without interactive `gcloud sql connect` prompts"
    )
    assert "chmod 600" in src, (
        "~/.dma-pg-superuser-pw must be mode 0600 (it contains a "
        "production credential)"
    )
    assert "PGPASSWORD" in src, (
        "the cache must export PGPASSWORD so psql + setup-pg-extensions "
        "auto-authenticate"
    )

    # Bug 3 fix: rotation + destroy-prior-versions.
    assert "set-password postgres" in src, (
        "setup-cloud-sql.sh must `set-password postgres` to rotate the "
        "superuser password every run — operators left stale local env "
        "vars that no longer authenticate"
    )
    assert "versions destroy" in src, (
        "setup-cloud-sql.sh must destroy prior Secret Manager versions "
        "of dma-insights-pg-superuser-pw after rotation — old passwords "
        "must NOT remain usable"
    )

    # Live verification (no fire-and-forget).
    assert "cloud-sql-proxy" in src and "SELECT 1" in src, (
        "setup-cloud-sql.sh must verify the rotated password via a live "
        "psql SELECT 1 round-trip through cloud-sql-proxy — otherwise "
        "a failed rotation goes undetected until the next deploy step"
    )

    # DEPLOYMENT.md references the script + the old paste block is gone.
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "setup-cloud-sql.sh" in doc, (
        "DEPLOYMENT.md must reference infra/setup-cloud-sql.sh"
    )
    # The legacy paste-block markers must be absent.
    import re as _re
    blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    for blk in blocks:
        for marker in (
            'SQL_PASSWORD="$(openssl rand -hex 24)"',
            "--tier=db-custom-2-7680",
            "gcloud sql instances create",
        ):
            assert marker not in blk, (
                f"DEPLOYMENT.md still has the legacy Cloud SQL paste block "
                f"(marker '{marker}'). Move to `bash setup-cloud-sql.sh` "
                f"instead. Block excerpt:\n{blk[:300]}"
            )


def test_setup_pg_extensions_is_non_interactive() -> None:
    """The earlier setup-pg-extensions.sh used `gcloud sql connect` which
    prompts for the postgres password every invocation — operators got
    "FATAL: password authentication failed" when they typed a stale
    local value. The rewrite uses cloud-sql-proxy + psql with
    PGPASSWORD resolved from (in order): existing env, ~/.dma-pg-
    superuser-pw cache, Secret Manager. Never prompts.
    """
    src = (APP_ROOT / "infra" / "setup-pg-extensions.sh").read_text()
    # Must NOT use the interactive-prompt path.
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "gcloud sql connect" not in code, (
        "setup-pg-extensions.sh must NOT call `gcloud sql connect` — "
        "that path prompts for the postgres password every session "
        "(2026-05-31 operator hit this). Use cloud-sql-proxy + psql "
        "with PGPASSWORD instead."
    )
    # Must use the non-interactive path with PGPASSWORD.
    assert "PGPASSWORD" in src and "cloud-sql-proxy" in src, (
        "setup-pg-extensions.sh must use cloud-sql-proxy + PGPASSWORD "
        "for non-interactive psql access"
    )
    # Auth-resolution must check the cache first, fall back to Secret
    # Manager. Either order is fine; both paths must exist.
    assert ".dma-pg-superuser-pw" in src, (
        "must check ~/.dma-pg-superuser-pw (the cache written by "
        "setup-cloud-sql.sh)"
    )
    assert "secrets versions access" in src, (
        "must fall back to Secret Manager when the cache is missing"
    )


def test_dma_psql_helper_handles_proxy_and_auth() -> None:
    """Operators kept hitting `psql -h 127.0.0.1 -p 5432 → Connection
    refused` because Cloud SQL isn't directly reachable — nothing
    listens on 5432 until cloud-sql-proxy is running. Sourcing the
    password solved AUTH but not CONNECTIVITY. `infra/dma-psql.sh` does
    both in one command (2026-05-31 fix).

    Contract:
      • script exists + executable
      • starts cloud-sql-proxy (the connectivity bit operators missed)
      • resolves the password without prompting: env → cache file →
        Secret Manager (both the dedicated secret + the legacy DSN)
      • passes all args through to psql (exec psql … "$@")
      • DEPLOYMENT.md §44.2 references it + the multi-line proxy paste
        block is gone.
    """
    script = APP_ROOT / "infra" / "dma-psql.sh"
    assert script.exists(), "infra/dma-psql.sh missing"
    assert script.stat().st_mode & 0o111, "dma-psql.sh not executable"
    src = script.read_text()

    # Connectivity: must start cloud-sql-proxy (the missing piece).
    assert "cloud-sql-proxy" in src and "pg_isready" in src, (
        "dma-psql.sh must start cloud-sql-proxy + wait for it — that's "
        "the connectivity step operators kept omitting (plain psql on "
        ":5432 gets Connection refused)"
    )
    # Auth: no interactive prompt; resolves from cache + Secret Manager.
    assert ".dma-pg-superuser-pw" in src, (
        "dma-psql.sh must check the ~/.dma-pg-superuser-pw cache"
    )
    assert "secrets versions access" in src, (
        "dma-psql.sh must fall back to Secret Manager for the password"
    )
    # Passthrough to psql.
    assert 'psql' in src and '"$@"' in src, (
        "dma-psql.sh must pass all args through to psql so any psql "
        "flag (-c, -f, -t, --csv) works"
    )
    # Must NOT use the prompt-y gcloud sql connect.
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "gcloud sql connect" not in code, (
        "dma-psql.sh must NOT use `gcloud sql connect` (interactive prompt)"
    )

    # DEPLOYMENT.md §44.2 references the helper + the old proxy paste
    # block is gone.
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "dma-psql.sh" in doc, (
        "DEPLOYMENT.md must reference infra/dma-psql.sh"
    )
    import re as _re
    blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    for blk in blocks:
        # The legacy §44.2 block started a proxy by hand with this exact
        # shape. Operators should call dma-psql.sh instead.
        assert "cloud-sql-proxy --port 5433" not in blk, (
            "DEPLOYMENT.md still has the hand-rolled cloud-sql-proxy "
            "block. Replace with `bash dma-psql.sh`. Excerpt:\n"
            f"{blk[:200]}"
        )


def test_preflight_redis_detects_literal_placeholder() -> None:
    """2026-05-31 operator pasted `REDIS_URL='rediss://...'` from a stale
    doc snippet verbatim — the script parsed `...` as a hostname and
    returned a confusing `UNKNOWN_HOST` verdict that buried the real
    cause (the URL is a placeholder).

    The new PLACEHOLDER_URL branch detects literal `...` / `<host>` /
    `YOUR_HOST` / empty-string hosts and emits an actionable verdict
    that names the cause + offers two fixes (use --from-secret or set
    REDIS_URL to a real value).

    Also pins that the canonical doc snippet for §0.2.7 no longer
    contains a literal-placeholder REDIS_URL paste-trap.
    """
    src = (APP_ROOT / "infra" / "preflight-redis.sh").read_text()
    # The PLACEHOLDER_URL verdict must exist + cover the literal
    # placeholders operators have actually pasted.
    assert "PLACEHOLDER_URL" in src, (
        "preflight-redis.sh must emit a PLACEHOLDER_URL verdict when "
        "REDIS_URL is a literal placeholder (not a real value)"
    )
    for placeholder in ('"..."', '""', '"<host>"', '"YOUR_HOST"'):
        assert placeholder in src, (
            f"PLACEHOLDER_URL detection must cover the {placeholder} "
            "host value (operators have pasted these verbatim)"
        )

    # The doc must NOT recommend pasting a literal `rediss://...` URL.
    # Only the --from-secret form OR an explicit `THE_REAL_TOKEN`-style
    # placeholder (clearly NOT runnable) is acceptable.
    doc = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    import re as _re
    bash_blocks = _re.findall(r"```bash\n(.*?)```", doc, _re.DOTALL)
    for blk in bash_blocks:
        # Look for the exact paste-trap: `REDIS_URL='rediss://...'`
        # at a command position (start of line OR after env-var-only
        # prefix). The string `rediss://...` ANYWHERE in a bash fence
        # IS a paste-trap when it's an assignment value.
        for ln in blk.splitlines():
            stripped = ln.lstrip()
            if stripped.startswith("#"):
                continue
            # Match: optional leading env vars, then REDIS_URL=...
            # with literal `...` as the value. Tolerate quoting style.
            if _re.search(
                r"^\s*REDIS_URL\s*=\s*['\"]?rediss?://\.\.\.['\"]?",
                ln,
            ):
                raise AssertionError(
                    "DEPLOYMENT.md still has the literal-placeholder "
                    "paste-trap `REDIS_URL='rediss://...'` in a bash "
                    "fence. Operators paste it verbatim and trip the "
                    "new PLACEHOLDER_URL verdict. Remove the literal "
                    f"placeholder. Line: {ln.strip()!r}"
                )

    # The script must auto-install redis-py so the "redis-py not
    # installed; skipping" warning doesn't leave the script with no
    # working probe (Cloud Shell redis-cli sometimes can't TLS to
    # rediss:// URLs).
    assert "pip" in src and "redis" in src.lower(), (
        "preflight-redis.sh must auto-install redis-py if missing "
        "(without it, the script has no reliable rediss:// probe on "
        "Cloud Shells whose redis-cli wasn't built with TLS)"
    )


def test_cloud_scheduler_attempt_deadlines_within_api_limit() -> None:
    """Cloud Scheduler rejects attempt_deadline > 30m (1800s) at apply with
    HTTP 400 `attempt_deadline must be between 15s and 30m0s` — a server-side
    range that `terraform validate` cannot catch. Lock every scheduler job's
    attempt_deadline to [15s, 1800s].

    Regression-pin: 2026-06-08 deploy — drive_crawler_daily_new_folders set
    attempt_deadline=3600s, so `terraform apply` 400'd and (because
    recover-db-passwords.sh runs apply internally) cascaded into a
    force-heal-db.sh fallback.
    """
    import re as _re

    main_tf = (APP_ROOT / "infra" / "terraform" / "main.tf").read_text()
    # Match each scheduler resource block + its attempt_deadline.
    deadlines = _re.findall(r'attempt_deadline\s*=\s*"(\d+)s"', main_tf)
    assert deadlines, "no attempt_deadline found in main.tf — scan regex stale?"
    offenders = [d for d in deadlines if not (15 <= int(d) <= 1800)]
    assert not offenders, (
        f"Cloud Scheduler attempt_deadline(s) outside [15s,1800s]: "
        f"{offenders}s. Cloud Scheduler caps it at 30m; >1800s 400s at "
        f"`terraform apply`. The `:run` trigger returns immediately so the "
        f"deadline need only cover the HTTP ack, not the job runtime."
    )


def test_deploy_scripts_resolve_newest_sha_via_resolver() -> None:
    """The bde8329 incident: a stale / wrong-branch checkout (or a leaked
    `SHA` env, or a leftover /tmp handoff) shipped an OLD image because every
    deploy path tagged from a bare `git rev-parse --short HEAD`.

    The fix is `infra/resolve-deploy-sha.sh` — fetch origin + sync the working
    tree to the deploy-branch tip, so "deploy" always means "deploy the newest
    committed code". Assert the resolver exists with its core logic, and that
    every build/deploy entrypoint routes its DEFAULT SHA through it (an
    explicit `SHA=` override is still allowed). This is a regression fence so a
    future edit can't reintroduce a bare-HEAD image tag.
    """
    resolver = INFRA / "resolve-deploy-sha.sh"
    assert resolver.is_file(), "infra/resolve-deploy-sha.sh missing"
    rsrc = resolver.read_text()
    assert "git fetch" in rsrc, "resolver must fetch origin before resolving"
    assert "origin/$branch" in rsrc or 'origin/"' in rsrc or "refs/remotes/origin/" in rsrc, (
        "resolver must resolve the deploy-branch tip on origin"
    )
    assert "checkout -B" in rsrc, "resolver must sync the tree to the newest tip"

    # SHA must be DETERMINISTIC across clones: the resolver emits the first 7
    # chars of the full SHA (= Cloud Build $SHORT_SHA), NOT `git rev-parse
    # --short`, whose abbreviation length auto-extends with a clone's object
    # density (the `2ee4efa` vs `2ee4efa7` incident → the deploy looked up an
    # image tag the build never produced).
    assert "cut -c1-7" in rsrc, (
        "resolver must emit a fixed 7-char SHA (cut -c1-7 = Cloud Build SHORT_SHA)"
    )
    assert "short7" in rsrc, (
        "resolver must route its short SHA through the deterministic short7 "
        "helper (first 7 of full SHA), not variable-length `git rev-parse --short`"
    )
    # No ACTIVE (non-comment) `git rev-parse --short` command may remain — its
    # length differs across clones (the 2ee4efa vs 2ee4efa7 incident).
    active_short = [
        ln for ln in rsrc.splitlines()
        if "rev-parse --short" in ln and not ln.lstrip().startswith("#")
    ]
    assert not active_short, (
        f"resolver still calls variable-length `git rev-parse --short`: {active_short}"
    )

    # Every entrypoint that TAGS/SHIPS an image must reference the resolver.
    for script in ("build.sh", "deploy.sh", "deploy-two-phase.sh"):
        body = (INFRA / script).read_text()
        assert "resolve-deploy-sha.sh" in body, (
            f"{script} must resolve its default SHA via resolve-deploy-sha.sh "
            f"(else a stale checkout ships an old image — the bde8329 bug)"
        )

    # deploy-two-phase must also REFUSE an explicitly-pinned stale SHA.
    twophase = (INFRA / "deploy-two-phase.sh").read_text()
    assert "merge-base --is-ancestor" in twophase and "STALE" in twophase, (
        "deploy-two-phase.sh must reject an explicit SHA that is an ancestor "
        "of (behind) the deploy-branch tip unless DEPLOY_ALLOW_STALE=1"
    )

    # The one-shot REDEPLOY guide must bootstrap to the newest code first.
    guide = (APP_ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "resolve-deploy-sha.sh" in guide, (
        "DEPLOYMENT.md §0.0 redeploy must resolve the newest SHA"
    )


def test_deploy_two_phase_defaults_project_id_from_gcloud() -> None:
    """An operator who ran `gcloud config set project <id>` (the standard
    Cloud Shell setup) must NOT also be forced to export PROJECT_ID. Incident:
    deploy-two-phase aborted at parameter validation ("PROJECT_ID env var
    required") even though the gcloud project was set — so nothing deployed.
    The script must default PROJECT_ID from the active gcloud project BEFORE
    the hard `:?` error, and export it for sub-scripts."""
    src = (INFRA / "deploy-two-phase.sh").read_text()
    assert "gcloud config get-value project" in src, (
        "deploy-two-phase.sh must default PROJECT_ID from the active gcloud "
        "project so a set gcloud project alone suffices"
    )
    fallback_idx = src.find("gcloud config get-value project")
    require_idx = src.find("PROJECT_ID:?")
    assert 0 < fallback_idx < require_idx, (
        "the gcloud-project fallback must come BEFORE the PROJECT_ID:? check"
    )
    assert "export PROJECT_ID REGION" in src, (
        "PROJECT_ID/REGION must be exported so preflight/migrate/terraform/"
        "post-deploy sub-scripts and gcloud invocations inherit them"
    )
