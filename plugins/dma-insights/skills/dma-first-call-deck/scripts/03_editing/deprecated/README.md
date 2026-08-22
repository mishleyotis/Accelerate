# Deprecated Editors

## slide9_editor.py (retired Batch 2, 2026-04)

**Reason:** Slide 9 in the current Zennify template is a *static* "What is a DMA?"
explainer with 23 shapes. The per-deck DMA Summary Dashboard (which this editor
was previously coded to edit) now lives on Slide 10 — see `slide10_editor.py`.

The editor was written against an older template variant where Slide 9 held
pillar cards with 3-tier benchmark colors (above/at/below peer median). Those
shapes (Sh27/28/29/3 + pillar accents) do not exist in the current template.

`color_level_system.SLIDE_9_ROLES` is deliberately empty for the current template.
If a future template revision moves per-deck content back onto Slide 9, this editor
can be restored — but it should be rewritten against the new role catalogue.

Kept in `deprecated/` to preserve the historical editing approach for reference.
