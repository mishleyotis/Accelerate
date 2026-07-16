"""D5 timeline mined from the Client Profile "Digital Evolution Timeline".

The Client Research / Profile report carries a rich, dated `Date | Initiative
| Evidence | Zennify Relevance` table that the parser previously ignored. We
mine it into `TimelineEventCandidate[]` as a DERIVED fallback for the D5
Context timeline (used by the orchestrator only when no dated evidence facts
produced events). These tests pin the extraction against all five real
sample reports — faithful (verbatim titles, normalised dates, no fabrication).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.parsers.client_profile import (
    _extract_digital_timeline,
    _normalize_timeline_date,
    parse_client_profile_path,
)

REAL = Path(__file__).parent / "fixtures" / "dma_packages_real_samples"

CLIENT_PROFILES = {
    "WSFS": REAL / "WSFS_Bank__DMA/04_reports/WSFS_Client_Profile_Research_Report.docx",
    "Nicola": REAL / "Nicola_Wealth__DMA/04_reports/NicolaWealth_ClientProfile_Research_Report.docx",
    "Calprivate": REAL / "Calprivate_Bank__DMA/04_reports/DMA_Client_Profile_CPB_20260527.docx",
    "Alma": REAL / "Alma_Bank__DMA/04_reports/AlmaBank_ClientProfile_Research_Report.docx",
    "Odlum": REAL / "Odlum_BROWN__DMA/04_reports/OdlumBrown_ClientProfile_FINAL.docx",
}

# Lower bounds observed in the real reports (extraction must not regress below).
MIN_EVENTS = {"WSFS": 15, "Nicola": 8, "Calprivate": 8, "Alma": 4, "Odlum": 8}


@pytest.mark.parametrize("name", sorted(CLIENT_PROFILES))
def test_timeline_extracted_from_real_client_profile(name: str) -> None:
    path = CLIENT_PROFILES[name]
    if not path.exists():
        pytest.skip(f"fixture missing: {path}")
    result = parse_client_profile_path(path)
    events = result.timeline_events

    assert len(events) >= MIN_EVENTS[name], (
        f"{name}: expected ≥{MIN_EVENTS[name]} timeline events, got {len(events)}"
    )
    # Every event is well-formed and faithful.
    for ev in events:
        assert isinstance(ev.event_date, date)
        assert ev.title and ev.title.strip()
        assert "\n" not in ev.title  # in-cell newlines collapsed
        assert ev.kind in {"milestone", "acquisition", "leadership", "regulatory"}
        # Dates fall in a sane window (no sentinel/garbage years).
        assert 1980 <= ev.event_date.year <= date.today().year + 1
    # Events are not all on the same date (real chronology spans years).
    assert len({ev.event_date.year for ev in events}) >= 2


def test_wsfs_timeline_carries_evidence_ids() -> None:
    """WSFS cites an E-ID per row — they must be threaded onto the events."""
    path = CLIENT_PROFILES["WSFS"]
    if not path.exists():
        pytest.skip("WSFS fixture missing")
    events = parse_client_profile_path(path).timeline_events
    with_eid = [e for e in events if e.e_id]
    assert len(with_eid) >= 15
    for e in with_eid:
        assert e.e_id.startswith("E-")


def test_no_timeline_table_yields_empty() -> None:
    """A document with no timeline-shaped table extracts nothing (no crash)."""
    assert _extract_digital_timeline([]) == []
    assert _extract_digital_timeline(
        [{"header": ["Metric", "Value"], "rows": [["Assets", "$10B"]]}]
    ) == []


@pytest.mark.parametrize(
    "raw,expected_year,expected_month",
    [
        ("2016", 2016, 1),
        ("Jan 2021", 2021, 1),
        ("March 2025", 2025, 3),
        ("Mar 1, 2025", 2025, 3),
        ("2019-2022", 2019, 1),  # range → start year
        ("Q2 2021", 2021, 4),  # Q2 → month 4
        ("2020-05", 2020, 5),
    ],
)
def test_normalize_timeline_date(raw, expected_year, expected_month) -> None:
    from app.services.parsers.facts_extractor import parse_event_date

    dt = parse_event_date(_normalize_timeline_date(raw))
    assert dt is not None, f"{raw!r} → None"
    assert dt.year == expected_year
    assert dt.month == expected_month


def test_garbage_date_cell_is_skipped() -> None:
    """Rows without a parseable date are dropped, not fabricated."""
    table = {
        "header": ["Date", "Initiative", "Evidence", "Zennify Relevance"],
        "rows": [
            ["TBD", "Some future plan", "E-001", "relevance"],
            ["2022", "nCino deployed", "E-002", "lending modernization"],
        ],
    }
    events = _extract_digital_timeline([table])
    assert len(events) == 1
    assert events[0].event_date.year == 2022
    assert events[0].e_id == "E-002"
