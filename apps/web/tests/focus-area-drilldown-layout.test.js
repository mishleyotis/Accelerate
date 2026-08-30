/* The focus-area drilldown: nothing overlaps, nothing escapes its card.
 *
 * Reported 2026-08-22 with screenshots of the promoted T. Rowe Price page:
 * "overlapping text on the focus area heatmap page". The SOURCE chip was
 * painting on top of the citation beside it, rendering as
 *
 *     "SOURCEAI section (after the ETF/SMA platform-growth discussion…"
 *     "SOURCE T. Rowe Price press release — …"
 *
 * The cause is the same one that broke the acquisition row, one card over:
 * `.b` is `white-space: nowrap` with the DEFAULT `flex-shrink: 1`. Under width
 * pressure the chip's BOX shrinks while its text does not, so the text spills
 * out of its own box and paints over the neighbour. The citation makes it
 * worse than most: it is `document · p.N · filename` joined, so it is long by
 * construction and puts the row under pressure at every viewport.
 *
 * TWO DIFFERENT MEASUREMENTS, because these are two different failures:
 *
 *   CLIPPING  the chip's own text wider than the chip's own box. Reverting
 *             the fix reproduces the defect at 8px / 15px / 19px / 24px
 *             across the four widths, and THIS is the measurement that
 *             catches it.
 *   OVERLAP   the two boxes intersect. Worth asserting and worth knowing it
 *             is NOT sufficient on its own: with the fix reverted the
 *             intersection stays 0px², because overflowing text paints
 *             outside its box without widening it. A box-intersection test
 *             alone would have called the reported bug clean.
 *   OVERFLOW  content wider than its container, which is what the same root
 *             cause did to the acquisition card one page over.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-asset-manager";
const RUN_ID = "DMA-ASM-TAM-20260801-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

/* The real citation from the promoted run — document, then the annotation the
   producer appended, then the URL. A shorter stand-in stops reproducing the
   pressure that made the chip shrink. */
const SOURCE_DOC = "T. Rowe Price Group Q2 2026 Earnings Conference Call "
  + "Transcript (Motley Fool transcript of the 2026-07-31 call) (Prepared "
  + "remarks — Rob Sharps, AI section (after the ETF/SMA platform-growth "
  + "discussion, before the governance/upskilling discussion))";
const SOURCE_FILE = "https://www.fool.com/earnings/call-transcripts/2026/08/07/"
  + "t-rowe-price-trow-q2-2026-earnings-call-transcript/";

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { ASSET_MANAGER: "Asset manager" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Asset Manager",
    subvertical: "ASSET_MANAGER", size_tier: "LARGE", hq: "Baltimore, MD",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 3.1, pillar_scores: {}, oss: {}, footprint: ["MD"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 3.1,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const ENV = {
  produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
  e_ids: ["E-CC-001"], internal_only: [],
  narrative_thread: "The line through this page, written last.",
};

function heatmapPage() {
  return {
    sections: {
      /* The H1 contract's own key names — `name`, `currency_note`,
         `verbatim_quote`, `source_document`, `involved_subcap_ids`. The
         adapter reads these and nothing else; a payload keyed any other way
         renders a card with an empty name and this test would be measuring
         a blank box. */
      focus_areas: { data: { ...ENV, focus_areas: [{
        fa_id: "FA-2",
        name: "Scale artificial intelligence (AI) from isolated pilots into "
            + "governed, end-to-end business workflows",
        currency_note: "Stated 2026-07-31 on the Q2 2026 earnings call, days "
                     + "before this run's 2026-08-10 reference date.",
        currency_status: "CURRENT",
        source_document: SOURCE_DOC,
        source_page: null,
        source_filename: SOURCE_FILE,
        verbatim_quote: "We are moving beyond isolated use cases and tools "
          + "and embedding AI directly into end-to-end business workflows "
          + "with more than 130 AI solutions deployed across the firm.",
        involved_subcap_ids: ["P4C1.1.1", "P4C1.1.2"],
        entity_score: 2.1, peer_score: 2.6, delta: -0.5,
        e_ids: ["E-CC-001"],
      }] } },
      workbook_scores: { data: { ...ENV, cells: [] } },
      cell_evidence: { data: { ...ENV, cells: [] } },
      evidence: { data: { ...ENV, items: [] } },
      alerts: { data: { ...ENV, alerts: [] } },
      safeguard_gates: { data: { ...ENV, gates: [], caps: [] } },
      evidence_age: { data: { ...ENV, buckets: [] } },
      cohort_patterns: { data: { ...ENV, patterns: [], threshold_pct: 60 } },
      value_chain: { data: { ...ENV, stages: [] } },
    },
  };
}

const WIDTHS = [1512, 1180, 900, 760];

async function inspect(width) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width, height: 1400 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop().split("?")[0];
      const body = which === "heatmap" ? heatmapPage() : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/heatmap`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    await settle(page);
    /* Into the focus-area drilldown: the reported view. Two clicks — the
       view switcher, then the card. Both selectors are the page's own
       structure (`.toggle-row button`, `.fa-card`), so a rename breaks this
       test loudly rather than leaving it measuring the wrong element. */
    const switched = await page.evaluate(() => {
      const hit = [...document.querySelectorAll(".toggle-row button")]
        .find((n) => /Focus areas/i.test(n.textContent || ""));
      if (!hit) return false;
      hit.click();
      return true;
    });
    if (!switched) return { found: false, why: "no 'Focus areas' view switcher" };
    await settle(page);
    const opened = await page.evaluate(() => {
      const card = document.querySelector(".fa-card");
      if (!card) return false;
      card.click();
      return true;
    });
    if (!opened) return { found: false, why: "no .fa-card rendered to drill into" };
    await settle(page);

    return await page.evaluate(() => {
      const chip = [...document.querySelectorAll("span")]
        .find((s) => (s.textContent || "").trim() === "SOURCE");
      if (!chip) return { found: false };
      const row = chip.parentElement;
      const cite = [...row.children].find((n) => n !== chip);
      const a = chip.getBoundingClientRect();
      const b = cite ? cite.getBoundingClientRect() : null;
      // Does the chip's own TEXT fit inside the chip's box? This is the
      // failure: nowrap text in a shrunk flex item.
      const chipClipped = chip.scrollWidth - chip.clientWidth;
      const overlap = b
        ? Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
          * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
        : 0;
      /* Overflow, counting only what a reader could actually lose.
         The hero header deliberately bleeds a decorative illustration
         (`right: -60`) behind `overflow: hidden` — it is clipped, invisible
         and intentional, and counting it would make this test red forever on
         correct output. So an element is skipped when the thing sticking out
         of it is an absolutely-positioned decoration rather than content in
         the flow. Anything that carries text is still measured. */
      const escapes = (n) => {
        const over = n.scrollWidth - n.clientWidth;
        if (over <= 1) return null;
        const decorative = [...n.children].every((c) => {
          const cs = getComputedStyle(c);
          if (cs.position === "absolute" || cs.position === "fixed") return true;
          return c.getBoundingClientRect().right
                 <= n.getBoundingClientRect().right + 1;
        });
        if (decorative) return null;
        return { over, tag: n.tagName, text: (n.textContent || "").slice(0, 60) };
      };
      const card = chip.closest(".card") || document.body;
      const worst = [card, ...card.querySelectorAll("*")].reduce((acc, n) => {
        const e = escapes(n);
        return e && e.over > acc.over ? e : acc;
      }, { over: 0, tag: null, text: "" });
      return {
        found: true, chipClipped, overlap, worst,
        citeText: cite ? (cite.textContent || "").slice(0, 40) : null,
        docOverflow: document.documentElement.scrollWidth
                     - document.documentElement.clientWidth,
      };
    });
  } finally { await browser.close(); server.close(); }
}

for (const width of WIDTHS) {
  test(`focus-area drilldown · SOURCE does not overlap its citation at ${width}px`,
       { skip }, async () => {
    const r = await inspect(width);
    assert.ok(r.found,
      `the SOURCE chip did not render — ${r.why || "the drilldown did not open"}`);
    assert.strictEqual(r.chipClipped, 0,
      `the SOURCE chip's text overflows its own box by ${r.chipClipped}px at `
      + `${width}px, which is what paints it over the citation `
      + `(${JSON.stringify(r.citeText)})`);
    assert.strictEqual(r.overlap, 0,
      `the SOURCE chip and its citation overlap by ${r.overlap}px² at ${width}px`);
  });

  test(`focus-area drilldown · nothing escapes the card at ${width}px`,
       { skip }, async () => {
    const r = await inspect(width);
    assert.ok(r.found, r.why || "the drilldown did not open");
    assert.ok(r.worst.over <= 1,
      `<${r.worst.tag}> overflows by ${r.worst.over}px at ${width}px — `
      + `${JSON.stringify(r.worst.text)}`);
    assert.ok(r.docOverflow <= 1,
      `the page scrolls sideways by ${r.docOverflow}px at ${width}px`);
  });
}
