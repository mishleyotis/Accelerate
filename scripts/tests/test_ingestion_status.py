"""The word "ingested" means two things, and a report quoted the wrong one.

A connector smoke test concluded that 178 clients were ingested. The true
number was 2. Both figures were read off real data:

    status = INGESTED   a package scan parsed a workbook into a run row —
                        the START of the pipeline. 178 of these.
    ingested            (owner, 2026-08-21) promoted, serving, visible on the
                        live web app, carrying a "DMAI - <Client Name>" Drive
                        folder, not older than 6 months. 2 of these:
                        Logix and Baxter.

The gap is not a rounding error. 178 against 2 is the entire unproduced
pipeline, and quoting the parse count reads as "nearly done" when almost
nothing has been produced.

These tests hold the distinction in place. They deliberately do not touch the
network — the live counts change hourly, and a test that needed production
would fail on the machines this script exists to be run from. What they pin is
that the SCRIPT cannot conflate the two, which is the failure that happened.
"""
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingestion_status.py"


def _load():
    spec = importlib.util.spec_from_file_location("ingestion_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_script_exists_and_parses():
    assert SCRIPT.is_file()
    ast.parse(SCRIPT.read_text())


def test_help_works_without_credentials():
    """A diagnostic that cannot introduce itself is not a diagnostic."""
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "--drive" in r.stdout
    assert "--json" in r.stdout


# ── the distinction ──


def test_the_serving_directory_is_the_source_of_the_headline_count():
    """The count must come from the SERVING layer, never from run statuses.
    A run row is a claim about a file; only the directory can say whether a
    client sees anything."""
    src = SCRIPT.read_text()
    assert "/v1/directory" in src
    assert '"ingested_clients": len(rows)' in src, (
        "the headline count must be the serving rows, not a run-status tally")


def test_the_parse_count_is_never_the_ingested_count():
    """The two numbers may both be reported; they may never be the same field.
    `runs_parsed_not_ingested` is named so that quoting it as ingestion reads
    wrong in the quote itself."""
    src = SCRIPT.read_text()
    assert "runs_parsed_not_ingested" in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "ingested_clients" in keys and "runs_parsed_not_ingested" in keys:
                i = keys.index("ingested_clients")
                p = keys.index("runs_parsed_not_ingested")
                assert node.values[i] is not node.values[p]
                return
    pytest.fail("no result dict carrying both counts was found")


def test_the_internal_audience_is_passed_explicitly():
    """Every internal endpoint default-denies to the customer audience
    (invariant 5). Omitting the parameter is a 403 that reads like a
    permissions problem — it was filed as one, as MEM-0117, and the endpoint
    was fine."""
    src = SCRIPT.read_text()
    assert "audience=internal" in src


def test_the_six_month_rule_is_actually_evaluated():
    mod = _load()
    assert mod.FRESH_MONTHS == 6
    assert mod._months_since("2020-01-01T00:00:00Z") > 6
    assert mod._months_since(None) is None
    # an unparseable date is unknown, never "fresh"
    assert mod._months_since("not a date") is None


def test_an_unknown_date_is_not_reported_as_fresh():
    """`within_6_months` must be None, not True, when there is no date.
    A default that looks like data is invariant 9's whole subject."""
    mod = _load()
    assert mod._months_since("") is None


# ── the read-only guarantee ──


def test_the_drive_check_never_creates_anything():
    """drive_fetch._insights_root finds-or-CREATES and heals names. A status
    report that calls it would make every client compliant on its first run
    and agree with itself forever after."""
    src = SCRIPT.read_text()
    # A CALL, not a mention — the docstring names this helper precisely to
    # explain why it is not used, and an earlier version of this test failed
    # on its own explanation.
    tree = ast.parse(src)
    calls = {ast.unparse(n.func) for n in ast.walk(tree)
             if isinstance(n, ast.Call)}
    assert not any("_insights_root" in c for c in calls), (
        "that helper creates the folder it reports on")
    for readonly in ("_find_client_folder", "_list_children", "_insights_name"):
        assert readonly in src


def test_a_drive_lookup_failure_is_unknown_not_missing(monkeypatch):
    """"Nobody looked" and "it is not there" must stay distinguishable —
    reporting an unreachable Drive as a missing folder would have every client
    fail a criterion it may well satisfy."""
    mod = _load()
    monkeypatch.setattr(sys, "path", ["/nonexistent"] + sys.path)
    out = mod.insights_folder("Some Client That Cannot Be Looked Up")
    assert out["present"] is None
    assert "why" in out
