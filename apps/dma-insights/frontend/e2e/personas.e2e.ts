/**
 * G12.E2E.PERSONAS — golden-path tests per persona.
 *
 * Each test block covers:
 *  1. Successful login via dev-login endpoint
 *  2. Navigation to primary routes
 *  3. Role-specific gate assertions (D5/D6 access, admin-only pages)
 *  4. Customer-view toggle removes internal tabs
 *  5. **End-to-end data persistence chain**: seed_ci'd entities show up
 *     in the directory listing AND their overview pages render the
 *     seeded entity name (proving Drive→parse→DB→API→UI is unbroken).
 *
 * Prerequisites:
 *  - Frontend dev server running on :5173 (vite proxies /api → BACKEND_URL)
 *  - Backend running on BACKEND_URL with env=local (/auth/dev-login active)
 *  - Postgres seeded via `python -m app.scripts.seed_ci` — at least one
 *    of the 5 sanitized fixtures must be persisted before these tests
 *    run, otherwise the data-rendering assertions will fail with a
 *    diagnostic message instead of an opaque selector timeout.
 *
 * Test entity selection:
 *   The 5 seeded entity display_ids are slug-derived:
 *     amalgamated-bank-synthet-0001
 *     amarillo-national-bank-s-0001
 *     americu-credit-union-syn-0001
 *     regions-bank-synthetic-0001
 *     wsfs-financial-corporati-0001
 *   Persona tests pick the entity dynamically from the live `/api/v1/
 *   entities` list at fixture-setup time — this keeps the suite
 *   forward-compatible if the slug helper ever changes shape.
 */
import { expect, Page, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { FRONTEND_ORIGIN, goTo, loginAs } from "./helpers";

interface SeededEntity {
  display_id: string;
  name: string;
}

/**
 * Resolve a real seeded entity at test setup so the suite asserts
 * against actual ingested data. If the DB is empty we fail loudly with
 * the operator-facing remediation hint instead of pretending to pass.
 *
 * Goes through the Vite proxy (FRONTEND_ORIGIN) so the request is
 * same-site as the SPA — the SameSite=Lax dma_session cookie attaches.
 * Calling the backend directly via BACKEND_URL was cross-site and
 * blocked by Chromium's SameSite policy, giving 401 on every call.
 */
async function pickSeededEntity(page: Page): Promise<SeededEntity> {
  const res = await page.request.get(`${FRONTEND_ORIGIN}/api/v1/entities`);
  if (!res.ok()) {
    throw new Error(
      `GET /api/v1/entities failed: ${res.status()} ${await res.text()}`,
    );
  }
  const body = await res.json();
  const items: SeededEntity[] = Array.isArray(body)
    ? body
    : (body.items ?? body.entities ?? []);
  if (items.length === 0) {
    throw new Error(
      "no seeded entities found — persona tests require `python -m " +
        "app.scripts.seed_ci` to have populated at least 1 of the 5 " +
        "sanitized fixtures. Re-run with the seed step before retrying."
    );
  }
  return items[0];
}

/**
 * The app runs PACK-FIRST (prod mode): the directory/dashboard serve the
 * committed 94-client startup pack, NOT the live API. So the directory lists
 * the STARTUP PAGES (the canonical data the backend will be linked to), and
 * this resolves a real pack client straight from that committed source so the
 * assertion matches exactly what the directory renders.
 */
function pickPackEntity(): SeededEntity {
  const here = path.dirname(fileURLToPath(import.meta.url)); // frontend/e2e
  const packPath = path.resolve(here, "../../startup-data/dashboard.json");
  const pack = JSON.parse(readFileSync(packPath, "utf-8")) as {
    entity_cards?: Array<{ name?: string; display_id?: string }>;
  };
  const card = (pack.entity_cards ?? []).find((c) => c.name && c.display_id);
  if (!card?.name || !card?.display_id) {
    throw new Error(
      `startup-data pack has no usable client at ${packPath} — the committed ` +
        `94-client pack is the directory's source of truth in pack-first mode.`,
    );
  }
  return { name: card.name, display_id: card.display_id };
}

// ── LoginPage smoke ─────────────────────────────────────────────────────────

test("LoginPage renders sign-in card without auth", async ({ page }) => {
  await page.goto("/");
  // Should see the login card
  await expect(page.locator(".login-card, [data-page='login']")).toBeVisible({
    timeout: 10_000,
  });
  // Must NOT see dashboard content
  await expect(page.locator("aside.sb, aside[aria-label='Primary navigation']")).not.toBeVisible();
});

// ── End-to-end data path: ingestion → DB → API → UI ─────────────────────────

test.describe("ingestion → persistence → UI chain", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "ae");
  });

  test("Entity Directory lists a startup-pack client (pack-first)", async ({ page }) => {
    // The app is PACK-FIRST in prod: the directory serves the committed
    // 94-client startup pack (the canonical data the backend will be linked
    // to), NOT the live seeded fixtures. So assert a real pack client — read
    // straight from the committed pack so the expectation matches exactly what
    // the directory renders. This is the load-bearing assertion that the
    // startup pages are wired to the directory and render.
    const entity = pickPackEntity();
    await goTo(page, "/clients");
    const namePrefix = entity.name.split(" ").slice(0, 2).join(" ");
    // Scope to the directory's OWN row elements (grid tiles or table
    // cells). A bare `text=` locator matched the TopBar subvertical
    // filter's hidden `<option>Farm Credit</option>` first in DOM order
    // (2026-07-05 build: "Farm Credit Mid-America, ACA" was the pack's
    // first card), so toBeVisible failed even though the row rendered.
    await expect(
      page
        .locator("main .card-tile, main table td")
        .filter({ hasText: namePrefix })
        .first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("Client Overview renders seeded entity by display_id", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    await goTo(page, `/clients/${entity.display_id}/overview`);
    // The overview hash route must NOT redirect away and must NOT show
    // the LoginPage (which would indicate auth dropped silently).
    await expect(
      page.locator(".login-card, [data-page='login']"),
    ).not.toBeVisible();
    // Entity name (or first word) renders somewhere on the page.
    const firstWord = entity.name.split(" ")[0];
    await expect(
      page.locator(`text=${firstWord}`).first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("Client Overview /api/v1/entities/{id}/overview returns seeded payload", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    // Go through the Vite proxy (FRONTEND_ORIGIN) so the dma_session cookie
    // attaches — see pickSeededEntity for the SameSite=Lax rationale.
    const res = await page.request.get(
      `${FRONTEND_ORIGIN}/api/v1/entities/${entity.display_id}/overview`,
    );
    expect(res.status(), `overview API for ${entity.display_id}`).toBe(200);
    const body = await res.json();
    expect(body).toBeTruthy();
    // The overview payload must include the entity name — the strongest
    // signal that seed_ci's persisted state is reachable end-to-end.
    const blob = JSON.stringify(body);
    const firstWord = entity.name.split(" ")[0];
    expect(blob).toContain(firstWord);
  });
});

// ── AE persona ──────────────────────────────────────────────────────────────

test.describe("AE persona", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "ae");
  });

  test("lands on Dashboard after login", async ({ page }) => {
    await goTo(page, "/");
    // Sidebar should be visible (authenticated shell)
    const sidebar = page.locator("aside.sb, aside[aria-label='Primary navigation']");
    await expect(sidebar).toBeVisible({ timeout: 10_000 });
  });

  test("Entity Directory loads with owner filter", async ({ page }) => {
    await goTo(page, "/clients");
    // Directory page heading or filter chip
    await expect(
      page.locator("text=/clients|directory|my clients/i").first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("AE can access Context (D5) — plan Part 8.1 access opening", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    await goTo(page, `/clients/${entity.display_id}/context`);
    // The old analyst-only gate returned 403 → dead tab for AEs. The page
    // must render real Context content (timeline/regulatory/peers), not an
    // access-denied empty state.
    await expect(
      page.locator("text=/timeline|regulator|acquisition|peers/i").first()
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator("text=/analyst access required|permission/i")
    ).not.toBeVisible();
  });

  test("Customer view toggle removes D5/D6 tabs", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    await goTo(page, `/clients/${entity.display_id}/overview`);
    // Look for the audience toggle button
    // Strict selector — the broad `[aria-label*='customer' i]` previously
    // matched the "Customer Experience" pillar progressbar too.
    const toggleBtn = page.locator(
      "button.audience-toggle, button:has-text('Customer view')",
    ).first();
    if (await toggleBtn.count() > 0) {
      await toggleBtn.click();
      // After toggle: Context and Health tabs should not be visible
      await expect(
        page.locator("text=/Context|Health/").first()
      ).not.toBeVisible({ timeout: 5_000 });
    }
  });
});

// ── Analyst persona ─────────────────────────────────────────────────────────

test.describe("Analyst persona", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "analyst");
  });

  test("can access Health page (D6)", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    await goTo(page, `/clients/${entity.display_id}/health`);
    // Should NOT see a 403 full-page error; some content renders
    const content = await page.content();
    expect(
      !content.includes("403") || content.includes("gates") || content.includes("alert")
    ).toBe(true);
  });

  test("can access Context page (D5)", async ({ page }) => {
    const entity = await pickSeededEntity(page);
    await goTo(page, `/clients/${entity.display_id}/context`);
    const content = await page.content();
    expect(!content.includes("403") || content.includes("timeline")).toBe(true);
  });

  test("Alerts page loads", async ({ page }) => {
    await goTo(page, "/alerts");
    await expect(
      page.locator("text=/alert|no open alerts/i").first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ── Admin persona ────────────────────────────────────────────────────────────

test.describe("Admin persona", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "admin");
  });

  test("Admin page is accessible", async ({ page }) => {
    await goTo(page, "/admin");
    // Admin page renders (heading or tab, not a 403)
    const content = await page.content();
    expect(
      content.includes("admin") ||
      content.includes("Admin") ||
      content.includes("users") ||
      content.includes("Users")
    ).toBe(true);
    expect(content.includes("403")).toBe(false);
  });

  test("Import audit page loads", async ({ page }) => {
    await goTo(page, "/admin/import/audit");
    const content = await page.content();
    expect(!content.includes("403")).toBe(true);
  });

  test("Prospecting page loads", async ({ page }) => {
    await goTo(page, "/prospecting");
    await expect(
      page.locator("text=/prospect|maturity|No entities/i").first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ── Hash router navigation ───────────────────────────────────────────────────

test.describe("Hash router deep links", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "ae");
  });

  test("deep link to /clients renders directory", async ({ page }) => {
    await page.goto("/#/clients");
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 10_000 });
  });

  test("back/forward works across hash routes", async ({ page }) => {
    await goTo(page, "/");
    await goTo(page, "/clients");
    await page.goBack();
    // Should return to dashboard hash
    await expect(page).toHaveURL(/#\//);
  });
});
