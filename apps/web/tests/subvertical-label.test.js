/* The sub-vertical a reader sees, and the assign that used to break it.
 *
 * Reported 2026-08-19: "I still see CU on the clients page as well as at the
 * header of the Logix Page instead of Credit Union."
 *
 * The api built its label table by normalising the stored string and falling
 * back to that string as its own label, so a client whose sub_vertical is the
 * bare `CU` arrived as `{CU: "CU"}` — and the Object.assign in data.js, which
 * exists so the server can name a sub-vertical this file has never heard of,
 * overwrote the correct entry with the code.
 *
 * The api resolves properly now. This suite pins the browser's half, because
 * a client running against an older api revision must still not put a code on
 * screen: a label that is the code back again is not a label.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "public", "proto", "js", "data.js"), "utf8");

/* The table and the merge, lifted out of the bundle and evaluated with a
   chosen boot payload — the merge is the half that had the defect, so it is
   the half under test rather than a re-implementation of it. */
function labelsFor(bootMap) {
  const table = SRC.match(/const SUBVERTICAL_LABEL = \{[\s\S]*?\n  \}/);
  const merge = SRC.match(
    /for \(const \[code, label\] of Object\.entries[\s\S]*?\n  \}/);
  assert.ok(table, "SUBVERTICAL_LABEL is gone from the bundle");
  assert.ok(merge, "the server-label merge is gone — a stale api can win again");
  // eslint-disable-next-line no-new-func
  return new Function("LIVE",
    `${table[0]};${merge[0]}; return SUBVERTICAL_LABEL;`)({ subvertical_labels: bootMap });
}

const CODES = ["RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB"];

test("every canonical code the api can serve has a label", () => {
  const t = labelsFor({});
  const missing = CODES.filter((c) => !t[c] || !String(t[c]).trim());
  assert.deepStrictEqual(missing, [],
    `no label for ${missing} — the api serves these codes, so a miss renders `
    + "blank where the sub-vertical belongs");
});

test("an unresolved sub-vertical says so rather than rendering nothing", () => {
  assert.ok(String(labelsFor({}).UNKNOWN || "").trim(),
    "the api sends UNKNOWN when a stored value resolves to no code; a blank "
    + "there reads as a missing feature rather than an unresolved datum");
});

test("no label is its own code", () => {
  const t = labelsFor({});
  const selfish = Object.entries(t)
    .filter(([code, label]) => String(label).trim().toUpperCase() === code);
  assert.deepStrictEqual(selfish, [],
    "a label equal to its code is what the reader saw on the header");
});

test("a server label that is just the code back again is rejected", () => {
  /* THE EXACT PAYLOAD THAT SHIPPED: `{"CU": "CU", "SV2": "Credit Unions"}`. */
  const t = labelsFor({ CU: "CU", SV2: "Credit Unions" });
  assert.strictEqual(t.CU, "Credit Unions",
    "an older api revision can still overwrite a correct label with a code");
});

test("a real server label still wins, because the server knows the vocabulary", () => {
  const t = labelsFor({ CU: "Credit unions (Canada)" });
  assert.strictEqual(t.CU, "Credit unions (Canada)");
});

test("a blank server label does not blank the built-in one", () => {
  assert.strictEqual(labelsFor({ CU: "   " }).CU, "Credit Unions");
});

test("the prototype's own key space still renders", () => {
  /* Fixture data predates the canonical codes; a fixture that stopped
     rendering would send the next author to fix the wrong thing. */
  const t = labelsFor({});
  assert.strictEqual(t.REGIONAL_BANK, "Regional Banks");
  assert.strictEqual(t.CREDIT_UNION, "Credit Unions");
});
