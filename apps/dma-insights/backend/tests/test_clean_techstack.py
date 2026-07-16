"""Unit tests for clean_techstack evidence-array hygiene.

2026-07-06: clean_techstack crashed with `malformed array literal` because
it bare-joined dirty evidence_index.e_id cells (multi-value "E-023, E-036",
factor-annotated "E-024:F5", truncated "E-") into a `{a,b}` PG array literal.
The sanitizer extracts canonical E-ID tokens and double-quotes each element.
"""
from app.scripts.clean_techstack import _clean_eids, _pg_text_array


def test_clean_eids_splits_multivalue_and_drops_junk():
    raw = ["E-023, E-036", "E-", "E-024", "E-024:F5", "", "E-027", "E-035:F5"]
    # multi-value cell split; :F5 factor suffix dropped; "E-"/"" discarded;
    # de-duplicated preserving first-seen order.
    assert _clean_eids(raw) == ["E-023", "E-036", "E-024", "E-027", "E-035"]


def test_clean_eids_handles_entity_named_ids():
    assert _clean_eids(["E-AlmaBank-001", "E-AlmaBank-001"]) == ["E-AlmaBank-001"]


def test_pg_text_array_quotes_every_element():
    assert _pg_text_array(["E-023", "E-036"]) == '{"E-023","E-036"}'


def test_pg_text_array_empty_is_noop_sentinel():
    # "" is the UPDATE's CASE-WHEN sentinel that preserves existing values.
    assert _pg_text_array([]) == ""
    assert _pg_text_array(["  ", ""]) == ""


def test_pg_text_array_survives_comma_colon_space_in_value():
    # even if a value slipped through with a separator, quoting keeps the
    # literal valid (the whole point of the fix).
    lit = _pg_text_array(["P4C1.8.2", "weird, value"])
    assert lit == '{"P4C1.8.2","weird, value"}'
