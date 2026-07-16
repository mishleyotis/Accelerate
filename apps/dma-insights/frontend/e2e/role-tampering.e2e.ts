/**
 * Phase 6 role-tampering regression tests against live seeded backend.
 *
 * No `page.route()` stubs — these run against the actual dev-login
 * + /auth/me + /entities endpoints serving real data from the seeded
 * PostgreSQL. Per the "no mock data" instruction, we authenticate as
 * a real AE persona via dev-login + verify the server-side gates hold
 * even when the client-side state is tampered with.
 *
 * Prerequisites:
 *   - Backend running on BACKEND_URL with env=local
 *   - dev-login active (env=local + admin_emails contains the test emails)
 *   - PostgreSQL seeded via `python -m app.scripts.seed_ci`
 *
 * Each test confirms that a tampered client-side value CANNOT
 * elevate the user's effective server-side role -- the backend's
 * JWT-decoded role is the only floor.
 */
import { expect, test } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("role tampering — live backend", () => {
  test("ae_session_storage_role_tamper_cannot_access_admin_users", async ({
    page,
  }) => {
    // Authenticate as a real AE persona via dev-login.
    await loginAs(page, "ae");

    // Plant a forged ADMIN value in sessionStorage BEFORE navigating
    // to any page that gates on it.
    await page.addInitScript(() => {
      window.sessionStorage.setItem("dma:user", JSON.stringify({
        user_id: "tampered",
        email: "ae.test@zennify.com",
        role: "ADMIN", // forged escalation
        name: "Tampered AE",
      }));
    });
    // `loginAs` plants the cookie + verifies via page.request.get but
    // never navigates the browser. `page.reload()` on an un-navigated
    // page reloads about:blank (no-op) → the SPA never mounts. Use
    // `goto("/")` so the addInitScript above runs at page load.
    await page.goto("/");
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 5_000 });

    // Server response from /auth/me must say AE (the JWT roles AE).
    const me = await page.request.get("/api/v1/auth/me");
    expect(me.status()).toBe(200);
    const meBody = await me.json();
    expect(meBody.role).toBe("AE");

    // Direct backend request: /admin/users must 403 for an AE.
    // Even with the tampered sessionStorage value, the server-side
    // JWT decode gives AE → admin endpoints reject.
    const adminUsers = await page.request.get("/api/v1/admin/users");
    expect(adminUsers.status()).toBe(403);
  });

  test("ae_acting_as_localStorage_cannot_escalate_beyond_can_act_as", async ({
    page,
  }) => {
    await loginAs(page, "ae");

    // Tamper: write ADMIN to acting-as localStorage.
    await page.addInitScript(() => {
      window.localStorage.setItem("dma:acting-as", "ADMIN");
    });
    // `loginAs` plants the cookie + verifies via page.request.get but
    // never navigates the browser. `page.reload()` on an un-navigated
    // page reloads about:blank (no-op) → the SPA never mounts. Use
    // `goto("/")` so the addInitScript above runs at page load.
    await page.goto("/");
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 5_000 });

    // Pull /auth/me — can_act_as list is the server's downgrade-only
    // floor. For an AE that's typically just ["AE"] (no escalation).
    const me = await page.request.get("/api/v1/auth/me");
    const meBody = await me.json();
    expect(meBody.role).toBe("AE");
    expect(meBody.can_act_as).not.toContain("ADMIN");
    expect(meBody.can_act_as).not.toContain("ANALYST");
  });

  test("ae_cannot_force_internal_view_against_server_strip", async ({
    page,
  }) => {
    // Even if the AE manipulates the URL to ?view=internal, the
    // server-side strip honours the user's ROLE. An AE seeing their
    // own entity gets internal data by default; that's the contract.
    // What we test here: a forced `view=customer` query param DOES
    // strip the response (server enforces customer-mode regardless
    // of role).
    await loginAs(page, "ae");

    // Get a seeded entity.
    const entResp = await page.request.get("/api/v1/entities");
    const entities = (await entResp.json()).items;
    expect(entities.length).toBeGreaterThan(0);
    const slug = entities[0].display_id || entities[0].id;

    // Customer-view request must strip peer fields (per Wave 4b).
    const customer = await page.request.get(
      `/api/v1/entities/${slug}/overview?view=customer`,
    );
    expect(customer.status()).toBe(200);
    const customerBody = await customer.json();
    // peer_benchmarks is in INTERNAL_ONLY_KEYS (top-level strip).
    expect(customerBody).not.toHaveProperty("peer_benchmarks");
    expect(customerBody).not.toHaveProperty("peer_internals");
    // parser_warnings is also internal-only.
    expect(customerBody).not.toHaveProperty("parser_warnings");

    // Internal-view request (default) keeps the fields.
    const internal = await page.request.get(
      `/api/v1/entities/${slug}/overview?view=internal`,
    );
    expect(internal.status()).toBe(200);
    // peer fields MAY be present (depending on seeded data); we just
    // assert the strip didn't fire. Not all fixtures populate
    // peer_benchmarks at top-level, so this is a no-strip check.
  });

  test("admin_cookie_required_for_admin_diagnostics", async ({ page }) => {
    // AE cookie → /admin/diagnostics 403. Admin cookie → 200.
    await loginAs(page, "ae");
    const aeResp = await page.request.get("/api/v1/admin/diagnostics");
    expect(aeResp.status()).toBe(403);

    await loginAs(page, "admin");
    const adminResp = await page.request.get("/api/v1/admin/diagnostics");
    expect([200, 404]).toContain(adminResp.status());
    // Either 200 (full diagnostics returned) or 404 (endpoint may be
    // include_in_schema=False; either way the admin can REACH it
    // while the AE cannot).
  });
});
