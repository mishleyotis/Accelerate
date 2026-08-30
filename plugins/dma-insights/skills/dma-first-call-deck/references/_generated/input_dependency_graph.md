<!-- DO NOT EDIT DIRECTLY.

     This file is regenerated from `references/01_brand/color_level_system.py`
     via `scripts/utils/generate_dependency_graph.py`. Any changes made here
     will be overwritten on the next regeneration.

     This is the **causal chain** from input data → transformation →
     shape state. Use it to debug QA mismatches: given a failed shape,
     walk backward to find the input driver; given an input, see every
     shape it affects.
-->


# Input Dependency Graph

_Every shape's final state → which input → through which transformation._

This document inverts the role catalogue in `color_level_system.py`.
Each editor walks forward (source → shape); this doc walks backward
(shape → source). QA failures are debugged with the Debugging Guide
at the bottom.

## Per-Slide Chains

For each slide, the shapes are grouped by their input source. All
shapes under one heading are driven by the same input — changing
that input moves all of them in lockstep.

## Slide 1

### Image: `input.client_logo`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `client_logo` | image file replacement (by editor) | — |

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `title_headline` | set_shape_text (text content) | text |

### Text input: `sv.tagline + ' ' + date`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh1 | `tagline` | set_shape_text (text content) | text |

## Slide 3

### Text input: `sv.descriptor`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `sv_descriptor` | set_shape_text (text content) | text |

## Slide 6

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `headline` | set_shape_text (text content) | text |

### Text input: `input.metrics[0].context`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh29 | `m1_context` | set_shape_text (text content) | text |

### Text input: `input.metrics[0].label`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh27 | `m1_label` | set_shape_text (text content) | text |

### Text input: `input.metrics[0].value`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh28 | `m1_value` | set_shape_text (text content) | text |

### Text input: `input.metrics[1].context`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh33 | `m2_context` | set_shape_text (text content) | text |

### Text input: `input.metrics[1].label`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh31 | `m2_label` | set_shape_text (text content) | text |

### Text input: `input.metrics[1].value`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh32 | `m2_value` | set_shape_text (text content) | text |

### Text input: `input.metrics[2].context`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh37 | `m3_context` | set_shape_text (text content) | text |

### Text input: `input.metrics[2].label`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh35 | `m3_label` | set_shape_text (text content) | text |

### Text input: `input.metrics[2].value`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh36 | `m3_value` | set_shape_text (text content) | text |

### Text input: `input.platform_summary`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh25 | `platform_summary` | set_shape_text (text content) | text |

### Text input: `input.platforms[0]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh20 | `platform_1` | set_shape_text (text content) | text |

### Text input: `input.platforms[1]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh21 | `platform_2` | set_shape_text (text content) | text |

### Text input: `input.platforms[2]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh22 | `platform_3` | set_shape_text (text content) | text |

### Text input: `input.platforms[3]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh23 | `platform_4` | set_shape_text (text content) | text |

### Text input: `input.platforms[4]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh24 | `platform_5` | set_shape_text (text content) | text |

### Text input: `input.priorities[0].desc`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `p1_desc` | set_shape_text (text content) | text |

### Text input: `input.priorities[0].name`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh11 | `p1_name` | set_shape_text (text content) | text |

### Text input: `input.priorities[1].desc`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh15 | `p2_desc` | set_shape_text (text content) | text |

### Text input: `input.priorities[1].name`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh14 | `p2_name` | set_shape_text (text content) | text |

### Text input: `input.priorities[2].desc`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh18 | `p3_desc` | set_shape_text (text content) | text |

### Text input: `input.priorities[2].name`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh17 | `p3_name` | set_shape_text (text content) | text |

### Static: `STATIC_COLORS['s6_logo_frame']` = `#E0EEF0`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `logo_frame` | STATIC_COLORS['s6_logo_frame'] | — |

### Static: `STATIC_COLORS['zennify_light_purple']` = `#F2F4F9`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `top_banner` | STATIC_COLORS['zennify_light_purple'] | — |

### Static: `STATIC_COLORS['zennify_mint_bg']` = `#E8F7F6`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh26 | `m1_card_bg` | STATIC_COLORS['zennify_mint_bg'] | — |
| Sh30 | `m2_card_bg` | STATIC_COLORS['zennify_mint_bg'] | — |
| Sh34 | `m3_card_bg` | STATIC_COLORS['zennify_mint_bg'] | — |

### Static: `STATIC_COLORS['zennify_teal']` = `#27BBAF`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh10 | `p1_strip` | STATIC_COLORS['zennify_teal'] | — |
| Sh13 | `p2_strip` | STATIC_COLORS['zennify_teal'] | — |
| Sh16 | `p3_strip` | STATIC_COLORS['zennify_teal'] | — |

### Theme ref: `THEME_REFS['s6_logo_placeholder_fill']` = `schemeClr:lt1`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh4 | `logo_placeholder` | schemeClr:lt1 (preserved) | — |

### Text input: `'Assets: $' + amount`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh6 | `fact_assets` | set_shape_text (text content) | text |

### Text input: `'Branches: ' + n + '+ in ' + n + ' states'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh7 | `fact_branches` | set_shape_text (text content) | text |

### Text input: `'Employees: ~' + count`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh8 | `fact_employees` | set_shape_text (text content) | text |

### Text input: `'Founded: ' + year + ', ' + state`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh5 | `fact_founded` | set_shape_text (text content) | text |

### Text input: `'WHAT WE KNOW ABOUT ' + client.upper()`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh1 | `eyebrow` | set_shape_text (text content) | text |

## Slide 9

_Slide 9 is static — no editable roles; no input dependencies._

## Slide 10

### Input: `s10.pillar_scores.P1` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh16 | `p1_pillar_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill |

### Input: `s10.pillar_scores.P2` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh15 | `p2_pillar_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill |

### Input: `s10.pillar_scores.P3` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh14 | `p3_pillar_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill |

### Input: `s10.pillar_scores.P4` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `p4_pillar_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill |

### Input: `s10.rec_scores[0]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh17 | `rec1_card_bg` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh18 | `rec1_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh19 | `rec1_label` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Input: `s10.rec_scores[1]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh20 | `rec2_card_bg` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh21 | `rec2_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh22 | `rec2_label` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Input: `s10.rec_scores[2]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh23 | `rec3_card_bg` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh24 | `rec3_strip` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh25 | `rec3_label` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `input.pillars.P1.insight`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `p1_insight` | set_shape_text (text content) | text |

### Text input: `input.pillars.P2.insight`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh8 | `p2_insight` | set_shape_text (text content) | text |

### Text input: `input.pillars.P3.insight`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh10 | `p3_insight` | set_shape_text (text content) | text |

### Text input: `input.pillars.P4.insight`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `p4_insight` | set_shape_text (text content) | text |

### Text input: `input.strengths[0] + '\n' + input.strengths[1]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh42 | `strengths` | set_shape_text (text content) | text |

### Text input: `sv.p2_name_override OR 'Customer Experience'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh9 | `p2_name` | set_shape_text (text content) | text |

### Static: `STATIC_COLORS['s10_legend_act_acc']` = `#F97316`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh27 | `legend_act_acc` | STATIC_COLORS['s10_legend_act_acc'] | — |

### Static: `STATIC_COLORS['s10_legend_act_bg']` = `#FFF3E8`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh26 | `legend_act_bg` | STATIC_COLORS['s10_legend_act_bg'] | — |

### Static: `STATIC_COLORS['s10_legend_bld_acc']` = `#8094C0`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh30 | `legend_bld_acc` | STATIC_COLORS['s10_legend_bld_acc'] | — |

### Static: `STATIC_COLORS['s10_legend_bld_bg']` = `#F2F4F9`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh29 | `legend_bld_bg` | STATIC_COLORS['s10_legend_bld_bg'] | — |

### Static: `STATIC_COLORS['s10_legend_cmp_acc']` = `#27BBAF`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh33 | `legend_cmp_acc` | STATIC_COLORS['s10_legend_cmp_acc'] | — |

### Static: `STATIC_COLORS['s10_legend_cmp_bg']` = `#E6F5F3`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh32 | `legend_cmp_bg` | STATIC_COLORS['s10_legend_cmp_bg'] | — |

### Static: `STATIC_COLORS['s10_strengths_accent']` = `#139F94`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh41 | `strengths_accent` | STATIC_COLORS['s10_strengths_accent'] | — |

### Static: `STATIC_COLORS['s10_strengths_bg']` = `#E8F7F6`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh40 | `strengths_bg` | STATIC_COLORS['s10_strengths_bg'] | — |

### Text input: `'Where ' + client + ' stands and what comes next'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh1 | `headline` | set_shape_text (text content) | text |

### Text input: `Sh7 rewrite: replace [Client], overall, peer + sentence 2-3`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh7 | `narrative` | set_shape_text (text content) | text |

### Text input: `recs[0].name + ' | Maturity: ' + cur + ' → Target: ' + tgt`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh36 | `rec1_name` | set_shape_text (text content) | text |

### Text input: `recs[1].name + ' | Maturity: ' + cur + ' → Target: ' + tgt`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh37 | `rec2_name` | set_shape_text (text content) | text |

### Text input: `recs[2].name + ' | Maturity: ' + cur + ' → Target: ' + tgt`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh38 | `rec3_name` | set_shape_text (text content) | text |

## Slide 13

### Input: `s13.pillar_levels.P1` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh19 | `p1_bg_rect` | score_to_level_5tier(score) → LEVEL_5TIER[level]['bg_rect'] | fill |
| Sh20 | `p1_circle` | score_to_level_5tier(score) → LEVEL_5TIER[level]['circle'] | fill |
| Sh21 | `p1_number` | score_to_level_5tier(score) → LEVEL_5TIER[level]['num_text'] | text, text_color |
| Sh22 | `p1_label` | score_to_level_5tier(score) → LEVEL_5TIER[level]['label_text'] | text, text_color |

### Input: `s13.pillar_levels.P2` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh23 | `p2_bg_rect` | score_to_level_5tier(score) → LEVEL_5TIER[level]['bg_rect'] | fill |
| Sh24 | `p2_circle` | score_to_level_5tier(score) → LEVEL_5TIER[level]['circle'] | fill |
| Sh25 | `p2_number` | score_to_level_5tier(score) → LEVEL_5TIER[level]['num_text'] | text, text_color |
| Sh26 | `p2_label` | score_to_level_5tier(score) → LEVEL_5TIER[level]['label_text'] | text, text_color |

### Input: `s13.pillar_levels.P3` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh27 | `p3_bg_rect` | score_to_level_5tier(score) → LEVEL_5TIER[level]['bg_rect'] | fill |
| Sh28 | `p3_circle` | score_to_level_5tier(score) → LEVEL_5TIER[level]['circle'] | fill |
| Sh29 | `p3_number` | score_to_level_5tier(score) → LEVEL_5TIER[level]['num_text'] | text, text_color |
| Sh30 | `p3_label` | score_to_level_5tier(score) → LEVEL_5TIER[level]['label_text'] | text, text_color |

### Input: `s13.pillar_levels.P4` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh31 | `p4_bg_rect` | score_to_level_5tier(score) → LEVEL_5TIER[level]['bg_rect'] | fill |
| Sh32 | `p4_circle` | score_to_level_5tier(score) → LEVEL_5TIER[level]['circle'] | fill |
| Sh33 | `p4_number` | score_to_level_5tier(score) → LEVEL_5TIER[level]['num_text'] | text, text_color |
| Sh34 | `p4_label` | score_to_level_5tier(score) → LEVEL_5TIER[level]['label_text'] | text, text_color |

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh11 | `narrative_headline` | set_shape_text (text content) | text |

### Text input: `input.strengths[0]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh6 | `strength_1` | set_shape_text (text content) | text |

### Text input: `input.strengths[1]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh7 | `strength_2` | set_shape_text (text content) | text |

### Text input: `input.strengths[2]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh9 | `strength_3` | set_shape_text (text content) | text |

### Text input: `input.strengths[3]`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh10 | `strength_4` | set_shape_text (text content) | text |

### Theme ref: `THEME_REFS['s13_bar_top_1']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `bar_top_1` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_bar_top_2']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh1 | `bar_top_2` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_bar_top_3']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `bar_top_3` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_bar_top_4']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `bar_top_4` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_pillar_row_bg_1']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh15 | `pillar_row_bg_1` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_pillar_row_bg_2']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh16 | `pillar_row_bg_2` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_pillar_row_bg_3']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh17 | `pillar_row_bg_3` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s13_pillar_row_bg_4']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh18 | `pillar_row_bg_4` | schemeClr:lt2 (preserved) | — |

### Text input: `client + ' Assessment'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `assessment_title` | set_shape_text (text content) | text |

### Text input: `client + ' Overall Maturity Industry Comparison'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh13 | `comparison_title` | set_shape_text (text content) | text |

### Image: `radar_chart_generator.py`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh44 | `radar_chart` | image file replacement (by editor) | — |
| Sh45 | `radar_legend` | image file replacement (by editor) | — |

## Slide 14

### Input: `s14.scores[0]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh17 | `bg_card_cap01` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh18 | `accent_strip_cap01` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh22 | `progress_bar_cap01` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh24 | `level_label_cap01` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[0] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh20 | `score_cap01` | set_shape_text (text content) | text |

### Input: `s14.scores[10]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh99 | `bg_card_cap11` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh100 | `accent_strip_cap11` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh104 | `progress_bar_cap11` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh106 | `level_label_cap11` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[10] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh102 | `score_cap11` | set_shape_text (text content) | text |

### Input: `s14.scores[11]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh107 | `bg_card_cap12` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh108 | `accent_strip_cap12` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh112 | `progress_bar_cap12` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh114 | `level_label_cap12` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[11] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh110 | `score_cap12` | set_shape_text (text content) | text |

### Input: `s14.scores[12]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh115 | `bg_card_cap13` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh116 | `accent_strip_cap13` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh120 | `progress_bar_cap13` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh122 | `level_label_cap13` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[12] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh118 | `score_cap13` | set_shape_text (text content) | text |

### Input: `s14.scores[13]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh124 | `bg_card_cap14` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh125 | `accent_strip_cap14` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh129 | `progress_bar_cap14` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh131 | `level_label_cap14` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[13] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh127 | `score_cap14` | set_shape_text (text content) | text |

### Input: `s14.scores[14]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh132 | `bg_card_cap15` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh133 | `accent_strip_cap15` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh137 | `progress_bar_cap15` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh139 | `level_label_cap15` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[14] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh135 | `score_cap15` | set_shape_text (text content) | text |

### Input: `s14.scores[15]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh140 | `bg_card_cap16` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh141 | `accent_strip_cap16` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh145 | `progress_bar_cap16` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh147 | `level_label_cap16` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[15] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh143 | `score_cap16` | set_shape_text (text content) | text |

### Input: `s14.scores[16]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh148 | `bg_card_cap17` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh149 | `accent_strip_cap17` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh153 | `progress_bar_cap17` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh155 | `level_label_cap17` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[16] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh151 | `score_cap17` | set_shape_text (text content) | text |

### Input: `s14.scores[1]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh25 | `bg_card_cap02` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh26 | `accent_strip_cap02` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh30 | `progress_bar_cap02` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh32 | `level_label_cap02` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[1] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh28 | `score_cap02` | set_shape_text (text content) | text |

### Input: `s14.scores[2]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh33 | `bg_card_cap03` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh34 | `accent_strip_cap03` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh38 | `progress_bar_cap03` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh40 | `level_label_cap03` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[2] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh36 | `score_cap03` | set_shape_text (text content) | text |

### Input: `s14.scores[3]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh41 | `bg_card_cap04` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh42 | `accent_strip_cap04` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh46 | `progress_bar_cap04` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh48 | `level_label_cap04` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[3] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh44 | `score_cap04` | set_shape_text (text content) | text |

### Input: `s14.scores[4]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh49 | `bg_card_cap05` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh50 | `accent_strip_cap05` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh54 | `progress_bar_cap05` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh56 | `level_label_cap05` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[4] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh52 | `score_cap05` | set_shape_text (text content) | text |

### Input: `s14.scores[5]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh58 | `bg_card_cap06` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh59 | `accent_strip_cap06` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh63 | `progress_bar_cap06` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh65 | `level_label_cap06` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[5] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh61 | `score_cap06` | set_shape_text (text content) | text |

### Input: `s14.scores[6]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh66 | `bg_card_cap07` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh67 | `accent_strip_cap07` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh71 | `progress_bar_cap07` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh73 | `level_label_cap07` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[6] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh69 | `score_cap07` | set_shape_text (text content) | text |

### Input: `s14.scores[7]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh74 | `bg_card_cap08` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh75 | `accent_strip_cap08` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh79 | `progress_bar_cap08` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh81 | `level_label_cap08` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[7] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh77 | `score_cap08` | set_shape_text (text content) | text |

### Input: `s14.scores[8]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh82 | `bg_card_cap09` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh83 | `accent_strip_cap09` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh87 | `progress_bar_cap09` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh89 | `level_label_cap09` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[8] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh85 | `score_cap09` | set_shape_text (text content) | text |

### Input: `s14.scores[9]` (score)

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh91 | `bg_card_cap10` | score_to_level_4tier(score) → LEVEL_4TIER[level]['card_bg'] | fill, border |
| Sh92 | `accent_strip_cap10` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh96 | `progress_bar_cap10` | score_to_level_4tier(score) → LEVEL_4TIER[level]['accent'] | fill, border |
| Sh98 | `level_label_cap10` | score_to_level_4tier(score) → LEVEL_4TIER[level]['label_text'] | text, text_color |

### Text input: `s14.scores[9] formatted`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh94 | `score_cap10` | set_shape_text (text content) | text |

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh1 | `headline` | set_shape_text (text content) | text |

### Static: `STATIC_COLORS['median_stroke']` = `#3D81F6`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh14 | `median_legend_line` | STATIC_COLORS['median_stroke'] | — |
| Sh23 | `median_line_cap01` | STATIC_COLORS['median_stroke'] | — |
| Sh31 | `median_line_cap02` | STATIC_COLORS['median_stroke'] | — |
| Sh39 | `median_line_cap03` | STATIC_COLORS['median_stroke'] | — |
| Sh47 | `median_line_cap04` | STATIC_COLORS['median_stroke'] | — |
| Sh55 | `median_line_cap05` | STATIC_COLORS['median_stroke'] | — |
| Sh64 | `median_line_cap06` | STATIC_COLORS['median_stroke'] | — |
| Sh72 | `median_line_cap07` | STATIC_COLORS['median_stroke'] | — |
| Sh80 | `median_line_cap08` | STATIC_COLORS['median_stroke'] | — |
| Sh88 | `median_line_cap09` | STATIC_COLORS['median_stroke'] | — |
| Sh97 | `median_line_cap10` | STATIC_COLORS['median_stroke'] | — |
| Sh105 | `median_line_cap11` | STATIC_COLORS['median_stroke'] | — |
| Sh113 | `median_line_cap12` | STATIC_COLORS['median_stroke'] | — |
| Sh121 | `median_line_cap13` | STATIC_COLORS['median_stroke'] | — |
| Sh130 | `median_line_cap14` | STATIC_COLORS['median_stroke'] | — |
| Sh138 | `median_line_cap15` | STATIC_COLORS['median_stroke'] | — |
| Sh146 | `median_line_cap16` | STATIC_COLORS['median_stroke'] | — |
| Sh154 | `median_line_cap17` | STATIC_COLORS['median_stroke'] | — |

### Static: `STATIC_COLORS['s14_legend_act_acc']` = `#F97316`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `legend_act_acc` | STATIC_COLORS['s14_legend_act_acc'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_act_bg']` = `#FFF3E8`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `legend_act_bg` | STATIC_COLORS['s14_legend_act_bg'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_bld_acc']` = `#8094C0`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh6 | `legend_bld_acc` | STATIC_COLORS['s14_legend_bld_acc'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_bld_bg']` = `#F2F4F9`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh5 | `legend_bld_bg` | STATIC_COLORS['s14_legend_bld_bg'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_cmp_acc']` = `#27BBAF`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh9 | `legend_cmp_acc` | STATIC_COLORS['s14_legend_cmp_acc'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_cmp_bg']` = `#E6F5F3`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh8 | `legend_cmp_bg` | STATIC_COLORS['s14_legend_cmp_bg'] | fill, border |

### Static: `STATIC_COLORS['s14_legend_dif_acc']` = `#185F60`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `legend_dif_acc` | STATIC_COLORS['s14_legend_dif_acc'] | fill, border |

### Static: `STATIC_COLORS['track_bar']` = `#E5E7EB`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh21 | `track_bar_cap01` | STATIC_COLORS['track_bar'] | fill, border |
| Sh29 | `track_bar_cap02` | STATIC_COLORS['track_bar'] | fill, border |
| Sh37 | `track_bar_cap03` | STATIC_COLORS['track_bar'] | fill, border |
| Sh45 | `track_bar_cap04` | STATIC_COLORS['track_bar'] | fill, border |
| Sh53 | `track_bar_cap05` | STATIC_COLORS['track_bar'] | fill, border |
| Sh62 | `track_bar_cap06` | STATIC_COLORS['track_bar'] | fill, border |
| Sh70 | `track_bar_cap07` | STATIC_COLORS['track_bar'] | fill, border |
| Sh78 | `track_bar_cap08` | STATIC_COLORS['track_bar'] | fill, border |
| Sh86 | `track_bar_cap09` | STATIC_COLORS['track_bar'] | fill, border |
| Sh95 | `track_bar_cap10` | STATIC_COLORS['track_bar'] | fill, border |
| Sh103 | `track_bar_cap11` | STATIC_COLORS['track_bar'] | fill, border |
| Sh111 | `track_bar_cap12` | STATIC_COLORS['track_bar'] | fill, border |
| Sh119 | `track_bar_cap13` | STATIC_COLORS['track_bar'] | fill, border |
| Sh128 | `track_bar_cap14` | STATIC_COLORS['track_bar'] | fill, border |
| Sh136 | `track_bar_cap15` | STATIC_COLORS['track_bar'] | fill, border |
| Sh144 | `track_bar_cap16` | STATIC_COLORS['track_bar'] | fill, border |
| Sh152 | `track_bar_cap17` | STATIC_COLORS['track_bar'] | fill, border |

### Text input: `CAPABILITY_ORDER[0] = 'Digital Strategy & Vision'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh19 | `cap_name_cap01` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[10] = 'Operational Risk & Fraud'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh101 | `cap_name_cap11` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[11] = 'Compliance & Surveillance'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh109 | `cap_name_cap12` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[12] = 'Business Resilience & TPRM'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh117 | `cap_name_cap13` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[13] = 'Data Governance'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh126 | `cap_name_cap14` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[14] = 'Analytics & AI Enablement'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh134 | `cap_name_cap15` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[15] = 'Architecture & Integration'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh142 | `cap_name_cap16` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[16] = 'Platform Enablement'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh150 | `cap_name_cap17` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[1] = 'Governance & Risk Appetite'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh27 | `cap_name_cap02` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[2] = 'Innovation Management'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh35 | `cap_name_cap03` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[3] = 'Culture & Change Enablement'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh43 | `cap_name_cap04` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[4] = 'Sustainable Finance & ESG'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh51 | `cap_name_cap05` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[5] = 'Digital Marketing & Acquisition'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh60 | `cap_name_cap06` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[6] = 'Onboarding & Fulfillment'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh68 | `cap_name_cap07` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[7] = 'Omnichannel Servicing'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh76 | `cap_name_cap08` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[8] = 'Personalization & Engagement'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh84 | `cap_name_cap09` | set_shape_text (text content) | text |

### Text input: `CAPABILITY_ORDER[9] = 'Process Automation'`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh93 | `cap_name_cap10` | set_shape_text (text content) | text |

## Slide 16

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `headline` | set_shape_text (text content) | text |

### Text input: `input.opportunity_intro`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh4 | `intro` | set_shape_text (text content) | text |

### Text input: `input.outcomes (3-5 bullets)`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `outcomes` | set_shape_text (text content) | text |

### Theme ref: `THEME_REFS['s16_arrow_fill']` = `schemeClr:accent4`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh11 | `arrow` | schemeClr:accent4 (preserved) | — |

### Theme ref: `THEME_REFS['s16_left_panel_bg']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `left_panel_bg` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s16_opportunity_bg_1']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh5 | `opp_card_1_bg` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s16_opportunity_bg_2']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh6 | `opp_card_2_bg` | schemeClr:lt2 (preserved) | — |

### Theme ref: `THEME_REFS['s16_opportunity_bg_3']` = `schemeClr:lt2`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh7 | `opp_card_3_bg` | schemeClr:lt2 (preserved) | — |

### Text input: `opportunities[0]: bold name + Maturity Gap + Why`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh8 | `opp_card_1` | set_shape_text (text content) | text |

### Text input: `opportunities[1]: same structure`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh9 | `opp_card_2` | set_shape_text (text content) | text |

### Text input: `opportunities[2]: same structure`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh10 | `opp_card_3` | set_shape_text (text content) | text |

## Slide 20

### Text input: `input.deliverables (≥3 items)`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh12 | `deliverables_body` | set_shape_text (text content) | text |

### Text input: `input.goal_statement`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh2 | `goal_statement` | set_shape_text (text content) | text |

### Text input: `input.headline`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh3 | `headline` | set_shape_text (text content) | text |

### Text input: `input.next_steps (≥3 rows: Date|Action|Owner)`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `next_steps_body` | set_shape_text (text content) | text |

### Static: `STATIC_COLORS['zennify_light_purple']` = `#F2F4F9`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh4 | `step_chip_1` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh6 | `step_chip_2` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh8 | `step_chip_3` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh10 | `step_chip_4` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh13 | `deliv_chip_1` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh15 | `deliv_chip_2` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh17 | `deliv_chip_3` | STATIC_COLORS['zennify_light_purple'] | — |
| Sh19 | `deliv_chip_4` | STATIC_COLORS['zennify_light_purple'] | — |

## Slide 21

### Text input: `input.presenter_email`

| Shape | Role | Transform | Writes |
|---|---|---|---|
| Sh0 | `presenter_email` | set_shape_text (text content) | text |


---

## Inverse Index — All Consumers of Each Input

Useful when changing an input: find every shape that will move.

| Input | Consumers (slide.sh) | Count |
|---|---|---|
| `input.client_logo` | s1.Sh2 | 1 |
| `input.deliverables (≥3 items)` | s20.Sh12 | 1 |
| `input.goal_statement` | s20.Sh2 | 1 |
| `input.headline` | s1.Sh0, s6.Sh2, s13.Sh11, s14.Sh1, s16.Sh3, s20.Sh3 | 6 |
| `input.metrics[0].context` | s6.Sh29 | 1 |
| `input.metrics[0].label` | s6.Sh27 | 1 |
| `input.metrics[0].value` | s6.Sh28 | 1 |
| `input.metrics[1].context` | s6.Sh33 | 1 |
| `input.metrics[1].label` | s6.Sh31 | 1 |
| `input.metrics[1].value` | s6.Sh32 | 1 |
| `input.metrics[2].context` | s6.Sh37 | 1 |
| `input.metrics[2].label` | s6.Sh35 | 1 |
| `input.metrics[2].value` | s6.Sh36 | 1 |
| `input.next_steps (≥3 rows: Date|Action|Owner)` | s20.Sh0 | 1 |
| `input.opportunity_intro` | s16.Sh4 | 1 |
| `input.outcomes (3-5 bullets)` | s16.Sh12 | 1 |
| `input.pillars.P1.insight` | s10.Sh12 | 1 |
| `input.pillars.P2.insight` | s10.Sh8 | 1 |
| `input.pillars.P3.insight` | s10.Sh10 | 1 |
| `input.pillars.P4.insight` | s10.Sh3 | 1 |
| `input.platform_summary` | s6.Sh25 | 1 |
| `input.platforms[0]` | s6.Sh20 | 1 |
| `input.platforms[1]` | s6.Sh21 | 1 |
| `input.platforms[2]` | s6.Sh22 | 1 |
| `input.platforms[3]` | s6.Sh23 | 1 |
| `input.platforms[4]` | s6.Sh24 | 1 |
| `input.presenter_email` | s21.Sh0 | 1 |
| `input.priorities[0].desc` | s6.Sh12 | 1 |
| `input.priorities[0].name` | s6.Sh11 | 1 |
| `input.priorities[1].desc` | s6.Sh15 | 1 |
| `input.priorities[1].name` | s6.Sh14 | 1 |
| `input.priorities[2].desc` | s6.Sh18 | 1 |
| `input.priorities[2].name` | s6.Sh17 | 1 |
| `input.strengths[0]` | s13.Sh6 | 1 |
| `input.strengths[0] + '\n' + input.strengths[1]` | s10.Sh42 | 1 |
| `input.strengths[1]` | s13.Sh7 | 1 |
| `input.strengths[2]` | s13.Sh9 | 1 |
| `input.strengths[3]` | s13.Sh10 | 1 |
| `s10.pillar_scores.P1` | s10.Sh16 | 1 |
| `s10.pillar_scores.P2` | s10.Sh15 | 1 |
| `s10.pillar_scores.P3` | s10.Sh14 | 1 |
| `s10.pillar_scores.P4` | s10.Sh2 | 1 |
| `s10.rec_scores[0]` | s10.Sh17, s10.Sh18, s10.Sh19 | 3 |
| `s10.rec_scores[1]` | s10.Sh20, s10.Sh21, s10.Sh22 | 3 |
| `s10.rec_scores[2]` | s10.Sh23, s10.Sh24, s10.Sh25 | 3 |
| `s13.pillar_levels.P1` | s13.Sh19, s13.Sh20, s13.Sh21, s13.Sh22 | 4 |
| `s13.pillar_levels.P2` | s13.Sh23, s13.Sh24, s13.Sh25, s13.Sh26 | 4 |
| `s13.pillar_levels.P3` | s13.Sh27, s13.Sh28, s13.Sh29, s13.Sh30 | 4 |
| `s13.pillar_levels.P4` | s13.Sh31, s13.Sh32, s13.Sh33, s13.Sh34 | 4 |
| `s14.scores[0]` | s14.Sh17, s14.Sh18, s14.Sh22, s14.Sh24 | 4 |
| `s14.scores[0] formatted` | s14.Sh20 | 1 |
| `s14.scores[10]` | s14.Sh99, s14.Sh100, s14.Sh104, s14.Sh106 | 4 |
| `s14.scores[10] formatted` | s14.Sh102 | 1 |
| `s14.scores[11]` | s14.Sh107, s14.Sh108, s14.Sh112, s14.Sh114 | 4 |
| `s14.scores[11] formatted` | s14.Sh110 | 1 |
| `s14.scores[12]` | s14.Sh115, s14.Sh116, s14.Sh120, s14.Sh122 | 4 |
| `s14.scores[12] formatted` | s14.Sh118 | 1 |
| `s14.scores[13]` | s14.Sh124, s14.Sh125, s14.Sh129, s14.Sh131 | 4 |
| `s14.scores[13] formatted` | s14.Sh127 | 1 |
| `s14.scores[14]` | s14.Sh132, s14.Sh133, s14.Sh137, s14.Sh139 | 4 |
| `s14.scores[14] formatted` | s14.Sh135 | 1 |
| `s14.scores[15]` | s14.Sh140, s14.Sh141, s14.Sh145, s14.Sh147 | 4 |
| `s14.scores[15] formatted` | s14.Sh143 | 1 |
| `s14.scores[16]` | s14.Sh148, s14.Sh149, s14.Sh153, s14.Sh155 | 4 |
| `s14.scores[16] formatted` | s14.Sh151 | 1 |
| `s14.scores[1]` | s14.Sh25, s14.Sh26, s14.Sh30, s14.Sh32 | 4 |
| `s14.scores[1] formatted` | s14.Sh28 | 1 |
| `s14.scores[2]` | s14.Sh33, s14.Sh34, s14.Sh38, s14.Sh40 | 4 |
| `s14.scores[2] formatted` | s14.Sh36 | 1 |
| `s14.scores[3]` | s14.Sh41, s14.Sh42, s14.Sh46, s14.Sh48 | 4 |
| `s14.scores[3] formatted` | s14.Sh44 | 1 |
| `s14.scores[4]` | s14.Sh49, s14.Sh50, s14.Sh54, s14.Sh56 | 4 |
| `s14.scores[4] formatted` | s14.Sh52 | 1 |
| `s14.scores[5]` | s14.Sh58, s14.Sh59, s14.Sh63, s14.Sh65 | 4 |
| `s14.scores[5] formatted` | s14.Sh61 | 1 |
| `s14.scores[6]` | s14.Sh66, s14.Sh67, s14.Sh71, s14.Sh73 | 4 |
| `s14.scores[6] formatted` | s14.Sh69 | 1 |
| `s14.scores[7]` | s14.Sh74, s14.Sh75, s14.Sh79, s14.Sh81 | 4 |
| `s14.scores[7] formatted` | s14.Sh77 | 1 |
| `s14.scores[8]` | s14.Sh82, s14.Sh83, s14.Sh87, s14.Sh89 | 4 |
| `s14.scores[8] formatted` | s14.Sh85 | 1 |
| `s14.scores[9]` | s14.Sh91, s14.Sh92, s14.Sh96, s14.Sh98 | 4 |
| `s14.scores[9] formatted` | s14.Sh94 | 1 |
| `sv.descriptor` | s3.Sh3 | 1 |
| `sv.p2_name_override OR 'Customer Experience'` | s10.Sh9 | 1 |
| `sv.tagline + ' ' + date` | s1.Sh1 | 1 |


---

## Debugging Guide

When `cross_slide_checker.py` reports a CRITICAL mismatch, use this graph to
trace the root cause without guessing.

### Example 1 — Wrong fill on a rec card

**QA reports:**

```
CRITICAL: Slide 10 Sh23 (rec3_card_bg) [fill]
  Driver:   s10.rec_scores[2] = 1.2
  Derived:  score_to_level_4tier(1.2) = 'Activating'; LEVEL_4TIER['Activating']['card_bg']
  Expected: #FFF3E8
  Actual:   srgb:F2F4F9
```

**Trace:**
1. Look up `s10.rec_scores[2]` in the Slide 10 section above → confirms Sh23
   is driven by the third rec's current_score.
2. Chain: `1.2 → score_to_level_4tier → 'Activating' → LEVEL_4TIER['Activating']['card_bg'] = #FFF3E8`.
3. Actual `#F2F4F9` is the **Building** `card_bg` (check `color_authority.md`).
4. Hypothesis: editor applied Building palette instead of Activating — likely
   the input score was 2.1 (passed to editor) but the QA was given 1.2.
5. Next step: verify the same input JSON was passed to the editor and the QA;
   regenerate the deck with the correct value.

### Example 2 — Wrong level label text

**QA reports:**

```
CRITICAL: Slide 14 Sh24 (level_label_cap01) [text_color]
  Driver:   s14.scores[0] = 2.45
  Derived:  score_to_level_4tier(2.45) = 'Building'; LEVEL_4TIER['Building']['label_text']
  Expected: #4E5E8A
  Actual:   srgb:F97316
```

**Trace:**
1. `s14.scores[0]` = first capability score (Digital Strategy & Vision per
   `CAPABILITY_ORDER`).
2. Score 2.45 → Building → label_text #4E5E8A (per `brand_level_tables.md`).
3. Actual `#F97316` is the Activating `accent/label_text` color.
4. This is a classic stale-edit problem: the editor wrote the `Activating`
   palette but the score is `Building`. Either the editor was run with an
   older input where this capability was below 1.5, or the editor's
   `score_to_level_4tier` call used the wrong score.

### Example 3 — Template drift (static color changed)

**QA reports:**

```
CRITICAL: Slide 6 Sh10 (p1_strip) [fill]
  Driver:   STATIC_COLORS['zennify_teal']
  Derived:  = #27BBAF
  Expected: #27BBAF
  Actual:   srgb:00A693
```

**Trace:**
1. Not a score issue — `STATIC_COLORS` lookup.
2. Template must have been re-exported from Google Slides with a
   slightly-different accent teal, OR a previous editor run accidentally
   overwrote it.
3. Check `slide6_editor.py` post-edit verification (`verify_slide6`) — if
   the verify step passed, the template shipped with the drift; if the
   verify step failed, the editor is leaving it unfixed.
4. Fix: bump template version OR have `slide6_editor.py` re-apply the
   STATIC fill on this shape during the edit loop.

### Chain walk: score → hex

For any score-driven shape, the chain is:

```
  input data source (e.g. s10.rec_scores[0])
    ↓
  score_to_level_Ntier(score)  (4-tier on Slides 10/14; 5-tier on Slide 13)
    ↓
  LEVEL_NTIER[level][palette_key]   (palette_key from the role spec)
    ↓
  expected hex
    ↓
  editor writes via apply_color_role
    ↓
  QA reads and compares
```

When any step diverges, the QA error message pins the exact break point.

### Static color chain

For static-colored shapes, the chain is shorter:

```
  STATIC_COLORS['source_key']
    ↓
  expected hex
    ↓
  editor (re-)applies via apply_color_role
    ↓
  QA reads and compares
```

If QA reports a static mismatch, the template is the suspect — either it
shipped with drift, or an unrelated edit corrupted it. Editors with
verify_* functions (slide6, slide10, slide13, slide14) will report this
during their post-edit pass.

### Theme-ref chain

For theme-ref shapes (Slide 13 pillar-row backgrounds, Slide 16 arrow):

```
  THEME_REFS['source_key'] = schemeClr:accent3 (or similar)
    ↓
  editor MUST NOT overwrite — leaves <a:schemeClr> in place
    ↓
  QA reads the <a:solidFill>/<a:schemeClr> element; if it finds
  <a:srgbClr> instead, editor has a bug (wrote explicit color over scheme)
```

The editor's `apply_color_role` deliberately skips `theme_ref` roles — no
writes — so any `theme_ref` mismatch is an upstream data issue (a
different editor or a manual edit touched the shape).

