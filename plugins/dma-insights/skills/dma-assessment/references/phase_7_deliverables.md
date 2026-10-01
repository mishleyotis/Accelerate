# Phase 7: Deliverable Generation

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Phase 7: Deliverable Generation

Execute Phase Gate Protocol. Apply ERR-006.

Generate in order: **1. Workbook** → **2. Report** (.docx) → **3. Charts** → **4. Peer Analysis** → **5. Run Manifest** → **6. Governance Logs** → **7. Validate** → **8. Citation validation**

### Report Generation Protocol (MANDATORY)

**Template is MANDATORY — NO deviation.**

**STEP 0:** The template is PINNED in the repo —
`plugins/dma-insights/references/templates/assessment_report_template.md` with
its section spec in `report_templates.json` — and every run is bound to it at
`engine.cli start`. Read the pinned export (and `gold_reference.json`, the
Golden 1 depth) before writing; `python3 -m engine.cli narrative preconditions
--run <R> --report assessment` must print nothing (SCORING gate PASS, workbook
complete, PRELIM closed, binding recorded) or no section may be written.
This is the ONLY acceptable report structure. Do NOT create ad hoc layouts. Do NOT invent
sections. Fill the template exactly as structured.

**STEP 1 — ANALYZE (before writing ANYTHING — save analysis to disk):**
  Create `$DMA_ROOT/07_deliverables/report_analysis.json` containing:
  ```python
  analysis = {
    "total_evidence_items": N,
    "unique_e_ids": [list],
    "items_per_pillar": {"P1": N, "P2": N, "P3": N, "P4": N},
    "top_5_strongest": [{"subcap_id": "P1C1.1.1", "score": 3.5, "evidence": "E-xxx", "why": "..."}],
    "top_5_weakest": [{"subcap_id": "P2C3.2.1", "score": 1.5, "evidence": "none", "why": "..."}],
    "top_3_patterns": ["pattern description with E-IDs"],
    "cross_pillar_links": ["P4C1 low → caps P2C4 because..."],
    "peer_gaps": [{"category": "P2C1", "entity_score": 2.5, "peer_median": 3.2, "gap": -0.7}]
  }
  ```
  **This file is the ONLY input to Step 2. If it doesn't exist, Steps 2-3 cannot proceed.**

**STEP 2 — SYNTHESIZE (write synthesis to disk — do NOT skip):**
  Create `$DMA_ROOT/07_deliverables/report_synthesis.md` answering:
  a. What story does the DATA tell? (cite specific E-IDs and scores)
  b. Where vs peers — and WHY? (cite peer_gaps from analysis)
  c. What should Zennify prioritize? (map to specific Zennify solutions with evidence)
  d. Cross-pillar unlocks? (cite cross_pillar_links from analysis)
  **Each answer must reference specific E-IDs, scores, and peer data. Generic answers = redo.**

**STEP 3 — WRITE (following template structure, reading from synthesis):**
  Read `report_synthesis.md` → write each report section using ONLY data from synthesis.
  a. SCQA Executive Summary with ≥7 unique E-ID citations
  b. Pillar Deep Dives using "What We See / Why It Matters" structure per pillar
  c. Recommendations with ROOT CAUSE (E-IDs) + SOLUTION (Zennify offering) + EXPECTED OUTCOMES
  d. NO investment amounts, cost estimates, or ROI projections anywhere in the report

**STEP 4 — VALIDATE (before declaring Phase 7 complete):**
  a. Count E-xxx citations in report. <30 = FAIL, rewrite.
  b. Specificity test: could any paragraph apply to a different institution? If YES = rewrite.
  c. Verify Assessment ID and Evidence Mode on cover page, header, Appendix C match run_manifest.json.
  d. Verify every recommendation cites specific E-IDs and maps to a named Zennify solution.
  e. Verify peer data appears ≥10 times with specific peer names and scores.

**ANTI-GENERIC CHECK (fires before EVERY section):**
FORBIDDEN without proxy evidence confirming the gap exists: "Appoint a CDO", "No CDO found",
"no digital strategy", "Create a Center of Excellence", "Establish a data governance committee",
"Hire a CISO", "Form an innovation lab". Before concluding "no evidence" for any capability →
exhaust proxy searches (Tiers 7-10: industry associations, vendor case studies, job postings,
Glassdoor, community forums).

### Data Borrowing from Research Report (MANDATORY)

The following sections are COPY operations from the Client Profile / Research Report.
Do NOT rewrite them. Load the research report, extract relevant sections, and transplant
with assessment-layer annotations:

1. Section 3 (Trend Analysis & Digital Evolution Timeline) ← Research Report Section 3.3
2. Section 4 (Issue Register & Issue Timeline) ← Research Report Section 5.1
3. Section 2 (Assessment Methodology, entity context) ← Research Report Section 2

For sections requiring NEW analysis (Pillar Deep Dives, Recommendations, Gap Prioritization),
follow the Analyze→Synthesize→Write protocol above.

### Report Rules
- **Scoring-related claims** (pillar deep dives, capability analysis, recommendations): Synthesize FROM workbook rationales ONLY. No scoring facts not in workbook.
- **Contextual sections** (trend analysis, issue timeline, entity profile): BORROW from research report per Data Borrowing protocol above. These sections provide context, not scoring assertions.
- Read scoring data ONLY from canonical export CSVs in `$DMA_ROOT/04_scoring/exports/`. No ad hoc data sources.
- Inline citations: ≥5 in Executive Summary, ≥2/capability in Pillar Deep Dives, ≥1/recommendation. Total ≥30.
- Post-generation: count E-xxx citations. <10 = FAIL, rewrite.
- Structure: per `DMA_Assessment_Report_Template.docx` from project knowledge base.

### Run Manifest (`run_manifest.json`)
Schema: `run_manifest_v3`, owned by the engine (`skills/dma-research/engine/schemas/run_manifest.schema.json`) and written only through `engine.assemble.write_manifest`, which validates first; `scripts/generate_governance_outputs.py` calls the engine and types nothing.
**Key validation rules:** schema_version="run_manifest_v3" | scores null until scored | scores.overall = mean of pillars ±0.02 | evidence_metrics.total_items = sum of tier_distribution | every catalogue category scored once scored.

### Governance Logs (CSV exports for Layer 2)

**`caps_applied_log.csv`** — Contract 2. Columns: cap_id, cap_type (EVIDENCE_CEILING/SENTIMENT/REGULATORY/CROSS_PILLAR/ADJ_*/CRITIC_CHALLENGE), trigger_reason, trigger_evidence, affected_id, raw_score, cap_ceiling, final_score, score_delta.

**`contradiction_log.csv`** — Contract 3. Columns: contradiction_id, subcap_id, evidence_a_id, evidence_a_ers, evidence_a_claim, evidence_b_id, evidence_b_ers, evidence_b_claim, resolution_rule, winner, justification, confidence_impact, flagged_in_report, contradiction_type (HARD/SOFT).

**`evidence_index.csv`** — Contract 4. Columns: evidence_id, source_name, url, tier, ers_score, publish_date, subcaps_supported, key_facts_count.

**`reasoning_chain_log.json`** — Contract 8. Per-subcap: decision_path, evidence_considered, ceiling_calc, m_level_match, caps_applied, contradictions, confidence, critic_result, final_score. See `references/reasoning_chain_schema.md`.

### Post-Delivery Evidence Validation
Before declaring Phase 7 complete, verify all evidence IDs referenced in the workbook and report exist in `evidence_index.csv`. Any broken reference = fix before proceeding to Phase 8.

---
