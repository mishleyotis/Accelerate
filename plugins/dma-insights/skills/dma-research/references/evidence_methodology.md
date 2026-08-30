# Evidence Methodology & Quality Framework

Read this file at the START of Batch 1 before collecting any evidence, and reference
continuously during Batches 2-3 (subcap research). This file governs HOW evidence is
collected, extracted, classified, scored, and stored.

---

## Evidence Rank Score (ERS) — MANDATORY for every evidence item

Every evidence item collected during research receives a composite quality score that
determines its weight in ceiling estimates and its citation priority in the research report.

### Formula

```
ERS = (0.35 × Tier_Score) + (0.25 × Recency_Score) + (0.20 × Specificity_Score) + (0.20 × Corroboration_Score)
```

ERS ranges from 1.0 (lowest quality) to 5.0 (highest quality).

### Factor Scores (each 1.0 to 5.0)

**Tier Score** (weight: 35%):
| Tier | Score | Rationale |
|------|-------|-----------|
| T1 — Regulatory/Audited | 5.0 | Independently verified, legally authoritative |
| T2 — Official Disclosures | 4.0 | Publicly filed, liability for misstatement |
| T3 — Third-Party Analysis | 3.0 | Independent perspective, professional standards |
| T4 — Internal (Unvalidated Narrative) | 2.0 | Unstructured memos, anecdotal claims — no external verification |
| T5 — Marketing/Claims | 1.0 | Explicitly promotional, no accountability |

**Critical Tier Classification Rules:**
- **Hubbl scans, BuiltWith, Wappalyzer = T1** (machine-generated, timestamped, objective)
- **Structured discovery notes with specific tech/metrics = T2** (formal engagement outputs)
- **NEVER classify Hubbl as T4.** This is the most common misclassification — it suppresses
  scores via T4 ceilings when the data is actually machine-verified deployment evidence.

**Recency Score** (weight: 25%):
| Age | Score | Label |
|-----|-------|-------|
| Current year (trailing 12 months) | 5.0 | CURRENT |
| Prior year (12-24 months) | 4.0 | RECENT |
| 2 years ago (24-36 months) | 3.0 | DATED |
| 3 years ago (36-48 months) | 2.0 | STALE |
| 4+ years ago | 1.0 | ARCHIVAL |

**Specificity Score** (weight: 20%):
| Level | Score | Example |
|-------|-------|---------|
| Quantified metric with methodology | 5.0 | "STP rate: 72.3%, measured monthly across all loan products" |
| Quantified metric without methodology | 4.0 | "STP rate: approximately 72%" |
| Specific qualitative with examples | 3.0 | "Implemented RPA for 3 lending processes" |
| General qualitative claim | 2.0 | "Pursuing automation across operations" |
| Vague or aspirational | 1.0 | "Committed to digital transformation excellence" |

**Corroboration Score** (weight: 20%):
| Level | Score | Description |
|-------|-------|-------------|
| 3+ independent sources agree | 5.0 | Multiple unrelated sources confirm same fact |
| 2 independent sources agree | 4.0 | Two unrelated sources confirm |
| Single source, T1-T2 | 3.0 | One source, high authority |
| Single source, T3 | 2.0 | One source, moderate authority |
| Single source, T4-T5 | 1.0 | One source, low authority |

"Independent" means different origins. Annual Report + Investor Deck from the same
institution are NOT independent (same author, same incentives). Annual Report + CFPB
complaints ARE independent.

### ERS Worked Examples

**High-ERS (4.30)**: App rating 4.2 stars from 12,450 reviews (T3, current, quantified,
corroborated by CFPB trend + Glassdoor).

**Low-ERS (2.00)**: "Industry-leading digital capabilities" from institution website
(T5, current, vague, uncorroborated).

**Medium-ERS (3.65)**: NCUA exam rated "satisfactory" (T1, 3 years old, specific rating,
single source).

### ERS Usage in Research

1. **Ceiling estimate weighting**: Higher-ERS evidence anchors ceiling estimates more strongly
2. **Evidence_Excerpt priority**: Column U in workbook should contain the highest-ERS finding
3. **Report citation order**: Lead each capability section with highest-ERS evidence
4. **Confidence flagging**: Capabilities where highest-ERS evidence < 2.5 → flag LOW confidence
5. **Contradiction resolution**: When evidence conflicts, higher ERS wins (with tier override)

### ERS Tie-Breaking

1. Higher tier wins
2. If tied: more recent wins
3. If tied: more specific wins
4. If tied: more corroborated wins

### Absence as Evidence

Searched-and-not-found IS evidence. It gets an ERS:
- Tier: Same as source checked (e.g., T3 if LinkedIn was searched)
- Recency: 5.0 (search was current)
- Specificity: 4.0 ("No CDO found on LinkedIn or leadership page")
- Corroboration: 4.0 if checked 2+ sources, 2.0 if checked 1

---

## Fact-Level Extraction Protocol

Evidence items often contain multiple distinct facts. Each fact maps to a different
subcapability. Use this granularity:

### Evidence ID Format

```
[E-xxx]        = Evidence item (one source document/page/report)
[E-xxx:Fy]     = Specific fact #y within evidence item #xxx
```

### Example: Multi-Fact Extraction from Annual Report

```
E-015: Gesa Credit Union Annual Report 2024 (T2, CURRENT) [KB-US-050]
  E-015:F1: "Board approved 3-year digital roadmap in Q2 2024"
    → Maps to: P1C1.1.1 (strategy doc), P1C1.1.5 (board oversight)
    → Specificity: 4.0 (specific action, dated, no methodology detail)
  E-015:F2: "$15M technology investment planned over 3 years"
    → Maps to: P1C1.1.2 (business alignment), P4C3 (tech investment)
    → Specificity: 4.0 (quantified, no breakdown)
  E-015:F3: "Launched redesigned mobile app Q3 2024, 47% adoption increase"
    → Maps to: P2C3 (omnichannel), P2C2 (digital engagement)
    → Specificity: 5.0 (quantified with timeframe)
  E-015:F4: "Partnered with [fintech] for real-time fraud monitoring"
    → Maps to: P3C2 (fraud), P1C3 (innovation partnerships)
    → Specificity: 3.0 (specific partnership, no outcome data)
  E-015:F5: No mention of data governance, CDO, or data strategy
    → Maps to: P4C1 (ABSENCE signal — expected for M3+ but missing)
    → Specificity: 4.0 (specific, documented absence)
```

### Key Principle: One `web_fetch` on a Rich Document Can Populate 20+ Subcaps

This is why `web_fetch` on annual reports, 10-Ks, investor presentations, and regulatory
filings is critical. A single rich document yields multiple high-ERS facts mapped across
pillars. Always prioritize fetching these document types when found in search results.

**Documents Worth Fetching in Full**:
- Annual reports / 10-K filings
- Investor presentations / earnings calls
- Regulatory exam summaries (if public)
- Press releases with quantified metrics
- Vendor case studies mentioning the institution
- Technology partnership announcements
- Industry analyst reports featuring the institution
- ESG/sustainability reports

---

## Evidence Triangulation Protocol

No ceiling estimate rests on single-source evidence. Triangulate across four dimensions:

### 1. Source Type Triangulation
Cross-reference across different tiers:
- T1 vs T2 vs T3 vs T4 vs T5
- REQUIREMENT: Ceiling estimates with only single-tier evidence get ±0.3 additional uncertainty

### 2. Temporal Triangulation
Show trajectory, not point-in-time:
- Current state (trailing 12 months)
- Historical pattern (2-5 years)
- Forward indicators (job postings, announcements, patents)
- REQUIREMENT: If only current data, flag as "point-in-time snapshot" with ±0.2 additional uncertainty

### 3. Perspective Triangulation
Compare stakeholder views of the same capability:
- Institution's stated view (official disclosures, website)
- Regulator's view (exam findings, enforcement)
- Market's view (analyst coverage, ratings)
- Customer's view (app ratings, CFPB complaints, reviews)
- Employee's view (Glassdoor, LinkedIn, job postings)
- REQUIREMENT: Note divergences — they are the most valuable analytical signals

### 4. Metric Triangulation
Input metrics without output metrics = aspiration, not capability:
- Input: investment, headcount, initiatives launched
- Process: STP rates, cycle times, exception rates
- Output: volumes, accuracy, adoption rates
- Outcome: NPS, revenue impact, cost ratios
- REQUIREMENT: If only input metrics exist, ceiling reflects aspiration (max L2.5)

---

## 5-Layer Document Analysis (HYBRID/INTERNAL modes)

When internal documents are provided, apply this framework to EVERY document.
Surface-level extraction is FORBIDDEN.

### Layer 1: Explicit Extraction
What the document explicitly states.
- Quantitative metrics with exact values
- Stated strategies, initiatives, timelines
- Explicit risk assessments, ratings, findings
- Output: `Metric: [Name] | Value: [X] | Period: [timeframe] | Source: [DOC] (p.X)`

### Layer 2: Implicit Signals
What the document implies but doesn't directly state.
- Language signals: "considering/exploring" → L1-L2; "implemented/standardized" → L3-L4; "optimized/AI-powered" → L4-L5
- Resource allocation: where money goes reveals true priorities
- Organizational structure: reporting lines indicate maturity
- Output: `Implicit Signal: [Interpretation] | Evidence: [Quote] | Ceiling: [L#] | Confidence: [H/M/L]`

### Layer 3: Absence Analysis
What's MISSING that should be present for higher maturity.
- At L3+, expect: documented strategy, KPIs, data governance, automation metrics
- Absence of expected content is evidence (typically L1-L2 ceiling signal)
- Output: `Absence: [What's missing] | Expected for: [L3/L4] | Implication: [ceiling impact]`

### Layer 4: Contradiction Detection
Does this contradict other sources?
- Types: METRIC_MISMATCH, TIMELINE_CONFLICT, CAPABILITY_CLAIM_VS_EVIDENCE, RISK_INCONSISTENCY
- Resolution: T1 > T2 > T3 > T4 > T5; recent > older; specific > general; outcome > input
- Output: `Contradiction: [Desc] | Source A: [X] | Source B: [Y] | Resolution: [winner] | Impact: [on ceiling]`

### Layer 5: Strategic Inference
What does this mean for trajectory?
- Where will they be in 2 years on current path?
- What single gap most constrains overall maturity?
- What capability interdependencies exist?
- Output: `Theme: [X] | Evidence: [IDs] | Inference: [Y] | Implications: [Z]`

---

## Analytical Red Flags

These patterns demand deeper investigation. When detected, execute additional targeted
searches and document the investigation in the evidence index.

### 1. Input-Output Disconnect
**Signal**: High investment claims + poor outcome metrics
**Example**: "$50M digital transformation" + "3.2 app rating"
**Action**: Search for implementation results, measure outcomes vs claims

### 2. Marketing-Reality Gap
**Signal**: T5 claims dramatically exceed T1-T3 evidence
**Example**: Website says "industry-leading AI" + no analyst recognition
**Action**: Search for validation — vendor case studies, analyst mentions

### 3. Temporal Inconsistency
**Signal**: Improvement claimed + metrics flat or declining
**Example**: "Transformed operations" + STP rate unchanged 3 years
**Action**: Search for specific improvement evidence, outcome metrics

### 4. Regulatory Divergence
**Signal**: Institution view differs from regulator view
**Example**: "Strong compliance" + CFPB consent order
**Action**: Prioritize T1 evidence, investigate remediation status

### 5. Customer Experience Disconnect
**Signal**: Internal metrics positive + customer sentiment negative
**Example**: "98% SLA achievement" + 2.5 star app rating
**Action**: Analyze complaint themes, check if right metrics are being tracked

### 6. Peer Outlier
**Signal**: Evidence suggests capability dramatically different from peers
**Example**: Small CU showing advanced AI but no data team
**Action**: Verify evidence quality, check if vendor-driven vs organic

### 7. Technology Stack Mismatch
**Signal**: Enterprise platform + basic/admin hiring only
**Example**: Salesforce FSC deployed + hiring Junior Admin only
**Action**: Flag URF-01, investigate depth of utilization

---

## Evidence Index Schema

Every evidence item collected MUST be stored in this schema (saved to checkpoint):

```json
{
  "evidence_id": "E-001",
  "source_name": "NCUA Call Report Q4 2024",
  "source_url": "https://...",
  "source_type": "regulatory_filing",
  "tier": "T1",
  "recency_tag": "CURRENT",
  "date_published": "2025-03-15",
  "kb_source_id": "KB-US-001",
  "ers_scores": {
    "tier_score": 5.0,
    "recency_score": 5.0,
    "specificity_score": 4.0,
    "corroboration_score": 3.0,
    "ers_total": 4.30
  },
  "facts": [
    {
      "fact_id": "E-001:F1",
      "fact_text": "Total assets $4.2B as of Q4 2024",
      "claim_type": "FACT",
      "specificity_score": 5.0,
      "subcap_mappings": ["P1C1.1.2"],
      "supports_or_challenges": "supports",
      "ceiling_implication": "L3+ (large CU with scale for investment)"
    }
  ],
  "corroborating_evidence_ids": [],
  "contradicting_evidence_ids": [],
  "search_query_that_found_it": "[Entity] NCUA call report assets",
  "batch_collected": 1,
  "notes": ""
}
```

---

## Evidence-to-Subcap Mapping Rules

1. **One fact can map to multiple subcaps** — a single annual report fact about board
   oversight maps to governance AND strategy subcaps
2. **Record the mapping at FACT level** (E-xxx:Fy), not just evidence level (E-xxx)
3. **Record direction**: Does this fact SUPPORT higher maturity or CHALLENGE/CONSTRAIN it?
4. **Record ceiling implication**: What maturity level does this evidence suggest?
5. **For the workbook**: Column K gets the fact-level IDs (E-001:F3, E-015:F1), Column U
   gets the most relevant fact text, Column V gets the source document name
