# Research Workbook Specification

This file defines the structure of the DMA Research Workbook — the PRIMARY deliverable
of the dma-research skill. The research workbook has the same 10-sheet structure as the
scoring workbook (per dma-assessment's workbook_specification.md) but with a critical
difference: scoring columns are LEFT EMPTY.

**File Naming:** `DMA_Research_Workbook_[INSTITUTION_NAME]_[DATE].xlsx`

---

## Column Responsibility Split

### Columns the RESEARCH skill FILLS (evidence layer)

| Col | Name | Fill Rules | Quality Gate |
|-----|------|-----------|-------------|
| A | Category_ID | Pillar code (P1-P4) from toolkit XLSX | Must match toolkit exactly |
| B | Category_Name | Full category name from toolkit | Must match toolkit exactly |
| C | Cap_ID | Capability code (C1-C5) from toolkit | Must match toolkit exactly |
| D | Capability | Full capability name from toolkit | Must match toolkit exactly |
| E | SubCap_ID | Subcapability code (P1C1.1.1) from toolkit | Must match toolkit exactly |
| F | SubCapability | Subcapability name from toolkit | Must match toolkit exactly |
| G | Tier | Highest evidence tier found (T1-T5 or NO_EVIDENCE) | Must be valid tier code |
| H | Diagnostic_Question | The question from toolkit Column H | Verbatim from toolkit |
| I | Weight_Pct | Subcapability weight from toolkit | Must sum to 100% per capability |
| K | Evidence_IDs | Comma-separated fact-level IDs | Format: E-xxx:Fy or NO_EVIDENCE |
| L | Evidence_URLs | Hyperlinks to sources | Valid URLs or "internal" |
| M | Evidence_Tier | All tiers represented | Comma-separated tier codes |
| U | Evidence_Excerpt | Analytical evidence write-up | See write-up protocol below |
| V | Source_Document | Source names and URLs | See format rules below |

### Columns LEFT EMPTY for assessment skill

| Col | Name | Why Empty |
|-----|------|-----------|
| J | Score_1_to_5 | Scoring is assessment skill's job |
| N | Confidence | Requires scoring context |
| O | Caps_Applied | Cap determination requires scoring |
| P | Final_Score | Calculated after scoring |
| Q | Prior_Score | Reassessment data |
| R | Scoring_Rationale | Written during scoring |
| S | Proof_Claims | Built during scoring |
| T | Proof_Links | Cross-references to caps log |

---

## Evidence Write-Up Protocol (Column U — THE MOST IMPORTANT COLUMN)

Column U is the "show your work" column. It bridges raw evidence to scoring. The scorer
reads this column to understand what was found and makes scoring decisions based on it.
A well-written Column U makes scoring faster, more accurate, and more defensible.

### Write-Up Structure (MANDATORY for every row with evidence)

```
[ERS: X.XX] [CLAIM_TYPE] [E-xxx:Fy] Source (Tier, Recency): Core finding in 1-2
sentences. [Second source if available: E-xxx:Fy] Corroborating/contrasting point.
[CEILING IMPLICATION: Lx.x ±x.x] [VALIDATION NEED: specific question if applicable]
```

### Write-Up Examples by Quality Level

**HIGH-QUALITY write-up (ERS ≥ 3.5, multiple sources)**:
```
[ERS: 4.30] [FACT] [E-015:F3] Annual Report 2024 (T2, CURRENT): Mobile app redesign
launched Q3 2024 with 47% adoption increase in first 90 days. [E-042:F1] App Store
(T3, CURRENT): Corroborated by 4.2-star rating from 12,450 reviews, up from 3.1 in
2023. [CFPB (T1, CURRENT): Mobile complaints down 28% YoY.] [CEILING: L3.5 ±0.3]
```

**MEDIUM-QUALITY write-up (ERS 2.5-3.5, limited sources)**:
```
[ERS: 3.10] [INFERENCE] [E-022:F2] Press Release Jan 2025 (T2, CURRENT): Announced
partnership with Alkami for digital banking platform migration. [E-031:F1] Job posting
(T4, CURRENT): "Alkami platform administrator" role confirms deployment in progress.
No utilization evidence found. [CEILING: L2.5 ±0.5] [VALIDATE: Deployment completion
date, migration scope, user adoption metrics]
```

**LOW-QUALITY write-up (ERS < 2.5, single source)**:
```
[ERS: 2.00] [HYPOTHESIS] [E-055:F1] Website About Page (T5, CURRENT): Claims "industry-
leading digital capabilities" — no specific features, metrics, or platforms mentioned.
No corroborating evidence from T1-T3 sources. [CEILING: L1.5 ±0.5] [VALIDATE: What
specific digital capabilities exist? What platforms are deployed?]
```

**NO_EVIDENCE write-up**:
```
No evidence identified through 8 searches across 6 tiers targeting "Is there a defined
cadence for refreshing the digital strategy?" Proxy searches (board minutes cadence,
strategic plan refresh cycle, annual technology review) also yielded no results.
Peer CUs of similar size typically disclose strategy refresh in annual reports.
[VALIDATE: INT-Q: "How often is the digital strategy reviewed and by whom?"]
```

### Write-Up Quality Rules

1. **Start with ERS score** — enables scorer to weight the evidence appropriately
2. **Include claim label** — FACT/INFERENCE/HYPOTHESIS/CEILING_ESTIMATE
3. **Cite at fact level** — E-xxx:Fy, not just E-xxx
4. **Include tier and recency** — (T2, CURRENT) or (T5, LEGACY)
5. **State the finding, not the source type** — "Mobile complaints down 28%" not "CFPB data shows..."
6. **Include contradictory evidence** when present — don't hide it
7. **End with ceiling implication** — "CEILING: L3.5 ±0.3" not just the fact
8. **Add validation need** if evidence is thin — specific internal discovery question
9. **Minimum 50 characters** for evidence rows, **minimum 100 characters** for NO_EVIDENCE rows
10. **Maximum 500 characters** — be analytical, not verbose. Compress.

### Write-Up Anti-Patterns (NEVER do these)

| Anti-Pattern | Why It's Bad | Fix |
|-------------|-------------|-----|
| "Evidence shows..." | Adds nothing | State the finding directly |
| Copy-pasting a URL as the excerpt | Not analytical | Extract the specific finding |
| "Strong digital capabilities observed" | Generic, no specifics | Cite specific metric or feature |
| Summarizing without ERS/tier | Scorer can't weight it | Always prefix with quality indicators |
| Missing ceiling implication | Scorer has to infer | Always state ceiling estimate |
| Single sentence for complex evidence | Undersells rich findings | Include 2+ sources when available |
| "See annual report for details" | Forces scorer to re-research | Extract the relevant facts here |

---

## Source Document Format (Column V — MANDATORY for every row with evidence)

### Format Rules

**For public evidence:**
```
[Document Title], [Publisher/Source], [Date Published]. URL: [full URL]
```
Example: "Annual Report 2024, Gesa Credit Union, 2025-03-15. URL: https://..."

**For regulatory evidence:**
```
[Filing Type] [Period], [Regulator]. URL: [full URL or database reference]
```
Example: "Call Report Q4 2024, NCUA. URL: https://..."

**For sentiment sources:**
```
[Platform] [Entity Name], [Date accessed]. [Aggregate metric if applicable]
```
Example: "iOS App Store - Gesa CU, accessed 2025-03-20. 4.2★, 12,450 reviews"

**For internal documents (HYBRID/INTERNAL mode):**
```
[Document Name], [Document Type], [INT-xxx]. [Author/Department if known], [Date]
```
Example: "Digital Strategy Roadmap, Board Presentation, INT-BOARD-001. CTO Office, Q2 2024"

**For NO_EVIDENCE:**
```
"No source — [N] searches executed across [M] tiers. See search log S-xxxx through S-xxxx."
```

---

## Sheet-by-Sheet Research Workbook Structure

### Sheets 3-6: P1-P4_Scoring_Detail (THE CORE SHEETS)

These are the primary output sheets. Each has ONE ROW PER SUBCAPABILITY.

**Row counts** (±5% tolerance based on toolkit version):
- Sheet 3 (P1): ~199-209 rows
- Sheet 4 (P2): ~274-300 rows
- Sheet 5 (P3): ~154-170 rows
- Sheet 6 (P4): ~178-196 rows
- **Total: ~836 rows** (range 805-875)

**All 22 columns (A-V) must exist**. Research fills A-I, K, L, M, U, V. Leaves J, N-T empty.

### Sheet 1: Summary (SKELETON)

Create the shell structure with pillar rows (P1-P4, Overall). Leave score columns empty.
Fill only: Pillar names, Evidence_Coverage_Pct (calculated from evidence per subcap).

### Sheet 2: Calculation_Chain (SKELETON)

Create Section A structure with all ~836 subcap rows (SubCap_ID, SubCapability, Weight).
Leave Raw_Score and Weighted_Value columns empty. Assessment skill fills these.

### Sheet 7: Evidence_Linkage_Matrix (POPULATED by research)

This sheet IS a research deliverable. Columns:

| Evidence_ID | Source_Name | Source_URL | Source_Type | Tier | Recency | ERS_Total | Date_Published | KB_Source_ID | Fact_Count | SubCap_Mappings | Claim_Types | Corroborating_IDs | Contradicting_IDs | Batch |
|-------------|-------------|-----------|-------------|------|---------|-----------|---------------|-------------|-----------|-----------------|-------------|-------------------|-------------------|-------|

One row per evidence item (not per fact). All evidence collected across all batches.

### Sheet 8: Caps_Applied_Log (SKELETON)

Create header row only. Assessment skill populates this.

### Sheet 9: Absent_Evidence_Log (POPULATED by research)

| SubCap_ID | SubCapability | Diagnostic_Question | Search_Count | Tiers_Searched | Highest_Tier_Found | Proxy_Attempts | Escalation_Level | Reason | Discovery_Question | Impact_Note |

One row per NO_EVIDENCE subcap. Documents the search effort that found nothing.

### Sheet 10: QA_Validation_Log (POPULATED by research)

Research skill runs its OWN validation checks and logs results here:

| Check_ID | Check_Name | Status | Details | Actions_Taken |
|----------|-----------|--------|---------|--------------|
| RES-001 | Subcap Row Count | PASS/FAIL | "P1: 203, P2: 291, P3: 164, P4: 189, Total: 847" |
| RES-002 | Evidence Coverage ≥80% | PASS/FAIL | "Coverage: 89% (744/836 subcaps with evidence)" |
| RES-003 | Column U Completeness | PASS/FAIL | "836/836 rows have Evidence_Excerpt populated" |
| RES-004 | Column V Completeness | PASS/FAIL | "744/836 rows have Source_Document (92 are NO_EVIDENCE)" |
| RES-005 | ERS Calculated | PASS/FAIL | "All 450 evidence items have ERS scores" |
| RES-006 | NO_EVIDENCE Documented | PASS/FAIL | "92 NO_EVIDENCE rows have search count ≥6" |
| RES-007 | Evidence_IDs Format | PASS/FAIL | "All IDs match E-\\d{3}(:F\\d+)? pattern" |
| RES-008 | Weights Sum to 100% | PASS/FAIL | "All 17 capabilities have weights summing to 100%" |
| RES-009 | Tier Distribution | INFO | "T1: 12%, T2: 28%, T3: 35%, T4: 15%, T5: 10%" |
| RES-010 | Safeguard Gates | PASS/FAIL | "14 PASS, 2 FAIL (G7 deferred, G9 deferred)" |

---

## Workbook Formatting

### Column Widths

| Columns | Width | Wrap Text |
|---------|-------|-----------|
| A-B | 12 chars | No |
| C-F | 18 chars | No |
| G | 14 chars | No |
| H | 40 chars | Yes |
| I | 10 chars | No |
| J | 10 chars (empty) | No |
| K-L | 25 chars | Yes |
| M | 12 chars | No |
| N-T | 10-50 chars (empty) | — |
| U | 65 chars | Yes — THIS IS THE KEY COLUMN |
| V | 35 chars | Yes |

### Conditional Formatting (Research-Specific)

- **Column G (Tier)**: Green=T1/T2, Yellow=T3, Orange=T4/T5, Red=NO_EVIDENCE
- **Column U (Evidence_Excerpt)**: Red background if <50 characters (too thin)
- **Column I (Weight)**: Red if >30% (unusually high weight — verify)

### Freeze Panes

- All Scoring_Detail sheets: Freeze Row 1 + Columns A-F
- Evidence_Linkage_Matrix: Freeze Row 1
- Absent_Evidence_Log: Freeze Row 1

### Data Validation (Applied by Research Skill)

- **Column G**: Dropdown (T1, T2, T3, T4, T5, NO_EVIDENCE)
- **Column I**: Number format 0.0%, allow 0.1-100.0
- **Column M**: Free text (multiple tiers allowed)

---

## Workbook Generation Code Pattern

```python
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

def create_research_workbook(entity_name, date_str, diagnostic_qs, evidence_index):
    wb = openpyxl.Workbook()

    # Define styles
    header_font = Font(name='DM Sans', size=10, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='27BBAF', end_color='27BBAF', fill_type='solid')
    t1_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
    t2_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
    t3_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
    t45_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
    no_ev_fill = PatternFill(start_color='FF0000', end_color='FF0000', fill_type='solid')
    wrap = Alignment(wrap_text=True, vertical='top')

    # Sheet 1: Summary (skeleton)
    ws_summary = wb.active
    ws_summary.title = 'Summary'
    # ... create skeleton structure

    # Sheet 2: Calculation_Chain (skeleton)
    ws_calc = wb.create_sheet('Calculation_Chain')
    # ... create skeleton with subcap rows, empty score columns

    # Sheets 3-6: P1-P4_Scoring_Detail
    for pillar_num in range(1, 5):
        ws = wb.create_sheet(f'P{pillar_num}_Scoring_Detail')
        headers = ['Category_ID', 'Category_Name', 'Cap_ID', 'Capability',
                   'SubCap_ID', 'SubCapability', 'Tier', 'Diagnostic_Question',
                   'Weight_Pct', 'Score_1_to_5', 'Evidence_IDs', 'Evidence_URLs',
                   'Evidence_Tier', 'Confidence', 'Caps_Applied', 'Final_Score',
                   'Prior_Score', 'Scoring_Rationale', 'Proof_Claims',
                   'Proof_Links', 'Evidence_Excerpt', 'Source_Document']
        # Write headers with formatting
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = wrap

        # Populate rows from diagnostic_qs + evidence_index
        row_num = 2
        for subcap in diagnostic_qs[f'P{pillar_num}']:
            evidence = evidence_index.get(subcap['subcap_id'], None)
            ws.cell(row=row_num, column=1, value=f'P{pillar_num}')          # A
            ws.cell(row=row_num, column=2, value=subcap['category_name'])    # B
            ws.cell(row=row_num, column=3, value=subcap['cap_id'])           # C
            ws.cell(row=row_num, column=4, value=subcap['capability'])       # D
            ws.cell(row=row_num, column=5, value=subcap['subcap_id'])        # E
            ws.cell(row=row_num, column=6, value=subcap['subcap_name'])      # F
            ws.cell(row=row_num, column=8, value=subcap['diagnostic_q'])     # H
            ws.cell(row=row_num, column=9, value=subcap['weight'])           # I

            if evidence and evidence['tier'] != 'NO_EVIDENCE':
                ws.cell(row=row_num, column=7, value=evidence['tier'])       # G
                ws.cell(row=row_num, column=11, value=evidence['ids'])       # K
                ws.cell(row=row_num, column=12, value=evidence['urls'])      # L
                ws.cell(row=row_num, column=13, value=evidence['tiers'])     # M
                ws.cell(row=row_num, column=21, value=evidence['excerpt'])   # U
                ws.cell(row=row_num, column=22, value=evidence['source'])    # V
            else:
                ws.cell(row=row_num, column=7, value='NO_EVIDENCE')
                ws.cell(row=row_num, column=11, value='NO_EVIDENCE')
                ws.cell(row=row_num, column=21, value=evidence['no_ev_text'] if evidence else
                    f'No evidence identified. 0 searches executed.')
                ws.cell(row=row_num, column=22, value='No source')

            # Columns J, N-T intentionally left empty
            row_num += 1

        # Apply formatting, freeze panes, data validation
        ws.freeze_panes = 'G2'
        # ... apply conditional formatting, column widths

    # Sheet 7: Evidence_Linkage_Matrix
    ws_elm = wb.create_sheet('Evidence_Linkage_Matrix')
    # ... populate from evidence_index

    # Sheet 8: Caps_Applied_Log (skeleton)
    ws_caps = wb.create_sheet('Caps_Applied_Log')
    # ... header row only

    # Sheet 9: Absent_Evidence_Log
    ws_absent = wb.create_sheet('Absent_Evidence_Log')
    # ... populate from NO_EVIDENCE subcaps

    # Sheet 10: QA_Validation_Log
    ws_qa = wb.create_sheet('QA_Validation_Log')
    # ... populate from validation results

    # Save
    filename = f'DMA_Research_Workbook_{entity_name}_{date_str}.xlsx'
    wb.save(f'/mnt/user-data/outputs/{filename}')
    return filename
```

---

## Validation Checks (Run Before Saving)

| Check | Pass Criteria | Severity |
|-------|-------------|----------|
| Row count per pillar | ±5% of toolkit targets | BLOCK |
| All 22 columns exist | Headers match spec | BLOCK |
| Scoring columns empty | J, N-T have no values | BLOCK |
| Evidence columns filled | U, V have values for all non-NO_EVIDENCE rows | BLOCK |
| Weight sums | Each capability weights sum to 100% ±1% | BLOCK |
| Evidence_IDs format | Match E-\d{3}(:\F\d+)? pattern | WARNING |
| Tier codes valid | All in {T1,T2,T3,T4,T5,NO_EVIDENCE} | WARNING |
| Excerpt minimum length | ≥50 chars for evidence rows, ≥100 for NO_EVIDENCE | WARNING |
| ELM completeness | Every E-xxx in scoring sheets exists in ELM | WARNING |
| Absent_Evidence_Log | Every NO_EVIDENCE subcap has a log entry | WARNING |
