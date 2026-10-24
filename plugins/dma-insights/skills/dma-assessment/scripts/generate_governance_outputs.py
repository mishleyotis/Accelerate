#!/usr/bin/env python3
"""
generate_governance_outputs.py — DMA Assessment Skill (Layer 1)

Extracts governance-compatible outputs from a completed scoring workbook:
  - run_manifest.json (Contract 1 — the ENGINE's manifest, run_manifest_v3,
    written through engine.assemble.write_manifest: nothing about the run is
    typed on the command line, it is all read from the workbook)
  - caps_applied_log.csv (Contract 2)
  - contradiction_log.csv (Contract 3)
  - evidence_index.csv (Contract 4)

Tabs are found through the engine's sheet contract, so a v7 workbook
(Evidence_Detail, P1_Subcap_Scoring, ...) is read as written. Measured
28-09-2026 (QA audit F-J01-006): this script looked for v3-era names and
produced an EMPTY evidence_index.csv with a warning on every v7 run; an
empty evidence index is now a refusal, not an export.

Usage:
    python generate_governance_outputs.py --workbook scored_workbook.xlsx \
        --output-dir ./governance_outputs/

Requires: openpyxl, pandas
"""

import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl required. Install: pip install openpyxl")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    pd = None  # Fallback to openpyxl-only mode

# The workbook's sheet contract and the manifest schema are the engine's
# (skills/dma-research/engine): one owner for both. Measured 28-09-2026
# (QA audit F-J01-006 / F-N01-019): this script required v3-era tab names
# and a manifest shape no writer produced, so every v7 run failed it.
_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "dma-research"
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))
try:
    from engine import assemble as _assemble
    from engine import contract as _contract
except Exception as _e:                                          # noqa: BLE001
    sys.exit(f"{Path(__file__).name}: the engine (skills/dma-research/engine) "
             f"is not importable, so neither the sheet contract nor the manifest "
             f"schema can be read: {_e}")
from engine.workbook import RunWorkbook as _RunWorkbook  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# === CONSTANTS: Layer 2 Contract Column Names (snake_case) ===

CAPS_COLUMNS = [
    "cap_id", "cap_type", "trigger_reason", "trigger_evidence",
    "affected_id", "raw_score", "cap_ceiling", "final_score", "score_delta"
]

CAPS_TYPE_ENUM = {
    "EVIDENCE_CEILING", "SENTIMENT", "REGULATORY", "CROSS_PILLAR",
    "ADJ_STALENESS", "ADJ_COMPLAINT", "ADJ_INCIDENT_MAJOR",
    "ADJ_INCIDENT_PATTERN", "CRITIC_CHALLENGE"
}

CONTRADICTION_COLUMNS = [
    "contradiction_id", "subcap_id", "evidence_a_id", "evidence_a_ers",
    "evidence_a_claim", "evidence_b_id", "evidence_b_ers", "evidence_b_claim",
    "resolution_rule", "winner", "justification", "confidence_impact",
    "flagged_in_report", "contradiction_type"
]

RESOLUTION_RULE_ENUM = {
    "ERS_RANKING", "T1T2_OVERRIDE", "TIEBREAKER",
    "CONSERVATIVE_DEFAULT", "UNRESOLVED"
}

EVIDENCE_COLUMNS = [
    "evidence_id", "source_name", "url", "tier",
    "ers_score", "publish_date", "subcaps_supported", "key_facts_count"
]

TIER_ENUM = {"T1", "T2", "T3", "T4", "T5"}

# Workbook column name mapping: Layer 1 PascalCase -> Layer 2 snake_case
CAPS_COL_MAP = {
    "Cap_ID": "cap_id", "CapLogID": "cap_id",
    "Cap_Type": "cap_type",
    "Trigger_Reason": "trigger_reason",
    "Trigger_Evidence": "trigger_evidence",
    "Affected_SubCap_or_Cap": "affected_id", "Affected_ID": "affected_id",
    "Raw_Score": "raw_score",
    "Cap_Ceiling": "cap_ceiling",
    "Final_Score": "final_score",
    "Score_Delta": "score_delta",
}

EVIDENCE_COL_MAP = {
    # the engine's Evidence_Detail (contract.EVIDENCE_COLUMNS) ...
    "E_ID": "evidence_id", "Source_URL": "url", "Date_Published": "publish_date",
    "SubCap_IDs": "subcaps_supported", "Fact_Count": "key_facts_count",
    # ... and the legacy names an older export used
    "Evidence_ID": "evidence_id",
    "Source_Name": "source_name", "Source": "source_name",
    "URL": "url",
    "Tier": "tier", "Evidence_Tier": "tier",
    "ERS_Score": "ers_score", "ERS": "ers_score",
    "Date_Period": "publish_date", "Publish_Date": "publish_date", "Date": "publish_date",
    "SubCaps_Supported": "subcaps_supported",
    "Fact_Summary": "key_facts_count", "Key_Facts_Count": "key_facts_count",
    "Facts_Count": "key_facts_count",
}


def load_workbook(path: str):
    """Load workbook and return openpyxl workbook object."""
    wb = openpyxl.load_workbook(path, data_only=True)
    logger.info(f"Loaded workbook: {path} ({len(wb.sheetnames)} sheets)")
    return wb


def find_sheet(wb, candidates: list[str]):
    """The sheet one of `candidates` names, resolved through the engine's
    contract: a canonical v7 name, an ingest alias or a legacy governance
    name all find the v7 tab."""
    for name in candidates:
        hit = _contract.resolve_tab(list(wb.sheetnames), name)
        if hit:
            return wb[hit]
    return None


def sheet_to_dicts(sheet) -> list[dict]:
    """Convert a worksheet to a list of dicts using first row as headers."""
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
    return [dict(zip(headers, row)) for row in rows[1:] if any(v is not None for v in row)]


def remap_columns(records: list[dict], col_map: dict) -> list[dict]:
    """Remap column names from Layer 1 PascalCase to Layer 2 snake_case."""
    remapped = []
    for rec in records:
        new_rec = {}
        for old_key, value in rec.items():
            new_key = col_map.get(old_key, old_key.lower().replace(" ", "_"))
            new_rec[new_key] = value
        remapped.append(new_rec)
    return remapped


def extract_caps_log(wb) -> list[dict]:
    """Extract caps_applied_log from workbook."""
    sheet = find_sheet(wb, ["Caps_Applied_Log", "Caps Applied Log", "CapsAppliedLog"])
    if not sheet:
        logger.warning("Caps_Applied_Log sheet not found — generating empty CSV")
        return []

    records = sheet_to_dicts(sheet)
    remapped = remap_columns(records, CAPS_COL_MAP)

    # Ensure all required columns exist
    for rec in remapped:
        for col in CAPS_COLUMNS:
            if col not in rec:
                rec[col] = ""
        # Calculate score_delta if missing
        if not rec.get("score_delta") and rec.get("raw_score") and rec.get("final_score"):
            try:
                rec["score_delta"] = round(float(rec["raw_score"]) - float(rec["final_score"]), 2)
            except (ValueError, TypeError):
                pass

    logger.info(f"Extracted {len(remapped)} cap entries")
    return remapped


def extract_evidence_index(wb) -> list[dict]:
    """Extract evidence_index from workbook."""
    sheet = find_sheet(wb, ["Evidence_Detail", "Evidence_Index", "Evidence Index",
                            "EvidenceIndex"])
    if not sheet:
        raise SystemExit(
            "REFUSED: the workbook has no evidence sheet (Evidence_Detail or an "
            "alias the contract recognises). An empty evidence_index.csv would "
            "report the run as unevidenced, which is a claim, not an absence.")

    records = sheet_to_dicts(sheet)
    if not records:
        raise SystemExit(
            f"REFUSED: the evidence sheet {sheet.title!r} has no rows. An empty "
            f"evidence_index.csv would report the run as unevidenced; a scored "
            f"run without evidence is a defect to fix, not a state to export.")
    remapped = remap_columns(records, EVIDENCE_COL_MAP)

    # Handle Fact_Summary -> key_facts_count conversion
    for rec in remapped:
        kfc = rec.get("key_facts_count", "")
        if isinstance(kfc, str) and not kfc.isdigit():
            # Count facts in summary text (rough heuristic: count sentences or semicolons)
            count = max(1, len(str(kfc).split(";")) if kfc else 0)
            rec["key_facts_count"] = count

        for col in EVIDENCE_COLUMNS:
            if col not in rec:
                rec[col] = ""

    logger.info(f"Extracted {len(remapped)} evidence items")
    return remapped


def extract_contradiction_log(wb) -> list[dict]:
    """Extract contradiction_log from workbook."""
    sheet = find_sheet(wb, ["Contradiction_Log", "Contradiction Log", "ContradictionLog"])
    if not sheet:
        logger.warning("Contradiction_Log sheet not found — generating empty CSV")
        return []

    records = sheet_to_dicts(sheet)
    # Layer 1 uses different column names; remap as best we can
    contradiction_col_map = {
        "Contradiction_ID": "contradiction_id",
        "SubCap_ID": "subcap_id", "Subcap_ID": "subcap_id",
        "Fact_A_ID": "evidence_a_id", "Evidence_A_ID": "evidence_a_id",
        "Fact_A_Source": "evidence_a_claim", "Evidence_A_Claim": "evidence_a_claim",
        "Evidence_A_ERS": "evidence_a_ers", "Fact_A_ERS": "evidence_a_ers",
        "Fact_B_ID": "evidence_b_id", "Evidence_B_ID": "evidence_b_id",
        "Fact_B_Source": "evidence_b_claim", "Evidence_B_Claim": "evidence_b_claim",
        "Evidence_B_ERS": "evidence_b_ers", "Fact_B_ERS": "evidence_b_ers",
        "Resolution": "resolution_rule", "Resolution_Rule": "resolution_rule",
        "Winning_Fact": "winner", "Winner": "winner",
        "Resolution_Rationale": "justification", "Justification": "justification",
        "Score_Impact": "confidence_impact", "Confidence_Impact": "confidence_impact",
        "Flagged_In_Report": "flagged_in_report",
        "Contradiction_Type": "contradiction_type",
        "Capabilities_Affected": "capabilities_affected",
    }

    remapped = remap_columns(records, contradiction_col_map)

    for rec in remapped:
        # Ensure all required columns exist
        for col in CONTRADICTION_COLUMNS:
            if col not in rec:
                rec[col] = ""

        # Default flagged_in_report for unresolved
        if str(rec.get("resolution_rule", "")).upper() == "UNRESOLVED":
            if not rec.get("flagged_in_report"):
                rec["flagged_in_report"] = "true"

    logger.info(f"Extracted {len(remapped)} contradictions")
    return remapped


def build_run_manifest(workbook_path) -> dict:
    """The run's manifest, from the workbook, in the engine's ONE shape.

    Institution, evidence mode, catalogue and engine versions, gates, scores
    and evidence counts are the workbook's own; the CLI types none of them."""
    wb = _RunWorkbook(Path(workbook_path))
    return _assemble.manifest_doc(wb, status="COMPLETE", stage="GOVERNANCE_EXPORT")


def write_csv(records: list[dict], columns: list[str], path: Path):
    """Write records to CSV with specified column order."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    logger.info(f"Wrote {len(records)} rows to {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Layer 2 governance outputs from scored workbook")
    parser.add_argument("--workbook", required=True, help="Path to scored workbook (.xlsx)")
    parser.add_argument("--output-dir", required=True, help="Output directory for governance files")
    # Accepted for compatibility with older invocations and IGNORED: every
    # one of these is read from the workbook now (F-A03-020: the version
    # flags defaulted to "5.0" and were written into the manifest as fact).
    for flag in ("--institution-name", "--institution-id", "--sub-vertical",
                 "--size-tier", "--primary-regulator", "--geography",
                 "--evidence-mode", "--assessor", "--tool-version",
                 "--rubric-version", "--taxonomy-version", "--template-version",
                 "--peer-methodology-version"):
        parser.add_argument(flag, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()
    ignored = [f for f in ("institution_name", "institution_id", "sub_vertical",
                           "size_tier", "primary_regulator", "geography",
                           "evidence_mode", "assessor", "tool_version",
                           "rubric_version", "taxonomy_version",
                           "template_version", "peer_methodology_version")
               if getattr(args, f) is not None]
    if ignored:
        logger.warning("ignored %s: the manifest is read from the workbook, "
                       "not typed", ", ".join("--" + f.replace("_", "-") for f in ignored))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load workbook
    wb = load_workbook(args.workbook)

    # Extract governance outputs
    caps_records = extract_caps_log(wb)
    evidence_records = extract_evidence_index(wb)
    contradiction_records = extract_contradiction_log(wb)

    # The manifest: the engine's, from the workbook
    manifest = build_run_manifest(args.workbook)

    # Write outputs
    manifest_path = output_dir / "run_manifest.json"
    caps_path = output_dir / "caps_applied_log.csv"
    evidence_path = output_dir / "evidence_index.csv"
    contradiction_path = output_dir / "contradiction_log.csv"

    write_csv(caps_records, CAPS_COLUMNS, caps_path)
    write_csv(evidence_records, EVIDENCE_COLUMNS, evidence_path)
    write_csv(contradiction_records, CONTRADICTION_COLUMNS, contradiction_path)
    try:
        _assemble.write_manifest(manifest_path, manifest)
    except _assemble.ManifestInvalid as e:
        logger.error("%s", e)
        return 1
    logger.info("Wrote run_manifest.json (%s)", manifest["schema_version"])

    # Summary
    logger.info("=== Governance outputs generated ===")
    logger.info(f"  {len(caps_records)} cap entries")
    logger.info(f"  {len(contradiction_records)} contradictions")
    logger.info(f"  {len(evidence_records)} evidence items")
    logger.info("  Manifest validation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
