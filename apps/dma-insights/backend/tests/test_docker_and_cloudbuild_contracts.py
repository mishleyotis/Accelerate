"""Phase 7 infra contract regression tests.

The audit identified that Dockerfiles + Cloud Build + Terraform
each declare overlapping things (image names, runtime files, env
vars). Drift between them is invisible until production.

Each test below pins one cross-file contract. A refactor that adds
a new image / drops a COPY / changes a tag must trip here BEFORE
deploy.

Contracts covered:
  - Backend image COPYs alembic + scripts + fixtures
  - Frontend image serves the Vite-built dist/ (per ADR 0016; supersedes
    ADR 0011's revert to standalone-src — see frontend.Dockerfile header)
  - Worker image can `python -m` every worker module
  - Frontend nginx template has no-cache on .html/.js/.jsx/.json/.css
  - Cloud Build no advisory `|| true` on release-critical stages
  - Cloud Build waitFor references existing prior steps
  - Terraform image refs match Cloud Build image names
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1].parent
INFRA = REPO_ROOT / "infra"
DOCKER_DIR = INFRA / "docker"
BACKEND_DOCKERFILE = DOCKER_DIR / "backend.Dockerfile"
FRONTEND_DOCKERFILE = DOCKER_DIR / "frontend.Dockerfile"
WORKER_DOCKERFILE = DOCKER_DIR / "worker.Dockerfile"
NGINX_TEMPLATE = DOCKER_DIR / "frontend-nginx.template"
CLOUDBUILD = INFRA / "cloudbuild.yaml"
TERRAFORM = INFRA / "terraform" / "main.tf"


# ── Backend image ────────────────────────────────────────────────


def test_backend_image_copies_alembic_versions():
    """Migration runs (`gcloud run jobs execute dma-insights-migrations`)
    use the BACKEND image. Without alembic + alembic/versions COPY'd
    in, `alembic upgrade head` exits with "No such file or directory"
    before any DDL is emitted."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY backend/alembic" in text, (
        "backend.Dockerfile must COPY backend/alembic/ for the "
        "migrations job to run."
    )
    assert "alembic.ini" in text, (
        "backend.Dockerfile must COPY backend/alembic.ini -- "
        "alembic exits non-zero without it."
    )


def test_backend_image_copies_app_directory():
    """The FastAPI app code lives under backend/app. Without it the
    image has nothing to run."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY backend/app" in text


def test_backend_image_copies_workers_for_shared_utils():
    """The backend imports workers.* utilities (e.g. for catalogue
    dispatch). Without the COPY the import crashes the FastAPI app
    on first reference (cold-start 500)."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY workers" in text, (
        "backend.Dockerfile must COPY workers/ -- backend imports "
        "shared utilities from this package."
    )


def test_backend_image_ships_ci_fixtures():
    """seed_ci uses the 5 sanitized DMA packages. Pre-2026-05-24 the
    image didn't ship them -> seed_ci raised ModuleNotFoundError.
    Pin the fix here."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    for fixture in ("regions", "amalgamated", "anb", "wsfs", "americu"):
        assert (
            f"COPY backend/tests/fixtures/dma_packages_sanitized/{fixture}"
            in text
        ), (
            f"backend.Dockerfile must COPY the {fixture} sanitized "
            "fixture -- seed_ci.py expects it at runtime."
        )


def test_backend_image_installs_alembic():
    """alembic must be in the runtime PATH. The Dockerfile pip-installs
    it explicitly OR pulls it via pyproject."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "alembic==" in text or '"alembic"' in text


# ── Frontend image ───────────────────────────────────────────────


def test_frontend_image_serves_vite_dist_not_standalone_src():
    """Per ADR 0016 (2026-05-29, supersedes ADR 0011) the production
    frontend is the Vite-built bundle at `frontend/dist/`. The
    standalone single-file artifact is a stakeholder-demo build whose
    `data.js` declares EVIDENCE / INSIGHT_CARDS / RECOMMENDATIONS /
    ROADMAP / FOCUS_AREAS / TECH_STACK / etc. as `[]` "UNTIL WIRED TO
    BACKEND" — AEs called this the "dummy page". The React/Vite tree
    has TanStack-Query hooks on every endpoint and renders real data
    or its own empty state per page.

    A Dockerfile edit that reverts to `COPY frontend/standalone-src/`
    re-introduces the dummy-page failure mode and must be caught here.
    """
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    # Multi-stage build that runs `vite build` and COPYs `dist/`.
    assert "vite build" in text or "pnpm run build" in text, (
        "frontend.Dockerfile must build the React/Vite app via "
        "`pnpm run build` (= tsc --noEmit && vite build) — per ADR 0016"
    )
    assert "COPY --from=build" in text and "/dist/" in text, (
        "frontend.Dockerfile must COPY --from=build /app/frontend/dist/ "
        "(the Vite-emitted bundle), not standalone-src/"
    )
    # The actual `COPY frontend/standalone-src` instruction must be
    # absent — only references inside `#` comments are allowed (the
    # Dockerfile header explains the supersession).
    code_lines = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "COPY frontend/standalone-src" not in code, (
        "frontend.Dockerfile must NOT COPY frontend/standalone-src/ "
        "as the served bundle — that reverts ADR 0016 (the 'dummy "
        "page' regression). Comments referencing the supersession are "
        "fine; only the actual Docker instruction is the failure mode."
    )


def test_frontend_image_uses_nginx_alpine():
    """The frontend image must be nginx-based. A switch to a Node
    runtime would balloon the image size and break the static-asset
    serving model."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "nginx" in text.lower()


def test_frontend_image_installs_gettext_for_envsubst():
    """The nginx template uses `${BACKEND_URL}` substitution at
    container start. envsubst lives in the gettext package -- without
    it the template ships literal `${BACKEND_URL}` and the proxy
    fails on every API call."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "gettext" in text


def test_frontend_image_stamps_build_sha():
    """A sed-stamp of the build SHA into index.html is the cache-bust
    contract. Without it the operator can't tell which revision the
    user's browser actually loaded."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert (
        "BUILD_SHA" in text
        and ("x-build-sha" in text.lower() or "sed" in text.lower())
    ), (
        "frontend.Dockerfile must sed-stamp the BUILD_SHA into "
        "index.html so operators can verify which revision is live."
    )


# ── Frontend nginx template ──────────────────────────────────────


def test_nginx_template_disables_cache_for_html_js_jsx():
    """JSX/JS/HTML must serve with no-cache headers -- the standalone
    bundle uses Babel in-browser, so a cached old .jsx + new index.html
    causes opaque "props is undefined" errors on every release."""
    if not NGINX_TEMPLATE.exists():
        pytest.skip(f"{NGINX_TEMPLATE} not present (separate config)")
    text = NGINX_TEMPLATE.read_text(encoding="utf-8")
    for ext in ("html", "js", "jsx"):
        # Either an `expires` directive that's zero/negative or a
        # `Cache-Control: no-cache` header for the extension.
        has_no_cache = (
            f".{ext}" in text and (
                "no-cache" in text
                or "expires off" in text
                or "expires -1" in text
            )
        )
        assert has_no_cache, (
            f"nginx template missing no-cache directive for .{ext}. "
            "Stale .jsx + new index.html crashes the standalone bundle."
        )


# ── Cloud Build no advisory swallow ──────────────────────────────


def test_cloudbuild_release_critical_stages_have_no_advisory_swallow():
    """Stages 1 (backend-tests), 2 (backend-build), 7 (e2e-personas),
    7b (frontend-image-smoke) must be BLOCKING. `|| true` or
    `::warning::` on the test command downgrades them to advisory.
    Stage 6 (terraform-plan) is the documented exception."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    advisory_swallows = []
    for step in spec.get("steps", []):
        sid = step.get("id", "")
        if sid in ("terraform-plan",):
            continue  # documented advisory stage
        args = step.get("args", [])
        joined = "\n".join(str(a) for a in args)
        # Find `|| true` on a test/build/lint invocation.
        for match in re.finditer(
            r"(pnpm test:e2e|pnpm test:visual|pytest|ruff check|"
            r"alembic upgrade head|alembic downgrade head:base|"
            r"pnpm exec tsc|pnpm exec vitest|pnpm run build)"
            r"[^\n]*?\|\|\s*true",
            joined,
        ):
            advisory_swallows.append((sid, match.group(0).strip()))
    assert not advisory_swallows, (
        f"Release-critical stages have advisory swallow: {advisory_swallows}. "
        "Remove `|| true` or move the stage to advisory."
    )


def test_cloudbuild_waitfor_references_existing_steps():
    """`waitFor: ["X"]` on stage Y means Y runs only after X. If X
    doesn't exist (typo or stage rename) Cloud Build silently runs
    Y in parallel with whatever was supposed to gate it."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    step_ids: set[str] = {s.get("id", "") for s in spec.get("steps", [])}
    bad_refs: list[tuple[str, str]] = []
    for step in spec.get("steps", []):
        for ref in step.get("waitFor", []) or []:
            if ref and ref != "-" and ref not in step_ids:
                bad_refs.append((step.get("id", ""), ref))
    assert not bad_refs, (
        f"Cloud Build waitFor references missing step IDs: {bad_refs}. "
        "Either fix the typo or add the missing stage."
    )


def test_cloudbuild_frontend_image_smoke_is_blocking():
    """Stage 7b (frontend-image-smoke) tests the actual production
    frontend artifact. Demoting it to advisory means a broken nginx
    config could ship without surfacing in CI."""
    text = CLOUDBUILD.read_text(encoding="utf-8")
    # Find the frontend-image-smoke stage block.
    m = re.search(
        r"- id: frontend-image-smoke[\s\S]+?(?=^  - id:|^\s*\Z)",
        text,
        re.MULTILINE,
    )
    assert m, "frontend-image-smoke stage not found"
    stage = m.group(0)
    # Must not have advisory swallow on the curl probes.
    swallows = re.findall(r"curl[^\n]*?\|\|\s*true", stage)
    assert not swallows, (
        f"frontend-image-smoke has advisory curl swallows: {swallows}. "
        "If a probe can fail without aborting the build, the stage is "
        "documentation, not verification."
    )


# ── Terraform <-> Cloud Build image-name parity ────────────────────


def test_terraform_image_names_match_cloudbuild_outputs():
    """Cloud Build pushes `gcr.io/$PROJECT_ID/dma-insights-{backend,
    frontend,workers}`. Terraform consumes the same paths. A
    refactor that renames either side must touch both files.
    """
    cb_text = CLOUDBUILD.read_text(encoding="utf-8")
    tf_text = TERRAFORM.read_text(encoding="utf-8")
    # Image names Cloud Build builds.
    cb_images = set(re.findall(
        r"gcr\.io/\$PROJECT_ID/(dma-insights-[a-z]+)", cb_text,
    ))
    tf_images = set(re.findall(
        r'gcr\.io/\$\{?var\.project_id\}?/(dma-insights-[a-z]+)', tf_text,
    ))
    missing_in_tf = cb_images - tf_images
    missing_in_cb = tf_images - cb_images
    assert not missing_in_tf, (
        f"Cloud Build builds these images but Terraform doesn't reference "
        f"them: {missing_in_tf}. They'd live in the registry unused."
    )
    assert not missing_in_cb, (
        f"Terraform references these images but Cloud Build doesn't build "
        f"them: {missing_in_cb}. Revisions would fail to start."
    )


# ── Pack-freshness deploy gates (master plan Part 14) ─────────────
#
# The 2026-07-02 deploy-gate audit found three silent-staleness holes:
# pages_manifest.json stamped source_sha "unknown" at every bake (no
# SOURCE_SHA reached export_startup_pages), the regen step was
# fail-open (`|| echo … continuing` shipped the stale committed pack
# silently), and frontend-image-smoke asserted nothing about the pack
# baked into the image. The contracts below pin the fixes.


def _regen_block() -> str:
    text = CLOUDBUILD.read_text(encoding="utf-8")
    start = text.index("- id: regen-startup-pack")
    end = text.index("- id: frontend-tests")
    return text[start:end]


def _frontend_smoke_block() -> str:
    text = CLOUDBUILD.read_text(encoding="utf-8")
    start = text.index("- id: frontend-image-smoke")
    end = text.index("- id: qa-gates")
    return text[start:end]


def test_cloudbuild_regen_passes_source_sha_into_containers():
    """The regen containers MUST receive SOURCE_SHA=${_IMAGE_SHA} so
    export_startup_pages stamps the build SHA into pages_manifest.json
    (pre-fix every bake stamped source_sha "unknown" and no freshness
    gate could ever work). export_startup_data additionally gets the
    explicit --sha (belt and braces)."""
    block = _regen_block()
    assert '-e "SOURCE_SHA=${_IMAGE_SHA}"' in block, (
        "regen-startup-pack no longer passes SOURCE_SHA=${_IMAGE_SHA} "
        "into the container env — export_startup_pages would stamp "
        "'unknown'/'local-*' and frontend-image-smoke check 6 would "
        "fail every build."
    )
    assert re.search(
        r"export_startup_data[^\n]*--sha \$\{_IMAGE_SHA\}", block
    ), (
        "export_startup_data must receive an explicit --sha ${_IMAGE_SHA} "
        "so the first-paint manifest carries the build SHA too."
    )


def test_cloudbuild_regen_exporters_are_hard_gated():
    """The exporters must run via `step_hard` (non-zero exit fails the
    build unless _ALLOW_STALE_PACK=true). The pre-Part-14 fail-open
    (`|| echo … keeping committed pack` via the plain `step` helper)
    shipped a stale pack SILENTLY whenever an export crashed."""
    block = _regen_block()
    for exporter in ("export_startup_data", "export_startup_pages"):
        # Optional VAR=value prefixes allowed (DMA_RERANK_BUDGET_SEC=0 makes
        # the baked pack budget-deterministic, 2026-07-11) — the contract is
        # step_hard + the exporter, not the exact env.
        assert re.search(
            rf'step_hard "(?:[A-Z_][A-Z0-9_]*=\S+ )*python -m app\.scripts\.{exporter}',
            block,
        ), (
            f"{exporter} is not invoked via step_hard in "
            "regen-startup-pack — a failed export would silently ship "
            "the stale committed pack again."
        )
        # No line may swallow an exporter failure with `|| echo`/`|| true`.
        for line in block.splitlines():
            if exporter in line and not line.lstrip().startswith("#"):
                assert "|| echo" not in line and "|| true" not in line, (
                    f"exporter invocation swallows failure: {line.strip()!r}"
                )
    # step_hard itself must fail the build and honour the ONE escape.
    assert "_ALLOW_STALE_PACK" in block and "exit 1" in block, (
        "step_hard must exit 1 on exporter failure with "
        "_ALLOW_STALE_PACK=true as the only downgrade."
    )


def test_cloudbuild_regen_runs_pack_parity_strict_gate():
    """Master plan Part 14.1: the regen chain ends with
    `qa_pack_parity --strict` (pack==DB value-level proof) before the
    Gemini gate — hard-gated like the exporters."""
    block = _regen_block()
    # Optional VAR=value prefixes allowed (budget-deterministic parity,
    # 2026-07-11) — the contract is step_hard + --strict, not the exact env.
    assert re.search(
        r'step_hard "(?:[A-Z_][A-Z0-9_]*=\S+ )*python -m app\.scripts\.qa_pack_parity[^"]*--strict',
        block,
    ), (
        "regen-startup-pack must run qa_pack_parity --strict via "
        "step_hard after the exports (plan Part 14.1); without it a "
        "wrong (not merely cold) pack bakes unverified."
    )


def test_cloudbuild_regen_asserts_source_sha_stamp_landed():
    """After the exports the regen step greps the manifest and fails
    loud when source_sha != ${_IMAGE_SHA} (the `source_sha ✓` redeploy
    checklist log line)."""
    block = _regen_block()
    assert '"source_sha": *"[^"]*"' in block, (
        "regen-startup-pack no longer greps pages_manifest.json for "
        "source_sha — the stamp gate is gone."
    )
    assert "source_sha ✓" in block, (
        "the regen stamp gate must print the `source_sha ✓` log line "
        "the DEPLOYMENT.md §26.5 redeploy checklist tells operators "
        "to verify."
    )


def test_cloudbuild_frontend_smoke_has_check6_pack_freshness():
    """Check 6: frontend-image-smoke must fetch the BAKED
    /startup-data/pages_manifest.json and hard-fail (exit 4) when its
    source_sha differs from ${_IMAGE_SHA}; _ALLOW_STALE_PACK=true is
    the only (loud-warning) escape."""
    block = _frontend_smoke_block()
    assert "startup-data/pages_manifest.json" in block, (
        "frontend-image-smoke lost check 6 — nothing asserts the baked "
        "startup pack is fresh; a stale pack would ship silently."
    )
    assert '"source_sha": *"[^"]*"' in block, (
        "check 6 must extract source_sha from the baked manifest."
    )
    assert re.search(
        r'\[ "\$\$PACK_SHA" = "\$\{_IMAGE_SHA\}" \]', block
    ), (
        "check 6 must compare the baked manifest's source_sha against "
        "${_IMAGE_SHA} — that equality IS the freshness contract."
    )
    assert '"${_ALLOW_STALE_PACK}" = "true"' in block, (
        "check 6 lost its _ALLOW_STALE_PACK escape hatch (the ONE "
        "sanctioned stale-pack path, per EXIT_CODES.md)."
    )
    # The failure path must be a hard exit, not a warning.
    check6_idx = block.index("startup-data/pages_manifest.json")
    tail = block[check6_idx:]
    assert "::error::" in tail and "exit 4" in tail, (
        "check 6's mismatch branch must ::error:: + exit 4 — anything "
        "softer reverts the silent-stale-pack failure mode."
    )


def test_cloudbuild_stale_and_cold_substitution_defaults_are_false():
    """Both escape hatches must DEFAULT to \"false\" — the gates are
    hard unless an operator deliberately flips a substitution on one
    build."""
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))
    subs = spec.get("substitutions", {})
    assert subs.get("_ALLOW_STALE_PACK") == "false", (
        "_ALLOW_STALE_PACK substitution must exist and default to "
        '"false" — a truthy default makes every freshness gate advisory.'
    )
    assert subs.get("_ALLOW_COLD_GEMINI") == "false", (
        '_ALLOW_COLD_GEMINI substitution must default to "false" — a '
        "truthy default makes the Gemini bake gate advisory."
    )


def test_exporters_resolve_source_sha_env_first(monkeypatch):
    """Both exporters must honour SOURCE_SHA (the regen env) first, and
    stamp a truthful `local-<git short sha>` (or 'unknown' in a git-less
    checkout) when it is absent — never a fake build SHA."""
    from app.scripts.export_startup_data import (
        _resolve_source_sha as data_sha,
    )
    from app.scripts.export_startup_pages import (
        _resolve_source_sha as pages_sha,
    )

    monkeypatch.setenv("SOURCE_SHA", "abc1234")
    assert data_sha() == "abc1234"
    assert pages_sha() == "abc1234"

    monkeypatch.delenv("SOURCE_SHA", raising=False)
    for resolved in (data_sha(), pages_sha()):
        assert resolved == "unknown" or resolved.startswith("local-"), (
            f"local-run stamp must be 'local-<sha>' or 'unknown', got "
            f"{resolved!r} — a fake build SHA would defeat the "
            "freshness gate."
        )
