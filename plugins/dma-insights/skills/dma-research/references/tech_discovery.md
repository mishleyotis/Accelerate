# Technology Stack Discovery & Utilization Framework

Read this file during Batch 1 Step 6 (tech stack discovery) and Batch 2 Step 3
(tech evidence consolidation).

---

## Scope

Discover ALL technology platforms across ALL categories. Zennify-priority platforms get
DEEPER investigation, but capture the COMPLETE landscape. Not finding Zennify-priority
tech is also an important signal (greenfield opportunity).

---

## Technology Evidence Levels (1-4)

| Level | Criteria | Language in Output | Confidence |
|-------|----------|-------------------|------------|
| 1 | Vendor explicitly named in T1/T2 with deployment confirmation | "implemented, deployed, uses, powers" | High |
| 2 | Official partnership announcement or case study | "partnered with, selected, announced engagement" | Medium-High |
| 3 | 2+ independent signals (job postings + conference mentions) | "likely uses, signals suggest, inferred from hiring" | Medium |
| 4 | Single weak source (one job posting, website mention) | "may use, potential, unconfirmed" | Low |

---

## Technology Utilization Levels

| Level | Criteria | Confidence Statement |
|-------|----------|---------------------|
| High | Case study with outcomes, recent feature announcements, advanced role hiring (Architect) | "Tool actively used at scale" |
| Medium | Basic admin hiring, some public mentions, no recent case studies | "Tool in use but utilization level unclear" |
| Low | Long relationship + basic hiring only, manual process mentions alongside tool | "Potential underutilization — flag for discovery" |
| Unknown | Presence confirmed but no utilization signals | "Cannot assess — flag for discovery" |

---

## Utilization Red Flags (URF-01 through URF-06)

These patterns indicate the gap between tool PRESENCE and tool UTILIZATION. Each adds
uncertainty to ceiling estimates.

### URF-01: Capability Plateau
- **Pattern**: Long vendor relationship (>5 years) + basic role hiring (Admin not Architect)
- **Implication**: Not advancing beyond basic use
- **Action**: Cap related P4 ceiling at L3.0, flag P1C4 for capability gap
- **Uncertainty modifier**: +0.2
- **Discovery Q**: "What is your team's expertise level with [Tool]? How many certified professionals?"
- **Internal doc**: INT-045 Technology Skills Inventory

### URF-02: Adoption Gap
- **Pattern**: Enterprise tool present + manual process mentions for same function
- **Implication**: Tool exists but not embedded in workflows
- **Action**: Flag utilization concern, add ±0.5 uncertainty to related capabilities
- **Uncertainty modifier**: +0.2
- **Discovery Q**: "What percentage of [process] goes through [Tool] vs. manual/spreadsheet?"
- **Internal doc**: INT-067 Process Automation Metrics

### URF-03: Stagnation Signal
- **Pattern**: No recent vendor case studies/announcements despite active relationship
- **Implication**: Not achieving showcase-worthy outcomes
- **Action**: Apply Legacy Platform Risk modifier, flag for validation
- **Uncertainty modifier**: +0.1
- **Discovery Q**: "When did you last upgrade or expand your [Tool] implementation?"

### URF-04: Entitlement Underutilization
- **Pattern**: Hiring for capabilities included in existing tool licenses
- **Implication**: May not know what they own
- **Action**: Flag potential entitlement underutilization
- **Uncertainty modifier**: +0.2
- **Discovery Q**: "Do you have a current inventory of your [Vendor] entitlements and feature usage?"
- **Internal doc**: INT-052 Software License Inventory

### URF-05: Shadow Systems
- **Pattern**: Multiple tools mentioned for same function (e.g., CRM + spreadsheets for pipeline)
- **Implication**: Primary tool not meeting needs or not adopted
- **Action**: Flag adoption/change management gap, impacts P1C4
- **Uncertainty modifier**: +0.2
- **Discovery Q**: "What is the single source of truth for [function]? Why are multiple tools in use?"

### URF-06: Peripheral Tool
- **Pattern**: Tool mentioned in job posting as "nice to have" not "required"
- **Implication**: Tool is peripheral, not core to operations
- **Action**: Downgrade tech evidence level, flag as non-critical system
- **Uncertainty modifier**: +0.1
- **Discovery Q**: "How central is [Tool] to your daily operations?"

---

## Vendor Tenure Analysis

| Tenure | With Recent Signals | Without Recent Signals |
|--------|--------------------|-----------------------|
| <2 years | Early adoption — expect implementation gaps (modifier: 0) | N/A (too new for absence to matter) |
| 2-5 years | Maturation phase — look for optimization signals (modifier: 0) | Slow adoption — flag (modifier: -0.1) |
| 5-10 years | Healthy evolution (modifier: 0) | **POTENTIAL STAGNATION** — mandatory utilization validation (modifier: -0.2) |
| 10+ years | Long-term strategic platform (modifier: 0) | **HIGH PROBABILITY of technical debt** — internal discovery required (modifier: -0.3) |

**Tenure detection queries:**
- "[Entity] [Vendor] since OR relationship history"
- "[Entity] [Vendor] case study site:[vendor].com"
- "[Entity] [Vendor] Dreamforce OR conference speaker"
- "[Entity] [Vendor] upgrade OR migration OR modernization"

---

## Zennify-Priority Platforms (DEEP Investigation)

### Priority 1: CRM & Member/Customer Engagement
**Deep targets**: Salesforce FSC, Service Cloud, Sales Cloud, Experience Cloud, Marketing
Cloud, Account Engagement (Pardot), nCino, Enclustr
**Also check**: Microsoft Dynamics, HubSpot, Zoho, SugarCRM, Pegasystems
**Capability mapping**: P2C1, P2C2, P2C3, P2C4, P4C3

### Priority 2: Data & Integration
**Deep targets**: MuleSoft Anypoint, Salesforce Data Cloud
**Also check**: Snowflake, Databricks, AWS Redshift, BigQuery, Informatica, Talend, dbt,
Fivetran, Dell Boomi, Jitterbit, Azure Data Factory, AWS Glue
**Capability mapping**: P4C1, P4C3, P3C1

### Priority 3: AI, Analytics & Automation
**Deep targets**: Salesforce Einstein, Agentforce, Einstein Copilot, Flow/OmniStudio
**Also check**: AWS SageMaker, Azure AI, Google Vertex AI, OpenAI Enterprise, Tableau,
Power BI, Qlik, Looker, UiPath, Automation Anywhere, Blue Prism, Appian, Microsoft Copilot
**Capability mapping**: P4C2, P3C1, P2C4
**Recency note**: AI landscape evolves rapidly. Evidence >18 months is STALE.

---

## Comprehensive Technology Categories (ALL must be searched)

### Core Banking/Insurance/Processing
- Banking: FIS (Horizon, Modern Banking), Fiserv (DNA, XP2, Portico, Premier, Signature),
  Jack Henry (Symitar, SilverLake, CIF 20/20), Temenos, Thought Machine, Mambu, Finxact
- Insurance: Guidewire, Duck Creek, Majesco, EIS Group, Sapiens, Britecore
- Lending: nCino, Encompass (ICE), Finastra Fusion, Abrigo, FICS, MeridianLink
- Payments: FIS/Worldpay, Fiserv/First Data, Jack Henry iPay, Zelle, FedNow, SWIFT
→ Maps to: P4C3, P3C1, P2C2, P2C3

### Digital Channels
Alkami, Q2, NCR Digital Banking (Catalyst), Backbase, Technisys, Narmi, Banno (Jack Henry),
MeridianLink, CUNA Mutual/TruStage digital tools
→ Maps to: P2C2, P2C3, P2C4
**Check app store for last update date. Stale apps (>6 months) = flag.**

### Cybersecurity & Identity
CrowdStrike, Palo Alto Networks, Splunk, Fortinet, Qualys, Tenable, KnowBe4, Proofpoint,
Veracode, Rapid7, SentinelOne, Okta, Ping Identity, CyberArk
→ Maps to: P4C4

### Fraud, AML & Compliance
NICE Actimize, Featurespace, Feedzai, Alloy, Socure, Verafin, SAS AML, Oracle Financial
Crime, LexisNexis Risk, Onfido, Jumio
→ Maps to: P3C2, P3C3

### Cloud & Infrastructure
AWS, Microsoft Azure, Google Cloud, Oracle Cloud, IBM Cloud
→ Maps to: P4C3

### Collaboration & Productivity
Microsoft 365, Google Workspace, Slack, Zoom, ServiceNow, Atlassian (Jira/Confluence)
→ Maps to: P1C4, P4C3

### Marketing Technology
Salesforce Marketing Cloud, HubSpot Marketing, Adobe Experience Cloud, Marketo, Mailchimp,
Google Analytics
→ Maps to: P2C1, P2C4

### Document & Content Management
Hyland OnBase, Laserfiche, Box, SharePoint, DocuSign, Adobe Sign
→ Maps to: P3C1, P3C3

---

## Mandatory Tech Search Sources

For EVERY entity, search these sources in this order:

1. **Salesforce AppExchange**: `[Entity] site:appexchange.salesforce.com`
2. **Vendor case studies**: `[Entity] case study site:salesforce.com`, `site:mulesoft.com`,
   `site:microsoft.com`, `site:aws.amazon.com`
3. **Conference presence**: `[Entity] Dreamforce speaker`, `[Entity] webinar [Vendor]`
4. **Tech detection**: BuiltWith, Wappalyzer mentions
5. **Review platforms**: `[Entity] reviewer site:g2.com`, `site:trustradius.com`
6. **Job postings**: `[Entity] jobs technology site:linkedin.com`, `site:indeed.com`

---

## Recency Verification Protocol

For EVERY technology platform identified:

| Priority | Source | Threshold |
|----------|--------|-----------|
| BEST | Vendor case study or press release with date | Within 24 months |
| GOOD | Job posting mentioning the tool | Within 12 months |
| ACCEPTABLE | Conference/webinar mention | Within 18 months |
| WEAK | Website mention only, no date | Flag as UNVERIFIED |
| STALE | Only evidence >36 months old | Flag as LEGACY/Unconfirmed |

**Output format per platform:**
```
[Platform] — Evidence Level [1-4], Utilization [High/Med/Low/Unknown],
Recency [CURRENT/RECENT/LEGACY/UNVERIFIED], Last confirmed: [date or Unknown],
Zennify Priority: [Yes/No], Red Flags: [list or None]
```

---

## Utilization Validation Checklist (for each tool found)

1. Search for case study/announcement (establish recency)
2. Check vendor tenure if discoverable
3. Analyze job postings for role seniority (Admin vs Architect)
4. Check for utilization red flags (URF-01 through URF-06)
5. Assign utilization level (High/Medium/Low/Unknown)
6. Assign recency tag (CURRENT/RECENT/LEGACY/UNVERIFIED)
7. Generate discovery questions referencing internal document IDs
