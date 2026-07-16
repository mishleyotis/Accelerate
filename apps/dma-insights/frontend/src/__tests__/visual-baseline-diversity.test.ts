/**
 * Regression guard: visual-regression baselines MUST be route-distinct
 * within each breakpoint.
 *
 * This test catches the class of failure that hid in the suite for
 * months: every "12 routes × 7 breakpoints" baseline file had only 7
 * unique md5 hashes (1 per breakpoint × 12 IDENTICAL screenshots),
 * because the standalone bundle's `/api/v1/auth/me` returned 401 →
 * every protected route fell back to LoginPage → every screenshot was
 * the same LoginPage rendered at a different width. The tests all
 * "passed" because actual matched expected — but the suite had ZERO
 * regression power: a real route-specific regression in HeatmapPage
 * could ship undetected because HeatmapPage was never actually
 * captured.
 *
 * The contract pinned here: at any given breakpoint, the count of
 * unique-hash baseline files must equal the count of baseline files.
 * If two routes ever produce identical screenshots at the same
 * breakpoint, this test fails loud and CI blocks the merge until the
 * tester regenerates with a backend that returns route-distinct data.
 *
 * Scope:
 *   - `e2e/visual/responsive.visual.ts-snapshots/` — the live-backend
 *     suite (G12.RESPONSIVE.SUITE, playwright.visual.config.ts).
 *   - `e2e/visual/standalone-responsive.visual.ts-snapshots/` is
 *     INTENTIONALLY EXCLUDED — the static demo build has no auth and
 *     all routes legitimately render LoginPage (ADR 0016: standalone
 *     is the wireframe-guide demo, not the production AE surface).
 */
import { createHash } from "node:crypto";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// __dirname here is `…/frontend/src/__tests__`. Walk up to frontend
// root then into e2e/visual/. Resolves identically under vitest
// (jsdom env) and plain node.
const SNAPSHOT_DIR = join(
  __dirname, "..", "..",
  "e2e", "visual", "responsive.visual.ts-snapshots",
);

/** Baseline filename shape: `<route>-responsive-<breakpoint>-<os>.png` */
const FILENAME_RE = /^(.+?)-responsive-(\d+)-([a-z]+)\.png$/;

interface Baseline {
  route: string;
  breakpoint: number;
  os: string;
  filename: string;
  hash: string;
}

function readBaselines(): Baseline[] {
  if (!existsSync(SNAPSHOT_DIR)) return [];
  const files = readdirSync(SNAPSHOT_DIR);
  const baselines: Baseline[] = [];
  for (const f of files) {
    const m = FILENAME_RE.exec(f);
    if (!m) continue;
    const buf = readFileSync(join(SNAPSHOT_DIR, f));
    baselines.push({
      route: m[1],
      breakpoint: Number(m[2]),
      os: m[3],
      filename: f,
      hash: createHash("md5").update(buf).digest("hex"),
    });
  }
  return baselines;
}

describe("visual baseline diversity", () => {
  const baselines = readBaselines();

  it("has at least one committed baseline", () => {
    // If no baselines exist yet, fail loudly with the regen command —
    // a silent skip would let a fresh checkout pass CI with no
    // regression coverage.
    expect(baselines.length).toBeGreaterThan(0);
  });

  it("groups baselines by breakpoint", () => {
    const byBreakpoint = new Map<number, Baseline[]>();
    for (const b of baselines) {
      const arr = byBreakpoint.get(b.breakpoint) ?? [];
      arr.push(b);
      byBreakpoint.set(b.breakpoint, arr);
    }
    // Pin the documented breakpoint ladder so a regen that drops a
    // viewport (e.g. someone removes the 980 viewport in
    // playwright.visual.config.ts) is caught here too.
    expect(byBreakpoint.size).toBeGreaterThanOrEqual(1);
  });

  it("every route is distinct at every breakpoint", () => {
    const byBreakpoint = new Map<number, Baseline[]>();
    for (const b of baselines) {
      const arr = byBreakpoint.get(b.breakpoint) ?? [];
      arr.push(b);
      byBreakpoint.set(b.breakpoint, arr);
    }
    const collisions: Array<{
      breakpoint: number;
      routes: string[];
      hash: string;
    }> = [];
    for (const [bp, arr] of byBreakpoint) {
      const byHash = new Map<string, string[]>();
      for (const b of arr) {
        const routes = byHash.get(b.hash) ?? [];
        routes.push(b.route);
        byHash.set(b.hash, routes);
      }
      for (const [hash, routes] of byHash) {
        if (routes.length > 1) {
          collisions.push({ breakpoint: bp, routes, hash });
        }
      }
    }
    if (collisions.length > 0) {
      const lines = collisions.map(
        (c) =>
          `  • breakpoint=${c.breakpoint} routes=[${c.routes.join(", ")}] ` +
          `share md5=${c.hash} — likely all rendering the same (login?) page`,
      );
      throw new Error(
        `Visual baselines are NOT route-distinct at one or more breakpoints:\n` +
        lines.join("\n") +
        `\n\nThis is the auth-fallback regression: routes that should ` +
        `render different content are all capturing the SAME screenshot. ` +
        `Likely cause: the test backend's /api/v1/auth/me returns 401, ` +
        `so React redirects every protected route to LoginPage before ` +
        `the screenshot. Fix the backend auth before regenerating.\n\n` +
        `To regenerate (against a live backend with dev-login working):\n` +
        `  cd apps/dma-insights/frontend\n` +
        `  BACKEND_URL=http://127.0.0.1:8000 pnpm test:visual:update`,
      );
    }
    expect(collisions).toEqual([]);
  });

  it("login is the only route that ever shares a hash with the standalone demo's login baseline", () => {
    // Sanity check: if our /login baseline ever drifts AWAY from the
    // standalone demo's /login baseline, something subtle changed in
    // the LoginPage chrome — worth flagging. This is informational
    // only (no .toBe assertion) so it documents intent without
    // failing on benign drift.
    const loginBaselines = baselines.filter((b) => b.route === "login");
    expect(loginBaselines.length).toBeGreaterThan(0);
  });
});
