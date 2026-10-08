# Research workbook specification

The workbook's shape has ONE owner: `engine/contract.py` — `SHEETS` (41 sheets) and
`PILLAR_COLUMNS` (33 columns on each `P#_Subcap_Scoring` sheet). `engine.cli start` creates
it, every scoring row seeded with its `SubCap_Name` from the catalogue; `engine.cli validate`
checks it; nothing builds a workbook beside the run (the retired `populate_workbook.py` and
`validate_workbook.py` refuse). This file carries the two things the contract does not: how
to write `What_We_Found`, and how to name a source. (Rewritten 29-09-2026, QA audit
F-L11-042 pair 34: the previous version documented the 22-column layout the engine
replaced, with the score in column J beside the contract's column D.)

## The columns (`python3 -m engine.cli columns` prints this list from the contract)

| Col | Name | Set | Written by |
|---|---|---|---|
| A | `SubCap_ID` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| B | `SubCap_Name` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| C | `Category` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| D | `Score` | app-facing (A–K) | the assessment stage, through `engine.assessment score` |
| E | `Confidence` | app-facing (A–K) | the assessment stage, through `engine.assessment score` |
| F | `Evidence_IDs` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| G | `Source_URLs` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| H | `Evidence_Ceiling` | app-facing (A–K) | the assessment stage, through `engine.assessment score` |
| I | `Caps_Applied` | app-facing (A–K) | the assessment stage, through `engine.assessment score` |
| J | `Rationale` | app-facing (A–K) | the assessment stage, through `engine.assessment score` |
| K | `Proxy_Searched` | app-facing (A–K) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| L | `Dominant_Claim` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| M | `Claim_Label` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| N | `What_We_Found` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| O | `Facet_Coverage` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| P | `DQ_Works` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| Q | `DQ_Fails` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| R | `DQ_Value` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| S | `DQ_Corroborates` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| T | `Triangulation` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| U | `Ceiling_Reasoning` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| V | `Why_It_Matters` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| W | `DMA_Impact` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| X | `DQ_Contradicts` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| Y | `Contradiction_Disposition` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| Z | `Absence_Claimed` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AA | `Proxy_Log` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AB | `Negative_Ladder` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AC | `Discovery_Questions` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AD | `Challenge_Verdict` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AE | `Ceiling_Band` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AF | `Uncertainty` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |
| AG | `Retrieved_At` | research columns (L–AG) | the research tier, through `engine.cli evidence / search / synthesise / absence` |

`Score` is column D. The research tier never writes by column letter: the four
commands above own their columns, and `engine.cli validate` refuses a row that got in around
them. A test (`${CLAUDE_PLUGIN_ROOT}/scripts/tests/test_research_skill_vocabulary.py`) holds this table equal to
`contract.PILLAR_COLUMNS`.

---

## The write-up protocol (`What_We_Found` — the most important column)

`What_We_Found` is the "show your work" column. It bridges raw evidence to scoring. The scorer
reads this column to understand what was found and makes scoring decisions based on it.
A well-written `What_We_Found` makes scoring faster, more accurate, and more defensible.

### Write-Up Structure (MANDATORY for every row with evidence)

```
[ERS: X.XX] [CLAIM_TYPE] [E-xxx:Fy] Source (Tier, Recency): Core finding in 1-2
sentences. [Second source if available: E-xxx:Fy] Corroborating/contrasting point.
[CEILING: x.x ±x.x] [VALIDATION NEED: specific question if applicable]
```

### Write-Up Examples by Quality Level

**HIGH-QUALITY write-up (ERS ≥ 3.5, multiple sources)**:
```
[ERS: 4.30] [FACT] [E-015:F3] Annual Report 2024 (T2, CURRENT): Mobile app redesign
launched Q3 2024 with 47% adoption increase in first 90 days. [E-042:F1] App Store
(T3, CURRENT): Corroborated by 4.2-star rating from 12,450 reviews, up from 3.1 in
2023. [CFPB (T1, CURRENT): Mobile complaints down 28% YoY.] [CEILING: 3.5 ±0.3]
```

**MEDIUM-QUALITY write-up (ERS 2.5-3.5, limited sources)**:
```
[ERS: 3.10] [INFERENCE] [E-022:F2] Press Release Jan 2025 (T2, CURRENT): Announced
partnership with Alkami for digital banking platform migration. [E-031:F1] Job posting
(T4, CURRENT): "Alkami platform administrator" role confirms deployment in progress.
No utilization evidence found. [CEILING: 2.5 ±0.5] [VALIDATE: Deployment completion
date, migration scope, user adoption metrics]
```

**LOW-QUALITY write-up (ERS < 2.5, single source)**:
```
[ERS: 2.00] [HYPOTHESIS] [E-055:F1] Website About Page (T5, CURRENT): Claims "industry-
leading digital capabilities" — no specific features, metrics, or platforms mentioned.
No corroborating evidence from T1-T3 sources. [CEILING: 1.5 ±0.5] [VALIDATE: What
specific digital capabilities exist? What platforms are deployed?]
```

**Declared-absence write-up** (`engine.cli absence` writes the row; this is its `--hunted` shape):
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
4. **Include tier and recency** — (T2, CURRENT) or (T5, STALE)
5. **State the finding, not the source type** — "Mobile complaints down 28%" not "CFPB data shows..."
6. **Include contradictory evidence** when present — don't hide it
7. **End with ceiling implication** — "CEILING: 3.5 ±0.3" not just the fact
8. **Add validation need** if evidence is thin — specific internal discovery question
9. **Minimum 50 characters** for evidence rows, **minimum 100 characters** for a declared absence
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

## Source format (`engine.cli evidence --source … --url … --published …`)

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

**For a declared absence:**
```
"No source — [N] searches executed across [M] tiers. See search log S-xxxx through S-xxxx."
```

---

