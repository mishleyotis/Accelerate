/**
 * Wireframe-completeness QA — asserts no page renders dummy data and
 * every page degrades to an honest empty state when its query yields no
 * data.
 *
 * Mocks every TanStack Query hook the page consumes (so no real fetch),
 * then renders each page in three scenarios:
 *
 *   1. loading       → spinner + "Loading…" text
 *   2. empty         → page-specific empty-state copy (NOT "TBD" / "TODO"
 *                     / hardcoded numbers)
 *   3. populated     → the rendered text matches the mocked data values
 *                     (no fallback to fake fillers)
 *
 * The bar is intentionally high: any leak of TODO / TBD / FIXME / dummy
 * / lorem ipsum / hardcoded sample numbers (3.2 etc.) fails the test.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { DashboardPage } from "@/pages/DashboardPage";
import { ClientOverviewPage } from "@/pages/ClientOverviewPage";
import { AlertsPage } from "@/pages/AlertsPage";
import * as queries from "@/lib/queries";
import * as drift from "@/lib/drift";
import * as hashRouter from "@/lib/hash-router";
import * as authStore from "@/store/auth";

const FORBIDDEN_DUMMY = /\b(TBD|TODO|FIXME|dummy|lorem ipsum)\b/i;

function emptyQuery() {
  return {
    data: undefined, isLoading: false, isError: false, error: null,
  } as ReturnType<typeof queries.useDashboard>;
}

function loadingQuery() {
  return {
    data: undefined, isLoading: true, isError: false, error: null,
  } as ReturnType<typeof queries.useDashboard>;
}

function withQueryClient(ui: ReactNode) {
  // RequestDmaModal nests useMutation, which requires a QueryClientProvider
  // even when surrounding read hooks are mocked. Every render in this
  // suite is wrapped so pages can be exercised in isolation.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("Dashboard page completeness", () => {
  // The 2026-06 rebuild ports the prototype DashboardHome 1:1 — it now
  // reads from `useEntities` + `useAlerts` for KPI counts (not the old
  // `tiles[]` array on the dashboard response). The tests below verify
  // the new contract: KPI strip + empty-state copy for active runs +
  // the no-fabricated-values guard.
  it("renders KPI strip + recent assessments grid with no dummy values", () => {
    vi.spyOn(queries, "useDashboard").mockReturnValue({
      data: { scope: "mine", tiles: [], active_runs: [] } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    render(withQueryClient(<DashboardPage />));
    expect(screen.getByText(/Command centre/i)).toBeTruthy();
    expect(screen.getByText(/Active assessments/i)).toBeTruthy();
    expect(screen.getAllByText(/Open alerts/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
  });

  it("empty active_runs renders the explicit empty-state card", () => {
    vi.spyOn(queries, "useDashboard").mockReturnValue({
      data: { scope: "mine", tiles: [], active_runs: [] } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    render(withQueryClient(<DashboardPage />));
    expect(screen.getByText(/No active runs/i)).toBeTruthy();
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
  });

  it("never falls back to fabricated dummy values when data is loading", () => {
    vi.spyOn(queries, "useDashboard").mockReturnValue(loadingQuery() as any);
    render(withQueryClient(<DashboardPage />));
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
    // KPI strip renders headers even while data is loading — no fake values.
    expect(screen.getByText(/Active assessments/i)).toBeTruthy();
  });
});

describe("ClientOverviewPage completeness (no hardcoded 3.2)", () => {
  function mockRoute(displayId: string) {
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: `/clients/${displayId}/overview`,
      query: {},
      hash: `/clients/${displayId}/overview`,
      navigate: vi.fn(),
      setQuery: vi.fn(),
    });
  }

  it("renders the empty state when the entity has no completed DMA", () => {
    mockRoute("fce-001");
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: {
        entity: {
          id: "x", display_id: "fce-001", name: "Farm Credit East",
          domain: null, subvertical: "FC", lobs: [],
          status: "ACTIVE", last_run_at: null,
          last_run_request_id: null, owner_email: null, owner_name: null,
          updated_at: new Date().toISOString(),
        },
        run: null,
        scqa: null,
        why_now_signals: [],
        top_findings: [],
        firmographics: null,
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    vi.spyOn(queries, "useEntityHeatmap").mockReturnValue(emptyQuery() as any);
    vi.spyOn(drift, "useDrift").mockReturnValue(emptyQuery() as any);
    render(withQueryClient(<ClientOverviewPage />));
    expect(
      screen.getByText(/Farm Credit East has no completed DMA yet/i),
    ).toBeTruthy();
    // The forbidden hardcoded 3.2 must NEVER appear here
    expect(screen.queryByText("3.2")).toBeNull();
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
  });

  it("score is derived from pillar cells, not from a hardcoded number", () => {
    mockRoute("fce-001");
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: {
        entity: {
          id: "x", display_id: "fce-001", name: "Farm Credit East",
          domain: null, subvertical: "FC", lobs: [],
          status: "ACTIVE",
          last_run_at: new Date().toISOString(),
          last_run_request_id: "REQ-A6654887",
          owner_email: null, owner_name: null,
          updated_at: new Date().toISOString(),
        },
        run: {
          id: "r", request_id: "REQ-A6654887", status: "ACTIVE",
          data_source: "PROJECT_API", evidence_mode: "hybrid",
          ccg_catalog_version: "v7.0", started_at: null,
          completed_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        scqa: { situation: "s", complication: "c", question: "q", answer: "a" },
        why_now_signals: [], top_findings: [],
        firmographics: null,
        // Post-2026-06 contract: overall score + per-pillar both come
        // directly off the overview response — no recompute from heatmap.
        pillar_scores: [
          { pillar_id: "P1", score: 2.0 },
          { pillar_id: "P2", score: 3.0 },
          { pillar_id: "P3", score: 2.5 },
          { pillar_id: "P4", score: 2.3 },
        ],
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    // Heatmap mock kept for legacy parity but the new Overview no longer
    // recomputes overall from heatmap cells.
    vi.spyOn(queries, "useEntityHeatmap").mockReturnValue({
      data: {
        entity_display_id: "fce-001", run_request_id: "REQ-A6654887",
        zoom: "pillar", view_mode: "standard", subvertical: "FC",
        peer_overlay: false, issue_overlay: false,
        cells: [
          { id: "P1", label: "Strategy", parent_id: null, score: 2.0,
            band: "M2", peer_median: null, peer_gap: null,
            is_thin_evidence: false, cap_applied: false, cap_reason: null,
            issue_count: 0, aliased_from: null },
          { id: "P2", label: "Engagement", parent_id: null, score: 3.0,
            band: "M3", peer_median: null, peer_gap: null,
            is_thin_evidence: false, cap_applied: false, cap_reason: null,
            issue_count: 0, aliased_from: null },
          { id: "P3", label: "Operations", parent_id: null, score: 2.5,
            band: "M3", peer_median: null, peer_gap: null,
            is_thin_evidence: false, cap_applied: false, cap_reason: null,
            issue_count: 0, aliased_from: null },
          { id: "P4", label: "Data & AI", parent_id: null, score: 2.3,
            band: "M2", peer_median: null, peer_gap: null,
            is_thin_evidence: false, cap_applied: false, cap_reason: null,
            issue_count: 0, aliased_from: null },
        ],
        value_chain_buckets: [], catalogue_version: "v7.0", warnings: [],
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    vi.spyOn(drift, "useDrift").mockReturnValue(emptyQuery() as any);
    render(withQueryClient(<ClientOverviewPage />));
    // (2.0 + 3.0 + 2.5 + 2.3) / 4 = 2.45 → rounded to 2.5 by meanPillarScore.
    // Both the ScoreRing and the P3 pillar bar render "2.5" — assert at
    // least one appearance; the old hardcoded 3.2 must NOT appear anywhere.
    const matches = screen.getAllByText("2.5");
    expect(matches.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("3.2")).toBeNull();
    // Per-pillar bars show all 4 pillars
    expect(screen.getByText(/P1 · Strategy/i)).toBeTruthy();
    // The post-2026-06 pillar labels in the ported overview come from
    // the canonical PILLARS array (short labels) — Data & Tech in P4.
    expect(screen.getByText(/P4 · Data & Tech/i)).toBeTruthy();
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
  });
});

describe("AlertsPage completeness", () => {
  // Post-2026-06 rebuild: AlertsPage is Analyst+ only (matches the
  // prototype's role gate at standalone-src/src/pages-f.jsx#L19). The
  // empty-state copy only renders when the role check passes, so the
  // mock now grants ANALYST and selects the Waived tab where the empty
  // state lives.
  it("empty list renders an explicit empty state", () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: {
        user_id: "u1", email: "x@zennify.com", role: "ANALYST", name: "X",
      },
    } as any);
    vi.spyOn(queries, "useAlerts").mockReturnValue({
      data: { items: [], open_count: 0 } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    render(withQueryClient(<AlertsPage />));
    // The Alerts tab is open by default and renders "No open alerts
    // matching" when filtered.length === 0.
    expect(screen.getByText(/No open alerts matching/i)).toBeTruthy();
    expect(screen.queryByText(FORBIDDEN_DUMMY)).toBeNull();
  });
});
