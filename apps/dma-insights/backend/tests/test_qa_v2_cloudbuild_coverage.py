"""Batch 13 — pin the cloudbuild "live DB always" production-readiness contract.

Per the operator mandate (2026-06): "In deployment the DB should
always be live. This is production and it is required." — every
pytest invocation in cloudbuild.yaml MUST run against a real
pgvector sidecar. NO stub DSN. NO skips on missing DB.

The production-ready cloudbuild structure (Batch 13):

  - **Stage 1 backend-tests** (python:3.12-slim): offline alembic
    --sql + ruff. NO pytest here (no live DB available).
  - **Stage 3 backend-tests-live-pg**: pgvector sidecar + seed_ci
    (6 canonical fixtures) → runs the FULL pytest sweep, --ignore
    only for tests that need the 113-package corpus (which seed_ci
    can't satisfy).
  - **Stage 10 qa-gates**: pgvector sidecar + historical_backfill
    (113-package corpus) → runs the 4 production harnesses + the
    corpus-dependent qa_v2 pytest (adversarial, reingest scenarios,
    backfill skip-path, language rewrite real-corpus sample).

If a future PR re-adds pytest to stage 1, OR orphans a qa_v2 test
from the live-DB stages, THIS contract test FAILs immediately.
"""
from __future__ import annotations

import re
from pathlib import Path

CLOUDBUILD = (
    Path(__file__).resolve().parents[2]
    / "infra" / "cloudbuild.yaml"
)
BACKEND_DOCKERFILE = (
    Path(__file__).resolve().parents[2]
    / "infra" / "docker" / "backend.Dockerfile"
)

# The backend image installs its Python deps with
# `pip install --prefix=/install` and exposes them to the interpreter
# ONLY via ENV PYTHONPATH=<this path> — they are NOT in the interpreter's
# default site-packages. See infra/docker/backend.Dockerfile.
IMAGE_DEPS_PATH = "/install/lib/python3.12/site-packages"


def test_cloudbuild_yaml_exists() -> None:
    assert CLOUDBUILD.is_file(), f"cloudbuild.yaml missing at {CLOUDBUILD}"


# ── qa_v2 test files ↔ cloudbuild stages ─────────────────────────────


def _qa_gates_block() -> str:
    content = CLOUDBUILD.read_text()
    start = content.index("- id: qa-gates")
    # qa-gates is the last stage; capture to end of file or next options block.
    end = content.find("\noptions:", start)
    if end == -1:
        end = len(content)
    return content[start:end]


def _live_pg_block() -> str:
    content = CLOUDBUILD.read_text()
    start = content.index("- id: backend-tests-live-pg")
    end = content.index("- id: frontend-tests")
    return content[start:end]


def test_qa_v2_self_healing_learning_runs_in_live_pg_stage() -> None:
    """6-fixture sidecar is enough for the self-healing+learning audit
    (corpus_health just asserts >=1 run per entity). Stage 3 runs the
    full pytest sweep against the sidecar; verify the self-healing
    test file ISN'T --ignored."""
    block = _live_pg_block()
    assert "tests/" in block, "live-pg stage missing pytest tests/"
    assert "--ignore=tests/test_qa_v2_self_healing_learning.py" not in block, (
        "qa_v2 self-healing test --ignored in live-pg stage; would never run in CI"
    )


def test_qa_v2_adversarial_resilience_runs_in_qa_gates() -> None:
    """Needs 100+ entities + anchor display_ids (Acuity, AMH, Ameris)
    that only exist in the full 113-package corpus. Stage 10 qa-gates
    runs it explicitly against the historical_backfill-seeded sidecar."""
    block = _qa_gates_block()
    assert "tests/test_qa_v2_adversarial_resilience.py" in block, (
        "qa_v2 adversarial test missing from qa-gates stage; would never "
        "run in CI (--ignored in live-pg stage because it needs full corpus)"
    )


def test_qa_v2_reingest_scenarios_runs_in_qa_gates() -> None:
    """Uses Acuity Insurance fixture from the 113-package corpus."""
    block = _qa_gates_block()
    assert "tests/test_qa_v2_reingest_scenarios.py" in block, (
        "qa_v2 reingest scenarios test missing from qa-gates stage"
    )


def test_backfill_skip_path_integration_runs_in_qa_gates() -> None:
    """Asserts manifest round-trip across >= 50 packages (Batch 8
    integration test); needs the full corpus."""
    block = _qa_gates_block()
    assert "tests/test_backfill_skip_path_integration.py" in block, (
        "backfill skip-path integration test missing from qa-gates stage"
    )


def test_language_rewrite_real_corpus_runs_in_qa_gates() -> None:
    """The language-rewrite test that queries 100 rationale strings
    from the live DB needs the full corpus to satisfy that floor."""
    block = _qa_gates_block()
    assert (
        "tests/test_language_rewrite.py::test_rewriter_reduces_violation_count_on_real_corpus_sample"
        in block
    ), (
        "language-rewrite real-corpus test missing from qa-gates stage; "
        "needs 100+ rationale strings from the seeded DB"
    )


# ── qa-gates stage shape ──────────────────────────────────────────────


def test_qa_gates_runs_all_5_production_harnesses() -> None:
    """The deploy-blocking harnesses. The 4 text-surface harnesses PLUS
    qa_attribution_fidelity — the gate that makes CI OBSERVE the AI layer
    (tier liveness + cross-encoder calibration + attribution fidelity),
    passed with --require-ai because the image bakes both NLP models."""
    content = CLOUDBUILD.read_text()
    expected = (
        "qa_render_validation",
        "qa_adversarial_resilience",
        "qa_rendered_language_audit",
        "qa_self_healing_learning_audit",
        "qa_attribution_fidelity",
    )
    missing = [h for h in expected if h not in content]
    assert not missing, (
        f"qa-gates stage missing harness(es): {missing}. The 5 "
        f"production-grade harnesses MUST be deploy-blocking in CI."
    )
    assert "qa_attribution_fidelity --require-ai" in content, (
        "qa_attribution_fidelity must run with --require-ai in qa-gates so a "
        "silently-cold/mis-baked NLP tier hard-fails the deploy."
    )


def test_qa_gates_seeds_full_corpus() -> None:
    """The qa-gates stage MUST call historical_backfill to seed the
    113-package corpus BEFORE running the harnesses + high-corpus
    pytest; otherwise the harness contracts can't be satisfied."""
    content = CLOUDBUILD.read_text()
    assert "historical_backfill" in content, (
        "qa-gates stage doesn't seed the corpus; harnesses would FAIL"
    )
    assert "dma_packages_batches" in content, (
        "qa-gates stage doesn't reference the canonical fixture corpus"
    )


def test_qa_gates_has_skipped_guard() -> None:
    """Per operator mandate "no skips, every test in prod": the
    qa-gates stage must FAIL if any test SKIPS."""
    content = CLOUDBUILD.read_text()
    # The grep -q SKIPPED + exit guard appears in the high-corpus
    # pytest block. Without it, a conditionally-skipped test would
    # silently pass cloudbuild.
    assert "grep -q SKIPPED" in content, (
        "qa-gates stage missing SKIPPED-grep guard; tests could "
        "silently skip without failing the deploy."
    )


# ── backend-tests stage shape ─────────────────────────────────────────


def test_backend_tests_stage_does_not_run_pytest() -> None:
    """Stage 1 backend-tests runs in python:3.12-slim with a STUB
    DSN (postgresql+psycopg://x/y for offline alembic --sql).
    Per operator mandate "in deployment the DB should always be
    live", pytest MUST NOT run in this stage — every test that
    touches DB code would crash with ConnectionRefusedError.

    The fix (Batch 13): pytest invocation moved to stage 3
    backend-tests-live-pg which has a real pgvector sidecar.
    """
    content = CLOUDBUILD.read_text()
    # Locate the backend-tests stage block (between `id: backend-tests`
    # and `id: backend-build`).
    stage_start = content.index("- id: backend-tests")
    stage_end = content.index("- id: backend-build")
    stage_block = content[stage_start:stage_end]
    # The stage must NOT contain `python -m pytest tests/`. Substring
    # `pytest` may appear in pip-install lines; we target the actual
    # invocation form.
    assert "python -m pytest tests/" not in stage_block, (
        "backend-tests stage runs pytest against the stub DSN; this "
        "breaks the operator mandate 'in deployment the DB should "
        "always be live'. Move pytest to backend-tests-live-pg."
    )


def test_backend_tests_live_pg_runs_full_pytest_sweep() -> None:
    """Stage 3 backend-tests-live-pg has the pgvector sidecar +
    seed_ci. It MUST run the FULL pytest sweep — not a hardcoded
    subset of test file names. Otherwise newly added tests aren't
    exercised in CI (orphan-test risk)."""
    content = CLOUDBUILD.read_text()
    stage_start = content.index("- id: backend-tests-live-pg")
    stage_end = content.index("- id: frontend-tests")
    stage_block = content[stage_start:stage_end]
    assert "python -m pytest tests/" in stage_block, (
        "backend-tests-live-pg stage doesn't run full pytest sweep; "
        "newly added tests would be orphaned in CI."
    )


# ── image-deps importability contract (2026-06-08 regression lock) ────
#
# The backend image installs deps under `--prefix=/install` and the
# interpreter only finds them via ENV PYTHONPATH=IMAGE_DEPS_PATH. Any
# `docker run -e PYTHONPATH=...` against that image OVERRIDES the image
# env, so the override MUST re-include IMAGE_DEPS_PATH or every
# `import sqlalchemy` inside the container dies with
# `ModuleNotFoundError: No module named 'sqlalchemy'`. That was the
# 2026-06-08 deploy blocker: backend-tests-live-pg passed
# `-e PYTHONPATH=/workspace/repo/backend:/workspace/repo`, dropping the
# deps path, so `python -m app.scripts.seed_ci` failed before any test
# ran. qa-gates had the same latent bug (`-e PYTHONPATH=.`).


def _pythonpath_overrides(block: str) -> list[str]:
    """Return every real `docker run -e PYTHONPATH=...` value in a stage
    block, skipping comment/doc lines so prose mentioning the flag does
    not register as an override."""
    vals: list[str] = []
    for line in block.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = re.search(r'-e\s+"?PYTHONPATH=([^"\s\\]+)', line)
        if m:
            vals.append(m.group(1))
    return vals


def test_backend_dockerfile_exposes_deps_via_pythonpath() -> None:
    """Lock the assumption the cloudbuild PYTHONPATH overrides depend on:
    backend.Dockerfile installs deps under --prefix=/install and exposes
    them via PYTHONPATH=IMAGE_DEPS_PATH. If this changes, the override
    literals in cloudbuild.yaml must change in lockstep."""
    dockerfile = BACKEND_DOCKERFILE.read_text()
    assert "--prefix=/install" in dockerfile, (
        "backend.Dockerfile no longer installs deps under --prefix=/install; "
        "update IMAGE_DEPS_PATH + the cloudbuild PYTHONPATH overrides."
    )
    assert IMAGE_DEPS_PATH in dockerfile, (
        f"backend.Dockerfile no longer exposes deps via {IMAGE_DEPS_PATH}; "
        "the cloudbuild PYTHONPATH overrides would silently drop the deps "
        "path and every container import would fail."
    )


def test_live_pg_stage_keeps_image_deps_on_pythonpath() -> None:
    """backend-tests-live-pg overrides PYTHONPATH so host source wins for
    `import app`; the override MUST still include IMAGE_DEPS_PATH or
    seed_ci/pytest die with ModuleNotFoundError on sqlalchemy
    (2026-06-08 deploy blocker)."""
    overrides = _pythonpath_overrides(_live_pg_block())
    assert overrides, (
        "backend-tests-live-pg sets no `-e PYTHONPATH=` override; expected "
        "one that prepends the host repo and appends IMAGE_DEPS_PATH."
    )
    for val in overrides:
        assert IMAGE_DEPS_PATH in val, (
            f"backend-tests-live-pg PYTHONPATH override {val!r} drops the "
            f"image deps path {IMAGE_DEPS_PATH}; image-installed deps "
            f"(sqlalchemy, fastapi, ...) become unimportable in the container."
        )


def test_qa_gates_stage_keeps_image_deps_on_pythonpath() -> None:
    """qa-gates runs the backend image with an overridden PYTHONPATH; it
    MUST keep IMAGE_DEPS_PATH so alembic / historical_backfill / the
    harnesses can import sqlalchemy."""
    overrides = _pythonpath_overrides(_qa_gates_block())
    assert overrides, "qa-gates sets no `-e PYTHONPATH=` override"
    for val in overrides:
        assert IMAGE_DEPS_PATH in val, (
            f"qa-gates PYTHONPATH override {val!r} drops the image deps path "
            f"{IMAGE_DEPS_PATH}; image-installed deps become unimportable."
        )


# ── e2e-personas: visual-suite resilience regression locks ───────────
# The production-surface visual suite launches a browser whose build is
# pinned by `@playwright/test` in package.json, NOT by the jammy image
# tag. When the runner is newer than the image's baked browser, EVERY
# launch fails ("chromium_headless_shell-... missing") ⇒ 84/84 red
# before a pixel is compared. `playwright install` heals that at
# runtime, so it is load-bearing — these tests stop it (and the
# self-healing wrapper) from being silently dropped again.


def _e2e_personas_block() -> str:
    content = CLOUDBUILD.read_text()
    start = content.index("- id: e2e-personas")
    end = content.index("- id: frontend-image-smoke")
    return content[start:end]


def test_e2e_personas_installs_matching_browser() -> None:
    """`playwright install` MUST run in e2e-personas — the pinned image's
    baked browser does not match the package.json runner, so omitting it
    fails the visual + persona suites 84/84 at browser launch."""
    block = _e2e_personas_block()
    assert "playwright install" in block, (
        "e2e-personas no longer runs `playwright install`; the image's "
        "baked chromium will not match @playwright/test and every browser "
        "launch fails before any assertion runs."
    )


def test_e2e_personas_browser_install_has_retry() -> None:
    """The browser install pulls ~113 MB; a single network blip must not
    sink the whole stage. It is wrapped in a bounded retry loop."""
    block = _e2e_personas_block()
    install_idx = block.index("pnpm exec playwright install")
    window = block[max(0, install_idx - 200):install_idx + 60]
    assert "for attempt" in window or "retry" in window.lower(), (
        "playwright install in e2e-personas is not wrapped in a retry; a "
        "transient download failure will fail the deploy."
    )


def test_e2e_personas_runs_self_healing_production_visual() -> None:
    """BOTH visual suites run through the self-healing wrapper: the
    production-surface suite as a resilient monitor (no STRICT flag),
    and the standalone suite as the BLOCKING contract via STRICT_VISUAL=1.

    Why the standalone suite is NOT a bare `pnpm test:visual:standalone`
    (2026-06-10): pixel baselines are environment-pinned — PNGs captured
    outside the pinned jammy container render with a different system
    font stack and can never converge at maxDiffPixelRatio 0.02, so the
    bare invocation produced a RECURRENT 84/84 failure. The wrapper makes
    CI the capture environment of record (regenerate in-container →
    re-compare → upload refreshed baselines), while STRICT_VISUAL=1
    preserves blocking semantics for true non-determinism/breakage."""
    block = _e2e_personas_block()
    assert "visual-selfheal.sh playwright.visual.config.ts" in block, (
        "e2e-personas no longer invokes the self-healing wrapper for the "
        "production-surface visual monitor."
    )
    assert "test:visual:standalone" in block, (
        "e2e-personas dropped the BLOCKING standalone visual contract."
    )
    assert (
        "STRICT_VISUAL=1" in block
        and "visual-selfheal.sh playwright.visual.standalone.config.ts" in block
    ), (
        "e2e-personas must run the standalone visual contract through "
        "scripts/visual-selfheal.sh with STRICT_VISUAL=1 — a bare "
        "`pnpm test:visual:standalone` re-introduces the recurrent "
        "84-baseline cross-environment failure (baselines can only be "
        "captured deterministically inside the pinned jammy container)."
    )
    # The blocking gate must NOT be soft-failed: the monitor's
    # `|| echo ::warning::` escape hatch is for the non-blocking suite only.
    standalone_idx = block.index(
        "visual-selfheal.sh playwright.visual.standalone.config.ts"
    )
    tail = block[standalone_idx : standalone_idx + 200]
    assert "||" not in tail.splitlines()[0], (
        "the STRICT_VISUAL standalone self-heal invocation is soft-failed "
        "with `||` — it must remain a hard gate."
    )


def test_visual_selfheal_script_exists_and_is_resilient() -> None:
    """The self-heal wrapper must exist and honour the resilience
    contract: it heals the browser, regenerates+re-compares on drift,
    and exposes STRICT_VISUAL to opt back into hard-fail."""
    script = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "scripts"
        / "visual-selfheal.sh"
    )
    assert script.is_file(), f"visual-selfheal.sh missing at {script}"
    body = script.read_text()
    for token in ("playwright install", "--update-snapshots", "STRICT_VISUAL", "ARTIFACT_DIR"):
        assert token in body, f"visual-selfheal.sh missing resilience token {token!r}"
