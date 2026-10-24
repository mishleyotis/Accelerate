"""The customer receives a REDUCED sentiment card (owner decision 1, 2026-10-04).

TRD §11 withheld `overview.sentiment` from the customer audience whole. The
SWBC gold audit (D-34, S-02) found the customer card returning null with no
badge, and the owner decided instead: customers get ratings bars + themes,
WITHOUT cell codes, internal sources, cap vocabulary or r_layer; the internal
audience keeps the full card. `thought_leadership` stays withheld.

So for the customer, and only the customer:
  · bars and themes serve; gap_analysis, narrative_thread (the analyst's
    reading of the card) and displayed_lines (a declared count) do not;
  · a theme loses `cap_statement` and `mapped_subcap_ids` — the cap argument
    and the cell codes ARE the internal half of the card;
  · any remaining field naming a cell code or cap vocabulary goes whole, and
    a theme left without its `theme` sentence is dropped rather than served
    as an empty row;
  · a bar or theme resting only on internal-origin evidence is withheld.

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import redaction                                      # noqa: E402
from dma_api.redaction import redact_section                      # noqa: E402

BODY = {
    "bars": [
        {"audience": "customer", "source": "App store", "rating": 4.1,
         "scale": 5, "n": 812, "as_of": "2026-08-01", "url": "https://x.example",
         "e_id": "E-CC-10", "trend_vs_prior": None},
        {"audience": "employee", "source": "Staff survey", "rating": 3.2,
         "scale": 5, "n": 140, "as_of": "2026-06-01", "url": None,
         "e_id": "E-CC-11", "trend_vs_prior": None},
    ],
    "themes": [
        {"theme": "Borrowers praise the online application and dislike "
                  "surprise fees", "audience": "customer", "direction": "mixed",
         "cap_statement": "Neither caps nor lifts the cell, scored 3.0.",
         "mapped_subcap_ids": ["P2C2.2.1"], "e_ids": ["E-CC-10"]},
        {"theme": "Complaints concentrate on P3C2.1.1 payment delays",
         "audience": "customer", "direction": "negative",
         "cap_statement": "Caps P3C2.1.1 at M3.",
         "mapped_subcap_ids": ["P3C2.1.1"], "e_ids": ["E-CC-10"]},
        {"theme": "Staff describe manual hand-offs between lines",
         "audience": "employee", "direction": "negative",
         "cap_statement": "x", "mapped_subcap_ids": ["P3C1.1.1"],
         "e_ids": ["E-CC-11"]},
    ],
    "gap_analysis": {"b2b_b2c": "x", "internal_external": "y", "e_ids": []},
    "narrative_thread": "The analyst's reading of the card.",
    "displayed_lines": 2,
    "r_layer": {"verdict": "ACCEPT"},
    "e_ids": ["E-CC-10", "E-CC-11"],
}


def _customer(body=BODY, scope=None):
    return redact_section("overview", "sentiment", copy.deepcopy(body), [],
                          "customer", evidence_scope=scope)


def test_the_customer_receives_the_card_rather_than_null():
    assert ("overview", "sentiment") not in redaction.CUSTOMER_WITHHELD
    assert ("overview", "thought_leadership") in redaction.CUSTOMER_WITHHELD
    out, rep = _customer()
    assert out is not None and rep["withheld"] is False
    assert len(out["bars"]) == 2


def test_cap_vocabulary_and_cell_codes_are_stripped():
    out, _ = _customer()
    for t in out["themes"]:
        assert "cap_statement" not in t and "mapped_subcap_ids" not in t
    # The theme that named a cell code in its own sentence is dropped whole.
    assert [t["theme"] for t in out["themes"]] == [
        "Borrowers praise the online application and dislike surprise fees",
        "Staff describe manual hand-offs between lines"]
    for k in ("gap_analysis", "narrative_thread", "displayed_lines",
              "r_layer"):
        assert k not in out, k


def test_a_bar_or_theme_resting_on_internal_evidence_is_withheld():
    out, _ = _customer(scope={"withheld": {"E-CC-11"}, "attribution": {}})
    assert [b["e_id"] for b in out["bars"]] == ["E-CC-10"]
    assert [t["audience"] for t in out["themes"]] == ["customer"]
    assert out["e_ids"] == ["E-CC-10"]


def test_the_internal_card_is_whole():
    out, _ = redact_section("overview", "sentiment", copy.deepcopy(BODY), [],
                            "internal")
    assert len(out["themes"]) == 3
    assert out["themes"][0]["cap_statement"]
    assert out["themes"][0]["mapped_subcap_ids"] == ["P2C2.2.1"]
    assert out["narrative_thread"]
