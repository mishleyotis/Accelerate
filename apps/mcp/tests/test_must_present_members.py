"""CG-16 — the members a list field must contain, not just that it exists.

THE ROOT CAUSE. Every "must-present set" in this product lived only as prose
inside a contract's `doc` string. `required: true` applies to the CONTAINER —
that `firmographics.fields` is a list — and CG-02 fires on
`body.get(fname) is None`. A payload carrying a list with one member satisfied
every gate the connector has.

Reported by the build owner as "changes do not get promoted": `website` was
added to the firmographics contract, no gate asked for it, and the next run
would have omitted it exactly as the last one did. Measured on the live
reference the same day — 12 firmographics fields served, no website among
them, while the producer's own absence ladder on that same section named the
firm's domain twice.

The design decision under test is the SECOND case below: a field the ladder
could not close is a finding and must stay legal, or this gate would push
producers into guessing. Held-with-a-reason passes; silence does not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_must_present, _norm_member

SPEC = {"type": "list", "item_type": "object", "must_present_key": "field",
        "must_present": ["employees", "website", "founded_year"],
        "must_present_any": [["AUM", "total_assets"]]}


def _f(field, value=None, quarantined=False, reason=None):
    return {"field": field, "value": value, "quarantined": quarantined,
            "quarantine_reason": reason}


def _run(items, spec=SPEC, empty_declared=False):
    return _check_must_present("firmographics", "fields", spec, items,
                               empty_declared)


COMPLETE = [_f("employees", 370), _f("website", "client.example"),
            _f("founded_year", 1923), _f("AUM", 18.0)]


def test_a_complete_set_passes():
    assert _run(COMPLETE) == []


# ── the defect, in the exact shape it shipped ─────────────────────────
def test_a_missing_member_blocks_and_names_it():
    out = _run([i for i in COMPLETE if i["field"] != "website"])
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-16" and r["severity"] == "block"
    assert "'website'" in r["message"] and "absent" in r["message"]


def test_the_live_reference_payload_is_refused_by_this_gate():
    """The 12-field shape actually served: three held with reasons, and no
    website. Exactly one reason, naming exactly the missing member — the gate
    must not also punish the three honest em dashes."""
    served = [_f("AUM", 18.0), _f("employees", 370), _f("branches", 6),
              _f("HQ", "Vancouver, British Columbia"),
              _f("primary_regulator", "CIRO"), _f("charter", "Investment Dealer"),
              _f("revenue", None, True, "private firm; no filings exist"),
              _f("CAGR", None, True, "needs a series; one dated point found"),
              _f("founded_year", None, True, "site and registry both 403")]
    out = _run(served)
    assert len(out) == 1
    assert "'website'" in out[0]["message"]


# ── the case that must stay legal, or producers start guessing ────────
def test_a_member_held_with_a_reason_passes():
    items = [_f("employees", 370), _f("AUM", 18.0),
             _f("website", None, True, "the firm's own site returns HTTP 403"),
             _f("founded_year", None, True, "registry returns HTTP 403")]
    assert _run(items) == []


def test_quarantined_with_no_reason_is_not_held_it_is_blank():
    """`quarantined: true` with an empty reason is the exemption bought for
    free — the same shape as a ladder field filled with a template."""
    items = [_f("employees", 370), _f("AUM", 18.0), _f("founded_year", 1923),
             _f("website", None, True, "   ")]
    out = _run(items)
    assert len(out) == 1
    assert "no quarantine reason" in out[0]["message"]


def test_present_but_null_with_no_quarantine_blocks_differently():
    items = [_f("employees", 370), _f("AUM", 18.0), _f("founded_year", 1923),
             _f("website", None)]
    out = _run(items)
    assert len(out) == 1
    assert "no value and no quarantine reason" in out[0]["message"]
    # a different diagnosis from "absent", because a different repair
    assert "absent" not in out[0]["message"]


def test_an_empty_string_value_is_blank_not_stated():
    items = [_f("employees", 370), _f("AUM", 18.0), _f("founded_year", 1923),
             _f("website", "")]
    assert len(_run(items)) == 1


# ── the either/or, which a flat membership cannot express ─────────────
def test_either_member_of_an_any_group_satisfies_it():
    for alt in ("AUM", "total_assets"):
        items = [_f("employees", 1), _f("website", "x.example"),
                 _f("founded_year", 1), _f(alt, 5.0)]
        assert _run(items) == [], alt


def test_an_any_group_with_none_of_its_members_blocks_once():
    items = [_f("employees", 1), _f("website", "x.example"), _f("founded_year", 1)]
    out = _run(items)
    assert len(out) == 1
    assert "AUM" in out[0]["message"] and "total_assets" in out[0]["message"]


# ── shape and robustness ──────────────────────────────────────────────
def test_member_names_normalise_on_both_sides():
    """`founded_year`, `Founded Year` and `founded-year` are one member.
    Two normalisers would be the drift class this build keeps paying for."""
    assert _norm_member("Founded Year") == _norm_member("founded-year") \
        == _norm_member("founded_year")
    items = [_f("Employees", 370), _f("Web Site", "x.example"),
             _f("Founded-Year", 1923), _f("Total Assets", 5.0)]
    # `website` vs `Web Site` normalise differently on purpose: the contract
    # names ONE canonical spelling, and a producer inventing another is a
    # contract fork rather than a synonym.
    out = _run(items)
    assert [("'website'" in r["message"]) for r in out] == [True]


def test_a_section_declaring_an_empty_state_and_sending_nothing_is_silent():
    """CG-02 already governs whether a section may be empty at all; this gate
    must not double-refuse an honest empty."""
    assert _run([], empty_declared=True) == []


def test_an_empty_list_WITHOUT_an_empty_state_is_still_refused():
    out = _run([], empty_declared=False)
    assert len(out) == 4          # three members plus the any-group


def test_a_spec_declaring_no_must_present_is_untouched():
    assert _run(COMPLETE, spec={"type": "list", "item_type": "object"}) == []


def test_non_dict_items_do_not_raise():
    out = _run(["nonsense", 42, None] + COMPLETE)
    assert out == []


def test_the_real_contract_declares_the_set_machine_readably():
    """The gate is worthless if the contract still states the set only in
    prose. This asserts the JSON carries it, which is what the gate reads."""
    from dma_mcp.contracts import sections
    spec = sections("overview")["firmographics"]["fields"]["fields"]
    assert "website" in spec["must_present"]
    assert spec["must_present_key"] == "field"
    assert any("AUM" in g for g in spec["must_present_any"])
