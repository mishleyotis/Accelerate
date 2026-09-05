"""The MCP resources: the schemas an agent fills, served as resources.

Owner, 2026-09-05: avail the gold-standard schemas AS RESOURCES, not only as
read tools. These tests pin that (a) every resource is readable offline —
no database, no encoder, no MCP SDK; (b) each page-contract resource is
byte-identical to get_page_contract; (c) the derived gold requirements never
disagree with the dual-source map; and (d) server.py actually registers them.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = ROOT / "apps" / "mcp"
for _p in (str(MCP_DIR), str(ROOT / "packages" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dma_mcp import resources as R                          # noqa: E402
from dma_mcp.contracts import PAGES, get_page_contract      # noqa: E402


def test_index_lists_unique_readable_resources():
    idx = R.resource_index()
    uris = [e["uri"] for e in idx]
    assert len(uris) == len(set(uris)), "duplicate resource uris"
    # six page contracts + index + join + gold
    assert len(uris) == len(PAGES) + 3
    for e in idx:
        assert e["mime_type"] == "application/json"
        assert e["name"] and e["description"]


def test_every_indexed_resource_reads_valid_json():
    for e in R.resource_index():
        out = R.read_resource(e["uri"])
        assert out["uri"] == e["uri"]
        json.loads(out["text"])          # must parse


def test_page_contract_resource_equals_the_tool():
    for page in PAGES:
        body = json.loads(R.read_resource(f"contract://page/{page}")["text"])
        assert body == get_page_contract(page)


def test_unknown_resource_raises():
    with pytest.raises(KeyError):
        R.read_resource("contract://page/nope")
    with pytest.raises(KeyError):
        R.read_resource("nonsense://x")


def test_join_resource_covers_every_served_required_section():
    body = json.loads(R.read_resource("join://section-sources")["text"])
    assert body.get("sections"), "join resource is empty — was it staged?"
    assert body["coverage"]["served_required_unsourced"] == []


def test_gold_requirements_agree_with_the_join():
    ss = json.loads(R.read_resource("join://section-sources")["text"])
    gold = json.loads(R.read_resource("gold://web-app-requirements")["text"])
    # every served section appears under served, every unserved under excluded
    served = {f"{p}.{s}" for p, ss_ in gold["served_sections"].items() for s in ss_}
    excluded = {f"{p}.{s}" for p, ss_ in gold["excluded_sections"].items()
                for s in ss_}
    for sec, v in ss["sections"].items():
        assert sec in (served if v["served"] else excluded), sec
    # the two owner-excluded sections are withheld, never served
    assert "overview.ceilings" in excluded
    assert "overview.evidence_coverage" in excluded


def test_server_registers_the_resources(monkeypatch):
    """server.py must register exactly the indexed resources — a resource in
    the index that server.py forgets to wire is a 404 at read time."""
    registered = []

    class _Stub:
        def __init__(self, *a, **k):
            self.name = a[0] if a else ""

        def tool(self, *a, **k):
            return lambda fn: fn

        def resource(self, uri, **k):
            registered.append(uri)
            return lambda fn: fn

        def streamable_http_app(self, *a, **k):
            return object()

    pkg = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    sub.MCPServer = _Stub
    pkg.server = sub
    monkeypatch.setitem(sys.modules, "mcp", pkg)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)
    monkeypatch.setenv("MCP_PATH_TOKEN", "test")
    monkeypatch.delitem(sys.modules, "server", raising=False)

    import server                                            # noqa: F401
    assert set(registered) == {e["uri"] for e in R.resource_index()}
