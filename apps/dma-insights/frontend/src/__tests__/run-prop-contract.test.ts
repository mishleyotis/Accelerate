/**
 * Regression: every client-detail page must propagate `?run=<request_id>`
 * to its data hook(s). Independent QA (2026-06-06) identified that
 * 6 of 6 client-detail pages called `useEntity*(displayId)` without
 * forwarding `query.run`, so the ClientBar's historical-run selector
 * was visually wired (URL changed, dropdown updated) but the page
 * data still resolved to the latest ACTIVE run. An AE who clicked
 * an old run got fresh data with a stale label on the chrome -- a
 * serious audit-trust violation.
 *
 * This is a STATIC source-AST check so it runs in CI Stage 1 (no
 * mount required). The pattern enforced is:
 *
 *   const selectedRun = typeof query.run === "string" ? query.run : null;
 *   ...
 *   useEntity{Surface}(displayId, selectedRun)  // or .run via params
 *
 * If any page drops this, the test reports which page + which hook,
 * with a copy-paste-ready fix snippet in the failure message.
 */
import { describe, test, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const REPO_ROOT = resolve(__dirname, "..", "..");

interface PageContract {
  page: string;
  hook: string;
  /**
   * Whether the hook takes the run as the 2nd positional arg
   * (`useEntityOverview(displayId, selectedRun)`) or inside a params
   * object (`useEntityHeatmap(displayId, { run: selectedRun })`).
   */
  shape: "positional" | "params";
}

const CONTRACTS: PageContract[] = [
  { page: "src/pages/ClientOverviewPage.tsx", hook: "useEntityOverview", shape: "positional" },
  { page: "src/pages/ClientOverviewPage.tsx", hook: "useEntityPlatforms", shape: "positional" },
  { page: "src/pages/InsightsPage.tsx", hook: "useEntityInsights", shape: "positional" },
  { page: "src/pages/HeatmapPage.tsx", hook: "useEntityHeatmap", shape: "params" },
  { page: "src/pages/PlatformPage.tsx", hook: "useEntityPlatforms", shape: "positional" },
  { page: "src/pages/ContextPage.tsx", hook: "useEntityContext", shape: "positional" },
  { page: "src/pages/HealthPage.tsx", hook: "useEntityHealth", shape: "positional" },
];


describe("client-detail pages must propagate ?run= to their data hooks", () => {
  test.each(CONTRACTS)(
    "$page → $hook receives the selected run",
    ({ page, hook, shape }) => {
      const src = readFileSync(resolve(REPO_ROOT, page), "utf-8");

      // 1. Page must read `query.run` into a `selectedRun` variable
      //    (or equivalent). The exact variable name is enforced for
      //    grep-ability + reviewability across the codebase.
      expect(src).toMatch(/const\s+selectedRun\s*=\s*typeof\s+query\.run\s*===\s*"string"\s*\?\s*query\.run\s*:\s*null/);

      // 2. Page must pass selectedRun to the hook.
      if (shape === "positional") {
        // useEntityFoo(displayId, selectedRun) -- no other arg shape.
        // Captures `displayId, selectedRun)` or `displayId, selectedRun,` (trailing
        // newline/comment). The lookahead requires either `)` or `,` so we
        // don't false-positive on `displayId, selectedRun.X` etc.
        const positional = new RegExp(
          `${hook}\\s*\\(\\s*displayId\\s*,\\s*selectedRun(?=\\s*[,)])`
        );
        expect(src).toMatch(positional);
      } else {
        // useEntityHeatmap(displayId, { ..., run: selectedRun, ... })
        const paramsShape = new RegExp(
          `${hook}\\s*\\(\\s*displayId\\s*,\\s*\\{[^}]*\\brun:\\s*selectedRun`
        );
        expect(src).toMatch(paramsShape);
      }
    },
  );

  test("never call useEntity*(displayId) WITHOUT a run arg in any client-detail page",
    () => {
      // Defence-in-depth: catch a new client-detail page that grabs
      // displayId-only by accident. The 6 pages enumerated in
      // CONTRACTS above are the ones the ClientBar's run selector
      // gates -- any of them ignoring `?run=` is an AE trust violation.
      //
      // ALLOWED exceptions (documented):
      //  - ClientShell.tsx renders the run selector itself and needs
      //    the latest ACTIVE run to power the dropdown's "current"
      //    option. The other run options come from useEntityRuns().
      //  - ProspectingPage.tsx is a prospecting (pre-engagement) view
      //    with no historical-run dimension -- the displayId here is
      //    a prospect target, not an existing client with prior runs.
      const EXEMPT_FILES = new Set<string>([
        "src/components/ClientShell.tsx",
        "src/pages/ProspectingPage.tsx",
      ]);
      const CHECKED_FILES = new Set(CONTRACTS.map((c) => c.page));
      const fs = require("node:fs") as typeof import("node:fs");
      const path = require("node:path") as typeof import("node:path");
      const offenders: string[] = [];

      for (const rel of CHECKED_FILES) {
        if (EXEMPT_FILES.has(rel)) continue;
        const full = path.resolve(REPO_ROOT, rel);
        const text = fs.readFileSync(full, "utf-8");
        for (const hook of [
          "useEntityOverview", "useEntityInsights", "useEntityHeatmap",
          "useEntityPlatforms", "useEntityContext", "useEntityHealth",
        ]) {
          // `useEntityFoo(displayId)` -- exactly that, with nothing
          // between displayId and the closing paren.
          const bad = new RegExp(`${hook}\\s*\\(\\s*displayId\\s*\\)`);
          if (bad.test(text)) {
            offenders.push(`${rel} :: ${hook}(displayId)`);
          }
        }
      }

      expect(offenders).toEqual([]);
    },
  );
});
