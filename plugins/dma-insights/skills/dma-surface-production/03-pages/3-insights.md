# Page: insights

Two sections. Cards must be claims, not topics. The landscape strip recomputes its counts from the tech-stack register, so techstack can be produced before or after but the counts must reconcile.

**2 sections · 2 surfaces.** Submit with `submit_page_payload(run_id, page='insights', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `insights` | yes | I1 | D2 |
| `landscape` | yes | T2 | D2 |

---

## I1 · Insight cards

- **Section** `insights.insights` — **renders on** D2 (Insights)
- **Contract** Triage layout grouped by priority, pillar or theme. Each card carries a claim as its title and opens a four-tab modal.

### A claim, not a topic

This is the whole of the surface and the one thing it is repeatedly graded down for, so it comes first.

| A topic | A claim |
|---|---|
| Names a subject | Asserts something that could be false |
| Survives any evidence | Fails if a specific fact turns out otherwise |
| Ends the reader's thought | Starts the reader's argument |
| "Data quality is a challenge" | "Three parallel cores, not under-investment, is the constraint" |

The test: **write the sentence that would make this card wrong.** If you cannot, the card asserts nothing and it is a topic. That sentence is `alternative_explanation` — which is why a card with no competing explanation is usually a card with no claim, and why the field is not optional in spirit even where the contract permits an empty one.

Second test: **could this card have been written from the score matrix alone?** If yes it is an observation. The cards that land come from JOINING two sources that sit apart — a complaint theme against a process score, a job posting against a platform tenure, a regulator finding against a self-description, a timeline event against a capability. Look for those joins first.

### Must present

Six to ten cards, each a defensible argument: what, why it matters, what to do, with severity and the capability it anchors on.

Zero cards on a completed run is a **failure state**, not an empty state.

No card may open with a score read-out; the `what_text` is a claim, not a metric.

Every `linked_subcap_id` must resolve to a served cell — dead links were 15 of 119.

### Every field renders. None of them is metadata.

Measured on a promoted run: the reasoning was written, stored, served — and displayed by nothing. That is the entire substance of a page being read as shallow. All of these now render, so write them as if a client is reading them, because one is.

| Field | Where it lands | What an empty one costs |
|---|---|---|
| `severity_rationale` | Beside the severity chip | A severity with no argument reads as a mood, and the first question in the room is "why critical?" |
| `alternative_explanation` | In the modal, under the claim | The card looks like the only reading anyone considered — the fastest way to lose a room that has considered another |
| `validation_question` | The modal's closing line | The AE has a claim and no next move. This field is the conversation |
| `claim_label` | On the card face | The reader cannot tell a fact from an inference, so they discount both |
| `r_layer` | Not rendered; audited | Nothing on screen, and AG-01 blocks the submission |

`severity` is justified by CONSEQUENCE, never by how far a score sits from a median. A wide gap on a capability nothing depends on is `info`; a narrow gap on the capability three others wait for is `critical`. The vocabulary is `critical │ high │ opportunity │ info` and the app maps each to a triage flag — nothing falls through to a default.

### The theme lens, and where its data actually comes from

D2 groups by priority, pillar or **theme**. An insight card has no `theme` field: the I1 contract does not define one, `insight_cards` has no column, and **you must not send one** — an invented item key is a contract fork.

The theme is real, though, and it is yours to control. **O6 findings carry `theme`** from a closed vocabulary, together with the cells each finding bears on, and the app derives a card's theme from the finding that shares the card's cell — then, failing that, from a finding in the same category, recording which rung answered.

So the lever is the OVERLAP:

- A card whose `linked_subcap_id` is a cell an O6 finding also links is themed, and grouped with its finding's siblings.
- A card whose cell no finding touches is grouped by pillar and labelled *no theme derivable*. Not an error — but if half the cards land there, the findings and the cards are about different assessments, and that is the defect to fix.
- The same applies to `pillar_id`: **do not send it.** A cell id begins with its pillar (`P4C1.3.1` → `P4`), so the app reads it. Sending a pillar that disagrees with the card's own cell creates two answers to one question.

The vocabulary, from O6 (see `03-pages/2-overview.md`) — upper case, 1–3 words:

```
DATA FOUNDATION │ WORKFLOW │ DECISIONING │ CHANNELS │ TIMING │
RISK & COMPLIANCE │ OPERATING MODEL
```

**No residual bucket.** There is no "Other" theme and you must not invent one. A finding that fits none of the seven is a finding whose theme has not been decided yet — decide it. `OPERATING MODEL` is the widest of the seven and takes most orphans honestly; reaching for it is a judgement, dumping into it is not.

### The gates this page dies on

- **AG-03** fires per ITEM. Every card's own `supporting_e_ids` must be non-empty — the section envelope's citations do not stand in, because a reader drills into the card. An inference cites the source it was drawn FROM. A card that claims a find with an empty list is a contradiction, not an empty state.
- **AG-01** blocks a ranked or causal claim with no `r_layer`, and an insight card is both by construction: it ranks by severity and asserts a mechanism. Record `{hypothesis, counter, domain_test, probes_run[], verdict, confidence}` per card. Method: `04-craft/1-reasoning.md`.
- **AG-02** — counts are computed. Where a card states how much it rests on, the number is the length of the citation list.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| cards[].what/why/so_what | Assessment report deep dives; research workbook | the analyst's argument, restated for an AE |
| cards[].linked_subcap_id | scoring workbook | must resolve to a cell this run serves |
| cards[].severity | producer | critical │ high │ opportunity │ info |
| cards[].severity_rationale | producer | 15–30 words arguing the CONSEQUENCE |
| cards[].alternative_explanation | producer | the competing reading, and why yours wins |
| cards[].validation_question | producer | a discovery question naming an internal document type |
| cards[].supporting_e_ids | research workbook + enrichment | mandatory per card; AG-03 |
| the card's theme | **not a field** | derived from the O6 finding sharing its cell |
| the card's pillar | **not a field** | read from the cell id's leading token |

### Prompt

```
Write 6-10 insight cards. An insight card is a DEFENSIBLE ARGUMENT THAT CHANGES WHAT SOMEONE DOES - not an observation, and not a score with prose around it. BEFORE WRITING, READ: all four pillar deep-dives in the assessment report, the issue register, the peer table, the sentiment sources, the tech stack and the timeline. The best insights come from JOINING two sources that sit apart - a complaint theme against a process score, a job posting against a platform tenure, a regulator finding against a self-description, a timeline event against a capability. Look for those joins FIRST; a card that could have been written from the score matrix alone is usually an observation. Per card: {ic_id, title, what_text, why_text, so_what_text, alternative_explanation,  severity, severity_rationale, linked_subcap_id, supporting_e_ids[],  validation_question, confidence, claim_label}   title        <=10 words. The argument in a phrase. Not a capability name                alone, not a score.   what_text    35-60 words. The CLAIM about this client, cited. States a state                of the world, not a measurement. Must NOT open with or consist of                a score read-out.   why_text     35-60 words. THE MECHANISM. How does the claimed state produce                the consequence? Name the causal path. If you cannot state a                mechanism you have an observation - either find the mechanism or                drop the card.   so_what_text 30-50 words. The DECISION this implies, for a named owner where                the leadership roster supports naming one. Specific enough to act                on this quarter. Never "consider investing in".   alternative_explanation                20-35 words. The strongest competing explanation you considered                and why the evidence favours yours. If it is equally supported,                say so and set confidence MEDIUM - a card that admits ambiguity                is more useful than one that hides it. Write the sentence that                would make this card WRONG; if you cannot, you have a topic.   severity     critical │ high │ opportunity │ info, justified by CONSEQUENCE,                not by how far the score sits from the median.   severity_rationale  15-30 words arguing the consequence. A severity with no                argument reads as a mood.   linked_subcap_id                a capability THIS run scored. A card pointing at a cell the pack                does not serve is a dead link and is rejected - 15 of 119                findings had them. PREFER a cell an O6 finding also links: the                theme lens derives the card's theme from that overlap, and a                card no finding touches groups as "no theme derivable".   supporting_e_ids                mandatory per card (AG-03). The section envelope does not stand                in - the reader drills into the card.   validation_question                the one question that would confirm or kill this card, phrased                for a client conversation and naming an internal document type.                This is a DISCOVERY QUESTION - never a toolkit diagnostic                question. DO NOT SEND: theme, pillar_id. Both are DERIVED by the app - theme from the O6 finding sharing your cell, pillar from the cell id's leading token. Sending either creates a second answer to one question. CHALLENGE (R-Layer, per card - this page is where it matters most)  A State the claim and your confidence.  B Search for counter-evidence deliberately. At least ONE contradictory query    per card: "[Entity] [area] failure complaint outage criticism". If the    counter-evidence is strong, the card changes or it goes.  C Is the claim reasonable for this sub-vertical, size tier and regulator?  D Probes, each firing a required extra search before the card may ship:    Input-Output Disconnect; Marketing-Reality Gap; Temporal Inconsistency;    Regulatory Divergence; CX Disconnect; Peer Outlier; Tech Stack Mismatch.  E ACCEPT / REJECT / UNCERTAIN. REJECT -> drop it. UNCERTAIN -> ship with the    alternative stated and confidence MEDIUM or LOW. Record the whole thing as    r_layer: AG-01 blocks a ranked or causal claim without it, and a card is    both. ENRICHMENT Where the package supports a claim thinly, enrich before dropping: ladder tiers 1-6, then 7-10. Register anything new through register_evidence with url + verbatim excerpt + retrieval date, and use the id the server gives back. A card upgraded from thin to cited is the highest-value work on this page. DO NOT write one card per pillar for symmetry. Write the cards the evidence supports. Eight cards about two pillars is itself a finding about the client. Zero cards on a completed run is a FAILURE STATE, not an empty state. GATES: AG-01 (r_layer per card); AG-03 (per-card citations); S28_insight_integrity (no score-predicate openers, no dead anchors, no zero-card completed runs); S2_accusatory; S1_jargon.
```

---

## T2 · Technology landscape strip

- **Section** `insights.landscape` — **renders on** D2 (Insights)
- **Contract** Confirmed, inferred, claimed and gaps. Four counts recomputed from the register, each tile printing its evidence basis.

### Must present

Four tiles, `kind` one of `CONFIRMED │ INFERRED │ CLAIMED │ GAPS`, each `{kind, count, basis, detail, named_items[]}`.

**The counts are recomputed from the techstack register and are never stored** (invariant 8). The four must sum to the register. So this section cannot be produced honestly before T1 is settled: if you write it first, write it again afterwards. `reconciles_to_register` is the assertion that you did.

**`basis` prints on the tile.** A bare count invites certainty; `5 · T1–T3 evidence` tells the reader what kind of 5. A tile with a count and no basis is the surface's characteristic defect.

**The GAPS tile names its platforms** in `named_items[]`. A gap count with no names is unactionable, and the reader's next question is always "which".

Every register row must carry a status from `CONFIRMED │ INFERRED │ CLAIMED │ ABSENT`, or the strip cannot be recomputed at all. That vocabulary is enforced on the techstack page by **CG-09** — plain TEXT column, exact case.

**Do not send `landscape.summary`.** The column exists and is deliberately unbound: the only summary line in the corpus belongs to the TECHSTACK page (T1), and this column's DDL comment imported it across a page boundary. A summary written here is discarded at promotion and duplicates T1's job.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| tiles[].kind | contract | CONFIRMED │ INFERRED │ CLAIMED │ GAPS |
| tiles[].count | **computed** | length of the matching register rows — never asserted |
| tiles[].basis | producer | the tier mix behind the count, printed on the tile |
| tiles[].named_items | tech register | the GAPS tile names the platforms |
| reconciles_to_register | producer | the assertion that the four counts sum to T1 |

### Prompt

```
Produce the technology landscape strip. It is a RECOUNT, not an analysis: four tiles whose numbers come from the tech-stack register you produced on the techstack page, recomputed here rather than restated. Per tile: {kind, count, basis, detail, named_items[]}   kind        CONFIRMED | INFERRED | CLAIMED | GAPS.   count       COMPUTED: the number of register rows carrying that status.               The four counts MUST sum to the register's row count. Never store               a count you did not count (invariant 8); AG-02 checks it.   basis       PRINTED ON THE TILE. What kind of count this is: the tier mix               behind it, in the form "5 · T1-T3 evidence". A bare count invites               a certainty the evidence does not carry.   detail      one line a reader can act on: what these rows have in common,               or what would move them to a firmer status.   named_items GAPS names the platforms. A gap count with no names is               unactionable. For the other three tiles, name them where the               list is short enough to be useful. RECONCILE before emitting: pull your own techstack register and count it. If the four tiles do not sum to it, the register changed after you wrote this - recount, do not adjust. Emit reconciles_to_register as the record that you did. DO NOT emit a summary line. That column is unbound: the corpus's one summary line belongs to T1 on the techstack page, and a second one here would be a second answer. GATES: AG-02 (counts computed); CG-09 on the register's status vocabulary; cross-surface reconciliation T2 <-> T1.
```
