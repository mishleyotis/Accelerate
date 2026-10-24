"""`engine.cli approve` — the owner's per-run record that lets the
autoapprove hook open a credit-spending connector call.

Measured 28-09-2026 (QA audit F-K01-003): the hook was auto-approving
tavily_research, tavily_crawl and the Explorium enrich/match calls as
"none spends". The fix withholds them and opens each one only against a
record in <run>/07_qa/approvals.json that carries the quoted cost and the
approver. This file tests the writer; the hook's reader is tested in
plugins/dma-insights/scripts/tests/test_autoapprove_connector.py, and the
two tool lists are pinned equal here.
"""
import json
import sys
from pathlib import Path

import pytest

from engine import cli
from fixtures import new_run

HOOK = (Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
        / "scripts" / "hooks" / "autoapprove_connector.py")


def _approve(run, *extra):
    return cli.main(["approve", "--run", run.run_id, "--root", str(run.root),
                     *extra])


def _records(run):
    return json.loads((run.qa_dir / "approvals.json").read_text())["approvals"]


def test_an_approval_writes_the_record_with_cost_approver_and_expiry(tmp_path, capsys):
    run = new_run(tmp_path)
    rc = _approve(run, "--tool", "enrich-business",
                  "--cost", "2 credits/row x 400 rows = 800 credits",
                  "--approved-by", "owner@example.com", "--max-calls", "3")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1
    recs = _records(run)
    assert recs[0]["tool"] == "enrich-business"
    assert recs[0]["cost_line"] == "2 credits/row x 400 rows = 800 credits"
    assert recs[0]["approved_by"] == "owner@example.com"
    assert recs[0]["max_calls"] == 3
    assert recs[0]["run_id"] == run.run_id
    assert recs[0]["expires"] > recs[0]["at"]


def test_approvals_accumulate_rather_than_overwrite(tmp_path):
    run = new_run(tmp_path)
    _approve(run, "--tool", "tavily_research", "--cost", "1 call",
             "--approved-by", "o")
    _approve(run, "--tool", "match-business", "--cost", "1 credit/row",
             "--approved-by", "o")
    assert [r["tool"] for r in _records(run)] == ["tavily_research", "match-business"]


@pytest.mark.parametrize("extra", [
    ("--cost", "   ", "--approved-by", "o"),
    ("--cost", "x", "--approved-by", ""),
    ("--cost", "x", "--approved-by", "o", "--expires-hours", "0"),
])
def test_a_blank_cost_or_approver_or_zero_expiry_is_refused(tmp_path, extra):
    run = new_run(tmp_path)
    with pytest.raises(SystemExit) as e:
        _approve(run, "--tool", "tavily_crawl", *extra)
    assert "REFUSED" in str(e.value)
    assert not (run.qa_dir / "approvals.json").exists()


def test_only_a_spend_tool_can_be_approved(tmp_path):
    run = new_run(tmp_path)
    with pytest.raises(SystemExit):
        _approve(run, "--tool", "export-to-csv", "--cost", "x", "--approved-by", "o")
    with pytest.raises(SystemExit):
        _approve(run, "--tool", "fetch-entities", "--cost", "x", "--approved-by", "o")


def test_the_cli_tool_list_equals_the_hooks_spend_suffixes():
    """One owner for the list: the hook. The CLI's choices must match it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("aac", HOOK)
    aac = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("aac", aac)
    spec.loader.exec_module(aac)
    assert cli.SPEND_TOOLS == aac.SPEND_SUFFIXES


def test_the_hook_reads_what_the_cli_wrote(tmp_path, monkeypatch):
    """End to end: approve, then the hook allows that tool and no other."""
    import subprocess
    run = new_run(tmp_path)
    _approve(run, "--tool", "tavily_research", "--cost", "1 research call",
             "--approved-by", "owner@example.com")
    env = {"DMA_APPROVALS_FILE": str(run.qa_dir / "approvals.json"),
           "PATH": "/usr/bin:/bin"}

    def hook(tool):
        r = subprocess.run([sys.executable, str(HOOK)], env=env,
                           input=json.dumps({"tool_name": tool, "tool_input": {}}),
                           capture_output=True, text=True)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None

    ok = hook("mcp__Tavily__tavily_research")
    assert ok["permissionDecision"] == "allow" and "1 research call" in ok["permissionDecisionReason"]
    assert hook("mcp__Tavily__tavily_crawl") is None
