# Page: insights

Two sections. Cards must be claims, not topics. The landscape strip recomputes its counts from the tech-stack register, so techstack can be produced before or after but the counts must reconcile.

**2 sections · 2 surfaces.** Submit with `submit_page_payload(run_id, page='insights', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The four standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `insights` | yes | I1 | D2 |
| `landscape` | yes | T2 | D2 |

---

## I1 · Insight cards

- **Section** `insights.insights` — **renders on** D2 (Insights)
- **Contract** Triage layout grouped by priority, pillar or theme. Each card carries a claim as its title and opens a four-tab modal.

### Must present

Six to ten cards, each a defensible argument: what, why it matters, what to do, with severity and the capability it anchors on.

Zero cards on a completed run is a failure state, not an empty state.

No card may open with a score read-out; the what_text is a claim, not a metric.

Every linked_subcap_id must resolve to a served cell — dead links were 15 of 119.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| cards[].what/why/so_what | Assessment report deep dives; research workbook | the analyst's argument, restated for an AE |
| cards[].linked_subcap_id | scoring workbook | must resolve to a cell this run serves |
| cards[].severity | producer | critical │ high │ opportunity │ info |
| cards[].e_ids | research workbook | mandatory; the serve layer excludes uncited cards |

### Prompt

```
Write 6-10 insight cards. An insight card is a DEFENSIBLE ARGUMENT THAT CHANGES WHAT SOMEONE DOES - not an observation, and not a score with prose around it. BEFORE WRITING, READ: all four pillar deep-dives in the assessment report, the issue register, the peer table, the sentiment sources, the tech stack and the timeline. The best insights come from JOINING two sources that sit apart - a complaint theme against a process score, a job posting against a platform tenure, a regulator finding against a self-description, a timeline event against a capability. Look for those joins FIRST; a card that could have been written from the score matrix alone is usually an observation. Per card: {ic_id, title, what_text, why_text, so_what_text, alternative_explanation,  severity, severity_rationale, linked_subcap_id, supporting_e_ids[],  validation_question, confidence, claim_label}   title        <=10 words. The argument in a phrase. Not a capability name                alone, not a score.   what_text    35-60 words. The CLAIM about this client, cited. States a state                of the world, not a measurement. Must NOT open with or consist of                a score read-out.   why_text     35-60 words. THE MECHANISM. How does the claimed state produce                the consequence? Name the causal path. If you cannot state a                mechanism you have an observation - either find the mechanism or                drop the card.   so_what_text 30-50 words. The DECISION this implies, for a named owner where                the leadership roster supports naming one. Specific enough to act                on this quarter. Never "consider investing in".   alternative_explanation                20-35 words. The strongest competing explanation you considered                and why the evidence favours yours. If it is equally supported,                say so and set confidence MEDIUM - a card that admits ambiguity                is more useful than one that hides it.   severity     critical │ high │ opportunity │ info, justified by CONSEQUENCE,                not by how far the score sits from the median.   severity_rationale  15-30 words arguing the consequence.   linked_subcap_id                a capability THIS run scored. A card pointing at a cell the pack                does not serve is a dead link and is rejected - 15 of 119                findings had them.   validation_question                the one question that would confirm or kill this card, phrased                for a client conversation and naming an internal document type.                This is a DISCOVERY QUESTION - never a toolkit diagnostic                question. CHALLENGE (R-Layer, per card - this page is where it matters most)  A State the claim and your confidence.  B Search for counter-evidence deliberately. At least ONE contradictory query    per card: "[Entity] [area] failure complaint outage criticism". If the    counter-evidence is strong, the card changes or it goes.  C Is the claim reasonable for this sub-vertical, size tier and regulator?  D Probes, each firing a required extra search before the card may ship:    Input-Output Disconnect; Marketing-Reality Gap; Temporal Inconsistency;    Regulatory Divergence; CX Disconnect; Peer Outlier; Tech Stack Mismatch.  E ACCEPT / REJECT / UNCERTAIN. REJECT -> drop it. UNCERTAIN -> ship with the    alternative stated and confidence MEDIUM or LOW. ENRICHMENT Where the package supports a claim thinly, enrich before dropping: ladder tiers 1-6, then 7-10. Mint E-CC ids for anything new with url + verbatim excerpt + retrieval date. A card upgraded from thin to cited is the highest-value work on this page. DO NOT write one card per pillar for symmetry. Write the cards the evidence supports. Eight cards about two pillars is itself a finding about the client. Zero cards on a completed run is a FAILURE STATE, not an empty state. GATES: S28_insight_integrity (no score-predicate openers, no dead anchors, no zero-card completed runs); S2_accusatory; S1_jargon.
```

---

## T2 · Technology landscape strip

- **Section** `insights.landscape` — **renders on** D2 (Insights)
- **Contract** Confirmed, inferred, claimed and gaps. Four counts recomputed from the register, each tile printing its evidence basis.

### Prompt

No prompt exists in the design specification for this surface. Produce it from the contract above, the standing clauses and the seven-step form in `04-craft/5-prompt-standard.md`.
