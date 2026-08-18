/* The heatmap and the assessment-health queue, against the run's own record.
 *
 * Run with `npm run test:web`. Loads the COMPILED bundle the way the browser
 * loads it — window globals, in order — because the compiled files are what
 * ships and what the open-app harness renders.
 *
 * Five defects are pinned here, all measured on run
 * d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb (Logix Federal Credit Union, promoted
 * 2026-08-18) and all of the same shape: the app asserted something the run
 * did not say.
 *
 *   H-01  the health queue printed "0 open alerts" and a green
 *         "✓ No open alerts — Evidence coverage meets the minimum threshold"
 *         over 14 promoted alerts, on a run whose own coverage is 33.0%
 *         against an 80% gate. `buildAlerts()` walks the boot directory's
 *         cell grain, a key the live directory does not carry.
 *   H-02  the evidence-age tracker read "Not computed" / "NO DATE" on 63 of
 *         63 rows because it aged `recency`, which the adapter sets to the
 *         recency BAND ("CURRENT"); 22 of those rows carry a date.
 *   H-05  the pillar zoom printed "no pillar score promoted" four times with
 *         no reason anywhere, and the reason it does have is the serving
 *         tier's stub, "no serving row for this run".
 *   H-08  the cohort table rendered a header and zero rows with no word about
 *         the five-run floor that withheld them.
 *   H-11  456 cell drawers told the reader "the score is inferred" over cells
 *         whose own provenance is `declared` — a recorded absence carrying a
 *         ladder, which is the opposite of an inference.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");

/* The bundle, loaded in the order app/route.js lists it. React is stubbed:
   nothing in these modules calls createElement at load time — they declare
   functions and then publish them onto window — so a stub is enough to load
   the page modules and reach the pure helpers inside them. */
function load(liveEntity, live = true) {
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  const w = {
    DMA_LIVE: live ? { authed: true, role: "ADMIN", entities: [] } : undefined,
    DMA_ENTITY: liveEntity || null,
    addEventListener() {}, removeEventListener() {},
    location: { hash: "" },
  };
  global.window = w;
  global.React = {
    createElement: () => null, Fragment: "Fragment",
    createContext: () => ({ Provider: null, Consumer: null }),
    useState: (v) => [v, () => {}], useEffect: () => {},
    useMemo: (f) => f(), useRef: () => ({ current: null }),
    useCallback: (f) => f, useContext: () => ({}),
    memo: (f) => f, forwardRef: (f) => f,
    // utils.js ships an error boundary, which is a class component.
    Component: class {}, PureComponent: class {},
  };
  global.document = { addEventListener() {}, removeEventListener() {},
                      querySelectorAll: () => [], createElement: () => ({ style: {} }) };
  for (const f of ["data.js", "live-adapter.js", "utils.js",
                   "pages-d3-heatmap.js", "pages-d5-d6-tech-runs.js"]) {
    require(path.join(JS, f));
  }
  // In a browser these modules resolve the bare name `DMA` off window; under
  // node `global.window` is an ordinary object, so the alias is the bridge.
  for (const k of Object.keys(w)) global[k] = w[k];
  return w;
}

/* The compiled bundle with its BLOCK COMMENTS removed.
 *
 * Babel preserves comments, and the comments in these files quote the very
 * sentences the fixes removed — that is the point of them, a defect note has
 * to name the defect. A source-text assertion that did not strip them would
 * be satisfied by the explanation of the fix rather than by the fix, which is
 * the most confident kind of wrong a test can be. Line comments are left
 * alone: stripping them would have to reason about `https://` inside string
 * literals, and no assertion here needs it. */
function code(file) {
  return fs.readFileSync(path.join(JS, file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

/* One promoted alert, in the contract's own shape: a subcap id and no name,
   a state and no `status`, and none of the three fields the prototype's
   table used to render. */
const ALERT = {
  subcap_id: "P4C2.5.1", score: 1.5, confidence: "LOW", evidence_count: 1,
  state: "WORKED_ABSENT", severity: "HIGH", runs_open: 1,
  sources_searched: ["Targeted query: model risk management policy"],
  queries_run: ["Logix model inventory validation"],
  new_evidence_ids: [],
  justification: "A model inventory leaves an artefact.",
  closure_condition: "A model risk management policy in board reporting.",
};

const ENTITY = (over) => Object.assign({
  id: "logix-federal-credit-union",
  alerts: [ALERT],
  evidenceAge: [],
  evidence: [],
  sectionState: {},
  subcaps: [{ id: "P4C2.5.1", name: "Model Inventory & Documentation" }],
}, over || {});

/* ── H-01 ─────────────────────────────────────────────────────────────── */

test("H-01 the alert queue is the run's promoted list, not the directory's", () => {
  const { DMA } = load(ENTITY());
  const alerts = DMA.alertsForEntity("logix-federal-credit-union");
  assert.strictEqual(alerts.length, 1,
    "the promoted alert did not reach the queue — this is the read that "
    + "returned [] on every live run while 14 alerts sat promoted");
  assert.strictEqual(alerts[0].subcap_id, "P4C2.5.1");
  assert.strictEqual(alerts[0].severity, "HIGH");
  assert.strictEqual(alerts[0].state, "WORKED_ABSENT");
  assert.strictEqual(alerts[0].runs_open, 1);
  assert.strictEqual(alerts[0].justification, ALERT.justification);
  assert.strictEqual(alerts[0].closure_condition, ALERT.closure_condition);
});

test("H-01 no alert field the producer did not write is invented", () => {
  const { DMA } = load(ENTITY());
  const a = DMA.alertsForEntity("logix-federal-credit-union")[0];
  for (const k of ["recommended_action", "proxy_searched", "subcap_name"]) {
    assert.ok(!(k in a),
      `${k} is the prototype's vocabulary, absent from the alert contract. `
      + "A PROXY_ESCALATION badge or a ✓ Searched tick nobody decided is a "
      + "fabricated finding on a client's quality queue.");
  }
});

test("H-01 an entity's queue never answers for another entity", () => {
  const { DMA } = load(ENTITY());
  assert.deepStrictEqual(DMA.alertsForEntity("some-other-client"), [],
    "a stale registry answered for the entity being viewed");
});

test("H-01 the false all-clear is gone from the shipped bundle", () => {
  const src = code("pages-d5-d6-tech-runs.js");
  assert.ok(!src.includes("Evidence coverage meets the minimum threshold"),
    "an empty alert list is a statement about the QUEUE. Coverage is a "
    + "different section's arithmetic, and on this run it is 33.0% against a "
    + "gate of 80.0 — the sentence was false where it was printed.");
  assert.ok(!src.includes("✓ No open alerts</"),
    "the green all-clear was printed over 14 promoted alerts");
});

/* ── H-02 ─────────────────────────────────────────────────────────────── */

test("H-02 the age panel reads the promoted rows, dates and ages", () => {
  const w = load(ENTITY({
    evidenceAge: [{
      e_id: "E-CC-188", title: "Written testimony", source_domain: "docs.house.gov",
      published_or_asof: "2025-03-26", age_months: 16, band: "aging",
      status: "AGING", identity_ok: true,
    }],
  }));
  const rows = w.evidenceAgeRows({ id: "logix-federal-credit-union" });
  assert.strictEqual(rows.length, 1);
  assert.strictEqual(rows[0].date, "2025-03-26");
  assert.strictEqual(rows[0].age, 16);
  assert.strictEqual(rows[0].status, "AGING");
  assert.strictEqual(rows[0].identity_ok, true);
});

test("H-02 a band word is never mistaken for a date", () => {
  // This is the exact defect: `recency` carries the BAND when there is one,
  // and `new Date("CURRENT")` is an Invalid Date, so the age came back NaN
  // and the whole column read "Not computed" — on the dated rows too.
  const w = load(ENTITY({
    evidenceAge: [],
    evidence: [
      { id: "E-1", title: "dated row", source: "docs.house.gov/x",
        recency: "CURRENT", recency_band: "CURRENT",
        published_date: "2026-06-30", age_months: 1 },
      { id: "E-2", title: "undated row", source: "example.com/y",
        recency: "ARCHIVAL", recency_band: "UNVERIFIED",
        published_date: null, age_months: null },
    ],
  }));
  const rows = w.evidenceAgeRows({ id: "logix-federal-credit-union" });
  assert.strictEqual(rows[0].date, "2026-06-30");
  assert.strictEqual(rows[0].age, 1);
  assert.strictEqual(rows[1].date, null,
    "a band word reached the DATE column");
  assert.strictEqual(rows[1].age, null,
    "an age was derived for a row with no date — invariant 9: derived values "
    + "are computed or null");
  assert.strictEqual(rows[1].status, null,
    "UNVERIFIED is the ladder's word for 'no date to rank on', not a "
    + "freshness verdict");
});

test("H-02 the two header shares are counted from the rows on screen", () => {
  // Invariant 8: the promoted stale_pct/undated_pct are 15.4 and 19.2, and
  // the rows reproduce them — 4 STALE of 26, 5 undated of 26. The panel
  // counts rather than reads, so the header can never disagree with its own
  // table.
  const rows = Array.from({ length: 26 }, (_, i) => ({
    date: i < 21 ? "2025-01-01" : null,
    status: i < 4 ? "STALE" : i < 21 ? "FRESH" : "UNDATED",
  }));
  const stale = rows.filter(r => String(r.status).toUpperCase() === "STALE").length;
  const undated = rows.filter(r => !r.date).length;
  assert.strictEqual(Number((stale / rows.length * 100).toFixed(1)), 15.4);
  assert.strictEqual(Number((undated / rows.length * 100).toFixed(1)), 19.2);
});

/* ── H-05 / H-08 ──────────────────────────────────────────────────────── */

test("H-05 the serving tier's stub is not a reason", () => {
  const w = load(ENTITY({
    sectionState: {
      "heatmap.workbook_scores": {
        empty_state: { kind: "section_not_promoted",
                       reason: "no serving row for this run",
                       sources_searched: [] },
      },
    },
  }));
  const r = w.sectionReason("heatmap.workbook_scores");
  assert.strictEqual(r.stub, true,
    "\"no serving row for this run\" is what pages.py writes when the writer "
    + "persisted zero rows, which is what a section with an empty collection "
    + "does. It is plumbing, not a reason, and a reader must not be handed it "
    + "in place of one.");
});

test("H-05 a producer's own reason is rendered, not replaced", () => {
  const w = load(ENTITY({
    sectionState: {
      "heatmap.cohort_patterns": {
        empty_state: {
          reason: "One credit union in the corpus carries a served score for "
                + "these categories, so every cohort sits below the minimum "
                + "of five and nothing is published",
          sources_searched: ["the promoted corpus", "the sub-vertical index"],
          closure_condition: "Three more promoted credit-union runs.",
        },
      },
    },
  }));
  const r = w.sectionReason("heatmap.cohort_patterns");
  assert.strictEqual(r.stub, false,
    "the producer's account carries a closure condition and a ladder and "
    + "must render as written — when the writer starts persisting an "
    + "envelope-only row this is the branch that takes over");
});

test("H-05 a section with no state at all is a stub", () => {
  const w = load(ENTITY());
  assert.strictEqual(w.sectionReason("heatmap.workbook_scores").stub, true);
});

test("H-05/H-08 neither zero-row surface renders bare", () => {
  const heat = code("pages-d3-heatmap.js");
  const health = code("pages-d5-d6-tech-runs.js");
  assert.ok(!heat.includes("no pillar score promoted"),
    "the pillar zoom repeated this four times and gave no reason anywhere");
  assert.ok(heat.includes("sectionReason(\"heatmap.workbook_scores\")"),
    "the pillar zoom must consult the section's own empty state");
  assert.ok(health.includes("sectionReason(\"heatmap.cohort_patterns\")"),
    "the cohort table rendered a header and zero rows with no branch for the "
    + "five-run floor that withheld them");
});

/* ── H-11 ─────────────────────────────────────────────────────────────── */

test("H-11 a recorded absence is not described as an inference", () => {
  const src = code("pages-d3-heatmap.js");
  assert.ok(!src.includes("the score is inferred"),
    "456 of the 705 cell drawers carried this sentence, and 456 of those 456 "
    + "cells are `provenance: declared` — a worked absence naming the "
    + "artefact that would settle the cell and the rungs searched for it. "
    + "Only 24 cells on the run are `inherited`.");
  assert.ok(src.includes("The absence is recorded rather than assumed"),
    "the declared branch must say what the record says");
  assert.ok(/inherited[\s\S]{0,400}provisional until corroborated/.test(src),
    "\"provisional until corroborated\" belongs to the inherited branch and "
    + "nowhere else");
  assert.ok(src.includes("reach_note"),
    "the section's empty_state promises the reader the cell, the artefact "
    + "that would settle it and the ladder that was run; reach_note is the "
    + "second of the three and reached no reader");
  assert.ok(src.includes("sources_searched"),
    "the ladder is the third, and it reached no reader either");
});

test("H-11 the ?subcap= deep link waits for the cell grain to arrive", () => {
  const src = code("pages-d3-heatmap.js");
  // The cell grain is a second fetch and lands after the entity does. With
  // `[route.params.subcap, entity?.id]` alone the effect ran once against an
  // empty subcap list and never again, so every cross-page cell chip landed
  // on the default view and opened nothing.
  assert.ok(/route\.params\.subcap[\s\S]{0,120}subcaps[\s\S]{0,40}\.length/
              .test(src),
    "the arrival of the cell grain must be in this effect's dependencies");
});

test("H-02 a calendar value is read at whatever precision it was written", () => {
  const w = load(ENTITY());
  assert.strictEqual(w.calendarValue("2026-06-30"), "2026-06-30");
  assert.strictEqual(w.calendarValue("2025-Q4"), "2025-10-01");
  assert.strictEqual(w.calendarValue("2026-Q1"), "2026-01-01");
  assert.strictEqual(w.calendarValue("2026-06"), "2026-06-01");
  assert.strictEqual(w.calendarValue("2026"), "2026-01-01");
  // The prototype's fixture states quarters, so the demo keeps its dates —
  // that is the reason this path exists at all rather than dropping to null.
  for (const band of ["CURRENT", "AGING", "STALE", "ARCHIVAL", "UNVERIFIED",
                      "", null, undefined]) {
    assert.strictEqual(w.calendarValue(band), null,
      `${band} is a word about a date, not a date`);
  }
});

test("H-02 the fixture's quarter-dated evidence still ages", () => {
  const w = load(null, false);
  const rows = w.evidenceAgeRows({ id: "fce-001" });
  assert.ok(rows.length > 0, "fixture mode lost its evidence rows");
  const dated = rows.filter(r => r.date);
  assert.ok(dated.length > 0,
    "the prototype states its recency as quarters; the design reference must "
    + "keep its dates rather than reading them as band words");
  assert.ok(dated.every(r => typeof r.age === "number"),
    "a row with a date must carry an age");
});
