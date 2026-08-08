# Source Catalogue & Search Query Templates

Read this file at the START of Batch 1, before executing any searches. Use these queries
as starting points — adapt with entity name and subvertical context.

---

## Knowledge Base Source ID Format

- `[KB-US-XXX]` = US public source from catalogue (US-001 through US-130+)
- `[KB-CA-XXX]` = Canadian public source
- `[KB-INT-XXX]` = Internal document type (INT-001 through INT-200) — used for discovery questions only
- `[E-XXX]` = Evidence item collected in THIS assessment

Always cite KB Source IDs alongside Evidence IDs where a source can be traced to the catalogue.

---

## Capability Search Query Templates

Replace `[Entity]` with institution name in all queries.

### P1: Strategy, Governance & Culture

**P1C1 Digital Strategy**
- `[Entity] digital transformation strategy roadmap`
- `[Entity] annual report technology investment`
- `[Entity] CDO CTO digital officer`
- `[Entity] digital strategy announcement 2024 OR 2025`

**P1C2 Governance & Risk Appetite**
- `[Entity] board risk committee governance`
- `[Entity] technology committee proxy statement`
- `[Entity] risk management framework`
- `[Entity] [regulator] examination results`

**P1C3 Innovation Management**
- `[Entity] fintech partnership innovation lab`
- `[Entity] accelerator incubator startup`
- `[Entity] patent technology innovation`

**P1C4 Culture & Change**
- `[Entity] digital training employee technology culture`
- `[Entity] Glassdoor technology reviews`
- `[Entity] change management transformation`

**P1C5 ESG Integration**
- `[Entity] ESG sustainability climate TCFD`
- `[Entity] DEI diversity annual report`
- `[Entity] community development green bond`

### P2: Member/Customer Experience

**P2C1 Digital Marketing**
- `[Entity] digital marketing mobile app marketing cloud`
- `[Entity] social media digital presence`
- `[Entity] marketing technology pardot hubspot`

**P2C2 Onboarding**
- `[Entity] account opening digital onboarding`
- `[Entity] online application new account`
- `[Entity] digital account opening time`

**P2C3 Omnichannel Servicing**
- `[Entity] mobile banking contact center chat`
- `[Entity] service cloud member service`
- `[Entity] branch transformation digital`
- `[Entity] app store rating reviews`

**P2C4 Personalization**
- `[Entity] personalization AI recommendations`
- `[Entity] next best action predictive`
- `[Entity] customer analytics segmentation`

### P3: Operations, Risk & Compliance

**P3C1 Core Automation**
- `[Entity] straight-through processing RPA automation`
- `[Entity] process automation efficiency`
- `[Entity] robotic process automation UiPath`

**P3C2 Fraud & Op Risk**
- `[Entity] fraud detection AML monitoring`
- `[Entity] fraud prevention technology`
- `[Entity] anti-money laundering compliance`

**P3C3 Compliance**
- `[Entity] CFPB NCUA OCC enforcement consent order`
- `[Entity] regulatory compliance findings`
- `[Entity] fair lending CRA compliance`

**P3C4 Resilience & TPRM**
- `[Entity] business continuity disaster recovery`
- `[Entity] vendor management third party risk`
- `[Entity] operational resilience outage`

### P4: Data, Analytics & Technology

**P4C1 Data Governance**
- `[Entity] data governance CDO data management`
- `[Entity] data quality data lake data cloud`
- `[Entity] master data management`

**P4C2 Analytics & AI**
- `[Entity] AI machine learning predictive analytics`
- `[Entity] Einstein analytics Salesforce`
- `[Entity] generative AI chatbot virtual assistant 2024 OR 2025`

**P4C3 Tech Architecture**
- `[Entity] core banking technology platform API`
- `[Entity] cloud migration modernization`
- `[Entity] MuleSoft integration API platform`
- `[Entity] core system Fiserv OR FIS OR Jack Henry`

**P4C4 Cybersecurity**
- `[Entity] cybersecurity breach data security`
- `[Entity] SOC 2 ISO 27001 security certification`
- `[Entity] data breach notification`

---

## Issue & Enforcement Search Sources

For each entity, search ALL relevant regulator enforcement pages:

| Regulator | URL | Subverticals |
|-----------|-----|-------------|
| NCUA Enforcement | ncua.gov enforcement-actions | Credit Unions |
| OCC Enforcement | occ.gov enforcement-actions | Banks |
| FDIC Enforcement | fdic.gov bank-failures | Banks |
| CFPB Enforcement | consumerfinance.gov enforcement/actions | All |
| SEC Enforcement | sec.gov enforce/enforceactions | Securities, Asset Mgmt |
| FINRA Disciplinary | finra.org | Broker-Dealers |
| State DOI | [varies by state] | Insurance |

**Negative search discipline**: If no issues found, list ALL sources searched, disclose
limitations, convert to risk questions. Absence of enforcement IS informative (supports
P3C3 compliance posture).

---

## Sentiment Search Sources

### Customer Sentiment
| Source | Search Query | Data Points |
|--------|-------------|-------------|
| iOS App Store | `[Entity] app store` | Rating, review count, recent themes |
| Google Play | `[Entity] google play` | Rating, review count, recent themes |
| CFPB Complaints | consumerfinance.gov complaint database | Volume, trends, categories |
| BBB | bbb.org search | Rating, complaint count |
| Trustpilot | trustpilot.com search | Rating, review themes |

### Employee Sentiment
| Source | Search Query | Data Points |
|--------|-------------|-------------|
| Glassdoor | `[Entity] Glassdoor reviews` | Rating, culture themes, tech mentions |
| Indeed | `[Entity] Indeed reviews` | Rating, work-life themes |
| LinkedIn | `[Entity] site:linkedin.com` | Employee count, growth, role distribution |

### Capability Signals from Sentiment
- **Employee tech mentions** → P1C4, P4
- **Employee process mentions** (manual work, outdated systems) → P3C1, P4C3
- **Customer digital mentions** (app, online, digital experience) → P2
