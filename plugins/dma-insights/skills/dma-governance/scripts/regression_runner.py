#!/usr/bin/env python3
"""
DMA Regression Runner — Golden case comparison for Workflow C.

Compares actual assessment output against golden case expected outcomes.
Tests score tolerances, cap triggering, contradiction resolution, and
proof structure compliance.

Produces:
  - regression_results.json  (per-case comparison with PASS/FAIL)

Usage:
  python regression_runner.py <assessment_dir> <golden_case.json> [--output-dir <dir>]
  python regression_runner.py <assessment_dir> --all-cases [--output-dir <dir>]
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

GOLDEN_CASES_DIR = Path(__file__).parent.parent / "templates" / "golden_cases"

PILLAR_NAMES = ["P1", "P2", "P3", "P4"]

# Tolerance thresholds from regression_suite.md
TOLERANCES = {
    "subcap": 0.5,
    "capability": 0.35,
    "category": 0.25,
    "pillar": 0.20,
    "overall": 0.15,
}


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def load_golden_case(path):
    """Load and validate a golden case JSON file."""
    with open(path) as f:
        case = json.load(f)
    required = ["case_id", "case_name"]
    for k in required:
        if k not in case:
            raise ValueError(f"Golden case missing required field: {k}")
    return case


def load_manifest(assessment_dir):
    """Load run_manifest.json from assessment directory."""
    p = Path(assessment_dir) / "run_manifest.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def load_caps_log(assessment_dir):
    """Load caps_applied_log.csv from assessment directory."""
    p = Path(assessment_dir) / "caps_applied_log.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_contradiction_log(assessment_dir):
    """Load contradiction_log.csv from assessment directory."""
    p = Path(assessment_dir) / "contradiction_log.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Comparison Engine
# ---------------------------------------------------------------------------

def compare_scores(actual_manifest, golden_case):
    """Compare actual assessment scores against golden case expected values."""
    results = []

    # Overall score comparison
    expected = golden_case.get("expected_scores", {})
    actual_overall = safe_float(actual_manifest.get("overall_score"))

    if "overall" in expected:
        exp = expected["overall"]
        if isinstance(exp, dict):
            exp_val = safe_float(exp.get("expected", exp.get("value")))
            tolerance = safe_float(exp.get("tolerance", TOLERANCES["overall"]))
            exp_min = safe_float(exp.get("min", exp_val - tolerance))
            exp_max = safe_float(exp.get("max", exp_val + tolerance))
        else:
            exp_val = safe_float(exp)
            exp_min = exp_val - TOLERANCES["overall"]
            exp_max = exp_val + TOLERANCES["overall"]

        delta = abs(actual_overall - exp_val)
        in_range = exp_min <= actual_overall <= exp_max

        results.append({
            "check": "overall_score",
            "level": "overall",
            "expected": exp_val,
            "expected_range": [round(exp_min, 2), round(exp_max, 2)],
            "actual": actual_overall,
            "delta": round(delta, 3),
            "in_tolerance": in_range,
            "status": "PASS" if in_range else "FAIL",
        })

    # Pillar score comparisons
    actual_pillars = actual_manifest.get("pillar_scores", {})
    expected_pillars = expected.get("pillars", {})
    for pillar in PILLAR_NAMES:
        if pillar in expected_pillars:
            exp_p = expected_pillars[pillar]
            if isinstance(exp_p, dict):
                exp_val = safe_float(exp_p.get("expected", exp_p.get("value")))
                tolerance = safe_float(exp_p.get("tolerance", TOLERANCES["pillar"]))
            else:
                exp_val = safe_float(exp_p)
                tolerance = TOLERANCES["pillar"]

            actual_val = safe_float(actual_pillars.get(pillar))
            delta = abs(actual_val - exp_val)

            results.append({
                "check": f"{pillar}_score",
                "level": "pillar",
                "expected": exp_val,
                "expected_range": [round(exp_val - tolerance, 2), round(exp_val + tolerance, 2)],
                "actual": actual_val,
                "delta": round(delta, 3),
                "in_tolerance": delta <= tolerance,
                "status": "PASS" if delta <= tolerance else "FAIL",
            })

    # Category score comparisons
    actual_cats = actual_manifest.get("category_scores",
                  actual_manifest.get("scores", {}).get("categories", {}))
    expected_cats = expected.get("categories", {})
    for cat_id, exp_c in expected_cats.items():
        if isinstance(exp_c, dict):
            exp_val = safe_float(exp_c.get("expected", exp_c.get("value")))
            tolerance = safe_float(exp_c.get("tolerance", TOLERANCES["category"]))
        else:
            exp_val = safe_float(exp_c)
            tolerance = TOLERANCES["category"]

        actual_val = safe_float(actual_cats.get(cat_id))
        delta = abs(actual_val - exp_val)

        results.append({
            "check": f"{cat_id}_score",
            "level": "category",
            "expected": exp_val,
            "expected_range": [round(exp_val - tolerance, 2), round(exp_val + tolerance, 2)],
            "actual": actual_val,
            "delta": round(delta, 3),
            "in_tolerance": delta <= tolerance,
            "status": "PASS" if delta <= tolerance else "FAIL",
        })

    return results


def check_cap_triggers(caps_log, golden_case):
    """Verify expected caps triggered correctly."""
    results = []

    expected_caps = golden_case.get("expected_caps", [])
    if not expected_caps:
        return results

    actual_cap_types = defaultdict(list)
    for row in caps_log:
        ct = row.get("cap_type", row.get("Cap_Type", ""))
        affected = row.get("affected_subcap_id", row.get("Affected_SubCap_ID",
                   row.get("subcap_id", "")))
        actual_cap_types[ct].append(affected)

    for exp_cap in expected_caps:
        cap_type = exp_cap.get("cap_type", "")
        should_trigger = exp_cap.get("should_trigger", True)
        affected_id = exp_cap.get("affected_subcap_id", "")

        if should_trigger:
            triggered = cap_type in actual_cap_types
            if affected_id:
                triggered = affected_id in actual_cap_types.get(cap_type, [])
            results.append({
                "check": f"cap_trigger_{cap_type}",
                "expected": f"TRIGGERED on {affected_id or 'any'}",
                "actual": "TRIGGERED" if triggered else "NOT_TRIGGERED",
                "status": "PASS" if triggered else "FAIL",
                "details": exp_cap.get("description", ""),
            })
        else:
            not_triggered = cap_type not in actual_cap_types
            if affected_id:
                not_triggered = affected_id not in actual_cap_types.get(cap_type, [])
            results.append({
                "check": f"cap_no_trigger_{cap_type}",
                "expected": f"NOT_TRIGGERED on {affected_id or 'any'}",
                "actual": "NOT_TRIGGERED" if not_triggered else "TRIGGERED",
                "status": "PASS" if not_triggered else "FAIL",
                "details": exp_cap.get("description", ""),
            })

    return results


def check_contradiction_resolution(contradiction_log, golden_case):
    """Verify contradiction resolution outcomes match expectations."""
    results = []

    expected_contradictions = golden_case.get("expected_contradictions", [])
    if not expected_contradictions:
        return results

    actual_resolutions = {}
    for row in contradiction_log:
        cid = row.get("contradiction_id", row.get("Contradiction_ID", ""))
        rule = row.get("resolution_rule", row.get("Resolution_Rule", ""))
        winner = row.get("winner", row.get("Winner", ""))
        actual_resolutions[cid] = {"rule": rule, "winner": winner}

    for exp in expected_contradictions:
        cid = exp.get("contradiction_id", "")
        exp_rule = exp.get("expected_resolution_rule", "")
        exp_winner = exp.get("expected_winner", "")

        actual = actual_resolutions.get(cid, {})
        rule_match = not exp_rule or actual.get("rule", "").upper() == exp_rule.upper()
        winner_match = not exp_winner or actual.get("winner", "").upper() == exp_winner.upper()

        results.append({
            "check": f"contradiction_{cid}",
            "expected_rule": exp_rule,
            "expected_winner": exp_winner,
            "actual_rule": actual.get("rule", "NOT_FOUND"),
            "actual_winner": actual.get("winner", "NOT_FOUND"),
            "rule_match": rule_match,
            "winner_match": winner_match,
            "status": "PASS" if (rule_match and winner_match) else "FAIL",
        })

    return results


def check_structural_invariants(actual_manifest, golden_case):
    """Verify structural invariants that must always hold."""
    results = []

    invariants = golden_case.get("structural_invariants", [])
    for inv in invariants:
        inv_type = inv.get("type", "")
        description = inv.get("description", "")

        if inv_type == "evidence_count_minimum":
            actual_count = int(actual_manifest.get("evidence_count", 0))
            min_count = int(inv.get("minimum", 0))
            results.append({
                "check": f"invariant_{inv_type}",
                "description": description,
                "expected": f"≥{min_count}",
                "actual": actual_count,
                "status": "PASS" if actual_count >= min_count else "FAIL",
            })

        elif inv_type == "no_score_above":
            max_score = safe_float(inv.get("max_score", 5.0))
            actual_overall = safe_float(actual_manifest.get("overall_score"))
            results.append({
                "check": f"invariant_{inv_type}",
                "description": description,
                "expected": f"≤{max_score}",
                "actual": actual_overall,
                "status": "PASS" if actual_overall <= max_score else "FAIL",
            })

        elif inv_type == "pillar_ordering":
            order = inv.get("expected_order", [])
            actual_pillars = actual_manifest.get("pillar_scores", {})
            actual_vals = [safe_float(actual_pillars.get(p)) for p in order]
            is_ordered = all(actual_vals[i] >= actual_vals[i + 1]
                            for i in range(len(actual_vals) - 1))
            results.append({
                "check": f"invariant_{inv_type}",
                "description": description,
                "expected_order": order,
                "actual_values": actual_vals,
                "status": "PASS" if is_ordered else "FAIL",
            })

    return results


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_single_case(assessment_dir, golden_case_path, output_dir=None):
    """Run regression comparison for a single golden case."""
    golden = load_golden_case(golden_case_path)
    manifest = load_manifest(assessment_dir)

    if not manifest:
        return {
            "case_id": golden.get("case_id"),
            "case_name": golden.get("case_name"),
            "status": "ERROR",
            "error": "run_manifest.json not found in assessment directory",
        }

    # Check if this is a stub case
    if golden.get("case_status") == "STUB":
        return {
            "case_id": golden.get("case_id"),
            "case_name": golden.get("case_name"),
            "status": "SKIPPED",
            "reason": "Golden case is a STUB — evidence inventory not yet curated",
        }

    caps_log = load_caps_log(assessment_dir)
    contradiction_log = load_contradiction_log(assessment_dir)

    # Run all comparisons
    score_results = compare_scores(manifest, golden)
    cap_results = check_cap_triggers(caps_log, golden)
    contradiction_results = check_contradiction_resolution(contradiction_log, golden)
    invariant_results = check_structural_invariants(manifest, golden)

    all_checks = score_results + cap_results + contradiction_results + invariant_results
    passes = sum(1 for c in all_checks if c.get("status") == "PASS")
    fails = sum(1 for c in all_checks if c.get("status") == "FAIL")

    case_verdict = "PASS" if fails == 0 else "FAIL"

    result = {
        "case_id": golden.get("case_id"),
        "case_name": golden.get("case_name"),
        "case_description": golden.get("description", ""),
        "case_status": golden.get("case_status", "ACTIVE"),
        "status": case_verdict,
        "checks_run": len(all_checks),
        "checks_passed": passes,
        "checks_failed": fails,
        "score_comparisons": score_results,
        "cap_trigger_checks": cap_results,
        "contradiction_checks": contradiction_results,
        "invariant_checks": invariant_results,
        "failures": [c for c in all_checks if c.get("status") == "FAIL"],
    }

    return result


def run_all_cases(assessment_dir, output_dir=None):
    """Run regression for all golden cases in the templates directory."""
    results = []

    if not GOLDEN_CASES_DIR.exists():
        print(f"⚠️ Golden cases directory not found: {GOLDEN_CASES_DIR}")
        return results

    case_files = sorted(GOLDEN_CASES_DIR.glob("case_*.json"))
    if not case_files:
        print("⚠️ No golden case files found")
        return results

    print(f"📋 Found {len(case_files)} golden cases")

    for case_file in case_files:
        print(f"\n▶ Running {case_file.name}...")
        try:
            result = run_single_case(assessment_dir, case_file, output_dir)
            results.append(result)
            status = result.get("status", "?")
            if status == "SKIPPED":
                print(f"  ⏭️ SKIPPED (stub case)")
            elif status == "PASS":
                print(f"  ✅ PASS ({result.get('checks_passed', 0)}/{result.get('checks_run', 0)})")
            elif status == "FAIL":
                print(f"  ❌ FAIL ({result.get('checks_failed', 0)} failures)")
                for f in result.get("failures", [])[:3]:
                    print(f"     → {f.get('check', '?')}: expected={f.get('expected', '?')}, actual={f.get('actual', '?')}")
            else:
                print(f"  ⚠️ {status}: {result.get('error', '')}")
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
            results.append({
                "case_id": case_file.stem,
                "status": "ERROR",
                "error": str(e),
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="DMA Regression Runner")
    parser.add_argument("assessment_dir", help="Path to assessment output directory")
    parser.add_argument("golden_case", nargs="?", help="Path to golden case JSON")
    parser.add_argument("--all-cases", action="store_true",
                        help="Run all golden cases")
    parser.add_argument("--output-dir", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.assessment_dir) / "regression_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🧪 DMA Regression Runner v2.1")
    print(f"   Assessment: {args.assessment_dir}")
    print(f"   Output: {output_dir}")

    if args.all_cases:
        results = run_all_cases(args.assessment_dir, output_dir)
    elif args.golden_case:
        result = run_single_case(args.assessment_dir, args.golden_case, output_dir)
        results = [result]
    else:
        sys.exit("Provide either a golden case path or --all-cases")

    # Summary
    active = [r for r in results if r.get("status") not in ("SKIPPED", "ERROR")]
    passes = sum(1 for r in active if r.get("status") == "PASS")
    fails = sum(1 for r in active if r.get("status") == "FAIL")
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")

    print(f"\n{'='*50}")
    print(f"REGRESSION SUMMARY")
    print(f"{'='*50}")
    print(f"Cases run:     {len(active)}")
    print(f"Passed:        {passes}")
    print(f"Failed:        {fails}")
    print(f"Skipped:       {skipped}")
    print(f"{'='*50}")
    overall = "PASS" if fails == 0 and len(active) > 0 else "FAIL" if fails > 0 else "NO_ACTIVE_CASES"
    print(f"VERDICT:       {overall}")
    print(f"{'='*50}")

    # Write output
    output = {
        "regression_date": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "governance_skill_version": "2.1",
        "assessment_dir": str(args.assessment_dir),
        "overall_verdict": overall,
        "cases_run": len(active),
        "cases_passed": passes,
        "cases_failed": fails,
        "cases_skipped": skipped,
        "results": results,
    }

    output_path = output_dir / "regression_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n📄 {output_path}")

    return overall


if __name__ == "__main__":
    verdict = main()
    sys.exit(0 if verdict == "PASS" else 1)
