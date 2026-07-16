"""Tests for `app.services.catalogue_staging.upload_workbook_to_staging`
and the refactored `/api/v1/admin/catalogue:upload` route shape.

2026-05-28 P1-C remainder: the upload route used to write to
`/tmp/dma-catalogue-staging/<sha>/<file>` (local to the backend
container) + best-effort publish a Pub/Sub message to a topic with
no subscriber. Net effect: the ccg_loader Cloud Run Job NEVER ran.

The refactor:
  1. Uploads workbook bytes to `gs://<bucket>/<version-prefix>/<file>`.
  2. Falls back to `/tmp/...` only when GCS is unreachable (local dev).
  3. Replaces the Pub/Sub call with `cloud_run_dispatch.dispatch_job`
     using `--version` + `--workbooks-dir` as the Cloud Run Job args.

Test matrix:
  - GCS success → workbooks_dir_arg starts with `gs://`, backing=gcs
  - GCS unavailable (no project_id) → falls back to /tmp,
                                       backing=local_fallback
  - GCS upload raises → falls back to /tmp + logs warning
  - SHA256 prefix included in local fallback path (idempotent retry)
  - Version-prefix derived from version_hint (v7.0 → v7.0/)
  - Content-type chosen from filename extension
  - Route source-shape: NO Pub/Sub publish, uses dispatch_job
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_gcs_unavailable_falls_back_to_local():
    """When no project_id is configured, helper writes to /tmp and
    marks backing='local_fallback' so the operator sees the
    degraded state."""
    from app.services.catalogue_staging import upload_workbook_to_staging

    out = upload_workbook_to_staging(
        workbook_bytes=b"hello world\n",
        filename="Pillar_1_v7.0.xlsx",
        version_hint="v7.0",
        bucket_name="dma-test-bucket",
        project_id=None,  # ← no GCP project → skip GCS
    )
    assert out.backing == "local_fallback"
    assert out.gcs_uri is None
    assert out.workbooks_dir_arg.startswith("/tmp/dma-catalogue-staging/")
    assert out.local_path is not None and out.local_path.exists()
    # SHA prefix used to namespace; same bytes → same dir (idempotent).
    assert out.sha256_prefix in str(out.local_path)
    # Cleanup so reruns don't accumulate /tmp dirs.
    out.local_path.unlink(missing_ok=True)


def test_local_fallback_same_bytes_same_dir():
    """Same bytes → same SHA → same on-disk dir. The route relies on
    this so an operator double-clicking 'Upload' doesn't pile up
    five copies."""
    from app.services.catalogue_staging import upload_workbook_to_staging

    body = b"deterministic body"
    a = upload_workbook_to_staging(
        workbook_bytes=body, filename="x.xlsx",
        version_hint="v7.0", bucket_name="b", project_id=None,
    )
    b2 = upload_workbook_to_staging(
        workbook_bytes=body, filename="x.xlsx",
        version_hint="v7.0", bucket_name="b", project_id=None,
    )
    assert a.local_path == b2.local_path
    assert a.sha256_prefix == b2.sha256_prefix
    if a.local_path:
        a.local_path.unlink(missing_ok=True)


def test_gcs_upload_exception_falls_back_to_local():
    """If the GCS upload itself raises (perms / network / bucket
    missing) the helper falls back to /tmp WITHOUT propagating.
    Locked because the route trusts this to never raise on
    transient GCS issues — a 5xx here would block the admin UI."""
    from app.services import catalogue_staging as cs

    def _explode(**_kwargs):
        raise RuntimeError("simulated GCS outage")

    with patch.object(cs, "_gcs_upload", side_effect=_explode):
        out = cs.upload_workbook_to_staging(
            workbook_bytes=b"data",
            filename="Pillar_1.xlsx",
            version_hint="v7.0",
            bucket_name="dma-test-bucket",
            project_id="dma-test-proj",  # ← will be TRIED but fail
        )
    assert out.backing == "local_fallback"
    assert out.gcs_uri is None
    assert out.workbooks_dir_arg.startswith("/tmp/")
    if out.local_path:
        out.local_path.unlink(missing_ok=True)


def test_gcs_success_returns_gs_uri():
    """Happy path: when GCS upload succeeds, the helper returns the
    gs:// URI as the workbooks_dir_arg so the worker's
    `_resolve_workbooks_dir` fetches from GCS."""
    from app.services import catalogue_staging as cs

    captured: dict = {}

    def _fake_upload(**kwargs):
        captured.update(kwargs)
        return f"gs://{kwargs['bucket_name']}/{kwargs['gcs_object']}"

    with patch.object(cs, "_gcs_upload", side_effect=_fake_upload):
        out = cs.upload_workbook_to_staging(
            workbook_bytes=b"x",
            filename="Pillar_1_Comprehensive_Capability_Mapping_v7.0.xlsx",
            version_hint="v7.0",
            bucket_name="dma-test-bucket",
            project_id="dma-test-proj",
        )
    assert out.backing == "gcs"
    assert out.gcs_uri == (
        "gs://dma-test-bucket/v7.0/"
        "Pillar_1_Comprehensive_Capability_Mapping_v7.0.xlsx"
    )
    assert out.workbooks_dir_arg == "gs://dma-test-bucket/v7.0/"
    # The version_hint is normalised to a `vX.Y/` prefix (strip then
    # re-add the leading 'v' so 'v7.0' and '7.0' both land at v7.0/).
    assert captured["gcs_object"].startswith("v7.0/")


def test_content_type_guessed_from_extension():
    """xlsx → openxml content-type; zip → application/zip; other →
    octet-stream. Locked so a future operator uploading a `.tar.gz`
    by mistake doesn't get mislabeled as xlsx in the Cloud Storage
    object metadata."""
    from app.services.catalogue_staging import _guess_content_type

    assert _guess_content_type("Pillar_1.xlsx") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert _guess_content_type("Pillar_bundle.zip") == "application/zip"
    assert _guess_content_type("unexpected.txt") == "application/octet-stream"
    # Case-insensitive on the extension.
    assert _guess_content_type("FOO.XLSX") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ── Route shape locks ─────────────────────────────────────────────────


def test_route_uses_cloud_run_dispatch_not_pubsub():
    """The refactored `/admin/catalogue:upload` route must dispatch via
    `cloud_run_dispatch.dispatch_job` (direct Cloud Run Jobs Run API)
    and MUST NOT use `publish_admin_job_trigger` (Pub/Sub to a topic
    with no subscriber — the original silent-no-op bug).

    Greps the source for both call sites.
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text()
    upload_block_start = src.find("async def upload_catalogue")
    upload_block_end = src.find("async def approve_catalogue_run", upload_block_start)
    assert upload_block_start != -1 and upload_block_end != -1, (
        "upload_catalogue route not found"
    )
    block = src[upload_block_start:upload_block_end]

    assert "dispatch_job" in block, (
        "upload_catalogue must call cloud_run_dispatch.dispatch_job — "
        "Cloud Run Jobs Run API is the only path that actually triggers "
        "the ccg_loader Cloud Run Job. The legacy Pub/Sub approach was "
        "a silent no-op because no subscriber consumed the topic."
    )
    assert "publish_admin_job_trigger" not in block, (
        "upload_catalogue must NOT call publish_admin_job_trigger — "
        "that publishes to admin-job-triggered, which has NO subscriber. "
        "Use dispatch_job instead."
    )
    # The dispatch must pass --version and --workbooks-dir.
    assert "--version" in block and "--workbooks-dir" in block, (
        "dispatch_args must include --version and --workbooks-dir; "
        "ccg_loader's argparse marks both `required=True` and exits "
        "rc=2 if either is missing"
    )


def test_route_uploads_to_gcs_via_staging_helper():
    """The route must delegate to `upload_workbook_to_staging` so
    workbooks land in the GCS bucket the ccg_loader reads from."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text()
    upload_block = src[
        src.find("async def upload_catalogue"):
        src.find("async def approve_catalogue_run")
    ]
    assert "upload_workbook_to_staging" in upload_block, (
        "upload_catalogue must call upload_workbook_to_staging — "
        "the staging helper is what knows how to use the GCS bucket "
        "the ccg_loader Cloud Run Job is configured to read"
    )
    # And reference the bucket via settings (so terraform changes
    # cascade automatically).
    assert "gcs_bucket_catalogue_staging" in upload_block, (
        "upload_catalogue must read the bucket name from "
        "settings.gcs_bucket_catalogue_staging — never hard-code "
        "the bucket name so cross-env (prod/dev/test) is clean"
    )


def test_route_marks_job_failed_on_dispatch_failure():
    """When the Cloud Run dispatch fails (e.g. project_id missing,
    job not in registry, IAM denied), the job_executions row MUST be
    marked status='failed' with a precise error_message — otherwise
    the admin UI shows 'running' forever for a job that will never
    actually run."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text()
    upload_block = src[
        src.find("async def upload_catalogue"):
        src.find("async def approve_catalogue_run")
    ]
    # The post-dispatch failure path must UPDATE the row to status=failed.
    assert "status='failed'" in upload_block, (
        "dispatch failure path must mark the row failed; otherwise it "
        "stays 'running' forever and the admin UI is misleading"
    )
    assert "dispatch_failed:" in upload_block, (
        "the error_message must carry a `dispatch_failed:` prefix so "
        "the admin UI can distinguish dispatch-level failures from "
        "worker-level failures"
    )
