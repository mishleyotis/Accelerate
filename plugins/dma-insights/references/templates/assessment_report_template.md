<!-- TEMPLATE OF RECORD: Digital Maturity Assessment Report
     Google Doc id 1FPr7wNuo2-Fk7PPTvk1VkQxYBvjLbEWwU7kZQY8TuDA (open it from Drive by id; the engine reads it through
     drive_fetch.py under the service-account identity, never from a shell).
     Exported 2026-09-03 as markdown. READ-ONLY copy: the engine's report spec
     (engine/report_spec.py) is built from report_templates.json beside this file,
     and tests assert the two agree. Re-pin with `engine.template pin` when the
     owner changes the Doc. -->

  
  
  
  

|  |
| :-: |
| **DMA Assessment Report**{{ENTITY_NAME}} |

  

|  |  |
| :-: | :-: |
| **OVERALL MATURITY**{{OVERALL_SCORE}} of {{SCALE_MAX}} ({{LEVEL}}) | **SUB-VERTICAL**{{SUBVERTICAL_NAME}} |
| **ASSESSMENT ID**{{ASSESSMENT_ID}} | **ASSESSMENT DATE**{{DATE}} |
| **EVIDENCE MODE**{{EVIDENCE_MODE}} | **CATALOGUE**{{CATALOGUE_VERSION}} ({{CATALOGUE_HASH_SHORT}}) |
| **PREPARED BY**Zennify Digital Maturity Assessment |   |

  

# Contents

  

###### *Select all (Ctrl+A) then press F9 in Word to populate page numbers after the template is filled.*

# Document Control and Catalogue Binding

*Every value in this section is resolved at render time. Nothing here is typed by hand. If any field resolves to UNRESOLVED, the render fails and the report is not issued.*

  

### Resolved catalogue binding

|  |  |  |
| :-: | :-: | :-: |
| **Field** | **Token** | **Resolution source** |
| **Catalogue version** | {{CATALOGUE_VERSION}} | Catalogue_Meta!version |
| Catalogue content hash | {{CATALOGUE_HASH}} | SHA-256 over the catalogue rows, computed at load |
| Catalogue resolved at | {{CATALOGUE_RESOLVED_AT}} | Render timestamp, UTC |
| Resolution path taken | {{CATALOGUE_SOURCE}} | One of: WORKBOOK_META, CATALOGUE_MANIFEST, CONNECTOR |
| **Structure counts** | {{PILLAR_COUNT}} pillars / {{CATEGORY_COUNT}} categories / {{CAPABILITY_COUNT}} capabilities / {{SUBCAP_COUNT}} subcapabilities | Counted from Catalogue_Meta, never asserted |
| Sub-vertical | {{SUBVERTICAL_NAME}} ({{SUBVERTICAL_ID}}) | Handoff_Lock!subvertical_id |
| Pillar weight set | {{WEIGHT_SET_ID}} v{{WEIGHT_SET_VERSION}} | Pillar_Weights!weight_set_id |
| Maturity scale | {{SCALE_MIN}} to {{SCALE_MAX}} ({{SCALE_LEVEL_COUNT}} levels) | Maturity_Rubric, counted |
| Evidence tier scheme | {{TIER_COUNT}} tiers, {{TIER_SCHEME_ID}} | Catalogue_Meta!tier_scheme |
| Solution catalogue | {{SOLUTION_CATALOGUE_VERSION}} ({{SOLUTION_COUNT}} solutions) | Solution_Catalogue, counted |
| Scoring workbook | {{SCORING_WORKBOOK}} rev {{SCORING_WORKBOOK_REV}} | File metadata |
| Research workbook | {{RESEARCH_WORKBOOK}} rev {{RESEARCH_WORKBOOK_REV}} | File metadata |
| Gate set | {{GATE_COUNT}} gates, {{GATE_SET_ID}} | Gate_Log, counted |

  

|  |
| :-: |
| **RESOLUTION RULE****ORDER:** Try Catalogue_Meta in the scoring workbook first. If absent or stale, read the catalogue manifest shipped with the plugin. If that is unreachable, call the DMA Insights connector for the active catalogue. Record which path succeeded in {{CATALOGUE_SOURCE}}.**COUNTS:** Pillar, category, capability, subcapability, tier, solution and gate counts are derived by counting catalogue rows at render time. Do not carry a count forward from a previous report and do not write a count into prose anywhere in this document.**DRIFT CHECK:** Compare {{CATALOGUE_HASH}} against the hash recorded in the scoring workbook when scores were written. A mismatch means the catalogue changed after scoring.**FAIL IF:** All three resolution paths fail; the hash comparison mismatches; any structure count resolves to zero; or the weight set referenced by the workbook is absent from the catalogue. |

  

### How to read the section controls

Each section opens with a control block. LENGTH gives a word band for the narrative in that section, excluding table content. The lower bound is a blocking gate, so a section under its minimum is treated as incomplete. The upper bound is advisory and exists to keep the report readable. MINIMUM DATA lists the counts a section must carry before it is considered valuable. FAIL IF lists the conditions that block issue of the report.

|  |  |  |
| :-: | :-: | :-: |
| **Total narrative budget** | **Minimum** | **Maximum** |
| All sections, excluding tables and this control page | {{REPORT_WORD_MIN}} words | {{REPORT_WORD_MAX}} words |

###### *Budget tokens are computed by summing the per-section minimums and maximums at render time, so editing a single section control updates the total automatically.*

# Surface Alignment

*This report is one input to the DMA Insights app. Each section below feeds named app surfaces, and the app is the authority for anything marked as owned there. Producing a section without knowing what it feeds is how a report and a dashboard end up disagreeing under the same client name.*

|  |  |  |
| :-: | :-: | :-: |
| **Section** | **Feeds app surface** | **Dashboard** |
| 1\. Executive Summary | O4 exec summary (challenged, never copied), O6 top findings | D1 |
| 2\. Assessment Methodology | No served surface; internal | n/a |
| 3\. Issue Impact and Cap Analysis | O1b capability ceilings, H5 safeguard gates | D1, D7 |
| 4\. Assessment Results | O1 scores and peer benchmarks, H4 workbook grain scores | D1, D3 |
| 5\. Pillar Deep Dives | H4 grain scores, H2 cell evidence, T1 and T2 tech stack, P1 platform fit | D3, D2, D4, D6 |
| 6\. Benchmark and Technology Estate | O1 peer benchmarks, T1 register, T3 platform detail | D1, D6 |
| 7\. Gap Prioritisation | O5 opportunity tiles, O6 findings, H1 focus areas | D1, D3 |
| 8\. Recommendations | P2 recommendations, P1 platform fit and story, T3 platform detail | D4, D6 |
| 9\. Transformation Roadmap | P3 roadmap, P4 stair-step curve | D4 |
| 10\. Data Gaps and Confidence | H3 thin-evidence alerts, H7 evidence age tracker | D7 |
| 11\. Workbook Traceability | H6 evidence store, H2 cell evidence | D3 |

### What this report does not repeat

*The research below was done once and is recorded once. This report cites it and does not restate it, so a figure that appears in both documents cannot drift between them.*

|  |  |  |
| :-: | :-: | :-: |
| **Content** | **Lives in** | **Why it is not here** |
| Firmographics, charter, regulator, scale | Client Profile section 1 | The identity anchor is established once, before any scoring |
| Financial trajectory and CAGR | Client Profile section 4.2 | A series the assessment reads rather than produces |
| Digital evolution timeline | Client Profile section 4.3 | Historical context, established before scoring begins |
| Sentiment ratings and trends | Client Profile section 4.4 | Captured at research; the assessment reads the effect on scores |
| The peer set and why each peer was chosen | Client Profile section 4.1 | Locked at research and immutable. Only the scores are added here |
| Insight cards, leadership, thought leadership | Client Profile section 5 | Research findings, not assessment findings |
| Client priorities in the client's own words | Client Profile section 6 | Verbatim quotes with page numbers belong to one document |
| The issue register itself | Client Profile section 7.1 | This report carries only what each issue cost in score terms |
| Evidence excerpts, ERS, search effort | Workbook | One row per fact, machine read. Section 11 says how to look one up |

  

|  |
| :-: |
| **STANDING CLAUSES CARRIED FROM THE APP****VARIANT CELLS:** The workbook scores every cell in the catalogue, including variant cells minted for other sub-verticals. A variant cell names its owner in its terminal segment. Never cite a cell whose code names exactly one sub-vertical that is not {{SUBVERTICAL_ID}}: it resolves in the workbook and renders nowhere, so the citation opens onto nothing.**SERVED CELL SET:** Every count, every mean and every gap in this report is computed over the cells this run serves ({{SERVED_CELL_COUNT}}), not the cells the workbook scores ({{SCORED_CELL_COUNT}}). Two denominators produce a contradiction a reader can find by counting.**GRAIN:** A score compared against a peer figure must be built from the same cell set at the same grain. A figure assembled from a different set is a grain violation even when both numbers are correct.**IDENTITY:** Every figure asserts this legal entity by name, regulator and footprint. A parent, a subsidiary or a same-name institution is contamination, and the figure is withheld with a stated reason rather than rendered.**EVIDENCE COVERAGE:** Not carried in this report. Coverage, tier distribution and self-sourced share are O10 and O11, they are internal instrumentation, and the app does not serve them to clients. |

# 1. Executive Summary

|  |
| :-: |
| **SECTION CONTROL: 1. EXECUTIVE SUMMARY****PURPOSE:** Give a client executive the verdict, the three patterns that define this institution, and the trajectory that closes the gap, in a single read.**FEEDS:** O4 exec summary and O6 top findings. The app treats this section as an input to challenge, never as text to copy, so write it to be argued with.**INPUTS:** Scoring workbook: Pillar_Rollup, Category_Rollup, Peer_Benchmarks, Subcap_Scores. Research workbook: Evidence_Register.**LENGTH:** 600 to 900 words across SCQA, strengths and development areas. Minimum is blocking.**MINIMUM DATA:** 7 unique E-IDs. 3 to 5 strength rows. 3 to 5 development rows. Every pillar row populated with score, peer median, gap, level and finding. At least one finding drawn from the AI and data overlay.**MUST INCLUDE:** The numeric overall score and its level. The gap to peer median in points. A named trajectory with a phase count and the condition that gates the second horizon. A cross-reference to at least three REC identifiers.**MUST NOT:** Carry any claim without an E-ID. Recommend an appointment, committee or centre of excellence unless proxy evidence confirms the gap exists.**FAIL IF:** Swapping the entity name and the numbers would leave the summary true for a different institution. |

  

|  |
| :-: |
| **PRE-WRITE PROTOCOL****1 ANALYSE:** Load all evidence mapped to scored subcapabilities. Count unique E-IDs. Identify the five strongest and five weakest capabilities by gap to peer median.**2 SYNTHESISE:** Cross-reference against Peer_Benchmarks. Name the three patterns that define this institution. State what story the data tells before writing a sentence of prose.**3 WRITE:** Write to the SCQA scaffold below. Every sentence traces to evidence.**4 VALIDATE:** Re-read against the FAIL IF condition. Rewrite anything that survives an entity swap. |

  

### 1.1 SCQA context

*Situation, Complication, Question, Answer. Each element cites evidence. The Answer carries a maturity trajectory with phased initiatives.*

Situation: {{ENTITY_NAME}} is a {{PRIMARY_METRIC}} {{SUBVERTICAL_NAME}} serving {{CUSTOMER_COUNT}} across {{GEOGRAPHY}} [{{E_ID}}, Tier {{TIER}}]. {{KEY_FINANCIAL_METRIC}} shows {{TREND}} [{{E_ID}}, Tier {{TIER}}].

Complication: Despite strength in {{TOP_CAPABILITIES}}, {{ENTITY_NAME}} trails in {{WEAK_CAPABILITIES}}. {{SPECIFIC_ISSUE}} [{{E_ID}}]. The overall score of {{OVERALL_SCORE}} places {{ENTITY_NAME}} at {{LEVEL}}, {{GAP_POINTS}} points from {{PEER_MEDIAN}}.

Question: How can {{ENTITY_NAME}} {{STRATEGIC_QUESTION}} while using existing strength in {{STRENGTHS}} to close the maturity gap?

Answer: A {{PHASE_COUNT}} phase sequence leading with {{TOP_3_INITIATIVES}} advances {{ENTITY_NAME}} from {{CURRENT_SCORE}} to {{TARGET_SCORE}}, closing {{CRITICAL_GAP_COUNT}} critical gaps. The first horizon carries {{PHASE_1_RECS}}; what follows is gated on {{GATING_CONDITION}}. See {{REC_REFS}}.

###### *State the sequence and what gates it. Do not state a duration: the app carries a horizon and a dependency chain and has no field for elapsed time, so a month count written here has nowhere to render and will contradict the roadmap.*

### 1.2 Key strengths

###### *3 to 5 rows. Each row carries a capability id, a score, the delta to peer median, and the E-ID that supports it.*

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Capability** | **Score** | **vs peer median** | **Evidence** | **Why it is a strength here** |
| {{CAP_ID}} {{CAP_NAME}} | {{SCORE}} | {{DELTA}} | {{E_ID}} | {{RATIONALE}} |

###### *Rows generated from Category_Rollup filtered to positive delta, ordered by delta descending.*

### 1.3 Critical development areas

###### *3 to 5 rows. Each row carries the gap to peer median, the named Zennify solution, and the REC that addresses it.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Capability** | **Score** | **Gap to peer** | **Evidence** | **Zennify solution** | **REC** |
| {{CAP_ID}} {{CAP_NAME}} | {{SCORE}} | {{GAP}} | {{E_ID}} | {{SOLUTION_NAME}} | {{REC_ID}} |

### 1.4 Assessment by pillar

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Pillar** | **Score** | **Peer median** | **Gap** | **Level** | **Key finding** |
| {{PILLAR_ID}}: {{PILLAR_NAME}} | {{SCORE}} | {{MEDIAN}} | {{GAP}} | {{LEVEL}} | {{FINDING}} |

###### *One row per pillar, generated by iterating Pillar_Rollup. Row count equals {{PILLAR_COUNT}}. Pillar names come from the catalogue, so a catalogue change reshapes this table without an edit here.*

# 2. Assessment Methodology

|  |
| :-: |
| **SECTION CONTROL: 2. METHODOLOGY****PURPOSE:** Let a sceptical reader reconstruct how the scores were produced.**FEEDS:** No served surface. This section exists for the reader of the document, not the app.**INPUTS:** Scoring workbook: Catalogue_Meta, Pillar_Weights, Maturity_Rubric, Peer_Benchmarks.**LENGTH:** 300 to 450 words. One page.**MINIMUM DATA:** Resolved structure counts. Scale bounds. Tier count and the weighting applied to each tier. Peer set size and the basis on which it was locked. Weight set identifier.**MUST INCLUDE:** A statement that structure counts are resolved from the catalogue at render time, quoting {{CATALOGUE_VERSION}} and {{CATALOGUE_HASH}}.**MUST NOT:** Restate the maturity rubric or the capability definitions. Both live in the scoring workbook and are referenced, not copied.**FAIL IF:** Any structure count in the prose is written as a literal rather than a token. |

{{METHODOLOGY_NARRATIVE}}

|  |  |  |
| :-: | :-: | :-: |
| **Element** | **Applied in this assessment** | **Defined in** |
| Framework structure | {{PILLAR_COUNT}} pillars, {{CATEGORY_COUNT}} categories, {{CAPABILITY_COUNT}} capabilities, {{SUBCAP_COUNT}} subcapabilities | Catalogue_Meta |
| Scoring scale | {{SCALE_MIN}} to {{SCALE_MAX}} | Maturity_Rubric |
| Evidence tiers | {{TIER_COUNT}} tiers, scheme {{TIER_SCHEME_ID}} | Evidence_Register |
| Pillar weighting | {{WEIGHT_SET_ID}}, weights sum to 1.00 | Pillar_Weights |
| Peer set | {{PEER_COUNT}} peers, locked at research phase | Handoff_Lock |
| Cap rules | {{CAP_RULE_COUNT}} triggers active | Cap_Triggers |

# 3. Issue Impact and Cap Analysis

|  |
| :-: |
| **SECTION CONTROL: 3. ISSUE IMPACT AND CAP ANALYSIS****PURPOSE:** Show what the live issues cost in score terms, which capabilities carry the cost, when each cap lifts, and what the overall score would be without them. The issues themselves and their narrative are in Client Profile section 7.1 and are not restated here.**FEEDS:** O1b capability ceilings and H5 safeguard gates. O1b needs the ceiling and the reason together; a ceiling with no reason renders as a bare number the client cannot argue with.**INPUTS:** Scoring workbook: Issue_Register, Cap_Triggers, Subcap_Scores, Caps_Applied_Log. Client Profile section 7.1.**LENGTH:** 400 to 700 words.**MINIMUM DATA:** Every capped capability with its uncapped score, the rule that fired, the reported score and the points withheld. A lift condition for every cap. The aggregate withheld and the uncapped overall. Every cap traced to a dated matter.**MUST INCLUDE:** The severity to cap mapping in force, read from Cap_Triggers rather than restated from memory, and the rule id that fired on each row.**MUST NOT:** Restate the issue register. Only capabilities whose score was actually constrained appear here, each naming the issue by id. Present a cap as permanent when the rule that set it carries a horizon.**FAIL IF:** A cap is applied in Subcap_Scores and does not appear here, a cap has no lift condition, or the aggregate withheld does not reconcile against the row sum. |

### 3.1 Capped capabilities

###### *Makes the cost of each issue concrete. The uncapped score is the score the evidence alone would support, so the difference between the two columns is what the issue is costing the institution in this assessment. Severity to cap mapping is read from Cap_Triggers at render time, so a change to the rule set propagates without editing this template; {{CAP_RULE_COUNT}} rules are active for {{SUBVERTICAL_NAME}}.*

|  |  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| **Capability** | **Uncapped** | **Rule** | **Cap** | **Reported** | **Withheld** | **Driving issue** |
| {{CAP_ID}} {{CAP_NAME}} | {{UNCAPPED}} | {{RULE_ID}} | {{CAP_VALUE}} | {{REPORTED}} | {{DELTA}} | {{ISSUE_ID}} |

###### *One row per constrained capability, ordered by points withheld. A capability whose evidence alone would not reach the cap is not constrained by it and does not belong here, even where the issue touches it.*

### 3.2 When each cap lifts

###### *A cap is a statement about a moment, not a verdict on the institution. Most rules carry a horizon: a matter that caps a capability today stops capping it once it ages past the rule's window or the remediation closes. Saying so turns a finding the client will resist into a date they can work towards.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Rule** | **Applies while** | **Lifts when** | **Expected lift date** | **Capability released** | **Score on lift** |
| {{RULE_ID}} | {{CONDITION}} | {{LIFT_CONDITION}} | {{DATE_OR_UNDETERMINED}} | {{CAP_ID}} | {{SCORE_AFTER_LIFT}} |

###### *Where a rule has no horizon, write UNDETERMINED rather than a guess, and say what would have to change. A cap presented as permanent when the rule that set it expires is the error most likely to be found by the client rather than by us.*

### 3.3 Aggregate effect

###### *What the caps cost the assessment as a whole. This is the figure an executive asks for first, and the one most likely to be reconstructed by hand from the table above, so the two must agree.*

|  |  |  |
| :-: | :-: | :-: |
| **Measure** | **Value** | **Basis** |
| **Capabilities constrained** | {{N}} of {{CAPABILITY_COUNT}} | Rows in the table above |
| **Total points withheld** | {{SUM_WITHHELD}} | Sum of the withheld column, reconciled at render |
| **Reported overall score** | {{OVERALL_SCORE}} | The headline figure, caps applied |
| **Uncapped overall score** | {{UNCAPPED_OVERALL}} | The same weighting with no cap applied |
| **Difference** | {{DELTA_OVERALL}} | What the live issues cost at the overall level |
| **Caps with a lift date inside 12 months** | {{N}} | From the lift table |
| **Caps with no determined horizon** | {{N}} | Each one needs a stated remediation condition |

###### *The uncapped overall is stated for contrast and is never the score. It is what the evidence would have supported had nothing been outstanding, which is a different claim from what the institution has achieved.*

# 4. Assessment Results

|  |
| :-: |
| **SECTION CONTROL: 4. ASSESSMENT RESULTS****PURPOSE:** Present the scorecard and show the arithmetic that produced the overall score.**FEEDS:** O1 scores and peer benchmarks, H4 workbook grain scores. H4 requires a source cell against every score.**INPUTS:** Scoring workbook: Pillar_Rollup, Category_Rollup, Pillar_Weights, Peer_Benchmarks.**LENGTH:** 350 to 600 words.**MINIMUM DATA:** Overall score with the weighted calculation written out. Every category in the catalogue present as a row, with score, peer median, gap and status. No category omitted, including those scored on thin evidence.**MUST INCLUDE:** The weight applied to each pillar and a check that the weights sum to 1.00.**MUST NOT:** Hardcode a category list. Rows are generated by iterating the catalogue.**FAIL IF:** The category row count is not equal to {{CATEGORY_COUNT}}, or the recomputed weighted score differs from {{OVERALL_SCORE}} by more than 0.01. |

### 4.1 Overall score

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Pillar** | **Score** | **Weight** | **Weighted contribution** | **Peer median** |
| {{PILLAR_ID}}: {{PILLAR_NAME}} | {{SCORE}} | {{WEIGHT}} | {{SCORE_X_WEIGHT}} | {{MEDIAN}} |
| **Total** | **{{OVERALL_SCORE}}** | **1.00** | **{{OVERALL_SCORE}}** | **{{PEER_MEDIAN_OVERALL}}** |

###### *Generated from Pillar_Rollup joined to Pillar_Weights. The total row is recomputed at render and compared against the workbook value; a variance above 0.01 blocks the render.*

### 4.2 Category scores and gaps

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Category** | **Score** | **Peer median** | **Gap** | **Status** | **Key evidence** |
| {{CATEGORY_ID}} {{CATEGORY_NAME}} | {{SCORE}} | {{MEDIAN}} | {{GAP}} | {{STATUS}} | {{E_IDS}} |

###### *One row per category, iterated from the catalogue. Row count equals {{CATEGORY_COUNT}}. Adding or renaming a category in the catalogue changes this table with no edit to the template.*

# 5. Pillar Deep Dives

*This section repeats once per pillar. The block below is the pattern; the render iterates Pillar_Rollup and produces {{PILLAR_COUNT}} instances of it.*

|  |
| :-: |
| **SECTION CONTROL: 5. PILLAR DEEP DIVE, PER PILLAR****PURPOSE:** Separate what the evidence shows from what it means, and expose the AI and data position that sits underneath both.**FEEDS:** H4 grain scores, H2 cell evidence, T1 and T2 tech stack, P1 platform fit. The AI and data overlay is what T1 and P1 read for readiness.**INPUTS:** Scoring workbook: Subcap_Scores (including the AI and data columns), Category_Rollup, Peer_Benchmarks, Platform_Peer_Adoption. Research workbook: Evidence_Register, Technographic_Scan.**LENGTH:** What We See 350 to 550 words. AI and Data Overlay 150 to 250 words. Why It Matters 300 to 450 words. Applies to every pillar.**MINIMUM DATA:** 5 or more unique E-IDs per pillar. The 3 strongest and 3 weakest capabilities named with scores and peer deltas. All 6 overlay rows populated, with UNKNOWN written explicitly where evidence is absent. At least 1 REC cross-reference.**MUST INCLUDE:** Named technologies, named leaders, named programmes and numeric metrics. Every capability discussed cites a subcapability score.**MUST NOT:** Infer in What We See. Introduce new facts in Why It Matters. Leave an overlay row blank rather than writing UNKNOWN.**FAIL IF:** A sentence would survive substitution of a different institution. 'The institution should improve analytics' fails. '{{CAP_ID}} scores 1.75 against a peer median of 2.00 because [{{E_ID}}] shows dashboarding with no model deployment' passes. |

  

## **5.N {{PILLAR_ID}}: {{PILLAR_NAME}}, score {{SCORE}} against median {{MEDIAN}} ({{GAP}})**

### Capability scorecard

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Capability** | **Score** | **Peer median** | **Gap** | **Evidence count** | **Lowest tier relied on** |
| {{CAP_ID}} {{CAP_NAME}} | {{SCORE}} | {{MEDIAN}} | {{GAP}} | {{E_COUNT}} | {{TIER}} |

### What we see

###### *Factual. Describe what the evidence shows. Cite every claim.*

{{PILLAR_WHAT_WE_SEE_NARRATIVE}}

### AI and data overlay

###### *Present in every pillar, not only the data and technology pillar. Per-subcapability detail lives in Subcap_Scores; this table is the pillar-level roll-up of it.*

|  |  |  |  |
| :-: | :-: | :-: | :-: |
| **Dimension** | **Finding for this pillar** | **Evidence** | **Workbook column** |
| **Data dependency** | {{DATA_DOMAINS_REQUIRED}} | {{E_IDS}} | Subcap_Scores!data_dependency |
| **Data readiness** | {{RED | AMBER | GREEN}} because {{REASON}} | {{E_IDS}} | Subcap_Scores!data_readiness |
| **AI footprint today** | {{DEPLOYED_AI_OR_NONE}} | {{E_IDS}} | Subcap_Scores!ai_evidence_ids |
| **AI-addressable subcaps** | {{N}} of {{PILLAR_SUBCAP_COUNT}}, led by {{TOP_3_SUBCAPS}} | n/a | Subcap_Scores!ai_applicability |
| **Blocking constraint** | {{WHAT_PREVENTS_AI_ADOPTION_HERE}} | {{E_IDS}} | Subcap_Scores!ai_blocker |
| **Peer AI posture** | {{WHAT_PEERS_DO_IN_THIS_PILLAR}} | {{E_IDS_OR_SCAN}} | Peer_Benchmarks!ai_posture |

{{PILLAR_AI_DATA_NARRATIVE}}

#### **Required Subcap_Scores columns for the overlay**

|  |  |  |
| :-: | :-: | :-: |
| **Column** | **Allowed values** | **Purpose** |
| ai_applicability | NONE, ASSISTIVE, AUGMENTED, AUTONOMOUS | How far AI can carry this subcapability |
| data_dependency | Comma-separated data domains | What the subcapability consumes |
| data_readiness | RED, AMBER, GREEN | Whether that data is fit to use today |
| ai_evidence_ids | E-IDs, or NONE_FOUND | What is deployed today |
| ai_blocker | Free text, or NONE | The constraint that must clear first |
| peer_ai_signal | E-ID, SCAN, or UNVERIFIED | Peer position and where it came from |

###### *These six columns are the contract between the workbook and this section. A pillar cannot render its overlay if they are absent.*

### Why it matters

###### *Analytical. Business impact for this institution, competitive position, cross-pillar dependency, and risk if unaddressed. Reference the RECs that close the gaps.*

{{PILLAR_WHY_IT_MATTERS_NARRATIVE}}

# 6. Benchmark and Technology Estate

|  |
| :-: |
| **SECTION CONTROL: 6. BENCHMARK AND TECHNOLOGY ESTATE****PURPOSE:** Place the institution against the peer set locked during research, then do the same for the technology it actually runs: what each product does here, where it stops, and who else in the cohort runs it.**FEEDS:** O1 peer benchmarks, T1 technology stack register, T3 platform detail, T2 landscape strip. T3 renders one sub-page per register row, so a product with nothing written against it renders its linked cells and says nothing more.**INPUTS:** Scoring workbook: Peer_Benchmarks, Platform_Peer_Adoption, Subcap_Scores, Handoff_Lock. Research workbook: Technographic_Scan, Tech_Landscape, Evidence_Register. Vendor scope documentation, fetched and registered.**LENGTH:** 700 to 1100 words of narrative, excluding tables.**MINIMUM DATA:** {{PEER_COUNT}} peers, between 3 and 5, each with an overall score. Position stated for every pillar. Every register row significant enough that a reader would ask who else runs this carries a peer breakdown. Every ABSENT row carries one too: a peer comparison on an absence is the most valuable comparison on the page.**MUST INCLUDE:** The vendor's own scope statement, fetched and cited, before any boundary claim is written. That fetch is the difference between a boundary and an opinion, and it is usually one page.**MUST NOT:** Introduce a peer that was not locked at research. Derive or project a score for any product. Assign fault to a vendor. Assert a limitation the vendor's own documentation contradicts.**FAIL IF:** The peer list differs from Handoff_Lock, a coverage share has no breakdown behind it, a deployed row has no source or no date, or a share disagrees with its own breakdown by more than one peer. |

### 6.1 Peer scores

###### *The peer set, its selection rationale and each peer's profile are in Client Profile section 4.1 and are not restated. This table carries only what the assessment adds: the scores.*

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Peer** | **Overall** | **Strongest pillar** | **Weakest pillar** | **AI and data posture** |
| {{PEER_NAME}} | {{SCORE}} | {{PILLAR}} | {{PILLAR}} | {{AI_POSTURE}} |

### 6.2 Strategic positioning

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Pillar** | **Entity** | **Peer median** | **Peer best** | **Position** | **Rank** |
| {{PILLAR_ID}}: {{PILLAR_NAME}} | {{SCORE}} | {{MEDIAN}} | {{BEST}} | {{ABOVE | AT | BELOW}} | {{RANK}} of {{PEER_COUNT_PLUS_1}} |

###### *Below the median and below every individual peer are different findings. Where the entity sits under all of them, say so: it is the sharper claim and it changes the conversation.*

### 6.3 Lead competitor

###### *Deep dive on the highest scoring peer, category by category. What they do differently, not merely that they score higher.*

{{LEAD_COMPETITOR_ANALYSIS}}

## **6.4 Technology estate**

###### *The register itself lives in the research workbook and in Client Profile section 5.2. This section carries what the assessment adds to it: what each product does to the assessed gaps, where it stops, what AI it makes possible, and who else in the cohort runs it.*

#### **Register reference and layer rollup**

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Layer** | **Covers** | **Pillar** | **Detected** | **Expected** | **Primary gap** |
| OPS | Operations and core banking | {{P3_ID}} | {{N}} | {{N}} | {{Y | N}} |
| CUST | Customer engagement | {{P2_ID}} | {{N}} | {{N}} | {{Y | N}} |
| DATA | Data and analytics | {{P4_ID}} | {{N}} | {{N}} | {{Y | N}} |
| INFRA | Infrastructure and cloud | {{P4_ID}} | {{N}} | {{N}} | {{Y | N}} |

###### *Four layers, spelled exactly as above. Do not use level codes here: they collide with the evidence levels carried on the same card. Detected against expected is what makes a layer a primary gap rather than merely a short list.*

#### **Register row shape**

###### *Each row is one product, and vendor and product are separate fields. A service or a category is not a product. Status is required on every row because the landscape strip recomputes its counts from it, and a row without a status makes the strip uncomputable.*

|  |  |  |
| :-: | :-: | :-: |
| **Field** | **Value** | **Rule** |
| ts_id | {{TS_ID}} | Stable across runs so a row can be compared to itself |
| vendor / product | {{VENDOR}} / {{PRODUCT}} | Two fields. Never a category name in either |
| layer | {{OPS | CUST | DATA | INFRA}} | One of four, exactly |
| status | {{CONFIRMED | INFERRED | CLAIMED | ABSENT}} | Required on every row |
| evidence_level | {{L1 | L2 | L3 | L4}} | Governs which verb the prose may use about this product |
| detection_basis | {{ONE_CLAUSE}} | One clause under 160 characters. It renders as a single muted line, so everything else belongs in the impact card |
| as_of | {{DATE}} | The date the detection was established, not the date it was read |
| linked_subcap_ids | {{CELL_IDS}} | Cells this run serves. The estate reach card is computed from what is absent from this list |

#### **What each product does to the assessed gaps**

###### *40 to 90 words per product, in four moves and in this order. Miss one and the card becomes commentary on a score the reader can already see beside it.*

|  |  |  |
| :-: | :-: | :-: |
| **Move** | **What to write** | **Cited to** |
| **1. Deployed capability** | What this product does in THIS estate, at the edition and scope actually run. Not the vendor catalogue, the deployed thing. | Vendor documentation for that edition, a client statement, a job posting naming the module, or a case study naming the deployment |
| **2. Cells it reaches** | Name the cells, or the capability they share, and say what about the product reaches them. | The linked cell list; read the served scores to choose which cells earn the words, and never print a score back |
| **3. Documented boundary** | Where this product stops, taken from the product's own documentation. This is the move the register cannot make for you and the reason the card exists. | The vendor's own scope statement, fetched and registered before the boundary is written |
| **4. Zennify pathway** | The integration or implementation work that carries the estate from that boundary to the capability the assessment says is missing. | Moves 2 and 3. A service line that does not follow from them reads as a service line bolted on |

  

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Product** | **Status** | **Impact on assessed gaps (40 to 90 words, four moves)** | **Cells** | **Evidence** |
| {{VENDOR}} {{PRODUCT}} | {{STATUS}} | {{FOUR_MOVE_PARAGRAPH}} | {{CELL_IDS}} | {{E_IDS}} |

  

|  |
| :-: |
| **FOUR THINGS THAT HAVE SHIPPED AND MUST NOT****NEVER DERIVE A SCORE:** Scores come from the workbook. No source states a post-investment target, so there is no target to state and none may be projected.**NEVER RESTATE WHAT IS SERVED:** If the paragraph still reads sensibly with the product name swapped for a cell id, it is score commentary rather than an impact statement.**NEVER CONTRADICT THE VENDOR:** The boundary is the most quotable sentence here and the one most likely to be read back by the vendor's account team. Where the documentation says the product does the thing, the finding is that the estate has not configured it, which is a different sentence with a different owner and needs its own evidence.**NEVER ASSIGN FAULT:** Write available value, not failure. The estate does not yet reach the member profile, rather than the vendor does not support member profiles. The reader is often the person who chose the incumbent, and a sentence about vendor failure invites a defence of the vendor instead of a conversation about the gap. |

#### **AI overlay on the estate**

###### *Applies the section 5 overlay at product grain. An AI capability is a property of a deployed product at its configured scope, so a claim here needs the same edition-level citation the impact card needs.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Product** | **AI available at this edition** | **In use here** | **Data it depends on** | **What blocks it** | **Evidence** |
| {{PRODUCT}} | {{VENDOR_DOCUMENTED_CAPABILITY}} | {{YES | NO | UNKNOWN}} | {{DATA_DOMAINS}} | {{BLOCKER_OR_NONE}} | {{E_ID}} |

###### *A product whose AI features exist at a higher edition than the one deployed is a licensing finding, not a capability gap, and it carries a different recommendation. Say which it is.*

#### **Estate reach, and its two permitted inputs**

###### *This is the card most likely to be written from feel, because everyone in the room has an opinion about what a core cannot do. It has exactly two inputs and a claim from neither does not go on the page.*

|  |  |  |
| :-: | :-: | :-: |
| **Input** | **What it is** | **Who computes it** |
| **1. Register arithmetic** | The cells in this product's own pillar that the register does not link to it, lowest score first | The surface computes it from the linked cell list. Do not contradict it; if the product reaches a cell on that list, add the cell to the linked list with evidence |
| **2. Documented boundary** | The vendor's own statement of what the product is for | You, from the vendor's scope page, registered as evidence and cited on the row |

  

|  |  |
| :-: | :-: |
| **Not a valid input** | **Why not** |
| The product's age | Legacy is not a capability boundary, and a detected old build establishes presence rather than exposure |
| No public case study | A vendor whose site has no example of the thing has not said the product cannot do the thing |
| The gap you would like to sell | If the pathway came first and the boundary was written to justify it, the boundary is the wrong way round |

## **6.5 Peer deployment**

###### *A technographic claim about a named institution is a research finding and carries a research finding's burden. Run this for the core, the digital channel, the CRM estate, the integration layer, and every ABSENT row. Ask what each peer runs at this layer rather than whether each peer runs this product: a peer on a different product at the same layer is a stronger finding than an unknown.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Product** | **Peer** | **Verdict** | **Basis** | **Source** | **As at** |
| {{PRODUCT}} | {{PEER_NAME}} | {{DEPLOYED | NOT FOUND | NOT ESTABLISHED}} | {{BASIS}} | {{URL}} | {{DATE}} |

###### *One row per named peer, including the peers that could not be established. Two of five deployed with three unknown is not forty per cent adoption, and the card can only say so when the unknowns are listed. Where the peer set has no public technographic footprint at all, omit the coverage share entirely: every row unresolved still renders, and it renders the truth.*

#### **What establishes a deployment**

###### *In descending order. The first class that lands is the one to cite.*

|  |  |
| :-: | :-: |
| **Evidence class** | **Verdict it supports** |
| The vendor names the institution | Deployed |
| The institution names the vendor, in its own newsroom or annual report | Deployed |
| An implementation partner names both the client and the product | Deployed |
| A partner names the client but not the product edition | Not established. The platform is established; the product is not |
| The peer is named on a competing product at the same layer | Not found, with that source. This is a strong finding, not a weak one |
| A careers posting naming the system, dated and the peer's own | Deployed |
| A vendor aggregate claim naming no institution | Not established for every peer. A share cannot be distributed across named peers |
| A vendor release naming an institution outside this peer set | Nothing at all. It does not touch this cohort |

#### **Recording an absence, and recording age**

|  |  |
| :-: | :-: |
| **Situation** | **What the basis must say** |
| Nothing found | What was searched, in the peer's own terms. Name the vendor release pages and the institution's own newsroom that were checked |
| Never write | Not researched. That describes the producer rather than the world |
| Never write | A bare not found with no source, which asserts an absence nobody established |
| The source is old | State the date and say the reading is uncontradicted rather than current. A twenty-year-old conversion release is real evidence and it is twenty years old |
| Two sources disagree | Both go in the basis. Never average them and never quietly prefer the newer one |

#### **Coverage share**

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Product** | **Deployed** | **Not found** | **Not established** | **Coverage share** | **Peers searched** |
| {{PRODUCT}} | {{N}} | {{N}} | {{N}} | {{SHARE_OR_OMITTED}} | {{PEER_COUNT}} |

###### *The share is a fraction of the named peer set and it must agree with its own breakdown to within one peer. A share with no breakdown behind it is refused. Where the unknowns dominate, omit the share and let the counts speak.*

# 7. Gap Prioritisation

|  |
| :-: |
| **SECTION CONTROL: 7. GAP PRIORITISATION****PURPOSE:** Rank every gap on a repeatable formula so the roadmap sequence can be defended.**FEEDS:** O5 opportunity tiles, O6 findings, H1 focus areas. O5 requires the breakdown to reproduce the headline arithmetic exactly.**INPUTS:** Scoring workbook: Category_Rollup, Peer_Benchmarks, Issue_Register.**LENGTH:** 450 to 700 words.**MINIMUM DATA:** Every gap ranked. All six factors scored per gap. Root cause at gap grain for the top 3 to 5, each with at least 2 E-IDs and the REC id where it is stated again.**MUST INCLUDE:** The weighted calculation shown in full for the top-ranked gap, so the ranking is checkable by hand.**MUST NOT:** Rank on gap size alone.**FAIL IF:** The six weights do not sum to 1.00, a gap ranked in the top 5 lacks a root cause, or a root cause here names a different cause from the one its recommendation gives in section 8. The pair is deliberate; a contradiction between them is not. |

### 7.1 Prioritisation formula

|  |  |  |
| :-: | :-: | :-: |
| **Factor** | **Weight** | **Scored on** |
| Gap size | 0.25 | Points below peer median |
| Peer comparison | 0.20 | Rank within the locked peer set |
| Strategic alignment | 0.15 | Fit to stated entity objectives |
| Implementation complexity | 0.15 | Inverted: lower complexity scores higher |
| Investment efficiency | 0.15 | Maturity points per unit of effort |
| Stakeholder readiness | 0.10 | Sponsorship and change capacity evidence |
| **Total** | **1.00** | **Verified at render; a sum other than 1.00 blocks issue** |

### 7.2 Gap priority register

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Rank** | **Gap** | **Capability** | **Gap size** | **Priority score** | **REC** |
| {{RANK}} | {{GAP_TITLE}} | {{CAP_ID}} | {{GAP_POINTS}} | {{PRIORITY_SCORE}} | {{REC_ID}} |

###### *Worked example for rank 1: (0.25 x {{F1}}) + (0.20 x {{F2}}) + (0.15 x {{F3}}) + (0.15 x {{F4}}) + (0.15 x {{F5}}) + (0.10 x {{F6}}) = {{PRIORITY_SCORE}}.*

### 7.3 Critical gap root causes

###### *Root cause at GAP grain, for the top 3 to 5 only. This is the diagnostic half of a deliberate pair: the same cause is stated again in section 8 at ACTION grain, framed as what the recommendation is built to remove. The repetition is intended, so that a reader of the ranking is not sent forward to understand it and a reader of a recommendation is not sent back. Both must say the same thing about the same gap.*

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Rank** | **Gap** | **Why the gap exists (60 to 120 words, cited)** | **Evidence** | **Stated again at** |
| {{RANK}} | {{GAP_TITLE}} | {{ROOT_CAUSE_AT_GAP_GRAIN}} | {{E_IDS}} | {{REC_ID}} |

###### *Write the cause, not the symptom. 'The score is low' restates the gap. 'Two core systems hold the customer record and neither is authoritative' is a cause, and it is the sentence the recommendation in section 8 will be built to remove.*

# 8. Recommendations

|  |
| :-: |
| **SECTION CONTROL: 8. RECOMMENDATIONS****PURPOSE:** Convert ranked gaps into named, evidenced actions, each with a platform choice that states its own readiness and each argued against before it ships.**FEEDS:** P2 recommendations and P1 platform fit and story, with the readiness block rendering as the DD-13 gate expansion. P3 reconciles its phases against these REC ids.**INPUTS:** Scoring workbook: Solution_Catalogue, Platform_Peer_Adoption, Category_Rollup, Subcap_Scores. Research workbook: Technographic_Scan, Tech_Landscape, Evidence_Register.**LENGTH:** 350 to 550 words per recommendation. Between 5 and 8 recommendations.**MINIMUM DATA:** Per recommendation: a provenance label, a root cause of 30 to 60 words with citations, a cost of inaction of 30 to 60 words, a KPI triple whose baseline exists with a date, one impact row per affected cell, a readiness contract for every platform named, and a completed rebuttal.**MUST INCLUDE:** A rebuttal on every recommendation without exception. A readiness contract on every platform named, covering conditions met, conditions not met and open discovery questions.**MUST NOT:** Present a derived recommendation as analyst judgement. State a duration in weeks or months anywhere: sequencing is expressed as horizon and dependency, and the app has no field for elapsed time. Name a platform with no readiness contract.**FAIL IF:** A recommendation ships with an empty rebuttal, a platform is named with no readiness contract, a KPI baseline has no source, an impact figure disagrees with the served score by more than 0.05, or its root cause contradicts the one section 7.3 gives for the same gap. |

  

|  |
| :-: |
| **PRE-WRITE VERIFICATION****1:** Specific E-IDs confirm the gap exists, rather than an absence of evidence being read as an absence of capability.**2:** Proxy searches are exhausted before any claim that a function does not exist.**3:** The solution maps to a named entry in Solution_Catalogue, which holds {{SOLUTION_COUNT}} solutions at version {{SOLUTION_CATALOGUE_VERSION}}.**4:** Every target cell is one this run serves. A cell whose code names a sub-vertical other than {{SUBVERTICAL_ID}} resolves in the workbook and renders nowhere.**5:** Every current figure in the impact table equals the served score for that cell. Assert it before writing. |

  

## **REC-{{NN}}: {{RECOMMENDATION_TITLE}}**

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Provenance** | **Target area** | **Effort band** | **Phase** | **Claim label** |
| {{ANALYST | DERIVED}} | {{L3_AREA}} | {{S | M | L}} | {{PHASE_ID}} | {{CLAIM_LABEL}} |

###### *Provenance is required and never blank. Derived means composed from the pack by rule. A derived recommendation presented as analyst judgement is the single failure that costs an account executive the most credibility, because the distinction is the reader's basis for trusting everything else on the page.*

#### **Root cause**

###### *30 to 60 words, cited. Why the gap exists, not a restatement of the gap. A root cause of 'the score is low' is not a root cause. Where this recommendation closes a gap ranked in the top 3 to 5, section 7.3 states the same cause at gap grain and this is the action-grain telling of it: same cause, framed as what this recommendation removes. Say the same thing, not a different thing in different words.*

{{ROOT_CAUSE_30_TO_60_WORDS}} [{{E_IDS}}]

#### **Cost of inaction**

###### *30 to 60 words. What degrades, which capability absorbs the damage, and what grounds the claim. Ground it in a dated regulator milestone, a peer trajectory, a contract or licence expiry, a migration date already in evidence, or a stated board commitment. Where nothing grounds it, write that no dated trigger is established: that is a better answer than invented urgency and an account executive can use it.*

{{COST_OF_INACTION_30_TO_60_WORDS}} [{{E_IDS}}]

#### **Solution**

{{SOLUTION_DESCRIPTION}} using {{PLATFORM_NAMES}}, aligned to {{ZENNIFY_SOLUTION_NAME}} from Solution_Catalogue.

### Platform readiness contract

###### *Required for every platform named above. The app renders this as the readiness gate expansion, and the verdict there must be traceable to the cells below. Readiness multiplies the platform fit score rather than annotating it, so a platform whose prerequisites are failing cannot present as a strong fit however good the narrative is.*

|  |  |  |  |
| :-: | :-: | :-: | :-: |
| **Platform** | **Readiness verdict** | **Depends on** | **Effect on fit** |
| {{PLATFORM_NAME}} | {{READY | READY WITH CONDITIONS | NOT READY YET}} | {{PLATFORMS_THAT_MUST_LAND_FIRST}} | {{MULTIPLIER}} |

###### *A platform is never sequenced ahead of something it depends on. Where the foundation is not ready, name the dependency and let the order follow it.*

#### **Conditions met**

###### *Threshold gates this platform already clears. Each one is a cell, a minimum and the served value, so the reader can check it. The threshold speaks in scores; no cap vocabulary and no maturity codes appear in this block.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Cell** | **Minimum** | **Current** | **Verdict** | **What this makes possible** | **Evidence** |
| {{CELL_ID}} | {{MIN}} | {{CURRENT}} | MET | {{ALREADY_TRUE_NOTE}} | {{E_ID}} |

#### **Conditions not met**

###### *Threshold gates this platform does not clear today. These are the rows the readiness verdict rests on, and each must state what has to become true first and why.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Cell** | **Minimum** | **Current** | **Verdict** | **What must be true first, and why** | **Evidence** |
| {{CELL_ID}} | {{MIN}} | {{CURRENT}} | NOT MET | {{MUST_BE_TRUE_FIRST_NOTE}} | {{E_ID}} |

#### **Open discovery questions**

###### *Conditions that no search in this run could settle. These carry a written basis of not established, together with the ladder that was walked. An open question stated plainly is a discovery agenda item; the same question left silent is a readiness claim with nothing behind it.*

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Condition** | **Why it matters to this platform** | **Basis** | **How it gets answered** | **Owner** |
| {{CONDITION}} | {{NOTE}} | Not established | {{DISCOVERY_METHOD}} | {{ZENNIFY | CLIENT}} |

###### *Reasoning lives in the note, not in the verdict. A condition written as a bare string renders as no gate at all, which is how nine real gates once disappeared from a live page.*

### Rebuttal

###### *Every recommendation carries one. A claim that survives its strongest counter-argument can be defended in the room; a claim that does not survive was going to fail there instead. Arguing against your own conclusion is the step that gets skipped, and it is the only one that catches a recommendation that is well formed, correctly cited and wrong.*

|  |  |
| :-: | :-: |
| **Step** | **What to record** |
| **A. Hypothesis** | {{THE_CLAIM}}, held at {{CONFIDENCE}}. State it before defending it. |
| **B. Steelman against** | {{THE_STRONGEST_CASE_FOR_NOT_DOING_THIS}}. Argue it properly rather than setting up something easy to knock down. |
| **B. Falsifier** | {{WHAT_WOULD_DISPROVE_THE_CLAIM}}, drawn from the client's own words where possible [{{E_ID}}]. State the conditions under which the steelman holds and the conditions under which it fails. |
| **B. Cheaper alternative** | {{THE_LOWER_COST_INTERVENTION_THAT_CLOSES_THE_SAME_GAP}}, and why it was not chosen. Where none exists, say so. |
| **B. Case for waiting** | {{THE_REASON_TO_DO_THIS_LATER}}, or a statement that none was found after looking. |
| **C. Domain test** | Plausible for {{SUBVERTICAL_NAME}} at {{SIZE_TIER}} under {{REGULATOR}}? And would this sentence be true of any institution in this sub-vertical? If yes, it is a fact about the sub-vertical and needs this entity's own figure, event or executive attached before it ships. |
| **D. Probes run** | {{PROBES}}. Each probe fires a search; a probe not run is not a probe. |
| **E. Verdict** | {{ACCEPT | REJECT | UNCERTAIN}}. Reject means drop or re-rank the recommendation, never soften the wording. |

#### **Probe set for a recommendation**

|  |  |  |
| :-: | :-: | :-: |
| **Probe** | **Fires when** | **Search or check** |
| Platform out of vertical | The platform serves a different sub-vertical | Relevance against the served cell set |
| Anchor cell of the wrong entity type | The target cell names another sub-vertical | Terminal segment of the cell id |
| Dependency inversion | This is sequenced ahead of what it needs | The depends-on chain |
| Stale metric in the impact table | A current figure disagrees with the served score | Recompute against Subcap_Scores |
| KPI baseline with no source | The baseline has no date or no evidence | Evidence_Register lookup |
| Gate asserted with no backing cells | A readiness verdict has no cells behind it | The readiness contract above |
| Initiative already underway | The client may have started or dropped this | Search the entity plus the initiative plus paused, completed, replaced or delayed |

#### **Impact on assessed capabilities**

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Cell** | **Name** | **Current** | **Target** | **Delta** | **Evidence** |
| {{CELL_ID}} | {{CELL_NAME}} | {{CURRENT}} | {{TARGET}} | {{DELTA}} | {{E_ID}} |

###### *One row per affected cell. Every current figure must equal what the heatmap serves, within 0.05. Assert it before emitting rather than after a reader finds the difference.*

#### **Measure of success**

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Metric** | **Baseline** | **Baseline as at** | **Baseline source** | **Target** |
| {{METRIC}} | {{BASELINE}} | {{DATE}} | {{E_ID}} | {{TARGET}} |

###### *The baseline must be a figure that already exists with a date against it. An aspiration is not a baseline, and a target with no baseline behind it cannot be judged later.*

#### **Why this phase**

###### *20 to 40 words naming the dependency or the gate that fixes this position. It must agree with the roadmap and with the stair-step. Sequencing asserts a dependency, so it is a causal claim and carries the same burden as a ranking.*

{{SEQUENCING_REASON_20_TO_40_WORDS}}

# 9. Transformation Roadmap

|  |
| :-: |
| **SECTION CONTROL: 9. ROADMAP****PURPOSE:** Put the recommendations in an order that follows dependency, and say what fixes each position.**FEEDS:** P3 roadmap and P4 stair-step curve. Phase ids reconcile against the section 8 recommendation set, and step order must equal roadmap order must equal sequencing order.**INPUTS:** Section 8 recommendations, section 7 ranking, Pillar_Rollup for the starting position.**LENGTH:** 300 to 500 words.**MINIMUM DATA:** 3 or more phases. Every recommendation assigned to exactly one phase. A rationale of 30 to 60 words per phase. A dependency chain that does not loop back on itself.**MUST INCLUDE:** A horizon drawn from the fixed vocabulary, spelled exactly as given. Where the order genuinely cannot be settled, a discovery phase that carries no recommendations and states which unresolved dependencies it exists to resolve.**MUST NOT:** State a duration, an elapsed time, a week count, a month count or a date range anywhere in this section. The app carries a horizon and a dependency chain, and it has no field for how long anything takes. A phase rationale that restates the phase title.**FAIL IF:** A recommendation from section 8 appears in no phase, a phase precedes something it depends on, the dependency chain loops, or any duration appears. |

### 9.1 Horizon vocabulary

###### *Three values, spelled exactly as below. They are matched on exact text, so a variation renders as nothing. This is a sequencing vocabulary rather than a schedule: it says what comes before what, and it deliberately makes no claim about elapsed time.*

|  |  |  |
| :-: | :-: | :-: |
| **Value** | **Means** | **Do not write** |
| next two quarters | The work that can start against what is already true | Q1, 0 to 6 months, 90 days, immediate |
| this year | The work gated on something in the first horizon landing | Months 6 to 12, H2, mid-term |
| beyond | The work whose prerequisites are not yet in view | Year 2, 18 months plus, long-term |

### 9.2 Phases

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Phase** | **Horizon** | **Recommendations** | **Capabilities** | **Depends on** | **Rationale** |
| PH-{{N}} {{PHASE_NAME}} | {{HORIZON}} | {{REC_IDS}} | {{CATEGORY_NAMES}} | {{PHASE_IDS}} | {{RATIONALE_30_TO_60_WORDS}} |

###### *The rationale argues the dependency, not the title. Write why this phase sits here and not earlier. A thin rationale is visibly thin, which is the honest failure; a rationale that repeats the phase name is the dishonest one.*

#### **The discovery phase, where the order cannot yet be settled**

###### *Where dependencies are genuinely unresolved, a phase that carries no recommendations and states which questions it exists to answer is a better artefact than an order invented to look decisive. Draw its questions from the open discovery questions in section 8.*

|  |  |  |  |
| :-: | :-: | :-: | :-: |
| **Phase** | **Recommendations** | **Unresolved dependencies it exists to resolve** | **Source** |
| PH-0 Discovery | none | {{THE_OPEN_QUESTIONS}} | Section 8 readiness contracts |

### 9.3 Stair-step

###### *A scoped ladder on one theme rather than a whole-assessment climb. Exactly one step is marked as the current position, and its entry condition states the served value that puts it there. Every step above the current position carries at least one blocking finding; the step below carries none.*

|  |  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: | :-: |
| **Step** | **Entry condition** | **What it unlocks for the client** | **Blocking findings** | **Effort** | **Position** |
| {{N}} | {{CELL}} \\\>= {{MIN}}, {{met | not met}} at {{CURRENT}} | {{CLIENT_OUTCOME}} | {{FINDING_IDS}} | {{S | M | L}} | {{CURRENT | }} |

###### *Theme: {{THEME}}, running from {{FROM_LEVEL}} to {{TO_LEVEL}}. An unlock is a client outcome in plain words, not a capability name. Blocking findings are plain ids that resolve into the pack, so the chip opens the finding and its citations. Entry conditions must state the same cell and threshold as the matching recommendation readiness contract, or the ladder and the panel will disagree.*

### 9.4 Maturity trajectory

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Horizon** | **Overall** | **Per pillar** | **Level** | **Peer position** |
| {{HORIZON}} | {{OVERALL}} | {{PILLAR_SCORES}} | {{LEVEL}} | {{POSITION}} |

###### *The per-pillar column expands to {{PILLAR_COUNT}} values, generated from the catalogue. Horizon uses the same three values as the phases; no dates and no durations appear here either.*

# 10. Data Gaps and Confidence

|  |
| :-: |
| **SECTION CONTROL: 10. DATA GAPS AND CONFIDENCE****PURPOSE:** State plainly what the assessment could not see. Transparency here is what makes the rest of the report credible.**FEEDS:** H3 thin-evidence alerts and H7 evidence age tracker. Coverage and freshness are different questions and the app keeps them apart.**INPUTS:** Scoring workbook: Subcap_Scores confidence columns. Research workbook: Coverage_Map, Assumptions, Negative_Searches.**LENGTH:** 250 to 400 words.**MINIMUM DATA:** Gaps listed per pillar. The count of cells scored on tier 4 or weaker evidence only. The count scored on no direct evidence. Named next steps that would close each material gap.**MUST INCLUDE:** What internal evidence would move each low-confidence score, and by roughly how much.**MUST NOT:** Present a gap without saying what it would take to close it. Express any of this as a coverage percentage: coverage is O10, it is internal, and a second denominator here would contradict the heatmap.**FAIL IF:** A pillar has low-confidence scores and no corresponding entry here. |

  

|  |  |  |  |  |
| :-: | :-: | :-: | :-: | :-: |
| **Pillar** | **Cells on thin evidence** | **What is missing** | **How to close it** | **Likely score movement** |
| {{PILLAR_ID}} | {{N}} | {{MISSING}} | {{METHOD}} | {{RANGE}} |

{{RECOMMENDED_NEXT_STEPS}}

# 11. Workbook Traceability

|  |
| :-: |
| **SECTION CONTROL: 11. WORKBOOK TRACEABILITY****PURPOSE:** Let a reader verify any claim in this report by locating the artefact behind it.**FEEDS:** H6 evidence store and H2 cell evidence read the register this section points at.**INPUTS:** Research workbook: Evidence_Register. Scoring workbook: Subcap_Scores.**LENGTH:** 100 to 150 words.**MINIMUM DATA:** Both workbook filenames with revision identifiers. Every artefact class mapped to a named tab and a match key.**MUST NOT:** Reproduce the evidence register. Carry evidence coverage, tier distribution or self-sourced share: those are O10 and O11 in the app, they are internal instrumentation, and the app never serves them to a client. A coverage figure computed here would sit on a different denominator from the one the heatmap serves, and the difference is a contradiction a reader can find by counting.**FAIL IF:** An E-ID cited anywhere in this report does not resolve in Evidence_Register, or a tab named below is absent. |

### 11.1 Where to verify a claim

|  |  |  |  |
| :-: | :-: | :-: | :-: |
| **To look up** | **Open** | **Tab** | **Match on** |
| Any [E-xxx] citation | {{RESEARCH_WORKBOOK}} rev {{RESEARCH_WORKBOOK_REV}} | Evidence_Register | evidence_id |
| A subcapability score and its rationale | {{SCORING_WORKBOOK}} rev {{SCORING_WORKBOOK_REV}} | Subcap_Scores | subcap_id, source_cell |
| A capability or maturity level definition | {{SCORING_WORKBOOK}} | Capability_Definitions, Maturity_Rubric | capability_id |
| Pillar weights and their rationale | {{SCORING_WORKBOOK}} | Pillar_Weights | weight_set_id |
| Peer figures and platform adoption | {{SCORING_WORKBOOK}} | Peer_Benchmarks, Platform_Peer_Adoption | peer_id |
| Cap rules and issue detail | {{SCORING_WORKBOOK}} | Cap_Triggers, Issue_Register | issue_id |
| Locked parameters and gate results | {{SCORING_WORKBOOK}} | Handoff_Lock, Gate_Log | assessment_id |
| Coverage, tier mix, self-sourced share | Not in this report | App surfaces O10 and O11 | internal instrumentation |

###### *This report carries no appendices and no evidence coverage instrumentation. Capability definitions, maturity level definitions, pillar weight rationale and the full evidence register are held in the workbooks and versioned with them.*