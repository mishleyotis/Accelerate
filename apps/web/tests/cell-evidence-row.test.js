/* The evidence rows inside a CELL drawer, and the url that was never on them.
 *
 * Reported 2026-08-19 with a photograph of the P1C1.1.1 drawer: "Evidence
 * drawers still do not have their URLs for each evidence." Both halves of that
 * were true and neither was a data defect.
 *
 *   · The url was in the store, in the api projection and in the adapter the
 *     whole time. The EVIDENCE drawer (drawers.jsx) rendered it. The CELL
 *     drawer (pages-d3-heatmap.jsx) never did — it printed the id, the tier,
 *     the title and the excerpt and stopped.
 *   · It could not have rendered one where it stood. The row was a single
 *     <button>, and an <a href> nested inside a button is invalid markup that
 *     browsers flatten: the link would not have been a link. So the row is a
 *     wrapper with the button and the anchor as SIBLINGS.
 *
 * WHAT THIS FILE DOES NOT DO, stated rather than implied: it does not open the
 * drawer in a browser. Doing that needs a heatmap payload fixture — cells,
 * workbook scores and a cell_evidence section — which no browser suite here
 * has yet. These cases assert the adapter's half against the real projection
 * shape, and the compiled bundle's half structurally. A browser case belongs
 * beside them when that fixture exists.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS_DIR = path.join(__dirname, "..", "public", "proto", "js");
const HEATMAP = fs.readFileSync(path.join(JS_DIR, "pages-d3-heatmap.js"), "utf8");

/* The block that renders one resolved evidence row in the cell drawer. Cut by
   its two landmarks so the assertions below are about THAT row and not about
   some other part of a 2,000-line module that happens to contain an anchor. */
function evidenceRowBlock() {
  const start = HEATMAP.indexOf("linkedEv.map");
  assert.ok(start > 0, "the cell drawer no longer maps linkedEv — update this test");
  const end = HEATMAP.indexOf("Linked insight cards", start);
  assert.ok(end > start, "the linked-insight-cards block moved — update this test");
  return HEATMAP.slice(start, end);
}

test("a cell-drawer evidence row carries its source url", () => {
  const block = evidenceRowBlock();
  assert.ok(/createElement\(\s*"a"/.test(block),
    "no anchor in the cell drawer's evidence row — the source url is served "
    + "and still unreachable from the row that cites it");
  assert.ok(/href:\s*`https:\/\/\$\{e\.source\}`/.test(block),
    "the anchor does not build its href from the item's own source");
});

test("the anchor is a sibling of the button, never nested in it", () => {
  const block = evidenceRowBlock();
  const button = block.indexOf('createElement("button"');
  const anchor = block.search(/createElement\(\s*"a"/);
  assert.ok(button > 0 && anchor > 0, "row markup no longer has both elements");
  assert.ok(anchor > button,
    "the anchor is emitted before the button, so it is inside it — a link "
    + "nested in a button is flattened by every browser and does not navigate");
  // The button's own children close before the anchor opens. Babel emits the
  // wrapper as createElement("div", …, button, anchorRow), so the anchor must
  // sit outside the button's argument list: the cheapest true statement of
  // that is the excerpt block (the button's last child) appearing between them.
  const lastChild = block.indexOf("No verbatim excerpt is served for this item");
  assert.ok(lastChild > button && lastChild < anchor,
    "the button's last child is not between the button and the anchor, so the "
    + "anchor may be inside the button again");
});

test("a row with no url says so rather than rendering nothing", () => {
  const block = evidenceRowBlock();
  assert.ok(block.includes("no source url served"),
    "a row whose item carries no url renders blank space, which reads as a "
    + "missing feature rather than a missing datum");
});

test("a row with no excerpt states the absence", () => {
  const block = evidenceRowBlock();
  assert.ok(block.includes("No verbatim excerpt is served for this item"),
    "36 of this corpus's 104 evidence rows carry no excerpt. Rendering "
    + "nothing for them makes an ingest defect invisible on the page");
});

test("the adapter keeps the whole url, not just the domain", () => {
  /* `source` is the url minus its scheme, which the drawer re-adds. Stripping
     the PATH as well would point every citation at a home page: the row that
     opened this round cites https://ncuso.org/credit-union/1999/, and
     ncuso.org alone is not that document. */
  const w = require("./adapter-window");
  const items = [{
    e_id: "E-1", source_name: "NCUA — Call Report Quarterly Data",
    source_url: "https://ncuso.org/credit-union/1999/",
    source_domain: "ncuso.org", tier: "T2", claim_type: "FACT",
  }];
  const out = w.adaptEvidence({ items });
  assert.strictEqual(out[0].source, "ncuso.org/credit-union/1999/");
  assert.strictEqual(`https://${out[0].source}`, items[0].source_url);
});
