"""Shared test seams for the connector suite.

CG-PAR (promote_checks.gold_parity) holds every promote to the committed
gold shape of three real promoted runs. The transaction tests across this
suite promote the WALKING SKELETON — every section an envelope and an empty
state — to exercise locking, writer order, rollback and retention; against
the gold that skeleton is (correctly) thinner on every page, so with the real
gate in place none of those mechanics could be reached.

So the gold comparison is replaced by a clean result for every test EXCEPT
those marked `real_parity`, which get the committed gold. The seam is here,
in tests, and nowhere in the product: there is no switch that turns CG-PAR
off in a deployed connector. The gate itself is pinned by
test_promote_parity.py (fake connection and the real schema).
"""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_parity: run promote against the committed gold "
                   "shape (CG-PAR) instead of the transaction-test stub")


@pytest.fixture(autouse=True)
def _gold_parity_stub(request, monkeypatch):
    if request.node.get_closest_marker("real_parity"):
        yield
        return
    try:
        from dma_mcp import promote_checks
    except Exception:                                 # noqa: BLE001
        yield
        return
    monkeypatch.setattr(
        promote_checks, "gold_parity",
        lambda live, *a, **k: ({}, {"gaps": 0, "warnings": [],
                                    "stubbed": "tests/conftest.py — "
                                               "transaction tests only"}))
    yield
