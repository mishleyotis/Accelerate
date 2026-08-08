#!/usr/bin/env python3
"""
generate_color_docs.py — Regenerate human-readable markdown docs from
color_level_system.py. These docs are the canonical reference for the
brand color system, per-slide role tables, and score-to-level mappings.

Run whenever color_level_system.py changes. Output paths:
  references/_generated/color_authority.md      — every color, every palette
  references/_generated/per_slide_role_tables.md — shape-by-shape role catalogue
  references/_generated/brand_level_tables.md    — 4-tier + 5-tier score ranges

A companion script `check_docs_in_sync.py` runs this generator and diffs
the output against the checked-in files; if they differ, the docs are stale.

Each generated file gets a header banner:

    <!-- DO NOT EDIT: regenerated from color_level_system.py via
         scripts/utils/generate_color_docs.py
         Run the script when the config changes. -->
"""
import datetime
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BRAND = _HERE.parent.parent / "references" / "01_brand"
_OUT = _HERE.parent.parent / "references" / "_generated"
sys.path.insert(0, str(_BRAND))
import color_level_system as cls  # noqa: E402


BANNER_LINES = [
    "<!-- DO NOT EDIT DIRECTLY.",
    "",
    "     This file is regenerated from `references/01_brand/color_level_system.py`",
    "     via `scripts/utils/generate_color_docs.py`. Any changes made here will be",
    "     overwritten on the next regeneration.",
    "",
    "     To change a color, palette, score range, or role: edit the config Python",
    "     file, then re-run the generator and commit both. `check_docs_in_sync.py`",
    "     will fail CI if they drift.",
    "-->",
    "",
]


def banner():
    return "\n".join(BANNER_LINES)


# ══════════════════════════════════════════════════════════════════════════════
# 1. color_authority.md — every color, every palette, single source of truth
# ══════════════════════════════════════════════════════════════════════════════

def gen_color_authority():
    lines = [banner(), "# Color Authority", "",
             "_Canonical color reference for the DMA First Call Deck skill._",
             "",
             "This is the single source of truth for every hex value used by the",
             "editors. If any reference file, editing contract, or script cites a",
             "different hex, this document wins.",
             ""]

    # ── 4-tier levels ─────────────────────────────────────────────────
    lines.append("## 4-Tier Maturity Levels (Slides 10 + 14)")
    lines.append("")
    lines.append("Score ranges map to level names; each level has three palette slots:")
    lines.append("- **accent**: bar fill / pillar-strip / rec-card-strip")
    lines.append("- **card_bg**: rec-card background / heatmap capability-block bg")
    lines.append("- **label_text**: color of the level label text (BUILDING, COMPETING, …)")
    lines.append("")
    lines.append("| Level | Score Range | Accent | Card Bg | Label Text | Preview |")
    lines.append("|---|---|---|---|---|---|")
    for name, data in cls.LEVEL_4TIER.items():
        lo, hi = data["score_range"]
        accent = data["accent"]
        card_bg = data["card_bg"]
        label_text = data["label_text"]
        # Preview column: block each color as colored-text markdown (fallback: hex swatch emoji)
        preview = f"`{name.upper()}`"
        lines.append(f"| **{name}** | {lo:.2f} – {hi:.2f} | `#{accent}` | `#{card_bg}` | `#{label_text}` | {preview} |")
    lines.append("")

    # ── 5-tier levels ─────────────────────────────────────────────────
    lines.append("## 5-Tier Maturity Levels (Slide 13 pillar indicators)")
    lines.append("")
    lines.append("Score ranges map to level numbers 1–5; each level has four palette slots:")
    lines.append("- **bg_rect**: pillar-row background rectangle")
    lines.append("- **circle**: the numbered circle")
    lines.append("- **num_text**: color of the number inside the circle")
    lines.append("- **label_text**: color of the level label (Emerging, Developing, …)")
    lines.append("")
    lines.append("| # | Label | Score Range | Bg Rect | Circle | Num Text | Label Text |")
    lines.append("|---|---|---|---|---|---|---|")
    for num, data in cls.LEVEL_5TIER.items():
        lo, hi = data["score_range"]
        lines.append(f"| {num} | **{data['label']}** | {lo:.2f} – {hi:.2f} | "
                     f"`#{data['bg_rect']}` | `#{data['circle']}` | "
                     f"`#{data['num_text']}` | `#{data['label_text']}` |")
    lines.append("")

    # ── Static colors ─────────────────────────────────────────────────
    lines.append("## Static Colors")
    lines.append("")
    lines.append("Colors that are not data-driven; used for brand panels, legends, and")
    lines.append("decorative elements. Editors verify these are preserved and re-apply")
    lines.append("them if the template has drifted.")
    lines.append("")
    lines.append("| Source Key | Hex | Usage |")
    lines.append("|---|---|---|")
    STATIC_NOTES = {
        "zennify_teal":        "priority strips (Slide 6)",
        "zennify_mint_bg":     "metric card backgrounds (Slide 6)",
        "zennify_light_purple": "top banners + icon chips (Slides 6, 10, 20)",
        "muted_header":        "eyebrow/header small-caps text across slides",
        "track_bar":           "17 heatmap track bars (Slide 14)",
        "median_stroke":       "17 heatmap median connectors + legend (Slide 14)",
        "s10_logo_frame":      "Slide 10 client-logo placeholder frame",
        "s6_logo_frame":       "Slide 6 client-logo placeholder frame",
        "s10_strengths_bg":    "Slide 10 competitive strengths card background",
        "s10_strengths_accent": "Slide 10 competitive strengths accent strip",
    }
    for key, hex_val in sorted(cls.STATIC_COLORS.items()):
        note = STATIC_NOTES.get(key, "")
        lines.append(f"| `{key}` | `#{hex_val}` | {note} |")
    lines.append("")

    # ── Theme refs ─────────────────────────────────────────────────────
    lines.append("## Theme References")
    lines.append("")
    lines.append("Shapes intentionally bound to the theme scheme (`<a:schemeClr>`) rather")
    lines.append("than explicit sRGB. Editors MUST NOT overwrite these with `srgbClr` —")
    lines.append("doing so breaks the template's dark-mode / brand-variant behavior.")
    lines.append("")
    lines.append("| Source Key | Scheme Ref |")
    lines.append("|---|---|")
    for key, ref in sorted(cls.THEME_REFS.items()):
        lines.append(f"| `{key}` | `{ref}` |")
    lines.append("")

    # ── Cross-slide consistency rule ───────────────────────────────────
    lines.append("## Cross-Slide Consistency")
    lines.append("")
    lines.append("The editors derive all colors from the same score inputs via the same")
    lines.append("`score_to_level_*` chain. If Slide 10 P4 pillar strip is Activating")
    lines.append("orange, then the Slide 14 Data & Technology column's dominant level")
    lines.append("(avg of its 4 capabilities) should also be Activating or at most 1 step")
    lines.append("away. `cross_slide_checker.py` enforces this.")
    lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 2. per_slide_role_tables.md — every editable shape on every slide
# ══════════════════════════════════════════════════════════════════════════════

def gen_per_slide_role_tables():
    lines = [banner(), "# Per-Slide Role Tables", "",
             "_Every shape edited by the skill, organized by slide._",
             "",
             "Each row is one shape in the slide's role catalogue. Editors iterate these",
             "tables and apply writes per the `F`/`B`/`T`/`TC` (Fill / Border / Text /",
             "Text-Color) flags.",
             "",
             "Columns:",
             "- **Sh#** — 0-indexed shape index on the slide",
             "- **Role** — logical name used by the editor",
             "- **Type** — `data` (score-driven) | `static` (fixed hex) | `theme_ref`",
             "  (schemeClr, preserve) | `text` (text-only) | `image` (image, not edited)",
             "- **Source** — for `data`: dotted input path (e.g. `s10.rec_scores[0]`);",
             "  for `static`: key into `STATIC_COLORS`; for `theme_ref`: key into `THEME_REFS`",
             "- **Palette** — slot in `LEVEL_*TIER[level]` (e.g. `accent`, `card_bg`)",
             "- **F/B/T/TC** — write flags: Fill, Border, Text content, Text Color",
             ""]

    SHAPE_COUNTS = {1: 3, 3: 37, 6: 40, 9: 23, 10: 44, 13: 46, 14: 158, 16: 14, 20: 21, 21: 2}

    slide_14_full = cls.get_slide14_full_roles()

    for slide_num in sorted(cls.ALL_SLIDE_ROLES.keys()):
        roles = cls.ALL_SLIDE_ROLES[slide_num]
        if slide_num == 14:
            roles = slide_14_full

        shape_count = SHAPE_COUNTS.get(slide_num, "?")
        lines.append(f"## Slide {slide_num} ({shape_count} shapes, {len(roles)} edited)")
        lines.append("")
        if not roles:
            lines.append(f"_No editable roles. Slide {slide_num} is **static** — template content ships ready._")
            lines.append("")
            continue

        lines.append("| Sh# | Role | Type | Source | Palette | F | B | T | TC |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for idx in sorted(roles.keys()):
            role_name, ctype, source, palette_key, wf, wb, wt, wtc = roles[idx]
            def mark(b): return "✓" if b else "·"
            src = f"`{source}`" if source else "—"
            palette = f"`{palette_key}`" if palette_key else "—"
            lines.append(f"| {idx} | `{role_name}` | `{ctype}` | {src} | {palette} | "
                         f"{mark(wf)} | {mark(wb)} | {mark(wt)} | {mark(wtc)} |")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 3. brand_level_tables.md — focused on the level/score mappings
# ══════════════════════════════════════════════════════════════════════════════

def gen_brand_level_tables():
    lines = [banner(), "# Brand Level Tables", "",
             "_Score-to-level and level-to-palette mappings used across the deck._",
             "",
             "These mappings are exposed by the config as `score_to_level_4tier` and",
             "`score_to_level_5tier`; editors call them directly, and QA derives every",
             "expected hex via the same functions.",
             ""]

    # 4-tier ranges
    lines.append("## 4-Tier Level Function: `score_to_level_4tier(score: float) -> str`")
    lines.append("")
    lines.append("Used by Slides 10 and 14.")
    lines.append("")
    lines.append("```python")
    lines.append("if score < 1.50:  return 'Activating'")
    lines.append("if score < 2.50:  return 'Building'")
    lines.append("if score < 3.50:  return 'Competing'")
    lines.append("return 'Differentiating'")
    lines.append("```")
    lines.append("")
    lines.append("| Score Range | Level | Notes |")
    lines.append("|---|---|---|")
    for name, data in cls.LEVEL_4TIER.items():
        lo, hi = data["score_range"]
        range_str = f"[{lo:.2f}, {hi:.2f}"
        range_str += "]" if name == "Differentiating" else ")"
        lines.append(f"| {range_str} | **{name}** | — |")
    lines.append("")

    # 5-tier ranges
    lines.append("## 5-Tier Level Function: `score_to_level_5tier(score: float) -> int`")
    lines.append("")
    lines.append("Used by Slide 13 pillar indicators.")
    lines.append("")
    lines.append("```python")
    lines.append("if score < 1.00:  return 1  # " + cls.LEVEL_5TIER[1]["label"])
    lines.append("if score < 2.00:  return 2  # " + cls.LEVEL_5TIER[2]["label"])
    lines.append("if score < 3.00:  return 3  # " + cls.LEVEL_5TIER[3]["label"])
    lines.append("if score < 4.00:  return 4  # " + cls.LEVEL_5TIER[4]["label"])
    lines.append("return 5                    # " + cls.LEVEL_5TIER[5]["label"])
    lines.append("```")
    lines.append("")
    lines.append("| Score Range | # | Label |")
    lines.append("|---|---|---|")
    for num, data in cls.LEVEL_5TIER.items():
        lo, hi = data["score_range"]
        range_str = f"[{lo:.2f}, {hi:.2f}"
        range_str += "]" if num == 5 else ")"
        lines.append(f"| {range_str} | {num} | **{data['label']}** |")
    lines.append("")

    # Loose 5-to-4 mapping for cross-slide consistency
    lines.append("## 5-Tier ↔ 4-Tier Loose Mapping")
    lines.append("")
    lines.append("Used by `cross_slide_checker.verify_cross_slide` to check Slide 13's")
    lines.append("5-tier indicator is consistent with Slide 10's 4-tier strips for the")
    lines.append("same pillar. Input scores should be identical; if they differ by more")
    lines.append("than 0.1, it's a warning (likely data pipeline inconsistency).")
    lines.append("")
    lines.append("| 5-Tier | Approx Score | 4-Tier Equivalent |")
    lines.append("|---|---|---|")
    lines.append(f"| 1 {cls.LEVEL_5TIER[1]['label']} | < 1.00 | Activating |")
    lines.append(f"| 2 {cls.LEVEL_5TIER[2]['label']} | 1.00–1.99 | Activating / Building |")
    lines.append(f"| 3 {cls.LEVEL_5TIER[3]['label']} | 2.00–2.99 | Building / Competing |")
    lines.append(f"| 4 {cls.LEVEL_5TIER[4]['label']} | 3.00–3.99 | Competing / Differentiating |")
    lines.append(f"| 5 {cls.LEVEL_5TIER[5]['label']} | ≥ 4.00 | Differentiating |")
    lines.append("")

    return "\n".join(lines)


def main():
    _OUT.mkdir(parents=True, exist_ok=True)

    outputs = {
        "color_authority.md":        gen_color_authority(),
        "per_slide_role_tables.md":  gen_per_slide_role_tables(),
        "brand_level_tables.md":     gen_brand_level_tables(),
    }

    for name, content in outputs.items():
        path = _OUT / name
        path.write_text(content + "\n")
        print(f"✓ Wrote {path} ({len(content.splitlines())} lines)")

    print(f"\nAll {len(outputs)} docs regenerated under {_OUT}")


if __name__ == "__main__":
    main()
