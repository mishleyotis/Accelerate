"""Audit the enrichment firing ledger against the G1-G10 trigger contract.

Training Spec Tab 01 §1: every enrichment firing must carry a valid trigger
ground plus (query, engine, outcome); anything else is a defect. This gate
reads the JSONL firing log written by ``enrichment_triggers.log_firing`` and
asserts:

  1. 100% of firings carry a valid G1-G10 trigger, query, engine, outcome;
  2. zero ``defect_no_trigger`` outcomes (legacy-mode proceeds are counted
     separately and reported, not failed);
  3. dedup outcomes are reported.

``--selftest`` proves the pipeline end-to-end without Vertex credentials:
three synthetic firings (one per engine) round-trip through log + audit, and
the >=0.9-cosine dedup helper is exercised on identical vs disjoint text.

Exit 1 on any invalid firing or non-legacy defect; 0 otherwise (an empty or
missing log is 0 firings — a pass with a note).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from app.services.enrichment_triggers import (
    Trigger,
    TriggerFiring,
    default_log_path,
    is_duplicate,
    log_firing,
)

_VALID_TRIGGERS = {t.value for t in Trigger}
_DEDUP_MARKERS = ("dedup", "duplicate", "merged")


def audit(log_path: str) -> dict:
    firings = 0
    invalid: list[dict] = []
    defects = 0
    legacy = 0
    dedups = 0
    outcomes: dict[str, int] = {}
    if os.path.exists(log_path):
        with open(log_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    invalid.append({"raw": line[:120], "reason": "not json"})
                    continue
                outcome = str(row.get("outcome") or "")
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                if outcome == "defect_no_trigger":
                    if row.get("legacy"):
                        legacy += 1
                    else:
                        defects += 1
                    continue
                firings += 1
                if row.get("trigger") not in _VALID_TRIGGERS:
                    invalid.append({"row": row, "reason": "invalid trigger"})
                for key in ("query", "engine", "outcome"):
                    if not str(row.get(key) or "").strip():
                        invalid.append({"row": row, "reason": f"missing {key}"})
                if any(m in outcome.lower() for m in _DEDUP_MARKERS):
                    dedups += 1
    return {
        "log": log_path, "logged_firings": firings, "invalid": invalid,
        "defect_no_trigger": defects, "legacy_firings": legacy,
        "dedup_outcomes": dedups, "outcomes": outcomes,
        "pass": not invalid and defects == 0,
    }


def emit_extras(report: dict, bench_dir: str) -> None:
    path = os.path.join(bench_dir, "raw", "extras", "enrichment_discipline.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    base = {"unit": "count", "owner_script": "enrichment_runner",
            "source": "qa_enrichment_discipline", "bound": None,
            "requires_db": False}
    with open(path, "w") as fh:
        json.dump({
            "enrich.untriggered_firings": {
                "value": report["defect_no_trigger"] + len(report["invalid"]),
                "direction": "down", **base},
            "enrich.logged_firings": {
                "value": report["logged_firings"], "direction": "up", **base},
        }, fh, indent=2)


def selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "firings.jsonl")
        for trig, engine in ((Trigger.G8_NEW_RUN, "gemini"),
                             (Trigger.G6_AE_NOTE, "clay"),
                             (Trigger.G1_EMPTY_FIELD, "crawler")):
            log_firing(TriggerFiring(
                trigger=trig, query=f"selftest:{engine}", engine=engine,
                outcome="skipped_cold", ts="selftest"), jsonl_path=log)
        report = audit(log)
        assert report["logged_firings"] == 3, report
        assert report["pass"], report
        dup, score = is_duplicate(
            "The bank runs three production cores in parallel.",
            ["The bank runs three production cores in parallel."])
        assert dup and score >= 0.85, (dup, score)
        distinct, score2 = is_duplicate(
            "The bank runs three production cores in parallel.",
            ["Migration to a new mobile app improved member sentiment."])
        assert not distinct, (distinct, score2)
        print(f"selftest PASS: 3/3 firings valid; dedup identical={score:.3f} "
              f"disjoint={score2:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G1-G10 enrichment discipline gate")
    ap.add_argument("--log", default=None)
    ap.add_argument("--emit-extras", default=None,
                    help="benchmarks dir to drop extras metrics into")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    report = audit(args.log or default_log_path())
    if args.emit_extras:
        emit_extras(report, args.emit_extras)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"# ENRICHMENT DISCIPLINE — {report['log']}")
        print(f"  firings={report['logged_firings']} "
              f"defects={report['defect_no_trigger']} "
              f"legacy={report['legacy_firings']} "
              f"dedup_outcomes={report['dedup_outcomes']} "
              f"invalid={len(report['invalid'])}")
        print(f"  outcomes: {report['outcomes']}")
        print(f"  => {'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
