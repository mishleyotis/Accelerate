/* The adapter, and the one property that makes it safe.
 *
 * Run with `npm run test:web` (node's built-in test runner, no framework).
 * The compiled bundle is loaded exactly as the browser loads it — window
 * globals, in order — because that IS the contract: data.js reads
 * window.DMA_ENTITY, and a test that imported modules some other way would
 * not be testing what ships.
 *
 * The property under test, above all others: in LIVE mode an entity-scoped
 * accessor returns null or [] and NEVER the fixture. The fixture describes a
 * fictional bank — three cores, an nCino migration, named executive hires —
 * and one fallback to it renders fabrication under a real client's name. That
 * single risk is why a whole second renderer was written instead of feeding
 * the prototype; this test is what makes feeding the prototype safe.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");

function load(live) {
  // Fresh module registry per case: data.js captures LIVE at load time, which
  // is the behaviour being relied on.
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  global.window = live ? { DMA_LIVE: live } : {};
  require(path.join(JS, "data.js"));
  require(path.join(JS, "live-adapter.js"));
  return global.window;
}

const LIVE = { authed: true, role: "ADMIN",
               entities: [{ id: "baxter", slug: "baxter", name: "Baxter CU", runs: [] }] };

const ENTITY_ACCESSORS = ["financialsFor", "sentimentFor", "coverageFor",
                          "uncertaintyFor", "evidenceSummaryFor", "whyNowFor"];
const LISTS = ["EVIDENCE", "INSIGHT_CARDS", "RECOMMENDATIONS", "TECH_STACK",
               "LEADERSHIP", "THOUGHT_LEADERSHIP", "FOCUS_AREAS", "ROADMAP",
               "ISSUES", "TIMELINE_EVENTS"];

test("fixture mode still answers, so the prototype runs standalone", () => {
  const { DMA } = load(null);
  assert.ok(DMA.ENTITIES.length > 0);
  for (const k of LISTS) assert.ok(DMA[k].length > 0, `${k} is empty in fixture mode`);
  for (const k of ENTITY_ACCESSORS) {
    assert.ok(DMA[k]("fce-001"), `${k} returned nothing for the flagship`);
  }
});

test("LIVE mode with no promoted payload yields null, never the fixture", () => {
  const { DMA } = load(LIVE);
  for (const k of ENTITY_ACCESSORS) {
    assert.strictEqual(DMA[k]("baxter"), null, `${k} must be null, not fixture data`);
  }
  for (const k of LISTS) {
    assert.deepStrictEqual(DMA[k], [], `${k} must be empty, not fixture data`);
  }
});

test("an id-scoped accessor refuses a registry for a different entity", () => {
  const w = load(LIVE);
  w.DMA_ENTITY = { id: "someone-else", financials: { headline: "LEAK" } };
  assert.strictEqual(w.DMA.financialsFor("baxter"), null,
                     "the accessor was given an id; a mismatch answers null");
});

test("clearing the registry empties the lists, which is the route-change contract", () => {
  // The list getters and the by-id lookups have no entity argument — the
  // evidence drawer only knows an e_id. They therefore answer for whichever
  // entity the registry holds, and the safety property has to live one level
  // up: useLiveEntity CLEARS window.DMA_ENTITY before fetching the next
  // entity, so during the change the lists are empty rather than showing the
  // previously viewed client's rows.
  const w = load(LIVE);
  w.DMA_ENTITY = { id: "previous", insightCards: [{ id: "IC-OLD" }],
                   evidence: [{ id: "E-OLD" }] };
  assert.strictEqual(w.DMA.INSIGHT_CARDS.length, 1);
  w.DMA_ENTITY = null;                       // what the loader does on change
  assert.deepStrictEqual(w.DMA.INSIGHT_CARDS, []);
  assert.strictEqual(w.DMA.getEvidence("E-OLD"), undefined,
                     "a cleared registry resolves nothing");
});

test("the loader clears the registry before fetching a different entity", () => {
  // Enforced by reading the loader: the guarantee above is only as good as
  // this line, and a refactor that drops it reintroduces cross-client bleed
  // with no visible symptom until two clients are open in one session.
  const fs = require("node:fs");
  const src = fs.readFileSync(path.join(__dirname, "..", "proto", "utils.jsx"), "utf8");
  const loader = src.slice(src.indexOf("function useLiveEntity"));
  assert.ok(/window\.DMA_ENTITY\s*=\s*null/.test(loader),
            "useLiveEntity must clear window.DMA_ENTITY before it fetches");
});

test("a matching registry answers, and the lists are getters not snapshots", () => {
  const w = load(LIVE);
  w.DMA_ENTITY = { id: "baxter", financials: { headline: "$6.5B · FY2025" },
                   insightCards: [{ id: "IC-1" }] };
  assert.strictEqual(w.DMA.financialsFor("baxter").headline, "$6.5B · FY2025");
  assert.strictEqual(w.DMA.INSIGHT_CARDS.length, 1);
  // Replacing the registry (a route change) must change what the lists say.
  w.DMA_ENTITY = { id: "baxter", insightCards: [{ id: "IC-1" }, { id: "IC-2" }] };
  assert.strictEqual(w.DMA.INSIGHT_CARDS.length, 2,
                     "a captured array would still say 1");
});

/* ── the mappings ─────────────────────────────────────────────────── */

test("subcaps carry the database's generated delta and thin flag", () => {
  const w = load(LIVE);
  const out = w.adaptSubcaps([{
    subcap_id: "P4C1.1.2", subcap_name: "Member data layer", pillar_id: "P4",
    category_id: "P4C1", capability_id: "P4C1.1", score: 1.95,
    peer_median: 2.5, delta: -0.55, confidence: "HIGH",
    linked_evidence_count: 2, is_thin_evidence: true,
    l3_platform_areas: ["[L3-SF-DATA-CLOUD] Salesforce Data Cloud"],
    source_cell: "P4_Subcap_Scoring!D12",
  }]);
  assert.strictEqual(out[0].score, 1.95);
  assert.strictEqual(out[0].delta, -0.55, "promoted, not recomputed");
  assert.strictEqual(out[0].thin, true);
  assert.deepStrictEqual(out[0].platforms, ["SF"]);
});

test("platform fit comes from the opportunity surface, and an unscored platform is absent", () => {
  const w = load(LIVE);
  const oss = w.adaptOss({ tiles: [
    { platform: "Salesforce", composite: 82.4 },
    { platform: "Databricks", composite: 41 },
    { platform: "Tableau", composite: null },
  ] });
  // Keyed by the PROMOTED platform string, and NOT rounded: a fit score is the
  // producer's figure, and 82.4 → 82 loses a tenth for no reason.
  assert.strictEqual(oss.Salesforce, 82.4);
  assert.strictEqual(oss.Databricks, 41);
  assert.ok(!("Tableau" in oss), "a zero would read as assessed-and-empty");
});

test("two tiles for the same vendor both survive", () => {
  // The regression this keying exists for. Folding onto a vendor alias put
  // "Salesforce Data Cloud" and "Service Cloud consolidation" on one key "SF",
  // last write won, and one promoted tile was silently destroyed — four tiles
  // rendered as three, with the survivor labelled with the other one's name.
  const w = load(LIVE);
  const oss = w.adaptOss({ tiles: [
    { platform: "Salesforce Data Cloud", composite: 70 },
    { platform: "Service Cloud consolidation", composite: 73 },
  ] });
  assert.strictEqual(Object.keys(oss).length, 2, "neither tile is lost");
  assert.strictEqual(oss["Salesforce Data Cloud"], 70);
  assert.strictEqual(oss["Service Cloud consolidation"], 73);
});

test("the roadmap phase carries a label and a colour so the strip can render", () => {
  // `background: r.color` was undefined under `color:"#fff"` — white on white,
  // 300px of apparently blank page — and `r.label.toUpperCase()` threw.
  const w = load(LIVE);
  const out = w.adaptRoadmap({ phases: [
    { phase: 1, horizon: "next two quarters", rec_ids: ["REC-001"],
      rationale: "the backbone lands first" },
    { phase: 2, rec_ids: [] },
  ] });
  assert.strictEqual(out[0].label, "next two quarters");
  assert.strictEqual(out[1].label, "Phase 2", "a phase with no horizon still labels");
  assert.ok(out[0].color && out[1].color, "every phase gets a colour");
  assert.notStrictEqual(out[0].color, out[1].color, "adjacent phases differ");
  assert.strictEqual(out[0].rationale, "the backbone lands first");
});

test("the stair-step ladder reaches the accessor's key, in the curve's shape", () => {
  // data.js reads `stairstepClusters`; buildLiveEntity emitted `stairstep`, so
  // the curve reported "no ladder promoted" against a promoted ladder.
  const w = load(LIVE);
  const c = w.stairstepClustersOf({ ladder: { theme: "Data foundation", steps: [
    { step_level: 1, label: "Named ownership", entry_condition: "a named owner",
      unlocks: "a governed source", current_position: true,
      covered_subcap_ids: ["P4C1.1.1"] },
    { step_level: 2, label: "One governed record", effort_band: "M" },
  ] } });
  const key = Object.keys(c)[0];
  assert.strictEqual(key, "Data foundation");
  assert.strictEqual(c[key].steps.length, 2);
  assert.strictEqual(c[key].steps[0].m, 1, "the rung level, not a maturity band");
  assert.strictEqual(c[key].current, 1);
  assert.ok(c[key].steps[0].note.includes("→"), "entry condition → unlocks");
  assert.deepStrictEqual(c[key].steps[0].platforms, [],
    "no platform is invented for a rung");
});

test("an absent ladder yields no clusters rather than a broken one", () => {
  const w = load(LIVE);
  assert.deepStrictEqual(w.stairstepClustersOf(null), {});
  assert.deepStrictEqual(w.stairstepClustersOf({ ladder: { steps: [] } }), {});
});

test("acquisitions map the contract's keys onto the card's", () => {
  // The card read a.target/a.date/a.details/a.subcaps/a.evidence; the contract
  // states target_name/closed_on/effect_note/affected_subcap_ids/e_ids. Passing
  // rows through raw rendered a blank title and an empty drilldown.
  const w = load(LIVE);
  const out = w.adaptAcquisitions({ rows: [{
    target_name: "HealthCare Associates Credit Union", closed_on: null,
    kind: "MERGER", status: "ANNOUNCED", effect_note: "member accounts migrate",
    integration_target: "servicing history", affected_subcap_ids: ["P2C3.1.1"],
    e_ids: ["E-CC-004"],
  }] });
  assert.strictEqual(out[0].target, "HealthCare Associates Credit Union");
  assert.strictEqual(out[0].kind, "MERGER");
  assert.ok(out[0].details.includes("member accounts migrate"));
  assert.deepStrictEqual(out[0].subcaps, ["P2C3.1.1"]);
  assert.deepStrictEqual(out[0].evidence, ["E-CC-004"]);
  assert.strictEqual(out[0].date, null, "undated stays null, never a placeholder");
});

test("issue caps are built from each issue's own linked cells", () => {
  // DMA.ISSUE_CAPS was {} in LIVE, so no issue could ever show the cells it
  // caps — the "issues not linked to the DMA" symptom.
  const w = load(LIVE);
  const caps = w.issueCapsOf({ issues: [
    { issue_id: "ISS-003", linked_subcap_ids: ["P2C2.1.1", "P2C3.1.1"] },
    { issue_id: "ISS-001", linked_subcap_ids: [] },
  ] });
  assert.deepStrictEqual(Object.keys(caps), ["ISS-003"]);
  assert.deepStrictEqual(Object.keys(caps["ISS-003"].caps),
                        ["P2C2.1.1", "P2C3.1.1"]);
  assert.strictEqual(caps["ISS-003"].caps["P2C2.1.1"], null,
    "linkage without a stated cap level does not imply a ceiling");
});

test("a section's envelope citations reach the card", () => {
  // e_ids live on the envelope, not in data, so the regulatory card printed
  // "cites no evidence ids" while the envelope carried two.
  const w = load(LIVE);
  const page = { sections: { regulatory_standing: {
    data: { primary_regulator: "NCUA" }, e_ids: ["E-BCU-001", "E-CC-006"] } } };
  assert.deepStrictEqual(w.secWithEnv(page, "regulatory_standing").e_ids,
                         ["E-BCU-001", "E-CC-006"]);
  // A data field of the same name is never overwritten.
  const page2 = { sections: { x: { data: { e_ids: ["E-1"] }, e_ids: ["E-2"] } } };
  assert.deepStrictEqual(w.secWithEnv(page2, "x").e_ids, ["E-1"]);
});

test("CAGR is computed from the dated points, or null", () => {
  const w = load(LIVE);
  const f = w.adaptFinancials({ series: [
    { period: "FY2023", value: 5.8, unit: "USD billions" },
    { period: "2025-12", value: 6.5 },
  ] }, null, null);
  // (6.5/5.8)^(1/2) - 1
  assert.ok(Math.abs(f.cagr - 0.0587) < 0.001, `got ${f.cagr}`);
  assert.strictEqual(f.cagr_basis, "2023–2025 · 2 yr", "the span is named");
  // One point cannot yield a rate, and a defaulted rate is a fabricated trend.
  const one = w.adaptFinancials({ series: [{ period: "FY2025", value: 6.5 }] }, null, null);
  assert.strictEqual(one.cagr, undefined);
});

test("an off-vocabulary timeline signal becomes unclassified, not neutral", () => {
  // Coercing prose to "neutral" made ten unclassified events look deliberately
  // neutral; the filters then matched nothing with no explanation.
  const w = load(LIVE);
  const out = w.adaptTimeline({ events: [
    { event_date: "2016-01-01", title: "a", signal: "POSITIVE" },
    { event_date: "2018-01-01", title: "b", signal: "The analytics practice predates the strategy." },
    { event_date: "2020-01-01", title: "c", signal: null },
  ] });
  assert.strictEqual(out[0].signal, "positive");
  assert.strictEqual(out[1].signal, "unclassified");
  assert.strictEqual(out[2].signal, "unclassified", "absent is not neutral");
  assert.ok(out[1].signal_raw.startsWith("The analytics"), "the raw value is kept");
});

test("sentiment groups by the payload's own audience and keeps each scale", () => {
  const w = load(LIVE);
  const s = w.adaptSentiment({ bars: [
    { audience: "employee", source: "Glassdoor", metric: "Overall",
      rating: 3.6, scale: "0..5", n: 312 },
    { audience: "customer", source: "Member NPS", rating: 79.81,
      scale: "NPS -100..100" },
  ] });
  assert.strictEqual(s.employee.length, 1);
  assert.strictEqual(s.customer.length, 1);
  assert.strictEqual(s.employee[0].scale, 5);
  assert.strictEqual(s.customer[0].scale, 100, "an NPS keeps its own bounds");
  assert.strictEqual(s.customer[0].score, 79.81, "never rescaled");
});

test("an unstated sentiment scale gives no bar rather than a wrong one", () => {
  const w = load(LIVE);
  assert.strictEqual(w.scaleMaxOf("stars"), null);
  assert.strictEqual(w.scaleMaxOf(undefined), null);
});

test("a ceiling stated as a band word is placed and flagged, not read as a score", () => {
  const w = load(LIVE);
  const u = w.adaptUncertainty({ rows: [
    { category_id: "P1C1", category_name: "Digital Strategy & Vision",
      ceiling: "Differentiating", uncertainty_band: 0.3, e_ids: ["E-1"],
      urf_modifiers: [{ clause: "no innovation lab confirmed", value: 0.1 }] },
    { category_id: "P4C1", ceiling: "2.5", uncertainty_band: 0.4 },
  ] });
  assert.strictEqual(u.P1C1.ceiling, 4.5, "band midpoint");
  assert.strictEqual(u.P1C1.ceiling_is_band, true);
  assert.strictEqual(u.P1C1.ceiling_stated, "Differentiating");
  assert.deepStrictEqual(u.P1C1.modifiers, ["no innovation lab confirmed 0.1"]);
  assert.strictEqual(u.P4C1.ceiling, 2.5);
  assert.strictEqual(u.P4C1.ceiling_is_band, false, "a number is a number");
});

test("coverage carries the gate as data, and per-pillar cell counts", () => {
  const w = load(LIVE);
  const c = w.adaptCoverage({ overall_pct: 96.0, gate_pct: 80.0, per_pillar: [
    { pillar_id: "P1", pct: 98.0, cells_total: 194, cells_covered: 190,
      below_gate: false }] });
  assert.strictEqual(c.gate_pct, 80, "the orange line is data, not a constant");
  assert.strictEqual(c.by_pillar[0].subcaps, 194);
  assert.strictEqual(c.by_pillar[0].scored, 190);
});

test("an insight's flag is authored where authored, derived where not, and says which", () => {
  const w = load(LIVE);
  const cards = w.adaptInsights({ cards: [
    { ic_id: "IC-1", title: "a", severity: "critical" },
    { ic_id: "IC-2", title: "b", severity: "high", linked_rec_id: "REC-01" },
    { ic_id: "IC-3", title: "c", flag: "MONITOR", severity: "critical" },
  ] }, { recommendations: [{ rec_id: "REC-01", l3_area: "Salesforce Data Cloud" }] });
  assert.strictEqual(cards[0].flag, "CRITICAL");
  assert.strictEqual(cards[0].flag_source, "severity");
  assert.deepStrictEqual(cards[1].platforms, ["SF"],
                         "chips come from the linked recommendation");
  assert.strictEqual(cards[2].flag, "MONITOR");
  assert.strictEqual(cards[2].flag_source, "authored",
                     "an authored flag wins over the derivation");
});

test("an insight card's theme is derived from the finding sharing its cell", () => {
  const w = load(LIVE);
  const findings = { findings: [
    { f_id: "F-01", theme: "DATA FOUNDATION", linked_subcap_ids: ["P4C1.1.1"] },
    { f_id: "F-02", theme: "WORKFLOW", linked_subcap_ids: ["P3C2.4.2"] },
  ] };
  const cards = w.adaptInsights({ cards: [
    // exact cell — the strongest rung
    { ic_id: "IC-1", title: "a", severity: "critical", linked_subcap_id: "P4C1.1.1" },
    // same category as F-02's cell, not the same cell
    { ic_id: "IC-2", title: "b", severity: "high", linked_subcap_id: "P3C2.9.9" },
    // a category no finding touches
    { ic_id: "IC-3", title: "c", severity: "info", linked_subcap_id: "P1C4.1.1" },
    // no cell at all
    { ic_id: "IC-4", title: "d", severity: "info" },
  ] }, { recommendations: [] }, findings);
  assert.strictEqual(cards[0].theme, "DATA FOUNDATION");
  assert.strictEqual(cards[0].theme_source, "finding on the same cell");
  assert.strictEqual(cards[1].theme, "WORKFLOW");
  assert.strictEqual(cards[1].theme_source, "finding in P3C2",
                     "the category rung is used and says so");
  assert.strictEqual(cards[2].theme, null, "no finding touches P1C4 — no theme");
  assert.strictEqual(cards[2].theme_source, null);
  assert.strictEqual(cards[3].theme, null, "no cell, nothing to inherit from");
});

test("an insight card has no theme when the run promoted no findings", () => {
  const w = load(LIVE);
  const cards = w.adaptInsights(
    { cards: [{ ic_id: "IC-1", title: "a", severity: "critical",
                linked_subcap_id: "P4C1.1.1" }] }, { recommendations: [] }, null);
  assert.strictEqual(cards[0].theme, null,
                     "a derived value is computed or null, never a default");
});

test("every severity the contract defines maps to a flag", () => {
  const w = load(LIVE);
  const cards = w.adaptInsights({ cards: [
    { ic_id: "IC-1", severity: "critical" }, { ic_id: "IC-2", severity: "high" },
    { ic_id: "IC-3", severity: "opportunity" }, { ic_id: "IC-4", severity: "info" },
  ] }, { recommendations: [] }, null);
  assert.deepStrictEqual(cards.map(c => c.flag),
                         ["CRITICAL", "OPPORTUNITY", "OPPORTUNITY", "MONITOR"]);
  assert.deepStrictEqual(cards.map(c => c.flag_source),
                         ["severity", "severity", "severity", "severity"],
                         "no contract severity falls through to the default");
});

test("financial periods come from the series and the footer from firmographics", () => {
  const w = load(LIVE);
  const f = w.adaptFinancials(
    { series: [{ period: "FY2024", value: 6.1, unit: "USD billions" },
               { period: "FY2025", value: 6.5, unit: "USD billions" }],
      trend: "RISING" },
    { fields: [{ field: "branches", value: "46" },
               { field: "employees", value: "767" }] },
    { primary_regulator: "NCUA", jurisdictions: ["Illinois", "Wisconsin"] });
  assert.deepStrictEqual(f.fy, ["FY2024", "FY2025"]);
  assert.strictEqual(f.unit, "B");
  assert.strictEqual(f.branches, 46);
  assert.strictEqual(f.regulator, "NCUA");
  assert.strictEqual(f.geography, "Illinois · Wisconsin");
  assert.deepStrictEqual(f.nim_pct, [null, null],
                         "not in the contract: null, never a zero bar");
});

test("evidence keeps its excerpt, and the tier summary is a pass-through", () => {
  const w = load(LIVE);
  const items = w.adaptEvidence({ items: [{
    e_id: "E-BCU-012", source_name: "BCU annual report",
    source_url: "https://bcu.org/ar", tier: "T1", claim_type: "FACT",
    ers: 4.4, recency_band: "CURRENT", excerpt: "Board committees: Technology…",
    subcaps: ["P1C1.1.1"] }] });
  assert.strictEqual(items[0].excerpt, "Board committees: Technology…");
  assert.strictEqual(items[0].source, "bcu.org/ar", "scheme stripped for display");
  assert.strictEqual(items[0].tier, "T1");

  const sum = w.adaptEvidenceSummary({ distribution: {
    tiers: { T1: 5, T2: 13 }, claims: { FACT: 73, INFERENCE: 2 },
    total_items: 84, excluded_identity: 0 } });
  assert.strictEqual(sum.total_items, 84);
  assert.strictEqual(sum.total_facts, 75, "claim counts, not recounted rows");
});

test("a leadership row with no name is a role GAP, and Clay is null until stored", () => {
  const w = load(LIVE);
  const roster = w.adaptLeadership({ roster: [
    { name: "John Sahagian", title: "CDO", domain: "Data", tenure_months: 92,
      source_e_id: "E-BCU-057" },
    { name: "-", title: "CISO" },
  ] }, null);
  assert.strictEqual(roster[0].clay, null,
                     "the app never calls Clay at request time");
  assert.strictEqual(roster[0].gap_flag, false);
  assert.strictEqual(roster[1].gap_flag, true, "an unnamed critical role is a gap");

  const enriched = w.adaptLeadership(
    { roster: [{ name: "John Sahagian", title: "CDO" }] },
    { items: [{ subject_kind: "person", subject_key: "John Sahagian",
                payload: { linkedin: "linkedin.com/in/x" } }] });
  assert.strictEqual(enriched[0].clay.linkedin, "linkedin.com/in/x");
  assert.strictEqual(enriched[0].enrichment_status, "stored");
});

test("buildLiveEntity returns null sections rather than inventing them", () => {
  const w = load(LIVE);
  const e = w.buildLiveEntity("baxter", {}, {});
  assert.strictEqual(e.id, "baxter");
  assert.strictEqual(e.financials, null);
  assert.strictEqual(e.sentiment, null);
  assert.deepStrictEqual(e.subcaps, []);
  assert.deepStrictEqual(e.insightCards, []);
  assert.deepStrictEqual(e.pillar_scores, {});
  assert.strictEqual(e.overall, null);
});

test("section provenance is carried per section, as the prototype states it", () => {
  const w = load(LIVE);
  const st = w.sectionStates({ overview: { sections: {
    exec_summary: { data_source: "producer", provenance: "producer",
                    produced_at: "2026-08-05T06:05:59Z",
                    producer_version: "dma-surface-production@2026-08-05",
                    e_ids: ["E-1", "E-2"] } } } });
  const s = st["overview.exec_summary"];
  assert.strictEqual(s.producer_version, "dma-surface-production@2026-08-05");
  assert.strictEqual(s.e_ids.length, 2);
  assert.ok(s.produced_at, "when it promoted must be renderable per card");
});

test("the tech layer rollup is computed from the register, not read from it", () => {
  const w = load(LIVE);
  const ts = { items: [
    { ts_id: "TS-1", layer: "OPS",  pillar_id: "P3", status: "CONFIRMED" },
    { ts_id: "TS-2", layer: "OPS",  pillar_id: "P3", status: "INFERRED" },
    { ts_id: "TS-3", layer: "CUST", pillar_id: "P2", status: "CONFIRMED" },
    { ts_id: "TS-4", layer: "CUST", pillar_id: "P2", status: "CONFIRMED" },
    // DATA: nothing confirmed, and one slot searched and not found
    { ts_id: "TS-5", layer: "DATA", pillar_id: "P4", status: "INFERRED" },
    { ts_id: "TS-6", layer: "DATA", pillar_id: "P4", status: "ABSENT" },
  ] };
  const rows = w.techLayersOf(ts);
  assert.deepStrictEqual(rows.map(r => r.layer), ["OPS", "CUST", "DATA"],
                         "only layers the register actually uses");
  const data = rows.find(r => r.layer === "DATA");
  assert.strictEqual(data.expected, 2, "an ABSENT row is a slot, so it counts");
  assert.strictEqual(data.detected, 1, "...but it is not detected");
  assert.strictEqual(data.is_primary_gap, true, "fewest confirmed wins");
  assert.match(data.basis, /0 confirmed of 2/);
  assert.strictEqual(rows.find(r => r.layer === "CUST").is_primary_gap, false,
                     "the best-covered layer is never the gap");
  assert.strictEqual(data.pillar_id, "P4", "the pillar comes off the rows");
});

test("a tie in the layer rollup flags nothing rather than guessing", () => {
  const w = load(LIVE);
  const rows = w.techLayersOf({ items: [
    { layer: "OPS",  status: "INFERRED" }, { layer: "OPS",  status: "INFERRED" },
    { layer: "DATA", status: "INFERRED" }, { layer: "DATA", status: "INFERRED" },
  ] });
  assert.deepStrictEqual(rows.map(r => r.is_primary_gap), [false, false],
    "both layers have 0 confirmed and the same ratio — inventing a winner is the defect");
});

test("the layer rollup is empty, never a fixture, when the run has no register", () => {
  const w = load(LIVE);
  assert.deepStrictEqual(w.techLayersOf(null), []);
  assert.deepStrictEqual(w.techLayersOf({ items: [] }), []);
  assert.deepStrictEqual(w.DMA.TECH_LAYERS, [],
                         "LIVE with nothing promoted returns [] and not the prototype's");
});
