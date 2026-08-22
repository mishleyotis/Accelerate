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
for (const m of ["data.js", "live-adapter.js", "utils.js"]) {
  require(path.join(JS_DIR, m));
}
module.exports = global.window;
