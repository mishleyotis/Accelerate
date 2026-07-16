"""Parallel-safety contract for the self-healing audit's mutation guard.

qa-gates runs the four QA harnesses CONCURRENTLY against one DB. The
self-healing audit detects an errant verify-only/dry-run write by snapshotting
row counts of `_SNAPSHOT_TABLES` before/after each healer invocation. Any table
that a *concurrent* harness can write (a GET-path lazy side-effect) therefore
produces a FALSE "verify-only mutated state" FAIL — which is exactly the
2026-06-18 qa-gates exit-9 (`vertex_synthesis_cache=+888`, written by the
render/adversarial harnesses' cold-synthesis caching).

This test pins the contract: the mutation snapshot tracks only canonical-data
tables that NO read-path endpoint mutates, so the guard stays meaningful AND
parallel-safe.
"""
from __future__ import annotations

from app.scripts.qa_self_healing_learning_audit import _SNAPSHOT_TABLES

# Tables written as a lazy side-effect of a GET-path read (or otherwise by a
# concurrent harness), so they must NOT be in the mutation snapshot.
_LAZILY_WRITTEN_ON_READ = {
    "vertex_synthesis_cache",  # synthesis cache — confirmed culprit (+888)
    "audit_log",               # most endpoints append an audit row
    "gemini_cache",            # legacy synthesis cache
    "job_executions",          # worker/job bookkeeping
    "chat_messages", "chat_sessions",  # written by /rag reads
}


def test_snapshot_excludes_lazily_written_tables():
    overlap = set(_SNAPSHOT_TABLES) & _LAZILY_WRITTEN_ON_READ
    assert not overlap, (
        f"_SNAPSHOT_TABLES includes lazily-written table(s) {sorted(overlap)} — "
        f"a concurrent qa-gates harness will write them DURING a verify-only "
        f"snapshot window and trip a false 'mutated state' FAIL (exit 9). "
        f"Track only canonical-data tables no read-path mutates."
    )


def test_snapshot_still_covers_canonical_data():
    """The guard must still catch a healer that wrongly COMMITs canonical data."""
    for canonical in ("entities", "runs", "subcap_scores", "evidence_index",
                      "focus_areas", "recommendations"):
        assert canonical in _SNAPSHOT_TABLES, (
            f"{canonical} dropped from the mutation snapshot — a verify-only "
            f"healer that wrongly writes it would no longer be caught."
        )
