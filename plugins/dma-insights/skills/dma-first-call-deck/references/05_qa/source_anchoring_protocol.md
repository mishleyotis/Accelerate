# Source Anchoring Protocol: Consolidated Rules for Fact Attribution

## Overview

This document consolidates the source anchoring rules from SKILL.md, dma_editing_contract.md, and qa_rubric.md into a single operational protocol. It defines what constitutes "anchored" data, how to trace facts from source document through PPTX output, and how to handle missing or incomplete attributions.

---

## Part 1: The Provenance Chain

Every fact in a Zennify Narrative deck travels through 4 stages of transformation:

```
SOURCE DOC (PDF, Excel, etc.)
    ↓
FACT_BANK (JSON, normalized facts)
    ↓
SLIDE_PLAN (narrative structure, slide-by-slide content outline)
    ↓
PPTX (final presentation file)
```

### Stage 1: Source Document
- Format: Any input document (PDF report, Excel data export, Google Sheet, internal memo, client presentation)
- What we extract: Raw data points, quotes, metrics, insights
- Metadata required: file_name, upload_date, document_type

### Stage 2: Fact_Bank
- Format: JSON file containing all extracted facts
- What it contains: Normalized, deduplicated facts with full provenance
- Structure: Each fact has `source`, `location`, `exact_text` fields (see below)

### Stage 3: Slide_Plan
- Format: JSON file outlining each slide's content
- What it contains: References to facts from fact_bank, organized by slide
- Critical rule: Every slide_plan reference must correspond to a fact_bank entry

### Stage 4: PPTX
- Format: PowerPoint file
- What it contains: Rendered narrative with data, visuals, formatting
- Critical rule: Every data point in PPTX must be traceable back through slide_plan → fact_bank → source doc

---

## Part 2: What Constitutes "Anchored" Data

A fact is **anchored** when it meets ALL three criteria:

### Criterion 1: Source File ID
The fact includes a reference to its original source document.

**Example**:
```json
{
  "fact_id": "F-0047",
  "text": "Enterprise segment revenue grew 35% YoY",
  "source": {
    "file_id": "source_doc_q4_2025_earnings.pdf",
    "document_type": "earnings_report",
    "author": "CFO",
    "upload_date": "2025-12-15"
  }
}
```

**What qualifies**:
- file_id must be a unique, traceable identifier
- If source is internal (Slack message, email), file_id must still be present (e.g., "slack_thread_2025-12-10_#sales-insights")
- If source is external (analyst report), file_id must map to a stored document

**What does NOT qualify**:
- Vague source: `"source": "internal knowledge"`
- Missing file_id: `"source": {"type": "company_data"}` without file_id
- Placeholder: `"source": "TBD"`

### Criterion 2: Location in Source
The fact includes a specific location (page, section, slide, cell) where it appears in the source.

**Example**:
```json
{
  "fact_id": "F-0047",
  "text": "Enterprise segment revenue grew 35% YoY",
  "location": {
    "type": "pdf_page",
    "page": 12,
    "section": "Financial Results by Segment"
  }
}
```

**What qualifies**:
- PDF: page number + section heading
- Excel: sheet name + cell range (e.g., "Q4_Summary!B5:C12")
- Google Sheet: sheet name + cell range + URL
- Presentation: slide number + shape text
- Database/API: table name + row ID

**What does NOT qualify**:
- Vague location: `"location": "somewhere in the earnings report"`
- General location: `"location": {"type": "document"}`
- Placeholder: `"location": "TBD"`

### Criterion 3: Exact Text or Citation
The fact includes the EXACT text from the source (quoted) OR a precise citation method.

**Example 1 (Exact Text)**:
```json
{
  "fact_id": "F-0047",
  "text": "Enterprise segment revenue grew 35% YoY",
  "source_exact_text": "\"Enterprise segment revenue grew 35 percent year-over-year, driven by increased adoption among Fortune 500 customers.\""
}
```

**Example 2 (Citation Method: Metric Definition)**:
```json
{
  "fact_id": "F-0048",
  "text": "NRR: 118%",
  "citation_method": "metric_definition",
  "metric_definition": {
    "name": "NRR (Net Revenue Retention)",
    "formula": "(Revenue_Start + Expansion - Churn) / Revenue_Start",
    "source": "source_doc_definitions.pdf, page 3, 'Key Metrics'"
  }
}
```

**What qualifies**:
- Direct quote from source (exact_text field)
- Calculation traceable to source (e.g., "CAC = Total Marketing Spend / New Customers", with both values sourced)
- Industry-standard metric (e.g., NRR) with definition reference
- Percentage derived from source data (e.g., "35% increase = (100 to 135) from Sheet Q4_Summary")

**What does NOT qualify**:
- Paraphrasing without source reference (e.g., "Revenue was higher")
- Calculated metric without showing the math or source values
- Interpretation without attribution (e.g., "This suggests market maturity")
- Placeholder: `"source_exact_text": "[exact text TBD]"`

---

## Part 3: DMA Evidence Tracing

DMA decks have specific sourcing requirements. These rules apply to **all DMA benchmark and performance decks**.

### DMA Evidence ID System (E-xxx)

All DMA evidence must be tagged with an Evidence ID in the format `E-001`, `E-002`, etc.

**Evidence ID Mapping**:
```json
{
  "evidence_id": "E-003",
  "type": "benchmark_performance",
  "slide": 3,
  "metric": "Revenue vs. Benchmark",
  "source_fact_ids": ["F-0023", "F-0024"],
  "benchmark_source": "E-Industry-Report-2025.pdf"
}
```

### DMA Minimum Data Slide Target (≥60%)

DMA decks MUST have at least 60% of body slides presenting externally-sourced, anchored data.

**Calculation**:
```
Data Slides = slides presenting benchmark, market, or competitive data (sourced)
Body Slides = total slides minus intro + closing (slides 2 through N-1)
Target = Data Slides / Body Slides ≥ 0.60
```

**Example**:
- Total slides: 10
- Body slides: 8 (slides 2-9)
- Data slides: 5 (benchmarks, market analysis, competitive positioning)
- Ratio: 5/8 = 62.5% ✓ PASS

If ratio < 60%, flag as FAIL and request additional evidence slides.

### DMA Benchmark Color Evidence Tracing

For benchmark performance charts (typically slides 3, 7, 8):
- **Above benchmark (green #00A86B)**: Must be sourced from [specific benchmark source] or calculated from anchored data
- **Below benchmark (red #DC143C)**: Must be sourced from [specific benchmark source] or calculated from anchored data
- **Benchmark line itself**: Must reference the original source (e.g., "Industry average, Data Source: Gartner 2025")

**Example Evidence Trace**:
```
SLIDE 3: Revenue vs. Benchmark Chart
  ├─ Company Revenue: $4.2M
  │   └─ Source: F-0023 (Q4 Earnings, page 5, "Total Revenue")
  ├─ Benchmark: $3.8M (Industry Median)
  │   └─ Source: E-002 (Gartner Industry Report 2025, page 43)
  └─ Variance: +$400K (10.5% above)
      └─ Calculation: $4.2M - $3.8M = $0.4M ✓ ANCHORED
```

---

## Part 4: Validation Checklist (Pre-Build)

Run these validation checks BEFORE building the PPTX:

### Check 1: Fact_Bank Completeness
```
For each fact in fact_bank.json:
  ✓ fact_id present and unique
  ✓ source.file_id present and not "TBD"
  ✓ source.upload_date present
  ✓ location.type and location.page/sheet/section present
  ✓ source_exact_text OR citation_method present
  ✓ No placeholder values ("TBD", "[INSERT]", "TBD")
```

**Command to validate**:
```bash
jq '.facts[] | select(.source.file_id == "TBD" or .location == null or .source_exact_text == null)' fact_bank.json
# Returns: any facts missing required fields (should return nothing)
```

### Check 2: Slide_Plan Cross-Reference
```
For each fact_id referenced in slide_plan.json:
  ✓ Fact exists in fact_bank.json
  ✓ Fact is marked as "used: true" or "status: active"
  ✓ No circular references (fact A referencing fact B which references fact A)
```

**Command to validate**:
```bash
# Extract all fact_ids from slide_plan
grep -o '"fact_id": "[^"]*"' slide_plan.json | cut -d'"' -f4 | sort | uniq > slide_plan_facts.txt

# Extract all fact_ids from fact_bank
jq '.facts[].fact_id' fact_bank.json | sort | uniq > fact_bank_facts.txt

# Find facts in slide_plan not in fact_bank
comm -23 slide_plan_facts.txt fact_bank_facts.txt
# Should return nothing (empty)
```

### Check 3: Evidence Slide Coverage (DMA Only)
```
Count slides presenting sourced benchmark/market data
Calculate ratio: Data Slides / Body Slides
Ensure ratio ≥ 0.60
```

### Check 4: DATA NEEDED Flags
```
Search all files (fact_bank, slide_plan) for "[DATA NEEDED]" markers
Count occurrences
If count > 0:
  ✓ Document which facts are incomplete
  ✓ Document action plan to complete them
  ✓ Do NOT build PPTX until [DATA NEEDED] count = 0 (unless explicitly approved for partial build)
```

**Command to validate**:
```bash
grep -r "\[DATA NEEDED\]" fact_bank.json slide_plan.json build_log.txt
# If output is empty, all data is present. If not empty, list what's missing.
```

### Check 5: Google Slides Compatibility (Sources & References)
```
Verify that all source citations can be rendered in text:
  ✓ No embedded objects or links that break in Google Slides
  ✓ Source citations are text-based, not embedded documents
  ✓ External sources (links, file references) are stored in footnote/appendix format
```

---

## Part 5: Validation Checklist (Post-Build)

After building the PPTX, validate that sourcing chain is intact:

### Check 1: Data Accuracy Sampling
```
For 3 randomly selected data slides:
  ✓ Extract the data shown in the slide
  ✓ Trace it back through slide_plan to fact_bank
  ✓ Verify fact_bank entry matches the slide data (exact match, no rounding errors)
  ✓ Verify fact_bank entry has full source attribution
  ✓ Open source document and confirm data appears there
```

**Example Trace**:
```
SLIDE 5: "Enterprise Adoption Up 45% YoY"
  ↓ Verify in PPTX
  ↓ Find in slide_plan.json: fact_id "F-0045"
  ↓ Find in fact_bank.json:
     {"fact_id": "F-0045", "text": "Enterprise adoption increased 45% year-over-year",
      "source": {"file_id": "source_q4_2025_earnings.pdf", "page": 12},
      "source_exact_text": "\"Enterprise adoption up 45 percent year-over-year\""}
  ↓ Open source_q4_2025_earnings.pdf, page 12
  ✓ Confirm text appears there
```

### Check 2: Placeholder Cleanup (Re-Check)
```
Search PPTX XML for remaining [DATA NEEDED] flags
If found:
  ✓ Document which ones are structural vs. content
  ✓ If content [DATA NEEDED], PPTX is NOT FINISHED
  ✓ If structural, note in delivery manifest
```

### Check 3: Color Attribution (DMA Benchmark Slides)
```
For each benchmark slide (typically 3, 7, 8):
  ✓ Green bars (#00A86B) represent "above benchmark"
  ✓ Red bars (#DC143C) represent "below benchmark"
  ✓ Source for benchmark line is cited in slide footer or legend
  ✓ Evidence ID (E-xxx) appears in slide notes or footer
```

### Check 4: Google Slides Render Test
```
1. Upload PPTX to Google Drive
2. Open in Google Slides
3. Verify:
   ✓ All text renders (no font substitution issues with citations)
   ✓ All data is visible (no overflow in footnotes or source citations)
   ✓ All links to sources work (if applicable)
   ✓ Benchmark colors display correctly
   ✓ No error messages or broken elements
```

---

## Part 6: Cross-Schema Integrity Rules

These rules ensure that data flows consistently through fact_bank → slide_plan → PPTX.

### Rule 1: Fact_Bank → Slide_Plan References
**Every fact referenced in slide_plan MUST exist in fact_bank.**

```json
// slide_plan.json
{
  "slides": [
    {
      "slide_num": 3,
      "facts": ["F-0045", "F-0023"]  // These IDs must exist in fact_bank
    }
  ]
}

// fact_bank.json
{
  "facts": [
    {"fact_id": "F-0045", ...},
    {"fact_id": "F-0023", ...}
    // Both F-0045 and F-0023 must be here
  ]
}
```

**Violation Detection**:
```bash
# Find fact_ids in slide_plan that don't exist in fact_bank
grep -o '"F-[0-9]*"' slide_plan.json | sort | uniq > sp_facts.txt
jq '.facts[].fact_id' fact_bank.json | sort | uniq > fb_facts.txt
comm -23 sp_facts.txt fb_facts.txt  # Lists missing facts
```

### Rule 2: Fact Usage Tracking
**Every fact in fact_bank should be marked with usage status.**

```json
{
  "fact_id": "F-0045",
  "text": "Enterprise adoption increased 45%",
  "status": "active",
  "used_in": ["slide_3", "slide_7_caption"],
  "last_updated": "2026-03-05"
}
```

**Validation**:
- status = "active" → fact is used in current deck
- status = "draft" → fact is pending confirmation, should not be in PPTX
- status = "archived" → fact was used in previous version, should not be in current PPTX
- Unused facts (used_in = []) should be documented and removed or repurposed

### Rule 3: Source File Inventory
**Maintain a registry of all source documents referenced in fact_bank.**

```
SOURCE FILE INVENTORY
====================
File ID | File Name | Type | Upload Date | Facts Extracted | Status
---
source_q4_2025_earnings.pdf | Q4 2025 Earnings Report | PDF | 2025-12-15 | F-0023, F-0045, F-0048 | ACTIVE
source_gartner_report_2025.pdf | Gartner Industry Report | PDF | 2025-11-20 | F-0012, F-0013 | ACTIVE
slack_thread_2025-12-10.txt | Sales insights thread | Slack | 2025-12-10 | F-0089 | DRAFT
```

**Validation**:
- Every file_id in fact_bank must appear in SOURCE FILE INVENTORY
- Every source file must be stored locally or accessible by URL
- Status = "ACTIVE" means file is current; "ARCHIVE" means historical

### Rule 4: Fact Deduplication
**No two facts should express the same data point with different values.**

**Example of Violation**:
```json
{
  "fact_id": "F-0045",
  "text": "Enterprise revenue $4.2M",
  "source": "source_q4_2025_earnings.pdf"
}

{
  "fact_id": "F-0156",
  "text": "Enterprise segment revenue reached $4.5M",
  "source": "source_q4_2025_earnings_updated.pdf"
}
// ^ Same data point, different values. VIOLATION.
```

**Detection**:
```bash
# Check for facts with similar text but different values
jq '.facts[] | select(.text | test("Enterprise revenue|revenue.*Enterprise"))' fact_bank.json
# If multiple results with different $ amounts, investigate
```

**Resolution**:
- Use most recent/authoritative source
- Document which version was used in slide_plan
- Mark superseded facts as "archived"

---

## Part 7: Handling Missing Data

Not all facts are always available. This section covers how to handle missing or incomplete data.

### Scenario 1: Data Available But Not Sourced
**Status**: Fact exists but lacks full provenance chain.

**Example**:
```json
{
  "fact_id": "F-0089",
  "text": "Churn rate: 8% monthly",
  "source": {"file_id": "TBD"},  // ← MISSING SOURCE
  "location": {"type": "spreadsheet", "sheet": "Metrics"}
}
```

**Action**:
1. Prioritize: Can this source be found (within 30 minutes)?
   - YES → Find and add source, mark fact as "active"
   - NO → Proceed to step 2
2. Mark fact status as "unanchored_draft"
3. Do NOT include in PPTX unless explicitly approved
4. Add to "Missing Data" section of build_log.txt
5. Note: "F-0089 (Churn rate) included in deck without source attribution. Requires verification."

### Scenario 2: Data Not Yet Obtained
**Status**: Fact is needed for the narrative but data hasn't been extracted yet.

**Example**:
```json
{
  "fact_id": "F-0090",
  "text": "[DATA NEEDED] - Customer acquisition cost by segment",
  "source": {
    "file_id": "[DATA NEEDED]",
    "expected_source": "Finance team FY2026 budget model"
  },
  "status": "pending"
}
```

**Action**:
1. Identify owner responsible for obtaining data
2. Set deadline (default: 48 hours before build)
3. Do NOT include in PPTX; use placeholder instead
4. Track in build_log.txt: "F-0090 pending; will update by 2026-03-08"
5. On deadline: If data received, add to fact_bank and include in build. If data not received, delete fact or note as "estimate based on historical trend"

### Scenario 3: Data Is Proprietary or Confidential
**Status**: Data exists and is sourced, but cannot be attributed publicly.

**Example**:
```json
{
  "fact_id": "F-0091",
  "text": "Key customer retention: 95%",
  "source": {
    "file_id": "internal_customer_database",
    "confidentiality": "internal_only",
    "public_attribution": "Company data (confidential)"
  }
}
```

**Action**:
1. Include the fact in the deck (it's sourced and verified)
2. Attribute as "Company data" or "Internal systems" without revealing source details
3. In slide_plan, mark: `"is_confidential_source": true`
4. In PPTX, render as: "Our data shows: [fact]" or "[Company]: [fact]"
5. In notes or footer, add: "Source: Internal systems, not for external distribution"

### Scenario 4: Data Is Calculated/Derived
**Status**: Data is not a direct quote but calculated from sourced inputs.

**Example**:
```json
{
  "fact_id": "F-0092",
  "text": "CAC payback period: 18 months",
  "calculation": {
    "formula": "CAC / (ARPU × Gross Margin) × 12",
    "inputs": [
      {"name": "CAC", "value": "$850", "source_fact_id": "F-0045"},
      {"name": "ARPU", "value": "$4,200/year", "source_fact_id": "F-0046"},
      {"name": "Gross Margin", "value": "72%", "source_fact_id": "F-0047"}
    ],
    "source_calculation_verified_by": "CFO, 2026-03-05"
  }
}
```

**Action**:
1. Include in fact_bank with full calculation chain
2. In slide_plan and PPTX, footnote: "CAC payback = [formula]; based on [F-0045, F-0046, F-0047]"
3. Verification: CFO or finance owner must sign off on calculation
4. Mark as "calculated_from_sourced_inputs: true"

---

## Part 8: Escalation Rules

When a fact cannot be anchored, follow this escalation path:

### Level 1: Attempt Resolution (24 hours)
- [ ] Search existing fact_bank for related anchored facts
- [ ] Check source file inventory for missing files
- [ ] Contact data owner with specific request (not vague "get me data")
- [ ] If resolved → add to fact_bank → proceed
- [ ] If not resolved → Level 2

### Level 2: Stakeholder Check (48 hours)
- [ ] Notify project lead: "Fact F-XXXX is unanchored. Need decision: include without source or defer?"
- [ ] Options presented:
  - A) Include with "Company internal data" attribution (no external source)
  - B) Include as estimate with caveat ("Estimated based on historical trends")
  - C) Remove from deck
- [ ] Stakeholder decision recorded: "Approved decision [A/B/C] per [Stakeholder Name], [Date]"
- [ ] Proceed → Level 3

### Level 3: Build Decision
- [ ] If decision = A or B, add to PPTX with recorded justification
- [ ] If decision = C, remove fact and adjust narrative
- [ ] Add entry to build_log.txt:
  ```
  UNANCHORED FACT: F-XXXX
  Decision: [A/B/C]
  Approved by: [Name]
  Date: [Date]
  Justification: [reason]
  ```

### Escalation Timeout
If fact remains unanchored after 72 hours AND no stakeholder decision has been made:
- Default action: Remove fact from deck
- Note in build_log: "F-XXXX removed due to unresolved sourcing (escalation timeout)"
- Notify stakeholder: "Removed [fact]. Contact us to reinstate with source."

---

## Part 9: Audit Trail

Maintain a detailed audit trail of all sourcing decisions and changes.

### Build Log Format

```
BUILD_LOG.txt
=============

DECK NAME: [name]
BUILD DATE: 2026-03-06
BUILD VERSION: v2.3

FACTS INCLUDED
==============
Total facts: 47
Fully anchored: 45
Partially anchored: 2
Unanchored: 0

FACTS ANCHORED: 45
├─ F-0001 through F-0045 (see fact_bank.json for details)

FACTS PARTIALLY ANCHORED: 2
├─ F-0089: Churn rate (Source file ID confirmed, location pending)
├─ F-0091: Key customer retention (Confidential source, approved by [Name])

FACTS UNANCHORED: 0

ESCALATIONS
===========
(none)

CHANGES FROM v2.2
=================
- Added F-0089 (churn rate) with source verification pending
- Removed F-0087 (market share estimate) due to unconfirmed source
- Updated F-0045 to reflect final Q4 numbers (source: earnings_v3.pdf)

SIGN-OFF
========
Prepared by: [Name]
Reviewed by: [Name]
Approved by: [Name]
Date: 2026-03-06
```

### Audit Trail Commands

Track changes to fact_bank and slide_plan:

```bash
# Show all facts added in last build
git log -p --since="2026-03-01" -- fact_bank.json | grep "^+.*fact_id"

# Show all fact deletions
git log -p -- fact_bank.json | grep "^-.*fact_id"

# Show all changes to unanchored facts
jq '.facts[] | select(.status == "unanchored_draft")' fact_bank.json
```

---

## Part 10: Consolidated Quick Reference

### The 3 Criteria for "Anchored"
1. **Source File ID**: fact_bank entry references a specific source document with file_id
2. **Location**: fact_bank entry specifies page, section, cell, or unique location in source
3. **Exact Text or Citation**: fact_bank entry includes either the exact quote or a verifiable calculation method

### Validation Workflow
```
PRE-BUILD:
  ✓ Check 1: All facts in fact_bank have file_id + location + exact_text
  ✓ Check 2: All facts in slide_plan exist in fact_bank
  ✓ Check 3: Data slides >= 60% of body slides (DMA only)
  ✓ Check 4: No [DATA NEEDED] flags remain (unless approved partial build)
  ✓ Check 5: All sources are Google Slides compatible

POST-BUILD:
  ✓ Check 1: Sample 3 slides, trace data back to sources
  ✓ Check 2: Re-check for leftover [DATA NEEDED] flags
  ✓ Check 3: Verify benchmark colors have DMA evidence attribution
  ✓ Check 4: Test PPTX in Google Slides

ESCALATION:
  If fact unanchored:
    → Level 1 (24h): Attempt to locate source
    → Level 2 (48h): Stakeholder decision (include as internal/estimate/remove)
    → Level 3: Build decision recorded in build_log.txt
    → Timeout (72h): Default removal unless approved
```

### DMA-Specific Rules
- **Evidence ID System**: All DMA evidence tagged E-001, E-002, etc.
- **Minimum Data Slides**: ≥60% of body slides must present externally-sourced, anchored data
- **Benchmark Colors**: Green (#00A86B) = above benchmark; Red (#DC143C) = below benchmark
- **Source Citation**: Benchmark line must reference original source in slide footer

### Files to Maintain
1. **fact_bank.json** — Master list of all facts with full provenance
2. **slide_plan.json** — Narrative structure with fact_id references
3. **source_inventory.txt** — Registry of all source documents
4. **build_log.txt** — Audit trail of build decisions and changes
5. **source_docs/** — Folder containing all original source files

---

## Summary Checklist

Before delivering a Zennify Narrative deck, verify:

- [ ] Fact_bank complete: All facts have file_id, location, and exact_text/citation
- [ ] Cross-references valid: All fact_ids in slide_plan exist in fact_bank
- [ ] DMA requirements met (if applicable): ≥60% data slides, all benchmarks sourced
- [ ] No [DATA NEEDED] flags remain (unless explicitly approved)
- [ ] Build log completed and signed off
- [ ] Sources tested: 3 sample slides traced back to original documents
- [ ] Google Slides compatibility verified
- [ ] Source file inventory maintained and current
- [ ] Escalations documented (if any)

End of source_anchoring_protocol.md
