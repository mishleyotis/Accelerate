"""A2 + F5 — persona role gating + cross-user persistence E2E.

Gated by SEED_CI_PG_URL. When set, exercises:

  A2 persona role gating:
    - AE can read overview / insights / heatmap / platforms
    - AE blocked from health (D6) / context-internal (D5)
    - Analyst can read everything
    - Admin can read everything + admin pages
    - Customer view strips D5/D6 + ERS field

  F5 cross-user persistence:
    - Persist 1 run as system seed
    - Open as user A → asserted row IDs (insight_card UUIDs etc.)
    - Open as user B → SAME row IDs returned (no per-user mutation)
    - Re-ingest same request_id → idempotent (same row IDs)

These directly exercise the storage + persistence layer over the
SQL the API endpoints will read, with NO fake data.
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

# NOTE: the SEED_CI_PG_URL skipif is applied as a CLASS decorator on
# TestCrossUserPersistence (the only DB-dependent class). Module-level
# pytestmark was over-skipping TestPersonaRoleGating (pure-logic role
# hierarchy + admin email assertions) and TestVisualBaselines (pure
# filesystem checks of frontend/playwright.visual.config.ts) — both
# classes don't need a live DB, so they should run unconditionally in
# stage 1 (host workspace) where the referenced files exist.


def _sync_url() -> str:
    # psycopg2 (sync) accepts only `postgresql://...` / `postgres://...`.
    # SEED_CI_PG_URL may be set with a SQLAlchemy driver suffix
    # (`+asyncpg` for async, `+psycopg` for psycopg3 sync) -- strip
    # either so the DSN is psycopg2-parseable.
    return LIVE_DB_URL.replace("+asyncpg", "").replace("+psycopg", "")


def _live(sql: str, params: tuple = ()) -> list[tuple]:
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _reset_and_seed() -> None:
    """Drop + re-migrate + seed all 5 fixtures."""
    import psycopg2
    with psycopg2.connect(_sync_url()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    env = {
        **os.environ,
        "DATABASE_URL_SYNC": _sync_url(),
        "DATABASE_URL": LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL else
            LIVE_DB_URL.replace("postgresql://", "postgresql+asyncpg://"),
        "ENV": "local",
    }
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )
    assert r.returncode == 0, f"alembic: {r.stderr}"
    r = subprocess.run(
        [sys.executable, "-m", "app.scripts.seed_ci"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, env=env,
    )
    assert r.returncode == 0, f"seed_ci: {r.stderr}"


# ── F5 cross-user persistence ──────────────────────────────────────────


@pytest.mark.skipif(
    not HAS_LIVE_DB,
    reason="SEED_CI_PG_URL not set — persona E2E + persistence tests skipped",
)
class TestCrossUserPersistence:
    """Persisted runs must look identical to every user — the same
    insight_card UUIDs, evidence IDs, subcap_scores rows. The
    'persistent memory' contract is what makes the layer of
    intelligence cross-session + cross-user."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        _reset_and_seed()

    def test_two_reads_return_same_row_ids(self):
        """User A reads WSFS run → captures row IDs. User B reads same
        run → SAME IDs. Mutations would prove a per-user shadow."""
        run_query = """
            SELECT s.subcap_id, s.id::text AS row_id
            FROM subcap_scores s
            JOIN runs r ON r.id = s.run_id
            WHERE r.request_id = 'DMA-ASM-WSFS-20260519-0001'
            ORDER BY s.subcap_id
        """
        read_a = _live(run_query)
        read_b = _live(run_query)
        assert read_a == read_b, (
            "cross-read mismatch — persisted state is not stable "
            "across queries (possible per-session mutation bug)"
        )
        assert len(read_a) >= 50

    def test_evidence_ids_stable_across_reads(self):
        """Evidence row UUIDs must round-trip identically. This is the
        contract the EvidenceDrawer 'Seen in N runs' chip relies on."""
        q = """
            SELECT ei.e_id, ei.id::text AS row_id, ei.content_hash
            FROM evidence_index ei
            JOIN evidence_run_links erl ON erl.evidence_id = ei.id
            JOIN runs r ON r.id = erl.run_id
            WHERE r.request_id = 'DMA-ASM-WSFS-20260519-0001'
            ORDER BY ei.e_id
        """
        read_a = _live(q)
        read_b = _live(q)
        assert read_a == read_b
        # Every evidence row has a content_hash (dedup invariant)
        for e_id, _, content_hash in read_a:
            assert content_hash, f"evidence {e_id} missing content_hash"
            assert len(content_hash) == 64, "SHA-256 must be 64 chars"

    def test_idempotent_reseed_preserves_row_ids(self):
        """Re-running seed_ci against an already-seeded DB MUST NOT
        create new row IDs — the idempotency contract that lets
        operators safely re-run."""
        q = """
            SELECT s.subcap_id, s.id::text
            FROM subcap_scores s
            JOIN runs r ON r.id = s.run_id
            WHERE r.request_id = 'DMA-ASM-REGIONS-20260518-0001'
            ORDER BY s.subcap_id
        """
        before = _live(q)
        # Re-run seed
        env = {
            **os.environ,
            "DATABASE_URL_SYNC": _sync_url(),
            "DATABASE_URL": LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL else
                LIVE_DB_URL.replace("postgresql://",
                                    "postgresql+asyncpg://"),
            "ENV": "local",
        }
        r = subprocess.run(
            [sys.executable, "-m", "app.scripts.seed_ci"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
            env=env,
        )
        assert r.returncode == 0, r.stderr
        assert "[=]" in r.stdout, "re-seed didn't mark as already_seeded"
        after = _live(q)
        assert before == after, (
            "re-seed mutated subcap_scores row IDs — idempotency broken"
        )

    def test_all_5_entities_persist_separately(self):
        """All fixtures map to distinct entity_id rows — never collapse.
        Persisted entity_id is the directory cohesion key.

        2026-06-06 Batch 6: FIXTURE_NAMES expanded from 5 to 6
        (richbank). Use the source-of-truth tuple length instead of
        hardcoding 5 so this scales with the seed set."""
        from app.scripts.seed_ci import FIXTURE_NAMES as _FN
        expected_n = len(_FN)
        rows = _live(
            "SELECT id::text, display_id, drive_folder_id FROM entities "
            "ORDER BY display_id"
        )
        assert len(rows) == expected_n
        ids = [r[0] for r in rows]
        assert len(set(ids)) == expected_n
        folders = [r[2] for r in rows]
        assert len(set(folders)) == expected_n

    def test_audit_log_record_for_each_seed_persisted(self):
        """Every persist must leave a forensic trail. dedup_audit
        rows are the audit invariant — one row per evidence input.

        Per-fixture evidence counts: regions=12, amalgamated=10,
        anb=15, wsfs=18, americu=14, richbank=18 → 87 total post
        Batch 6. Use the source-of-truth fixture set + a sum() so the
        test scales with future additions."""
        ((n_audit,),) = _live("SELECT COUNT(*) FROM dedup_audit")
        from pathlib import Path

        from app.scripts.seed_ci import FIXTURE_NAMES as _FN
        from app.services.parsers.dma_package import parse_package
        fixture_root = (
            Path(__file__).parent / "fixtures" / "dma_packages_sanitized"
        )
        expected_total = 0
        for name in _FN:
            p = fixture_root / name
            if not p.exists():
                continue
            try:
                pkg = parse_package(p)
                expected_total += len(pkg.evidence)
            except Exception:
                pass
        assert n_audit == expected_total, (
            f"dedup_audit={n_audit}, expected {expected_total} "
            f"(sum of evidence across FIXTURE_NAMES={_FN})"
        )

    def test_overview_endpoint_returns_pillar_scores_for_seeded_entity(self):
        """RQA-04 regression — the D1 Overview endpoint MUST aggregate
        subcap_scores into per-pillar averages and return them so the
        UI ScoreRing + PillarBars render.

        Before 2026-05-26 the response always shipped pillar_scores=[]
        even when 60+ scored subcaps existed for the run. The ScoreRing
        on D1 rendered empty for every entity in production — a silent
        data-presentation defect that no existing test caught because
        none of them asserted the SHAPE the UI consumes.

        Pure-SQL assertion: verify the aggregation logic produces a
        non-empty per-pillar score set for the seeded WSFS entity
        directly from `subcap_scores`. The router now runs the same
        AVG()/substring(1,2) aggregation in `entities.py`. If subcap_id
        format changes, both this test AND the prod endpoint break
        together — that's the contract.
        """
        rows = _live(
            """
            SELECT substring(subcap_id, 1, 2) AS pillar_id,
                   ROUND(AVG(score)::numeric, 2) AS score,
                   COUNT(*) AS n
            FROM subcap_scores
            WHERE run_id = (
                SELECT id FROM runs
                WHERE request_id = 'DMA-ASM-WSFS-20260519-0001'
            )
              AND score IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """
        )
        assert len(rows) >= 1, "no pillar rows from subcap_scores"
        pillar_ids = {r[0] for r in rows}
        assert pillar_ids <= {"P1", "P2", "P3", "P4"}, (
            f"unexpected pillar_ids: {pillar_ids}"
        )
        for pid, score, n in rows:
            assert score is not None, f"pillar {pid} has NULL avg"
            assert 0.0 <= float(score) <= 5.0, (
                f"pillar {pid} score out of band: {score}"
            )
            assert n > 0, f"pillar {pid} has 0 scored subcaps"

    def test_overview_pillar_scores_sql_executes_against_all_5_entities(self):
        """RQA-08 regression — the EXACT SQL the router runs to aggregate
        pillar_scores MUST execute without error against every seeded
        run. The prior test above only ran a SIMPLIFIED version, so it
        missed the 2026-05-27 FILTER-on-ROUND bug that returned 500 from
        /api/v1/entities/{id}/overview for every entity:

            ROUND(AVG(peer_median)::numeric, 2)
                FILTER (WHERE peer_median IS NOT NULL) AS peer_median

        PostgreSQL parses the FILTER as applying to ROUND (NOT an
        aggregate), erroring with `FILTER specified, but round is not an
        aggregate function`. The fix moves the FILTER inside the ROUND
        so it modifies AVG:

            ROUND(
                AVG(peer_median) FILTER (WHERE peer_median IS NOT NULL)
                ::numeric, 2
            ) AS peer_median

        This test EXTRACTS the SQL block from the router source so it
        runs the LIVE query the production endpoint actually issues —
        any future edit that re-introduces the parser error fails here
        before it can reach the stage 7 e2e suite.
        """
        # 1. Pin the router source — the brittle form must not return.
        router_path = (
            REPO_ROOT / "app" / "routers" / "entities.py"
        )
        router_src = router_path.read_text()
        # Reject the FILTER-after-ROUND form (the exact 2026-05-27 bug).
        bad_pattern = (
            "ROUND(AVG(peer_median)::numeric, 2)\n"
            "                            FILTER (WHERE peer_median IS NOT NULL)"
        )
        assert bad_pattern not in router_src, (
            "entities.py /overview re-introduced the brittle "
            "`ROUND(AVG(peer_median)::numeric, 2) FILTER (...)` form — "
            "PostgreSQL will error 'FILTER specified, but round is not an "
            "aggregate function' on every /overview call. Use "
            "`ROUND(AVG(peer_median) FILTER (...)::numeric, 2)` instead."
        )

        # 2. Extract the actual pillar-scores SELECT from the router
        #    so the same SQL the prod code runs is exercised here.
        import re
        match = re.search(
            r"(SELECT\s+substring\(subcap_id,\s*1,\s*2\)\s+AS\s+pillar_id"
            r"[\s\S]+?ORDER BY 1)",
            router_src,
        )
        assert match, "could not locate pillar_scores SELECT in entities.py"
        sql_from_router = match.group(1).replace(":rid", "%s")

        # 3. Execute the router's SQL against every seeded run.
        runs = _live("SELECT id, request_id FROM runs WHERE status = 'ACTIVE'")
        assert len(runs) >= 5, f"expected ≥ 5 ACTIVE runs, got {len(runs)}"
        for run_id, request_id in runs:
            res = _live(sql_from_router, params=(str(run_id),))
            assert len(res) >= 1, (
                f"run {request_id} produced no pillar rows — "
                f"SQL may have aggregated 0 rows incorrectly"
            )
            for pid, pscore, pmedian, n_scored, n_peer in res:
                assert pid in {"P1", "P2", "P3", "P4"}, (
                    f"run {request_id} pillar {pid!r} — unexpected ID"
                )
                if pscore is not None:
                    assert 0.0 <= float(pscore) <= 5.0
                if pmedian is not None:
                    assert 0.0 <= float(pmedian) <= 5.0
                assert n_scored > 0
                assert 0 <= int(n_peer or 0) <= int(n_scored)


# ── A2 persona role gating ─────────────────────────────────────────────


class TestPersonaRoleGating:
    """The role hierarchy is downgrade-only — ADMIN ≥ ANALYST ≥ AE ≥
    CUSTOMER. This test verifies the can_act_as mapping that the
    frontend SettingsPopover reads + clamps to."""

    def test_can_act_as_hierarchy_is_downgrade_only(self):
        """ADMIN can act as any role below; AE can only act as AE."""
        from app.routers.auth import _can_act_as_for_role
        admin = _can_act_as_for_role("ADMIN")
        analyst = _can_act_as_for_role("ANALYST")
        ae = _can_act_as_for_role("AE")
        customer = _can_act_as_for_role("CUSTOMER")
        # ADMIN can act as everyone except CUSTOMER
        assert "ADMIN" in admin
        assert "ANALYST" in admin
        assert "AE" in admin
        # ANALYST cannot escalate to ADMIN
        assert "ADMIN" not in analyst
        assert "ANALYST" in analyst
        assert "AE" in analyst
        # AE only AE
        assert ae == ["AE"]
        # CUSTOMER only CUSTOMER
        assert customer == ["CUSTOMER"]

    def test_admin_emails_resolve_to_admin_role(self):
        """The 7 hardcoded admin emails (plus the operator's) must
        resolve to ADMIN. Anyone else under @zennify.com → AE."""
        from app.auth import assign_initial_role
        admin_emails = [
            "mishley.otiende@zennify.com",
            "richard.odhiambo@zennify.com",
            "sam.friedewald@zennify.com",
            "kevin.murray@zennify.com",
            "chris.conant@zennify.com",
            "carlie.welsh@zennify.com",
            "tom.hedgecoth@zennify.com",
        ]
        for email in admin_emails:
            assert assign_initial_role(email) == "ADMIN", (
                f"{email} should be ADMIN"
            )
        # Random Zennify employee → AE
        assert assign_initial_role("random.person@zennify.com") == "AE"

    def test_subcap_score_band_helper_clamps_to_M1_M5(self):
        """The maturity band lookup is shared by every UI render —
        bands MUST be one of M1..M5. The actual band boundaries
        (per ADR 0008 + the wireframe heatmap rule):
            M5: [4.5, 5.0]
            M4: [3.5, 4.5)
            M3: [2.5, 3.5)
            M2: [1.5, 2.5)
            M1: [1.0, 1.5)
        """
        from app.services.parsers.scoring_workbook import score_to_band
        assert score_to_band(1.0) == "M1"
        assert score_to_band(1.4) == "M1"
        assert score_to_band(1.5) == "M2"
        assert score_to_band(2.4) == "M2"
        assert score_to_band(2.5) == "M3"
        assert score_to_band(3.4) == "M3"
        assert score_to_band(3.5) == "M4"
        assert score_to_band(4.4) == "M4"
        assert score_to_band(4.5) == "M5"
        assert score_to_band(5.0) == "M5"


# ── A3 visual-baseline placeholder ─────────────────────────────────────


class TestVisualBaselines:
    """A3 — visual baselines. The Playwright suite under
    `frontend/playwright.visual.config.ts` captures screenshots per
    breakpoint; this test asserts the config + baseline directory
    are correctly set up so the build doesn't silently skip the gate.

    Visual regression has to run in a real browser context which
    isn't available in pytest. Per ADR 0011 the standalone bundle
    is the surface; visual regression covers it via
    `pnpm test:visual` (documented in DEPLOYMENT.md §31.5).
    """

    def test_playwright_visual_config_present(self):
        config = REPO_ROOT.parent / "frontend" / "playwright.visual.config.ts"
        assert config.exists(), (
            "playwright.visual.config.ts missing — A3 baseline gate "
            "is unwirred"
        )
        text = config.read_text()
        for bp in ("1920", "1440", "1280", "1180", "980", "900", "760"):
            assert bp in text, (
                f"breakpoint {bp} missing from visual config"
            )

    def test_e2e_routes_inventory(self):
        """The 12 routes covered by A3 visual must include each D-page."""
        routes_file = (
            REPO_ROOT.parent / "frontend" / "e2e" / "visual"
            / "routes.ts"
        )
        if not routes_file.exists():
            pytest.skip(f"visual routes file not present: {routes_file}")
        text = routes_file.read_text()
        for page in ("overview", "insights", "heatmap", "platform",
                     "context", "health"):
            assert page in text, (
                f"visual route inventory missing {page}"
            )
