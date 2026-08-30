# DMA Report Template

Read this file during Phase 7 when generating the assessment report (.docx). This template
mirrors the official `Digital_Maturity_Assessment_Report_Template.docx` structure exactly.
When generating the report, use the docx skill and follow this section-by-section.

The report template docx is bundled at `templates/Digital_Maturity_Assessment_Report_Template.docx`.
If available, clone it and populate; otherwise, generate a new docx following this structure.

---

## Cover Page

```
DIGITAL MATURITY
ASSESSMENT REPORT

[INSTITUTION NAME]

Assessment Date: [ASSESSMENT DATE]
Assessment ID: [ASSESSMENT-ID]
```

Assessment ID format: `DMA-[SUB_VERTICAL_ABBREV]-[YYYYMMDD]-[SEQ]`

---

## Section 1: Executive Summary

```
Overall Digital Maturity Score: [X.XX] — [MATURITY LEVEL]
```

### The Bottom Line
2-3 sentences capturing the strategic essence. MUST be institution-specific. Include:
overall positioning vs peers, primary constraint, key opportunity. Apply specificity test.

### Key Strengths
3 items, format:
```
[Strength 1] → [Business implication and strategic value]
[Strength 2] → [Business implication and strategic value]
[Strength 3] → [Business implication and strategic value]
```
Each strength must name the specific capability, score, and its concrete business value.

### Critical Gaps
3 items, format:
```
[Gap 1]: Score [X.X] vs Peer Median [X.X] — [Specific risk if not addressed]
[Gap 2]: Score [X.X] vs Peer Median [X.X] — [Specific risk if not addressed]
[Gap 3]: Score [X.X] vs Peer Median [X.X] — [Specific risk if not addressed]
```

### Strategic Recommendation
1-2 sentences on highest-priority action. Be specific about the recommended initiative,
investment range, and projected score improvement.

---

## Section 2: Assessment Context

### Institution Profile
```
Name: [Institution Name]
Type: [Charter type, primary membership/customer base]
Scale: [Members/Customers], [Total Assets], [Net Worth Ratio]
Geography: [Branch count], [Geographic footprint]
```

### Methodology & Evidence
```
Framework: Zennify [Sub-Vertical] Digital Maturity Model v5.0 — 4 pillars,
16 categories; a 1-5 SCORE scale (M1 Foundational … M5, the workbook's
own scale) which RENDERS in four bands — Activating, Building,
Competing, Differentiating. Never name a fifth band in prose: it has no
colour to render into (charter invariant 6).
Benchmarks: [Sub-Vertical] — [Size Tier] capability medians, P25/P75, best, laggard
Evidence Mode: [PUBLIC / INTERNAL / HYBRID]
```

NOTE: The bundled docx template may still reference "L1-L5" in its methodology text.
When populating, replace all L1-L5 references with M1-M5.

### Evidence Sources
List top evidence sources with tier classification:
```
[Source 1 description] ([Source name], Tier [X])
[Source 2 description] ([Source name], Tier [X])
[Source 3 description] ([Source name], Tier [X])
```

### Limitations
State evidence mode limitations clearly. For PUBLIC mode: no access to internal policies,
risk reports, model documentation, or detailed channel KPIs. Control-heavy capabilities
scored conservatively.

---

## Section 3: Trend Analysis (5-Year Context)

### Financial Growth Story
Narrative explaining financial trajectory with inline hyperlinks. Include asset growth CAGR,
member/customer growth rate, and trend classification:
ACCELERATING / STABLE / STAGNANT / DECLINING

### Digital Evolution Story
Timeline of major digital initiatives over the past 5 years with outcomes. What worked,
what didn't, and how this context informs the current assessment.

### Sentiment Trajectory
App ratings and complaint trends over time with trend interpretation. Include iOS/Android
ratings, CFPB complaint volumes, and employee sentiment from Glassdoor/Indeed.

```
[INSERT: 5-Year Trajectory Chart — Generated via Python matplotlib]
```

---

## Section 4: Issue Register

Opening: "This section documents regulatory actions, enforcement orders, material findings,
and other issues that may impact capability scores through the Severity-to-Maturity Cap Matrix."

### Issue Time Map

TABLE: Issue Register
| Issue ID | Type | Date | Status | Severity | Age (mo) | Source |
|----------|------|------|--------|----------|----------|--------|
| ISS-001 | [Type] | [Date] | [Active/Terminated] | [S1/S2/S3] | [X] | [T1/T2] |

### Severity Cap Impact
Document which capabilities are capped due to issues and the specific cap applied.
Reference the cap rules from scoring_methodology.md.

---

## Section 5: Assessment Results

### Pillar Scorecard

TABLE: Pillar Scorecard
| Pillar | Score | vs Median | Trend | Level |
|--------|-------|-----------|-------|-------|
| P1: Strategy, Governance & Culture | [X.XX] | [+/-X.XX] | [↑/↓/→] | [Level] |
| P2: Member/Customer Experience & Engagement | [X.XX] | [+/-X.XX] | [↑/↓/→] | [Level] |
| P3: Operations, Risk & Compliance | [X.XX] | [+/-X.XX] | [↑/↓/→] | [Level] |
| P4: Data, Analytics & Technology | [X.XX] | [+/-X.XX] | [↑/↓/→] | [Level] |

```
[INSERT: Radar Chart — Pillar Benchmark Comparison with Trends]
[INSERT: Capability Heatmap with Trends]
```

---

## Section 6: Pillar Deep Dives

Opening: "The following sections provide detailed analysis of each pillar, including
capability scorecards, evidence summaries, and strategic implications."

### For EACH pillar (6.1 through 6.4), use this structure:

```
# 6.X. Pillar [N]: [Pillar Name]

Pillar Weight: [XX]% | Pillar Score: [X.XX] | vs Median: [+/-X.XX] | Trend: [↑/↓/→]
```

#### Capability Scorecard

TABLE: Capability Scorecard (one per pillar)
| Capability | Score | vs Median | Trend | Conf. | Gap |
|-----------|-------|-----------|-------|-------|-----|
| P#C#: [Name] | [X.X] | [+/-X.X] | [↑/↓/→] | [H/M/L] | [X.X] |

#### Pillar Score Calculation
```
P[N] = (C1 score × weight) + (C2 score × weight) + ... = X.XX
```
Show the full weighted calculation with every term.

#### What We See
For each capability in the pillar, 1-2 sentence evidence summary with inline citations:
```
P#C# [Capability Name] ([X.X]): [Evidence-based observation with inline hyperlink citation]
```
Cite the highest-ERS evidence for each capability. Every claim must have an inline citation.

#### Why It Matters
2-3 sentences connecting pillar performance to strategic business implications specific to
THIS institution. Answer: "What does this pillar performance mean for their ability to
achieve their business objectives?"

---

## Section 7: Benchmark Comparison

### The Strategic Pattern
2-3 sentences explaining overall positioning vs peers in size tier and sub-vertical.

### Areas of Strength (Above P75)
```
[Capability]: Score [X.X] vs P75 [X.X] — This means [interpretation]
```

### Areas for Improvement (Below Median)
```
[Capability]: Score [X.X] vs Median [X.X] — Urgency: [HIGH/MEDIUM] because [specific risk]
```

---

## Section 8: Gap Prioritization

### Gap-to-Solution Mapping

TABLE: Gap-to-Solution Mapping
| Initiative | Gap(s) | Solution | Investment | Score Outcome |
|-----------|--------|----------|-----------|---------------|
| [Name] | GAP-XX | [Solution] | $XXX-$XXX | [Cap]: X.X→X.X |

### Priority Calculation Methodology
```
Priority = (0.25 × Business Impact) + (0.20 × Risk Exposure) + (0.20 × Competitive Gap)
         + (0.15 × Effort Inverse) + (0.10 × Quick Win) + (0.10 × Trend Momentum)
```

TABLE: Gap Priority Register
| Gap ID | Capability | Current | Target | Gap | Root Cause | Priority Score |
|--------|-----------|---------|--------|-----|-----------|---------------|
| GAP-01 | [Name] | [X.X] | [X.X] | [X.X] | [Institution-specific root cause] | [X.X] - [CRITICAL/HIGH/MEDIUM] |

### Critical Gaps Detail
For each CRITICAL/HIGH priority gap, provide institution-specific root cause analysis
with evidence citations.

---

## Section 9: Recommendations

Opening: "The following recommendations are prioritized based on business impact, risk
exposure, competitive positioning, and implementation feasibility. Each recommendation
includes institution-specific root cause analysis and expected score outcomes."

### For EACH recommendation (repeat this structure):

```
RECOMMENDATION [N]: [Initiative Name]
Addresses Gap(s): [GAP-XX] | Score Impact: [X.X] → [X.X] (+[X.X])
```

#### Root Cause Analysis
Institution-specific root cause with evidence citations (highest-ERS evidence first).

#### Recommended Solution
```
[Solution Name] — Type: [Catalog/Custom/Innovative] |
Investment: $[XXX]K-$[XXX]K | Time to Value: [X-X months]
```

#### Why This Solution for This Institution
Explain why this specific solution addresses this institution's specific situation.
Apply the specificity test — this section must NOT be generic.

#### Expected Outcomes
```
Capability Score: [X.X] → [X.X] (+[X.X]) within [X] months
Pillar Score Impact: [X.X] → [X.X] (+[X.X])
[Specific KPI]: [Current baseline] → [Target] ([X] months)
```

#### Risk of Inaction
Specific consequences if this gap is not addressed, including score trajectory and
business impact. Quantify where possible.

---

## Section 10: Transformation Roadmap

### Current State
```
Overall Score: [X.XX] — [MATURITY LEVEL]
```

### Phase 1: Foundation (Months 0-6)
[Initiatives, dependencies, expected outcomes]

#### Phase 1 Expected Outcomes
```
Overall Score: [X.XX] → [X.XX] (+[X.XX])
Phase 1 Investment: $[X.X]M - $[X.X]M
```

### Phase 2: Build (Months 6-12)
[Same structure as Phase 1]

### Phase 3: Scale (Months 12-18)
[Same structure as Phase 1]

### Projected Maturity Trajectory

TABLE: Maturity Trajectory
| Timeframe | Overall | P1 | P2 | P3 | P4 | Level | Milestone |
|-----------|---------|----|----|----|----|-------|-----------|
| Current | [X.XX] | [X.X] | [X.X] | [X.X] | [X.X] | [Level] | Baseline |
| +6 months | [X.XX] | [X.X] | [X.X] | [X.X] | [X.X] | [Level] | [Key milestone] |
| +12 months | [X.XX] | [X.X] | [X.X] | [X.X] | [X.X] | [Level] | [Key milestone] |
| +18 months | [X.XX] | [X.X] | [X.X] | [X.X] | [X.X] | [Level] | [Key milestone] |

### Total Investment Summary
```
Total Roadmap Investment: $[X.X]M - $[X.X]M
Score Improvement: [X.XX] → [X.XX] (+[X.XX]) over [X] months
Level Progression: [Current Level] → [Target Level]
```

---

## Section 11: Data Gaps & Confidence

### What We Couldn't Assess
"The following areas had insufficient evidence for confident scoring. This impacts overall
assessment confidence and may understate or overstate certain capabilities."

List each gap with its impact on confidence and affected capabilities.

### Capabilities Marked N/A
List any capabilities marked "N/A — Insufficient Public Signal" due to the 30% Unknown Rule.

### Recommended Next Steps
"To improve assessment accuracy, the following internal evidence should be provided:"
List 3+ specific internal document/data requests.

---

## Section 12: Evidence Sources

Opening: "All sources are hyperlinked inline throughout this report. Below is a summary
organized by evidence tier."

### Tier 1 — Regulatory/Audited Sources
List each with hyperlink and date. Sort by ERS within tier.

### Tier 2 — Official Disclosures
### Tier 3 — Third-Party/News
### Tier 4 — Internal Documents (If Provided)
### Tier 5 — Marketing/Website Claims

---

## Appendix A: Capability Definitions

For each of the 16 categories, provide a 2-3 sentence definition. These are standard
across all assessments:

**P1C1: Digital Strategy & Vision** — Existence of a documented digital strategy and vision
aligned with the institution's overall strategic plan and customer-centric outcomes. Includes
a clear view of how digital capabilities support growth, efficiency, and experience over a
multi-year horizon.

**P1C2: Governance & Risk Appetite** — Formal governance of digital initiatives and a clearly
articulated risk appetite for technology, data, and innovation. Includes cross-functional
steering committees, defined roles, and integration of cybersecurity, fraud, third-party,
and regulatory considerations.

**P1C3: Innovation Management & Funding** — Structured management of digital innovation and
experimentation, including defined innovation themes, idea intake and evaluation processes,
and governance over pilots. Includes dedicated innovation funding and clear criteria for
scaling or sunsetting pilots.

**P1C4: Culture & Change Enablement** — The organization's culture and change-management
disciplines as they relate to digital transformation. Includes leadership sponsorship,
formal change management frameworks, communication and training programs, and incentives
that encourage continuous improvement.

**P1C5: Sustainable Finance & ESG Integration** — Integration of ESG considerations into
digital strategy and operations. Includes sustainable finance initiatives, climate risk
assessment, DEI programs, and community impact measurement.

**P2C1: Digital Marketing & Acquisition** — Digital marketing capabilities for attracting
and converting target segments. Includes SEO/SEM, content marketing, social media, digital
advertising, marketing automation, and lead management.

**P2C2: Onboarding & Fulfillment** — End-to-end digital onboarding and fulfillment journeys
for core products and services. Includes account opening, loan origination, document
collection, identity verification, and time-to-fund optimization.

**P2C3: Omnichannel Servicing & Support** — Seamless servicing across digital, contact center,
and physical channels. Includes channel integration, service consistency, self-service
capabilities, and intelligent routing.

**P2C4: Personalization & Proactive Engagement** — Personalized and proactive engagement
based on data and triggers across channels. Includes next-best-action, targeted offers,
financial wellness tools, and lifecycle-based communications.

**P3C1: Core Process Automation** — Automation of core operational processes to improve
efficiency and reduce manual errors. Includes STP, workflow automation, exception handling,
and back-office digitization.

**P3C2: Operational Risk & Fraud Management** — Management of operational risks and fraud
prevention/detection. Includes transaction monitoring, fraud detection models, operational
loss tracking, and risk event management.

**P3C3: Compliance, Supervision & Surveillance** — Regulatory compliance, supervision, and
surveillance capabilities. Includes complaint management, regulatory reporting, conduct
monitoring, and audit trail management.

**P3C4: Business Resilience & Third-Party Management** — Business continuity, disaster
recovery, and third-party risk management. Includes BCP/DR planning, vendor due diligence,
concentration risk management, and resilience testing.

**P4C1: Data Management & Governance** — Enterprise data management and governance. Includes
data quality, master data management, data lineage, metadata management, and data stewardship.

**P4C2: Analytics & AI Enablement** — Advanced analytics and AI/ML capabilities. Includes
descriptive/predictive/prescriptive analytics, model development, MLOps, and AI governance.

**P4C3: Technology Architecture & Integration** — Technology architecture and integration
capabilities. Includes API management, microservices, cloud strategy, core banking
integration, and technical debt management.

**P4C4: Information Security & Cybersecurity** — Information security and cybersecurity.
Includes IAM, threat detection, vulnerability management, incident response, and security
architecture.

---

## Appendix B: Maturity Level Definitions

**M1 — Foundational**: Ad-hoc, reactive, minimal documentation. Processes are manual and
inconsistent. No formal strategy or governance. Technology is legacy and siloed.

**M2 — Developing**: Some standardization beginning. Basic documentation exists. Initial
pilots underway. Awareness of gaps but limited action. Partial automation of select processes.

**M3 — Established**: Documented processes and policies. Consistent execution across the
organization. Integrated technology platforms. Data-driven decision making emerging. Regular
governance and review cycles.

**M4 — Advanced**: Optimized and continuously improving. Proactive rather than reactive.
Advanced analytics and automation. Strong governance with clear accountability. Innovation
embedded in culture.

**M5 — Transformational**: Industry-leading capabilities. Continuous innovation. Real-time,
predictive operations. Seamless customer experiences. Ecosystem orchestration. Serves as
benchmark for peers.

---

## Appendix C: Sub-Vertical Pillar Weights

TABLE: Pillar Weights by Sub-Vertical
| Sub-Vertical | P1 Strategy | P2 Experience | P3 Operations | P4 Data/Tech |
|-------------|------------|--------------|--------------|-------------|
| Credit Unions | 25% | 30% | 20% | 25% |
| Regional Banks | 25% | 30% | 20% | 25% |
| Commercial Lending | 20% | 20% | 35% | 25% |
| Corporate & Investment Banks | 20% | 20% | 35% | 25% |
| Insurance Carriers | 20% | 20% | 30% | 30% |
| Insurance Brokerages | 20% | 35% | 20% | 25% |
| Wealth Managers / RIAs | 25% | 30% | 20% | 25% |
| Asset Management | 20% | 30% | 25% | 25% |

---

## Chart Generation Notes

Generate the following charts using Python matplotlib during Phase 7:

1. **Radar Chart** — Pillar Benchmark Comparison with Trends (Section 5)
2. **Capability Heatmap** — Color-coded by maturity level with trend arrows (Section 5)
3. **5-Year Trajectory Chart** — Financial, digital, and sentiment trends (Section 3)
4. **Maturity Trajectory** — Projected score improvement over roadmap phases (Section 10)

All chart data must come from the Scoring Workbook (single source of truth).
