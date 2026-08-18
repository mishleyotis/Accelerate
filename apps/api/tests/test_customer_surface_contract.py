"""What a client may be sent, asserted rather than assumed.

Every check here failed, or would have failed, against a real promoted body.

The one that started it: `overview.evidence_coverage` — the tier histogram,
the item and fact counts, the self-sourced share — was served to the CUSTOMER
audience in full on both promoted clients. Nothing rendered it, because
`adaptCoverage` in the web adapter happens to drop those keys, so a hand check
of the screen agreed with a green test suite and neither was looking at the
body on the wire. That pairing is the worst kind: the leak is real, the
evidence of it is invisible, and every reviewer is satisfied.

So these tests read the BODY, never the page. A rendering accident must never
again be what stands between an internal construct and a client.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api.redaction import (AUDIENCES, CUSTOMER_WITHHELD,
                               CUSTOMER_WITHHELD_PAGES, CUSTOMER_STRIP_KEYS,
                               normalise_audience, redact_section)

# The census fields. Named individually rather than checked as a section, so
# that moving one of them into another section does not quietly re-open this.
CENSUS_KEYS = ("tiers", "fact_count", "item_count", "gate_pct",
               "self_sourced_pct", "claim_classes", "per_pillar")


def _census_body() -> dict:
    """Shaped like the real thing — Logix run d7ed1d90, overview.evidence_coverage."""
    return {
        "tiers": [{"tier": "T1", "count": 4, "pct": 6.3},
                  {"tier": "T5", "count": 17, "pct": 27.0}],
        "fact_count": 59, "item_count": 63, "gate_pct": 80,
        "self_sourced_pct": 30.2, "overall_pct": 33.0,
        "claim_classes": [{"claim_label": "FACT", "count": 59, "pct": 93.7}],
        "per_pillar": [{"pillar_id": "P1", "pct": 35.3, "below_gate": True}],
        "r_layer": {"verdict": "ACCEPT", "hypothesis": "reach is honest"},
        "internal_only": ["r_layer"],
    }


def test_the_evidence_census_is_withheld_from_the_customer():
    """G9. The regression this file exists for."""
    out, rep = redact_section("overview", "evidence_coverage",
                              _census_body(), ["r_layer"], "customer")
    assert out is None, (
        "overview.evidence_coverage reached the customer body. It is the "
        "census of how well WE evidenced the assessment — our method showing "
        "through — and it is not the client's to read.")
    assert rep["withheld"] is True


def test_the_internal_audience_still_gets_the_census():
    """The other half. Withholding it from the client must not cost the
    analyst the figure that explains every ceiling on the page."""
    out, _ = redact_section("overview", "evidence_coverage",
                            _census_body(), ["r_layer"], "internal")
    assert out is not None
    for key in CENSUS_KEYS:
        assert key in out, f"the internal body lost {key}"
    assert out["r_layer"]["verdict"] == "ACCEPT"


@pytest.mark.parametrize("key", CENSUS_KEYS)
def test_no_census_field_survives_anywhere_in_a_customer_body(key):
    """Belt and braces, and the reason the keys are named one by one: a
    census field moved into a section that is NOT withheld would re-open the
    leak with this file still green. If one of these ever legitimately
    belongs on a client surface, delete it from CENSUS_KEYS deliberately."""
    body = {key: _census_body()[key], "narrative_thread": "a real sentence."}
    for page, section in (("overview", "evidence_coverage"),):
        out, _ = redact_section(page, section, dict(body), [], "customer")
        assert out is None or key not in out


def test_r_layer_never_reaches_a_customer_body_however_it_is_marked():
    """Restates the invariant from the key-strip side. `r_layer` is declared
    per SECTION and was marked per PATH, which is how it reached the customer
    body on 36 paths across two clients."""
    assert "r_layer" in CUSTOMER_STRIP_KEYS
    body = {"r_layer": {"verdict": "ACCEPT"}, "rows": [{"r_layer": {"x": 1}}]}
    out, _ = redact_section("overview", "firmographics", body, [], "customer")
    assert "r_layer" not in out
    assert "r_layer" not in out["rows"][0], "nested r_layer survived"


def test_the_withheld_set_is_not_silently_shrunk():
    """A guard on the guard. Removing a section from CUSTOMER_WITHHELD is a
    decision about what a client may read, and it must be made in a diff a
    reviewer can see rather than by an import that quietly resolves smaller."""
    assert CUSTOMER_WITHHELD >= frozenset((
        ("overview", "ceilings"),
        ("overview", "sentiment"),
        ("overview", "thought_leadership"),
        ("overview", "evidence_coverage"),
        ("heatmap", "alerts"),
        ("heatmap", "evidence_age"),
        ("heatmap", "cohort_patterns"),
    ))
    assert "context" in CUSTOMER_WITHHELD_PAGES


def test_an_unknown_audience_is_a_customer():
    """Default-deny, restated where a reader of this file will look for it."""
    for value in (None, "", "  ", "INTERNAL_PREVIEW", "analyst", "internal2"):
        assert normalise_audience(value) == "customer", repr(value)
    # Trimming and case-folding a legitimate value is not the same thing as
    # guessing at an illegitimate one, and both belong in this test so the
    # difference stays deliberate.
    for value in ("internal", "  Internal ", "INTERNAL"):
        assert normalise_audience(value) == "internal", repr(value)
    assert set(AUDIENCES) == {"customer", "internal"}


def test_build_page_has_no_audience_default():
    """The fail-open that was one careless call away. `build_page` defaulted
    to `audience="internal"` while the module that decides redaction defaults
    to `customer`; the two disagreed, and only the twelve HTTP routes passing
    an explicit value kept it honest."""
    import inspect

    from dma_api.pages import build_page

    param = inspect.signature(build_page).parameters["audience"]
    assert param.default is inspect.Parameter.empty, (
        "build_page must not default `audience`. A caller that forgets it "
        "should fail loudly, not be handed the internal body.")
