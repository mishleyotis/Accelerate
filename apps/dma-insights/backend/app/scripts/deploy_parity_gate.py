"""Pre-deploy parity gate — NON-NEGOTIABLE (operator mandate 2026-06-11).

For EVERY ACTIVE client, every page-critical field must be persisted
and renderable BEFORE a deploy may proceed. Any violation invokes the
self-healing ladder (the §2c derive scripts, idempotent) exactly once,
then re-checks; clients still violating FAIL the gate (exit 1) and the
deploy must not ship.

Checked per client (the prototype's filled-page contract):
  score      — overall maturity derivable (scored subcaps > 0)
  findings   — top_findings persisted (>0)
  why_now    — why_now_signals persisted (>0)
  platform   — platform_scores with fit > 0
  focus      — ≥1 RENDERABLE focus area (post focus_area_sanity)
  alerts     — thin subcaps exist ⇒ alerts derived for the entity

Usage:
  DATABASE_URL=... python -m app.scripts.deploy_parity_gate [--no-heal]
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.focus_area_sanity import clean_focus_area

HEAL_LADDER = [
    "app.scripts.repark_junk_entities",
    "app.scripts.backfill_run_dates",
    "app.scripts.broadcast_peer_medians",
    "app.scripts.derive_insights",
    "app.scripts.derive_focus_areas",
    "app.scripts.derive_alerts",
]

CHECK_SQL = """
SELECT e.display_id,
  (SELECT count(*) FROM subcap_scores s WHERE s.run_id=r.id AND s.score>0) AS scored,
  jsonb_array_length(COALESCE(r.top_findings,'[]'::jsonb))   AS findings,
  jsonb_array_length(COALESCE(r.why_now_signals,'[]'::jsonb)) AS why_now,
  (SELECT count(*) FROM platform_scores p
    WHERE p.run_id=r.id AND p.fit_score>0)                    AS pfit,
  (SELECT count(*) FROM subcap_scores s
    WHERE s.run_id=r.id AND s.is_thin_evidence)               AS thin,
  (SELECT count(*) FROM alerts a
    WHERE a.entity_id=e.id AND a.closed_at IS NULL)           AS alerts
FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
WHERE e.status='ACTIVE' ORDER BY e.display_id
"""

FA_SQL = """
SELECT e.display_id, f.title, f.verbatim_quote
FROM focus_areas f
JOIN entities e ON e.id=f.entity_id
JOIN runs r ON r.id=f.run_id AND r.status='ACTIVE'
WHERE e.status='ACTIVE'
"""


async def _violations(url: str) -> dict[str, list[str]]:
    engine = create_async_engine(url)
    out: dict[str, list[str]] = {}
    async with async_sessionmaker(engine)() as session:
        fa_ok: dict[str, int] = {}
        for r in (await session.execute(text(FA_SQL))).all():
            keep, _ = clean_focus_area(r.title, r.verbatim_quote)
            if keep:
                fa_ok[r.display_id] = fa_ok.get(r.display_id, 0) + 1
        for r in (await session.execute(text(CHECK_SQL))).all():
            bad = []
            if not r.scored:
                bad.append("score")
            if not r.findings:
                bad.append("findings")
            if not r.why_now:
                bad.append("why_now")
            if not r.pfit:
                bad.append("platform")
            if not fa_ok.get(r.display_id):
                bad.append("focus")
            if r.thin and not r.alerts:
                bad.append("alerts")
            if bad:
                out[r.display_id] = bad
    await engine.dispose()
    return out


def _heal() -> None:
    env = os.environ.copy()
    for mod in HEAL_LADDER:
        print(f"  ⟳ self-heal: {mod}", flush=True)
        subprocess.run(
            [sys.executable, "-m", mod], env=env, check=False,
            capture_output=True, timeout=1800,
        )


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    heal = "--no-heal" not in sys.argv[1:]
    v1 = asyncio.run(_violations(url))
    if not v1:
        print("# deploy_parity_gate: PASS — every ACTIVE client fully filled")
        return 0
    print(f"# deploy_parity_gate: {len(v1)} client(s) violating — "
          f"{'invoking self-heal' if heal else 'heal disabled'}")
    for k, bad in sorted(v1.items())[:20]:
        print(f"  ✗ {k}: {','.join(bad)}")
    if not heal:
        return 1
    _heal()
    v2 = asyncio.run(_violations(url))
    if not v2:
        print("# deploy_parity_gate: HEALED → PASS")
        return 0
    print(f"# deploy_parity_gate: FAIL — {len(v2)} client(s) still violating "
          f"after self-heal; deploy MUST NOT proceed")
    for k, bad in sorted(v2.items()):
        print(f"  ✗ {k}: {','.join(bad)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
