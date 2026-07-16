"""Hollow-package census pin — keeps the escaped fail-loud gate honest.

The committed 113-package corpus is seeded in CI with ``DMA_ALLOW_HOLLOW=1``
because its baseline includes 15 scored-but-hollow packages (14 with zero
recommendations + ATB with zero evidence AND zero recommendations) that must
ship as live clients with honest thin-data presentation, not disappear into
PENDING_REVIEW (2026-07-04 regen incident: the gate + repark parked all 15
and the pack would have exported ~80 clients instead of 94).

That escape disarms the ingest-level detection of a REAL regression class:
a parser change that silently hollows packages (empty recommendations /
evidence parses on scored packages — exactly what Part 12.1's DATA_LOSS
gate was built to fail-loud on). This census re-arms it: the number of runs
whose parser_warnings carry the ``hollow_package`` marker must equal the
known corpus baseline EXACTLY. More hollow runs ⇒ a parser regression is
eating data; fewer ⇒ the baseline moved (a package gained recs/evidence) —
either way a human looks before the pin is updated.

    DATABASE_URL=... python -m app.scripts.qa_hollow_census --expect 15

Exit codes: 0 census matches, 1 census drifted, 2 DB unreachable.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Parse-time census: runs whose PARSER marked the package hollow at ingest
# (zero recs / zero evidence). A regression tripwire — the derive chain has
# not run yet, so this counts raw-parse hollowness.
_PARSE_TIME_SQL = (
    "SELECT count(*) FROM runs "
    "WHERE parser_warnings::text LIKE '%hollow_package%'"
)
_PARSE_TIME_NAMES_SQL = (
    "SELECT DISTINCT e.name FROM runs r "
    "JOIN entities e ON e.id = r.entity_id "
    "WHERE r.parser_warnings::text LIKE '%hollow_package%' "
    "ORDER BY e.name"
)

# Post-derive SHIPPED-hollow gate: a client actually SHIPS hollow only if,
# AFTER run_derive_chain (which synthesizes grounded gap-recs + fills
# evidence), an ACTIVE entity's ACTIVE run still has scores but zero
# recommendations OR zero evidence. This is the "no hollows in what ships"
# contract — parse-time hollowness is remediated by the derive chain, so
# only genuinely-unfillable clients (held in PENDING_REVIEW) fall out here.
_SHIPPED_HOLLOW_SQL = """
    SELECT count(*) FROM runs r JOIN entities e ON e.id = r.entity_id
    WHERE r.status = 'ACTIVE' AND e.status = 'ACTIVE'
      AND EXISTS (SELECT 1 FROM subcap_scores s WHERE s.run_id = r.id)
      AND (NOT EXISTS (SELECT 1 FROM recommendations rc WHERE rc.run_id = r.id)
        OR NOT EXISTS (SELECT 1 FROM evidence_index ei WHERE ei.run_id = r.id))
"""
_SHIPPED_HOLLOW_NAMES_SQL = """
    SELECT e.display_id FROM runs r JOIN entities e ON e.id = r.entity_id
    WHERE r.status = 'ACTIVE' AND e.status = 'ACTIVE'
      AND EXISTS (SELECT 1 FROM subcap_scores s WHERE s.run_id = r.id)
      AND (NOT EXISTS (SELECT 1 FROM recommendations rc WHERE rc.run_id = r.id)
        OR NOT EXISTS (SELECT 1 FROM evidence_index ei WHERE ei.run_id = r.id))
    ORDER BY e.display_id
"""


async def main_async(expect: int, post_derive: bool = False) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    count_sql = _SHIPPED_HOLLOW_SQL if post_derive else _PARSE_TIME_SQL
    names_sql = _SHIPPED_HOLLOW_NAMES_SQL if post_derive else _PARSE_TIME_NAMES_SQL
    label = "shipped-hollow (post-derive, ACTIVE clients)" if post_derive \
        else "parse-time hollow-gated runs"
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            n = (await conn.execute(text(count_sql))).scalar() or 0
            names = [row[0] for row in (await conn.execute(text(names_sql))).all()]
    finally:
        await engine.dispose()
    if n == expect:
        print(f"# qa_hollow_census: OK — {n} {label} == pinned {expect}")
        return 0
    if post_derive:
        print(
            f"# qa_hollow_census[post-derive]: FAIL — {n} SHIPPED clients still "
            f"hollow (expected {expect}).\n"
            f"  hollow clients: {', '.join(names) or '(none)'}\n"
            "  An ACTIVE client shipped with scores but zero recs OR zero evidence.\n"
            "  The derive chain must synthesize grounded gap-recs + fill evidence,\n"
            "  or the client must be held in PENDING_REVIEW — never shipped thin.",
            file=sys.stderr,
        )
        return 1
    print(
        f"# qa_hollow_census: FAIL — {n} {label} != pinned {expect}.\n"
        f"  hollow entities: {', '.join(names) or '(none)'}\n"
        "  MORE than pinned ⇒ a parser regression is likely hollowing scored\n"
        "  packages (zero recs/evidence) and DMA_ALLOW_HOLLOW=1 would ship them\n"
        "  silently. FEWER ⇒ the corpus baseline improved. Diagnose FIRST, then\n"
        "  update --expect in infra/cloudbuild.yaml deliberately.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", type=int, required=True,
                    help="pinned hollow-run count for the committed corpus")
    ap.add_argument("--post-derive", action="store_true",
                    help="gate on SHIPPED hollowness (ACTIVE clients still "
                         "missing recs/evidence AFTER the derive chain) rather "
                         "than the parse-time marker; pin --expect 0")
    args = ap.parse_args()
    return asyncio.run(main_async(args.expect, post_derive=args.post_derive))


if __name__ == "__main__":
    raise SystemExit(main())
