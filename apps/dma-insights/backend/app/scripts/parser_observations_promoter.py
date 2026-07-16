"""Auto-PR-emitting promoter for the parser-observations queue.

Drains `parser_observations` (migration 026) and emits a patch
proposal listing the highest-frequency unknown columns the operator
should consider promoting into the static ALIASES dicts. The intent
is twofold:

  1. CLI use today — `python -m app.scripts.parser_observations_promoter`
     prints the patch and exits 0. The operator copy-pastes the
     suggested alias additions into the parser source.
  2. Cloud Run Job tomorrow — wrapped by a worker that runs nightly
     against prod, emits the report to Cloud Logging, and (in a
     future iteration) opens a draft PR via the GitHub API.

The script DOES NOT auto-edit source code or auto-open a PR in this
revision — landing that would commit live-secret + branch-write
behavior that has to be operator-blessed. This is the "humans
approve, machines suggest" half of the loop.

Algorithm
---------
For each (parser_name, observation_kind) pair, fetch up to N
observations sorted by `occurrence_count DESC, distinct_runs DESC`
and emit a markdown block per pair:

    ## research_workbook · unknown_column (3 candidates)

    | Variant            | Count | Distinct runs | Guess        |
    |--------------------|------:|--------------:|--------------|
    | `subcapability`    | 42    | 7             | `subcap_id`  |
    | `proof_claims`     | 28    | 5             | `excerpt`    |
    | `evidence_score`   | 9     | 2             | (no guess)   |

    Suggested patch (PERPILLAR_HEADER_ALIASES):
    ```python
    "subcap_id": [..., "subcapability"],
    "excerpt":   [..., "proof_claims"],
    # evidence_score: no high-confidence canonical guess; review manually
    ```

State branches:
  - empty_queue       → "no observations recorded; queue clean" + exit 0
  - low_frequency     → variants below `--min-occurrences` (default 3)
                        are skipped — keeps the report focused on
                        recurring patterns vs one-offs
  - no_guess          → variant included in the table; the suggested
                        patch comments it out so the operator manually
                        decides the canonical mapping
  - high_guess        → variant included AND emitted as a one-line
                        suggested alias addition

Run with::

    python -m app.scripts.parser_observations_promoter
    python -m app.scripts.parser_observations_promoter --min-occurrences 5
    python -m app.scripts.parser_observations_promoter --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

log = structlog.get_logger(__name__)


@dataclass
class Candidate:
    value: str
    canonical_guess: str | None
    occurrence_count: int
    distinct_runs: int
    sample_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromotionReport:
    """Per (parser_name, observation_kind) bucket of candidates."""

    parser_name: str
    observation_kind: str
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def total_observations(self) -> int:
        return sum(c.occurrence_count for c in self.candidates)


async def fetch_promotion_buckets(
    engine: AsyncEngine, *, min_occurrences: int, limit_per_bucket: int,
) -> list[PromotionReport]:
    """SELECT from `parser_observations` and bucket by
    (parser_name, observation_kind)."""
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text(
                """
                SELECT parser_name, observation_kind, observed_value,
                       canonical_guess, occurrence_count, distinct_runs,
                       sample_context
                  FROM parser_observations
                 WHERE occurrence_count >= :min_occ
                 ORDER BY parser_name, observation_kind,
                          occurrence_count DESC, distinct_runs DESC
                """
            ),
            {"min_occ": min_occurrences},
        )).mappings().all()
    buckets: dict[tuple[str, str], PromotionReport] = defaultdict(
        lambda: PromotionReport(parser_name="", observation_kind="")
    )
    for r in rows:
        key = (r["parser_name"], r["observation_kind"])
        if buckets[key].parser_name == "":
            buckets[key].parser_name = r["parser_name"]
            buckets[key].observation_kind = r["observation_kind"]
        if len(buckets[key].candidates) >= limit_per_bucket:
            continue
        buckets[key].candidates.append(Candidate(
            value=r["observed_value"],
            canonical_guess=r["canonical_guess"],
            occurrence_count=r["occurrence_count"],
            distinct_runs=r["distinct_runs"],
            sample_context=r["sample_context"] or {},
        ))
    return list(buckets.values())


def render_markdown(reports: list[PromotionReport]) -> str:
    """Render the operator-facing report. Each bucket gets a table +
    a suggested alias-patch block. Variants with no canonical_guess
    are commented out in the patch — the operator decides the
    mapping manually rather than the script guessing wrong."""
    if not reports:
        return (
            "# parser_observations promoter\n\n"
            "_No observations meet the minimum-occurrences threshold._\n"
            "Queue is clean.\n"
        )
    out = ["# parser_observations promoter", ""]
    for rep in sorted(
        reports,
        key=lambda r: (-r.total_observations, r.parser_name),
    ):
        out.append(
            f"## {rep.parser_name} · {rep.observation_kind} "
            f"({len(rep.candidates)} candidates, "
            f"{rep.total_observations} total observations)"
        )
        out.append("")
        out.append("| Variant | Count | Distinct runs | Guess |")
        out.append("|---|---:|---:|---|")
        for c in rep.candidates:
            guess = f"`{c.canonical_guess}`" if c.canonical_guess else "_(no guess)_"
            out.append(
                f"| `{c.value}` | {c.occurrence_count} | "
                f"{c.distinct_runs} | {guess} |"
            )
        out.append("")
        # Suggested patch — group by canonical_guess.
        by_guess: dict[str | None, list[str]] = defaultdict(list)
        for c in rep.candidates:
            by_guess[c.canonical_guess].append(c.value)
        out.append("Suggested patch:")
        out.append("```python")
        for guess, values in sorted(
            by_guess.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
        ):
            for v in values:
                line = f'"{v}",'
                if guess:
                    out.append(f'    "{guess}": [..., {line}]')
                else:
                    out.append(
                        f"    # no high-confidence guess for {line} "
                        f"— review manually"
                    )
        out.append("```")
        out.append("")
    return "\n".join(out)


def render_json(reports: list[PromotionReport]) -> str:
    """Machine-readable alternative used by the future Cloud Run Job
    wrapper to drive the GitHub-API auto-PR path."""
    payload = [
        {
            "parser_name": r.parser_name,
            "observation_kind": r.observation_kind,
            "candidates": [
                {
                    "value": c.value,
                    "canonical_guess": c.canonical_guess,
                    "occurrence_count": c.occurrence_count,
                    "distinct_runs": c.distinct_runs,
                    "sample_context": c.sample_context,
                }
                for c in r.candidates
            ],
        }
        for r in reports
    ]
    return json.dumps(payload, indent=2)


async def _main_async(args: argparse.Namespace) -> int:
    # Lazy import settings — avoids env-var requirements when running
    # just `--help`.
    from app.config import get_settings
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        reports = await fetch_promotion_buckets(
            engine,
            min_occurrences=args.min_occurrences,
            limit_per_bucket=args.limit,
        )
    finally:
        await engine.dispose()
    if args.json:
        sys.stdout.write(render_json(reports))
    else:
        sys.stdout.write(render_markdown(reports))
    sys.stdout.write("\n")
    log.info(
        "parser_observations_promoter.done",
        buckets=len(reports),
        total=sum(r.total_observations for r in reports),
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--min-occurrences",
        type=int,
        default=3,
        help="Skip variants seen fewer than N times (default 3).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Cap candidates per (parser, kind) bucket (default 20).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of markdown.",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
