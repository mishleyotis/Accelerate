"""engine.evidence_client — the Bash path to the evidence engine, offline."""
import io
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from engine import evidence_client as ec

CARD = {"card_id": "EV-0a1b2c3d",
        "item": {"source_name": "Example Regulator — Call report", "source_url": "https://reg.example.test/r",
                 "excerpt": "Total assets of $6.11 billion at June 30, 2026, up 4.2 percent over the year.",
                 "claim_type": "FACT", "tier": "T1", "published_date": "2026-08-15",
                 "linked_subcap_ids": [], "origin": "producer"},
        "provenance": {"recency": "CURRENT", "entity_match": "confirmed", "context_handle": "CTX-1"}}


class _Resp(io.BytesIO):
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(calls, result):
    def open_(req, timeout=0):
        body = json.loads(req.data)
        calls.append((req.full_url, body["method"], dict(req.header_items())))
        if body["method"] == "initialize":
            return _Resp(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "dmai-evidence"}}}).encode())
        return _Resp(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}]}}).encode())
    return open_


def test_brief_renders_the_batch_lines_the_lane_pastes():
    calls = []
    result = {"cards": [CARD], "coverage": {"saturation": False}, "search": {"hits": 7}}
    out = ec.brief(run_id="R", legal_name="Example Federal Credit Union", domains=["example-fcu.test"],
                   questions=["total assets"], facet="value", subcaps=["P1C1.1.1"], actor="research-p1c1-collector",
                   base="https://e.test", headers={"X-DMA-Path-Token": "t"}, opener=_opener(calls, result))
    assert [c[1] for c in calls] == ["initialize", "tools/call"]
    assert calls[0][0] == "https://e.test/mcp"
    assert all(h.get("X-dma-path-token") == "t" for _, _, h in calls)
    lines = out["batch_lines"]
    assert lines[0][:4] == ["search", "--query", "total assets", "--tool"] and "evidence_engine" in lines[0]
    ev = lines[1]
    assert ev[0] == "evidence" and ev[ev.index("--excerpt") + 1] == CARD["item"]["excerpt"]
    assert ev[ev.index("--subcap") + 1] == "P1C1.1.1" and ev[-1] == "research-p1c1-collector"
    assert ev[ev.index("--published") + 1] == "2026-08-15"


def test_spend_refusal_and_errors_pass_through_untouched():
    calls = []
    out = ec.brief(run_id="R", legal_name="X", domains=[], questions=["q"], base="https://e.test",
                   headers={}, opener=_opener(calls, {"needs_spend_approval": True, "cards": []}))
    assert out["needs_spend_approval"] is True and "batch_lines" not in out

    def boom(req, timeout=0):
        raise OSError("connection refused")
    out = ec.call("research_brief", {}, base="https://e.test", headers={}, opener=boom)
    assert "unreachable" in out["error"]


def test_the_cli_subcommand_exists_and_prints_json(monkeypatch, tmp_path):
    from engine import cli
    monkeypatch.setattr(ec, "brief", lambda **kw: {"cards": [CARD], "batch_lines": [["evidence", "--x", "y"]],
                                                   "coverage": {"saturation": True}, "kw": sorted(kw)})
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["evidence-brief", "--run", "R", "--legal-name", "Example FCU", "--domain", "example-fcu.test",
                       "--question", "q", "--facet", "works", "--subcap", "P1C1.1.1", "--json"])
    assert rc == 0
    out = json.loads(buf.getvalue())
    assert out["coverage"]["saturation"] is True
    assert "batch_lines" in out and out["batch_lines"][0][0] == "evidence"


def test_the_helper_it_mints_through_is_the_sibling_not_the_connectors():
    src = Path(ec.__file__).read_text()
    assert "evidence_auth_headers.sh" in src and "mcp_auth_headers.sh" not in src
