---
name: dma-first-call-deck
description: >
  Generates Zennify-branded DMA First Call Pitch Decks for 9 financial services
  sub-verticals (CIB Banking, Commercial Lending, Credit Unions, Farm Credit,
  Insurance Brokerages, Insurance Carriers, Retail Banking, Wealth Asset Management,
  Wealth RIAs). ALWAYS use this skill when the user mentions: first call, pitch deck,
  first meeting deck, intro deck, DMA pitch, DMA first call, pre-assessment deck,
  prospect deck, sales deck for DMA, or any request to create a first-meeting
  presentation for a financial services client. Also trigger when 9 sub-vertical
  PPTX templates are referenced, when the user asks to create a deck from DMA
  assessment data for a new client, or when generating a deck that introduces
  Zennify's DMA offering to a prospect. This skill handles pre-assessment pitch
  decks ONLY — post-assessment DMA deliverables use the zennify-narrative skill.
---

# DMA First Call Deck Builder

Build first-meeting pitch decks: AIDA framework (80% Sales + 20% Consultant), opportunity framing, 12 QA checks.

---

## Reading manifest — by phase

Read only what the turn needs. Everything else is reached by the file map below.

| Phase | Read | Why |
|---|---|---|
| Every turn | this file's HARD RULES, COLOR AUTHORITY, Hard Constraints | the non-negotiables |
| Turn 1 (intake) | `references/02_registries/subvertical_registry.md` | the sub-vertical id and template |
| Turn 2 (plan) | `references/04_narrative/slide_plan.md` | the batch plan and the per-turn scripts |
| Turns 3–6 (build) | `references/03_editing/editing_contract.md`, `references/04_narrative/headline_rewrite_playbook.md`, `references/06_industry_content/{sv_id}.md` | shape specs, headlines, industry text |
| Turn 7 (QA) | `references/05_qa/qa_rubric.md`, `references/05_qa/narrative_traps.md` | the twelve checks |
| On a colour question | `references/_generated/color_authority.md` | the one owner, generated |

## Skill File Map

```
dma-first-call-deck/
├── SKILL.md                              ← YOU ARE HERE
│
├── references/
│   ├── 01_brand/                         ← Voice, colors, fonts, headlines
│   │   ├── brand_guidelines.md
│   │   └── communication_frameworks.md
│   ├── 02_registries/                    ← Sub-vertical + solution lookups
│   │   ├── subvertical_registry.md
│   │   └── solution_offerings_registry.md
│   ├── 03_editing/                       ← Per-slide shape specs + overflow
│   │   ├── editing_contract.md
│   │   └── overflow_rules.md
│   ├── 04_narrative/                     ← Headline writing + story structure
│   │   ├── slide_plan.md                  ← the slide-by-slide plan (Turn 2)
│   │   ├── headline_rewrite_playbook.md
│   │   ├── headline_exemplars.md
│   │   └── narrative_style_guide.md
│   ├── 05_qa/                            ← Quality checks + anti-patterns
│   │   ├── qa_rubric.md
│   │   ├── narrative_traps.md
│   │   └── source_anchoring_protocol.md
│   └── 06_industry_content/              ← Slides 5+7 text per sub-vertical
│       └── {sv_id}.md                       (9 files)
│
├── references/01_brand/color_level_system.yaml   ← the colour module's mirror (scripts/utils/sync_config_yaml.py keeps them equal)
├── references/_generated/input_dependency_graph.md ← what each slide reads (scripts/utils/check_docs_in_sync.py checks it)
├── schemas/
│   ├── fact_bank.schema.json
│   └── slide_plan.schema.json
│
└── scripts/
    ├── 01_intake/                        ← SV selection + template prep + data extraction
    │   ├── subvertical_selector.py          Run: Turn 2
    │   ├── template_preparer.py             Run: Turn 3
    │   └── fact_extractor.py                Run: Turn 1 (parses both report formats)
    ├── 02_planning/                      ← Headlines + solution mapping
    │   ├── headline_injector.py
    │   ├── headline_scorer.py
    │   ├── storyline_tester.py
    │   └── solution_inferrer.py             ⛔ NOT AUTO-RUN — PL-owned decision
    ├── 03_editing/                       ← Complex slide editors (color + size changes)
    │   ├── _editor_common.py                Shared: config-driven dispatcher + utilities
    │   ├── heatmap_editor.py                Run: Turn 6 (158-shape Slide 14, fill+border, 4-tier)
    │   ├── slide13_editor.py                Run: Turn 5 (46-shape Slide 13, maturity-level 1–5 indicators)
    │   ├── slide10_editor.py                Run: Turn 5 (44-shape Slide 10, 4-tier pillar + rec)
    │   ├── slide16_editor.py                Run: Turn 5 (14-shape Slide 16, opportunity cards)
    │   ├── slide20_editor.py                Run: Turn 5 (21-shape Slide 20, mobilization)
    │   ├── slide6_editor.py                 Run: Turn 3 (40-shape Slide 6, text + priorities fallback)
    │   ├── radar_chart_generator.py          Run: Turn 5 (Slide 13 radar image + legend)
    │   ├── solution_slides_editor.py        ⛔ NOT AUTO-RUN — Slides 17-19 are PL-owned
    │   └── deprecated/slide9_editor.py      Retired Batch 2 — Slide 9 is now static
    ├── 04_qa/                            ← All quality checks
    │   ├── qa_checker.py
    │   ├── cross_slide_checker.py
    │   ├── opportunity_language_checker.py
    │   ├── word_economy_checker.py
    │   ├── overflow_checker.py                (supplementary math-based pre-check)
    │   ├── visual_overflow_inspector.py       (supplementary shape-level estimation)
    │   ├── render_and_inspect.py              Run: EVERY BATCH — renders slides to PNG for Claude to VIEW
    │   ├── slide_autofix.py                   Run: EVERY BATCH — auto-reduces fonts, flags trims/redos
    │   ├── final_highlight_strip.py           Run: ABSOLUTE LAST STEP — strips + verifies zero highlights on packed PPTX
    │   └── narrative_trap_detector.py
    └── requirements.txt
```

### What to Read When
See Turn descriptions above — each Turn lists its required references and scripts.
---

## ⛔ HARD RULES

1. **DO NOT use `ask_user_input_v0`.** Never show interactive buttons. The reports contain everything.
2. **Max 5 tool calls per turn.** Count them. Split across turns if needed.
3. **NEVER edit slides before presenting the slide plan AND receiving user approval.** Present plan → STOP → wait.
4. **Infer EVERYTHING from uploaded documents.** The ONLY acceptable question: "Please upload your DMA assessment and client research report."
5. **Do NOT preemptively search the web or invoke connectors.** Max 1 web search per batch, only for specific missing facts.
6. **QA at every batch boundary.** Show changes → wait for "continue."
7. **Read reference files incrementally** — only what the current turn requires.
8. **SKIP unchanged slides entirely.** If a slide is static or already correct: do NOT view it, do NOT edit it, do NOT QA it, do NOT convert it to an image. Save every tool call for slides that actually change.
9. **Use Python scripts for complex XML edits.** When a slide has many shapes or mixed bold/regular formatting (like Slide 14 heatmap with 158 shapes or Slide 10 dashboard with 44), write a targeted Python script in one bash call rather than dozens of individual str_replace calls. The script reads XML, replaces only `<a:t>` content within existing `<a:r>` runs, preserves all formatting. This is NOT regex on XML — it's structured text replacement within parsed elements.
10. **Pre-check before viewing.** Before spending a tool call to view a slide, ask: "Am I editing this slide in THIS batch?" If no → skip. "Do I already know what text to replace from the editing contract?" If yes → go straight to the edit.
8. **Plan-to-contract reconciliation:** Before presenting the slide plan, cross-check every content block against `references/03_editing/editing_contract.md`. Every draft must map to a specific shape number (Sh#), fit within its max char limit, use the correct color scheme, and follow opportunity language rules. If the plan says "Sh8" but the contract says Slide 6 only has Sh0-Sh6 — that's wrong.
11. **Slide 14 theme chain.** Slide 14 chains to `theme4.xml` (master5), NOT the Zennify brand theme. All color edits on Slide 14 MUST use explicit hex values (srgbClr), never scheme colors. The `heatmap_editor.py` script handles this correctly — it reads the role catalogue from `color_level_system.py` and dispatches writes via `apply_color_role`, which always writes `srgbClr`.
12. **Median markers are connectors.** The 17 median markers on Slide 14 are `<p:cxnSp>` connector shapes. Only change x-position. NEVER change width (0), height (128100), y-position, or call set_shape_fill. The line color #3D81F6 (blue) is on `<a:ln>`, not shape fill.
13. **Post-edit highlight strip + final verification.** After EVERY batch of XML edits, run `python3 scripts/03_editing/highlight_stripper.py --unpacked-dir unpacked/`. AND as the ABSOLUTE LAST STEP before delivery, run `python3 scripts/04_qa/final_highlight_strip.py --pptx working/deck.pptx --out working/deck.pptx` which strips ALL highlights from ALL slides (including unedited ones) and VERIFIES zero remain. The QA checker auto-fails any deck with remaining `<a:highlight>` elements. Yellow highlights are template markers — they MUST NOT appear in the delivered deck. If `final_highlight_strip.py` exits with code 1, do NOT deliver.
14. **Opportunity-first framing.** NEVER state what the client lacks. ALWAYS state what the investment enables. Run `scripts/04_qa/opportunity_language_checker.py` after every content batch. Any "no [capability]" phrasing is an automatic rewrite. Internal codes (ISS-xxx) are banned from all slides.
15. **Sub-vertical terminology.** For `credit_unions`, replace ALL instances of "Customer" with "Member" and "Customer Experience" with "Member Experience" across ALL edited slides. This includes: pillar headers, body text, radar chart labels, heatmap column headers, the Slide 1 subtitle, and **Slide 10 Sh9 pillar name**. Exception: do NOT replace "customer" in Zennify-about text (Slide 3) where it refers to Zennify's customer base. Final check: `grep -ri 'customer' unpacked/ppt/slides/slide{1,6,9,10,13,14,16,20}.xml` — for credit union decks, expected result is ZERO matches. Note: Slides 17-19 are excluded (PL-owned, PLs handle terminology).
16. **RENDER → VIEW → FIX loop is MANDATORY after every batch.** After editing any slide:
    1. Run `python3 scripts/04_qa/render_and_inspect.py --pptx working/deck.pptx --slides [edited slides] --outdir qa_renders/`
    2. Use the `view` tool to LOOK AT each rendered PNG: `view qa_renders/slide_06.png`
    3. **Visually judge** the image. Check for: text overflowing shape boundaries, text overlapping adjacent columns/shapes, font too small to read, crowded layout, placeholder text still visible.
    4. If ANY visual issue is found → **fix immediately**: rewrite content shorter (preferred), reduce font size, or restructure. Then re-render and re-view.
    5. Do NOT proceed to the next batch until every edited slide passes visual inspection.
    The math-based `overflow_checker.py` and `visual_overflow_inspector.py` are supplementary pre-checks. The rendered PNG viewed by Claude is the FINAL AUTHORITY on whether a slide looks correct. Claude has vision — use it.
17. **Solution slides are PL-owned.** Do NOT edit Slides 17-19. Do NOT run `solution_inferrer.py` or `solution_slides_editor.py`. Practice Leads decide which solution offerings to place. The skill leaves these slides exactly as they appear in the template. If the user explicitly requests solution slide edits, confirm with them that PLs have signed off before proceeding.
18. **Color authority is `color_level_system.py`.** The single source of truth for every color, every level palette, and every per-shape role is `references/01_brand/color_level_system.py`. The human-readable view is `references/_generated/color_authority.md` (regenerated from the config via `scripts/utils/generate_color_docs.py`). If any older reference file, editing contract snippet, or COLOR AUTHORITY section in this skill cites a different hex, **the config wins**. Before every color edit, verify the hex against `LEVEL_4TIER` / `LEVEL_5TIER` / `STATIC_COLORS` / `THEME_REFS`, or read the generated `color_authority.md`. The editors already do this automatically via `get_expected_hex`; QA (`cross_slide_checker.py`) verifies it.

---

## ⛔ COLOR AUTHORITY (Single Source of Truth)

**The canonical color reference is `references/01_brand/color_level_system.py`.**

Human-readable views (all auto-generated from the config — never hand-edit):

- [`references/_generated/color_authority.md`](references/_generated/color_authority.md) — every color, every palette
- [`references/_generated/brand_level_tables.md`](references/_generated/brand_level_tables.md) — 4-tier + 5-tier score→level functions
- [`references/_generated/per_slide_role_tables.md`](references/_generated/per_slide_role_tables.md) — every editable shape on every slide

Any script, reference file, or plan that cites a color hex MUST derive it from
the config (via `from color_level_system import LEVEL_4TIER`, `LEVEL_5TIER`,
`STATIC_COLORS`, `THEME_REFS`) OR match the corresponding entry in the
regenerated reference docs. The editors do this automatically via
`apply_color_role`; QA (`cross_slide_checker.py`) verifies every shape matches
the config-derived expected hex.

To change a color, edit `color_level_system.py`, then:
1. Run `python3 scripts/utils/generate_color_docs.py` to regenerate docs
2. Commit both the config change and the regenerated docs together
3. `scripts/utils/check_docs_in_sync.py` will fail CI if they drift

**Cross-slide consistency rule:** The heatmap level colors (Slide 14) and the
Slide 13 circle fills share the same score inputs. If a capability scores
"Building" on Slide 14, its pillar-level indicator on Slide 13 should be
Level 2 or 3 (score-consistent). Run `cross_slide_checker.py` after every
batch that touches Slides 10, 13, or 14.

---

## Template Acquisition

Templates are NOT bundled. **Auto-download only the 1 selected template.**

**Priority chain:**

1. **User uploads** — check `/mnt/user-data/uploads/`
2. **Google Drive** (requires `docs.google.com` in egress):
   `wget -O template.pptx 'https://docs.google.com/presentation/d/{ID}/export/pptx'`
3. **GitHub** (requires `raw.githubusercontent.com` in egress):
   `wget -O template.pptx 'https://raw.githubusercontent.com/{OWNER}/{REPO}/main/templates/{sv_id}.pptx'`
4. **Ask user** to upload from [shared folder](https://drive.google.com/drive/folders/1HOzlTpaxEmx9pg0o9wlTtnhjVXsmhiHa)

Google Slides IDs for all 9 templates: see `references/02_registries/subvertical_registry.md`.

**Setup (one-time):** Settings → Capabilities → Allow network egress → add `docs.google.com` and/or `raw.githubusercontent.com`. Or select "All domains."

**After download:** `scripts/01_intake/template_preparer.py` normalizes automatically.

---

## Narrative Framework: 80/20 AIDA + Consultant

| Phase | Slides | Purpose |
|---|---|---|
| **Attention** (~10%) | 1, 5 | Hook: insight headline + industry stat |
| **Interest** (~45%) | 3, 6, 7, 8, 9, 13, 14 | Their reality: profile, pain, DMA data |
| **Desire** (~35%) | 4, 10, 11, 12, 15, 16, 17-19 | Better future: methodology, solutions |

*\*Slides 17-19 are PL-owned solution slides — left as template defaults.*
| **Action** (~10%) | 20, 21 | Mobilization close: dates, owners, CTA |

**Big Idea** (draft before editing): "[Client] [situation], but [opportunity] enables [outcome] by [timeframe]."

---

## Workflow: 7 Turns

### Turn 1: Read Reports + Present Slide Plan | 3-5 tool calls

User uploads 1-2 docs + says "Create a first call deck for [client]."

**In a SINGLE response, do ALL of the following:**

1. **Acknowledge briefly** (1 sentence): "I'll build your DMA First Call Deck. Reading your documents now."
2. **Read the documents** using tool calls: check `/mnt/user-data/uploads/`, read both reports.
3. **Read references:** `references/02_registries/subvertical_registry.md` → `references/01_brand/brand_guidelines.md`.
4. **In your thinking block:** Extract ALL data. Synthesize per Section 9 of brand_guidelines.md. Draft Big Idea. Draft all headlines. Map 9 solutions. Apply the "So What" test to every data point.
5. **Present the SLIDE PLAN** (format below).

**DO NOT:** ask questions, show interactive buttons, or split this into 2 messages. Read → synthesize → present plan — all in one response.

**⛔ End your response with the slide plan. Wait for "approved" or revision requests. Do NOT download templates or edit anything yet.**

**BEFORE presenting, cross-check EVERY slide's content against `references/03_editing/editing_contract.md`:**
- Each content block maps to a specific shape number (Sh0, Sh1, Sh3, etc.)
- Each shape has a max char limit — draft content must fit
- Colors are specified per shape — note them in the plan
- Opportunity language: scan for "no", "lacks", "gap" → reframe as "positioned to", "ready for", "opportunity"
- Strategic objectives MUST appear in Slide 6 Key Differentiators

**⛔ BEFORE PRESENTING THE PLAN — run this self-check in your thinking block:**

1. **Shape numbers match editing contract?** Every content block references the correct Sh# from `references/03_editing/editing_contract.md`. For Slide 6 (40 shapes): Sh1 (eyebrow), Sh2 (headline), Sh5-8 (quick facts), Sh11/14/17 (priority names), Sh12/15/18 (priority descs), Sh20-24 (platforms), Sh25 (platform summary), Sh27/31/35 (metric labels), Sh28/32/36 (metric values), Sh29/33/37 (metric context). For Slide 10 (44 shapes): see editing_contract §5.
2. **Slide 6 has 3 strategic priorities (Sh11/14/17)?** If research report has <3, the Level 1→Level 2→Level 3 fallback chain (see `references/05_qa/strategic_priorities_fallback.md`) applies. `slide6_editor.py` auto-populates `[DATA NEEDED: strategic priority N]` for missing slots — these are acceptable. NEVER fabricate a priority to fill a slot.
3. **Slide 6 has all 40-shape components populated?** Plan must cover: 1 eyebrow (Sh1) + 1 headline (Sh2) + 4 quick facts (Sh5-8) + 3 priorities (Sh11/12, Sh14/15, Sh17/18) + up to 5 platforms (Sh20-24) + 1 platform summary (Sh25) + 3 metric cards (Sh27/28/29, Sh31/32/33, Sh35/36/37). NO Sh3/Sh5 paragraph blocks — those were the OLD 7-shape layout and no longer exist in the template.
4. **No negative language?** Scan the ENTIRE plan for: "no CDO", "no MDM", "no iPaaS", "lacks", "no formal", "not found", "missing". Reframe: "no MDM" → "MDM represents a high-value opportunity to unify member data". "No iPaaS" → "Integration platform opportunity to connect the 212-tool estate."
5. **Colors specified for assessment slides?** Slide 10 has 4-tier pillar strips + 3 rec card triplets (see editing_contract §5). Slide 13 has circle/rectangle fill colors per 5-level system. Slide 14 has 4-level bar + accent + border colors (border MUST equal fill — see editing_contract §6). Slide 9 is static (no color edits). See `references/_generated/color_authority.md` for the canonical hex values.
6. **Content fits the shape?** Check character counts against max chars from editing contract. Slide 6 Sh2 headline ≤130ch (2 lines). Priority names 2–4 words / ≤40ch. Priority descriptions ≤95ch. Metric labels ≤20ch uppercase. Metric values ≤10ch. Metric context ≤60ch. No Sh3/Sh5 "2600ch" or "1500ch" budgets — those were the old layout.
7. **"So What" test passes?** Every metric has context + business consequence. Not just "ROAA: 0.34%" but "ROAA 0.34% (below peer ~0.75%) — constraining reinvestment capacity."
8. **Headlines score ≥7/9?** Every headline has number + entity + verb + arguable claim.
9. **No maturity jargon in headlines?** "2.45 to 3.15" is DMA jargon — translate to business outcomes ("recapture $2M+ in efficiency" or "top-quartile digital capability"). Scores are OK in body text tables, NOT in headlines.
10. **No pillar codes in client-facing text?** P1C1, P2C2 etc. are internal DMA codes — they NEVER appear on any slide. In the plan: use full capability names in all content blocks, headlines, and descriptions. Pillar codes may appear ONLY in a reference ID column of the heatmap table (never as the primary label). "Products & Channels" not "P2C2". "Digital Strategy & Vision" not "P1C1".
11. **Client name spelled out on Slides 1, 6?** Cover and org profile use the full name. No abbreviations on these slides.
12. **Slide 13 strength bullets are descriptive, not scores?** "Zero enforcement actions, Verafin ML" not "Fraud & Risk Mgmt: 2.82 (+0.32)". The score appears in the circle indicator — don't repeat it in text. Use the 35 characters to explain WHY it's a strength.
13. **⛔ EVERY color change shows ACTUAL HEX values?** The plan MUST contain explicit hex codes for EVERY fill/text color change. NOT "Level 2 Developing" alone — must be "Level 2 Developing → bg #C7D3EC, circle #8094C0". NOT "Building" alone on the heatmap — must be "Building → bar #8094C0, label #4E5E8A". If a reviewer cannot verify the exact hex output from the plan, the plan is incomplete.
14. **⛔ Heatmap table has ALL 17 rows × ALL columns filled?** No "..." shortcuts, no empty cells. Every row must show: template score, new score, peer, delta, template level, new level, bar fill/bench color hex (unified — level determines color), label text hex, bar width EMU, median X EMU, card bg hex. If a value is UNCHANGED from the template, write "UNCHANGED" — do not leave blank.
15. **⛔ Slide 13 indicator table has ALL 4 rows × ALL columns?** Each pillar row must show: current BG fill hex → new BG fill hex, current circle fill hex → new circle fill hex. Mark UNCHANGED rows explicitly.
16. **⛔ Slide 10 pillar-strip + rec-card color tables complete?** The DMA Summary Dashboard lives on Slide 10 (not Slide 9). Plans MUST show all 4 pillar strips (P1/P2/P3/P4) with their level-derived accent hex, and all 3 rec cards with their card_bg + accent_strip + label_text hex triplets. Mark UNCHANGED rows explicitly.

If ANY check fails → fix in thinking block BEFORE presenting. Do NOT present a plan that fails these checks.

**Present the slide plan using this format:**

> **CRITICAL: The plan is a CHANGE MANIFEST.** For every shape being edited, show:
> - **Current** template value (text, color, score — read from the template)
> - **New** value (what it will become after editing)
> - **Reason** (data source or logic for the change)
>
> This lets the reviewer verify EVERY change before it happens.
> Read the actual template shapes BEFORE drafting the plan — do NOT assume template defaults.

---

## SLIDE PLAN FOR APPROVAL

Read `references/04_narrative/slide_plan.md` — the slide-by-slide plan the person approves, batch by batch, with the per-turn scripts. Read it at Turn 2, not before.

## Build Rules

See `references/03_editing/editing_contract.md` Section 11 for full XML rules and Section 12 for the Font Size Registry.
- **POST-EDIT FONT CHECK (every batch):** `grep -i 'typeface=' ppt/slides/slide{N}.xml | grep -v 'DM Sans' | grep -v 'DM Sans Medium' | grep -v 'DM Sans SemiBold'`
  **Expected pre-existing fonts (in template, DO NOT FIX):** Inter, Calibri, Arial, Noto Sans
  **CRITICAL — must fix if found (introduced by editing):** Any OTHER font not in the above list. Key points:
- `str_replace` for simple edits. Python scripts for complex multi-paragraph shapes (10+ `<a:t>` elements).
- Replace `<a:t>` content only unless overflow is detected. Font size adjustment is permitted within the Safe Font Size Ranges defined in `references/03_editing/editing_contract.md` Section 12. When reducing font size:
  1. Trim content FIRST — shorter content at the template font is always preferred over longer content at a smaller font.
  2. If trimming alone is insufficient, the per-slide editors (`heatmap_editor.py`, `slide16_editor.py`, `slide20_editor.py`) already apply the Safe Minimum font size automatically for the shapes that are known to overflow. For manual edits on shapes outside those editors' scope, reduce the `sz` attribute on `<a:rPr>` and/or `<a:defRPr>` to the Safe Minimum via inline `str_replace`, or re-use `_editor_common.set_font_size(shape, size_pt)` from Python. The standalone `scripts/03_editing/font_adjuster.py` utility still exists for the same purpose but is no longer part of the main flow.
  3. NEVER reduce below absolute minimums: 17pt headlines, 7pt body, 6pt labels.
  4. NEVER increase font sizes above the template value.
  5. When adjusting, modify ALL runs in the same shape to the same size (do not create mixed sizes unless the template already uses them).
  6. Log every font adjustment: "Slide X ShY: reduced from Zpt to Wpt (overflow: N chars over limit)."
  Positions and shape dimensions remain immutable — NEVER change.
- **Slide 16 MANDATORY font reductions:** Sh3 headline from 26pt → 21pt. Sh8/9/10 cards from 11pt → 9pt. Sh12 outcomes from 10pt → 9pt. Apply BEFORE writing content.
- **Slide 20 MANDATORY font reduction:** Sh0 and Sh8 body from 11pt → 10pt. Set `b="0"` on all body runs. Only bullet headers (date|action) use `b="1"`.
- XML escape: `&`→`&amp;`, `<`→`&lt;`. Remove `<a:highlight>` (see Hard Rule #13). Missing data → `[DATA NEEDED]`.

---

## QA (see `references/05_qa/qa_rubric.md`)

| # | Check | Severity | When |
|---|---|---|---|
| 1 | Headline scoring | HIGH | Turn 2 |
| 2 | Glance Test | MEDIUM | Each batch |
| 3 | Client-is-Hero | MEDIUM | Each batch |
| 4 | MECE Consistency | MEDIUM | Turns 4, 6 |
| 5 | Brand/Source/Schema | CRITICAL | Turn 7 |
| 6 | Shape Integrity | CRITICAL | Turn 7 |
| 7 | Solution Integrity | INFO | Turn 6 — verify Slides 17-19 are UNTOUCHED (PL-owned) |
| 8 | Opportunity Language | HIGH | Each batch |
| 9 | Text Overflow | HIGH | Pre-edit |
| 10 | SV Consistency | HIGH | Turns 2, 7 |
| 11 | Narrative Traps | HIGH | Turn 7 |
| 12 | Storyline Test | HIGH | Turns 1, 7 |
| 13 | Visual Render + Autofix | CRITICAL | Each batch + Turn 7 |

### ⛔ CHECK #13 — RENDER → VIEW → AUTOFIX → RE-RENDER PROTOCOL

This is the MOST IMPORTANT QA check. It runs after EVERY batch. No exceptions.

**Step 1 — Autofix (font reductions):**
```bash
python3 scripts/04_qa/slide_autofix.py \
  --pptx working/deck.pptx \
  --slides [edited slide numbers] \
  --out working/deck.pptx \
  --report autofix_report.json
```
Exit codes: 0 = all auto-fixed. 1 = trims needed (Claude must edit). 2 = redo needed.

**Step 2 — Render edited slides to PNG:**
```bash
python3 scripts/04_qa/render_and_inspect.py \
  --pptx working/deck.pptx \
  --slides [edited slide numbers] \
  --outdir qa_renders/
```

**Step 3 — VIEW every rendered PNG:**
```
view qa_renders/slide_01.png
view qa_renders/slide_06.png
...
```
For EACH image, check ALL of the following:
1. **Text clipping** — is any text cut off at shape boundaries?
2. **Cross-shape overlap** — does text from one shape bleed into an adjacent shape? (Especially Slide 6 left→right column)
3. **Font readability** — is any text too small to read at presentation scale (~24in wide)?
4. **Layout balance** — are sections unevenly spaced or crowded vs. empty?
5. **Placeholder remnants** — any "[CLIENT]", "[DATA NEEDED]", template text still visible?
6. **Color accuracy** — do fills/accents match COLOR AUTHORITY hex values?
7. **Yellow highlights** — any yellow background highlighting on text? These are template markers that MUST be stripped. If visible → run `final_highlight_strip.py` and re-render.

**Step 4 — FIX ESCALATION (if any issue found):**

| Level | When | Action | Tool calls |
|---|---|---|---|
| **L1 TRIM** | Text overflows by ≤20% | Rewrite shape content shorter. Cut least-critical points, remove parentheticals, use shorter synonyms. | 1 str_replace or script |
| **L2 FONT** | Trim alone insufficient | `slide_autofix.py` already applied font reductions. Verify minimum: 17pt headline, 7pt body, 6pt label. | 0 (auto) |
| **L3 REWRITE** | Font at minimum AND still overflows | Full content rewrite for that shape. Restructure: fewer bullets, split across sub-headers, remove secondary details. Target 90% of capacity at safe-min font. | 1-2 tool calls |
| **L4 REDO** | Shape content fundamentally doesn't fit | Propose to user: "Slide [N] Sh[X] needs a structural change — the content is [Y]% over capacity even at minimum font. I recommend [strategy]. Shall I proceed?" | ⛔ STOP and ask |

**Step 5 — Re-render after any fix:**
After every L1/L2/L3 fix, re-run Steps 1-3. Do NOT proceed until:
- `slide_autofix.py` exits with code 0
- Every rendered PNG passes visual inspection
- Zero overflow, zero placeholder text, zero color mismatches

**Step 6 — Present to user:**
Show the final rendered PNG(s) for this batch. Include the autofix summary:
"Batch [N] — [slides]. Autofix: [X font reductions, Y trims applied]. Visual QA: PASS."

⛔ **STOP. Wait for "continue" before next batch.**

---

## Hard Constraints

- **R-BRAND:** Colors/fonts from `references/01_brand/brand_guidelines.md` only.
- **R-GROUND:** Content from source docs only. No fabrication.
- **R-TMPL:** Never create blank slides. Edit template only.
- **R-DATA:** Every number traces to source. Missing → `[DATA NEEDED]`.
- **R-EDIT-01:** Do NOT edit static slides (2, 4, 8, 10, 11, 15, 17, 18, 19, 22). Slides 17-19 are PL-owned solution slides.
- **R-EDIT-02:** Do NOT edit read-only (5, 7) except [CLIENT] swap.
- **R-FONT:** DM Sans only. Sentence case.
- **R-OPPORTUNITY:** Frame as opportunities. Banned words in `references/01_brand/brand_guidelines.md`.
- **R-COMPAT:** Must work in Google Slides. No OLE, SmartArt, VBA.
