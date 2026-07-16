"""Self-improvement observation log for the workbook parsers.

Per the 2026-06 operator mandate: "scripting codes and parsing
segments should always check for new structures and self improve the
code base and their catalogue of parsing techniques."

Today the parsers (`research_workbook.parse_per_pillar_sheets`,
`dma_package._scoring_from_xlsx_fallback`, `package_csvs.
parse_scoring_detail_csv`) ALL key off a static `ALIASES` dict in
their source. When a real-world workbook ships a new column-header
variant (or a sheet-name variant, or a subcap-ID format the regex
doesn't cover), the parser:

  * falls through to the LLM column-mapper (if one is wired), or
  * silently drops the column (no LLM fallback path), or
  * leaks a parser_warning that gets buried in `runs.parser_warnings`.

In every case the SIGNAL is lost — the next code change to the
ALIASES dict has to be reverse-engineered from operator complaints.

This module is the FOUNDATION of the self-improvement loop:

   workbook parsed → unknown columns observed → UPSERT into
   parser_observations → admin endpoint surfaces top-K observations →
   operator (or future nightly job) promotes the variant into the
   ALIASES dict → next deploy ships the learned variant.

Persistence-before-self-improvement contract (per 2026-06 mandate):
the observation rows live in Postgres, NOT in process memory; they
survive worker restarts, deploys, and Cloud Run scale-to-zero. The
admin endpoint reads from the same canonical table — there is no
in-process cache that could diverge.

Usage::

    await record_parser_observation(
        session,
        parser_name="research_workbook",
        observation_kind="unknown_column",
        observed_value="Sub_Capability_ID",
        canonical_guess="subcap_id",
        sample_context={"sheet": "P1C1", "neighbor_headers": [...]},
        run_id=str(run_id),
    )

State branches (matches migration 026 contract):
  - first_sighting   → INSERT (count=1, distinct_runs=1, first_seen=NOW)
  - same_value_seen  → UPSERT (count++, last_seen=NOW; sample_context
                       NEVER overwritten — first capture wins, so the
                       table stays small)
  - distinct_run     → distinct_runs handled best-effort via
                       per-row counter; precise tracking would need a
                       child table which is overkill at this layer.
  - write_failed     → log + swallow; observations MUST NEVER block
                       ingest. The whole point is to learn passively.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


async def record_parser_observation(
    session: AsyncSession,
    *,
    parser_name: str,
    observation_kind: str,
    observed_value: str,
    canonical_guess: str | None = None,
    sample_context: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    """UPSERT a parser observation. Best-effort — failures are logged
    + swallowed; the caller continues parsing.

    `run_id` is currently used only as a logging breadcrumb (we don't
    track exact distinct_runs without a child table); it's accepted
    so future schema upgrades can wire it in without changing every
    call site.
    """
    # Trim oversize observed_value defensively — the column is
    # varchar(255). A workbook with an absurd 1KB header is itself a
    # signal worth keeping, but truncated to fit.
    obs_value = (observed_value or "")[:255]
    if not obs_value:
        return
    try:
        await session.execute(
            text(
                """
                INSERT INTO parser_observations (
                    parser_name, observation_kind, observed_value,
                    canonical_guess, sample_context,
                    occurrence_count, distinct_runs,
                    first_seen, last_seen
                ) VALUES (
                    :parser, :kind, :value,
                    :canonical, CAST(:ctx AS JSONB),
                    1, 1, NOW(), NOW()
                )
                ON CONFLICT
                    (parser_name, observation_kind, observed_value)
                DO UPDATE SET
                    occurrence_count = parser_observations.occurrence_count + 1,
                    last_seen        = NOW(),
                    -- canonical_guess: keep the first non-null guess
                    -- (later guesses are likely no better and
                    -- overwriting risks losing a known-good mapping)
                    canonical_guess  = COALESCE(
                        parser_observations.canonical_guess,
                        EXCLUDED.canonical_guess
                    )
                """
            ),
            {
                "parser": parser_name[:64],
                "kind": observation_kind[:64],
                "value": obs_value,
                "canonical": (canonical_guess or "")[:64] or None,
                "ctx": json.dumps(sample_context or {}),
            },
        )
    except Exception as e:
        # Best-effort: NEVER block ingest on observation-write failure.
        # The most common cause is the table not existing yet (e.g.
        # an old PG that hasn't been migrated to 026). Log at info
        # level so the noise stays bounded in prod.
        log.info(
            "parser_observations.write_failed",
            parser=parser_name,
            kind=observation_kind,
            err=type(e).__name__,
            err_msg=str(e)[:200],
            run_id=run_id,
        )
