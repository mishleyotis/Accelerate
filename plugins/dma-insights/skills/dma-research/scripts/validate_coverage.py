#!/usr/bin/env python3
"""
Validate evidence coverage against DMA research thresholds.

Usage:
    python validate_coverage.py <evidence_index.json> [--strict] [--report <output_path>]

Checks:
  - Per-subcap evidence count (≥3 = READY, 1-2 = THIN, 0 = NO_EVIDENCE)
  - Per-capability coverage percentage
  - Per-pillar coverage percentage
  - Overall coverage against 80% threshold
  - Minimum coverage hard gate items
  - Tier distribution quality
  - ERS quality distribution
"""

import argparse
import json
import sys
from collections import defaultdict


def load_evidence_index(path):
    with open(path) as f:
        return json.load(f)


def validate_subcap_coverage(evidence_index):
    """Check evidence count per subcapability."""
    coverage = evidence_index.get('subcap_coverage', {})
    
    results = {'READY': [], 'THIN': [], 'NO_EVIDENCE': [], 'BLOCKED': []}
    
    for subcap_id, data in sorted(coverage.items()):
        count = data.get('evidence_count', 0)
        status = data.get('coverage_status', '')
        
        if count >= 3:
            results['READY'].append(subcap_id)
        elif count >= 1:
            results['THIN'].append(subcap_id)
        else:
            results['NO_EVIDENCE'].append(subcap_id)
        
        if status == 'BLOCKED':
            results['BLOCKED'].append(subcap_id)
    
    total = len(coverage)
    return results, total


def validate_capability_coverage(evidence_index):
    """Check coverage at capability level."""
    coverage = evidence_index.get('subcap_coverage', {})
    
    cap_stats = defaultdict(lambda: {'total': 0, 'ready': 0, 'thin': 0, 'none': 0})
    
    for subcap_id, data in coverage.items():
        # Extract capability ID (e.g., P1C1 from P1C1.1.1)
        parts = subcap_id.split('.')
        cap_id = parts[0] if parts else subcap_id
        
        count = data.get('evidence_count', 0)
        cap_stats[cap_id]['total'] += 1
        if count >= 3:
            cap_stats[cap_id]['ready'] += 1
        elif count >= 1:
            cap_stats[cap_id]['thin'] += 1
        else:
            cap_stats[cap_id]['none'] += 1
    
    return dict(cap_stats)


def validate_hard_gate(evidence_index):
    """Check minimum coverage hard gate items."""
    items = evidence_index.get('evidence_items', [])
    coverage = evidence_index.get('subcap_coverage', {})
    
    gates = {
        'T1 regulatory anchor': False,
        'T1/T2 financial sources (≥2)': False,
        'Independent operating model sources (≥2)': False,
        'Issue/enforcement search': False,
        'Sentiment data attempt': False,
        'Tech stack discovery': False,
        'Org capability proxies': False,
        'Diagnostic questions loaded': False,
        '≥80% subcap coverage': False,
    }
    
    # Check tier distribution
    t1_count = sum(1 for e in items if e.get('tier') == 'T1')
    t1_t2_count = sum(1 for e in items if e.get('tier') in ('T1', 'T2'))
    
    gates['T1 regulatory anchor'] = t1_count >= 1
    gates['T1/T2 financial sources (≥2)'] = t1_t2_count >= 2
    
    # Check coverage percentage
    total = len(coverage)
    with_evidence = sum(1 for d in coverage.values() if d.get('evidence_count', 0) > 0)
    coverage_pct = (with_evidence / total * 100) if total > 0 else 0
    gates['≥80% subcap coverage'] = coverage_pct >= 80
    
    # Check if diagnostic questions were loaded
    with_dq = sum(1 for d in coverage.values() if d.get('diagnostic_question', ''))
    gates['Diagnostic questions loaded'] = with_dq > 0
    
    return gates, coverage_pct


def validate_ers_quality(evidence_index):
    """Check ERS distribution quality."""
    items = evidence_index.get('evidence_items', [])
    
    ers_scores = []
    for item in items:
        ers = item.get('ers_scores', {}).get('ers_total', 0)
        if ers > 0:
            ers_scores.append(ers)
    
    if not ers_scores:
        return {'avg': 0, 'min': 0, 'max': 0, 'high_count': 0, 'low_count': 0}
    
    return {
        'avg': sum(ers_scores) / len(ers_scores),
        'min': min(ers_scores),
        'max': max(ers_scores),
        'high_count': sum(1 for s in ers_scores if s >= 3.5),
        'low_count': sum(1 for s in ers_scores if s < 2.5),
        'total': len(ers_scores),
    }


def print_report(subcap_results, total, cap_stats, gates, coverage_pct, ers_stats, strict=False):
    """Print validation report."""
    print(f"\n{'='*70}")
    print(f"DMA RESEARCH EVIDENCE COVERAGE VALIDATION")
    print(f"{'='*70}")
    
    # Overall
    ready = len(subcap_results['READY'])
    thin = len(subcap_results['THIN'])
    none = len(subcap_results['NO_EVIDENCE'])
    blocked = len(subcap_results['BLOCKED'])
    
    print(f"\n--- SUBCAPABILITY COVERAGE ---")
    print(f"Total subcaps: {total}")
    print(f"  READY (≥3 items):  {ready:4d}  ({100*ready/max(total,1):.1f}%)")
    print(f"  THIN (1-2 items):  {thin:4d}  ({100*thin/max(total,1):.1f}%)")
    print(f"  NO_EVIDENCE:       {none:4d}  ({100*none/max(total,1):.1f}%)")
    print(f"  BLOCKED:           {blocked:4d}")
    print(f"  Overall coverage:  {coverage_pct:.1f}%")
    
    status = "✅ PASS" if coverage_pct >= 80 else "❌ FAIL"
    print(f"  Coverage gate:     {status} (threshold: 80%)")
    
    # Capability level
    print(f"\n--- CAPABILITY COVERAGE ---")
    for cap_id in sorted(cap_stats.keys()):
        stats = cap_stats[cap_id]
        cap_pct = 100 * stats['ready'] / max(stats['total'], 1)
        flag = "⚠️" if cap_pct < 60 else "✅"
        print(f"  {cap_id}: {stats['ready']}/{stats['total']} ready ({cap_pct:.0f}%) "
              f"| {stats['thin']} thin | {stats['none']} none {flag}")
    
    # Hard gates
    print(f"\n--- HARD GATE CHECKS ---")
    all_pass = True
    for gate, passed in gates.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False
        print(f"  {status}  {gate}")
    
    gate_result = "✅ ALL GATES PASS" if all_pass else "❌ GATES FAILED — remediation required"
    print(f"\n  {gate_result}")
    
    # ERS quality
    if ers_stats.get('total', 0) > 0:
        print(f"\n--- EVIDENCE QUALITY (ERS) ---")
        print(f"  Total items scored: {ers_stats['total']}")
        print(f"  Average ERS:        {ers_stats['avg']:.2f}")
        print(f"  Min/Max:            {ers_stats['min']:.2f} / {ers_stats['max']:.2f}")
        print(f"  High quality (≥3.5): {ers_stats['high_count']} ({100*ers_stats['high_count']/ers_stats['total']:.0f}%)")
        print(f"  Low quality (<2.5):  {ers_stats['low_count']} ({100*ers_stats['low_count']/ers_stats['total']:.0f}%)")
    
    # Thin subcaps list (for remediation)
    if thin > 0 and thin <= 50:
        print(f"\n--- THIN SUBCAPS (need remediation searches) ---")
        for sc_id in subcap_results['THIN'][:30]:
            print(f"  {sc_id}")
        if thin > 30:
            print(f"  ... and {thin - 30} more")
    
    # No evidence list
    if none > 0 and none <= 30:
        print(f"\n--- NO_EVIDENCE SUBCAPS ---")
        for sc_id in subcap_results['NO_EVIDENCE'][:20]:
            print(f"  {sc_id}")
        if none > 20:
            print(f"  ... and {none - 20} more")
    
    print(f"\n{'='*70}")
    
    # Exit code
    if strict and not all_pass:
        return 1
    if strict and coverage_pct < 80:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description='Validate DMA research evidence coverage')
    parser.add_argument('evidence_index', help='Path to evidence_index.json')
    parser.add_argument('--strict', action='store_true', help='Exit code 1 if gates fail')
    parser.add_argument('--report', help='Save report to file')
    args = parser.parse_args()
    
    evidence_index = load_evidence_index(args.evidence_index)
    
    subcap_results, total = validate_subcap_coverage(evidence_index)
    cap_stats = validate_capability_coverage(evidence_index)
    gates, coverage_pct = validate_hard_gate(evidence_index)
    ers_stats = validate_ers_quality(evidence_index)
    
    exit_code = print_report(subcap_results, total, cap_stats, gates, coverage_pct,
                            ers_stats, strict=args.strict)
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
