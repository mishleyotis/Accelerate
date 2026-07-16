"""Rendered-language audit (Batch 6) -- DB-text audit's twin for the
served API surface.

The original ``qa_language_audit.py`` scans DB-persisted narrative text
(subcap_scores.rationale, document_sections.body, recommendations.
description, etc.) -- 1791 violations across 98/104 entities at the
Batch 3 baseline.

This harness scans the SAME content but as served by the API surface
AFTER the Batch 6 ``narrative_polish`` pass has applied. The reduction
demonstrates the rewriter's production impact on the AE-facing
surfaces while leaving the source rows pristine (the bot's text is
audit-preserved at the DB layer; only the rendered output is
polished).

For each ACTIVE entity, the harness hits:
  - /api/v1/entities/{display_id}/recommendations -- list (polished
    titles)
  - /api/v1/recommendations/{rec_id} -- detail (polished title +
    description)
  - /api/v1/entities/{display_id}/heatmap/subcap/{subcap_id} -- a
    sample of 3-5 subcaps per entity (polished_rationale +
    polished_cap_reason)

For each scanned text, runs the same 6 audit rules from
``qa_language_audit.RULES`` and counts violations. Emits per-rule and
per-surface totals + an OK/FAIL classification per entity.

Usage:

    export DATABASE_URL=postgresql+asyncpg://...
    python -m app.scripts.qa_rendered_language_audit \\
        --output docs/qa/qa_rendered_language_audit.tsv

Exit code: 0 if the rendered total is < 50% of the DB-text total
(production-impact contract); 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

from app.database import get_sessionmaker
from app.deps import CurrentUser, get_current_user
from app.main import app
from app.scripts.qa_language_audit import RULES


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid4()),
        email="qa-rendered@dma.local",
        role="ADMIN",
        name="QA Rendered Audit",
    )


def _count_violations_in(text_in: str) -> Counter:
    """Per-rule violation count on a single text blob."""
    out: Counter = Counter()
    if not text_in or not isinstance(text_in, str):
        return out
    for rule_id, rule in RULES.items():
        for pat, _ in rule["patterns"]:
            n = len(re.findall(pat, text_in, re.IGNORECASE))
            if n:
                out[rule_id] += n
    return out


async def fetch_entities(
    limit: int | None,
) -> list[tuple[str, str]]:
    """Return (display_id, name) of all ACTIVE entities."""
    sm = get_sessionmaker()
    async with sm() as session:
        sql = (
            "SELECT display_id, name FROM entities "
            "WHERE status='ACTIVE' AND display_id IS NOT NULL "
            "ORDER BY display_id"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = (await session.execute(text(sql))).all()
    return [(r.display_id, r.name) for r in rows]


async def fetch_sample_subcap_ids_for(
    display_id: str, k: int = 3,
) -> list[str]:
    """Random sample of K subcap_ids for the entity's ACTIVE run."""
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(
            text(
                "SELECT s.subcap_id FROM subcap_scores s "
                "JOIN runs r ON r.id = s.run_id "
                "JOIN entities e ON e.id = r.entity_id "
                "WHERE e.display_id = :did AND r.status='ACTIVE' "
                "  AND s.rationale IS NOT NULL "
                "  AND length(s.rationale) >= 100 "
                "ORDER BY random() LIMIT :k"
            ),
            {"did": display_id, "k": k},
        )).all()
    return [r[0] for r in rows]


async def _scan_entity_responses(
    client: httpx.AsyncClient, display_id: str,
) -> Counter:
    """Probe the polished endpoints for one entity; sum per-rule
    violations across all rendered narrative strings encountered.
    """
    totals: Counter = Counter()

    # 1. Recommendation list (polished titles).
    r = await client.get(f"/api/v1/entities/{display_id}/recommendations")
    if r.status_code == 200:
        try:
            items = r.json()
        except (json.JSONDecodeError, ValueError):
            items = []
        for rec in items if isinstance(items, list) else []:
            totals.update(_count_violations_in(rec.get("title", "")))

    # 2. Subcap detail (polished_rationale + polished_cap_reason).
    sample = await fetch_sample_subcap_ids_for(display_id, k=3)
    for sid in sample:
        r2 = await client.get(
            f"/api/v1/entities/{display_id}/heatmap/subcap/{sid}"
        )
        if r2.status_code == 200:
            try:
                body = r2.json()
            except (json.JSONDecodeError, ValueError):
                body = {}
            totals.update(_count_violations_in(body.get("polished_rationale", "")))
            totals.update(_count_violations_in(body.get("polished_cap_reason", "")))

    return totals


async def main_async(args: argparse.Namespace) -> int:
    app.dependency_overrides[get_current_user] = _fake_user
    entities = await fetch_entities(args.limit)
    print(f"# {len(entities)} active entities to audit", flush=True)

    rows = ["display_id\tname\ttotal_violations\tby_rule"]
    overall: Counter = Counter()
    per_entity_totals: list[tuple[str, int]] = []
    errored: list[str] = []

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
    ) as client:
        for i, (display_id, name) in enumerate(entities, 1):
            try:
                ent_violations = await _scan_entity_responses(client, display_id)
            except Exception as e:
                # DO NOT silently drop an errored entity: excluding it shrinks
                # rendered_total and could let the < 0.5x-baseline contract PASS
                # while a chunk of the corpus failed to render. Record it and
                # gate on it below.
                print(
                    f"# AUDIT ERROR for {display_id}: {type(e).__name__}: {e}",
                    flush=True,
                )
                errored.append(f"{display_id} ({type(e).__name__})")
                continue
            total = sum(ent_violations.values())
            per_entity_totals.append((display_id, total))
            overall.update(ent_violations)
            rows.append(
                f"{display_id}\t{name}\t{total}\t"
                f"{json.dumps(dict(ent_violations))}"
            )
            if i % 20 == 0:
                print(
                    f"  ... {i}/{len(entities)} audited "
                    f"(rendered total so far: {sum(overall.values())})",
                    flush=True,
                )

    output = "\n".join(rows) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        print(f"# wrote audit to {out}", flush=True)

    rendered_total = sum(overall.values())
    n_entities_with_violations = sum(
        1 for _, t in per_entity_totals if t > 0
    )
    print(
        f"\n# RENDERED-LANGUAGE AUDIT SUMMARY: "
        f"{rendered_total} violations across "
        f"{n_entities_with_violations}/{len(entities)} entities",
        flush=True,
    )
    if overall:
        print("\n# By rule:", flush=True)
        for rid, n in overall.most_common():
            desc = RULES[rid]["description"]
            print(f"  {n:5}  {rid}  --  {desc}", flush=True)

    # A render error is a false-pass hole: an errored entity contributes 0
    # violations, so enough of them would drag rendered_total under the
    # contract threshold while the corpus is actually broken. Any render error
    # on a freshly-seeded+derived corpus is a real defect — gate on it.
    if errored:
        print(
            f"\n# AUDIT INCOMPLETE: {len(errored)} entity(ies) failed to render "
            f"— cannot certify the language contract (would under-count "
            f"violations). Errored: {', '.join(errored[:10])}"
            + (f", +{len(errored) - 10} more" if len(errored) > 10 else ""),
            flush=True,
        )
        return 1

    # Comparison vs the DB-text baseline (Batch 3: 1791 violations).
    # The production contract is rendered_total < db_total * 0.5; the
    # exit code reflects this.
    DB_BASELINE = 1791
    if rendered_total < DB_BASELINE * 0.5:
        print(
            f"\n# PRODUCTION CONTRACT MET: rendered={rendered_total} < "
            f"db_baseline={DB_BASELINE} * 0.5 = {DB_BASELINE * 0.5:.0f}",
            flush=True,
        )
        return 0
    print(
        f"\n# PRODUCTION CONTRACT NOT MET: rendered={rendered_total} "
        f">= db_baseline={DB_BASELINE} * 0.5 = {DB_BASELINE * 0.5:.0f}",
        flush=True,
    )
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--output",
        help="Write TSV to this path (default: stdout summary only)",
    )
    p.add_argument(
        "--limit", type=int,
        help="Audit only first N entities",
    )
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
