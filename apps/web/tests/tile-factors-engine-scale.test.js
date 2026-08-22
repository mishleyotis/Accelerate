/* The tile factor breakdown, on the engine's scale and nobody else's.
 *
 * Reported twice on 2026-08-19, both times with a screenshot of a live tile
 * drawer: two clients rendered two different "Composite factors" systems for
 * one number — a six-factor breakdown summing to 76.5 on one and a
 * three-factor breakdown summing to 67.0 on the other. The payload side is
 * pinned by CG-31 (factor names are the engine's four; tile composite equals
 * the card's engine fit). This file pins the RENDER side:
 *
 *   1. the drawer scales factor values as the engine emits them — 0..1, so
 *      the bar is value*100 of the rail, not the old 0..10 scale that would
 *      draw an engine bar at a tenth of its width;
 *   2. contributions render in points of 100, matching the headline the
 *      breakdown must sum toward;
 *   3. no legacy factor name is hardcoded anywhere in the compiled bundle —
 *      the renderer displays what the payload carries, and the payload gate
 *      refuses the legacy names, so a hardcoded fallback would be the one
 *      way the old vocabulary could still reach a reader.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS_DIR = path.join(__dirname, "..", "public", "proto", "js");

function bundle(name) {
  return fs.readFileSync(path.join(JS_DIR, name), "utf8");
}

function factorBlock() {
  const src = bundle("pages-d3-d4.js");
  const start = src.indexOf("Composite factors");
  assert.ok(start > 0,
    "the Composite factors drawer is gone from pages-d3-d4 — update this test");
  const end = src.indexOf("Cells it addresses", start);
  assert.ok(end > start,
    "the cells-it-addresses block moved — update this test");
  return src.slice(start, end);
}

test("the factor bar is drawn on the engine's 0..1 scale", () => {
  const block = factorBlock();
  assert.ok(block.includes("* 100"),
    "the bar width no longer multiplies the factor value by 100 — an "
    + "engine value of 0.95 would draw at a tenth of the rail");
  assert.ok(!/\*\s*10\)/.test(block),
    "the old 0..10 scale is back in the bar width");
});

test("contributions render in points of 100, toward the headline", () => {
  const block = factorBlock();
  assert.ok(/contribution\)\s*\*\s*100/.test(block),
    "the contribution is no longer multiplied into points of 100 — an "
    + "engine contribution of 0.5024 would render as +0.5 beside a "
    + "headline of 61.7");
});

test("no legacy factor name is hardcoded in any compiled page module", () => {
  const LEGACY = ["business_impact", "risk_exposure", "competitive_gap",
                  "effort_inverse", "quick_win", "trend_momentum",
                  "Addressable gap depth", "Sub-vertical relevance",
                  "Substrate already in place"];
  for (const f of fs.readdirSync(JS_DIR).filter((n) => n.endsWith(".js"))) {
    const src = bundle(f);
    for (const name of LEGACY) {
      assert.ok(!src.includes(name),
        `legacy factor name "${name}" is hardcoded in ${f} — the payload `
        + "gate (CG-31) refuses these names, so a hardcoded copy is the "
        + "one path left for the old vocabulary to reach a reader");
    }
  }
});

test("the storyline challenge has no renderer left in the bundle", () => {
  for (const f of fs.readdirSync(JS_DIR).filter((n) => n.endsWith(".js"))) {
    const src = bundle(f);
    assert.ok(!src.includes("OvStorylineChallenge"),
      `OvStorylineChallenge survives in ${f} — excluded by owner `
      + "instruction 2026-08-19");
    assert.ok(!src.includes("Storyline challenge"),
      `a "Storyline challenge" label survives in ${f}`);
  }
});
