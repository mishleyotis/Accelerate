# Narrative Style Guide

## Headline Writing: The #1 Rule

**Every headline is a full sentence stating an insight with specifics. Never a label.**

### Label vs. Insight

| ✗ Label (FAIL) | ✓ Insight (PASS) |
|---|---|
| Market Overview | Credit union digital adoption accelerated 3x since 2020, creating urgency |
| Digital Maturity Assessment Summary | Acme CU scores 2.4/5, trailing peers by 0.6 across all four pillars |
| The Assessment | Data & Technology gaps at 1.8/5 represent Acme's most critical maturity barrier |
| Areas of Focus | Three capabilities—Digital Onboarding, Analytics, and API Integration—close 70% of the gap |
| Roadmap | A 16-week phased roadmap moves Acme from 2.4 to 3.2, matching peer median |
| Next Steps | Approving the diagnostic by March 15 enables a Q2 quick-win deployment |

### DMA Headline Patterns (21 slides)

| Slide | Pattern |
|---|---|
| 1 (Title) | [Client] Digital Maturity Assessment |
| 2 (Static intro) | DO NOT CHANGE — pre-set Zennify intro slide. (Historical note: older narrative guides labeled Slide 2 as "Org Profile" — that was the old template numbering. Current template puts Org Profile on Slide 6.) |
| 3 (Summary) | [Client] scores [X]/5 overall, [above/below] peer median of [Y] |
| 4-5 (Static) | DO NOT CHANGE — headlines are pre-set |
| 6 (Org Profile) | REWRITE Sh2 headline (Quantified Impact, max ~130 chars, 2 lines). Populate 4 quick facts + 3 strategic priorities (with fallback per `../05_qa/strategic_priorities_fallback.md` if report is thin) + up to 5 key platforms + 3 metric cards. Headline pattern: "[Client]'s [key metric] and [growth descriptor] create a [strong foundation] for [digital outcome]." NO color operations. |
| 7 (Assessment) | [Client] shows [strongest pillar] strength at [score] but trails in [weakest] at [score] |
| 8 (Heatmap) | [N] of [total] capabilities score below benchmark, concentrated in [pillar] |
| 9 (Discussion) | DO NOT CHANGE |
| 10 (DMA Summary Dashboard) | DO NOT rewrite headline (Sh1 is static: "Where [Client] stands and what comes next"). REWRITE narrative Sh7 (3 sentences: score vs peer, strengths, gaps) + 4 pillar insights (1 sentence each, diagnostic tone) + 2 competitive strengths (1 line each) + 3 priority rec names/metrics. Level colors drive everything — see editing_contract §5. |
| 11 (Roadmap) | A [N]-phase roadmap targets [score] maturity by [timeframe], starting with [quick win] |
| 12 (Next Steps) | Approving the diagnostic by [date] positions [Client] for [specific outcome] |
| 13 (Thank You) | DO NOT CHANGE — update contact info only |
| **Appendix (14–21, hidden by default)** | |
| 14 (Framework) | DO NOT CHANGE — pre-set framework overview |
| 15 (Why Assess) | EDIT PLACEHOLDERS — replace client name references only |
| 16 (Capability) | DO NOT CHANGE — pre-set assessment visual |
| 17 (Four Pillars) | DO NOT CHANGE — check for hardcoded org names, replace if found |
| 18 (Levels Detail) | DO NOT CHANGE — pre-set staircase |
| 19 (Five Levels) | DO NOT CHANGE — pre-set descriptions |
| 20 (Peer Compare) | [Client] trails peer median by [X] overall, with [pillar] showing the widest gap |
| 21 (Color Palette) | **NEVER INCLUDE IN OUTPUT** — brand reference only |

### Construction Rules

1. **Start with data**: "2.4/5" not "low maturity"
2. **State what it means**: "trailing peers by 0.6" not "there is a gap"
3. **Include specifics**: Names, numbers, timeframes, pillar names
4. **End with implication**: "creating urgency" / "enabling Q2 launch"
5. **Length**: 10–20 words. Under 10 is suspicious. Over 25 fails Glance Test.
6. **Contains a verb**: If no verb, it's a label.

### The Storyline Test

Read all headlines top-to-bottom. They must tell the complete story without reading body text.

> "Acme CU serves 120K members with $2.1B in assets. They score 2.4/5, trailing peers by 0.6.
> Data & Technology is the weakest pillar at 1.8. Three key capabilities close 70% of the gap.
> A 16-week roadmap targets 3.2 maturity. Approving by March 15 enables Q2 deployment."

If the story has holes, the headlines need rewriting.

---

## Client-is-Hero Principle

The client is Luke Skywalker / Frodo. Zennify is Yoda / Gandalf.

| ✓ Hero language (client) | ✗ Self-promotion (Zennify) |
|---|---|
| "You will transform member onboarding" | "Zennify will transform your onboarding" |
| "Your team can achieve 3.2 maturity" | "Our solution delivers 3.2 maturity" |
| "[Client] is positioned to lead in digital lending" | "Zennify's innovative approach leads digital lending" |

### Acceptable Zennify references
- "Zennify recommends..." / "Our assessment reveals..."
- "We've seen institutions like yours achieve..."
- "The framework helps you identify..."

### Violation patterns to detect
- "Zennify/We" + [transform, revolutionize, deliver, achieve, drive, lead, create, build]
- "Our solution" + achievement verb
- Self-aggrandizing: "innovative", "superior", "cutting-edge", "world-class", "best-in-class"

### Exempt slides
Slides 4-6 (methodology) describe Zennify's framework — these naturally use "we" and are exempt.

---

## MECE Test

For every set of supporting points on a slide:

1. **Pairwise merge check**: Can any two points be combined? → Overlap → fix
2. **Missing factor check**: What would a skeptic say is missing? → Gap → fix
3. **Prove headline check**: Do all points together prove the headline? → If not → restructure

---

## Writing Voice

| Do | Don't |
|---|---|
| Confident, not arrogant | "We believe this might possibly help" |
| Specific always | "Some improvement in certain areas" |
| Active voice | "The assessment was conducted by our team" |
| Second person for client | "The institution's digital capabilities" instead of "Your digital capabilities" |
| Forward-looking | "Previously we analyzed" without implication |

### Word Economy

| Wordy | Concise |
|---|---|
| "In order to" | "To" |
| "At this point in time" | "Now" |
| "Due to the fact that" | "Because" |
| "A large number of" | "[specific number]" |
| "Leverage synergies" | [specific action] |

### Numbers

- Always specific from the source document
- Appropriate precision: 2.41 not 2.4089
- Provide context: "2.4/5 (vs. peer median 3.0)"
- Show impact: "0.6 gap = ~$2.1M in unrealized efficiency"
- Compare to benchmarks: "Below the 3.0 industry median"

---

## Source-Anchored Reframing: What's Allowed

ALLOWED (reframing with same semantic content):
- Directional claims from data: "trailing", "leading", "below benchmark"
- Calculated deltas: "0.6 gap implies X capability deficit"
- Inferred urgency from trends: "accelerating 3x → creating time pressure"
- Benchmark comparisons: "below the 3.0 industry median"

PROHIBITED (adds meaning not in source):
- Emotional adjectives absent from source: "dangerously", "critically"
- Invented consequences: "causing market loss" (unless source quantifies)
- Added moral judgment: "must act now" (unless source recommends)
- Extrapolated projections not in source data

THE TEST: Could you defend the headline by pointing to a specific sentence in the source document? If yes → allowed. If no → fabrication.

## DMA Headline Edge Cases
For each DMA headline pattern in the existing guide, add fallback rules:
- Slide 7: If strongest/weakest tied → use the pillar with more L3+ capabilities. If gap < 0.3 → "shows balanced maturity across pillars, with [pillar] slightly leading at [score]"
- Slide 8: If all capabilities above benchmark → "All [N] capabilities meet or exceed benchmark, with [pillar] showing strongest performance". If >75% below → "The assessment reveals broad gaps, with [N] of [total] capabilities below benchmark, concentrated in [pillar]"
- Slide 10: DMA Summary Dashboard. If <3 priority recommendations exist (rare — would mean client has <3 below-benchmark capabilities across 17) → leave 3rd card geometry intact and fill with "Emerging strength | Maturity: {X} → Target: {Y}" for a capability scoring at Competing level with room to reach Differentiating. If the overall score EQUALS peer median (delta < 0.05) → narrative Sh7 opens with "{Client} scores at peer median ({X}/5), with distinct strengths and concentrated gaps" instead of above/below framing.
- Slide 11: If report has no timeline → "[Client]'s roadmap sequence prioritizes [quick win] first, followed by [medium-term], then [long-term]" (phase-based instead of time-based)

---

## Gap → Opportunity Reframing Protocol

Every gap statement MUST be immediately followed by the opportunity it creates.

**Rules:**
1. The word "no" followed by a capability name is ALWAYS banned. Rewrite as an investment opportunity.
2. No internal reference codes (ISS-xxx, subcap IDs, etc.) on any client-facing slide. Rewrite as plain business language.
3. Every data point on Slides 7, 9, 13, 16 must pass the "So What → So That" test: if a fact doesn't lead to an action, cut it.

**Pattern:** `[Current state] positions [Client] to [outcome] through [action].`

See `references/01_brand/brand_guidelines.md` — Gap → Opportunity Reframing Table for the full banned-phrases list and required rewrites.

---

## Headline Rules (Font-Aware)

Every editable headline MUST contain at least one numeric data point (score, dollar amount, percentage, count). Generic headlines without data are banned.

| Slide | Rule | Max Chars (at target font) |
|---|---|---|
| Slide 1 Sh0 | Narrative blueprint format, 65–80 chars. NEVER use `Client: stat` colon format. | 80 at 24pt |
| Slide 6 Sh1 | `[Client]'s [anchor metric] [differentiator] create(s) a strong foundation for [outcome]` | 125 at 17pt |
| Slide 9 Sh2 | MUST include: overall score, peer median comparison, strongest pillar, weakest pillar. | 100 at 17pt |
| Slide 14 Sh1 | `[Top cap] leads at [score], while [weakest 1] ([score]) and [weakest 2] ([score]) present the highest-impact opportunities` | 124 at 21pt |
| Slide 16 Sh3 | **MUST reduce font from 26pt → 21pt.** `[N spelled out] capability areas are ready for transformation — investing in them unlocks [outcome 1], [outcome 2], and [outcome 3]` | 124 at 21pt |
| Slide 20 Sh3 | `Share your feedback so we can deliver a refined maturity model and targeted capability map for [Client]'s [next session / leadership]` | ~100 at ~19pt |
