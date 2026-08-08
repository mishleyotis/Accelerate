# Scoring Methodology

Read this file when scoring any capability. Follow the 8-step decision tree exactly.

---

## 8-Step Scoring Decision Tree

For EACH subcapability, follow this exact sequence:

### Step 1: Evidence Collection

Search for evidence using:
- Public Evidence Inventory sources for this capability
- Internal document analysis (if INTERNAL/HYBRID mode)
- Web search queries specific to this capability (see `capability_criteria.md`)

Document EVERYTHING found:
- Positive signals (capability present at some level)
- Negative signals (capability absent or weak)
- Contradictory signals (conflicting information across sources)
- Absence signals (expected evidence not found — this IS evidence)

### Step 2: Evidence Classification

For each evidence item, assign:

**Tier**:
- T1: From regulator, auditor, or court? → T1
- T2: Official company disclosure (10-K, board minutes, annual report)? → T2
- T3: Independent third-party (analyst, news, ratings, app store)? → T3
- T4: Internal document not externally validated? → T4
- T5: Marketing, website, promotional material? → T5

**Signal Direction**:
- POSITIVE: Evidence supports capability presence at level [M1-M5]
- NEGATIVE: Evidence indicates capability weakness or absence
- NEUTRAL: Provides context but not maturity signal
- CONTRADICTORY: Conflicts with other evidence

### Step 3: Establish Evidence-Based Ceiling

What is the MAXIMUM supportable level given evidence quality?

| Condition | Ceiling |
|-----------|---------|
| Highest tier = T5 only | M2 (2.0) |
| Highest tier = T4 (no T1-T3) | M2.5 (2.5) |
| Highest tier = T3 (no T1-T2) | M4 (4.0) |
| Highest tier = T1 or T2 | M5 (5.0) |
| Single source only | Additional cap at 3.0 |
| Evidence >24 months old | Apply -0.3 staleness discount |

### Step 4: Determine Raw Maturity Level

Using POSITIVE evidence, determine which M-level criteria are satisfied. Load the relevant
Pillar XLSX file's Maturity Descriptors sheet for the specific subcapability's M1-M5
definitions, then match evidence to the closest descriptor.

**General scoring calibration** (use when subcap-specific descriptors are ambiguous):

**M1 (1.0-1.4)**: Capability absent or purely ad-hoc
- No documentation, no ownership, no metrics, reactive only
- If ALL these are true, or no evidence exists: Score = 1.0

**M2 (1.5-2.4)**: Basic capability exists but inconsistent
- Some documentation (partial, outdated, draft)
- Resources allocated but not dedicated
- Pilots or initial implementation in progress
- Score = 1.5 + (0.2 × additional criteria met beyond 3)

**M3 (2.5-3.4)**: Standardized, documented, consistently executed
- Dedicated resources and clear ownership
- Metrics tracked and reported regularly
- External validation exists (audit, benchmark, rating)
- Score = 2.5 + (0.2 × additional criteria met beyond 3)

**M4 (3.5-4.4)**: Optimized, data-driven, cross-functional
- Processes optimized based on data analysis
- Proactive identification and resolution
- Performance above peer median
- External recognition (awards, case studies, analyst mention)
- Score = 3.5 + (0.15 × additional criteria met beyond 4)

**M5 (4.5-5.0)**: Industry-leading, innovative
- Top quartile performance
- Innovation embedded — creating new approaches
- External parties benchmark against
- Regulatory exemplar status
- Score = 4.5 + (0.1 × additional criteria met beyond 4, max 5.0)

### Step 5: Apply Negative Evidence Adjustments

For each NEGATIVE evidence item:

**Regulatory findings**:
- Active/unresolved (S3): Apply severity cap → 1.5 on primary capability
- Terminated <24mo or MRA outstanding (S2): Cap at 3.0
- Resolved <24mo: Note in narrative, monitor

**Customer sentiment** (applies to P2 categories):
- App rating <3.0 → Cap at 2.0
- App rating 3.0-3.5 → Cap at 2.5
- App rating 3.5-4.0 → Cap at 3.5
- Complaint trend increasing >20% YoY → additional -0.3

**Operational incidents**:
- Major incident <12mo → reduce by 0.5
- Pattern of incidents → reduce by 0.3

**Peer comparison**:
- Score >1.0 below peer median → Flag for validation (is it justified or evidence gap?)

### Step 6: Resolve Contradictions

If contradictory evidence exists, apply resolution hierarchy:

1. T1 beats T2-T5 (regulatory/audited most authoritative)
2. Within same tier: Recent beats older
3. External beats internal (for capability claims)
4. Specific beats general (quantified > qualitative)
5. Outcome metrics beat input metrics

**Document the resolution**: "Evidence A (T3, current) claims [X]; Evidence B (T5, current) claims [Y]. Resolution: A takes precedence per T3>T5 rule."

If UNRESOLVABLE: Default to conservative (lower) interpretation. Reduce confidence to LOW. Flag as data quality issue in report.

### Step 7: Apply Cross-Pillar Dependencies

Check all dependency constraints. These caps are non-negotiable:

| If This Score... | Then Cap... | Rationale |
|-----------------|------------|-----------|
| P1C2 (Governance) < 2.5 | ALL P3 categories at 3.0 | Weak governance can't support advanced risk management |
| P4C4 (Cybersecurity) < 2.5 | P4C1 (Data Governance) at 3.0 | Data governance requires security foundation |
| P3C3 (Compliance) < 2.5 | P2C2 (Onboarding) at 3.0 | Compliance gaps constrain customer-facing innovation |
| P4C1 (Data Governance) < 2.5 | P2C4 (Personalization) at 3.0 | Personalization requires data quality foundation |
| P4C3 (Architecture) < 2.5 | P3C1 (Automation) at 3.0 | Automation requires integration capability |
| Disclosed breach <12mo | P4C4 at 2.0 | Active security failure |
| Disclosed breach <24mo | P4C4 at 3.0 | Recent security failure |

### Step 8: Calculate Final Score

```
FINAL = min(Raw_Score, Evidence_Ceiling, All_Applicable_Caps)
```

Document completely:
- Raw Score: [X.XX] (from Step 4)
- Evidence Ceiling: [X.XX] (from Step 3)
- Caps Applied: [list each cap, its value, and why it triggered]
- Final Score: [X.XX]
- Confidence: [HIGH / MEDIUM / LOW]
- Evidence IDs: [list all IDs that informed the score]

---

## Aggregation Formulas

### Subcapability → Capability
```
capability_score = Σ(subcap_score × subcap_weight)
```
If no weights defined, use equal weighting: `capability_score = mean(subcap_scores)`

### Capability → Category
```
category_score = Σ(capability_score × capability_weight)
```
If no weights defined, use equal weighting.

### Category → Pillar
```
pillar_score = Σ(category_score × category_weight)
```
Use category weights from the Pillar XLSX files.

### Pillar → Overall
```
overall_score = Σ(pillar_score × pillar_weight)
```
Use sub-vertical-specific pillar weights from the SKILL.md table.

### Validation Rules
- All weights at each level must sum to 100% (1.0). If they don't, STOP and fix.
- Show all intermediate calculations. Never present a final number without showing how you got there.
- Round to 2 decimal places at each aggregation level.
- If >30% of subcapabilities have NO_EVIDENCE → mark the capability as N/A.

---

## Recency Rules

- Use RELATIVE time references only. NEVER hardcode years.
- "current year", "prior year", "2 years ago" — not "2025", "2024", "2023"
- Recency weights: current year 1.0 | prior year 0.85 | 2yr ago 0.7 | 3yr ago 0.55 | 4+ yr 0.4
- If most recent evidence >24 months old → flag STALE_DATA, confidence = LOW
