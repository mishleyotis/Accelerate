// Diagnostic: after auth + on the Directory page, dump every clickable
// element + its text so we can build a robust capture script.
import { chromium } from "@playwright/test";

async function waitForBoot(page) {
  await page.waitForFunction(
    () => !document.getElementById("__bundler_thumbnail"),
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () => !document.body.innerText.includes("Hydrating data layer"),
    { timeout: 60000 },
  );
  await page.waitForLoadState("networkidle", { timeout: 30000 });
  await page.waitForTimeout(800);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto("http://localhost:8082/");
  await waitForBoot(page);

  // Auth
  await page.getByRole("button", { name: /Continue with Google/i }).click();
  await page.waitForTimeout(2000);

  // Dump sidebar
  console.log("=== POST-AUTH (dashboard) ===");
  const navInfo = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll("button, a"));
    return all.map((e) => ({
      tag: e.tagName,
      text: e.textContent?.trim().slice(0, 50),
      href: e.getAttribute("href"),
      role: e.getAttribute("role"),
      aria: e.getAttribute("aria-label"),
    })).filter((x) => x.text && x.text.length > 0).slice(0, 40);
  });
  console.log(JSON.stringify(navInfo, null, 2));

  // Navigate to Clients
  await page.locator("button:has-text('Clients'), a:has-text('Clients')").first().click();
  await page.waitForTimeout(1500);
  console.log("=== /clients ===");
  const clientInfo = await page.evaluate(() => ({
    bodyTextHead: document.body.innerText.slice(0, 400),
    clickables: Array.from(document.querySelectorAll("button, a, [role='button'], tr, .card, .row"))
      .filter((e) => e.textContent && e.textContent.trim().length > 0)
      .slice(0, 25)
      .map((e) => ({
        tag: e.tagName,
        text: e.textContent?.trim().slice(0, 50),
        cls: e.className?.slice(0, 50),
      })),
  }));
  console.log(JSON.stringify(clientInfo, null, 2));

  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
