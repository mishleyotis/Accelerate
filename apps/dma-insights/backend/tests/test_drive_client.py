"""Tests for the pure drive_client helpers (no GCP creds required)."""
from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime

import pytest

from app.services.drive_client import (
    folder_is_newer_than_watermark,
    http_status_of,
    is_transient_drive_error,
    parse_drive_timestamp,
    run_with_transient_retries,
)


class TestParseDriveTimestamp:
    def test_z_suffix(self) -> None:
        dt = parse_drive_timestamp("2025-09-19T19:24:12.345Z")
        assert dt is not None
        assert dt.year == 2025 and dt.month == 9 and dt.day == 19

    def test_already_offset(self) -> None:
        dt = parse_drive_timestamp("2025-09-19T19:24:12+00:00")
        assert dt is not None

    def test_empty_returns_none(self) -> None:
        assert parse_drive_timestamp("") is None
        assert parse_drive_timestamp(None) is None

    def test_bogus_returns_none(self) -> None:
        assert parse_drive_timestamp("not-a-date") is None


class TestFolderIsNewerThanWatermark:
    def test_no_watermark_is_cold_start(self) -> None:
        """State-branch: cold_start — every folder is "new"."""
        folder = {"modifiedTime": "2025-09-19T19:24:12Z"}
        assert folder_is_newer_than_watermark(folder, None) is True

    def test_modified_after_watermark_is_newer(self) -> None:
        """State-branch: watermark_advance — modifiedTime > watermark."""
        folder = {"modifiedTime": "2025-09-19T19:24:12Z"}
        watermark = datetime(2025, 9, 19, 12, 0, 0, tzinfo=UTC)
        assert folder_is_newer_than_watermark(folder, watermark) is True

    def test_modified_before_watermark_is_not_newer(self) -> None:
        """State-branch: no_new_files — no folder beats its watermark."""
        folder = {"modifiedTime": "2025-09-19T12:00:00Z"}
        watermark = datetime(2025, 9, 19, 19, 24, 12, tzinfo=UTC)
        assert folder_is_newer_than_watermark(folder, watermark) is False

    def test_missing_modified_time_is_newer(self) -> None:
        """Missing modifiedTime → conservative re-ingest."""
        folder: dict = {}
        watermark = datetime(2025, 9, 19, 12, 0, 0, tzinfo=UTC)
        assert folder_is_newer_than_watermark(folder, watermark) is True

    def test_naive_watermark_normalized(self) -> None:
        """A naive watermark should be treated as UTC, not crash."""
        folder = {"modifiedTime": "2025-09-19T19:24:12Z"}
        watermark = datetime(2025, 9, 19, 12, 0, 0)  # naive
        assert folder_is_newer_than_watermark(folder, watermark) is True


# ── Transient-failure classification + retry wrapper (2026-07-06) ─────────
# Production shapes from drive_crawler execution 7sdfs: downloads dying with
# 'SSLError: [SSL] record layer failure' / 'TimeoutError: The read operation
# timed out'. No real Drive calls — HttpError is duck-typed via stubs.


class _StatusCodeError(Exception):
    """Stub for googleapiclient HttpError exposing `status_code`."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


class _RespStatusError(Exception):
    """Stub for the older HttpError shape exposing `resp.status`."""

    class _Resp:
        def __init__(self, status) -> None:
            self.status = status

    def __init__(self, status) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = self._Resp(status)


class TestHttpStatusOf:
    def test_status_code_attr(self) -> None:
        assert http_status_of(_StatusCodeError(503)) == 503

    def test_resp_status_attr(self) -> None:
        assert http_status_of(_RespStatusError(429)) == 429

    def test_string_status_coerced(self) -> None:
        assert http_status_of(_RespStatusError("502")) == 502

    def test_plain_exception_has_no_status(self) -> None:
        assert http_status_of(ValueError("nope")) is None

    def test_garbage_status_is_none(self) -> None:
        assert http_status_of(_RespStatusError("not-a-code")) is None


class TestIsTransientDriveError:
    def test_production_ssl_record_layer_failure(self) -> None:
        # CI Financials / CI Segal Bryant & Hammill (execution 7sdfs).
        assert is_transient_drive_error(
            ssl.SSLError(1, "[SSL] record layer failure (_ssl.c:2580)")
        ) is True

    def test_production_read_timeout(self) -> None:
        # BOK Financial / Bank of Utah (execution 7sdfs).
        assert is_transient_drive_error(
            TimeoutError("The read operation timed out")
        ) is True

    def test_connection_reset(self) -> None:
        assert is_transient_drive_error(ConnectionResetError()) is True

    def test_transient_http_statuses(self) -> None:
        for status in (429, 500, 502, 503, 504):
            assert is_transient_drive_error(_StatusCodeError(status)) is True
            assert is_transient_drive_error(_RespStatusError(status)) is True

    def test_permanent_http_statuses(self) -> None:
        # 403 is deliberately non-transient: usually permissions / the
        # export ceiling; quota has its own state branch at the listing
        # layer.
        for status in (400, 401, 403, 404):
            assert is_transient_drive_error(_StatusCodeError(status)) is False

    def test_non_network_errors(self) -> None:
        assert is_transient_drive_error(ValueError("bad parse")) is False
        assert is_transient_drive_error(KeyError("id")) is False


class TestRunWithTransientRetries:
    """The folder-level retry wrapper — injected sleep, no real waiting."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_succeeds_after_transient_failures(self) -> None:
        calls = {"n": 0}
        delays: list[float] = []

        async def _flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ssl.SSLError(1, "[SSL] record layer failure")
            return "OK:run-123"

        async def _sleep(s: float) -> None:
            delays.append(s)

        res = self._run(run_with_transient_retries(
            _flaky, attempts=3, label="BOK Financial - DMA", sleep=_sleep,
        ))
        assert res == "OK:run-123"
        assert calls["n"] == 3
        assert delays == [2.0, 4.0], "exponential backoff 2^attempt"

    def test_non_transient_raises_immediately(self) -> None:
        calls = {"n": 0}

        async def _broken() -> str:
            calls["n"] += 1
            raise ValueError("parse failure — retrying cannot help")

        async def _sleep(s: float) -> None:  # pragma: no cover
            raise AssertionError("must not sleep for a non-transient error")

        with pytest.raises(ValueError):
            self._run(run_with_transient_retries(
                _broken, attempts=3, sleep=_sleep,
            ))
        assert calls["n"] == 1

    def test_exhausted_attempts_reraise_original(self) -> None:
        calls = {"n": 0}
        delays: list[float] = []

        async def _always_timeout() -> str:
            calls["n"] += 1
            raise TimeoutError("The read operation timed out")

        async def _sleep(s: float) -> None:
            delays.append(s)

        with pytest.raises(TimeoutError):
            self._run(run_with_transient_retries(
                _always_timeout, attempts=3, sleep=_sleep,
            ))
        assert calls["n"] == 3
        assert delays == [2.0, 4.0]

    def test_backoff_capped_at_max_delay(self) -> None:
        calls = {"n": 0}
        delays: list[float] = []

        async def _always_503() -> str:
            calls["n"] += 1
            raise _StatusCodeError(503)

        async def _sleep(s: float) -> None:
            delays.append(s)

        with pytest.raises(_StatusCodeError):
            self._run(run_with_transient_retries(
                _always_503, attempts=6, max_delay=8.0, sleep=_sleep,
            ))
        assert delays == [2.0, 4.0, 8.0, 8.0, 8.0]

    def test_custom_is_retryable_gate_wins(self) -> None:
        """The crawler gates retries on its soft deadline — a False from
        the injected gate must stop retries even for transient errors."""
        calls = {"n": 0}

        async def _flaky() -> str:
            calls["n"] += 1
            raise TimeoutError("The read operation timed out")

        with pytest.raises(TimeoutError):
            self._run(run_with_transient_retries(
                _flaky, attempts=3,
                is_retryable=lambda e: False,
                sleep=None,
            ))
        assert calls["n"] == 1
