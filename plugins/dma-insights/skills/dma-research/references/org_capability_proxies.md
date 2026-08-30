# Organizational Capability Proxies

Read this file during Batch 1 Step 10 (organizational capability analysis) and when
writing A9 (Organizational Capability Assessment) in Batch 4.

---

## Purpose

Internal expertise, culture, and organizational capability are invisible to public research
but can be estimated through proxy signals. These proxies feed P1C4 (Culture & Change)
ceiling estimates and modify confidence across all P4 capabilities.

---

## LinkedIn Analysis Protocol

### Search Queries
- `[Entity] [Tool] site:linkedin.com`
- `[Entity] Salesforce Administrator site:linkedin.com`
- `[Entity] certified [Tool] site:linkedin.com`
- `[Entity] technology team site:linkedin.com`

### Metrics to Extract

| Metric | How to Estimate | Interpretation |
|--------|----------------|---------------|
| Specialist count | Employees with [Tool] in title | Raw capability signal |
| Certified count | Employees mentioning [Tool] certification | Quality signal |
| Specialist ratio | Specialists / Total IT headcount (from LinkedIn company page) | Density signal |

### Interpretation Thresholds

| Ratio | Level | P1C4 Impact |
|-------|-------|-------------|
| < 5% | LOW | Flag organizational capability gap. Cap P1C4 ceiling at L2.5 |
| 5-15% | MEDIUM | Normal capability. No modifier |
| > 15% | HIGH | Strong internal capability. Supports higher P1C4 and P4 ceilings |

---

## Job Posting Seniority Analysis

### Seniority Signals

| Hiring For | Maturity Signal | Interpretation |
|-----------|----------------|---------------|
| Admin / Junior Admin | Building basic capability | Early maturity — implementing |
| Senior Admin / Lead | Scaling existing capability | Mid maturity — operationalizing |
| Architect / Technical Architect | Optimizing at scale | Higher maturity — advancing |
| Director / VP of [Platform] | Strategic investment | Transformation signal |

### Requirement vs. Preferred Analysis

| Tool Placement | Signal | Action |
|---------------|--------|--------|
| Required skill | Tool is critical to operations | Evidence level 3 (confirmed from hiring) |
| Preferred skill | Tool exists but not central | Evidence level 3-4, flag potential |
| Nice to have | Tool is peripheral | URF-06 triggered, downgrade evidence level |

### Job Posting Red Flags

- Posting mentions "clean up" or "remediate" existing implementation → technical debt signal
- Posting mentions "documentation" as primary responsibility → knowledge loss signal
- Posting mentions both tool AND manual alternatives for same function → URF-02, URF-05

---

## Glassdoor/Indeed Culture Signals

### Positive Signals (support higher P1C4, P4C3 ceilings)
- "Great tech stack" / "Modern tools"
- "Good training opportunities" / "Investment in technology"
- "Innovative culture" / "Encouraging experimentation"
- Mentions of specific modern platforms by name

### Negative Signals (cap P1C4 at L3.0, flag capability gap)
- "Outdated systems" / "Need to modernize"
- "No training budget" / "Technical debt"
- "Manual processes" / "Spreadsheet-heavy"
- "Siloed teams" / "Resistance to change"

### Scoring Impact

| Dominant Theme | P1C4 Impact | P4C3 Impact |
|---------------|-------------|-------------|
| Positive dominant | Supports higher ceiling | Supports higher ceiling |
| Negative dominant | Cap at L3.0, flag gap | Cap at L3.0, flag technical debt |
| Mixed | Note uncertainty, generate discovery questions | Add ±0.2 uncertainty |

---

## Turnover / Tenure Signal Detection

### Detection Method
LinkedIn analysis of role tenure for tool-specific positions.

### Interpretation

| Pattern | Signal | Impact |
|---------|--------|--------|
| High turnover (avg <2 years in role) | Capability instability — knowledge loss risk | Flag P1C4 risk, add ±0.2 uncertainty |
| Long tenure (avg >5 years) | Institutional knowledge exists | Verify it's CURRENT knowledge (not legacy) |
| Recent senior departure | Potential knowledge loss event | Flag for discovery — who replaced them? |

---

## Output Format for A9 (Org Capability Assessment)

### Section A: LinkedIn Analysis Summary
```
[Entity] LinkedIn Snapshot (as of [date]):
- Total employees listed: ~[N]
- IT/Technology employees: ~[N] ([X]% of total)
- [Tool 1] specialists: [N] ([X]% of IT) — [HIGH/MEDIUM/LOW]
- [Tool 2] specialists: [N] ([X]% of IT) — [HIGH/MEDIUM/LOW]
- Certified professionals detected: [N] across [tools]
```

### Section B: Job Posting Pattern Analysis
```
Active postings (last 90 days): [N] technology roles
Seniority distribution: [N] Admin, [N] Senior, [N] Architect, [N] Director
Key signals: [list]
Red flags: [list or None]
```

### Section C: Culture Signals
```
Glassdoor overall: [X]/5 ([N] reviews)
Technology theme: [Positive/Negative/Mixed]
Key quotes (paraphrased): [2-3 relevant themes]
```

### Section D: Capability Gap Flags
```
[List any gaps identified from above analysis]
```

### Section E: P1C4 Ceiling Estimate
```
P1C4 Culture & Change ceiling: L[X] (±[Y])
Basis: [Evidence IDs and proxy signals]
Claim type: CEILING_ESTIMATE
Key uncertainty: [What we can't know]
Discovery priority: [HIGH/MEDIUM/LOW]
```
