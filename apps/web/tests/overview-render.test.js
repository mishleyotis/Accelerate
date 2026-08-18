/* D1 Overview: seven defects a reader met on the page, pinned in the DOM.
 *
 * Every case here was measured on the promoted Logix run against the compiled
 * bundle (ENRICHMENT_GUIDE items O-01, O-03, O-12, O-19, O-20, O-21, O-24,
 * O-25, O-27). None of them was a data defect — all nine values were promoted,
 * served and complete, and the renderer did not read them, read them into a
 * slot too narrow to hold them, or asserted the opposite of what they said:
 *
 *   O-01/O-03  four pillar bars drawn as empty grey rails, indistinguishable
 *              from a score of zero, over a promoted ~900-character
 *              explanation of why no pillar figure resolves on that run —
 *              rendered nowhere — beside a legend promising a peer median
 *              tick that is never drawn.
 *   O-12       "No critical role gaps in the promoted roster." printed eight
 *              pixels above the card's own badge reading "1 of 4 expected".
 *   O-19       a fit score of 55.5 wrapped one character per line — `5/5./5`
 *              in a 22px column — on three of five tiles, and printed at a
 *              different precision from the same figure on D4.
 *   O-20       the whole tile body: cells addressed, weighted factors, stack
 *              context, rank rationale and seven reasoned discards, promoted
 *              on both audiences, rendered on neither.
 *   O-21       five authored challenge volleys, stripped for the customer
 *              audience by the server — which is a redaction decision about
 *              content that had no renderer at all.
 *   O-24/O-25  evidence coverage and 16 complete ceiling rows rendering on NO
 *              page of the application, in either audience.
 *   O-27       a section's own reasoning trace, on twelve of twelve sections,
 *              reaching no reader.
 *
 * Driven through the same harness as render-boundary.test.js: the COMPILED
 * bundle, the real script list, real payload reads. Two of these assertions —
 * the score column's geometry and the pillar rail — cannot be made against
 * innerText at all, which is exactly how they survived: they are facts about
 * layout, so they are measured with getBoundingClientRect.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const { resolvePlaywright, startServer, settle, selectAudience } =
  require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";

const pw = resolvePlaywright();
const CHROME = process.env.CHROMIUM_PATH
  || (fs.existsSync("/opt/pw-browsers")
      ? fs.readdirSync("/opt/pw-browsers").filter((d) => d.startsWith("chromium"))
          .map((d) => `/opt/pw-browsers/${d}/chrome-linux/chrome`)
          .find((p) => fs.existsSync(p))
      : null);
const skip = (!pw || !CHROME) ? "playwright-core or Chromium is not resolvable here" : false;

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Chicago, IL",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.9, pillar_scores: {}, oss: {}, footprint: ["IL"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.9,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data, extra) => ({
  data, e_ids: [], produced_at: "2026-08-01T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null, ...extra,
});

const DISCLOSURE =
  "No peer figure is served at this grain: the assessment names a locked "
  + "five-member cohort and records peer scoring as a pending phase. No pillar "
  + "figure is served here either — this run's ingestion carried no pillar "
  + "rollup row, so there is no served row a pillar figure could be checked "
  + "against.";

const TRACE = {
  hypothesis: "The hypothesis this section was written from.",
  counter: "The strongest objection the producer could put against it.",
  domain_test: "Chief executive, chief information officer, chief operating "
    + "officer and chief information security officer are the accountability "
    + "set for a credit union of this size.",
  probes_run: ["A route that was tried and what it returned."],
  verdict: "ACCEPT", confidence: "MEDIUM",
};

/* One promoted overview. `variant` swaps exactly one thing, so a failure names
   the state that broke rather than the fixture. */
function overview(variant, audience) {
  const cust = audience === "customer";
  const pillars = variant === "scored"
    ? [{ pillar_id: "P1", score: 1.5963, peer_median: 1.4, basis: "computed_mean_of_subcaps", n: 187 },
       { pillar_id: "P2", score: 1.5151, basis: "computed_mean_of_subcaps", n: 232 },
       { pillar_id: "P3", score: 1.7478, basis: "computed_mean_of_subcaps", n: 115 },
       { pillar_id: "P4", score: 1.4327, basis: "computed_mean_of_subcaps", n: 171 }]
    : ["P1", "P2", "P3", "P4"].map((id) => ({
        pillar_id: id, score: null, peer_median: null, peer_n: null,
        delta: null, direction: null, peer_basis: "cannot_estimate",
        proxy_disclosure: DISCLOSURE,
      }));

  const roster = variant === "full-roster"
    ? [{ name: "A One", title: "President and Chief Executive Officer", domain: "enterprise", relevance_note: "n" },
       { name: "B Two", title: "Chief Information Officer", domain: "technology", relevance_note: "n" },
       { name: "C Three", title: "Chief Operating Officer", domain: "operations", relevance_note: "n" },
       { name: "D Four", title: "Chief Information Security Officer", domain: "security", relevance_note: "n" }]
    : [{ name: "Ana Fonseca", title: "President and Chief Executive Officer",
         domain: "enterprise", tenure_months: 91, relevance_note: "Owns the investment." }];

  const sections = {};
  sections.scores = sec({
    composite: 1.59, framing: "A framing sentence the run states.",
    pillars, ...(cust ? {} : { r_layer: TRACE }),
  });
  sections.firmographics = sec({ fields: [
    { field: "total_assets", value: "9687804914", unit: "USD" },
  ] });
  sections.leadership = sec({
    roster,
    ...(cust ? {} : { r_layer: TRACE }),
    enrichment_status: {
      required: true, sources: ["clay"], count: roster.length, thin_below: 4,
      thin: roster.length < 4, ran: true, enriched_rows: roster.length,
      thin_reason: "the contact-enrichment ladder established a route for fewer than half the named leaders",
      closes_with: "a Clay contact search against the entity's own domain",
    },
  });
  sections.exec_summary = sec({
    situation: "The situation.", complication: "The complication.",
    question: "The question?", answer: "The answer.",
    sequencing_rationale: "Model governance comes before the models.",
    ...(cust ? {} : {
      r_layer: TRACE,
      storyline_challenge: { volleys: [
        { volley: 1, challenger: "client_executive", outcome: "changed",
          challenge: "You are telling her the threshold is not coming.",
          answer: "The proposition is a second use for funded capacity.",
          changed: "The framing sentence was rewritten." },
        { volley: 2, challenger: "finance", outcome: "held",
          challenge: "Show me the return.",
          answer: "Neither item asks for new money.", changed: null },
      ] },
    }),
  });
  sections.opportunity = sec({
    tiles: [
      { platform: "Salesforce Agentforce Service Agent with Experience Cloud",
        composite: 55.5, rank: 3, relevance: 0.7,
        headline: "A service agent that answers from the record.",
        their_stack_context: "Their reporting layer is described by their own BI manager.",
        rank_rationale: "Rank three on the arithmetic and on sequence alike.",
        factors: [{ name: "Addressable gap depth", value: 11, weight: 2.5, contribution: 27.5 },
                  { name: "Sub-vertical relevance", value: 0.85, weight: 30, contribution: 25.5 },
                  { name: "Substrate already in place", value: 0.7, weight: 20, contribution: 14 }],
        addressable_cells: [
          { subcap_id: "P4C2.5.1", name: "Model Inventory & Documentation",
            current: 1.5, gap: 1.5, peer: null,
            feature_that_addresses_it: "A catalogue-backed registry." },
        ] },
      { platform: "Salesforce Data Cloud", composite: 66.75, rank: 2,
        headline: "One member profile.", factors: [], addressable_cells: [] },
    ],
    discarded: [{ platform: "nCino", reason: "Origination is the one layer this run can say nothing about." }],
    ...(cust ? {} : { r_layer: TRACE }),
  });
  sections.evidence_coverage = sec({
    overall_pct: 33.0, gate_pct: 80.0,
    per_pillar: [
      { pillar_id: "P1", pct: 35.3, cells_total: 187, cells_covered: 66, below_gate: true },
      { pillar_id: "P2", pct: 24.6, cells_total: 232, cells_covered: 57, below_gate: true },
      { pillar_id: "P3", pct: 53.9, cells_total: 115, cells_covered: 62, below_gate: true },
      { pillar_id: "P4", pct: 28.1, cells_total: 171, cells_covered: 48, below_gate: true },
    ],
    denominator_definition: "Share of the 705 cells that carry at least one linked item.",
    ...(cust ? {} : { r_layer: TRACE }),
  });
  // Ceilings are internal: the server serves `data: null` to the customer.
  sections.ceilings = cust ? sec(null) : sec({
    rows: [{ category_id: "P1C1", category_name: "Digital Strategy", ceiling: "M3",
             uncertainty_band: 0.4, rationale: "A multi-year build is evidenced.",
             limiting_absence: "A dated digital strategy document.",
             urf_modifiers: ["URF-01"], claim_label: "CEILING_ESTIMATE",
             confidence: "MEDIUM", e_ids: [] }],
    r_layer: TRACE,
  });
  return { entity: { display_id: ENTITY, name: "Test Credit Union" },
           run: { run_id: RUN_ID, promoted_at: "2026-08-01T00:00:00Z",
                  completed_at: "2026-08-01T00:00:00Z", evidence_mode: "PUBLIC" },
           audience: audience || "internal", sections };
}

test("D1 overview renders what the run promoted", { skip, concurrency: false }, async (t) => {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  const open = async ({ variant, audience }) => {
    const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop();
      if (which !== "overview") {
        return route.fulfill({ status: 404, contentType: "application/json",
                               body: '{"error":"not_found"}' });
      }
      await route.fulfill({ status: 200, contentType: "application/json",
                            body: JSON.stringify(overview(variant, audience)) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/overview`, { waitUntil: "domcontentloaded" });
    await settle(page);
    // The view defaults to the CUSTOMER body now, so a subtest asserting
    // internal-only content has to ask for the internal one — which is what
    // an analyst does, and therefore what the test should model.
    await selectAudience(page, audience === "customer" ? "customer" : "internal");
    return { page, errors };
  };

  try {
    await t.test("O-01/O-03 · an unserved pillar renders its reason, not an empty rail", async () => {
      const { page, errors } = await open({ variant: "unscored" });
      const text = await page.evaluate(() => document.body.innerText || "");

      // The promoted explanation is on the page — ONCE. It is identical on all
      // four rows and printing one paragraph four times is noise, not
      // disclosure.
      const hits = text.split("No peer figure is served at this grain").length - 1;
      assert.strictEqual(hits, 1,
        `the proxy_disclosure should render exactly once under the bars, found ${hits}`);

      // No 8px grey rail on a row with no figure. A rail with a zero-width
      // fill is read as a score of zero by everyone who has not seen the
      // payload, and this run scores no pillar — it does not score them nought.
      const rails = await page.$$eval(".pbar .pbar-track", (els) => els.length);
      assert.strictEqual(rails, 0,
        "an unscored pillar still drew a bar track, which reads as a score of zero");
      const said = await page.$$eval("[data-no-figure]", (els) => els.map((e) => e.getAttribute("data-no-figure")));
      assert.deepStrictEqual(said, ["P1", "P2", "P3", "P4"],
        "every unserved pillar must say so in the slot the bar would have used");

      // And the legend promises no mark that is never drawn.
      assert.ok(!text.includes("Peer median"),
        "the legend still promises a peer median with no tick anywhere on the chart");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("O-01 · a served pillar figure renders as a bar with its number", async () => {
      const { page, errors } = await open({ variant: "scored" });
      const text = await page.evaluate(() => document.body.innerText || "");
      const bars = await page.$$eval(".pbar .pbar-fill",
        (els) => els.map((e) => e.getBoundingClientRect().width));
      assert.strictEqual(bars.length, 4, "four served pillar scores must draw four fills");
      assert.ok(bars.every((w) => w > 0), `a served score drew a zero-width fill: ${bars}`);
      for (const n of ["1.6", "1.5", "1.7", "1.4"]) {
        assert.ok(text.includes(n), `pillar figure ${n} is missing from the bars`);
      }
      // One pillar states a peer median; the legend may name that mark now.
      assert.ok(text.includes("Peer median"),
        "a drawn peer tick must be named in the legend");
      assert.ok(!text.includes("No pillar figure is served on this run"),
        "the no-figure line must not render beside figures that ARE served");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("O-12 · the roster footer is derived from the expected seat count", async () => {
      const short = await open({ variant: "unscored" });
      const t1 = await short.page.evaluate(() => document.body.innerText || "");
      assert.ok(!t1.includes("No critical role gaps in the promoted roster"),
        "a roster of 1 against an expected 4 must not be given a clean bill of health");
      assert.ok(/1 of the 4 leadership seats/.test(t1),
        `the footer must name the shortfall it was derived from:\n${t1.slice(0, 600)}`);
      await short.page.close();

      const full = await open({ variant: "full-roster" });
      const t2 = await full.page.evaluate(() => document.body.innerText || "");
      assert.ok(t2.includes("No critical role gaps in the promoted roster"),
        "a roster that MEETS its expected count may state so — the claim is not banned, it is earned");
      await full.page.close();
    });

    await t.test("O-19 · the fit score occupies one line and one precision", async () => {
      const { page, errors } = await open({ variant: "unscored" });
      const boxes = await page.$$eval(".g5 .card-tile", (tiles) => tiles.map((t) => {
        const el = [...t.querySelectorAll("div")]
          .find((d) => /^\d+(\.\d+)?$/.test((d.textContent || "").trim())
                       && parseFloat(getComputedStyle(d).fontSize) > 18);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { text: el.textContent.trim(), w: Math.round(r.width),
                 h: Math.round(r.height), lh: parseFloat(getComputedStyle(el).fontSize) };
      }).filter(Boolean));
      assert.ok(boxes.length >= 2, `expected a score on every tile, got ${JSON.stringify(boxes)}`);
      for (const b of boxes) {
        // Measured before the fix: w=22 h=72 for "55.5" — four glyphs stacked
        // in a 24px line slot. One line means the box is no taller than about
        // one-and-a-bit times the font size.
        assert.ok(b.h <= b.lh * 1.6,
          `the fit score "${b.text}" is ${b.h}px tall in a ${b.lh}px slot — it is wrapping per character`);
        assert.ok(b.w >= b.text.length * 5,
          `the fit score "${b.text}" is only ${b.w}px wide — the column collapsed`);
      }
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(!text.includes("66.75"),
        "the composite must print at the one decimal D4 uses, not at four significant figures");
      assert.ok(text.includes("66.8"), "the composite is missing at one decimal");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("O-20 · the tile body and the reasoned discards render", async () => {
      const { page, errors } = await open({ variant: "unscored" });
      let text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes("Considered and set aside"),
        "the platforms that were considered and not ranked are missing");
      assert.ok(text.includes("Origination is the one layer"),
        "a discard rendered without the reason it was discarded for");
      assert.ok(text.includes("Cells it addresses"),
        "the tile face does not say how much of the assessment the platform touches");

      await page.evaluate(() => {
        const b = [...document.querySelectorAll("button")]
          .find((n) => (n.textContent || "").includes("Cells it addresses"));
        if (b) b.click();
      });
      await settle(page);
      text = await page.evaluate(() => document.body.innerText || "");
      for (const needle of ["How the score is made", "Against their stack",
                            "Why it ranks here", "Model Inventory & Documentation",
                            "P4C2.5.1"]) {
        assert.ok(text.includes(needle), `the tile body is missing "${needle}"`);
      }
      /* The factor bars rank the same way the numbers beside them do. Drawn as
         `value * 10` a gap-depth count of 11 filled half the track while the
         larger contribution drew a sliver, because a count and a fraction are
         not on one scale — only the contributions are. */
      const bars = await page.evaluate(() => {
        const head = [...document.querySelectorAll("div")]
          .find((d) => (d.textContent || "").trim() === "How the score is made");
        const grid = head && head.parentElement;
        return [...grid.querySelectorAll(":scope > div")].map((row) => {
          const track = row.children[1];
          const fill = track && track.firstElementChild;
          const val = row.children[2];
          return fill ? { w: fill.getBoundingClientRect().width,
                          n: parseFloat((val.textContent || "").replace(/[^\d.]/g, "")) } : null;
        }).filter(Boolean);
      });
      assert.strictEqual(bars.length, 3, `expected three weighted factors, got ${bars.length}`);
      const byBar = bars.slice().sort((a, b) => b.w - a.w).map((b) => b.n);
      const byNum = bars.slice().sort((a, b) => b.n - a.n).map((b) => b.n);
      assert.deepStrictEqual(byBar, byNum,
        `the factor bars rank differently from the contributions beside them: ${JSON.stringify(bars)}`);
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("O-21/O-27 · the volleys and the section traces render, internal only", async () => {
      const { page, errors } = await open({ variant: "unscored" });
      let text = await page.evaluate(() => document.body.innerText || "");
      // Collapsed, not absent: the control is on the page for every section
      // that promoted a trace.
      const traces = await page.$$eval("[data-trace]",
        (els) => els.map((e) => e.getAttribute("data-trace")).sort());
      for (const want of ["overview.scores", "overview.leadership",
                          "overview.exec_summary", "overview.opportunity",
                          "overview.evidence_coverage", "overview.ceilings"]) {
        assert.ok(traces.includes(want), `no reasoning trace mounted for ${want} — got ${traces}`);
      }
      assert.ok(text.includes("Self-check · ACCEPT"),
        "the producer's own verdict must be labelled as a verdict, not left as a bare pill");

      await page.evaluate(() => {
        [...document.querySelectorAll("[data-trace] button")].forEach((b) => b.click());
      });
      await settle(page);
      text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes("chief information security officer"),
        "the leadership trace names the seats the roster could not establish, and it did not render");
      assert.ok(text.includes("The strongest objection the producer could put against it"),
        "a section's counter-case did not render");

      await page.evaluate(() => {
        const b = [...document.querySelectorAll("button")]
          .find((n) => (n.textContent || "").includes("Read full"));
        if (b) b.click();
      });
      await settle(page);
      text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes("2 volleys"), "the storyline challenge did not render");
      assert.ok(text.includes("Story held") && text.includes("Story changed"),
        "a volley rendered without saying what the storyline did with it");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("O-24/O-25 · coverage and ceilings render, ceilings internal only", async () => {
      const { page, errors } = await open({ variant: "unscored" });
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes("Evidence coverage"), "the coverage card is not mounted on any page");
      assert.ok(text.includes("33% overall"), "the overall coverage percentage did not render");
      assert.ok(text.includes("80% hard gate"), "the gate the coverage is measured against did not render");
      assert.ok(text.includes("Capability ceiling"), "the ceilings card is not mounted on any page");
      assert.ok(text.includes("Digital Strategy"), "a ceiling row rendered without its category");
      /* The `ceiling` vocabulary is the assessment's M1–M5 LEVEL scale, not
         the four-value band_t. It resolves to a level and the level goes
         through the one colour resolver — a row that renders neither figure
         nor token is the passthrough this guards against. */
      assert.ok(/M3/.test(text) && /3\.0/.test(text),
        "the stated ceiling token and the level it resolves to must both render");
      assert.ok(!/M5|Transformational/.test(text),
        "M5/Transformational must not exist in code, enum or prose");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });

    await t.test("the customer audience gets none of the internal content", async () => {
      const { page, errors } = await open({ variant: "unscored", audience: "customer" });
      // Drive the app's OWN audience toggle: the payload choice and the app's
      // audience state are two different things, and the redaction being
      // tested is the renderer's.
      await page.evaluate(() => {
        const b = [...document.querySelectorAll("button")]
          .find((n) => (n.textContent || "").trim().toLowerCase() === "customer");
        if (b) b.click();
      });
      await settle(page);
      const text = await page.evaluate(() => document.body.innerText || "");
      for (const banned of ["REASONING TRACE", "Self-check", "STORYLINE CHALLENGE",
                            "Capability ceiling"]) {
        assert.ok(!text.includes(banned),
          `"${banned}" is internal-only and reached the customer audience`);
      }
      // …and still gets what the producer DID promote to it.
      assert.ok(text.includes("No peer figure is served at this grain"),
        "the customer gets four blank bars and no reason for them");
      assert.ok(text.includes("Evidence coverage"),
        "coverage is promoted to this audience and must render");
      assert.ok(text.includes("Cells it addresses"),
        "the opportunity tile body is promoted to this audience and must render");
      assert.deepStrictEqual(errors, [], errors.join("\n"));
      await page.close();
    });
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
});

/* The two cards were not broken — they had no CALL SITE. That is the failure
   mode this file exists for, and it is invisible to any test that renders a
   component directly, so it is asserted against the shipped bundle. */
test("the coverage and ceiling surfaces are mounted by a page", () => {
  const js = path.join(__dirname, "..", "public", "proto", "js");
  const src = fs.readdirSync(js).filter((f) => f.endsWith(".js") && f !== "cards-data-driven.js")
    .map((f) => fs.readFileSync(path.join(js, f), "utf8")).join("\n");
  for (const [name, why] of [
    ["CoverageByPillarCard", "evidence_coverage: 5 percentages promoted and served"],
    ["OvCeilingCard", "ceilings: 16 rows with zero nulls on ten columns"],
  ]) {
    assert.ok(new RegExp(`createElement\\(${name}`).test(src),
      `${name} has no call site outside the file that defines it — ${why} `
      + `would render on no page of the application.`);
  }
});
