"""ONE definition of peer_coverage, in three deployables.

Owner, 2026-10-13 (R-INTERAC-20261010): "Align to ensure the same is used and
that no redo of such is done." Until then the contract text said "the
established share", the connector gate (AG-04) divided by every named peer
with one peer of slack, and the engine divided by the established subset.

The definition: peers DEPLOYED / NAMED peers, rounded to 2 places; null when
no peer is established either way. The connector, the ship script (which
computes it onto every page before submit, so a producer's figure never ships
and never costs a repair round) and the engine each hold a copy — they are
separate deployables — and this test keeps the three identical.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "plugins" / "dma-insights" / "skills" / "dma-research"))
from dma_mcp.peer_set import peer_coverage as connector        # noqa: E402
from engine.techscan import peer_coverage as engine            # noqa: E402
ship = _load("ship_page_under_test", ROOT / "plugins" / "dma-insights" / "skills"
             / "dma-surface-production" / "scripts" / "ship_page.py")

CASES = [
    ([], None),
    ([None, None, None, None, None], None),          # nothing established: null, never 0
    ([True, None, None, None, None], 0.2),
    ([False, None, None, None, None], 0.0),          # one established absence: 0 of 5
    ([True, True, True, None, None], 0.6),
    ([True, False, None], 0.33),
    ([True], 1.0),
]


def _rows(states):
    return [{"peer": f"P{i}", "deployed": s} for i, s in enumerate(states)]


def test_the_three_copies_agree_on_every_case():
    for states, want in CASES:
        assert connector(_rows(states)) == want, states
        assert ship._peer_coverage(_rows(states)) == want, states
        assert engine(states) == want, states


def test_the_ship_script_computes_it_onto_every_tile_and_register_row(tmp_path):
    (tmp_path / "platform.platform_story.json").write_text(json.dumps({"platforms": [
        {"platform": "MuleSoft", "peer_coverage": 1.0,           # a typed, wrong figure
         "peer_deployments": _rows([True, None, None, None, None])},
        {"platform": "Workshop", "peer_deployments": _rows([None, None])},
        {"platform": "No peers"}]}))
    (tmp_path / "techstack.techstack.json").write_text(json.dumps({"items": [
        {"ts_id": "TS-1", "peer_deployments": _rows([True, True, False, None, None])}]}))
    pl = ship.assemble(tmp_path, "platform")["platform_story"]["platforms"]
    assert [t.get("peer_coverage", "absent") for t in pl] == [0.2, None, "absent"]
    ts = ship.assemble(tmp_path, "techstack")["techstack"]["items"]
    assert ts[0]["peer_coverage"] == 0.4


def test_the_contract_text_is_unchanged_so_no_page_is_staled():
    """The contract's "the established share" IS this definition (the share of
    the named peers established as running it). The text is deliberately not
    edited: contract_version is a hash of contracts_data.json, and a changed
    hash marks every page passed under the old one stale — a redo the owner
    ruled out (2026-10-13)."""
    for p in (ROOT / "packages" / "shared" / "contracts_data.json",
              ROOT / "apps" / "mcp" / "dma_mcp" / "contracts_data.json"):
        assert "peer_coverage is a number 0-1 or null, the established share" in p.read_text()
