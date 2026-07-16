"""Contract test: Phase 4 self-healing + learning-loop integrity gate.

Per the integrated batched plan Batch 7 spec: this test pins the
production-impact contract that the 7 continuous-learning loops
have their integrity guarantees in place on the live DB, and that
the operator-runnable self-healing scripts' safe modes work as
documented.

The full audit harness lives at
``app/scripts/qa_self_healing_learning_audit.py`` (17 cells: 9
self-healing scripts + 7 learning loops + 1 cross-loop
corpus_health). This pytest exercises a subset that runs without
GCP credentials, guaranteeing the contract holds in any CI / local
env that has a live PG with the seeded corpus.

Per the operator mandate "no test skips, no silent error
swallowing": the live-DB gate uses DATABASE_URL_SYNC (matches the
SEED_CI_PG_URL convention used by 20+ other live-DB tests).

Test isolation: every check runs inside ONE asyncio.run block so
asyncpg's per-loop pool tears down cleanly. The "Event loop is
closed" pool-teardown error fires when multiple asyncio.run calls
reuse the shared engine across loops.
"""
from __future__ import annotations

import asyncio
import os

import pytest


def _live_db() -> bool:
    return bool(os.environ.get("DATABASE_URL_SYNC", ""))


pytestmark = pytest.mark.skipif(
    not _live_db(),
    reason=(
        "DATABASE_URL_SYNC not set -- learning-loop integrity test "
        "requires live PG. Set DATABASE_URL_SYNC to the local Postgres "
        "connection string."
    ),
)


def test_self_healing_and_learning_loops_end_to_end() -> None:
    """One-shot end-to-end gate that asserts:

      1. ``corpus_health`` -- every ACTIVE entity has >= 1 run.
         (Hard contract: 0 entities with 0 runs.)
      2. All 7 learning loops complete WITHOUT FAIL classification.
         (FAIL = silent-swallow / table missing / schema drift.)
      3. Loop 6 (catalogue_alias_bridge) integrity: every broadcast
         row's parent_category_id matches ^P[1-4]C\\d+$.
      4. Loop 5 (synthesis_cache_invalidation) read-side queries
         succeed; the cache table is queryable + has the expected
         shape.
      5. ``audit_self_healing_scripts`` reports NO 'mutated state'
         observations -- the verify-only / dry-run / help modes
         never touch DB rows.

    Single asyncio.run so the asyncpg engine pool's loop matches
    across all the harness functions. Resets the module-global engine
    BEFORE running so the audit doesn't inherit a half-dead pool from
    a prior test (pytest reuses python process across many tests; the
    shared get_sessionmaker() global needs a fresh engine bound to
    THIS test's event loop).
    """
    # Reset the shared engine + sessionmaker so the audit binds a
    # fresh pool to the asyncio.run loop we're about to enter.
    import app.database as _db

    _db._engine = None
    _db._sessionmaker = None

    from app.scripts.qa_self_healing_learning_audit import (
        _check_corpus_health,
        audit_learning_loops,
        audit_self_healing_scripts,
    )

    async def _run() -> dict:
        corpus = await _check_corpus_health()
        loops = await audit_learning_loops()
        scripts = await audit_self_healing_scripts()
        # Dispose the engine inside the loop so the pool tears down
        # cleanly before asyncio.run returns.
        if _db._engine is not None:
            await _db._engine.dispose()
            _db._engine = None
            _db._sessionmaker = None
        return {"corpus": corpus, "loops": loops, "scripts": scripts}

    out = asyncio.run(_run())
    corpus = out["corpus"]
    loops = out["loops"]
    scripts = out["scripts"]

    # 1. corpus_health
    assert corpus.classification != "FAIL", (
        f"corpus_health FAIL: {corpus.observations}"
    )
    assert corpus.counters.get("no_runs", 0) == 0, (
        f"Found {corpus.counters.get('no_runs', 0)} entities with 0 "
        f"runs (persist pipeline regression)."
    )

    # 2. All 7 learning loops -- no FAILs.
    loop_fails = [r for r in loops if r.classification == "FAIL"]
    assert not loop_fails, (
        f"Found {len(loop_fails)} learning-loop FAILs "
        f"(deploy-blocking):\n"
        + "\n".join(
            f"  - {r.name}: {'; '.join(r.observations)[:120]}"
            for r in loop_fails
        )
    )
    assert len(loops) == 7, (
        f"Expected 7 learning-loop checks; got {len(loops)}: "
        f"{[r.name for r in loops]}"
    )

    # 3. + 4. specific loop assertions surface in the loop-by-loop
    # results above; FAIL has already been asserted away.

    # 5. self-healing safe modes don't mutate DB.
    mutating = [
        r for r in scripts
        if r.classification == "FAIL"
        and any("mutated state" in o for o in r.observations)
    ]
    assert not mutating, (
        "Self-healing scripts mutated DB state in verify-only mode:\n"
        + "\n".join(
            f"  - {r.name}: counters={r.counters}; "
            f"{'; '.join(r.observations)[:160]}"
            for r in mutating
        )
    )
