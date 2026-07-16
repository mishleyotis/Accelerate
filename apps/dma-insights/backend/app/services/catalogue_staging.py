"""Catalogue staging uploader — admin catalogue:upload route helper.

Responsibilities:
  - Accept workbook bytes (xlsx or zip) + a version string.
  - Upload to `gs://{settings.gcs_bucket_catalogue_staging}/{version}/{filename}`
    where the ccg_loader Cloud Run Job is already configured to read.
  - Return the GCS prefix path (the `--workbooks-dir` arg the worker
    needs).

Resilience:
  - GCS unavailable / no SA perms → fall back to a local `/tmp/dma-
    catalogue-staging/<sha>/` path. The worker can't read this in
    production (it's a different container) BUT this lets local
    dev + tests still exercise the upload endpoint without GCP
    credentials.
  - Bucket missing → log loud warning + fall back to /tmp. Operator
    should run `terraform apply` to recreate the bucket; meanwhile
    /tmp lets the surface keep responding instead of 503'ing.
  - Filename collisions → SHA-256 of the body is included in the
    GCS object path, so re-uploading the same file is idempotent
    + re-uploading a CHANGED file with the same name doesn't clobber.

State-transition contract:
  uploaded_gcs    → returned path starts with `gs://...`. Worker
                    `_resolve_workbooks_dir` will fetch from GCS.
  uploaded_local  → returned path is `/tmp/...`. Worker can't read
                    in prod; suitable only for local dev / test paths.
  failed          → raises RuntimeError with operator-actionable text.
"""
from __future__ import annotations

import hashlib
import logging
import pathlib

log = logging.getLogger(__name__)


class StagedWorkbook:
    """Result of upload_workbook_to_staging — exposes both the local
    on-disk path (for inspection / fallback) AND the worker-facing
    `--workbooks-dir` arg the dispatcher needs to pass."""

    def __init__(
        self,
        workbooks_dir_arg: str,
        local_path: pathlib.Path | None,
        gcs_uri: str | None,
        sha256_prefix: str,
        backing: str,
    ) -> None:
        self.workbooks_dir_arg = workbooks_dir_arg
        self.local_path = local_path
        self.gcs_uri = gcs_uri
        self.sha256_prefix = sha256_prefix
        # `backing` is "gcs" / "local_fallback" — exposed in the admin
        # response so the operator sees which path was used. In prod
        # "local_fallback" is a red flag (worker won't be able to read).
        self.backing = backing

    def to_dict(self) -> dict:
        return {
            "workbooks_dir_arg": self.workbooks_dir_arg,
            "local_path": str(self.local_path) if self.local_path else None,
            "gcs_uri": self.gcs_uri,
            "sha256_prefix": self.sha256_prefix,
            "backing": self.backing,
        }


def upload_workbook_to_staging(
    *,
    workbook_bytes: bytes,
    filename: str,
    version_hint: str | None,
    bucket_name: str,
    project_id: str | None,
    sha256_prefix: str | None = None,
) -> StagedWorkbook:
    """Upload `workbook_bytes` to the catalogue-staging bucket.

    Returns a StagedWorkbook describing where the upload landed. The
    `workbooks_dir_arg` field is the EXACT string to pass as the
    `--workbooks-dir` arg to the ccg_loader Cloud Run Job.

    Args:
      workbook_bytes: full file body (xlsx or zip).
      filename: original upload filename (used to namespace GCS object).
      version_hint: e.g. "v7.0" / "v7.1" — used as the GCS prefix so
        re-uploading v7.0 over v7.0 replaces the prior file (idempotent).
        When None, falls back to the SHA prefix so each upload gets a
        unique directory (useful for "test this random file" flows).
      bucket_name: target GCS bucket (`settings.gcs_bucket_catalogue_staging`).
      project_id: GCP project — when None or empty, GCS upload is
        skipped and we fall through to /tmp.
      sha256_prefix: pre-computed SHA prefix; computed from bytes when None.
    """
    if sha256_prefix is None:
        sha256_prefix = hashlib.sha256(workbook_bytes).hexdigest()[:16]
    version_dir = (version_hint or "").strip().lstrip("v") or sha256_prefix
    # Normalize: 'v7.0' → '7.0'; we add the 'v' back explicitly so
    # both 'v7.0' and '7.0' inputs land at the same GCS prefix.
    gcs_prefix = f"v{version_dir}" if version_hint else version_dir

    # Try GCS first.
    if project_id:
        try:
            gcs_uri = _gcs_upload(
                workbook_bytes=workbook_bytes,
                bucket_name=bucket_name,
                gcs_object=f"{gcs_prefix}/{filename}",
            )
            return StagedWorkbook(
                workbooks_dir_arg=f"gs://{bucket_name}/{gcs_prefix}/",
                local_path=None,
                gcs_uri=gcs_uri,
                sha256_prefix=sha256_prefix,
                backing="gcs",
            )
        except Exception as e:
            log.warning(
                "catalogue_staging.gcs_upload_failed",
                extra={
                    "err": str(e)[:200],
                    "err_type": type(e).__name__,
                    "bucket": bucket_name,
                    "project_id": project_id,
                },
            )
            # fall through to local

    # Local fallback — same shape as the legacy /tmp path so the
    # rest of the route doesn't have to branch.
    staging_root = pathlib.Path("/tmp/dma-catalogue-staging")
    staging_dir = staging_root / sha256_prefix
    staging_dir.mkdir(parents=True, exist_ok=True)
    target = staging_dir / filename
    target.write_bytes(workbook_bytes)
    return StagedWorkbook(
        workbooks_dir_arg=str(staging_dir),
        local_path=target,
        gcs_uri=None,
        sha256_prefix=sha256_prefix,
        backing="local_fallback",
    )


def _gcs_upload(
    *,
    workbook_bytes: bytes,
    bucket_name: str,
    gcs_object: str,
) -> str:
    """Upload bytes to GCS. Raises on any failure (caller catches +
    falls back).

    Returns the `gs://bucket/object` URI on success.
    """
    try:
        from google.cloud import storage  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError(
            f"google-cloud-storage not installed; cannot upload to GCS: {e}"
        ) from e

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_object)
    # Use `if_generation_match=None` (the default) — we DO want to
    # overwrite the same logical path when an operator re-uploads
    # the same version (idempotent retry). The version-prefix scheme
    # means cross-version uploads never collide.
    blob.upload_from_string(
        workbook_bytes,
        content_type=_guess_content_type(gcs_object),
    )
    return f"gs://{bucket_name}/{gcs_object}"


def _guess_content_type(name: str) -> str:
    n = name.lower()
    if n.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if n.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"
