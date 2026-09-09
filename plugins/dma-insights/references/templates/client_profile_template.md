<!-- TEMPLATE OF RECORD: Client Profile Research Report
     Google Doc id 142FoFcgs2-zzMm2_y4ykQW_gSUVbIOWSMHV_sgITs0Y (open it from Drive by id; the engine reads it through
     drive_fetch.py under the service-account identity, never from a shell).
     Exported 2026-09-03 as markdown. READ-ONLY copy: the engine's report spec
     (engine/report_spec.py) is built from report_templates.json beside this file,
     and tests assert the two agree. Re-pin with `engine.template pin` when the
     owner changes the Doc. -->

![][image1]

| Client Profile {{ENTITY_NAME}} |
| :---- |

| SUB-VERTICAL {{SUBVERTICAL_NAME}} | SIZE TIER {{SIZE_TIER}} |
| :---- | :---- |
| **ASSESSMENT ID** {{ASSESSMENT_ID}} | **ASSESSMENT DATE** {{DATE}} |
| **EVIDENCE MODE** {{EVIDENCE_MODE}} | **WEBSITE** {{WEBSITE}} |
| **CATALOGUE** {{CATALOGUE_VERSION}} ({{CATALOGUE_HASH_SHORT}}) | **PREPARED BY** Zennify Digital Maturity Assessment |

# Contents

###### *Select all (Ctrl+A) then press F9 in Word to populate page numbers after the template is filled.*

# Document Control and Catalogue Binding

*Every value below is resolved at render time from the active catalogue. Nothing here is typed by hand. If any field resolves to UNRESOLVED, the render fails and the profile is not handed off.*

| Field | Token | Resolution source |
| :---- | :---- | :---- |
| **Catalogue version** | {{CATALOGUE_VERSION}} | Catalogue_Meta\!version |
| Catalogue content hash | {{CATALOGUE_HASH}} | SHA-256 over the catalogue rows, computed at load |
| Catalogue resolved at | {{CATALOGUE_RESOLVED_AT}} | Render timestamp, UTC |
| Resolution path taken | {{CATALOGUE_SOURCE}} | One of: WORKBOOK_META, CATALOGUE_MANIFEST, CONNECTOR |
| **Structure counts** | {{PILLAR_COUNT}} pillars / {{CATEGORY_COUNT}} categories / {{CAPABILITY_COUNT}} capabilities / {{SUBCAP_COUNT}} subcapabilities | Counted from Catalogue_Meta, never asserted |
| Sub-vertical | {{SUBVERTICAL_NAME}} ({{SUBVERTICAL_ID}}), confidence {{SUBVERTICAL_CONFIDENCE}}% | Classification step |
| Evidence tier scheme | {{TIER_COUNT}} tiers, {{TIER_SCHEME_ID}} | Catalogue_Meta\!tier_scheme |
| Gate set | {{GATE_COUNT}} gates, {{GATE_SET_ID}} | Gate_Log, counted |
| Research workbook | {{RESEARCH_WORKBOOK}} rev {{RESEARCH_WORKBOOK_REV}} | File metadata |
| Scoring workbook | {{SCORING_WORKBOOK}} rev {{SCORING_WORKBOOK_REV}} | File metadata |

| RESOLUTION RULE ORDER: Try Catalogue_Meta in the scoring workbook first. If absent or stale, read the catalogue manifest shipped with the plugin. If that is unreachable, call the DMA Insights connector for the active catalogue. Record which path succeeded in {{CATALOGUE_SOURCE}}. COUNTS: Pillar, category, capability, subcapability, tier and gate counts are derived by counting catalogue rows at render time. Never write one as a literal in prose. HANDOFF: The hash recorded here is written into Handoff_Lock. The assessment stage compares against it and refuses to score if the catalogue has moved. FAIL IF: All three resolution paths fail, any structure count resolves to zero, or the sub-vertical is not present in the catalogue. |
| :---- |

### How to read the section controls

Each section opens with a control block. LENGTH gives a word band for narrative in that section, excluding table content; the lower bound is a blocking gate and the upper bound is advisory. MINIMUM DATA lists the counts the section must carry before the research is considered usable by the assessment stage. FAIL IF lists the conditions that block handoff.

| Total narrative budget | Minimum | Maximum |
| :---- | :---- | :---- |
| All sections, excluding tables and this control page | {{PROFILE_WORD_MIN}} words | {{PROFILE_WORD_MAX}} words |

###### *Budget tokens are computed by summing the per-section bands at render time, so editing one section control updates the total automatically.*

# Surface Alignment

*This profile is one input to the DMA Insights app, and for three surfaces it is the source of truth rather than a fallback. Firmographics, client focus areas and the leadership roster are read from this document, so a section left thin here renders as an empty card under the client's name.*

| Section | Feeds app surface | This document is |
| :---- | :---- | :---- |
| 1. Firmographics | O2 firmographics strip | **Source of truth (after the run manifest and entity profile)** |
| 2. Executive Summary | O4 exec summary, O3 why-now signals | Input to challenge |
| 3. Entity Profile | O2 firmographics, C3 regulatory standing | Supporting |
| 4. Market Position and Trends | O1 peers, O8 and C6 financial, C1 timeline, O9 and C4 sentiment | Supporting |
| 5. Strategic Intelligence | I1 insight cards, T1 and T2 tech stack, O7 leadership, O12 thought leadership, C5 acquisitions | **Source of truth for the leadership roster** |
| 6. Client Priorities | H1 focus areas | **Source of truth for every verbatim quote and page number** |
| 7. Risk and Issues | C2 issue register, C3 regulatory standing | Supporting |
| 8. Workbook References | No served surface | Internal |

###### *Measured across the app corpus: 57 of 138 clients shipped with no focus areas at all, and 53 shipped machine scoring text where a client quote belonged. Both failures start in this document.*

| STANDING CLAUSES CARRIED FROM THE APP IDENTITY: Every figure asserts this legal entity by name, regulator and footprint. A parent, a subsidiary or a same-name institution is contamination. A figure that cannot be tied to this entity is quarantined with a written reason, never rendered and never guessed. ABSENCE: A field with nothing behind it carries a real reason or it carries nothing. A status word such as pending, queued or held never renders. A recorded absence names what was searched, where and when. ORDER: Field order is meaning. The order fields are written here is the order the app serves them, so write them in the order the strip should read. VARIANT CELLS: Never map a claim to a cell whose code names a sub-vertical other than {{SUBVERTICAL_ID}}. It resolves in the workbook and renders nowhere. EVIDENCE COVERAGE: Not carried in this document. Coverage and tier distribution are O10 and O11, they are internal instrumentation, and the app does not serve them to clients. |
| :---- |

# 1. Firmographics

| SECTION CONTROL: 1. FIRMOGRAPHICS PURPOSE: Establish the identity anchor. Every later claim in both documents hangs on these figures being about this legal entity. FEEDS: O2 firmographics strip, rendered inside the app hero on D1 Overview. INPUTS: Regulatory registry for the ownership shape, the entity's own investor and about pages, filings. Route table below. LENGTH: 150 to 250 words of narrative around the table. MINIMUM DATA: Every must-present field either stated with a value or quarantined with a written reason. Blank is neither. Each populated field carries value, unit, as_of, source_e_id and confidence. MUST INCLUDE: Website, bare and lowercased. It is required on every sub-vertical and it is the only firmographic that is load-bearing elsewhere in the app. MUST NOT: Model a figure the entity does not disclose. Send footprint as a firmographic: it renders from regulatory standing jurisdictions in section 7, and the two must agree. Serialise branches as anything other than an integer. FAIL IF: A must-present field is blank rather than stated or quarantined, website is written with a scheme or a www prefix, or any figure fails the identity check. |
| :---- |

### 1.1 Must-present fields

###### *Write these in the order the strip should read. Submitted order is served order, so ranking matters.*

| Field | Value | Unit | As at | Evidence | Conf. |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **website** | {{DOMAIN_BARE_LOWERCASE}} | n/a | {{DATE}} | {{E_ID}} | {{CONF}} |
| employees | {{VALUE}} | headcount | {{DATE}} | {{E_ID}} | {{CONF}} |
| assets_or_aum_or_revenue | {{VALUE}} | {{UNIT}} | {{DATE}} | {{E_ID}} | {{CONF}} |
| cagr | {{VALUE}} | {{PERCENT_A_YEAR_OVER_PERIOD}} | {{DATE}} | {{E_ID}} | {{CONF}} |
| branches | {{INTEGER}} | count | {{DATE}} | {{E_ID}} | {{CONF}} |
| headquarters | {{CITY_STATE}} | n/a | {{DATE}} | {{E_ID}} | {{CONF}} |
| founded | {{YEAR}} | year | {{DATE}} | {{E_ID}} | {{CONF}} |
| primary_regulator | {{REGULATOR}} | n/a | {{DATE}} | {{E_ID}} | {{CONF}} |
| charter | {{CHARTER_TYPE}} | n/a | {{DATE}} | {{E_ID}} | {{CONF}} |
| ownership | {{STRUCTURE}} | n/a | {{DATE}} | {{E_ID}} | {{CONF}} |

###### *Field names follow the sub-vertical vocabulary. A credit union carries shares, member_count and net_worth_ratio; it never carries a bank's deposits. Undated share across the set: {{UNDATED_PCT}}, stated rather than hidden.*

### 1.2 Quarantined and absent fields

###### *A field that cannot be resolved to this entity is quarantined with a reason a reader can act on. A field the entity genuinely does not disclose is absent with its route recorded. Absent and quarantined are different states and the app renders them differently.*

| Field | State | Reason as written for the reader | Route attempted | Searched |
| :---- | :---- | :---- | :---- | :---- |
| {{FIELD}} | {{QUARANTINED | ABSENT}} | {{REAL_REASON_NOT_A_STATUS_WORD}} | {{REGISTRY_OR_SOURCE}} | {{DATE}} |

###### *A real reason renders. 'A credit union returns its surplus to members' explains an absent revenue field and is worth reading. 'Queued for enrichment' is a status word and must never appear.*

### 1.3 Which registry holds the figure

###### *Route by ownership shape as well as sub-vertical. For an entity that files nothing, every route built on a filer misses, and the strip comes back empty from a search that was run correctly, which reads as a verified absence when it is not.*

| Ownership shape | Where the firmographic lives |
| :---- | :---- |
| SEC registrant | 10-K and 10-Q cover page and MD\&A; XBRL facts carry the period explicitly |
| Insured depository, unlisted | The regulator's call report, NCUA 5300 or FFIEC and UBPR, quarterly and dated |
| Private, employee-owned | Trade press annual ranking tables; Form 5500 for an ESOP, which is public and dated; state licence registries; the entity's own acquisition announcements, which usually disclose the target's revenue and headcount |
| Insurance intermediary | State departments of insurance the entity is licensed in, plus the NAIC producer database, which also gives section 7 its jurisdictions |
| Affiliated adviser or broker-dealer | SEC Form ADV via IAPD, and FINRA BrokerCheck |

### 1.4 Identity check

| Check | Result | Basis |
| :---- | :---- | :---- |
| Legal entity name matches every figure | {{PASS | QUARANTINE}} | {{E_ID}} |
| Regulator consistent across all sources | {{PASS | QUARANTINE}} | {{E_ID}} |
| Footprint agrees with section 7 jurisdictions | {{PASS | MISMATCH}} | {{E_ID}} |
| Magnitude sane for size tier and sub-vertical | {{PASS | REJECT}} | {{BASIS}} |
| No parent or same-name contamination | {{PASS | QUARANTINE}} | {{E_ID}} |

###### *A disagreement between this section and section 7 is a contradiction, not a variation. Fix it in section 7 and make the two agree before handoff.*

# 2. Executive Summary

| SECTION CONTROL: 2. EXECUTIVE SUMMARY PURPOSE: Tell an account executive what this institution is, what matters about it, and where Zennify has a right to a conversation. FEEDS: O4 exec summary and O3 why-now signals. The app challenges this summary rather than copying it, so write it to be argued with. INPUTS: Research workbook: Evidence_Register, Tech_Landscape, Coverage_Map. LENGTH: 500 to 800 words. Minimum is blocking. MINIMUM DATA: Snapshot fully populated with a classification confidence. 5 to 7 findings, each carrying a quantified observation with an E-ID, a maturity implication and a named Zennify solution. Every critical gap with a priority and the capabilities it affects. 3 or more strategic objectives tied to a source. MUST INCLUDE: For every finding, why it matters to a sales conversation and which solution applies. At least one finding on the AI or data position, since the assessment carries an AI and data overlay in every pillar. MUST NOT: State a finding without a quantified observation. 'Strong digital presence' is not a finding; 'mobile app rated 4.6 across 12,400 reviews [E-042]' is. FAIL IF: Fewer than 5 findings, or any finding lacking an E-ID. |
| :---- |

| PRE-WRITE PROTOCOL 1: What data is most relevant for this entity, given its sub-vertical and size tier? 2: Why does it matter to an account executive preparing for a first conversation? 3: What is the implication for Zennify, and which solution does it point at? ONLY THEN: Write. Answer all three internally before the first sentence. |
| :---- |

### 2.1 Entity snapshot

| Field | Value | Evidence |
| :---- | :---- | :---- |
| Entity name | {{ENTITY_NAME}} | {{E_ID}} |
| Sub-vertical classification | {{SUBVERTICAL_NAME}} (confidence {{SUBVERTICAL_CONFIDENCE}}%) | {{E_ID}} |
| Size tier | {{SIZE_TIER}} | {{E_ID}} |
| Primary metric | {{PRIMARY_METRIC_NAME}}: {{PRIMARY_METRIC_VALUE}} | {{E_ID}} |
| Headquarters | {{HEADQUARTERS}} | {{E_ID}} |
| Geographic footprint | {{FOOTPRINT}} | {{E_ID}} |
| Primary regulator | {{REGULATOR}} | {{E_ID}} |

### 2.2 Top findings

| ID | Finding | Quantified observation | Maturity implication | Zennify relevance |
| :---- | :---- | :---- | :---- | :---- |
| F-{{NNN}} | {{FINDING_TITLE}} | {{OBSERVATION}} [{{E_ID}}] | {{IMPLICATION}} | {{SOLUTION_NAME}} because {{WHY}} |

###### *5 to 7 rows. Order by relevance to a first conversation, not by pillar.*

### 2.3 Critical gaps

###### *Gaps in the research that will constrain scoring accuracy. Each one flows to the internal evidence request held in the workbook.*

| ID | Gap | Priority | Capabilities affected | Effect on scoring | How to close |
| :---- | :---- | :---- | :---- | :---- | :---- |
| G-{{NNN}} | {{GAP}} | {{1 | 2 | 3}} | {{CAP_IDS}} | {{EFFECT}} | {{METHOD}} |

### 2.4 Strategic objectives

###### *What the entity says it intends to achieve, and how that maps to current industry direction. Sourced from the entity's own statements, not inferred.*

| Objective | Stated where | Horizon | Industry trend it tracks | Capability implication |
| :---- | :---- | :---- | :---- | :---- |
| {{OBJECTIVE}} | {{E_ID}} | {{HORIZON}} | {{TREND}} | {{CAP_IDS}} |

### 2.5 Why-now signals

###### *Dated triggers that make this a conversation for now rather than later. Emit 2 to 4. All five columns are required on every signal, and the one that gets left out is the cost of acting now: a signal carrying only upside is a pitch rather than a finding. Name the concurrent commitment it collides with, drawn from the timeline, the issue register or the tech stack, and where the cost is genuinely low say why it is low.*

| ID | Dated trigger | Window and what closes it | Consequence of waiting | Cost of acting now | Why first | Ev. |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| WN-{{NN}} | {{WHAT_CHANGED_AND_WHEN}} | {{WINDOW_AND_CLOSING_EVENT}} | {{WHICH_CELL_DEGRADES}} | {{COLLIDING_COMMITMENT}} | {{REASON}} | {{E_ID}} |

###### *An undated trigger is not a trigger and a window with no closing event is not a window; drop either rather than implying urgency the evidence does not support. A change of control, a regulatory deadline, a leadership arrival and a contract renewal are all why-now signals and belong here as well as in their own sections.*

# 3. Entity Profile

| SECTION CONTROL: 3. ENTITY PROFILE PURPOSE: Establish the organisational facts every later section depends on. FEEDS: O2 firmographics and C3 regulatory standing. C3 jurisdictions are what the O2 strip renders as footprint, so the two must agree. INPUTS: Regulatory filings, annual reports, corporate registry, entity site. LENGTH: 400 to 700 words. MINIMUM DATA: 3 or more years of the primary financial metric. Named primary regulator with licence status. Enforcement history searched, with a nil result recorded explicitly where nothing is found. Business lines with revenue contribution where published. MUST INCLUDE: An E-ID against every claim. A CAGR where 3 or more years are available, shown with its inputs. MUST NOT: Treat an absence of published data as an absence of the underlying function. FAIL IF: Fewer than 3 years of financial data with no explanation, or the regulator is unnamed. |
| :---- |

### 3.1 Corporate identity

| Field | Value | Evidence |
| :---- | :---- | :---- |
| Legal name | {{LEGAL_NAME}} | {{E_ID}} |
| Formation date | {{FORMATION_DATE}} | {{E_ID}} |
| Corporate structure | {{STRUCTURE}} | {{E_ID}} |
| Ownership | {{OWNERSHIP}} | {{E_ID}} |
| Registered address | {{ADDRESS}} | {{E_ID}} |

### 3.2 Scale metrics

| Metric | Current | 3 years prior | CAGR | Evidence |
| :---- | :---- | :---- | :---- | :---- |
| {{METRIC_NAME}} | {{CURRENT}} | {{PRIOR}} | {{CAGR_PCT}} | {{E_ID}} |

###### *CAGR: ({{END_VALUE}} / {{START_VALUE}}) ^ (1 / {{YEAR_COUNT}}) \- 1. Show the inputs so the figure can be checked.*

### 3.3 Regulatory standing

###### *Enforcement history drives the issue register and cap determination. A confirmed nil result is evidence and must be recorded, not omitted.*

| Field | Value | Searched | Evidence |
| :---- | :---- | :---- | :---- |
| Primary regulator | {{REGULATOR}} | n/a | {{E_ID}} |
| Licence status | {{STATUS}} | n/a | {{E_ID}} |
| Enforcement actions | {{ACTIONS_OR_NONE_FOUND}} | {{DATE}} | {{E_ID}} |
| Consent orders | {{ORDERS_OR_NONE_FOUND}} | {{DATE}} | {{E_ID}} |
| Additional jurisdictions | {{JURISDICTIONS}} | n/a | {{E_ID}} |

### 3.4 Business composition

| Business line | Revenue contribution | Primary products | Digital delivery | Evidence |
| :---- | :---- | :---- | :---- | :---- |
| {{LINE}} | {{PCT_OR_UNPUBLISHED}} | {{PRODUCTS}} | {{CHANNELS}} | {{E_ID}} |

# 4. Market Position and Trends

| SECTION CONTROL: 4. MARKET POSITION AND TRENDS PURPOSE: Lock the peer set and establish the direction of travel before any scoring begins. FEEDS: O1 peer benchmarks, O8 and C6 financial trajectory, C1 digital evolution timeline, O9 and C4 sentiment. C1 needs three or more dated points to draw an arc. INPUTS: Regulatory call reports, peer filings, app stores, employer review sites, press. LENGTH: 500 to 850 words. MINIMUM DATA: 3 to 5 peers, each with size tier, key metric, geographic overlap percentage and a selection rationale. 5 years of financial data with a trend classification and a computed CAGR. 6 or more timeline rows across 3 or more distinct years. Sentiment from 2 or more sources with numeric ratings, sample sizes where published, and observation dates. MUST INCLUDE: The peer set lock statement. Once this section is approved the peer set is immutable for the assessment. MUST NOT: Select peers on size alone. Overlap and comparability carry equal weight. FAIL IF: Fewer than 3 peers, more than 5 peers, or any peer without a selection rationale. |
| :---- |

### 4.1 Peer comparison

| Peer | Size tier | Key metric | Geography | Overlap % | Selection rationale |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{PEER_NAME}} | {{TIER}} | {{METRIC}} | {{GEOGRAPHY}} | {{PCT}} | {{RATIONALE}} |

**Peer set lock: once this section is approved, the peer set is immutable for the remainder of the assessment. It is written to Handoff_Lock and the assessment stage reads it from there.**

### 4.2 Financial trajectory

| Year | {{PRIMARY_METRIC_NAME}} | Year on year | Evidence | Trend classification |
| :---- | :---- | :---- | :---- | :---- |
| {{YEAR}} | {{VALUE}} | {{YOY_PCT}} | {{E_ID}} | {{ACCELERATING | STABLE | DECLINING | VARIABLE}} |

### 4.3 Digital evolution timeline

###### *Feeds the assessment timeline directly. Keep it chronological and keep every row sourced.*

| Date | Initiative | Evidence | Capability impact | Zennify relevance |
| :---- | :---- | :---- | :---- | :---- |
| {{DATE}} | {{INITIATIVE}} | {{E_ID}} | {{CAP_IDS}} | {{RELEVANCE}} |

### 4.4 Sentiment overview

| Source | Rating | Scale | Sample | As at | Direction | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| {{SOURCE}} | {{RATING}} | {{SCALE}} | {{N}} | {{DATE}} | {{DIRECTION}} | {{E_ID}} |

# 5. Strategic Intelligence

| SECTION CONTROL: 5. STRATEGIC INTELLIGENCE PURPOSE: The analytical core. Move from facts to judgement to implication, and gather the raw material the assessment overlay depends on. FEEDS: I1 insight cards, T1 and T2 tech stack, O7 leadership, O12 thought leadership, C5 acquisitions. The app has no package source for leadership or thought leadership, so what is captured here is all it will ever have. INPUTS: Job postings, vendor case studies, conference material, leadership profiles, press, technographic scan. LENGTH: 700 to 1100 words. MINIMUM DATA: 8 or more insight cards, each with observation, interpretation, implication, capabilities touched and a confidence. Technology landscape populated across all four categories. Peer technographic scan covering the locked peer set. AI and data signals recorded for every pillar. Leadership with tenure and an explicit gap list. Acquisitions, or an explicit nil. MUST INCLUDE: Interpretation that a reader could disagree with. A card that only restates a fact is not an insight card. MUST NOT: List facts without judgement. Treat a leadership title being absent from public sources as proof the function is absent. FAIL IF: Fewer than 8 insight cards, or the technographic scan is missing with no fallback recorded. |
| :---- |

### 5.1 Insight cards

| ID | Observation (what) | Interpretation (why) | Implication (so what) | Capabilities | Conf. | Flag |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| IC-{{NNN}} | {{FACT}} [{{E_ID}}] | {{JUDGEMENT}} | {{SOLUTION_ALIGNMENT}} | {{CAP_IDS}} | {{HIGH | MED | LOW}} | {{FLAG}} |

### 5.2 Technology landscape

###### *One row per named product. Vendor and product are separate fields, and a service or a category is not a product: a CRM is a category, and a named CRM product is a product. This register is what the app reads to build the stack page, so a row that is a category name renders as a category name under the client's name.*

| ts_id | Vendor | Product | Layer | Status | Ev. level | As at |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| {{TS_ID}} | {{VENDOR}} | {{PRODUCT}} | {{OPS | CUST | DATA | INFRA}} | {{CONFIRMED | INFERRED | CLAIMED | ABSENT}} | {{L1 | L2 | L3 | L4}} | {{DATE}} |

| ts_id | Detection basis (one clause, under 160 characters) | Cells it serves | Evidence |
| :---- | :---- | :---- | :---- |
| {{TS_ID}} | {{ONE_CLAUSE}} | {{CELL_IDS}} | {{E_IDS}} |

###### *Detection basis is one clause and it renders as a single muted line under the product name. Anything longer belongs in the assessment report's estate impact card, not here.*

#### **Layers**

###### *Four layers, spelled exactly as below. Do not substitute level codes: those collide with the evidence levels carried on the same card.*

| Layer | Covers | Pillar | Detected | Expected | Primary gap |
| :---- | :---- | :---- | :---- | :---- | :---- |
| OPS | Operations and core banking | {{P3_ID}} | {{N}} | {{N}} | {{Y | N}} |
| CUST | Customer engagement | {{P2_ID}} | {{N}} | {{N}} | {{Y | N}} |
| DATA | Data and analytics | {{P4_ID}} | {{N}} | {{N}} | {{Y | N}} |
| INFRA | Infrastructure and cloud | {{P4_ID}} | {{N}} | {{N}} | {{Y | N}} |

#### **Status vocabulary**

| Status | Means | What it requires |
| :---- | :---- | :---- |
| CONFIRMED | In use, and something says so | A source row. A machine scan alone is a detection, not a confirmation |
| INFERRED | The evidence points at it without naming it | The inference stated, and what it was drawn from |
| CLAIMED | Marketing or a vendor page asserts it | The claim, and who is making it |
| ABSENT | Looked for, not found | The ladder: what was searched, where, and when |

###### *Status is required on every row. The landscape strip recomputes its counts from this field, so a blank status makes the strip uncomputable. Technology gaps are the ABSENT rows read together, which is why they are not a separate column.*

#### **Dropped candidates**

###### *A candidate you cannot cite is a rumour. It is reported here with its reason, never silently discarded, because a reader who has heard the rumour will otherwise assume it was missed.*

| Candidate | Where it surfaced | Why it was dropped |
| :---- | :---- | :---- |
| {{CANDIDATE}} | {{SOURCE}} | {{REASON}} |

#### **Compliance attestations**

| Attestation | Scope as stated | As at | Evidence |
| :---- | :---- | :---- | :---- |
| {{ATTESTATION}} | {{SCOPE}} | {{DATE}} | {{E_ID}} |

###### *Record only what the client states. An attestation the client has not claimed is not an attestation.*

#### **Peer technographic scan**

###### *Primary source for the platform peer comparison carried in the assessment report. Run against the peer set locked in section 4.1 and written to Platform_Peer_Adoption in the scoring workbook.*

| Platform | Entity | {{PEER_1}} | {{PEER_2}} | {{PEER_3}} | Source | Confidence |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| {{PLATFORM_NAME}} | {{Y | N | UNKNOWN}} | {{Y | N | UNKNOWN}} | {{Y | N | UNKNOWN}} | {{Y | N | UNKNOWN}} | {{SCAN | RESEARCH}} | {{HIGH | MED | LOW}} |

| TECHNOGRAPHIC SOURCING AND DEGRADATION PRIMARY: The technographic scan across the locked peer set. Rows sourced this way are marked SCAN. FALLBACK: Manual research, from filings, vendor case studies, job postings or conference material. Rows sourced this way are marked RESEARCH and carry an E-ID. DEGRADATION: Where the scan returns nothing for a peer, fall back to research for that peer only. State coverage explicitly, for example 'scan covered 3 of 5 peers, 2 by research'. CONFIDENCE: HIGH when the scan covers every peer. MEDIUM when at least half the peer set is scan-sourced. LOW when more than half is research or unknown. COLUMN COUNT: The peer columns expand to {{PEER_COUNT}}, generated from Handoff_Lock rather than fixed here. FAIL IF: The scan is absent and no research fallback is recorded, or coverage is not stated. |
| :---- |

#### **AI and data signals**

###### *Raw material for the AI and data overlay carried in every pillar of the assessment report. Record one row per pillar, writing NONE_FOUND where nothing surfaces rather than leaving the row out.*

| Pillar | AI or automation observed | Data platform observed | Governance signal | Hiring signal | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{PILLAR_ID}} | {{OBSERVED_OR_NONE_FOUND}} | {{PLATFORM_OR_NONE_FOUND}} | {{SIGNAL}} | {{ROLES_POSTED}} | {{E_ID}} |

###### *One row per pillar. Row count equals {{PILLAR_COUNT}}, iterated from the catalogue.*

### 5.3 Leadership

###### *This document is the roster source for the app. Each entry gets roughly 25 words on what the person owns that the assessment touches; an entry that restates the job title is an org chart row and adds nothing. An empty roster is an explicit verified absence naming every source searched, never a silent blank. Record the search that established a gap, since an unlisted executive is not a missing function.*

| Role | Name | Tenure | What they own that the assessment touches | Contact route | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{ROLE}} | {{NAME_OR_NOT_IDENTIFIED}} | {{TENURE}} | {{RELEVANCE_25_WORDS}} | {{ESTABLISHED | NONE}} | {{E_ID}} |

| Role searched | Found | Search performed | Proxy evidence for the function | Conclusion |
| :---- | :---- | :---- | :---- | :---- |
| {{ROLE}} | {{Y | N}} | {{METHOD_AND_DATE}} | {{PROXY_OR_NONE}} | {{GAP_CONFIRMED | INCONCLUSIVE}} |

### 5.4 Acquisition history

###### *Recent acquisitions often explain technology fragmentation and integration debt. Record an explicit nil where none are found.*

| Date | Target | Rationale | Integration status | Technology implication | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{DATE}} | {{TARGET}} | {{RATIONALE}} | {{STATUS}} | {{IMPLICATION}} | {{E_ID}} |

### 5.5 Thought leadership and public voice

###### *The entity's own public voice, dated and verbatim. The app has no package source for this, so if it is not captured here it does not exist for the run. Quote the executive, do not summarise them.*

| Speaker and role | Verbatim statement | Venue | Date | Theme | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{NAME_ROLE}} | {{VERBATIM}} | {{VENUE}} | {{DATE}} | {{THEME}} | {{E_ID}} |

# 6. Client Priorities

| SECTION CONTROL: 6. CLIENT PRIORITIES PURPOSE: Capture what the client says its own priorities are, in the client's own words, with a page number an account executive can point at in the room. FEEDS: H1 focus areas on D3 Heatmap, and P2b conversation starters on D4 Platform. This document is the source of truth: the app reads the quote and the page from here and has no other route to them. INPUTS: The client's own documents. Strategic plans, annual reports, letters to members or shareholders, board materials, published strategy pages, meeting notes where they exist. LENGTH: 300 to 500 words. MINIMUM DATA: 3 to 5 priorities. Each carries a verbatim quote of 50 to 400 characters, the source document, the page number, the filename, and the capability cells it bears on. Each carries a currency status and a note. MUST INCLUDE: The page number. Document, page and filename together are the provenance triple, and without the page an account executive cannot show the client where it came from. MUST NOT: Quote the scoring ledger, a diagnostic question, a scoring rationale, a section tag, or any text containing a capability code or a maturity level. That is machine text, not the client speaking. Map a priority to a cell this run does not serve. FAIL IF: Fewer than 3 priorities on a client with a full assessment, any quote without a page number, or any quote that reads as though a system rather than a person wrote it. |
| :---- |

| QUOTE ADMISSIBILITY TEST IT PASSES IF: A person wrote it about their own institution, and a reader who knows nothing about this framework would understand it. REJECT IF IT CONTAINS: A capability code in the pillar-category form, the words score or maturity followed by a level, the word category followed by a code, a bracketed section tag, or the phrasing of a diagnostic question. REJECT IF: The source document belongs to a different entity. Check the filename and the running header before quoting, since a profile carrying another institution's filename has shipped before. LENGTH: 50 to 400 characters, verbatim, copied rather than paraphrased. Trim with an ellipsis at a clause boundary if it runs long, never mid-phrase. |
| :---- |

### 6.1 Stated priorities

| ID | Priority in the client's words | Verbatim quote | Document | Page | Cells |
| :---- | :---- | :---- | :---- | :---- | :---- |
| FA-{{NN}} | {{TITLE}} | {{QUOTE_50_TO_400_CHARS}} | {{FILENAME}} | {{PAGE}} | {{CELL_IDS}} |

###### *3 to 5 rows. Titles must be distinguishable from one another: two priorities that reduce to the same phrase are one priority recorded twice.*

### 6.2 Currency check

###### *The document tells you what the client said then. This table establishes what they are saying now. A superseded priority is one of the most valuable findings this research can produce, because without it an account executive walks in carrying last year's agenda.*

| ID | Currency status | Newest supporting statement | Stated on | Where found | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| FA-{{NN}} | {{CONFIRMED_CURRENT | AGING | SUPERSEDED | UNCONFIRMED}} | {{NOTE_20_TO_45_WORDS}} | {{DATE}} | {{SOURCE}} | {{E_ID}} |

| Status | Means | What to record |
| :---- | :---- | :---- |
| CONFIRMED_CURRENT | Restated within the last 12 months | The statement and its date |
| AGING | Last stated 12 to 24 months ago | The most recent statement found |
| SUPERSEDED | They now say something different | What they say instead, and when they said it |
| UNCONFIRMED | No recent statement found | What was searched, where, and on what date |

### 6.3 Sources checked for current voice

###### *Every source read here is minted as evidence with a URL, a verbatim excerpt, a retrieval date and a tier, then linked to the priority and to the cells it bears on. Enrichment that is not recorded cannot open in a drilldown, so an unrecorded source may as well not have been read.*

| Source class | Checked | Date | Yield | Evidence minted |
| :---- | :---- | :---- | :---- | :---- |
| Two most recent quarterly filings and latest annual report | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |
| Newsroom and press releases, last 12 months | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |
| Executive interviews and podcasts | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |
| Conference talks and panels | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |
| Earnings call commentary where public | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |
| Trade press naming the entity | {{Y | N}} | {{DATE}} | {{FINDING_OR_NIL}} | {{E_IDS}} |

###### *Run a search per priority. One document-level search mapped identically onto five priorities is the most common failure in this section.*

### 6.4 Counter-evidence pass

###### *For each priority, search for the case against it before shipping it.*

| ID | Paused, completed or replaced? | Plausible for this sub-vertical and size? | Client framing or vendor framing? | Verdict |
| :---- | :---- | :---- | :---- | :---- |
| FA-{{NN}} | {{FINDING_OR_NIL}} | {{Y | N}} | {{CLIENT | VENDOR}} | {{SHIP | SHIP_LOW_CONF | DROP}} |

# 7. Risk and Issues

| SECTION CONTROL: 7. RISK AND ISSUES PURPOSE: Surface everything that will cap a score, and record the boundaries of what the research established. FEEDS: C2 issue register and C3 regulatory standing. C2 wants one row per matter with a status that is never null. INPUTS: Regulatory actions, breach databases, litigation records, complaint data, press. LENGTH: 400 to 650 words. MINIMUM DATA: Every issue with type, severity, status, capability impact and cap value. Negative searches across 4 or more categories, each with the search date. Every assumption with a validation method that internal discovery could execute. MUST INCLUDE: The severity to cap mapping in force, read from Cap_Triggers rather than restated from memory. MUST NOT: Record an assumption without a way to test it. FAIL IF: An issue carries a severity but no capability impact, or an assumption has no validation method. |
| :---- |

### 7.1 Issue register

| ID | Type | Severity | Status | Description | Capability impact | Cap |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| I-{{NNN}} | {{TYPE}} | {{SEVERITY}} | {{STATUS}} | {{DESCRIPTION}} | {{CAP_IDS}} | {{CAP_VALUE}} |

###### *Severity to cap mapping is read from Cap_Triggers at render time, so a change to the rule set propagates without editing this template. {{CAP_RULE_COUNT}} rules are active for {{SUBVERTICAL_NAME}}.*

| Severity | Maximum score | Effect | Source |
| :---- | :---- | :---- | :---- |
| {{SEVERITY}} | {{MAX_SCORE}} | {{EFFECT}} | Cap_Triggers |

### 7.2 Negative search results

###### *Confirmed absence is evidence. Record what was searched, where, and when.*

| Category searched | Source | Query | Date | Result | Evidence |
| :---- | :---- | :---- | :---- | :---- | :---- |
| {{CATEGORY}} | {{SOURCE}} | {{QUERY}} | {{DATE}} | {{NONE_FOUND | N_FOUND}} | {{E_ID}} |

### 7.3 Assumptions register

| ID | Assumption | Why it was needed | Capabilities affected | Validation method | Priority |
| :---- | :---- | :---- | :---- | :---- | :---- |
| A-{{NNN}} | {{ASSUMPTION}} | {{EVIDENCE_GAP}} | {{CAP_IDS}} | {{HOW_TO_TEST}} | {{1 | 2 | 3}} |

# 8. Workbook References

| SECTION CONTROL: 8. WORKBOOK REFERENCES PURPOSE: Point to where the machine-readable artefacts live. This profile carries no appendices. FEEDS: No served surface. This section exists for the reader of the document. INPUTS: Both workbooks. LENGTH: 100 to 150 words. MINIMUM DATA: Both workbook filenames with revision identifiers. Every relocated artefact mapped to a named tab. MUST NOT: Reproduce any workbook content here. This section is a pointer and nothing else. FAIL IF: A tab named below is absent from the workbook, or either revision identifier is unresolved. |
| :---- |

**The handoff package and the gate attestation now live in the scoring workbook rather than in this document. The assessment stage reads them from there, so a parameter cannot be changed in prose without changing the artefact the pipeline actually consumes.**

### 8.1 Where each artefact lives

| Artefact | Workbook | Tab | Previously |
| :---- | :---- | :---- | :---- |
| Full evidence register | {{RESEARCH_WORKBOOK}} | Evidence_Register | Appendix A.1 |
| Capability coverage and confidence | {{RESEARCH_WORKBOOK}} | Coverage_Map | Appendix A.2 |
| Gate results and attestation | {{SCORING_WORKBOOK}} | Gate_Log | Appendix A.3 |
| Locked parameters | {{SCORING_WORKBOOK}} | Handoff_Lock | Appendix B.1 |
| Priority and caution capabilities | {{SCORING_WORKBOOK}} | Handoff_Lock | Appendix B.2, B.3 |
| Cap triggers | {{SCORING_WORKBOOK}} | Cap_Triggers | Appendix B.4 |
| Internal evidence request | {{RESEARCH_WORKBOOK}} | Evidence_Request | Appendix B.5 |
| Assessment metadata | {{SCORING_WORKBOOK}} | Catalogue_Meta | Appendix C.1 |
| Search log | {{RESEARCH_WORKBOOK}} | Search_Log | Appendix C.2 |
| Audit trail | {{RESEARCH_WORKBOOK}} | Audit_Trail | Appendix C.3 |
| Peer platform adoption | {{SCORING_WORKBOOK}} | Platform_Peer_Adoption | New |
| AI and data signals per subcap | {{SCORING_WORKBOOK}} | Subcap_Scores | New |
| Firmographics fields with provenance | {{RESEARCH_WORKBOOK}} | Firmographics | New (feeds O2) |
| Client priorities with page numbers | {{RESEARCH_WORKBOOK}} | Focus_Areas | New (feeds H1) |
| Served vs scored cell scoping | {{SCORING_WORKBOOK}} | Catalogue_Meta | New |

### 8.2 Handoff status

| Check | Value | Source |
| :---- | :---- | :---- |
| Gates passed | {{GATES_PASSED}} of {{GATE_COUNT}} | Gate_Log |
| Blocking failures | {{BLOCKING_FAILURES}} | Gate_Log |
| Peer set locked | {{Y | N}}, {{PEER_COUNT}} peers | Handoff_Lock |
| Evidence items | {{EVIDENCE_COUNT}} | Evidence_Register |
| Catalogue hash written to lock | {{CATALOGUE_HASH_SHORT}} | Handoff_Lock |
| Firmographics must-present set | {{N}} stated, {{N}} quarantined, 0 blank | Firmographics |
| Client priorities captured | {{N}} with page numbers | Focus_Areas |
| Cells served vs scored | {{SERVED_CELL_COUNT}} of {{SCORED_CELL_COUNT}} | Catalogue_Meta |
| Handoff status | {{READY | BLOCKED}} | Gate_Log |

###### *A handoff status of BLOCKED stops the assessment stage. Gate results are recorded in the workbook and are not restated here, so there is one copy and it is the one the pipeline reads.*

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAALkAAAAsCAYAAAA5BhmsAAAGJklEQVR4Xu2c23HbRhSGXYIekyGV4UOG5PhJJfAlGRK8jDoIS1AHVgdxB3EDMsZPSShm6A6UDpQOVIKDQ2ul5YeziwXAG6D9Zs7Y5vnPAb38SewuCL57dyAGq/Rx+Gfa4+ORSCsQgw/u028S0eiR1pEZ+8kY3ERvk15QF4k0EprbDmojkcZBU2vBmsjbpTuZbbrJ/BuDurOBZvYFayPNxzZpZzJ/ZJ7Q2GdvcprYNvNw9fkTH49Gbxc0aZFRqWVQf3JoXs3E2b8fmKcm0lxoUomL0UjdaOhMZp+ovZwunnrJ9VV3Nht1p/N/WXNSaFqfeV1G76+//EZtpFlcJvMljUuNgTqf9qT00vSCZvUZ3DBYv+6dh9ZEmsH2U/j5U5k5Gxpc6qg5OU6Dr1Pvf84Qjf62ocl74+seNSdFrlzSnM8GL1xN2+Tqo8nfDGdt8n0Z3MA+/fuwM0FT+PHXyXU2V/1D9oKzxdZH10KsKp1xssx6p9JfjsV8Vbrj2ej1eU9vmK/L2ZrcZfDMmA/U2mw1joUle0lQcygulRV+mWA/gxiZWi1+GI97rLWh3j4mH2fYfUg3md269Nnfn5jTdC58euZ80Ule99i7ycL5fH38NJ3flKp7v0qvaMZQg5vQvqA1XN0t2ZOaQ1HH5K5PHrkAQq0vfBdMqJVwPa4F+xk0k4e+MX19BZ+WOV/YJldrszOMnddgDfM7uAwuF3iotaHeZeAQzSGoY3L2Eqgx0Ulm/2V/fuXjLzGZp+wl5HRlw2EEzeRlgz0NPh1zvsiZfLp4oMbOawTracAXg/99d0utDfXbcMzbqWP+lHTHiw8hg0WNRPYmUufIl8nikVpqBGrs6I2ud+b22h61hLYG8JocW3lyxsppEv35ClV1rjOjDWtk3UCNgWdUGR9qttB8IQZ3bi06zJs9fhOiOxUcWO3FkLk1dWIk6mzy+rwhmHfpDPKiU6t9mrtMTp0NtS6DUce8gTptXAlrXP2114OaLTSeFc6Vtmth6jMudT7tseFAyScwNQJ1zkG16CTJsqiGeQntk9mGer1v3uTUEOpl54UagTrmDdSFmFxgHfMCNaqOpjMxXKVLag1VDC5Q65rSHBsOkjpQz1CXRdA2KOuK8pqGUK/V7MPkWY+v1AjUMW+grqrJu8pYU8N83nTP8X6TXlFr2JvBC/THQpuH+14EaqtG55dkZ4yZl7DzGtRrNY02uTIls/Pb6waevGo6ieEmv/VnQ32IYakNqcm9mf66c06d6sBBck1TDNRXDZnCFPW18xrUazVNNrnAWvtiFXPqgnPHRAFTB5pUwrcwFag3QZ2NfUP0zrEKtjHLwkGSoIZQXzWiycPYfh1XOU7wgrMMmck2NB01hPptFLyZBsoN0edicIE1+7oMzr4hz4d6rabpJhdYr01jXIvjUtB0/XXqbUp9LYMXnC3Kon0KcM/YRa5OWQxVQenrNI2Beq2mHSbPX+pnsKYSNB7zBufeebHB8zWe49SBA1Rm0FkbOsDbG3it4PYge4b0pV6raYPJBfZgUF+an+/TUYj5XAYv852XomPUhYNTdoC0U2VnMv+dOhttByenqfC8qNdq2mJy7cpx0XFLMVh9/hhiQGokiubS1Pv610WbplATAntIdBxzwmyBmVs4acdlXtMQ6rWatphcYB+JvczFhT7uvnd9D5xGPSeDCxygMnHIXgI1Lp0N9VpN201OTWVCvyI7sBaORYtF9vP13QccnLLBfoLvFOoKftnKQJ0ENYR6raZNJi+8+FOXUDMWGdw1b/f1rIs2TSkb7GmQF4xaLUrf7Os5poF6raZNJmcfLt5rQ0P2PUZ2kbuKeQSDH5PvFy5mt5dT+e767Fb+TU2kOjQ587UZKHvY1Phou8Ejh4UG39uCk9CcEtptbsR1t1E0eCQUmpz5vTFY57cSi4wuNzVTHw0eKYP2M3PU7BUa1YT2g/vR4JF9cFSDG2hYzej9f758YF6iaO88ErHRdsaoORg0rwnJOQ1eYUcm8rbpfv/lg5dw3TB+MGhiX0SDRxqL6wf3o8EjrWLg+B3yrcE9N0RHIo1CM/rwPh1RF4k0Gvt3yH13/EcijUaMXnTHfyRyDP4HnqN3NbY32TcAAAAASUVORK5CYII=>