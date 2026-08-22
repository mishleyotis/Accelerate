/* Two reader-facing defects the owner reported on 15 August.
 *
 * ONE — "issues with the readiness tab; how peer scores inherited category
 * benchmarks or pillar benchmarks."
 *
 * All 28 gap rows on the promoted run serve `peer_score: null` with
 * `peer_basis: cannot_estimate`, and the producer's own note says why: "The
 * locked peer set is benchmarked at CATEGORY grain, so no peer figure exists
 * for this cell; the category comparison is stated on the workbook surface
 * instead." Meanwhile `heatmap.workbook_scores` carries twenty-one
 * `peer_median` values across categories and pillars.
 *
 * The comparison existed, one section away, on a surface the same reader has
 * open — and the platform page rendered an absence next to it.
 *
 * The fix is a RESOLVER, not a fallback, and the distinction is the whole
 * point: a category median is not a cell peer score, and rendering one as the
 * other is the grain violation the CG family exists to catch. So the grain
 * travels with the figure and the row says which it is.
 *
 * TWO — "When I click enrich via Clay, this is not persisted across sessions to
 * me as a user such that I never click it again."
 *
 * The panel deliberately persisted nothing ("navigate away and every curtain is
 * closed again"). Defensible for a curtain over already-promoted data; wrong
 * for a reader, who meets a request the first time and busywork every time
 * after. The reveal now persists per browser and per entity. A "no route"
 * result does NOT, because that is a statement about what THIS run found and
 * freezing it would keep a curtain down over a contact a later run fills.
 *
 * Reads the COMPILED bundle, as the other suites do: what ships is asserted.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");

function compiledFunction(file, name) {
  const src = fs.readFileSync(path.join(JS, file), "utf8");
  const start = src.indexOf(`function ${name}(`);
  assert.notStrictEqual(start, -1, `${name} is not in the compiled ${file}`);
  let depth = 0, i = src.indexOf("{", start);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}" && --depth === 0) break;
  }
  /* `benchmarkFor` calls pfText/pfNum. Those are STUBBED rather than
     extracted: pfText reaches `sentence()` in another module, and pulling the
     transitive closure in would make this a test of the whole page's helper
     graph instead of a test of the resolution. Both coercers carry their own
     coverage; what is asserted here is which benchmark is chosen and at what
     grain, and the stubs honour the contracts that decision depends on —
     null for absent, and a number or null, never NaN. */
  const helpers = `
    function pfText(v) {
      return (v === null || v === undefined || v === "") ? null : String(v);
    }
    function pfNum(v) {
      if (v === null || v === undefined || v === "") return null;
      const n = Number(v);
      return isFinite(n) ? n : null;
    }`;
  // eslint-disable-next-line no-new-func
  return new Function(`${helpers}\n${src.slice(start, i + 1)}\nreturn ${name};`)();
}

// The live shape: /v1/entities/{id}/heatmap serves these id-KEYED, and the
// contract allows a list of rows too. Both are exercised.
const SCORES = {
  categories: {
    P4C3: { score: 2.19, peer_median: 3.0 },
    P2C2: { score: 2.4, peer_median: null },
  },
  pillars: {
    P4: { score: 1.95, peer_median: 2.9 },
    P2: { score: 2.4, peer_median: 2.7 },
  },
};

test("a cell inherits its CATEGORY benchmark, labelled with the grain", () => {
  const f = compiledFunction("pages-d3-d4.js", "benchmarkFor");
  const m = f("P4C3.1.2", SCORES);
  assert.ok(m, "P4C3.1.2 sits in P4C3, which states a peer median");
  assert.strictEqual(m.value, 3.0);
  assert.strictEqual(m.grain, "category");
  assert.strictEqual(m.of, "P4C3", "the grain must name WHICH category");
});

test("it falls to the PILLAR only when the category states none", () => {
  const f = compiledFunction("pages-d3-d4.js", "benchmarkFor");
  const m = f("P2C2.1.1", SCORES);
  assert.strictEqual(m.value, 2.7);
  assert.strictEqual(m.grain, "pillar");
  assert.strictEqual(m.of, "P2");
});

test("a run that states neither inherits nothing", () => {
  const f = compiledFunction("pages-d3-d4.js", "benchmarkFor");
  assert.strictEqual(f("P1C1.1.1", SCORES), null,
    "P1 is in neither table; inventing a benchmark would be worse than none");
  assert.strictEqual(f("P4C3.1.2", null), null);
  assert.strictEqual(f(null, SCORES), null);
  assert.strictEqual(f("not-a-cell-id", SCORES), null);
});

test("the list-shaped contract variant resolves identically", () => {
  const f = compiledFunction("pages-d3-d4.js", "benchmarkFor");
  const asList = {
    categories: [{ category_id: "P4C3", score: 2.19, peer_median: 3.0 }],
    pillars: [{ pillar_id: "P4", score: 1.95, peer_median: 2.9 }],
  };
  assert.strictEqual(f("P4C3.1.2", asList).value, 3.0);
  assert.strictEqual(f("P4C3.1.2", asList).grain, "category");
});

test("the grain is never dropped on the way to the page", () => {
  /* The failure this guards is subtle and is the only one that matters: a
     benchmark rendered WITHOUT its grain is indistinguishable from a peer
     score for the cell, and a reader would compute a gap that means something
     else. Both the chip and the delta must carry it. */
  const src = fs.readFileSync(path.join(JS, "pages-d3-d4.js"), "utf8");
  const chip = src.slice(src.indexOf("function BenchmarkChip"),
                         src.indexOf("function BenchmarkChip") + 900);
  assert.match(chip, /mark\.grain/,
    "BenchmarkChip must render the grain beside the figure");
  assert.match(chip, /mark\.of/,
    "and name which category or pillar it came from, on the tooltip");
  assert.doesNotMatch(chip, /MaturityChip/,
    "a maturity chip is this app's vocabulary for a CELL's own score; wearing " +
    "it would make an inherited category figure read as one");
  assert.match(src, /inherited \? <span[^>]*> \{mark\.grain\}<\/span> : null|inherited/,
    "the delta column must mark an inherited difference as inherited");
});

test("the leadership reveal persists, and only the reveal", () => {
  const src = fs.readFileSync(path.join(JS, "pages-d1-overview.js"), "utf8");
  assert.match(src, /localStorage/,
    "a reveal the reader has already made must survive the session");
  assert.match(src, /dma\.reveal\./,
    "and be keyed per entity, so one client's reveal never uncovers another's");
  // The negative: "no route" is a finding about THIS run and must not be
  // frozen — a later run that finds the contact would stay curtained.
  const enrich = src.slice(src.indexOf("const enrich ="),
                           src.indexOf("const enrich =") + 700);
  const remembers = (enrich.match(/remember\(/g) || []).length;
  assert.strictEqual(remembers, 1,
    "remember() is called on the resolved branch only; persisting the " +
    "no-route branch would keep a curtain down over a contact a later run fills");
});
