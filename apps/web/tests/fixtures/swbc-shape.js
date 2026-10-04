/* SWBC-SHAPED sections, for the render tests that pin the 2026-10-04 gold
 * audit of run 7968492e (display_id swbc).
 *
 * SHAPE, NOT CONTENT. Every key, list length, null pattern and audience split
 * below is the promoted run's own — that is what the defects were about: a
 * renderer that read `bars[]` and not `themes[]`, a tile with `rows: []` and
 * no `state`, a firmographics `cagr` held while a subsidiary series computed
 * one anyway, a heatmap peer column null in every row. The prose and the
 * figures are written for this file and describe no real institution, so the
 * fixture can be committed without carrying a client's content.
 *
 * Findings this file serves: RC-03 (D-01, D-02), RC-11 (D-05, D-14, D-15,
 * D-16, D-32, D-37).
 */

const ENV = (over) => ({
  produced_at: "2026-10-02T08:00:00Z",
  producer_version: "fixture@2026-10-04",
  ...over,
});

const sec = (data) => ({ data, e_ids: (data && data.e_ids) || [],
                         produced_at: "2026-10-02T08:00:00Z",
                         producer_version: "fixture", provenance: "fixture",
                         empty_state: null });

/* ── overview.sentiment — 1 bar, 6 themes (3 customer, 3 employee), no
   gap_analysis (one audience rated, so the contract says omit it). ───── */
const THEMES = [
  { audience: "customer",
    theme: "Payment trouble after closing is the largest complaint category",
    mapped_subcap_ids: ["P2C3.7.3", "P2C3.5.4", "P2C3.2.3", "P2C3.3.1"],
    cap_statement: "The complaint record concentrates in servicing after "
      + "closing. It caps nothing further: Complaint Management (2.0) already "
      + "sits below 3.0 and the record is consistent with that score." },
  { audience: "customer",
    theme: "Review sites single out the online application",
    mapped_subcap_ids: ["P2C2.2.1"],
    cap_statement: "Two undated editorial reviews corroborate that a digital "
      + "application exists; this supports Digital Application Availability "
      + "at 3.0 and neither caps nor lifts it." },
  { audience: "customer",
    theme: "Borrowers praise loan officers and report trouble reaching the company by phone",
    mapped_subcap_ids: ["P2C3.3.1", "P2C2.2.1"],
    cap_statement: "Mixed reading: adds 0.2 of uncertainty to Contact Center "
      + "Excellence (2.4) and no cap." },
  { audience: "employee",
    theme: "The few employees who rated the employer rate culture highest",
    mapped_subcap_ids: ["P1C4.8.1"],
    cap_statement: "Undated and under 30 ratings, so UNVERIFIED and low-sample; "
      + "it neither caps nor lifts Innovation Culture (1.0)." },
  { audience: "employee",
    theme: "A workplace award for the mortgage subsidiary",
    mapped_subcap_ids: ["P1C4.8.6"],
    cap_statement: "A self-published award announcement with no scale; it "
      + "neither caps nor lifts DEI Integration (1.5)." },
  { audience: "employee",
    theme: "Two regional best-employer distinctions claimed on the careers page",
    mapped_subcap_ids: ["P1C4.7.2"],
    cap_statement: "Undated self-published claims; Recognition Programs (2.5) "
      + "is neither capped nor lifted." },
];

const SENTIMENT = ENV({
  bars: [{
    audience: "customer",
    source: "Review-site rating relayed by a third-party mortgage review page",
    rating: 4.9, scale: "1-5 stars", n: 1000, as_of: "2025-11-04",
    url: "https://reviews.example.test/lender", e_id: "E-CC-9001",
    trend_vs_prior: null,
  }],
  e_ids: ["E-CC-9001", "E-CC-9002", "E-CC-9003"],
  themes: THEMES,
  r_layer: { hypothesis: "h", counter: "c", domain_test: "d",
             probes_run: ["p"], verdict: "ACCEPT", confidence: "medium" },
  empty_state: {
    reason: "One rated line is available, company-reported and relayed by a "
      + "review site. Employee readings give themes but no dated rated line.",
    sources_searched: ["App store search — no consumer app found"],
    closure_condition: "A second rated source with rating, scale, n and date.",
  },
  internal_only: ["bars", "empty_state.sources_searched", "r_layer"],
  narrative_thread: "One company-reported rating and a complaint record that "
    + "sits after closing keep the picture indicative rather than settled.",
});

/* ── context.context_sentiment — two tiles, the employee one with rows:[]
   and NO `state` key, exactly as promoted. ─────────────────────────────── */
const CONTEXT_SENTIMENT = ENV({
  e_ids: ["E-CC-9001", "E-CC-9002", "E-CC-9003"],
  context_tiles: [
    { audience: "customer",
      note: "One rated line is available. The federal complaint record is a "
        + "count with no rate, so it is context and not a rating.",
      rows: [{ source: "Review-site rating (company-reported)", rating: 4.9,
               scale: "1-5 stars", n: 1000, as_of: "2025-11-04",
               url: "https://reviews.example.test/lender", e_id: "E-CC-9001",
               note: "Company-reported; read as context for Complaint Management." }],
      e_ids: ["E-CC-9001", "E-CC-9002"],
      sources_searched: ["App store search — none found"] },
    { audience: "employee",
      note: "An employer-review site shows 4.1 of 5 on 7 ratings, undated, so "
        + "it draws no bar. Two workplace awards are claims, not ratings.",
      rows: [],
      e_ids: ["E-CC-9003", "E-CC-9004", "E-CC-9005"],
      sources_searched: ["Employer-review site — reached, 7 ratings, undated",
                         "Glassdoor — HTTP 403, not reached"] },
  ],
  empty_state: {
    reason: "One rated line carries the card and it is indicative only.",
    sources_searched: ["see tiles"],
    closure_condition: "A second rated source for any audience.",
  },
  internal_only: ["r_layer", "context_tiles[*].sources_searched",
                  "empty_state.sources_searched"],
  narrative_thread: "The outside view has one rated line.",
});

/* ── overview.financial_series — four points, every basis naming a
   SUBSIDIARY, not the group. ─────────────────────────────────────────── */
const SUB_BASIS = "Dollar volume of loans originated in the calendar year, "
  + "Example Mortgage Corporation only: a subsidiary of the group, not the group";
const FINANCIAL_SERIES = ENV({
  e_ids: ["E-CC-9101", "E-CC-9102", "E-CC-9103", "E-CC-9104"],
  trend: "VOLATILE",
  series: [
    { period: "CY2022", value: 2.8, unit: "USD billions", as_of: "2022-12-31",
      source_e_id: "E-CC-9101", basis: SUB_BASIS },
    { period: "CY2023", value: 2.1, unit: "USD billions", as_of: "2023-12-31",
      source_e_id: "E-CC-9102", basis: SUB_BASIS },
    { period: "CY2024", value: 2.3, unit: "USD billions", as_of: "2024-12-31",
      source_e_id: "E-CC-9103", basis: SUB_BASIS },
    { period: "CY2025", value: 2.3, unit: "USD billions", as_of: "2025-12-31",
      source_e_id: "E-CC-9104", basis: SUB_BASIS },
  ],
  reading: "The mortgage line's originations fell and recovered; group "
    + "growth is not established.",
  internal_only: ["r_layer"],
  narrative_thread: "A labelled subsidiary series.",
});

/* ── overview.firmographics — ten fields, six of them HELD with a reason. */
const held = (field, unit, reason) => ({
  field, value: null, unit, as_of: null, confidence: "LOW", quarantined: true,
  source_e_id: "E-CC-9200", recency_band: "UNVERIFIED", quarantine_reason: reason,
});
const FIRMOGRAPHICS = ENV({
  e_ids: ["E-CC-9200"],
  fields: [
    { field: "employees", value: "2300", unit: "employees, self-reported",
      as_of: "2026-04-06", confidence: "MEDIUM", quarantined: false,
      source_e_id: "E-CC-9200", recency_band: "CURRENT", quarantine_reason: null },
    held("revenue", "USD", "The group is privately held and publishes no consolidated revenue."),
    held("assets", "USD", "No consolidated balance sheet is published."),
    held("cagr", "percent a year", "No enterprise revenue or asset series is published, so no group growth rate can be computed."),
    { field: "hq", value: "San Antonio, Texas", unit: null, as_of: null,
      confidence: "HIGH", quarantined: false, source_e_id: "E-CC-9200",
      recency_band: "UNVERIFIED", quarantine_reason: null },
    held("branches", "count", "The group states a national footprint and no branch count."),
    { field: "founded", value: "1976", unit: "year", as_of: null,
      confidence: "HIGH", quarantined: false, source_e_id: "E-CC-9200",
      recency_band: "UNVERIFIED", quarantine_reason: null },
    held("primary_regulator", null, "Each regulated line holds its own licence; there is no single primary regulator."),
    held("charter", null, "The parent is not a chartered depository."),
    { field: "website", value: "example.test", unit: null, as_of: null,
      confidence: "HIGH", quarantined: false, source_e_id: "E-CC-9200",
      recency_band: "UNVERIFIED", quarantine_reason: null },
  ],
  undated_pct: 80,
  internal_only: [],
  narrative_thread: "A privately held group that states little at group level.",
});

/* ── heatmap.workbook_scores — 16 categories, two with no category figure,
   peer_median null in EVERY row at both grains. ──────────────────────── */
const CATS = ["P1C1", "P1C2", "P1C3", "P1C4", "P2C1", "P2C2", "P2C3", "P2C4",
              "P3C1", "P3C2", "P3C3", "P3C4", "P4C1", "P4C2", "P4C3", "P4C4"];
const PEER_REASON = "The peer column is empty at every grain because the "
  + "three peers identified for this engagement were not scored.";
const WORKBOOK_SCORES = ENV({
  e_ids: [],
  categories: Object.fromEntries(CATS.map((c, i) => [c, {
    score: (c === "P1C2" || c === "P2C1") ? null : 1.5 + (i % 5) * 0.2,
    peer_median: null, source_cell: `Category_Detail!B${i + 2}`,
  }])),
  pillars: Object.fromEntries(["P1", "P2", "P3", "P4"].map((p, i) => [p, {
    score: 1.9 + i * 0.05, peer_median: null, source_cell: `Pillar_Summary!C${i + 2}`,
  }])),
  empty_state: {
    reason: "Two categories carry no workbook roll-up. " + PEER_REASON,
    sources_searched: ["Workbook peer table: no peer figure"],
    closure_condition: "A peer table scored at pillar and category grain.",
  },
  internal_only: ["r_layer"],
  narrative_thread: "Fourteen of sixteen categories carry a workbook figure.",
});

/* The cells behind the two categories with no workbook figure, so the grid
   has something it could average — and must label if it does. */
const SUBCAPS = [
  { subcap_id: "P1C2.1.1", category_id: "P1C2", pillar_id: "P1", score: 2.0, subcap_name: "Risk appetite statement" },
  { subcap_id: "P1C2.1.2", category_id: "P1C2", pillar_id: "P1", score: 3.0, subcap_name: "Risk reporting" },
  { subcap_id: "P2C1.1.1", category_id: "P2C1", pillar_id: "P2", score: 1.0, subcap_name: "Channel strategy" },
];

/* ── techstack.techstack — 36 rows over four layers, ONE absent (a vendor
   naming itself plus a category), every layer `expected: null`. ──────── */
function techItems() {
  const out = [];
  let n = 1;
  const add = (layer, pillar, status) => out.push({
    ts_id: `TS-${String(n).padStart(3, "0")}`, vendor: `Vendor ${n}`,
    product: `Product ${n++}`, layer, pillar_id: pillar, status,
    evidence_level: "L2", detection_basis: "Named in a vendor case study.",
    as_of: null, linked_subcap_ids: [], e_ids: ["E-CC-9300"],
  });
  for (const [layer, pillar, mix] of [
    ["OPS", "P3", { CONFIRMED: 6, INFERRED: 3, CLAIMED: 3 }],
    ["CUST", "P2", { CONFIRMED: 1, INFERRED: 2, CLAIMED: 5 }],
    ["DATA", "P4", { CONFIRMED: 4, INFERRED: 4, CLAIMED: 2 }],
    ["INFRA", "P4", { CONFIRMED: 1, INFERRED: 3, CLAIMED: 1 }],
  ]) {
    for (const [status, k] of Object.entries(mix)) {
      for (let i = 0; i < k; i++) add(layer, pillar, status);
    }
  }
  out.push({
    ts_id: "TS-099", vendor: "Example Group", product: "Shared customer data platform",
    layer: "DATA", pillar_id: "P4", status: "ABSENT", evidence_level: "L4",
    detection_basis: "The institution said in discovery that it has no customer "
      + "data platform; no public source confirms or contradicts it.",
    as_of: null, linked_subcap_ids: ["P4C1.2.2"], e_ids: ["E-CC-9301"],
  });
  return out;
}
const LAYER_BASIS = "The expected-product count is left unstated: no product "
  + "list exists for a group of this shape.";
const TECHSTACK = ENV({
  e_ids: ["E-CC-9300", "E-CC-9301"],
  items: techItems(),
  layers: ["OPS", "CUST", "DATA", "INFRA"].map((layer) => ({
    layer, detected: null, expected: null, expected_basis: LAYER_BASIS,
    is_primary_gap: layer === "DATA",
  })),
  internal_only: ["r_layer"],
  narrative_thread: "Thirty-five products placed and one recorded absent.",
});

function pages(over) {
  const p = {
    overview: { sections: {
      sentiment: sec(SENTIMENT),
      financial_series: sec(FINANCIAL_SERIES),
      firmographics: sec(FIRMOGRAPHICS),
    } },
    context: { sections: { context_sentiment: sec(CONTEXT_SENTIMENT) } },
    heatmap: { sections: { workbook_scores: sec(WORKBOOK_SCORES) } },
    techstack: { sections: { techstack: sec(TECHSTACK) } },
  };
  return Object.assign(p, over || {});
}

/* What a CUSTOMER read of a section carries once the server's default-deny
   walker has run: the `internal_only` paths are gone. The sentiment card's
   reduced customer variant (owner decision 1, 2026-10-04) is bars + themes;
   whether `bars` is still internal_only is the redaction stream's call, so
   the tests render BOTH shapes. */
function customerCopy(section, keep) {
  const d = JSON.parse(JSON.stringify(section));
  for (const p of d.internal_only || []) {
    if ((keep || []).includes(p)) continue;
    const parts = p.split(".");
    if (parts.length === 1) delete d[parts[0]];
    else if (d[parts[0]] && typeof d[parts[0]] === "object") delete d[parts[0]][parts[1]];
  }
  delete d.r_layer;
  return d;
}

module.exports = { SENTIMENT, CONTEXT_SENTIMENT, FINANCIAL_SERIES,
                   FIRMOGRAPHICS, WORKBOOK_SCORES, TECHSTACK, SUBCAPS,
                   PEER_REASON, LAYER_BASIS, sec, pages, customerCopy };
