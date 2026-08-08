#!/usr/bin/env python3
"""
DMA Scoring Quality Validator — MANDATORY after Phase 4
========================================================
This script MUST be run before proceeding past Phase 4. It checks for the 7 most
common failure modes and blocks progression if any CRITICAL check fails.

Usage:
    python validate_scoring_quality.py <workbook_path>

Exit codes:
    0 = PASS (all checks pass)
    1 = FAIL (one or more CRITICAL checks failed — fix before proceeding)
"""

import sys
import os
import re
import json
from collections import Counter

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl required. Run: pip install openpyxl --break-system-packages")
    sys.exit(1)


def load_workbook(path):
    if not os.path.exists(path):
        print(f"FATAL: Workbook not found at {path}")
        sys.exit(1)
    return openpyxl.load_workbook(path, data_only=True)


# ──────────────────────────────────────────────────────────────────────
# CHECK 1: Row count per pillar (are we scoring at subcap level?)
# ──────────────────────────────────────────────────────────────────────
def check_row_counts(wb):
    """Each pillar sheet must have ≥50 data rows. Fewer = capability-level scoring."""
    expected_minimums = {
        "P1_Scoring_Detail": 50,
        "P2_Scoring_Detail": 50,
        "P3_Scoring_Detail": 50,
        "P4_Scoring_Detail": 50,
    }
    issues = []
    for sheet_name, min_rows in expected_minimums.items():
        if sheet_name not in wb.sheetnames:
            issues.append(f"CRITICAL: Sheet '{sheet_name}' missing entirely")
            continue
        ws = wb[sheet_name]
        data_rows = ws.max_row - 1
        if data_rows < min_rows:
            issues.append(
                f"CRITICAL: {sheet_name} has {data_rows} rows (need ≥{min_rows}). "
                f"You are scoring at CAPABILITY level, not SUBCAPABILITY level."
            )
    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 2: Score differentiation within capabilities
# ──────────────────────────────────────────────────────────────────────
def check_differentiation(wb):
    """No capability should have 100% identical scores across its subcaps."""
    issues = []
    total_caps = 0
    uniform_caps = 0
    low_variation_caps = 0

    for pname in ["P1_Scoring_Detail", "P2_Scoring_Detail", "P3_Scoring_Detail", "P4_Scoring_Detail"]:
        if pname not in wb.sheetnames:
            continue
        ws = wb[pname]
        cap_scores = {}
        for row in range(2, ws.max_row + 1):
            cap_id = ws.cell(row=row, column=3).value
            score = ws.cell(row=row, column=10).value
            if cap_id and score is not None:
                cap_scores.setdefault(cap_id, []).append(score)

        for cap_id, scores in cap_scores.items():
            if len(scores) < 2:
                continue
            total_caps += 1
            unique = len(set(scores))
            ratio = unique / len(scores)

            if unique == 1 and not all(s == 1.0 for s in scores):
                uniform_caps += 1
                issues.append(
                    f"CRITICAL: {cap_id} — ALL {len(scores)} subcaps scored identically ({scores[0]}). "
                    f"HARD BLOCK: differentiate at least 2 subcaps before proceeding."
                )
            elif ratio < 0.4 and not all(s == 1.0 for s in scores):
                low_variation_caps += 1
                issues.append(
                    f"WARNING: {cap_id} — only {unique}/{len(scores)} unique scores "
                    f"(variation ratio {ratio:.2f}). Re-examine diagnostic questions."
                )

    if uniform_caps > 0:
        issues.insert(0,
            f"CRITICAL SUMMARY: {uniform_caps}/{total_caps} capabilities have ZERO score "
            f"differentiation. This is the #1 quality failure in DMA assessments."
        )
    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 3: Rationale quality
# ──────────────────────────────────────────────────────────────────────
def check_rationale_quality(wb):
    """Rationales must be ≥150 chars, cite evidence IDs, and not use forbidden patterns."""
    FORBIDDEN = [
        "demonstrates well-developed capability",
        "demonstrates minimal capability",
        "demonstrates established maturity",
        "demonstrates basic capability",
        "demonstrates advanced capability",
        "demonstrates foundational capability",
        "demonstrates transformational",
        "based on public evidence analysis",
        "based on available data",
        "evidence suggests m",
        "score assigned based on",
        "category-based scoring",
    ]
    issues = []
    total = 0
    under_150 = 0
    forbidden_matches = 0
    no_evidence_cite = 0
    all_same_length = True
    lengths = set()

    for pname in ["P1_Scoring_Detail", "P2_Scoring_Detail", "P3_Scoring_Detail", "P4_Scoring_Detail"]:
        if pname not in wb.sheetnames:
            continue
        ws = wb[pname]
        for row in range(2, ws.max_row + 1):
            subcap_id = ws.cell(row=row, column=5).value
            rationale = str(ws.cell(row=row, column=17).value or "")
            if not subcap_id:
                continue
            total += 1
            rlen = len(rationale)
            lengths.add(rlen)

            if rlen < 150:
                under_150 += 1

            rat_lower = rationale.lower()
            for pat in FORBIDDEN:
                if pat in rat_lower:
                    forbidden_matches += 1
                    if forbidden_matches <= 5:
                        issues.append(
                            f"CRITICAL: {subcap_id} rationale uses forbidden pattern: '{pat}'"
                        )
                    break

            if not re.search(r'E-\d+', rationale) and not re.search(r'HUBBL-\d+', rationale):
                no_evidence_cite += 1

    if len(lengths) <= 3 and total > 20:
        issues.insert(0,
            f"CRITICAL: All rationales cluster around {sorted(lengths)} character lengths. "
            f"This indicates template-stamped rationales, not individual analysis."
        )

    if under_150 > 0:
        issues.append(
            f"CRITICAL: {under_150}/{total} rationales are under 150 characters "
            f"(minimum required)."
        )

    if forbidden_matches > 5:
        issues.append(
            f"CRITICAL: {forbidden_matches} total forbidden pattern matches "
            f"(showing first 5 above)."
        )

    if no_evidence_cite > total * 0.2:
        issues.append(
            f"WARNING: {no_evidence_cite}/{total} rationales don't cite any Evidence ID "
            f"(E-xxx pattern). Rationales must reference specific evidence."
        )

    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 4: Evidence differentiation per capability
# ──────────────────────────────────────────────────────────────────────
def check_evidence_differentiation(wb):
    """Subcaps within a capability should NOT all cite identical evidence sets."""
    issues = []
    total_caps = 0
    identical_evidence_caps = 0

    for pname in ["P1_Scoring_Detail", "P2_Scoring_Detail", "P3_Scoring_Detail", "P4_Scoring_Detail"]:
        if pname not in wb.sheetnames:
            continue
        ws = wb[pname]
        cap_evidence = {}
        for row in range(2, ws.max_row + 1):
            cap_id = ws.cell(row=row, column=3).value
            evidence = str(ws.cell(row=row, column=11).value or "")
            if cap_id:
                cap_evidence.setdefault(cap_id, []).append(evidence)

        for cap_id, ev_list in cap_evidence.items():
            if len(ev_list) < 2:
                continue
            total_caps += 1
            unique_ev = set(ev_list)
            if len(unique_ev) == 1 and ev_list[0].strip():
                identical_evidence_caps += 1
                if identical_evidence_caps <= 5:
                    issues.append(
                        f"CRITICAL: {cap_id} — all {len(ev_list)} subcaps cite identical "
                        f"evidence '{ev_list[0][:60]}...'. Map facts to individual subcaps."
                    )

    if identical_evidence_caps > 0:
        issues.append(
            f"CRITICAL SUMMARY: {identical_evidence_caps}/{total_caps} capabilities have "
            f"ZERO evidence differentiation across subcaps."
        )
    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 5: Required columns present
# ──────────────────────────────────────────────────────────────────────
def check_required_columns(wb):
    """Verify columns S (Proof_Claims), T (Proof_Links), U (Evidence_Excerpt), V (Source_Document)."""
    required = {18: "Proof_Claims", 19: "Proof_Links", 20: "Evidence_Excerpt", 21: "Source_Document"}
    issues = []
    for pname in ["P1_Scoring_Detail", "P2_Scoring_Detail", "P3_Scoring_Detail", "P4_Scoring_Detail"]:
        if pname not in wb.sheetnames:
            continue
        ws = wb[pname]
        for col, name in required.items():
            header = ws.cell(row=1, column=col).value
            if header is None:
                issues.append(f"CRITICAL: {pname} missing column {col} ({name})")
            elif str(header).strip() != name:
                # Allow close matches
                pass

        # Check if Evidence_Excerpt (col 20 or wherever it is) is populated
        excerpt_col = None
        for col in range(1, ws.max_column + 1):
            if str(ws.cell(row=1, column=col).value or "").strip() == "Evidence_Excerpt":
                excerpt_col = col
                break
        if excerpt_col:
            blank_excerpts = 0
            total_rows = 0
            for row in range(2, ws.max_row + 1):
                if ws.cell(row=row, column=5).value:
                    total_rows += 1
                    val = ws.cell(row=row, column=excerpt_col).value
                    if not val or len(str(val).strip()) < 30:
                        blank_excerpts += 1
            if blank_excerpts > total_rows * 0.3:
                issues.append(
                    f"WARNING: {pname} — {blank_excerpts}/{total_rows} Evidence_Excerpt cells "
                    f"are blank or <30 chars."
                )
    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 6: Caps Applied Log
# ──────────────────────────────────────────────────────────────────────
def check_caps_applied(wb):
    """Caps_Applied_Log should have real entries, not just 'None/N/A'."""
    issues = []
    if "Caps_Applied_Log" not in wb.sheetnames:
        issues.append("CRITICAL: Caps_Applied_Log sheet missing")
        return issues

    ws = wb["Caps_Applied_Log"]
    data_rows = ws.max_row - 1
    if data_rows <= 1:
        first_val = str(ws.cell(row=2, column=1).value or "").lower()
        if "none" in first_val or "n/a" in first_val:
            issues.append(
                "WARNING: Caps_Applied_Log has no real entries. Verify that evidence "
                "ceilings, severity caps, and cross-pillar dependencies were actually "
                "evaluated. Most assessments have at least some caps."
            )
    return issues


# ──────────────────────────────────────────────────────────────────────
# CHECK 7: Evidence fact-level granularity
# ──────────────────────────────────────────────────────────────────────
def check_evidence_fact_granularity(wb):
    """Evidence_IDs should use fact-level citations (E-xxx:Fy), not just E-xxx."""
    issues = []
    total_cells = 0
    has_fact_refs = 0

    for pname in ["P1_Scoring_Detail", "P2_Scoring_Detail", "P3_Scoring_Detail", "P4_Scoring_Detail"]:
        if pname not in wb.sheetnames:
            continue
        ws = wb[pname]
        for row in range(2, ws.max_row + 1):
            evidence = str(ws.cell(row=row, column=11).value or "")
            if evidence.strip() and evidence.strip().lower() not in ("none", "n/a", ""):
                total_cells += 1
                if re.search(r'E-\d+:F\d+|HUBBL-\d+:F\d+', evidence):
                    has_fact_refs += 1

    if total_cells > 0 and has_fact_refs < total_cells * 0.5:
        issues.append(
            f"WARNING: Only {has_fact_refs}/{total_cells} Evidence_ID cells use fact-level "
            f"references (E-xxx:Fy). Most just use E-xxx without specifying which fact. "
            f"This prevents subcap-level differentiation."
        )
    return issues


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__ or "scoring-quality checks over a completed workbook")
        print("Usage: python validate_scoring_quality.py <workbook_path>")
        return
    if len(sys.argv) < 2:
        print("Usage: python validate_scoring_quality.py <workbook_path>")
        sys.exit(1)

    wb_path = sys.argv[1]
    wb = load_workbook(wb_path)

    print("=" * 72)
    print("DMA SCORING QUALITY VALIDATOR")
    print("=" * 72)
    print(f"Workbook: {wb_path}")
    print(f"Sheets: {', '.join(wb.sheetnames)}")
    print()

    all_issues = []
    checks = [
        ("1. Row Count (Subcap-Level Scoring)", check_row_counts),
        ("2. Score Differentiation", check_differentiation),
        ("3. Rationale Quality", check_rationale_quality),
        ("4. Evidence Differentiation", check_evidence_differentiation),
        ("5. Required Columns (S/T/U/V)", check_required_columns),
        ("6. Caps Applied Log", check_caps_applied),
        ("7. Evidence Fact Granularity", check_evidence_fact_granularity),
    ]

    critical_count = 0
    warning_count = 0

    for check_name, check_fn in checks:
        print(f"── {check_name} ──")
        issues = check_fn(wb)
        if not issues:
            print("  ✅ PASS")
        else:
            for issue in issues:
                level = "🔴 CRITICAL" if issue.startswith("CRITICAL") else "🟡 WARNING"
                print(f"  {level}: {issue}")
                if issue.startswith("CRITICAL"):
                    critical_count += 1
                else:
                    warning_count += 1
                all_issues.append(issue)
        print()

    print("=" * 72)
    print(f"RESULT: {critical_count} CRITICAL, {warning_count} WARNING")
    if critical_count > 0:
        print("❌ FAIL — Fix all CRITICAL issues before proceeding to Phase 5.")
        print("   Do NOT skip this. Re-score affected subcapabilities.")
        sys.exit(1)
    elif warning_count > 0:
        print("⚠️  PASS WITH WARNINGS — Review warnings, fix if possible.")
        sys.exit(0)
    else:
        print("✅ PASS — All quality checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
