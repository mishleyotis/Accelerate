/* The heatmap in the CUSTOMER audience: the grid is theirs, and so is the
 * evidence drawer behind it.
 *
 * Reported 2026-10-07 by the build owner: "It is the customer view that lacks
 * heatmap details for most clients … Fix the evidence drawer too … Ensure no
 * recurrence."
 *
 *   HM-CUST-1  ClientHeatmap locked the customer audience out of the standard
 *              grid (pillar · category · capability · cell): the Standard
 *              button was disabled and an effect switched any customer read
 *              back to Focus areas. A customer therefore saw the focus areas
 *              and the value chain only — on most promoted clients a handful
 *              of cards and an arrangement the catalogue does not carry. The
 *              PRD lists the heatmap dashboard as "internal + customer" on all
 *              five surfaces (H4 grid, H1, H2 cell evidence, H6, H9), and the
 *              TRD's audience table SHOWS thin-evidence markers to the
 *              customer; what a customer may not see is stripped by the
 *              server (apps/api/dma_api/redaction.py), not hidden by a lock.
 *              The unlock landed first in afadd6c (client-dashboard.test.js
 *              pins it there too); this file pins it beside the drawer fixes.
 *   HM-CUST-2  The Issues overlay (issue register + caps) is Context-page and
 *              O1b-ceiling material, both customer-withheld, so it is not
 *              offered to the customer at all.
 *   HM-CUST-3  The evidence drawer keyed its tier filter and every item chip on
 *              `tier`, which the server strips from the customer body: a
 *              customer read printed "undefined · undefined" on every item and
 *              "undefined · N" as a filter.
 *
 * Run with `npm run test:web` after `npm run build:proto`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");

const ID = "customer-view-shape";
const RUN = { id: "run", run_id: "run" };

function sec(data) {
  return { data, data_source: "producer", provenance: null,
           produced_at: "2026-10-07T00:00:00Z", producer_version: "t", e_ids: [],
           empty_state: null };
}

const CELLS = [
  { subcap_id: "P1C1.1.1", subcap_name: "Digital vision articulation", pillar_id: "P1",
    category_id: "P1C1", capability_id: "P1C1.1", score: 1.5, peer_median: 2.9,
    linked_evidence_count: 2, is_thin_evidence: true },
  { subcap_id: "P2C1.1.1", subcap_name: "Campaign orchestration", pillar_id: "P2",
    category_id: "P2C1", capability_id: "P2C1.1", score: 2.5, peer_median: 2.4,
    linked_evidence_count: 4, is_thin_evidence: false },
];

const WORKBOOK = {
  pillars: { P1: { score: 1.55, peer_median: 2.56 }, P2: { score: 1.73, peer_median: 2.41 } },
  categories: { P1C1: { score: 1.56, peer_median: 2.92 }, P2C1: { score: 1.84, peer_median: 2.41 } },
};

/* An evidence item as the CUSTOMER body serves it: no tier, no ers, no
   recency band (all stripped by the server for that audience). */
const CUSTOMER_ITEMS = [
  { e_id: "E-1", source_name: "Annual report 2025", source_url: "https://example.org/ar",
    claim_type: "FACT", published_date: "2025-03-01", excerpt: "x".repeat(60),
    linked_subcap_ids: ["P1C1.1.1"] },
  { e_id: "E-2", source_name: "Trade press", source_url: "https://example.org/tp",
    claim_type: "INFERENCE", published_date: "2024-06-01", excerpt: "y".repeat(60),
    linked_subcap_ids: ["P1C1.1.1"] },
];

function heatmap(audience) {
  const { win } = H.load();
  H.installEntity(ID, { heatmap: { sections: { workbook_scores: sec(WORKBOOK) } } },
                  { subcaps: CELLS, evidence: { items: CUSTOMER_ITEMS } });
  const entity = win.DMA_ENTITY;
  return H.textOf(H.render(win.ClientHeatmap, { entity, run: RUN }, { audience }));
}

test("HM-CUST-1 · the customer opens on the standard grid, not on focus areas", () => {
  const text = heatmap("customer");
  assert.match(text, /\bZoom\b/,
    "the customer heatmap did not open on the standard grid — its zoom control is absent");
  assert.ok(!/not part of the customer view/i.test(text),
    "the standard grid is still described as withheld from the customer");
});

test("HM-CUST-1 · the compiled bundle carries no customer lock on the grid", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const js = fs.readFileSync(path.join(H.JS_DIR, "pages-d3-heatmap.js"), "utf8");
  assert.ok(!/audience === "customer" \? "focus"/.test(js),
    "the heatmap defaults the customer to focus areas again");
  assert.ok(!/mode === "standard"\) setMode\("focus"\)/.test(js),
    "an effect switches the customer off the standard grid again");
  assert.ok(!/disabled: audience === "customer"/.test(js),
    "the Standard button is disabled for the customer again");
});

test("HM-CUST-2 · the Issues overlay is internal only", () => {
  assert.match(heatmap("internal"), /\bIssues\b/, "the internal read lost its Issues toggle");
  assert.ok(!/\bIssues\b/.test(heatmap("customer")),
    "the customer read offers the Issues overlay (issue register and caps are customer-withheld)");
});

test("HM-CUST-3 · the customer evidence drawer never prints an undefined tier", () => {
  const { win } = H.load();
  H.installEntity(ID, { heatmap: { sections: { workbook_scores: sec(WORKBOOK) } } },
                  { subcaps: CELLS, evidence: { items: CUSTOMER_ITEMS } });
  const subcap = win.DMA_ENTITY.subcaps.find((s) => s.id === "P1C1.1.1");
  const text = H.textOf(H.render(win.EvidenceDrawer, {}, {
    audience: "customer", evidenceDrawer: { subcap }, closeEvidence: () => {},
    openSubcap: () => {} }));
  assert.ok(text.length > 0, "the drawer rendered nothing");
  assert.ok(!/undefined/.test(text), `the customer drawer printed "undefined": ${text.slice(0, 300)}`);
  assert.match(text, /Annual report 2025/, "the drawer lost the customer's evidence items");
});
