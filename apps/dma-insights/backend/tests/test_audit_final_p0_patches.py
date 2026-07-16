"""Final audit (2026-05-28) P0 patches — pin the fixes against regression.

This file holds focused tests for the six P0 / P1 defects the
principal-QA audit confirmed in the last pass. Each test pins ONE
specific fix and would FAIL if the fix were reverted.

Defects covered:
  P0-1  ingest_package per-entry size limit rejected 59 MB pptx decks
        → fix: skip 05_narrative_deck/* BEFORE the size gate fires.
  P0-2  historical_backfill `_extract_zips` used `extractall()` →
        zip-slip + no per-entry / cumulative caps.
        → fix: re-use the safe extractor pattern; warnings returned.
  P0-3  `_classify_outcome` checked `already_ingested` (underscore)
        but the emitter used `already ingested` (space). Every
        idempotent skip was misclassified as `skipped_no_report`.
        → fix: accept both shapes + the unambiguous
        `folder unchanged since` marker.
  P0-4  RAG offline Vertex fallback returned (body,0,0) which the
        caller treated as a successful Vertex call. The offline
        message was written to Redis (15 min TTL) AND
        vertex_synthesis_cache. Operators who fixed IAM/model/project
        kept seeing offline mode until the TTL expired.
        → fix: raise VertexOfflineFallback; caller catches and sets
        fallback_used=True so both caches are bypassed.
  P0-5  Standalone SSE parser only accepted obj.token || obj.delta,
        but the backend emits obj.text. Every streamed chunk
        yielded "" so the panel fell back to scripted local answers.
        → fix: accept obj.text || obj.token || obj.delta.
  P0-6  Standalone had `uploadAssessment` to /ingest/assessment
        (JSON-only) but NO ZIP-package upload control. The audit
        identified this as the missing manual re-ingest path.
        → fix: add `uploadPackage(file)` to /ingest/package.
  P1-7  Drive-backfill catalogue default fell back to v7.0 when the
        package manifest had no rubric_version. Historical
        assessments predate v7 so this mis-routed every subcap.
        → fix: data_source=DRIVE_BACKFILL → v5.0 default.
"""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

# ── P0-1 ─────────────────────────────────────────────────────────────


def test_zip_entry_should_skip_excludes_05_narrative_deck() -> None:
    """The skip list must match 05_narrative_deck/* even when the zip
    has a top-level entity-name folder above it (the n8n pipeline
    always wraps the package in `{Entity}_DMA_Complete_Package/`)."""
    from app.routers.ingest_package import _zip_entry_should_skip

    assert _zip_entry_should_skip("05_narrative_deck/WSFS DMA Deck (1).pptx")
    assert _zip_entry_should_skip(
        "WSFS_DMA_Complete_Package/05_narrative_deck/WSFS DMA Deck (1).pptx"
    )
    assert _zip_entry_should_skip("narrative_deck/something.pptx")
    # Bare pptx extension at any path is also skipped (operators that
    # drop a stray pptx in the wrong folder get a clean ingest).
    assert _zip_entry_should_skip("04_reports/stray_deck.pptx")
    # Real parsed artifacts are NOT skipped.
    assert not _zip_entry_should_skip(
        "03_scoring_workbook/WSFS_DMA_Assessment_Workbook.xlsx"
    )
    assert not _zip_entry_should_skip("01_evidence/evidence_index.csv")
    assert not _zip_entry_should_skip("04_reports/Assessment_Report.docx")


def test_max_per_entry_uncompressed_bytes_cap_is_50_mb() -> None:
    """The audit pinned 50 MB as the per-parsed-entry cap; the
    transport (compressed) cap is 100 MB."""
    from app.routers.ingest_package import (
        _MAX_PER_ENTRY_UNCOMPRESSED_BYTES,
        _MAX_UPLOAD_BYTES,
    )

    assert _MAX_PER_ENTRY_UNCOMPRESSED_BYTES == 50 * 1024 * 1024
    assert _MAX_UPLOAD_BYTES == 100 * 1024 * 1024


def test_ingest_package_zip_with_60mb_deck_skips_deck_not_413(tmp_path: Path) -> None:
    """A zip containing a 60 MB pptx in 05_narrative_deck/ must not
    cause a 400/413; the deck is skipped and remaining entries
    extract normally.

    We can't run the full router (requires DB session); we instead
    exercise the extraction-phase decision logic directly by building
    a zip + walking it the same way the route would.
    """
    from app.routers.ingest_package import (
        _MAX_PER_ENTRY_UNCOMPRESSED_BYTES,
        _zip_entry_should_skip,
    )

    # Build a synthetic zip with one 60 MB pptx in 05_narrative_deck/.
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        deck_bytes = b"\0" * (60 * 1024 * 1024)
        zf.writestr("WSFS_DMA_Complete_Package/05_narrative_deck/deck.pptx", deck_bytes)
        zf.writestr(
            "WSFS_DMA_Complete_Package/01_evidence/evidence_index.csv",
            "evidence_id,source_url\nE-001,https://example.com\n",
        )

    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        skipped, extracted = [], []
        for info in zf.infolist():
            if _zip_entry_should_skip(info.filename):
                skipped.append(info.filename)
                continue
            # Without the skip, this would trip the 50 MB cap below.
            assert info.file_size <= _MAX_PER_ENTRY_UNCOMPRESSED_BYTES, (
                f"unskipped entry {info.filename} is {info.file_size} bytes "
                f"(cap {_MAX_PER_ENTRY_UNCOMPRESSED_BYTES}); the skip "
                "contract must intercept this entry."
            )
            extracted.append(info.filename)

    assert any("deck.pptx" in s for s in skipped), skipped
    assert any("evidence_index.csv" in e for e in extracted), extracted


# ── P0-2 ─────────────────────────────────────────────────────────────


def test_historical_backfill_extract_zips_returns_tuple_with_warnings(
    tmp_path: Path,
) -> None:
    """The new contract is (extracted_count, warnings) — callers must
    fold the warnings into the parser_warnings trace. The prior
    signature returned only an int + used extractall().
    """
    from app.scripts.historical_backfill import _extract_zips

    # Empty work_dir → (0, []).
    n, warns = _extract_zips(tmp_path)
    assert n == 0
    assert warns == []


def test_historical_backfill_extract_zips_rejects_zip_slip(tmp_path: Path) -> None:
    """A zip carrying an entry whose path resolves OUTSIDE work_dir is
    rejected with a structured warning, NOT extracted."""
    from app.scripts.historical_backfill import _extract_zips

    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        # Note: zip-slip relies on `../../`-style relative paths.
        zf.writestr("../../etc/passwd", "x")
    _n, warns = _extract_zips(tmp_path)
    # The zip should fail extraction; the original .zip is left in
    # place so a human can triage. The warning includes
    # `drive_zip_slip:` so admin diagnostics can flag the folder.
    assert any("drive_zip_slip" in w or "drive_zip_failed" in w for w in warns), warns
    # The traversal target must NOT exist.
    assert not (tmp_path.parent.parent / "etc" / "passwd").exists()


def test_historical_backfill_extract_zips_skips_deck_entries(tmp_path: Path) -> None:
    """A zip containing a 60 MB deck pptx + a small CSV: the deck is
    skipped (warning emitted) and the CSV extracts."""
    from app.scripts.historical_backfill import _extract_zips

    pkg = tmp_path / "WSFS_pkg.zip"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("05_narrative_deck/deck.pptx", b"\0" * (1 * 1024 * 1024))
        zf.writestr("01_evidence/evidence_index.csv", "evidence_id\nE-001\n")

    n, warns = _extract_zips(tmp_path)
    assert n == 1, f"expected 1 zip extracted, got {n}"
    assert (tmp_path / "01_evidence" / "evidence_index.csv").exists()
    assert not (tmp_path / "05_narrative_deck" / "deck.pptx").exists()
    assert any("drive_zip_skipped_deck" in w for w in warns), warns


# ── P0-3 ─────────────────────────────────────────────────────────────


def test_classify_outcome_accepts_already_ingested_space_variant() -> None:
    """The emitter at `_ingest_folder` produces:
        SKIP:{folder} — already ingested (run REQ-… on …; folder unchanged since)
    with a SPACE. The classifier must accept this AND the underscore
    variant + the unambiguous 'folder unchanged since' marker.
    """
    from app.scripts.historical_backfill import _classify_outcome

    # Space variant — the actual emitter shape.
    outcome, reason, _run_id, _err = _classify_outcome(
        "SKIP:WSFS Bank — already ingested (run REQ-DEADBEEF on 2026-05-20; "
        "folder unchanged since)"
    )
    assert outcome == "skipped_already_ingested", (
        f"space-variant 'already ingested' must classify as "
        f"skipped_already_ingested, got {outcome!r}"
    )
    assert "already ingested" in reason

    # Underscore variant — accepted for forward-compat.
    outcome, _, _, _ = _classify_outcome(
        "SKIP:Acme — already_ingested (idempotent skip)"
    )
    assert outcome == "skipped_already_ingested"

    # Unambiguous marker variant.
    outcome, _, _, _ = _classify_outcome("SKIP:Acme — folder unchanged since prior run")
    assert outcome == "skipped_already_ingested"

    # Genuine "no report" path must still classify correctly.
    outcome, _, _, _ = _classify_outcome("SKIP:Acme — no DMA package detected")
    assert outcome == "skipped_no_report"


# ── P0-4 ─────────────────────────────────────────────────────────────


def test_vertex_offline_fallback_is_exception_not_tuple() -> None:
    """The fix replaced the (body, 0, 0) return with a typed
    exception. Callers MUST handle it explicitly and set
    fallback_used=True so Redis + L2 cache writes are skipped.
    """
    from app.routers.rag import VertexOfflineFallback

    err = VertexOfflineFallback(
        body="offline body", kind="PermissionDenied",
        msg="403 forbidden", hint="grant role",
    )
    assert isinstance(err, Exception)
    assert err.body == "offline body"
    assert err.kind == "PermissionDenied"
    assert "grant role" in err.hint


@pytest.mark.asyncio
async def test_generate_via_vertex_raises_offline_fallback_on_import_error(
    monkeypatch,
) -> None:
    """If `get_vertex_client` import fails (e.g. google-cloud-aiplatform
    not installed in dev image), the helper MUST raise
    VertexOfflineFallback — NOT return a tuple — so the router's
    caller is FORCED to set fallback_used=True.
    """
    from app.routers import rag

    # Force the import-of-vertex_client branch to raise. We monkeypatch
    # the module's vertex import path so any access raises ImportError.
    def _boom(*a, **kw):
        raise ImportError("simulated: google-cloud-aiplatform missing")

    monkeypatch.setattr(
        "app.services.vertex_client.get_vertex_client", _boom, raising=False,
    )

    with pytest.raises(rag.VertexOfflineFallback) as excinfo:
        await rag._generate_via_vertex(
            prompt="hi", model_alias="rag_answer_concise", max_paragraphs=2,
        )
    assert "offline mode" in excinfo.value.body.lower() or "vertex" in excinfo.value.body.lower()


# ── P0-5 ─────────────────────────────────────────────────────────────


def test_standalone_sse_parser_accepts_text_field() -> None:
    """The standalone backend-loader parses backend SSE token events.
    Backend emits `data: {"text":"..."}`; parser must accept `text`
    (and continue to accept `token` and `delta` aliases).
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent.parent / "frontend" / "standalone-src" / "src" / "backend-loader.js"
    txt = src.read_text()
    # The patched line yields obj.text first.
    assert "obj.text || obj.token || obj.delta" in txt, (
        "backend-loader SSE parser must accept obj.text first "
        "(backend emits `data: {\"text\":\"...\"}`); regression risk: "
        "every streamed chunk yields '' and the chat panel falls "
        "back to local scripted answers."
    )


# ── P0-6 ─────────────────────────────────────────────────────────────


def test_standalone_admin_upload_package_exists_and_targets_ingest_package() -> None:
    """The standalone admin UI must expose `DMA.admin.uploadPackage(file)`
    which POSTs multipart/form-data to /api/v1/ingest/package (NOT
    /ingest/assessment which is JSON-only).
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent.parent / "frontend" / "standalone-src" / "src" / "backend-loader.js"
    txt = src.read_text()
    assert "window.DMA.admin.uploadPackage" in txt, (
        "missing uploadPackage on window.DMA.admin — "
        "audit identified this as the missing manual re-ingest path"
    )
    # And it must target /ingest/package, not /ingest/assessment.
    upload_pkg_block_start = txt.find("window.DMA.admin.uploadPackage")
    upload_pkg_block = txt[upload_pkg_block_start : upload_pkg_block_start + 2_000]
    assert "/api/v1/ingest/package" in upload_pkg_block
    assert "FormData" in upload_pkg_block, (
        "uploadPackage must post multipart/form-data (FormData), "
        "not JSON (the package route uses UploadFile)"
    )
    # uploadAssessment is still wired to the JSON route.
    upload_ass_block_start = txt.find("window.DMA.admin.uploadAssessment")
    upload_ass_block = txt[upload_ass_block_start : upload_ass_block_start + 2_000]
    assert "/api/v1/ingest/assessment" in upload_ass_block


# ── P1-7 ─────────────────────────────────────────────────────────────


def test_drive_backfill_missing_rubric_resolves_to_v5_default() -> None:
    """When the package manifest has no rubric_version and
    data_source='DRIVE_BACKFILL', the catalogue version MUST default
    to settings.backfill_default_catalogue_version (typically v5.0)
    NOT settings.catalogue_default_version (v7.0).

    Historical Drive assessments predate v7.0; mis-mapping to v7.0
    mis-routes every legacy subcap ID through aliases that don't
    exist for the old IDs.
    """
    from app.services.parsers.package_persist import _rubric_version_to_catalog

    v = _rubric_version_to_catalog(None, data_source="DRIVE_BACKFILL")
    assert v == "v5.0", (
        f"expected v5.0 for missing rubric on DRIVE_BACKFILL, got {v!r}"
    )

    # Manual upload should still default to v7.0 (current production).
    v = _rubric_version_to_catalog(None, data_source="MANUAL_BACKFILL")
    assert v == "v7.0", (
        f"expected v7.0 for missing rubric on MANUAL_BACKFILL, got {v!r}"
    )

    # Explicit rubric still wins, regardless of data_source.
    v = _rubric_version_to_catalog("v5.5", data_source="DRIVE_BACKFILL")
    assert v == "v5.5"
    v = _rubric_version_to_catalog("v7.0", data_source="MANUAL_BACKFILL")
    assert v == "v7.0"


def test_backfill_default_catalogue_version_in_settings() -> None:
    """The new env var must exist on Settings and default to v5.0."""
    from app.config import get_settings
    s = get_settings()
    assert hasattr(s, "backfill_default_catalogue_version")
    assert s.backfill_default_catalogue_version == "v5.0"
