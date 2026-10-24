"""CG-10 — UNVERIFIED is the rung for a date nobody could establish, not for
one sitting in the cited evidence.

RC-04 (SWBC gold audit, 2026-10-04; slices OH-07, XC-02). `_records_absence`
accepts `recency_band: "UNVERIFIED"` as a recorded date absence, and nothing
looked at what the item cites. SWBC's firmographics stated `founded: 1976`
with `as_of: null` and band UNVERIFIED while its own cited excerpt (E-CC-1283)
reads "April 1, 1976", and every other stated row did the same against
evidence carrying a published date. The rung recorded a search that was never
needed: the date was on the page the producer had already registered.

The rule: an item that leaves its dating field null on an UNVERIFIED/undated
rung is refused when any evidence row it cites carries a published_date, or
an excerpt holding a full calendar date. The message names the derivable date.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_undated_rung_against_evidence  # noqa: E402

FOUNDED = {"field": "founded", "value": "1976", "as_of": None,
           "recency_band": "UNVERIFIED", "source_e_id": "E-CC-1283",
           "quarantined": False, "quarantine_reason": None}
E1283 = {"e_id": "E-CC-1283", "published_date": None, "tier": "T2",
         "excerpt": "Founded on April 1, 1976, SWBC has grown from a small "
                    "insurance agency into a diversified financial services "
                    "company."}


def _run(items, found):
    payload = {"firmographics": {"fields": items}}
    return _check_undated_rung_against_evidence("overview", payload, found)


def test_swbc_founded_unverified_against_a_dated_excerpt_is_refused():
    out = _run([FOUNDED], [E1283])
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-10"
    assert r["path"] == "firmographics.fields[0].as_of"
    assert "April 1, 1976" in r["message"]


def test_a_cited_row_with_a_published_date_is_refused_too():
    row = dict(E1283, excerpt="SWBC is headquartered in San Antonio, Texas, "
                              "and serves clients in all fifty states.",
               published_date="2026-04-06")
    out = _run([dict(FOUNDED, field="hq", value="San Antonio")], [row])
    assert len(out) == 1 and "2026-04-06" in out[0]["message"]


def test_genuinely_undated_evidence_keeps_the_rung():
    row = dict(E1283, excerpt="SWBC is headquartered in San Antonio, Texas, "
                              "and serves clients across the country.")
    assert _run([FOUNDED], [row]) == []


def test_a_bare_year_is_not_a_full_date():
    row = dict(E1283, excerpt="Serving financial institutions since 1976, the "
                              "company now employs about 2,300 people.")
    assert _run([FOUNDED], [row]) == []


def test_a_stated_date_or_a_held_row_is_out_of_scope():
    dated = dict(FOUNDED, as_of="1976-04-01")
    held = dict(FOUNDED, value=None, quarantined=True,
                quarantine_reason="Three records disagree on the year.")
    assert _run([dated, held], [E1283]) == []


def test_the_check_is_wired_into_pass2():
    import inspect
    from dma_mcp import validation2
    src = inspect.getsource(validation2.validate_pass2)
    assert "_check_undated_rung_against_evidence(" in src
