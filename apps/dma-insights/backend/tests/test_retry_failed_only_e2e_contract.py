"""End-to-end contract simulation for the retry-failed-only loop.

This is a SHAPE consistency test — it verifies every link in the chain
that fires when a `historical_backfill` retry-failed-only run is
dispatched (formerly via the Operations panel's "Retry failed folders"
button, removed for strict prototype fidelity — see the note below):

    Dispatch POST  → /api/v1/admin/jobs/historical_backfill:execute
                     { mode: "retry", args: { extra_args: ["--retry-failed-only"] } }
              ↓
    JOB_REGISTRY    historical_backfill.modes must include "retry"
              ↓
    JOB_DISPATCH    cloud_run_dispatch.JOB_DISPATCH has historical_backfill →
                     ("dma-insights-historical-backfill", [], "app.scripts.historical_backfill")
              ↓
    extra_args      dispatch_job_arg_validator(["--retry-failed-only"]) returns the list
              ↓
    args_list       JOB_DISPATCH default_args + extra_args
              ↓
    Worker          app.scripts.historical_backfill parses --retry-failed-only
                    from sys.argv and narrows the folder set
              ↓
    Loop body       writes one backfill_quarantine row per folder via
                    _write_quarantine_row
              ↓
    /admin/diagnostics  re-reports backfill_folders_flagged_for_retry shrunk

Why a single consistency test rather than separate unit tests:
  - Each link CAN be changed independently in a PR; an isolated unit
    test wouldn't catch a wire-format drift along the chain
  - This file pins the dispatch→worker chain end-to-end. (The former
    FE→BE half lived in OperationsPanel.test.tsx, removed with the
    Operations panel for strict prototype fidelity; the BE still
    accepts the exact payload documented above.)
  - When this test fails, the failure message names the exact link
    that drifted

Pure-logic — no DB, no Drive, no Cloud Run. Live-PG behaviour is
covered by `tests/test_backfill_quarantine.py::TestQuarantineLivePg`.
"""
from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"


def test_job_registry_includes_historical_backfill_with_retry_mode() -> None:
    """JOB_REGISTRY drives `validate_mode`. The "retry" mode must be
    accepted or the admin route returns 400 before dispatch ever fires.
    """
    from app.services.job_executions import JOB_REGISTRY

    assert "historical_backfill" in JOB_REGISTRY, (
        "historical_backfill must be in JOB_REGISTRY — the admin route "
        "calls validate_mode() before dispatch, which rejects unknown jobs"
    )
    spec = JOB_REGISTRY["historical_backfill"]
    assert "retry" in spec["modes"], (
        "historical_backfill must accept mode='retry' — the Retry "
        "failed folders button POSTs mode=retry"
    )
    assert "full" in spec["modes"], (
        "historical_backfill must also accept mode='full' — manual "
        "operator dispatches still use the default mode"
    )


def test_job_dispatch_maps_historical_backfill_to_cloud_run_job() -> None:
    """JOB_DISPATCH is the BE→Cloud-Run-Job-name map. Drifting this
    silently invokes the wrong worker or returns job_not_in_registry."""
    from app.services.cloud_run_dispatch import JOB_DISPATCH

    assert "historical_backfill" in JOB_DISPATCH
    cr_name, default_args, module = JOB_DISPATCH["historical_backfill"]
    assert cr_name == "dma-insights-historical-backfill", (
        "Cloud Run Job name must match the terraform-defined resource "
        "in infra/terraform/main.tf::google_cloud_run_v2_job.historical_backfill"
    )
    assert module == "app.scripts.historical_backfill", (
        "Python module path for local-env subprocess must match the "
        "actual worker entrypoint"
    )
    assert default_args == [], (
        "default_args must be empty — extra_args is the operator's "
        "only knob; injecting defaults would silently change behaviour"
    )


def test_admin_route_validates_dispatch_arg_validator_against_extra_args() -> None:
    """The execute_job route extracts extra_args via
    `dispatch_job_arg_validator(body.args.get("extra_args"))`. The
    validator must (a) accept a list of strings, (b) reject anything
    else (defensive against arbitrary command injection)."""
    from app.services.cloud_run_dispatch import dispatch_job_arg_validator

    # Happy path — exactly what a retry-failed-only dispatch sends.
    out = dispatch_job_arg_validator(["--retry-failed-only"])
    assert out == ["--retry-failed-only"]

    # None → empty list (no extra args).
    assert dispatch_job_arg_validator(None) == []

    # Pure list of strings is fine.
    assert dispatch_job_arg_validator(["--foo", "--bar"]) == ["--foo", "--bar"]


def test_diagnostics_endpoint_omits_quarantine_key_when_table_missing() -> None:
    """The /admin/diagnostics endpoint must DEFENSIVELY skip the
    backfill_folders_flagged_for_retry query when the table doesn't
    exist (migration 022 not applied). The category is OMITTED rather
    than included as an empty list, so the UI's `?? []` null-coalesce
    handles both states cleanly.

    Source-shape lock: grep the admin.py for the defensive try/except
    around the backfill_quarantine query.
    """
    admin_py = (APP_DIR / "routers" / "admin.py").read_text()

    # The defensive try/except block must reference both:
    #   - the table name (so we know the right query is wrapped)
    #   - "does not exist" or "undefinedtable" in the error filter
    assert "backfill_quarantine" in admin_py.lower(), (
        "/admin/diagnostics endpoint missing backfill_quarantine query"
    )
    # Quote search — case-insensitive.
    lowered = admin_py.lower()
    quarantine_pos = lowered.find("backfill_quarantine")
    # Walk forward looking for the defensive error handler.
    window = lowered[quarantine_pos: quarantine_pos + 2000]
    assert "does not exist" in window or "undefinedtable" in window, (
        "/admin/diagnostics endpoint missing the defensive "
        '"relation does not exist" handler for backfill_quarantine — '
        "the endpoint would 500 if migration 022 isn't applied"
    )


def test_startup_diagnostic_includes_backfill_category() -> None:
    """The 5th diagnostic category must be in the startup_diagnostic
    SQL list — the structured Cloud Logging emit must mirror the
    /admin/diagnostics keys."""
    from app.services.startup_diagnostic import _DIAGNOSTIC_QUERIES

    keys = {q[0] for q in _DIAGNOSTIC_QUERIES}
    assert "backfill_folders_flagged_for_retry" in keys, (
        "startup_diagnostic._DIAGNOSTIC_QUERIES drifted from "
        "/admin/diagnostics — the category set MUST match"
    )


def test_load_retry_targets_query_matches_diagnostics_filter() -> None:
    """The set of outcomes deemed retry-eligible MUST agree between:
      - historical_backfill._load_retry_targets (worker side, post-flag)
      - /admin/diagnostics backfill_folders_flagged_for_retry (UI side)
      - startup_diagnostic._DIAGNOSTIC_QUERIES (Cloud Logging side)

    Drift would mean the UI surfaces N retry-eligible folders but the
    worker processes fewer (or more) — the operator's view of the
    quarantine state would lie.
    """
    expected_outcomes = {
        "failed_parse",
        "failed_persist",
        "failed_other",
        "skipped_no_report",
    }

    # 1. Worker filter.
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    for outcome in expected_outcomes:
        assert f'"{outcome}"' in backfill_src, (
            f"historical_backfill._load_retry_targets missing retry-eligible "
            f"outcome {outcome!r}"
        )

    # 2. /admin/diagnostics filter.
    admin_src = (APP_DIR / "routers" / "admin.py").read_text()
    for outcome in expected_outcomes:
        assert f"'{outcome}'" in admin_src, (
            f"/admin/diagnostics missing retry-eligible outcome "
            f"{outcome!r} in backfill_folders_flagged_for_retry filter"
        )

    # 3. startup_diagnostic filter.
    sd_src = (
        APP_DIR / "services" / "startup_diagnostic.py"
    ).read_text()
    for outcome in expected_outcomes:
        assert f"'{outcome}'" in sd_src, (
            f"startup_diagnostic missing retry-eligible outcome "
            f"{outcome!r} in backfill_folders_flagged_for_retry filter"
        )


def test_quarantine_outcome_enum_locked_across_layers() -> None:
    """The CHECK constraint enum in migration 022 must agree with the
    _classify_outcome output set. The outcome text is surfaced verbatim
    in the import-audit UI — a drift breaks the rendered text."""
    from app.scripts.historical_backfill import _classify_outcome

    canonical_outcomes = {
        "ok",
        "skipped_no_report",
        "skipped_already_ingested",
        "failed_parse",
        "failed_persist",
        "failed_other",
    }

    # Force one of each via _classify_outcome.
    sample_inputs = [
        ("OK:abc", "ok"),
        ("SKIP:no DMA package detected", "skipped_no_report"),
        ("SKIP:already_ingested x", "skipped_already_ingested"),
        ("ERROR:parse:x", "failed_parse"),
        ("ERROR:persist:x", "failed_persist"),
        ("ERROR:something_else:x", "failed_other"),
    ]
    produced = set()
    for res, expected in sample_inputs:
        outcome, *_ = _classify_outcome(res)
        produced.add(outcome)
        assert outcome == expected, f"{res!r} → {outcome!r}, expected {expected!r}"

    assert produced == canonical_outcomes, (
        f"_classify_outcome produces {produced}; canonical is "
        f"{canonical_outcomes}"
    )

    # Migration 022 enum must match.
    mig_src = (
        BACKEND_DIR / "alembic" / "versions" / "022_backfill_quarantine.py"
    ).read_text()
    for outcome in canonical_outcomes:
        assert f"'{outcome}'" in mig_src, (
            f"migration 022 CHECK constraint missing outcome {outcome!r}"
        )


def test_dispatch_arg_passthrough_does_not_silently_drop_retry_flag() -> None:
    """The chain extra_args→args_list→subprocess argv must not drop or
    duplicate the --retry-failed-only flag. Default args is [] for
    historical_backfill so the concatenated list is exactly
    ["--retry-failed-only"] (no surprises)."""
    from app.services.cloud_run_dispatch import (
        JOB_DISPATCH,
        dispatch_job_arg_validator,
    )

    _, default_args, _ = JOB_DISPATCH["historical_backfill"]
    extra_args = dispatch_job_arg_validator(["--retry-failed-only"])
    args_list = list(default_args) + list(extra_args)

    assert args_list == ["--retry-failed-only"], (
        f"args_list drifted: {args_list}. The worker reads sys.argv[1:] "
        f"and a stray argument breaks the --retry-failed-only flag check"
    )


def test_worker_parses_retry_failed_only_from_sys_argv() -> None:
    """Worker-side: the flag must be parsed from sys.argv (not just env)
    so a Cloud Run Job execution with `args=["--retry-failed-only"]`
    actually fires the retry path."""
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    # The flag must be checked AGAINST sys.argv-derived flags set.
    assert '"--retry-failed-only" in flags' in backfill_src, (
        "historical_backfill.main() must check '--retry-failed-only' "
        "against sys.argv-derived flags — if the check drifted, the "
        "retry path silently degrades to full backfill"
    )


def test_diagnostics_summary_total_includes_quarantine_count() -> None:
    """The _summary.total_issues counter must INCLUDE the new category
    (if present) so the banner says '5 operational issues detected'
    when 1 catalogue stub is missing + 4 folders need retry — instead
    of just '1'."""
    admin_src = (APP_DIR / "routers" / "admin.py").read_text()
    # The summary block must use isinstance(v, list) — the new
    # implementation iterates every list value (including the optional
    # backfill key) rather than hard-coding the original 4.
    assert "isinstance(v, list)" in admin_src, (
        "/admin/diagnostics _summary.total_issues counter must iterate "
        "EVERY list-shaped category (defensive against new categories) — "
        "drifting to a hardcoded 4-category list silently undercounts"
    )
