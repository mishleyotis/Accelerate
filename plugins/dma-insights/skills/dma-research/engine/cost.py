#!/usr/bin/env python3
"""What a run costs, measured — and the budget it is held to.

    python3 -m engine.cost model                 # the rate card and the levers
    python3 -m engine.cost estimate --subcaps 183 [--shape measured|target]
    python3 -m engine.cost budget --run R [--json]
    python3 -m engine.cost record --run R --turns N --cache-read N \
            --cache-write N --output N [--uncached N] [--model sonnet]

WHY THIS EXISTS. The 2026-08-30 review set a ceiling of **$5 per pillar**.
Nothing in the engine knew what a run cost, so the ceiling was a hope. This
module measures it, and the measurement is uncomfortable:

    Golden 1, six subcaps, 188 assistant turns, Sonnet 5
      cache read   24,454,213 tok   $4.89   (76% of the bill)
      cache write     441,293 tok   $1.10
      uncached in     211,703 tok   $0.42
      output            2,935 tok   $0.03
      ----------------------------------------
      total                         $6.45   =  $1.07 per subcap

At that shape a CU T1_CORE engagement (690 selected cells) costs **~$741**,
against a $20 target. The gap is 37x, and no amount of prompt tightening
closes 37x — so the module states the levers that DO, with the arithmetic
attached, and enforces the budget rather than hoping for it.

WHERE THE MONEY ACTUALLY GOES. Not output (0.4% of the bill). Not search.
**Cache reads: 130K tokens re-read on every one of 188 turns.** Cost is
`turns x context x rate`, so the only levers that matter are the ones that
reduce turns or context — and the one that reduces BOTH is changing the
grain at which research is dispatched.
"""
from __future__ import annotations

# Runnable both ways: -m engine.cost, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from . import contract as C

#: $ per 1M tokens, Anthropic first-party rates. Cache reads bill at 0.1x
#: input, cache writes at 1.25x — which is why a long-lived context is cheap
#: to KEEP and expensive to re-read many times.
RATES = {
    "opus":   {"in": 5.00, "out": 25.00},
    "sonnet": {"in": 2.00, "out": 10.00},
    "haiku":  {"in": 1.00, "out": 5.00},
}
CACHE_READ_MULT, CACHE_WRITE_MULT = 0.10, 1.25

#: The review's ceiling. Per PILLAR, so a four-pillar engagement is $20.
BUDGET_PER_PILLAR = 5.00

#: Golden 1, measured 2026-08-29. The baseline every projection starts from,
#: kept as data so a re-measurement replaces it rather than arguing with it.
MEASURED = {
    "label": "Golden 1 P1C1, 2026-08-29",
    "model": "sonnet", "subcaps": 6, "turns": 188,
    "cache_read": 24_454_213, "cache_write": 441_293,
    "uncached": 211_703, "output": 2_935,
    "wall_clock_min": 18.7,
}

#: Each lever, what it multiplies the bill by, and what it costs to have.
#: `evidence` is why the factor is believed — a lever with no measurement
#: behind it says so, because an invented factor is how a budget gets
#: "achieved" on paper.
LEVERS = [
    {
        "id": "capability_grain",
        "factor": 0.20,
        "what": "Dispatch research at CAPABILITY grain, not subcap grain.",
        "why": ("690 selected cells sit under 136 capabilities — roughly five "
                "subcaps each, sharing sources, sharing searches and sharing "
                "the diagnostic questions' framing. One research pass per "
                "capability that SYNTHESISES per subcap amortises the context "
                "read across five cells instead of paying it five times."),
        "evidence": ("arithmetic on the catalogue: 690 cells / 136 "
                     "capabilities = 5.07 cells per pass"),
        "cost": ("subcap syntheses within one capability share a context, so "
                 "a mistaken frame propagates to five cells rather than one. "
                 "The floors gate and the independent challenge still run per "
                 "subcap, which is what contains it."),
    },
    {
        "id": "turn_discipline",
        "factor": 0.26,
        "what": "Eight turns per card, not thirty-one.",
        "why": ("Cost is turns x context. Golden 1 spent 31.3 assistant turns "
                "per subcap; the protocol already says to work a card in at "
                "most four Bash invocations and it was not enforced. Batch "
                "the ledger writes, batch the searches, and stop narrating "
                "between them."),
        "evidence": ("measured 188 turns / 6 subcaps = 31.3; the protocol's "
                     "own ceiling implies ~8"),
        "cost": "none identified — the extra turns were narration, not work.",
    },
    {
        "id": "context_hygiene",
        "factor": 0.50,
        "what": "Clear spent tool results from the context each card.",
        "why": ("The workbook is the record, so a researcher on card N does "
                "not need card 1's tool results in context — they are on "
                "disk. Context editing (clear_tool_uses) drops them; the "
                "average re-read falls from ~130K towards ~65K."),
        "evidence": ("measured 24.45M cache-read / 188 turns = 130K per turn "
                     "on a run whose live working set is far smaller"),
        "cost": ("a cleared result cannot be re-read without re-fetching; the "
                 "engine's own state must therefore stay in the workbook, "
                 "which is the existing invariant."),
    },
    {
        "id": "model_tiering",
        "factor": 0.65,
        "what": "Haiku for the mechanical turns, Sonnet for the reasoning.",
        "why": ("Logging a search, appending evidence and reading a card are "
                "not reasoning. At $1/1M against Sonnet's $2 they halve the "
                "rate on the turns that carry no judgement."),
        "evidence": ("rate-card arithmetic; the split of mechanical to "
                     "reasoning turns is NOT yet measured, so 0.65 is a "
                     "conservative placeholder rather than a result"),
        "cost": ("a mis-tiered turn produces a worse judgement at a lower "
                 "price, which is the expensive kind of saving. Tier by "
                 "COMMAND, never by feel."),
    },
]


#: The wall-clock target for a finished assessment, and the fan-out that
#: reaches it. Measured: Golden 1 ran 6 subcaps in 18.7 min SEQUENTIALLY
#: inside one researcher — 3.1 min/subcap. At capability grain and eight
#: turns a card that becomes ~4 min per capability pass, and the sixteen
#: category researchers are independent by construction: each owns its own
#: grain, writes its own rows, and shares only the workbook, which appends.
TARGET_WALL_CLOCK_MIN = 120
PARALLEL_LANES = 16                 # one per catalogue category
MIN_PER_CAPABILITY_PASS = 4.0       # levered: 8 turns at ~30s
PHASE_MINUTES = {
    # PRELIM and the reports are NOT parallel across categories — they are
    # about the institution, not a capability — so they are added whole.
    "preflight (financials, census, the question)": 10,
    "PRELIM (profile, timeline, peers, tech baseline)": 15,
    "category research (16 lanes, in parallel)": None,   # computed
    "gates + independent challenge": 10,
    "report sections (2 producers, in parallel) + review": 25,
    "assemble, verify, push": 5,
}


def schedule(subcaps: int, capabilities: int | None = None,
             lanes: int = PARALLEL_LANES) -> dict:
    """Wall clock, given the fan-out. Parallelism is a property of the
    DISPATCH, not of the work: sixteen category researchers touch disjoint
    grains, so the research phase divides by the number of lanes the harness
    actually runs — and by nothing else."""
    caps = capabilities or max(1, round(subcaps / 5.07))
    research_serial = caps * MIN_PER_CAPABILITY_PASS
    research_parallel = research_serial / max(1, lanes)
    phases = dict(PHASE_MINUTES)
    phases["category research (16 lanes, in parallel)"] = round(
        research_parallel, 1)
    total = sum(v for v in phases.values() if v)
    return {
        "subcaps": subcaps, "capability_passes": caps, "lanes": lanes,
        "research_serial_min": round(research_serial, 1),
        "research_parallel_min": round(research_parallel, 1),
        "phases_min": phases,
        "total_min": round(total, 1),
        "target_min": TARGET_WALL_CLOCK_MIN,
        "within_target": total <= TARGET_WALL_CLOCK_MIN,
        "headroom_min": round(TARGET_WALL_CLOCK_MIN - total, 1),
    }


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cost_of(*, cache_read: int = 0, cache_write: int = 0, uncached: int = 0,
            output: int = 0, model: str = "sonnet") -> dict:
    """One usage record, priced."""
    r = RATES.get(model) or RATES["sonnet"]
    parts = {
        "cache_read": cache_read / 1e6 * r["in"] * CACHE_READ_MULT,
        "cache_write": cache_write / 1e6 * r["in"] * CACHE_WRITE_MULT,
        "uncached_input": uncached / 1e6 * r["in"],
        "output": output / 1e6 * r["out"],
    }
    total = sum(parts.values())
    return {"model": model, "total_usd": round(total, 4),
            "parts_usd": {k: round(v, 4) for k, v in parts.items()},
            "share": {k: (round(v / total, 3) if total else 0.0)
                      for k, v in parts.items()},
            "tokens": {"cache_read": cache_read, "cache_write": cache_write,
                       "uncached": uncached, "output": output}}


def measured_baseline() -> dict:
    m = MEASURED
    c = cost_of(cache_read=m["cache_read"], cache_write=m["cache_write"],
                uncached=m["uncached"], output=m["output"], model=m["model"])
    c.update({
        "label": m["label"], "subcaps": m["subcaps"], "turns": m["turns"],
        "usd_per_subcap": round(c["total_usd"] / m["subcaps"], 4),
        "usd_per_turn": round(c["total_usd"] / m["turns"], 5),
        "context_per_turn_tokens": round(m["cache_read"] / m["turns"]),
        "minutes_per_subcap": round(m["wall_clock_min"] / m["subcaps"], 2),
    })
    return c


def projected(levers: list[str] | None = None) -> dict:
    """The per-subcap cost with the named levers applied (all, by default)."""
    base = measured_baseline()["usd_per_subcap"]
    use = [l for l in LEVERS if levers is None or l["id"] in levers]
    factor = 1.0
    for l in use:
        factor *= l["factor"]
    return {"levers": [l["id"] for l in use], "combined_factor": round(factor, 4),
            "usd_per_subcap": round(base * factor, 5),
            "reduction_x": round(1 / factor, 1) if factor else None}


def pillar_estimate(subcaps_by_pillar: dict[str, int],
                    levers: list[str] | None = None) -> dict:
    """What each pillar costs, measured shape and levered shape."""
    base = measured_baseline()["usd_per_subcap"]
    proj = projected(levers)
    out = {"budget_per_pillar_usd": BUDGET_PER_PILLAR, "pillars": {},
           "levers": proj["levers"], "combined_factor": proj["combined_factor"]}
    total_m = total_p = 0.0
    for pillar, n in sorted(subcaps_by_pillar.items()):
        m, p = base * n, proj["usd_per_subcap"] * n
        total_m += m
        total_p += p
        out["pillars"][pillar] = {
            "subcaps": n,
            "measured_usd": round(m, 2),
            "levered_usd": round(p, 2),
            "within_budget": p <= BUDGET_PER_PILLAR,
            "over_by_usd": round(max(0.0, p - BUDGET_PER_PILLAR), 2),
        }
    out["run_total_measured_usd"] = round(total_m, 2)
    out["run_total_levered_usd"] = round(total_p, 2)
    out["run_budget_usd"] = round(BUDGET_PER_PILLAR * len(subcaps_by_pillar), 2)
    out["within_budget"] = total_p <= out["run_budget_usd"]
    return out


def for_run(wb) -> dict:
    """This run's actual selection, priced."""
    by_pillar: dict[str, int] = {}
    for cell in wb.selected_subcaps():
        by_pillar[str(cell).split("C")[0]] = by_pillar.get(
            str(cell).split("C")[0], 0) + 1
    est = pillar_estimate(by_pillar)
    est["run_id"] = wb.metadata().get("run_id")
    est["entity"] = wb.metadata().get("entity_name")
    return est


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.cost",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("model", help="the rate card, the baseline and the levers")
    e = sub.add_parser("estimate")
    e.add_argument("--subcaps", type=int)
    e.add_argument("--sv", default="CU"); e.add_argument("--scope",
                                                         default="T1_CORE")
    e.add_argument("--json", action="store_true")
    b = sub.add_parser("budget")
    b.add_argument("--run", required=True); b.add_argument("--root")
    b.add_argument("--json", action="store_true")
    t = sub.add_parser("schedule", help="wall clock, given the fan-out")
    t.add_argument("--sv", default="CU"); t.add_argument("--scope",
                                                         default="T1_CORE")
    t.add_argument("--lanes", type=int, default=PARALLEL_LANES)
    t.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "model":
        base = measured_baseline()
        print(f"RATE CARD ($/1M tokens)")
        for m, r in RATES.items():
            print(f"  {m:<7} in {r['in']:>5.2f}  out {r['out']:>6.2f}  "
                  f"cache-read {r['in'] * CACHE_READ_MULT:.2f}  "
                  f"cache-write {r['in'] * CACHE_WRITE_MULT:.2f}")
        print(f"\nMEASURED BASELINE — {base['label']}")
        print(f"  {base['subcaps']} subcaps, {base['turns']} turns, "
              f"{base['model']}: ${base['total_usd']:.2f}")
        for k, v in base["parts_usd"].items():
            print(f"    {k:<16} ${v:>6.2f}  {base['share'][k] * 100:>4.0f}%")
        print(f"  ${base['usd_per_subcap']:.3f}/subcap · "
              f"${base['usd_per_turn']:.4f}/turn · "
              f"{base['context_per_turn_tokens'] // 1000}K context re-read "
              f"per turn")
        print(f"\n  Cache reads are {base['share']['cache_read'] * 100:.0f}% "
              f"of the bill. Cost = turns x context, so only levers that cut "
              f"turns or context matter.")
        print(f"\nLEVERS (budget: ${BUDGET_PER_PILLAR:.2f}/pillar)")
        for l in LEVERS:
            print(f"\n  {l['id']}  x{l['factor']}")
            print(f"    {l['what']}")
            print(f"    why      {l['why']}")
            print(f"    evidence {l['evidence']}")
            print(f"    cost     {l['cost']}")
        p = projected()
        print(f"\n  combined x{p['combined_factor']} "
              f"({p['reduction_x']}x reduction) -> "
              f"${p['usd_per_subcap']:.4f}/subcap")
        return 0

    if a.cmd == "schedule":
        tax = C.taxonomy()
        cells = tax.selected(a.sv, a.scope)
        caps = len({".".join(str(c).split(".")[:2]) for c in cells})
        sch = schedule(len(cells), caps, a.lanes)
        if a.json:
            print(json.dumps(sch, indent=2))
            return 0 if sch["within_target"] else 1
        print(f"{sch['subcaps']} cells in {sch['capability_passes']} "
              f"capability passes, {sch['lanes']} parallel lanes\n")
        for phase, mins in sch["phases_min"].items():
            print(f"  {mins:>6.1f} min  {phase}")
        print(f"  {'-' * 6}")
        print(f"  {sch['total_min']:>6.1f} min  TOTAL  "
              f"(target {sch['target_min']}, headroom "
              f"{sch['headroom_min']:.0f} min)")
        print(f"\n  research alone would be {sch['research_serial_min']:.0f} "
              f"min serial; {sch['lanes']} lanes make it "
              f"{sch['research_parallel_min']:.0f}.")
        return 0 if sch["within_target"] else 1

    if a.cmd == "estimate":
        if a.subcaps:
            by = {"P1": a.subcaps}
        else:
            tax = C.taxonomy()
            by = {}
            for cell in tax.selected(a.sv, a.scope):
                by[str(cell).split("C")[0]] = by.get(
                    str(cell).split("C")[0], 0) + 1
        est = pillar_estimate(by)
    else:
        from . import runstate
        run = runstate.locate(a.run, Path(a.root) if a.root else None)
        est = for_run(run.open())

    if getattr(a, "json", False):
        print(json.dumps(est, indent=2))
        return 0 if est["within_budget"] else 1
    print(f"budget ${est['budget_per_pillar_usd']:.2f}/pillar · levers "
          f"{', '.join(est['levers'])} (x{est['combined_factor']})\n")
    print(f"  {'pillar':<8}{'cells':>7}{'measured':>12}{'levered':>10}  verdict")
    for pillar, row in est["pillars"].items():
        verdict = ("within budget" if row["within_budget"]
                   else f"OVER by ${row['over_by_usd']:.2f}")
        print(f"  {pillar:<8}{row['subcaps']:>7}"
              f"{row['measured_usd']:>11,.0f}${row['levered_usd']:>9,.2f}"
              f"  {verdict}")
    print(f"\n  run total: measured ${est['run_total_measured_usd']:,.0f} · "
          f"levered ${est['run_total_levered_usd']:,.2f} · "
          f"budget ${est['run_budget_usd']:.2f}")
    if not est["within_budget"]:
        print(f"  OVER BUDGET by "
              f"${est['run_total_levered_usd'] - est['run_budget_usd']:,.2f} "
              f"even with every lever applied — the scope, not the prompt, is "
              f"the remaining variable.")
    return 0 if est["within_budget"] else 1


if __name__ == "__main__":
    sys.exit(main())
