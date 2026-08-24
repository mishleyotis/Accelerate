"""CG-49 — a client-visible absence does not name this system's machinery.

Invariant 5 is default-deny redaction, and the serve layer honours it at KEY
grain: `customer_allowlist.json` keeps `reason`, `closure_condition`,
`closure` and `kind` from an empty_state and drops the rest, so
`sources_searched` and `r_layer` never reach a customer.

What a key-grain allowlist structurally cannot see is what those four kept
keys SAY. MEM-0137 measured the leak on a promoted run; the sweep that
produced this gate found it STILL LIVE on all five clients in the directory,
12 fields between them — including `context.issue_register.empty_state.reason`
naming MEM-0209 and MEM-0210, which the same session wrote hours earlier.

THE HARD PART IS WHAT NOT TO MATCH. "gate", "connector", "staged" and
"promoted" all appeared in that sweep, and all of them are ordinary English —
"no regulatory gate applies to this division" is exactly the sentence a
client should read. A gate that refused those would be refusing good prose,
which is the failure this build has already paid for on the vetter and on
CG-47. Only tokens that cannot occur by accident are matched, and the
negative cases below are the ones that keep it that way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402


def run(page, section, empty_state):
    return V2._check_customer_empty_state_prose(
        page, {section: {"empty_state": empty_state}})


def ids(out):
    return [r["gate_id"] for r in out]


# ── the leaks measured on live promoted runs ──────────────────────────

@pytest.mark.parametrize("page,section,key,text,token", [
    ("context", "issue_register", "reason",
     "They are real observations and they are not the client's matters, so "
     "they have been recorded where assessment defects belong (MEM-0209, "
     "MEM-0210) and removed from here.", "MEM-0209"),
    ("platform", "starters", "closure_condition",
     "Held under CUSTOMER_WITHHELD pending MEM-0081.", "CUSTOMER_WITHHELD"),
    ("heatmap", "cohort_patterns", "reason",
     "No cohort could be assembled; see MEM-0099.", "MEM-0099"),
    ("heatmap", "safeguard_gates", "reason",
     "SG-01 and SG-06 did not run for this assessment.", "SG-01"),
])
def test_each_measured_leak_is_refused(page, section, key, text, token):
    out = run(page, section, {key: text})
    assert ids(out) == ["CG-49"], out
    assert token in out[0]["message"]
    assert out[0]["path"] == f"{page}.{section}.empty_state.{key}"
    assert out[0]["severity"] == "block"


def test_the_verdict_shows_the_repair_rather_than_only_refusing():
    """The substance never has to be lost, and the verdict says so — a gate
    that only refuses teaches a producer to delete the sentence."""
    out = run("context", "issue_register",
              {"reason": "recorded as MEM-0209 and MEM-0210"})
    m = out[0]["message"]
    assert "recorded where assessment defects belong" in m
    assert "r_layer" in m, "and where the id does belong"


def test_the_client_safe_rewrite_passes():
    assert run("context", "issue_register", {
        "reason": "No open matter of this division's own was located. Two "
                  "observations about how this assessment was evidenced are "
                  "recorded where assessment defects belong, and removed "
                  "from here.",
        "closure_condition": "A regulatory action, conduct matter or "
                             "disclosed incident naming the division "
                             "itself."}) == []


# ── what must NOT be matched, which is most of the vocabulary ─────────

@pytest.mark.parametrize("text", [
    "No regulatory gate applies to a division of this size.",
    "The connector between the two systems was never built.",
    "Nothing has been staged for this quarter yet.",
    "The transaction was promoted internally before it closed.",
    "A gate review is scheduled for the next cycle.",
])
def test_ordinary_english_is_not_a_leak(text):
    """These words all appeared in the live sweep. Refusing them would refuse
    the sentence a client should read."""
    assert run("context", "issue_register", {"reason": text}) == [], text


@pytest.mark.parametrize("text", [
    "Assets grew to $3.71bn by 31 March 2026.",
    "Rated 4.3 over 4,262 ratings on the Android store.",
    "Searched the FDIC and OCC enforcement databases; neither names it.",
])
def test_real_client_facing_prose_passes(text):
    assert run("overview", "sentiment", {"reason": text}) == [], text


# ── the tokens that cannot occur by accident ──────────────────────────

@pytest.mark.parametrize("token", [
    "MEM-0209", "REF-0061", "CG-46", "AG-03", "ET-04", "SG-01", "SG-V4",
    "CUSTOMER_WITHHELD", "no_staged_submission",
    "get_evidence(", "get_report_bundle(", "promote_run(",
    "submit_page_payload(", "register_evidence(", "record_finding(",
])
def test_every_unambiguous_identifier_is_caught(token):
    out = run("platform", "starters", {"reason": f"Blocked by {token} today."})
    assert ids(out) == ["CG-49"], token


def test_all_four_customer_visible_keys_are_read():
    for key in V2.CUSTOMER_EMPTY_STATE_KEYS:
        assert ids(run("platform", "starters", {key: "see MEM-0001"})) == \
            ["CG-49"], key


def test_the_key_list_mirrors_the_serve_allowlist():
    """A key the API starts serving and this gate stops reading is a leak
    that reopens silently."""
    import json
    api = Path(__file__).resolve().parents[3] / "apps" / "api" / "dma_api" \
        / "customer_allowlist.json"
    served = set(json.loads(api.read_text())["empty_state_keys"])
    assert served == set(V2.CUSTOMER_EMPTY_STATE_KEYS), (
        f"the API serves {sorted(served)} but this gate reads "
        f"{sorted(V2.CUSTOMER_EMPTY_STATE_KEYS)}")


def test_keys_the_customer_never_sees_are_not_this_gates_business():
    """`sources_searched` and `r_layer` are dropped by the serve allowlist,
    so a finding id there is correct and must not be refused — that is where
    the verdict tells producers to put it."""
    assert run("context", "issue_register", {
        "reason": "No open matter was located.",
        "sources_searched": ["the register behind MEM-0209"],
        "r_layer": {"note": "see MEM-0210"}}) == []


# ── scope and safety ──────────────────────────────────────────────────

def test_a_section_with_no_empty_state_is_untouched():
    assert V2._check_customer_empty_state_prose(
        "context", {"issue_register": {"issues": []}}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"s": "not-a-dict"},
                                 {"s": {"empty_state": "prose"}},
                                 {"s": {"empty_state": {"reason": None}}},
                                 {"s": {"empty_state": {"reason": 7}}}])
def test_malformed_payloads_do_not_raise(bad):
    V2._check_customer_empty_state_prose("context", bad)


def test_every_leaking_section_is_named_not_just_the_first():
    out = V2._check_customer_empty_state_prose("heatmap", {
        "cohort_patterns": {"empty_state": {"reason": "see MEM-0099"}},
        "safeguard_gates": {"empty_state": {"reason": "SG-01 did not run"}}})
    assert len(out) == 2


def test_the_finding_list_is_bounded():
    payload = {f"s{i}": {"empty_state": {"reason": "see MEM-0001"}}
               for i in range(30)}
    assert len(V2._check_customer_empty_state_prose("heatmap", payload)) <= 6


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-49" in GATES
    assert GATES["CG-49"][-1] == "block"
    why = GATES["CG-49"][3]
    assert "key grain" in why.lower() or "KEY grain" in why
    assert "MEM-0209" in why, "the registry names the leak this build wrote"
    assert "refusing good prose" in GATES["CG-49"][2], (
        "and what it deliberately does not match, so nobody widens it into "
        "a gate that refuses 'no regulatory gate applies'")


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_customer_empty_state_prose" in src, \
        "CG-49 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
