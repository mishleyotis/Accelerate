/* O9 · the sentiment card renders the THEMES, not only the bars.
 *
 * RC-03 / D-01, gold audit of run 7968492e (2026-10-04). The card the owner
 * called "empty": the run promoted one rated bar and SIX themes, each with a
 * cap statement and the cells it bears on, plus a narrative thread. The
 * renderer read `bars[]` and nothing else, so the six themes reached no
 * reader, the employee group printed "Not established for this run." over
 * three employee themes, and the B2B/B2C chip read `industry_avg` and
 * `b2b_b2c_gap` — keys the contract never declares — so it could never light.
 *
 * Owner decision 1 (2026-10-04): the customer gets a REDUCED card — ratings
 * bars and themes, without cell codes, cap vocabulary, internal sources or
 * the reasoning trace. Internal keeps the full card.
 *
 * Rendered in-process against the COMPILED bundle (tests/ssr-harness.js), so
 * `npm run build:proto` first.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/swbc-shape");

const ID = "swbc-shape";
const CELL = /\bP[1-4]C\d(?:\.\d+){0,2}\b/;

function card(sentiment, audience) {
  const { win } = H.load();
  H.installEntity(ID, { overview: { sections: { sentiment: F.sec(sentiment) } } });
  const html = H.render(win.SentimentCard, { entity: { id: ID }, audience },
                        { audience });
  return { html, text: H.textOf(html) };
}

test("O9 internal · all six promoted themes render, with their cap statements", () => {
  const { html, text } = card(F.SENTIMENT, "internal");
  const rows = (html.match(/data-sentiment-theme=/g) || []).length;
  assert.strictEqual(rows, 6,
    `the run promoted 6 themes and the card rendered ${rows}. A theme that `
    + `promotes and reaches no screen is RC-03's defect`);
  for (const t of F.SENTIMENT.themes) {
    assert.ok(text.includes(t.theme), `theme missing: ${t.theme}`);
  }
  // The cap statement is the analysis — "sentiment that caps a cell is
  // evidence" — and internal readers get it.
  assert.ok(text.includes("Complaint Management (2.0)"),
    "the cap statement did not render on the internal card");
  // …with the cells it bears on as chips.
  assert.ok(text.includes("P2C3.7.3") && text.includes("P1C4.8.1"),
    "the mapped cells did not render as chips on the internal card");
});

test("O9 · an audience with themes and no bar is not 'Not established'", () => {
  const { text } = card(F.SENTIMENT, "internal");
  assert.ok(!/Not established for this run/i.test(text),
    "the employee group printed 'Not established for this run.' over three "
    + "promoted employee themes");
});

test("O9 · the narrative thread renders", () => {
  const { text } = card(F.SENTIMENT, "internal");
  assert.ok(text.includes(F.SENTIMENT.narrative_thread),
    "narrative_thread is promoted and reached no reader");
});

test("O9 · the gap chip is derived from gap_analysis.b2b_b2c, never from undeclared keys", () => {
  // The keys the old card read. Neither is declared by the contract, so a
  // payload carrying them must light nothing.
  const forged = { ...F.SENTIMENT, industry_avg: 3.2, b2b_b2c_gap: true };
  const a = card(forged, "internal");
  assert.ok(!/B2B\/B2C gap/.test(a.text),
    "the chip lit from `b2b_b2c_gap`, a key no contract declares");
  assert.ok(!/Industry avg/i.test(a.text),
    "the header printed `industry_avg`, a key no contract declares");

  const withGap = { ...F.SENTIMENT, gap_analysis: {
    b2b_b2c: "Employees rate the workplace well above how customers rate "
      + "service, which says the constraint is process rather than capability.",
    internal_external: null, e_ids: [] } };
  const b = card(withGap, "internal");
  assert.ok(/B2B\/B2C gap/.test(b.text),
    "gap_analysis.b2b_b2c is non-empty and the chip did not light");
  assert.ok(b.text.includes("constraint is process rather than capability"),
    "the gap analysis prose did not render on the internal card");
});

test("O9 customer · the REDUCED card: bars and themes, no cell codes, no cap vocabulary", () => {
  // Both customer shapes: bars still internal_only (today's redaction) and
  // bars released to the customer (decision 1). Either way, themes render.
  for (const keep of [[], ["bars"]]) {
    const cust = F.customerCopy(F.SENTIMENT, keep);
    const { html, text } = card(cust, "customer");
    assert.ok(html.length > 0, "the customer card rendered nothing");
    const rows = (html.match(/data-sentiment-theme=/g) || []).length;
    assert.strictEqual(rows, 6, `customer card rendered ${rows} of 6 themes`);
    assert.ok(!CELL.test(text),
      `a cell code reached the customer card: ${(text.match(CELL) || [])[0]}`);
    assert.ok(!/\bcaps?\b|\blifts?\b|uncertainty/i.test(text),
      "cap vocabulary reached the customer card");
    assert.ok(!/hypothesis|counter|probes?/i.test(text),
      "the reasoning trace reached the customer card");
    assert.ok(!text.includes(F.SENTIMENT.narrative_thread),
      "the internal synthesis reached the reduced customer card");
    if (keep.includes("bars")) {
      assert.ok(/4\.9/.test(text), "a released bar did not render for the customer");
    }
  }
});

test("O9 customer · cap statements and chips stay off even if the payload carries them", () => {
  // Default-deny is the server's job; the card does not rely on it alone.
  const { text } = card(F.SENTIMENT, "customer");
  assert.ok(!text.includes("Complaint Management (2.0)"),
    "a cap statement rendered on the customer card");
  assert.ok(!CELL.test(text), "a cell chip rendered on the customer card");
});
