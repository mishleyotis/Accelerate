"""Run deduplication — four rules in strict order (stage 1.2 / TRD §07).

  1 artefact priority        (lower is better: a scoring workbook beats a
                              package export)
  2 completion date          (newer wins)
  3 parsed section count     (more complete wins)
  4 stable tiebreak          (lexicographic on the stable key, so the same
                              inputs select the same winner twice)

The loser is retained and MARKED (import_files.dedup_loser + the rule
that decided), never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    stable_key: str                 # artefact id / drive file id
    artefact_priority: int
    completed_at: datetime | None
    parsed_section_count: int


@dataclass(frozen=True)
class DedupOutcome:
    winner: Candidate
    losers: list  # [(Candidate, deciding_rule)]


def pick_winner(candidates: list[Candidate]) -> DedupOutcome:
    if not candidates:
        raise ValueError("no candidates")

    def deciding_rule(a: Candidate, b: Candidate) -> str:
        if a.artefact_priority != b.artefact_priority:
            return "artefact_priority"
        if a.completed_at != b.completed_at:   # None-safe: != never compares
            return "completion_date"
        if a.parsed_section_count != b.parsed_section_count:
            return "parsed_section_count"
        return "stable_tiebreak"

    def sort_key(c: Candidate):
        return (
            c.artefact_priority,                          # asc: 1 beats 4
            -c.completed_at.timestamp() if c.completed_at else float("inf"),
            -c.parsed_section_count,
            c.stable_key,                                 # asc: reproducible
        )

    ordered = sorted(candidates, key=sort_key)
    winner = ordered[0]
    losers = [(c, deciding_rule(winner, c)) for c in ordered[1:]]
    return DedupOutcome(winner=winner, losers=losers)
