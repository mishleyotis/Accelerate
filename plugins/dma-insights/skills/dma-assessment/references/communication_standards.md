# Communication Standards

Read this file when writing any narrative content — capability analyses, executive summaries,
recommendations, or peer comparisons.

---

## Inline Citation Standard

Every factual claim is immediately followed by its source. No statement floats without
attribution. The reader should never ask "where did that come from?"

### Citation Format
```
[Claim/metric] (Source Description, Tier, Date/Period)
```

### Examples
```
"App rating improved from 3.2 to 4.1 over 24 months (iOS App Store, T3, trailing 24mo)"

"The consent order cited deficiencies in overdraft disclosure practices
(CFPB Enforcement, T1, March prior year)"

"Management indicated a $15M digital investment planned for the coming fiscal year
(Board Strategy Presentation Q3, T2, current year)"

"First-contact resolution stands at 68% (Internal Contact Center Report, T4, current FY)"
```

### Narrative Integration

**WRONG** (citations disconnected from flow):
```
The institution has improved its mobile capabilities. The app rating is 4.1.
This represents significant improvement. Customer complaints are declining.
[Sources: App Store, CFPB data]
```

**RIGHT** (citations woven into narrative):
```
Mobile capabilities have strengthened materially: the iOS app rating improved
from 3.2 to 4.1 over trailing 24 months (iOS App Store, T3, current), a
trajectory corroborated by declining CFPB complaint volumes — down 23%
year-over-year in the mobile banking category (CFPB Consumer Complaint Database,
T1, trailing 12 months). This improvement coincides with management's stated
$8M mobile platform investment (Annual Report, T2, current FY), suggesting the
investment is translating to measurable customer experience gains.
```

---

## Absence Documentation

When expected evidence is NOT found, document the absence with the same rigor as
found evidence. Absences are evidence.

```
The assessment sought but did not find evidence of:

• Data governance policy or framework: Neither the Annual Report (T2, current)
  nor the publicly filed Risk Management disclosure (T2, current) reference a
  formal data governance program. Internal document request for "Data Governance
  Policy" (INT-REQ-045) returned no response.

• Chief Data Officer or equivalent role: LinkedIn search for "[Institution]
  Chief Data Officer" (T3, current) returned no results. Organizational chart
  in Board materials (INT-BOARD-023, T4, current) shows no dedicated data role.

ABSENCE IMPLICATION:
The absence of these artifacts, expected for M3+ data governance maturity,
constrains P4C1 to M2 maximum regardless of other evidence.
```

---

## Language Sensitivity Rules

### Mandatory Substitutions
| Never Use | Instead Use |
|-----------|------------|
| "gap" | "area for improvement" or "opportunity" |
| "weakness" | "development area" |
| "critical gap" | "priority improvement area" |
| "lagging" | "opportunity to strengthen" |
| "failing" | "area requiring focused attention" |
| "poor" | "below peer benchmark" |
| "behind" | "opportunity to advance toward peer median" |

### Timeline Language
Never use fixed time ranges ("0-6 months", "12-18 months"). Always anchor to
institutional milestones or events:
- "Aligned with the [system] migration (target: [quarter])"
- "Before the next [regulatory exam / annual planning cycle / board review]"
- "Following completion of [named initiative]"

### The SO WHAT Test
Every finding must follow: **FINDING → SO WHAT (for THIS institution) → NOW WHAT**

Before writing any finding, complete this mentally:
1. FINDING: What did we observe? (with evidence citation)
2. SO WHAT: Why does this matter for THIS institution specifically?
   - Quantify the impact where possible (cost, risk, opportunity)
   - Connect to institution's specific context (size, strategy, competitive position)
3. NOW WHAT: What specific action should be taken?
   - Name the action specifically
   - Explain why THIS action for THIS institution

---

## Specificity Enforcement

### The Generic Statement Test
Before writing ANY sentence, ask: "Could this sentence appear unchanged in a report
for a DIFFERENT institution?" If YES → rewrite with institution-specific data.

### Forbidden Generic Patterns (never produce these or similar)
- "The institution should improve its digital capabilities" → Instead: "[Institution]'s P2C3 score of 2.50 vs. peer median 3.20 suggests unified omnichannel platform investment would address the 68% FCR rate (Internal Dashboard, T4)"
- "Digital transformation is important for competitiveness" → DELETE. Replace with specific finding.
- "Industry best practices suggest..." → Cite a specific peer: "[Peer Name] achieved 3.45 on P2C3 after implementing [specific solution] (Peer Analysis, T3)"
- "Consider implementing..." → "Deploy [specific solution] to address [specific gap] because [specific evidence-based reason]"
- "There is room for improvement in..." → "[Institution]'s [metric] of [value] falls [X.XX] below the peer median of [value], driven by [root cause with evidence]"

### Multi-Source Synthesis Pattern
When analyzing a capability with mixed evidence, use this structure:

```
[Capability] presents a nuanced picture requiring evidence triangulation.

POSITIVE INDICATORS suggest [emerging/established/advanced] capability:
[Evidence 1 with inline citation]. [Evidence 2 with inline citation].
[Evidence 3 if applicable with inline citation].

NEGATIVE INDICATORS suggest execution challenges persist:
[Evidence 1 with inline citation]. [Evidence 2 with inline citation].

RECONCILIATION:
The divergence between [source A] and [source B] suggests [specific analytical
insight, e.g., "a classic input-output disconnect: investments have been made,
but outcomes have not yet followed"]. [Higher-tier evidence] takes precedence
over [lower-tier evidence] per the evidence hierarchy.

CONCLUSION:
Raw evidence supports [level] ([rationale]). However, [cap type] caps the score
at [X.XX] per [cap rule]. The [evidence type] supports this cap as appropriate.

FINAL SCORE: [X.XX] ([Level]), Confidence: [H/M/L]
Evidence IDs: [list]
```

---

## Recency Language Rules

- Use RELATIVE time references only. NEVER hardcode years.
- "current year", "prior year", "trailing 12 months", "2 years ago"
- NOT: "2025", "FY2024", "January 2023"
- Rationale: Assessments may be referenced after the assessment date; relative
  references remain accurate.
