# QA capture rig (2026-06-11 wireframe-fidelity rebuild)

Reproduces the evidence loop the rebuild was driven by:

1. Serve the authoritative wireframe at :8082 (`python3 -m http.server 8082`
   from a dir whose index.html = docs/wireframe-2026-06/DMA_Insights__Standalone.html).
2. `node proto-capture-full.mjs` + `node proto-capture-2.mjs` → `/tmp/proto-shots`
   (every route, drawer/modal/panel transitions, customer audience, 5 widths).
3. Backend :8000 seeded (historical_backfill --dir tests/fixtures/dma_packages_batches
   --force + the §2c refresh chain) + vite :5173 → `node prod-capture.mjs`
   → `/tmp/prod-shots` (selector failures it logs ARE findings).
4. `python diff-qa.py` → strict pixel table + `/tmp/qa-diffs/*.png`;
   `python sbs.py <pair> [croppx]` → side-by-side composites in `/tmp/qa-sbs`.
5. `python make-sheets.py` → per-page all-client contact sheets from a
   `scripts/corpus-screenshots.mjs` run.

Read docs/PROTOTYPE_DIFF_REPORT.md for the metric's content-vs-structure
caveat before judging numbers.
