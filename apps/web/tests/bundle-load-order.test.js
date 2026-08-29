/* Every harness that loads the compiled bundle loads it in the browser's order.
 *
 * data.js refuses to define a colour mapping unless window.DMA_BANDS is
 * already there — invariant 7, AUD-0048: one authored resolver, one runtime
 * resolver, and never a silent second one. app/route.js SCRIPTS therefore
 * loads proto/js/bands.js FIRST among the prototype's own modules.
 *
 * On 2026-08-29 five separate harnesses did not, and the guard fired at
 * require time in each: 66 of 231 web tests red, reported as 66 independent
 * failures when they were one missing module. The guard behaved perfectly —
 * loud, specific, naming the file and the reason. What was missing was
 * anything asserting that the harnesses load what the page loads.
 *
 * So this test reads the loaders rather than the product: any test file that
 * pulls in the compiled data.js must also pull in bands.js, and earlier in
 * the file. It fails on the SIXTH harness, at the moment it is written,
 * instead of in CI as a wall of unrelated-looking failures. */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const DIR = __dirname;

/* A require of the COMPILED module, not a mention of it in prose. The
 * distinction matters: subvertical-label.test.js reads data.js with
 * readFileSync to assert on its source text and never executes it, so it
 * cannot trip the guard and must not be forced to load bands.js. */
const REQUIRES = /require\(\s*path\.join\([^)]*?["']([a-z0-9-]+\.js)["']\s*\)/g;
const IN_LIST = /["']([a-z0-9-]+\.js)["']/g;

function loadedModules(src) {
  /* Both shapes the harnesses use: a direct require(path.join(JS, "x.js")),
     and a for-loop over an array of names that is then required. */
  const out = [];
  for (const m of src.matchAll(REQUIRES)) out.push([m.index, m[1]]);
  for (const block of src.matchAll(/for\s*\(const \w+ of \[([\s\S]*?)\]\)/g)) {
    for (const n of block[1].matchAll(IN_LIST)) out.push([block.index, n[1]]);
  }
  return out.sort((a, b) => a[0] - b[0]).map(([, n]) => n);
}

const files = fs.readdirSync(DIR)
  .filter((f) => f.endsWith(".js"))
  .filter((f) => f !== path.basename(__filename));

test("every harness loading the compiled data.js loads bands.js first", () => {
  const checked = [];
  for (const f of files) {
    const src = fs.readFileSync(path.join(DIR, f), "utf8");
    const mods = loadedModules(src);
    const d = mods.indexOf("data.js");
    if (d === -1) continue;                       // does not execute the bundle
    checked.push(f);
    const b = mods.indexOf("bands.js");
    assert.ok(b !== -1,
      `${f} requires the compiled data.js but never loads bands.js. ` +
      "data.js throws without window.DMA_BANDS — see app/route.js SCRIPTS.");
    assert.ok(b < d,
      `${f} loads bands.js AFTER data.js; data.js reads window.DMA_BANDS at ` +
      "load time, so the order is the contract, not a preference.");
  }
  /* The measurement must not be vacuous: a regex that silently matched
     nothing would pass this test while checking no harness at all. */
  assert.ok(checked.length >= 5,
    `expected to find at least 5 harnesses loading the bundle, found ` +
    `${checked.length} (${checked.join(", ")}) — the detector has stopped ` +
    "seeing them, which passes for the wrong reason");
});

test("route.js still loads bands.js before any other prototype module", () => {
  /* The source of truth this test defers to. If the page's own order ever
     changes, the rule above is measuring the wrong thing and should fail
     here first. */
  const route = fs.readFileSync(path.join(DIR, "..", "app", "route.js"), "utf8");
  const list = route.slice(route.indexOf("const SCRIPTS = ["));
  const proto = [...list.matchAll(/["']proto\/js\/([a-z0-9-]+\.js)["']/g)]
    .map((m) => m[1]);
  assert.ok(proto.length > 1, "SCRIPTS carries no proto modules to order");
  assert.strictEqual(proto[0], "bands.js",
    `app/route.js loads ${proto[0]} first among proto modules; this suite's ` +
    "rule assumes bands.js is first. One of the two is now wrong.");
});
