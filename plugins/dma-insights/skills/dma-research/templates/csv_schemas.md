# CSV Schema Definitions for Research Appendix Artifacts

Use these schemas when generating the CSV appendix files in Batches 4 and 6.

---

## A1: Evidence Inventory CSV

```csv
evidence_id,source_name,source_url,source_type,tier,recency_tag,date_published,kb_source_id,ers_total,tier_score,recency_score,specificity_score,corroboration_score,fact_count,subcap_mappings,claim_types,corroborating_ids,contradicting_ids,batch_collected
E-001,"NCUA Call Report Q4 2024","https://...","regulatory_filing",T1,CURRENT,2025-03-15,KB-US-001,4.30,5.0,5.0,4.0,3.0,3,"P1C1.1.2|P4C3.1.1|P3C3.2.1","FACT|FACT|FACT","E-005|E-012","",1
```

**Columns**: evidence_id, source_name, source_url, source_type, tier, recency_tag,
date_published, kb_source_id, ers_total, tier_score, recency_score, specificity_score,
corroboration_score, fact_count, subcap_mappings (pipe-separated), claim_types
(pipe-separated), corroborating_ids (pipe-separated), contradicting_ids (pipe-separated),
batch_collected

---

## A2: Search Log CSV

```csv
search_id,query,search_tier,subcap_target,capability_target,pillar,timestamp,results_count,useful_results,evidence_ids_generated,fetched_urls,escalation_level,notes
S-0001,"Gesa Credit Union digital strategy planning cycle",1,P1C1.1.3,P1C1,P1,2025-03-15T10:00:00Z,8,2,"E-011|E-012","https://...",0,""
S-0002,"Gesa Credit Union annual report 2024 strategy",2,P1C1.1.3,P1C1,P1,2025-03-15T10:00:05Z,5,1,"E-015","https://...",0,"Fetched full annual report"
```

**Columns**: search_id, query, search_tier (1-10), subcap_target, capability_target,
pillar, timestamp, results_count, useful_results, evidence_ids_generated (pipe-separated),
fetched_urls (pipe-separated), escalation_level (0=initial, 1-4=escalation), notes

---

## A3: Financial Trends CSV

```csv
metric,year_1,year_2,year_3,year_4,year_5,yoy_change_latest,5yr_cagr,trend_direction,evidence_ids,notes
Total Assets ($M),3200,3500,3700,3900,4200,7.7%,5.6%,↑,"E-001:F1|E-001:F2",""
Net Worth Ratio (%),10.2,10.5,10.1,9.8,9.6,-2.0%,-1.2%,↓,"E-001:F3","Declining — monitor"
Member Count,185000,192000,198000,205000,215000,4.9%,3.1%,↑,"E-001:F4",""
```

**Columns**: metric, year_1 through year_5 (oldest to newest), yoy_change_latest,
5yr_cagr, trend_direction (↑/→/↓), evidence_ids (pipe-separated), notes

**Required metrics** (vary by subvertical — see `references/subvertical_profiles.md`):
- Credit Unions: Total assets, shares, loans, net worth ratio, ROA, member count, loan-to-share
- Banks: Total assets, deposits, loans, NIM, efficiency ratio, NPL ratio, CET1 ratio
- Insurance: DWP, combined ratio, loss ratio, investment income, surplus
- Asset Mgmt: AUM, net flows, expense ratio, alpha

---

## A4: Tech Stack Map CSV

```csv
platform,vendor,category,zennify_priority,evidence_level,utilization_level,recency_tag,last_confirmed,vendor_tenure,red_flags,uncertainty_modifier,ceiling_impact,capability_mapping,discovery_questions,evidence_ids
Salesforce FSC,Salesforce,CRM,true,2,Medium,CURRENT,2024-09-15,5-10yr,URF-01,+0.2,"P2C1 L3.5|P2C3 L3.0","What % of member interactions use FSC?|How many certified admins?","E-012|E-015:F4|E-032"
```

**Columns**: platform, vendor, category, zennify_priority (true/false), evidence_level
(1-4), utilization_level (High/Medium/Low/Unknown), recency_tag, last_confirmed (date),
vendor_tenure (<2yr/2-5yr/5-10yr/10+yr/Unknown), red_flags (pipe-separated URF codes),
uncertainty_modifier (sum), ceiling_impact (pipe-separated capability|ceiling pairs),
capability_mapping (pipe-separated P#C# IDs), discovery_questions (pipe-separated),
evidence_ids (pipe-separated)

---

## A5: Issue Register CSV

```csv
issue_id,issue_description,regulator,date_identified,date_resolved,severity,status,type,milestones,capability_impact,evidence_ids,notes
ISS-001,"CFPB consent order — unfair overdraft practices",CFPB,2023-06-15,2024-12-01,HIGH,Resolved,Enforcement,"2023-06-15: Order issued|2024-03-01: Remediation plan filed|2024-12-01: Terminated","P3C3 ↓|P2C3 ↓","E-025|E-026","Impacts P3C3 ceiling"
```

**If no issues found**:
```csv
issue_id,issue_description,regulator,date_identified,date_resolved,severity,status,type,milestones,capability_impact,evidence_ids,notes
ISS-000,"No enforcement actions found","All searched (NCUA|OCC|CFPB|SEC)",,,,Negative Search,,"Searched: [list URLs and dates]","P3C3 ↑ (positive signal)","","Negative search documented — supports compliance posture"
```

---

## A6: Sentiment Data CSV

```csv
source,platform,rating,review_count,date_checked,trend_direction,positive_themes,negative_themes,capability_signals,evidence_ids
Customer,iOS App Store,4.2,12450,2025-03-15,↑,"easy to use|fast transfers|good design","occasional crashes|slow loan process","P2C3 ↑|P2C2 ↓","E-040|E-041"
Customer,Google Play,3.8,8200,2025-03-15,→,"convenient|good mobile check deposit","login issues|limited features","P2C3 →|P4C4 ↓","E-042|E-043"
Customer,CFPB Complaints,,45,2025-03-15,↓,"","account access|fees|overdraft","P2C3 ↓|P3C3 →","E-044"
Employee,Glassdoor,3.9,215,2025-03-15,→,"good benefits|community focus","outdated systems|slow to change","P1C4 ↓|P4C3 ↓","E-045|E-046"
```

**Columns**: source (Customer/Employee), platform, rating (if applicable), review_count,
date_checked, trend_direction, positive_themes (pipe-separated), negative_themes
(pipe-separated), capability_signals (pipe-separated with direction), evidence_ids

---

## A7: Evidence-to-Capability Coverage Map CSV

```csv
capability_id,capability_name,total_subcaps,subcaps_with_evidence,subcaps_thin,subcaps_no_evidence,coverage_pct,highest_ers,lowest_ers,avg_ers,tier_distribution,ceiling_estimate,uncertainty_band,discovery_priority
P1C1,Digital Strategy & Vision,12,10,1,1,83%,4.30,1.85,3.15,"T1:2|T2:4|T3:3|T5:1",L3.0,±0.3,MEDIUM
P4C3,Technology Architecture,15,8,4,3,53%,3.65,1.50,2.40,"T3:5|T4:2|T5:1",L2.5,±0.6,HIGH
```

---

## A8: Assumptions Register CSV

```csv
assumption_id,assumption,basis,capability_affected,falsification_search,search_outcome,confidence_impact,resolution
ASM-001,"Entity uses Fiserv DNA as core","Job postings mention Fiserv + Symitar terminology","P4C3","[Entity] core system site:fiserv.com","Confirmed via Fiserv case study (E-055)",None,"Validated — not an assumption"
ASM-002,"No active regulatory enforcement","Searched NCUA + CFPB + state — no results","P3C3","[Entity] NCUA enforcement 2024 2025","No results across 3 searches","P3C3 ceiling +0.5","Treated as positive signal with caveat — enforcement may be sealed"
```

---

## A9: Organizational Capability Assessment CSV

```csv
metric,value,source,date_checked,interpretation,capability_impact,evidence_ids
LinkedIn Total Employees,~850,LinkedIn Company Page,2025-03-15,Mid-size workforce,"Size context for all pillars",E-060
LinkedIn IT/Tech Employees,~65,LinkedIn search,2025-03-15,"7.6% of workforce — MEDIUM specialist ratio","P1C4: supports L2.5-3.0 ceiling",E-061
Salesforce-titled Employees,8,LinkedIn search,2025-03-15,"~12% of IT — MEDIUM density","P4C3: moderate SF capability",E-062
Certified SF Professionals,2,LinkedIn search,2025-03-15,"Low certification count — URF-01 flag","P4C3: cap at L3.0 for SF utilization",E-063
Active Tech Job Postings,5,Indeed/LinkedIn,2025-03-15,"3 Admin-level, 2 Senior — no Architect","P1C4: building basic capability",E-064
Glassdoor Overall Rating,3.9/5,Glassdoor,2025-03-15,"Above average","P1C4: positive culture signal",E-045
Glassdoor Tech Theme,Mixed,Glassdoor reviews,2025-03-15,"'Good tools' but 'slow to change'","P1C4: ceiling L3.0, P4C3: ±0.2 uncertainty",E-046
Average Tech Role Tenure,~3.2 years,LinkedIn estimate,2025-03-15,"Moderate stability","P1C4: no knowledge loss flag",E-065
```
