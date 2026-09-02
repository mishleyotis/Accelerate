/* An issue bar stays inside its own lane, and never shows one clipped letter.
 *
 * Reported 2026-09-02 from the promoted Golden 1 page: the issue register's
 * time axis pushed bars past the card edge, and two of them rendered a single
 * character where a title should be.
 *
 * MEASURED ON THAT RUN'S OWN PAYLOAD. The geometry is
 *
 *     const left  = clamp(pct(start))
 *     const right = clamp(pct(end))
 *     const width = Math.max(2, right - left)      // <- the floor
 *
 * The 2% floor is what keeps a same-day matter visible. It was applied
 * WITHOUT re-checking the right edge, so a bar pinned near the end of the
 * axis ran off the track:
 *
 *     I-001  opened 2026-08-25, axis ends 2026-09-02 (today)
 *            left 99.55%  width 2.00%  ->  ends at 101.55%
 *
 * Eight days before the axis end on a five-year axis is 0.45% of the track,
 * floored to 2%, and the surplus 1.55% hangs over the card. Both of Golden
 * 1's active matters did it. The second half is the same case seen from the
 * other side: an 85-character title inside a 2%-wide bar rendered as "D".
 *
 * A single clipped letter is not a short label — it is a name the reader
 * cannot read presented as though it were one, next to a row whose own label
 * already carries the title in full with a tooltip.
 *
 * The fixture dates are the promoted run's, shifted only so that "today" is
 * fixed: the defect is a function of the distance between the last opened_on
 * and the axis end, so it must be pinned rather than left to drift with the
 * clock.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Sacramento, CA",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.25, pillar_scores: {}, oss: {}, footprint: ["CA"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.25,
        evidence_mode: "PUBLIC", subcap_count: 690 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const ENV = {
  produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
  e_ids: ["E-CC-188"], internal_only: [],
  narrative_thread: "The line through this page, written last from what was produced.",
};

/* Verbatim from the promoted run: the two matters that overflowed opened
   eight days before the axis end, and their titles are contract-legal
   (8-16 words), which is what makes this a rendering defect and not a
   payload one. */
const ISSUES = [
  { issue_id: "I-001",
    title: "Databricks lakehouse runs live in Phase 1 but is not connected "
      + "to Salesforce Data 360",
    severity: "MATERIAL", status: "Active",
    opened_on: "2026-08-25", resolved_on: null },
  { issue_id: "I-002",
    title: "Microsoft Copilot answers reconcile inconsistently with other "
      + "enterprise data and dashboards",
    severity: "MATERIAL", status: "Active",
    opened_on: "2026-08-25", resolved_on: null },
  { issue_id: "I-003",
    title: "Integration architecture runs point to point in custom code "
      + "with no enterprise service bus",
    severity: "MATERIAL", status: "Active",
    opened_on: "2024-07-01", resolved_on: null },
  { issue_id: "I-004",
    title: "October 2021 post-upgrade login outage locked members out of "
      + "the mobile app and website",
    severity: "MINOR", status: "Resolved",
    opened_on: "2021-10-25", resolved_on: "2021-11-08" },
  { issue_id: "I-005",
    title: "July 2024 global third-party technology outage degraded online "
      + "and mobile banking",
    severity: "MINOR", status: "Resolved",
    opened_on: "2024-07-19", resolved_on: "2024-08-15" },
].map((x) => ({
  ...x, provenance: "analyst", rationale: "", capped_subcap_ids: [],
  linked_subcap_ids: [], e_ids: ["E-CC-188"],
}));

function contextPage() {
  return {
    sections: {
      issue_register: { data: { ...ENV, verified_absent: false, issues: ISSUES } },
      timeline: { data: { ...ENV, events: [], arc_shape: null, storyline: null,
                          verified_sparse: true } },
      acquisitions: { data: { ...ENV, rows: [], empty_state: {
        reason: "No acquisition, merger or charter change appears in the "
          + "regulator's record for this institution.",
        sources_searched: ["regulator merger register", "trade press"] } } },
      context_sentiment: { data: { ...ENV, context_tiles: [] } },
      regulatory_standing: { data: { ...ENV, primary_regulator: "NCUA",
        license_type: "State credit union", charter_date: "1933-01-01",
        jurisdictions: ["US"], additional_regulators: [],
        enforcement_actions: [], absence_of_enforcement: null } },
    },
  };
}

async function renderContext(width) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width, height: 1400 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname
        .split("/").pop().split("?")[0];
      const body = which === "context" ? contextPage() : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/context`,
                    { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    return { page, browser, server };
  } catch (e) {
    await browser.close(); server.close(); throw e;
  }
}

/* Every absolutely-positioned bar on the page, with its own box and the box
   of the lane it is positioned inside. Measured in pixels, because a
   percentage that reads correctly in the source is exactly what shipped. */
async function bars(page) {
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll("div[style*='position: absolute']")) {
      const s = getComputedStyle(el);
      if (s.position !== "absolute") continue;
      const lane = el.offsetParent;
      if (!lane) continue;
      const b = el.getBoundingClientRect(), l = lane.getBoundingClientRect();
      if (b.width === 0 || b.height === 0) continue;
      /* Bars only. The axis year ticks are absolutely positioned in the
         header lane too, and they are SUPPOSED to be narrow and to carry
         text ("2021") — measuring them reported the axis as a defect. A
         bar is the thing with a filled background in a full-height lane;
         a tick is a dashed border in a 14px one. */
      const filled = s.backgroundColor && s.backgroundColor !== "transparent"
        && !/^rgba\(0, 0, 0, 0\)$/.test(s.backgroundColor);
      if (!filled || l.height < 20) continue;
      out.push({ text: (el.textContent || "").trim(),
                 left: b.left, right: b.right, width: b.width,
                 laneLeft: l.left, laneRight: l.right });
    }
    return out;
  });
}

for (const width of [1512, 1180, 960]) {
  test(`issue timeline · no bar escapes its lane at ${width}px`,
       { skip }, async () => {
    const { page, browser, server } = await renderContext(width);
    try {
      const escaped = (await bars(page)).filter(
        (b) => b.right > b.laneRight + 1 || b.left < b.laneLeft - 1);
      assert.deepEqual(escaped, [],
        `bar(s) outside their lane: ${JSON.stringify(escaped)}`);
    } finally { await browser.close(); server.close(); }
  });
}

test("issue timeline · the page never scrolls sideways", { skip }, async () => {
  const { page, browser, server } = await renderContext(960);
  try {
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(over <= 0, `page scrolls sideways by ${over}px`);
  } finally { await browser.close(); server.close(); }
});

test("issue timeline · a bar too narrow to hold a title carries none",
     { skip }, async () => {
  /* I-001 and I-002 are the 2%-wide stubs. Whatever a bar shows, it is
     never a fragment so short the reader cannot tell what it names. */
  const { page, browser, server } = await renderContext(1512);
  try {
    const stubs = (await bars(page)).filter((b) => b.width < 60 && b.text);
    assert.deepEqual(stubs, [],
      `narrow bar(s) carrying a clipped label: ${JSON.stringify(stubs)}`);
  } finally { await browser.close(); server.close(); }
});

test("issue timeline · every matter is still named in its row",
     { skip }, async () => {
  /* Suppressing the stub label must not lose the title: the row's own label
     column carries all five in full. */
  const { page, browser, server } = await renderContext(1512);
  try {
    const body = await page.evaluate(() => document.body.innerText);
    for (const i of ISSUES) {
      const head = i.title.split(" ").slice(0, 4).join(" ");
      assert.ok(body.includes(head) || body.includes(i.issue_id),
        `${i.issue_id} is not named anywhere on the page`);
    }
  } finally { await browser.close(); server.close(); }
});
