# Deep Search Protocol — Subcapability-Level Evidence Collection

Read this file at the start of Batches 2 and 3, before executing any subcapability searches.
This protocol defines the 3-5 query approach for each subcapability, with escalation to
proxy searches (Tiers 7-10) when direct evidence is thin.

---

## Core Principle: Diagnostic Question Drives Everything

The diagnostic question (Column H in Pillar XLSX) is the research compass. EVERY search
query traces back to what the diagnostic question is actually asking. Generic searches
that ignore the diagnostic question produce generic evidence.

**Before generating queries, decompose the diagnostic question:**
```
Subject:    What capability is being assessed?
Verb:       What state is expected? (exists, documented, measured, automated, optimized...)
Qualifier:  What maturity level is implied?
Evidence:   What kind of source would contain the answer?
Negative:   What absence would signal low maturity?
```

---

## The 10-Query Tier System

For EACH subcapability, generate and execute queries across 10 structured tiers. Not all
tiers will yield results — that's expected. The goal is to exhaust all reasonable avenues
before marking a subcap as evidence-thin. Tiers 1-6 are MANDATORY. Tiers 7-10 are executed
when Tiers 1-6 yield <3 evidence items.

### Tier 1: Direct Capability Search (MANDATORY)
Decompose the diagnostic question into a direct search.

```
Diagnostic Q: "Is there a defined cadence for refreshing the digital strategy?"
→ T1-Q1: "[Entity] digital strategy planning cycle"
→ T1-Q2: "[Entity] strategic plan refresh annual review"
```

**Rules**: Extract the core capability noun + verb from the diagnostic question.
Combine with entity name. Keep 4-6 words. No filler words.

### Tier 2: Official Document Search (MANDATORY)
Target specific high-tier document types that would contain the answer.

```
→ T2-Q1: "[Entity] annual report 2024 2025 strategy"
→ T2-Q2: "[Entity] investor presentation strategic plan"
```

**Document targets by domain**:
| Subcap Domain | Primary Document Targets |
|--------------|------------------------|
| Strategy/Governance | Annual report, proxy statement, investor deck, board committee charters |
| Customer Experience | App store listing, CFPB complaints database, J.D. Power study |
| Technology | Vendor case study, technology partnership announcement, conference presentation |
| Data/Analytics | Privacy policy, data governance announcement, CDO appointment |
| Risk/Compliance | Regulatory enforcement page, SOC2 attestation, breach disclosure |
| Operations | Process automation announcement, efficiency metrics disclosure |
| Talent/Culture | Glassdoor company page, LinkedIn company page, training program announcement |
| ESG | Sustainability report, TCFD disclosure, DEI report, CRA exam |

### Tier 3: Keyword Variant Search (MANDATORY)
Use synonyms, related terms, and alternative framings from the subcap name.

```
Subcap: "Strategy Refresh Cadence"
→ T3-Q1: "[Entity] technology roadmap update timeline"
→ T3-Q2: "[Entity] digital transformation milestones 2024"
```

**Synonym libraries by concept**:
- Strategy: roadmap, plan, vision, blueprint, framework, agenda
- Automation: RPA, straight-through, automated, digital workflow, self-service
- Governance: oversight, committee, charter, accountability, risk appetite
- Innovation: fintech, startup, accelerator, pilot, emerging technology
- Customer experience: member experience, digital banking, mobile app, omnichannel
- Data governance: data management, CDO, data quality, master data, data lake
- Compliance: regulatory, examination, audit, enforcement, consent order, MRA
- Cybersecurity: information security, data protection, breach, SOC2, ISO 27001

### Tier 4: Regulatory/Enforcement Search (MANDATORY)
Search the entity's primary regulator for any relevant filings or actions.

```
→ T4-Q1: "[Entity] NCUA examination enforcement"
→ T4-Q2: "[Entity] CFPB complaint enforcement action"
```

**Regulator-specific searches** (execute ALL relevant to entity's subvertical):
| Regulator | Search Query Template | What It Reveals |
|-----------|----------------------|-----------------|
| NCUA | "[Entity] NCUA enforcement examination" | P3C3, P1C2 |
| OCC | "[Entity] OCC enforcement consent order" | P3C3, P1C2 |
| FDIC | "[Entity] FDIC enforcement cease desist" | P3C3 |
| CFPB | "[Entity] CFPB complaint enforcement" | P2C3, P3C3 |
| SEC | "[Entity] SEC enforcement filing" | P1C2, P3C3 |
| FINRA | "[Entity] FINRA disciplinary action" | P3C3 |
| State DOI | "[Entity] [state] insurance department enforcement" | P3C3 |

### Tier 5: Technology/Platform Search (MANDATORY)
Search for technology platforms related to this subcapability.

```
Diagnostic Q about automation → search for RPA/automation platforms
Diagnostic Q about customer experience → search for CRM/digital platforms
Diagnostic Q about data → search for data platforms/CDO
```

→ T5-Q1: "[Entity] [relevant platform] implementation"
→ T5-Q2: "[Entity] [relevant vendor] case study"

**Platform-to-subcap mapping**: See `references/tech_discovery.md` for comprehensive
platform lists per capability domain.

### Tier 6: Sentiment/Review Search (MANDATORY)
Search customer and employee sentiment sources for capability signals.

```
→ T6-Q1: "[Entity] app store reviews [capability keyword]"
→ T6-Q2: "[Entity] Glassdoor reviews [capability keyword]"
```

**Sentiment sources that reveal capability maturity**:
| Source | What It Reveals | Capability Mapping |
|--------|----------------|-------------------|
| App Store ratings | Digital channel quality | P2C2, P2C3, P2C4 |
| CFPB complaints | Service/compliance gaps | P2C3, P3C2, P3C3 |
| Glassdoor reviews | Culture/tech/process | P1C4, P4C3 |
| Indeed reviews | Operations/tools | P3C1, P4C3 |
| BBB complaints | Service quality | P2C3, P3C2 |
| LinkedIn employee data | Talent/expertise | P1C4, P4C1, P4C2 |

---

### Tier 7: Proxy Signal Search (IF <3 evidence items from Tiers 1-6)
When direct evidence is scarce, search for proxy indicators.

```
Board oversight → "[Entity] board member technology background"
Process maturity → "[Entity] hiring process improvement six sigma"
Data quality → "[Entity] HMDA data submission quality"
Innovation → "[Entity] hackathon fintech accelerator patent"
```

**Comprehensive proxy library**:

| Capability Domain | Proxy Signal | Search Query | What Presence Means | What Absence Means |
|------------------|-------------|-------------|--------------------|--------------------|
| Board digital oversight | Board bio with tech background | "[Entity] board director technology CTO" | Governance maturity signal | May lack tech perspective at board level |
| Digital strategy | Strategic hire announcement | "[Entity] hires CDO CTO CIO digital officer" | Investment in digital leadership | May lack dedicated digital leadership |
| Innovation culture | Patent filings | "[Entity] patent fintech innovation" | Active innovation output | Not necessarily negative (many CUs don't patent) |
| Process maturity | Lean/Six Sigma references | "[Entity] lean six sigma process improvement" | Operational maturity | May be early in process optimization |
| Data governance | HMDA/CRA data quality | "[Entity] HMDA CRA data quality audit" | Data management maturity | Could indicate data quality gaps |
| Compliance posture | Compliance hire seniority | "[Entity] chief compliance officer hire" | Investment in compliance | May be reactive (post-enforcement) |
| Employee digital skills | Certification partnerships | "[Entity] Salesforce training certification program" | Skills investment | May lack structured training |
| Vendor management | Vendor diversity reports | "[Entity] vendor diversity supplier management" | TPRM maturity | Not necessarily negative |
| Cybersecurity | Security certification | "[Entity] SOC2 ISO 27001 penetration test" | Security maturity | May be immature or not public |
| Change management | Change management hire | "[Entity] change management organizational transformation" | CM maturity signal | May lack structured CM |

### Tier 8: Peer Association Search (IF <3 evidence items from Tiers 1-7)
Search for the entity in the context of its peers doing the same activity.

```
→ T8-Q1: "[Entity] AND [peer entity] [capability keyword]"
→ T8-Q2: "[Entity] [league table or industry award] [capability area]"
→ T8-Q3: "[Entity] [industry conference] [capability keyword] speaker panelist"
```

**Peer contexts that reveal capability**:
- Industry awards/recognition (e.g., CUNA Diamond Award, BAI Innovation Award)
- Conference speaking/panel participation
- Peer benchmarking reports (e.g., Callahan's, SNL Financial)
- Shared vendor/partner announcements
- Joint initiatives or consortiums

### Tier 9: Vendor/Partner Reverse Search (IF <3 evidence items from Tiers 1-8)
Search from the vendor's perspective for mentions of the entity.

```
→ T9-Q1: "site:salesforce.com [Entity]"
→ T9-Q2: "site:mulesoft.com [Entity] case study"
→ T9-Q3: "[Vendor] customer [Entity] implementation"
```

**High-value vendor sites to search**:
- salesforce.com, mulesoft.com, tableau.com (CRM/data)
- aws.amazon.com, azure.microsoft.com (cloud)
- servicenow.com, atlassian.com (ITSM/collaboration)
- crowdstrike.com, paloaltonetworks.com (security)
- ncino.com (lending), alkami.com (digital banking)
- fiserv.com, fisglobal.com, jackhenry.com (core)

### Tier 10: Contradictory/Negative Search (MANDATORY — at least 1 per CAPABILITY)
Search explicitly for evidence AGAINST the entity's capability.

```
→ T10-Q1: "[Entity] [capability area] failure complaint problem"
→ T10-Q2: "[Entity] [capability area] outdated legacy criticism"
→ T10-Q3: "[Entity] security breach data loss incident"
→ T10-Q4: "[Entity] customer complaint service poor"
```

**Negative search templates by domain**:
| Domain | Negative Queries |
|--------|-----------------|
| Strategy | "[Entity] strategy failure outdated technology behind" |
| Customer | "[Entity] poor service complaint mobile app problems" |
| Technology | "[Entity] system outage legacy technology technical debt" |
| Data | "[Entity] data breach privacy violation data quality" |
| Compliance | "[Entity] enforcement action violation fine penalty" |
| Operations | "[Entity] manual process inefficient slow processing" |
| Culture | "[Entity] Glassdoor poor culture turnover toxic" |
| Security | "[Entity] cybersecurity breach hack incident" |

---

## Query Construction Rules (Updated)

1. **Every query MUST include the institution name** (or official abbreviation)
2. **Queries should be 4-8 words** — shorter is better for precision
3. **3-5 queries per subcap minimum** (Tiers 1-5 for direct, escalate to Tiers 7-10 if thin)
4. **No duplicate framings** — each query must try a genuinely different angle
5. **Do NOT repeat the diagnostic question verbatim** — decompose it
6. **Include year markers** for recency: add "2024 2025" to at least 2 queries per subcap
7. **Use `web_fetch`** on EVERY rich document found (annual reports, filings, vendor case studies)
8. **At least 1 contradictory search per capability group** (Tier 10)
9. **Track ALL queries in the search log** (for A2 appendix and reproducibility)
10. **If Tiers 1-6 yield 0 results**: Execute Tiers 7-10 immediately. If still 0 after all
    10 tiers, document as NO_EVIDENCE with full search log.

---

## Smart Query Batching

### Rich Document Mining FIRST (per capability)

When starting a new capability, fetch shared rich documents ONCE:
- Annual report, 10-K, proxy statement (if not already fetched)
- Extract ALL facts and map each to the specific subcap(s) it applies to

```
ANNUAL REPORT MINING PROTOCOL:
1. Fetch the full document
2. Extract ALL facts with dates, metrics, names, initiatives
3. For EACH fact, determine which subcapabilities it maps to (may be 5-20)
4. Assign evidence IDs at fact level (E-xxx:Fy)
5. Map every fact to its subcap targets
6. Record in evidence index
→ One fetch can populate evidence for 20-50 subcapabilities
```

### THEN: Individual Subcap Searches (MANDATORY — the primary mechanism)

After mining shared documents, EACH subcap still gets its own 3-5 targeted searches
driven by its specific diagnostic question. The shared document mining is a HEAD START,
not a replacement. Many subcaps will have specific capabilities (e.g., "strategy refresh
cadence", "budget alignment", "board engagement") that shared documents do NOT cover.

**ANTI-PATTERN — THIS IS THE #1 FAILURE MODE:**
```
BAD:  Search "Entity digital strategy" → map results to P1C1.1.1, P1C1.1.2, P1C1.1.3,
      P1C1.1.4, P1C1.1.5 → all 5 subcaps have identical evidence → DONE
      (This is category-level searching disguised as subcap-level)

GOOD: Mine annual report → extract 3 facts that map to P1C1.1.1 and P1C1.1.2
      THEN search "Entity strategy refresh cadence annual cycle" for P1C1.1.3
      THEN search "Entity digital vision communication leadership" for P1C1.1.4
      THEN search "Entity board digital oversight technology committee" for P1C1.1.5
      → Each subcap has DIFFERENT evidence because each has a DIFFERENT question
```

---

## Escalation Protocol (When Evidence Is Thin)

After executing Tiers 1-6 for a subcapability with <3 evidence items:

### Level 1 Escalation: Broaden Terms (Tiers 7-8)
- Remove specificity from queries (use parent capability keywords)
- Search for proxy signals
- Search for peer associations
- Add 3-4 additional queries

### Level 2 Escalation: Vendor Reverse Search (Tier 9)
- Search vendor websites for entity mentions
- Search technology review platforms (G2, TrustRadius)
- Search conference presentation archives
- Add 2-3 additional queries

### Level 3 Escalation: Infer from Adjacent Evidence
- Check if adjacent subcapabilities in the same capability have evidence
  that implies something about this subcap
- Example: If P4C3.2.1 "API strategy" has no direct evidence but P4C3.1.1
  "Core platform" shows they use MuleSoft, infer API capability exists
- Label as INFERENCE with explicit reasoning

### Level 4: Document as NO_EVIDENCE
- If ALL escalation levels fail, document thoroughly:
  ```
  SubCap [ID]: NO_EVIDENCE
  Total searches: [N] across [M] tiers
  Highest tier result: [None / T5 vague mention]
  Reason: [Why evidence is unavailable]
  Proxy check: [What proxies were tried, why they failed]
  Adjacent evidence: [What nearby subcaps suggest]
  Internal discovery Q: [Question that would resolve this]
  ```
- Column G: NO_EVIDENCE
- Column K: NO_EVIDENCE
- Column U: "No evidence identified through [N] searches across [M] tiers targeting
  [diagnostic Q topic]. Proxy searches for [list] also yielded no results. Recommend
  internal discovery: [specific question]."

---

## Domain-Specific Search Libraries

### P1: Strategy, Governance & Culture

**High-value sources**: Annual reports, proxy statements, board committee charters,
press releases, ESG reports, investor presentations, Glassdoor

**Rich document priority**: ALWAYS `web_fetch` annual reports and proxy statements
when found. They contain evidence for 50%+ of P1 subcaps.

**P1-specific proxy searches**:
- Board technology oversight: "[Entity] board director CTO CIO technology" + proxy statement
- Strategic cadence: "[Entity] strategic plan annual planning budget cycle"
- Innovation program: "[Entity] fintech lab accelerator hackathon startup"
- Change management: "[Entity] digital transformation change management rollout"
- ESG: "[Entity] ESG TCFD climate risk sustainability report CSR"

### P2: Customer Experience

**High-value sources**: App stores, CFPB complaints, J.D. Power, company website
(test digital account opening), customer testimonials, industry awards

**Rich document priority**: ALWAYS `web_fetch` CFPB complaint narratives (themes reveal
service gaps). ALWAYS check both iOS App Store AND Google Play.

**P2-specific proxy searches**:
- Digital adoption: "[Entity] mobile banking adoption users active"
- Onboarding: "[Entity] online account opening digital enrollment time"
- Omnichannel: "[Entity] branch contact center chat mobile integration"
- Personalization: "[Entity] recommendation engine next best action AI"
- Marketing tech: "[Entity] marketing automation campaign email digital"

### P3: Operations, Risk & Compliance

**High-value sources**: Regulatory enforcement databases, CFPB actions, SOC2/ISO mentions,
breach disclosure databases, operational resilience reports

**Rich document priority**: ALWAYS search ALL relevant regulator enforcement pages.
Document negative searches (no enforcement = positive P3C3 signal).

**P3-specific proxy searches**:
- Automation level: "[Entity] straight through processing rate exception"
- Fraud tech: "[Entity] fraud detection real-time machine learning alert"
- Compliance tech: "[Entity] regtech compliance monitoring automated"
- BCP/DR: "[Entity] business continuity disaster recovery test exercise"
- TPRM: "[Entity] vendor management third party risk program"

### P4: Data, Analytics & Technology

**High-value sources**: Job postings (reveal tech stack + seniority), vendor case studies,
technology conference presentations, CDO/CTO announcements, patent filings

**Rich document priority**: ALWAYS search LinkedIn/Indeed for current technology job
postings. They reveal: what tools are in use, what seniority level is being hired (maturity
signal), what skills are prioritized, what gaps exist.

**P4-specific proxy searches**:
- Data governance: "[Entity] CDO chief data officer data strategy governance"
- Analytics: "[Entity] analytics dashboard predictive model AI ML"
- Architecture: "[Entity] core system migration cloud API modernization"
- Integration: "[Entity] MuleSoft integration API middleware ESB"
- Cybersecurity: "[Entity] SOC2 ISO 27001 cybersecurity CISO penetration"
- AI/GenAI: "[Entity] generative AI chatbot virtual assistant copilot 2024 2025"

---

## Search Volume Management

### Expected Volume
~836 subcaps × 3-5 queries = **2,500-4,200 web searches** per assessment.
Plus ~100-200 `web_fetch` calls on rich documents.

### Batching Strategy
- **Per-capability batches**: Process all subcaps in one capability before moving to next
- **Checkpoint after each capability**: Save evidence index, print stats
- **Checkpoint after each category**: Save workbook progress, print coverage summary
- **Emergency checkpoint**: If approaching context limits, stop at capability boundary

### Context Window Optimization
- Compact output format (1 line per finding) saves ~80% of tokens vs prose
- Do NOT reproduce search result snippets in chat — extract facts directly
- Rich document mining supplements per-subcap searches (mine once, map broadly)
- After fetching a rich document, mine it for ALL subcaps at once (not one at a time)
- Print capability summaries, not individual search narration
