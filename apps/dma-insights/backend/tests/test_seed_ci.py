"""A4 — seed_ci.py tests.

Covers BOTH the dry-run path (always runs in CI without a DB) AND
the live-persist path (runs when SEED_CI_PG_URL points to a real
Postgres). State branches:

  - SEED_CI_PG_URL unset → only dry-run / argument-handling tests run
  - SEED_CI_PG_URL set   → full ingest + persistence-verification
                            tests fire end-to-end against the real DB

This is the user's "no dry runs that don't link to proper artifacts"
mandate — when a real DB is reachable, the test ASSERTS rows landed
in entities / runs / subcap_scores / evidence_index / evidence_run_links.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run seed_ci via the module entrypoint so we exercise the same
    path operators use in CI."""
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.seed_ci", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )


def test_dry_run_smoke_against_all_5_fixtures():
    """The canonical CI invocation. Must exit 0 and surface all 5."""
    r = _run("--dry-run", "--skip-db-check")
    assert r.returncode == 0, r.stderr
    from app.scripts.seed_ci import FIXTURE_NAMES as _FN
    for fixture in _FN:
        assert fixture in r.stdout, (
            f"fixture {fixture} not in dry-run output: {r.stdout}"
        )
    assert f"summary: ok={len(_FN)}" in r.stdout


def test_dry_run_only_filter_narrows_set():
    r = _run("--dry-run", "--skip-db-check", "--only", "regions,wsfs")
    assert r.returncode == 0, r.stderr
    assert "regions" in r.stdout
    assert "wsfs" in r.stdout
    assert "amalgamated" not in r.stdout
    assert "summary: ok=2" in r.stdout


def test_unknown_fixture_name_exits_1():
    r = _run("--dry-run", "--skip-db-check", "--only", "regions,fake-bank")
    assert r.returncode == 1
    assert "fake-bank" in r.stderr or "fake-bank" in r.stdout


def test_dry_run_extracts_correct_run_ids():
    """Locking the run_id contract: a parser change that breaks the
    run_id resolver shows up here as a test failure with the diff."""
    r = _run("--dry-run", "--skip-db-check")
    assert r.returncode == 0
    expected = {
        "regions": "DMA-ASM-REGIONS-20260518-0001",
        "amalgamated": "DMA-ASSESS-AMAL-20260428-0001",
        "anb": "DMA-ASM-ANB-20260420-0001",
        "wsfs": "DMA-ASM-WSFS-20260519-0001",
        "americu": "DMA-RES-AMERICU-20260427-0001",
    }
    for fixture, rid in expected.items():
        assert rid in r.stdout, (
            f"fixture {fixture} did not produce run_id {rid}"
        )


def test_dry_run_produces_non_zero_counts_for_every_fixture():
    """Catches the bug class where a fixture parses but extracts 0
    subcaps / 0 evidence — the silent failure the user reported."""
    r = _run("--dry-run", "--skip-db-check")
    assert r.returncode == 0
    # Parse the summary lines — each must have subcaps > 0 + evidence > 0.
    for line in r.stdout.splitlines():
        if "[?]" in line:  # dry-run lines have a [?] marker
            assert "subcaps=  0" not in line.replace("subcaps=  ", "subcaps="), (
                f"fixture has 0 subcaps: {line}"
            )


def test_help_flag_works():
    r = _run("--help")
    assert r.returncode == 0
    assert "seed_ci" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--only" in r.stdout


def test_force_regen_rebuilds_fixtures():
    """`--force-regen` re-runs generate_fixtures.py before seeding.
    Files must exist after the run."""
    from tests.fixtures.dma_packages_sanitized.generate_fixtures import (
        FIXTURE_BUILDERS,
        FIXTURE_ROOT,
    )
    r = _run("--dry-run", "--skip-db-check", "--force-regen")
    assert r.returncode == 0, r.stderr
    for name in FIXTURE_BUILDERS:
        assert (FIXTURE_ROOT / name).exists(), (
            f"fixture {name} not regenerated"
        )


@pytest.mark.parametrize("fixture", [
    "regions", "amalgamated", "anb", "wsfs", "americu",
])
def test_each_fixture_parses_via_real_parser(fixture):
    """Sanity-check each fixture independently via `parse_package` so
    a parser regression surfaces with the offending fixture name."""
    from app.services.parsers.dma_package import parse_package
    from tests.fixtures.dma_packages_sanitized.generate_fixtures import (
        FIXTURE_ROOT,
    )
    pkg = parse_package(FIXTURE_ROOT / fixture)
    assert pkg.run_manifest.run_id, f"{fixture}: empty run_id"
    assert len(pkg.subcap_scores or []) > 0, f"{fixture}: 0 subcaps"
    assert len(pkg.evidence or []) > 0, f"{fixture}: 0 evidence"
    assert len(pkg.peers or []) > 0, f"{fixture}: 0 peers"


# ── Production-image regression guard ─────────────────────────────────


def test_ensure_fixtures_noop_when_present_no_generator_needed(tmp_path):
    """Replicates the production-image hot path: fixtures pre-bundled
    on disk, generator module unavailable. `_ensure_fixtures` must NOT
    attempt to import the generator (which doesn't ship in the prod
    image) — must be a silent no-op.

    Regression for the ModuleNotFoundError that broke build 87c5964
    e2e-personas step (`from tests.fixtures.dma_packages_sanitized
    .generate_fixtures import regenerate` exploded inside the backend
    image because backend.Dockerfile didn't ship tests/).
    """
    from app.scripts.seed_ci import FIXTURE_NAMES, _ensure_fixtures
    # Create the 5 fixture dirs (empty stubs are sufficient — the
    # function only checks `.exists()`).
    for name in FIXTURE_NAMES:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    # Must succeed without importing the generator — even if the
    # generator path on disk is bogus.
    _ensure_fixtures(tmp_path, force_regen=False)


def test_ensure_fixtures_hard_fails_with_actionable_error_when_missing_and_no_generator(tmp_path, monkeypatch):
    """Production-image misconfiguration guard: if a future
    backend.Dockerfile change drops the fixture COPY, seed_ci must
    fail with an actionable RuntimeError pointing at the Dockerfile
    (NOT the bare ModuleNotFoundError that triggered this fix).

    Simulates the production-image state where `tests/` is NOT on
    disk: we evict any cached `tests.*` modules from sys.modules
    AND prevent the import system from finding them.
    """
    from app.scripts.seed_ci import _ensure_fixtures
    # Evict every cached tests.* module so the import re-runs from
    # the now-broken sys.path (tmp_path has no tests/ dir).
    for mod in list(sys.modules):
        if mod == "tests" or mod.startswith("tests."):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    # Install an import hook that blocks `tests.fixtures.dma_packages_sanitized.generate_fixtures`
    # so even if some entry remains on sys.path the import fails — the
    # exact failure mode the production image exhibits.
    import importlib.abc

    class _BlockGenerator(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.startswith("tests"):
                raise ModuleNotFoundError(f"prod-image sim: {name} not shipped")
            return None
    blocker = _BlockGenerator()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])
    with pytest.raises(RuntimeError, match="fixtures missing"):
        _ensure_fixtures(tmp_path, force_regen=False)


def test_backend_dockerfile_ships_fixtures():
    """backend.Dockerfile MUST COPY EVERY fixture in `FIXTURE_NAMES` so the
    e2e-personas step's `python -m app.scripts.seed_ci` works inside
    the production backend image (no host bind-mount there).

    Source-of-truth: iterate `FIXTURE_NAMES` rather than a hardcoded list
    so a future fixture addition can't silently drift the Dockerfile out
    of sync (2026-06-08: `richbank` was added to FIXTURE_NAMES in Batch 6
    but never COPY'd, so seed_ci hard-failed inside the image in
    e2e-personas — this hardcoded-5 test couldn't catch it).

    State branches:
      all_copied  → seed_ci works inside the image (current state).
      any_missing → seed_ci hard-fails with RuntimeError (the bare
                    ModuleNotFoundError is wrapped into something
                    actionable).
    """
    from app.scripts.seed_ci import FIXTURE_NAMES

    dockerfile = (
        REPO_ROOT.parent / "infra" / "docker" / "backend.Dockerfile"
    )
    assert dockerfile.exists(), f"backend.Dockerfile missing at {dockerfile}"
    text = dockerfile.read_text()
    for fixture in FIXTURE_NAMES:
        assert (
            f"dma_packages_sanitized/{fixture} " in text
            or f"dma_packages_sanitized/{fixture}\n" in text
            or f"dma_packages_sanitized/{fixture}/" in text
        ), (
            f"backend.Dockerfile missing COPY for fixture {fixture!r} — "
            "seed_ci will ModuleNotFoundError inside the production "
            "image (e2e-personas runs it with no host mount). Add a COPY "
            "for backend/tests/fixtures/dma_packages_sanitized/"
            f"{fixture} and keep it in lockstep with FIXTURE_NAMES."
        )


def test_seed_ci_no_runtime_imports_from_tests_package():
    """seed_ci.py is a PRODUCTION script — it runs from inside the
    backend image where the `tests/` package is NOT shipped (only
    the fixture DATA is COPY'd). Any `from tests.fixtures...` import
    at module top-level OR in unconditional code paths would
    ModuleNotFoundError at startup.

    The only acceptable site for `from tests.fixtures.*` is INSIDE
    `_ensure_fixtures`, wrapped in try/except, ONLY reached when
    fixtures are missing on disk (dev-only regen path).
    """
    seed_ci_src = (
        REPO_ROOT.parent / "backend" / "app" / "scripts" / "seed_ci.py"
    ).read_text()
    # Allow the import ONLY inside the function body of _ensure_fixtures
    # — find every `from tests.` line and check its enclosing function.
    offenders: list[tuple[int, str]] = []
    in_ensure_fixtures = False
    for lineno, line in enumerate(seed_ci_src.splitlines(), start=1):
        stripped = line.lstrip()
        if line.startswith("def _ensure_fixtures"):
            in_ensure_fixtures = True
            continue
        if in_ensure_fixtures and line and not line[0].isspace():
            in_ensure_fixtures = False
        if (
            ("from tests." in stripped or "import tests." in stripped)
            and not in_ensure_fixtures
        ):
            offenders.append((lineno, line.rstrip()))
    assert not offenders, (
        "seed_ci.py imports from `tests.*` outside _ensure_fixtures — "
        "this WILL break inside the production backend image. "
        "Move the import inside _ensure_fixtures' try/except, "
        "or eliminate it entirely:\n  "
        + "\n  ".join(f"L{n}: {ln}" for n, ln in offenders)
    )


# ── Live-DB tests — only run when SEED_CI_PG_URL is set ───────────────


def _live_run(*args: str, **env_extras: str) -> subprocess.CompletedProcess:
    """Run seed_ci against the live DB pointed at by SEED_CI_PG_URL."""
    env = os.environ.copy()
    env.update({
        "DATABASE_URL_SYNC": LIVE_DB_URL.replace("+asyncpg", ""),
        "DATABASE_URL": LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL
                        else LIVE_DB_URL.replace("postgresql://",
                                                  "postgresql+asyncpg://"),
        "ENV": "local",
    })
    env.update(env_extras)
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.seed_ci", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, env=env,
    )


def _live_query(sql: str) -> list[tuple]:
    """Return rows from a live PG query (psycopg2 — sync, simple)."""
    import psycopg2
    sync_url = LIVE_DB_URL.replace("+asyncpg", "")
    with psycopg2.connect(sync_url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


@pytest.mark.skipif(not HAS_LIVE_DB,
                    reason="SEED_CI_PG_URL not set; live-persist tests skipped")
class TestLivePersistence:
    """Storage + persistence is core to functionality — when a real
    Postgres is reachable, these tests prove the full ingest chain
    actually writes rows the web app can render against."""

    def test_full_ingest_persists_5_runs_with_subcaps_and_evidence(self):
        """The headline assertion: seed_ci against a fresh DB
        produces 5 entities, 5 runs, ≥ 200 subcap_scores, ≥ 50
        evidence rows. Below either floor → ingest broken."""
        # Reset to clean slate
        import psycopg2
        sync_url = LIVE_DB_URL.replace("+asyncpg", "")
        with psycopg2.connect(sync_url) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Run migrations
        migrate = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
            env={**os.environ, "DATABASE_URL_SYNC": sync_url},
        )
        assert migrate.returncode == 0, f"alembic failed: {migrate.stderr}"

        # Run seed
        r = _live_run()
        assert r.returncode == 0, (
            f"seed_ci exited {r.returncode}; stderr=\n{r.stderr}"
        )
        # 2026-06-06 Batch 6: FIXTURE_NAMES expanded from 5 to 6
        # (richbank added). Source-of-truth: derive expected count
        # from the FIXTURE_NAMES tuple instead of hardcoding so future
        # additions don't drift this assertion silently.
        from app.scripts.seed_ci import FIXTURE_NAMES as _FN
        expected_summary = f"summary: ok={len(_FN)} new={len(_FN)}"
        assert expected_summary in r.stdout, r.stdout

        # ASSERT against the live DB — this is the "real persistence
        # exercise" the user explicitly demanded.
        ((n_entities,),) = _live_query("SELECT COUNT(*) FROM entities")
        ((n_runs,),) = _live_query("SELECT COUNT(*) FROM runs")
        ((n_scores,),) = _live_query("SELECT COUNT(*) FROM subcap_scores")
        ((n_evidence,),) = _live_query("SELECT COUNT(*) FROM evidence_index")
        ((n_links,),) = _live_query("SELECT COUNT(*) FROM evidence_run_links")

        # 2026-06-06 Batch 6: FIXTURE_NAMES expanded from 5 to 6
        # (richbank added with a synthetic Client Profile DOCX so the
        # parser-extraction chain is exercised end-to-end). Use the
        # source-of-truth FIXTURE_NAMES tuple instead of a hardcoded 5.
        from app.scripts.seed_ci import FIXTURE_NAMES as _FN
        expected_n = len(_FN)
        assert n_entities == expected_n, (
            f"entities={n_entities}, expected {expected_n} (FIXTURE_NAMES={_FN})"
        )
        assert n_runs == expected_n, (
            f"runs={n_runs}, expected {expected_n}"
        )
        assert n_scores >= 250, (
            f"subcap_scores={n_scores}, expected >= 250 "
            "— catalogue bootstrap or persist regression"
        )
        assert n_evidence >= 50, (
            f"evidence={n_evidence}, expected >= 50 "
            "— dedup engine collapsed unique rows (excerpt-collision regression)"
        )
        assert n_links == n_evidence, (
            f"evidence_run_links={n_links} != evidence={n_evidence}"
        )
        # Cross-entity dedup contract (`cross_entity_kept` branch in
        # evidence_dedup): the SAME content_hash may legitimately
        # appear in MULTIPLE entities' evidence_index rows. The
        # 5-fixture baseline (Batch 5) had 0 hash overlap; the
        # 6-fixture baseline (Batch 6 + richbank) introduced
        # cross-entity overlap because richbank shares some research
        # content with other fixtures. The within-entity dedup is
        # what matters: assert (entity_id, content_hash) is unique so
        # we never persist a duplicate evidence row for the SAME
        # entity. Re-introducing this asserts the dedup engine still
        # guards within-entity collapse without forbidding the
        # cross-entity overlap that the 5-branch decision matrix
        # explicitly preserves.
        ((n_dup_within_entity,),) = _live_query(
            "SELECT COUNT(*) FROM ("
            " SELECT entity_id, content_hash, COUNT(*) c "
            " FROM evidence_index "
            " GROUP BY entity_id, content_hash "
            " HAVING COUNT(*) > 1"
            ") s"
        )
        assert n_dup_within_entity == 0, (
            f"within-entity duplicate content_hashes={n_dup_within_entity}"
            " — dedup engine regressed; the same content was persisted"
            " twice for one entity"
        )

    def test_re_seed_is_idempotent(self):
        """Running seed_ci against an already-seeded DB → 0 new rows.
        Idempotency is the contract that lets operators re-run safely."""
        # Capture counts BEFORE second seed
        before_runs = _live_query("SELECT COUNT(*) FROM runs")[0][0]
        before_evidence = _live_query("SELECT COUNT(*) FROM evidence_index")[0][0]

        r = _live_run()
        assert r.returncode == 0, r.stderr
        # All fixtures should report as already_seeded (= marker). Use
        # FIXTURE_NAMES as source of truth so this stays in sync as the
        # seed set grows.
        from app.scripts.seed_ci import FIXTURE_NAMES as _FN
        expected_n = len(_FN)
        assert r.stdout.count("[=]") == expected_n, (
            f"expected {expected_n} already_seeded markers (FIXTURE_NAMES={_FN}), "
            f"got:\n{r.stdout}"
        )

        after_runs = _live_query("SELECT COUNT(*) FROM runs")[0][0]
        after_evidence = _live_query("SELECT COUNT(*) FROM evidence_index")[0][0]
        assert after_runs == before_runs, "re-seed created duplicate runs"
        assert after_evidence == before_evidence, (
            "re-seed created duplicate evidence rows"
        )

    def test_only_filter_seeds_subset_real_db(self):
        """`--only` against live DB persists only the named fixtures."""
        # Clean + seed only regions + wsfs
        import psycopg2
        sync_url = LIVE_DB_URL.replace("+asyncpg", "")
        with psycopg2.connect(sync_url) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
            env={**os.environ, "DATABASE_URL_SYNC": sync_url},
        )

        r = _live_run("--only", "regions,wsfs")
        assert r.returncode == 0, r.stderr

        run_ids = [r[0] for r in _live_query(
            "SELECT request_id FROM runs ORDER BY request_id"
        )]
        assert run_ids == [
            "DMA-ASM-REGIONS-20260518-0001",
            "DMA-ASM-WSFS-20260519-0001",
        ], f"unexpected runs in DB: {run_ids}"
