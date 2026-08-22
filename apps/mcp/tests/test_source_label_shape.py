"""CG-36 — a source label names a document; it does not locate a quote.

Reported 2026-08-22: "the focus area heatmap drilldown has very different
shapes as required by the golden standards", with a screenshot of a SOURCE
line running three wrapped lines under a clipped focus-area title.

"Different shapes" turned out to be measurable rather than a matter of taste.
Both clients pass the same contract, carry the same field set and the same
section keys; what differs is length, and only in the fields the producer
writes freely:

    field              Baxter (golden)   T. Rowe Price
    source_document       37-52            178-266     <- this gate
    name                  59-65             94-106
    verbatim_quote       137-164            105-200     (comparable)
    currency_note        141-220            276-333

Only `source_document` is gated here, because only it has a rule that can be
stated without arguing about prose style: it is a CITATION, and a citation
names a document. The others are reported as a shape observation, not refused.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                   # noqa: E402
from dma_mcp.validation import (SOURCE_LABEL_MAX,                 # noqa: E402
                                _check_source_label_is_a_citation as label)

#: The four T. Rowe Price labels, verbatim off the promoted run.
TRP = [
    "T. Rowe Price press release — T. Rowe Price Announces Creation of Global "
    "Strategy Function (¶4 of the release (Sharps quote), immediately after "
    "¶3's introduction of Andrew Reich)",
    "T. Rowe Price Group Q2 2026 Earnings Conference Call Transcript (Motley "
    "Fool transcript of the 2026-07-31 call) (Prepared remarks — Rob Sharps' "
    "opening statement, AI section (after the ETF/SMA platform-growth "
    "discussion, before the governance/upskilling discussion))",
    "T. Rowe Price press release — T. Rowe Price Announces Chief Operating "
    "Officer Departure and Launch of New Technology, Data and Operations "
    "Function (¶6 of the release (Sharps quote), immediately after ¶5's "
    "introduction of Ramon Richards)",
    "T. Rowe Price Retirement Plan Services — Financial Wellness Approach "
    "(troweprice.com) ('Financial wellness' section — subheading beneath the "
    "page's primary heading, directly above the three-statistic stat block)",
]

#: Baxter's four, verbatim off run c1351d25. These are the golden standard the
#: report was measured against, so they are the test's real fixture.
BCU = [
    "PYMNTS — BCU Data Culture & AI panel (2025-08)",
    "Salesforce customer story — BCU Agentforce (2026-01)",
    "SavvyMoney / BCU partnership outcomes",
    "CULytics — BCU digital transformation (2020-09)",
]


def _fa(*docs):
    return {"focus_areas": [{"fa_id": f"FA-{i+1}", "source_document": d}
                            for i, d in enumerate(docs)]}


# ── the defect ──


def test_every_t_rowe_price_label_is_refused():
    out = label("focus_areas", _fa(*TRP))
    assert len(out) == 4, "all four carried a locator note or ran past the ceiling"
    assert [r["path"] for r in out] == [
        f"focus_areas.focus_areas[{i}].source_document" for i in range(4)]


#: The clause that says WHICH of the two rules fired. Both messages end with
#: the same advice, which mentions a locator note either way — so the reason
#: has to be read from the reason clause, not from the whole string.
FOUND_LOCATOR = "it carries a locator note"


def test_the_refusal_names_the_locator_it_found():
    out = label("focus_areas", _fa(TRP[0]))
    assert FOUND_LOCATOR in out[0]["message"]
    assert "¶4 of the release" in out[0]["message"], (
        "showing the offending parenthetical is what makes it fixable without "
        "the producer hunting for it")


def test_a_long_label_with_no_locator_is_refused_on_length_only():
    """The honest reason matters: told "locator note" for a plain long title,
    a producer goes looking for a parenthetical that is not there."""
    out = label("focus_areas", _fa("Publisher — " + "a very long subject " * 8))
    assert len(out) == 1
    assert FOUND_LOCATOR not in out[0]["message"]
    assert f"{SOURCE_LABEL_MAX}-character ceiling" in out[0]["message"]


def test_a_short_label_with_a_locator_is_still_refused():
    """Length is not the rule, it is one of two. A brief locator note is the
    same defect in fewer characters."""
    out = label("focus_areas", _fa("PR Newswire — Global Strategy (¶4)"))
    assert len(out) == 1 and FOUND_LOCATOR in out[0]["message"]


# ── what must NOT be refused ──


def test_every_baxter_label_passes():
    """The gold standard has to survive its own gate, or the gate is wrong."""
    assert label("focus_areas", _fa(*BCU)) == []


def test_a_parenthetical_that_is_part_of_the_name_passes():
    """Publications really are named this way. A gate that refused a
    parenthesised subtitle would push producers into mangling real titles."""
    assert label("focus_areas", _fa(
        "PYMNTS — BCU Data Culture & AI panel (2025-08)",
        "Federal Reserve — Supervision and Regulation Report (November 2025)",
        "T. Rowe Price — 2025 Annual Report (Form 10-K)",
    )) == []


def test_a_label_at_the_ceiling_passes_and_one_over_does_not():
    at = "P — " + "x" * (SOURCE_LABEL_MAX - 4)
    assert len(at) == SOURCE_LABEL_MAX
    assert label("focus_areas", _fa(at)) == []
    assert len(label("focus_areas", _fa(at + "x"))) == 1


def test_other_fields_are_not_touched():
    """`currency_note` is prose by design and runs long on both clients. This
    gate is about a citation label, not about how much a producer writes."""
    assert label("focus_areas", {"focus_areas": [
        {"source_document": BCU[0], "currency_note": "word " * 90,
         "verbatim_quote": "q" * 300}]}) == []


def test_non_dict_bodies_are_ignored():
    assert label("s", None) == [] and label("s", []) == []


def test_it_reads_source_document_wherever_it_sits():
    """Keyed off the field name, not off one section's shape — the same label
    field appears on cell evidence and on the evidence index."""
    out = label("cell_evidence", {"cells": [{"items": [
        {"source_document": TRP[0]}]}]})
    assert len(out) == 1
    assert out[0]["path"] == "cell_evidence.cells[0].items[0].source_document"


# ── registered and wired ──


def test_the_gate_is_registered_and_blocks():
    assert "CG-36" in GATES
    assert GATES["CG-36"][-1] == "block"


def test_the_check_is_wired_into_the_dispatch():
    """Every test above calls the check directly and would stay green with it
    unwired. Asserted over the AST, because the name appears in its own def
    and docstring and a substring search would pass on an unwired file."""
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation.py").read_text(encoding="utf-8")
    called = {getattr(n.func, "id", None) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call)}
    assert "_check_source_label_is_a_citation" in called
