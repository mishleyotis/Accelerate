---
name: dma-governance
description: >
  Conducts read-only audits of completed DMA (Digital Maturity Assessment) workbooks and
  reports, performs calibration analysis, runs regression checks, and generates governance
  outputs including issue registers, QA verdicts, and patch blocks. ALWAYS use this skill
  when the user mentions: DMA audit, DMA review, assessment QA, governance review, calibration,
  drift analysis, score comparison across assessments, quality check on a DMA workbook,
  patch block, cross-assessment consistency, regression testing a completed assessment,
  or reviewing assessment quality. Also trigger when the user uploads a completed DMA
  workbook (.xlsx) and asks to "check it", "review it", "audit it", or "validate it".
  Layer 2 governance companion to the DMA Assessment Skill (Layer 1).
  v2.4: 108 checks (91 automated + 17 LLM). New: report citation density, evidence
  completeness, anti-generic detection, internal evidence audit, peer data validation,
  file existence. Aligned with assessment skill v5.4.
---

# DMA Governance Skill v2.4

**Purpose**: Read-only audit of completed DMA assessments. Enforces standards, detects issues,
measures calibration, validates proof structures — without modifying scores.

**v2.4 Changes:** Report-level citation density check (catches zero-citation reports). Evidence
completeness audit (URL, ERS, excerpt). Anti-generic content detection. Internal evidence tier
validation. Peer data presence in report. Output artifact existence checks. Strengthened
cross-document ID consistency. Aligned with assessment skill v5.4.

**Architecture**: Layer 2 of 3. Layer 1 (Assessment) produces → **Layer 2 (this) audits** → Layer 3 (Repository) stores.

---

## Core Principle: READ-ONLY

Outputs only: Issue Register, QA Verdict, Patch Block, Calibration Metrics. All are proposals. Fixes executed by Layer 1 re-run or human decision.

---

## Execution: Script + LLM Two-Pass Model

**Pass 1 (Python):** 79 deterministic checks — mathematical, structural, pattern-based.
**Pass 2 (LLM):** 12 judgment checks — semantic, argumentation, synthesis.

### Prerequisites
```bash
pip install openpyxl python-docx --break-system-packages
```

### Scripts

| Script | Workflow | Purpose |
|--------|----------|---------|
| `scripts/gov_auditor.py` | A | 79 automated checks (IV, SI, ET, AG, CD, CE, CL, RC, DC) |
| `scripts/calibration_engine.py` | B | Cross-assessment calibration + drift detection |
| `scripts/regression_runner.py` | C | Golden case regression testing |

---

## Interface Contracts

**Inputs from Layer 1** (all required):
- Scoring workbook (.xlsx) with Columns S/T proof structure
- Report (.docx)
- `run_manifest.json` (run_manifest_v2 schema)
- `caps_applied_log.csv` (including CRITIC_CHALLENGE type)
- `contradiction_log.csv` (including contradiction_type: HARD/SOFT)
- `evidence_index.csv` (full inventory with ERS)
- `reasoning_chain_log.json` (Contract 8 — decision trail per subcap)
- Critic_Log (worksheet or sheet)
- `02_peers/` directory: peer_scores, peer_synthesis.md, peer_comparison_table.csv (v5.4+)
- `04_scoring/exports/` directory: 6 canonical export CSVs (v5.4+)

**Outputs from Layer 2:**
- `issue_register.csv` — structured issues with fix instructions
- `qa_verdict.json` — per `schemas/qa_verdict.schema.json`
- `patch_block.md` — program learning updates

---

## Workflow A: Single Assessment Audit

### Step 0: Setup
```bash
export ASSESSMENT_DIR="<path>"
export GOV_OUTPUT="$ASSESSMENT_DIR/governance_output"
mkdir -p "$GOV_OUTPUT"
```

### Step 1: Pass 1 — Automated Checks
```bash
python scripts/gov_auditor.py "$ASSESSMENT_DIR" --output-dir "$GOV_OUTPUT"
```
Produces: `check_results.json`, `preliminary_issues.csv`, `audit_summary.json`.
**CRITICAL IV failures → STOP. Do not proceed to Pass 2.**

### Step 1.5: Artifact Provenance & Evidence ID Integrity (NEW)

These catch the most common "ship-stopper" defects between automated and LLM passes:

**AP-01: Run ID Consistency (STRENGTHENED)**
Extract `run_id` from EVERY artifact: run_manifest.json, workbook Run_Metadata sheet,
report cover page text, report header text, Appendix C metadata table, all CSV file header
comments, chart footer text, qa_verdict.json.
**FAIL if:** Any mismatch across ANY artifact = mixed-run output. CRITICAL severity.

**AP-02: Taxonomy Count Reconciliation**
Compare subcap counts across: run_manifest `subcap_count_expected`, workbook total rows, evidence_index unique subcap IDs, report narrative claims, Appendix A7 denominator.
**FAIL if:** Any divergence. Prevents "707 vs 850" defect.

**AP-03: Evidence ID Registry Validation (CRITICAL)**
Build authoritative list from `evidence_index.csv`. Cross-check every reference in: workbook Column K, report citations, issue register, caps_applied_log.trigger_evidence, contradiction_log evidence IDs.
**FAIL if:** Any referenced ID not in registry.
Output: `qa_evidence_reference_failures.csv` (artifact_name, location, referenced_id, exists_in_registry, suggested_fix).

**AP-04: Evidence ID Range Enforcement**
No range-style references ("E-087 through E-095"). All must be explicit enumerations.
**FAIL if:** Any range-style reference in final artifacts.

**AP-05: Score State Propagation Check**
Verify: `final_score ≤ capped_score ≤ raw_score`. Category/pillar tables use `final_score`. Recompute pillar from categories: must match ±0.01.
**FAIL if:** Propagation violated or rollup mismatch.

**AP-06: Report Citation Density (NEW — CRITICAL)**
Load report .docx → extract all E-xxx patterns → count unique E-IDs.
**FAIL if:** Total unique E-IDs < 30. Executive Summary < 5 citations. Any pillar deep dive < 2 citations per capability. Any recommendation < 1 citation.
Output: `qa_citation_density_report.csv` (section, e_id_count, minimum_required, pass_fail).
**This check catches the zero-citation report issue documented in QA-007/QA-009.**

**AP-07: Evidence Mode Consistency (NEW — HIGH)**
Extract EVIDENCE_MODE from: run_manifest.json, workbook Run_Metadata, report cover page text, Appendix C metadata.
**FAIL if:** Any mismatch across artifacts.

### Step 1.6: Evidence Completeness Audit (NEW)

**EC-01: URL Validity** — Every evidence item in workbook Column L has a specific URL. Blank or "multiple searches" = FAIL.
**EC-02: ERS Population** — Every evidence item in Column M has an ERS score in range [1.0, 5.0].
**EC-03: Excerpt Length** — Column U ≥ 50 characters for every scored subcap.
**EC-04: Source Attribution** — Column V non-empty for every scored subcap.
**EC-05: Tier Classification** — Column M contains valid T1-T5 designation for every evidence item.
**FAIL if:** >5% of scored subcaps fail any EC check. Severity: CRITICAL.

### Step 1.7: Output Artifact Existence Check (NEW)

**FE-01: Mandatory file checklist:**
- `run_manifest.json` — CRITICAL
- `02_peers/` directory with ≥3 peer files (peer_scores, peer_synthesis, peer_comparison) — HIGH
- `04_scoring/Workbook.xlsx` — CRITICAL
- `04_scoring/exports/` with 6 CSV files — CRITICAL
- `07_deliverables/Report.docx` — CRITICAL
- `08_qa/qa_verdict.json` — HIGH
- `caps_applied_log.csv` — HIGH
- `contradiction_log.csv` — HIGH
- `evidence_index.csv` — HIGH
- `reasoning_chain_log.json` — HIGH
**FAIL if:** Any CRITICAL file missing. PASS_WITH_NOTES if HIGH file missing.

### Step 2: Pass 2 — LLM Deep Reasoning

Read `audit_summary.json`, then perform judgment checks per `scripts/llm_reasoning_prompts.md`:

**PV-01: Proof Structure Completeness**
Verify across Columns R, S, T and reasoning_chain_log.json: Claims (C1-C3), Evidence Links (E#:F#), Rule Links (RuleID), Counterclaim, Constraint Satisfaction.
Cross-validate: R score matches T JSON final_score. S claim count matches T claims[] length. Reasoning chain final_score matches workbook.
PASS: ≥95% complete | WARNINGS: 80-94% | FAIL: <80%

**BEFORE scoring PV-01, establish whether its INPUTS EXIST — and never
accept their absence as drift.** Measured on a promoted assessment: 0 of
709 rows carried columns R/S/T, `reasoning_chain_log.json` did not exist,
PV-01 computed 0% against an 80% floor, and the verdict recorded the
finding under `schema_drift_accepted` and returned PASS_WITH_NOTES. That
run reached a regulated client's dashboard asserting Differentiating
trade surveillance on a subsidiary's officer list. A check that is always
skipped is not a check, and `schema_drift_accepted` is the mechanism that
skipped it.

So:

* If columns R/S/T are absent on **every** row, this is NOT a PV-01
  score of 0%. It is a **FORMAT CONTRADICTION**, and it is the audit's
  headline finding: `dma-assessment` declares an 11-column layout
  canonical and the 22-column R/S/T layout legacy and forbidden, while
  this check audits R/S/T. Emit issue `GOV-FORMAT-01` at **CRITICAL**,
  naming both skills, and set the verdict to **FAIL** — not
  PASS_WITH_NOTES. The two skills must be reconciled by their owner; an
  auditor that scores 0% and passes is an auditor reporting that it did
  not run.
* If the columns are PRESENT and incomplete, score PV-01 normally.
* `schema_drift_accepted` may never be used to dispose of a proof check.
  Recording that a check's inputs are out of scope is recording that the
  check did not run, and a verdict that says PASS about a check that did
  not run is the single most expensive sentence this layer can emit.
  Where a check genuinely cannot run, its result is **NOT_RUN with the
  reason**, and a NOT_RUN proof check caps the verdict at FAIL.

**PV-02: Rule Link Validity**
For each RuleID: exists in framework? Correctly applied? Score consistent?
PASS: All valid + correct | FAIL: Any invalid or misapplied

**PV-03: Counterclaim Quality**
Substantive = specific opposing interpretation + evidence + rebuttal. Non-substantive = generic filler.
PASS: ≥90% substantive | WARNINGS: 75-89% | FAIL: <75%

**CR-01: Critic Log Resolution**
Each finding: ADDRESSED / ACCEPTED_WITH_RATIONALE / INVALID / UNADDRESSED.
PASS: 100% resolved | WARNINGS: ≥90% | FAIL: Any HIGH unaddressed or >10% unaddressed

**Narrative Deep Review:** RC-05 milestone anchoring, RC-07/08 score/peer match, RC-09 trend consistency, overall specificity vs. generic.

**RC-13: Report Citation Density (NEW)** — ≥50 unique E-xxx references in report. FAIL <30.
**RC-14: Recommendation Evidence Anchoring (NEW)** — Every recommendation cites specific E-IDs and maps to a named Zennify solution.
**RC-15: Peer Benchmark Integration (NEW)** — Grep report for peer names. FAIL if: total peer references <10, exec summary has 0 peer refs, any pillar deep dive has 0 peer context.

**AG-01: Anti-Generic Content Detection (NEW — HIGH):**
For each report section, apply the specificity test:
- Executive Summary: every sentence must reference institution-specific data
- Pillar Deep Dives: every "What We See" paragraph must cite E-IDs
- Recommendations: every recommendation must cite specific evidence confirming the gap
FAIL if: >20% of report sentences could apply unchanged to a different institution.
FAIL if: Any recommendation uses forbidden generic phrases without evidence: "Appoint a CDO",
"Create a CoE", "Establish data governance committee", "Hire a CISO", "Form an innovation lab".
FAIL if: Any "NO_EVIDENCE" or "BLOCKED" subcap in the workbook has no documented proxy search
attempts (Tiers 7-10) in the search log. Proxy search exhaustion is required before gaps are declared.

**IE-01: Internal Evidence Classification Audit (NEW — HYBRID/INTERNAL mode only):**
Scan evidence_index.csv for internal sources:
- Any Hubbl/BuiltWith/Wappalyzer scan classified as T4 or T5 = CRITICAL
- Any structured discovery note with specific metrics classified as T4 = HIGH
- Any client-provided policy document classified as T5 = HIGH
Cross-check: If EVIDENCE_MODE is HYBRID or INTERNAL and <10% of evidence items are
internal-sourced = WARNING (internal evidence likely overlooked or not loaded).

**Root Cause Analysis (CRITICAL/HIGH issues):**
```
Surface finding → Proximate cause → Root cause → Systemic risk → Prevention
```

### Step 3: Merge & Generate Final Outputs

**1. Issue Register** (`issue_register.csv`): Pass 1 preliminary + Pass 2 LLM findings → sequential ISS-XXX IDs.

**2. QA Verdict** (`qa_verdict.json`): Per `schemas/qa_verdict.schema.json`. Populate from Pass 1 check_results + PV/CR results + DC flags. Apply verdict rules (see Quick Reference).

**3. Patch Block** (`patch_block.md`): Structural issues + rubric proposals + regression enhancements + error log entries + program actions. Use `templates/patch_block_template.md`.

---

## Workflow B: Cross-Assessment Calibration

Run when ≥2 assessments available. See `references/calibration_framework.md`.

```bash
python scripts/calibration_engine.py <manifest1.json> <manifest2.json> --output-dir "$GOV_OUTPUT/calibration"
```

LLM interpretation: contextualize drift flags (institution differences vs. genuine drift) → assess comparability → generate recommendations.

Output: structured calibration report per `templates/calibration_report_template.md`.

---

## Workflow C: Rubric Version Regression

Run when rubric/template/taxonomy change proposed.

```bash
python scripts/regression_runner.py <assessment_dir> --all-cases --output-dir "$GOV_OUTPUT/regression"
```

LLM interpretation: analyze failures (expected vs. regression) → assess comparability impact → verdict PASS/PARTIAL/FAIL.

---

## Proof-Carrying Score Verification

Every subcap must contain across R, S, T: Claims, Evidence Links, Rule Links, Counterclaim, Constraint Satisfaction. Plus reasoning_chain_log.json (Contract 8) for programmatic verification.

PV-01/02/03 checks validate completeness, rule validity, and counterclaim quality.

**Severity, corrected 2026-08-09.** These were MEDIUM ("fix before
delivery"), and MEDIUM is what let a run with a 0% proof structure ship
under PASS_WITH_NOTES. A score without a proof structure is not a score
with a documentation gap — it is an assertion whose basis nobody can
check, which is exactly what the 52 top-band cells of one promoted run
turned out to be. **A PV-01 FAIL is CRITICAL and the verdict is FAIL.**
PV-02 and PV-03 failures stay MEDIUM: an invalid rule link and a
non-substantive counterclaim are defects in proof that EXISTS.

---

## Reference Files

| File | When | Contents |
|------|------|----------|
| `schemas/interface_contracts.md` | Before any audit | All I/O schemas |
| `schemas/qa_verdict.schema.json` | Step 3 | Verdict JSON structure |
| `references/audit_checks.md` | Pass 1 | 79 check catalog |
| `references/distributional_checks.md` | DC flags | Pattern sanity checks |
| `references/calibration_framework.md` | Workflow B | Metrics, drift thresholds |
| `references/regression_suite.md` | Workflow C | Golden cases, tolerances |
| `references/governance_protocols.md` | B-C | CCB, version control |
| `scripts/llm_reasoning_prompts.md` | Pass 2 | Structured rubrics + examples |

---

## Workspace

```
$DMA_GOV_ROOT = /home/claude/dma_governance/
  audits/[institution]_[date]/    # Per-assessment outputs
  calibration/                     # Cross-assessment data
  golden_cases/                    # Test case evidence packs
```

---

## Quick Reference: Verdict Rules

| Condition | Verdict | Action |
|-----------|---------|--------|
| Any CRITICAL open (incl. AP-06, EC, FE) | FAIL | FIX_AND_REAUDIT |
| No CRITICAL, ≥1 HIGH (incl. AG-01, IE-01, RC-15) | PASS_WITH_NOTES | FIX_AND_REAUDIT |
| No CRITICAL/HIGH, ≥1 MEDIUM | PASS_WITH_NOTES | DELIVER (note issues) |
| All fixed or LOW only | PASS | DELIVER |
| Distributional anomalies only | PASS_WITH_NOTES | DELIVER (flag calibration) |
| PV fails | PASS_WITH_NOTES | FIX_AND_REAUDIT |
| CR fails | PASS_WITH_NOTES | FIX_AND_REAUDIT |

**New checks summary (v2.4):**
AP-06 (report citations), AP-07 (evidence mode), EC-01 to EC-05 (evidence completeness),
FE-01 (file existence), RC-13/14/15 (report quality), AG-01 (anti-generic), IE-01 (internal evidence).
Total automated + LLM checks: 91 automated + 17 LLM = 108 checks (was 79+12=91).

**PV/CR note:** Layer 1 PASS may still get Layer 2 PV/CR findings — by design. Layer 1 checks structure; Layer 2 checks reasoning quality. Persistent PV/CR patterns → patch block recommending Layer 1 self-checks.
