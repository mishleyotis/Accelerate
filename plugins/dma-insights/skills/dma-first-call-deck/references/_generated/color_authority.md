<!-- DO NOT EDIT DIRECTLY.

     This file is regenerated from `references/01_brand/color_level_system.py`
     via `scripts/utils/generate_color_docs.py`. Any changes made here will be
     overwritten on the next regeneration.

     To change a color, palette, score range, or role: edit the config Python
     file, then re-run the generator and commit both. `check_docs_in_sync.py`
     will fail CI if they drift.
-->

# Color Authority

_Canonical color reference for the DMA First Call Deck skill._

This is the single source of truth for every hex value used by the
editors. If any reference file, editing contract, or script cites a
different hex, this document wins.

## 4-Tier Maturity Levels (Slides 10 + 14)

Score ranges map to level names; each level has three palette slots:
- **accent**: bar fill / pillar-strip / rec-card-strip
- **card_bg**: rec-card background / heatmap capability-block bg
- **label_text**: color of the level label text (BUILDING, COMPETING, …)

| Level | Score Range | Accent | Card Bg | Label Text | Preview |
|---|---|---|---|---|---|
| **Activating** | 0.00 – 1.49 | `#F97316` | `#FFF3E8` | `#F97316` | `ACTIVATING` |
| **Building** | 1.50 – 2.49 | `#8094C0` | `#F2F4F9` | `#4E5E8A` | `BUILDING` |
| **Competing** | 2.50 – 3.49 | `#27BBAF` | `#E6F5F3` | `#198478` | `COMPETING` |
| **Differentiating** | 3.50 – 5.00 | `#185F60` | `#E8F7F6` | `#185F60` | `DIFFERENTIATING` |

## 5-Tier Maturity Levels (Slide 13 pillar indicators)

Score ranges map to level numbers 1–5; each level has four palette slots:
- **bg_rect**: pillar-row background rectangle
- **circle**: the numbered circle
- **num_text**: color of the number inside the circle
- **label_text**: color of the level label (Emerging, Developing, …)

| # | Label | Score Range | Bg Rect | Circle | Num Text | Label Text |
|---|---|---|---|---|---|---|
| 1 | **Foundational** | 0.00 – 0.99 | `#FFCB99` | `#FE9732` | `#F2F4F9` | `#1C4A4D` |
| 2 | **Developing** | 1.00 – 1.99 | `#C7D3EC` | `#8094C0` | `#F2F4F9` | `#1C4A4D` |
| 3 | **Established** | 2.00 – 2.99 | `#E6F3FA` | `#3D81F6` | `#F2F4F9` | `#1C4A4D` |
| 4 | **Advanced** | 3.00 – 3.99 | `#E8F7F6` | `#62D7B8` | `#F2F4F9` | `#1C4A4D` |
| 5 | **Transformational** | 4.00 – 5.00 | `#B0EED3` | `#27BBAF` | `#FFFFFF` | `#1C4A4D` |

## Static Colors

Colors that are not data-driven; used for brand panels, legends, and
decorative elements. Editors verify these are preserved and re-apply
them if the template has drifted.

| Source Key | Hex | Usage |
|---|---|---|
| `median_stroke` | `#3D81F6` | 17 heatmap median connectors + legend (Slide 14) |
| `s10_legend_act_acc` | `#F97316` |  |
| `s10_legend_act_bg` | `#FFF3E8` |  |
| `s10_legend_bld_acc` | `#8094C0` |  |
| `s10_legend_bld_bg` | `#F2F4F9` |  |
| `s10_legend_cmp_acc` | `#27BBAF` |  |
| `s10_legend_cmp_bg` | `#E6F5F3` |  |
| `s10_strengths_accent` | `#139F94` | Slide 10 competitive strengths accent strip |
| `s10_strengths_bg` | `#E8F7F6` | Slide 10 competitive strengths card background |
| `s14_legend_act_acc` | `#F97316` |  |
| `s14_legend_act_bg` | `#FFF3E8` |  |
| `s14_legend_bld_acc` | `#8094C0` |  |
| `s14_legend_bld_bg` | `#F2F4F9` |  |
| `s14_legend_cmp_acc` | `#27BBAF` |  |
| `s14_legend_cmp_bg` | `#E6F5F3` |  |
| `s14_legend_dif_acc` | `#185F60` |  |
| `s6_logo_frame` | `#E0EEF0` | Slide 6 client-logo placeholder frame |
| `track_bar` | `#E5E7EB` | 17 heatmap track bars (Slide 14) |
| `zennify_dark_teal` | `#1C4A4D` |  |
| `zennify_light_purple` | `#F2F4F9` | top banners + icon chips (Slides 6, 10, 20) |
| `zennify_mint_bg` | `#E8F7F6` | metric card backgrounds (Slide 6) |
| `zennify_muted_body` | `#3D5A5C` |  |
| `zennify_muted_header` | `#8094C0` |  |
| `zennify_teal` | `#27BBAF` | priority strips (Slide 6) |

## Theme References

Shapes intentionally bound to the theme scheme (`<a:schemeClr>`) rather
than explicit sRGB. Editors MUST NOT overwrite these with `srgbClr` —
doing so breaks the template's dark-mode / brand-variant behavior.

| Source Key | Scheme Ref |
|---|---|
| `s13_bar_top_1` | `lt2` |
| `s13_bar_top_2` | `lt2` |
| `s13_bar_top_3` | `lt2` |
| `s13_bar_top_4` | `lt2` |
| `s13_pillar_row_bg_1` | `lt2` |
| `s13_pillar_row_bg_2` | `lt2` |
| `s13_pillar_row_bg_3` | `lt2` |
| `s13_pillar_row_bg_4` | `lt2` |
| `s16_arrow_border` | `dk2` |
| `s16_arrow_fill` | `accent4` |
| `s16_left_panel_bg` | `lt2` |
| `s16_opportunity_bg_1` | `lt2` |
| `s16_opportunity_bg_2` | `lt2` |
| `s16_opportunity_bg_3` | `lt2` |
| `s6_logo_placeholder_fill` | `lt1` |

## Cross-Slide Consistency

The editors derive all colors from the same score inputs via the same
`score_to_level_*` chain. If Slide 10 P4 pillar strip is Activating
orange, then the Slide 14 Data & Technology column's dominant level
(avg of its 4 capabilities) should also be Activating or at most 1 step
away. `cross_slide_checker.py` enforces this.

