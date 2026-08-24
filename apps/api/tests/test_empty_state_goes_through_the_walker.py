"""The one part of a section that never went through the redaction walker.

MEM-0137, BLOCKER. `pages.py` redacted `built["data"]` and then attached
`env["empty_state"]` beside it, straight off the envelope. So every rule in
`redaction` — the internal_only paths, CUSTOMER_STRIP_KEYS, the vendor and
seller-voice safety nets, the serve allowlist — applied to the section's
content and to nothing in its empty state.

MEASURED IN PRODUCTION, 2026-08-24, on three promoted clients:
`platform.starters.empty_state.sources_searched` serves a customer
`get_evidence('platform')`, `r_layer` and the literal string
`CUSTOMER_WITHHELD`; `heatmap.safeguard_gates.empty_state.sources_searched`
serves SG-01 and SG-V4. Ten fields between them, on pages a client opens.

An empty state is where this hurts most. It is the surface a reader lands on
when there is nothing else there — the one place they read every word — and
its whole job is to say "here is what we looked for", which is a sentence
about OUR machinery unless somebody rewrites it for them.

The internal audience keeps the ladder. `sources_searched` IS the evidence
that a search ran, and stripping it there would destroy the distinction the
ladder exists to make: "I looked and found nothing" against "I could not
look".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api.redaction import redact_empty_state          # noqa: E402

ALLOWLIST = json.loads(
    (Path(__file__).resolve().parents[1] / "dma_api"
     / "customer_allowlist.json").read_text())
KEEP = set(ALLOWLIST["empty_state_keys"])

#: T. Rowe Price's real served empty_state, trimmed for length. Every key
#: here was in the customer body in production.
PRODUCTION = {
    "kind": "held_for_internal",
    "reason": ("These five openers are prepared for the account team's own "
               "first conversations, and every fact behind them already "
               "appears in this page's served findings in client-facing "
               "form."),
    "closure_condition": "nothing to close; the facts are already served",
    "sources_searched": [
        "get_page_contract('platform') — read for the starters item contract",
        "r_layer",
        "CUSTOMER_WITHHELD",
    ],
    "r_layer": "L3",
    "queries_run": 4,
}


# ── the customer body ─────────────────────────────────────────────────

def test_the_measured_leak_is_gone():
    out, dropped = redact_empty_state(dict(PRODUCTION), "customer")
    blob = json.dumps(out)
    for leaked in ("get_evidence(", "get_page_contract(", "r_layer",
                   "CUSTOMER_WITHHELD"):
        assert leaked not in blob, leaked
    assert "sources_searched" in dropped


def test_only_the_four_allowed_keys_survive():
    out, _ = redact_empty_state(dict(PRODUCTION), "customer")
    assert set(out) <= KEEP, set(out) - KEEP
    assert set(out) == {"kind", "reason", "closure_condition"}


def test_the_reason_a_client_can_read_is_kept():
    """The point is not to empty the empty state. A reader must still learn
    why the surface is blank."""
    out, _ = redact_empty_state(dict(PRODUCTION), "customer")
    assert out["reason"] == PRODUCTION["reason"]
    assert out["closure_condition"]


def test_what_was_dropped_is_reported_not_silent():
    _out, dropped = redact_empty_state(dict(PRODUCTION), "customer")
    assert dropped
    for key in ("sources_searched", "r_layer", "queries_run"):
        assert key in dropped, key


@pytest.mark.parametrize("gate", ["SG-01", "SG-V4", "CG-49"])
def test_a_gate_id_in_sources_searched_never_reaches_a_customer(gate):
    """heatmap.safeguard_gates.empty_state.sources_searched, measured live."""
    out, _ = redact_empty_state(
        {"reason": "No safeguard applied.", "sources_searched": [gate]},
        "customer")
    assert gate not in json.dumps(out)


# ── the internal audience keeps its ladder ────────────────────────────

def test_internal_keeps_everything():
    out, dropped = redact_empty_state(dict(PRODUCTION), "internal")
    assert out == PRODUCTION
    assert dropped == []


def test_the_ladder_is_the_reason_internal_keeps_it():
    """`sources_searched` IS the evidence a search ran. Without it, an honest
    thin surface and a broken one look identical, which is the defect this
    whole build keeps removing."""
    out, _ = redact_empty_state(dict(PRODUCTION), "internal")
    assert out["sources_searched"] == PRODUCTION["sources_searched"]


# ── prose carries what a key filter cannot see ────────────────────────

def test_a_finding_id_in_the_kept_reason_takes_the_WHOLE_key():
    """The case a key filter structurally cannot see: `reason` is allowed and
    its VALUE is where the id sits.

    And the whole key goes, never half a sentence — the owner-level decision
    recorded on CG-49 is that surgery on prose is the wrong repair:
    "stripping prose leaves a client reading half a sentence, while refusing
    it makes the producer write the sentence a client can read." At serve time
    there is no producer to ask, so the sentence is withheld whole and the
    receipt says one was. The right fix stays upstream."""
    out, dropped = redact_empty_state(
        {"reason": "Held pending MEM-0081; see the internal note.",
         "kind": "held_for_internal"}, "customer")
    assert "MEM-0081" not in json.dumps(out)
    assert out == {"kind": "held_for_internal"}, "surgery, not withholding"
    assert dropped == ["reason (names MEM-0081)"], \
        "the receipt must name what it found, so a producer can fix the source"


@pytest.mark.parametrize("prose", [
    "no regulatory gate applies to this institution",
    "the connector between the two core systems was retired in 2021",
    "staged for the next reporting cycle",
    "we searched the register and the filings and found nothing",
])
def test_ordinary_english_is_not_machinery(prose):
    """A rule that refuses these teaches producers to fight it. "gate",
    "connector" and "staged" are words a client may legitimately read; the
    pattern matches IDENTIFIERS and CALL SYNTAX, not vocabulary."""
    out, dropped = redact_empty_state({"reason": prose}, "customer")
    assert out == {"reason": prose}, dropped
    assert dropped == []


def test_the_vendor_safety_net_runs_over_the_kept_prose():
    out, dropped = redact_empty_state(
        {"reason": "Zennify will prepare these openers before the call."},
        "customer")
    assert "Zennify" not in json.dumps(out) or dropped


# ── shapes that must not break it ─────────────────────────────────────

@pytest.mark.parametrize("value", [None, {}, [], "text", 3, True])
def test_a_non_dict_empty_state_passes_through_untouched(value):
    out, dropped = redact_empty_state(value, "customer")
    assert out == value or (value == {} and out is None)
    assert dropped == []


def test_an_empty_state_of_only_forbidden_keys_becomes_none():
    """Nothing left to say is `None`, not `{}` — a bare object renders as a
    card with no text in it."""
    out, dropped = redact_empty_state(
        {"sources_searched": ["x"], "r_layer": "L3"}, "customer")
    assert out is None
    assert len(dropped) >= 2


def test_the_callers_object_is_never_mutated():
    """The promoted payload is shared across readers; one audience's redaction
    must not reach another's response."""
    original = json.loads(json.dumps(PRODUCTION))
    redact_empty_state(PRODUCTION, "customer")
    assert PRODUCTION == original


# ── it is wired into the serving path ─────────────────────────────────

def test_pages_routes_the_empty_state_through_it():
    import inspect

    from dma_api import pages
    src = inspect.getsource(pages)
    assert "redact_empty_state(\n            env.get(\"empty_state\"), audience)" \
        in src, "pages.py must not read the envelope's empty_state directly"
    assert 'empty = env.get("empty_state")\n' not in src, \
        "the raw read is back and MEM-0137 is live again"


def test_the_redaction_receipt_counts_the_empty_state_too():
    """A client needs to tell blank-because-withheld from blank-because-empty,
    and the count is the receipt that says which."""
    import inspect

    from dma_api import pages
    src = inspect.getsource(pages)
    assert "+ len(empty_dropped))" in src


def test_the_four_keys_are_the_allowlists_own():
    """Not a second hand-written list. `empty_state_keys` is generated from
    the contract, and a rule held in two places drifts."""
    import inspect

    from dma_api import redaction
    src = inspect.getsource(redaction.redact_empty_state)
    assert 'allow["empty_state_keys"]' in src
    assert KEEP == {"reason", "closure_condition", "closure", "kind"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
