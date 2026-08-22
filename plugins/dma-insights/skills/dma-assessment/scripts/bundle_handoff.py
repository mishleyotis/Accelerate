#!/usr/bin/env python3
"""
bundle_handoff.py — DMA Assessment Skill (Layer 1)

Packages all assessment deliverables into a standardized bundle for Layer 2 ingestion.
Validates completeness before bundling.

Usage:
    python bundle_handoff.py --assessment-dir ./output/ --bundle-dir ./handoff/

Required files in assessment-dir:
  - Scoring workbook (.xlsx)
  - Assessment report (.docx)
  - run_manifest.json
  - caps_applied_log.csv
  - contradiction_log.csv
  - evidence_index.csv
  - reasoning_chain_log.json (Contract 8)

Output:
  - Validated directory with all files + checksums manifest
  - Or ZIP archive if --zip flag set
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_FILES = {
    "run_manifest.json": "Contract 1 — Assessment metadata (v2 hybrid)",
    "caps_applied_log.csv": "Contract 2 — Cap/adjustment records",
    "contradiction_log.csv": "Contract 3 — Contradiction records",
    "evidence_index.csv": "Contract 4 — Evidence inventory",
    "reasoning_chain_log.json": "Contract 8 — Reasoning audit trail",
}

RECOMMENDED_FILES = {
    # All previously recommended files are now required
}

WORKBOOK_EXTENSIONS = {".xlsx", ".xlsm"}
REPORT_EXTENSIONS = {".docx"}


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_files_by_extension(directory: Path, extensions: set) -> list[Path]:
    return [f for f in directory.iterdir() if f.suffix.lower() in extensions]


def validate_and_bundle(assessment_dir: Path, bundle_dir: Path, create_zip: bool) -> int:
    """Validate completeness and create handoff bundle."""
    issues = []
    files_to_bundle = []

    # Check required governance files
    for filename, desc in REQUIRED_FILES.items():
        filepath = assessment_dir / filename
        if filepath.exists():
            files_to_bundle.append(filepath)
            logger.info(f"  ✓ {filename} ({desc})")
        else:
            issues.append(f"CRITICAL: Missing {filename} ({desc})")
            logger.error(f"  ✗ {filename} — MISSING")

    # Check recommended files
    for filename, desc in RECOMMENDED_FILES.items():
        filepath = assessment_dir / filename
        if filepath.exists():
            files_to_bundle.append(filepath)
            logger.info(f"  ✓ {filename} ({desc})")
        else:
            logger.warning(f"  ⚠ {filename} — missing (recommended: {desc})")

    # Find workbook
    workbooks = find_files_by_extension(assessment_dir, WORKBOOK_EXTENSIONS)
    if workbooks:
        files_to_bundle.extend(workbooks)
        for wb in workbooks:
            logger.info(f"  ✓ {wb.name} (Scoring workbook)")
    else:
        issues.append("CRITICAL: No scoring workbook (.xlsx) found")
        logger.error("  ✗ Scoring workbook — MISSING")

    # Find report
    reports = find_files_by_extension(assessment_dir, REPORT_EXTENSIONS)
    if reports:
        files_to_bundle.extend(reports)
        for r in reports:
            logger.info(f"  ✓ {r.name} (Assessment report)")
    else:
        issues.append("CRITICAL: No assessment report (.docx) found")
        logger.error("  ✗ Assessment report — MISSING")

    # Include any chart/image files
    for ext in (".png", ".jpg", ".svg", ".pdf"):
        for f in assessment_dir.glob(f"*{ext}"):
            files_to_bundle.append(f)
            logger.info(f"  + {f.name} (supplementary)")

    # Validate run_manifest can be parsed
    manifest_path = assessment_dir / "run_manifest.json"
    institution_name = "unknown"
    assessment_date = "unknown"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            institution_name = manifest.get("institution", {}).get("name", "unknown")
            assessment_date = manifest.get("assessment", {}).get("date", "unknown")
        except (json.JSONDecodeError, KeyError) as e:
            issues.append(f"HIGH: run_manifest.json parse error: {e}")

    # Check for critical issues
    critical_count = sum(1 for i in issues if i.startswith("CRITICAL"))
    if critical_count > 0:
        logger.error(f"\nBundle FAILED: {critical_count} critical files missing")
        for issue in issues:
            logger.error(f"  {issue}")
        return 1

    # Create bundle directory
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    checksums = {}
    for filepath in files_to_bundle:
        dest = bundle_dir / filepath.name
        shutil.copy2(filepath, dest)
        checksums[filepath.name] = compute_sha256(dest)

    # Write checksums manifest
    checksums_manifest = {
        "bundle_created": str(Path(sys.argv[0]).name),
        "institution": institution_name,
        "assessment_date": assessment_date,
        "file_count": len(checksums),
        "checksums": checksums,
    }
    with open(bundle_dir / "bundle_manifest.json", "w") as f:
        json.dump(checksums_manifest, f, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"Bundle created: {bundle_dir}")
    logger.info(f"  Institution: {institution_name}")
    logger.info(f"  Date: {assessment_date}")
    logger.info(f"  Files: {len(checksums)}")

    if issues:
        logger.warning(f"  Warnings: {len(issues)}")
        for issue in issues:
            logger.warning(f"    {issue}")

    # Create ZIP if requested
    if create_zip:
        zip_name = f"{institution_name.replace(' ', '_')}_{assessment_date}"
        zip_path = bundle_dir.parent / zip_name
        shutil.make_archive(str(zip_path), "zip", bundle_dir)
        logger.info(f"  ZIP: {zip_path}.zip")

    logger.info(f"{'='*60}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Bundle assessment deliverables for Layer 2 handoff")
    parser.add_argument("--assessment-dir", required=True, help="Directory with assessment outputs")
    parser.add_argument("--bundle-dir", required=True, help="Output directory for handoff bundle")
    parser.add_argument("--zip", action="store_true", help="Also create ZIP archive")
    args = parser.parse_args()

    assessment_dir = Path(args.assessment_dir)
    if not assessment_dir.exists():
        logger.error(f"Assessment directory not found: {assessment_dir}")
        sys.exit(1)

    bundle_dir = Path(args.bundle_dir)

    logger.info(f"Validating assessment outputs in: {assessment_dir}")
    sys.exit(validate_and_bundle(assessment_dir, bundle_dir, args.zip))


if __name__ == "__main__":
    main()
