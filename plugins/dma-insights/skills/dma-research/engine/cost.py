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


#: A run's own measurements. `record` appends one JSON line per stage to
#: `<qa_dir>/cost_ledger.jsonl` and mirrors the totals into Run_Metadata
#: (`stage_timings`, `cost_summary`); `report` reads the ledger back against
#: the schedule and the budget; `report --as-baseline` writes
#: `cost_baseline.json`, which replaces the hand-typed MEASURED constant for
#: every projection (owner issue 9, 2026-09-03: "the assessment takes more
#: than six hours" — and nothing recorded where the hours went).
LEDGER_NAME = "cost_ledger.jsonl"
BASELINE_NAME = "cost_baseline.json"
BASELINE_ENV = "DMA_COST_BASELINE"

#: The stages the driver records, in order, and the schedule phase each one
#: is measured against (None: not in the schedule's phase table).
STAGE_PHASE = {
    "PREFLIGHT": "preflight (financials, census, the question)",
    "START": None,
    "PRELIM": "PRELIM (profile, timeline, peers, tech baseline)",
    "KG": None,
    "RESEARCH": "category research (16 lanes, in parallel)",
    "CHALLENGE": "gates + independent challenge",
    "GATES": "gates + independent challenge",
    "HANDOFF": None,
    "SCORING": None,
    "INGEST_A": None,
    "REPORTS": "report sections (2 producers, in parallel) + review",
    "PAGES_A": None,
    "PACKAGE": "assemble, verify, push",
    "INGEST_B": None,
    "PAGES_B": None,
    "PROMOTE": None,
}


def _baseline_file(path=None):
    import os
    p = path or os.environ.get(BASELINE_ENV)
    return Path(p) if p else None


def measured_baseline(baseline_path=None) -> dict:
    """The baseline every projection starts from: a RECORDED one when the
    caller (or $DMA_COST_BASELINE) names a `cost_baseline.json`, else the
    hand-typed MEASURED constant — and the answer says which."""
    m = dict(MEASURED)
    src = "constant"
    bp = _baseline_file(baseline_path)
    if bp is not None and bp.is_file():
        try:
            rec = json.loads(bp.read_text())
            need = ("model", "subcaps", "turns", "cache_read", "cache_write",
                    "uncached", "output", "wall_clock_min")
            if all(k in rec for k in need) and rec["subcaps"] and rec["turns"]:
                m.update({k: rec[k] for k in need})
                m["label"] = rec.get("label") or f"recorded baseline {bp.name}"
                src = str(bp)
        except (ValueError, OSError):
            pass
    c = cost_of(cache_read=m["cache_read"], cache_write=m["cache_write"],
                uncached=m["uncached"], output=m["output"], model=m["model"])
    c.update({
        "label": m["label"], "subcaps": m["subcaps"], "turns": m["turns"],
        "usd_per_subcap": round(c["total_usd"] / m["subcaps"], 4),
        "usd_per_turn": round(c["total_usd"] / m["turns"], 5),
        "context_per_turn_tokens": round(m["cache_read"] / m["turns"]),
        "minutes_per_subcap": round(m["wall_clock_min"] / m["subcaps"], 2),
        "source": src,
    })
    return c


# ── the ledger: what THIS run spent, stage by stage ──────────────────────

def _ledger_path(run) -> Path:
    return Path(run.qa_dir) / LEDGER_NAME


def ledger(run) -> list[dict]:
    p = _ledger_path(run)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _parse_ts(v):
    if not v:
        return None
    try:
        return _dt.datetime.strptime(str(v), "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


def record(run, *, stage: str, elapsed_s: float | None = None,
           started_at: str | None = None, ended_at: str | None = None,
           usd: float | None = None, turns: int | None = None,
           tokens: dict | None = None, model: str | None = None,
           lanes: int | None = None, attempts: int | None = None,
           note: str = "", wb=None) -> dict:
    """Append one stage record and mirror the totals into Run_Metadata.

    Refuses a record with no duration at all (a timing that cannot be added
    is not a timing) and an unknown stage name only loudly, as a note — a
    driver that grows a stage must not be refused by its cost ledger."""
    stage = str(stage or "").strip().upper()
    if not stage:
        raise ValueError("record needs --stage")
    a, b = _parse_ts(started_at), _parse_ts(ended_at)
    if elapsed_s is None and a and b:
        elapsed_s = (b - a).total_seconds()
    if elapsed_s is None:
        raise ValueError("record needs --elapsed-s, or --started-at AND "
                         "--ended-at (UTC, %Y-%m-%dT%H:%M:%SZ)")
    elapsed_s = float(elapsed_s)
    if elapsed_s < 0:
        raise ValueError(f"elapsed {elapsed_s}s is negative")
    tokens = dict(tokens or {})
    if usd is None and tokens:
        usd = cost_of(cache_read=int(tokens.get("cache_read") or 0),
                      cache_write=int(tokens.get("cache_write") or 0),
                      uncached=int(tokens.get("uncached") or 0),
                      output=int(tokens.get("output") or 0),
                      model=model or "sonnet")["total_usd"]
    rec = {
        "recorded_at": _utcnow(), "stage": stage,
        "started_at": started_at, "ended_at": ended_at,
        "elapsed_s": round(elapsed_s, 1),
        "usd": (round(float(usd), 4) if usd is not None else None),
        "turns": turns, "tokens": tokens or None, "model": model,
        "lanes": lanes, "attempts": attempts, "note": note or "",
        "known_stage": stage in STAGE_PHASE,
    }
    lp = _ledger_path(run)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    # Mirror into the workbook, so the run's own record carries its cost.
    try:
        wb = wb or run.open()
        rows = ledger(run)
        timings, summary = _totals(rows)
        wb.set_metadata("stage_timings", json.dumps(timings, sort_keys=True),
                        save=False)
        wb.set_metadata("cost_summary", json.dumps(summary, sort_keys=True))
    except Exception as e:                       # noqa: BLE001
        rec["metadata_mirror"] = f"not written: {str(e)[:120]}"
    rec["ledger"] = str(lp)
    return rec


def _totals(rows: list[dict]) -> tuple[dict, dict]:
    timings: dict = {}
    usd_total = 0.0
    usd_known = False
    turns = 0
    for r in rows:
        st = r["stage"]
        t = timings.setdefault(st, {"elapsed_s": 0.0, "records": 0, "attempts": 0,
                                    "first_started_at": None, "last_ended_at": None})
        t["elapsed_s"] = round(t["elapsed_s"] + float(r.get("elapsed_s") or 0), 1)
        t["records"] += 1
        t["attempts"] += int(r.get("attempts") or 1)
        if r.get("started_at") and not t["first_started_at"]:
            t["first_started_at"] = r["started_at"]
        if r.get("ended_at"):
            t["last_ended_at"] = r["ended_at"]
        if r.get("usd") is not None:
            usd_total += float(r["usd"])
            usd_known = True
        turns += int(r.get("turns") or 0)
    summary = {"total_usd": (round(usd_total, 4) if usd_known else None),
               "total_elapsed_s": round(sum(t["elapsed_s"] for t in timings.values()), 1),
               "turns": turns, "stages": len(timings)}
    return timings, summary


def report(run, *, wb=None) -> dict:
    """Per-stage wall clock against the schedule, USD against the budget.
    `within` is False when either is over — and the CLI exits 1 on it."""
    wb = wb or run.open()
    rows = ledger(run)
    timings, summary = _totals(rows)
    sel = wb.selected_subcaps()
    caps = len({".".join(str(c).split(".")[:2]) for c in sel})
    pillars = sorted({str(c).split("C")[0] for c in sel})
    sch = schedule(len(sel), caps, PARALLEL_LANES)
    stages = []
    for st, t in timings.items():
        phase = STAGE_PHASE.get(st)
        planned = sch["phases_min"].get(phase) if phase else None
        actual = round(t["elapsed_s"] / 60.0, 1)
        stages.append({"stage": st, "actual_min": actual,
                       "planned_min": planned,
                       "over_by_min": (round(actual - planned, 1)
                                       if planned is not None and actual > planned
                                       else 0.0),
                       "attempts": t["attempts"], "records": t["records"]})
    total_min = round(summary["total_elapsed_s"] / 60.0, 1)
    budget = round(BUDGET_PER_PILLAR * max(1, len(pillars)), 2)
    usd = summary["total_usd"]
    over_time = total_min > TARGET_WALL_CLOCK_MIN
    over_budget = usd is not None and usd > budget
    return {
        "run_id": wb.metadata().get("run_id"), "ledger": str(_ledger_path(run)),
        "records": len(rows), "stages": stages,
        "total_min": total_min, "target_min": TARGET_WALL_CLOCK_MIN,
        "schedule_total_min": sch["total_min"],
        "total_usd": usd, "budget_usd": budget, "pillars": pillars,
        "over_wall_clock": over_time, "over_budget": over_budget,
        "within": not (over_time or over_budget),
        "unrecorded": [st for st in STAGE_PHASE if st not in timings],
        "note": ("USD is None when no stage carried tokens or a price — "
                 "wall clock alone is judged" if usd is None else ""),
    }


def as_baseline(run, *, label: str | None = None, wb=None) -> dict:
    """Write this run's measurements in MEASURED's shape to
    `<qa_dir>/cost_baseline.json`, so `measured_baseline` can read a real
    run instead of the 2026-08-29 constant. Refuses a ledger with no tokens
    or no turns: a baseline with nothing measured in it is the constant
    under another name."""
    wb = wb or run.open()
    rows = ledger(run)
    tok = {"cache_read": 0, "cache_write": 0, "uncached": 0, "output": 0}
    turns = 0
    model = None
    for r in rows:
        for k in tok:
            tok[k] += int((r.get("tokens") or {}).get(k) or 0)
        turns += int(r.get("turns") or 0)
        model = model or r.get("model")
    if not turns or not any(tok.values()):
        raise ValueError(
            "the ledger carries no turns or no tokens — record stages with "
            "--turns and --tokens (agent_run.py --record-run does) before "
            "calling this a baseline")
    _t, summary = _totals(rows)
    rec = {
        "label": label or f"{wb.metadata().get('entity_name')} {wb.metadata().get('run_id')}, "
                          f"{_utcnow()[:10]}",
        "model": model or "sonnet", "subcaps": len(wb.selected_subcaps()),
        "turns": turns, **tok,
        "wall_clock_min": round(summary["total_elapsed_s"] / 60.0, 1),
        "total_usd": summary["total_usd"], "recorded_at": _utcnow(),
    }
    out = Path(run.qa_dir) / BASELINE_NAME
    out.write_text(json.dumps(rec, indent=2))
    rec["written_to"] = str(out)
    rec["use"] = f"export {BASELINE_ENV}={out}  # every projection then starts here"
    return rec


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
    t.add_argument("--run", help="phases from a RUN's own selection, not the taxonomy")
    t.add_argument("--root")
    t.add_argument("--json", action="store_true")
    rc = sub.add_parser("record", help="append one stage's wall clock / cost to the run")
    rc.add_argument("--run", required=True); rc.add_argument("--root")
    rc.add_argument("--stage", required=True)
    rc.add_argument("--elapsed-s", type=float)
    rc.add_argument("--started-at"); rc.add_argument("--ended-at")
    rc.add_argument("--usd", type=float); rc.add_argument("--turns", type=int)
    rc.add_argument("--tokens", help='JSON {"cache_read":…,"cache_write":…,"uncached":…,"output":…}')
    rc.add_argument("--model"); rc.add_argument("--lanes", type=int)
    rc.add_argument("--attempts", type=int); rc.add_argument("--note", default="")
    rp = sub.add_parser("report", help="per-stage wall clock vs schedule, USD vs budget")
    rp.add_argument("--run", required=True); rp.add_argument("--root")
    rp.add_argument("--json", action="store_true")
    rp.add_argument("--as-baseline", action="store_true",
                    help="also write cost_baseline.json from this run's ledger")
    rp.add_argument("--label")

    a = ap.parse_args(argv)
    if a.cmd == "record":
        from . import runstate
        run = runstate.locate(a.run, Path(a.root) if a.root else None)
        try:
            rec = record(run, stage=a.stage, elapsed_s=a.elapsed_s,
                         started_at=a.started_at, ended_at=a.ended_at, usd=a.usd,
                         turns=a.turns, tokens=json.loads(a.tokens) if a.tokens else None,
                         model=a.model, lanes=a.lanes, attempts=a.attempts, note=a.note)
        except (ValueError, TypeError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        print(json.dumps(rec, indent=2))
        return 0
    if a.cmd == "report":
        from . import runstate
        run = runstate.locate(a.run, Path(a.root) if a.root else None)
        wb = run.open()
        rep = report(run, wb=wb)
        if a.as_baseline:
            try:
                rep["baseline"] = as_baseline(run, label=a.label, wb=wb)
            except ValueError as e:
                print(f"REFUSED: {e}", file=sys.stderr)
                return 1
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            print(f"run {rep['run_id']} · {rep['records']} record(s) in {rep['ledger']}\n")
            print(f"  {'stage':<12}{'actual':>9}{'planned':>9}  over")
            for st in rep["stages"]:
                pl = f"{st['planned_min']:.1f}" if st["planned_min"] is not None else "—"
                over = f"+{st['over_by_min']:.1f}" if st["over_by_min"] else ""
                print(f"  {st['stage']:<12}{st['actual_min']:>8.1f}m{pl:>9}  {over}"
                      + (f"  ({st['attempts']} attempts)" if st["attempts"] > st["records"] else ""))
            print(f"\n  wall clock {rep['total_min']:.1f} min (target {rep['target_min']}, "
                  f"schedule {rep['schedule_total_min']})"
                  + ("  OVER" if rep["over_wall_clock"] else ""))
            usd = rep["total_usd"]
            print(f"  cost       {('$%.2f' % usd) if usd is not None else 'not priced'} "
                  f"(budget ${rep['budget_usd']:.2f} for {len(rep['pillars'])} pillar(s))"
                  + ("  OVER" if rep["over_budget"] else ""))
            if rep["unrecorded"]:
                print(f"  unrecorded stages: {', '.join(rep['unrecorded'])}")
            if rep.get("baseline"):
                print(f"\n  baseline written: {rep['baseline']['written_to']}\n"
                      f"  {rep['baseline']['use']}")
        return 0 if rep["within"] else 1
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
        if a.run:
            from . import runstate
            run = runstate.locate(a.run, Path(a.root) if a.root else None)
            cells = run.open().selected_subcaps()
        else:
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
