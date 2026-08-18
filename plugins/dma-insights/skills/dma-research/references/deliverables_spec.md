# Deliverables Specification

Read this file during Batch 3 (report generation) and Batch 4 (appendix artifacts).

---

## Main Report Sections (Batch 3 — single .docx)

### D0: Executive Summary (1 page max)
- Classification decision + confidence score
- Toolkit binding (PARAMETER LOCK)
- Top 7 maturity findings with "So What" impact statement
- Key trend snapshot (5-year trajectory)
- Top 5 evidence gaps
- Top 5 utilization uncertainties with discovery questions

### D1: Entity Profile (11 sections)
- A) Identity & Boundary
- B) Structure & Footprint
- C) Regulatory Footprint (+ Coverage Map if platform/holdco)
- D) Operating Model
- E) Products & Lines of Business
- F) Financial Trends Summary (reference A3 CSV for full table)
- G) Technology Signals Summary (reference A4 CSV for full map) — Zennify-priority flagged
- H) Risk & Compliance Profile
- I) Sentiment Summary
- J) Peer Set (3-6 comparable institutions)
- K) Open Questions

### D2: Classification Decision Log
- Candidates considered
- Decision matrix
- Conflicts & resolution
- Final classification + confidence breakdown (40+30+20+10)
- PARAMETER LOCK statement

### D3: Capability Insights (ALL 4 pillars, ALL 17 capabilities)

Per pillar: summary findings, evidence highlights with E-IDs and KB-IDs, ceiling estimates
with uncertainty bands, key uncertainties, discovery priorities.

**Insight Card format** (embedded per capability):

```
┌─────────────────────────────────────────────────┐
│ INSIGHT CARD: [Capability ID] [Capability Name] │
├─────────────────────────────────────────────────┤
│ Observation: [Finding + Evidence IDs]           │
│ Trend/Pattern: [Direction + timeframe]          │
│ So What: [Business/risk/member impact]          │
│ Ceiling Estimate: L[X] (±[Y])                  │
│ Alternative Explanation: [Competing hypothesis] │
│ Validation Questions: [2-5 specific Qs]         │
│ Claim Type: [FACT/INFERENCE/HYPOTHESIS/CEILING] │
│ Confidence: [HIGH/MEDIUM/LOW] — [reason]        │
│ Capability Impact: [P#C#]                       │
└─────────────────────────────────────────────────┘
```

### D4: Critical Unknowns & Discovery Questions

Table per capability area. Columns:
Capability | What We Know | What We Cannot Know | Uncertainty Band |
Discovery Questions | Internal Doc Reference (INT-xxx)

**Required content:**
- For each P4 capability: technology presence vs utilization unknown
- For P1C4: org capability proxies vs actual expertise
- Recommended internal engagement focus areas

### D5: Technology Utilization Risk Summary

Table columns: Tool/Platform | Zennify Priority? | Presence Evidence | Utilization Evidence |
Recency Tag | Red Flags | Ceiling Estimate | Discovery Priority

**Required narrative:**
- Summary of utilization uncertainties
- Capabilities most at risk of over-estimation
- Recommended discovery focus areas
- Zennify-relevant opportunity areas (greenfield + optimization)

### D6: Safeguard Gates Summary
Table: Gate | Status (PASS/FAIL) | Confidence Impact | Remediation

---

## Appendix Artifacts (Batch 4 — separate files)

### CSV Files

| ID | Name | Key Columns |
|----|------|------------|
| A1 | Evidence Inventory | E-ID, KB-ID, Tier, Type, Publisher, URL, Date, Recency, Capabilities, Key Extract |
| A2 | Search Log | Query, KB Reference, Date, Results, Dead Ends, E-IDs generated |
| A3 | Financial Trends | 5-year table with subvertical-appropriate metrics |
| A4 | Tech Stack Map | Vendor, Category, Zennify Priority, Evidence Level, Utilization, Recency, Red Flags, Ceiling, Discovery Qs |
| A5 | Issue Register | Issue, Regulator, Date, Severity, Status, Milestones, E-IDs |
| A6 | Sentiment Data | Source, Rating, Volume, Themes, Trend, Capability Signals |
| A7 | Coverage Map | Capability, Evidence Available, Coverage Level, Uncertainty, Ceiling, Discovery Priority |
| A8 | Assumptions Register | Assumption, Basis, Falsification Search, Outcome, Confidence Impact |
| A9 | Org Capability | LinkedIn metrics, Job posting analysis, Glassdoor signals, Capability gaps, P1C4 ceiling |

### PNG Visualizations

| ID | Name | Requirements |
|----|------|-------------|
| VIZ-01 | Financial Trends | 5-year trend chart, key metrics |
| VIZ-02 | Capability Coverage Heatmap | 17 capabilities × evidence coverage level |
| VIZ-03 | Technology Stack Map | All platforms, color-coded: Green=Zennify confirmed, Blue=Other confirmed, Orange=Inferred, Gray=Unverified |
| VIZ-04 | Sentiment Trend | 24-month trajectory (conditional — only if data found) |
| VIZ-05 | Issue Timeline | Regulatory/compliance events (conditional — only if issues found) |

**Code requirements**: matplotlib, dpi=150, bbox_inches='tight', plt.close() after saving.

---

## PARAMETER LOCK Block (Final Output)

```
════════════════════════════════════════════════════════════
PARAMETER LOCK: [Subvertical] toolkit bound for scoring phase
CEILING ESTIMATE SUMMARY: [X] capabilities assessed, avg uncertainty ±[Y]
TECH PLATFORMS MAPPED: [N] total, [M] Zennify-priority, [P] confirmed current
KB SOURCES REFERENCED: [N] sources from pillar1_evidence_sources.json
RECENCY STATUS: [X] current, [Y] recent, [Z] legacy/unverified
CLAIM DISTRIBUTION: [N] FACT, [N] INFERENCE, [N] HYPOTHESIS, [N] CEILING_ESTIMATE
STOP: Public Evidence Research Phase Complete. NO SCORING PERFORMED.
════════════════════════════════════════════════════════════
```
