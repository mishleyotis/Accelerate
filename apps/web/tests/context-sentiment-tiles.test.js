/* C4 · a tile with no rows is a stated absence, not a missing tile.
 *
 * RC-03 / D-02, gold audit of run 7968492e (2026-10-04). The run promoted two
 * context tiles: customer with one row, employee with `rows: []`, a note, its
 * citations and the ladder it searched. `adaptContextSentiment` kept a
 * row-less tile only when it carried `state === "WORKED_ABSENT"` — a key the
 * C4 contract does not declare ({audience, rows, e_ids}) — so the employee
 * tile vanished: groups = ["customer"], absent = 0. The customer tile's own
 * `note`, which carried the complaint-record analysis, was never rendered.
 *
 * The renderer may not depend on an undeclared key (RC-03 reverse binding).
 * A tile with no rows and a note, citations or a ladder is worked-absent by
 * what it carries; the note renders for EVERY tile.
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");

const ID = "gold-audit-shape";

test("C4 adapter · the gold-audit-shaped tiles yield the customer group AND the employee tile", () => {
  const { win } = H.load();
  const out = win.adaptContextSentiment(F.CONTEXT_SENTIMENT);
  assert.ok(out, "the adapter returned null for two promoted tiles");
  const groups = Object.keys(out.groups);
  const absent = out.absent.map((a) => a.group);
  assert.deepStrictEqual(groups, ["customer"]);
  assert.deepStrictEqual(absent, ["employee"],
    `the employee tile (rows: [], no \`state\`) was dropped: groups=${JSON.stringify(groups)}, `
    + `absent=${absent.length}. A renderer that needs an undeclared key to `
    + `show a promoted tile is the RC-03 reverse-binding defect`);
  assert.strictEqual(out.absent[0].note, F.CONTEXT_SENTIMENT.context_tiles[1].note);
  assert.deepStrictEqual(out.absent[0].e_ids, F.CONTEXT_SENTIMENT.context_tiles[1].e_ids);
});

test("C4 adapter · the tile note travels for a tile WITH rows", () => {
  const { win } = H.load();
  const out = win.adaptContextSentiment(F.CONTEXT_SENTIMENT);
  assert.ok(out.notes && out.notes.customer,
    "the customer tile's note is dropped whenever the tile has rows");
  assert.strictEqual(out.notes.customer.note, F.CONTEXT_SENTIMENT.context_tiles[0].note);
});

test("C4 adapter · a declared state still works, and an empty bare tile says nothing", () => {
  const { win } = H.load();
  const out = win.adaptContextSentiment({ context_tiles: [
    { audience: "market", rows: [], state: "WORKED_ABSENT", sources_searched: ["x"] },
    { audience: "employee", rows: [] },
  ] });
  assert.deepStrictEqual(out.absent.map((a) => a.group), ["market"],
    "a tile carrying nothing at all is not a finding; one with a ladder is");
});

function grid(open, audience, section) {
  const { win } = H.load();
  H.installEntity(ID, { context: { sections: {
    context_sentiment: F.sec(section || F.CONTEXT_SENTIMENT) } } });
  const html = H.render(win.SentimentGridInteractive, {
    sentOpen: open, setSentOpen: () => {}, openEvidence: () => {},
    entity: { id: ID } }, { audience });
  return H.textOf(html);
}

test("C4 render · the employee tile is on the face and its note opens", () => {
  const face = grid(null, "internal");
  assert.match(face, /employee/i, "no employee tile on the face of the grid");
  const opened = grid("aud-employee", "internal");
  assert.ok(opened.includes("3.9 of 5 on 9 ratings"),
    "the employee tile's note did not render when opened");
  assert.ok(opened.includes("E-CC-9003"), "the employee tile's citations did not render");
});

test("C4 render · the customer tile's own note renders beside its row", () => {
  const opened = grid("aud-customer", "internal");
  assert.ok(opened.includes("count with no rate"),
    "the customer tile's note — the complaint-record analysis — rendered nowhere");
});

test("C4 render · the face never claims a search the payload does not record", () => {
  // A customer read has the ladder stripped (internal_only), so the tile
  // cannot say "searched" on its own authority.
  const cust = F.customerCopy(F.CONTEXT_SENTIMENT);
  for (const t of cust.context_tiles) delete t.sources_searched;
  const face = grid(null, "customer", cust);
  assert.ok(!/Searched, not established/i.test(face),
    "the tile asserted a search on a payload that records none");
  assert.match(face, /employee/i, "the employee tile vanished for the customer");
});
