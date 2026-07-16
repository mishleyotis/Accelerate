"""Tests for the parser_observations_promoter script.

The promoter is the "humans approve, machines suggest" half of the
self-improvement loop. Pure-logic tests (no live PG) — the SELECT
side is exercised by the live-PG integration suite via
`test_admin_endpoints_live_pg.py` (added separately).

Coverage matrix:

  render_markdown_empty_says_clean
    Empty queue → user-friendly "queue clean" message rather than an
    empty file. Operator should never wonder "did the job fail?"

  render_markdown_groups_by_canonical_guess
    Suggested-patch block must group variants under their predicted
    canonical field so the operator can copy a clean alias entry.

  render_markdown_variants_without_guess_get_review_comment
    When no canonical_guess is available, the suggested patch comments
    out the line — we DON'T want the operator pasting a guess we
    don't actually have.

  render_json_round_trip
    Machine-readable output is valid JSON with the documented shape.

  render_markdown_sorts_buckets_by_total_observations
    Highest-signal buckets appear first; operator's attention goes to
    the most impactful candidates.
"""
from __future__ import annotations

import json

from app.scripts.parser_observations_promoter import (
    Candidate,
    PromotionReport,
    render_json,
    render_markdown,
)


def _rep(parser: str, kind: str, *candidates: Candidate) -> PromotionReport:
    return PromotionReport(
        parser_name=parser,
        observation_kind=kind,
        candidates=list(candidates),
    )


def test_render_markdown_empty_says_clean() -> None:
    out = render_markdown([])
    assert "Queue is clean" in out
    assert "No observations" in out


def test_render_markdown_groups_by_canonical_guess() -> None:
    rep = _rep(
        "research_workbook", "unknown_column",
        Candidate(
            value="subcapability",
            canonical_guess="subcap_id",
            occurrence_count=42, distinct_runs=7,
        ),
        Candidate(
            value="proof_claims",
            canonical_guess="excerpt",
            occurrence_count=28, distinct_runs=5,
        ),
        Candidate(
            value="sub_cap_label",
            canonical_guess="subcap_id",
            occurrence_count=8, distinct_runs=2,
        ),
    )
    out = render_markdown([rep])
    # subcap_id group should contain both subcapability + sub_cap_label.
    assert '"subcap_id": [..., "subcapability",]' in out
    assert '"subcap_id": [..., "sub_cap_label",]' in out
    assert '"excerpt": [..., "proof_claims",]' in out


def test_render_markdown_variants_without_guess_get_review_comment() -> None:
    rep = _rep(
        "research_workbook", "unknown_column",
        Candidate(
            value="weird_column",
            canonical_guess=None,
            occurrence_count=5, distinct_runs=2,
        ),
    )
    out = render_markdown([rep])
    # No naked alias suggestion — must be a comment.
    assert '"unknown_column": [..., "weird_column"' not in out
    assert "review manually" in out


def test_render_json_round_trip() -> None:
    rep = _rep(
        "package_csvs.parse_issue_register_csv", "unknown_column",
        Candidate(
            value="diagnostic_question",
            canonical_guess=None,
            occurrence_count=33, distinct_runs=4,
            sample_context={"csv": "issue_register.csv"},
        ),
    )
    out = render_json([rep])
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["parser_name"] == "package_csvs.parse_issue_register_csv"
    assert payload[0]["candidates"][0]["value"] == "diagnostic_question"
    assert payload[0]["candidates"][0]["occurrence_count"] == 33


def test_render_markdown_sorts_buckets_by_total_observations() -> None:
    low = _rep(
        "low_signal", "unknown_column",
        Candidate(
            value="x", canonical_guess=None,
            occurrence_count=3, distinct_runs=1,
        ),
    )
    high = _rep(
        "high_signal", "unknown_column",
        Candidate(
            value="y", canonical_guess="subcap_id",
            occurrence_count=99, distinct_runs=10,
        ),
    )
    out = render_markdown([low, high])
    # The high-signal bucket header must appear before the low.
    assert out.index("high_signal") < out.index("low_signal")
