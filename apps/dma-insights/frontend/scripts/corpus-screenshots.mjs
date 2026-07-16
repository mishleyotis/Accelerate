/**
 * Full-corpus screenshot sweep (2026-06-10 final tests).
 *
 * Captures, for EVERY ACTIVE entity, all 8 client pages, plus —
 * on a rotating per-entity basis so every interaction surface is
 * proven across many different entities — the interaction states:
 * heatmap zoom ladder + view modes + synthesis drawer, platform
 * roadmap views + drilldowns, insight modal, evidence drawer,
 * run-selector / settings / notifications popovers, customer
 * audience toggle, and the global pages (dashboard, directory,
 * alerts, prospecting, admin).
 *
 * Usage:
 *   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node scripts/corpus-screenshots.mjs <cookie> [shard]/[nshards]
 * Output: /tmp/corpus_shots/<entity>/<page>[-<state>].png
 *         /tmp/corpus_shots/_global/*.png
 *         /tmp/corpus_shots/summary.json
 */
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const COOKIE = process.argv[2];
if (!COOKIE) throw new Error("pass the dma_session cookie as argv[2]");
const [SHARD, NSHARDS] = (process.argv[3] || "1/1").split("/").map(Number);

const APP = "http://127.0.0.1:5173";
const OUT = "/tmp/corpus_shots";
mkdirSync(OUT, { recursive: true });

const summary = { pages: 0, states: 0, failures: [] };
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.addCookies([
  { name: "dma_session", value: COOKIE, domain: "127.0.0.1", path: "/" },
]);
const page = await ctx.newPage();
page.setDefaultTimeout(15000);

async function settle() {
  try {
    await page.waitForFunction(
      () => {
        const main = document.querySelector("main") || document.body;
        const txt = (main.textContent || "").trim();
        const skel = main.querySelectorAll(".skel, [data-loading]").length;
        return txt.length > 40 && skel === 0;
      },
      { timeout: 12000 },
    );
  } catch { /* capture whatever rendered — the screenshot is the evidence */ }
  await page.waitForTimeout(350);
}

async function shot(file) {
  await page.screenshot({ path: file, fullPage: true });
  summary.pages += 1;
}

async function go(route, file) {
  try {
    await page.goto(`${APP}/#${route}`, { waitUntil: "domcontentloaded" });
    await settle();
    await shot(file);
    return true;
  } catch (e) {
    summary.failures.push(`${route}: ${String(e).slice(0, 120)}`);
    return false;
  }
}

async function tryState(label, file, fn) {
  try {
    await fn();
    await page.waitForTimeout(450);
    await page.screenshot({ path: file, fullPage: false });
    summary.states += 1;
    return true;
  } catch (e) {
    summary.failures.push(`${label}: ${String(e).slice(0, 140)}`);
    return false;
  }
}

// ── entity list from the API ─────────────────────────────────────────
const resp = await ctx.request.get(
  `${APP}/api/v1/entities?limit=200`,
  { headers: { Cookie: `dma_session=${COOKIE}` } },
);
const all = (await resp.json()).items.filter((e) => e.status === "ACTIVE");
const ents = all.filter((_, i) => i % NSHARDS === SHARD - 1);
console.log(`entities: ${ents.length} (shard ${SHARD}/${NSHARDS} of ${all.length})`);

const PAGES = ["overview", "insights", "heatmap", "platform", "context",
  "health", "techstack", "runs"];

let idx = 0;
for (const e of ents) {
  idx += 1;
  const did = e.display_id;
  const dir = `${OUT}/${did}`;
  mkdirSync(dir, { recursive: true });

  for (const p of PAGES) {
    await go(`/clients/${did}/${p}`, `${dir}/${p}.png`);
  }

  // Rotate deep interaction-state capture across the corpus so every
  // surface is exercised against MANY entities without 95×every-state
  // blow-up: each entity gets one state-family by index, and the first
  // 3 entities get the full set.
  const fam = idx <= 3 ? "all" : ["heatmap", "platform", "insights", "drawers", "audience"][idx % 5];

  if (fam === "all" || fam === "heatmap") {
    await go(`/clients/${did}/heatmap`, `${dir}/heatmap-pillar.png`);
    // zoom ladder: click first pillar cell → category → capability → subcap
    for (const [state, sel] of [
      ["zoom-category", ".hm-cell"],
      ["zoom-capability", ".hm-cell"],
      ["zoom-subcap", ".hm-cell"],
    ]) {
      await tryState(`${did} hm ${state}`, `${dir}/heatmap-${state}.png`, async () => {
        await page.locator(sel).first().click();
        await page.waitForTimeout(500);
      });
    }
    // synthesis drawer on a subcap cell
    await tryState(`${did} hm drawer`, `${dir}/heatmap-synthesis-drawer.png`, async () => {
      await page.locator(".hm-cell").first().click();
      await page.waitForSelector('[role="dialog"], .drawer', { timeout: 6000 });
    });
    await page.keyboard.press("Escape").catch(() => {});
    // view modes
    for (const mode of ["focus", "value_chain"]) {
      await tryState(`${did} hm mode ${mode}`, `${dir}/heatmap-mode-${mode}.png`, async () => {
        await page.goto(`${APP}/#/clients/${did}/heatmap`);
        await settle();
        const btn = page.getByRole("button", {
          name: mode === "focus" ? /focus/i : /value/i }).first();
        await btn.click();
        await page.waitForTimeout(700);
      });
    }
    // peer + issues overlays
    await tryState(`${did} hm overlays`, `${dir}/heatmap-overlays.png`, async () => {
      await page.goto(`${APP}/#/clients/${did}/heatmap`);
      await settle();
      for (const name of [/peer/i, /issue/i]) {
        const sw = page.getByRole("button", { name }).or(
          page.locator("label", { hasText: name })).first();
        await sw.click({ timeout: 3000 }).catch(() => {});
      }
      await page.waitForTimeout(600);
    });
  }

  if (fam === "all" || fam === "platform") {
    await go(`/clients/${did}/platform`, `${dir}/platform-base.png`);
    // select each platform card (first 3)
    await tryState(`${did} platform card-select`, `${dir}/platform-card-selected.png`, async () => {
      await page.locator(".card-tile").nth(1).click();
    });
    // roadmap views
    for (const view of ["chevron", "curve", "impact"]) {
      await tryState(`${did} roadmap ${view}`, `${dir}/platform-roadmap-${view}.png`, async () => {
        const rx = { chevron: /chevron|phase/i, curve: /curve|step/i, impact: /impact|customer/i }[view];
        await page.getByRole("button", { name: rx }).first().click();
        await page.waitForTimeout(500);
      });
    }
  }

  if (fam === "all" || fam === "insights") {
    await go(`/clients/${did}/insights`, `${dir}/insights-base.png`);
    await tryState(`${did} insight modal`, `${dir}/insights-modal.png`, async () => {
      await page.locator(".ic, [data-insight-card]").first().click();
      await page.waitForSelector('[role="dialog"]', { timeout: 6000 });
    });
    await page.keyboard.press("Escape").catch(() => {});
    await tryState(`${did} insights filtered`, `${dir}/insights-filtered.png`, async () => {
      const sel = page.locator("select").first();
      await sel.selectOption({ index: 1 });
      await page.waitForTimeout(500);
    });
  }

  if (fam === "all" || fam === "drawers") {
    await go(`/clients/${did}/overview`, `${dir}/overview-base.png`);
    await tryState(`${did} evidence drawer`, `${dir}/overview-evidence-drawer.png`, async () => {
      await page.locator('[data-evidence-chip], .ev-chip, .chip').first().click();
      await page.waitForSelector('[role="dialog"], .drawer', { timeout: 6000 });
    });
    await page.keyboard.press("Escape").catch(() => {});
    await tryState(`${did} scqa expand`, `${dir}/overview-scqa-expanded.png`, async () => {
      await page.getByRole("button", { name: /read full|expand/i }).first().click();
    });
    await tryState(`${did} run selector`, `${dir}/chrome-run-selector.png`, async () => {
      await page.getByRole("button", { name: /DMA-|REQ-/ }).first().click();
      await page.waitForTimeout(400);
    });
  }

  if (fam === "all" || fam === "audience") {
    await go(`/clients/${did}/overview`, `${dir}/overview-internal.png`);
    await tryState(`${did} customer audience`, `${dir}/overview-customer.png`, async () => {
      await page.getByRole("button", { name: /customer/i }).first().click();
      await page.waitForTimeout(2500);
      // must settle — not an endless spinner
      const txt = await page.locator("main").textContent();
      if (!txt || txt.trim().length < 30) throw new Error("customer view blank");
    });
    await page.getByRole("button", { name: /internal/i }).first()
      .click({ timeout: 3000 }).catch(() => {});
  }

  console.log(`[${idx}/${ents.length}] ${did} done`);
}

// ── globals (once) ───────────────────────────────────────────────────
if (SHARD === 1) {
  const g = `${OUT}/_global`;
  mkdirSync(g, { recursive: true });
  await go("/", `${g}/dashboard.png`);
  await go("/clients", `${g}/directory.png`);
  await tryState("directory table view", `${g}/directory-table.png`, async () => {
    await page.getByRole("button", { name: /table|list/i }).first().click();
  });
  await go("/alerts", `${g}/alerts.png`);
  await go("/prospecting", `${g}/prospecting.png`);
  await go("/admin", `${g}/admin.png`);
  await go("/admin/import/audit", `${g}/admin-import-audit.png`);
  // topbar popovers
  await tryState("search popover", `${g}/popover-search.png`, async () => {
    await page.keyboard.press("Meta+k").catch(() => {});
    await page.getByPlaceholder(/search/i).first().click({ timeout: 3000 });
  });
  await tryState("settings popover", `${g}/popover-settings.png`, async () => {
    await page.locator('[aria-label*="settings" i], [title*="settings" i]').first().click();
  });
  await tryState("notifications popover", `${g}/popover-notifications.png`, async () => {
    await page.locator('[aria-label*="notification" i], [title*="notification" i]').first().click();
  });
}

writeFileSync(`${OUT}/summary-${SHARD}.json`, JSON.stringify(summary, null, 1));
console.log(`DONE pages=${summary.pages} states=${summary.states} failures=${summary.failures.length}`);
for (const f of summary.failures.slice(0, 40)) console.log("  fail:", f);
await browser.close();
