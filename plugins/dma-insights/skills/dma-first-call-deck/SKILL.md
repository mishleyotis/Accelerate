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
    │   ├── slide13_editor.py                Run: Turn 5 (46-shape Slide 13, 5-tier indicators)
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

> 5-Level reference (bg ≠ circle):
> L1: bg=#FFCB99, circle=#FE9732 | L2: bg=#C7D3EC, circle=#8094C0 | L3: bg=#E6F3FA, circle=#3D81F6
> L4: bg=#E8F7F6, circle=#62D7B8 | L5: bg=#B0EED3, circle=#27BBAF
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

**Heatmap capability changes (all 17 — full names, NO P#C# codes):**

| # | Capability | Tmpl Score | New Score | Peer | Δ | Tmpl Level | New Level | Bar Fill / Bench Color | Label Text Color | Bar Width (EMU) | Median X (EMU) | Card BG |
|---|-----------|-----------|-----------|------|---|-----------|-----------|----------------------|-----------------|----------------|----------------|---------|
| 1 | Digital Strategy & Vision | 3.1 | [X.XX] | [X.XX] | [±X.XX] | Competing | [Level] | [#F97316/#8094C0/#27BBAF/#185F60] | [#F97316/#4E5E8A/#198478/#185F60] | [round((score/5)×1883700)] | [track_left+round((peer/5)×1883700)] | [#FFF3E8/#F2F4F9/#E6F5F3/#E8F7F6] |
| 2 | Governance & Risk Appetite | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 3 | Innovation Management | 3.2 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 4 | Culture & Change Enablement | 2.9 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 5 | Sustainable Finance & ESG | 2.7 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 6 | Digital Mktg & Acquisition | 2.6 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 7 | Onboarding & Fulfillment | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 8 | Omnichannel Servicing | 2.7 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 9 | Personalization & Engagement | 2.3 | [X.XX] | [X.XX] | [±X.XX] | Activating | [...] | [...] | [...] | [...] | [...] | [...] |
| 10 | Process Automation | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 11 | Operational Risk & Fraud | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 12 | Compliance & Surveillance | 3.2 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 13 | Business Resilience & TPRM | 2.5 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 14 | Data Governance | 1.7 | [X.XX] | [X.XX] | [±X.XX] | Activating | [...] | [...] | [...] | [...] | [...] | [...] |
| 15 | Analytics & AI Enablement | 2.3 | [X.XX] | [X.XX] | [±X.XX] | Building | [...] | [...] | [...] | [...] | [...] | [...] |
| 16 | Architecture & Integration | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |
| 17 | Platform Enablement | 2.8 | [X.XX] | [X.XX] | [±X.XX] | Competing | [...] | [...] | [...] | [...] | [...] | [...] |

> **Column definitions (every [...] MUST be replaced with an actual value):**
>
> - **Tmpl Score / New Score:** The template's placeholder score → the actual DMA score from the report.
> - **Tmpl Level / New Level:** Score→Level: 0.00–1.49=Activating, 1.50–2.49=Building, 2.50–3.49=Competing, 3.50–5.00=Differentiating.
> - **Bar Fill / Bench Color:** UNIFIED level-based color for accent strip (+1), progress bar (+5), AND benchmark reference: Activating=`#F97316`, Building=`#8094C0`, Competing=`#27BBAF`, Differentiating=`#185F60`. There is NO separate peer-relative color system — the level determines the color, period. Benchmark line stroke: `#3D81F6` (on `<a:ln>`, NOT shape fill).
> - **Label Text Color:** The two-tier TEXT color for the level label (+7): Activating=#F97316, Building=#4E5E8A, Competing=#198478, Differentiating=#185F60.
> - **Bar Width (EMU):** `round((new_score / 5.0) × 1,883,700)`. Track width is 1,883,700 EMU for all templates.
> - **Median X (EMU):** `track_left + round((peer / 5.0) × 1,883,700)`. Track left varies per pillar column (P1=484632, P2=2606040, P3=4727448, P4=6848856). **Show the actual computed integer.**
> - **Card BG:** The card background color for the level: Activating=#FFF3E8, Building=#F2F4F9, Competing=#E6F5F3, Differentiating=#E8F7F6. *Not changed by script — already in template. Shown to verify visual consistency.*
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
python3 /mnt/skills/public/pptx/scripts/office/pack.py unpacked/ working/deck.pptx
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
**Per-batch QA:** Run Check #13 protocol on Slide 14 (render → view → autofix → re-render). Extra checks: all 17 bars visible with correct level-derived colors (see `references/_generated/color_authority.md` — Activating=#F97316, Building=#8094C0, Competing=#27BBAF, Differentiating=#185F60). Median connectors (#3D81F6) correctly positioned, labels readable. Score text verification (from script audit). Run `cross_slide_checker.py` which auto-verifies Slide 14 ↔ Slide 13 ↔ Slide 10 level consistency via config-derived expectations. ⛔ STOP.

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
