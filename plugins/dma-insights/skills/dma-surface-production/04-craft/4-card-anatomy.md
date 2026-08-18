# Card anatomy

Every surface renders into a fixed shell. Knowing the shell tells you what to write and how
long each piece can be — prose written without knowing where it lands is prose that clips
mid-word, which was a measured defect on 501 cards.

## The universal card shell

```
┌─ card ───────────────────────────────────────────────────────────┐
│  card-head                                                        │
│    <h3>            CARD HEADER   2–4 words, sentence case         │
│    badge           COUNT or STATE   right-aligned                 │
├───────────────────────────────────────────────────────────────────┤
│  rows / body                                                      │
│    chip            ID CHIP       the item's own id, monospace     │
│    row title       13px / 600 / line-height 1.35   ≤ 12 words     │
│    eyebrow line    10px / uppercase / letter-spacing .05em        │
│                    THEME · magnitude · platform chips             │
│    chevron         expand affordance, where the row expands       │
├───────────────────────────────────────────────────────────────────┤
│  expansion         inset panel, appears in flow, no overlay       │
└───────────────────────────────────────────────────────────────────┘
```

**What goes where.** The header names the card, never the finding. The row title carries the
claim. The eyebrow carries orientation — theme, then magnitude, then platform. The expansion
carries the argument.

A row title that needs the eyebrow to make sense is too short. An eyebrow that repeats the
title is wasted.

## Per-surface anatomy

### O1 Hero — the only card guaranteed to be read

| Slot | Content | Budget |
|---|---|---|
| Ring | Composite to 1dp | — |
| Ring label | The band word — Building, Competing | 1 word |
| Pillar strip | Four bars, score to 1dp, peer delta arrow | — |
| Posture chip | LEADING / COMPETING / LAGGING / MIXED | vocabulary |
| Basis chip | EVIDENCE / HYBRID / INFERRED | vocabulary |
| Framing line | The gap, quantified and localised | **18–32 words** |
| Firmographics strip | Assets · employees · branches, inline | value + unit each |

The framing line must not open with the composite — it renders beside the number.

### O6 Top findings

| Slot | Content | Budget |
|---|---|---|
| Card header | "Top findings" + count badge | fixed |
| ID chip | `F-nn` | — |
| Row title | A claim, ideally one that rejects the obvious alternative | **≤ 12 words** |
| Eyebrow | THEME, uppercase, one of the client's own domains | **1–3 words** |
| Eyebrow, second | Magnitude, quantified | **6–14 words** |
| Platform chips | Short platform names | — |
| **Expansion** | what · why · so what · rejected alternative | **55–95 words** body |

### I1 Insight card and its modal

Card face: id chip, title, theme eyebrow, priority badge — `ACT NOW` / `PLAN NEXT` / `WATCH`,
rendered in the prototype alongside `CRITICAL` and `OPPORTUNITY`.

Modal sub-headings are literal and uppercase, and each has its own job:

| Heading | Carries | Budget |
|---|---|---|
| **WHAT** | What is observably true, cited | 30–60 words |
| **WHY** | The mechanism — not a restatement of the what | 30–60 words |
| **SO WHAT** | The commercial consequence, one clause | 15–30 words |
| Rejected alternative | The competing explanation and why the evidence favours yours | 20–35 words |

Four tabs: Argument · Evidence · Capabilities · Action.

### DD-1 Synthesis drawer

| Slot | Content | Budget |
|---|---|---|
| Header | Cell id and name | — |
| Score block | Score, confidence band | — |
| Peer ladder | Labelled **Entity** and **Peer median**, with signed delta | — |
| Evidence list | Per item: tier, claim class, recency, publisher, excerpt | excerpt 50–500 |
| Synthesis | With the grounded-on count printed beside it | **40–90 words** |
| Thin marker | Where under three items | — |

### O3 Why-now signal

Five headers, all required. Each is a distinct question and none may be folded into another:

| Header | Answers |
|---|---|
| Trigger | What happened, dated |
| Window | How long it stays open |
| Consequence of waiting | What is lost |
| Cost of acting now | What it takes — stated honestly |
| Why this sequence | Why this before the others |

### P2 Recommendation card and its modal

The highest-value card on D4 and, until this was written, the only one this file did not
describe. Everything below is read off the prototype's `rec-row` and `RecommendationModal`,
which are authoritative for layout and card anatomy.

**Card face.** A half-width column that halves again at tablet width, so every slot is
narrow.

| Slot | Field | Budget / note |
|---|---|---|
| ID chip | `rec_id` | `REC-nnn`, agent-authored, shared with the roadmap |
| Card header | `title` | **4–9 words**, sentence case, no terminal stop. It sits on one flex line beside two badges and a chevron; a 12-word title pushes the badges onto a second row |
| Badge | `phase` | Renders as `Phase <value>`. Send the **ordinal only** (`"1"`), never `"Phase 1 (0–6 mo)"` — the label is the app's |
| Badge | `effort_band` | `S` / `M` / `L`. One letter, rendered raw |
| Eyebrow | `l3_area` | The catalogue L3 platform area. 2–6 words, title case as the catalogue spells it |
| **Sub-header** | `l4_feature` | The L4 feature, **2–6 words**. This is a *catalogue feature name*, not a solution sentence — the prototype's is "Data Cloud", "Workflow Engine". "API-led connectivity layer with the packaged core connector" is a `root_cause` clause wearing a feature's slot |
| Body | `root_cause` | 30–60 words per contract, **line-clamped to 3 lines on the face** (~28 words at 11.5px in a half-width column). The first sentence is the card; the rest is read in the modal. It may not open on an absence — see `01-start-here/3-language.md` |
| Chips | `evidence_ids[]` | Labelled `cites`. Each opens the evidence drawer. This — not `root_cause` prose — is what the prototype calls the row's root cause |
| Footer cell | `validation_gate.threshold` + `.verdict` | `P4C3 >= 2.0` in mono, then a MET / NOT MET badge |
| Footer cell | `len(dma_impact)` | "Cells it moves". **Computed, never sent** |
| Footer cell | `kpi_triple.metric` (+ `.baseline`, `.baseline_as_of`, `.target`) | metric **≤ 8 words**; baseline and target render underneath at 10.5px |

**Modal head.** `rec_id` chip · `l3_area` badge · `l4_feature` badge · `Phase <phase>` ·
`claim_label` · "Effort <effort_band>" · then `title` at 17px. Nothing else fits, and a
`platform` key does not exist on a promoted recommendation — the head prints the run's own
L3 area and L4 feature.

**Modal tabs — four, in this order.** Rationale & notes · DMA impact · Root cause evidence ·
Sequencing.

| Tab | Renders | From |
|---|---|---|
| **Rationale** | Five numbered rows: **1 Root cause** (prose + evidence chips) · **2 Cost of inaction** · **3 Sequencing** (`sequencing_reason` + phase badge) · **4 Expected outcome** (metric · effort · Baseline · Target) · **5 Validation gate** (threshold, verdict, current value, backing cells as clickable chips) | `root_cause`, `evidence_ids`, `cost_of_inaction`, `sequencing_reason`, `kpi_triple`, `validation_gate` |
| **DMA impact** | One row per affected cell: name, `current` → `target`, signed `delta`, and `target_basis` under it | `dma_impact[]` |
| **Root cause evidence** | Per cited id: tier chip, claim class, recency, ERS, source title, the verbatim excerpt in a quote block | the evidence store, via `evidence_ids[]` |
| **Sequencing** | Three columns — **Prerequisites** (the recommendations this one depends on) · **This initiative** · **Unlocks** (the recommendations that depend on it) | `dependencies[]` only, resolved both ways |

**The two things called "prerequisites" are different fields.** `dependencies[]` is a list of
`rec_id`s and drives the modal's Sequencing tab. `prerequisites[]` is a list of readiness
conditions and drives the **separate Readiness card** on D4, above the recommendation list —
never the modal. It takes exactly two shapes, and rows are deduplicated across the page on
`(cell, minimum)`, so `P4C3 >= 2.0` and `P4C3 >= 2.5` are two rows, not one:

```
{cell, minimum, current, verdict}          → progress bar against the minimum, MET/NOT MET
{condition, basis, note}                   → a text condition with its evidence basis
```

A cell-shaped prerequisite with no `minimum` draws no bar and no verdict. Send both numbers
or send the text shape.

**`provenance` is required and was absent on every recommendation of the run measured here.**
`ANALYST` or `DERIVED`, never blank; `DERIVED` means composed from the pack by rule, and 32
clients shipped derived rows presented as analyst judgement.

Two things to know before you send it, because the sources disagree and this file does not
resolve them:

- The **Surface Specification** states `provenance` per recommendation and per starter.
- The **Backend Schema** stores one `provenance_t` per row from the section envelope, and
  the writer fills that column from `sys:provenance` — the **submission-level** argument to
  `submit_page_payload`, whose values are `analyst · derived · producer` and whose **default
  is `producer`**.

So a per-item `ANALYST` validates and is then dropped, and a page submitted without the
argument serves every row as `producer`. Send both: the item field the contract asks for,
and `provenance="analyst"` or `"derived"` on the submission. If a page genuinely mixes the
two, say so in the section and raise it — one class per submission cannot express a mixed
page, and picking silently is the failure mode this note exists to prevent.

**Conversation starters are not in this modal.** P2b is its own card, rendered beside the
recommendation list with its own copy-all control. A starter that only makes sense after
opening a recommendation is a starter written in the wrong place.

### P2b Conversation starter

| Slot | Content | Budget |
|---|---|---|
| Opening shape | gap / peer / timing / their words / contradiction / system | vocabulary, distinct across the set |
| Text | Say-it-aloud | **45–90 words** |
| Follow-up question | A discovery question, never a toolkit diagnostic | 1 sentence |

No codes, no bracketed ids mid-sentence, no score-first opening — an AE reads this out loud.

### T1 Tech stack layer card

| Slot | Content |
|---|---|
| Layer name | Operations & core banking / Customer engagement / Data & analytics / Infrastructure & cloud |
| Pillar tag | The pillar that absorbs a gap at this layer |
| Detection count | "2 of 4 detected" |
| Primary gap marker | On the layer that carries it |
| Rows | vendor · product · status · evidence level |

### H5 Assessment caps and safeguard gates

| Slot | Content | Budget |
|---|---|---|
| Cap rows | kind · ceiling · affected categories · rationale | rationale quoted or closely paraphrased |
| Gate rows | plain label · result · detail | **plain label 8–18 words** |
| Not-run reason | Required wherever the result is not-run | 1 sentence |

## Report section headings the surfaces map to

The assessment report is organised into twelve numbered sections with named sub-headings.
Several map straight onto surfaces, and using the report's own heading as the retrieval target
is faster and more faithful than re-deriving:

| Report section | Sub-headings | Feeds |
|---|---|---|
| 1 Executive Summary | The Bottom Line · Key Strengths · Critical Gaps · Strategic Recommendation | O4, O6, O5 |
| 2 Assessment Context | Institution Profile · Methodology · Evidence Sources · **Proxy Ladders Run** · Limitations | O2, H6, empty states |
| 3 Trend Analysis | Corporate trajectory · Technology trajectory · Sentiment | C1, O8, O9, C4 |
| 4 Issue Register | table · per-issue detail · Severity cap impact | C2, H5 caps |
| 5 Assessment Results | pillar table · score distribution | O1, H4 |
| 6 Platform Landscape | table by platform | T1, T2 |
| 7 Capability-Boundary Analysis | one sub-section per platform | P1 |
| 8 Prioritised Opportunities | formula · ranking · **evidence chain · PATTERN · CHALLENGE · LINKAGE · What to do** | O5, P2, I1 |
| 9 Cost of Inaction | What can be derived · What is not derivable · Non-financial costs | O3 |
| 10 Where Not To Propose | table | P1 exclusions |
| 11 Clarification Trail | Discovery questions · Hypotheses | P2b follow-ups |
| 12 Methodology Integrity | Constrained sources · Validation performed | H5, O10, O11 |

**Section 8's five sub-headings are the model for any recommendation.** Evidence chain, then
pattern, then the steelman and its falsifier, then the linkage to what the client already has,
then one concrete action. Reuse that shape.
