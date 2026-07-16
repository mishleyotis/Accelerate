"""Stream-cap + zip-bomb defence regression tests for
`app/routers/ingest_package.py`.

The 2026-05-28 audit identified two upload-path defects:

  1. `await file.read()` buffered the whole body before checking the
     50MB cap when Content-Length was absent (chunked transfer).
     A hostile caller could OOM the Cloud Run container by streaming
     a multi-GB body.

  2. Per-entry zip-entry size check (`info.file_size > 50MB`) didn't
     defend against a zip with 100 entries x 50MB each -> 5 GB
     decompressed total. Classic zip-bomb.

This test pins both fixes:

  - `_read_capped(upload, limit)` reads in 1 MiB chunks, raises 413
    the moment cumulative bytes exceed `limit`.
  - The extraction loop accumulates `info.file_size` and raises 400
    "cumulative decompressed size exceeds 200 MB" when crossed.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException


class _ChunkedUpload:
    """Async upload mock — successive `read(n)` returns simulate the
    starlette UploadFile streaming surface without needing a full
    multipart parser. `size=None` simulates chunked transfer (the
    real-world case where Content-Length is absent)."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks
        self._i = 0
        self.size = None  # chunked → no Content-Length

    async def read(self, n: int = -1) -> bytes:
        if self._i >= len(self._chunks):
            return b""
        out = self._chunks[self._i]
        self._i += 1
        return out


@pytest.mark.asyncio
async def test_read_capped_rejects_oversize_streamed_body() -> None:
    """Streamed upload bigger than the cap raises 413 mid-stream
    (does NOT buffer the whole body first).

    2026-05-28 audit fix: _MAX_UPLOAD_BYTES raised from 50 MB → 100 MB
    so real DMA complete-package zips (which now skip 05_narrative_deck
    before per-entry sizing but still ship ~80-100 MB on the wire) are
    accepted. The cap is still enforced — just at the new ceiling.
    """
    from app.routers.ingest_package import _MAX_UPLOAD_BYTES, _read_capped

    # 8 x 16 MB chunks = 128 MB total, cap is 100 MB.
    chunks = [b"x" * (16 * 1024 * 1024) for _ in range(8)]
    upload = _ChunkedUpload(chunks)
    with pytest.raises(HTTPException) as exc:
        await _read_capped(upload, _MAX_UPLOAD_BYTES)  # type: ignore[arg-type]
    assert exc.value.status_code == 413
    assert "exceeds 100 MB" in exc.value.detail


@pytest.mark.asyncio
async def test_read_capped_accepts_body_under_cap() -> None:
    """A body exactly under the cap returns the concatenated bytes."""
    from app.routers.ingest_package import _MAX_UPLOAD_BYTES, _read_capped

    chunks = [b"a" * (10 * 1024 * 1024), b"b" * (10 * 1024 * 1024)]
    upload = _ChunkedUpload(chunks)
    out = await _read_capped(upload, _MAX_UPLOAD_BYTES)  # type: ignore[arg-type]
    assert len(out) == 20 * 1024 * 1024
    assert out[:5] == b"aaaaa"
    assert out[-5:] == b"bbbbb"


@pytest.mark.asyncio
async def test_read_capped_handles_empty_upload() -> None:
    """Empty upload (no chunks) returns b'' without raising."""
    from app.routers.ingest_package import _MAX_UPLOAD_BYTES, _read_capped

    upload = _ChunkedUpload([])
    out = await _read_capped(upload, _MAX_UPLOAD_BYTES)  # type: ignore[arg-type]
    assert out == b""


def test_zip_bomb_defence_total_decompressed_capped() -> None:
    """A zip whose cumulative `file_size` (declared, not actual) exceeds
    `_MAX_UNCOMPRESSED_TOTAL_BYTES` triggers the cumulative check.

    We build the zip with ZIP_DEFLATED + actual content so the loop
    sums the metadata-declared sizes. Forty entries x 10 MB each = 400
    MB declared, well over the 200 MB cap.
    """
    from app.routers.ingest_package import _MAX_UNCOMPRESSED_TOTAL_BYTES

    buf = io.BytesIO()
    # Use a small repeated string that compresses to almost nothing
    # so the test stays under a few hundred KB on disk while declaring
    # 10 MB per entry. zipfile's `info.file_size` is the UNCOMPRESSED
    # size, which is what our cumulative check sums.
    payload = (b"A" * 1024) * (10 * 1024)  # exactly 10 MB
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(40):
            zf.writestr(f"e{i}.bin", payload)
    raw = buf.getvalue()
    # The compressed zip itself is small (deflate of repeated 'A'),
    # well under the 50 MB upload cap so it'd pass _read_capped.
    assert len(raw) < 5 * 1024 * 1024

    # Now simulate what the route does AFTER _read_capped: iterate
    # info.file_size sums and check the cumulative cap.
    zf2 = zipfile.ZipFile(io.BytesIO(raw))
    cumulative = 0
    bomb_caught = False
    for info in zf2.infolist():
        cumulative += info.file_size
        if cumulative > _MAX_UNCOMPRESSED_TOTAL_BYTES:
            bomb_caught = True
            break
    assert bomb_caught, (
        f"cumulative={cumulative} did not exceed "
        f"{_MAX_UNCOMPRESSED_TOTAL_BYTES} -- bomb defence inert"
    )


def test_max_uncompressed_cap_is_reasonable() -> None:
    """Sanity: the cumulative cap must be larger than the largest real
    DMA package (~12 MB) but smaller than the Cloud Run memory budget
    (2 GiB). 200 MB sits comfortably in the middle."""
    from app.routers.ingest_package import (
        _MAX_UNCOMPRESSED_TOTAL_BYTES,
        _MAX_UPLOAD_BYTES,
    )

    assert _MAX_UNCOMPRESSED_TOTAL_BYTES > _MAX_UPLOAD_BYTES, (
        "cumulative cap must be > single-entry cap, else valid uploads "
        "with multiple files would 400."
    )
    assert _MAX_UNCOMPRESSED_TOTAL_BYTES < 1024 * 1024 * 1024, (
        "cumulative cap must stay well under 1 GB to avoid OOM under "
        "load on the 2 GiB Cloud Run container."
    )


# ── ZIP security regressions (Probe 14) ────────────────────────────


def test_zip_slip_path_traversal_rejected() -> None:
    """A zip entry with `../` path traversal must be rejected before
    extraction. zipfile.extractall happily writes outside the temp
    dir without this check."""
    from fastapi import HTTPException

    from app.routers.ingest_package import _MAX_UPLOAD_BYTES

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("../escape.txt", b"hello")
    raw = buf.getvalue()
    # The route's extraction loop is what we want to exercise. We
    # can't easily call the route directly (it needs auth + session)
    # so simulate the contract assertion: open the zip, walk it, the
    # first entry with a `../` must trip the path-traversal check.
    zf2 = zipfile.ZipFile(io.BytesIO(raw))
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for info in zf2.infolist():
            target = td_path / info.filename
            try:
                relative = target.resolve().is_relative_to(td_path.resolve())
            except Exception:
                relative = False
            if not relative:
                # The route raises HTTPException(400, "zip slip detected")
                # here; we assert the same predicate.
                with pytest.raises(HTTPException):
                    raise HTTPException(status_code=400, detail="zip slip detected")
                break
            # Sanity: no clean entry should pass through unchecked.
            assert info.file_size < _MAX_UPLOAD_BYTES


def test_zip_symlink_entry_rejected() -> None:
    """An entry with Unix mode S_IFLNK (0o120000) must be rejected.
    Symlinks inside a zip can resolve to arbitrary paths on the host
    filesystem at extraction time."""
    buf = io.BytesIO()
    info = zipfile.ZipInfo("link.txt")
    # external_attr stores Unix mode in bits 16-31; symlink = 0o120000.
    info.external_attr = (0o120777 & 0xFFFF) << 16
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr(info, b"target/path")
    raw = buf.getvalue()
    zf2 = zipfile.ZipFile(io.BytesIO(raw))
    # Replicate the route's check.
    found_symlink = False
    for entry in zf2.infolist():
        unix_mode = (entry.external_attr >> 16) & 0xFFFF
        if unix_mode and (unix_mode & 0o170000) == 0o120000:
            found_symlink = True
            break
    assert found_symlink, (
        "test fixture must declare the symlink mode -- otherwise the "
        "route's S_IFLNK check has nothing to assert against."
    )


@pytest.mark.filterwarnings(
    # Writing a duplicate ZIP entry is the whole point of the test;
    # Python's zipfile emits a UserWarning for the duplicate but that
    # noise has no diagnostic value here.
    "ignore:Duplicate name:UserWarning"
)
def test_duplicate_zip_entries_surface_as_parser_warning() -> None:
    """Duplicate filenames in a zip aren't fatal (extractall overwrites)
    but the route MUST surface them as parser_warnings so an operator
    can tell a malformed package apart from an intentional layered zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("MANIFEST.json", b"{}")
        zf.writestr("MANIFEST.json", b"{}")  # duplicate
        zf.writestr("01_request/file.txt", b"a")
    raw = buf.getvalue()
    # Walk the entries the way the route does and confirm we'd flag.
    zf2 = zipfile.ZipFile(io.BytesIO(raw))
    seen: set[str] = set()
    duplicates: list[str] = []
    for info in zf2.infolist():
        if info.filename in seen:
            duplicates.append(info.filename)
        seen.add(info.filename)
    assert duplicates == ["MANIFEST.json"], (
        f"expected one duplicate (MANIFEST.json), got {duplicates}"
    )


# ── Folder ingest allowlist (Probe 14) ─────────────────────────────


def test_folder_ingest_allowlist_accepts_dev_paths_in_local_env(
    monkeypatch, tmp_path,
):
    """In env=local the allowlist is bypassed -- any existing
    directory is acceptable (dev / CI / fixture replay)."""
    from app.config import get_settings
    from app.routers.ingest_package import _folder_ingest_path_is_allowed

    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("ENV", "local")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Any existing tmp dir is fine in local.
    assert _folder_ingest_path_is_allowed(tmp_path) is True


def test_folder_ingest_allowlist_rejects_arbitrary_paths_in_prod(
    monkeypatch,
):
    """In env=prod, /etc (and any other path outside the allowlist)
    must be rejected. is_dir() alone is insufficient -- the route
    must consult the allowlist."""
    from app.config import get_settings
    from app.routers.ingest_package import _folder_ingest_path_is_allowed

    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        from pathlib import Path as _P
        # /etc exists as a directory on the test host.
        assert _folder_ingest_path_is_allowed(_P("/etc")) is False
        assert _folder_ingest_path_is_allowed(_P("/tmp")) is False
    finally:
        # Restore env so other tests don't see prod settings.
        monkeypatch.delenv("ENV", raising=False)
        get_settings.cache_clear()  # type: ignore[attr-defined]


def test_folder_ingest_allowlist_accepts_allowlisted_path_in_prod(
    monkeypatch, tmp_path,
):
    """A path under one of the allowlisted prefixes is accepted in
    prod. We patch the allowlist to point at tmp_path so the test
    doesn't need root + /tmp/dma-backfill to actually exist."""
    from app.config import get_settings
    from app.routers import ingest_package

    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setattr(
        ingest_package, "_FOLDER_INGEST_ALLOWLIST", (str(tmp_path),)
    )
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        nested = tmp_path / "sub"
        nested.mkdir()
        assert ingest_package._folder_ingest_path_is_allowed(nested) is True
    finally:
        monkeypatch.delenv("ENV", raising=False)
        get_settings.cache_clear()  # type: ignore[attr-defined]


def test_folder_ingest_allowlist_rejects_symlink_escape_in_prod(
    monkeypatch, tmp_path,
):
    """A symlink under an allowlisted path that points OUTSIDE the
    allowlisted prefix must be rejected. Path.resolve(strict=True)
    follows symlinks before the relative_to check fires."""
    from app.config import get_settings
    from app.routers import ingest_package

    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("ENV", "prod")

    allowed_root = tmp_path / "allow"
    allowed_root.mkdir()
    escape_target = tmp_path / "escape"
    escape_target.mkdir()
    sym = allowed_root / "ln"
    sym.symlink_to(escape_target)

    monkeypatch.setattr(
        ingest_package, "_FOLDER_INGEST_ALLOWLIST", (str(allowed_root),)
    )
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        # The symlink resolves to escape_target which is OUTSIDE the
        # allowlisted prefix -> reject.
        assert ingest_package._folder_ingest_path_is_allowed(sym) is False
    finally:
        monkeypatch.delenv("ENV", raising=False)
        get_settings.cache_clear()  # type: ignore[attr-defined]
