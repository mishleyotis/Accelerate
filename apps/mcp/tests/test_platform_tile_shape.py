"""CG-03b (P1) — a platform tile carries its peer and estate shape.

RC-09 (SWBC gold audit, 2026-10-04; slices PL-01, PL-03, PL-10, PL-12). A
python count over contracts_data.json found `peer_synthesis` 0 times,
`estate_reach` 0 times and `peer_deployments` twice; get_page_contract
('platform') never stated them, so they read as optional. SWBC promoted eight
tiles, seven with peer_synthesis null, six with peer_deployments null and
every estate_reach with cells_not_yet_reached null. The gold runs carry all
three on every tile.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_prose_shapes  # noqa: E402

ER = {"cells_not_yet_reached": 94, "by_category": [
    {"category_id": "P2C1", "category_name": "x", "cells_this_run_scores": 30,
     "cells_a_register_product_is_linked_to": 4}],
    "derivation": "computed from the register", "e_ids": []}
PEER = {"peer": "Alliant Credit Union", "deployed": None, "as_of": None,
        "basis": "Unestablished: the release names no integration layer.",
        "source_url": None}


def _run(*tiles):
    return _check_prose_shapes("platform", "platform_story",
                               {"platforms": list(tiles)})


def test_the_gold_tile_passes():
    assert _run({"platform": "MuleSoft", "peer_synthesis": "One of five.",
                 "estate_reach": ER, "peer_deployments": [PEER],
                 "peer_coverage": 0.2}) == []


def test_peers_identified_not_scored_is_a_synthesis_too():
    assert _run({"platform": "x", "peer_deployments": None,
                 "peer_synthesis": "Assurant, TruStage and Fortegra are "
                                   "identified, not scored.",
                 "estate_reach": ER}) == []


def test_the_swbc_tile_is_refused():
    out = _run({"platform": "Service Cloud", "peer_synthesis": None,
                "peer_deployments": None,
                "estate_reach": dict(ER, cells_not_yet_reached=None)})
    paths = {r["path"] for r in out}
    assert paths == {"platform_story.platforms[0].peer_synthesis",
                     "platform_story.platforms[0].estate_reach"}


def test_estate_reach_must_be_an_integer_count():
    out = _run({"platform": "x", "peer_synthesis": "s",
                "estate_reach": dict(ER, cells_not_yet_reached="many")})
    assert len(out) == 1 and "integer" in out[0]["message"]


def test_a_peer_row_is_whole():
    bad = {"peer": "X", "deployed": "maybe", "basis": ""}
    out = _run({"platform": "x", "peer_synthesis": "s", "estate_reach": ER,
                "peer_deployments": [bad]})
    assert len(out) == 1
    msg = out[0]["message"]
    for want in ("as_of", "deployed must be", "basis is empty",
                 "source_url or e_ids"):
        assert want in msg, want


def test_the_shape_is_machine_contract():
    spec = sections("platform")["platform_story"]["fields"]["platforms"]
    shape = spec["item_shape"]
    assert set(shape["required_keys"]) == {"peer_synthesis", "estate_reach"}
    assert "cells_not_yet_reached" in shape["estate_reach"]["integer_keys"]
    for k in ("peer_synthesis", "estate_reach", "peer_deployments",
              "peer_coverage"):
        assert k in spec["doc"], k
