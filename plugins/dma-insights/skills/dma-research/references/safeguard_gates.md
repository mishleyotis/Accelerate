# Safeguard Gates

Read this file during Batch 2 Step 5. Run ALL 16 gates. Document PASS/FAIL for each.
Failed gates require remediation before proceeding.

---

## Gate Definitions

| Gate | Name | Pass Criteria | Failure Impact |
|------|------|--------------|----------------|
| G1 | Identity & Boundary | T1 or T1+T2 corroboration of entity identity + boundary | BLOCK — cannot classify |
| G2 | Regulatory Anchor | T1 evidence of primary regulator (or Regulatory Coverage Map for platforms) | BLOCK — cannot classify |
| G3 | Evidence Coverage | Regulatory anchor + operating model + financials (3+ years) + issue search | Reduces confidence, flag gaps |
| G4 | Traceability | All sections have Evidence IDs or "Not found" + attempted sources from KB | BLOCK — unverifiable output |
| G5 | Classification Anchors | Based on regulatory context + operating model + revenue engine | BLOCK — cannot bind toolkit |
| G6 | Trend Validity | 3+ datapoints for any trend claim, OR labeled "Snapshot/Hypothesis" | Relabel as snapshot |
| G7 | Artifact Pack | All required visualizations generated as separate PNG files | Deliver in Batch 4 |
| G8 | Partnership Validity | Tech claims evidence-leveled (1-4), boundary-checked, utilization-assessed | Downgrade confidence |
| G9 | Issue Validity | Each issue has dated milestones + status verification attempt | Flag as unverified |
| G10 | No Toolkit Blending | Single subvertical toolkit bound. Multi-model = separate assessments | BLOCK — restart classification |
| G11 | Technology Utilization | All tech findings have utilization level + red flag check + uncertainty band | Reduce P4 confidence |
| G12 | Org Capability Proxy | LinkedIn/job posting/Glassdoor analysis completed for P1C4/P4 | Flag as unassessed |
| G13 | Critical Unknowns | Critical Unknowns Register completed with discovery questions per capability | Missing context for scoring |
| G14 | Ceiling Estimate Framing | All capability estimates framed as ceilings with uncertainty bands | Relabel all estimates |
| G15 | KB Grounding | All sources traced to catalogue IDs where applicable | Reduced traceability |
| G16 | Recency Verification | All tech findings have recency tag and last-confirmed date | Flag as UNVERIFIED |

---

## Gate Severity

- **BLOCK gates** (G1, G2, G4, G5, G10): MUST pass before proceeding. If failed, remediate immediately.
- **Confidence gates** (G3, G8, G11, G12, G15, G16): Failure reduces confidence levels but does not block.
- **Labeling gates** (G6, G13, G14): Failure requires relabeling output, not additional research.
- **Deferred gates** (G7, G9): Can be addressed in later batches.

---

## Output Format (D6)

| Gate | Status | Evidence | Confidence Impact | Remediation |
|------|--------|---------|-------------------|-------------|
| G1 Identity | PASS | NCUA charter #12345 [E-001] | None | — |
| G11 Tech Utilization | FAIL | 3 platforms missing utilization assessment | -1 tier on P4 confidence | Complete utilization checklist for [platforms] |
