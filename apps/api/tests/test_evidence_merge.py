"""One artefact, several rows: what merges and what must not.

Measured on run d7ed1d90 (104 evidence rows): 20 urls carry more than one row,
36 rows carry no excerpt, and 10 of those 36 sit on a url another row already
quotes. The worked example is P1C1.1.1 — the package linked a congressional
testimony to the cell through a row with no span, while two producer rows
carried spans of that same testimony and were linked elsewhere. The reader
opened the cell and saw a citation with no quote.

These cases pin the asymmetry that makes the merge safe: a SPAN is a citation
and several spans of one document are several citations; a reference with no
span is not, and is absorbed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from evidence_merge import merge_same_source, source_key  # noqa: E402

URL = "https://docs.house.gov/meetings/BA/BA20/x.pdf"


def row(e_id, excerpt=None, url=URL, tier="T2", links=()):
    return {"e_id": e_id, "excerpt": excerpt, "source_url": url,
            "tier": tier, "linked_subcap_ids": list(links)}


def test_a_reference_with_no_span_is_absorbed_into_the_row_that_quotes_it():
    items, rep = merge_same_source([
        row("E-CC-188", "a verbatim span", links=["P1C2.1.1"]),
        row("E-PKG-003", None, links=["P1C1.1.1"]),
    ])
    assert [i["e_id"] for i in items] == ["E-CC-188"]
    assert rep["absorbed"] == 1 and rep["excerpts_recovered"] == 1


def test_the_absorbed_row_hands_over_its_cell_links():
    """THE WHOLE POINT. The package row held the link to P1C1.1.1 and the
    producer row held the quote; after the merge the cell reaches the quote."""
    items, _ = merge_same_source([
        row("E-CC-188", "a verbatim span", links=["P1C2.1.1"]),
        row("E-PKG-003", None, links=["P1C1.1.1"]),
    ])
    assert items[0]["linked_subcap_ids"] == ["P1C1.1.1", "P1C2.1.1"]


def test_the_absorbed_id_is_named_and_never_just_dropped():
    items, _ = merge_same_source([
        row("E-CC-188", "a verbatim span"), row("E-PKG-003", None)])
    assert items[0]["also_filed_as"] == ["E-PKG-003"]


def test_two_spans_of_one_document_are_two_citations():
    """E-CC-188 and E-CC-199 quote different paragraphs of one testimony.
    Collapsing them would delete a citation the producer made."""
    items, rep = merge_same_source([
        row("E-CC-188", "the first paragraph"),
        row("E-CC-199", "a different paragraph"),
    ])
    assert [i["e_id"] for i in items] == ["E-CC-188", "E-CC-199"]
    assert rep["absorbed"] == 0


def test_both_spans_receive_the_links_of_the_reference_they_absorb():
    items, _ = merge_same_source([
        row("E-CC-188", "the first paragraph"),
        row("E-CC-199", "a different paragraph"),
        row("E-PKG-003", None, links=["P1C1.1.1"]),
    ])
    assert all("P1C1.1.1" in i["linked_subcap_ids"] for i in items)
    assert all(i["also_filed_as"] == ["E-PKG-003"] for i in items)


def test_where_nothing_quotes_the_url_one_reference_survives():
    """Two unquotable rows on one url are the same unreachable reference listed
    twice. The stronger tier survives, then the lower id — stable across
    processes, because an order that depends on a dict is not a rule."""
    items, rep = merge_same_source([
        row("E-B", None, tier="T5", links=["P2C1.1.1"]),
        row("E-A", None, tier="T2", links=["P1C1.1.1"]),
    ])
    assert [i["e_id"] for i in items] == ["E-A"]
    assert items[0]["linked_subcap_ids"] == ["P1C1.1.1", "P2C1.1.1"]
    assert rep["excerpts_recovered"] == 0


def test_a_row_with_no_url_is_never_merged_with_anything():
    items, rep = merge_same_source([
        row("E-1", None, url=None), row("E-2", None, url=""),
        row("E-3", "span", url=None)])
    assert [i["e_id"] for i in items] == ["E-1", "E-2", "E-3"]
    assert rep["absorbed"] == 0


def test_the_listing_keeps_its_original_order():
    items, _ = merge_same_source([
        row("E-1", "s", url="https://a.example"),
        row("E-2", None, url="https://b.example"),
        row("E-3", "s", url="https://c.example"),
    ])
    assert [i["e_id"] for i in items] == ["E-1", "E-2", "E-3"]


def test_http_and_https_are_one_document():
    items, _ = merge_same_source([
        row("E-1", "span", url="https://x.example/doc"),
        row("E-2", None, url="http://x.example/doc/"),
    ])
    assert [i["e_id"] for i in items] == ["E-1"]


def test_an_archive_wrapper_is_a_different_retrieval():
    """A page fetched from the live host and the same page recovered from an
    archive are different retrievals with different dates, and this corpus
    holds three archive rows for a host that 403s the verifier."""
    a = source_key("https://www.logixbanking.com/x")
    b = source_key("http://web.archive.org/web/20260311012900/https://www.logixbanking.com/x")
    assert a != b


def test_a_query_string_distinguishes_two_responses():
    """itunes.apple.com/lookup?id=… returns a different artefact per id."""
    assert source_key("https://h.example/lookup?id=1") != \
           source_key("https://h.example/lookup?id=2")
