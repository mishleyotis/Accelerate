"""Unit tests for `qa_language_audit --nlp-coverage` (the Part 3.5 static
gate) and the `--pattern-gaps` warning walker — synthetic module sources only,
no DB, no repo-wide scan.
"""
from __future__ import annotations

import textwrap

from app.scripts.qa_language_audit import (
    _REPORT_ONLY_EXEMPT,
    NLP_COVERAGE_GRANDFATHER,
    _iter_pattern_gaps,
    scan_module_source,
)


def _scan(src: str) -> dict:
    return scan_module_source(textwrap.dedent(src))


# ── prose-emission detection ─────────────────────────────────────────────────

def test_field_assign_fstring_without_import_violates():
    got = _scan("""
        def build(row):
            card = {}
            card["so_what_text"] = f"Make {row['name']} a near-term focus"
            return card
    """)
    assert not got["imports_nlp"]
    assert [s.kind for s in got["sites"]] == ["field_assign"]
    assert got["sites"][0].detail == "so_what_text"


def test_import_forms_are_recognized():
    for imp in ("import app.services.nlp",
                "from app.services.nlp import titlecraft",
                "from app.services import nlp",
                "from app.services.nlp.quality import markdown_lint"):
        got = _scan(f"""
            {imp}
            title = f"generated headline for the client overview page"
        """)
        assert got["imports_nlp"], imp
    got = _scan("from app.services import startup_enrich\nx = 1\n")
    assert not got["imports_nlp"]


def test_dict_key_and_kwarg_prose_detected():
    got = _scan("""
        def emit(name):
            return {"title": f"{name} launches digital core"}
    """)
    assert any(s.detail == "title" for s in got["sites"])
    got = _scan("""
        def emit(model, name):
            model.update(body=f"{name} shows meaningful modernization signals")
    """)
    assert any(s.detail == "body" for s in got["sites"])


def test_long_fstring_counts_short_does_not():
    long_src = """
        def emit(a, b, c):
            x = f"{a} is the highest-fit platform surface for this institution at {b}/100, concentrated in {c}"
            return x
    """
    assert any(s.kind == "long_fstring" for s in _scan(long_src)["sites"])
    assert not _scan('def f(a):\n    return f"{a}: ok"\n')["sites"]


def test_print_log_and_raise_are_suppressed():
    got = _scan("""
        import logging
        log = logging.getLogger(__name__)
        def run(n, took, errors, skipped):
            print(f"backfill finished: {n} packages in {took}s with {errors} errors, {skipped} skipped")
            log.warning(f"quarantined {errors} of {n} packages during the historical backfill run")
            raise ValueError(f"run {n} failed catastrophically with {errors} unrecoverable parse errors")
    """)
    assert got["sites"] == []


def test_plain_string_constants_short_or_spaceless_do_not_count():
    got = _scan("""
        KIND = "engineering_signal"
        def tag(row):
            row["label"] = KIND
            row["label"] = "noise"
            return row
    """)
    assert got["sites"] == []


def test_prose_string_literal_into_field_counts():
    got = _scan("""
        def stub(card):
            card["why_text"] = "This capability trails the peer benchmark set."
            return card
    """)
    assert [s.detail for s in got["sites"]] == ["why_text"]


def test_grandfather_lists_are_disjoint_and_relative():
    assert not (NLP_COVERAGE_GRANDFATHER & _REPORT_ONLY_EXEMPT)
    for rel in NLP_COVERAGE_GRANDFATHER | _REPORT_ONLY_EXEMPT:
        # _SCAN_ROOTS covers app/scripts + ALL of app/services (widened
        # 2026-07-03 so prose emitted by services is gated too) — the
        # grandfather entries follow the same roots.
        assert rel.startswith(("app/scripts/", "app/services/")), rel
        assert rel.endswith(".py")


# ── pattern-gap walker ───────────────────────────────────────────────────────

def test_iter_pattern_gaps_structured_envelope_and_legacy():
    warnings = [
        {"code": "PATTERN_GAP", "path": "07_data/new_shape.csv",
         "reason": "no fingerprint matched (best 0.31)"},
        # ingestion re-architecture envelope form ({code, severity, detail})
        {"code": "pattern_gap", "severity": "INFO",
         "detail": "05_misc/unknown.xlsx — sheet names unregistered"},
        "INFO/pattern_gap: 04_reports/odd.docx — heading set unknown",
        {"code": "OTHER", "path": "x"},
        "plain string warning",
        42,
    ]
    got = list(_iter_pattern_gaps(warnings))
    assert got[0] == ("07_data/new_shape.csv", "no fingerprint matched (best 0.31)")
    assert got[1] == ("05_misc/unknown.xlsx", "sheet names unregistered")
    assert got[2] == ("04_reports/odd.docx", "heading set unknown")
    assert len(got) == 3
    assert list(_iter_pattern_gaps(None)) == []
    assert list(_iter_pattern_gaps("not-a-list")) == []
