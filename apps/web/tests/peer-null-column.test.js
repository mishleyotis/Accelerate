/* H4 · a column that is null in every row states WHY, once; a fallback
 * figure says on its face that it is not the workbook's.
 *
 * RC-03 (absence modelled only at section grain) and RC-11 / D-32, gold
 * audit of run 7968492e (2026-10-04).
 *
 *   · `heatmap.workbook_scores` promoted 16 categories and 4 pillars with
 *     `peer_median: null` in every row, and an empty_state whose reason says
 *     exactly why: the three peers identified for the engagement were not
 *     scored. The section was POPULATED, so the absence was never at section
 *     grain, and the grid printed sixteen silent peer cells (EnrichmentGap
 *     renders nothing without a reason) and no reason anywhere.
 *   · P1C2 and P2C1 carry no workbook category figure. The grid filled them
 *     with a band-coloured mean of their cells and said so only in a `title`
 *     attribute — on the face it read as the workbook's own number.
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");

const ID = "gold-audit-shape";

function setup() {
  const { win } = H.load();
  H.installEntity(ID, { heatmap: { sections: { workbook_scores: F.sec(F.WORKBOOK_SCORES) } } },
                  { subcaps: F.SUBCAPS });
  const ent = { id: ID, subcaps: win.DMA_ENTITY.subcaps, pillar_scores: {},
                pillar_peer_medians: {}, workbookScores: win.DMA_ENTITY.workbookScores };
  return { win, ent, pillars: win.runPillarsOf(ent) };
}

test("H4 category grid · an all-null peer column renders the section's reason", () => {
  const { win, ent, pillars } = setup();
  const html = H.render(win.CategoryHeatmap, {
    entity: ent, pillars, pillarFocus: null, showPeers: true, showIssues: false,
    setCatFocus: () => {}, onSynth: () => {}, audience: "internal" });
  const text = H.textOf(html);
  assert.ok(text.includes(F.PEER_REASON),
    "every category's peer median is null and the producer's reason for it "
    + "rendered nowhere on the grid");
  const n = (text.match(new RegExp(F.PEER_REASON.slice(0, 40).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length;
  assert.strictEqual(n, 1, `the reason rendered ${n} times; once per grid, not once per pillar`);
});

test("H4 pillar tiles · an all-null peer column renders the section's reason", () => {
  const { win, ent, pillars } = setup();
  const text = H.textOf(H.render(win.PillarHeatmap, {
    entity: ent, pillars, setPillarFocus: () => {}, audience: "internal" }));
  assert.ok(text.includes(F.PEER_REASON),
    "the four pillar tiles carry no peer figure and no reason");
});

test("D-32 · a cell-mean fallback says on its FACE that it is not a workbook figure", () => {
  const { win, ent, pillars } = setup();
  const html = H.render(win.CategoryHeatmap, {
    entity: ent, pillars, pillarFocus: "P1", showPeers: false, showIssues: false,
    setCatFocus: () => {}, onSynth: () => {}, audience: "internal" });
  const text = H.textOf(html);
  // P1C2 has no workbook figure and two scored cells (2.0, 3.0).
  assert.match(text, /2\.5/, "the fallback mean did not render at all");
  assert.match(text, /cell mean · not a workbook figure/,
    "the fallback mean is labelled only in a tooltip; on its face it reads "
    + "as the workbook's category score");
});
