/* Text that lands on top of other text. Measured from geometry, not read.
 *
 * REPORTED 2026-08-23 with a screenshot of a promoted platform page:
 * "overlapping text". No contract gate can see this — every field was
 * allowed, every value was served, and the payload is correct. The defect is
 * entirely in what a browser did with it, so the only instrument that can
 * find it is a browser.
 *
 * The existing visual-qa-gates suite measures TRUNCATION: text that clips at
 * a boundary and cannot be recovered. Overlap is the opposite failure of the
 * same box — the boundary was not enforced at all, the text spilled, and it
 * landed on its neighbour. A layout can pass the truncation gate precisely
 * BY overflowing, so the two gates have to exist together or the fix for one
 * is the cause of the other.
 *
 * TWO MECHANISMS, and both are checked, because in CSS they are different
 * bugs with different fixes:
 *
 *   SPILL      an element whose text is wider than its box while the box
 *              lets it out (`overflow: visible`, `white-space: nowrap`, a
 *              fixed width). The text is drawn outside its own rectangle, so
 *              nothing about the element's own layout looks wrong — the
 *              damage shows up on whatever sits next to it. This is what a
 *              long client name or an unabbreviated source title does.
 *
 *   COLLISION  two in-flow text boxes whose rectangles genuinely intersect.
 *              In normal flow this cannot happen by design; it happens when
 *              a fixed height meets content that grew, or when a negative
 *              margin is used to pull a row up.
 *
 * Deliberately NOT flagged: absolutely-positioned and fixed elements, and
 * anything under a transform. Those overlap on purpose — a tooltip, a drawer,
 * a badge sitting on a chart are all layered by intent, and a gate that
 * cannot tell intent from accident gets switched off within a week.
 *
 * Run with `npm run test:web`. Drives the COMPILED bundle, like every other
 * render suite here: the app serves `public/proto/js`, so a test that read
 * the JSX would measure code that does not ship.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "overlap-credit-union";
const RUN_ID = "DMA-ASM-OCU-20260823-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

/* Strings chosen to break a layout the way real client data breaks it. A
   gate tested on `lorem ipsum` is a gate tested on a word length no client
   has. Every one of these is the shape of something that has actually
   reached a page: an unabbreviated institution name, a catalogue label with
   no spaces to wrap at, a regulator's full document title. */
const LONG_NAME =
  "American Airlines Federal Credit Union — Consolidated Technology and "
  + "Digital Transformation Programme Office";
const NO_BREAKPOINTS =
  "SalesforceDataCloudFinancialServicesCloudMemberEngagementAccelerator";
const LONG_TITLE =
  "Model governance and third-party risk oversight for the analytics estate, "
  + "sequenced ahead of the core conversion so the platform decision is made "
  + "once";

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: LONG_NAME,
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM",
    hq: "Fort Worth, Texas, United States of America",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-23",
    overall: 2.14, pillar_scores: {}, oss: {}, footprint: ["TX"], runs: [
      { id: RUN_ID, date: "2026-08-23", status: "ACTIVE", overall: 2.14,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data, extra) => ({
  data, e_ids: [], produced_at: "2026-08-23T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null, ...extra,
});

function overviewPayload() {
  const sections = {};
  sections.scores = sec({
    composite: 2.14, posture: "MIXED",
    pillars: ["P1", "P2", "P3", "P4"].map((id) => ({
      pillar_id: id, score: 2.1, peer_median: 2.6, peer_n: 5,
      peer_basis: "same_subvertical_cohort_median",
    })),
    narrative_thread: "The estate is built and the governance around it is not.",
  });
  sections.firmographics = sec({
    fields: [
      { field: "total_assets", value: "9.1", unit: "billion USD",
        as_of: "2026-06-30" },
      { field: "employees", value: "1,240", as_of: "2026-06-30" },
      { field: "headquarters",
        value: "Fort Worth, Texas, United States of America",
        as_of: "2026-06-30" },
    ],
    narrative_thread: "Scale is disclosed quarterly.",
  });
  sections.findings = sec({
    findings: [
      { finding_id: "F-1", title: LONG_TITLE,
        body: "The analytics estate is in place and its oversight is not "
          + "evidenced, which is the sequencing risk this run names.",
        e_ids: [], severity: "HIGH" },
      { finding_id: "F-2", title: NO_BREAKPOINTS,
        body: "A catalogue label with nowhere to wrap, which is what a "
          + "vendor product string looks like before anyone abbreviates it.",
        e_ids: [], severity: "MEDIUM" },
    ],
    ranking_basis: "By the width of the gap each names.",
    narrative_thread: "Two findings, one of them the sequencing decision.",
  });
  sections.sentiment = sec({
    bars: [
      { audience: "customer", source: "Apple App Store", rating: 4.75,
        scale: 5, n: 9585, as_of: "2026-08-23" },
      { audience: "employee",
        source: "Indeed — employer profile, all reviewing offices",
        rating: 3.7, scale: 5, n: 99, as_of: "2026-08-23" },
    ],
    themes: [], narrative_thread: "Members rate it above the people serving.",
  });
  return { entity: { display_id: ENTITY, name: LONG_NAME },
           run: { run_id: RUN_ID, promoted_at: "2026-08-23T00:00:00Z",
                  completed_at: "2026-08-23T00:00:00Z", evidence_mode: "PUBLIC" },
           audience: "internal", sections };
}

function platformPayload() {
  return {
    entity: { display_id: ENTITY, name: LONG_NAME },
    run: { run_id: RUN_ID, promoted_at: "2026-08-23T00:00:00Z" },
    audience: "internal",
    sections: {
      platform_story: sec({
        platforms: [
          { platform: NO_BREAKPOINTS, fit_score: 77.5, rank: 1,
            rationale: "Named for the member-data layer.",
            fit_basis: "Computed by the shared platform-fit engine.",
            readiness: { verdict: "READY WITH CONDITIONS",
                         already_true: "The member data layer is in place." } },
          { platform: "Salesforce Financial Services Cloud", fit_score: 74.1,
            rank: 2, rationale: "Second on fit and first on alignment.",
            fit_basis: "Rank fusion moved this card up one place." },
        ],
        discarded: [{ platform: "A commerce suite",
                      reason: "The estate has no commerce surface to serve." }],
        narrative_thread: "One platform is ranked and one is set aside.",
      }),
      readiness: sec({
        title: LONG_TITLE,
        stages: [{ stage: "Foundations",
                   condition: "Governance is named and its owner is stated." }],
        narrative_thread: "Readiness runs through governance.",
      }),
    },
  };
}

/* ── the measurement ────────────────────────────────────────────────────
   Both mechanisms are found in ONE page.evaluate: two passes over the DOM
   from a single layout, so nothing can change between them.

   SPILL IS MEASURED AS INK, not as `scrollWidth - clientWidth`. The first
   version of this probe used the scrollWidth difference and reported four
   findings on one page; measuring the painted text with a Range showed two
   of them were real (a breadcrumb link 24px of text wide inside a 17px box)
   and two were sub-pixel rounding on a flex button whose ink was 12px NARROWER
   than its box. A gate whose findings are half noise is a gate somebody
   silences. What a reader sees is the ink, so the ink is what is measured. */
const PROBE = () => {
  const vis = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden") return null;
    if (Number(s.opacity) === 0) return null;
    return s;
  };
  const ownText = (el) => {
    let t = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) t += n.nodeValue;
    }
    return t.trim();
  };
  const label = (el, text) =>
    `${el.tagName.toLowerCase()}${el.className ? "." + String(el.className).split(" ")[0] : ""}`
    + `: ${text.slice(0, 70)}`;

  const spills = [];
  const boxes = [];

  for (const el of document.querySelectorAll("body *")) {
    const s = vis(el);
    if (!s) continue;
    const text = ownText(el);
    if (!text) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;

    // SPILL. The box lets its own text out sideways. `overflow-x: visible`
    // is the default, so this is not exotic — it is what happens to any
    // flex item squeezed below its content width by a longer sibling.
    //
    // 2px of tolerance covers sub-pixel layout; anything past that is text a
    // reader can see sitting outside the element that owns it.
    if (s.overflowX === "visible") {
      const rng = document.createRange();
      rng.selectNodeContents(el);
      const ink = rng.getBoundingClientRect();
      const past = Math.max(ink.right - r.right, r.left - ink.left);
      if (past > 2) {
        spills.push(`${label(el, text)}  [ink ${Math.round(ink.width)}px in a `
                    + `${Math.round(r.width)}px box, ${Math.round(past)}px outside]`);
      }
    }

    // Layered on purpose: absolute, fixed, sticky, or transformed. A gate
    // that flags a tooltip over a chart gets switched off within a week.
    if (s.position !== "static" && s.position !== "relative") continue;
    if (s.transform && s.transform !== "none") continue;
    boxes.push({ el, r, text });
  }

  // COLLISION. Rectangles of in-flow text boxes that genuinely intersect.
  // Ancestors are skipped (a parent legitimately contains its child) and so
  // is a hairline touch, which is antialiasing rather than a defect.
  const hits = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (w <= 2 || h <= 2) continue;
      const area = w * h;
      const smaller = Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
      if (smaller <= 0 || area / smaller < 0.2) continue;
      hits.push(`${label(a.el, a.text)}  OVER  ${label(b.el, b.text)}`
                + `  [${Math.round(w)}x${Math.round(h)}px]`);
    }
  }
  return { spills, hits };
};

async function probe(page) {
  return page.evaluate(PROBE);
}

test("no text overlaps other text", { skip, concurrency: false }, async (t) => {
  const { server } = await startServer(BOOT);
  const base = server ? `http://127.0.0.1:${server.address().port}` : null;
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });

  const open = async (which, { width = 1512 } = {}) => {
    const page = await browser.newPage({ viewport: { width, height: 1100 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.route("**/api/entity/**", async (route) => {
      const tail = new URL(route.request().url()).pathname.split("/").pop();
      const body = tail === "overview" ? overviewPayload()
        : tail === "platform" ? platformPayload() : null;
      if (!body) {
        return route.fulfill({ status: 404, contentType: "application/json",
                               body: '{"error":"not_found"}' });
      }
      await route.fulfill({ status: 200, contentType: "application/json",
                            body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/${which}`,
                    { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    return { page, errors };
  };

  try {
    // THE PROBE MUST BE ABLE TO FAIL. A geometry gate that reports clean
    // because it examined nothing is the exact defect class this build keeps
    // removing — "I looked and found nothing" reading the same as "I could
    // not look". So an element is deliberately broken first, the probe is
    // required to catch it, and only then is the real page measured.
    await t.test("the probe catches a collision it is shown", async () => {
      const { page } = await open("overview");
      const caught = await page.evaluate((src) => {
        const host = document.createElement("div");
        host.style.cssText = "position:relative;width:300px;height:40px";
        const a = document.createElement("div");
        a.textContent = "A line of text that is deliberately overlapped here";
        a.style.cssText = "position:relative;margin-bottom:-18px;font-size:14px";
        const b = document.createElement("div");
        b.textContent = "A second line landing on top of the first one";
        b.style.cssText = "position:relative;font-size:14px";
        host.appendChild(a); host.appendChild(b);
        document.body.appendChild(host);
        // eslint-disable-next-line no-new-func
        const out = new Function("return (" + src + ")()")();
        host.remove();
        return out.hits.some((h) => h.includes("deliberately overlapped"));
      }, PROBE.toString());
      assert.ok(caught,
        "the collision probe did not find a collision it was handed. Every "
        + "clean result below would be meaningless.");
      await page.close();
    });

    await t.test("the probe catches a spill it is shown", async () => {
      const { page } = await open("overview");
      const caught = await page.evaluate((src) => {
        const el = document.createElement("div");
        el.textContent = "AnUnbrokenStringFarWiderThanItsOwnBoxWillEverBe";
        el.style.cssText = "width:40px;white-space:pre;overflow:visible;"
                         + "font-size:14px";
        document.body.appendChild(el);
        // eslint-disable-next-line no-new-func
        const out = new Function("return (" + src + ")()")();
        el.remove();
        return out.spills.some((s) => s.includes("AnUnbrokenString"));
      }, PROBE.toString());
      assert.ok(caught, "the spill probe did not find a spill it was handed.");
      await page.close();
    });

    // ── the real pages, at three widths ───────────────────────────────
    //
    // 1512 is the laptop the defect was reported from; 1180 is the width the
    // sidebar collapses at; 900 is where a two-column card becomes one. A
    // gate that measures only the widest case measures the case that never
    // failed — the truncation gate learned that the expensive way.
    for (const which of ["overview", "platform"]) {
      for (const width of [1512, 1180, 900]) {
        await t.test(`${which} at ${width}px: nothing spills its box`, async () => {
          const { page, errors } = await open(which, { width });
          const { spills } = await probe(page);
          assert.deepStrictEqual(errors, []);
          assert.deepStrictEqual(spills, [],
            `${which} @${width}: text is drawn outside its own box and will `
            + `land on whatever sits beside it. Give the slot a wrap, a `
            + `min-width:0 inside its flex parent, or an ellipsis with the `
            + `full string in title=:\n  ${spills.join("\n  ")}`);
          await page.close();
        });

        await t.test(`${which} at ${width}px: no two text boxes collide`, async () => {
          const { page } = await open(which, { width });
          const { hits } = await probe(page);
          assert.deepStrictEqual(hits, [],
            `${which} @${width}: two in-flow text boxes overlap. Neither is `
            + `positioned, so this is not layering — a fixed height met `
            + `content that grew, or a negative margin pulled a row up:`
            + `\n  ${hits.join("\n  ")}`);
          await page.close();
        });
      }
    }

    // The client name is the single longest string any page renders and it
    // appears in the header of all six. Called out on its own because it is
    // the string that changes per client — every other one is authored.
    await t.test("a very long client name does not break the header", async () => {
      const { page } = await open("overview", { width: 900 });
      const bad = await page.evaluate((name) => {
        const out = [];
        for (const el of document.querySelectorAll("body *")) {
          if ((el.textContent || "").indexOf(name.slice(0, 40)) < 0) continue;
          if (el.children.length) continue;
          const r = el.getBoundingClientRect();
          if (r.right > window.innerWidth + 1) {
            out.push(`${el.tagName}: runs ${Math.round(r.right - window.innerWidth)}px past the viewport`);
          }
        }
        return out;
      }, LONG_NAME);
      assert.deepStrictEqual(bad, [],
        `the client name runs off the page:\n  ${bad.join("\n  ")}`);
      await page.close();
    });
  } finally {
    await browser.close();
    if (server) server.close();
  }
});
