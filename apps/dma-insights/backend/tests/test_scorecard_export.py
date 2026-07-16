"""B-6 — prospecting scorecard export tests.

The HTML render is pure (jinja2) so it tests without a DB or browser.
Customer-safety is asserted structurally: only scores / pillars / platform
fit appear — never ERS, alert counts, or evidence.
"""
from __future__ import annotations

import pytest

from app.services.scorecard_export import (
    PillarScore,
    PlatformFit,
    ScorecardData,
    maturity_hex,
    maturity_label,
    render_scorecard_html,
)


def _data(**kw) -> ScorecardData:
    base = ScorecardData(
        entity_name="Provident Bank",
        subvertical="REG_BANK",
        display_id="prov-001",
        overall=3.2,
        assessment_date="2026-05-01",
        pillars=[
            PillarScore("P1", "Strategy & Governance", 3.4),
            PillarScore("P2", "Customer Experience", 2.9),
            PillarScore("P3", "Operations & Workflow", 3.1),
            PillarScore("P4", "Data & Technology", 2.1),
        ],
        top_platforms=[
            PlatformFit("Salesforce", 78.0),
            PlatformFit("Databricks", 64.0),
            PlatformFit("Tableau", 41.0),
        ],
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def test_maturity_band_thresholds_match_adr_0008() -> None:
    assert maturity_label(4.6) == "Differentiating"
    assert maturity_label(3.6) == "Competing"
    assert maturity_label(2.6) == "Building"
    assert maturity_label(1.0) == "Activating"
    assert maturity_label(None) == "Not assessed"
    assert maturity_hex(None) == "#E5E7EB"
    assert maturity_hex(5.0) == "#139F94"


def test_html_contains_entity_scores_and_platforms() -> None:
    html = render_scorecard_html(_data())
    assert "Provident Bank" in html
    assert "3.2" in html               # overall
    assert "Strategy &amp; Governance" in html or "Strategy & Governance" in html
    assert "2.1" in html               # P4 score
    assert "Salesforce" in html
    assert "78" in html                # fit score rounded
    assert "share-safe" in html        # customer-safe marker


def test_html_is_customer_safe_no_internal_signals() -> None:
    html = render_scorecard_html(_data()).lower()
    for forbidden in ("ers", "evidence", "alert", "thin", "e-0"):
        assert forbidden not in html, f"customer scorecard leaked '{forbidden}'"


def test_html_handles_missing_scores_gracefully() -> None:
    html = render_scorecard_html(_data(
        overall=None,
        pillars=[PillarScore("P1", "Strategy & Governance", None)],
        top_platforms=[],
    ))
    assert "—" in html                 # null overall renders as dash
    assert "Not assessed" in html
    # no platforms section header when there are none
    assert "Top platform opportunities" not in html


def test_pdf_export_matches_weasyprint_availability() -> None:
    """PDF export tracks weasyprint availability — and NEVER skips (the
    live-PG stage forbids skips). When weasyprint is absent the render raises
    RuntimeError so the router returns a 501 rather than fabricating a file;
    when it is installed (the production backend image, 2026-07-07) it returns
    a real PDF. Either branch asserts."""
    import importlib.util

    from app.services.scorecard_export import render_scorecard_pdf

    if importlib.util.find_spec("weasyprint") is None:
        with pytest.raises(RuntimeError, match="weasyprint"):
            render_scorecard_pdf(_data())
    else:
        pdf = render_scorecard_pdf(_data())
        assert isinstance(pdf, bytes | bytearray) and pdf[:5] == b"%PDF-"
        assert len(pdf) > 500  # a real, non-empty document
