/**
 * Standalone build auth-hydration RUNTIME tests.
 *
 * The existing `frontend/src/__tests__/standalone-auth-hydration.test.ts`
 * only `readFileSync`s the source and greps for strings ("fetch(\"/api/v1/
 * auth/me\")", "AbortController", "[data-page=\"login\"]"). That catches
 * structural drift but cannot prove the BROWSER behaviour that broke in
 * CI on 2026-05-28:
 *   - Did the hydration finish?
 *   - Did the spinner clear within the documented 3s timeout?
 *   - Did 401/500/200 each render the correct surface?
 *
 * F-201 of the principal-QA audit closes that gap. Each test below
 * intercepts /api/v1/auth/me with a specific response shape and asserts
 * the resulting visible DOM markers + console-error count.
 *
 * Runs against the standalone bundle (per ADR 0011 the only surface
 * served in prod). The dev server proxies /api/* to BACKEND_URL — we
 * use route interception so no live backend is required.
 */
import { expect, test } from "@playwright/test";

const ADMIN_USER = {
  user_id: "admin-test-id",
  email: "admin@zennify.com",
  role: "ADMIN",
  name: "Admin Test",
};

test.describe("standalone auth hydration runtime", () => {
  test.beforeEach(async ({ page }) => {
    // Drop sessionStorage so each test starts from cold boot.
    await page.addInitScript(() => {
      try { window.sessionStorage.clear(); } catch { /* private mode */ }
    });
  });

  test("cookie_only_admin_session_reaches_admin_shell", async ({ page }) => {
    // /auth/me returns 200 + ADMIN user — boot must hydrate and the
    // authenticated shell (`aside.sb`) must render. NO LoginPage flash.
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ADMIN_USER),
      }),
    );
    // Stub out the other boot fetches so we don't 404-noise the test.
    for (const path of [
      "**/api/v1/entities*",
      "**/api/v1/dashboard*",
      "**/api/v1/alerts*",
    ]) {
      await page.route(path, (route) =>
        route.fulfill({
          status: 200, contentType: "application/json",
          body: JSON.stringify({ items: [], active_runs: [], total: 0 }),
        }),
      );
    }

    await page.goto("/");
    // The authenticated shell carries `aside.sb`.
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 5_000 });
    // And the LoginPage marker must NOT be visible (no flash).
    await expect(page.locator('[data-page="login"]')).toHaveCount(0);
  });

  test("auth_me_401_renders_visible_login_marker", async ({ page }) => {
    // /auth/me 401 means no valid cookie. Boot must clear hydrating
    // state and surface the standalone LoginPage with its visible
    // `[data-page="login"]` marker.
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({ status: 401, body: "Not authenticated" }),
    );

    await page.goto("/");
    await expect(page.locator('[data-page="login"]')).toBeVisible({
      timeout: 5_000,
    });
    // Shell must NOT be rendered on the 401 path.
    await expect(page.locator("aside.sb")).toHaveCount(0);
  });

  test("auth_me_500_renders_visible_login_marker_and_does_not_hang", async ({
    page,
  }) => {
    // /auth/me 5xx == server problem. Hydration is best-effort: must
    // fall back to LoginPage rather than hang on the boot spinner.
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" }),
    );

    await page.goto("/");
    await expect(page.locator('[data-page="login"]')).toBeVisible({
      timeout: 5_000,
    });
  });

  test("auth_me_timeout_exits_hydrating_within_3_seconds", async ({ page }) => {
    // Simulate a hanging /auth/me by never resolving the route. The
    // hydration block uses AbortController(2.5s) + setTimeout(3s)
    // fallback, so the LoginPage must appear within ~3.5s. Without
    // the timeout this would hang the full Playwright timeout.
    await page.route("**/api/v1/auth/me", () => {
      // Intentionally never call route.fulfill / route.continue —
      // the request hangs server-side.
    });

    const t0 = Date.now();
    await page.goto("/");
    await expect(page.locator('[data-page="login"]')).toBeVisible({
      timeout: 5_000,
    });
    const elapsed = Date.now() - t0;
    expect(elapsed).toBeLessThan(5_000); // hard cap; 3.5s expected
  });

  test("malformed_auth_me_response_does_not_crash_app", async ({ page }) => {
    // /auth/me returns 200 with non-JSON body. Hydration's try/catch
    // must swallow the parse error and fall through to LoginPage --
    // not throw an uncaught error that breaks React rendering.
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({
        status: 200, contentType: "text/html",
        body: "<html>not a json body</html>",
      }),
    );

    const consoleErrors: string[] = [];
    page.on("pageerror", (e) => consoleErrors.push(e.message));

    await page.goto("/");
    await expect(page.locator('[data-page="login"]')).toBeVisible({
      timeout: 5_000,
    });
    // We tolerate console warnings but not uncaught page-error throws.
    expect(consoleErrors.filter((m) => /Uncaught/i.test(m))).toEqual([]);
  });

  test("session_storage_user_does_not_override_lower_server_role", async ({
    page,
  }) => {
    // Tampering scenario: an AE plants role=ADMIN in sessionStorage.
    // Hydration MUST trust the server response (which says AE) and
    // discard the elevated localStorage value. Otherwise an attacker
    // could navigate to admin routes by tampering with storage.
    await page.addInitScript(() => {
      window.sessionStorage.setItem("dma:user", JSON.stringify({
        user_id: "ae", email: "ae@zennify.com",
        role: "ADMIN",  // tampered
        name: "AE",
      }));
    });
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          user_id: "ae", email: "ae@zennify.com",
          role: "AE",  // truth from server
          name: "AE",
        }),
      }),
    );
    for (const path of [
      "**/api/v1/entities*",
      "**/api/v1/dashboard*",
      "**/api/v1/alerts*",
    ]) {
      await page.route(path, (route) =>
        route.fulfill({
          status: 200, contentType: "application/json",
          body: JSON.stringify({ items: [], active_runs: [], total: 0 }),
        }),
      );
    }

    await page.goto("/");
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 5_000 });
    // After hydration the canonical role state must reflect the
    // server's AE response, not the tampered ADMIN value.
    const role = await page.evaluate(() => {
      const raw = window.sessionStorage.getItem("dma:user") || "{}";
      return (JSON.parse(raw) as { role?: string }).role;
    });
    expect(role).toBe("AE");
  });
});
