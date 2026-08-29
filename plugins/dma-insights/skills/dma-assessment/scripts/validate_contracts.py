#!/usr/bin/env python3
"""
validate_contracts.py — DMA Assessment Skill (Layer 1)

Validates governance outputs against Layer 2 interface contract schemas.
Run this BEFORE handoff to Layer 2 to catch schema violations early.

Usage:
    python validate_contracts.py --dir ./governance_outputs/

Checks:
  - run_manifest.json: Schema completeness, validation rules, field types
  - caps_applied_log.csv: Column names, enum values, math integrity
  - contradiction_log.csv: Column names, enum values, flagging rules
  - evidence_index.csv: Column names, tier enums, ERS validity
  - Cross-file referential integrity

Exit codes: 0 = PASS, 1 = FAIL (CRITICAL issues), 2 = PASS_WITH_NOTES (warnings only)
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _catalogue_categories():
    """The category ids in the pinned catalogue, or a refusal.

    Read rather than listed: a hand-kept set is a second place for the
    taxonomy to live, and AUD-0051 is what happens when the two disagree."""
    import json
    import re
    from pathlib import Path as _P
    here = _P(__file__).resolve()
    for anc in here.parents:
        cand = anc / "packages" / "shared" / "catalogue_v70_tier.json"
        if cand.is_file():
            tier = json.loads(cand.read_text())["tier"]
            return sorted({m.group(0) for c in tier
                           if (m := re.match(r"P\dC\d+", c))})
        cand = anc / "skills" / "dma-research" / "engine" / "data" / \
            "catalogue_v70_tier.json"
        if cand.is_file():
            tier = json.loads(cand.read_text())["tier"]
            return sorted({m.group(0) for c in tier
                           if (m := re.match(r"P\dC\d+", c))})
    raise SystemExit(
        "validate_contracts: the catalogue is not resolvable from "
        f"{here}, so the category set cannot be counted. It is not "
        "hardcoded on purpose — see AUD-0051.")


class ContractValidator:
    """Validates governance output files against Layer 2 interface contracts."""

    def __init__(self, output_dir: str):
        self.dir = Path(output_dir)
        self.issues = []  # (severity, contract, check, message)

    def fail(self, contract: str, check: str, msg: str):
        self.issues.append(("CRITICAL", contract, check, msg))

    def warn(self, contract: str, check: str, msg: str):
        self.issues.append(("HIGH", contract, check, msg))

    def note(self, contract: str, check: str, msg: str):
        self.issues.append(("MEDIUM", contract, check, msg))

    # === Contract 1: run_manifest.json ===

    def validate_manifest(self) -> dict | None:
        path = self.dir / "run_manifest.json"
        if not path.exists():
            self.fail("C1", "existence", "run_manifest.json not found")
            return None

        try:
            with open(path) as f:
                m = json.load(f)
        except json.JSONDecodeError as e:
            self.fail("C1", "parse", f"Invalid JSON: {e}")
            return None

        # Required nested keys (hybrid v2.0)
        required_paths = [
            ("$schema",),
            ("run_id",),
            ("institution", "name"), ("institution", "id"),
            ("institution", "sub_vertical"), ("institution", "size_tier"),
            ("institution", "primary_regulator"), ("institution", "geography"),
            ("assessment", "date"), ("assessment", "evidence_mode"),
            ("assessment", "assessor"), ("assessment", "tool_version"),
            ("assessment", "status"),
            ("versions", "rubric"), ("versions", "taxonomy"),
            ("scores", "overall"), ("scores", "pillars"),
            ("scores", "categories"),
            ("evidence_metrics", "total_items"),
            ("evidence_metrics", "tier_distribution"),
            ("evidence_metrics", "avg_ers"),
            ("evidence_metrics", "median_ers"),
            ("evidence_metrics", "sources_per_subcap_avg"),
            ("evidence_metrics", "single_source_subcap_count"),
            ("evidence_metrics", "no_evidence_subcap_count"),
            ("evidence_metrics", "document_count"),
            ("scoring_metrics", "caps_applied_count"),
            ("scoring_metrics", "adjustments_applied_count"),
            ("scoring_metrics", "dependency_caps_triggered"),
            ("scoring_metrics", "contradictions_found"),
            ("scoring_metrics", "contradictions_unresolved"),
            ("scoring_metrics", "na_capabilities"),
            ("scoring_metrics", "peer_count"),
            ("confidence_distribution",),
            ("qa", "verdict"), ("qa", "regression_tests"),
            ("qa", "issues_found"), ("qa", "critical_issues"),
            ("files_generated",),
        ]

        for path_parts in required_paths:
            obj = m
            for part in path_parts:
                if not isinstance(obj, dict) or part not in obj:
                    self.fail("C1", "schema", f"Missing field: {'.'.join(path_parts)}")
                    obj = None
                    break
                obj = obj[part]

        # Validation rule 1: overall = weighted avg of pillars
        scores = m.get("scores", {})
        pillars = scores.get("pillars", {})
        if pillars and all(isinstance(v, (int, float)) for v in pillars.values()):
            weights = {"P1": 0.25, "P2": 0.25, "P3": 0.25, "P4": 0.25}
            weighted_avg = sum(pillars.get(p, 0) * weights.get(p, 0.25) for p in weights)
            overall = scores.get("overall", 0)
            if isinstance(overall, (int, float)) and abs(weighted_avg - overall) > 0.02:
                self.fail("C1", "VR1",
                          f"overall ({overall}) != weighted pillar avg ({weighted_avg:.2f})")

        # Validation rule 2: total_items = sum of tier_distribution
        em = m.get("evidence_metrics", {})
        td = em.get("tier_distribution", {})
        if td and isinstance(em.get("total_items"), int):
            tier_sum = sum(v for v in td.values() if isinstance(v, (int, float)))
            if tier_sum != em["total_items"]:
                self.fail("C1", "VR2",
                          f"total_items ({em['total_items']}) != tier sum ({tier_sum})")

        # Validation rule 3: confidence_distribution sum = total subcap count (soft check)
        cd = m.get("confidence_distribution", {})
        if cd:
            conf_sum = sum(v for v in cd.values() if isinstance(v, (int, float)))
            if conf_sum == 0:
                self.note("C1", "VR3", "confidence_distribution sums to 0 — may be unpopulated")

        # Every category the CATALOGUE holds — counted, not listed.
        #
        # AUD-0051: this was a hand-kept set of 17 including P1C5, the
        # category v7.0 retired and every one of whose cells resolves
        # NOT_COMPARABLE. A complete v7.0 run was reported as missing a
        # category it correctly does not have, and the count fed coverage
        # maths that then read over 100%.
        expected_cats = set(_catalogue_categories())
        missing_cats = expected_cats - set(cats.keys())
        if missing_cats:
            self.warn("C1", "categories", f"Missing category scores: {sorted(missing_cats)}")

        # Enum checks
        em_mode = m.get("assessment", {}).get("evidence_mode", "")
        if em_mode not in ("PUBLIC", "INTERNAL", "HYBRID"):
            self.fail("C1", "enum", f"Invalid evidence_mode: {em_mode}")

        size = m.get("institution", {}).get("size_tier", "")
        if size not in ("Mega", "Large", "Medium", "Small", "Micro", "Nano"):
            self.fail("C1", "enum", f"Invalid size_tier: {size}")

        sub_vert = m.get("institution", {}).get("sub_vertical", "")
        valid_sub_verts = {
            "Credit Unions", "Regional Banks", "Commercial Lending", "CIB",
            "Insurance Carriers", "Insurance Brokerages",
            "Wealth Managers / RIAs", "Asset Management",
        }
        if sub_vert and sub_vert not in valid_sub_verts:
            self.warn("C1", "enum", f"sub_vertical '{sub_vert}' not in canonical enum: {sorted(valid_sub_verts)}")

        status = m.get("assessment", {}).get("status", "")
        valid_statuses = {"IN_PROGRESS", "SCORING_COMPLETE", "REPORT_DRAFT", "AWAITING_REVIEW", "DELIVERED"}
        if status and status not in valid_statuses:
            self.fail("C1", "enum", f"Invalid assessment.status: {status}")

        # v2 schema check
        schema_val = m.get("$schema", "")
        if schema_val != "run_manifest_v2":
            self.warn("C1", "schema_version",
                      f"$schema is '{schema_val}', expected 'run_manifest_v2' — may be v1 format")

        # run_id format check
        import re
        run_id = m.get("run_id", "")
        if run_id and not re.match(r"^DMA-[A-Z0-9]{2,6}-[0-9]{8}-[0-9]{4}$", run_id):
            self.warn("C1", "run_id", f"run_id '{run_id}' does not match expected pattern")

        # qa.issues_found type check (must be object in v2)
        qa = m.get("qa", {})
        issues_found = qa.get("issues_found")
        if isinstance(issues_found, int):
            self.warn("C1", "issues_found",
                      "qa.issues_found is integer — v2 requires object {CRITICAL, HIGH, MEDIUM, LOW}")
        elif isinstance(issues_found, dict):
            if qa.get("critical_issues", 0) != issues_found.get("CRITICAL", 0):
                self.fail("C1", "VR4",
                          f"qa.critical_issues ({qa.get('critical_issues')}) != "
                          f"qa.issues_found.CRITICAL ({issues_found.get('CRITICAL')})")

        return m

    # === Contract 2: caps_applied_log.csv ===

    def validate_caps_log(self) -> list[dict]:
        path = self.dir / "caps_applied_log.csv"
        if not path.exists():
            self.fail("C2", "existence", "caps_applied_log.csv not found")
            return []

        records = self._read_csv(path, "C2")
        if not records:
            return []

        expected_cols = {"cap_id", "cap_type", "trigger_reason", "trigger_evidence",
                         "affected_id", "raw_score", "cap_ceiling", "final_score", "score_delta"}
        actual_cols = set(records[0].keys())
        missing = expected_cols - actual_cols
        if missing:
            self.fail("C2", "columns", f"Missing columns: {missing}")

        type_enum = {"EVIDENCE_CEILING", "SENTIMENT", "REGULATORY", "CROSS_PILLAR",
                     "ADJ_STALENESS", "ADJ_COMPLAINT", "ADJ_INCIDENT_MAJOR",
                     "ADJ_INCIDENT_PATTERN", "CRITIC_CHALLENGE"}

        for i, rec in enumerate(records):
            row_id = rec.get("cap_id", f"row_{i+1}")

            # Enum check
            cap_type = str(rec.get("cap_type", "")).strip()
            if cap_type and cap_type not in type_enum:
                self.warn("C2", f"enum_{row_id}", f"Invalid cap_type: {cap_type}")

            # Math check: score_delta = raw - final
            try:
                raw = float(rec.get("raw_score", 0))
                final = float(rec.get("final_score", 0))
                delta = float(rec.get("score_delta", 0))
                if abs((raw - final) - delta) > 0.01:
                    self.fail("C2", f"math_{row_id}",
                              f"score_delta ({delta}) != raw-final ({raw-final:.2f})")
            except (ValueError, TypeError):
                pass

            # final_score <= cap_ceiling
            try:
                final = float(rec.get("final_score", 0))
                ceiling = float(rec.get("cap_ceiling", 999))
                if final > ceiling + 0.01:
                    self.fail("C2", f"ceiling_{row_id}",
                              f"final_score ({final}) > cap_ceiling ({ceiling})")
            except (ValueError, TypeError):
                pass

            # ADJ_ types must have trigger_evidence
            if cap_type.startswith("ADJ_") and not rec.get("trigger_evidence"):
                self.warn("C2", f"adj_evidence_{row_id}",
                          f"{cap_type} missing trigger_evidence")

        return records

    # === Contract 3: contradiction_log.csv ===

    def validate_contradiction_log(self) -> list[dict]:
        path = self.dir / "contradiction_log.csv"
        if not path.exists():
            self.fail("C3", "existence", "contradiction_log.csv not found")
            return []

        records = self._read_csv(path, "C3")
        if not records:
            return []

        expected_cols = {"contradiction_id", "subcap_id", "evidence_a_id", "evidence_a_ers",
                         "evidence_a_claim", "evidence_b_id", "evidence_b_ers",
                         "evidence_b_claim", "resolution_rule", "winner", "justification",
                         "confidence_impact", "flagged_in_report", "contradiction_type"}
        actual_cols = set(records[0].keys())
        missing = expected_cols - actual_cols
        if missing:
            self.fail("C3", "columns", f"Missing columns: {missing}")

        rule_enum = {"ERS_RANKING", "T1T2_OVERRIDE", "TIEBREAKER",
                     "CONSERVATIVE_DEFAULT", "UNRESOLVED"}
        type_enum = {"HARD", "SOFT"}

        for i, rec in enumerate(records):
            row_id = rec.get("contradiction_id", f"row_{i+1}")

            rule = str(rec.get("resolution_rule", "")).strip().upper()
            if rule and rule not in rule_enum:
                self.warn("C3", f"enum_{row_id}", f"Invalid resolution_rule: {rule}")

            # contradiction_type must be HARD or SOFT
            ctr_type = str(rec.get("contradiction_type", "")).strip().upper()
            if ctr_type and ctr_type not in type_enum:
                self.warn("C3", f"type_{row_id}",
                          f"Invalid contradiction_type: {ctr_type} — expected HARD or SOFT")

            rule = str(rec.get("resolution_rule", "")).strip().upper()
            if rule and rule not in rule_enum:
                self.warn("C3", f"enum_{row_id}", f"Invalid resolution_rule: {rule}")

            # UNRESOLVED must be flagged in report
            if rule == "UNRESOLVED":
                flagged = str(rec.get("flagged_in_report", "")).strip().lower()
                if flagged not in ("true", "1", "yes"):
                    self.fail("C3", f"flag_{row_id}",
                              "UNRESOLVED contradiction not flagged_in_report")

            # Winner must be evidence_a_id or evidence_b_id or NONE
            winner = str(rec.get("winner", "")).strip()
            a_id = str(rec.get("evidence_a_id", "")).strip()
            b_id = str(rec.get("evidence_b_id", "")).strip()
            if winner and winner not in (a_id, b_id, "NONE", ""):
                self.warn("C3", f"winner_{row_id}",
                          f"winner ({winner}) not in {{evidence_a_id, evidence_b_id, NONE}}")

        return records

    # === Contract 4: evidence_index.csv ===

    def validate_evidence_index(self) -> list[dict]:
        path = self.dir / "evidence_index.csv"
        if not path.exists():
            self.fail("C4", "existence", "evidence_index.csv not found")
            return []

        records = self._read_csv(path, "C4")
        if not records:
            return []

        expected_cols = {"evidence_id", "source_name", "url", "tier",
                         "ers_score", "publish_date", "subcaps_supported",
                         "key_facts_count"}
        actual_cols = set(records[0].keys())
        missing = expected_cols - actual_cols
        if missing:
            self.fail("C4", "columns", f"Missing columns: {missing}")

        tier_enum = {"T1", "T2", "T3", "T4", "T5"}

        for i, rec in enumerate(records):
            row_id = rec.get("evidence_id", f"row_{i+1}")

            tier = str(rec.get("tier", "")).strip().upper()
            if tier and tier not in tier_enum:
                self.warn("C4", f"tier_{row_id}", f"Invalid tier: {tier}")

            try:
                ers = float(rec.get("ers_score", 0))
                if ers < 0 or ers > 5:
                    self.warn("C4", f"ers_{row_id}", f"ERS out of range: {ers}")
            except (ValueError, TypeError):
                pass

        return records

    # === Cross-file referential integrity ===

    def validate_cross_references(self, manifest, caps, contradictions, evidence):
        if not manifest:
            return

        evidence_ids = {str(r.get("evidence_id", "")).strip() for r in evidence}

        # All evidence IDs in caps should exist in evidence index
        for rec in caps:
            trigger_ev = str(rec.get("trigger_evidence", ""))
            for eid in trigger_ev.replace(",", " ").split():
                eid = eid.strip().split(":")[0]  # Handle E-001:F1 format
                if eid and eid.startswith("E-") and eid not in evidence_ids:
                    self.note("XREF", "caps_evidence",
                              f"Cap {rec.get('cap_id')} references unknown evidence: {eid}")

        # All evidence IDs in contradictions should exist
        for rec in contradictions:
            for field in ("evidence_a_id", "evidence_b_id"):
                eid = str(rec.get(field, "")).strip().split(":")[0]
                if eid and eid.startswith("E-") and eid not in evidence_ids:
                    self.note("XREF", "contradiction_evidence",
                              f"Contradiction {rec.get('contradiction_id')} references unknown evidence: {eid}")

    # === Helpers ===

    def _read_csv(self, path: Path, contract: str) -> list[dict]:
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            self.fail(contract, "parse", f"CSV parse error: {e}")
            return []

    def run_all(self) -> tuple[str, list]:
        """Run all validations and return (verdict, issues)."""
        logger.info(f"Validating governance outputs in: {self.dir}")

        manifest = self.validate_manifest()
        caps = self.validate_caps_log()
        contradictions = self.validate_contradiction_log()
        evidence = self.validate_evidence_index()
        self.validate_cross_references(manifest, caps, contradictions, evidence)

        # === Contract 8: reasoning_chain_log.json ===
        rcl_path = self.dir / "reasoning_chain_log.json"
        if not rcl_path.exists():
            self.warn("C8", "existence",
                      "reasoning_chain_log.json not found — Layer 2 reasoning audit will be limited")
        else:
            try:
                with open(rcl_path, encoding="utf-8") as f:
                    rcl = json.load(f)

                # Validate structure
                subcaps = rcl.get("subcaps", [])
                summary = rcl.get("summary", {})
                if not subcaps:
                    self.fail("C8", "structure", "reasoning_chain_log.json has empty subcaps array")
                elif not summary:
                    self.fail("C8", "structure", "reasoning_chain_log.json missing summary object")
                else:
                    # summary.decision_paths_logged must equal len(subcaps)
                    logged = summary.get("decision_paths_logged", 0)
                    if logged != len(subcaps):
                        self.warn("C8", "count_mismatch",
                                  f"summary.decision_paths_logged ({logged}) != subcaps array length ({len(subcaps)})")

                    # Spot-check: every subcap entry has required fields
                    required_subcap_keys = {"id", "decision_path", "evidence_considered",
                                            "ceiling_calc", "m_level_match", "final_score"}
                    for entry in subcaps[:10]:  # Sample first 10
                        missing = required_subcap_keys - set(entry.keys())
                        if missing:
                            self.warn("C8", f"fields_{entry.get('id', '?')}",
                                      f"Missing keys in reasoning chain entry: {missing}")
                            break

                    # Cross-reference: evidence IDs should exist in evidence_index
                    if evidence:
                        evidence_ids_set = {str(r.get("evidence_id", "")).strip()
                                            for r in evidence}
                        for entry in subcaps[:20]:  # Sample first 20
                            for ref in entry.get("evidence_considered", []):
                                eid = str(ref).split(":")[0]
                                if eid and eid.startswith("E-") and eid not in evidence_ids_set:
                                    self.note("C8", f"xref_{entry.get('id', '?')}",
                                              f"Reasoning chain references unknown evidence: {eid}")
                                    break  # One note per entry is enough

            except json.JSONDecodeError as e:
                self.fail("C8", "parse", f"reasoning_chain_log.json is not valid JSON: {e}")
            except Exception as e:
                self.fail("C8", "read", f"Error reading reasoning_chain_log.json: {e}")

        # Verdict
        critical_count = sum(1 for s, *_ in self.issues if s == "CRITICAL")
        high_count = sum(1 for s, *_ in self.issues if s == "HIGH")

        if critical_count > 0:
            verdict = "FAIL"
        elif high_count > 0:
            verdict = "PASS_WITH_NOTES"
        elif self.issues:
            verdict = "PASS_WITH_NOTES"
        else:
            verdict = "PASS"

        # Report
        logger.info(f"\n{'='*60}")
        logger.info(f"CONTRACT VALIDATION: {verdict}")
        logger.info(f"  CRITICAL: {critical_count}")
        logger.info(f"  HIGH: {high_count}")
        logger.info(f"  MEDIUM: {sum(1 for s, *_ in self.issues if s == 'MEDIUM')}")
        logger.info(f"{'='*60}")

        for sev, contract, check, msg in self.issues:
            logger.info(f"  [{sev}] {contract}.{check}: {msg}")

        return verdict, self.issues


def main():
    parser = argparse.ArgumentParser(description="Validate governance outputs against Layer 2 contracts")
    parser.add_argument("--dir", required=True, help="Directory containing governance output files")
    args = parser.parse_args()

    validator = ContractValidator(args.dir)
    verdict, issues = validator.run_all()

    if verdict == "FAIL":
        sys.exit(1)
    elif verdict == "PASS_WITH_NOTES":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
