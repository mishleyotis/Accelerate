"""The abbreviation in the label, spelled out where there is nowhere else.

Four rounds of sweeps cleared abbreviations from promoted prose and a reader
still opened a drawer onto "Logix FCU call report aggregation". That string is
`source_name` on a package-ingested evidence row: it never travels through a
payload, so no payload gate ever sees it, and by charter the ingested tier is
read-only once scanned. 31 of this corpus's 104 rows carry one.

So it is expanded in the projection — the last place the ingested tier can
still be reached before a client reads it. The excerpt is not touched here or
anywhere: that IS a verbatim span, and the verifier compares it against the
bytes it came from.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_api.evidence import _COLUMNS, _row_to_item  # noqa: E402


def row(**over):
    base = dict.fromkeys(_COLUMNS)
    base.update({"e_id": "E-1", "origin": "package", "tier": "T2",
                 "claim_type": "FACT", "identity_ok": True})
    base.update(over)
    return tuple(base[c] for c in _COLUMNS)


def test_a_package_label_is_spelled_out():
    item = _row_to_item(row(
        source_name="NCUSO.org — Logix FCU call report aggregation (charter 1999)"))
    assert item["source_name"] == (
        "NCUSO.org — Logix Federal Credit Union call report aggregation "
        "(charter 1999)")


def test_a_role_in_a_label_takes_title_case():
    """"President & chief executive" reads as a sentence fragment dropped into
    a title. In prose the lower-case form is right; the two styles are held
    apart rather than one being bent to serve both."""
    item = _row_to_item(row(
        source_name="US House Financial Services — Testimony of Ana Fonseca, "
                    "President & CEO, Logix FCU"))
    assert item["source_name"].endswith(
        "President & Chief Executive, Logix Federal Credit Union")


def test_the_excerpt_is_never_rewritten():
    """The verifier compares an excerpt against the bytes it was taken from.
    A tidy-up here would break that and misquote the source in the same move."""
    span = ("For an institution like Logix, crossing the arbitrary $10 billion "
            "threshold that subjects us to greater CFPB scrutiny has a cost.")
    item = _row_to_item(row(source_name="A source", excerpt=span))
    assert item["excerpt"] == span


def test_a_row_with_no_label_survives_the_projection():
    item = _row_to_item(row(source_name=None))
    assert item["source_name"] is None


def test_a_label_already_spelled_out_is_left_alone():
    name = "National Credit Union Administration — Call Report Quarterly Data"
    assert _row_to_item(row(source_name=name))["source_name"] == name
