"""Gate I, and the wiring it refuses to let rot.

A safeguard nobody exercises is a comment. These assert that the gate
catches each way the enrichment ledger can be quietly disconnected, by
breaking the wiring in a copy and checking the gate says which piece went.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate_i_enrichment_drift.py"
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import ledger  # noqa: E402


def _run(*args):
    return subprocess.run([sys.executable, str(GATE), *args],
                          capture_output=True, text=True, cwd=str(ROOT))


def test_the_repo_is_wired_today():
    r = _run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gate I passed" in r.stdout


def test_it_names_every_facet_it_watches():
    assert str(len(ledger.FACETS)) in _run().stdout


@pytest.mark.parametrize("path,needle", [
    ("apps/mcp/dma_mcp/promote.py", "record_promotion_for_sections"),
    ("apps/mcp/dma_mcp/promote.py", "ledger.summary"),
    ("apps/mcp/dma_mcp/bundle.py", "ledger.summary"),
])
def test_it_catches_the_wiring_being_removed(path, needle, tmp_path):
    """Each of these is a way the ledger goes quiet without failing.

    Removing the promote hook is the worst: every facet then reports
    `enriched_not_promoted` for ever, including work that IS live, and a
    safeguard crying wolf is one that gets switched off.
    """
    target = ROOT / path
    original = target.read_text()
    try:
        target.write_text(original.replace(needle, "removed_for_the_test"))
        r = _run()
        assert r.returncode == 1, r.stdout
        assert "gate I FAILED" in r.stdout
    finally:
        target.write_text(original)


@pytest.mark.parametrize("needle", [
    "CREATE TABLE enrichment_ledger",
    "CREATE TABLE facet_promotion_state",
    "CREATE VIEW enrichment_drift",
    "next_enrichment_version",
    "ON DELETE CASCADE",
])
def test_it_catches_the_schema_being_hollowed_out(needle):
    target = (ROOT / "migrations" / "versions"
              / "0051_enrichment_ledger_and_promotion_state.py")
    original = target.read_text()
    try:
        target.write_text(original.replace(needle, "-- removed for the test"))
        r = _run()
        assert r.returncode == 1, r.stdout
        assert needle in r.stdout or "0051" in r.stdout
    finally:
        target.write_text(original)


def test_the_gate_is_satisfiable():
    """A gate that refuses a fully-current client is one nobody can ever
    pass, which is the same as no gate — it gets disabled on its first
    green run."""
    clean = [{"facet": f, "state": "current", "enrichment_version": 1,
              "promoted_version": 1, "enriched_at": None, "promoted_at": None}
             for f in ledger.FACETS]
    assert ledger.summary(clean)["done"] is True
    assert ledger.summary(clean)["reason"] is None


def test_an_unreadable_client_is_not_reported_as_passing():
    """Exit 2, not 0. A gate that cannot see its subject must not clear it —
    the whole failure class here is work nobody could see."""
    r = _run("--entity", "no-such-client-exists-anywhere")
    assert r.returncode != 0, r.stdout
    assert "gate I passed" not in r.stdout
