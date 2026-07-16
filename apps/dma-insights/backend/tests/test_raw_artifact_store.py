"""Raw-artifact store round-trip tests (Part 12.2).

Covers:
  - pure compress/decompress round-trip (zstd + none codecs)
  - codec selection by suffix (text-likes → zstd; docx/xlsx/pdf → none)
  - live-DB store_package + load_artifact round-trip incl. the
    ON CONFLICT (sha256) global dedup (second run bumps last_seen_run
    instead of duplicating bytes)

Live-DB tests follow the repo convention: skipped unless
DATABASE_URL_SYNC is set (same gate as
tests/test_backfill_skip_path_integration.py).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.services.raw_artifact_store import (
    _codec_for,
    compress_payload,
    decompress_payload,
    load_artifact,
    store_package,
)

# ── pure-logic: codec + round-trip ────────────────────────────────────


def test_zstd_round_trip() -> None:
    raw = ("{" + '"k": "v", ' * 500 + '"end": 1}').encode()
    stored = compress_payload(raw, "zstd")
    assert len(stored) < len(raw)          # JSON compresses hard
    assert decompress_payload(stored, "zstd") == raw


def test_none_codec_round_trip() -> None:
    raw = os.urandom(4096)                 # incompressible
    stored = compress_payload(raw, "none")
    assert stored == raw
    assert decompress_payload(stored, "none") == raw


def test_codec_selection_by_suffix() -> None:
    assert _codec_for("01_evidence/evidence_index.json") == "zstd"
    assert _codec_for("03_scoring_workbook/export_scoring_detail.csv") == "zstd"
    assert _codec_for("08_appendices/report_synthesis.md") == "zstd"
    # Already-compressed containers store verbatim.
    assert _codec_for("04_reports/Assessment_Report.docx") == "none"
    assert _codec_for("03_scoring_workbook/toolkit.xlsx") == "none"
    assert _codec_for("01_evidence/filing.pdf") == "none"


# ── live-DB round-trip + dedup ────────────────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_SYNC"),
    reason="DATABASE_URL_SYNC not set — live-PG raw-artifact tests skipped",
)


def _package_dir(tmp_path: Path) -> Path:
    root = tmp_path / "Raw Test - DMA"
    (root / "01_evidence").mkdir(parents=True)
    (root / "05_narrative_deck").mkdir()
    (root / "01_evidence" / "evidence_index.json").write_text(
        '{"rows": [' + ",".join(['{"e_id": "E-%03d"}' % i for i in range(200)]) + "]}"
    )
    (root / "01_evidence" / "notes.md").write_text("# notes\n" + "line\n" * 200)
    # Cosmetic artifacts must be skipped.
    (root / "05_narrative_deck" / "deck.pptx").write_bytes(b"PPTX")
    (root / "01_evidence" / "chart.png").write_bytes(b"\x89PNG")
    return root


@pytestmark_db
def test_store_package_round_trip_and_global_dedup(tmp_path: Path) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings

    root = _package_dir(tmp_path)

    async def _run() -> None:
        engine = create_async_engine(get_settings().database_url, echo=False)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as session:
                ent = (await session.execute(text(
                    "INSERT INTO entities (name, display_id, status) "
                    "VALUES (:n, :d, 'ACTIVE') RETURNING id"
                ), {"n": "Raw Store Test", "d": f"rawtest-{uuid.uuid4().hex[:8]}"},
                )).scalar()
                run1 = (await session.execute(text(
                    "INSERT INTO runs (entity_id, request_id, data_source, "
                    "evidence_mode, status, ccg_catalog_version, started_at, "
                    "completed_at) "
                    "VALUES (:e, :r, 'MANUAL_BACKFILL', 'public', 'ACTIVE', "
                    "'v7.0', NOW(), NOW()) RETURNING id"
                ), {"e": ent, "r": f"REQ-{uuid.uuid4().hex[:8].upper()}"},
                )).scalar()
                run2 = (await session.execute(text(
                    "INSERT INTO runs (entity_id, request_id, data_source, "
                    "evidence_mode, status, ccg_catalog_version, started_at, "
                    "completed_at) "
                    "VALUES (:e, :r, 'MANUAL_BACKFILL', 'public', 'ACTIVE', "
                    "'v7.0', NOW(), NOW()) RETURNING id"
                ), {"e": ent, "r": f"REQ-{uuid.uuid4().hex[:8].upper()}"},
                )).scalar()

                # First store: both material text files land compressed.
                c1 = await store_package(
                    session, entity_id=str(ent), run_id=str(run1),
                    root_path=root,
                )
                assert c1["stored"] == 2          # json + md
                assert c1["deduped"] == 0
                assert c1["skipped_cosmetic"] >= 2  # deck + png
                assert 0 < c1["bytes_stored"] < c1["bytes_raw"]

                rows = (await session.execute(text(
                    "SELECT rel_path, codec, size_raw, size_stored, sha256 "
                    "FROM raw_artifacts WHERE entity_id = :e ORDER BY rel_path"
                ), {"e": ent})).all()
                assert [r.rel_path for r in rows] == [
                    "01_evidence/evidence_index.json", "01_evidence/notes.md",
                ]
                for r in rows:
                    assert r.codec == "zstd"
                    assert r.size_stored < r.size_raw

                # load_artifact round-trips the ORIGINAL bytes.
                original = (root / "01_evidence" / "evidence_index.json").read_bytes()
                got = await load_artifact(session, sha256=rows[0].sha256)
                assert got == original

                # Second run, same bytes: global dedup — no new rows,
                # last_seen_run bumps to run2.
                c2 = await store_package(
                    session, entity_id=str(ent), run_id=str(run2),
                    root_path=root,
                )
                assert c2["stored"] == 0
                assert c2["deduped"] == 2
                n = (await session.execute(text(
                    "SELECT COUNT(*) FROM raw_artifacts WHERE entity_id = :e"
                ), {"e": ent})).scalar()
                assert n == 2
                last_seen = (await session.execute(text(
                    "SELECT DISTINCT last_seen_run::text FROM raw_artifacts "
                    "WHERE entity_id = :e"
                ), {"e": ent})).scalars().all()
                assert last_seen == [str(run2)]

                # Cleanup (FK cascade from entity removes artifacts +
                # runs). The ACTIVE-entity delete guard requires an
                # archive first.
                await session.execute(
                    text("UPDATE entities SET status='ARCHIVED' WHERE id = :e"),
                    {"e": ent},
                )
                await session.execute(
                    text("DELETE FROM entities WHERE id = :e"), {"e": ent},
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_zstandard_absent_degrades_to_gzip(monkeypatch):
    """The 2026-07-04 CI live-PG stage caught the built image without
    zstandard and the module-level import took the whole ingest chain
    down. Absent-lib contract: new writes degrade to stdlib gzip (the
    codec column already speaks it); reading an existing zstd row fails
    with a clear install message instead of a bare ModuleNotFoundError."""
    from app.services import raw_artifact_store as ras

    monkeypatch.setattr(ras, "zstandard", None)
    assert ras._codec_for("07_data/anything.csv") == "gzip"
    payload = b"material text layer " * 64
    stored = ras.compress_payload(payload, "gzip")
    assert ras.decompress_payload(stored, "gzip") == payload
    with pytest.raises(RuntimeError, match="zstandard"):
        ras.decompress_payload(b"\x28\xb5\x2f\xfd", "zstd")
    with pytest.raises(RuntimeError, match="zstandard"):
        ras.compress_payload(payload, "zstd")
