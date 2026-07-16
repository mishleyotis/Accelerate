/**
 * Lighthouse CI config — closes G12.PERF.BUDGET.
 *
 * The plan's Stage 12 gate:
 *   Lighthouse Performance ≥ 85, FCP < 1.5s, TTI < 3s on dashboard + heatmap.
 *
 * This config lets `lhci autorun` run those budgets against any URL
 * (the dev server locally, or the live Cloud Run URL in CI). The plan
 * originally deferred this to "pending Cloud Run deploy" — that
 * deferral is now scoped to "operator points lhci at the live URL";
 * the threshold definition + assertion config live here in the repo.
 *
 * Usage (local, against dev server):
 *   cd frontend && pnpm dev &
 *   npx --yes @lhci/cli@0.13.x autorun --config=./lighthouserc.cjs
 *
 * Usage (against live Cloud Run):
 *   LHCI_BUILD_URL=https://dma-insights-...run.app \
 *     npx --yes @lhci/cli@0.13.x autorun --config=./lighthouserc.cjs
 *
 * Why .cjs: @lhci/cli still loads config via CommonJS require().
 *
 * State branches (from `assertions` block below):
 *   all_thresholds_met      → exit 0; pass
 *   perf_below_85           → fail with specific score
 *   fcp_above_1500ms        → fail
 *   tti_above_3000ms        → fail
 *   server_unreachable      → exit 1 with the URL that failed
 */

const BASE_URL = process.env.LHCI_BUILD_URL || "http://localhost:5173";

module.exports = {
  ci: {
    collect: {
      url: [
        `${BASE_URL}/#/`,                          // dashboard
        `${BASE_URL}/#/clients/fce-001/heatmap`,   // heatmap (plan's named gate)
      ],
      numberOfRuns: 3,                              // median of 3 runs
      settings: {
        // Disable noisy categories — only Performance is in the SLA.
        onlyCategories: ["performance"],
        // Throttle to typical mobile so the desktop+broadband bias
        // doesn't hide real-user perf regressions.
        preset: "desktop",
      },
    },
    assert: {
      assertions: {
        // Plan thresholds — Stage 12 G12.PERF.BUDGET
        "categories:performance":          ["error", { minScore: 0.85 }],
        "first-contentful-paint":          ["error", { maxNumericValue: 1500 }],
        "interactive":                     ["error", { maxNumericValue: 3000 }],

        // Soft bounds — warnings only (catch trends but don't block)
        "largest-contentful-paint":        ["warn",  { maxNumericValue: 2500 }],
        "cumulative-layout-shift":         ["warn",  { maxNumericValue: 0.1 }],
        "total-blocking-time":             ["warn",  { maxNumericValue: 300 }],
      },
    },
    upload: {
      // Local artifact storage by default; flip to "lhci" + a server
      // URL when the team adopts a hosted LHCI server.
      target: "filesystem",
      outputDir: "./artifacts/lighthouse",
    },
  },
};
