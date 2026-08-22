"""The surface-contract allowlist: internal artifacts render nowhere.

Owner instruction, 2026-08-19, third round on the same material: "internal
artifacts (reasoning traces, capability ceiling, evidence coverage, tiers,
counts, uncertainty) are dropped at the payload boundary and render
nowhere."

Withholding them from the CUSTOMER audience was the previous rule and it
was measured insufficient twice. The audience is a toggle in the browser,
so anybody who moved it met the capability-ceiling table, the evidence
census and a reasoning trace on the same screen as the client's own scores
— which is what the third round's screenshots show. "Nowhere" is a
different rule from "not by default".

These tests pin the difference, because the previous rule passes every
customer-audience assertion while failing the instruction.
"""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_api import redaction  # noqa: E402
from dma_api.redaction import (NEVER_SERVED, NEVER_SERVED_KEYS,  # noqa: E402
                               redact_section)

AUDIENCES = ("internal", "customer", "ae", "")


@pytest.mark.parametrize("audience", AUDIENCES)
@pytest.mark.parametrize("page,section", sorted(NEVER_SERVED))
def test_an_allowlisted_section_is_withheld_from_every_audience(
        page, section, audience):
    data, report = redact_section(page, section, {"rows": [{"a": 1}]}, [],
                                  audience)
    assert data is None, (
        f"{page}.{section} was served to audience {audience!r}. It is on the "
        "allowlist, which means no reader gets it — not that the default "
        "reader does not.")
    assert report["withheld"] is True
    assert report.get("never_served") is True, (
        "the report must distinguish a section withheld BY AUDIENCE from one "
        "that reaches nobody, or an operator reading it cannot tell which "
        "rule fired")


@pytest.mark.parametrize("audience", AUDIENCES)
def test_the_reasoning_trace_reaches_no_audience_at_any_depth(audience):
    """Three traces appeared on one screen: section, roster row and card.

    Stripped by key at any depth for exactly that reason — a per-path rule
    is one a producer has to remember, and the measured leak was on paths
    nobody had marked.
    """
    # pillars[].deltas is inside scores' contract item grammar, so the
    # depth assertion survives the customer allowlist (2026-08-19), which
    # drops non-contract keys before this test would read them.
    payload = {
        "composite": 2.1,
        "r_layer": {"verdict": "ACCEPT", "confidence": "HIGH"},
        "pillars": [{"pillar_id": "P1", "r_layer": {"verdict": "ACCEPT"},
                     "score": {"r_layer": {"verdict": "ACCEPT"}}}],
    }
    out, _ = redact_section("overview", "scores", payload, [], audience)
    assert "r_layer" not in out
    assert "r_layer" not in out["pillars"][0]
    assert "r_layer" not in out["pillars"][0].get("score", {})
    # The finding itself survives; only our argument with ourselves goes.
    assert out["composite"] == 2.1


def test_the_allowlist_is_not_silently_shrunk():
    """Both entries were reported from a live screenshot. Removing one puts
    it back on a client's screen, so a deliberate change has to edit this
    test and say why."""
    assert NEVER_SERVED == frozenset((("overview", "ceilings"),
                                      ("overview", "evidence_coverage")))
    assert NEVER_SERVED_KEYS == ("r_layer",)


def test_r_layer_is_no_longer_only_a_customer_rule():
    """The regression this file exists to prevent.

    Moving `r_layer` back into CUSTOMER_STRIP_KEYS would pass every
    customer-audience test in the suite and restore the exact defect: the
    trace renders the moment a reader moves the audience toggle.
    """
    assert "r_layer" not in redaction.CUSTOMER_STRIP_KEYS


@pytest.mark.parametrize("audience", AUDIENCES)
def test_a_section_not_on_the_allowlist_still_serves(audience):
    out, report = redact_section("overview", "findings",
                                 {"findings": [{"f_id": "F-1"}]}, [], audience)
    assert out is not None and report["withheld"] is False


def test_the_receipt_counts_the_unconditional_pass_too():
    """`report["keys_stripped"] = ...` in the customer branch discarded what
    the unconditional pass had already recorded. A receipt that under-reports
    its own deletions is the defect this module was rewritten to end."""
    out, report = redact_section(
        "overview", "leadership",
        {"roster": [{"name": "X", "r_layer": {"v": 1}, "email": "a@b.c"}]},
        [], "customer")
    assert "roster[0].r_layer" in report["keys_stripped"]
    assert "roster[0].email" in report["keys_stripped"]
    assert out["roster"][0] == {"name": "X"}


def test_the_serve_rules_tag_moved():
    """The ETag carries the rules version. Changing what is served without
    changing the tag serves the old body from every cache that has one."""
    from dma_api import pages
    assert pages.SERVE_RULES == "serve-rules@10", (
        "the allowlist changed what is served; bump SERVE_RULES or caches "
        "keep answering with the body that carried the ceilings table")


def test_build_page_has_no_fail_open_audience_default():
    sig = inspect.signature(__import__("dma_api.pages", fromlist=["pages"])
                            .build_page)
    assert sig.parameters["audience"].default is inspect.Parameter.empty


def test_a_never_served_section_leaves_no_key_behind():
    """Owner, 2026-08-20: "do not include any surface I excluded in the live
    payload." The stub the page body used to emit for an allowlisted section
    (data: null, data_source: "withheld") still NAMED the excluded surface in
    every response, which is inclusion. Negative control for the pre-fix
    tree: `withheld_entry` did not exist — this fails by ImportError there.
    """
    from dma_api.pages import withheld_entry

    # the allowlist absence: no entry at all, the key vanishes
    assert withheld_entry({"withheld": True, "never_served": True}) is None

    # the audience absence keeps its stub: an internal reader previewing the
    # customer body is owed the fact that a surface exists and was withheld
    stub = withheld_entry({"withheld": True})
    assert stub is not None
    assert stub["data"] is None and stub["data_source"] == "withheld"
    assert stub["empty_state"]["kind"] == "withheld_for_audience"


def test_never_served_omission_reaches_the_page_body():
    """The seam above proves the decision; this proves build_page consults
    it — a build loop that inlines the stub again would pass the seam test
    while re-including the excluded keys."""
    import inspect as _inspect
    from dma_api import pages
    src = _inspect.getsource(pages.build_page)
    assert "withheld_entry(" in src, (
        "build_page no longer routes withheld sections through "
        "withheld_entry; the never-served omission is unenforced")
