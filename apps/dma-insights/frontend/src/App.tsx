/**
 * App shell — Sidebar + TopBar + routed page.
 *
 * Route table (hash routes, parsed by useRoute):
 *   /                                       → DashboardPage
 *   /clients                                → DirectoryPage
 *   /clients/{display_id}/overview          → ClientOverviewPage
 *   /clients/{display_id}/insights          → InsightsPage
 *   /clients/{display_id}/heatmap           → HeatmapPage
 *   /clients/{display_id}/platform          → PlatformPage
 *   /clients/{display_id}/context           → ContextPage (Analyst+)
 *   /clients/{display_id}/health            → HealthPage (Analyst+)
 *   /clients/{display_id}/techstack         → TechStackPage
 *   /clients/{display_id}/techstack/:techId → TechStackDetailPage
 *   /clients/{display_id}/runs              → ClientRunsPage
 *   /alerts                                 → AlertsPage
 *   /prospecting                            → ProspectingPage
 *   /admin, /admin/*                        → AdminPage (ADMIN-only)
 *   anything else                           → NotFound
 *
 * The auth gate runs once at boot via whoAmI(); unauthenticated users
 * land on the LoginPage which drives the live Google OIDC flow.
 */
import { useEffect } from "react";
import { ClientShell } from "@/components/ClientShell";
import { DrawerHost } from "@/components/DrawerHost";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { EmptyState } from "@/components/utils";
import { useRoute } from "@/lib/hash-router";
import { useAuthStore } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { whoAmI } from "@/lib/auth";
import { installTableLabels } from "@/lib/tableLabels";
import { DashboardPage } from "@/pages/DashboardPage";
import { DirectoryPage } from "@/pages/DirectoryPage";
import { ClientOverviewPage } from "@/pages/ClientOverviewPage";
import { InsightsPage } from "@/pages/InsightsPage";
import { HeatmapPage } from "@/pages/HeatmapPage";
import { PlatformPage } from "@/pages/PlatformPage";
import { ContextPage } from "@/pages/ContextPage";
import { HealthPage } from "@/pages/HealthPage";
import { TechStackPage } from "@/pages/TechStackPage";
import { TechStackDetailPage } from "@/pages/TechStackDetailPage";
import { ClientRunsPage } from "@/pages/ClientRunsPage";
import { ProspectingPage } from "@/pages/ProspectingPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { AdminPage, ImportAuditPage } from "@/pages/AdminPage";
import { ImportPage } from "@/pages/ImportPage";
import { LoginPage } from "@/pages/LoginPage";

function StubPage({ name }: { name: string }) {
  return (
    <EmptyState
      title={`${name} — coming soon`}
      body="Backend route is live; frontend port lands in the next batch."
    />
  );
}

function NotFound({ path }: { path: string }) {
  const { navigate } = useRoute();
  return (
    <EmptyState
      title="Page not found"
      body={path}
      cta={
        <button className="btn btn-primary" onClick={() => navigate("/")}>
          Back to Dashboard
        </button>
      }
    />
  );
}

function pickClientPage(tab: string): JSX.Element {
  if (tab === "overview") return <ClientOverviewPage />;
  if (tab === "insights") return <InsightsPage />;
  if (tab === "heatmap") return <HeatmapPage />;
  if (tab === "platform") return <PlatformPage />;
  if (tab === "context") return <ContextPage />;
  if (tab === "health") return <HealthPage />;
  if (tab === "techstack") return <TechStackPage />;
  if (tab === "runs") return <ClientRunsPage />;
  return <StubPage name={`Client / ${tab}`} />;
}

function dispatch(path: string) {
  // /login: when authenticated (we only reach `dispatch` when authed --
  // unauthed renders LoginPage in App() below), bounce to /. Sidebar
  // sign-out navigates to /login then setUser(null) but the navigate
  // can land before the setUser, so we'd otherwise render NotFound for
  // a flash. Just redirect via the hash router so the flow is clean.
  if (path === "/login") {
    setTimeout(() => {
      if (window.location.hash === "#/login") window.location.hash = "#/";
    }, 0);
    return <DashboardPage />;
  }
  if (path === "/" || path === "") return <DashboardPage />;
  if (path === "/clients") return <DirectoryPage />;

  // /clients/:id/techstack/:techId — wrap in ClientShell so the bar shows
  // even on the deep-link.
  const techDetailMatch = path.match(/^\/clients\/([^/]+)\/techstack\/([^/]+)$/);
  if (techDetailMatch) {
    return (
      <ClientShell displayId={techDetailMatch[1]}>
        <TechStackDetailPage />
      </ClientShell>
    );
  }

  // /clients/:id — short form defaults to overview.
  const clientRootMatch = path.match(/^\/clients\/([^/]+)$/);
  if (clientRootMatch) {
    return (
      <ClientShell displayId={clientRootMatch[1]}>
        <ClientOverviewPage />
      </ClientShell>
    );
  }

  // /clients/:id/:tab — two-segment client routes
  const clientMatch = path.match(/^\/clients\/([^/]+)\/([^/]+)$/);
  if (clientMatch) {
    return (
      <ClientShell displayId={clientMatch[1]}>
        {pickClientPage(clientMatch[2])}
      </ClientShell>
    );
  }

  if (path === "/alerts") return <AlertsPage />;
  if (path === "/prospecting") return <ProspectingPage />;
  if (path === "/admin/import/audit") return <ImportAuditPage />;
  // Dedicated Import & jobs surface — MUST precede the /admin catch-all
  // (QA audit 2026-06-11: the Sidebar linked here but the route fell
  // through to AdminPage, so the wireframe's import pipeline page never
  // rendered).
  if (path === "/admin/import") return <ImportPage />;
  if (path === "/admin" || path.startsWith("/admin/")) return <AdminPage />;
  return <NotFound path={path} />;
}

export function App() {
  const { path } = useRoute();
  const { user, loading, setUser } = useAuthStore();
  const { audience } = useUiStore();
  const mobileNavOpen = useUiStore((s) => s.mobileNavOpen);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);

  useEffect(() => {
    // Hard 3s timeout — without this, a slow / hanging /auth/me (cold
    // DB pool, sidecar warmup, dropped proxy) leaves `loading=true`
    // forever, the boot spinner shows forever, and every E2E selector
    // that waits for `[data-page="login"]` misses for the full test
    // timeout (2026-05-29 standalone-auth-hydration regression). On
    // timeout we resolve as "no session" → LoginPage renders.
    let cancelled = false;
    const t = setTimeout(() => {
      if (!cancelled) setUser(null);
    }, 3000);
    void whoAmI().then((u) => {
      if (cancelled) return;
      clearTimeout(t);
      setUser(u);
    });
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [setUser]);

  // Listen for the `dma:auth-expired` event fired by lib/api when any
  // request returns 401. Clear the cached user AND wipe the TanStack
  // Query cache + IndexedDB so cached entity data from the just-expired
  // session can't render after a re-login as a different user. The
  // explicit logout path in lib/auth.ts already does this; mid-session
  // 401s need the same treatment per the 2026-06-05 QA audit.
  useEffect(() => {
    function handleExpiry() {
      void import("@/lib/auth").then(({ clearClientSessionCache }) =>
        clearClientSessionCache(),
      );
      setUser(null);
    }
    window.addEventListener("dma:auth-expired", handleExpiry);
    return () => window.removeEventListener("dma:auth-expired", handleExpiry);
  }, [setUser]);

  // Responsive tables (≤760px): label every `.tbl` row cell from its column
  // header so the prototype's stacked-card mobile layout shows the right
  // prefixes. Generic — covers every current + future table automatically.
  useEffect(() => installTableLabels(), []);

  if (loading) {
    // Boot loader — matches the uploaded prototype's `loader-page
    // full-dark` shape (dark teal background, glyph with two concentric
    // animated rings + Zennify icon core, three-line title/body/detail
    // stack, indeterminate progress strip). CSS lives in
    // `frontend/styles/app.css` (.loader-page / .loader-card /
    // .loader-glyph / .loader-progress / .loader-title etc.).
    return (
      <div className="loader-page full-dark">
        <div className="loader-card">
          <div className="loader-glyph dark">
            <div className="ring" />
            <div className="ring-2" />
            <div className="core">
              <img
                src="/brand/icon_teal.png"
                width={36}
                height={36}
                alt=""
                style={{ borderRadius: 8, display: "block" }}
              />
            </div>
          </div>
          <div>
            <div className="loader-title">Loading DMA Insights…</div>
            <div className="loader-body" style={{ marginTop: 6 }}>
              Stitching together the assessment workspace.
            </div>
          </div>
          <div className="loader-progress" />
          <div className="loader-detail">
            Hydrating data layer · checking cached runs
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage onSuccess={setUser} />;
  }

  return (
    <div className="shell">
      <Sidebar />
      {mobileNavOpen ? (
        <div
          className="sb-backdrop"
          aria-hidden="true"
          onClick={() => setMobileNavOpen(false)}
        />
      ) : null}
      <div className="main">
        <TopBar audience={audience} />
        <main className="page-main">{dispatch(path)}</main>
      </div>
      <DrawerHost />
    </div>
  );
}
