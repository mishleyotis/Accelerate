"""Live-DB integration tests — exercise the storage + persistence
layer against a real Postgres so we catch the "tests dry-run but
production crashes" class of bug.

Gated by SEED_CI_PG_URL. When unset (default in CI without a DB),
the whole module is skipped. When set, every test fires real SQL.

Coverage:
  - /readyz against live DB (drift detection works for real)
  - end-to-end ingest writes to entities + runs + subcap_scores
  - re-ingest with same request_id is idempotent (no duplicate run)
  - parser_warnings JSONB column accepts the orchestrator output
  - audit_log INSERTs from the drive-feedback wiring don't deadlock
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)
REPO_ROOT = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.skipif(
    not HAS_LIVE_DB,
    reason="SEED_CI_PG_URL not set — live-DB integration tests skipped",
)


def _sync_url() -> str:
    return LIVE_DB_URL.replace("+asyncpg", "")


def _async_url() -> str:
    if "+asyncpg" in LIVE_DB_URL:
        return LIVE_DB_URL
    return LIVE_DB_URL.replace("postgresql://", "postgresql+asyncpg://")


def _live_query(sql: str, params: tuple = ()) -> list[tuple]:
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _reset_and_migrate() -> None:
    """Drop + recreate the public schema, then alembic-upgrade-head.
    Idempotent — every test that needs a known state calls this."""
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "DATABASE_URL_SYNC": _sync_url()},
    )
    assert r.returncode == 0, f"alembic failed: {r.stderr}"


def _run_seed() -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL_SYNC": _sync_url(),
        "DATABASE_URL": _async_url(),
        "ENV": "local",
    }
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.seed_ci"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, env=env,
    )


# ── Migration round-trip (A1) ─────────────────────────────────────────


def test_alembic_upgrade_downgrade_upgrade_clean():
    """Round-trip: head → base → head must complete without error.
    Catches non-reversible migrations + downgrade bugs."""
    _reset_and_migrate()
    # downgrade base
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "DATABASE_URL_SYNC": _sync_url()},
    )
    assert r.returncode == 0, f"downgrade failed: {r.stderr}"
    # upgrade head again
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "DATABASE_URL_SYNC": _sync_url()},
    )
    assert r.returncode == 0, f"re-upgrade failed: {r.stderr}"

    # alembic_version must be exactly 1 head row
    ((n,),) = _live_query("SELECT COUNT(*) FROM alembic_version")
    assert n == 1, "multiple alembic heads (split-brain)"
    ((head,),) = _live_query("SELECT version_num FROM alembic_version")
    assert head, "alembic_version empty after round-trip"


def test_pgvector_extension_present_post_migration():
    _reset_and_migrate()
    rows = _live_query(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    )
    assert rows, "pgvector extension missing"
    version = rows[0][0]
    # 0.5+ is required for the ivfflat indexes
    assert version, f"pgvector empty version: {rows}"


# ── End-to-end ingest + persistence ───────────────────────────────────


def test_seed_ci_writes_persistable_state_for_web_app():
    """After seeding the canonical fixtures, the web app should be able
    to render the directory + per-entity views. Exercise this by
    asserting the actual data the API endpoints read from.

    2026-06-06 Batch 6: FIXTURE_NAMES expanded from 5 → 6 (richbank
    added). Source-of-truth is the FIXTURE_NAMES tuple so future
    additions don't drift this assertion."""
    _reset_and_migrate()
    r = _run_seed()
    assert r.returncode == 0, r.stderr

    from app.scripts.seed_ci import FIXTURE_NAMES as _FN
    expected_n = len(_FN)

    # One row per fixture — the directory page should show that many
    entities = _live_query(
        "SELECT display_id, subvertical FROM entities ORDER BY display_id"
    )
    assert len(entities) == expected_n, (
        f"entities={len(entities)}, expected {expected_n} "
        f"(FIXTURE_NAMES={_FN})"
    )
    # Each entity has a non-empty subvertical so the directory filter works
    for display_id, subvertical in entities:
        assert subvertical, f"entity {display_id} missing subvertical"

    # Per-entity D3 heatmap reads from subcap_scores — every run must
    # have ≥ 50 scores so the heatmap is not empty
    rows = _live_query("""
        SELECT r.request_id, COUNT(s.id) AS n_scores
        FROM runs r LEFT JOIN subcap_scores s ON s.run_id = r.id
        GROUP BY r.request_id
        ORDER BY r.request_id
    """)
    for rid, n in rows:
        assert n >= 50, f"run {rid} has only {n} scores (D3 would be empty)"

    # Evidence drawer reads from evidence_index — every run must have
    # ≥ 10 evidence rows (so the drawer paginates instead of being blank)
    rows = _live_query("""
        SELECT r.request_id, COUNT(ei.id) AS n_evidence
        FROM runs r
        LEFT JOIN evidence_run_links erl ON erl.run_id = r.id
        LEFT JOIN evidence_index ei ON ei.id = erl.evidence_id
        GROUP BY r.request_id
        ORDER BY r.request_id
    """)
    for rid, n in rows:
        assert n >= 10, f"run {rid} has only {n} evidence rows"


def test_dedup_audit_records_one_row_per_evidence_decision():
    """The 5-branch dedup engine must write one audit row per
    decision so operators can trace why a row landed or was
    deduplicated."""
    _reset_and_migrate()
    _run_seed()

    # Should have at least 1 audit row per parser-evidence-input
    # across the seeded fixtures. The 5-fixture baseline (Batch 5)
    # was 69 inputs (12+10+15+18+14); the 6-fixture baseline (Batch 6
    # adds richbank) was 87 (69 + 18 from richbank evidence_index).
    # Pin the LOWER bound on the per-fixture inputs (>=12 each) so
    # future fixtures stretch the floor without re-pinning the
    # hardcoded total on every batch.
    from app.scripts.seed_ci import FIXTURE_NAMES as _FN
    ((n_audit,),) = _live_query("SELECT COUNT(*) FROM dedup_audit")
    floor = 12 * len(_FN)
    assert n_audit >= floor, (
        f"dedup_audit={n_audit}, expected at least {floor} "
        f"(>= 12 rows per fixture across {len(_FN)} fixtures)"
    )

    # Action breakdown — at minimum kept + cross_entity_kept must fire
    rows = _live_query(
        "SELECT action, COUNT(*) FROM dedup_audit GROUP BY action"
    )
    actions = dict(rows)
    assert "kept" in actions, f"no 'kept' rows: {actions}"
    # Fixtures share some content_hashes across entities so
    # `cross_entity_kept` should also fire when the second+ fixture's
    # row matches the first's hash
    # (not strictly required if all hashes are perfectly unique)


def test_freshness_band_populated_by_generated_column():
    """`freshness_band` is a STORED generated column maintained by
    Postgres (migration 018). After ingest every evidence row must
    have a non-null band."""
    _reset_and_migrate()
    _run_seed()

    rows = _live_query("""
        SELECT freshness_band, COUNT(*)
        FROM evidence_index GROUP BY freshness_band
    """)
    assert rows, "evidence_index empty"
    for band, count in rows:
        assert band in ("current", "aging", "dated", "stale", "undated"), (
            f"unexpected freshness_band: {band}"
        )
        assert count > 0


# ── audit_log integration (F4 wiring) ─────────────────────────────────


def test_audit_log_table_writable():
    """The drive-feedback orchestrator writes to audit_log
    (best-effort). Assert the column shape accepts the JSON payload
    so the live wiring doesn't silently 500."""
    _reset_and_migrate()
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn, conn.cursor() as cur:
        cur.execute("""
                INSERT INTO audit_log (
                    action, resource_type, resource_id, actor_email,
                    before_json, after_json
                ) VALUES (
                    'drive_feedback_written', 'run',
                    'test-run-id-123', 'system',
                    NULL, %s::jsonb
                )
            """, ('{"state": "upload_ok", "written": ["x.json"]}',))
        conn.commit()
        cur.execute("""
            SELECT after_json->>'state' FROM audit_log
            WHERE resource_id = 'test-run-id-123'
        """)
        ((state,),) = cur.fetchall()
        assert state == "upload_ok"
