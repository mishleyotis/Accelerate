/* The surface contracts six reader reports turned into defects.
 *
 * Run with `npm run test:web`. Half of these are pure-function assertions on
 * the compiled adapter; half drive the compiled bundle in a browser through
 * tests/proto-page-harness.js, with a payload shaped like production's.
 *
 * Every case here exists because the page said something the payload did not:
 *
 *  1  D5's filter chips read Positive/Neutral/Negative, which is a mood. The
 *     field means the direction an event moved the ASSESSED position of the
 *     cells it names, so a merger that has converted nothing is NEUTRAL and
 *     reads as an insult. Stored values do not move; the words do.
 *  2  `maturity_effect` arrives as "TOKEN — one clause" and was printed whole
 *     inside a badge.
 *  3  `arc_shape` has five contract words and this run serves a sentence. It
 *     must print, and must not be dressed as one of the five.
 *  4  The PRIMARY GAP LAYERS tile located instead of filtering.
 *  5  A platform tile click left the stair-step ladder and the roadmap
 *     byte-identical.
 *  6  The reasoning trace's ACCEPT badge is the producer's self-check and read
 *     as a control with no counterpart.
 *  7  Thought leadership had to hold three to five entries, and CONTRADICTS —
 *     the contract's most valuable row — was adapted and never rendered.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const { JS_DIR, resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium } =
  require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";

/* ── the adapter, loaded the way the browser loads it ─────────────────── */

function loadAdapter() {
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  global.window = {};
  require(path.join(JS_DIR, "data.js"));
  require(path.join(JS_DIR, "live-adapter.js"));
  return global.window;
}

test("maturity_effect splits into a token and a reason, and never renders whole", () => {
  const { splitMaturityEffect } = loadAdapter();

  // Production's shape, verbatim from the served run.
  const real = splitMaturityEffect(
    "NEUTRAL — It adds a second member book and a second set of source systems "
    + "to integrate, and takes no capability away, so the two integration cells "
    + "score what they scored before it.");
  assert.strictEqual(real.token, "NEUTRAL");
  assert.ok(real.reason.startsWith("It adds a second member book"),
            "the clause is the reason, without its enum prefix");
  assert.ok(!/NEUTRAL/.test(real.reason), "the enum must not survive into the body");

  // A bare token — the acquisitions row writes it this way and puts its clause
  // in `effect_note`.
  assert.deepStrictEqual(splitMaturityEffect("NEUTRAL"),
                         { token: "NEUTRAL", reason: null });

  // No prefix at all: the whole string is the reason and the badge has to fall
  // back to the event's own direction.
  const bare = splitMaturityEffect("The integration layer is unchanged by it.");
  assert.strictEqual(bare.token, null);
  assert.strictEqual(bare.reason, "The integration layer is unchanged by it.");

  // A sentence that merely OPENS with a word and a dash is not a token. This
  // is the case that would otherwise put "The merger" in a badge.
  const prose = splitMaturityEffect("The merger — which has not closed — changes nothing.");
  assert.strictEqual(prose.token, null);
  assert.ok(prose.reason.startsWith("The merger"));

  // Absent is absent, never a sentinel (invariant 9).
  assert.deepStrictEqual(splitMaturityEffect(null), { token: null, reason: null });
  assert.deepStrictEqual(splitMaturityEffect(""), { token: null, reason: null });
});

/* BUILD OWNER'S ADJUDICATION, 2026-08-14. This test previously pinned
   Advanced / Constrained — a relabel an earlier session made to stop a reader
   asking "why is a merger a negative event?". The owner reviewed the live page
   and reversed it: the timeline segments Positive · Negative · Neutral.

   The assertions BELOW the labels are the ones that matter and they do not
   move: the stored vocabulary is the contract, and only the displayed word
   ever changed. That separation is why this reversal cost one map and three
   test lines rather than a migration. */
test("the three stored signals are labelled on the axis they name", () => {
  const { MATURITY_EFFECT_LABEL } = loadAdapter();
  assert.strictEqual(MATURITY_EFFECT_LABEL.positive, "Positive");
  assert.strictEqual(MATURITY_EFFECT_LABEL.neutral, "Neutral");
  assert.strictEqual(MATURITY_EFFECT_LABEL.negative, "Negative");
  // The producer's own token translates to the SAME vocabulary, so a badge
  // and a chip on one screen cannot name one axis two ways.
  const { effectTokenLabel } = global.window;
  assert.strictEqual(effectTokenLabel("ADVANCED"), "POSITIVE");
  assert.strictEqual(effectTokenLabel("CONSTRAINED"), "NEGATIVE");
  assert.strictEqual(effectTokenLabel("NEUTRAL"), "NEUTRAL");
  // An unknown token is printed as the producer wrote it, never dropped.
  assert.strictEqual(effectTokenLabel("SOMETHING_ELSE"), "SOMETHING_ELSE");
  // The stored vocabulary is a contract and does not move with the labels.
  const { peerOfSignal } = global.window;
  assert.strictEqual(peerOfSignal("POSITIVE"), "positive");
  assert.strictEqual(peerOfSignal("NEGATIVE"), "negative");
  assert.strictEqual(peerOfSignal("a whole sentence"), "unclassified");
});

test("arc_shape prints what is there, and says when it is off-vocabulary", () => {
  const { arcShapeOf, ARC_SHAPES } = loadAdapter();
  assert.deepStrictEqual(ARC_SHAPES,
    ["STEADY_INVESTMENT", "STOP_START", "POST_EVENT_CATCHUP",
     "LEGACY_ANCHORED", "RECENT_ACCELERATION"],
    "the five contract words, from the Surface Specification's D5 step 4");

  const known = arcShapeOf("LEGACY_ANCHORED");
  assert.strictEqual(known.in_vocabulary, true);
  assert.strictEqual(known.label, "legacy anchored");

  // What production actually serves today.
  const off = arcShapeOf("strategy-first, substrate-later");
  assert.strictEqual(off.in_vocabulary, false);
  assert.strictEqual(off.label, "strategy-first, substrate-later",
                     "printed as promoted — never dropped, never normalised");
  assert.strictEqual(arcShapeOf(null), null);
  assert.strictEqual(arcShapeOf(""), null);
});

test("adaptTimeline carries the split, not the blob", () => {
  const { adaptTimeline } = loadAdapter();
  const [e] = adaptTimeline({ events: [{
    event_date: "2026-06-01", title: "Merger announced", body: "…",
    kind: "M&A", signal: "NEUTRAL", capability_ids: ["P4C3.1.1"],
    maturity_effect: "NEUTRAL — nothing has converted.", e_ids: [], claim_label: "FACT",
  }] });
  assert.strictEqual(e.effect_token, "NEUTRAL");
  assert.strictEqual(e.effect_reason, "nothing has converted.");
  assert.strictEqual(e.signal, "neutral", "the stored enum is untouched");
});

/* ── the payload the browser cases run against ────────────────────────── */

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Chicago, IL",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.9, pillar_scores: { P1: 3.1, P2: 2.7, P3: 2.9, P4: 2.6 },
    oss: {}, footprint: ["IL"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.9,
        evidence_mode: "HYBRID", subcap_count: 706 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data) => ({
  data, e_ids: [], produced_at: "2026-08-01T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null,
});

const gapRow = (id, area, name) => ({
  subcap_id: id, name, pillar: "P4", l3_area: area, l4_feature: `${name} feature`,
  catalogue_path: `${area} > ${name}`, current_score: 2, peer_score: null,
  peer_basis: "cannot_estimate", peer_note: "no peer figure at this grain",
  e_ids: [], gap: null, band: "Building",
});

const tile = (rank, platform, cells) => ({
  rank, platform, composite: 70 + rank, relevance: 0.8,
  their_stack_context: `Context for ${platform}.`,
  rank_rationale: `Why ${platform} ranks ${rank}.`,
  factors: [{ name: "gap_coverage", value: 7, weight: 1, contribution: 7 }],
  addressable_cells: cells.map((c) => ({ subcap_id: c, name: null, current: 2,
                                         peer: null, feature_that_addresses_it: `${c} feature` })),
});

const rec = (id, area, phase, cells) => ({
  rec_id: id, title: `${area} recommendation ${id}`, l3_area: area,
  l4_feature: `${area} feature`, phase, effort_band: "M",
  root_cause: "Root cause.", cost_of_inaction: "Cost.",
  sequencing_reason: "Because.", dependencies: [], prerequisites: [
    { cell: "P4C3", minimum: 2, current: 2.19, verdict: "MET" },
  ],
  dma_impact: cells.map((c) => ({ subcap_id: c, name: c, current: 2, target: 2.3,
                                  delta: 0.3, target_basis: "stated uplift" })),
  evidence_ids: [], claim_label: "FACT",
});

const AREA_A = "Integration & API Management";
const AREA_B = "Member Data Platform & Member 360";

function payloadFor(page) {
  const run = { run_id: RUN_ID, promoted_at: "2026-08-01T00:00:00Z",
                completed_at: "2026-08-01T00:00:00Z" };
  const entity = { display_id: ENTITY, name: "Test Credit Union" };
  const sections = {};

  if (page === "context") {
    sections.timeline = sec({
      arc_shape: "strategy-first, substrate-later",
      storyline: "The arc runs in one direction, and the substrate lagged it.",
      verified_sparse: null,
      events: [
        { event_date: "2026-06-01", title: "Merger with another credit union announced",
          body: "A merger was announced; nothing has converted.", kind: "M&A",
          signal: "NEUTRAL", capability_ids: ["P4C3.1.1"],
          maturity_effect: "NEUTRAL — It adds a second member book and takes no "
            + "capability away, so the two integration cells score what they scored before it.",
          claim_label: "FACT", e_ids: [] },
        { event_date: "2018-07-01", title: "First chief data officer appointed",
          body: "A data officer was appointed.", kind: "LEADERSHIP",
          signal: "POSITIVE", capability_ids: ["P4C1.1.2"],
          maturity_effect: "ADVANCED — The role is why the strategy layer exists at all.",
          claim_label: "FACT", e_ids: [] },
      ],
    });
    sections.acquisitions = sec({ rows: [
      { target_name: "HealthCare Associates Credit Union", kind: "MERGER",
        status: "ANNOUNCED", closed_on: null, maturity_effect: "NEUTRAL",
        effect_note: "Nothing has converted, so the cells score what they scored.",
        integration_target: "member accounts", affected_subcap_ids: ["P4C3.1.1"], e_ids: [] },
    ] });
  }

  if (page === "techstack") {
    // Four layers. DATA has NO confirmed row, which is what earns it the
    // primary-gap flag — and its unconfirmed rows are what the tile filters to.
    const item = (ts, product, layer, status) => ({
      ts_id: ts, product, vendor: "V", layer, pillar_id: "P4", status,
      evidence_level: "L3", detection_basis: `How ${product} was detected.`,
      linked_subcap_ids: ["P4C1.1.3"], dma_impact: null, peer_coverage: null,
      peer_deployments: [], e_ids: [],
    });
    sections.techstack = sec({ items: [
      item("TS-1", "Core", "OPS", "CONFIRMED"),
      item("TS-2", "Servicing", "OPS", "INFERRED"),
      item("TS-3", "Portal", "CUST", "CONFIRMED"),
      item("TS-4", "Messaging", "CUST", "INFERRED"),
      item("TS-5", "Warehouse", "DATA", "INFERRED"),
      item("TS-6", "CDP", "DATA", "ABSENT"),
      item("TS-7", "BI", "DATA", "CLAIMED"),
      item("TS-8", "Cloud", "INFRA", "CONFIRMED"),
    ], dropped: [] });
  }

  if (page === "overview") {
    sections.scores = sec({ composite: 2.9, framing: "A framing sentence.", pillars: [
      { pillar_id: "P1", score: 3.1 }, { pillar_id: "P2", score: 2.7 },
      { pillar_id: "P3", score: 2.9 }, { pillar_id: "P4", score: 2.6 }] });
    sections.opportunity = sec({
      tiles: [tile(1, "MuleSoft Anypoint Platform", ["P4C3.4.5", "P4C3.5.3"]),
              tile(2, "Salesforce Data Cloud", ["P4C1.2.1", "P4C1.3.1"])],
      discarded: [{ platform: "Something else", relevance: 0.2, reason: "Not the gap." }],
    });
    // Five entries, one of them CONTRADICTS: the contract calls that the most
    // valuable row on the card and it must never be filtered out.
    sections.thought_leadership = sec({ entries: [1, 2, 3, 4, 5].map((i) => ({
      kind: "ARTICLE", published_on: `2026-0${i}-01`,
      headline: `Executive position ${i}`,
      quote: `A verbatim sentence number ${i} from a named executive.`,
      author_name: `Person ${i}`, author_role: "Chief Data Officer",
      url: `https://example.com/${i}`, linked_subcap_ids: ["P4C1.1.2"],
      alignment: { value: i === 4 ? "CONTRADICTS" : "EXTENDS",
                   clause: `Clause for entry ${i}` },
      e_id: null, claim_label: "FACT",
    })) });
  }

  if (page === "platform") {
    sections.platform_story = sec({
      platforms: [
        { story_md: "What the integration platform changes.",
          gaps: [gapRow("P4C3.1.1", AREA_A, "EA Framework & Governance"),
                 gapRow("P4C3.1.2", AREA_A, "Technology Roadmap")] },
        { story_md: "What the member-data platform changes.",
          gaps: [gapRow("P4C1.2.1", AREA_B, "Data Governance Operating Model"),
                 gapRow("P4C1.3.1", AREA_B, "Member 360 Profile")] },
      ],
      discarded: [{ platform: "Something else", relevance: 0.2, reason: "Not the gap." }],
    });
    sections.recommendations = sec({ recommendations: [
      rec("REC-001", AREA_A, 1, ["P4C3.1.1", "P4C3.1.2"]),
      rec("REC-002", AREA_B, 2, ["P4C1.2.1", "P4C1.3.1"]),
    ] });
    sections.roadmap = sec({
      sequencing_basis: "Backbone first.",
      phases: [
        { phase: "1", horizon: "next two quarters", rationale: "First.",
          depends_on: [], rec_ids: ["REC-001"] },
        { phase: "2", horizon: "this year", rationale: "Second.",
          depends_on: ["1"], rec_ids: ["REC-002"] },
      ],
    });
    sections.stairstep = sec({ ladder: { theme: "Data foundation", current_position: 1,
      steps: [
        { step_level: 1, label: "Named data ownership", entry_condition: "…",
          unlocks: "…", effort_band: "S", blocking_findings: [],
          covered_subcap_ids: ["P4C3.1.1"], current_position: true },
        { step_level: 2, label: "One governed member record", entry_condition: "…",
          unlocks: "…", effort_band: "L", blocking_findings: [],
          covered_subcap_ids: ["P4C1.2.1", "P4C1.3.1"] },
      ] } });
    sections.starters = sec({ starters: [
      { rank: 1, text: "A question the evidence earns.", opens_on: "data",
        named_gap_subcap_id: null, e_ids: [] },
    ] });
  }

  if (page === "insights") {
    sections.insights = sec({ cards: [
      { ic_id: "IC-01", title: "A defensible claim", what_text: "What it says.",
        why_text: "Why it matters.", so_what_text: "What to do.",
        severity: "high", severity_rationale: "It caps five systems.",
        confidence: "HIGH", claim_label: "INFERENCE",
        alternative_explanation: "The alternative reading.",
        validation_question: "What would settle it?",
        affects: ["P4C1.1.3"], supporting_e_ids: [],
        r_layer: { verdict: "ACCEPT", confidence: "HIGH",
                   hypothesis: "The data layer is the binding constraint.",
                   counter: "The counter-case.", domain_test: "The domain test.",
                   probes_run: ["one", "two"] } },
    ] });
  }

  return { entity, run, audience: "internal", sections };
}

/* ── the browser cases ────────────────────────────────────────────────── */

const pw = resolvePlaywright();

test("surfaces read the axis they name, and answer the control the reader pressed",
     { skip: pw ? false : "playwright-core not installed" }, async (t) => {
  const { chromium } = pw;
  const browser = await chromium.launch({
    executablePath: resolveChromium(),
    args: ["--no-sandbox"],
  });
  const { server, base } = await startServer(BOOT);

  // One page, one context, per case — the app caches reads per route and a
  // shared page would measure the previous case's payload.
  const open = async (tab) => {
    const ctx = await browser.newContext({ viewport: { width: 1512, height: 1100 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message).split("\n")[0]));
    await page.route("**/api/entity/**", (route) => {
      const m = route.request().url().match(/\/api\/entity\/[^/]+\/([^/?]+)/);
      route.fulfill({ status: 200, contentType: "application/json",
                      body: JSON.stringify(payloadFor(m ? m[1] : tab)) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/${tab}`, { waitUntil: "domcontentloaded" });
    await settle(page);
    // EVERY session lands as AE (app-root's _landingRole), so the internal
    // surfaces these cases are about are withheld on load. Role state is
    // per-document, so this is redone for every case rather than once.
    await actAsAdmin(page);
    // These cases are ABOUT internal surfaces — reasoning traces, the
    // self-check, thought leadership — so the internal body is asked for
    // explicitly rather than assumed from `audience_default`. That default has
    // been both values and is now "internal" again (owner, 2026-08-19); asking
    // makes these cases independent of it either way.
    await selectAudience(page, "internal");
    return { ctx, page, errors };
  };
  // Same switch tests/qa-gate.js makes, for the same reason: the acting-as
  // role is part of the read key, so the switch triggers a REFETCH whose
  // loading state has a STABLE DOM — settle() alone would measure the spinner.
  const actAsAdmin = async (page) => {
    const opened = await page.evaluate(() => {
      const gear = document.querySelector(
        "header.topbar button.icon-btn[aria-label='Settings']");
      if (!gear) return false;
      gear.click();
      return true;
    });
    if (!opened) return false;
    await page.waitForTimeout(350);
    const clicked = await page.evaluate(() => {
      const pop = document.querySelector(".popover");
      if (!pop) return false;
      const btn = [...pop.querySelectorAll(".toggle-row button")]
        .find((b) => /^admin$/i.test((b.textContent || "").trim()));
      if (!btn) return false;
      btn.click();
      return true;
    });
    if (!clicked) { await page.keyboard.press("Escape").catch(() => {}); return false; }
    await page.waitForResponse(
      (res) => res.url().includes("/api/entity/") && res.url().includes("role=ADMIN"),
      { timeout: 15000 }).catch(() => {});
    await settle(page, 400, 15000);
    return true;
  };
  // innerText applies CSS text-transform, so an eyebrow written "Effect on
  // assessed maturity" reads back SHOUTED. Every text assertion below is
  // case-insensitive for that reason, not out of looseness.
  const textOf = (page) => page.evaluate(() => document.getElementById("app").innerText);

  try {
    await t.test("D5 · the timeline chips name the effect on assessed maturity", async () => {
      const { ctx, page, errors } = await open("context");
      const txt = await textOf(page);
      assert.match(txt, /Effect on assessed maturity/i,
                   "the chip group states the axis it filters on");
      assert.match(txt, /Positive · 1/);
      assert.match(txt, /Neutral · 1/);
      assert.match(txt, /Negative · 0/);
      // The REVERSED assertion, per the owner's adjudication: the relabelled
      // words must not survive anywhere in the control row, so a half-applied
      // rename cannot leave one chip reading Constrained beside two that read
      // Positive and Neutral.
      const chips = await page.evaluate(() => [...document.querySelectorAll(".toggle-row button")]
        .map((b) => b.textContent.trim()));
      assert.ok(!chips.some((c) => /Advanced|Constrained/.test(c)),
                `a relabelled word survived in the filter row: ${JSON.stringify(chips)}`);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("D5 · the effect renders as a badge plus its reason, never the blob",
                 async () => {
      const { ctx, page, errors } = await open("context");
      // Open the merger event.
      await page.evaluate(() => {
        const b = [...document.querySelectorAll("#app .main button")]
          .find((x) => /Merger with another credit union/.test(x.textContent));
        b.click();
      });
      await page.waitForTimeout(500);
      const txt = await textOf(page);
      assert.match(txt, /Effect on assessed maturity/i);
      assert.match(txt, /It adds a second member book/, "the clause renders as prose");
      assert.ok(!/NEUTRAL — It adds a second member book/.test(txt),
                "the raw \"TOKEN — clause\" blob must never reach the page");
      // The token is a badge of its own.
      const badges = await page.evaluate(() => [...document.querySelectorAll("#app .main .b")]
        .map((b) => b.textContent.trim()));
      assert.ok(badges.includes("NEUTRAL"), `no NEUTRAL badge: ${JSON.stringify(badges)}`);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("D5 · an off-vocabulary arc_shape prints, and is marked as off-vocabulary",
                 async () => {
      const { ctx, page, errors } = await open("context");
      const txt = await textOf(page);
      assert.match(txt, /strategy-first, substrate-later/,
                   "the value prints as promoted rather than being dropped");
      assert.match(txt, /not one of the five arc words/);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("tech stack · the primary-gap tile filters to the gap rows", async () => {
      const { ctx, page, errors } = await open("techstack");
      const before = await page.evaluate(() =>
        document.querySelectorAll("#app .main .card .card-tile, #app .main .ts-row").length);
      const rowsBefore = await page.evaluate(() => document.getElementById("app").innerText);
      assert.match(rowsBefore, /Warehouse/);
      assert.match(rowsBefore, /Core/, "an OPS row is on screen before the filter");

      await page.evaluate(() => {
        const b = [...document.querySelectorAll("#app .main button")]
          .find((x) => /Primary gap rows/.test(x.textContent));
        b.click();
      });
      await page.waitForTimeout(600);
      const after = await textOf(page);
      // DATA is the flagged layer (no CONFIRMED row); its three unconfirmed
      // rows are what the tile shows.
      assert.match(after, /3 of 8 rows/i);
      assert.match(after, /Warehouse/);
      assert.match(after, /CDP/);
      assert.match(after, /BI/);
      assert.ok(!/\bCore\b/.test(after),
                "a confirmed row in another layer is not a gap and must be held back");
      // And the way back is on the page.
      assert.match(after, /Show all 8/);
      assert.ok(before >= 0);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("platform · the ladder and the roadmap answer a tile click", async () => {
      const { ctx, page, errors } = await open("platform");
      const read = () => page.evaluate(() => {
        const card = (re) => [...document.querySelectorAll("#app .main .card")]
          .find((c) => re.test(c.textContent.slice(0, 120)));
        const ladder = card(/Stair-step ladder/);
        const road = card(/Transformation roadmap/);
        return { ladder: ladder ? ladder.innerText : "", road: road ? road.innerText : "" };
      });
      const first = await read();
      assert.ok(first.ladder.length > 40, "the ladder rendered");
      assert.ok(first.road.length > 40, "the roadmap rendered");

      await page.evaluate(() => {
        const tiles = [...document.querySelectorAll(
          "#app .main .g4 > .card-tile, #app .main .g5 > .card-tile")];
        tiles[1].click();
      });
      await page.waitForTimeout(700);
      const second = await read();
      assert.notStrictEqual(second.ladder, first.ladder,
        "the stair-step ladder ignored the platform selection");
      assert.notStrictEqual(second.road, first.road,
        "the transformation roadmap ignored the platform selection");
      assert.match(second.ladder, /Salesforce Data Cloud/);
      assert.match(second.road, /Salesforce Data Cloud/);
      // Marked, not filtered: the other platform's rung is still on the ladder.
      assert.match(second.ladder, /Named data ownership/);
      assert.match(second.ladder, /One governed member record/);
      // And the one panel that genuinely cannot be scoped says so.
      const aside = await page.evaluate(() => {
        const c = [...document.querySelectorAll("#app .main .card")]
          .find((x) => /Considered and set aside/.test(x.textContent.slice(0, 120)));
        return c ? c.innerText : "";
      });
      assert.match(aside, /this list is the run's/);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("insights · the reviewer gets a pair, and no producer self-check",
                 async () => {
      /* The "Reasoning trace / Self-check · ACCEPT" half of this test is
         SUPERSEDED as of 2026-08-19: `r_layer` is stripped for every audience
         at the API boundary and the modal's trace block is deleted.

         The reviewer pair is unaffected and still asserted — it was never the
         producer's verdict, it is the human's, and it was deliberately built
         to render whether or not a card carries a trace. */
      const { ctx, page, errors } = await open("insights");
      await page.evaluate(() => document.querySelector("#app .main .ic").click());
      await page.waitForTimeout(600);
      const modal = await page.evaluate(() => {
        const m = document.querySelector(".modal-mask");
        return { text: m ? m.innerText : "",
                 buttons: [...(m ? m.querySelectorAll("button") : [])]
                   .map((b) => b.textContent.trim()) };
      });
      assert.doesNotMatch(modal.text, /Reasoning trace/i,
        "the producer's trace reached the insight modal");
      assert.doesNotMatch(modal.text, /Self-check/i,
        "the producer's self-check reached the insight modal");
      assert.match(modal.text, /Your verdict/i);
      const accepts = modal.buttons.filter((b) => /^Accept$/.test(b)).length;
      const rejects = modal.buttons.filter((b) => /^Reject$/.test(b)).length;
      assert.strictEqual(accepts, 1, `expected exactly one Accept, saw ${accepts}`);
      assert.strictEqual(rejects, 1, `expected exactly one Reject, saw ${rejects}`);
      // The honest disclosure about where the verdict goes.
      assert.match(modal.text, /Stored as an annotation against IC-01/);
      assert.match(modal.text, /log rather than a loop/);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });

    await t.test("overview · thought leadership holds five, and shows a CONTRADICTS",
                 async () => {
      const { ctx, page, errors } = await open("overview");
      const card = await page.evaluate(() => {
        const c = [...document.querySelectorAll("#app .main .card")]
          .find((x) => /Thought leadership signal/.test(x.textContent.slice(0, 120)));
        return c ? { text: c.innerText, cards: c.querySelectorAll(".card-tile").length } : null;
      });
      assert.ok(card, "the thought-leadership card rendered");
      assert.strictEqual(card.cards, 5,
        `the payload carried 5 entries and the render showed ${card.cards}`);
      assert.match(card.text, /5 named executives/);
      assert.match(card.text, /CONTRADICTS/,
        "the contract's most valuable row was invisible before this");
      assert.match(card.text, /Clause for entry 4/);
      assert.deepStrictEqual(errors, []);
      await ctx.close();
    });
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
});
