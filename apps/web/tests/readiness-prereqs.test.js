/* The readiness card said there were no gates over a payload carrying nine.
 *
 * `areaPrereqs` skipped anything that was not an object —
 * `if (!q || typeof q !== "object") continue;` — and every prerequisite this
 * run promoted is a SENTENCE. The contract states `prerequisites[]` and no
 * item shape, so a list of strings is legal, and the card rendered
 *
 *     No recommendation in this run promoted a prerequisite, so no readiness
 *     gate applies.
 *
 * above five recommendations with nine prerequisites between them. Reported
 * three rounds running as "the readiness card is empty"; the gates were there
 * the whole time and nothing read them.
 *
 * Same shape as two defects already fixed in this codebase — `scale: 5` that
 * only parsed as "0..5", and `capped_subcap_ids` as records where the reader
 * wanted ids. A payload field that is present, legal and unread is invisible
 * to every contract gate, because the contract is satisfied.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");
const VENDOR = path.join(__dirname, "..", "public", "vendor");

function load() {
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  global.window = { DMA_LIVE: { entity: { display_id: "x" }, sections: {} } };
  global.self = global.window;
  global.React = require(path.join(VENDOR, "react.production.min.js"));
  global.ReactDOM = { createRoot: () => ({ render() {} }) };
  // The real load order from app/route.js, up to the module under test.
  // Anything later is not needed to reach two pure helpers, and loading it
  // would only add ways for this test to fail for reasons of its own.
  // bands.js FIRST, as app/route.js SCRIPTS loads it: data.js throws without window.DMA_BANDS rather than fall back to a second colour mapping (invariant 7, AUD-0048).
  for (const m of ["bands.js", "data.js", "live-adapter.js", "utils.js",
                   "cards-data-driven.js", "drawers.js", "pages-d3-d4.js"]) {
    require(path.join(JS, m));
  }
  return global.window;
}

// The five recommendations this run actually promoted, verbatim.
const PROMOTED = [
  { id: "REC-2", prerequisites: [
    "An inventory of models actually in production, which public evidence cannot establish",
    "P4C2.1.1 >= 2.5, which the run serves at 3.0"] },
  { id: "REC-3", prerequisites: [
    "Internal disclosure of existing continuity and recovery practice, without which the scope cannot be right-sized"] },
  { id: "REC-1", prerequisites: [
    "REC-2 complete, so the first model to touch a member is registered",
    "Confirmation of the warehouse's true production scope, currently inferred from role specifications"] },
  { id: "REC-4", prerequisites: [
    "REC-1 for anything personalised; the assistance layer itself needs only the existing app authentication"] },
  { id: "REC-5", prerequisites: [
    "REC-1 complete — every journey here reads from the member profile"] },
];

test("a prerequisite written as a sentence still produces a gate", () => {
  const w = load();
  const rows = w.areaPrereqs(PROMOTED);
  assert.ok(rows.length >= 7,
    `the promoted run carries nine prerequisites and produced ${rows.length} `
    + `gate rows. Zero is the reported defect: the card then says no `
    + `recommendation promoted a prerequisite.`);
});

test("a sentence stating a cell and a minimum becomes a cell gate", () => {
  const w = load();
  const q = w.prereqOf("P4C2.1.1 >= 2.5, which the run serves at 3.0");
  assert.strictEqual(q.cell, "P4C2.1.1");
  assert.strictEqual(q.minimum, 2.5);
  assert.strictEqual(q.current, 3,
    "the current reading is stated after the threshold and must not be "
    + "transposed with it");
});

test("a sentence stating no cell becomes a text condition, never a cell gate", () => {
  const w = load();
  const q = w.prereqOf("REC-2 complete, so the first model to touch a member is registered");
  assert.strictEqual(q.cell, undefined);
  assert.ok(q.condition.startsWith("REC-2 complete"));
});

test("a cell named with no threshold word is not read as a minimum", () => {
  /* "P4C2.1.1 was 2.5 last year" states no requirement. Reading the number
     as a minimum would invent a gate the run never set. */
  const w = load();
  const q = w.prereqOf("P4C2.1.1 was 2.5 at the last assessment");
  assert.strictEqual(q.cell, undefined, "a bare mention is not a threshold");
  assert.ok(q.condition);
});

test("the object shape keeps working exactly as before", () => {
  const w = load();
  const q = w.prereqOf({ cell: "P1C1.1", minimum: 2, verdict: "MET" });
  assert.deepStrictEqual(q, { cell: "P1C1.1", minimum: 2, verdict: "MET" });
});

test("both shapes in one run render as one kind of row", () => {
  const w = load();
  const rows = w.areaPrereqs([
    { id: "R1", prerequisites: ["P4C2.1.1 >= 2.5, which the run serves at 3.0"] },
    { id: "R2", prerequisites: [{ cell: "P4C2.1.1", minimum: 3.0 }] },
  ]);
  const cells = rows.filter((r) => r.kind === "cell");
  assert.strictEqual(cells.length, 1,
    "one cell, two thresholds, one row — a reader who sees the same "
    + "identifier twice concludes the card is broken");
  assert.deepStrictEqual(cells[0].thresholds.map((t) => t.min).sort(), [2.5, 3]);
});

test("an empty or malformed prerequisite is dropped, not rendered blank", () => {
  const w = load();
  assert.strictEqual(w.prereqOf(""), null);
  assert.strictEqual(w.prereqOf(null), null);
  assert.strictEqual(w.areaPrereqs([{ id: "R", prerequisites: ["", null] }]).length, 0);
});
