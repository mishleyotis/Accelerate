# Deprecated QA scripts

## cross_slide_checker_pre_batch3.py (retired Batch 3, 2026-04)

Pre-Batch-3 checker used reverse color-hex lookup (`LEVEL_FILLS` dict) to infer
what level each shape was at, then checked cross-slide consistency. This
approach was brittle:
- Reverse lookup loses context: if a color was wrong, the error couldn't
  explain WHY (just "expected A, got B")
- Multiple levels share colors (e.g., Building accent #8094C0 is also the
  muted_header static color) — reverse lookup was ambiguous
- `LEVEL_FILLS` dict was stale and partially wrong (mapped #B0EED3 → level 3
  when it's actually 5-tier Transformational bg)

Replaced by `cross_slide_checker.py` which takes the same input_data the
editors took and walks every role in `color_level_system.ALL_SLIDE_ROLES`,
deriving expected state via the SAME score→level→palette→hex chain the editors
used, then asserting actual matches expected. Errors now cite the input driver
that fed the expectation.
