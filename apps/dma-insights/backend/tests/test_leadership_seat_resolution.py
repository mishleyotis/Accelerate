"""Leadership critical-seat resolution — no fabricated gaps (2026-07 FCMA).

``enrich_roster`` minted CISO + CDO "gap" rows for FCMA even though the
Client Profile marks CISO (Tiffany Smith, "Chief Security Officer") and CDO
(Daniel Brittain, "Head of Product Strategy, Data and Architecture") FILLED and
lists "Hire a CISO" / "Appoint a CDO" as R12-FORBIDDEN. The matcher now
resolves functional/synonym titles and honours FILLED/CONSOLIDATED markers +
the R12 forbidden-phrase list before declaring any gap. Titles verbatim from
the batch_15 FCMA Client Profile leadership register.
"""
from __future__ import annotations

from app.scripts.derive_leadership import _seat_marked_filled, enrich_roster

# The FCMA roster (subset) — the two seats that were fabricated resolve to
# real people via FUNCTIONAL titles, not the CISO/CDO acronyms.
_FCMA_ROSTER = [
    {"name": "Dan Wagner", "title": "President and Chief Executive Officer"},
    {"name": "Kevin Geron", "title": "Chief Information Officer"},
    {"name": "Tiffany Smith", "title": "Chief Security Officer + Head of IT Operations"},
    {"name": "Daniel Brittain", "title": "Head of Product Strategy, Data and Architecture"},
]


def _gap_titles(roster, blob=""):
    out, _gaps, _n = enrich_roster(roster, blob)
    return {r.get("title") for r in out if r.get("gap_flag")}


class TestFunctionalTitleResolution:
    def test_no_ciso_or_cdo_gap_from_functional_titles(self) -> None:
        gaps = _gap_titles(_FCMA_ROSTER)
        assert "CISO" not in gaps, "Chief Security Officer must fill the CISO seat"
        assert "CDO" not in gaps, "Head of Product Strategy, Data & Arch fills CDO"

    def test_cto_cio_resolved_by_cio_title(self) -> None:
        assert "CTO / CIO" not in _gap_titles(_FCMA_ROSTER)

    def test_de_facto_cdo_in_background_fills_seat(self) -> None:
        roster = [{"name": "A B", "title": "VP", "background": "the de facto CDO"}]
        assert "CDO" not in _gap_titles(roster)


class TestFilledAndR12Markers:
    _PROFILE = "\n".join([
        "Chief Data Officer: FILLED — Daniel Brittain (Head of Product Strategy, Data and Architecture)",
        "Chief Information Security Officer: FILLED — Tiffany Smith (Chief Security Officer)",
        "Chief Technology Officer: CONSOLIDATED — Kevin Geron",
        "'Appoint a CDO' — FORBIDDEN (Brittain filled)",
        "'Hire a CISO' — FORBIDDEN (Smith confirmed)",
    ])

    def test_filled_markers_suppress_gaps(self) -> None:
        # minimal roster (no functional title) — the FILLED/CONSOLIDATED
        # markers + R12 phrases alone must suppress the seats.
        gaps = _gap_titles([{"name": "Only CEO", "title": "CEO"}], self._PROFILE)
        assert not ({"CISO", "CDO", "CTO / CIO"} & gaps)

    def test_seat_marked_filled_detects_each_seat(self) -> None:
        assert _seat_marked_filled("CISO", self._PROFILE)
        assert _seat_marked_filled("CDO", self._PROFILE)
        assert _seat_marked_filled("CTO / CIO", self._PROFILE)

    def test_r12_forbidden_phrase_suppresses_gap(self) -> None:
        assert _seat_marked_filled("CDO", "'Appoint a CDO' — FORBIDDEN")
        assert _seat_marked_filled("CISO", "'Hire a CISO' — FORBIDDEN")


class TestGenuineGapStillFires:
    def test_missing_seat_with_no_evidence_is_still_a_gap(self) -> None:
        # a roster with none of the critical seats + no FILLED markers must
        # still surface the honest gaps (the fix must not suppress real ones).
        gaps = _gap_titles([{"name": "Jane Doe", "title": "President & CEO"}], "")
        assert gaps, "a genuinely absent critical seat must still be a gap"
