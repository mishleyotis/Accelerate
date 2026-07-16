"""Catalogue load-time validators.

Run before promotion from `staging.*` to canonical schema. Failures
short-circuit the loader (admin sees the failure detail in /admin/catalogue).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    passed: list[str] = field(default_factory=list)
    failed: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


# ---------- shape expectations (v7.0 locked) ----------
EXPECTED_PILLAR_SUBCAP_COUNTS = {"P1": 205, "P2": 292, "P3": 164, "P4": 190}
EXPECTED_TOTAL_SUBCAPS = sum(EXPECTED_PILLAR_SUBCAP_COUNTS.values())  # 851
EXPECTED_TOTAL_L1 = 136
EXPECTED_TOTAL_CATEGORIES = 16


def validate_pillar_totals(
    subcaps_rows: Iterable[dict[str, object]],
) -> ValidationReport:
    """Re-counts subcaps per pillar against the locked v7.0 expected counts."""
    report = ValidationReport()
    by_pillar: dict[str, int] = {}
    for row in subcaps_rows:
        subcap_id = str(row.get("subcap_id", ""))
        if not subcap_id:
            continue
        pillar = subcap_id[:2]  # "P1"..."P4"
        by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
    for pillar, expected in EXPECTED_PILLAR_SUBCAP_COUNTS.items():
        actual = by_pillar.get(pillar, 0)
        if actual == expected:
            report.passed.append(f"pillar_subcap_count.{pillar}")
        else:
            report.failed.append(
                {
                    "gate": f"pillar_subcap_count.{pillar}",
                    "expected": expected,
                    "actual": actual,
                }
            )
    total = sum(by_pillar.values())
    if total == EXPECTED_TOTAL_SUBCAPS:
        report.passed.append("total_subcap_count")
    else:
        report.failed.append(
            {
                "gate": "total_subcap_count",
                "expected": EXPECTED_TOTAL_SUBCAPS,
                "actual": total,
            }
        )
    return report


def validate_fk_closure(
    subcaps_rows: Iterable[dict[str, object]],
    matrix_subcap_refs: Iterable[str],
) -> ValidationReport:
    """Every subcap_id referenced by any matrix table must exist in ccg_subcaps."""
    report = ValidationReport()
    known = {str(r.get("subcap_id")) for r in subcaps_rows}
    orphans = sorted(set(matrix_subcap_refs) - known)
    if not orphans:
        report.passed.append("fk_closure.subcap_ids")
    else:
        report.failed.append(
            {
                "gate": "fk_closure.subcap_ids",
                "orphans_first_20": orphans[:20],
                "orphan_count": len(orphans),
            }
        )
    return report


def validate_value_chain_subverticals(
    vc_rows: Iterable[dict[str, object]],
    canonical_subvertical_codes: Iterable[str] = ("RB", "CU", "CL", "CIB", "FC", "AM",
                                                  "RIA", "IC", "IB"),
) -> ValidationReport:
    """Every value-chain row's subvertical_code must be one of the 9 canonical
    codes (or a `pending_admin_review` row inserted by an earlier loader run)."""
    report = ValidationReport()
    canonical = set(canonical_subvertical_codes)
    unknowns = sorted(
        {str(r.get("subvertical_code")) for r in vc_rows} - canonical
    )
    if not unknowns:
        report.passed.append("vc_subverticals.canonical_only")
    else:
        # Per resolved decision 8, this is a *warning*, not a failure — the
        # loader auto-inserts the new code into ccg_subverticals with
        # status='pending_admin_review'.
        report.warnings.append(
            {"gate": "vc_subverticals.canonical_only", "new_codes": unknowns}
        )
    return report


def merge_reports(*reports: ValidationReport) -> ValidationReport:
    out = ValidationReport()
    for r in reports:
        out.passed.extend(r.passed)
        out.failed.extend(r.failed)
        out.warnings.extend(r.warnings)
    return out
