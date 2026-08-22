# Evidence Index Template

Use this structure when building the evidence index during Phase 1.

---

## Evidence Index Columns

| Column | Description | Format |
|--------|------------|--------|
| Evidence_ID | Unique identifier | E-001, E-002... (public) or INT-[DOC]-001 (internal) |
| Description | Brief summary of evidence | Max 100 words |
| Source | Document name or URL | Full reference |
| Tier | Evidence tier classification | T1, T2, T3, T4, T5 |
| Date | When this evidence was current | Relative: "current FY", "prior year", etc. |
| Categories | Which P#C# categories this informs | Comma-separated list: P1C1, P2C3 |
| Signal | Direction of evidence | POSITIVE, NEGATIVE, NEUTRAL, CONTRADICTORY |
| Level_Indicated | What maturity level this suggests | M1, M2, M3, M4, M5 |
| Confidence | How reliable is this evidence | HIGH, MEDIUM, LOW |

## Internal Document Abbreviations

| Abbreviation | Document Type |
|-------------|--------------|
| BOARD | Board presentations, minutes |
| AUDIT | Internal/external audit reports |
| STRAT | Strategy documents |
| TECH | Technology assessments, architecture docs |
| RISK | Risk assessments, registers |
| COMP | Compliance reports, exam responses |
| VEND | Vendor assessments, RFPs |
| HR | HR reports, training materials |
| PROJ | Project charters, status reports |
| POL | Policies, procedures |
| ARCH | Architecture documents, system diagrams |
| FIN | Financial reports, budgets |
| OPS | Operations reports, dashboards |

## Fact Extraction Format (for internal documents)

```
fact_id: INT-[DOC_ABBREV]-[SEQ]
document_name: [Full filename]
page_or_section: [Page number or section heading]
fact_text: [Verbatim or close paraphrase, max 100 words]
categories_supported: [P1C1, P2C3, ...]
maturity_signal: POSITIVE | NEGATIVE | NEUTRAL
maturity_level_implied: M1-M5
confidence: HIGH | MEDIUM | LOW
```
