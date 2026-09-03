/* A badge never paints over its neighbour, and never loses its own text.
 *
 * HISTORY, because this file has changed its mind once and the reason matters.
 *
 * 2026-08-22 — two defects, two pages, one cause. `.b` was `white-space:
 * nowrap` with the flex default `flex-shrink: 1`. A badge is almost always a
 * flex item, so under width pressure its BOX shrank while its text did not:
 * the label spilled out and painted over whatever sat beside it.
 *
 *     focus-area drilldown   "SOURCEAI section (after the ETF/SMA…"
 *     acquisition card       a kind chip 235px past the card edge
 *
 * The fix then was `flex-shrink: 0` — keep the box, let it overflow the row
 * where a reader and a test can both see it. This file asserted that, and
 * said in as many words that if `.b` ever stopped being nowrap the test
 * "should be reconsidered rather than kept passing by accident".
 *
 * 2026-09-02 — reconsidered, because the promoted Golden 1 platform and
 * context pages billed for it. Readiness chips rendered
 *
 *     "Governed member domain owed in the cat…"
 *     "Licence and user-seat audit decides a…"
 *
 * clipped mid-word at the card edge. `nowrap` + `flex-shrink: 0` is a box
 * that can neither shrink, wrap, nor move to its own line, so it leaves the
 * card and the card's own overflow cuts it. A truncated status label is not a
 * shorter label — it is a claim the reader cannot finish.
 *
 * Capping the CONTENT was tried first: a 60-character budget on the
 * producer's `basis`. Wrong altitude twice. The pill holds ~38 characters at
 * this font, so 60 still clipped; and a content rule protects one field on
 * one page while ~40 other `.b` sites stay exposed.
 *
 * So the badge owns its own text now: `white-space: normal` +
 * `overflow-wrap: anywhere` + `max-width: 100%`. Shrinking is safe again
 * PRECISELY BECAUSE the text reflows instead of spilling — the 2026-08-22
 * defect was shrink WITH nowrap, and that combination is what these tests
 * now forbid. A short badge is unaffected: it fits, so it does not wrap.
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

test("the badge class exists — the premise of this test", () => {
  assert.ok(ruleFor(".b"), ".b is not in app.css; this test measures nothing");
});

test("a badge wraps its own text rather than clipping it", () => {
  const rule = ruleFor(".b");
  assert.match(rule, /white-space:\s*normal/,
    "a badge whose label cannot fit its line must wrap INSIDE its box. With "
    + "nowrap it leaves the card and the card's overflow cuts it, which is "
    + "the 2026-09-02 defect: 'Governed member domain owed in the cat…'");
  assert.doesNotMatch(rule, /white-space:\s*nowrap/,
    "a leftover nowrap declaration in the same rule is a cascade accident "
    + "waiting to be reordered into a regression");
});

test("a badge cannot be wider than the box it sits in", () => {
  const rule = ruleFor(".b");
  assert.match(rule, /max-width:\s*100%/,
    "without this a single unbroken token still escapes its container");
  assert.match(rule, /overflow-wrap:\s*anywhere/,
    "a label with no space to break at (a long id, a URL) needs an explicit "
    + "break opportunity or max-width cannot hold it");
});

test("the dangerous combination is nowrap WITH shrinking, and it is absent", () => {
  /* This is the 2026-08-22 defect stated exactly. Either property alone is
     fine: nowrap + no-shrink overflows visibly (the old fix), and wrap +
     shrink reflows (the current one). Only nowrap + shrink spills text over
     a neighbour, which is the one failure a reader cannot see is a bug. */
  const rule = ruleFor(".b");
  const nowrap = /white-space:\s*nowrap/.test(rule);
  const shrinks = !/flex-shrink:\s*0/.test(rule);
  assert.ok(!(nowrap && shrinks),
    "`.b` is nowrap AND shrinkable — its box will shrink while its text does "
    + "not, and the label will paint over its neighbour");
});

test("no badge variant re-introduces nowrap", () => {
  /* `.b-purple`, `.b-below` and friends set colour. One of them setting
     `white-space: nowrap` would restore clipping for that variant only — the
     hardest version to find, because every other badge would look right. */
  const offenders = [];
  const re = /(^|[},])\s*(\.b-[\w-]+)\s*\{([^}]*)\}/gm;
  let m;
  while ((m = re.exec(CSS)) !== null) {
    if (/white-space:\s*nowrap/.test(m[3])) offenders.push(m[2]);
  }
  assert.deepStrictEqual(offenders, [],
    `badge variants re-enable nowrap: ${offenders.join(", ")}`);
});

test("the readiness row wraps, so a sentence-shaped chip takes its own line", () => {
  /* The call site of the reported defect. The class fix keeps the text
     inside the chip; this keeps the CHIP inside the row rather than making
     the row's other columns absorb the pressure. */
  const src = fs.readFileSync(
    path.join(__dirname, "..", "proto", "pages-live-client.jsx"), "utf8");
  assert.match(src,
    /Prerequisites[\s\S]{0,900}?className="row"[\s\S]{0,160}?flexWrap:\s*"wrap"/,
    "the prerequisites row lost its flexWrap; a basis chip that cannot fit "
    + "beside the condition text will run past the card edge again");
});
