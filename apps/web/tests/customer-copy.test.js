/* Renderer copy is content too, and it escapes every payload check.
 *
 * RC-11, gold audit of run 7968492e (2026-10-04). SELLER_VOCABULARY and
 * VENDOR_NAME scan what the PRODUCER writes; nothing scans what the RENDERER
 * writes. Four constants on the technology pages asserted things no payload
 * said, on the client's own page:
 *
 *   D-14  the register footer: "1 technologies absent across customer + data
 *         layers - the primary Zennify engagement opportunity" and "All
 *         absent-technology rows link directly to platform recommendations"
 *         — seller voice, ungrammatical, and unverified
 *   D-13  the T3 detail, when the customer read has `dma_impact` withheld by
 *         the server: "the reasoning that connects them was not written" —
 *         false; 36 of 36 were written and withheld from this view
 *   D-37  the T3 peer badge "not researched" — our workflow word, shown to
 *         the client
 *
 * This is the per-audience render scan RC-11 (e) asks for, run in-process on
 * the compiled bundle (`npm run build:proto` first).
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");

const ID = "gold-audit-shape";
const ENTITY = { id: ID, name: "Example Group", subcaps: [] };
const RUN = { id: "run" };

/* The renderer-side scan. Seller vocabulary and our own vendor name never
   reach a client page from a constant; the workflow words are our backlog,
   which no reader is party to. */
const SELLER = /\bZennify\b|engagement opportunit|primary .{0,20}opportunit|link directly to platform/i;
const WORKFLOW = /\bnot researched\b|\bqueued\b|\bpending enrichment\b/i;

function register(audience, section) {
  const { win } = H.load();
  H.installEntity(ID, { techstack: { sections: { techstack: F.sec(section || F.TECHSTACK) } } });
  return H.textOf(H.render(win.ClientTechStack, { entity: ENTITY, run: RUN }, { audience }));
}

function detail(audience, techId, section) {
  const { win } = H.load();
  H.installEntity(ID, { techstack: { sections: { techstack: F.sec(section || F.TECHSTACK) } } });
  return H.textOf(H.render(win.ClientTechStackDetail,
    { entity: ENTITY, run: RUN, techId }, { audience }));
}

test("D-14 · the register footer carries no seller voice, in either audience", () => {
  for (const audience of ["customer", "internal"]) {
    const text = register(audience);
    const hit = text.match(SELLER);
    assert.strictEqual(hit, null,
      `the ${audience} technology register printed renderer seller copy: "${hit && hit[0]}"`);
    assert.ok(!/\b1 technologies\b/.test(text), "the footer does not pluralise");
  }
});

test("D-14 · the footer states only what the register holds", () => {
  const text = register("internal");
  assert.match(text, /1 product recorded absent/,
    "the footer no longer states the register's own absent count");
});

test("D-13 · a withheld dma_impact is said to be withheld, not unwritten", () => {
  // The customer read: the server strips items[*].dma_impact for the
  // customer audience (redaction CUSTOMER_ALWAYS).
  const cust = JSON.parse(JSON.stringify(F.TECHSTACK));
  for (const it of cust.items) delete it.dma_impact;
  const text = detail("customer", "TS-099", cust);
  assert.ok(text.length > 0, "the detail page rendered nothing");
  assert.ok(!/was not written/i.test(text),
    "the customer detail says the reasoning 'was not written' — it was written and withheld");
  assert.match(text, /withheld from this view/i,
    "the customer detail does not say the reasoning is withheld from this view");
});

test("D-13 · internal, with no dma_impact, still says it is not stated", () => {
  const text = detail("internal", "TS-099");
  assert.match(text, /states no assessment impact/i);
});

test("D-37 · the peer badge never shows a workflow word", () => {
  for (const audience of ["customer", "internal"]) {
    const text = detail(audience, "TS-099");
    const hit = text.match(WORKFLOW);
    assert.strictEqual(hit, null, `${audience} detail printed "${hit && hit[0]}"`);
  }
});
