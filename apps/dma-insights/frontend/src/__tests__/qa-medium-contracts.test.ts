/**
 * Regression: medium-priority QA findings — frontend AST contracts.
 *
 * Pins:
 *   M-1: ClientOverviewPage no longer synthesises `peer = score + 0.3`.
 *        Reads peer_median from the typed EntityOverviewResponse.pillar_scores.
 *   M-3: ClientRunsPage's View and Compare buttons encode the row's
 *        request_id into `?run=` / `?run_b=` so the destination page
 *        resolves THE selected run, not the latest ACTIVE.
 *   M-4: DashboardPage + DirectoryPage no longer hard-code `open_alerts: 0`
 *        on the entity card row construction.
 *   M-6: Dashboard "Needs attention" count uses entity_display_id not alert id.
 *
 * Static AST checks (no DOM, no live fetch) so they run in CI Stage 1.
 */
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const REPO_ROOT = resolve(__dirname, "..", "..");


function srcOf(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), "utf-8");
}


describe("M-1: Overview no longer synthesises peer_median", () => {
  test("ClientOverviewPage reads peer_median from the typed response",
    () => {
      const src = srcOf("src/pages/ClientOverviewPage.tsx");
      // The pre-fix synthetic pattern must be GONE.
      expect(src).not.toMatch(/peer\s*=\s*s\s*!=\s*null\s*\?\s*s\s*\+\s*0\.3/);
      expect(src).not.toMatch(/peer\s*=\s*s\s*\+\s*0\.3/);
      // The peer must come from a real map keyed by pillar_id.
      expect(src).toMatch(/peerMedianMap\s*\[\s*p\.id\s*\]/);
    });

  test("EntityOverviewResponse.pillar_scores is typed (no cast)",
    () => {
      const src = srcOf("src/lib/queries.ts");
      // The contract: pillar_scores is an Array<{pillar_id, score, peer_median, ...}>.
      // Match the start of the declaration; the literal block-content includes
      // the exact field names.
      expect(src).toMatch(/pillar_scores:\s*Array<\s*\{[^}]*peer_median:\s*number\s*\|\s*null/);
    });
});


describe("M-3: ClientRuns View/Compare propagate the row's request_id", () => {
  test("View navigates to overview?run=<request_id>", () => {
    const src = srcOf("src/pages/ClientRunsPage.tsx");
    expect(src).toMatch(/\/clients\/\$\{displayId\}\/overview\?run=\$\{encodeURIComponent\(r\.request_id\)\}/);
  });

  test("Compare navigates to health?tab=diff&run_b=<request_id>", () => {
    const src = srcOf("src/pages/ClientRunsPage.tsx");
    expect(src).toMatch(/\/clients\/\$\{displayId\}\/health\?tab=diff&run_b=\$\{encodeURIComponent\(r\.request_id\)\}/);
  });

  test("Health Diff tab honours ?run_a / ?run_b URL params", () => {
    const src = srcOf("src/pages/HealthPage.tsx");
    expect(src).toMatch(/query\.run_a/);
    expect(src).toMatch(/query\.run_b/);
    // The URL-params win in the default-selector effect when they
    // match a known run.
    expect(src).toMatch(/knownIds\.has\(urlRunA\)\s*\?\s*urlRunA/);
  });
});


describe("M-4: open_alerts is NOT hard-coded on entity cards", () => {
  test("DashboardPage reads open_alerts from EntitySummary", () => {
    const src = srcOf("src/pages/DashboardPage.tsx");
    // The pre-fix hard-code was `open_alerts: 0,` (no comment); the fix
    // assigns from `e.open_alerts` (with a comment explaining).
    expect(src).not.toMatch(/open_alerts:\s*0\s*,(?!\s*\/)/);
    expect(src).toMatch(/open_alerts:\s*e\.open_alerts/);
  });

  test("DirectoryPage reads open_alerts from EntitySummary", () => {
    const src = srcOf("src/pages/DirectoryPage.tsx");
    expect(src).not.toMatch(/open_alerts:\s*0\s*,(?!\s*\/)/);
    expect(src).toMatch(/open_alerts:\s*e\.open_alerts/);
  });

  test("Frontend EntitySummary type carries open_alerts: number", () => {
    const src = srcOf("src/lib/queries.ts");
    expect(src).toMatch(/open_alerts:\s*number/);
  });
});


describe("M-6: stale-alert KPI counts entities, not alerts", () => {
  test("DashboardPage 'Needs attention' uses entity_display_id",
    () => {
      const src = srcOf("src/pages/DashboardPage.tsx");
      // The fix uses `a.entity_display_id` inside the Set; the
      // pre-fix used `a.id`.
      expect(src).toMatch(/new Set\(\s*\(alertsQ\.data\?\.items\s*\?\?\s*\[\]\)\s*\.map\(\(a\)\s*=>\s*a\.entity_display_id\)/);
      // The pre-fix `a.id` pattern in the same context must NOT be
      // present.
      expect(src).not.toMatch(/new Set\(\s*\([^)]*alertsQ[^)]*\)\.map\(\(a\)\s*=>\s*a\.id\)\)/);
    });
});


describe("M-2: Scorecard + Rerun buttons call real mutations", () => {
  test("ClientOverviewPage imports useExportScorecard + useRequestNewRun",
    () => {
      const src = srcOf("src/pages/ClientOverviewPage.tsx");
      expect(src).toMatch(/useExportScorecard/);
      expect(src).toMatch(/useRequestNewRun/);
    });

  test("ScorecardButton + RerunButton are defined as real-mutation components",
    () => {
      const src = srcOf("src/pages/ClientOverviewPage.tsx");
      expect(src).toMatch(/function ScorecardButton\(/);
      expect(src).toMatch(/function RerunButton\(/);
      expect(src).toMatch(/exportMutation\.mutateAsync/);
      expect(src).toMatch(/mutation\.mutateAsync/);
    });
});
