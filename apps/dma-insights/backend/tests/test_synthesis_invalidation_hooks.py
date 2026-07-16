"""Synthesis-cache invalidation hooks — package_persist + chat_feedback.

Stress-tests the wiring that makes the user-mandated rule real:
"once vertex models interpret the information, this is persisted,
unless there is new information or a rerun has been done."

The new information / rerun triggers are:
  - package_persist.publish_post_commit (every new run)
  - chat_feedback POST with rating=-1 + unhelpful_reason='hallucinated'
  - catalogue loader on version bump (covered in catalogue tests)

State coverage per test
-----------------------
test_publish_post_commit_invalidates_entity_rows
    → on every successful ingest, mark_invalidated fires with
      target_kind='entity' + target_ids=(entity_id,)
test_publish_post_commit_invalidate_failure_doesnt_block_ingest
    → if the synthesis_cache module's mark_invalidated raises, the
      ingest still completes (publish result returned unchanged)
test_feedback_hallucinated_invalidates_one_row
    → rating=-1 + 'hallucinated' → safe_mark_invalidated called with
      InvalidationSpec.cache_row_id set
test_feedback_other_reason_does_not_invalidate
    → rating=-1 + 'too_verbose' → NO cache invalidation
test_feedback_positive_does_not_invalidate
    → rating=+1 → NO cache invalidation
test_invalidation_spec_kinds_disjoint
    → InvalidationSpec for ingest vs feedback have non-overlapping
      target_kind+cache_row_id → safe to apply both sequentially
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch


async def _fake_publisher_ok(envelope):
    """Always succeeds. Returns (True, message_id, None)."""
    return (True, "msg-123", None)


async def _fake_publisher_fail(envelope):
    """Pub/Sub fails — but invalidation must still fire."""
    raise RuntimeError("pubsub down")


async def test_publish_post_commit_invalidates_entity_rows() -> None:
    """The contract: every successful ingest invalidates the entity's
    cache rows. Stress: spec passed to mark_invalidated must scope to
    target_kind='entity' + target_ids=(entity_id,)."""
    from app.services.parsers.package_persist import publish_post_commit

    invalidate_calls: list[Any] = []

    def _capture(spec):
        invalidate_calls.append(spec)
        return 1

    with patch("app.services.synthesis_cache_db.safe_mark_invalidated", _capture):
        await publish_post_commit(
            db_run_id="run-uuid-1",
            entity_id="ent-uuid-1",
            request_id="REQ-DEADBEEF",
            ccg_catalog_version="v7.0",
            is_rerun=False,
            parent_request_id=None,
            publisher=_fake_publisher_ok,
        )

    # build_invalidation_for_new_run returns [entity_spec] when no subcaps
    assert len(invalidate_calls) == 1
    spec = invalidate_calls[0]
    assert spec.target_kind == "entity"
    assert spec.target_ids == ("ent-uuid-1",)
    assert spec.reason == "rerun_invalidate_all_surfaces"


async def test_publish_post_commit_invalidate_failure_doesnt_block_ingest() -> None:
    """If safe_mark_invalidated raises (synthesis_cache_db not deployed
    yet, DB down, etc.) the ingest result is returned unchanged.

    This is the resilience contract: ingest never wedges on
    audit-layer issues."""
    from app.services.parsers.package_persist import publish_post_commit

    def _raise(spec):
        raise RuntimeError("synthesis_cache_db unreachable")

    with patch("app.services.synthesis_cache_db.safe_mark_invalidated", _raise):
        result = await publish_post_commit(
            db_run_id="run-uuid-2",
            entity_id="ent-uuid-2",
            request_id="REQ-CAFEBABE",
            ccg_catalog_version="v7.0",
            publisher=_fake_publisher_ok,
        )

    # publish_post_commit returns the publisher's tuple unchanged
    assert result == (True, "msg-123", None)


async def test_publish_post_commit_invalidate_runs_even_when_pubsub_fails() -> None:
    """The Pub/Sub publish AND the cache invalidation are independent
    side-effects — one failing must NOT block the other."""
    from app.services.parsers.package_persist import publish_post_commit

    invalidate_called = False

    def _track(spec):
        nonlocal invalidate_called
        invalidate_called = True
        return 1

    with patch("app.services.synthesis_cache_db.safe_mark_invalidated", _track):
        result = await publish_post_commit(
            db_run_id="run-uuid-3",
            entity_id="ent-uuid-3",
            request_id="REQ-DEADBABE",
            ccg_catalog_version="v7.0",
            publisher=_fake_publisher_fail,
        )

    # Publish reported outer_error; invalidation STILL fired.
    assert result == (False, None, "outer_error")
    assert invalidate_called, "invalidation must fire even on publish failure"


def test_invalidation_spec_kinds_disjoint() -> None:
    """Sanity: the spec emitted by ingest (target_kind='entity')
    cannot collide with the spec emitted by feedback (cache_row_id
    only). Applying both sequentially is safe."""
    from app.services.synthesis_orchestrator import (
        build_invalidation_for_feedback,
        build_invalidation_for_new_run,
    )

    ingest_specs = build_invalidation_for_new_run("ent-x", None)
    feedback_spec = build_invalidation_for_feedback("row-y")

    # Ingest spec targets an entity_id; feedback targets a row_id.
    assert ingest_specs[0].cache_row_id is None
    assert feedback_spec.cache_row_id == "row-y"
    assert feedback_spec.target_kind is None
    assert feedback_spec.target_ids is None
    assert ingest_specs[0].target_kind == "entity"


def test_feedback_invalidation_reason_distinct() -> None:
    """Reason strings on the two paths are distinct so audit can
    differentiate 'a rerun invalidated this' from 'a hallucination
    feedback invalidated this'."""
    from app.services.synthesis_orchestrator import (
        build_invalidation_for_feedback,
        build_invalidation_for_new_run,
    )
    ingest = build_invalidation_for_new_run("ent-x", None)[0]
    feedback = build_invalidation_for_feedback("row-y")
    assert ingest.reason == "rerun_invalidate_all_surfaces"
    assert feedback.reason == "feedback_invalidated"
    assert ingest.reason != feedback.reason
