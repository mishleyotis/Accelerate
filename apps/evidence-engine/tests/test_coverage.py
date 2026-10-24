from evidence_engine import coverage as cov


def _card(cid, excerpt, oc, facet="works", recency="CURRENT", host="a.test", rung="news", em="confirmed"):
    return {"card_id": cid, "item": {"excerpt": excerpt},
            "provenance": {"origin_cluster": oc, "facet_hints": [facet], "recency": recency,
                           "host": host, "ladder_rung": rung, "entity_match": em,
                           "source_type_hint": "news"}}


def test_conflict_candidates_flag_different_figures_from_different_origins():
    cards = [_card("EV-1", "The credit union serves 212,000 members across the state.", "OC-a"),
             _card("EV-2", "It serves 198,000 members and 14 branches.", "OC-b"),
             _card("EV-3", "It serves 212,000 members.", "OC-c")]
    out = cov.conflict_candidates(cards)
    assert out and out[0]["field"] == "members"
    vals = {v["value"] for v in out[0]["values"]}
    assert vals == {"212000", "198000"}
    assert "never averages" in out[0]["disposition"]


def test_same_origin_does_not_conflict():
    cards = [_card("EV-1", "It has 212,000 members.", "OC-a"), _card("EV-2", "It has 198,000 members.", "OC-a")]
    assert cov.conflict_candidates(cards) == []


def test_novelty_and_saturation():
    assert cov.novelty(["OC-a", "OC-b"], set()) == 1.0
    assert cov.novelty(["OC-a", "OC-b"], {"OC-a", "OC-b"}) == 0.0
    assert cov.saturation([0.5, 0.05, 0.02])
    assert not cov.saturation([0.05])
    assert not cov.saturation([0.05, 0.5])


def test_concentration_flag_over_40_percent():
    cards = [_card(f"EV-{i}", "x", "OC-a") for i in range(3)] + [_card("EV-9", "x", "OC-b")]
    c = cov.concentration(cards)
    assert c["flag"] and c["top_cluster"] == "OC-a" and c["share"] == 0.75
    assert not cov.concentration(cards[:1])["flag"]      # too few to judge


def test_coverage_block_persists_state_and_lists_ladder():
    state = {}
    ret = [_card("EV-1", "212,000 members.", "OC-a", rung="regulator")]
    queries = [{"kind": "site:entity"}, {"kind": "site:regulator"}, {"kind": "facet"}]
    block, state = cov.coverage_block(run_state=state, facet="works", returned=ret, queries=queries,
                                      sources_used=["searxng", "edgar-xbrl"])
    assert block["novelty"] == 1.0 and not block["saturation"]
    assert block["ladder_searched"] == ["entity_site", "regulator", "filings", "news"]
    block2, state = cov.coverage_block(run_state=state, facet="works", returned=ret, queries=[], sources_used=[])
    assert block2["novelty"] == 0.0
    block3, state = cov.coverage_block(run_state=state, facet="works", returned=ret, queries=[], sources_used=[])
    assert block3["saturation"] is True
    assert state["clusters"]["works"] == ["OC-a"]


def test_coverage_report_shape():
    cards = [_card("EV-1", "x", "OC-a"), _card("EV-2", "y", "OC-b", facet="fails", recency="UNVERIFIED")]
    rep = cov.coverage_report(cards, {"novelty_history": {"works": [0.0, 0.0]}}, {"EV-1": ["L-1"]})
    assert rep["cards_total"] == 2
    assert set(rep["per_facet"]) == {"works", "fails"}
    assert rep["per_label"]["L-1"]["cards"] == 1
    assert rep["saturation_by_facet"]["works"] is True
    assert rep["recency"]["UNVERIFIED"] == 1
