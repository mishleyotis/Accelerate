# Diagnostic Questions Reference (Fallback)

**What this file is, measured.** It holds **one group of question PATTERNS per
category — 16 groups, ~66 questions in all**, not one question per
subcapability. Against a catalogue of 851 subcapabilities that is roughly 8%
of the coverage a per-subcap bank would give. The skill's own index used to
describe it as "All ~836 diagnostic questions", which is the claim this
paragraph replaces: a run that falls back to this file is running on
category-level patterns and **must say so in its coverage statement**.

**These are patterns, and a pattern is not a question until it is graded.**
Many are written in a closed form ("Does the organization have…"). A closed
question cannot produce a graded answer, and a five-level scale needs one
that can. Before you search, rewrite each as a graded probe — the rule is in
`Grading a closed pattern` below, and every pattern is followed by the graded
form to use.

Use this file ONLY if the Pillar Scoring Toolkit XLSX files are not available. When the
XLSX files ARE available, read diagnostic questions directly from Column H of each pillar's
Capability Map sheet — that is the authoritative source.

This file provides the STRUCTURE and MAPPING LOGIC for diagnostic questions. The actual
questions vary by subvertical toolkit version. The patterns below apply universally.

## Grading a closed pattern

Every closed pattern converts the same way, and the conversion is mechanical:

| closed | graded |
|---|---|
| Does X have Y? | To what extent is Y established at X, and since when? |
| Is Y documented? | How far does Y's documentation reach, and who owns it? |
| Are Ys defined? | Which Ys are defined, by whom, and how are they reviewed? |
| Can X do Y? | Where has X demonstrated Y, and where has it not held? |
| Has X done Y? | What is the arc of Y at X — earliest signal, refreshes, stalls? |

The graded form is what goes in the search plan and what the answer is scored
against. A yes/no answer scores nothing, because there is no level in it.

**The retired 17th category (P1C5, ESG) has been removed from this file.** It
does not exist in catalogue v7.0, and every one of its cells resolves
NOT_COMPARABLE across versions. A run that finds it in an older toolkit is
looking at a v5.0 workbook.

---

## How to Extract Diagnostic Questions from Pillar XLSX

```python
import openpyxl

def extract_diagnostic_questions(pillar_xlsx_path):
    wb = openpyxl.load_workbook(pillar_xlsx_path, read_only=True)
    # The Capability Map sheet contains the subcap hierarchy
    ws = wb['Capability Map']  # or similar name — check sheet names
    
    subcaps = []
    for row in ws.iter_rows(min_row=2):  # skip header
        subcap = {
            'subcap_id': row[0].value,      # Column A: e.g., P1C1.1.1
            'subcap_name': row[1].value,     # Column B: e.g., Strategy Document
            'capability': row[2].value,      # Column C: parent capability
            'diagnostic_q': row[7].value,    # Column H: the diagnostic question
            'weight': row[3].value,          # Column D: weight percentage
        }
        if subcap['subcap_id']:  # skip empty rows
            subcaps.append(subcap)
    return subcaps
```

**Note**: Column positions may vary by toolkit version. Always verify by checking
the header row. Look for columns labeled "Diagnostic Question" or "Assessment Question."

---

## Diagnostic Question Patterns by Capability Domain

### P1: Strategy, Governance & Culture (~200 subcaps)

**P1C1 Digital Strategy** (typical subcap questions):
- Does the organization have a documented digital strategy?
- Is the strategy aligned to overall business objectives?
- Is there a defined cadence for refreshing the strategy?
- Is the strategy communicated to all levels of the organization?
- Does the board approve and oversee the digital strategy?
- Are KPIs defined to measure strategy execution?
- Is there a multi-year technology investment roadmap?

**P1C2 Governance & Risk Appetite**:
- Is there a technology governance committee?
- Are digital risk appetite statements documented?
- Is there board-level oversight of technology risk?
- Are technology investment decisions governed by a formal process?
- Are audit findings tracked and remediated?

**P1C3 Innovation Management**:
- Does the organization have a formal innovation program?
- Are fintech partnerships actively pursued?
- Is there a dedicated innovation budget?
- Are emerging technologies evaluated systematically?

**P1C4 Culture & Change**:
- Is there a digital skills training program?
- Are change management practices formalized?
- Is digital literacy assessed across the organization?
- Is technology adoption measured and reported?

**P2C1 Digital Marketing**:
- Is digital marketing strategy documented?
- Are marketing channels integrated?
- Is marketing effectiveness measured with analytics?
- Are personalized campaigns delivered?

**P2C2 Onboarding**:
- Is digital account opening available?
- What is the straight-through processing rate for new accounts?
- Are identity verification processes automated?
- Is the onboarding experience measured (time-to-fund, abandonment)?

**P2C3 Omnichannel Servicing**:
- Are all service channels (mobile, web, branch, contact center) integrated?
- Can members start a transaction in one channel and complete in another?
- Is contact center technology modern (cloud-based, AI-assisted)?
- Are service quality metrics tracked per channel?

**P2C4 Personalization**:
- Are personalized recommendations delivered?
- Is AI/ML used for next-best-action?
- Are member segments defined and actively managed?
- Is personalization effectiveness measured?

### P3: Operations, Risk & Compliance (~160 subcaps)

**P3C1 Core Automation**:
- What percentage of processes are automated?
- Is RPA or process automation technology deployed?
- Are exception rates tracked?
- Is straight-through processing measured?

**P3C2 Fraud & Op Risk**:
- Is real-time fraud detection in place?
- Are fraud losses tracked and reported?
- Is the fraud detection platform modern (ML-based)?
- Are operational risk events systematically captured?

**P3C3 Compliance**:
- Are there any active enforcement actions?
- Is compliance monitoring automated?
- Are regulatory changes tracked systematically?
- Is the compliance management system documented?

**P3C4 Resilience & TPRM**:
- Is business continuity planning documented and tested?
- Is disaster recovery tested annually?
- Are third-party vendors risk-assessed?
- Is vendor concentration risk monitored?

### P4: Data, Analytics & Technology (~190 subcaps)

**P4C1 Data Governance**:
- Is there a Chief Data Officer or equivalent role?
- Is a data governance framework documented?
- Are data quality metrics tracked?
- Is master data management in place?

**P4C2 Analytics & AI**:
- Are predictive analytics deployed in production?
- Is AI/ML used for business decisions?
- Are model risk management practices in place?
- Is analytics adoption tracked across the organization?

**P4C3 Technology Architecture**:
- Is the core platform modern or legacy?
- Is an API strategy documented?
- Is cloud adoption in progress?
- Are integration patterns standardized?

**P4C4 Cybersecurity**:
- Are cybersecurity certifications current (SOC2, ISO 27001)?
- Has the organization experienced data breaches?
- Is security awareness training conducted?
- Is vulnerability management automated?

---

## Converting Diagnostic Questions to Search Queries

### Formula

```
Search Query = [Entity Name] + [Core Subject from Question] + [Evidence Target Keyword]
```

### Examples

| Diagnostic Question | Core Subject | Evidence Target | Search Query |
|----|----|----|-----|
| "Does the org have a documented digital strategy?" | digital strategy | existence/document | "[Entity] digital strategy roadmap document" |
| "Is the strategy communicated to all levels?" | strategy communication | internal comms | "[Entity] digital strategy employee communication announcement" |
| "Are marketing channels integrated?" | marketing integration | platform/tool | "[Entity] omnichannel marketing integrated campaign" |
| "Is real-time fraud detection in place?" | fraud detection | technology | "[Entity] fraud detection real-time monitoring platform" |
| "Is the core platform modern or legacy?" | core platform | technology | "[Entity] core banking system modernization migration" |
| "Are cybersecurity certifications current?" | security certification | audit/cert | "[Entity] SOC2 ISO 27001 security certification" |

### Evidence Reuse Across Subcaps

A single evidence item often maps to multiple subcapabilities. When you find a rich source
(like an annual report), extract multiple facts and map each to the relevant subcap:

```
E-015: Annual Report 2024 (T2, CURRENT)
  F1: "Board approved 3-year digital roadmap" → P1C1.1.1 (strategy doc), P1C1.1.5 (board engagement)
  F2: "$15M technology investment planned" → P1C1.1.2 (business alignment)
  F3: "Launched mobile app redesign Q3" → P2C3 (omnichannel), P2C2 (onboarding)
  F4: "Partnered with [fintech] for fraud detection" → P3C2 (fraud), P1C3 (innovation)
  F5: No mention of data governance or CDO → P4C1 (ABSENCE signal)
```

This is why `web_fetch` on annual reports and 10-Ks is critical — one document can
populate evidence for 20+ subcapabilities.