"""Offline test harness: every test runs with no network and no model.

The package is importable from the repo checkout; fixtures (saved FSI-shaped
pages and PDFs, invented institutions) live beside the tests. No test names
a real client (tests/test_no_client_strings.py enforces it over the package
AND the tests)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = HERE / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Every test gets its own data dir, no backends, no bucket, no models."""
    monkeypatch.setenv("EE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EDGAR_LOCAL_DATA_DIR", str(tmp_path / "edgar"))
    monkeypatch.setenv("SEARXNG_URL", "")
    monkeypatch.setenv("PARALLEL_ENABLED", "0")
    monkeypatch.setenv("EE_GCS_BUCKET", "")
    monkeypatch.setenv("EE_MODELS_DIR", "")
    monkeypatch.setenv("EE_PATH_TOKEN", "")
    from evidence_engine import config
    config.reset_settings()
    yield
    config.reset_settings()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
