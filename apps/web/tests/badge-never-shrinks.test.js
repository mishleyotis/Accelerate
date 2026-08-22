/* A badge does not shrink, anywhere on any page.
 *
 * Two of the defects reported on 2026-08-22 came from different pages and had
 * one cause: `.b` is `white-space: nowrap` and, until this was fixed, carried
 * the flex default `flex-shrink: 1`. A badge is almost always a flex item, so
 * under width pressure its BOX shrank while its text did not — the label spilled
 * out of its own box and painted over its neighbour.
 *
 *     focus-area drilldown   "SOURCEAI section (after the ETF/SMA…"
 *     acquisition card       a kind chip 235px past the card edge
 *
 * Both were first fixed at the call site. That was the wrong altitude: the
 * property belongs to the badge, and every `.b` in the stylesheet was one
 * narrow viewport away from the same defect. This asserts the class-level
 * fix, which is what makes the two call-site fixes redundant rather than
 * load-bearing.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const CSS = fs.readFileSync(
  path.join(__dirname, "..", "public", "proto", "app.css"), "utf8");

function ruleFor(selector) {
  // The block for a selector, matched at a rule boundary so `.b` does not
  // match `.b-teal` and report the wrong declarations.
  const re = new RegExp(
    `(^|[},])\\s*${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`, "m");
  const m = re.exec(CSS);
  return m ? m[2] : null;
}

test("the badge class exists and is nowrap — the premise of this test", () => {
  const rule = ruleFor(".b");
  assert.ok(rule, ".b is not in app.css; this test is measuring nothing");
  assert.match(rule, /white-space:\s*nowrap/,
    "if .b ever stops being nowrap the shrink hazard is gone and this test "
    + "should be reconsidered rather than kept passing by accident");
});

test("the badge class refuses to shrink", () => {
  const rule = ruleFor(".b");
  assert.match(rule, /flex-shrink:\s*0/,
    "`.b` is nowrap, so with the flex default of `flex-shrink: 1` its box "
    + "shrinks while its text does not, and the label paints over whatever is "
    + "beside it. This is the class-level fix for the two overlaps reported "
    + "on 2026-08-22.");
});

test("no badge variant quietly re-enables shrinking", () => {
  /* `.b-purple`, `.b-below` and friends set colour. One of them setting
     `flex-shrink` back to a positive value would restore the defect for that
     variant only — the hardest version to find, because every other badge on
     the page would look right. */
  const offenders = [];
  const re = /(^|[},])\s*(\.b-[\w-]+)\s*\{([^}]*)\}/gm;
  let m;
  while ((m = re.exec(CSS)) !== null) {
    if (/flex-shrink:\s*(?!0)/.test(m[3])) offenders.push(m[2]);
  }
  assert.deepStrictEqual(offenders, [],
    `badge variants re-enable shrinking: ${offenders.join(", ")}`);
});

test("the two call sites that were patched first are still correct", () => {
  /* Belt and braces, deliberately. The class fix makes these redundant; a
     future edit removing them should stay harmless, and a future edit
     removing the CLASS fix should not silently rely on them. */
  const proto = path.join(__dirname, "..", "proto");
  const heatmap = fs.readFileSync(path.join(proto, "pages-d3-heatmap.jsx"), "utf8");
  assert.match(heatmap, /className="b b-purple"[\s\S]{0,80}flexShrink: 0/,
    "the SOURCE chip lost its explicit flexShrink");
});
