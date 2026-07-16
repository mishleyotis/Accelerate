/**
 * Accessibility sweep — runs axe-core (via vitest-axe) against the
 * rendered shape of every primary page-level component. Asserts zero
 * critical + serious violations.
 *
 * Each test mocks the page's queries so the page renders deterministic
 * happy-path content; axe then walks the resulting DOM. Loading and
 * empty states are covered by the wireframe-completeness suite.
 *
 * State-branch contract for axe failures:
 *   - critical / serious → fail the build (a11y regressions block ship)
 *   - moderate / minor   → not failed by this suite (caught by the
 *                          full a11y matrix in Stage 12 deploy)
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { DashboardPage } from "@/pages/DashboardPage";
import { ClientOverviewPage } from "@/pages/ClientOverviewPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { ProspectingPage } from "@/pages/ProspectingPage";
import { ClientRunsPage } from "@/pages/ClientRunsPage";
import { TechStackDetailPage } from "@/pages/TechStackDetailPage";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { Modal } from "@/components/Modal";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as queries from "@/lib/queries";
import * as drift from "@/lib/drift";
import * as hashRouter from "@/lib/hash-router";
import * as authStore from "@/store/auth";

function withClient(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function mockRoute(path: string) {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path,
    query: {},
    hash: path,
    navigate: vi.fn(),
    setQuery: vi.fn(),
  });
}

function emptyQuery() {
  return {
    data: undefined, isLoading: false, isError: false, error: null,
  } as ReturnType<typeof queries.useDashboard>;
}

/**
 * Filter axe violations down to the impact levels we want to block on.
 * "critical" + "serious" violations are the WCAG 2.1 AA showstoppers.
 */
function blockingViolations(results: Awaited<ReturnType<typeof axe>>) {
  return results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
}

describe("a11y · Sidebar", () => {
  it("has zero critical/serious violations", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: { user_id: "u", email: "x@zennify.com", role: "ADMIN", name: "X" },
    } as any);
    mockRoute("/");
    // Sidebar reads `useAlerts` + `useDashboard` for the live badge / dot
    // counts; wrap in a QueryClient so the hooks don't throw.
    const { container } = render(withClient(<Sidebar />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · TopBar", () => {
  it("internal mode has zero critical/serious violations", async () => {
    mockRoute("/clients/fce-001/overview");
    // NotificationsButton (B-9) reads via TanStack Query, so the TopBar
    // needs a QueryClient in scope when mounted in isolation.
    const { container } = render(withClient(<TopBar audience="internal" />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });

  it("customer mode has zero critical/serious violations", async () => {
    mockRoute("/clients/fce-001/overview");
    const { container } = render(withClient(<TopBar audience="customer" />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · Modal", () => {
  it("open modal has zero critical/serious violations", async () => {
    const { container } = render(
      <Modal open onClose={() => undefined} title="Test dialog">
        <p>body</p>
      </Modal>,
    );
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · DashboardPage happy path", () => {
  it("has zero critical/serious violations", async () => {
    vi.spyOn(queries, "useDashboard").mockReturnValue({
      data: {
        scope: "mine",
        tiles: [
          { kind: "my_clients", label: "My clients", value: 12, delta: null,
            last_refreshed_at: new Date().toISOString() },
          { kind: "open_alerts", label: "Open alerts", value: 3, delta: null,
            last_refreshed_at: new Date().toISOString() },
        ],
        active_runs: [
          {
            id: "r1", request_id: "REQ-A6654887", status: "ACTIVE",
            data_source: "PROJECT_API", evidence_mode: "hybrid",
            ccg_catalog_version: "v7.0", started_at: null,
            completed_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    const { container } = render(withClient(<DashboardPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · ClientOverview happy path", () => {
  it("has zero critical/serious violations with pillar bars", async () => {
    mockRoute("/clients/fce-001/overview");
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: {
        entity: {
          id: "x", display_id: "fce-001", name: "Farm Credit East",
          domain: "fce.com", subvertical: "FC", lobs: [],
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
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    vi.spyOn(queries, "useEntityHeatmap").mockReturnValue({
      data: {
        entity_display_id: "fce-001", run_request_id: "REQ-A6654887",
        zoom: "pillar", view_mode: "standard", subvertical: "FC",
        peer_overlay: false, issue_overlay: false,
        cells: [
          { id: "P1", label: "Strategy", parent_id: null, score: 3.2,
            band: "M3", peer_median: null, peer_gap: null,
            is_thin_evidence: false, cap_applied: false, cap_reason: null,
            issue_count: 0, aliased_from: null },
        ],
        value_chain_buckets: [], catalogue_version: "v7.0", warnings: [],
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    vi.spyOn(drift, "useDrift").mockReturnValue(emptyQuery() as any);
    const { container } = render(withClient(<ClientOverviewPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · AlertsPage", () => {
  it("populated alerts table has zero critical/serious violations", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: { user_id: "u", email: "x@zennify.com", role: "ANALYST", name: "X" },
    } as any);
    vi.spyOn(queries, "useAlerts").mockReturnValue({
      data: {
        items: [
          {
            id: "a1", kind: "stale_evidence", severity: "high",
            title: "Stale evidence in P2", body: "...",
            linked_subcap_ids: ["P2C1.1.1"], linked_e_ids: [],
            opened_at: new Date().toISOString(),
            closed_at: null, resolution: null, age_days: 4,
          },
        ],
        open_count: 1,
      } as any,
      isLoading: false, isError: false, error: null,
    } as any);
    const { container } = render(withClient(<AlertsPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · ProspectingPage", () => {
  it("empty state has zero critical/serious violations", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: { user_id: "u", email: "x@zennify.com", role: "AE", name: "X" },
    } as any);
    mockRoute("/prospecting");
    const { container } = render(withClient(<ProspectingPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · ClientRunsPage", () => {
  it("empty state has zero critical/serious violations", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: { user_id: "u", email: "x@zennify.com", role: "AE", name: "X" },
    } as any);
    mockRoute("/clients/fce-001/runs");
    const { container } = render(withClient(<ClientRunsPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · TechStackDetailPage", () => {
  it("empty state has zero critical/serious violations", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: { user_id: "u", email: "x@zennify.com", role: "AE", name: "X" },
    } as any);
    mockRoute("/clients/fce-001/techstack/salesforce-crm");
    const { container } = render(withClient(<TechStackDetailPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

/* ─────────────────────────────────────────────────────────────────────
 * Extended a11y sweep (closes G12.A11Y from STATUS.md — full per-route
 * gate). The 9 surfaces above + the 7 below cover every primary
 * route. Tests follow the same pattern: mock auth + route, render
 * empty/loading state (worst-case for label drift), axe-walk the DOM,
 * fail on critical/serious only.
 *
 * State-branch contract per page:
 *   - empty / loading state should still have proper labels + roles
 *     so screen readers can announce "loading" / "no data yet"
 *   - any moderate / minor violation surfaces in the wireframe-
 *     completeness suite + the deploy-time full a11y matrix
 * ─────────────────────────────────────────────────────────────────── */
import { DirectoryPage } from "@/pages/DirectoryPage";
import { InsightsPage } from "@/pages/InsightsPage";
import { HeatmapPage } from "@/pages/HeatmapPage";
import { PlatformPage } from "@/pages/PlatformPage";
import { ContextPage } from "@/pages/ContextPage";
import { HealthPage } from "@/pages/HealthPage";
import { TechStackPage } from "@/pages/TechStackPage";
import { LoginPage } from "@/pages/LoginPage";

function adminUser() {
  vi.spyOn(authStore, "useAuthStore").mockReturnValue({
    user: { user_id: "u", email: "x@zennify.com", role: "ADMIN", name: "X" },
  } as any);
}

describe("a11y · DirectoryPage", () => {
  it("empty state has zero critical/serious violations", async () => {
    adminUser();
    mockRoute("/clients");
    const { container } = render(withClient(<DirectoryPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · InsightsPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/insights");
    const { container } = render(withClient(<InsightsPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · HeatmapPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/heatmap");
    const { container } = render(withClient(<HeatmapPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · PlatformPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/platform");
    const { container } = render(withClient(<PlatformPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · ContextPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/context");
    const { container } = render(withClient(<ContextPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · HealthPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/health");
    const { container } = render(withClient(<HealthPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · TechStackPage", () => {
  it("loading state renders accessibly", async () => {
    adminUser();
    mockRoute("/clients/fce-001/techstack");
    const { container } = render(withClient(<TechStackPage />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});

describe("a11y · LoginPage", () => {
  it("renders accessibly with no user", async () => {
    vi.spyOn(authStore, "useAuthStore").mockReturnValue({
      user: null,
    } as any);
    mockRoute("/");
    const { container } = render(withClient(<LoginPage onSuccess={vi.fn()} />));
    const results = await axe(container);
    expect(blockingViolations(results)).toHaveLength(0);
  });
});
