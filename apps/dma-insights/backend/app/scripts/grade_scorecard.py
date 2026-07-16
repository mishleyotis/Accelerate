"""Per-segment grade scorecard — the pre-redeploy gate (plan VALIDATION section).

The deploy is HELD until this reads PASS across all segments. It grades every
PERSISTED insight card against the L3 rubric (``nlp.grader.grade``) using the
same shared ``EntityState`` the composer read, and aggregates PASS/fail per
subvertical segment.

Two card classes are reported separately so coverage gaps stay visible:
  * GOLD cards (``GLD*`` — composer-authored) are held to the full bar; a
    healthy gold path passes ~all of them.
  * LADDER cards (deterministic fallback — profile / section / rec / gap) are
    report-sourced and were not composed to the thesis rubric; their grade
    distribution shows where the gold composer (or Gemini) still needs to reach.

The pure scoring/aggregation core (``grade_run``/``aggregate``) takes an
``EntityState`` + card dicts and is unit-testable with no DB. The ``main_async``
wrapper loads state + cards per ACTIVE run and prints the scorecard; ``--json``
emits the machine-readable form and the process exits non-zero when the GOLD
pass-rate falls under ``--fail-under`` (the CI gate).

Usage:
    export DATABASE_URL=postgresql+asyncpg://...
    python -m app.scripts.grade_scorecard [--json] [--fail-under 0.95] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field

from app.services.nlp.grader import Item, grade

# Overlay-client display_ids that must grade at least as well as their gold
# overlay (plan VERIFICATION). Reported explicitly in the scorecard.
OVERLAY_CLIENTS = (
    "farm-credit-mid-america--0001", "regions-bank-0001",
    "alliant-insurance-servic-0001", "capital-farm-credit-0001",
    "greenstone-farm-credit-s-3001",
)


@dataclass
class CardGrade:
    ic_id: str
    is_gold: bool
    passed: bool
    grade: float
    hard_fails: list[str]


@dataclass
class SegmentScore:
    subvertical: str
    n_clients: int = 0
    gold_total: int = 0
    gold_pass: int = 0
    ladder_total: int = 0
    ladder_pass: int = 0
    hard_fail_counts: Counter = field(default_factory=Counter)

    @property
    def gold_pass_rate(self) -> float:
        return self.gold_pass / self.gold_total if self.gold_total else 1.0

    def as_dict(self) -> dict:
        return {
            "subvertical": self.subvertical, "n_clients": self.n_clients,
            "gold_total": self.gold_total, "gold_pass": self.gold_pass,
            "gold_pass_rate": round(self.gold_pass_rate, 3),
            "ladder_total": self.ladder_total, "ladder_pass": self.ladder_pass,
            "top_hard_fails": dict(self.hard_fail_counts.most_common(5)),
        }


def _row_to_item(row: dict) -> Item:
    """Reconstruct the grader Item from a persisted insight_cards row. A high-
    severity card is treated as a top-ranked item (the stricter 3/3 weighted
    bar); supporting cards use the 2/3 bar."""
    sev = (row.get("severity") or "").lower()
    return Item(
        surface="insight_card",
        title=row.get("title") or "",
        what=row.get("what_text") or "",
        why=row.get("why_text") or "",
        so_what=row.get("so_what_text") or "",
        anchor_subcap=row.get("linked_subcap_id"),
        e_ids=list(row.get("linked_e_ids") or []),
        siblings=[],
        is_top=sev in ("critical", "high"),
    )


def grade_run(state, card_rows: list[dict]) -> list[CardGrade]:
    """Grade every persisted card for one run against the rubric (pure)."""
    out: list[CardGrade] = []
    for row in card_rows:
        ic_id = row.get("ic_id") or ""
        g = grade(_row_to_item(row), state)
        out.append(CardGrade(
            ic_id=ic_id, is_gold=ic_id.startswith("GLD"),
            passed=bool(g.passed), grade=float(g.grade),
            hard_fails=list(g.hard_fails or []),
        ))
    return out


def aggregate(per_run: list[tuple[str, list[CardGrade]]]) -> dict[str, SegmentScore]:
    """Roll per-run grades into per-subvertical segments (pure).

    ``per_run`` is a list of ``(subvertical, [CardGrade, ...])``.
    """
    segs: dict[str, SegmentScore] = {}
    for subvertical, grades in per_run:
        sv = subvertical or "UNKNOWN"
        seg = segs.setdefault(sv, SegmentScore(subvertical=sv))
        seg.n_clients += 1
        for cg in grades:
            if cg.is_gold:
                seg.gold_total += 1
                seg.gold_pass += int(cg.passed)
            else:
                seg.ladder_total += 1
                seg.ladder_pass += int(cg.passed)
            if not cg.passed:
                seg.hard_fail_counts.update(cg.hard_fails or ["weighted"])
    return segs


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.nlp.entity_knowledge import load_entity_state

    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    per_run: list[tuple[str, list[CardGrade]]] = []
    overlay_rows: list[dict] = []
    async with maker() as session:
        runs = (await session.execute(text(
            """
            SELECT e.display_id, e.subvertical
              FROM entities e JOIN runs r ON r.entity_id = e.id
             WHERE r.status = 'ACTIVE'
             ORDER BY e.display_id
            """ + ("" if args.limit is None else " LIMIT :lim")),
            {} if args.limit is None else {"lim": args.limit})).all()
        for run in runs:
            state = await load_entity_state(
                session, entity_display_id=run.display_id)
            if state is None:
                continue
            rows = [dict(m) for m in (await session.execute(text(
                "SELECT ic_id, severity, title, what_text, why_text, "
                "so_what_text, linked_subcap_id, linked_e_ids "
                "FROM insight_cards WHERE run_id = :rid"),
                {"rid": state.run_id})).mappings().all()]
            grades = grade_run(state, rows)
            per_run.append((run.subvertical, grades))
            if run.display_id in OVERLAY_CLIENTS:
                gp = sum(1 for g in grades if g.is_gold and g.passed)
                gt = sum(1 for g in grades if g.is_gold)
                overlay_rows.append({"client": run.display_id,
                                     "gold_pass": gp, "gold_total": gt})
    await engine.dispose()

    segs = aggregate(per_run)
    gold_total = sum(s.gold_total for s in segs.values())
    gold_pass = sum(s.gold_pass for s in segs.values())
    overall = gold_pass / gold_total if gold_total else 1.0
    gate_ok = overall >= args.fail_under

    if args.json:
        print(json.dumps({
            "overall_gold_pass_rate": round(overall, 3),
            "gold_total": gold_total, "gold_pass": gold_pass,
            "fail_under": args.fail_under, "gate_ok": gate_ok,
            "segments": [s.as_dict() for s in sorted(
                segs.values(), key=lambda x: x.subvertical)],
            "overlays": overlay_rows,
        }, indent=2))
    else:
        print(f"# grade scorecard — overall GOLD pass rate "
              f"{overall:.1%} ({gold_pass}/{gold_total}), "
              f"gate {'PASS' if gate_ok else 'FAIL'} "
              f"(>= {args.fail_under:.0%})")
        for s in sorted(segs.values(), key=lambda x: x.subvertical):
            print(f"  {s.subvertical:8} clients={s.n_clients:3} "
                  f"gold {s.gold_pass:3}/{s.gold_total:<3} "
                  f"({s.gold_pass_rate:.0%})  ladder {s.ladder_pass}/{s.ladder_total}"
                  + (f"  fails={dict(s.hard_fail_counts.most_common(4))}"
                     if s.gold_pass < s.gold_total else ""))
        for o in overlay_rows:
            print(f"  overlay {o['client']}: gold {o['gold_pass']}/{o['gold_total']}")
    return 0 if gate_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--fail-under", type=float, default=0.95,
                   help="min overall GOLD pass rate for the gate (default 0.95)")
    p.add_argument("--limit", type=int, help="only first N runs")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
