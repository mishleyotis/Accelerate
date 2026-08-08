"""CG-09 over contract-declared vocabularies on plain TEXT columns.

The generated enum registry knows Postgres enums only. `signal` is TEXT, so a
producer that wrote a consequence sentence into it promoted cleanly and left the
D5 timeline's Positive/Neutral/Negative filters matching zero of ten events. The
gate below is what makes that a refused submission instead of a silent page.
"""
from dma_mcp.validation import _check_contract_vocabularies


def _events(signal):
    return {"events": [{"event_date": "2024-03-01", "title": "t", "body": "b",
                        "signal": signal, "claim_label": "FACT"}]}


def test_prose_in_signal_is_refused_and_named():
    body = _events("The analytics practice predates the data strategy, so the "
                   "intent layer is older than its substrate.")
    reasons = _check_contract_vocabularies("context", "timeline", body)
    assert len(reasons) == 1
    r = reasons[0]
    # A verdict names the gate, the JSON path and what was expected.
    assert r["gate_id"] == "CG-09"
    assert r["path"] == "timeline.events[0].signal"
    assert "POSITIVE │ NEUTRAL │ NEGATIVE" in r["message"]
    # and it says where the sentence actually belongs
    assert "maturity_effect" in r["message"]


def test_a_declared_value_passes():
    for v in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
        assert _check_contract_vocabularies("context", "timeline", _events(v)) == []


def test_null_passes_because_absent_is_not_wrong():
    # A derived value is computed or null (invariant 9). Null is a legitimate
    # answer here; a sentence is not.
    assert _check_contract_vocabularies("context", "timeline", _events(None)) == []


def test_a_lowercase_value_is_still_refused():
    # Case matters: the renderer compares against the declared spelling, so
    # "positive" would miss the filter exactly as prose does.
    reasons = _check_contract_vocabularies("context", "timeline", _events("positive"))
    assert len(reasons) == 1
    assert "'positive'" in reasons[0]["message"]


def test_long_prose_is_truncated_in_the_verdict():
    body = _events("x" * 400)
    detail = _check_contract_vocabularies("context", "timeline", body)[0]["message"]
    # The verdict has to be readable; the payload does not get echoed whole.
    assert "…" in detail and len(detail) < 400


def test_techstack_status_vocabulary_is_policed():
    # The charter's correction to the prototype: four states, required per row.
    body = {"items": [{"ts_id": "TS-1", "product": "p", "status": "PRESENT"}]}
    reasons = _check_contract_vocabularies("techstack", "techstack", body)
    assert len(reasons) == 1
    assert "CONFIRMED │ INFERRED │ CLAIMED │ ABSENT" in reasons[0]["message"]
    body["items"][0]["status"] = "CLAIMED"
    assert _check_contract_vocabularies("techstack", "techstack", body) == []


def test_a_section_with_no_declared_vocabulary_is_untouched():
    assert _check_contract_vocabularies("overview", "findings",
                                        {"findings": [{"f_id": "F-1"}]}) == []


def test_a_coined_event_kind_is_refused():
    """Measured on a served run: 4 of 11 events carried TECHNOLOGY (x3) or
    CAPABILITY (x1). Neither is one of the eight, the column is plain TEXT and
    nothing else looked — so those four rendered on D5 and matched no filter.
    A near-miss is not a synonym; it is an event no reader can reach."""
    body = {"events": [{"event_date": "2024-03-01", "kind": "TECHNOLOGY"},
                       {"event_date": "2024-04-01", "kind": "CAPABILITY"},
                       {"event_date": "2024-05-01", "kind": "PLATFORM"}]}
    reasons = _check_contract_vocabularies("context", "timeline", body)
    assert [r["path"] for r in reasons] == ["timeline.events[0].kind",
                                            "timeline.events[1].kind"]
    assert "PLATFORM │ LEADERSHIP │ M&A" in reasons[0]["message"]


def test_a_coined_arc_shape_is_refused():
    """Served value: 'strategy-first, substrate-later', against five words."""
    reasons = _check_contract_vocabularies(
        "context", "timeline", {"arc_shape": "strategy-first, substrate-later"})
    assert len(reasons) == 1 and reasons[0]["path"] == "timeline.arc_shape"
    assert "STEADY_INVESTMENT" in reasons[0]["message"]


def test_a_vocabulary_that_leads_a_clause_accepts_the_clause():
    """`maturity_effect` is contracted as the WORD 'with one clause of
    reasoning', and `arc_shape` as one of five 'with one sentence of
    evidence'. An exact-match rule here would have refused all eleven events
    of a run doing precisely what it was asked — a gate that fires on
    compliance is worse than no gate."""
    body = {"arc_shape": "STEADY_INVESTMENT — four dated investments, no gaps",
            "events": [{"maturity_effect": "ADVANCED — the core is no longer "
                                           "the constraint"},
                       {"maturity_effect": "NEUTRAL"}]}
    assert _check_contract_vocabularies("context", "timeline", body) == []


def test_the_clause_cannot_smuggle_in_a_coined_word():
    body = {"events": [{"maturity_effect": "IMPROVED — reads like one of the "
                                           "three, is not one of the three"}]}
    reasons = _check_contract_vocabularies("context", "timeline", body)
    assert len(reasons) == 1
    assert "ADVANCED │ CONSTRAINED │ NEUTRAL" in reasons[0]["message"]


def test_per_item_provenance_vocabularies_are_per_surface():
    """The contract states a DIFFERENT vocabulary per surface, which is why
    the column 0027 adds is TEXT and not provenance_t: an enum column would
    abort the promote transaction on a value the contract itself declares."""
    ok = _check_contract_vocabularies(
        "platform", "starters", {"starters": [{"provenance": "TEMPLATE_FILL"}]})
    assert ok == []
    bad = _check_contract_vocabularies(
        "platform", "starters", {"starters": [{"provenance": "DERIVED"}]})
    assert len(bad) == 1 and "TEMPLATE_FILL │ ANALYST" in bad[0]["message"]
    # and the recommendation's own two, which are not the starter's two
    assert _check_contract_vocabularies(
        "platform", "recommendations",
        {"recommendations": [{"provenance": "DERIVED"}]}) == []
