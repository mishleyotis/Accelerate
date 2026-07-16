/**
 * Canonical route inventory for visual regression tests
 * (G12.RESPONSIVE.SUITE — see playwright.visual.config.ts).
 *
 * Each entry defines the hash-route path, the persona to log in as
 * (unauthenticated routes use `null`), and the selector to wait for
 * before capturing the screenshot.
 *
 * Wait-selector contract (industry-grade):
 *   Each page renders an outer `<div className="page" data-page="<n>">`
 *   in BOTH populated and empty states. We wait on `[data-page="<n>"]`
 *   so a route with no seeded data (e.g. "Context still building")
 *   still produces a deterministic screenshot of its empty-state UI.
 *   Per-page populated-content selectors (`.score-ring`, `.insight-card`,
 *   etc.) were brittle — they failed when the seed was incomplete OR
 *   when the page legitimately renders an empty state, which are both
 *   valid render targets for the regression suite.
 *
 * Persona contract:
 *   Backend `dev-login` provisions a session for the email; the role
 *   floor comes from the backend. CLAUDE.md "Role toggle" says the
 *   role gate is downgrade-only, so an analyst-flagged route can be
 *   visited by an admin persona without escalation issues. We pick
 *   the LEAST-privileged persona that can access each route so a
 *   role-gate regression that locks an AE out fails loud here.
 */

export interface VisualRoute {
  name: string;
  path: string;
  persona: "ae" | "analyst" | "admin" | null;
  /** CSS / Playwright selector waited on before screenshot. */
  waitFor?: string;
  /** Locators to mask in the diff (timestamps, live counts, etc.) */
  maskSelectors?: string[];
}

// Seeded by `python -m app.scripts.seed_ci` in the backend test env.
// 2026-06-06 Batch 6: switched from WSFS to richbank-community-trust
// because richbank ships a synthetic Client Profile DOCX that triggers
// EVERY firmographics regex pattern + emits 4 focus areas with distinct
// gradient colors. The other sanitised fixtures have CSV+JSON only --
// no DOCX -- so they render universal empty-states on the
// client-detail pages and defeat the prototype-fidelity contract this
// suite enforces.
const ENTITY_ID = "richbank-community-trust-0001";

export const VISUAL_ROUTES: VisualRoute[] = [
  {
    name: "login",
    path: "/",
    persona: null,
    waitFor: '.login-card, [data-page="login"]',
  },
  {
    name: "dashboard",
    path: "/",
    persona: "ae",
    waitFor: '[data-page="dashboard"]',
    maskSelectors: ["[data-testid='last-refreshed']", ".freshness-dot"],
  },
  {
    name: "directory",
    path: "/clients",
    persona: "ae",
    waitFor: '[data-page="directory"]',
    maskSelectors: ["[data-testid='entity-count']"],
  },
  {
    name: "overview",
    path: `/clients/${ENTITY_ID}/overview`,
    persona: "ae",
    // ClientOverviewPage has no `data-page` wrapper. At 760px the CSS
    // media query collapses .page-head into a stacked layout that may
    // not be reported as "visible" by Playwright's default selector
    // state. `main` is the React app root that's always attached +
    // visible at every breakpoint.
    waitFor: ".page-head, .score-ring, main",
    maskSelectors: ["[data-testid='last-refreshed']", ".freshness-chip"],
  },
  {
    name: "insights",
    path: `/clients/${ENTITY_ID}/insights`,
    persona: "ae",
    waitFor: '[data-page="insights"], main',
  },
  {
    name: "heatmap",
    path: `/clients/${ENTITY_ID}/heatmap`,
    persona: "ae",
    waitFor: '[data-page="heatmap"], main',
  },
  {
    name: "platform",
    path: `/clients/${ENTITY_ID}/platform`,
    persona: "ae",
    waitFor: '[data-page="platform"], main',
  },
  {
    name: "context",
    path: `/clients/${ENTITY_ID}/context`,
    persona: "analyst",
    // ContextPage returns a bare `<EmptyState>` (no `data-page` wrapper)
    // when the seeded run has no document_lineage rows for the context
    // section_kind — that empty state IS a legitimate render target,
    // so wait on either marker.
    waitFor: '[data-page="context"], .empty',
  },
  {
    name: "health",
    path: `/clients/${ENTITY_ID}/health`,
    persona: "analyst",
    waitFor: '[data-page="health"], .empty',
  },
  {
    name: "alerts",
    path: "/alerts",
    persona: "ae",
    waitFor: '[data-page="alerts"]',
  },
  {
    name: "prospecting",
    path: "/prospecting",
    persona: "ae",
    waitFor: '[data-page="prospecting"]',
  },
  {
    name: "admin",
    path: "/admin",
    persona: "admin",
    waitFor: '[data-page="admin"]',
  },
];
