/* The compiled bundle's window globals, loaded the way the browser loads
   them. Extracted so a test can assert a pure helper without driving a page —
   `scaleFraction` is the function behind every sentiment bar and the cheapest
   place to catch a notation it stops understanding. */
const path = require("node:path");

const JS_DIR = process.env.PROTO_JS_DIR
  || path.join(__dirname, "..", "public", "proto", "js");
const VENDOR = path.join(__dirname, "..", "public", "vendor");

for (const k of Object.keys(require.cache)) delete require.cache[k];
global.window = global.window || {};
global.self = global.window;
global.React = require(path.join(VENDOR, "react.production.min.js"));
/* bands.js FIRST, for the same reason app/route.js loads it first among the
   prototype's own modules: data.js throws without `window.DMA_BANDS` rather
   than fall back to a second colour mapping, which is the invariant-7 defect
   (AUD-0048) that guard exists to have stopped.

   This harness listed the other three and not this one, so every suite
   reaching the compiled bundle through it died on that guard at require
   time — 66 of 231 web tests on 2026-08-29, reported as 66 failures rather
   than as the one missing module they were. The guard was right and loud;
   the harness simply was not loading the browser's script order. Keep this
   list in step with SCRIPTS in app/route.js. */
for (const m of ["bands.js", "data.js", "live-adapter.js", "utils.js"]) {
  require(path.join(JS_DIR, m));
}
module.exports = global.window;
