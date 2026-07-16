"""Per-script x all-94 coverage AUDIT — stdlib-first, no DB (mandate 2026-06-24).

Scans the committed `startup-data/clients/*/` snapshot against the
`qa_coverage_contract` and prints, per OWNING SCRIPT, a coverage line plus the
clients that fail each HARD check. This is the fast baseline tracker the user
asked for ("ensure all 94 report outputs are considered to refine each
individual script"): run it before a fix to see the defect spread, after a fix
to prove every one of the 94 is covered.

2026-07-02 QA-gates workstream (plan Part 0.3): the audit now loads ALL TEN
page files per client (overview, insights, heatmap, heatmap_pillar, platforms,
platforms_roadmap, context, health, techstack, runs) plus the per-client
scores JSON, `dashboard.json`/`scores.json`, and — when present — the new
`focus_areas.json` / `heatmap_value_chain.json` surfaces, and evaluates the
plan's global-acceptance COUNTERS (registered in `qa_coverage_contract.
COUNTERS`, each owned by a script and pinned to a numeric target).

Exit code: 1 if any HARD check has ≥1 defect (un-allowlisted) OR any HARD
counter misses its target; 0 otherwise. SOFT checks/counters are reported and
never fail.

`--baseline tests/fixtures/qa_baseline_2026-07-02.json` (pre-regen mode): the
committed pack still carries the OLD baseline data, so a HARD counter that
misses its target but is AT-OR-BETTER-THAN the recorded baseline is reported
as BASE (suppressed — baseline-known) instead of failing the gate. A counter
WORSE than its baseline, or failing with no recorded baseline, still fails.
Post-regen the gate runs WITHOUT --baseline and every counter must meet its
target outright. The full counter table always prints in both modes.

Usage:
  python -m app.scripts.qa_startup_audit [--clients-dir DIR] [--json] [--max N]
                                         [--baseline tests/fixtures/qa_baseline_2026-07-02.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter as TallyCounter
from collections import defaultdict

# Import works both as a module (-m app.scripts.qa_startup_audit) and directly.
try:
    from app.scripts import qa_coverage_contract as contract
except ImportError:  # pragma: no cover - direct-run fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.scripts import qa_coverage_contract as contract

CHECKS = contract.CHECKS

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "startup-data", "clients",
)


def _read_json(path: str) -> dict | list | None:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _load_bundle(cdir: str) -> dict:
    """Load every page surface for one client (all 10 + optional new surfaces).

    `bundle["_files"]` records per-surface load status ("ok" | "absent" |
    "error") so the surface-coverage counters can distinguish a missing new
    surface (tolerated pre-regen, counted) from a corrupt required one.
    """
    out: dict = {"_files": {}}
    for name in contract.PAGE_FILES + contract.OPTIONAL_PAGE_FILES:
        p = os.path.join(cdir, f"{name}.json")
        if not os.path.exists(p):
            out["_files"][name] = "absent"
            continue
        body = _read_json(p)
        if body is None:
            out["_files"][name] = "error"
            out[name] = {}
        else:
            out["_files"][name] = "ok"
            out[name] = body
    # per-client scores snapshot lives NEXT TO the client dir: clients/{id}.json
    top = _read_json(cdir + ".json")
    if isinstance(top, dict):
        out["client_scores"] = top
    return out


# ── counter aggregation ──────────────────────────────────────────────────────
def _merge(totals: dict, contrib: dict) -> None:
    for name, (num, den) in contrib.items():
        slot = totals.setdefault(name, [0.0, None])
        slot[0] += num
        if den is not None:
            slot[1] = (slot[1] or 0.0) + den


def counter_value(spec, num: float, den: float | None) -> float | None:
    """None → not applicable (no denominator population); treated as PASS."""
    if spec.unit == "pct":
        return None if not den else round(100.0 * num / den, 2)
    if spec.unit == "avg":
        return None if not den else round(num / den, 3)
    return num


def counter_target(spec, n_clients: int) -> float:
    return float(n_clients) if spec.target == contract.ALL_CLIENTS else float(spec.target)


def _meets(value: float, bound: float, direction: str) -> bool:
    return value <= bound if direction == "<=" else value >= bound


def _resolve_path(baseline: dict, path: str) -> float | None:
    node: object = baseline
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if isinstance(node, int | float) and not isinstance(node, bool) else None


def baseline_value(baseline: dict | None, spec) -> float | None:
    """Resolve the recorded baseline for a counter.

    Order: (1) `counters.{name}` — this instrument's own measurement of the
    committed pack, recorded when the counter landed; (2) the mapped dotted
    path into the original eight-audit baseline (same defect, sometimes a
    slightly different instrument — kept for cross-validation)."""
    if not baseline:
        return None
    direct = _resolve_path(baseline, f"counters.{spec.name}")
    if direct is not None:
        return direct
    return _resolve_path(baseline, spec.baseline_path) if spec.baseline_path else None


def counter_verdicts(totals: dict, n_clients: int,
                     baseline: dict | None = None) -> list[dict]:
    """Pure verdict computation for every registered counter.

    status ∈ pass | fail | baseline | na. `baseline` (suppressed) only when a
    baseline dict is supplied AND the value is at-or-better-than the recorded
    baseline. HARD `fail` verdicts gate the exit code.
    """
    out: list[dict] = []
    for spec in contract.COUNTERS:
        num, den = totals.get(spec.name, (0.0, None))
        value = counter_value(spec, num, den)
        target = counter_target(spec, n_clients)
        base = baseline_value(baseline, spec)
        if value is None:
            status = "na"
        elif _meets(value, target, spec.direction):
            status = "pass"
        elif baseline is not None and base is not None and _meets(value, base, spec.direction):
            status = "baseline"
        else:
            status = "fail"
        out.append({
            "name": spec.name, "script": spec.script, "severity": spec.severity,
            "unit": spec.unit, "value": value, "target": target,
            "direction": spec.direction, "baseline": base,
            "pass": status in ("pass", "na"),
            "suppressed": status == "baseline", "status": status,
        })
    return out


def audit(clients_dir: str, max_n: int | None = None) -> dict:
    dirs = sorted(
        d for d in (os.path.join(clients_dir, x) for x in os.listdir(clients_dir))
        if os.path.isdir(d)
    )
    if max_n:
        dirs = dirs[:max_n]

    # corpus-level inputs for parity/contamination/dashboard counters
    root = os.path.dirname(os.path.abspath(clients_dir))
    dashboard = _read_json(os.path.join(root, "dashboard.json")) or {}
    scores_doc = _read_json(os.path.join(root, "scores.json")) or {}
    scores_rows = {r.get("display_id"): r for r in (scores_doc.get("clients") or [])
                   if isinstance(r, dict)}
    dash_cards = {c.get("display_id"): c for c in (dashboard.get("entity_cards") or [])
                  if isinstance(c, dict)}
    names: dict[str, str] = {}
    for cdir in dirs:
        cid = os.path.basename(cdir)
        top = _read_json(cdir + ".json")
        nm = ((top or {}).get("identity") or {}).get("name")
        if nm:
            names[cid] = nm
    all_names = set(names.values())

    # per (script, field): {ok, defect, na, [defect_clients]}
    agg: dict = defaultdict(lambda: {"ok": 0, "defect": 0, "na": 0, "sev": "hard",
                                     "bad": []})
    totals: dict[str, list] = {}
    opp_signatures: TallyCounter = TallyCounter()
    counter_errors: list[str] = []
    for cdir in dirs:
        cid = os.path.basename(cdir)
        bundle = _load_bundle(cdir)
        bundle["scores_row"] = scores_rows.get(cid) or {}
        bundle["dashboard_card"] = dash_cards.get(cid) or {}
        for chk in CHECKS:
            key = (chk.script, chk.field)
            agg[key]["sev"] = chk.severity
            try:
                res = chk.fn(bundle)
            except Exception as e:  # a malformed client must not crash the audit
                res = False
                agg[key]["bad"].append(f"{cid}(ERR:{type(e).__name__})")
                agg[key]["defect"] += 1
                continue
            if res is True:
                agg[key]["ok"] += 1
            elif res is False:
                agg[key]["defect"] += 1
                agg[key]["bad"].append(cid)
            else:
                agg[key]["na"] += 1
        # Part 0.3 counters (one malformed client must not crash the audit)
        own = names.get(cid, "")
        try:
            _merge(totals, contract.collect_client_counters(
                bundle, entity_name=own, foreign_names=all_names - {own}))
            for card in (bundle.get("platforms") or {}).get("cards") or []:
                sig = contract.opportunity_signature(card.get("opportunity_md"))
                if sig:
                    opp_signatures[sig] += 1
        except Exception as e:
            counter_errors.append(f"{cid}(ERR:{type(e).__name__}:{e})")

    # corpus-level counters
    _merge(totals, contract.collect_dashboard_counters(dashboard, len(dirs)))
    total_opps = float(sum(opp_signatures.values()))
    dominant = float(opp_signatures.most_common(1)[0][1]) if opp_signatures else 0.0
    totals["opportunity_md_dominant_skeleton_pct"] = [dominant, total_opps or None]

    return {"n": len(dirs), "agg": agg, "totals": totals,
            "counter_errors": counter_errors}


def _print_counter_table(verdicts: list[dict], n: int, show_baseline: bool) -> None:
    print(f"\n# Part 0.3 acceptance counters — {n} clients "
          "(HARD gate; BASE = baseline-known, suppressed)\n")
    width = max(len(v["name"]) for v in verdicts) + 1
    hdr = f"   {'counter':{width}} {'value':>10} {'target':>9} "
    hdr += f"{'baseline':>9} " if show_baseline else ""
    hdr += "status  owner"
    print(hdr)
    for v in verdicts:
        val = "—" if v["value"] is None else f"{v['value']:g}"
        tgt = f"{v['direction']}{v['target']:g}"
        status = {"pass": "ok", "na": "n/a", "baseline": "BASE",
                  "fail": "✗FAIL" if v["severity"] == "hard" else "⚠warn"}[v["status"]]
        line = f"   {v['name']:{width}} {val:>10} {tgt:>9} "
        if show_baseline:
            base = "—" if v["baseline"] is None else f"{v['baseline']:g}"
            line += f"{base:>9} "
        line += f"{status:6}  {v['script']}"
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients-dir", default=os.path.normpath(_DEFAULT_DIR))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--show", type=int, default=8, help="max defect clients to list")
    ap.add_argument("--baseline", default=None,
                    help="baseline audit JSON (e.g. tests/fixtures/qa_baseline_2026-07-02.json); "
                         "suppresses HARD counter failures at-or-better-than the recorded baseline")
    args = ap.parse_args()

    if not os.path.isdir(args.clients_dir):
        print(f"ERROR: clients dir not found: {args.clients_dir}", file=sys.stderr)
        return 2
    baseline = None
    if args.baseline:
        baseline = _read_json(args.baseline)
        if baseline is None:
            print(f"ERROR: baseline file unreadable: {args.baseline}", file=sys.stderr)
            return 2
    rep = audit(args.clients_dir, args.max)
    n = rep["n"]
    agg = rep["agg"]
    verdicts = counter_verdicts(rep["totals"], n, baseline)
    counter_hard_fails = [v for v in verdicts
                          if v["status"] == "fail" and v["severity"] == "hard"]

    if args.json:
        out = {f"{s}::{f}": {k: v for k, v in d.items() if k != "bad"}
               for (s, f), d in agg.items()}
        counters = {v["name"]: {k: v[k] for k in
                                ("value", "target", "pass", "status", "severity",
                                 "unit", "script", "baseline", "suppressed")}
                    for v in verdicts}
        print(json.dumps({"n": n, "checks": out, "counters": counters,
                          "counter_errors": rep["counter_errors"]}, indent=2))
        hard_fail = any(d["sev"] == "hard" and d["defect"] for d in agg.values())
        return 1 if (hard_fail or counter_hard_fails) else 0

    # grouped by owning script
    by_script: dict = defaultdict(list)
    for (script, field), d in agg.items():
        by_script[script].append((field, d))

    hard_defects = 0
    print(f"\n# qa_startup_audit — {n} clients · per-script coverage\n")
    for script in sorted(by_script):
        print(f"━━ {script} " + "━" * (54 - len(script)))
        for field, d in by_script[script]:
            tag = "HARD" if d["sev"] == "hard" else "soft"
            denom = d["ok"] + d["defect"]
            cov = f"{d['ok']}/{denom}" if denom else "—"
            flag = ""
            if d["sev"] == "hard" and d["defect"]:
                hard_defects += d["defect"]
                flag = "  ✗ FAIL"
            elif d["defect"]:
                flag = "  ⚠ warn"
            na = f" (na {d['na']})" if d["na"] else ""
            print(f"   [{tag}] {field:32} {cov:>8}{na}{flag}")
            if d["bad"]:
                shown = ", ".join(d["bad"][: args.show])
                more = f" +{len(d['bad']) - args.show} more" if len(d["bad"]) > args.show else ""
                print(f"          ↳ {shown}{more}")
        print()

    _print_counter_table(verdicts, n, show_baseline=baseline is not None)
    for err in rep["counter_errors"][:10]:
        print(f"   COUNTER_ERR {err}")
    suppressed = sum(1 for v in verdicts
                     if v["status"] == "baseline" and v["severity"] == "hard")
    if suppressed:
        print(f"\n   {suppressed} HARD counter(s) suppressed as baseline-known "
              "(pre-regen mode; post-regen run drops --baseline)")

    status = "FAIL" if (hard_defects or counter_hard_fails) else "PASS"
    print(f"\n# RESULT: {status} — {hard_defects} hard-check defect(s), "
          f"{len(counter_hard_fails)} hard counter miss(es) across {n} clients")
    for v in counter_hard_fails[:20]:
        print(f"   COUNTER FAIL {v['name']} value={v['value']} target="
              f"{v['direction']}{v['target']} baseline={v['baseline']} owner={v['script']}")
    return 1 if (hard_defects or counter_hard_fails) else 0


if __name__ == "__main__":
    raise SystemExit(main())
