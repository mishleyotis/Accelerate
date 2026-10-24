/* O9 customer · the reduced card renders the body redaction ACTUALLY serves.
 *
 * Owner decision 1 (2026-10-04): the customer gets ratings bars and themes,
 * with no cell codes, internal sources, cap vocabulary or r_layer. The card
 * and the server projection were changed in two separate round-1 streams.
 * The card's own tests rendered `customerCopy`, a hand-built imitation of
 * the customer body. This suite renders the bodies `redact_section`
 * returns. They are committed in fixtures/projections/sentiment_customer.json,
 * and apps/api tests/test_sentiment_projection_fixture.py fails if the
 * projection drifts from them. So the card is always tested against the
 * real wire shape.
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");
const P = require(path.join(__dirname, "..", "..", "..", "fixtures",
                            "projections", "sentiment_customer.json"));

const ID = "projection-shape";
const CELL = /\bP[1-4]C\d(?:\.\d+){0,2}\b/;

function card(sentiment, audience) {
  const { win } = H.load();
  H.installEntity(ID, { overview: { sections: { sentiment: F.sec(sentiment) } } });
  const html = H.render(win.SentimentCard, { entity: { id: ID }, audience },
                        { audience });
  return { html, text: H.textOf(html) };
}

for (const [name, c] of Object.entries(P.cases)) {
  test(`O9 customer · ${name}: every served theme renders, nothing else of the analyst's`, () => {
    const cust = c.customer;
    assert.ok(cust, `${name}: the projection withheld sentiment whole`);
    const { html, text } = card(cust, "customer");
    assert.ok(!/Not shown to this audience|No sentiment promoted/.test(text),
      `${name}: the card rendered an absence over a served reduced card`);
    const rows = (html.match(/data-sentiment-theme=/g) || []).length;
    assert.strictEqual(rows, cust.themes.length,
      `${name}: ${cust.themes.length} themes served, ${rows} rendered`);
    for (const t of cust.themes) {
      assert.ok(text.includes(t.theme), `${name}: served theme missing: ${t.theme}`);
    }
    // What the projection took out is not put back by the card…
    const servedThemes = new Set(cust.themes.map((t) => t.theme));
    for (const t of c.input.themes.filter((x) => !servedThemes.has(x.theme))) {
      assert.ok(!text.includes(t.theme), `${name}: a withheld theme rendered: ${t.theme}`);
    }
    // …and the analyst's half reaches no customer.
    assert.ok(!CELL.test(text), `${name}: a cell code rendered: ${(text.match(CELL) || [])[0]}`);
    assert.ok(!/\bcaps?\b|\blifts?\b|uncertainty|ceiling/i.test(text),
      `${name}: cap vocabulary rendered`);
    assert.ok(!text.includes(c.input.narrative_thread), `${name}: narrative rendered`);
    assert.ok(!text.includes(c.input.gap_analysis.b2b_b2c), `${name}: gap analysis rendered`);
    assert.ok(!/B2B\/B2C gap/.test(text), `${name}: the gap chip lit for the customer`);
  });

  test(`O9 customer · ${name}: every served bar renders its rating, and only those`, () => {
    const cust = c.customer;
    const { text } = card(cust, "customer");
    const { win } = H.load();
    for (const b of cust.bars || []) {
      assert.ok(text.includes(b.source), `${name}: served bar missing: ${b.source}`);
      assert.ok(text.includes(win.fx(b.rating, 1)),
        `${name}: served bar's rating ${b.rating} did not render`);
    }
    const served = new Set((cust.bars || []).map((b) => b.source));
    for (const b of c.input.bars.filter((x) => !served.has(x.source))) {
      assert.ok(!text.includes(b.source), `${name}: a withheld bar rendered: ${b.source}`);
    }
    // An audience with served themes never reads as having nothing.
    for (const aud of new Set(cust.themes.map((t) => t.audience))) {
      assert.ok(!(new RegExp(`${aud}\\s+No rating or theme`, "i")).test(text),
        `${name}: the ${aud} group printed "No rating or theme" over served themes`);
    }
  });
}

test("O9 internal · the same input keeps the analyst's card", () => {
  const input = P.cases.decision_1.input;
  const { html, text } = card(input, "internal");
  assert.strictEqual((html.match(/data-sentiment-theme=/g) || []).length,
                     input.themes.length);
  assert.ok(text.includes(input.narrative_thread));
  assert.ok(/B2B\/B2C gap/.test(text));
});
