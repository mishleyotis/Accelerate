"""End-to-end simulation of the crawler's filter + bound path (no real Drive).

Proves the operator's three asks against the actual `_main_body` flow, not just
the pure helpers:
  - it EXCLUDES folders that map to already-ACTIVE clients (the seeded 94),
  - it CAPS the number of new folders ingested per run, and
  - it only ever ingests the NEW, uncapped remainder.

Drive IO + the DB lookup are stubbed so this is fast + hermetic.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.scripts.historical_backfill as hb  # noqa: E402
import app.services.drive_client as drive_client  # noqa: E402
from workers.drive_crawler import main as crawler  # noqa: E402


class _Ex:
    """Stand-in for the runner's execution tracker."""

    def __init__(self) -> None:
        self.counters: dict = {}

    def update(self, **kw) -> None:
        self.counters.update(kw)


def test_main_body_excludes_known_and_caps_new(monkeypatch) -> None:
    # 2 already-ACTIVE clients (must be skipped) + 8 net-new folders.
    known_folders = ["Haventree Bank - DMA", "Zions Bancorporation - DMA"]
    new_folders = [f"Net New Bank {i:02d} - DMA" for i in range(8)]
    all_folders = [{"id": f"id-{n}", "name": n, "modifiedTime": "2026-06-18T00:00:00Z"}
                   for n in (known_folders + new_folders)]

    # Cap small so the test is meaningful + fast.
    monkeypatch.setattr(crawler, "CRAWLER_MAX_FOLDERS", 5)
    monkeypatch.setattr(crawler, "CRAWLER_CONCURRENCY", 4)
    monkeypatch.setattr(crawler, "CRAWLER_DEADLINE_SEC", 60)

    # Stub Drive IO (these are imported lazily inside _main_body).
    monkeypatch.setattr(drive_client, "build_drive_service", lambda: object())
    monkeypatch.setattr(drive_client, "list_dma_folders", lambda svc, root: all_folders)
    monkeypatch.setattr(drive_client, "folder_is_newer_than_watermark",
                        lambda folder, wm: True)
    # The 2 known clients are already ACTIVE in the DB (seeded 'local:…'
    # rows → excluded by name key; the id ledger is empty).
    monkeypatch.setattr(crawler, "_load_known_active_keys",
                        lambda: {crawler._norm_client_key(n) for n in known_folders})
    monkeypatch.setattr(crawler, "_load_ingested_folder_ids", lambda: set())

    ingested: list[str] = []

    async def _fake_ingest(service, folder, tmp_root) -> str:
        ingested.append(folder["name"])
        return f"OK:run-{folder['id']}"

    monkeypatch.setattr(hb, "_ingest_folder", _fake_ingest)

    args = types.SimpleNamespace(once=True, since=None, dry_run=False)
    settings = types.SimpleNamespace(drive_root_folder_id="root-folder")
    ex = _Ex()

    rc = crawler._main_body(args, settings, ex)

    assert rc == 0, "all stubbed ingests succeed → exit 0"
    # None of the already-ACTIVE clients were ingested…
    assert not any(name in ingested for name in known_folders), (
        f"crawler re-ingested an already-ACTIVE client: {ingested}"
    )
    # …and the new set was capped to CRAWLER_MAX_FOLDERS.
    assert len(ingested) == 5, f"expected cap of 5 ingested, got {len(ingested)}: {ingested}"
    assert all(n in new_folders for n in ingested)
    assert ex.counters.get("folders_new") == 5


def test_main_body_since_override_disables_exclusion(monkeypatch) -> None:
    """`--since` (explicit full re-pull) must NOT apply the exclude-existing
    filter — the operator is asking to re-ingest everything."""
    folders = [{"id": "id-h", "name": "Haventree Bank - DMA",
                "modifiedTime": "2026-06-18T00:00:00Z"}]
    monkeypatch.setattr(crawler, "CRAWLER_MAX_FOLDERS", 25)
    monkeypatch.setattr(drive_client, "build_drive_service", lambda: object())
    monkeypatch.setattr(drive_client, "list_dma_folders", lambda svc, root: folders)
    monkeypatch.setattr(drive_client, "folder_is_newer_than_watermark",
                        lambda folder, wm: True)

    # If exclusion were (wrongly) applied, this known client would be skipped.
    called = {"load_known": False, "load_ledger": False}

    def _boom() -> set:
        called["load_known"] = True
        return {crawler._norm_client_key("Haventree Bank - DMA")}

    def _boom_ledger() -> set:
        called["load_ledger"] = True
        return {"id-h"}

    monkeypatch.setattr(crawler, "_load_known_active_keys", _boom)
    monkeypatch.setattr(crawler, "_load_ingested_folder_ids", _boom_ledger)

    ingested: list[str] = []

    async def _fake_ingest(service, folder, tmp_root) -> str:
        ingested.append(folder["name"])
        return f"OK:run-{folder['id']}"

    monkeypatch.setattr(hb, "_ingest_folder", _fake_ingest)

    args = types.SimpleNamespace(once=True, since="2020-01-01", dry_run=False)
    settings = types.SimpleNamespace(drive_root_folder_id="root-folder")

    rc = crawler._main_body(args, settings, _Ex())
    assert rc == 0
    assert called["load_known"] is False, "--since must skip the known-keys lookup"
    assert called["load_ledger"] is False, "--since must skip the ledger lookup"
    assert ingested == ["Haventree Bank - DMA"], "--since must re-ingest even known clients"
