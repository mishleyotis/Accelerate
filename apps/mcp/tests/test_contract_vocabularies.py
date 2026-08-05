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
