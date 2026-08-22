# Critical Unknowns & Uncertainty Framework

Read this file during Batch 2 Step 4 (uncertainty band calculation) and when writing
D4 (Critical Unknowns & Discovery Questions) in Batch 3.

---

## Core Principle

"I don't know" is the most defensible finding in public evidence research. Public evidence
reveals PRESENCE but not UTILIZATION, ADOPTION, or EFFECTIVENESS. Every capability estimate
carries inherent uncertainty that must be quantified, not hidden.

---

## Uncertainty Band Calculation

```
Total uncertainty = Base uncertainty + Σ(Red flag modifiers) + Σ(Evidence gap modifiers)
Maximum: ±0.8 — if exceeded, mark as "Cannot reliably estimate"
```

### Base Uncertainty by Capability

| Capability | Knowable Publicly | Unknowable Publicly | Base ± | Key Internal Docs |
|-----------|-------------------|---------------------|--------|-------------------|
| P1C1 Digital Strategy | Strategy announcements, press releases | Board priorities, investment allocation | ±0.3 | INT-001, INT-002 |
| P1C2 Governance | Board composition, committee charters | Risk appetite specifics, audit findings | ±0.4 | INT-010, INT-012 |
| P1C3 Innovation | Partnership announcements, fintech deals | Innovation budget, pipeline | ±0.3 | INT-020, INT-021 |
| P1C4 Culture & Change | Glassdoor ratings, job postings | Training investment, expertise depth | ±0.5 | INT-030, INT-032 |
| P1C5 ESG | Published ESG reports | Actual progress, integration depth | ±0.3 | INT-040 |
| P2C1 Digital Marketing | Digital presence, website quality | Marketing tech utilization, conversion rates | ±0.4 | INT-050 |
| P2C2 Onboarding | Whether digital opening exists | Time-to-fund, abandonment rates, STP rate | ±0.3 | INT-055 |
| P2C3 Omnichannel | Available channels (app, web, branch) | Channel utilization mix, integration quality | ±0.4 | INT-060 |
| P2C4 Personalization | AI announcements | Actual implementation depth, model performance | ±0.5 | INT-065 |
| P3C1 Automation | Technology platform presence | STP rates, exception rates, manual workarounds | ±0.5 | INT-070 |
| P3C2 Fraud & Op Risk | Disclosed fraud incidents | Fraud loss rates, detection effectiveness | ±0.4 | INT-080 |
| P3C3 Compliance | Enforcement actions (or absence) | Internal compliance posture, MRA status | ±0.3 | INT-085 |
| P3C4 Resilience & TPRM | Major outages (if any) | BCP/DR capabilities, vendor management maturity | ±0.5 | INT-090 |
| P4C1 Data Governance | CDO existence, data team hiring | Data quality metrics, governance maturity | ±0.5 | INT-100 |
| P4C2 Analytics & AI | AI/ML announcements | Model deployment count, analytics adoption rates | ±0.5 | INT-110 |
| P4C3 Tech Architecture | Core platform (sometimes) | Technical debt, API adoption, integration quality | ±0.5 | INT-120 |
| P4C4 Cybersecurity | Breaches (if disclosed), SOC2 | Security posture, vulnerability management | ±0.4 | INT-130 |

### Red Flag Modifiers (additive to base)

| Red Flag | Modifier | Triggered When |
|----------|----------|---------------|
| URF-01 Capability Plateau | +0.2 | Long vendor tenure + basic hiring only |
| URF-02 Adoption Gap | +0.2 | Enterprise tool + manual process mentions |
| URF-03 Stagnation | +0.1 | No recent vendor case studies despite relationship |
| URF-04 Entitlement Underutilization | +0.2 | Hiring for capabilities in existing licenses |
| URF-05 Shadow Systems | +0.2 | Multiple tools for same function |
| URF-06 Peripheral Tool | +0.1 | Tool is "nice to have" not required |

### Evidence Gap Modifiers (additive to base)

| Gap | Modifier | Triggered When |
|-----|----------|---------------|
| No T1/T2 evidence | +0.2 | Capability has only T3-T5 sources |
| Single source only | +0.1 | Capability has only 1 evidence item |
| Evidence >24 months old | +0.1 | Most recent evidence is stale |

### Calculation Example

```
P4C3 (Tech Architecture) for a credit union with:
- Base uncertainty: ±0.5
- URF-01 triggered (long Fiserv tenure, hiring Admins): +0.2
- URF-03 triggered (no recent Fiserv case study): +0.1
- No T1/T2 evidence for architecture: +0.2

Total: 0.5 + 0.2 + 0.1 + 0.2 = ±1.0 → CAPPED at ±0.8
Result: "Cannot reliably estimate — uncertainty exceeds threshold"
```

---

## Systematic Unknowns (ALWAYS unknown from public evidence)

These are structurally invisible to external research. Flag for every assessment:

1. Contract/entitlement details (what licenses they own)
2. Utilization metrics (are they using what they own)
3. Internal expertise levels (do they have competent staff)
4. Internal strategic debates (greenfield vs brownfield, ROI questioning)
5. Organizational dysfunction (knowledge loss, team silos)
6. Shadow systems (spreadsheets alongside enterprise tools)
7. Vendor relationship health (satisfaction, renewal likelihood)

---

## Discovery Question Requirements

For EACH capability with uncertainty ≥ ±0.4, generate 3-5 discovery questions that:
1. Reference specific internal document IDs from the KB (INT-xxx)
2. Target the specific unknowable dimension
3. Would materially change the ceiling estimate if answered
4. Are specific enough for a client conversation (not "tell me about your data governance")

**Good**: "What percentage of loan originations flow through nCino vs. manual processing?
(Ref: INT-067 Process Automation Metrics)"

**Bad**: "How mature is your automation capability?"

---

## Output Format for D4 (Critical Unknowns Table)

| Capability | What We Know | What We Cannot Know | Uncertainty ± | Discovery Questions | Internal Doc Ref |
|-----------|-------------|--------------------|----|----|----|
| P4C3 | Core: Fiserv DNA confirmed [E-015]. Digital: Alkami detected [E-022]. | Technical debt level, API adoption rate, integration architecture quality | ±0.8 (CAPPED) | 1. What % of integrations use APIs vs batch files? 2. When was last core upgrade? 3. What is your API transaction volume? | INT-120, INT-045 |
