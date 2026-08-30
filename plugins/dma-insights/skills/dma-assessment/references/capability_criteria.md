# Capability Scoring Criteria

**16 categories, v7.0.** The retired 17th (P1C5, Sustainable Finance & ESG
Integration) has been removed: it does not exist in catalogue v7.0 and every
one of its cells resolves NOT_COMPARABLE across versions, so scoring against
it produced criteria for a category the app cannot render.

**Two scales, and they are not the same.** The SCORE is 1-5 (M1…M5) and is
what the workbook carries and this file calibrates. The BAND is what
RENDERS, and there are exactly four of them — `<2 Activating`, `<3 Building`,
`<4 Competing`, `>=4 Differentiating`, on the raw score before display
rounding. There is no fifth band and no colour for one. Never write a fifth
band word into prose or a payload: it will not match what renders (charter
invariant 6).

Read this file when scoring specific categories. For each category, use the diagnostic
questions to guide evidence collection and the level indicators to calibrate scoring.
For subcapability-level M1-M5 descriptors, always load the relevant Pillar XLSX file.

---

## P1: Strategy, Governance & Culture

### P1C1: Digital Strategy & Vision

DIAGNOSTIC QUESTIONS:
1. Does a board-approved digital strategy exist with multi-year horizon?
2. Are digital initiatives explicitly linked to business outcomes?
3. Is there executive-level ownership (CDO, CTO, or equivalent)?
4. Are KPIs defined, measured, and reported to the board?
5. Is the strategy refreshed based on market/competitive feedback?

LEVEL INDICATORS:
- M1: No documented digital strategy; digital treated as IT cost center; no digital exec
  Evidence patterns: No innovation section on website; no digital mentions in annual report
- M2: Strategy document exists but lacks measurable outcomes; "digital transformation" mentioned without specifics
  Evidence patterns: Annual report mentions "digital investment"; job postings for digital roles
- M3: Board-approved strategy with 3-year horizon; named initiatives with owners/timelines; quarterly KPI reporting
  Evidence patterns: Strategy referenced in investor presentation; digital KPIs in annual report
- M4: Strategy linked to competitive differentiation; regular refresh; digital embedded in all BU plans; quantified ROI
  Evidence patterns: Analyst reports cite digital capabilities; industry awards; digital metrics in investor materials
- M5: Strategy sets industry direction; external recognition as digital leader; innovation as core competency
  Evidence patterns: Case studies published; conference keynotes; other institutions benchmark against

SEARCH QUERIES: "[Institution] digital transformation strategy", "[Institution] annual report technology", "[Institution] CDO CTO digital"

### P1C2: Governance & Risk Appetite

DIAGNOSTIC QUESTIONS:
1. Is there a formal technology/digital governance framework?
2. Are risk appetite statements defined for digital initiatives?
3. Do digital initiatives go through formal risk assessment?
4. Is there board-level oversight of digital/technology risk?
5. Are three lines of defense clearly defined for digital?

LEVEL INDICATORS:
- M1: No formal governance framework; ad-hoc decisions; no risk appetite
  Evidence: No technology committee in proxy; audit findings cite governance gaps
- M2: Basic approval processes; risk assessment for major projects only
  Evidence: Technology mentioned in audit committee charter; basic policies exist
- M3: Documented framework; regular technology committee (quarterly+); risk appetite statements
  Evidence: Technology/Digital Committee in proxy; risk appetite in disclosures
- M4: Risk-aware innovation culture; real-time risk monitoring; integrated GRC platform
  Evidence: No regulatory findings; clean audit opinions; mature risk framework
- M5: Governance as competitive advantage; regulatory exemplar
  Evidence: Regulatory exemplar citations; thought leadership on governance

CROSS-PILLAR DEPENDENCY: P1C2 < 2.5 → Cap ALL P3 categories at 3.0

SEARCH QUERIES: "[Institution] board technology committee", "[Institution] risk management framework", "[Institution] [regulator] examination"

### P1C3: Innovation Management & Funding

DIAGNOSTIC QUESTIONS:
1. Is there dedicated innovation funding or budget?
2. Are there formal processes for evaluating new technologies?
3. Does the institution engage with fintechs/startups systematically?
4. Is there a sandbox or experimentation environment?
5. Are innovation metrics tracked and reported?

LEVEL INDICATORS:
- M1: No dedicated innovation activity or funding
- M2: Ad-hoc innovation; occasional fintech engagement
- M3: Dedicated innovation budget; formal fintech evaluation; documented POC pipeline
- M4: Innovation lab/team; active fintech partnerships; sandbox; innovation metrics
- M5: Industry-recognized innovation leader; patents; spin-offs; innovation revenue

SEARCH QUERIES: "[Institution] fintech partnership", "[Institution] innovation lab", "[Institution] technology patent"

### P1C4: Culture & Change Enablement

DIAGNOSTIC QUESTIONS:
1. Is there a digital literacy/training program?
2. Are employees empowered to suggest/implement digital improvements?
3. Is digital fluency part of performance evaluation?
4. How is organizational change managed for digital initiatives?
5. What is employee sentiment on digital transformation?

LEVEL INDICATORS:
- M1: Resistance to digital change; no training; siloed culture
- M2: Basic digital training; some change management for major projects
- M3: Comprehensive training; formal change methodology; digital goals in reviews
- M4: Digital-first culture; continuous learning; strong engagement scores
- M5: Industry-recognized culture; employer brand for digital talent

SEARCH QUERIES: "[Institution] Glassdoor reviews", "[Institution] digital training", "[Institution] employer awards technology"

## P2: Member/Customer Experience & Engagement

### P2C1: Digital Marketing & Acquisition

DIAGNOSTIC QUESTIONS:
1. What percentage of new accounts come through digital channels?
2. Is there marketing automation capability?
3. Is there multi-touch attribution for digital marketing?
4. What is cost-per-acquisition for digital vs. traditional?
5. Is there A/B testing of digital marketing content?

LEVEL INDICATORS:
- M1: <10% digital acquisition; no marketing automation
- M2: 10-25% digital acquisition; basic email automation
- M3: 25-50% digital; marketing automation platform; campaign analytics
- M4: 50-75% digital; advanced personalization; multi-touch attribution
- M5: >75% digital; AI-driven marketing; industry-leading CPA

SEARCH QUERIES: "[Institution] digital marketing", "[Institution] mobile app downloads", "[Institution] customer acquisition"

### P2C2: Onboarding & Fulfillment

DIAGNOSTIC QUESTIONS:
1. Can accounts be opened end-to-end digitally?
2. What is average time-to-fund for digital applications?
3. What is digital application abandonment rate?
4. Is there document automation (e-signature, digital verification)?
5. What percentage of applications are straight-through processed?

LEVEL INDICATORS:
- M1: Paper-based onboarding; branch/office visit required
- M2: Some digital capture; manual review required; >5 day time-to-fund
- M3: End-to-end digital possible; 1-3 day time-to-fund; e-signatures; >50% STP
- M4: Same-day account opening; >80% STP; digital ID verification; <25% abandonment
- M5: Real-time account opening; industry-leading conversion; frictionless

CROSS-PILLAR DEPENDENCY: P3C3 (Compliance) < 2.5 → Cap P2C2 at 3.0

SEARCH QUERIES: "[Institution] online account opening", "[Institution] digital application", "site:[institution].com apply"

### P2C3: Omnichannel Servicing & Support

DIAGNOSTIC QUESTIONS:
1. Can customers seamlessly transition between channels?
2. What is first-contact resolution rate?
3. What percentage of service requests are self-served?
4. Is there a unified customer view across channels?
5. What is customer satisfaction by channel?

SENTIMENT DATA REQUIRED (T3):
- iOS/Android app store ratings and review trends
- CFPB complaint data (customer service category)
- Google reviews / BBB rating
- Glassdoor (employee view of service quality)

LEVEL INDICATORS:
- M1: Siloed channels; inconsistent experience; no self-service
- M2: Basic digital servicing; limited self-service; no unified view
- M3: Multiple channels integrated; unified history; >60% FCR; >50% self-service
- M4: Seamless omnichannel; >75% FCR; AI-assisted agents; 4.0+ app rating
- M5: Industry-leading service; AI-driven; predictive; >4.5 app rating

SENTIMENT CAPS: <3.0 stars → 2.0 | 3.0-3.5 → 2.5 | 3.5-4.0 → 3.5 | Complaints +20% YoY → -0.3

SEARCH QUERIES: iOS/Android App Store "[Institution]", CFPB complaints "[Institution]", "[Institution] customer service"

### P2C4: Personalization & Proactive Engagement

DIAGNOSTIC QUESTIONS:
1. Is there behavioral-based personalization of digital experience?
2. Are there next-best-action capabilities?
3. Is there event-triggered proactive outreach?
4. Is there product recommendation capability?
5. What is offer acceptance rate?

LEVEL INDICATORS:
- M1: No personalization; mass communications only
- M2: Segment-based communications; basic product targeting
- M3: Behavioral personalization; lifecycle engagement; 10-15% offer acceptance
- M4: Real-time personalization; AI-driven NBA; >20% offer acceptance
- M5: Industry-leading; predictive engagement; >30% offer acceptance

CROSS-PILLAR DEPENDENCY: P4C1 (Data Governance) < 2.5 → Cap P2C4 at 3.0

---

## P3: Operations, Risk & Compliance

### P3C1: Core Process Automation

DIAGNOSTIC QUESTIONS:
1. What is straight-through processing rate for key processes?
2. Is there RPA or intelligent automation deployed?
3. Are exception rates tracked and managed?
4. Is there workflow automation for operational processes?
5. What is manual intervention rate?

LEVEL INDICATORS:
- M1: Primarily manual; <20% STP
- M2: Some automation; 20-40% STP; basic workflow tools
- M3: Standardized automation; 40-60% STP; RPA in production
- M4: Advanced automation; 60-80% STP; ML-assisted decisioning
- M5: Hyper-automation; >80% STP; autonomous operations

CROSS-PILLAR DEPENDENCY: P4C3 (Architecture) < 2.5 → Cap P3C1 at 3.0

### P3C2: Operational Risk & Fraud Management

DIAGNOSTIC QUESTIONS:
1. Is there real-time fraud detection capability?
2. What is fraud loss rate vs. industry benchmark?
3. Is there behavioral analytics for fraud detection?
4. Are operational risks tracked systematically?
5. Is there incident management with root cause analysis?

LEVEL INDICATORS:
- M1: Reactive fraud response; no systematic risk tracking
- M2: Basic fraud rules; manual monitoring; some risk tracking
- M3: Real-time alerting; risk register; incident management; losses within benchmark
- M4: ML-based detection; predictive risk; proactive controls; losses below benchmark
- M5: Industry-leading prevention; near-zero losses; risk intelligence

### P3C3: Compliance, Supervision & Surveillance

DIAGNOSTIC QUESTIONS:
1. Is there a compliance management system?
2. Are regulatory changes tracked and implemented systematically?
3. Is there complaint analytics and trending?
4. Is there automated compliance monitoring?
5. What is examination history and trend?

REGULATORY DATA REQUIRED (T1):
- Enforcement actions (CFPB, OCC, FDIC, Fed, NCUA, State, SEC, FINRA)
- Consent orders, MOUs, cease and desist orders
- Fair lending investigations
- BSA/AML findings

LEVEL INDICATORS:
- M1: Reactive compliance; manual; recent enforcement actions
- M2: Basic program; some automation; MRAs outstanding
- M3: Comprehensive program; regulatory change management; clean recent exams
- M4: Proactive compliance; predictive risk; positive regulatory relationships
- M5: Compliance as enabler; regulatory exemplar; thought leader

SEVERITY CAPS: S3 (active enforcement <12mo) → 1.5 | S2 (terminated <24mo, MRA) → 3.0

### P3C4: Business Resilience & Third-Party Management

DIAGNOSTIC QUESTIONS:
1. Is there comprehensive BCP/DR testing?
2. What is RTO achievement rate?
3. Is there a third-party risk management program?
4. Are critical vendors assessed and monitored?
5. Is there operational resilience testing beyond IT DR?

LEVEL INDICATORS:
- M1: Basic DR only; limited vendor oversight; untested plans
- M2: Annual DR testing; vendor inventory; some due diligence
- M3: Comprehensive BCP/DR; tested RTOs; formal TPRM; critical vendor oversight
- M4: Operational resilience framework; scenario testing; real-time vendor monitoring
- M5: Industry-leading resilience; minimal incidents; ecosystem risk management

---

## P4: Data, Analytics & Technology

### P4C1: Data Management & Governance

DIAGNOSTIC QUESTIONS:
1. Is there a data governance framework and policy?
2. Is there executive ownership of data (CDO or equivalent)?
3. Is there a data catalog or inventory?
4. Are data quality metrics defined and tracked?
5. Is there master data management?

LEVEL INDICATORS:
- M1: No data governance; data siloed by system
- M2: Basic policies; some metadata documentation
- M3: Formal governance; data stewards; quality metrics; CDO exists
- M4: Enterprise data management; data catalog; quality automation; single customer view
- M5: Data as strategic asset; industry-recognized; data monetization

CROSS-PILLAR IMPACT: P4C1 < 2.5 → Cap P2C4 (Personalization) at 3.0

### P4C2: Analytics & AI Enablement

DIAGNOSTIC QUESTIONS:
1. Is there centralized analytics capability?
2. Are predictive/ML models in production?
3. Is there self-service analytics for business users?
4. Are there AI use cases beyond basic analytics?
5. Is there model risk management for AI/ML?

LEVEL INDICATORS:
- M1: Basic reporting only; no predictive capability
- M2: Standard BI platform; some descriptive analytics
- M3: Analytics team; predictive models in development/pilot; self-service dashboards
- M4: Production ML models; AI use cases (chatbot, fraud, NBA); analytics CoE
- M5: Industry-leading AI; AI in core processes; proprietary models

### P4C3: Technology Architecture & Integration

DIAGNOSTIC QUESTIONS:
1. Is there API-first architecture strategy?
2. What percentage of integrations are via APIs vs. batch?
3. Is there integration platform/middleware?
4. Is there cloud adoption strategy and execution?
5. Is the core system modern or legacy?

LEVEL INDICATORS:
- M1: Legacy systems; batch integrations; significant technical debt
- M2: Some API capability; modernization underway; hybrid state
- M3: API platform; majority real-time integration; cloud hybrid; modern middleware
- M4: API-first; microservices; cloud-native; developer portal
- M5: Industry-leading architecture; open banking ready; platform model

CROSS-PILLAR IMPACT: P4C3 < 2.5 → Cap P3C1 (Automation) at 3.0

### P4C4: Information Security & Cybersecurity

DIAGNOSTIC QUESTIONS:
1. Is there a cybersecurity framework (NIST, ISO 27001)?
2. Is there 24/7 security operations capability?
3. Is there penetration testing and vulnerability management?
4. Is there security awareness training?
5. What is breach/incident history?

SECURITY DATA REQUIRED:
- Disclosed breaches (state AG offices, HHS if health data)
- SOC2 / ISO 27001 certification status
- Vendor security assessments

LEVEL INDICATORS:
- M1: Minimal security program; no framework
- M2: Basic controls; annual pen testing; some training
- M3: Formal framework; SOC2/ISO certified; vuln management; SecOps
- M4: Advanced threat detection; zero-trust progress; security automation
- M5: Industry-leading; no significant incidents; security as enabler

CROSS-PILLAR IMPACT: P4C4 < 2.5 → Cap P4C1 (Data Governance) at 3.0
SEVERITY CAPS: Breach <12mo → 2.0 | Breach <24mo → 3.0