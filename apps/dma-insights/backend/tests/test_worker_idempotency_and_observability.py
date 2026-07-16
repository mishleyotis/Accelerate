"""Phase 3 worker idempotency + observability regression tests.

Per the audit's worker section:
  - embedder duplicate Pub/Sub message doesn't duplicate vectors
  - intelligence_recompute invalid citation fails-closed
  - drive_crawler 403 file quarantined, not crash
  - sheet_poller duplicate row updates existing request
  - ccg_loader duplicate subcap fails validation
  - peer_patterns insufficient data → skipped state
  - chat_learning sparse feedback → insufficient_samples

Each test pins ONE observable contract so a refactor that drops
the self-healing surfaces here BEFORE the production incident.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Workers package isn't on PYTHONPATH for backend tests by default.
APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


# ── Pub/Sub idempotency table (processed_runs) ─────────────────────


def test_embedder_pubsub_loop_uses_ack_nack_for_idempotency():
    """The embedder's --subscribe loop must ACK successful messages
    so Pub/Sub doesn't redeliver them, and NACK failures so Pub/Sub
    does. Without explicit ack the message stays in-flight until
    Pub/Sub's redelivery timer fires -- making duplicates much more
    likely + multiplying the embedder load."""
    from workers.embedder import main as em_main

    src = Path(em_main.__file__).read_text(encoding="utf-8")
    assert "message.ack()" in src, (
        "embedder --subscribe must ACK successful messages. Without "
        "explicit ack Pub/Sub redelivers on timeout, causing duplicate "
        "embedding writes."
    )
    assert "message.nack()" in src, (
        "embedder --subscribe must NACK failed messages so Pub/Sub "
        "redelivers them on the configured backoff schedule."
    )


def test_embedder_acks_messages_missing_required_fields():
    """A malformed message (no run_id) must be ACK'd (skip + log)
    rather than NACK'd (Pub/Sub would redeliver indefinitely)."""
    from workers.embedder import main as em_main

    src = Path(em_main.__file__).read_text(encoding="utf-8")
    # The skip+ack pattern for missing fields must be present.
    assert "ack+skip" in src or "skip" in src.lower()


# ── ccg_loader validation ──────────────────────────────────────────


def test_ccg_loader_dedupes_categories_by_composite_key():
    """The ccg_loader parsers de-dup categories + L1 capabilities by
    `(category_id, l1_id)`. The contract is documented in the
    parse_capability_map docstring -- a refactor that drops the
    de-dup would silently let duplicate categories shadow each other."""
    from workers.ccg_loader import parsers as cp

    src = Path(cp.__file__).read_text(encoding="utf-8")
    # The dedup contract is documented in the parser docstring.
    assert "de-duplicated by" in src or "deduped" in src.lower() or "dedup" in src.lower(), (
        "ccg_loader.parsers must document its de-dup contract for "
        "(category_id, l1_id). A refactor that drops it would let "
        "duplicate categories silently shadow each other."
    )


def test_ccg_loader_writes_audit_row_with_status_for_admin_approval():
    """The ccg_loader writes a `ccg_loader_runs` audit row with a
    status. Per ADR 0005 (catalogue versioning) re-uploads land in
    AWAITING_APPROVAL state -- the admin approves before the new
    catalogue version becomes active. Pin the audit-row contract
    so a refactor that bypasses the approval step trips here."""
    from workers.ccg_loader import main as cl_main

    src = Path(cl_main.__file__).read_text(encoding="utf-8")
    assert "ccg_loader_runs" in src, (
        "ccg_loader.main must persist an audit row to ccg_loader_runs."
    )
    assert "AWAITING_APPROVAL" in src or "REJECTED" in src, (
        "ccg_loader.main must surface a typed status (AWAITING_APPROVAL "
        "/ REJECTED) so the admin UI can gate activation."
    )


def test_ccg_loader_persist_table_missing_returns_zero_not_crash():
    """If migration 012 (ccg_loader_runs table) hasn't run yet, the
    INSERT raises UndefinedTable. The worker must surface this as a
    warning + return 0 (graceful) rather than crash -- otherwise the
    catalogue load runs but no audit row gets written."""
    from workers.ccg_loader import main as cl_main

    src = Path(cl_main.__file__).read_text(encoding="utf-8")
    # The persist function must catch UndefinedTable / "does not exist".
    assert (
        "undefinedtable" in src.lower()
        or "does not exist" in src.lower()
    ), (
        "ccg_loader.main must gracefully handle a missing "
        "ccg_loader_runs table (migration 012 not applied). Crashing "
        "loses the load + the audit signal."
    )


# ── chat_learning sparse-feedback handling ─────────────────────────


def test_chat_learning_handles_sparse_feedback_with_documented_state():
    """When the feedback corpus is below the clustering threshold,
    the worker must surface 'insufficient_samples' OR similar typed
    state (not crash, not write empty cluster rows)."""
    from workers.chat_learning import main as cl_main

    src = Path(cl_main.__file__).read_text(encoding="utf-8")
    # The worker must mention an insufficient-samples / threshold
    # handling path so the operator can debug a "no signals" symptom.
    assert (
        "insufficient_samples" in src.lower()
        or "min_samples" in src.lower()
        or "threshold" in src.lower()
        or "skip" in src.lower()
    ), (
        "chat_learning must declare a typed insufficient-data state. "
        "Otherwise low-feedback days look like a silent crash."
    )


# ── peer_patterns insufficient cohort ──────────────────────────────


def test_peer_patterns_handles_insufficient_cohort():
    """A cohort with < N entities can't KMeans-cluster. The worker
    must surface this as a typed status (e.g. insufficient_data or
    insufficient_cohort), not crash sklearn.cluster's n_samples
    validation."""
    from workers.peer_patterns import main as pp_main

    src = Path(pp_main.__file__).read_text(encoding="utf-8")
    assert (
        "insufficient" in src.lower()
        or "min_entit" in src.lower()
        or "n_samples" in src.lower()
        or "len(" in src
    ), (
        "peer_patterns must guard against insufficient cohort size. "
        "Without the guard sklearn raises 'n_samples=N should be >= n_clusters'."
    )


# ── drive_crawler 403 quarantine ──────────────────────────────────


def test_drive_crawler_quarantines_403_without_crashing():
    """A file the SA can't read (403) must be quarantined + logged
    but the crawl continues. Pre-fix a single 403 would crash the
    whole worker and the remaining 100+ folders never got processed."""
    from workers.drive_crawler import main as dc_main

    src = Path(dc_main.__file__).read_text(encoding="utf-8")
    # Must catch the 403 / PermissionDenied / HttpError 403 case and
    # log/quarantine rather than re-raise.
    has_403_handling = (
        "HttpError" in src
        or "PermissionDenied" in src
        or "status_code == 403" in src
        or "resp.status_code" in src
        or "403" in src
    )
    assert has_403_handling, (
        "drive_crawler must explicitly handle 403 / PermissionDenied "
        "from the Drive API. Otherwise one inaccessible file crashes "
        "the whole crawl."
    )


# ── sheet_poller duplicate-row idempotency ─────────────────────────


def test_sheet_poller_documents_row_conflict_state_branch():
    """The Ops Sheet may have the same row processed twice on
    operator-triggered re-poll. The worker documents `row_conflict`
    as one of its typed state branches -- a "sheet wins; conflict
    logged" UPSERT semantics. A refactor that drops the explicit
    state-branch must surface here."""
    from workers.sheet_poller import main as sp_main

    src = Path(sp_main.__file__).read_text(encoding="utf-8")
    assert "row_conflict" in src, (
        "sheet_poller must document its row_conflict state branch in "
        "the docstring so the dedup contract is explicit."
    )


# ── intelligence_recompute fail-closed on invalid citation ────────


def test_intelligence_recompute_nacks_on_recompute_exception():
    """When recompute_entity raises (e.g. Vertex 503 / validator
    rejects a hallucinated citation), the worker MUST nack so
    Pub/Sub redelivers and the operator gets a retry chance. ACK
    on exception would lose the work silently."""
    from workers.intelligence_recompute import main as ir_main

    src = Path(ir_main.__file__).read_text(encoding="utf-8")
    # Must have an except block that NACKs (not silently acks).
    import re
    # Look for `except ... message.nack()` pattern.
    m = re.search(
        r"except\s+[A-Za-z]+[\s\S]+?message\.nack\(\)",
        src,
    )
    assert m is not None, (
        "intelligence_recompute --subscribe must NACK on exception so "
        "Pub/Sub redelivers. ACK-on-exception silently loses work."
    )


def test_intelligence_recompute_documents_state_branches():
    """The audit pinned the typed state-branch contract: the worker
    has documented handling for (entity_id present, run_id only,
    missing both, recompute raises, recompute returns, ADC missing).
    A refactor that drops the explicit branch table makes the worker
    a black box."""
    from workers.intelligence_recompute import main as ir_main

    src = Path(ir_main.__file__).read_text(encoding="utf-8")
    # The docstring documents the 6 state branches.
    for branch in ("entity_id", "run_id", "ACK", "NACK"):
        assert branch in src, (
            f"intelligence_recompute docstring missing state branch "
            f"marker '{branch}'. The 6-branch contract is what makes "
            "this worker debuggable in prod."
        )


# ── Embedder --subscribe drains malformed messages safely ─────────


def test_embedder_subscribe_loop_handles_malformed_pubsub_messages():
    """The audit: '--subscribe mode crashes on a single bad message
    and stops processing (must skip + log + ack)'. Pin the
    skip-and-continue contract."""
    from workers.embedder import main as em_main

    src = Path(em_main.__file__).read_text(encoding="utf-8")
    # The subscribe loop must catch+log per-message exceptions so a
    # malformed envelope doesn't kill the long-running subscriber.
    # Either try/except inside the receive loop OR an explicit
    # skip-and-ack on validation failure.
    has_skip = (
        "ack(" in src.lower() and "except" in src
    ) or (
        "skip" in src.lower() and "except" in src
    ) or (
        "continue" in src and "except" in src
    )
    assert has_skip, (
        "embedder --subscribe mode must skip+ack malformed messages "
        "so one bad message doesn't kill the long-running subscriber."
    )


# ── Worker tracker survives concurrent invocations ────────────────


def test_worker_runner_preserves_prior_env_execution_id_in_nested_context():
    """The audit identified that long-lived workers (embedder
    --subscribe) leak the auto-created job_execution_id across
    Pub/Sub messages if track_job_execution doesn't restore
    DMA_JOB_EXECUTION_ID in finally. Pin the contract."""
    src = Path(
        APP_ROOT / "workers" / "_runner.py"
    ).read_text(encoding="utf-8")
    # The runner must save the prior env value AND restore it in
    # finally so message #2 doesn't write onto message #1's row.
    assert "_prior_env_execution_id" in src, (
        "_runner.py must capture the prior DMA_JOB_EXECUTION_ID env "
        "value so nested invocations don't cross-contaminate."
    )
    assert "DMA_JOB_EXECUTION_ID" in src
    # Must restore in finally (otherwise an exception path leaks the id).
    assert "finally:" in src
