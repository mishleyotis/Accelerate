# Analytical Framework

Read this file when beginning any analytical work. This framework ensures every conclusion
is defensible, institution-specific, and survives counter-argument challenge.

---

## Argument Construction Framework

Every analytical conclusion — whether a score, finding, or recommendation — must be
constructed as a formal argument before being written into any deliverable.

### The 6-Part Argument Structure

```
1. CLAIM: What are we asserting?
   └── State the conclusion clearly and specifically

2. EVIDENCE: What supports this claim?
   └── List ALL relevant evidence with tier, source, and date
   └── Include both supporting AND challenging evidence

3. REASONING: How does evidence lead to claim?
   └── Explicit logical chain — no implied steps
   └── If you can't articulate the reasoning, the conclusion isn't supported

4. COUNTER-ARGUMENTS: What challenges this claim?
   └── Identify ALL plausible alternative interpretations
   └── If you can't think of counter-arguments, you haven't thought hard enough

5. REBUTTAL: Why do counter-arguments fail?
   └── Address each counter-argument with evidence or logic
   └── If a counter-argument survives rebuttal, revise the claim

6. QUALIFICATION: Under what conditions might this claim fail?
   └── State limitations, assumptions, confidence level
   └── Intellectual honesty strengthens credibility
```

---

## Evidence Triangulation Protocol

No conclusion rests on single-source evidence. Triangulate across four dimensions:

### 1. Source Type Triangulation

Cross-reference evidence from different tier types:
- T1 (Regulatory) vs T2 (Disclosures) vs T3 (Third-Party) vs T4 (Internal) vs T5 (Marketing)
- REQUIREMENT: Minimum 2 different tier types for M3+ scores
- Note divergences between tiers as analytical signals

### 2. Temporal Triangulation

Show trajectory, not just point-in-time:
- Current state (trailing 12 months)
- Historical pattern (2-5 years)
- Forward indicators (announced plans, job postings, patents)
- REQUIREMENT: If only current data exists, flag as "point-in-time snapshot" with reduced confidence

### 3. Perspective Triangulation

Compare how different stakeholders view the same capability:
- Institution's stated view (internal docs, public statements)
- Regulator's view (exam findings, enforcement actions)
- Market's view (analyst coverage, ratings agencies)
- Customer's view (complaints, app ratings, reviews, NPS)
- Employee's view (Glassdoor, turnover data, job postings)
- REQUIREMENT: Note perspective divergences — they are often the most valuable analytical signals

### 4. Metric Triangulation

Input metrics without output metrics = aspiration, not capability:
- Input metrics (investment, headcount, initiatives launched)
- Process metrics (STP rates, cycle times, exception rates)
- Output metrics (volumes, accuracy, adoption rates)
- Outcome metrics (NPS, revenue impact, cost ratios)
- REQUIREMENT: If only input metrics exist, score reflects aspiration (M2 max)

---

## Reasoning Chain Documentation

Every category score requires a documented reasoning chain using this template:

```
CATEGORY: [P#C#] [Name]
CONCLUSION: Score = [X.XX] ([Level])

EVIDENCE INVENTORY:
┌──────┬──────────────────────────────────┬──────┬────────┬──────────────────────────┐
│ ID   │ Evidence Item                    │ Tier │ Date   │ Supports (↑) / Challenges (↓) │
├──────┼──────────────────────────────────┼──────┼────────┼──────────────────────────┤
│ E-01 │ [Description]                    │ T2   │ [Date] │ ↑ M3: [reason]           │
│ E-02 │ [Description]                    │ T3   │ [Date] │ ↑ M4: [reason]           │
│ E-03 │ [Description]                    │ T5   │ [Date] │ ↓ Contradicts E-02       │
│ E-04 │ [Description]                    │ T1   │ [Date] │ ↓ Caps at M3             │
└──────┴──────────────────────────────────┴──────┴────────┴──────────────────────────┘

REASONING:
Step 1: E-01 and E-02 suggest capability at [level] because [logic]
Step 2: However, E-03 contradicts by claiming [X], but E-03 is T5 marketing
        while E-02 is T3 third-party validated → E-02 takes precedence
Step 3: E-04 (T1 regulatory finding) caps the maximum at [level]
Step 4: Synthesizing: [level] supported by evidence, [level] ceiling from E-04

ALTERNATIVE INTERPRETATIONS:
Alt-1: [Alternative reading] → Rejected because: [reason with evidence]
Alt-2: [Another alternative] → Rejected because: [reason with evidence]

CONFIDENCE: [HIGH / MEDIUM / LOW]
- Evidence coverage: [Complete / Partial / Limited]
- Source agreement: [High / Mixed / Low]
- Recency: [Current / Dated / Stale]

FINAL SCORE: [X.XX] after caps: [list caps applied]
```

---

## Analytical Red Flags

These patterns demand deeper investigation before scoring. If detected, document the
investigation and resolution in the reasoning chain.

### 1. Input-Output Disconnect
**Signal**: High investment claims + poor outcome metrics
**Example**: "$50M digital transformation" + "3.2 app rating"
**Investigation**: Where did the money go? Implementation failure? Wrong priorities?

### 2. Marketing-Reality Gap
**Signal**: T5 claims dramatically exceed T1-T3 evidence
**Example**: Website says "industry-leading AI" + no analyst recognition
**Investigation**: Aspiration vs. delivery? Definition inflation?

### 3. Temporal Inconsistency
**Signal**: Improvement claimed + metrics flat or declining
**Example**: "Transformed our operations" + STP rate unchanged 3 years
**Investigation**: What specifically improved? How is success measured?

### 4. Regulatory Divergence
**Signal**: Institution's view differs from regulator's view
**Example**: Internal: "Strong compliance culture" + CFPB consent order
**Investigation**: Awareness gap? Remediation incomplete?

### 5. Customer Experience Disconnect
**Signal**: Internal metrics positive + customer sentiment negative
**Example**: "98% SLA achievement" + 2.5 star app rating
**Investigation**: Wrong SLAs? Measurement gaming? Selective metrics?

### 6. Peer Outlier
**Signal**: Score dramatically different from comparable peers (>1.5 gap)
**Example**: P4C2 Analytics at M4 when all peers at M2-M3
**Investigation**: True differentiation? Evidence quality issue? Peer selection problem?

---

## 5-Layer Document Analysis

Mandatory for every internal document. Surface-level extraction is FORBIDDEN.

### Layer 1: Explicit Extraction
What does the document explicitly state?
- Quantitative metrics with exact values
- Stated strategies, initiatives, timelines
- Explicit risk assessments and ratings
- Output format: `Metric: [Name] | Value: [X] | Period: [timeframe] | Source: [DOC] (p.X)`

### Layer 2: Implicit Signals
What does the document imply but not state directly?
- Language signals: "considering/exploring" → M1–M2; "implemented/standardized" → M3–M4; "optimized/AI-powered" → M4–M5
- Resource allocation patterns: where money goes reveals true priorities
- Organizational structure: reporting lines indicate capability maturity
- Output format: `Implicit Signal: [Interpretation] | Evidence: [Quote] | Maturity: [M1-M5] | Confidence: [H/M/L]`

### Layer 3: Absence Analysis
What's MISSING that should be present?
- At M3+, expect: documented strategy, KPIs, data governance, automation metrics
- Absence of expected content is itself evidence (typically M1–M2 signal)
- Check against the Maturity Descriptors for what should exist at each level
- Output format: `Absence: [What's missing] | Expected for: [M3/M4] | Implication: [Capability impact]`

### Layer 4: Contradiction Detection
Does this contradict other sources?
- Types: METRIC_MISMATCH, TIMELINE_CONFLICT, CAPABILITY_CLAIM_VS_EVIDENCE, RISK_RATING_INCONSISTENCY
- Resolution hierarchy: T1 > T2 > T3 > T4 > T5; recent > older; specific > general; outcome > input
- Output format: `Contradiction: [Desc] | Source A: [X] | Source B: [Y] | Resolution: [Which wins] | Impact: [On scoring]`

### Layer 5: Strategic Inference
What does this mean for the institution's trajectory?
- Where will they be in 2 years on current path?
- What single gap most constrains overall maturity?
- What capability interdependencies exist?
- Output format: `Theme: [X] | Evidence: [IDs] | Inference: [Y] | Implications: [Z]`
