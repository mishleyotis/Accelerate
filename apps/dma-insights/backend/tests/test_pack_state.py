"""pack_state contract: a real pack client loads and scores end-to-end."""
import json
import os

import pytest

_CLIENTS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "startup-data", "clients"))
_CID = "farm-credit-mid-america--0001"

pytestmark = pytest.mark.skipif(
    not os.path.isdir(os.path.join(_CLIENTS, _CID)),
    reason="startup-data pack not present")


def test_load_pack_state_populates_state():
    from app.services.nlp.pack_state import load_pack_state
    state = load_pack_state(_CLIENTS, _CID)
    assert len(state.capabilities) > 100
    assert state._excerpts
    assert state.why_now_signals
    assert state.name.startswith("Farm Credit")
    assert state.all_score_values
    cap = state.capability("P4C1")
    assert cap is not None and cap.subcap_id.startswith("P4C1")


def test_score_real_insight_card_end_to_end():
    from app.services.nlp.grader import Item
    from app.services.nlp.pack_state import load_pack_state
    from app.services.nlp.rubric100 import WEIGHTS, RubricScore, score_item

    state = load_pack_state(_CLIENTS, _CID)
    with open(os.path.join(_CLIENTS, _CID, "insights.json")) as fh:
        items = json.load(fh)["items"]
    assert items
    it = items[0]
    item = Item(surface="insight_card", title=it.get("title") or "",
                what=it.get("what_text") or "", why=it.get("why_text") or "",
                so_what=it.get("so_what_text") or "",
                anchor_subcap=it.get("linked_subcap_id"),
                e_ids=list(it.get("linked_e_ids") or []))
    r = score_item(item, state, surface="insight_card")
    assert isinstance(r, RubricScore)
    assert 0.0 <= r.total <= 100.0
    assert set(r.dims) == set(WEIGHTS)
    assert r.band in {"GOLD", "SHIP_WITH_NOTES", "REVISE", "REJECT"}
