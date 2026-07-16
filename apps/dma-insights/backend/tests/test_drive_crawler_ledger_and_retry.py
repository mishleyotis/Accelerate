"""Drive-crawler DB-ledger reconciliation + download robustness contract.

2026-07-06 incident (execution dma-insights-drive-crawler-7sdfs): every
scheduled crawl failed — 0/25 ingested, 24 download failures
('SSLError: [SSL] record layer failure', 'TimeoutError: The read operation
timed out') — while historical_backfill read the SAME Drive root an hour
later and ingested 43/150 with zero failures. Two crawler-only defects:

  A. ONE googleapiclient service object was shared across
     CRAWLER_CONCURRENCY concurrent folder tasks (service objects are not
     safe for concurrent requests), corrupting the TLS session; and there
     was no folder-level retry, so every blip failed the folder outright.
  B. The audit counters lied — `folders_new` was overwritten with the
     OK count inside the ingest loop (so the row read `folders_new: 0`
     while 25 genuinely-new folders were attempted), and new-folder
     detection didn't reconcile against the DB ledger
     (runs.drive_folder_id) the way the backfill does.

This pins the fixes: per-task Drive services, transient-retry via
drive_client.run_with_transient_retries, ledger-based candidacy
regardless of modifiedTime, truthful counters, and the documented exit
contract (partial-ok = 0; systemic all-fail = 7). No real Drive calls —
Drive IO + DB loaders are stubbed.
"""
from __future__ import annotations

import ssl
import sys
import types
from pathlib import Path

import pytest

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


def _args(since: str | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(once=True, since=since, dry_run=False)


_SETTINGS = types.SimpleNamespace(drive_root_folder_id="root-folder")


def _wire(monkeypatch, folders, *, ledger=None, known=None,
          max_folders=25, concurrency=4):
    """Common stubbing for _main_body runs (hermetic, no Drive, no DB)."""
    monkeypatch.setattr(crawler, "CRAWLER_MAX_FOLDERS", max_folders)
    monkeypatch.setattr(crawler, "CRAWLER_CONCURRENCY", concurrency)
    monkeypatch.setattr(crawler, "CRAWLER_DEADLINE_SEC", 60)
    monkeypatch.setattr(drive_client, "build_drive_service", lambda: object())
    monkeypatch.setattr(drive_client, "list_dma_folders",
                        lambda svc, root: folders)
    monkeypatch.setattr(crawler, "_load_ingested_folder_ids",
                        lambda: set(ledger or set()))
    monkeypatch.setattr(crawler, "_load_known_active_keys",
                        lambda: set(known or set()))


class TestLedgerReconciliation:
    """B: a folder with no ACTIVE ingested run is a candidate REGARDLESS
    of modifiedTime; folders already in the ledger are done."""

    def test_never_ingested_folder_is_candidate_despite_old_mtime(
        self, monkeypatch,
    ) -> None:
        # Folder B predates any conceivable checkpoint (2020!) but has no
        # ACTIVE run → must be ingested. Folder A is in the ledger → done.
        folders = [
            {"id": "id-a", "name": "Already Ingested Bank - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"},
            {"id": "id-b", "name": "Ancient Never Ingested Bank - DMA",
             "modifiedTime": "2020-01-01T00:00:00Z"},
        ]
        _wire(monkeypatch, folders, ledger={"id-a"})

        ingested: list[str] = []

        async def _fake_ingest(service, folder, tmp_root) -> str:
            ingested.append(folder["id"])
            return f"OK:run-{folder['id']}"

        monkeypatch.setattr(hb, "_ingest_folder", _fake_ingest)

        ex = _Ex()
        rc = crawler._main_body(_args(), _SETTINGS, ex)
        assert rc == 0
        assert ingested == ["id-b"], (
            "ledger folder must be skipped; never-ingested folder must be "
            "picked up no matter how old its modifiedTime is"
        )
        assert ex.counters.get("folders_new") == 1

    def test_seeded_name_key_still_excludes_local_seeds(
        self, monkeypatch,
    ) -> None:
        """The seeded corpus ('local:…' ledger keys) is still excluded by
        normalized name — the 2026-06-18 duplicate-entities guard."""
        folders = [
            {"id": "id-h", "name": "Haventree Bank - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"},
            {"id": "id-n", "name": "Net New Bank - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"},
        ]
        _wire(monkeypatch, folders,
              known={crawler._norm_client_key("Haventree Bank - DMA")})

        ingested: list[str] = []

        async def _fake_ingest(service, folder, tmp_root) -> str:
            ingested.append(folder["id"])
            return f"OK:run-{folder['id']}"

        monkeypatch.setattr(hb, "_ingest_folder", _fake_ingest)

        rc = crawler._main_body(_args(), _SETTINGS, _Ex())
        assert rc == 0
        assert ingested == ["id-n"]


class TestPerTaskDriveService:
    """A: every concurrent folder task must get its OWN Drive service —
    sharing one corrupts the TLS session (the 7sdfs SSL/timeout storm)."""

    def test_one_service_built_per_ingested_folder(self, monkeypatch) -> None:
        folders = [
            {"id": f"id-{i}", "name": f"New Bank {i:02d} - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"}
            for i in range(3)
        ]
        _wire(monkeypatch, folders, concurrency=4)

        built = {"n": 0}

        def _build() -> object:
            built["n"] += 1
            return object()

        monkeypatch.setattr(drive_client, "build_drive_service", _build)

        seen_services: list[object] = []

        async def _fake_ingest(service, folder, tmp_root) -> str:
            seen_services.append(service)
            return f"OK:run-{folder['id']}"

        monkeypatch.setattr(hb, "_ingest_folder", _fake_ingest)

        rc = crawler._main_body(_args(), _SETTINGS, _Ex())
        assert rc == 0
        # 1 listing service + 1 per folder task.
        assert built["n"] == 1 + len(folders)
        assert len(set(map(id, seen_services))) == len(folders), (
            "each folder task must receive a distinct service object"
        )


class TestTransientRetryIntegration:
    """A: a transient download failure must be retried with backoff, not
    fail the folder — while non-transient errors still fail fast."""

    def test_ssl_blip_retried_then_ok(self, monkeypatch) -> None:
        folders = [{"id": "id-x", "name": "Flaky Bank - DMA",
                    "modifiedTime": "2026-07-01T00:00:00Z"}]
        _wire(monkeypatch, folders)

        # No real waiting: the wrapper's default sleep is asyncio.sleep.
        async def _no_sleep(_s: float) -> None:
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        attempts = {"n": 0}

        async def _flaky_ingest(service, folder, tmp_root) -> str:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ssl.SSLError(1, "[SSL] record layer failure (_ssl.c:2580)")
            return "OK:run-x"

        monkeypatch.setattr(hb, "_ingest_folder", _flaky_ingest)

        ex = _Ex()
        rc = crawler._main_body(_args(), _SETTINGS, ex)
        assert rc == 0
        assert attempts["n"] == 2, "one transient failure + one retry"
        assert ex.counters.get("files_parsed") == 1
        assert ex.counters.get("files_errored") == 0

    def test_non_transient_error_fails_folder_without_retry(
        self, monkeypatch,
    ) -> None:
        folders = [{"id": "id-x", "name": "Broken Bank - DMA",
                    "modifiedTime": "2026-07-01T00:00:00Z"}]
        _wire(monkeypatch, folders)

        attempts = {"n": 0}

        async def _broken_ingest(service, folder, tmp_root) -> str:
            attempts["n"] += 1
            raise ValueError("structurally broken package")

        monkeypatch.setattr(hb, "_ingest_folder", _broken_ingest)

        ex = _Ex()
        rc = crawler._main_body(_args(), _SETTINGS, ex)
        assert rc == 7, "all-failed run is a systemic failure"
        assert attempts["n"] == 1, "non-transient errors must not retry"
        assert ex.counters.get("files_errored") == 1


class TestCountersAreTruthful:
    """B: folders_new must report the detected new candidates — the old
    code overwrote it with the OK count, so the 7sdfs audit row read
    folders_new=0 while 25 new folders were attempted."""

    def test_folders_new_not_clobbered_when_everything_fails(
        self, monkeypatch,
    ) -> None:
        folders = [
            {"id": f"id-{i}", "name": f"New Bank {i:02d} - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"}
            for i in range(4)
        ]
        _wire(monkeypatch, folders)

        async def _fail_ingest(service, folder, tmp_root) -> str:
            return f"ERROR:download:{folder['name']}: TimeoutError"

        monkeypatch.setattr(hb, "_ingest_folder", _fail_ingest)

        ex = _Ex()
        rc = crawler._main_body(_args(), _SETTINGS, ex)
        assert rc == 7
        assert ex.counters.get("folders_new") == 4, (
            "folders_new must keep the detected-new count even when every "
            "ingest fails (7sdfs regression)"
        )
        assert ex.counters.get("files_parsed") == 0
        assert ex.counters.get("files_errored") == 4


class TestExitCodeContract:
    """C: infra/EXIT_CODES.md § drive_crawler — partial-ok exits 0; a
    systemic failure (≥1 failed, zero OK) exits 7."""

    @pytest.mark.parametrize(
        ("results", "expected_rc"),
        [
            # every folder ingested → 0
            (["OK:r1", "OK:r2"], 0),
            # skips only (unchanged corpus) → 0
            (["SKIP:done", "SKIP:done"], 0),
            # PARTIAL-OK: one flaky folder must not poison the run → 0
            (["OK:r1", "ERROR:download:x"], 0),
            # systemic: everything attempted failed → 7
            (["ERROR:download:x", "ERROR:download:y"], 7),
            # the 7sdfs shape: skips but ZERO successful ingests + fails → 7
            (["SKIP:done", "ERROR:download:x", "ERROR:download:y"], 7),
        ],
    )
    def test_exit_code(self, monkeypatch, results, expected_rc) -> None:
        folders = [
            {"id": f"id-{i}", "name": f"Bank {i:02d} - DMA",
             "modifiedTime": "2026-07-01T00:00:00Z"}
            for i in range(len(results))
        ]
        _wire(monkeypatch, folders, concurrency=1)

        # Deterministic result per folder (order-independent by id).
        by_id = {f["id"]: r for f, r in zip(folders, results, strict=True)}

        async def _scripted_ingest(service, folder, tmp_root) -> str:
            return by_id[folder["id"]]

        monkeypatch.setattr(hb, "_ingest_folder", _scripted_ingest)

        rc = crawler._main_body(_args(), _SETTINGS, _Ex())
        assert rc == expected_rc


class TestDownloadChunkNetworkRetry:
    """Chunk-level `_download_file` must retry socket-level transient
    failures (SSLError / TimeoutError), not just HttpError 5xx — the
    7sdfs failures were raw ssl/socket exceptions the old except clause
    never caught."""

    class _FakeRequest:
        pass

    class _FakeFiles:
        def get_media(self, fileId):  # Drive API casing
            return TestDownloadChunkNetworkRetry._FakeRequest()

    class _FakeDrive:
        def files(self):
            return TestDownloadChunkNetworkRetry._FakeFiles()

    def _fake_downloader(self, fail_times: int, calls: dict):
        outer = self

        class _FakeDownloader:
            def __init__(self, fh, request, chunksize=0) -> None:
                assert isinstance(
                    request, outer._FakeRequest,
                ), "must download via files().get_media"

            def next_chunk(self):
                calls["n"] += 1
                if calls["n"] <= fail_times:
                    raise ssl.SSLError(
                        1, "[SSL] record layer failure (_ssl.c:2580)",
                    )
                return None, True

        return _FakeDownloader

    def test_ssl_blip_mid_chunk_retries_then_completes(
        self, monkeypatch, tmp_path,
    ) -> None:
        calls = {"n": 0}
        monkeypatch.setattr(
            hb, "MediaIoBaseDownload", self._fake_downloader(2, calls),
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        dest = tmp_path / "workbook.xlsx"
        hb._download_file(
            self._FakeDrive(),
            {"id": "f1", "name": "workbook.xlsx", "mimeType": "application/pdf"},
            dest,
        )
        assert calls["n"] == 3, "2 transient failures + 1 success"
        assert dest.exists()

    def test_persistent_network_failure_exhausts_and_raises(
        self, monkeypatch, tmp_path,
    ) -> None:
        calls = {"n": 0}
        monkeypatch.setattr(
            hb, "MediaIoBaseDownload", self._fake_downloader(99, calls),
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        with pytest.raises(ssl.SSLError):
            hb._download_file(
                self._FakeDrive(),
                {"id": "f1", "name": "workbook.xlsx",
                 "mimeType": "application/pdf"},
                tmp_path / "workbook.xlsx",
            )
        assert calls["n"] == hb._DOWNLOAD_MAX_ATTEMPTS
