"""Raw-artifact store — "download into the database, process, then compress".

Part 12.2: nothing raw was persisted before this service — package files
died with the tmp dir, every re-parse meant a re-download, and
provenance stopped at ``import_files`` metadata. This module persists
the package's material byte-streams into ``raw_artifacts`` (migration
049) so ALL parsing can read from DB bytes: re-parse without
re-download, deterministic re-ingest, exact artifact→section→field
provenance.

Contract
--------
- Cosmetic artifacts (decks, PNGs, OS cruft — the
  ``artifact_manifest`` COSMETIC class) are never stored.
- Text-likes (json/csv/md/txt/…) compress with zstandard level 9
  (measured corpus ratios: JSON -78%, CSV -72%, MD -51%, TXT -64%).
  Already-compressed containers (docx/xlsx/pdf/zip) store codec='none'.
- Global dedup on sha256: the same peer JSON shipped by N packages
  stores ONCE; ``first_seen_run``/``last_seen_run`` track the lineage
  window (ON CONFLICT (sha256) DO UPDATE last_seen_run).
- ``load_artifact`` returns the original bytes (transparent
  decompression) by sha256 or row id.

Batched writes: one SELECT for existing hashes, one UPDATE for
last_seen_run bumps, one executemany INSERT for new rows — never one
round-trip per file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text

from app.services.artifact_manifest import COSMETIC, classify_path

# zstandard is a declared dependency (pyproject + both Dockerfiles), but a
# module-level hard import took the WHOLE ingest chain down when an image
# shipped without it (2026-07-04 CI live-PG stage). Belt-and-braces like
# nlp/similarity: degrade to stdlib gzip for writes (the codec column
# already speaks gzip) and fail with a clear message only if asked to READ
# a zstd row without the library.
try:
    import zstandard
except ImportError:  # pragma: no cover - exercised via _zstd_or_none()
    zstandard = None  # type: ignore[assignment]

log = structlog.get_logger()

ZSTD_LEVEL = 9
GZIP_LEVEL = 6

# Suffix → codec. Everything else defaults to zstd (text-leaning corpus)
# unless it's a known already-compressed container.
_NONE_CODEC_SUFFIXES = frozenset({
    ".docx", ".doc", ".xlsx", ".xlsm", ".xls", ".pdf", ".zip",
    ".pptx", ".ppt", ".gz", ".zst",
})

# Files above this size are skipped (raw store is for the material text
# layer + reports; a stray 500 MB evidence video does not belong in
# Postgres).
MAX_STORED_BYTES = 48 * 1024 * 1024


def _file_kind(rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower().lstrip(".")
    return (suffix or "unknown")[:32]


def _codec_for(rel_path: str) -> str:
    if Path(rel_path).suffix.lower() in _NONE_CODEC_SUFFIXES:
        return "none"
    return "zstd" if zstandard is not None else "gzip"


def compress_payload(raw: bytes, codec: str) -> bytes:
    if codec == "zstd":
        if zstandard is None:
            raise RuntimeError(
                "zstandard not installed — _codec_for never selects zstd "
                "in this state; pass codec='gzip' or install zstandard")
        return zstandard.ZstdCompressor(level=ZSTD_LEVEL).compress(raw)
    if codec == "gzip":
        import gzip
        return gzip.compress(raw, compresslevel=GZIP_LEVEL)
    return raw


def decompress_payload(stored: bytes, codec: str) -> bytes:
    if codec == "zstd":
        if zstandard is None:
            raise RuntimeError(
                "raw_artifacts row is zstd-compressed but zstandard is not "
                "installed — install the declared dependency "
                "(pyproject: zstandard) to read this artifact")
        return zstandard.ZstdDecompressor().decompress(stored)
    if codec == "gzip":
        import gzip
        return gzip.decompress(stored)
    return stored


_INSERT_SQL = """
    INSERT INTO raw_artifacts (
        entity_id, run_id, rel_path, file_kind, materiality,
        sha256, size_raw, size_stored, codec, content,
        first_seen_run, last_seen_run
    ) VALUES (
        CAST(:eid AS uuid), CAST(:rid AS uuid), :rel, :kind, :mat,
        :sha, :size_raw, :size_stored, :codec, :content,
        CAST(:rid AS uuid), CAST(:rid AS uuid)
    )
    ON CONFLICT (sha256) DO UPDATE SET
        last_seen_run = EXCLUDED.last_seen_run
"""


async def store_package(
    session: Any,
    *,
    entity_id: str,
    run_id: str,
    root_path: str | Path,
) -> dict[str, int]:
    """Walk ``root_path`` and persist every material artifact.

    Returns counters: ``{stored, deduped, skipped_cosmetic,
    skipped_oversize, bytes_raw, bytes_stored}``. Caller commits.
    """
    root = Path(root_path)
    counters = {
        "stored": 0, "deduped": 0, "skipped_cosmetic": 0,
        "skipped_oversize": 0, "bytes_raw": 0, "bytes_stored": 0,
    }
    if not root.is_dir():
        return counters

    candidates: list[tuple[str, Path]] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            continue
        if classify_path(rel) == COSMETIC:
            counters["skipped_cosmetic"] += 1
            continue
        try:
            if f.stat().st_size > MAX_STORED_BYTES:
                counters["skipped_oversize"] += 1
                continue
        except OSError:
            continue
        candidates.append((rel, f))

    if not candidates:
        return counters

    # Hash pass (also dedups identical files WITHIN the package).
    by_sha: dict[str, tuple[str, bytes]] = {}
    for rel, f in candidates:
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        sha = hashlib.sha256(raw).hexdigest()
        if sha not in by_sha:
            by_sha[sha] = (rel, raw)

    if not by_sha:
        return counters

    # One batched lookup for globally-deduped hashes.
    existing = {
        row.sha256 for row in (await session.execute(
            text(
                "SELECT sha256 FROM raw_artifacts "
                "WHERE sha256 = ANY(:hashes)"
            ),
            {"hashes": list(by_sha.keys())},
        )).all()
    }

    if existing:
        await session.execute(
            text(
                "UPDATE raw_artifacts "
                "SET last_seen_run = CAST(:rid AS uuid) "
                "WHERE sha256 = ANY(:hashes)"
            ),
            {"rid": str(run_id), "hashes": list(existing)},
        )
        counters["deduped"] = len(existing)

    rows: list[dict] = []
    for sha, (rel, raw) in by_sha.items():
        if sha in existing:
            continue
        codec = _codec_for(rel)
        stored = compress_payload(raw, codec)
        # zstd on an already-dense payload can inflate — keep whichever
        # representation is smaller (codec reflects what's stored).
        if codec == "zstd" and len(stored) >= len(raw):
            codec, stored = "none", raw
        rows.append({
            "eid": str(entity_id),
            "rid": str(run_id),
            "rel": rel,
            "kind": _file_kind(rel),
            "mat": "MATERIAL",
            "sha": sha,
            "size_raw": len(raw),
            "size_stored": len(stored),
            "codec": codec,
            "content": stored,
        })
        counters["bytes_raw"] += len(raw)
        counters["bytes_stored"] += len(stored)

    if rows:
        await session.execute(text(_INSERT_SQL), rows)
        counters["stored"] = len(rows)

    log.info(
        "raw_artifact_store.stored",
        entity_id=str(entity_id), run_id=str(run_id),
        **counters,
    )
    return counters


async def load_artifact(
    session: Any,
    *,
    sha256: str | None = None,
    artifact_id: str | None = None,
) -> bytes | None:
    """Fetch + transparently decompress one stored artifact's bytes.

    Lookup by ``sha256`` (global dedup key) or row ``artifact_id``;
    returns None when not found.
    """
    if not sha256 and not artifact_id:
        raise ValueError("load_artifact requires sha256 or artifact_id")
    if sha256:
        sql = "SELECT codec, content FROM raw_artifacts WHERE sha256 = :key"
        params: dict[str, Any] = {"key": sha256}
    else:
        sql = (
            "SELECT codec, content FROM raw_artifacts "
            "WHERE id = CAST(:key AS uuid)"
        )
        params = {"key": str(artifact_id)}
    row = (await session.execute(text(sql), params)).first()
    if row is None:
        return None
    return decompress_payload(bytes(row.content), row.codec)
