/**
 * Shared helpers for E2E persona tests.
 *
 * `loginAs()` provisions an authenticated session for a persona before any
 * SPA navigation. The implementation is fully deterministic:
 *
 *   1. POST `/api/v1/auth/dev-login` directly to BACKEND_URL — we do NOT
 *      rely on Vite's proxy to round-trip the Set-Cookie back to the
 *      browser. The proxy step worked in dev but was flaky in CI
 *      (mcr.microsoft.com/playwright:v1.49.0-jammy): the response cookie
 *      sometimes appeared in `page.context().cookies()` yet did NOT
 *      attach to the SPA's subsequent same-origin `fetch('/api/v1/auth/me')`
 *      calls, so whoAmI() returned null and the App rendered LoginPage.
 *      Symptoms: every authenticated-shell assertion (sidebar visible,
 *      AdminPage rendered, /clients directory loaded) failed in CI while
 *      passing locally. The proxy/APIRequestContext interaction with
 *      Chromium's response-cookie store is the variable; bypassing it
 *      removes the variable.
 *
 *   2. Parse the JWT from the Set-Cookie response header.
 *
 *   3. Inject the cookie into the BrowserContext via `addCookies` using
 *      Playwright's `url:` form — this is the documented-stable shape
 *      Playwright recommends for synthetic cookie placement. Cookies set
 *      this way are treated as first-party by Chromium and attach to all
 *      subsequent fetches from the matching origin. A previous attempt
 *      using the `domain:` form (`{domain:"localhost", path:"/", ...}`)
 *      was rejected by Chromium for non-FQDN domains; `url:` derives the
 *      attributes from the URL itself and avoids that pitfall.
 *
 *   4. When BACKEND_URL is on a different host than FRONTEND_ORIGIN
 *      (CI: dma-ci-e2e-backend vs localhost), mirror the cookie to the
 *      backend host too so any direct `page.request.*(BACKEND/...)`
 *      calls in tests carry auth as well. (We try to avoid those —
 *      `pickSeededEntity()` uses the proxy path now — but defence in
 *      depth keeps PDF/API tests working.)
 *
 *   5. Verify auth by calling `/api/v1/auth/me` via the SPA's same-origin
 *      path. If this returns non-200, throw with diagnostic context.
 *      Without this gate, every downstream assertion would fail far from
 *      the root cause; with it, loginAs itself reports the auth state
 *      that broke and dumps the cookie jar.
 */
import { Page } from "@playwright/test";

// Honour BACKEND_URL env var so CI can point at a sidecar container
// (e.g. http://dma-ci-e2e-backend:8000 on Cloud Build's `cloudbuild`
// network). Falls back to localhost for the dev workflow where the
// operator runs `uvicorn` themselves on port 8000.
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

// Vite dev server origin — Playwright config sets this as baseURL too.
export const FRONTEND_ORIGIN = "http://localhost:5173";

export const PERSONAS = {
  admin: "mishley.otiende@zennify.com",
  analyst: "richard.odhiambo@zennify.com",
  ae: "ae.test@zennify.com",
} as const;

export type Persona = keyof typeof PERSONAS;


/** Extract the JWT value from a Set-Cookie response header (string or array). */
function extractJwt(setCookie: string | string[] | undefined): string {
  if (!setCookie) {
    throw new Error("dev-login response had no Set-Cookie header");
  }
  const headers = Array.isArray(setCookie) ? setCookie : [setCookie];
  for (const h of headers) {
    const m = /(?:^|,\s*|;\s*)dma_session=([^;,\s]+)/.exec(h);
    if (m) return m[1];
  }
  throw new Error(`dev-login Set-Cookie did not contain dma_session: ${headers.join(" | ")}`);
}


export async function loginAs(page: Page, persona: Persona): Promise<void> {
  const email = PERSONAS[persona];

  // 1. Wipe any leftover dma_session from a prior test in this context.
  await page.context().clearCookies({ name: "dma_session" });

  // 2. POST dev-login directly to BACKEND (NOT through the Vite proxy).
  //    We need full control over cookie placement; relying on proxied
  //    Set-Cookie was the CI flake source (see file header).
  const res = await page.request.post(`${BACKEND}/api/v1/auth/dev-login`, {
    params: { email },
  });
  if (!res.ok()) {
    throw new Error(
      `dev-login for ${email} returned ${res.status()}: ${await res.text()}`,
    );
  }

  // 3. Parse the JWT from the Set-Cookie response header.
  const jwt = extractJwt(res.headers()["set-cookie"]);

  // 4. Inject the cookie into the BrowserContext for the SPA origin
  //    (URL form derives domain/path/secure deterministically). Also
  //    mirror to the backend host if it differs, so tests that hit
  //    BACKEND directly remain authenticated.
  const cookies: Parameters<typeof page.context.prototype.addCookies>[0] = [
    {
      name: "dma_session",
      value: jwt,
      url: FRONTEND_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ];
  const backendHost = new URL(BACKEND).hostname;
  const frontendHost = new URL(FRONTEND_ORIGIN).hostname;
  if (backendHost !== frontendHost) {
    cookies.push({
      name: "dma_session",
      value: jwt,
      url: BACKEND,
      httpOnly: true,
      sameSite: "Lax",
    });
  }
  await page.context().addCookies(cookies);

  // 5. Verify the cookie ATTACHES to fetches before any test code
  //    depends on it. Hitting /api/v1/auth/me via the SPA's proxy
  //    path is the exact same path the SPA's whoAmI() will use on
  //    mount — if this succeeds, the SPA boot will succeed too.
  //    If it fails, throw with full diagnostic context so the test
  //    log points at the real failure, not at the symptom 10 lines
  //    later.
  const meRes = await page.request.get(`${FRONTEND_ORIGIN}/api/v1/auth/me`);
  if (!meRes.ok()) {
    const ctxCookies = await page.context().cookies();
    throw new Error(
      `auth verification FAILED: GET /api/v1/auth/me returned ` +
      `${meRes.status()} ${await meRes.text()} after loginAs(${persona}). ` +
      `Cookies in context: ${JSON.stringify(
        ctxCookies.map((c) => ({
          name: c.name,
          domain: c.domain,
          path: c.path,
          httpOnly: c.httpOnly,
          sameSite: c.sameSite,
          secure: c.secure,
        })),
      )}. BACKEND=${BACKEND}, FRONTEND_ORIGIN=${FRONTEND_ORIGIN}`,
    );
  }
}

/** Navigate to a hash route and wait for the SPA to FINISH booting.
 *
 * Wait for one of the visible post-boot markers:
 *   - `aside.sb`             → authenticated layout (cookie valid → signIn)
 *   - `main.login-card`      → Vite-tree LoginPage root
 *   - `[data-page="login"]`  → standalone-src LoginPage outer container
 *   - `[data-page="boot"]`   → optional explicit hydrating marker (future)
 *
 * 2026-05-28 audit fix: the previous list included `#gis-script` —
 * but that's a <script> tag injected into <head> (see
 * `frontend/standalone-src/src/pages-auth-dashboard-directory.jsx:28`
 * where `s.id = "gis-script"`). Playwright's `waitForSelector` defaults
 * to `state: 'visible'` and a script tag is never visible, so this
 * selector NEVER matched and the helper hung for the full 15s timeout
 * any time the SPA happened to render the login state.
 *
 * On timeout this helper now dumps a full diagnostic snapshot:
 *   - current URL + document.title
 *   - body innerText excerpt
 *   - marker visibility for each candidate selector + `#gis-script` (attached only)
 *   - last 10 page errors / console errors
 *   - response statuses for /api/v1/auth/me + /api/v1/admin/users
 * That's the difference between "selector timed out" and an actionable
 * stack-trace pointing at the broken backend / wrong role / hydration hang.
 */
export async function goTo(page: Page, route: string): Promise<void> {
  // Capture page-side diagnostics throughout the navigation.
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const networkLog: Array<{ url: string; status: number }> = [];
  const onPageError = (err: Error) => {
    pageErrors.push(`${err.name}: ${err.message}`);
  };
  const onConsole = (msg: { type: () => string; text: () => string }) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  };
  const onResponse = (resp: { url: () => string; status: () => number }) => {
    const u = resp.url();
    if (/\/api\/v1\/(auth|admin|entities|dashboard|alerts)\b/.test(u)) {
      networkLog.push({ url: u, status: resp.status() });
    }
  };
  page.on("pageerror", onPageError);
  page.on("console", onConsole);
  page.on("response", onResponse);

  try {
    await page.goto(`/#${route}`);
    await page.waitForSelector(
      'aside.sb, main.login-card, [data-page="login"], [data-page="boot"]',
      { timeout: 15_000, state: "visible" },
    );
  } catch (err) {
    // Build a diagnostic snapshot so the CI log says WHY the boot
    // never reached a visible marker.
    const snapshot = await page.evaluate(() => {
      const sel = (s: string) => {
        const el = document.querySelector(s) as HTMLElement | null;
        if (!el) return { selector: s, present: false };
        const r = el.getBoundingClientRect();
        const cs = window.getComputedStyle(el);
        return {
          selector: s,
          present: true,
          visible:
            r.width > 0 && r.height > 0 &&
            cs.visibility !== "hidden" && cs.display !== "none",
          rect: { w: r.width, h: r.height },
        };
      };
      return {
        href: window.location.href,
        title: document.title,
        bodyText: (document.body?.innerText || "").slice(0, 600),
        markers: [
          sel("aside.sb"),
          sel("main.login-card"),
          sel('[data-page="login"]'),
          sel('[data-page="boot"]'),
          sel("#gis-script"),
          sel(".login-shell"),
          sel(".boot"),
        ],
      };
    }).catch(() => ({ error: "evaluate failed" }));

    // Browser-context probes — if the backend is unreachable from inside
    // the page (CORS / proxy / hostname mismatch), THIS shows it.
    const probes = await page.evaluate(async () => {
      async function probe(url: string) {
        try {
          const r = await fetch(url, { credentials: "include" });
          return { url, status: r.status, ok: r.ok };
        } catch (e) {
          return { url, error: String((e as Error).message || e) };
        }
      }
      return [
        await probe("/api/v1/auth/me"),
        await probe("/api/v1/admin/users"),
      ];
    }).catch(() => ({ error: "probe failed" }));

    const message =
      `goTo("${route}") never reached a visible post-boot marker.\n` +
      `DOM snapshot:\n${JSON.stringify(snapshot, null, 2)}\n` +
      `Browser-context probes:\n${JSON.stringify(probes, null, 2)}\n` +
      `Network responses captured:\n${JSON.stringify(networkLog, null, 2)}\n` +
      `Page errors: ${JSON.stringify(pageErrors)}\n` +
      `Console errors (last 10): ${JSON.stringify(consoleErrors.slice(-10))}\n` +
      `Original error: ${(err as Error).message}`;
    throw new Error(message);
  } finally {
    page.off("pageerror", onPageError);
    page.off("console", onConsole);
    page.off("response", onResponse);
  }
}
