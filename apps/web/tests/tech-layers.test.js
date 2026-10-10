/* T1 · a layer whose expected count is not stated never renders "n of n".
 *
 * RC-11 / D-16, gold audit of run 7968492e (2026-10-04). Every layer
 * promoted `expected: null`. The adapter then fell back to `expected = the
 * rows on screen`, so the infrastructure layer rendered "5 of 5 detected" and
 * the primary-gap data layer "10 of 11" — the circular rollup this module's
 * own comment calls a defect. A count of the register cannot be the register's
 * denominator.
 *
 * What the denominator SHOULD count — product slots (the producer) or cells
 * (the server) — is open adjudication T-03 / DNR-6 and is not settled here.
 * This pins only that no denominator is invented when none is stated.
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");

const ID = "gold-audit-shape";

function page() {
  const { win } = H.load();
  H.installEntity(ID, { techstack: { sections: { techstack: F.sec(F.TECHSTACK) } } });
  const html = H.render(win.ClientTechStack,
    { entity: { id: ID, name: "Example Group" }, run: { id: "run" } },
    { audience: "internal" });
  return H.textOf(html);
}

test("D-16 adapter · expected is null when the run states none", () => {
  const { win } = H.load();
  const rows = win.techLayersOf(F.TECHSTACK);
  for (const r of rows) {
    assert.strictEqual(r.expected, null,
      `${r.layer}: expected=${r.expected} was derived from the register's own `
      + `row count — circular`);
  }
});

test("D-16 render · no layer renders 'n of n' over an unstated denominator", () => {
  const text = page();
  const circular = [...text.matchAll(/(\d+) of (\d+) detected/g)];
  assert.deepStrictEqual(circular.map((m) => m[0]), [],
    `a layer rendered a ratio whose denominator nobody stated: ${circular.map((m) => m[0]).join(", ")}`);
  assert.match(text, /expected not stated/,
    "the layer cards do not say the expected count is unstated");
});

test("D-16 render · a stated expected still renders as a ratio", () => {
  const { win } = H.load();
  const ts = JSON.parse(JSON.stringify(F.TECHSTACK));
  ts.layers[0].expected = 17;
  H.installEntity(ID, { techstack: { sections: { techstack: F.sec(ts) } } });
  const text = H.textOf(H.render(win.ClientTechStack,
    { entity: { id: ID, name: "Example Group" }, run: { id: "run" } },
    { audience: "internal" }));
  assert.match(text, /of 17 detected/, "a stated denominator stopped rendering");
});
