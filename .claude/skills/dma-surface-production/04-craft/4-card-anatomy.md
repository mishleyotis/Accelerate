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
