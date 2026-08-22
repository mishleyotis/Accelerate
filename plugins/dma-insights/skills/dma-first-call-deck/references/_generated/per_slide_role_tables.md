<!-- DO NOT EDIT DIRECTLY.

     This file is regenerated from `references/01_brand/color_level_system.py`
     via `scripts/utils/generate_color_docs.py`. Any changes made here will be
     overwritten on the next regeneration.

     To change a color, palette, score range, or role: edit the config Python
     file, then re-run the generator and commit both. `check_docs_in_sync.py`
     will fail CI if they drift.
-->

# Per-Slide Role Tables

_Every shape edited by the skill, organized by slide._

Each row is one shape in the slide's role catalogue. Editors iterate these
tables and apply writes per the `F`/`B`/`T`/`TC` (Fill / Border / Text /
Text-Color) flags.

Columns:
- **Sh#** — 0-indexed shape index on the slide
- **Role** — logical name used by the editor
- **Type** — `data` (score-driven) | `static` (fixed hex) | `theme_ref`
  (schemeClr, preserve) | `text` (text-only) | `image` (image, not edited)
- **Source** — for `data`: dotted input path (e.g. `s10.rec_scores[0]`);
  for `static`: key into `STATIC_COLORS`; for `theme_ref`: key into `THEME_REFS`
- **Palette** — slot in `LEVEL_*TIER[level]` (e.g. `accent`, `card_bg`)
- **F/B/T/TC** — write flags: Fill, Border, Text content, Text Color

## Slide 1 (3 shapes, 3 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `title_headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 1 | `tagline` | `text` | `sv.tagline + ' ' + date` | — | · | · | ✓ | · |
| 2 | `client_logo` | `image` | `input.client_logo` | — | · | · | · | · |

## Slide 3 (37 shapes, 1 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 3 | `sv_descriptor` | `text` | `sv.descriptor` | — | · | · | ✓ | · |

## Slide 6 (40 shapes, 36 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `top_banner` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 1 | `eyebrow` | `text` | `'WHAT WE KNOW ABOUT ' + client.upper()` | — | · | · | ✓ | · |
| 2 | `headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 3 | `logo_frame` | `static` | `s6_logo_frame` | — | · | · | · | · |
| 4 | `logo_placeholder` | `theme_ref` | `s6_logo_placeholder_fill` | — | · | · | · | · |
| 5 | `fact_founded` | `text` | `'Founded: ' + year + ', ' + state` | — | · | · | ✓ | · |
| 6 | `fact_assets` | `text` | `'Assets: $' + amount` | — | · | · | ✓ | · |
| 7 | `fact_branches` | `text` | `'Branches: ' + n + '+ in ' + n + ' states'` | — | · | · | ✓ | · |
| 8 | `fact_employees` | `text` | `'Employees: ~' + count` | — | · | · | ✓ | · |
| 10 | `p1_strip` | `static` | `zennify_teal` | — | · | · | · | · |
| 11 | `p1_name` | `text` | `input.priorities[0].name` | — | · | · | ✓ | · |
| 12 | `p1_desc` | `text` | `input.priorities[0].desc` | — | · | · | ✓ | · |
| 13 | `p2_strip` | `static` | `zennify_teal` | — | · | · | · | · |
| 14 | `p2_name` | `text` | `input.priorities[1].name` | — | · | · | ✓ | · |
| 15 | `p2_desc` | `text` | `input.priorities[1].desc` | — | · | · | ✓ | · |
| 16 | `p3_strip` | `static` | `zennify_teal` | — | · | · | · | · |
| 17 | `p3_name` | `text` | `input.priorities[2].name` | — | · | · | ✓ | · |
| 18 | `p3_desc` | `text` | `input.priorities[2].desc` | — | · | · | ✓ | · |
| 20 | `platform_1` | `text` | `input.platforms[0]` | — | · | · | ✓ | · |
| 21 | `platform_2` | `text` | `input.platforms[1]` | — | · | · | ✓ | · |
| 22 | `platform_3` | `text` | `input.platforms[2]` | — | · | · | ✓ | · |
| 23 | `platform_4` | `text` | `input.platforms[3]` | — | · | · | ✓ | · |
| 24 | `platform_5` | `text` | `input.platforms[4]` | — | · | · | ✓ | · |
| 25 | `platform_summary` | `text` | `input.platform_summary` | — | · | · | ✓ | · |
| 26 | `m1_card_bg` | `static` | `zennify_mint_bg` | — | · | · | · | · |
| 27 | `m1_label` | `text` | `input.metrics[0].label` | — | · | · | ✓ | · |
| 28 | `m1_value` | `text` | `input.metrics[0].value` | — | · | · | ✓ | · |
| 29 | `m1_context` | `text` | `input.metrics[0].context` | — | · | · | ✓ | · |
| 30 | `m2_card_bg` | `static` | `zennify_mint_bg` | — | · | · | · | · |
| 31 | `m2_label` | `text` | `input.metrics[1].label` | — | · | · | ✓ | · |
| 32 | `m2_value` | `text` | `input.metrics[1].value` | — | · | · | ✓ | · |
| 33 | `m2_context` | `text` | `input.metrics[1].context` | — | · | · | ✓ | · |
| 34 | `m3_card_bg` | `static` | `zennify_mint_bg` | — | · | · | · | · |
| 35 | `m3_label` | `text` | `input.metrics[2].label` | — | · | · | ✓ | · |
| 36 | `m3_value` | `text` | `input.metrics[2].value` | — | · | · | ✓ | · |
| 37 | `m3_context` | `text` | `input.metrics[2].context` | — | · | · | ✓ | · |

## Slide 9 (23 shapes, 0 edited)

_No editable roles. Slide 9 is **static** — template content ships ready._

## Slide 10 (44 shapes, 32 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 1 | `headline` | `text` | `'Where ' + client + ' stands and what comes next'` | — | · | · | ✓ | · |
| 2 | `p4_pillar_strip` | `data` | `s10.pillar_scores.P4` | `accent` | ✓ | · | · | · |
| 3 | `p4_insight` | `text` | `input.pillars.P4.insight` | — | · | · | ✓ | · |
| 7 | `narrative` | `text` | `Sh7 rewrite: replace [Client], overall, peer + sentence 2-3` | — | · | · | ✓ | · |
| 8 | `p2_insight` | `text` | `input.pillars.P2.insight` | — | · | · | ✓ | · |
| 9 | `p2_name` | `text` | `sv.p2_name_override OR 'Customer Experience'` | — | · | · | ✓ | · |
| 10 | `p3_insight` | `text` | `input.pillars.P3.insight` | — | · | · | ✓ | · |
| 12 | `p1_insight` | `text` | `input.pillars.P1.insight` | — | · | · | ✓ | · |
| 14 | `p3_pillar_strip` | `data` | `s10.pillar_scores.P3` | `accent` | ✓ | · | · | · |
| 15 | `p2_pillar_strip` | `data` | `s10.pillar_scores.P2` | `accent` | ✓ | · | · | · |
| 16 | `p1_pillar_strip` | `data` | `s10.pillar_scores.P1` | `accent` | ✓ | · | · | · |
| 17 | `rec1_card_bg` | `data` | `s10.rec_scores[0]` | `card_bg` | ✓ | ✓ | · | · |
| 18 | `rec1_strip` | `data` | `s10.rec_scores[0]` | `accent` | ✓ | ✓ | · | · |
| 19 | `rec1_label` | `data` | `s10.rec_scores[0]` | `label_text` | · | · | ✓ | ✓ |
| 20 | `rec2_card_bg` | `data` | `s10.rec_scores[1]` | `card_bg` | ✓ | ✓ | · | · |
| 21 | `rec2_strip` | `data` | `s10.rec_scores[1]` | `accent` | ✓ | ✓ | · | · |
| 22 | `rec2_label` | `data` | `s10.rec_scores[1]` | `label_text` | · | · | ✓ | ✓ |
| 23 | `rec3_card_bg` | `data` | `s10.rec_scores[2]` | `card_bg` | ✓ | ✓ | · | · |
| 24 | `rec3_strip` | `data` | `s10.rec_scores[2]` | `accent` | ✓ | ✓ | · | · |
| 25 | `rec3_label` | `data` | `s10.rec_scores[2]` | `label_text` | · | · | ✓ | ✓ |
| 26 | `legend_act_bg` | `static` | `s10_legend_act_bg` | — | · | · | · | · |
| 27 | `legend_act_acc` | `static` | `s10_legend_act_acc` | — | · | · | · | · |
| 29 | `legend_bld_bg` | `static` | `s10_legend_bld_bg` | — | · | · | · | · |
| 30 | `legend_bld_acc` | `static` | `s10_legend_bld_acc` | — | · | · | · | · |
| 32 | `legend_cmp_bg` | `static` | `s10_legend_cmp_bg` | — | · | · | · | · |
| 33 | `legend_cmp_acc` | `static` | `s10_legend_cmp_acc` | — | · | · | · | · |
| 36 | `rec1_name` | `text` | `recs[0].name + ' | Maturity: ' + cur + ' → Target: ' + tgt` | — | · | · | ✓ | · |
| 37 | `rec2_name` | `text` | `recs[1].name + ' | Maturity: ' + cur + ' → Target: ' + tgt` | — | · | · | ✓ | · |
| 38 | `rec3_name` | `text` | `recs[2].name + ' | Maturity: ' + cur + ' → Target: ' + tgt` | — | · | · | ✓ | · |
| 40 | `strengths_bg` | `static` | `s10_strengths_bg` | — | · | · | · | · |
| 41 | `strengths_accent` | `static` | `s10_strengths_accent` | — | · | · | · | · |
| 42 | `strengths` | `text` | `input.strengths[0] + '\n' + input.strengths[1]` | — | · | · | ✓ | · |

## Slide 13 (46 shapes, 33 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `bar_top_1` | `theme_ref` | `s13_bar_top_1` | — | · | · | · | · |
| 1 | `bar_top_2` | `theme_ref` | `s13_bar_top_2` | — | · | · | · | · |
| 2 | `bar_top_3` | `theme_ref` | `s13_bar_top_3` | — | · | · | · | · |
| 3 | `bar_top_4` | `theme_ref` | `s13_bar_top_4` | — | · | · | · | · |
| 6 | `strength_1` | `text` | `input.strengths[0]` | — | · | · | ✓ | · |
| 7 | `strength_2` | `text` | `input.strengths[1]` | — | · | · | ✓ | · |
| 9 | `strength_3` | `text` | `input.strengths[2]` | — | · | · | ✓ | · |
| 10 | `strength_4` | `text` | `input.strengths[3]` | — | · | · | ✓ | · |
| 11 | `narrative_headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 12 | `assessment_title` | `text` | `client + ' Assessment'` | — | · | · | ✓ | · |
| 13 | `comparison_title` | `text` | `client + ' Overall Maturity Industry Comparison'` | — | · | · | ✓ | · |
| 15 | `pillar_row_bg_1` | `theme_ref` | `s13_pillar_row_bg_1` | — | · | · | · | · |
| 16 | `pillar_row_bg_2` | `theme_ref` | `s13_pillar_row_bg_2` | — | · | · | · | · |
| 17 | `pillar_row_bg_3` | `theme_ref` | `s13_pillar_row_bg_3` | — | · | · | · | · |
| 18 | `pillar_row_bg_4` | `theme_ref` | `s13_pillar_row_bg_4` | — | · | · | · | · |
| 19 | `p1_bg_rect` | `data` | `s13.pillar_levels.P1` | `bg_rect` | ✓ | · | · | · |
| 20 | `p1_circle` | `data` | `s13.pillar_levels.P1` | `circle` | ✓ | · | · | · |
| 21 | `p1_number` | `data` | `s13.pillar_levels.P1` | `num_text` | · | · | ✓ | ✓ |
| 22 | `p1_label` | `data` | `s13.pillar_levels.P1` | `label_text` | · | · | ✓ | ✓ |
| 23 | `p2_bg_rect` | `data` | `s13.pillar_levels.P2` | `bg_rect` | ✓ | · | · | · |
| 24 | `p2_circle` | `data` | `s13.pillar_levels.P2` | `circle` | ✓ | · | · | · |
| 25 | `p2_number` | `data` | `s13.pillar_levels.P2` | `num_text` | · | · | ✓ | ✓ |
| 26 | `p2_label` | `data` | `s13.pillar_levels.P2` | `label_text` | · | · | ✓ | ✓ |
| 27 | `p3_bg_rect` | `data` | `s13.pillar_levels.P3` | `bg_rect` | ✓ | · | · | · |
| 28 | `p3_circle` | `data` | `s13.pillar_levels.P3` | `circle` | ✓ | · | · | · |
| 29 | `p3_number` | `data` | `s13.pillar_levels.P3` | `num_text` | · | · | ✓ | ✓ |
| 30 | `p3_label` | `data` | `s13.pillar_levels.P3` | `label_text` | · | · | ✓ | ✓ |
| 31 | `p4_bg_rect` | `data` | `s13.pillar_levels.P4` | `bg_rect` | ✓ | · | · | · |
| 32 | `p4_circle` | `data` | `s13.pillar_levels.P4` | `circle` | ✓ | · | · | · |
| 33 | `p4_number` | `data` | `s13.pillar_levels.P4` | `num_text` | · | · | ✓ | ✓ |
| 34 | `p4_label` | `data` | `s13.pillar_levels.P4` | `label_text` | · | · | ✓ | ✓ |
| 44 | `radar_chart` | `image` | `radar_chart_generator.py` | — | · | · | · | · |
| 45 | `radar_legend` | `image` | `radar_chart_generator.py` | — | · | · | · | · |

## Slide 14 (158 shapes, 145 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 1 | `headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 2 | `legend_act_bg` | `static` | `s14_legend_act_bg` | — | ✓ | ✓ | · | · |
| 3 | `legend_act_acc` | `static` | `s14_legend_act_acc` | — | ✓ | ✓ | · | · |
| 5 | `legend_bld_bg` | `static` | `s14_legend_bld_bg` | — | ✓ | ✓ | · | · |
| 6 | `legend_bld_acc` | `static` | `s14_legend_bld_acc` | — | ✓ | ✓ | · | · |
| 8 | `legend_cmp_bg` | `static` | `s14_legend_cmp_bg` | — | ✓ | ✓ | · | · |
| 9 | `legend_cmp_acc` | `static` | `s14_legend_cmp_acc` | — | ✓ | ✓ | · | · |
| 12 | `legend_dif_acc` | `static` | `s14_legend_dif_acc` | — | ✓ | ✓ | · | · |
| 14 | `median_legend_line` | `static` | `median_stroke` | — | · | · | · | · |
| 17 | `bg_card_cap01` | `data` | `s14.scores[0]` | `card_bg` | ✓ | ✓ | · | · |
| 18 | `accent_strip_cap01` | `data` | `s14.scores[0]` | `accent` | ✓ | ✓ | · | · |
| 19 | `cap_name_cap01` | `text` | `CAPABILITY_ORDER[0] = 'Digital Strategy & Vision'` | — | · | · | ✓ | · |
| 20 | `score_cap01` | `text` | `s14.scores[0] formatted` | — | · | · | ✓ | · |
| 21 | `track_bar_cap01` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 22 | `progress_bar_cap01` | `data` | `s14.scores[0]` | `accent` | ✓ | ✓ | · | · |
| 23 | `median_line_cap01` | `static` | `median_stroke` | — | · | · | · | · |
| 24 | `level_label_cap01` | `data` | `s14.scores[0]` | `label_text` | · | · | ✓ | ✓ |
| 25 | `bg_card_cap02` | `data` | `s14.scores[1]` | `card_bg` | ✓ | ✓ | · | · |
| 26 | `accent_strip_cap02` | `data` | `s14.scores[1]` | `accent` | ✓ | ✓ | · | · |
| 27 | `cap_name_cap02` | `text` | `CAPABILITY_ORDER[1] = 'Governance & Risk Appetite'` | — | · | · | ✓ | · |
| 28 | `score_cap02` | `text` | `s14.scores[1] formatted` | — | · | · | ✓ | · |
| 29 | `track_bar_cap02` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 30 | `progress_bar_cap02` | `data` | `s14.scores[1]` | `accent` | ✓ | ✓ | · | · |
| 31 | `median_line_cap02` | `static` | `median_stroke` | — | · | · | · | · |
| 32 | `level_label_cap02` | `data` | `s14.scores[1]` | `label_text` | · | · | ✓ | ✓ |
| 33 | `bg_card_cap03` | `data` | `s14.scores[2]` | `card_bg` | ✓ | ✓ | · | · |
| 34 | `accent_strip_cap03` | `data` | `s14.scores[2]` | `accent` | ✓ | ✓ | · | · |
| 35 | `cap_name_cap03` | `text` | `CAPABILITY_ORDER[2] = 'Innovation Management'` | — | · | · | ✓ | · |
| 36 | `score_cap03` | `text` | `s14.scores[2] formatted` | — | · | · | ✓ | · |
| 37 | `track_bar_cap03` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 38 | `progress_bar_cap03` | `data` | `s14.scores[2]` | `accent` | ✓ | ✓ | · | · |
| 39 | `median_line_cap03` | `static` | `median_stroke` | — | · | · | · | · |
| 40 | `level_label_cap03` | `data` | `s14.scores[2]` | `label_text` | · | · | ✓ | ✓ |
| 41 | `bg_card_cap04` | `data` | `s14.scores[3]` | `card_bg` | ✓ | ✓ | · | · |
| 42 | `accent_strip_cap04` | `data` | `s14.scores[3]` | `accent` | ✓ | ✓ | · | · |
| 43 | `cap_name_cap04` | `text` | `CAPABILITY_ORDER[3] = 'Culture & Change Enablement'` | — | · | · | ✓ | · |
| 44 | `score_cap04` | `text` | `s14.scores[3] formatted` | — | · | · | ✓ | · |
| 45 | `track_bar_cap04` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 46 | `progress_bar_cap04` | `data` | `s14.scores[3]` | `accent` | ✓ | ✓ | · | · |
| 47 | `median_line_cap04` | `static` | `median_stroke` | — | · | · | · | · |
| 48 | `level_label_cap04` | `data` | `s14.scores[3]` | `label_text` | · | · | ✓ | ✓ |
| 49 | `bg_card_cap05` | `data` | `s14.scores[4]` | `card_bg` | ✓ | ✓ | · | · |
| 50 | `accent_strip_cap05` | `data` | `s14.scores[4]` | `accent` | ✓ | ✓ | · | · |
| 51 | `cap_name_cap05` | `text` | `CAPABILITY_ORDER[4] = 'Sustainable Finance & ESG'` | — | · | · | ✓ | · |
| 52 | `score_cap05` | `text` | `s14.scores[4] formatted` | — | · | · | ✓ | · |
| 53 | `track_bar_cap05` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 54 | `progress_bar_cap05` | `data` | `s14.scores[4]` | `accent` | ✓ | ✓ | · | · |
| 55 | `median_line_cap05` | `static` | `median_stroke` | — | · | · | · | · |
| 56 | `level_label_cap05` | `data` | `s14.scores[4]` | `label_text` | · | · | ✓ | ✓ |
| 58 | `bg_card_cap06` | `data` | `s14.scores[5]` | `card_bg` | ✓ | ✓ | · | · |
| 59 | `accent_strip_cap06` | `data` | `s14.scores[5]` | `accent` | ✓ | ✓ | · | · |
| 60 | `cap_name_cap06` | `text` | `CAPABILITY_ORDER[5] = 'Digital Marketing & Acquisition'` | — | · | · | ✓ | · |
| 61 | `score_cap06` | `text` | `s14.scores[5] formatted` | — | · | · | ✓ | · |
| 62 | `track_bar_cap06` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 63 | `progress_bar_cap06` | `data` | `s14.scores[5]` | `accent` | ✓ | ✓ | · | · |
| 64 | `median_line_cap06` | `static` | `median_stroke` | — | · | · | · | · |
| 65 | `level_label_cap06` | `data` | `s14.scores[5]` | `label_text` | · | · | ✓ | ✓ |
| 66 | `bg_card_cap07` | `data` | `s14.scores[6]` | `card_bg` | ✓ | ✓ | · | · |
| 67 | `accent_strip_cap07` | `data` | `s14.scores[6]` | `accent` | ✓ | ✓ | · | · |
| 68 | `cap_name_cap07` | `text` | `CAPABILITY_ORDER[6] = 'Onboarding & Fulfillment'` | — | · | · | ✓ | · |
| 69 | `score_cap07` | `text` | `s14.scores[6] formatted` | — | · | · | ✓ | · |
| 70 | `track_bar_cap07` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 71 | `progress_bar_cap07` | `data` | `s14.scores[6]` | `accent` | ✓ | ✓ | · | · |
| 72 | `median_line_cap07` | `static` | `median_stroke` | — | · | · | · | · |
| 73 | `level_label_cap07` | `data` | `s14.scores[6]` | `label_text` | · | · | ✓ | ✓ |
| 74 | `bg_card_cap08` | `data` | `s14.scores[7]` | `card_bg` | ✓ | ✓ | · | · |
| 75 | `accent_strip_cap08` | `data` | `s14.scores[7]` | `accent` | ✓ | ✓ | · | · |
| 76 | `cap_name_cap08` | `text` | `CAPABILITY_ORDER[7] = 'Omnichannel Servicing'` | — | · | · | ✓ | · |
| 77 | `score_cap08` | `text` | `s14.scores[7] formatted` | — | · | · | ✓ | · |
| 78 | `track_bar_cap08` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 79 | `progress_bar_cap08` | `data` | `s14.scores[7]` | `accent` | ✓ | ✓ | · | · |
| 80 | `median_line_cap08` | `static` | `median_stroke` | — | · | · | · | · |
| 81 | `level_label_cap08` | `data` | `s14.scores[7]` | `label_text` | · | · | ✓ | ✓ |
| 82 | `bg_card_cap09` | `data` | `s14.scores[8]` | `card_bg` | ✓ | ✓ | · | · |
| 83 | `accent_strip_cap09` | `data` | `s14.scores[8]` | `accent` | ✓ | ✓ | · | · |
| 84 | `cap_name_cap09` | `text` | `CAPABILITY_ORDER[8] = 'Personalization & Engagement'` | — | · | · | ✓ | · |
| 85 | `score_cap09` | `text` | `s14.scores[8] formatted` | — | · | · | ✓ | · |
| 86 | `track_bar_cap09` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 87 | `progress_bar_cap09` | `data` | `s14.scores[8]` | `accent` | ✓ | ✓ | · | · |
| 88 | `median_line_cap09` | `static` | `median_stroke` | — | · | · | · | · |
| 89 | `level_label_cap09` | `data` | `s14.scores[8]` | `label_text` | · | · | ✓ | ✓ |
| 91 | `bg_card_cap10` | `data` | `s14.scores[9]` | `card_bg` | ✓ | ✓ | · | · |
| 92 | `accent_strip_cap10` | `data` | `s14.scores[9]` | `accent` | ✓ | ✓ | · | · |
| 93 | `cap_name_cap10` | `text` | `CAPABILITY_ORDER[9] = 'Process Automation'` | — | · | · | ✓ | · |
| 94 | `score_cap10` | `text` | `s14.scores[9] formatted` | — | · | · | ✓ | · |
| 95 | `track_bar_cap10` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 96 | `progress_bar_cap10` | `data` | `s14.scores[9]` | `accent` | ✓ | ✓ | · | · |
| 97 | `median_line_cap10` | `static` | `median_stroke` | — | · | · | · | · |
| 98 | `level_label_cap10` | `data` | `s14.scores[9]` | `label_text` | · | · | ✓ | ✓ |
| 99 | `bg_card_cap11` | `data` | `s14.scores[10]` | `card_bg` | ✓ | ✓ | · | · |
| 100 | `accent_strip_cap11` | `data` | `s14.scores[10]` | `accent` | ✓ | ✓ | · | · |
| 101 | `cap_name_cap11` | `text` | `CAPABILITY_ORDER[10] = 'Operational Risk & Fraud'` | — | · | · | ✓ | · |
| 102 | `score_cap11` | `text` | `s14.scores[10] formatted` | — | · | · | ✓ | · |
| 103 | `track_bar_cap11` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 104 | `progress_bar_cap11` | `data` | `s14.scores[10]` | `accent` | ✓ | ✓ | · | · |
| 105 | `median_line_cap11` | `static` | `median_stroke` | — | · | · | · | · |
| 106 | `level_label_cap11` | `data` | `s14.scores[10]` | `label_text` | · | · | ✓ | ✓ |
| 107 | `bg_card_cap12` | `data` | `s14.scores[11]` | `card_bg` | ✓ | ✓ | · | · |
| 108 | `accent_strip_cap12` | `data` | `s14.scores[11]` | `accent` | ✓ | ✓ | · | · |
| 109 | `cap_name_cap12` | `text` | `CAPABILITY_ORDER[11] = 'Compliance & Surveillance'` | — | · | · | ✓ | · |
| 110 | `score_cap12` | `text` | `s14.scores[11] formatted` | — | · | · | ✓ | · |
| 111 | `track_bar_cap12` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 112 | `progress_bar_cap12` | `data` | `s14.scores[11]` | `accent` | ✓ | ✓ | · | · |
| 113 | `median_line_cap12` | `static` | `median_stroke` | — | · | · | · | · |
| 114 | `level_label_cap12` | `data` | `s14.scores[11]` | `label_text` | · | · | ✓ | ✓ |
| 115 | `bg_card_cap13` | `data` | `s14.scores[12]` | `card_bg` | ✓ | ✓ | · | · |
| 116 | `accent_strip_cap13` | `data` | `s14.scores[12]` | `accent` | ✓ | ✓ | · | · |
| 117 | `cap_name_cap13` | `text` | `CAPABILITY_ORDER[12] = 'Business Resilience & TPRM'` | — | · | · | ✓ | · |
| 118 | `score_cap13` | `text` | `s14.scores[12] formatted` | — | · | · | ✓ | · |
| 119 | `track_bar_cap13` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 120 | `progress_bar_cap13` | `data` | `s14.scores[12]` | `accent` | ✓ | ✓ | · | · |
| 121 | `median_line_cap13` | `static` | `median_stroke` | — | · | · | · | · |
| 122 | `level_label_cap13` | `data` | `s14.scores[12]` | `label_text` | · | · | ✓ | ✓ |
| 124 | `bg_card_cap14` | `data` | `s14.scores[13]` | `card_bg` | ✓ | ✓ | · | · |
| 125 | `accent_strip_cap14` | `data` | `s14.scores[13]` | `accent` | ✓ | ✓ | · | · |
| 126 | `cap_name_cap14` | `text` | `CAPABILITY_ORDER[13] = 'Data Governance'` | — | · | · | ✓ | · |
| 127 | `score_cap14` | `text` | `s14.scores[13] formatted` | — | · | · | ✓ | · |
| 128 | `track_bar_cap14` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 129 | `progress_bar_cap14` | `data` | `s14.scores[13]` | `accent` | ✓ | ✓ | · | · |
| 130 | `median_line_cap14` | `static` | `median_stroke` | — | · | · | · | · |
| 131 | `level_label_cap14` | `data` | `s14.scores[13]` | `label_text` | · | · | ✓ | ✓ |
| 132 | `bg_card_cap15` | `data` | `s14.scores[14]` | `card_bg` | ✓ | ✓ | · | · |
| 133 | `accent_strip_cap15` | `data` | `s14.scores[14]` | `accent` | ✓ | ✓ | · | · |
| 134 | `cap_name_cap15` | `text` | `CAPABILITY_ORDER[14] = 'Analytics & AI Enablement'` | — | · | · | ✓ | · |
| 135 | `score_cap15` | `text` | `s14.scores[14] formatted` | — | · | · | ✓ | · |
| 136 | `track_bar_cap15` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 137 | `progress_bar_cap15` | `data` | `s14.scores[14]` | `accent` | ✓ | ✓ | · | · |
| 138 | `median_line_cap15` | `static` | `median_stroke` | — | · | · | · | · |
| 139 | `level_label_cap15` | `data` | `s14.scores[14]` | `label_text` | · | · | ✓ | ✓ |
| 140 | `bg_card_cap16` | `data` | `s14.scores[15]` | `card_bg` | ✓ | ✓ | · | · |
| 141 | `accent_strip_cap16` | `data` | `s14.scores[15]` | `accent` | ✓ | ✓ | · | · |
| 142 | `cap_name_cap16` | `text` | `CAPABILITY_ORDER[15] = 'Architecture & Integration'` | — | · | · | ✓ | · |
| 143 | `score_cap16` | `text` | `s14.scores[15] formatted` | — | · | · | ✓ | · |
| 144 | `track_bar_cap16` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 145 | `progress_bar_cap16` | `data` | `s14.scores[15]` | `accent` | ✓ | ✓ | · | · |
| 146 | `median_line_cap16` | `static` | `median_stroke` | — | · | · | · | · |
| 147 | `level_label_cap16` | `data` | `s14.scores[15]` | `label_text` | · | · | ✓ | ✓ |
| 148 | `bg_card_cap17` | `data` | `s14.scores[16]` | `card_bg` | ✓ | ✓ | · | · |
| 149 | `accent_strip_cap17` | `data` | `s14.scores[16]` | `accent` | ✓ | ✓ | · | · |
| 150 | `cap_name_cap17` | `text` | `CAPABILITY_ORDER[16] = 'Platform Enablement'` | — | · | · | ✓ | · |
| 151 | `score_cap17` | `text` | `s14.scores[16] formatted` | — | · | · | ✓ | · |
| 152 | `track_bar_cap17` | `static` | `track_bar` | — | ✓ | ✓ | · | · |
| 153 | `progress_bar_cap17` | `data` | `s14.scores[16]` | `accent` | ✓ | ✓ | · | · |
| 154 | `median_line_cap17` | `static` | `median_stroke` | — | · | · | · | · |
| 155 | `level_label_cap17` | `data` | `s14.scores[16]` | `label_text` | · | · | ✓ | ✓ |

## Slide 16 (14 shapes, 11 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `left_panel_bg` | `theme_ref` | `s16_left_panel_bg` | — | · | · | · | · |
| 3 | `headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 4 | `intro` | `text` | `input.opportunity_intro` | — | · | · | ✓ | · |
| 5 | `opp_card_1_bg` | `theme_ref` | `s16_opportunity_bg_1` | — | · | · | · | · |
| 6 | `opp_card_2_bg` | `theme_ref` | `s16_opportunity_bg_2` | — | · | · | · | · |
| 7 | `opp_card_3_bg` | `theme_ref` | `s16_opportunity_bg_3` | — | · | · | · | · |
| 8 | `opp_card_1` | `text` | `opportunities[0]: bold name + Maturity Gap + Why` | — | · | · | ✓ | · |
| 9 | `opp_card_2` | `text` | `opportunities[1]: same structure` | — | · | · | ✓ | · |
| 10 | `opp_card_3` | `text` | `opportunities[2]: same structure` | — | · | · | ✓ | · |
| 11 | `arrow` | `theme_ref` | `s16_arrow_fill` | — | · | · | · | · |
| 12 | `outcomes` | `text` | `input.outcomes (3-5 bullets)` | — | · | · | ✓ | · |

## Slide 20 (21 shapes, 12 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `next_steps_body` | `text` | `input.next_steps (≥3 rows: Date|Action|Owner)` | — | · | · | ✓ | · |
| 2 | `goal_statement` | `text` | `input.goal_statement` | — | · | · | ✓ | · |
| 3 | `headline` | `text` | `input.headline` | — | · | · | ✓ | · |
| 4 | `step_chip_1` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 6 | `step_chip_2` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 8 | `step_chip_3` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 10 | `step_chip_4` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 12 | `deliverables_body` | `text` | `input.deliverables (≥3 items)` | — | · | · | ✓ | · |
| 13 | `deliv_chip_1` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 15 | `deliv_chip_2` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 17 | `deliv_chip_3` | `static` | `zennify_light_purple` | — | · | · | · | · |
| 19 | `deliv_chip_4` | `static` | `zennify_light_purple` | — | · | · | · | · |

## Slide 21 (2 shapes, 1 edited)

| Sh# | Role | Type | Source | Palette | F | B | T | TC |
|---|---|---|---|---|---|---|---|---|
| 0 | `presenter_email` | `text` | `input.presenter_email` | — | · | · | ✓ | · |

