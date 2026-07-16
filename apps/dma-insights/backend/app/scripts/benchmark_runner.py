"""One-command benchmark snapshot for the enhancement run.

Aggregates every pack-measurable quality gate into a single machine-readable
snapshot so the fix -> regen -> re-measure loop has one instrument:

  * ``qa_startup_audit`` counters (each carries its own contract target,
    direction, owner script);
  * ``pack_quality_gate`` S1-S14 segment violation counts;
  * ``countercheck_pack`` defect classes + per-segment scorecard vs the
    gold-standard overlays;
  * shipped ML model metrics (``app/ml/models/*.meta.json``);
  * optional extras registered by later phases (rubric100, mapping eval,
    refusal probes) via their own snapshot JSON files in ``benchmarks/raw``.

Enhancement targets (the ">50% past baseline" contract, see
``benchmarks/README.md``) are derived per metric class:

  * ``down`` (defect counts/rates)        -> baseline * 0.5
  * ``up`` bounded pct, baseline <= 66.6  -> baseline * 1.5
  * ``up`` bounded pct, baseline  > 66.6  -> baseline + (bound-baseline)/2
  * ``up`` fraction in [0,1]              -> same rules against bound 1.0
  * ``bool``                              -> 1 (absolute)

``targets.json`` may override any metric with a spec-absolute target
(misattribution < 2%, headline F1 >= 0.9, refusal >= 98%, untriggered = 0).

Usage:
    python -m app.scripts.benchmark_runner --out ../benchmarks/runs/run.json
    python -m app.scripts.benchmark_runner \
        --compare ../benchmarks/baselines/2026-07-11_baseline.json [--report md]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", ".."))
_APPROOT = os.path.normpath(os.path.join(_BACKEND, ".."))
DEFAULT_CLIENTS = os.path.join(_APPROOT, "startup-data", "clients")
DEFAULT_PACK = os.path.join(_APPROOT, "startup-data")
DEFAULT_OVERLAYS = os.path.join(_APPROOT, "startup-data", "refinement")
DEFAULT_BENCH = os.path.join(_APPROOT, "benchmarks")
_AUDIT_BASELINE = os.path.join(_BACKEND, "tests", "fixtures", "qa_baseline_2026-07-02.json")

_PACK_GATE_ROW = re.compile(r"^(S\d+[a-z_]*\w*)\s+(\d+)\s+(\d+)")


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"], cwd=_BACKEND,
            capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _environment() -> dict:
    env = {
        "db": bool(os.environ.get("DATABASE_URL")),
        "vertex": not os.environ.get("DMA_DISABLE_VERTEX") and bool(os.environ.get("VERTEX_PROJECT_ID")),
    }
    try:
        from app.services.nlp import semantic
        env["st_models"] = bool(semantic.model_available())
    except Exception:
        env["st_models"] = False
    try:
        import sklearn
        env["sklearn"] = sklearn.__version__
    except Exception:
        env["sklearn"] = None
    return env


def _metric(value, *, unit, direction, owner, source, bound=None, requires_db=False):
    return {"value": value, "unit": unit, "direction": direction,
            "owner_script": owner, "source": source, "bound": bound,
            "requires_db": requires_db}


def collect_startup_audit(clients_dir: str) -> dict[str, dict]:
    """Run qa_startup_audit --json in-process-adjacent (subprocess keeps its
    argparse/main contract intact) and lift each counter into the snapshot."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.scripts.qa_startup_audit",
         "--clients-dir", clients_dir, "--json", "--baseline", _AUDIT_BASELINE],
        cwd=_BACKEND, capture_output=True, text=True, timeout=1800)
    out = proc.stdout
    # the audit prints JSON on stdout; tolerate leading log lines
    payload = json.loads(out[out.index("{"):])
    metrics: dict[str, dict] = {}
    for name, c in (payload.get("counters") or {}).items():
        unit = c.get("unit") or "count"
        # Contract counters state targets either as ceilings (defect counts,
        # direction down) or floors (coverage pct, direction up). The audit
        # JSON does not carry direction explicitly, so infer it from the
        # pass verdict: passing below target = ceiling; passing above =
        # floor; failing above target = ceiling; failing below = floor.
        value, target = c.get("value"), c.get("target")
        if unit == "bool":
            direction = "up"
        elif value is None or target is None or value == target:
            direction = "down" if unit in ("count", "clients", "events", "violations") else "up"
        else:
            passed = bool(c.get("pass"))
            below = value < target
            direction = "down" if (passed and below) or (not passed and not below) else "up"
        metrics[f"audit.{name}"] = _metric(
            value, unit=unit, direction=direction,
            owner=c.get("script") or "unknown", source="qa_startup_audit",
            bound=100.0 if unit == "pct" else (1.0 if unit == "bool" else None))
        metrics[f"audit.{name}"]["contract_target"] = target
        metrics[f"audit.{name}"]["contract_pass"] = bool(c.get("pass"))
        metrics[f"audit.{name}"]["severity"] = c.get("severity")
    return metrics


def collect_pack_gate(pack_dir: str) -> dict[str, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "app.scripts.pack_quality_gate",
         "--pack", pack_dir, "--audit"],
        cwd=_BACKEND, capture_output=True, text=True, timeout=1800)
    metrics: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        m = _PACK_GATE_ROW.match(line.strip())
        if not m:
            continue
        seg, violations, clients = m.group(1), int(m.group(2)), int(m.group(3))
        metrics[f"pack.{seg}"] = _metric(
            violations, unit="violations", direction="down",
            owner="pack_quality_gate", source="pack_quality_gate")
        metrics[f"pack.{seg}"]["clients"] = clients
        metrics[f"pack.{seg}"]["enforced"] = "ENFORCED FAIL" in line
    return metrics


def collect_countercheck(clients_dir: str, overlay_dir: str) -> dict[str, dict]:
    from app.scripts.countercheck_pack import scan
    result = scan(clients_dir, overlay_dir)
    metrics: dict[str, dict] = {}
    for defect, total in result["aggregate"].items():
        metrics[f"cc.{defect}"] = _metric(
            total, unit="defects", direction="down",
            owner="countercheck_pack", source="countercheck_pack")
        metrics[f"cc.{defect}"]["clients"] = len(result["clients_hit"].get(defect, []))
    metrics["cc.gate_pass"] = _metric(
        1.0 if result["gate_pass"] else 0.0, unit="bool", direction="up",
        owner="countercheck_pack", source="countercheck_pack", bound=1.0)
    overlays_missing = sum(1 for o in result["overlays"] if not o["in_pack"])
    metrics["cc.overlays_unmatched"] = _metric(
        overlays_missing, unit="count", direction="down",
        owner="grade_scorecard", source="countercheck_pack")
    return metrics


def collect_ml_meta() -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    models_dir = os.path.join(_BACKEND, "app", "ml", "models")
    if not os.path.isdir(models_dir):
        return metrics
    for fn in sorted(os.listdir(models_dir)):
        if not fn.endswith(".meta.json"):
            continue
        with open(os.path.join(models_dir, fn)) as fh:
            meta = json.load(fh)
        name = meta.get("name", fn.split("_v")[0])
        trainer = f"train_{name}"
        held = meta.get("heldout_no_stated") or {}
        cv = meta.get("cv") or {}
        if held.get("model_macro_f1") is not None:
            metrics[f"ml.{name}_heldout_macro_f1"] = _metric(
                held["model_macro_f1"], unit="f1", direction="up",
                owner=trainer, source=fn, bound=1.0)
        if held.get("model_acc") is not None:
            metrics[f"ml.{name}_heldout_acc"] = _metric(
                held["model_acc"], unit="acc", direction="up",
                owner=trainer, source=fn, bound=1.0)
        if cv.get("macro_f1") is not None:
            metrics[f"ml.{name}_cv_macro_f1"] = _metric(
                cv["macro_f1"], unit="f1", direction="up",
                owner=trainer, source=fn, bound=1.0)
        if cv.get("acc") is not None:
            metrics[f"ml.{name}_cv_acc"] = _metric(
                cv["acc"], unit="acc", direction="up",
                owner=trainer, source=fn, bound=1.0)
    return metrics


def collect_extras(bench_dir: str) -> dict[str, dict]:
    """Later phases (rubric100, mapping eval, refusal probes, enrichment
    discipline) drop {name: metric} JSON files into benchmarks/raw/extras;
    each metric must already follow the snapshot metric schema."""
    metrics: dict[str, dict] = {}
    extras_dir = os.path.join(bench_dir, "raw", "extras")
    if not os.path.isdir(extras_dir):
        return metrics
    for fn in sorted(os.listdir(extras_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(extras_dir, fn)) as fh:
                payload = json.load(fh)
            for name, m in payload.items():
                if isinstance(m, dict) and "value" in m:
                    metrics[name] = m
        except (json.JSONDecodeError, OSError):
            continue
    return metrics


def enhancement_target(baseline: float | None, direction: str,
                       unit: str, bound: float | None) -> float | None:
    """The >50%-past-baseline rule (see module docstring)."""
    if baseline is None:
        return None
    if unit == "bool":
        return 1.0
    if direction == "down":
        return round(baseline * 0.5, 4)
    top = bound if bound is not None else None
    if top is None:
        return round(baseline * 1.5, 4)
    if baseline <= top * (2.0 / 3.0):
        return round(min(baseline * 1.5, top), 4)
    return round(baseline + (top - baseline) * 0.5, 4)


def meets(value: float | None, target: float | None, direction: str) -> bool | None:
    if value is None or target is None:
        return None
    return value <= target if direction == "down" else value >= target


def snapshot(clients_dir: str, pack_dir: str, overlay_dir: str,
             bench_dir: str, kind: str) -> dict:
    metrics: dict[str, dict] = {}
    metrics.update(collect_startup_audit(clients_dir))
    metrics.update(collect_pack_gate(pack_dir))
    metrics.update(collect_countercheck(clients_dir, overlay_dir))
    metrics.update(collect_ml_meta())
    metrics.update(collect_extras(bench_dir))
    return {
        "run_id": f"{_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}_{_git_sha()}",
        "git_sha": _git_sha(),
        "kind": kind,
        "environment": _environment(),
        "corpus": {"clients": len([d for d in os.listdir(clients_dir)
                                   if os.path.isdir(os.path.join(clients_dir, d))])},
        "metrics": metrics,
    }


def load_overrides(bench_dir: str) -> dict:
    p = os.path.join(bench_dir, "targets.json")
    if not os.path.exists(p):
        return {}
    with open(p) as fh:
        return (json.load(fh)).get("overrides", {})


def compare(current: dict, baseline: dict, bench_dir: str, fmt: str) -> tuple[str, bool]:
    overrides = load_overrides(bench_dir)
    rows = []
    all_pass = True
    names = sorted(set(current["metrics"]) | set(baseline["metrics"]))
    for name in names:
        cur = current["metrics"].get(name, {})
        base = baseline["metrics"].get(name, {})
        bval, cval = base.get("value"), cur.get("value")
        direction = cur.get("direction") or base.get("direction") or "down"
        unit = cur.get("unit") or base.get("unit") or "count"
        bound = cur.get("bound") if cur.get("bound") is not None else base.get("bound")
        if name in overrides:
            tgt = overrides[name].get("target")
            rule = overrides[name].get("rule", "absolute")
        else:
            tgt = enhancement_target(bval, direction, unit, bound)
            rule = "halve" if direction == "down" else "1.5x/residual"
        ok = meets(cval, tgt, direction)
        # metrics with no baseline (net-new) pass only their absolute override
        if ok is False:
            all_pass = False
        rows.append({
            "metric": name, "owner": cur.get("owner_script") or base.get("owner_script"),
            "baseline": bval, "current": cval, "target": tgt, "rule": rule,
            "direction": direction, "pass": ok,
        })
    if fmt == "md":
        lines = ["| metric | owner | baseline | current | target | rule | pass |",
                 "|---|---|---|---|---|---|---|"]
        for r in rows:
            mark = {True: "PASS", False: "MISS", None: "n/a"}[r["pass"]]
            lines.append(f"| {r['metric']} | {r['owner']} | {r['baseline']} | "
                         f"{r['current']} | {r['target']} | {r['rule']} | {mark} |")
        return "\n".join(lines), all_pass
    if fmt == "by-script":
        by_owner: dict[str, list[dict]] = {}
        for r in rows:
            by_owner.setdefault(r["owner"] or "unknown", []).append(r)
        lines = ["# PER-SCRIPT SCORECARD — output quality vs gold-benchmark targets"]

        def _score(owner_rows):
            n_pass = sum(1 for r in owner_rows if r["pass"])
            n_all = sum(1 for r in owner_rows if r["pass"] is not None)
            return n_pass, n_all

        for owner in sorted(by_owner, key=lambda o: (_score(by_owner[o])[0]
                                                     / max(_score(by_owner[o])[1], 1))):
            owner_rows = by_owner[owner]
            n_pass, n_all = _score(owner_rows)
            verdict = ("AT/ABOVE TARGET" if n_all and n_pass == n_all
                       else f"{n_pass}/{n_all} metrics at target")
            lines.append(f"\n## {owner} — {verdict}")
            for r in sorted(owner_rows, key=lambda x: (x["pass"] is not False,
                                                       str(x["metric"]))):
                mark = {True: "pass", False: "MISS", None: "n/a "}[r["pass"]]
                lines.append(f"  [{mark}] {r['metric']:44} "
                             f"{r['baseline']} -> {r['current']}"
                             f"  (target {r['target']})")
        return "\n".join(lines), all_pass
    return json.dumps(rows, indent=2), all_pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="enhancement-run benchmark snapshot")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--pack", default=DEFAULT_PACK)
    ap.add_argument("--overlay-dir", default=DEFAULT_OVERLAYS)
    ap.add_argument("--bench-dir", default=DEFAULT_BENCH)
    ap.add_argument("--kind", default="iteration", choices=["baseline", "iteration"])
    ap.add_argument("--out", default=None, help="write snapshot JSON here")
    ap.add_argument("--compare", default=None, help="baseline snapshot to compare against")
    ap.add_argument("--report", default="json",
                    choices=["json", "md", "by-script"])
    ap.add_argument("--fail-on-miss", action="store_true")
    args = ap.parse_args(argv)

    snap = snapshot(args.clients_dir, args.pack, args.overlay_dir,
                    args.bench_dir, args.kind)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(snap, fh, indent=2)
        print(f"snapshot written: {args.out} ({len(snap['metrics'])} metrics)")
    if args.compare:
        with open(args.compare) as fh:
            base = json.load(fh)
        report, all_pass = compare(snap, base, args.bench_dir, args.report)
        print(report)
        print(f"\nOVERALL: {'ALL TARGETS MET' if all_pass else 'TARGETS OUTSTANDING'}")
        if args.fail_on_miss and not all_pass:
            return 1
    elif not args.out:
        print(json.dumps(snap, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
