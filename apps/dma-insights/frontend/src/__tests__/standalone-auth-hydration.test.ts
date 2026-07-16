/**
 * Standalone build auth hydration regression suite.
 *
 * The 2026-05-28 incident root cause: the standalone build never
 * hydrated from the /api/v1/auth/me JWT cookie. `loadStoredUser()`
 * read only sessionStorage, so:
 *
 *   - operators returning to the app after a tab close were forced
 *     to sign in again even though their cookie was still valid
 *   - Playwright e2e tests that inject the JWT via `addCookies` +
 *     verify /auth/me returns 200 saw the SPA stay on LoginPage
 *     because nothing actually called signIn() with the response
 *
 * The fix: a one-shot boot useEffect in AppProvider that calls
 * /auth/me when sessionStorage has no user, and signs in if the
 * cookie is valid. Plus a `hydrating` flag so Router renders a
 * spinner during the brief boot fetch instead of flashing LoginPage.
 *
 * These tests pin the source shape so a refactor that drops the
 * hydration hook fires a regression here BEFORE the e2e suite
 * (which is slow + container-bound) catches it.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SRC = resolve(process.cwd(), "standalone-src/src");

function load(name: string): string {
  return readFileSync(resolve(SRC, name), "utf-8");
}

describe("standalone build auth hydration", () => {
  const app = load("app-root.jsx");

  it("AppProvider calls /api/v1/auth/me on boot when sessionStorage is empty", () => {
    // The useEffect must reference /api/v1/auth/me AND signIn().
    // The standalone build's e2e + operator gap was that the SPA
    // never read the HttpOnly JWT cookie; this hook closes it.
    expect(app).toContain('fetch("/api/v1/auth/me"');
    // The boot fetch must be inside a useEffect (not a top-level call).
    expect(app).toMatch(
      /useEffect\([\s\S]*?fetch\(['"]\/api\/v1\/auth\/me['"]/,
    );
  });

  it("hydration calls signIn with the server body, not a derived email", () => {
    // signIn must receive the FULL response object (so server role
    // wins). Passing just `body.email` would silently strip the
    // server's role assignment — a security regression.
    expect(app).toMatch(/signIn\(body\)/);
  });

  it("hydration is best-effort — network errors leave the user on LoginPage", () => {
    // The catch block must NOT throw / setAuthed(true). A 401 or
    // 5xx during boot should land the user on LoginPage (the
    // BackendErrorBanner surfaces the underlying failure).
    expect(app).toMatch(/catch\s*\([^)]*\)\s*{[\s\S]{0,300}?\}/);
    // The fetch is wrapped in try/catch and the failure path doesn't
    // mutate authed.
    // Window widened (was 2500) — the timeout/AbortController hardening
    // added in the 2026-05-28 fix puts the try/catch further down.
    const hydrationBlock = app.slice(
      app.indexOf("Boot hydration from /api/v1/auth/me"),
      app.indexOf("Boot hydration from /api/v1/auth/me") + 4500,
    );
    expect(hydrationBlock).toContain("try");
    expect(hydrationBlock).toContain("catch");
  });

  it("hydration is short-circuited when sessionStorage has a user", () => {
    // The useEffect must check `stored` first. Skipping this would
    // re-call /auth/me on every page navigation (wasteful + a flicker).
    expect(app).toMatch(
      /if\s*\(\s*stored\s*\)\s*{[\s\S]{0,200}?setHydrating\(false\)/,
    );
  });

  it("Router shows a spinner while hydrating (not LoginPage)", () => {
    // Without the hydrating check, the user would see a FLASH of
    // LoginPage during the boot fetch even when their cookie was
    // valid + the SPA was about to signIn from the /auth/me response.
    expect(app).toMatch(
      /if\s*\(\s*hydrating\s*\)\s*return\s*<LoadingScreen/,
    );
    // The hydrating flag must be destructured from useApp() in Router.
    // Destructure order is "{ route, authed, hydrating } = useApp()" —
    // useApp comes AFTER the names, so match around it.
    expect(app).toMatch(/hydrating[\s\S]{0,80}?useApp\(\)/);
  });

  it("hydrating is exported in the context", () => {
    // Other components might want to gate their initial fetches on
    // hydration completion. The context must expose `hydrating`.
    expect(app).toMatch(/authed, setAuthed, hydrating/);
  });
});

describe("standalone build hydration timeout (e2e hang fix)", () => {
  const app = load("app-root.jsx");

  it("hydration fetch has an AbortController hard-timeout", () => {
    // Without this, /auth/me hanging in CI leaves the SPA in the
    // hydration spinner forever; the Playwright helper times out
    // after 15s because no selector matches the spinner state.
    expect(app).toContain("AbortController");
    expect(app).toMatch(/ctl\.abort\(\)/);
    // The signal must be passed to fetch.
    expect(app).toMatch(/signal:\s*ctl\.signal/);
  });

  it("hydration has a belt-and-braces fallback setTimeout", () => {
    // Even if AbortController doesn't fire (Chromium quirk), this
    // hard timer also flips hydrating=false so the LoginPage renders.
    expect(app).toContain("fallbackTimer");
    expect(app).toMatch(/setHydrating\(false\)/);
  });

  it("hydration timeout is ≤ 3 seconds", () => {
    // 2.5s for the fetch abort, 3s for the fallback. Anything longer
    // risks the e2e helper's 15s timeout when the spinner is also
    // gated by the App's 600ms boot delay + font-ready Promise.
    expect(app).toMatch(/setTimeout\(\(\)\s*=>\s*ctl\.abort\(\),\s*[12]\d{3}\)/);
  });
});

describe("LoginPage data-page marker for e2e helper", () => {
  const login = load("pages-auth-dashboard-directory.jsx");

  it("LoginPage outer container exposes data-page=login", () => {
    // The e2e goTo() helper waits for one of:
    //   - aside.sb  (authenticated)
    //   - #gis-script  (LoginPage script injected)
    //   - [data-page="login"]  (synchronous marker)
    // The synchronous marker avoids races with GIS script loading.
    expect(login).toMatch(/data-page="login"/);
  });
});
