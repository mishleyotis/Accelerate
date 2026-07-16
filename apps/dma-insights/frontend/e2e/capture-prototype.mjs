// Capture prototype screenshots at 1440px for all 12 routes by driving
// the prototype's interactive flow: wait for SPA boot, click "Continue
// with Google" mock auth, then click each sidebar item to navigate.
//
// The uploaded prototype is a self-contained bundler HTML that:
//   1. Renders __bundler_thumbnail SVG immediately
//   2. Babel-transforms the embedded type=text/babel script
//   3. Decompresses gzipped React + page bundle via DecompressionStream
//   4. Mounts a React app on a loading state ("Hydrating data layer…")
//   5. Becomes interactive (login screen visible) only after step 4
//   6. After login click, the post-auth shell renders with sidebar nav
//
// Output: /tmp/proto-shots/proto-<route>-1440.png for every route.
import { chromium } from "@playwright/test";

const FROZEN_ISO = "2026-01-15T09:00:00.000Z";

// Sidebar items the prototype renders post-login. Keys map to our
// route names so paired diffs against the React baselines work. The
// prototype renders alert counts inline ("Alerts108"); regexes account
// for that.
const NAV_ITEMS = [
  { name: "dashboard",   text: /^Dashboard$/i },
  { name: "directory",   text: /^Clients$/i },
  { name: "alerts",      text: /^Alerts\d*$/i },
  { name: "prospecting", text: /^Prospecting$/i },
];

// Admin is role-gated in the prototype; the default user is ANALYST.
// We try the role switcher and fall through silently if the prototype
// doesn't expose admin-mode without code changes.
const ADMIN_ROLE_SWITCH_TEXTS = [/ADMIN/i, /Admin home/i];

// Within a client (clicked from the directory), the inner tabs are:
const CLIENT_TABS = [
  { name: "overview",  text: /^Overview$/i },
  { name: "insights",  text: /^Insights$/i },
  { name: "heatmap",   text: /^Heatmap$/i },
  { name: "platform",  text: /^Platform$/i },
  { name: "context",   text: /^Context$/i },
  { name: "health",    text: /^Health$/i },
];

async function waitForBoot(page) {
  // Stage 1: bundler thumbnail removed.
  await page.waitForFunction(
    () => !document.getElementById("__bundler_thumbnail"),
    { timeout: 60000 },
  );
  // Stage 2: loading state text gone (SPA hydrated).
  await page.waitForFunction(
    () => !document.body.innerText.includes("Hydrating data layer"),
    { timeout: 60000 },
  );
  // Stage 3: networkidle for any final beat.
  await page.waitForLoadState("networkidle", { timeout: 30000 });
  await page.waitForTimeout(800);
}

async function snap(page, name) {
  const outPath = `/tmp/proto-shots/proto-${name}-1440.png`;
  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`  → ${outPath}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.clock.install({ time: new Date(FROZEN_ISO) });

  await page.goto("http://localhost:8082/");
  console.log("waiting for prototype boot...");
  await waitForBoot(page);
  console.log("booted; capturing login");
  await snap(page, "login");

  // Click the mock-auth button.
  const continueBtn = page.getByRole("button", { name: /Continue with Google/i });
  if (await continueBtn.count() === 0) {
    console.error("Continue button missing; dumping body text:");
    console.error(await page.locator("body").innerText());
    process.exit(1);
  }
  await continueBtn.click();
  await page.waitForTimeout(2000);
  console.log("authed");

  // Capture each global page.
  for (const item of NAV_ITEMS) {
    const link = page.getByRole("button", { name: item.text }).or(
                  page.getByRole("link", { name: item.text }));
    if (await link.count() === 0) {
      console.log(`  ! ${item.name}: nav item not found, skipping`);
      continue;
    }
    await link.first().click();
    await page.waitForTimeout(1500);
    console.log(`captured ${item.name}`);
    await snap(page, item.name);
  }

  // For client-detail tabs we need to drill into one client first.
  await page.getByRole("button", { name: /^Clients$/i }).first().click();
  await page.waitForTimeout(1500);
  // The prototype renders entity rows as `.dir-row` (per the
  // .proto.tsx). Fall back to clicking the first heading text if the
  // class doesn't match.
  let drilled = false;
  for (const sel of [".dir-row", ".entity-card", "[data-entity-id]", "a[href*='/clients/']"]) {
    const loc = page.locator(sel).first();
    if (await loc.count() > 0) {
      await loc.click();
      drilled = true;
      console.log(`drilled into first entity via ${sel}`);
      break;
    }
  }
  if (!drilled) {
    // Last resort: click the first h2 / h3 inside the main panel.
    const h = page.locator("main h2, main h3, main strong").first();
    if (await h.count() > 0) {
      await h.click();
      drilled = true;
      console.log("drilled into first entity via main heading click");
    }
  }
  if (drilled) {
    await page.waitForTimeout(2000);
    for (const tab of CLIENT_TABS) {
      const tabEl = page.getByRole("tab", { name: tab.text }).or(
                     page.getByRole("button", { name: tab.text }));
      if (await tabEl.count() === 0) {
        console.log(`  ! ${tab.name}: tab not found, skipping`);
        continue;
      }
      await tabEl.first().click();
      await page.waitForTimeout(1500);
      console.log(`captured ${tab.name}`);
      await snap(page, tab.name);
    }
  } else {
    console.log("  ! no entity row could be clicked");
  }

  // Try admin via role-switcher (best-effort; the prototype's role
  // gating may not expose ADMIN cleanly).
  const settingsBtn = page.locator(".user-chip, .settings-btn, [aria-label='Account']").first();
  if (await settingsBtn.count() > 0) {
    await settingsBtn.click();
    await page.waitForTimeout(500);
    for (const re of ADMIN_ROLE_SWITCH_TEXTS) {
      const opt = page.getByRole("button", { name: re }).or(page.getByRole("menuitem", { name: re }));
      if (await opt.count() > 0) {
        await opt.first().click();
        await page.waitForTimeout(1500);
        console.log("switched to ADMIN");
        // Now click admin nav item if it appeared
        const adminItem = page.getByRole("button", { name: /Admin home|^Admin$/i }).first();
        if (await adminItem.count() > 0) {
          await adminItem.click();
          await page.waitForTimeout(1500);
          await snap(page, "admin");
          console.log("captured admin");
        }
        break;
      }
    }
  }

  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
