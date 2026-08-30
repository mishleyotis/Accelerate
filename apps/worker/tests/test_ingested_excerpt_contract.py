"""G1 — what the ingest tier may store in `evidence_index.excerpt`.

The defect this pins, measured on Logix run d7ed1d90 (2026-08-18): **36 of 62
evidence rows carried a zero-length excerpt**, so they could link to a cell
and could never be cited. The run's own evidence index carried 16 rows where
the package had supplied 36, because a producer had to re-register every
source by hand from the fetched artefacts. It promoted cleanly — every gate
passed — and read on screen as a thin assessment of a thin institution.

Two writers share this column and only one knew the rules.
`register_evidence` refuses a span outside 50-500, refuses a claim with no
traceable URL, and verifies the span against the artefact it fetches. The
worker's workbook-parse path wrote whatever the cell held, including the
empty string, and nothing downstream refused it until a producer cited it.

Why the empty string specifically is worse than NULL, which is the part that
took a day to see:

  · `repair_evidence_namespace` selects on `excerpt IS NULL` — '' is invisible
  · `embed` filters on `excerpt IS NOT NULL` — '' is silently un-embedded
  · `CONTENT_HASH_EXPR` concatenates the excerpt with no COALESCE, so a NULL
    excerpt gives a NULL content_hash and `evidence_dedup_uq` never fires

so a row holding '' is outside the repair, outside the embedding corpus and
outside the dedup index, while reading as populated to every check written
against None. One state, not two.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.evidence_ids import (EXCERPT_MAX, EXCERPT_MIN, citable_span,
                                     stored_url)

GOOD = ("Logix Federal Credit Union has utilized CaseHUB as the central hub "
        "for its fraud investigations for more than a decade.")


def test_the_floor_is_the_contract_floor():
    """Not a number chosen here. It is the column comment, what
    register_evidence refuses outside, and what ET-04 blocks a citation for."""
    assert (EXCERPT_MIN, EXCERPT_MAX) == (50, 500)


def test_a_real_span_is_stored_unchanged():
    span, why = citable_span(GOOD)
    assert span == GOOD and why is None


@pytest.mark.parametrize("value", [None, "", "   ", "\n\t ", " "])
def test_no_excerpt_is_None_and_never_the_empty_string(value):
    """The regression. A whitespace-only workbook cell used to survive as ''
    because `"   "` is truthy and `"   ".strip()` is `""`."""
    span, why = citable_span(value)
    assert span is None, f"{value!r} must not be stored"
    assert why, "an absence must carry its reason"


def test_a_short_fragment_is_dropped_rather_than_stored():
    """The rationale miner accepted 20 characters. A 20-49 character fragment
    landed, linked to cells, and then refused the first producer who cited
    it — a defect manufactured at ingest and surfaced two stages later,
    wearing the appearance of evidence the whole way."""
    span, why = citable_span("Uses Symitar Episys.")
    assert span is None
    assert "20-character fragment" in why and "ET-04" in why


def test_a_span_at_the_floor_is_kept():
    exactly = "x" * EXCERPT_MIN
    span, why = citable_span(exactly)
    assert span == exactly and why is None
    span, why = citable_span("x" * (EXCERPT_MIN - 1))
    assert span is None and why


def test_an_over_long_span_is_truncated_not_refused():
    span, why = citable_span("y" * 900)
    assert why is None and len(span) == EXCERPT_MAX


def test_surrounding_whitespace_is_not_what_makes_a_span_short():
    padded = f"   {GOOD}   "
    span, why = citable_span(padded)
    assert span == GOOD and why is None


@pytest.mark.parametrize("value,expect", [
    (None, None), ("", None), ("   ", None),
    ("https://ncua.gov/x", "https://ncua.gov/x"),
    ("  https://ncua.gov/x  ", "https://ncua.gov/x"),
])
def test_a_source_url_is_a_url_or_it_is_None(value, expect):
    assert stored_url(value) == expect


def test_the_lander_records_every_uncitable_row_and_stores_NULL():
    """The count has to leave the ingest, or "this package landed evidence
    nobody can cite" stays something a producer discovers by writing prose
    about it. Logix's 36 were named in a payload, not in a scan.

    Run against the real column, because the claim is about what is IN it:
    a fake cursor that accepts the INSERT proves nothing about whether the
    empty string survived.
    """
    import os

    import pg8000.dbapi

    from dma_worker.evidence_ids import EvidenceLander

    dsn = os.environ.get("LOCAL_DATABASE_URL",
                         "postgresql://postgres:local@localhost:5432/dma_insights")
    host = dsn.split("@")[1].split(":")[0] if "@" in dsn else "localhost"
    try:
        conn = pg8000.dbapi.connect(
            user="dmai-migrate@digital-maturity-assessor.iam", password="local",
            host=host, port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")

    cur = conn.cursor()
    seen = []
    try:
        cur.execute("INSERT INTO entities (display_id, legal_name) "
                    "VALUES ('g1-excerpt-probe', 'G1 Excerpt Probe') "
                    "RETURNING id")
        entity_id = cur.fetchone()[0]

        lander = EvidenceLander(
            cur, entity_id=entity_id, run_id=None, run_seq=1, token="G1PROBE",
            reference_date=None,
            observe=lambda kind, payload: seen.append((kind, dict(payload))))

        stored = lander.land({"e_id": "E-001", "excerpt": "   ",
                              "source_url": "https://example.org/a",
                              "source_name": "Example"})

        kinds = [k for k, _ in seen]
        assert "evidence_excerpt_uncitable" in kinds, (
            "a row that landed uncitable left no trace of having done so")
        payload = seen[kinds.index("evidence_excerpt_uncitable")][1]
        assert payload["package_local_id"] == "E-001"
        assert payload["source_url"] == "https://example.org/a", (
            "the observation must name the source, or it cannot be acted on")

        assert stored, "the row should still land — it links, it just cannot be cited"
        cur.execute("SELECT excerpt, content_hash FROM evidence_index "
                    "WHERE e_id = %s", (stored,))
        excerpt, _hash = cur.fetchone()
        assert excerpt is None, (
            f"the column holds {excerpt!r}. '' is invisible to "
            "repair_evidence_namespace (IS NULL), to embed (IS NOT NULL) and "
            "to the dedup index, while reading as populated to every check "
            "written against None.")
    finally:
        conn.rollback()
        conn.close()


# ── which column an excerpt may come FROM (2026-08-22) ──


def test_a_quotation_column_outranks_every_summary_spelling():
    """`_EV_ALIASES["excerpt"]` used to open with `fact_summary`, so a
    register carrying BOTH a real quotation column and a summary served the
    summary — an assessor's sentence ABOUT the source, stored as the source's
    own words behind a citation.

    The measurement that settles it, taken on the production intake tree:
    one package holds 899 facts carrying both a paraphrase and an
    `anchor_quote`, and ZERO of the pairs are identical. They are different
    kinds of text, not two spellings of one.

    The summaries stay in the tuple, last, because some generations ship no
    quotation column at all and an evidence drawer cannot render empty —
    but they are the fallback, never the preference.
    """
    from dma_worker.workbook_parser import _EV_ALIASES

    order = list(_EV_ALIASES["excerpt"])
    quotations = {"excerpt", "anchor_quote", "verbatim", "quote", "passage"}
    summaries = {"fact_summary", "summary"}

    assert quotations <= set(order), "a quotation spelling went missing"
    assert summaries <= set(order), "the fallback must still exist"

    last_quotation = max(order.index(q) for q in quotations if q in order)
    first_summary = min(order.index(s) for s in summaries if s in order)
    assert last_quotation < first_summary, (
        f"a summary column outranks a quotation column: {order}")
