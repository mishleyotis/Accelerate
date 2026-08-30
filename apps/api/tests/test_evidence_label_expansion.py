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


# ── an identifier is not an abbreviation ───────────────────────────────

def test_an_identifier_is_left_alone():
    """`VC-CU-01` is a catalogue value-chain id and the `CU` in it names the
    chain, not the phrase. Expanding it breaks the id; flagging it sends a
    producer to fix something already right. Sixteen of these were counted as
    abbreviations on a served page before the shape was excluded."""
    from abbreviations import expand, unexplained
    for ident in ("VC-CU-01", "P1C1.1.1", "E-CC-188", "TS-14"):
        assert list(unexplained(ident)) == [], f"{ident} read as an abbreviation"
        assert expand(ident, "label") == ident


def test_prose_around_an_identifier_is_still_expanded():
    from abbreviations import expand, unexplained
    text = "Stage VC-CU-01 of the CU chain"
    assert list(unexplained(text)) == ["CU"]
    assert expand(text, "label") == "Stage VC-CU-01 of the Credit Union chain"


# ── the second projection, which is how the abbreviation survived ──────

def test_the_cell_item_projection_spells_its_label_out():
    """The evidence endpoint spells a package label out in `_row_to_item`;
    `computed.py` builds the SAME field for the cell drawer straight off the
    column and was not changed with it. 26 cell items served "President & CEO"
    on a page whose evidence tab served the same source spelled out."""
    src = (ROOT / "apps" / "api" / "dma_api" / "computed.py").read_text()
    assert '"source_title": _expand_abbrev(' in src, \
        "the cell-item projection reads source_name straight off the column " \
        "again, so a package label reaches the drawer unexpanded"


def test_the_cell_item_carries_its_source_url():
    """An item that names a source and cannot link to it makes the reader take
    the title on trust."""
    src = (ROOT / "apps" / "api" / "dma_api" / "computed.py").read_text()
    assert "ei.source_url" in src and '"source_url": r[8]' in src


def test_the_tracked_copy_wins_over_a_staged_one():
    """A build artefact shadowing its own source is how verification runs
    against the wrong copy, and it does not announce itself: the file is
    there, it parses, and it is merely old.

    `apps/api/shared/` is gitignored and written by deploy.sh. The first
    version of the loader skipped any candidate already on `sys.path` and
    inserted the other at position 0, so the staged copy won whenever a caller
    had put the repo path on first — and a stale copy from an earlier deploy
    answered a rule the tracked file had and it did not."""
    import abbreviations
    assert "packages/shared" in abbreviations.__file__, (
        f"the abbreviation list resolved from {abbreviations.__file__} — a "
        "staged build artefact is shadowing the tracked source")


def test_a_controlled_vocabulary_token_is_left_to_its_label_route():
    """`sub_vertical` carries `CU` and the frontend resolves it through
    SUBVERTICAL_LABEL to "Credit Union". The string a reader sees is already
    spelled out; rewriting the token would break the lookup. It was the last
    thing a scan of the six served pages flagged, seven times, and every one
    of them was this."""
    from abbreviations import EXCERPT_FIELDS, expand, unexplained
    assert "sub_vertical" in EXCERPT_FIELDS
    # and the value itself is still a bare token, so the exclusion is by FIELD
    # and not by shape — a bare `CU` in prose must still be caught.
    assert list(unexplained("CU members expect it")) == ["CU"]
    assert expand("CU members expect it", "label") == "Credit Union members expect it"


def test_an_alignment_quote_is_a_verbatim_span_and_never_rewritten():
    """CG-27 flagged 'CFPB' inside an alignment_quote on the first
    engine-scored resubmission. The quote is the client's own words — the
    same standing as an excerpt — so the FIELD is exempt and the check
    walks past it, rather than the quote being edited to please a gate."""
    from abbreviations import EXCERPT_FIELDS, unexplained
    assert "alignment_quote" in EXCERPT_FIELDS
    # the quote DOES carry an unexplained short form — which is exactly why
    # the exemption has to be on the field, not on the text
    assert list(unexplained(
        "crossing the arbitrary $10 billion threshold that subjects us to "
        "greater CFPB scrutiny")) == ["CFPB"]


def test_a_catalogue_path_is_controlled_vocabulary_and_never_rewritten():
    """The path L3 -> L4 -> sub-capability must stay renderable and
    resolvable (contract, gap rows). Its segments l3_area and l4_feature
    are individually exempt; the joined path is the same vocabulary."""
    from abbreviations import EXCERPT_FIELDS
    assert "catalogue_path" in EXCERPT_FIELDS
