/* The four visual-QA gates the round-3 brief asked for that had no test.
 *
 * Every defect below was reported from a rendered page, not from a payload,
 * and each one passed every contract gate on its way there. The surface
 * contract answers "is the field allowed to be served"; none of these is a
 * question about a field.
 *
 *   TRUNCATION   a card title clipped mid-word with no way to read the rest.
 *                A one-line clamp on a slot whose content is a sentence, and
 *                no `title` attribute behind it, so the text simply ends.
 *   PLACEMENT    "Considered and set aside" argued platform choices on the
 *                overview, the page that does not own them. Content on the
 *                wrong page is not a formatting problem: the reader forms the
 *                argument in the wrong order.
 *   EMPTY STATE  a field with nothing in it rendered a label, a dash and an
 *                explanation of its own absence. Revenue is the measured one
 *                — a credit union has none to state — and the instruction was
 *                to remove the row, never to explain it.
 *   PROVENANCE   evidence ids reached client prose as bare text, `(E-CC-303)`
 *                mid-sentence, and a card that cites nothing looked identical
 *                to a card that cites four sources.
 *
 * Run with `npm run test:web`. Drives the COMPILED bundle through the shared
 * harness for the same reason every other render suite here does: the app
 * serves `public/proto/js`, so a test that read the JSX would verify code
 * that does not ship.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const { resolvePlaywright, startServer, settle, selectAudience,
        assertNoStringifiedObjects,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "gate-credit-union";
const RUN_ID = "DMA-ASM-GCU-20260819-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Gate Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Burbank, CA",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-19",
    overall: 1.59, pillar_scores: {}, oss: {}, footprint: ["CA"], runs: [
      { id: RUN_ID, date: "2026-08-19", status: "ACTIVE", overall: 1.59,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data, extra) => ({
  data, e_ids: [], produced_at: "2026-08-19T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null, ...extra,
});

/* A title long enough to overflow any single-line slot in this layout, and a
   real sentence rather than filler, because a clamp that breaks on lorem
   ipsum and holds on real prose has not been tested. */
const LONG_TITLE =
  "Model governance and third-party risk oversight for the analytics estate, "
  + "sequenced ahead of the core conversion so the platform decision is made "
  + "once";

/* The platform argument that belongs on the platform page and nowhere else. */
const SET_ASIDE_HEADING = "Considered and set aside";

function overviewPayload() {
  const sections = {};
  sections.scores = sec({
    composite: 1.59, posture: "MIXED",
    pillars: ["P1", "P2", "P3", "P4"].map((id) => ({
      pillar_id: id, score: 1.5, peer_median: 2.5, peer_n: 5,
      peer_basis: "same_subvertical_cohort_median",
    })),
    narrative_thread: "The estate is built and the governance around it is not.",
  });
  // Two held fields and one blank. NONE of them may produce a row: the
  // instruction was that an empty field is removed, not explained.
  sections.firmographics = sec({
    fields: [
      { field: "total_assets", value: "9.1", unit: "billion USD",
        as_of: "2026-06-30" },
      { field: "revenue", value: null, held: true,
        quarantine_reason: "A credit union returns its surplus to members." },
      { field: "ebitda", value: "", held: false },
      { field: "employees", value: null, held: false },
    ],
    narrative_thread: "Scale is disclosed quarterly and the rest is not.",
  });
  // One card cites, one does not. The bracketed group must never render.
  sections.findings = sec({
    findings: [
      { finding_id: "F-1", title: LONG_TITLE,
        body: "The analytics estate is in place and its oversight is not "
          + "evidenced (E-CC-187, E-CC-199), which is the sequencing risk.",
        e_ids: ["E-CC-187", "E-CC-199"], severity: "HIGH" },
      { finding_id: "F-2", title: "Fraud casework runs on a modern platform",
        body: "Case management integrates with the core in real time.",
        e_ids: [], severity: "MEDIUM" },
      // Cites an id this run does not serve. Invariant 4 makes that a
      // fail-closed condition at submit; the render must not turn it into a
      // heading over an empty list.
      { finding_id: "F-3", title: "A finding whose sources did not arrive",
        body: "The argument stands on a source the served index does not hold.",
        e_ids: ["E-CC-999"], severity: "LOW" },
    ],
    ranking_basis: "By the width of the gap each names.",
    narrative_thread: "Two findings, one of them the sequencing decision.",
  });
  // Bars whose scale is stated as a NUMBER, which is how the promoted
  // payloads state it and what blanked five real ratings for three rounds.
  sections.sentiment = sec({
    bars: [
      { audience: "customer", source: "Apple App Store", rating: 4.75,
        scale: 5, n: 9585, as_of: "2026-08-19" },
      { audience: "employee", source: "Indeed — employer profile", rating: 3.7,
        scale: 5, n: 99, as_of: "2026-08-19" },
    ],
    themes: [], narrative_thread: "Members rate it above the people serving.",
  });
  return { entity: { display_id: ENTITY, name: "Gate Credit Union" },
           run: { run_id: RUN_ID, promoted_at: "2026-08-19T00:00:00Z",
                  completed_at: "2026-08-19T00:00:00Z", evidence_mode: "PUBLIC" },
           audience: "internal", sections };
}

/* The evidence INDEX, which is its own endpoint rather than a section of any
   page — `getEvidence` resolves every citation against this list, so without
   it each chip is dropped one `return null` at a time and the defect below
   cannot be reproduced. */
function evidencePayload() {
  return {
    items: [
      { e_id: "E-CC-187", source_name: "Annual report", tier: "T2",
        source_url: "https://example.org/annual-report",
        recency_band: "CURRENT", published_date: "2026-03-31",
        excerpt: "The analytics programme is described across two pages with "
          + "no named owner for model risk." },
      { e_id: "E-CC-199", source_name: "Call report, quarter two", tier: "T1",
        source_url: "https://example.org/call-report",
        recency_band: "CURRENT", published_date: "2026-06-30",
        excerpt: "The quarterly filing states the asset base and the member "
          + "count on which every scale figure here rests." },
    ],
    distribution: { total_items: 2, tiers: { T1: 1, T2: 1 }, claims: {} },
  };
}

function platformPayload() {
  return {
    entity: { display_id: ENTITY, name: "Gate Credit Union" },
    run: { run_id: RUN_ID, promoted_at: "2026-08-19T00:00:00Z" },
    audience: "internal",
    sections: {
      platform_story: sec({
        platforms: [{ platform: "Salesforce Data Cloud", fit_score: null,
                      rank: 1, rationale: "Named for the member-data layer." }],
        discarded: [
          { platform: "A commerce suite",
            reason: "Ranked out because the estate has no commerce surface "
              + "to serve (E-CC-206)." },
        ],
        narrative_thread: "One platform is ranked and one is set aside.",
      }),
      readiness: sec({
        title: LONG_TITLE,
        stages: [{ stage: "Foundations", condition: "Governance is named." }],
        narrative_thread: "Readiness runs through governance.",
      }),
    },
  };
}

/* Every element whose job is to be a TITLE. A clipped body paragraph is a
   design decision; a clipped title is a defect, because the title is the only
   text that names the thing. */
const TITLE_SELECTOR = "h1, h2, h3, h4, .title, .card-head h3, "
  + "[class*='txt-fit-1'], [class*='txt-fit-2']";

async function clippedTitles(page) {
  return page.evaluate((sel) => {
    const out = [];
    for (const el of document.querySelectorAll(sel)) {
      const text = (el.innerText || "").trim();
      if (!text) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      // A title slot only counts as a title where it reads like one: bold,
      // or a heading tag. Muted 10px sub-lines are captions and are allowed
      // to clamp.
      const heading = /^H[1-4]$/.test(el.tagName)
        || Number(style.fontWeight) >= 600;
      if (!heading) continue;
      const clipsDown = el.scrollHeight > el.clientHeight + 1;
      const clipsAcross = el.scrollWidth > el.clientWidth + 1;
      if (!clipsDown && !clipsAcross) continue;
      const title = el.getAttribute("title") || "";
      if (title.trim().length >= text.length) continue;   // reachable on hover
      out.push(`${el.tagName}.${el.className || "-"}: ${text.slice(0, 90)}`);
    }
    return out;
  }, TITLE_SELECTOR);
}

test("visual QA gates", { skip, concurrency: false }, async (t) => {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });

  const open = async (which, { width = 1512 } = {}) => {
    const page = await browser.newPage({ viewport: { width, height: 1100 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.route("**/api/entity/**", async (route) => {
      const which2 = new URL(route.request().url()).pathname.split("/").pop();
      const body = which2 === "overview" ? overviewPayload()
        : which2 === "platform" ? platformPayload()
        : which2 === "evidence" ? evidencePayload() : null;
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
    // ── TRUNCATION ────────────────────────────────────────────────────
    await t.test("no title clips with its full text out of reach", async () => {
      for (const which of ["overview", "platform"]) {
        const { page } = await open(which);
        const bad = await clippedTitles(page);
        assert.deepStrictEqual(bad, [],
          `${which}: a title is clipped and the rest of it is unreachable. `
          + `Let it wrap, or carry the full string in title= so a hover `
          + `reveals it:\n  ${bad.join("\n  ")}`);
        await page.close();
      }
    });

    await t.test("titles still do not clip at a narrow viewport", async () => {
      // The reported clip was at a laptop width, not a phone. A gate that
      // only measures the widest case measures the case that never failed.
      const { page } = await open("platform", { width: 1180 });
      const bad = await clippedTitles(page);
      assert.deepStrictEqual(bad, [],
        `narrow viewport: ${bad.join("\n  ")}`);
      await page.close();
    });

    // ── PLACEMENT ─────────────────────────────────────────────────────
    await t.test("the platform argument renders on the platform page", async () => {
      const { page } = await open("platform");
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes(SET_ASIDE_HEADING),
        "the platforms considered and set aside do not render on the page "
        + "that owns them, so the payload's `discarded` reaches no reader");
      await page.close();
    });

    await t.test("and nowhere else", async () => {
      const { page } = await open("overview");
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(!text.includes(SET_ASIDE_HEADING),
        "a platform argument is being made on the overview. Content on the "
        + "wrong page is not a formatting problem — the reader forms the "
        + "argument in the wrong order");
      await page.close();
    });

    // ── EMPTY STATE ───────────────────────────────────────────────────
    await t.test("an empty field renders no row and no explanation", async () => {
      const { page } = await open("overview");
      const text = await page.evaluate(() => document.body.innerText || "");

      // The measured one. Revenue is held, and a held field is REMOVED.
      assert.ok(!/\bRevenue\b/i.test(text),
        "revenue rendered a row. A credit union has no revenue figure to "
        + "state, and the instruction was to remove the field, not to "
        + "explain it");
      for (const label of ["Ebitda", "EBITDA", "Employees"]) {
        assert.ok(!text.includes(label),
          `${label} is empty and still rendered a label`);
      }
      // The field that DOES carry a value must still be there, or this gate
      // would pass on a panel that renders nothing at all.
      assert.ok(/9\.1/.test(text),
        "the disclosed scale figure vanished with the empty ones");

      // No status word anywhere. These name our own workflow, which the
      // reader is not party to, and they are what "explained" looked like.
      const PLUMBING = ["queued for enrichment", "pending enrichment",
                        "awaiting enrichment", "not yet enriched",
                        "no data available", "not available", "coming soon",
                        "placeholder", "TBD", "held"];
      const said = PLUMBING.filter((w) =>
        new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i")
          .test(text));
      assert.deepStrictEqual(said, [],
        `a status word reached the page: ${said.join(", ")}. An absence is `
        + `stated in the producer's own words or not at all`);
      await page.close();
    });

    // ── PROVENANCE ────────────────────────────────────────────────────
    await t.test("evidence ids never render as prose", async () => {
      const { page } = await open("overview");
      const text = await page.evaluate(() => document.body.innerText || "");
      const leaked = [...text.matchAll(/[([]\s*E-(?:[A-Z]{1,4}-)?\d{1,5}[^)\]]*[)\]]/g)]
        .map((m) => m[0]);
      assert.deepStrictEqual(leaked, [],
        `a bracketed citation group rendered as text: ${leaked.join(", ")}. `
        + `A reader cannot open an id, and the id is not the source's name — `
        + `the chips beneath the card are the provenance`);
      await page.close();
    });

    /* The evidence list lives in the drilldown, so the gate has to open it —
       a provenance check that only reads the collapsed face is measuring the
       one state where there is nothing to measure. */
    const openFinding = async (page, title) => {
      const clicked = await page.evaluate((t) => {
        // Collapsed, a finding ROW's whole text is its title — the id chip
        // and the theme line are empty on a fixture that names neither — so
        // the exact-text match lands on the row, and the click handler is on
        // its CHILD. An earlier version of this walked only upwards from the
        // match and never fired anything.
        const row = [...document.querySelectorAll("div")]
          .find((n) => (n.textContent || "").trim() === t);
        if (!row) return false;
        row.setAttribute("data-qa-open", "1");   // survives the re-render
        const hit = [row, ...row.querySelectorAll("div")]
          .find((n) => getComputedStyle(n).cursor === "pointer");
        (hit || row).click();
        return true;
      }, title);
      assert.ok(clicked, `no row on this page is titled "${title}"`);
      await settle(page);
      return page.evaluate(() => {
        const row = document.querySelector("[data-qa-open]");
        const text = row ? row.innerText || "" : "";
        if (row) row.removeAttribute("data-qa-open");
        return text;
      });
    };

    await t.test("a finding that cites shows the sources it cites", async () => {
      const { page } = await open("overview");
      const text = await openFinding(page, LONG_TITLE);
      assert.ok(text, "the cited finding did not render at all");
      assert.ok(/E-CC-187/.test(text) && /E-CC-199/.test(text),
        "a finding citing two sources shows neither. The ids belong in the "
        + "evidence list even though they must never appear in the prose");
      assert.ok(/Annual report/.test(text),
        "the chip shows an id and not the source's name, so the id is doing "
        + "the naming — which is what a reader cannot use");
      await page.close();
    });

    await t.test("a citation that resolves to nothing says so", async () => {
      /* This card used to render "Evidence · click to view" over an empty
         list: the ids were dropped one `return null` at a time. A heading
         promising sources with nothing under it is indistinguishable from a
         bug, which is the whole complaint this round is about. */
      const { page } = await open("overview");
      const text = await openFinding(page, "A finding whose sources did not arrive");
      assert.ok(text, "the finding did not render");
      assert.ok(!/Evidence · click to view/.test(text),
        "a heading promises an evidence list and none of the ids resolve");
      assert.ok(/not among the evidence served/.test(text),
        "a finding citing a source this run does not serve renders neither "
        + "the sources nor the fact that they are missing");
      await page.close();
    });

    await t.test("a finding that cites nothing stays bare", async () => {
      const { page } = await open("overview");
      const text = await openFinding(page, "Fraud casework runs on a modern platform");
      assert.ok(!/E-CC-/.test(text),
        "a finding that cites nothing is showing evidence chips");
      assert.ok(!/not among the evidence served/.test(text),
        "a finding with no citations is being told its sources went missing");
      await page.close();
    });

    // ── ABBREVIATIONS, ON SCREEN ──────────────────────────────────────
    await t.test("no abbreviation reaches the page, chrome included", async () => {
      /* The payload gate (CG-27) reads payloads. It cannot see the app's own
         chrome, and that is where four of them were: the sidebar printed the
         role enum "AE" on every page of the product, the client bar printed
         "PROJECT API", and two card headings read "KPI". Found by reading a
         rendered page, which is the only place they exist. */
      const BARE = /\b(CU|FCU|NCUA|CFPB|CEO|CIO|COO|CTO|CISO|KPI|ROI|SLA|NPS|AE|API|UX|B2B|B2C)\b/;
      // A quoted source title and a verbatim excerpt carry whatever the source
      // wrote; rewriting either would misquote it.
      const QUOTED = /^\s*["“]|Testimony of |^\s*[A-Z][^.]{0,60} — /;
      for (const which of ["overview", "platform"]) {
        const { page } = await open(which);
        const hits = await page.evaluate(([bare, quoted]) => {
          const rx = new RegExp(bare), qx = new RegExp(quoted);
          return (document.body.innerText || "").split("\n")
            .filter((l) => rx.test(l) && !qx.test(l)).slice(0, 4);
        }, [BARE.source, QUOTED.source]);
        assert.deepStrictEqual(hits, [],
          `${which}: an abbreviation is on screen. Spell it out — the payload `
          + `gate cannot see the app's own chrome:\n  ${hits.join("\n  ")}`);
        await page.close();
      }
    });

    // ── TONE, ON SCREEN ───────────────────────────────────────────────
    await t.test("no accusatory line reaches the page from any card", async () => {
      /* AG-12 started life reading `starters` only, and the phrase that
         reached the live page — "What it cannot do is answer a question" —
         was on a platform-story tile one card away, read by the same person.
         The gate is wider now; this asserts the outcome rather than the
         gate. */
      const ACC = /do not quite line up|what it cannot do|you do not (have|know|track|measure)|fall(s|ing)? (short|behind)/i;
      for (const which of ["overview", "platform"]) {
        const { page } = await open(which);
        const hits = await page.evaluate((src) => {
          const rx = new RegExp(src, "i");
          return (document.body.innerText || "").split("\n")
            .filter((l) => rx.test(l)).slice(0, 3);
        }, ACC.source);
        assert.deepStrictEqual(hits, [],
          `${which}: a card makes the client the subject of a failure:\n  `
          + hits.join("\n  "));
        await page.close();
      }
    });

    // ── THE BAR THAT WOULD NOT DRAW ───────────────────────────────────
    await t.test("a rating with a numeric scale draws a filled bar", async () => {
      /* Reported three rounds running as "sentiment is still empty", and from
         the page it was: `scale: 5` parsed as no bound at all, so the rule
         that protects a reader from an unbounded rating blanked five bounded
         ones. */
      const { page } = await open("overview");
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(/4\.8|4\.75/.test(text) && /3\.7/.test(text),
        "the ratings do not render as figures");
      const filled = await page.evaluate(() =>
        [...document.querySelectorAll("[class*='bar'] *")]
          .filter((e) => e.getBoundingClientRect().width > 1).length);
      assert.ok(filled > 0,
        "every bar is an empty grey rail over a rating the payload states");
      await page.close();
    });

    await t.test("no record reaches a slot that wanted a word", async () => {
      for (const which of ["overview", "platform"]) {
        const { page } = await open(which);
        await assertNoStringifiedObjects(page, which);
        await page.close();
      }
    });
  } finally {
    await browser.close();
    server.close();
  }
});
