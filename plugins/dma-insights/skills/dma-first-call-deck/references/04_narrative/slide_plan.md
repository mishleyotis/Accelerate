# SLIDE PLAN FOR APPROVAL

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## SLIDE PLAN FOR APPROVAL

**Client:** [Full name] | **SV:** [Sub-vertical] | **Date:** [Date]
**Overall:** [X]/5 ([Level]) | **Peer Median:** [Y] | **Delta:** [±Z]

### Big Idea
> "[Client] [situation], but [opportunity] enables [outcome] by [timeframe]."

---

### Pillar Summary

| Pillar | Score | Peer | Delta | Pillar Strip Color (Slide 10) | Level (Slide 13) | Insight |
|--------|-------|------|-------|-------------------------------|-------------------|---------|
| P1 Strategy & Governance | X.XX | X.XX | ±X.XX | #hex (4-tier) | Level N (Label) | [what this means] |
| P2 Customer Experience | X.XX | X.XX | ±X.XX | #hex | Level N | ... |
| P3 Operations & Risk | X.XX | X.XX | ±X.XX | #hex | Level N | ... |
| P4 Data & Technology | X.XX | X.XX | ±X.XX | #hex | Level N | ... |

---

### Slides by Batch

> Each batch = one conversation turn. After presenting each batch, I pause for your "continue."

---

#### BATCH 1 (Turn 2): Cover + Overview — Slides 1, 3

**SLIDE 1 — Cover** (EDIT)

| Shape | Current (Template) | New (After Edit) | Reason |
|-------|-------------------|------------------|--------|
| **Sh0** (headline, ~25pt, max 80ch) | "Bring clarity to your complexity" | "[Your digital maturity blueprint: where [Client] stands today and the investments that accelerate [outcome]]" | Big Idea headline |
| **Sh1** (tagline, ~18pt) | "[SV tagline]. DATE" | "[SV tagline]. [Actual date]" | Date swap |
| **Sh2** (logo) | "Client logo" placeholder | [Client logo image if available, else unchanged] | Branding |
| **Colors** | No changes | No changes | — |

**SLIDE 3 — Company Overview** (MINIMAL EDIT)

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh3** (descriptor) | "The data and experience consultants for [SV]" | Auto-swapped per SV | template_preparer.py |
| All others | Zennify stats | **UNCHANGED** | Static content |

---

#### BATCH 2 (Turn 3): Org Profile — Slide 6

**SLIDE 6 — Org Profile** (EDIT via `slide6_editor.py`, 40 shapes, text-only)

> **⚠️ THIS IS THE NEW 40-SHAPE STRUCTURE. DO NOT use the old Sh3/Sh5 paragraph layout (that was 7 shapes). The template now ships with structured components: quick-facts strip + 3 strategic priorities + 5 key platforms + 3 metric cards.**

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh1** (eyebrow, ~11pt) | "WHAT WE KNOW ABOUT [CLIENT NAME]" | "WHAT WE KNOW ABOUT [CLIENT NAME IN ALL CAPS]" | Client name in uppercase |
| **Sh2** (headline, ~26pt, max 130ch, 2 lines) | "[Insight-driven headline about the client's position and opportunity]" | "[Client]'s [key metric] and [growth descriptor] create a [foundation] for [digital outcome]" | Quantified Impact headline |
| **Sh4** (logo frame) | "Client \| logo" placeholder text | Client logo image (swap via `replace_image_in_pptx`) OR clear text | Branding |
| **Sh5** (founded, ~8pt) | "Founded: [Year], [State]" | "Founded: {year}, {state}" | Research report |
| **Sh6** (assets, ~8pt) | "Assets: $[X]B" | "Assets: ${amount}" | Research report financial baseline |
| **Sh7** (branches, ~8pt) | "Branches: [X]+ in [X] states" | "Branches: {count}+ in {state_count} states" | Research report |
| **Sh8** (employees, ~8pt) | "Employees: ~[X]" | "Employees: ~{count}" | Research report |
| **Sh11** (Priority 1 name, bold) | "[Priority 1 name]" | 2–4 word name (title case) | Level 1 research report → Level 2 web search → Level 3 `[DATA NEEDED]` flag |
| **Sh12** (Priority 1 desc, max 95ch) | "[One-line description...]" | 1-sentence fact→implication | Same fallback chain |
| **Sh14, Sh17** (Priority 2+3 names) | Same template placeholders | Same pattern | Same fallback chain |
| **Sh15, Sh18** (Priority 2+3 descs) | Same template placeholders | Same pattern | Same fallback chain |
| **Sh20–24** (Platform 1–5) | "[Platform 1]" ... "[Platform 5]" | Up to 5 platform names | Research report tech stack + DMA research utilization |
| **Sh25** (platform summary) | "[X]+ technologies across the [entity description]" | "{count}+ technologies across the {entity}" | DMA research tech inventory |
| **Sh27, Sh31, Sh35** (Metric labels, uppercase) | "[METRIC N LABEL]" × 3 | Uppercase 1–3 word labels (e.g., "MEMBER GROWTH", "EFFICIENCY RATIO", "MOBILE APP RATING") | Research report |
| **Sh28, Sh32, Sh36** (Metric values, large) | "[Value]" × 3 | Display number (e.g., "+8.2%", "72%", "4.86★") | Research report |
| **Sh29, Sh33, Sh37** (Metric context, 1-line) | "[One-line context...]" × 3 | 1-sentence context (~60ch) | Research report |
| **Colors** | Template colors preserved | **No color changes** | Text-only slide. Teal strips (`#27BBAF`) + mint card bgs (`#E6F5F3`) untouched |

**DO NOT MODIFY:** Sh0 (top banner), Sh3 (logo container frame), Sh9 ("STATED STRATEGIC PRIORITIES" header), Sh10/13/16 (priority teal accent strips), Sh19 ("KEY PLATFORMS" header), Sh26/30/34 (metric card mint bg), Sh38 (Zennify icon), Sh39 (footer).

**Strategic Priorities Fallback (CRITICAL):**

If fewer than 3 distinct strategic priorities are found in the research report, follow the 3-level chain in `references/05_qa/strategic_priorities_fallback.md`:

1. **Level 1 — Research report**: Look for sections titled "Strategic Priorities", "Strategic Objectives", "Strategic Initiatives", "5-Year Plan", "Key Initiatives", "Investment Priorities", "Growth Strategy". Each priority needs a 2–4 word name + ≥1 supporting fact.
2. **Level 2 — Web search fallback** (max 3 queries, logged to `research_audit/slide6_priorities.json`):
   - `"{client}" strategic plan site:{client_domain}` OR `linkedin.com/company/{slug}`
   - `"{client}" annual report strategic objectives {fiscal_year}`
   - `"{client}" CEO letter shareholders` OR `"{client}" investor day presentation`
   - Source ranking: client site > annual report PDF > verified CEO LinkedIn > trade press. Blocked: Glassdoor, Reddit, snapshots >24mo old.
3. **Level 3 — Graceful degradation**: Insert `[DATA NEEDED: strategic priority N]` flags. `slide6_editor.py` auto-populates these when <3 priorities are supplied. The audit trail logs status (VERIFIED / DATA_NEEDED).

**🚫 NEVER fabricate a priority.** A visible `[DATA NEEDED]` flag is preferable to a plausible-sounding ungrounded claim — the sales rep can fill gaps verbally on the call; they cannot retract a fabricated strategy once it's on a slide.

**Invocation:**
```bash
python3 scripts/03_editing/slide6_editor.py \
  --pptx working/deck.pptx --out working/deck.pptx \
  --client "[Exact Full Client Name]" \
  --eyebrow-client "[CLIENT NAME IN ALL CAPS]" \
  --headline "[Quantified Impact headline]" \
  --quick-facts quick_facts.json \
  --priorities priorities.json \
  --platforms platforms.json \
  --metrics metrics.json \
  --audit-out research_audit/slide6_priorities.json
```

22 text operations, zero color operations. Pre/post shape count MUST equal 40.

---

#### BATCH 3 (Turn 4): Assessment — Slides 9, 13

**SLIDE 9 — DMA Summary** (EDIT)

| Shape | Current (Template) | New | Reason |
|-------|-------------------|-----|--------|
| **Sh1** (sub-headline, 11pt, max 324ch) | "This assessment identifies maturity strengths and gaps across four business-crit..." | "[Client] scores [X]/5 — [strongest] leads, [weakest] presents the highest-value opportunity" | Assessment data |
| **Sh2** (title) | "Where CLIENT stands and what comes next" | "Where [Client] stands and what comes next" | [CLIENT] swap |
| **Sh4** (strongest pillar desc, 10pt, max 132ch) | "[Placeholder strongest pillar text]" | "[Evidence-based description of why this pillar leads]" | Assessment data |
| **Sh5** (strongest pillar name, 10pt BOLD) | "[Placeholder name]" | "[Actual strongest pillar name]" | Assessment data |
| **Sh13** (score narrative, 10pt, max 600ch) | "Higginbotham's digital maturity score of 2.66..." | "[Client]'s score of [X] (out of 5) [above/below] peer median of [Y]..." | Assessment data |
| **Sh14-19** (remaining pillars) | Placeholder names + descriptions | Actual pillar names + evidence descriptions (max 140ch each) | Assessment data |

**⛔ SLIDE 9 — Card accent color changes (MANDATORY: show current fill → new fill with hex):**

> Read the actual template fills BEFORE presenting. The template may use scheme colors
> (accent5, accent6) that resolve to different hex per theme. Show the resolved hex.

| Pillar | Card Shape | Current Template Fill | → New Fill | Benchmark | Score vs Peer | Delta |
|--------|-----------|----------------------|-----------|-----------|--------------|-------|
| P1 Strategy & Governance | **Sh29** | #[read from template] | #[27BBAF/B0EED3/FFCB99] | [above/at/below] | [X.XX] vs [Y.YY] | [±Z.ZZ] |
| P2 Customer Experience | **Sh28** | #[read from template] | #[27BBAF/B0EED3/FFCB99] | [above/at/below] | [X.XX] vs [Y.YY] | [±Z.ZZ] |
| P3 Operations & Risk | **Sh27** | #[read from template] | #[27BBAF/B0EED3/FFCB99] | [above/at/below] | [X.XX] vs [Y.YY] | [±Z.ZZ] |
| P4 Data & Technology | **Sh3** | #[read from template] | #[27BBAF/B0EED3/FFCB99] | [above/at/below] | [X.XX] vs [Y.YY] | [±Z.ZZ] |

> 3-tier: Above (+0.2) → #27BBAF | At (±0.2) → #B0EED3 | Below (−0.2) → #FFCB99
> Mark any row where the color DOES NOT change as "UNCHANGED".

**SLIDE 13 — Key Strengths + Radar** (EDIT)

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh11** (headline, 20pt BOLD, max 130ch) | "Zennify's assessment reveals a solid foundation..." | "[Strongest] anchors at [level], [weakest] = highest-value opportunity" | Paradox headline |
| **Sh12** | "Higginbotham Assessment" | "[Client] Assessment" | Name swap |
| **Sh13** | "Higginbotham Overall Maturity..." | "[Client] Overall Maturity Industry Comparison" | Name swap |
| **Sh6** (strength 1, max 35ch) | "[Template placeholder]" | "[Evidence-based strength — NOT a score label]" | Assessment data |
| **Sh7** (strength 2, max 35ch) | "[Template placeholder]" | "[Evidence-based strength]" | Assessment data |
| **Sh9** (strength 3, max 35ch) | "[Template placeholder]" | "[Evidence-based strength]" | Assessment data |
| **Sh10** (strength 4, max 35ch) | "[Template placeholder]" | "[Evidence-based strength]" | Assessment data |

**⛔ SLIDE 13 — Level indicator color changes (MANDATORY: every cell filled, bg rect ≠ circle):**

> BG rect and circle use DIFFERENT colors per level (verified from Level_Color_Code.pptx).
> Read the actual template fills BEFORE presenting. Show resolved hex, not "scheme:accent3".

| Pillar | Score | Level | Sh (BG) | Current BG Fill | → New BG Fill | Sh (Circle) | Current Circle Fill | → New Circle Fill |
|--------|-------|-------|---------|----------------|--------------|------------|--------------------|--------------------|
| P1 | [X.XX] | [N] [Label] | Sh19 | #[read] | #[FFCB99/C7D3EC/E6F3FA/E8F7F6/B0EED3] | Sh20 | #[read] | #[FE9732/8094C0/3D81F6/62D7B8/27BBAF] |
| P2 | [X.XX] | [N] [Label] | Sh23 | #[read] | #[...] | Sh24 | #[read] | #[...] |
| P3 | [X.XX] | [N] [Label] | Sh27 | #[read] | #[...] | Sh28 | #[read] | #[...] |
| P4 | [X.XX] | [N] [Label] | Sh31 | #[read] | #[...] | Sh32 | #[read] | #[...] |

> Maturity-level reference — the 1–5 SCORE scale from `skills/dma-research/engine/rubric.py` (cuts 1.5 / 2.5 / 3.5 / 4.5), not the four display bands (bg ≠ circle):
> L1 Foundational: bg=#FFCB99, circle=#FE9732 | L2 Developing: bg=#C7D3EC, circle=#8094C0 | L3 Established: bg=#E6F3FA, circle=#3D81F6
> L4 Advanced: bg=#E8F7F6, circle=#62D7B8 | L5 Leading: bg=#B0EED3, circle=#27BBAF
> Mark rows where BOTH fills are UNCHANGED.

**⛔ SLIDE 13 — Level indicator text changes (MANDATORY: show current → new for every cell):**

| Pillar | Sh (num) | Current Num | → New Num | Num Text Color | Sh (label) | Current Label | → New Label | Label Text Color |
|--------|---------|------------|----------|---------------|-----------|--------------|------------|-----------------|
| P1 | Sh21 | "[N]" | "[N]" | #F2F4F9 | Sh22 | "[current]" | "[new]" | #1C4A4D |
| P2 | Sh25 | "[N]" | "[N]" | #F2F4F9 | Sh26 | "[current]" | "[new]" | #1C4A4D |
| P3 | Sh29 | "[N]" | "[N]" | #F2F4F9 | Sh30 | "[current]" | "[new]" | #1C4A4D |
| P4 | Sh33 | "[N]" | "[N]" | #F2F4F9 | Sh34 | "[current]" | "[new]" | #1C4A4D |

> Number text: #F2F4F9 (levels 1-4), #FFFFFF (level 5). Label text: #1C4A4D (all levels).
> Mark rows where text is UNCHANGED.

**SLIDE 13 — Radar chart replacement:**

| Element | Current | New | Method |
|---------|---------|-----|--------|
| **Sh60** (radar chart image) | Placeholder 4-axis spider (Higginbotham) | New radar with: Current [P1,P2,P3,P4], Peer [medians], Target [targets] | File-swap via rId |
| **Sh61** (legend image) | "Higginbotham Current/Target" | "[Client] Current/Target" | File-swap via rId |

> **Radar chart data for generation:**
> | Pillar | Current | Peer Median | Target | Cap Avg Check |
> |--------|---------|-------------|--------|---------------|
> | P1 Strategy & Governance | X.XX | X.XX | X.XX | cap avg=X.XX (Δ=X.XX) |
> | P2 Customer Experience | X.XX | X.XX | X.XX | cap avg=X.XX (Δ=X.XX) |
> | P3 Operations & Risk | X.XX | X.XX | X.XX | cap avg=X.XX (Δ=X.XX) |
> | P4 Data & Technology | X.XX | X.XX | X.XX | cap avg=X.XX (Δ=X.XX) |
> | **Overall** | X.XX | | | weighted=X.XX (Δ=X.XX, tolerance ±0.15) |
> Series colors: Industry Avg #8094C0 | Client Current #27BBAF | Client Target #198478

---

#### BATCH 4 (Turn 5): Heatmap — Slide 14

**SLIDE 14 — Heatmap** (EDIT via `heatmap_editor.py`)

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh1** (headline, 26pt, max 82ch) | "Capability heat map" | "[Best cap] leads at [X.XX]; [worst] at [Y.YY] presents the highest-impact opportunity" | Gap→Outcome headline |

**⛔ MANDATORY: Fill ALL 17 rows with ALL columns. No "..." shortcuts. Every color, every EMU value, every level.**
**The reviewer uses this table to verify the heatmap script output. Missing values = rejected plan.**

**Heatmap capability changes (all 17 template blocks — full names, NO P#C# codes; row 5 is the retired P1C5 block, see the note below the column definitions):**

| # | Capability | Tmpl Score | New Score | Peer | Δ | Tmpl Level | New Level | Bar Fill / Bench Color | Label Text Color | Bar Width (EMU) | Median X (EMU) | Card BG |
|---|-----------|-----------|-----------|------|---|-----------|-----------|----------------------|-----------------|----------------|----------------|---------|
| 1 | Digital Strategy & Vision | 3.1 | [X.XX] | [X.XX] | [±X.XX] | Competing | [Band] | [#FFCB99/#62D7B8/#27BBAF/#139F94] | [#F97316/#4E5E8A/#198478/#139F94] | [round((score/5)×1883700)] | [track_left+round((peer/5)×1883700)] | [#FFF3E8/#F2F4F9/#E6F5F3/#E8F7F6] |
| 2 | Governance & Risk Appetite | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 3 | Innovation Management | 3.2 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 4 | Culture & Change Enablement | 2.9 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 5 | Sustainable Finance & ESG | 2.7 | null | null | — | Building | NOT ASSESSED | #E5E7EB | #6B7280 | 0 | track_left | #FFFFFF |
| 6 | Digital Mktg & Acquisition | 2.6 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 7 | Onboarding & Fulfillment | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 8 | Omnichannel Servicing | 2.7 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 9 | Personalization & Engagement | 2.3 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 10 | Process Automation | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 11 | Operational Risk & Fraud | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 12 | Compliance & Surveillance | 3.2 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 13 | Business Resilience & TPRM | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 14 | Data Governance | 1.7 | [X.XX] | [X.XX] | [±X.XX] | Activating | [...] | [...] | [...] | [...] | [...] | [...] |
| 15 | Analytics & AI Enablement | 2.3 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 16 | Architecture & Integration | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 17 | Platform Enablement | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |

> **Column definitions (every [...] MUST be replaced with an actual value):**
>
> - **Tmpl Score / New Score:** The template's placeholder score → the actual DMA score from the report.
> - **Tmpl Level / New Level:** Score→Band is strict less-than on the RAW score, the app's own rule (`apps/web/lib/bands.js` == `engine.contract.band_of`): <2.00=Activating, <3.00=Building, <4.00=Competing, ≥4.00=Differentiating. There is no fifth band. (Tmpl Level is the template's placeholder score under this rule.)
> - **Bar Fill / Bench Color:** UNIFIED band color for accent strip (+1), progress bar (+5), AND benchmark reference — the app's fills: Activating=`#FFCB99`, Building=`#62D7B8`, Competing=`#27BBAF`, Differentiating=`#139F94`. There is NO separate peer-relative color system — the band determines the color, period. Benchmark line stroke: `#3D81F6` (on `<a:ln>`, NOT shape fill).
> - **Label Text Color:** The TEXT color for the band label (+7), a legibility choice on the card tint: Activating=#F97316, Building=#4E5E8A, Competing=#198478, Differentiating=#139F94.
> - **Bar Width (EMU):** `round((new_score / 5.0) × 1,883,700)`. Track width is 1,883,700 EMU for all templates.
> - **Median X (EMU):** `track_left + round((peer / 5.0) × 1,883,700)`. Track left varies per pillar column (P1=484632, P2=2606040, P3=4727448, P4=6848856). **Show the actual computed integer.**
> - **Card BG:** The card background color for the level: Activating=#FFF3E8, Building=#F2F4F9, Competing=#E6F5F3, Differentiating=#E8F7F6. *Not changed by script — already in template. Shown to verify visual consistency.*
>
> **Row 5 — Sustainable Finance & ESG is the retired P1C5 category.** Catalogue v7.0 has 16 categories (`engine.contract.counts()`); the nine templates are v5.0-shaped and still carry the block. A v7.0 run has no score for it: pass `null` for its score and median and `heatmap_editor.py` renders the block NOT ASSESSED (card #FFFFFF, bar #E5E7EB at zero width, label #6B7280, score "—"). **Never invent a score for it.** Row 17 is the template's label; v7.0's fourth P4 category is Information Security & Cybersecurity. Re-authoring the templates to 16 blocks is an open owner decision.
>
> **Median marker properties (unchanged by script — verify only):**
> - Shape type: `<p:cxnSp>` connector (NOT `<p:sp>`)
> - Line color: #3D81F6 (blue), weight 1.5pt, solid dash
> - Width: 0 (vertical line), Height: 128,100 EMU
> - Only the X position changes. Y, width, height, color are preserved.
>
> **Score cells (offset +3):** Text-only replacement in 158-shape mode. NO fill added. Score text changes from template placeholder to actual score (e.g., "3.1" → "2.22").
>
> **Changes summary (MANDATORY):**
> - Scores changed: [N]/17 (list which stayed same if any)
> - Levels changed: [N]/17 (e.g., "3 changed from Competing→Building, 1 from Activating→Building")
> - Colors changed: [N]/17 (list level transitions that changed bar fill / bench color)
> - Bars resized: [N]/17
> - Medians repositioned: [N]/17

**Cross-slide consistency check (MANDATORY before presenting plan):**
> - Strongest pillar (highest avg of cap scores): [name] — ✓/✗ matches Slide 10 narrative and Slide 13 highest indicator?
> - Weakest pillar (lowest avg): [name] — ✓/✗ matches Slide 10 priority rec framing and Slide 16 opportunity framing?
> - Overall score in Slide 10 narrative = Slide 13 narrative = weighted avg of pillars (±0.15)?
> - P1 pillar-strip color on Slide 10 (Sh16) logically consistent with P1 level on Slide 13 and P1 capability levels on Slide 14?

---

#### BATCH 5 (Turn 6): Opportunities — Slide 16

**SLIDE 16 — Opportunities** (EDIT)

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh3** (headline, 26pt, max 82ch) | "Areas of focus: Key capabilities" | "[N] capability areas are ready for transformation — investing unlocks [outcomes]" | Gap→Outcome |
| **Sh4** (intro, 15pt, max 267ch) | [Template intro text] | [Client-specific context paragraph] | Report data |
| **Sh8** (gap 1, 11pt, max 426ch) | [Placeholder] | Gap 1: [Cap] ([score] vs peer [median], [delta]). Why it matters: [evidence → consequence → opportunity]. Solution: [product] | Top gap |
| **Sh9** (gap 2, max 408ch) | [Placeholder] | Gap 2: [same depth] | 2nd gap |
| **Sh10** (gap 3, max 402ch) | [Placeholder] | Gap 3: [same depth] | 3rd gap |
| **Sh12** (outcomes, 10pt, max 665ch) | [Placeholder outcomes] | 3-5 specific projected outcomes with metrics | Report synthesis |
| **Colors** | No changes | No changes | — |

**SLIDES 17-19 — Solution Offerings** (DO NOT EDIT)

> ⛔ **Slides 17-19 are PL-owned.** Practice Leads decide which solution offerings to place.
> The skill leaves these slides exactly as they appear in the template.
> Do NOT run `solution_inferrer.py` or `solution_slides_editor.py`.
> Do NOT delete, reorder, or populate any solution slide content.
> If the user explicitly asks to edit solution slides, remind them that PLs own this decision and confirm before proceeding.

---

#### BATCH 6 (Turn 7): Close + QA + Deliver — Slides 20, 21

**SLIDE 20 — Close** (EDIT)

| Shape | Current | New | Reason |
|-------|---------|-----|--------|
| **Sh3** (headline, ~19pt, max 100ch) | "Next steps" | "[Business outcome] in [timeframe]: phased [approach] starting with [quick win]" | The Window headline |
| **Sh0** (action table, 11pt, max 1080ch) | "YOUR NEXT STEPS" placeholder | Date \| Action \| Owner table (min 3 rows) | Mobilization |
| **Sh12** (deliverables, 11pt, max 893ch) | "WHAT WE'LL BRING TO NEXT CALL" placeholder | Specific deliverables + dates (min 3 items) | Follow-up commitment |
| **Sh2** (goal statement, ~19pt, max 120ch) | Follow-up narrative placeholder | "[Client] is positioned to [X] by [date] — today's conversation is the first step." | Close |
| **Colors** | No changes | No changes | — |

**SLIDE 21 — Contact** (EDIT)

| Shape | Current | New |
|-------|---------|-----|
| **Sh0** | "klastname@zennify.com" | [Presenter email — or DATA NEEDED] |

---

### Opportunity Language Self-Check (MANDATORY)
> Before presenting, scan the ENTIRE plan above for these exact patterns and reframe:
> - "no [X]" → "[X] represents a high-value opportunity" or "[X]-ready"
> - "lacks [X]" → "positioned to establish [X]"
> - "not found" → "not yet deployed — presenting opportunity for"
> - "missing" → "opportunity to introduce"
> - "gap" (when describing client state) → "delta" or "opportunity area"
> - "deficit/weakness" → "area of focus"
>
> **List each reframe performed:**
> | Original phrase | Reframed to |
> |-----------------|-------------|
> | [phrase] | [replacement] |

### Data Needed
> [List fields not extractable from uploaded reports]

---

**⛔ STOP. Wait for "approved." Do NOT download templates or edit anything.**

---

### Turn 2: Batch 1 — Cover (Slide 1) | 3-4 tool calls

**After user approval only.**

Download template (1 call) → Unpack via `scripts/01_intake/template_preparer.py` (1 call, also does [CLIENT]→name swap on ALL slides) → View Slide 1 XML (1 call) → Edit Slide 1 headline (1 str_replace call).

**Slide 3:** `template_preparer.py` already swapped [CLIENT]. The SV descriptor is baked into the template. Do NOT view or edit Slide 3 — it's correct as-is. Zero tool calls on Slide 3.

**After editing:** Repack PPTX → convert edited slides to images → present in chat:
```bash
# Pack, convert to images, show
python3 scripts/00_util/pack_pptx.py unpacked/ working/deck.pptx
soffice --headless --convert-to pdf working/deck.pptx --outdir working/
pdftoppm -png -f 1 -l 3 working/deck.pdf working/slide  # Slides 1-3
```
**Present:** Show Slide 1 and Slide 3 images. "Batch 1 — Slides 1, 3 edited. [changes summary]."

**Per-batch QA:** Run Check #13 protocol on Slide 1 (render → view → autofix → re-render). Also: Opportunity language. ⛔ STOP.**

---

### Turn 3: Batch 2 — Org Profile (Slide 6) | 4-5 tool calls

**Read:** `references/03_editing/editing_contract.md` (Slide 6, 40-shape spec) + `references/05_qa/strategic_priorities_fallback.md` (priorities fallback chain).

**Slide 6 (Organizational Profile, 40 shapes) — MANDATORY: Run `scripts/03_editing/slide6_editor.py`.**

The slide is a structured dashboard: eyebrow + headline + 4 quick facts + 3 strategic priorities + up to 5 key platforms + 3 metric cards. **Text-only slide — no color operations.**

**Pre-flight:** Extract structured fields from client research report:
- `quick_facts.json` — founded year/state, assets, branches, states, employees, entity descriptor
- `priorities.json` — up to 3 strategic priorities (name + description + source)
- `platforms.json` — up to 5 platform names from tech stack
- `metrics.json` — exactly 3 metric cards (label + value + context)

**Strategic priorities fallback protocol (critical):**

If fewer than 3 priorities are found in the research report, follow the 3-level chain in `references/05_qa/strategic_priorities_fallback.md`:
1. **Level 1** — Parse report for section titles like "Strategic Priorities", "Strategic Objectives", "5-Year Plan", "Key Initiatives". Extract distinct 2–4 word names with ≥1 supporting fact each.
2. **Level 2** — If <3 found, run up to 3 web searches:
   - `"{client}" strategic plan site:{client_domain}`
   - `"{client}" annual report strategic objectives {fiscal_year}`
   - `"{client}" CEO letter shareholders` OR `"{client}" investor day presentation`
   - Source ranking: client site > annual report PDF > CEO thought leadership > trade press. Blocked: Glassdoor, Reddit, archived snapshots >24mo old.
3. **Level 3** — If still <3, auto-populate `[DATA NEEDED: strategic priority N]` flags. The editor does this automatically when <3 are passed in. Audit trail written to `research_audit/slide6_priorities.json`.

**NEVER fabricate a priority.** A `[DATA NEEDED]` flag is preferable to a plausible-sounding ungrounded claim — it protects the sales call.

**Invoke:**
```bash
python3 scripts/03_editing/slide6_editor.py \
  --pptx working/deck.pptx --out working/deck.pptx \
  --client "[Exact Full Client Name]" \
  --eyebrow-client "[CLIENT NAME IN ALL CAPS]" \
  --headline "[Quantified Impact headline — max ~130 chars, 2 lines]" \
  --quick-facts quick_facts.json \
  --priorities priorities.json \
  --platforms platforms.json \
  --metrics metrics.json \
  --audit-out research_audit/slide6_priorities.json
```

Script performs 22 text-only operations. Post-edit shape count MUST equal 40.

**DO NOT MODIFY:** Sh0 (top banner), Sh3 (logo frame), Sh9 (priorities section header), Sh10/13/16 (priority accent strips — teal `#27BBAF`), Sh19 (platforms header), Sh26/30/34 (metric card backgrounds — mint `#E6F5F3`), Sh38 (icon), Sh39 (footer). These are structural and must not be touched.

**After editing:** Repack → convert Slide 6 to image → present.
**Per-batch QA:** Run Check #13 protocol on Slide 6 (render → view → autofix → re-render). Extra checks: no raw `[Priority N name]` / `[Platform N]` / `[METRIC N LABEL]` / `[Value]` placeholders survive (auto-checked by `cross_slide_checker.py`); `[DATA NEEDED]` flags are acceptable but flagged as warnings — review `research_audit/slide6_priorities.json` before delivery; headline ≤2 lines on render. ⛔ STOP.

---

### Turn 4: Batch 3 — Assessment (Slides 9, 10, 13) | 5 tool calls MAX

**Read:** `references/03_editing/editing_contract.md` (Slides 10, 13) + `references/_generated/color_authority.md`.

**Edit order: Slide 13 → Slide 10.** Slide 10 synthesizes scores + levels from the same data as Slide 13, so editing 13 first lets you catch input inconsistencies before they cascade.

**Slide 9 is STATIC** — no editor runs, no per-deck changes. The current template ships Slide 9 as a "What is a DMA?" explainer with 23 shapes; per-deck DMA Summary content lives on Slide 10.

**Slide 13 (46 shapes):** Run `scripts/03_editing/slide13_editor.py` — edits strength bullets (Sh6/7/9/10), headline (Sh11), titles with client name (Sh12/13), and 4 pillar indicator groups (Sh19-34) derived via `score_to_level_5tier`.

**Slide 10 (DMA Summary Dashboard, 44 shapes) — MANDATORY: Run `scripts/03_editing/slide10_editor.py`.**

Write pillars.json, recs.json, strengths.json from the slide plan, then invoke:
```bash
python3 scripts/03_editing/slide10_editor.py \
  --pptx working/deck.pptx --out working/deck.pptx \
  --client "[Exact Full Client Name]" \
  --subvertical [sv_id] \
  --overall-score X.X --peer-median Y.Y \
  --pillars pillars.json \
  --recs recs.json \
  --strengths strengths.json
```

The editor dispatches every color write via `apply_color_role` (using `color_level_system.SLIDE_10_ROLES`): 4 pillar accent strips (4-tier level colors), 3 priority rec cards (bg + strip + label_text triplets, all level-coded), 4 pillar insight sentences, 2 competitive strength bullets, Sh7 narrative surgical replace (`[Client]` + shipped overall/peer scores auto-detected by regex), Sh1 headline `[Customer name]` swap, and optional P2 pillar name override (Sh9) for `credit_unions` / `insurance_brokerages` / `insurance_carriers`. Sh4 pillar-name height is auto-normalized to match Sh9/11/13; Sh6 "PRIORITY RECOMMENDATIONS" is repositioned up 10px to clear the Data Governance rec card in LibreOffice PDF rendering.

Highlight stripping is automatic — the editor runs a slide-wide strip post-save catching `<a:highlight>` markers on any text shape including the ones it doesn't otherwise touch.

**MANDATORY: Generate radar chart + legend via `scripts/03_editing/radar_chart_generator.py`.**
Pass `--client '[Exact Full Client Name]'` from the fact bank. For `credit_unions` sub-vertical, also pass `--terminology '{"Customer Experience": "Member Experience"}'`.
Post-generation checks: radar PNG > 20KB, legend contains correct client name (not "Higginbotham" or any other default — use `--verify` flag to confirm). If wrong name in legend, re-run with correct `--client`.
Replace the radar + legend images via python-pptx rId swap.

**DO NOT MODIFY:** Group shapes, separator lines, tick mark pictures, background rectangles. Only edit shapes declared in `SLIDE_10_ROLES` (or `SLIDE_13_ROLES` for S13). Shapes outside the role catalogue are "don't touch" by design.

**Pre/post shape count:** Slide 10 must equal 44, Slide 13 must equal 46. The editors enforce this via `verify_shape_count` pre-flight gates.

**After editing:** Repack → convert Slides 10, 13 to images → present in chat.
**Per-batch QA:** Run Check #13 protocol on Slides 10, 13 (render → view → autofix → re-render). Extra checks: run `python3 scripts/04_qa/cross_slide_checker.py --pptx working/deck.pptx --input input.json` — config-driven verification of every per-shape color, cross-slide score consistency, zero leftover placeholders (`[Customer name]`, `[Client]`, `Higginbotham`, etc.), zero `<a:highlight>` markers, shape count gates. Radar chart legible + correct client name. ⛔ STOP.

### Turn 5: Batch 4 — Heatmap (Slide 14) | 3-4 tool calls

**MANDATORY: Run `scripts/03_editing/heatmap_editor.py` — do NOT manually edit Slide 14.**

1. Write scores.json + medians.json from the slide plan (1 bash call)
2. Run: `python3 scripts/03_editing/heatmap_editor.py --pptx working/deck.pptx --scores scores.json --medians medians.json --out working/deck.pptx` (1 bash call)
3. Script replaces all 17 scores + cell colors + verifies. If verification fails → re-run.
4. Edit headline (Sh1 — NOT Sh0 which is the eyebrow) via str_replace on unpacked XML (1 str_replace call)
5. Repack → convert Slide 14 to image → present (1 bash call)

**Post-edit MANDATORY checks:**
- All 17 scores match slide plan (script verifies automatically)
- No Calibri/Arial fonts (grep typeface= in slide14.xml)
- Headline is data-centric with business outcome, not DMA jargon

**After editing:** Repack → convert Slide 14 to image → present in chat.
**Per-batch QA:** Run Check #13 protocol on Slide 14 (render → view → autofix → re-render). Extra checks: all 16 scored bars visible with the app's band colors (see `references/_generated/color_authority.md` — Activating=#FFCB99, Building=#62D7B8, Competing=#27BBAF, Differentiating=#139F94) and the retired P1C5 block rendered NOT ASSESSED. Median connectors (#3D81F6) correctly positioned, labels readable. Score text verification (from script audit). Run `cross_slide_checker.py` which auto-verifies Slide 14 ↔ Slide 13 ↔ Slide 10 level consistency via config-derived expectations. ⛔ STOP.

### Turn 6: Batch 5 — Opportunities (Slide 16) | 4 tool calls MAX

**Read:** `references/03_editing/editing_contract.md` (Slide 16).

**Slides 17-19 — DO NOT EDIT.** Solution slides are PL-owned. Leave as template defaults.

**Slide 16 MANDATORY font adjustments (apply BEFORE writing content):**
- Sh3 headline: reduce from 26pt → 21pt (max 124 chars at 2 lines)
- Sh8/9/10 capability cards: reduce from 11pt → 9pt (max ~640 chars each)
- Sh12 outcomes: reduce from 10pt → 9pt (max ~814 chars)
- Sh8/9/10 formatting: BOLD header line only, all body text `b="0"` (regular weight)

Edit Slide 16 manually (font adjustments + content).

**After editing:** Repack → run visual overflow inspector → convert Slide 16 to image → present in chat.
**Present:** Show Slide 16 image. Confirm Slides 17-19 left untouched for PLs.
**Per-batch QA:** Run Check #13 protocol on Slide 16 only (render → view → autofix → re-render). Extra checks: opportunity language. ⛔ STOP.

---

### Turn 7: Batch 6 + QA + Deliver — Close + QA + Deliver | 5 tool calls MAX

Edit Slides 20, 21.

**FINAL QA (all 13 checks):**

**Checks 1-12:**
```bash
python3 scripts/04_qa/qa_checker.py --unpacked-dir unpacked/ --subvertical {sv_id} --json --out qa_report.json
```

**Check #13 — FULL DECK visual render + autofix:**
```bash
# Autofix all edited slides
python3 scripts/04_qa/slide_autofix.py \
  --pptx working/deck.pptx \
  --slides 1,6,9,10,13,14,16,20 \
  --out working/deck.pptx \
  --report autofix_report.json

# Render ALL edited slides to PNG (17-19 excluded — PL-owned)
python3 scripts/04_qa/render_and_inspect.py \
  --pptx working/deck.pptx \
  --slides 1,3,6,9,10,13,14,16,20,21 \
  --outdir qa_renders/
```

**VIEW EVERY RENDERED PNG — no exceptions:**
```
view qa_renders/slide_01.png
view qa_renders/slide_03.png
view qa_renders/slide_06.png
view qa_renders/slide_09.png
view qa_renders/slide_13.png
view qa_renders/slide_14.png
view qa_renders/slide_16.png
view qa_renders/slide_20.png
view qa_renders/slide_21.png
```

For each image, run the 7-point visual check (text clipping, cross-shape overlap, font readability, layout balance, placeholder remnants, color accuracy, yellow highlights). If ANY issue → apply fix escalation (L1→L4) → re-render → re-view.

**If autofix_report.json shows `redo_needed > 0`:**
Present to user: "Final QA found [N] shapes that need content rewrites — font reduction alone can't fix them. Here's what needs to change: [details]. Shall I rewrite and re-render?"

**Only after ALL 13 checks pass:**

**ABSOLUTE LAST STEP — Final Highlight Strip:**
```bash
python3 scripts/04_qa/final_highlight_strip.py \
  --pptx working/deck.pptx \
  --out working/deck.pptx
```
This unpacks the PPTX, strips ALL `<a:highlight>` elements from ALL slides (not just edited ones), repacks, and VERIFIES zero remain. If verification fails (exit code 1), do NOT deliver — inspect the flagged slides manually and fix.

**Then re-render the full deck one more time to confirm no visual regressions:**
```bash
python3 scripts/04_qa/render_and_inspect.py \
  --pptx working/deck.pptx \
  --slides 1,6,9,10,13,14,16,20 \
  --outdir qa_renders_final/
```
VIEW each PNG to confirm the highlight removal didn't break any text formatting.

**Deliver:** Copy final PPTX to `/mnt/user-data/outputs/`. Present the file + the rendered slide PNGs from qa_renders_final/ + QA verdict + autofix summary.

**Present:** "[Client] First Call Deck — [N] slides edited, [M] font adjustments auto-applied, [H] highlights stripped, QA PASS. [Download link]." Show all edited slide thumbnails from qa_renders_final/.

---
