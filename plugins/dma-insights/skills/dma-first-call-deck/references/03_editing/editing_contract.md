# Editing Contract — 22-Slide First Call Pitch Deck

> **Cross-references:**
> - Colors, headline patterns, 9-pt scoring: `references/01_brand/brand_guidelines.md`
> - Overflow formula + font table: `references/03_editing/overflow_rules.md`
> - Industry content verification: `references/06_industry_content/{sv_id}.md`
> - Solution offerings for Slides 17-19: `../02_registries/solution_offerings_registry.md`
> - Heatmap script: `scripts/03_editing/heatmap_editor.py`
> - Slide 13 script: `scripts/03_editing/slide13_editor.py`
> - QA checks: `references/05_qa/qa_rubric.md`

## Table of Contents
1. Slide Classification
2. AIDA Phase Mapping
3. Batch 1: Slides 1, 3 (Turn 3)
4. Batch 2: Slide 6 (Turn 4)
5. Batch 3: Slides 9, 10, 13 (Turn 5)
6. Batch 4: Slide 14 (Turn 6)
7. Batch 5: Slides 16, 17, 18, 19 (Turn 7)
8. Batch 6: Slides 20, 21 (Turn 8)
9. Static Slides (DO NOT CHANGE)
10. Cross-Slide Consistency Matrix
11. XML Editing Rules

---

## 1. Slide Classification

| Category | Slides | Action |
|---|---|---|
| Static — DO NOT CHANGE | 2, 4, 8, 11, 15, 22 | Zero edits |
| Sub-vertical dynamic | 1, 3, 5, 7, 17, 18, 19 | Template carries content; tagline swap + [CLIENT] |
| Assessment-driven | 6, 9, **10**, 13, 14, 16, 20 | Full edit from DMA + client research |
| Minimal edit | 12, 21 | Contact info or label→headline only |

## 2. AIDA Phase → Slide Mapping

| Phase | Slides | Purpose |
|---|---|---|
| Attention (~10%) | 1, 5 | Hook: headline + industry stat |
| Interest (~45%) | 3, 6, 7, 8, 9, **10**, 13, 14 | Their reality |
| Desire (~35%) | 4, 11, 12, 15, 16, 17-19 | Better future |
| Action (~10%) | 20, 21 | Mobilization close |

---

## 3. Batch 1: Cover + Overview (Turn 3)

### SLIDE 1 — Title Cover | 3 shapes | Attention

| Sh | Size px | Font | Content | Edit | Max Chars |
|---|---|---|---|---|---|
| 0 | 730×39 | inherited (~25pt) | "Bring clarity to your complexity" | **REPLACE** with insight headline | ~80 (2 lines) |
| 1 | 619×97 | inherited (~18pt) | SV tagline + "DATE" | **AUTO-SWAP** tagline per SV. Replace DATE with actual date. | ~120 |
| 2 | 121×52 | 14pt | "Client logo" | Replace with client logo image if available | N/A (image) |

**Colors changed:** None.
**Headline pattern:** Big Idea Statement — "Your digital maturity blueprint: where [Client] stands today and the investments that accelerate [outcome]"
**Headline score threshold:** ≥7/9.

---

### SLIDE 3 — Company Overview | 37 shapes | Interest

| Sh | Size px | Font | Content | Edit | Max Chars |
|---|---|---|---|---|---|
| 3 | 763×51 | 23pt | "The data and experience consultants for [SV]" | **AUTO-SWAP** SV descriptor from `../02_registries/subvertical_registry.md` | ~60 |
| All others | various | 9-26pt | Zennify stats (CSAT 4.9/5, Certs 580+, Projects 700+, Data 200+) | **DO NOT CHANGE** | — |

**Colors changed:** None. Existing: #B0EED3 on Sh4 "WHY ZENNIFY" header.
**Headline:** Not required (Zennify positioning slide).

---

## 4. Batch 2: Org Profile (Turn 4)

### SLIDE 6 — Organizational Profile | 40 shapes | Interest

> **⚠️ WAS 7 SHAPES, NOW 40.** Historical contracts described a 2-paragraph layout (Sh3 + Sh5). The template now ships a structured dashboard: quick-facts strip, 3 strategic priorities, 5 key platforms, 3 metric cards. **Every deck currently ships with visible `[CLIENT NAME]`, `[Priority 1 name]`, `[Platform 1]`, `[METRIC 1 LABEL]`, `[Value]` placeholders until updated.**
>
> **Script:** `scripts/03_editing/slide6_editor.py` — MANDATORY for this slide.
>
> **Strategic priorities fallback:** If research report lacks explicit priorities, follow the 3-level fallback chain in `references/05_qa/strategic_priorities_fallback.md` (report → web search → `[DATA NEEDED]`).

**Title + structural — DO NOT CHANGE:**

| Sh | Content | Notes |
|---|---|---|
| 0 | Background shape (top banner tint) | DO NOT CHANGE |
| 3 | Client logo frame (rectangle container) | DO NOT CHANGE geometry |
| 9 | "STATED STRATEGIC PRIORITIES" (section header) | DO NOT CHANGE |
| 19 | "KEY PLATFORMS" (section header) | DO NOT CHANGE |
| 38 | Small icon/picture (bottom-right) | DO NOT CHANGE |
| 39 | "© 2026 Zennify \| Confidential" footer | DO NOT CHANGE |

**Eyebrow + headline — REPLACE text:**

| Sh | Size px | Font | Content | Edit | Max Chars |
|---|---|---|---|---|---|
| 1 | 672×17 | ~11pt uppercase | "WHAT WE KNOW ABOUT [CLIENT NAME]" | **REPLACE** `[CLIENT NAME]` → client name (uppercase) | — |
| 2 | 710×63 | ~26pt | "[Insight-driven headline about the client's position and opportunity]" | **REPLACE** with 1-sentence insight headline | ~130 (2 lines) |

**Client logo — REPLACE image:**

| Sh | Content | Edit |
|---|---|---|
| 4 | "Client \| logo" placeholder text | Replace text with client logo image via `replace_image_in_pptx()` OR clear text if logo unavailable |

**Quick facts strip (4 facts) — REPLACE bracketed values:**

| Sh | Template text | Edit | Source |
|---|---|---|---|
| 5 | "Founded: [Year], [State]" | REPLACE `[Year]`, `[State]` | Research report |
| 6 | "Assets: $[X]B" | REPLACE `[X]` (keep "$" and "B" suffix) | Research report financial baseline |
| 7 | "Branches: [X]+ in [X] states" | REPLACE two `[X]` tokens | Research report |
| 8 | "Employees: ~[X]" | REPLACE `[X]` (keep "~" and rounding) | Research report |

**Strategic Priorities (3 priorities × 3 shapes) — REPLACE text:**

Each priority has 3 shapes: accent strip (teal `#27BBAF`, DO NOT CHANGE color), name (bold), description.

| Priority | Accent Strip | Name (TEXT) | Description (TEXT) |
|---|---|---|---|
| P1 | **Sh10** (keep teal) | **Sh11** | **Sh12** |
| P2 | **Sh13** (keep teal) | **Sh14** | **Sh15** |
| P3 | **Sh16** (keep teal) | **Sh17** | **Sh18** |

- **Sh11/14/17 (Name):** 2–4 word title case (e.g., "Member Growth", "Digital Transformation"). Max ~40 chars.
- **Sh12/15/18 (Description):** 1-sentence description, max ~95 chars. Pattern: fact → strategic implication. NOT "Strong market presence" — YES "Acquisition-led growth (21.9% CAGR) positions [Client] to consolidate fragmented competitors."

**Sourcing protocol:** See `references/05_qa/strategic_priorities_fallback.md` for the 3-level chain (report → web search → `[DATA NEEDED]`). The agent MUST NOT fabricate priorities — prefer `[DATA NEEDED]` flags over plausible-sounding ungrounded claims.

**Key Platforms (up to 5 platforms + 1 summary) — REPLACE text:**

| Sh | Template text | Edit | Notes |
|---|---|---|---|
| 20 | `[Platform 1]` | REPLACE with platform name | Sources: research report tech stack, DMA research utilization data |
| 21 | `[Platform 2]` | REPLACE | Same |
| 22 | `[Platform 3]` | REPLACE | Same |
| 23 | `[Platform 4]` | REPLACE | Same |
| 24 | `[Platform 5]` | REPLACE or leave blank if <5 known | OK to leave `[Platform 5]` as empty string if only 4 platforms confirmed |
| 25 | "[X]+ technologies across the [entity description]" | REPLACE with total count + descriptor (e.g., "60+ technologies across the credit union") | DMA research tech inventory |

**Metric Cards (3 cards × 4 shapes each) — REPLACE text, DO NOT CHANGE colors:**

Each card has 4 shapes: background rectangle (Zennify mint `#E6F5F3`, DO NOT CHANGE), uppercase label, big value text, 1-line context.

| Card | BG Rect | Label (TEXT) | Value (TEXT) | Context (TEXT) |
|---|---|---|---|---|
| M1 | **Sh26** (keep mint) | **Sh27** | **Sh28** | **Sh29** |
| M2 | **Sh30** (keep mint) | **Sh31** | **Sh32** | **Sh33** |
| M3 | **Sh34** (keep mint) | **Sh35** | **Sh36** | **Sh37** |

- **Sh27/31/35 (Label):** Uppercase, 1–3 words (e.g., `MEMBER GROWTH`, `EFFICIENCY RATIO`, `DIGITAL ADOPTION`). Max ~20 chars.
- **Sh28/32/36 (Value):** Large display number (e.g., `+8.2%`, `72%`, `4.86★`, `$2.5B`). Max ~10 chars.
- **Sh29/33/37 (Context):** 1-sentence explanation, max ~60 chars.

**Metric selection guidance (in priority order):**
1. DMA-derived: overall maturity score vs peer median
2. Financial: asset growth YoY, efficiency ratio, revenue growth
3. Scale: member/customer count, branch count, employee count with trajectory
4. Digital: mobile app rating, digital adoption %, online channel share
5. NPS / CSAT if publicly disclosed

**Colors changed:** None. Slide 6 is a **text-only slide** — all colors are preserved from template (teal accent strips, mint metric card backgrounds).

**Headline pattern (Sh2):** Quantified Impact — "[Client]'s [key metric] and [growth descriptor] create a [strong foundation] for [digital outcome]."

**Post-edit verification — pre + post shape count MUST be 40.**

**Font normalization:** Slide 6 ships with DM Sans typefaces throughout — verified clean. Editors use `_editor_common.set_shape_text`, which synthesizes DM Sans runs when paragraphs are empty, preventing font drift during text replacement.

---

## 5. Batch 3: Assessment (Turn 5)

> **Slides in this batch:** 9, 10, 13. All three are score-bearing and must cross-validate before batch commit. Edit in order: Slide 9 → Slide 13 → Slide 10 (Slide 10 synthesizes both).

### SLIDE 9 — What is a DMA? | 23 shapes | STATIC (no per-deck edits)

Slide 9 in the current template is a **static "What is a DMA?" explainer** —
the header ("About the Assessment"), the 4-pillar overview, and the "What we
cover" bullets are all content that ships ready with the template. **No
editor runs on Slide 9.**

The per-deck DMA Summary Dashboard (pillar strips + rec cards + narrative +
strengths panel) lives on **Slide 10**. See the Slide 10 section below.

> **Historical note:** An earlier template revision placed per-deck pillar
> cards with 3-tier benchmark colors on Slide 9. That editor has been
> retired to `scripts/03_editing/deprecated/slide9_editor.py`. If a future
> template revision moves per-deck content back onto Slide 9, a new editor
> would need to be written against the updated role catalogue in
> `color_level_system.SLIDE_9_ROLES` (currently empty).

---

### SLIDE 13 — Key Strengths + Assessment | 46 shapes | Interest

| Sh | Size px | Font | Content | Edit | Max Chars |
|---|---|---|---|---|---|
| 5 | 198×25 | 12pt BOLD | "Key Strengths" | **DO NOT CHANGE** | — |
| 6 | 176×18 | 10pt | Strength bullet 1 | **REPLACE** — describe WHY it's strong, not the score | ~35 (strict 1 line) |
| 7 | 172×18 | 10pt | Strength bullet 2 | **REPLACE** — descriptive, not score label | ~35 |
| 9 | 196×18 | 10pt | Strength bullet 3 | **REPLACE** — evidence-based | ~35 |
| 10 | 171×18 | 10pt | Strength bullet 4 | **REPLACE** — evidence-based | ~35 |

⚠ **Strength bullets describe WHAT makes the area strong — NOT the score.**
The score appears in the adjacent circle indicator (Sh21-34). Don't repeat it.
- WRONG: "Fraud & Risk Mgmt: 2.82 (+0.32)" ← score label, wastes 35 chars
- CORRECT: "Zero enforcements, Verafin ML fraud" ← evidence of strength
- WRONG: "Tech Architecture: 2.82 (+0.32)" ← repeats the score
- CORRECT: "Triple cloud + 6-tool DevOps pipeline" ← what makes it strong
| 11 | 713×60 | 20pt BOLD | Overall narrative headline | **REPLACE** with insight headline | ~130 (65ch × 2 lines) |
| 12 | 427×25 | 12pt BOLD | "[Client] Assessment" | Replace [Client] | ~65 |
| 13 | 427×25 | 12pt BOLD | "[Client] Overall Maturity Industry Comparison" | Replace [Client] | ~65 |
| 14 | 264×40 | 13pt BOLD | "THE ASSESSMENT" | **DO NOT CHANGE** | — |
| 15-18 | 209×20 | 9pt | Four pillar names | **DO NOT CHANGE** | — |

**Pillar level indicators (4 groups: bg rect + circle + number text + label text):**

Each pillar has 4 shapes. FILL edits go to bg rect + circle. TEXT edits go to number + label.
The bg rect and circle use theme scheme colors (accent3-5) which MUST be overridden with
explicit `<a:srgbClr>` when editing. Use `slide13_editor.py --apply-indicators` or python-pptx
`fill.solid()` + `fill.fore_color.rgb = RGBColor(...)` which writes explicit srgbClr.

| Pillar | BG Rect (FILL) | Circle (FILL) | Number (TEXT) | Label (TEXT) |
|--------|---------------|--------------|--------------|-------------|
| P1 | **Sh19** | **Sh20** | Sh21 | Sh22 |
| P2 | **Sh23** | **Sh24** | Sh25 | Sh26 |
| P3 | **Sh27** | **Sh28** | Sh29 | Sh30 |
| P4 | **Sh31** | **Sh32** | Sh33 | Sh34 |

**Editing instructions:**
- **Sh19/23/27/31 (BG Rect):** CHANGE FILL to the 5-level color. Override scheme color → explicit srgbClr.
- **Sh20/24/28/32 (Circle):** CHANGE FILL to the 5-level color (same color as bg rect). Override scheme color.
- **Sh21/25/29/33 (Number):** REPLACE text with level number ("1"-"5"). Text color: #FFFFFF for Level 5, #1C4A4D for 1-4.
- **Sh22/26/30/34 (Label):** REPLACE text with level label. Text color: #FFFFFF for Level 5, #1C4A4D for 1-4.

**5-Level Color System (DIFFERENT fills for bg rect vs circle — from Level_Color_Code.pptx):**

| Level | Label Text | BG Rect Fill | Circle Fill | Number Text Color | Label Text Color |
|---|---|---|---|---|---|
| 1 | Foundational | #FFCB99 | #FE9732 | #F2F4F9 | #1C4A4D |
| 2 | Developing | #C7D3EC | #8094C0 | #F2F4F9 | #1C4A4D |
| 3 | Established | #E6F3FA | #3D81F6 | #F2F4F9 | #1C4A4D |
| 4 | Advanced | #E8F7F6 | #62D7B8 | #F2F4F9 | #1C4A4D |
| 5 | Transformational | #B0EED3 | #27BBAF | #FFFFFF | #1C4A4D |

**Industry comparison bars (Sh46-59):** 8 pairs of number + label shapes. REPLACE scores. COLOR bar fills per 5-level system above.

**Radar Chart (Sh60) + Legend (Sh61) — IMAGE REPLACEMENT:**

| Sh | Type | Size px | Content | Edit |
|---|---|---|---|---|
| 60 | PICTURE | 398×264 | Placeholder radar chart (4-axis spider) | **REPLACE** with generated PNG from `scripts/03_editing/radar_chart_generator.py` |
| 61 | PICTURE | 360×34 | Legend ("Higginbotham Current/Target") | **REPLACE** with generated legend PNG (uses client name) |

**Radar chart has 3 series:**
1. **Industry Average** (gray #8094C0) — peer median per pillar
2. **Client Current** (teal #27BBAF) — actual pillar scores from DMA assessment
3. **Client Target** (dark teal #198478) — target maturity per pillar

**Score consistency validation (MUST pass before generating):**
- Overall score ≈ weighted average of pillar scores (P1: 25%, P2: 30%, P3: 20%, P4: 25%) — tolerance ±0.15
- Each pillar score ≈ average of capability scores within that pillar — tolerance ±0.20
- All scores in 0-5 range
- Target scores > current scores (warn if not)
- Flag inconsistencies BEFORE chart generation — never produce a chart with bad data

**Image generation:** `python scripts/03_editing/radar_chart_generator.py --client "[Name]" --scores '{...}' --medians '{...}' --targets '{...}' --overall X.XX --out-chart radar.png --out-legend legend.png`

**Image replacement method (Google Slides safe):** Use file-swap in `ppt/media/`, NOT `add_picture()`.
1. Parse `ppt/slides/_rels/slide13.xml.rels` to find rId→filename for Sh60 and Sh61
2. Overwrite the target image files with new PNGs (radar chart and legend)
3. Do NOT modify slide XML — relationship IDs and shape positions stay unchanged
Use `radar_chart_generator.py` functions: `find_image_rids()` then `replace_image_in_pptx()`.

**Headline pattern (Sh11):** Paradox — "[Strongest area] anchors the scorecard at [level], while [weakest] presents the highest-value transformation opportunity — aligned with [Client]'s strategy to [objective]."

**DO NOT MODIFY — Slide 13 decorative shapes:**
- Sh0-4: Background rectangles and page number
- Sh8: Separator line
- Sh35: GROUP shape (tick mark container — 4 sub-shapes)
- Sh36-43: Tick mark icons and separator shapes
- Sh44-45, 48-49, 52-53, 56-57: Industry comparison background rectangles

**EDITED shapes (level indicators — fill + text per 5-level system):**
- Sh19-22 (P1), Sh23-26 (P2), Sh27-30 (P3), Sh31-34 (P4): fills and text per instructions above

If ANY of these shapes are accidentally modified, the slide layout breaks. Pre-edit and post-edit shape count MUST be 62.

**Cross-slide check (after editing):** Pillar levels here must match Slide 9 card colors and Slide 14 heatmap levels. Run `scripts/04_qa/cross_slide_checker.py` logic.

---

## 6. Batch 4: Heatmap (Turn 6)

### SLIDE 14 — Capability Heatmap | 73 shapes | Interest

> **TWO TEMPLATE DESIGNS EXIST.** Script auto-detects by shape count:
> - **158 shapes** → NEW progress bar design (bars, medians, accent strips, level labels)
> - **73 shapes** → OLD cell grid design (colored cell backgrounds only)
> **Script:** `scripts/03_editing/heatmap_editor.py` — uses python-pptx, MANDATORY for this slide.

**Legend + Headers — DO NOT CHANGE (except Sh1 headline):**

| Sh | Content | Notes |
|---|---|---|
| 0 | "THE ASSESSMENT \| MATURITY SCORE + INDUSTRY BENCHMARKS" (13pt) | **DO NOT CHANGE** (EYEBROW) |
| 1 | "Capability heat map" (26pt) | **REPLACE** with insight headline. Max ~82ch (2 lines). |
| 2,4,6,8 | Legend items (Above/Below/At/Well below benchmark) | DO NOT CHANGE |
| 9 | "THE ASSESSMENT" (13pt BOLD) | DO NOT CHANGE |
| 12,30,45,60 | Pillar headers (9pt BOLD) | DO NOT CHANGE |

**Score Cells (17 × BOLD 12pt, 49×44px, colored background):**

| Sh | Capability | Edit |
|---|---|---|
| 15 | Digital Strategy & Vision | **REPLACE** score text + **CHANGE FILL** per benchmark |
| 18 | Governance & Risk Appetite | Same |
| 21 | Innovation Management | Same |
| 24 | Culture & Change Enablement | Same |
| 27 | Sustainable Finance & ESG | Same |
| 33 | Digital Marketing & Acquisition | Same |
| 36 | Onboarding & Fulfillment | Same |
| 39 | Omnichannel Servicing | Same |
| 42 | Personalization & Engagement | Same |
| 48 | Process Automation | Same |
| 51 | Operational Risk & Fraud | Same |
| 54 | Compliance & Surveillance | Same |
| 57 | Business Resilience & TPRM | Same |
| 63 | Data Governance | Same |
| 66 | Analytics & AI Enablement | Same |
| 69 | Architecture & Integration | Same |
| 72 | Platform Enablement | Same |

**Score cell background colors (benchmark vs peer median):**

| Condition | Fill Color | Hex |
|---|---|---|
| Score > peer median + 0.2 | Teal | #27BBAF |
| Score within ±0.2 of peer | Light green | #B0EED3 |
| Score < peer − 0.2 | Light orange | #FFCB99 |
| Score < peer − 0.5 | Blue | #058DC7 |

**Score → Level mapping (explicit ranges):**

| Score Range | Level | Fill Color (accent/bar) | Label Text Color |
|---|---|---|---|
| 0.00 – 1.49 | Activating | #F97316 | #F97316 |
| 1.50 – 2.49 | Building | #8094C0 | #4E5E8A |
| 2.50 – 3.49 | Competing | #27BBAF | #198478 |
| 3.50 – 5.00 | Differentiating | #185F60 | #185F60 |

**158-shape per-capability block (8 shapes each, 17 blocks):**

| Offset | Shape | Edit | Fill Color | Border Color | Text Color |
|--------|-------|------|-----------|-------------|-----------|
| +0 | Background card | CHANGE FILL to level card_bg + border to MATCH fill | Activating=#FFF3E8, Building=#F2F4F9, Competing=#E6F5F3, Differentiating=#E8F7F6 | **MUST EQUAL FILL** (same hex) | — |
| +1 | Accent strip | CHANGE FILL per level + border to MATCH fill | Activating=#F97316, Building=#8094C0, Competing=#27BBAF, Differentiating=#185F60 | **MUST EQUAL FILL** (same hex) | — |
| +2 | Capability name | Replace if differs | — | noFill (preserved) | — |
| +3 | Score | REPLACE text only. **NO FILL** in 158-shape (level shown by accent/bar/label) | — | noFill (preserved) | — |
| +4 | Track bar | DO NOT CHANGE fill or border | #E5E7EB | #E5E7EB (fixed) | — |
| +5 | Progress bar | CHANGE WIDTH `round((score/5)×1883700)` + FILL per level + border to MATCH fill | Same as accent strip | **MUST EQUAL FILL** (same hex) | — |
| +6 | Median marker (`cxnSp`) | CHANGE X = `track_x + round((median/5)×1883700)`. **cxnSp connector — never set shape fill, never change width/height/y.** | Line stroke #3D81F6 (preserved) | #3D81F6 (fixed on `<a:ln>`) | — |
| +7 | Level label | REPLACE text (e.g., "BUILDING") + CHANGE FONT COLOR per level | — | noFill (preserved) | Activating=#F97316, Building=#4E5E8A, Competing=#198478, Differentiating=#185F60 |

**⚠️ BORDER INVARIANT (fill-border rule):** Offsets **+0, +1, +5** must have `<a:ln>` stroke equal to their `<a:solidFill>`. Any mismatch = visible visual bug (teal-filled card with purple border). `heatmap_editor.py` enforces this automatically via `set_shape_border()`. Post-edit QA: `cross_slide_checker.py --check-borders` flags any drift as CRITICAL.

**Known template bugs (fixed on first editor run):** Template ships with 3 fill-border mismatches — Sh82 (bg_card #FFF3E8 / border #F2F4F9), Sh87 (progress #F97316 / border #FF9900 unauthorized), Sh124 (bg_card #FFF3E8 / border #F2F4F9). These are corrected the first time `heatmap_editor.py` runs on the template.

**Block base indices (158-shape):**
P1: 17, 25, 33, 41, 49 (5 caps) | P2: 58, 66, 74, 82 (4 caps) | P3: 91, 99, 107, 115 (4 caps) | P4: 124, 132, 140, 148 (4 caps)

**MANDATORY execution:** Run `heatmap_editor.py --pptx [file] --scores [json] --medians [json]`. The script edits all 17 scores + colors in one pass and VERIFIES post-edit. NEVER proceed to next batch if verification fails.

**Headline pattern (Sh0):** Gap→Outcome — "[Best cap] leads at [score]; [weakest] ([score]) and [2nd worst] ([score]) present the highest-value transformation opportunities."

---

## 7. Batch 5: Opportunities + Solutions (Turn 7)

### SLIDE 16 — Opportunities | 14 shapes | Desire

**⚠️ MANDATORY FONT ADJUSTMENTS — automatic via `slide16_editor.py`:**
Font reductions are baked into the editor (Sh3: 26→21pt, Sh8/9/10: 11→9pt,
Sh12: 10→9pt). No separate `font_adjuster.py` invocation required. The
editor also writes `<a:normAutofit>` as a PowerPoint autofit safety net.

| Sh | Size px | Template Font | **Target Font** | Content | Edit | **Max Chars (at target)** |
|---|---|---|---|---|---|---|
| 2 | 264×40 | 13pt BOLD | 13pt (no change) | "OPPORTUNITIES" | **DO NOT CHANGE** (EYEBROW) | — |
| 3 | 589×34 | ~~26pt~~ | **21pt** | "Areas of focus: Key capabilities" | **REPLACE** with insight headline | **~124 (2 lines)** |
| 4 | 736×68 | 15pt | 15pt (no change) | Intro sentence | **REPLACE** with client context | ~267 (89ch × 3 lines) |
| 8 | 427×90 | ~~11pt~~ | **9pt** | Cap 1: Bold name + regular body | **REPLACE** all fields. **Bold header ONLY, body `b="0"`.** | **~665 (target ~300)** |
| 9 | 411×90 | ~~11pt~~ | **9pt** | Cap 2: Same structure | **REPLACE** | **~640 (target ~300)** |
| 10 | 404×90 | ~~11pt~~ | **9pt** | Cap 3: Same structure | **REPLACE** | **~629 (target ~300)** |
| 12 | 192×246 | ~~10pt~~ | **9pt** | OUTCOMES bullets | **REPLACE** with projected outcomes | **~814 (target ~400)** |
| 13 | 183×40 | 13pt BOLD | 13pt (no change) | "OUTCOMES" | **DO NOT CHANGE** | — |

**Card formatting (Sh8/9/10 at 9pt):**
```
Line 1 (BOLD): [Capability Name]
Line 2 (REGULAR, italic): Current: [score] → Target: [target]
Lines 3+ (REGULAR): Why it matters: [opportunity-framed explanation]

NEVER bold the entire card. NEVER include ISS-xxx codes.
```

**Colors changed:** None (font sizes only).
**Headline pattern:** Gap→Outcome — "[N spelled out] capability areas are ready for transformation — investing in them unlocks [outcome 1], [outcome 2], and [outcome 3]."
**Capability selection:** Top 3 gaps from DMA assessment via `scripts/02_planning/solution_inferrer.py`.

---

### SLIDE 17 — Solution Offerings (Col 1-3) | 16 shapes | Desire
### SLIDE 18 — Solution Offerings (Col 4-6) | 16 shapes | Desire (CONDITIONAL)
### SLIDE 19 — Solution Offerings (Col 7-9) | 16 shapes | Desire (CONDITIONAL)

**Slides 18 and 19 are CONDITIONAL.** Only edit if `solution_plan.json` specifies `num_slides ≥ 2` or `≥ 3` respectively. Unedited slides retain template defaults and are skipped during QA.

All three slides share identical 3-column structure.
**Description text color: #B0EED3 (light green).** "RECOMMENDED SOLUTIONS" header: also #B0EED3. **Lock ALL positions and sizes. Text-only replacement.**

**Description shapes (Sh5/11/14) overflow risk:** At 12pt, max ~90–135 chars. Trim descriptions to ≤120 chars (one concise sentence). If needed, reduce from 12pt → 10pt (safe minimum, max ~130–195 chars).

| Sh | Size px | Font | Role | Edit | Max Chars |
|---|---|---|---|---|---|
| 0-2 | AUTO_SHAPE bg | — | 3 column backgrounds | **DO NOT CHANGE** | — |
| 3 | 58×11 | inherited | Slide number | **DO NOT CHANGE** | — |
| 4 | 265×38 | inherited BOLD | Column 1 title | **REPLACE** per offering | ~35 (1 line) |
| 5 | 265-283×43-71 | 11pt | Column 1 description | **REPLACE**. Text color: **#B0EED3** | ~175 |
| 6 | 899×31 | 24pt | "Proven solutions for [SV]" | **AUTO-SWAP** SV label | ~68 |
| 7 | 740×42 | inherited | "RECOMMENDED SOLUTIONS FOR [CLIENT]" | Replace [CLIENT]. Text color: **#B0EED3** | ~50 |
| 9 | 271×246-261 | 9-10pt BOLD | Column 1 capabilities | **REPLACE**. Preserve bold "Key capabilities" as first line header. | ~930 |
| 10 | 265×38 | inherited BOLD | Column 2 title | **REPLACE** | ~35 |
| 11 | 265-277×43-57 | 11pt | Column 2 description | **REPLACE**. Text color: **#B0EED3** | ~184 |
| 12 | 277×206-235 | 9-10pt BOLD | Column 2 capabilities | **REPLACE** | ~800 |
| 13 | 265×38 | inherited BOLD | Column 3 title | **REPLACE** | ~35 |
| 14 | 271-277×43-57 | 11pt | Column 3 description | **REPLACE**. Text color: **#B0EED3** | ~184 |
| 15 | 265-277×235-249 | 9-10pt BOLD | Column 3 capabilities | **REPLACE** | ~900 |

**Colors on this slide:**
- Description text (Sh5, 11, 14): **#B0EED3** (light green)
- "RECOMMENDED SOLUTIONS" header (Sh7): **#B0EED3**
- All other text: inherited (#1C4A4D or black)

**Solution mapping:** 9 offerings from `../02_registries/solution_offerings_registry.md`, selected by `scripts/02_planning/solution_inferrer.py` based on DMA capability gaps. 3 per slide, no duplicates.

---

## 8. Batch 6: Close + Deliver (Turn 8)

### SLIDE 20 — Mobilization Close | 21 shapes | Action

> **NEVER end with "Questions?" — this is a first sales call. Always mobilization.**

**⚠️ MANDATORY FONT + FORMATTING ADJUSTMENTS — automatic via `slide20_editor.py`:**
Font reductions are baked into the editor (Sh0 next-steps body and Sh12
deliverables body: both 11→10pt). No separate `font_adjuster.py` invocation
required. The editor also writes `<a:normAutofit>` for PowerPoint native
autofit. Body paragraphs after the first run inherit regular (non-bold)
formatting via `set_shape_text`'s default bold-reset behavior.

| Sh | Size px | Template Font | **Target Font** | Content | Edit | **Max Chars (at target)** |
|---|---|---|---|---|---|---|
| 0 | 329×284 | ~~11pt BOLD~~ | **10pt** | "YOUR NEXT STEPS" + action items | **REPLACE** with Date \| Action \| Owner table. Min 3 rows. | **~1314** |
| 2 | 752×65 | inherited (~19pt) | ~19pt (no change) | Follow-up narrative | **REPLACE** with goal statement: "[Client] is positioned to [achieve X] by [date] — today's conversation is the first step." | ~120 (2 lines) |
| 3 | 771×94 | inherited (~19pt) | ~19pt (no change) | "Next steps" header | **REPLACE** with insight headline: "Share your feedback so we can deliver a refined maturity model and targeted capability map for [Client]'s leadership team" | ~100 (2 lines) |
| 12 | 284×268 | ~~11pt BOLD~~ | **10pt** | "WHAT WE'LL BRING TO NEXT CALL" + deliverables | **REPLACE** with specific deliverables + dates | **~1160** |

**Sh0/Sh12 body formatting (MANDATORY):** Every body text `<a:rPr>` must include:
```xml
<a:rPr b="0" i="0" lang="en" sz="1000" u="none" cap="none" strike="noStrike">
```
Only the first run per bullet (date/action header) uses `b="1"`. All remaining runs use `b="0"`.

**Colors changed:** None.
**Headline pattern:** The Window — "Share feedback → refined model → capability map → [Client]'s leadership team"

**Required elements (QA Check 11 — Generic Close):**
1. Restatement of key recommendation
2. Action table with dates + owners (Date | Action | Owner)
3. Specific deliverables for next call
4. Goal statement with timeline

---

### SLIDE 21 — Contact | 2 shapes | Action

| Sh | Content | Edit |
|---|---|---|
| 0 | "klastname@zennify.com" | Replace with presenter email |
| 1 | "Let's move forward together." | **DO NOT CHANGE** |

---

## 9. Static & Read-Only Slides

### SLIDE 2 — Welcome | 5 shapes | DO NOT CHANGE
No edits. "Thank you for being here."

### SLIDE 4 — Agenda | 7 shapes | DO NOT CHANGE
Mostly static. Replace headline ONLY if it's a label ("Overview"). Otherwise keep.

### SLIDE 5 — Industry Forces | 14 shapes | READ-ONLY
**VERIFY** correct sub-vertical loaded. Only swap [CLIENT] if present.
Colors: Big stats #139F94 (teal). Headers #1C4A4D. Body #555555.
Cross-check against `references/06_industry_content/{sv_id}.md`.

### SLIDE 7 — Pain Points | 15 shapes | READ-ONLY
**VERIFY** correct sub-vertical. Only swap [CLIENT]. Do NOT edit pain point content.

### SLIDE 8 — DMA Intro | 3 shapes | DO NOT CHANGE
"Digital Maturity Assessment — An outside-in view of your business."

### SLIDE 10 — DMA Summary Dashboard | 44 shapes | Interest

> **⚠️ WAS STATIC, NOW DYNAMIC.** Historical contracts marked this "Why Maturity | 11 shapes | DO NOT CHANGE." The template now ships a 44-shape DMA summary dashboard with client score, peer median, 4 pillar cards (level-coded), 2 competitive strengths, and 3 priority recommendation cards (level-coded). **Edit every deck.**
>
> **Script:** `scripts/03_editing/slide10_editor.py` — uses python-pptx, MANDATORY for color ops.

**Title + eyebrow — DO NOT CHANGE:**

| Sh | Content | Notes |
|---|---|---|
| 0 | "DIGITAL MATURITY ASSESSMENT SUMMARY" (eyebrow, ~11pt) | DO NOT CHANGE |
| 5 | "Digital Maturity Assessment Summary" (off-canvas repeat) | DO NOT CHANGE |
| 6 | "PRIORITY RECOMMENDATIONS" (section header) | DO NOT CHANGE |
| 43 | "COMPETITIVE STRENGTHS" (section header) | DO NOT CHANGE |
| 26-35 | Peer benchmarks legend strip (3 badges + label) | DO NOT CHANGE — static legend |
| 39 | "The outside-in view surfaces the priorities. Your context sharpens them." | DO NOT CHANGE — closing tagline |

**Headline + narrative — REPLACE text, STRIP yellow highlights:**

| Sh | Size px | Font | Content | Edit | Max Chars |
|---|---|---|---|---|---|
| 1 | 526×51 | ~30pt | "Where [Customer name] stands and what comes next" | **REPLACE** `[Customer name]` → client name. **STRIP** `<a:highlight>`. | ~70 (2 lines) |
| 7 | 490×91 | ~11pt | "[Client]'s overall digital maturity score is 2.6 (out of 5), just below the peer median of 2.9. While some capabilities are well developed, foundational gaps in governance, data unification, and operational consistency are slowing momentum and diluting ROI." | **REPLACE** `[Client]` → client name, `2.6` → overall score, `2.9` → peer median, and rewrite sentences 2-3 per deck. **STRIP** `<a:highlight>`. | ~380 (4 lines) |

**⚠️ Sh7 has hardcoded numbers (`2.6`, `2.9`) that are NOT bracketed.** They must be replaced via explicit str_replace or python-pptx, not the `[CLIENT]` auto-swap in `template_preparer.py`. The `slide10_editor.py` script handles this.

**Pillar cards — 4 shapes per pillar (name + insight + accent strip):**

Each pillar has 3 shapes: name header, insight sentence, colored accent strip. The accent strip uses the 4-tier heatmap level palette (not the 3-tier benchmark palette of Slide 9 — see Cross-Slide Consistency Matrix). Strip fill MUST be overridden via explicit `<a:srgbClr>` when the shape inherits scheme colors.

| Pillar | Name (TEXT) | Insight (TEXT) | Accent Strip (FILL) |
|---|---|---|---|
| P1 Strategy & Governance | **Sh13** | **Sh12** | **Sh16** |
| P2 Customer Experience¹ | **Sh9** | **Sh8** | **Sh15** |
| P3 Operations & Compliance | **Sh11** | **Sh10** | **Sh14** |
| P4 Data & Tech | **Sh4** | **Sh3** | **Sh2** |

¹ **Terminology override for credit_unions:** Sh9 = "Member Experience". See `subvertical_registry.md`.

**Editing instructions:**
- **Sh13/9/11/4 (Pillar names):** REPLACE text only if sub-vertical override applies (credit_unions). Otherwise DO NOT CHANGE.
- **Sh12/8/10/3 (Pillar insights):** REPLACE with 1-sentence insight per pillar (70–80 chars). Tone: diagnostic, not prescriptive ("X is strong but Y" — not "We recommend Z"). Must be consistent with Slide 14 heatmap cell content for that pillar.
- **Sh16/15/14/2 (Accent strips):** CHANGE FILL to the 4-tier heatmap level color for that pillar's current maturity level. Convert `schemeClr` → explicit `srgbClr`.

**4-Tier Pillar Accent Color System (matches Slide 14 heatmap levels):**

| Level | Score Range | Accent Fill Hex |
|---|---|---|
| Activating | 0.00–1.49 | #F97316 |
| Building | 1.50–2.49 | #8094C0 |
| Competing | 2.50–3.49 | #27BBAF |
| Differentiating | 3.50–5.00 | #185F60 |

**Competitive Strengths panel — REPLACE bullet text:**

| Sh | Content | Edit | Max Chars |
|---|---|---|---|
| 40 | Background rect (purple-tint) | DO NOT CHANGE | — |
| 41 | Left accent strip | DO NOT CHANGE — Zennify green `#27BBAF` preserved | — |
| 42 | "Digital channel coverage is broad and above peer median ¦ Governance structures in place with clear executive ownership" (2 bullets separated by newline) | **REPLACE** with 2 client-specific strengths. Each ~65 chars, 1 line per bullet. | ~130 total |

**Strengths sourcing:** Pull from Slide 14 heatmap capabilities scoring ≥3.5 (Differentiating) OR above peer median + 0.3. Prefer capabilities that map to named client investments in the research report.

**Priority Recommendations panel — 4 shapes per card × 3 cards, all level-coded:**

Each card has: background rect (light tint), accent strip (bold), level label (uppercase), and name + metrics text. **Three colors must align per card** (card bg + strip + label text), driven by the rec's maturity level.

| Card | BG Rect (FILL) | Accent Strip (FILL) | Level Label (TEXT + COLOR) | Name + Metrics (TEXT) |
|---|---|---|---|---|
| Rec 1 | **Sh17** | **Sh18** | **Sh19** | **Sh36** |
| Rec 2 | **Sh20** | **Sh21** | **Sh22** | **Sh37** |
| Rec 3 | **Sh23** | **Sh24** | **Sh25** | **Sh38** |

**Editing instructions:**
- **Sh17/20/23 (Card BG):** CHANGE FILL to the level's card background tint. Convert scheme → srgbClr.
- **Sh18/21/24 (Accent strip):** CHANGE FILL to the level's accent color.
- **Sh19/22/25 (Level label):** REPLACE text with uppercase level name ("ACTIVATING" / "BUILDING" / "COMPETING" / "DIFFERENTIATING"). CHANGE text color to the level's label text color.
- **Sh36/37/38 (Name + Metrics):** REPLACE with pipe-separated format: `{capability_name} | Maturity: {current} → Target: {target}`. Current score from DMA assessment, target = Slide 16 opportunity target.

**Priority Rec Card Color System (matches Slide 14 heatmap + brand_guidelines §7):**

| Level | Card BG | Accent Strip | Label Text Color |
|---|---|---|---|
| Activating | #FFF3E8 | #F97316 | #C25008 |
| Building | #F2F4F9 | #8094C0 | #4E5E8A |
| Competing | #E6F5F3 | #27BBAF | #198478 |
| Differentiating | #E8F7F6 | #185F60 | #185F60 |

**Rec sourcing:** Pull top 3 opportunities from Slide 16 by gap magnitude (peer median − client score, descending). Rec names, current scores, and target scores MUST match Slide 16 capability cards exactly — run `cross_slide_checker.py`.

**Headline pattern (Sh1):** Static — "Where {client_name} stands and what comes next." No insight-headline rewrite for Sh1; the narrative insight lives in Sh7.

**DO NOT MODIFY — Slide 10 decorative / structural shapes:**
- Sh5: Off-canvas title repeat (rendered off-slide)
- Sh17-25 (card BGs, strips, labels): Geometry is fixed; only FILL and TEXT change
- Sh26-35: Peer benchmarks legend strip (static 3-level badges + "Peer benchmarks" label)
- Sh39: Closing tagline
- Sh40-43: Competitive Strengths panel geometry (bg, accent, header text)

**Post-edit verification — pre + post shape count MUST be 44.**

**Cross-slide check (after editing):** Pillar accent colors (Sh16/15/14/2) MUST match Slide 14 heatmap pillar-level colors AND Slide 13 pillar level indicators. Overall score in Sh7 MUST match Slide 9 Sh13 and Slide 13 overall. Priority rec names in Sh36/37/38 MUST be a subset of Slide 16 opportunity capabilities. Run `scripts/04_qa/cross_slide_checker.py` with `--include-slide-10` flag.

**Font normalization:** The editor uses `_editor_common.set_shape_text` which synthesizes DM Sans runs when replacing text in empty paragraphs, avoiding Calibri/theme-default pollution. The template ships some non-DM-Sans runs but these only affect shapes the editor does not touch; any editor-touched text is normalized to DM Sans on replacement.

**Highlight strip:** Sh1 and Sh7 historically contained `<a:highlight val="FFFF00"/>` template markers on `[Customer name]` and `[Client]` respectively; Sh5 eyebrow has them on `endParaRPr`. `slide10_editor.py` now runs a **slide-wide highlight strip** after editing (catching all shapes, including ones it doesn't otherwise touch), so no separate `highlight_stripper.py` invocation is required for Slide 10. The final deck-wide sweep in `final_highlight_strip.py` is still useful as a belt-and-suspenders verification pass for solution slides.

### SLIDE 11 — Framework | 47 shapes | DO NOT CHANGE
### SLIDE 12 — Two-Step Approach | 41 shapes | MINIMAL EDIT
Replace headline only if it's a label. Contains #059669 "✓ COMPLETE" marker — preserve.

### SLIDE 15 — Discussion | 25 shapes | DO NOT CHANGE
Optional: adapt sub-headline to "Does this match your reality?"

### SLIDE 22 — Appendix | 4 shapes | DO NOT CHANGE

---

## 10. Cross-Slide Consistency Matrix

**Slides 9, 10, 13, 14, 16 must be internally consistent:**

| Element | Slide 9 | Slide 10 | Slide 13 | Slide 14 | Slide 16 |
|---|---|---|---|---|---|
| Overall score | In narrative text (Sh13) | In narrative Sh7 (inline) | In comparison section | — | — |
| Peer median | In Sh13 score text | In narrative Sh7 (inline) | In comparison bar scores | Blue #3D81F6 marker line X-position | — |
| Per-pillar status | Card accent color (3-tier) | Pillar strip fill (4-tier) Sh16/15/14/2 | Circle + rect fill (5-level) | Bar + accent + label (4-level) | — |
| Strongest pillar | Named in Sh4 text | Competitive strength reflected in Sh42 | Highest level indicator | Longest bars, Competing/Differentiating level | — |
| Weakest pillar | Named as opportunity in text | Priority Rec 1 on right panel | Lowest level indicator | Shortest bars, Activating level | Capability card 1 |
| Priority recs (top 3) | — | Sh36/37/38 names + scores | — | — | Opportunity capability cards |

**Any inconsistency = CRITICAL failure.** Run `scripts/04_qa/cross_slide_checker.py --include-slide-10`.

---

## 11. XML Editing Rules

1. **str_replace tool ONLY.** Never sed, awk, or Python regex on slide XML.
2. Replace `<a:t>` text content only. **NEVER** modify `<a:rPr>`, `<a:pPr>`, position `<a:off>`, or size `<a:ext>` attributes.
3. **Exception for Slide 14 ONLY:** Progress bar `<a:ext cx=...>` and median marker `<a:off x=...>` — these encode the data visualization.
4. **Run preservation:** When 2+ runs in a paragraph have different formatting, replace ONLY the `<a:t>` within each run. Never merge or split `<a:r>` elements.
5. **Bullet preservation:** Maintain `<a:pPr lvl="X">` attributes and bullet characters. Never add or remove `<a:p>` elements.
6. **Table cell preservation:** Never change `<a:tcPr>`, `<a:tcW>`, `<a:trHeight>`. Only replace `<a:t>` text.
7. **⚠️ MANDATORY: Remove `<a:highlight>` tags after EVERY edit.** When replacing text in shapes that contain `<a:highlight>`, delete the entire `<a:highlight>...</a:highlight>` element — do not just replace the `<a:t>` text inside it. Run `scripts/03_editing/highlight_stripper.py` at every batch boundary. Yellow highlights are template markers, NOT formatting.
8. **Never create or delete shapes.** Shape count per slide must match pre-edit count exactly.
9. **Color hex UPPERCASE:** `val="1C4A4D"` not `val="1c4a4d"`.
10. **XML escaping:** `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;` in all text content.
11. **Missing data:** Insert `[DATA NEEDED: field_name]` — never fabricate numbers or claims.
12. **DM Sans only.** Never modify `typeface` attributes. No Arial, Calibri, Noto Sans.
13. **Slide 14 uses Office theme (Theme5).** Any `schemeClr` refs on Slide 14 resolve to Microsoft Office default colors (dk1=#000000, accent1=#4472C4), NOT Zennify colors. ALWAYS use explicit `<a:srgbClr val="HEXHEX"/>` for ALL color operations on Slide 14. The `heatmap_editor.py` script uses python-pptx `RGBColor()` which writes explicit srgbClr — this is correct. NEVER use theme color names (accent1, dk1, etc.) in str_replace operations on Slide 14.
14. **Convert scheme colors to explicit srgbClr when editing.** When modifying any shape's fill color (Slides 9, 13, 14), replace the existing `<a:schemeClr>` with `<a:srgbClr val="HEXHEX"/>`. Python-pptx's `fill.solid()` + `fill.fore_color.rgb` does this automatically. For XML str_replace: write `<a:srgbClr val="HEXHEX"/>`, never `<a:schemeClr val="accent3"/>`. Slide 13 indicator shapes (Sh19-34) use scheme refs accent3/accent4/accent5 that MUST be overridden.
15. **158-shape score cells: text only, NO fill.** In the 158-shape heatmap design, score shapes (block offset +3) have NO background fill — the score text sits transparently on the card background. Do NOT call `set_shape_fill()` on score shapes. Level is communicated by accent strip, progress bar, and label. The 73-shape design DOES use score cell fills (it's the only visual indicator there).
16. **Median markers are `<p:cxnSp>` connectors.** The 17 median marker lines on Slide 14 are connector shapes, not regular shapes. Only change the x-position (`<a:off x="..."/>`). NEVER call `set_shape_fill()` on a connector (color is on `<a:ln>`, not shape fill). NEVER change width (must stay 0), height (must stay 128100 EMU), or y-position. The line color #3D81F6 (blue) is preserved automatically.
17. **Slide 10 Sh7 hardcoded score anchors.** Slide 10 Sh7 narrative contains hardcoded scores (template default `2.6` overall, `2.9` peer median) that are NOT inside brackets — they're part of example prose. The `slide10_editor.py` script now **auto-detects** these anchors at runtime by regex (`"maturity score is \d\.\d"` and `"peer median of \d\.\d"`), so the script works correctly regardless of what template values happen to be shipped. No `--normalize-fonts` flag is required; `_editor_common.set_shape_text` handles font consistency for any text it writes.
18. **Slide 10 `[Customer name]` placeholder (resolved).** `template_preparer.py` now covers all bracketed placeholder variants: `[CLIENT NAME]`, `[Client Name]`, `[client name]`, `[Customer name]`, `[Customer Name]`, `[customer name]`, `[CLIENT]`, `[Client]`, `[client]`. Post-prep verification: `placeholder_manifest.json` should show 0 remaining placeholder text on any edited slide. If the QA (`cross_slide_checker.verify_placeholders`) still flags `[Customer name]` or similar, the template_preparer was skipped or the template has a variant not yet listed in the pattern set.

---

## 12. Font Size Registry

This registry defines the safe font size ranges for each critical shape.
**For Slides 14, 16, and 20, font adjustments are baked into the editors**
(`heatmap_editor.py`, `slide16_editor.py`, `slide20_editor.py`) — they apply
the target font at write-time, so no separate `font_adjuster.py` invocation
is required. Editors also set `<a:normAutofit>` as a PowerPoint autofit
safety net for dynamic overflow.

For Slides 1, 6, 17–19 the adjustments are either handled by the editor
(Slide 6) or by the solution-slides editor (17–19). The registry is kept
as the authoritative reference for target sizes; it's the same data the
editors use internally.

### Safe Font Size Ranges

| Slide | Shape | Role | Template Font | Safe Minimum | Max Chars (Template) | Max Chars (Safe Min) |
|---|---|---|---|---|---|---|
| 1 | Sh0 | Title headline | 30pt (layout) | 24pt | ~65 (2 lines) | ~80 (2 lines) |
| 6 | Sh1 | Org profile headline | ~19pt | 17pt | ~100 | ~125 |
| 14 | Sh1 | Heatmap headline | 26pt | 21pt | 82 (2 lines) | 124 (2 lines) |
| **16** | **Sh3** | **Opportunities headline** | **26pt** | **21pt** | **42 (1 line!)** | **124 (2 lines)** |
| **16** | **Sh8/9/10** | **Capability cards** | **11pt** | **9pt** | **421–445** | **629–665** |
| **16** | **Sh12** | **Outcomes bullets** | **10pt** | **9pt** | **659** | **814** |
| 17–19 | Sh5/11/14 | Solution description | 12pt | 10pt | ~90–135 | ~130–195 |
| 17–19 | Sh9/12/15 | Key caps + outcomes | 9–10pt | 8pt | ~800–900 | ~1000+ |
| **20** | **Sh0** | **Next steps body** | **11pt** | **10pt** | **1086** | **1314** |
| **20** | **Sh12** | **Deliverables body** | **11pt** | **10pt** | **960** | **1160** |

**Bold rows = MANDATORY adjustments** — always reduce to safe minimum for these shapes.

### Absolute Minimums

- Headlines: 17pt minimum
- Body text: 7pt minimum
- Labels/captions: 6pt minimum

### Slide 16 Card Formatting (Sh8/9/10)

After reducing font to 9pt, apply this structure per card:
```
Line 1 (BOLD, 9pt): [Capability Name]
Line 2 (REGULAR, 9pt, italic): Current: [score] → Target: [target]
Lines 3+ (REGULAR, 9pt): Why it matters: [explanation using opportunity framing]

NEVER bold the entire card. NEVER include ISS-xxx codes.
Target ~300 chars per card (max ~640 at 9pt).
```

### Slide 20 Body Formatting (Sh0/Sh12)

After reducing font to 10pt, set every body `<a:rPr>` to:
```xml
<a:rPr b="0" i="0" lang="en" sz="1000" u="none" cap="none" strike="noStrike">
```
Only bullet headers (date | action) use `b="1"`. All body runs use `b="0"`.

### Decision Tree

```
1. Calculate max_chars at TEMPLATE font using actual shape dimensions
2. Estimate content length from slide plan
3. If content ≤ max_chars → use template font, no adjustment
4. If content > max_chars:
   a. Trim content first (shorter synonyms, remove modifiers)
   b. If trimmed still overflows → reduce font to Safe Minimum
   c. Recalculate max_chars at reduced font
   d. If still overflows → trim + reduce. Flag [TEXT TRUNCATED] if needed.
```
