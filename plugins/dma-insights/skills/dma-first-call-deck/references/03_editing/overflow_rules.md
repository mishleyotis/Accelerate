# Overflow Prevention Rules

## Font Size → Character Width Table (DM Sans)

| Font (pt) | Chars/100px | 200px max | 400px max | 700px max |
|---|---|---|---|---|
| 7 | 26 | 52 | 104 | 182 |
| 8 | 23 | 46 | 92 | 161 |
| 9 | 20 | 40 | 80 | 140 |
| 10 | 18 | 36 | 72 | 126 |
| 11 | 16 | 32 | 64 | 112 |
| 12 | 15 | 30 | 60 | 105 |
| 13 | 14 | 28 | 56 | 98 |
| 14-15 | 12-13 | 24-26 | 48-52 | 84-91 |
| 16-18 | 10-11 | 20-22 | 40-44 | 70-77 |
| 19-21 | 9 | 18 | 36 | 63 |
| 22-24 | 8 | 16 | 32 | 56 |
| 25-26 | 7 | 14 | 28 | 49 |
| 42-45 | 4 | 8 | 16 | 28 |

## ⛔ SAFETY MARGIN RULE

The formula above gives the THEORETICAL maximum. Real slides have bold headers, paragraph spacing, empty separator lines, and font rendering differences. **Always apply a 30% safety margin** to the formula result. Example: if the formula says max 2600 chars, treat the real limit as ~1800 chars.

For shapes with dense per-component text (like Slide 10 priority rec cards or Slide 6 metric cards), the character budget is per-shape, not per-slide. See per-shape max chars in editing_contract.md.

**The rendered PNG is the final authority.** If text visually overflows even when under the char limit, the text is too long.

## Overflow Formula

```python
def check_overflow(shape_width_px, shape_height_px, font_pt, text):
    chars_per_line = shape_width_px / (font_pt * 0.55)
    max_lines = shape_height_px / (font_pt * 1.3)
    max_chars = int(chars_per_line * max_lines)
    estimated_lines = len(text) / chars_per_line
    
    overflow = len(text) > max_chars
    headline_too_long = estimated_lines > 2  # for headlines only
    
    return {
        "overflow": overflow,
        "headline_too_long": headline_too_long,
        "max_chars": max_chars,
        "text_chars": len(text),
        "estimated_lines": round(estimated_lines, 1),
        "buffer_pct": round((1 - len(text)/max_chars) * 100) if max_chars > 0 else 0
    }
```

## Overflow Actions

| Situation | Action |
|---|---|
| Bullet text overflows | Truncate lowest-priority items. Append `[...]`. |
| Body text overflows at template font | **Step 1:** Trim content (shorter synonyms, remove modifiers). **Step 2:** If still overflows, reduce font to Safe Minimum per Section 12 of editing_contract.md. **Step 3:** If still overflows at safe min, split content or flag `[TEXT TRUNCATED]`. |
| Headline > 2 lines | Shorten: remove modifiers, reduce specificity, split compound claims. If still > 2 lines, reduce font to Safe Minimum for that shape. |
| Capability description overflows | Tighten wording. Remove subordinate clauses. Reduce font if within safe range. |
| Any overflow at safe minimum font | Flag `[TEXT TRUNCATED]` for QA review. |

## Critical Slide Constraints (Font-Aware)

Use the **Target Font** column for max chars calculations. Shapes marked with ⚠️ REQUIRE mandatory font reduction.

| Slide | Shape | Template Font | Target Font | Max Chars (at target) | Notes |
|---|---|---|---|---|---|
| 1 Sh0 | headline | 30pt (layout) | 24pt | ~80 | 2-line headline ⚠️ |
| 6 Sh2 | headline | ~26pt | 24pt | ~130 | 2-line headline (new 40-shape layout) |
| 6 Sh11/14/17 | priority names | ~11pt bold | 11pt | ~40 | 1-line bold |
| 6 Sh12/15/18 | priority descs | ~9pt | 9pt | ~95 | 1-sentence fact→implication |
| 6 Sh20-24 | platform names | ~10pt | 10pt | ~35 each | 1 line per platform |
| 6 Sh27/31/35 | metric labels | ~8pt uppercase | 8pt | ~20 | 1–3 words |
| 6 Sh28/32/36 | metric values | ~24pt | 24pt | ~10 | Big display number |
| 6 Sh29/33/37 | metric context | ~8pt | 8pt | ~60 | 1-sentence |
| 9 Sh1 | sub-headline | 11pt | 11pt | ~324 | Sub-headline insight |
| 9 Sh13 | body | 10pt | 10pt | ~600 | Score paragraph |
| 10 Sh2 | headline | ~30pt | 30pt | ~70 (2 lines) | Static: "Where {client} stands and what comes next" |
| 10 Sh7 | narrative | ~11pt | 11pt | ~380 (4 lines) | Score vs peer + strengths + gaps |
| 10 Sh12/8/10/3 | pillar insights | ~9pt | 9pt | ~80 each | 1-sentence per pillar |
| 10 Sh36/37/38 | rec metrics | ~10pt | 10pt | ~75 each | "{cap} \| Maturity: X → Target: Y" |
| 13 Sh6-10 | bullets | 10pt | 10pt | ~35 each | Strength bullets — strict 1 line |
| 13 Sh11 | headline | 20pt | 20pt | ~130 | 2-line narrative headline |
| 14 Sh1 | headline | 26pt | 21pt | ~124 | 2-line heatmap headline ⚠️ |
| **16 Sh3** | **headline** | **26pt** | **21pt** | **~124** | **2-line opportunities headline ⚠️** |
| **16 Sh8-10** | **cards** | **11pt** | **9pt** | **~629–665 (target ~300)** | **Capability blocks ⚠️** |
| **16 Sh12** | **outcomes** | **10pt** | **9pt** | **~814 (target ~400)** | **Outcome bullets ⚠️** |
| 17-19 Sh4/10/13 | titles | inherited | inherited | ~35 each | Solution titles — 1 line |
| 17-19 Sh5/11/14 | desc | 12pt | 10pt | ~130–195 | Solution descriptions (trim to ≤120ch preferred) |
| 17-19 Sh9/12/15 | body | 9-10pt | 8pt (if needed) | ~800-1000 | Capability lists — longest text blocks |
| **20 Sh0** | **body** | **11pt** | **10pt** | **~1314** | **Next steps action table ⚠️ + b="0"** |
| 20 Sh3 | headline | ~19pt | ~19pt | ~100 | Next steps headline |
| **20 Sh8** | **body** | **11pt** | **10pt** | **~1160** | **Deliverables ⚠️ + b="0"** |
