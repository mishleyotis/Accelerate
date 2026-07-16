"""Self-improvement observation log — parser-side gather + helper UPSERT.

The end-to-end loop is:

  workbook parsed → unknown column observed → flushed to
  parser_observations table → admin endpoint surfaces → operator
  promotes recurring variant into source ALIASES dict → next deploy.

Coverage matrix (the contract pieces this layer pins):

  per_pillar_emits_unknown_column_when_header_outside_aliases
    The most important signal: a workbook header that isn't in
    PERPILLAR_HEADER_ALIASES MUST appear in
    PerPillarParseResult.observations. Without this, the learning
    loop has no input.

  per_pillar_skips_known_aliases
    A header that IS in the alias dict must NOT generate an
    observation. Otherwise the table fills with noise on every
    well-formed workbook.

  observation_includes_canonical_guess_when_obvious
    Best-effort canonical guess (keyword heuristic) helps operators
    review. Verify "Sub_Capability_ID" → guess="subcap_id".

  per_pillar_observations_capped_per_sheet
    Sample-context per observation includes the SHEET name so the
    operator knows where it was seen.

  record_parser_observation_upsert_swallows_table_missing
    The helper MUST NOT raise when the migration is missing. Best-
    effort: heal-eventually, never break ingest.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.parser_observations import record_parser_observation
from app.services.parsers.research_workbook import parse_per_pillar_sheets


class _FakeCell:
    def __init__(self, v: Any) -> None:
        self.value = v


class _FakeSheet:
    def __init__(self, title: str, rows: list[list[Any]]) -> None:
        self.title = title
        self._rows = rows
        self.max_row = len(rows)
        self.max_col = max((len(r) for r in rows), default=0)

    def iter_rows(self, *, values_only: bool = True):
        for r in self._rows:
            yield tuple(r)


class _FakeWorkbook:
    def __init__(self, sheets: list[_FakeSheet]) -> None:
        self.worksheets = sheets

    def __getitem__(self, title: str) -> _FakeSheet:
        return next(s for s in self.worksheets if s.title == title)


def _per_pillar_sheet_with_extra_column(extra_name: str) -> _FakeSheet:
    """Build a per-pillar sheet whose header row matches the standard
    AlmaBank/WSFS shape PLUS one extra column the ALIASES dict
    doesn't know about."""
    header = [
        "SubCap_ID",
        "Evidence_IDs",
        "Source_URLs",
        "Tier",
        "Key_Evidence_Excerpt",
        extra_name,
    ]
    # One body row — irrelevant content, just enough to not get
    # short-circuited by the all-None empty-row check.
    body = [
        "P1C1.1.1",
        "E-001",
        "https://example.org/a",
        3,
        "excerpt",
        "X",
    ]
    return _FakeSheet("P1C1", [header, body])


def test_per_pillar_emits_unknown_column_when_header_outside_aliases() -> None:
    """A workbook with a novel column 'Sub_Capability_ID' must surface
    in observations so the operator can extend the ALIASES dict."""
    wb = _FakeWorkbook([
        _per_pillar_sheet_with_extra_column("Sub_Capability_ID"),
    ])
    result = parse_per_pillar_sheets(wb)
    kinds = [o["kind"] for o in result.observations]
    values = [o["value"] for o in result.observations]
    assert "unknown_column" in kinds
    assert "Sub_Capability_ID" in values


def test_per_pillar_skips_known_aliases() -> None:
    """All canonical-shape headers are in ALIASES dict; the parser must
    NOT emit observations for the standard six (otherwise the table
    fills with noise on every well-formed workbook)."""
    header = [
        "SubCap_ID", "Evidence_IDs", "Source_URLs",
        "Tier", "Key_Evidence_Excerpt",
    ]
    body = ["P1C1.1.1", "E-001", "https://x.org/a", 3, "exc"]
    wb = _FakeWorkbook([_FakeSheet("P1C1", [header, body])])
    result = parse_per_pillar_sheets(wb)
    # The 5 standard headers must NOT generate observations.
    standard = {h.lower() for h in header}
    for obs in result.observations:
        assert obs["value"].lower() not in standard, (
            f"standard header {obs['value']!r} leaked into observations"
        )


def test_observation_includes_canonical_guess_when_obvious() -> None:
    """The heuristic guess helps the operator see what to map the
    variant to. 'Sub_Capability_ID' should guess 'subcap_id'."""
    wb = _FakeWorkbook([
        _per_pillar_sheet_with_extra_column("Sub_Capability_ID"),
    ])
    result = parse_per_pillar_sheets(wb)
    matching = [
        o for o in result.observations
        if o["value"] == "Sub_Capability_ID"
    ]
    assert matching, "Sub_Capability_ID should have surfaced"
    assert matching[0]["canonical_guess"] == "subcap_id"


def test_observation_includes_sheet_context() -> None:
    """Each observation MUST tag the sheet it was seen on so the
    operator can verify the variant isn't a spurious one-off (e.g. on
    the 'Summary' sheet that nobody cares about)."""
    wb = _FakeWorkbook([
        _per_pillar_sheet_with_extra_column("WeirdCol_X"),
    ])
    result = parse_per_pillar_sheets(wb)
    matching = [o for o in result.observations if o["value"] == "WeirdCol_X"]
    assert matching
    ctx = matching[0]["sample_context"]
    assert ctx["sheet"] == "P1C1"
    assert ctx["parser"] == "research_workbook.parse_per_pillar_sheets"


def test_record_parser_observation_swallows_table_missing() -> None:
    """Helper must NOT raise when the migration is missing. The
    contract is: best-effort UPSERT, never break ingest."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError(
        'relation "parser_observations" does not exist'
    )
    # No raise.
    asyncio.run(record_parser_observation(
        session,
        parser_name="research_workbook",
        observation_kind="unknown_column",
        observed_value="X",
    ))
    session.execute.assert_called_once()


def test_record_parser_observation_truncates_oversize_value() -> None:
    """Defensive: a 10kb header must be truncated to fit varchar(255),
    not raise nor silently drop the observation."""
    session = AsyncMock()
    asyncio.run(record_parser_observation(
        session,
        parser_name="research_workbook",
        observation_kind="unknown_column",
        observed_value="X" * 10_000,
    ))
    # Sanity: execute was called once, and the bound 'value' is ≤ 255.
    call_args = session.execute.call_args
    params = call_args[0][1]  # (sql, params)
    assert len(params["value"]) <= 255


def test_record_parser_observation_skips_empty_value() -> None:
    """An empty observed_value would silently match every existing row
    on the unique constraint — it's nonsense data. Skip it."""
    session = AsyncMock()
    asyncio.run(record_parser_observation(
        session,
        parser_name="research_workbook",
        observation_kind="unknown_column",
        observed_value="",
    ))
    session.execute.assert_not_called()


# Smoke: pytest marker import — the file must collect cleanly even if
# the async helpers are run synchronously above.
@pytest.mark.asyncio
async def test_helper_signature_async() -> None:
    """Pin that the helper is `async def` so callers using `await`
    don't silently get a coroutine they forget to await."""
    session = AsyncMock()
    coro = record_parser_observation(
        session,
        parser_name="x",
        observation_kind="unknown_column",
        observed_value="v",
    )
    # awaiting it must not raise.
    await coro


# ── Cross-package pattern-mining promotions (2026-06) ────────────────
# These variants were observed in real DMA packages but weren't in the
# original ALIASES dict. Promoted in the same commit as parser_observations
# so the migration AND the learned-variant promotion ship together.
# Pin these so future ALIASES dict edits don't silently regress them.


def test_aliases_recognize_subcapability_variant() -> None:
    """`subcapability` (9 occurrences across fixtures) is a known
    spelling of subcap_id. Promoted into ALIASES; the per-pillar
    parser MUST resolve it without falling back to the LLM."""
    from app.services.parsers.research_workbook import PERPILLAR_HEADER_ALIASES
    assert "subcapability" in PERPILLAR_HEADER_ALIASES["subcap_id"]


def test_aliases_recognize_proof_claims_variant() -> None:
    """`proof_claims` (8 occurrences) is analyst-narrative — same
    semantics as excerpt."""
    from app.services.parsers.research_workbook import PERPILLAR_HEADER_ALIASES
    assert "proof_claims" in PERPILLAR_HEADER_ALIASES["excerpt"]


def test_aliases_recognize_proof_links_variant() -> None:
    """`proof_links` (8 occurrences) carries source URLs."""
    from app.services.parsers.research_workbook import PERPILLAR_HEADER_ALIASES
    assert "proof_links" in PERPILLAR_HEADER_ALIASES["source_urls"]


def test_aliases_recognize_tier_sv_variant() -> None:
    """`tier_sv` (7 occurrences) is the subvertical-flagged tier
    column — same int semantics as plain `tier`."""
    from app.services.parsers.research_workbook import PERPILLAR_HEADER_ALIASES
    assert "tier_sv" in PERPILLAR_HEADER_ALIASES["tier"]


def test_promoted_variant_does_not_appear_as_observation() -> None:
    """End-to-end: a workbook using ONE of the promoted variants
    (`subcapability`) must parse cleanly WITHOUT generating an
    unknown_column observation. This is the closing-the-loop assertion."""
    from app.services.parsers.research_workbook import parse_per_pillar_sheets
    header = [
        "subcapability",  # was unknown; now recognized
        "Evidence_IDs", "Source_URLs", "Tier", "Key_Evidence_Excerpt",
    ]
    body = ["P1C1.1.1", "E-001", "https://x.org/a", 3, "exc"]
    wb = _FakeWorkbook([_FakeSheet("P1C1", [header, body])])
    result = parse_per_pillar_sheets(wb)
    leaked = [
        o for o in result.observations
        if o["value"].lower() == "subcapability"
    ]
    assert not leaked, (
        f"`subcapability` should be a known alias now; it leaked into "
        f"observations: {leaked!r}"
    )


# ── CSV observers (2026-06 — second-layer self-improvement hook) ──────


def test_csv_observer_returns_empty_for_known_headers() -> None:
    """A well-formed scoring CSV must NOT emit observations."""
    from app.services.parsers.package_csvs import (
        SCORING_DETAIL_ALIASES,
        observe_csv_unknown_columns,
    )
    txt = (
        "SubCap_ID,Category,Score,Confidence,Evidence_Ceiling,Caps_Applied\n"
        "P1C1.1.1,P1C1,3.0,HIGH,4.5,\n"
    )
    out = observe_csv_unknown_columns(
        txt,
        alias_lookup=SCORING_DETAIL_ALIASES,
        parser_name="package_csvs.parse_scoring_detail_csv",
    )
    assert out == []


def test_csv_observer_surfaces_unknown_columns() -> None:
    """`Diagnostic_Question` (33 occurrences across fixtures) is NOT
    yet recognized. It must show up as an unknown_column observation
    with a heuristic canonical_guess hint."""
    from app.services.parsers.package_csvs import (
        SCORING_DETAIL_ALIASES,
        observe_csv_unknown_columns,
    )
    txt = (
        "SubCap_ID,Score,Confidence,Diagnostic_Question,Uncertainty_Band\n"
        "P1C1.1.1,3.0,HIGH,Some question,LOW\n"
    )
    out = observe_csv_unknown_columns(
        txt,
        alias_lookup=SCORING_DETAIL_ALIASES,
        parser_name="package_csvs.parse_scoring_detail_csv",
    )
    values = [o["value"] for o in out]
    assert "Diagnostic_Question" in values
    assert "Uncertainty_Band" in values


def test_csv_observer_dedupes_within_call() -> None:
    """A header repeated in the same row (rare but possible) must NOT
    yield duplicate observations within the call. The cross-call
    UPSERT collapses these too, but in-call dedup keeps the payload
    small."""
    from app.services.parsers.package_csvs import (
        ISSUE_REGISTER_ALIASES,
        observe_csv_unknown_columns,
    )
    # Construct a CSV that duplicates "Diagnostic_Notes" verbatim.
    txt = (
        "issue_id,severity,Diagnostic_Notes,Diagnostic_Notes\n"
        "ISS-1,HIGH,foo,bar\n"
    )
    out = observe_csv_unknown_columns(
        txt,
        alias_lookup=ISSUE_REGISTER_ALIASES,
        parser_name="package_csvs.parse_issue_register_csv",
    )
    values = [o["value"].lower() for o in out]
    assert values.count("diagnostic_notes") == 1


def test_csv_observer_handles_empty_input() -> None:
    """Empty or all-whitespace CSV → empty list (not a crash)."""
    from app.services.parsers.package_csvs import (
        SCORING_DETAIL_ALIASES,
        observe_csv_unknown_columns,
    )
    assert observe_csv_unknown_columns(
        "",
        alias_lookup=SCORING_DETAIL_ALIASES,
        parser_name="x",
    ) == []
    assert observe_csv_unknown_columns(
        "   \n\n   ",
        alias_lookup=SCORING_DETAIL_ALIASES,
        parser_name="x",
    ) == []


def test_csv_observer_strips_provenance_header() -> None:
    """The `# run_id: ...` provenance line that DMA exports prepend
    must not be parsed as a header row."""
    from app.services.parsers.package_csvs import (
        SCORING_DETAIL_ALIASES,
        observe_csv_unknown_columns,
    )
    txt = (
        "# run_id: DMA-ASM-X-20260101-0001\n"
        "SubCap_ID,Score,Confidence\n"
        "P1C1.1.1,3.0,HIGH\n"
    )
    out = observe_csv_unknown_columns(
        txt,
        alias_lookup=SCORING_DETAIL_ALIASES,
        parser_name="x",
    )
    # No unknowns. If the provenance line were misread as a header,
    # we'd see "# run_id" as an unknown.
    assert out == []


def test_csv_observer_known_aliases_include_cap_id_chain() -> None:
    """The cap-centric layout's `cap_id` / `cap_severity` /
    `cap_source` were promoted in b18a9d9; the observer's alias dict
    must reflect that so those columns no longer surface as unknown."""
    from app.services.parsers.package_csvs import (
        ISSUE_REGISTER_ALIASES,
        observe_csv_unknown_columns,
    )
    txt = (
        "cap_id,cap_severity,cap_source,description\n"
        "CAP-1,HIGH,Risk Memo,Doc gap\n"
    )
    out = observe_csv_unknown_columns(
        txt,
        alias_lookup=ISSUE_REGISTER_ALIASES,
        parser_name="x",
    )
    assert out == []
