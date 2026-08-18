#!/usr/bin/env python3
"""
generate_dependency_graph.py — Regenerate references/_generated/input_dependency_graph.md
from color_level_system.py.

Inverts the role catalogue: for every input data source (e.g. `s10.pillar_scores.P1`,
`input.client`), lists every shape that consumes it and through what transformation.

This makes every shape's final state traceable: if QA reports a mismatch on
Slide 10 Sh23, a reader can walk back through the chain to find which input
drove the expected state and where a break might have occurred.

Called by `generate_color_docs.py` (it runs in sequence) and verified by
`check_docs_in_sync.py`.
"""
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BRAND = _HERE.parent.parent / "references" / "01_brand"
_OUT = _HERE.parent.parent / "references" / "_generated"
sys.path.insert(0, str(_BRAND))
import color_level_system as cls  # noqa: E402


BANNER = """<!-- DO NOT EDIT DIRECTLY.

     This file is regenerated from `references/01_brand/color_level_system.py`
     via `scripts/utils/generate_dependency_graph.py`. Any changes made here
     will be overwritten on the next regeneration.

     This is the **causal chain** from input data → transformation →
     shape state. Use it to debug QA mismatches: given a failed shape,
     walk backward to find the input driver; given an input, see every
     shape it affects.
-->

"""


WRITE_FLAG_LABELS = {
    0: "fill", 1: "border", 2: "text", 3: "text_color"
}


def classify_source(source):
    """Return a bucket for grouping sources."""
    if source is None:
        return "other"
    if source.startswith("s10."):
        return "s10_data"
    if source.startswith("s13."):
        return "s13_data"
    if source.startswith("s14."):
        return "s14_data"
    if source.startswith("input."):
        return "input_text"
    if source.startswith("sv."):
        return "subvertical"
    if source in cls.STATIC_COLORS:
        return "static_color"
    if source in cls.THEME_REFS:
        return "theme_ref"
    return "other"


def transform_for(role_spec, slide_num):
    """Describe the transformation the editor applies for this role spec."""
    role_name, ctype, source, palette_key, wf, wb, wt, wtc = role_spec
    if ctype == "data":
        if slide_num == 13:
            return f"score_to_level_5tier(score) → LEVEL_5TIER[level]['{palette_key}']"
        else:
            return f"score_to_level_4tier(score) → LEVEL_4TIER[level]['{palette_key}']"
    if ctype == "static":
        return f"STATIC_COLORS['{source}']"
    if ctype == "theme_ref":
        return f"schemeClr:{cls.THEME_REFS.get(source, '?')} (preserved)"
    if ctype == "text":
        return "set_shape_text (text content)"
    if ctype == "image":
        return "image file replacement (by editor)"
    return "?"


def write_flags_str(wf, wb, wt, wtc):
    flags = []
    if wf: flags.append("fill")
    if wb: flags.append("border")
    if wt: flags.append("text")
    if wtc: flags.append("text_color")
    return ", ".join(flags) if flags else "—"


def build_inverse_index():
    """For every source, list the (slide, shape_idx, role_name, role_spec) consumers."""
    idx = defaultdict(list)

    slide_14_full = cls.get_slide14_full_roles()

    for slide_num in sorted(cls.ALL_SLIDE_ROLES.keys()):
        roles = cls.ALL_SLIDE_ROLES[slide_num]
        if slide_num == 14:
            roles = slide_14_full

        for shape_idx, role_spec in roles.items():
            source = role_spec[2]  # source field
            idx[source].append((slide_num, shape_idx, role_spec))
    return idx


def render_chain_by_slide():
    """Per-slide, group by source → show every shape chain."""
    lines = []
    slide_14_full = cls.get_slide14_full_roles()

    for slide_num in sorted(cls.ALL_SLIDE_ROLES.keys()):
        roles = cls.ALL_SLIDE_ROLES[slide_num]
        if slide_num == 14:
            roles = slide_14_full

        if not roles:
            lines.append(f"## Slide {slide_num}")
            lines.append("")
            lines.append(f"_Slide {slide_num} is static — no editable roles; no input dependencies._")
            lines.append("")
            continue

        lines.append(f"## Slide {slide_num}")
        lines.append("")

        # Group shapes by their data source
        by_source = defaultdict(list)
        for shape_idx, role_spec in roles.items():
            source = role_spec[2]
            by_source[source].append((shape_idx, role_spec))

        # Order: data sources first, then static, then theme_ref, then text/image
        def source_sort_key(s):
            cat = classify_source(s)
            order = {
                "s10_data": 0, "s13_data": 1, "s14_data": 2,
                "input_text": 3, "subvertical": 4,
                "static_color": 5, "theme_ref": 6, "other": 7
            }
            return (order.get(cat, 99), s or "")

        for source in sorted(by_source.keys(), key=source_sort_key):
            shapes = by_source[source]
            role_spec_sample = shapes[0][1]
            ctype = role_spec_sample[1]

            # Human-readable source heading
            if ctype == "data":
                heading = f"### Input: `{source}` (score)"
            elif ctype == "static":
                heading = f"### Static: `STATIC_COLORS['{source}']` = `#{cls.STATIC_COLORS.get(source, '?')}`"
            elif ctype == "theme_ref":
                heading = f"### Theme ref: `THEME_REFS['{source}']` = `schemeClr:{cls.THEME_REFS.get(source, '?')}`"
            elif ctype == "text":
                heading = f"### Text input: `{source}`"
            elif ctype == "image":
                heading = f"### Image: `{source}`"
            else:
                heading = f"### `{source}`"
            lines.append(heading)
            lines.append("")
            lines.append("| Shape | Role | Transform | Writes |")
            lines.append("|---|---|---|---|")

            for shape_idx, role_spec in sorted(shapes, key=lambda x: x[0]):
                role_name, ct, src, palette, wf, wb, wt, wtc = role_spec
                xform = transform_for(role_spec, slide_num)
                flags = write_flags_str(wf, wb, wt, wtc)
                lines.append(f"| Sh{shape_idx} | `{role_name}` | {xform} | {flags} |")
            lines.append("")

    return "\n".join(lines)


def render_inverse_index():
    """Global view: for each UNIQUE input source, every (slide, shape) that consumes it."""
    lines = ["## Inverse Index — All Consumers of Each Input", "",
             "Useful when changing an input: find every shape that will move.",
             ""]
    idx = build_inverse_index()
    # Only show actually-used sources
    data_sources = [s for s in idx.keys() if classify_source(s) in ("s10_data", "s13_data", "s14_data", "input_text", "subvertical")]
    if not data_sources:
        return "\n".join(lines)
    lines.append("| Input | Consumers (slide.sh) | Count |")
    lines.append("|---|---|---|")
    for source in sorted(data_sources):
        consumers = idx[source]
        # Collapse like shapes: format as "s10.Sh17-18,21-22,24-25"
        locations = sorted(set((c[0], c[1]) for c in consumers))
        loc_str = ", ".join(f"s{slide}.Sh{idx}" for slide, idx in locations)
        lines.append(f"| `{source}` | {loc_str} | {len(locations)} |")
    lines.append("")
    return "\n".join(lines)


def render_debug_guide():
    """Hand-written debugging guide — walks through how to use the graph."""
    return """## Debugging Guide

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
"""


def main():
    _OUT.mkdir(parents=True, exist_ok=True)

    lines = [BANNER]
    lines.append("# Input Dependency Graph")
    lines.append("")
    lines.append("_Every shape's final state → which input → through which transformation._")
    lines.append("")
    lines.append("This document inverts the role catalogue in `color_level_system.py`.")
    lines.append("Each editor walks forward (source → shape); this doc walks backward")
    lines.append("(shape → source). QA failures are debugged with the Debugging Guide")
    lines.append("at the bottom.")
    lines.append("")

    lines.append("## Per-Slide Chains")
    lines.append("")
    lines.append("For each slide, the shapes are grouped by their input source. All")
    lines.append("shapes under one heading are driven by the same input — changing")
    lines.append("that input moves all of them in lockstep.")
    lines.append("")

    lines.append(render_chain_by_slide())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(render_inverse_index())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(render_debug_guide())

    out_path = _OUT / "input_dependency_graph.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"✓ Wrote {out_path} ({len(lines)} logical blocks)")


if __name__ == "__main__":
    main()
