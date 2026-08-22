#!/usr/bin/env python3
"""
DMA Calibration Engine — Cross-assessment comparison for Workflow B.

Loads multiple run_manifest.json files, computes calibration metrics,
runs drift detection, and outputs structured calibration data.

Produces:
  - calibration_metrics.json  (all computed metrics)
  - drift_flags.json  (any metric exceeding thresholds)

Usage:
  python calibration_engine.py <manifest1.json> <manifest2.json> [...] [--output-dir <dir>]
  python calibration_engine.py --manifest-dir <dir>  [--output-dir <dir>]
"""

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, stdev


PILLAR_NAMES = ["P1", "P2", "P3", "P4"]

# Drift thresholds from calibration_framework.md
DRIFT_THRESHOLDS = {
    "overall_mean": 0.15,      # per assessment
    "pillar_mean": 0.20,       # per pillar
    "stdev_decrease": 0.10,    # score compression
    "high_confidence_increase": 5.0,  # percentage points
    "cap_rate_change": 5.0,    # percentage points
    "sources_per_subcap_decrease": 0.3,
}


def load_manifests(paths):
    """Load and validate multiple run manifests."""
    manifests = []
    for p in paths:
        with open(p) as f:
            m = json.load(f)
        m["_source_path"] = str(p)
        manifests.append(m)
    return manifests


def discover_manifests(directory):
    """Find all run_manifest.json files in a directory tree."""
    d = Path(directory)
    return sorted(d.rglob("run_manifest.json"))


def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def compute_score_metrics(manifests):
    """Section 2.1: Score distribution comparison."""
    metrics = {"overall": [], "pillars": defaultdict(list), "categories": defaultdict(list)}

    for m in manifests:
        inst = m.get("institution_name", "unknown")
        overall = safe_float(m.get("overall_score"))
        metrics["overall"].append({"institution": inst, "score": overall})

        pillars = m.get("pillar_scores", {})
        for p in PILLAR_NAMES:
            val = safe_float(pillars.get(p))
            metrics["pillars"][p].append({"institution": inst, "score": val})

        categories = m.get("scores", {}).get("categories", {})
        if not categories:
            categories = m.get("category_scores", {})
        for cat, val in categories.items():
            metrics["categories"][cat].append({"institution": inst, "score": safe_float(val)})

    # Compute statistics
    def stats(values):
        scores = [v["score"] for v in values if v["score"] > 0]
        if len(scores) < 2:
            return {"mean": mean(scores) if scores else 0, "median": 0,
                    "stdev": 0, "min": 0, "max": 0, "n": len(scores)}
        return {
            "mean": round(mean(scores), 3),
            "median": round(median(scores), 3),
            "stdev": round(stdev(scores), 3),
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
            "n": len(scores),
        }

    return {
        "overall": {"values": metrics["overall"], "stats": stats(metrics["overall"])},
        "pillars": {p: {"values": v, "stats": stats(v)} for p, v in metrics["pillars"].items()},
        "categories": {c: {"values": v, "stats": stats(v)} for c, v in metrics["categories"].items()},
    }


def compute_evidence_metrics(manifests):
    """Section 2.2: Evidence discipline metrics."""
    metrics = {
        "avg_ers": [],
        "total_evidence": [],
        "tier_distributions": [],
        "sources_per_subcap": [],
        "single_source_rate": [],
    }

    for m in manifests:
        inst = m.get("institution_name", "unknown")
        em = m.get("evidence_metrics", {})

        if em:
            metrics["avg_ers"].append(safe_float(em.get("avg_ers")))
            metrics["total_evidence"].append(safe_int(em.get("total_items", m.get("evidence_count", 0))))
            metrics["sources_per_subcap"].append(safe_float(em.get("sources_per_subcap_avg")))

            tier_dist = em.get("tier_distribution", {})
            total = sum(safe_int(v) for v in tier_dist.values()) or 1
            metrics["tier_distributions"].append({
                t: round(safe_int(tier_dist.get(t, 0)) / total * 100, 1)
                for t in ["T1", "T2", "T3", "T4", "T5"]
            })

            ss_count = safe_int(em.get("single_source_subcap_count", 0))
            total_subcaps = safe_int(em.get("total_items", 1))
            metrics["single_source_rate"].append(
                round(ss_count / max(total_subcaps, 1) * 100, 1))
        else:
            metrics["total_evidence"].append(safe_int(m.get("evidence_count", 0)))

    def safe_stats(values):
        vals = [v for v in values if v > 0]
        if not vals:
            return {"mean": 0, "median": 0, "n": 0}
        return {"mean": round(mean(vals), 2),
                "median": round(median(vals), 2), "n": len(vals)}

    return {
        "avg_ers": safe_stats(metrics["avg_ers"]),
        "total_evidence": safe_stats(metrics["total_evidence"]),
        "sources_per_subcap": safe_stats(metrics["sources_per_subcap"]),
        "single_source_rate": safe_stats(metrics["single_source_rate"]),
        "tier_distributions": metrics["tier_distributions"],
    }


def compute_scoring_behavior(manifests):
    """Section 2.3–2.5: Cap frequency, confidence, contradictions."""
    cap_rates = []
    confidence_dists = []
    contradiction_rates = []

    for m in manifests:
        sm = m.get("scoring_metrics", m.get("caps_applied", {}))
        total_caps = safe_int(sm.get("caps_applied_count", sm.get("total", 0)))
        contradictions = safe_int(sm.get("contradictions_found", 0))

        conf = m.get("confidence_distribution", {})
        total_conf = sum(safe_int(v) for v in conf.values()) or 1

        cap_rates.append(total_caps)
        contradiction_rates.append(contradictions)
        confidence_dists.append({
            level: round(safe_int(conf.get(level, 0)) / total_conf * 100, 1)
            for level in ["HIGH", "MEDIUM", "LOW"]
        })

    return {
        "cap_rates": cap_rates,
        "confidence_distributions": confidence_dists,
        "contradiction_rates": contradiction_rates,
        "avg_high_confidence_pct": round(
            mean([d.get("HIGH", 0) for d in confidence_dists]), 1) if confidence_dists else 0,
    }


def compute_assessor_metrics(manifests, score_metrics):
    """Section 1.4: Per-assessment assessor-specific metrics.

    Produces harshness index, category bias, confidence tendency, evidence effort
    for each assessment relative to the cohort.
    """
    cohort_overall_mean = score_metrics["overall"]["stats"]["mean"]
    cohort_pillar_means = {
        p: score_metrics["pillars"].get(p, {}).get("stats", {}).get("mean", 0)
        for p in PILLAR_NAMES
    }

    assessor_profiles = []
    for m in manifests:
        inst = m.get("institution_name", "unknown")
        overall = safe_float(m.get("overall_score"))

        # Harshness index: deviation from cohort mean (negative = harsher)
        harshness = round(overall - cohort_overall_mean, 3) if cohort_overall_mean else 0

        # Category bias: which pillars deviate most from cohort
        pillars = m.get("pillar_scores", {})
        category_bias = {}
        max_bias = 0
        max_bias_pillar = None
        for p in PILLAR_NAMES:
            p_val = safe_float(pillars.get(p))
            p_cohort = cohort_pillar_means.get(p, 0)
            bias = round(p_val - p_cohort, 3) if p_cohort else 0
            category_bias[p] = bias
            if abs(bias) > abs(max_bias):
                max_bias = bias
                max_bias_pillar = p

        # Confidence tendency: HIGH confidence percentage for this assessment
        conf = m.get("confidence_distribution", {})
        total_conf = sum(safe_int(v) for v in conf.values()) or 1
        high_pct = round(safe_int(conf.get("HIGH", 0)) / total_conf * 100, 1)

        # Evidence effort: sources per subcap, total evidence count
        em = m.get("evidence_metrics", {})
        sources_per_subcap = safe_float(em.get("sources_per_subcap_avg"))
        total_evidence = safe_int(em.get("total_items", m.get("evidence_count", 0)))

        assessor_profiles.append({
            "institution": inst,
            "harshness_index": harshness,
            "category_bias": category_bias,
            "max_bias_pillar": max_bias_pillar,
            "max_bias_value": max_bias,
            "high_confidence_pct": high_pct,
            "sources_per_subcap": sources_per_subcap,
            "total_evidence": total_evidence,
        })

    return assessor_profiles


def compute_tier_diversity(manifests):
    """Herfindahl tier diversity index: 1 - sum(tier_pct²).

    Higher = more diverse evidence tier usage. 0 = all one tier.
    """
    diversity_scores = []
    for m in manifests:
        em = m.get("evidence_metrics", {})
        tier_dist = em.get("tier_distribution", {})
        total = sum(safe_int(v) for v in tier_dist.values())
        if total == 0:
            diversity_scores.append({"institution": m.get("institution_name", "?"),
                                     "herfindahl_diversity": 0, "tier_distribution": {}})
            continue

        pcts = {t: safe_int(tier_dist.get(t, 0)) / total for t in ["T1", "T2", "T3", "T4", "T5"]}
        hhi = sum(p ** 2 for p in pcts.values())
        diversity = round(1 - hhi, 4)

        diversity_scores.append({
            "institution": m.get("institution_name", "?"),
            "herfindahl_diversity": diversity,
            "tier_distribution": {t: round(p * 100, 1) for t, p in pcts.items()},
        })

    if diversity_scores:
        vals = [d["herfindahl_diversity"] for d in diversity_scores if d["herfindahl_diversity"] > 0]
        avg = round(mean(vals), 4) if vals else 0
    else:
        avg = 0

    return {
        "per_assessment": diversity_scores,
        "cohort_average": avg,
    }


def compute_resolution_consistency(manifests):
    """Resolution consistency: % using ERS_RANKING vs T1T2_OVERRIDE across assessments."""
    resolution_stats = []
    for m in manifests:
        sm = m.get("scoring_metrics", {})
        resolutions = sm.get("contradiction_resolutions", {})
        total = sum(safe_int(v) for v in resolutions.values()) or 1

        ers_count = safe_int(resolutions.get("ERS_RANKING", 0))
        t1t2_count = safe_int(resolutions.get("T1T2_OVERRIDE", 0))
        other_count = total - ers_count - t1t2_count

        resolution_stats.append({
            "institution": m.get("institution_name", "?"),
            "ers_ranking_pct": round(ers_count / total * 100, 1),
            "t1t2_override_pct": round(t1t2_count / total * 100, 1),
            "other_pct": round(other_count / total * 100, 1),
            "total_contradictions": total if total > 1 else 0,
        })

    return resolution_stats


def compute_staleness_rate(manifests):
    """Staleness rate: stale_evidence / total_evidence per assessment."""
    staleness_data = []
    for m in manifests:
        em = m.get("evidence_metrics", {})
        stale = safe_int(em.get("stale_evidence_count", 0))
        total = safe_int(em.get("total_items", m.get("evidence_count", 0)))
        rate = round(stale / max(total, 1) * 100, 1)

        staleness_data.append({
            "institution": m.get("institution_name", "?"),
            "stale_count": stale,
            "total_evidence": total,
            "staleness_pct": rate,
        })

    vals = [d["staleness_pct"] for d in staleness_data]
    avg = round(mean(vals), 1) if vals else 0

    return {
        "per_assessment": staleness_data,
        "cohort_average_staleness_pct": avg,
    }


def check_rubric_compatibility(manifests):
    """Flag cross-major-version comparisons that may be invalid."""
    versions = {}
    for m in manifests:
        rv = m.get("rubric_version", m.get("assessment_skill_version", "unknown"))
        inst = m.get("institution_name", "unknown")
        versions[inst] = str(rv)

    unique_majors = set()
    for v in versions.values():
        major = v.split(".")[0] if "." in v else v
        unique_majors.add(major)

    compatible = len(unique_majors) <= 1

    return {
        "versions": versions,
        "unique_major_versions": list(unique_majors),
        "cross_version_compatible": compatible,
        "warning": None if compatible else
            f"Multiple major rubric versions detected: {list(unique_majors)}. "
            f"Cross-version comparison may be unreliable.",
    }


def detect_drift(score_metrics, evidence_metrics, behavior_metrics,
                 baselines=None, assessor_metrics=None):
    """Section 3: Drift detection against baselines."""
    flags = []

    if not baselines:
        baselines = {
            "overall_mean": 2.85,
            "P1_mean": 3.05, "P2_mean": 3.08, "P3_mean": 2.54, "P4_mean": 2.82,
            "high_confidence_pct": 55.0,
            "cap_rate_baseline": 20.0,
            "evidence_cap_baseline": 20.0,
        }

    # Overall score drift
    current_mean = score_metrics["overall"]["stats"]["mean"]
    baseline_mean = baselines.get("overall_mean", 2.85)
    delta = abs(current_mean - baseline_mean)
    if delta > DRIFT_THRESHOLDS["overall_mean"]:
        direction = "harsher" if current_mean < baseline_mean else "more lenient"
        flags.append({
            "flag_id": "DRIFT-SCORE-001",
            "type": "score_drift",
            "severity": "ALERT",
            "metric": "overall_mean",
            "current": current_mean,
            "baseline": baseline_mean,
            "delta": round(delta, 3),
            "description": f"Overall mean {current_mean:.2f} deviates from baseline {baseline_mean:.2f} ({direction})",
            "recommendation": "Review scoring consistency; consider anchor case recalibration",
        })

    # Pillar-level drift
    for p in PILLAR_NAMES:
        p_stats = score_metrics["pillars"].get(p, {}).get("stats", {})
        p_mean = p_stats.get("mean", 0)
        p_baseline = baselines.get(f"{p}_mean", 3.0)
        p_delta = abs(p_mean - p_baseline)
        if p_delta > DRIFT_THRESHOLDS["pillar_mean"]:
            flags.append({
                "flag_id": f"DRIFT-{p}-001",
                "type": "pillar_drift",
                "severity": "CAUTION",
                "metric": f"{p}_mean",
                "current": p_mean,
                "baseline": p_baseline,
                "delta": round(p_delta, 3),
                "description": f"{p} mean {p_mean:.2f} deviates from baseline {p_baseline:.2f}",
                "recommendation": f"Review {p} scoring methodology",
            })

    # Confidence inflation
    current_high = behavior_metrics.get("avg_high_confidence_pct", 0)
    baseline_high = baselines.get("high_confidence_pct", 55.0)
    if current_high - baseline_high > DRIFT_THRESHOLDS["high_confidence_increase"]:
        flags.append({
            "flag_id": "DRIFT-CONF-001",
            "type": "confidence_inflation",
            "severity": "CAUTION",
            "metric": "high_confidence_pct",
            "current": current_high,
            "baseline": baseline_high,
            "delta": round(current_high - baseline_high, 1),
            "description": f"HIGH confidence at {current_high:.0f}% (baseline {baseline_high:.0f}%)",
            "recommendation": "Enforce ERS-confidence cross-checks",
        })

    # Score compression: stdev dropped significantly
    current_stdev = score_metrics["overall"]["stats"].get("stdev", 0)
    baseline_stdev = baselines.get("overall_stdev", 0.45)
    if baseline_stdev > 0 and (baseline_stdev - current_stdev) > DRIFT_THRESHOLDS["stdev_decrease"]:
        flags.append({
            "flag_id": "DRIFT-COMPRESS-001",
            "type": "score_compression",
            "severity": "CAUTION",
            "metric": "overall_stdev",
            "current": current_stdev,
            "baseline": baseline_stdev,
            "delta": round(baseline_stdev - current_stdev, 3),
            "description": f"Score stdev {current_stdev:.3f} vs baseline {baseline_stdev:.3f} — scores are compressing",
            "recommendation": "Review whether score differentiation is sufficient; check for anchoring bias",
        })

    # Assessor-level drift (if assessor_metrics provided)
    if assessor_metrics:
        for ap in assessor_metrics:
            if abs(ap["harshness_index"]) > DRIFT_THRESHOLDS["overall_mean"] * 1.5:
                direction = "harsher" if ap["harshness_index"] < 0 else "more lenient"
                flags.append({
                    "flag_id": f"DRIFT-ASSESSOR-{ap['institution'][:8]}",
                    "type": "assessor_drift",
                    "severity": "CAUTION",
                    "metric": "harshness_index",
                    "current": ap["harshness_index"],
                    "institution": ap["institution"],
                    "description": f"{ap['institution']} is {direction} than cohort by {abs(ap['harshness_index']):.2f}",
                    "recommendation": f"Review {ap['institution']} scoring methodology",
                })

    return flags


def run_calibration(manifest_paths, output_dir=None, baselines=None):
    """Execute full calibration analysis."""
    manifests = load_manifests(manifest_paths)
    output_dir = Path(output_dir) if output_dir else Path("calibration_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📊 DMA Calibration Engine v2.1")
    print(f"   Assessments: {len(manifests)}")
    print(f"   Output: {output_dir}")
    print()

    # Compute metrics
    score_metrics = compute_score_metrics(manifests)
    evidence_metrics = compute_evidence_metrics(manifests)
    behavior_metrics = compute_scoring_behavior(manifests)
    assessor_metrics = compute_assessor_metrics(manifests, score_metrics)
    tier_diversity = compute_tier_diversity(manifests)
    resolution_consistency = compute_resolution_consistency(manifests)
    staleness = compute_staleness_rate(manifests)
    rubric_compat = check_rubric_compatibility(manifests)

    drift_flags = detect_drift(score_metrics, evidence_metrics, behavior_metrics,
                               baselines, assessor_metrics)

    # Add rubric compatibility warning as a drift flag if applicable
    if not rubric_compat["cross_version_compatible"]:
        drift_flags.append({
            "flag_id": "DRIFT-VERSION-001",
            "type": "rubric_version_mismatch",
            "severity": "ALERT",
            "metric": "rubric_version",
            "description": rubric_compat["warning"],
            "recommendation": "Use version bridge mapping before comparing scores cross-version",
        })

    # Cohort profile
    sub_verticals = Counter(m.get("sub_vertical", "unknown") for m in manifests)
    size_tiers = Counter(m.get("size_tier", "unknown") for m in manifests)
    evidence_modes = Counter(m.get("evidence_mode", "unknown") for m in manifests)

    calibration_output = {
        "calibration_date": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "governance_skill_version": "2.1",
        "cohort": {
            "count": len(manifests),
            "sub_verticals": dict(sub_verticals),
            "size_tiers": dict(size_tiers),
            "evidence_modes": dict(evidence_modes),
            "institutions": [m.get("institution_name", "unknown") for m in manifests],
        },
        "rubric_compatibility": rubric_compat,
        "score_metrics": {
            "overall": score_metrics["overall"]["stats"],
            "pillars": {p: v["stats"] for p, v in score_metrics["pillars"].items()},
        },
        "evidence_metrics": evidence_metrics,
        "tier_diversity": tier_diversity,
        "staleness": staleness,
        "behavior_metrics": behavior_metrics,
        "resolution_consistency": resolution_consistency,
        "assessor_metrics": assessor_metrics,
        "drift_flags": drift_flags,
        "drift_summary": {
            "total_flags": len(drift_flags),
            "alerts": sum(1 for f in drift_flags if f["severity"] == "ALERT"),
            "cautions": sum(1 for f in drift_flags if f["severity"] == "CAUTION"),
        },
    }

    # Write outputs
    metrics_path = output_dir / "calibration_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(calibration_output, f, indent=2)
    print(f"📄 {metrics_path}")

    if drift_flags:
        flags_path = output_dir / "drift_flags.json"
        with open(flags_path, "w") as f:
            json.dump(drift_flags, f, indent=2)
        print(f"📄 {flags_path}")

    # Summary
    print()
    print(f"{'='*50}")
    print(f"CALIBRATION SUMMARY")
    print(f"{'='*50}")
    print(f"Assessments:         {len(manifests)}")
    print(f"Overall mean:        {score_metrics['overall']['stats']['mean']:.2f}")
    print(f"Tier diversity:      {tier_diversity['cohort_average']:.3f}")
    print(f"Avg staleness:       {staleness['cohort_average_staleness_pct']:.1f}%")
    print(f"Rubric compatible:   {'Yes' if rubric_compat['cross_version_compatible'] else 'NO'}")
    print(f"Drift flags:         {len(drift_flags)} ({sum(1 for f in drift_flags if f['severity']=='ALERT')} alerts)")
    print(f"{'='*50}")

    return calibration_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DMA Calibration Engine")
    parser.add_argument("manifests", nargs="*", help="Paths to run_manifest.json files")
    parser.add_argument("--manifest-dir", help="Directory containing manifest files")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--baselines", help="Path to baselines JSON file")
    args = parser.parse_args()

    paths = args.manifests or []
    if args.manifest_dir:
        paths.extend(discover_manifests(args.manifest_dir))

    if len(paths) < 2:
        sys.exit("Need ≥2 manifests for calibration. Provide paths or --manifest-dir.")

    baselines = None
    if args.baselines:
        with open(args.baselines) as f:
            baselines = json.load(f)

    run_calibration(paths, args.output_dir, baselines)
