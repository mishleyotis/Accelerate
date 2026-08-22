# Solution Offerings Registry — 14 Productized Offerings

## Universal Offerings (all 9 sub-verticals)

### Data Modernization
**Description:** Unify disparate data sources into a governed foundation that powers reporting, analytics, AI, and real-time decisioning.
**Key capabilities:** Unified data across core systems | Data governance, quality monitoring, and lineage | Cloud data platform architecture | Master data management and entity resolution | Real-time data pipelines and event streaming

### Financial Services Customer Platform
**Description:** Give frontline teams a single view of every client, account, and relationship opportunity across products and channels.
**Key capabilities:** Unified client and household views | Relationship intelligence and next-best-action | Pipeline management and deal tracking | Integrated servicing and case management | Cross-product visibility and wallet share analytics

### Personalized Customer Engagement
**Description:** Turn client and transaction data into targeted engagement, retention, and growth programs.
**Key capabilities:** Segmentation by behavior, value, and lifecycle stage | Event-driven triggers from transactions and milestones | Personalized journeys across email, mobile, and digital | Cross-sell and upsell recommendation engine | Campaign performance analytics and attribution

### Salesforce Platform Optimization & Governance
**Description:** Improve platform performance, simplify operations, and reduce technical debt.
**Key capabilities:** Platform health assessment covering metadata, automation, and integrations | Process re-engineering aligned to business workflows | Technical debt remediation and architecture modernization | Governance framework for change management | Performance monitoring and optimization

### Agentic Workforce
**Description:** Deploy AI agents that automate knowledge work, accelerate decisions, and reduce manual processing.
**Key capabilities:** AI-assisted workflows for document generation and review | Autonomous agents for data collection, verification, and compliance checks | Intelligent routing and escalation | Natural language interfaces for internal systems | Agent performance monitoring and guardrails

## Common Offerings (4-8 sub-verticals)

### Contact Center Modernization
**Applicable:** CIB, Commercial, Credit Unions, Insurance Brokerages, Insurance Carriers, Retail, Wealth AM, Wealth RIAs (8/9)
**Description:** Unify inquiries across voice, chat, and digital channels with full account context and AI-powered routing.
**Key capabilities:** Omnichannel routing across voice, chat, email, and secure messaging | Unified agent desktop with client context | AI-powered case classification and routing | Self-service portals with escalation | Real-time supervisor dashboards and quality monitoring

### Digital Lending Platform
**Applicable:** Commercial, Credit Unions, Farm Credit, Retail (4/9)
**Description:** Modernize lending from application through underwriting, closing, and servicing.
**Key capabilities:** Digital loan origination across consumer and commercial | Automated underwriting and credit decisioning | Document collection and verification automation | Portfolio monitoring and early warning systems | Regulatory compliance automation

### Digital Account Opening & Onboarding
**Applicable:** CIB, Credit Unions, Retail (3/9)
**Description:** Replace manual onboarding with digital-first identity verification and account opening.
**Key capabilities:** Automated identity verification and KYC | Digital document collection and e-signature | Real-time account provisioning | Compliance screening integration | Onboarding analytics and abandonment tracking

## Sub-Vertical-Specific Onboarding Variants

### Digital Borrower Onboarding & KYC
**Applicable:** Commercial Lending
**Description:** Streamline borrower onboarding with automated entity verification and KYC for commercial clients.

### Digital Borrower Onboarding & Application
**Applicable:** Farm Credit
**Description:** Digitize farm operation onboarding with automated credit applications and agricultural data integration.

### Digital Client Onboarding & Submission Management
**Applicable:** Insurance Brokerages
**Description:** Automate client intake and submission workflows across carriers with digital quoting and binding.

### Digital Policyholder Onboarding & Quoting
**Applicable:** Insurance Carriers
**Description:** Modernize policyholder onboarding with digital quoting, binding, and policy issuance.

### Digital Investor Onboarding & Subscription
**Applicable:** Wealth Asset Management
**Description:** Streamline investor onboarding with digital subscription documents, accreditation verification, and capital call management.

### Digital Client Onboarding & Account Transfer
**Applicable:** Wealth Asset Management, Wealth RIAs
**Description:** Automate client onboarding and account transfers across custodians with digital authorization and ACAT processing.

## Capability-to-Offering Mapping

Used by `solution_inferrer.py` to map DMA capability gaps to offerings:

| Weak Capability | Primary Offering | Secondary |
|---|---|---|
| Data Governance | Data Modernization | — |
| Analytics & AI Enablement | Agentic Workforce | Data Modernization |
| Architecture & Integration | Data Modernization | SF Platform Optimization |
| Platform Enablement | SF Platform Optimization | Data Modernization |
| Digital Strategy & Vision | (strategic — not offering-mapped) | — |
| Governance & Risk Appetite | SF Platform Optimization | — |
| Innovation Management | Agentic Workforce | — |
| Culture & Change Enablement | (organizational — not offering-mapped) | — |
| Sustainable Finance & ESG | (regulatory — not offering-mapped) | — |
| Digital Marketing & Acquisition | Personalized Customer Engagement | — |
| Onboarding & Fulfillment | Digital Onboarding (SV variant) | FS Customer Platform |
| Omnichannel Servicing | Contact Center Modernization | FS Customer Platform |
| Personalization & Engagement | Personalized Customer Engagement | FS Customer Platform |
| Process Automation | SF Platform Optimization | Agentic Workforce |
| Operational Risk & Fraud | (risk — covered by platform) | SF Platform Optimization |
| Compliance & Surveillance | SF Platform Optimization | — |
| Business Resilience & TPRM | (risk — not offering-mapped) | — |
