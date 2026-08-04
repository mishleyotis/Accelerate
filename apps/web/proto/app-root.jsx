/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · App root - router + provider + tweaks
   ═══════════════════════════════════════════════════════════════════════ */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "role": "ANALYST",
  "audience_default": "internal",
  "ip_open_default": false,
  "overview_layout": "balanced",
  "heatmap_density": "comfortable",
  "show_thin_outline": true,
  "phase_mode": "phase1",
  "accent_palette": "teal"
}/*EDITMODE-END*/;

/* ── App provider ────────────────────────────────────────────────── */
function AppProvider({ children }) {
  // Production divergence: the session's role seeds the tweaks too —
  // the tweaks-sync effect below would otherwise clobber it on mount.
  const _sessionRole =
    (typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.role) || TWEAK_DEFAULTS.role;
  const [tweaks, setTweaks] = useState({ ...TWEAK_DEFAULTS, role: _sessionRole });
  const [role, setRole] = useState(_sessionRole);
  // Production divergence: the host page verifies the session cookie
  // server-side and passes the verdict in DMA_LIVE.
  const [authed, setAuthed] = useState(
    !!(typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.authed));
  const [audience, setAudience] = useState(TWEAK_DEFAULTS.audience_default);
  const [ipOpen, setIpOpen] = useState(TWEAK_DEFAULTS.ip_open_default);
  const [ipSurface, setIpSurface] = useState("why_now");
  const [ipContext, setIpContext] = useState(null);
  const [evidenceDrawer, setEvidenceDrawer] = useState(null);
  const [insightModal, setInsightModal] = useState(null);
  const [recModal, setRecModal] = useState(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const route = useRoute();

  // Sync role tweak
  useEffect(() => { setRole(tweaks.role); }, [tweaks.role]);

  // Compute alert + active counts
  const openAlerts = DMA.ALERTS.filter(a => a.status === "OPEN").length;
  const activeRuns = DMA.ENTITIES.filter(e => e.in_progress).length;

  const pushToast = (text, kind) => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, { id, text, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200);
  };
  const removeToast = id => setToasts(t => t.filter(x => x.id !== id));

  // Set up tweaks panel persistence
  const setTweak = useCallback((key, val) => {
    setTweaks(t => {
      const next = typeof key === "object" ? { ...t, ...key } : { ...t, [key]: val };
      try { window.parent.postMessage({ type: "__edit_mode_set_keys", edits: next }, "*"); } catch (e) {}
      return next;
    });
  }, []);

  const openEvidence = (evidenceId, subcap) => setEvidenceDrawer({ evidenceId, subcap });
  const closeEvidence = () => setEvidenceDrawer(null);
  const openSubcap = (subcapId) => {
    // Find subcap across entities, jump to heatmap if on a client page
    if (route.path.startsWith("/clients/")) {
      const parts = route.path.split("/");
      const eid = parts[2];
      navigate(`/clients/${eid}/heatmap`, { subcap: subcapId });
    }
  };
  const openInsight = id => setInsightModal(id);
  const closeInsight = () => setInsightModal(null);
  const openRec = id => setRecModal(id);
  const closeRec = () => setRecModal(null);
  const openNewRun = () => setNewRunOpen(true);
  const closeNewRun = () => setNewRunOpen(false);

  const ctx = {
    tweaks, setTweak,
    role, setRole,
    authed, setAuthed,
    audience, setAudience,
    ipOpen, setIpOpen, ipSurface, setIpSurface, ipContext, setIpContext,
    evidenceDrawer, openEvidence, closeEvidence,
    insightModal, openInsight, closeInsight,
    recModal, openRec, closeRec,
    newRunOpen, openNewRun, closeNewRun,
    sidebarOpen, setSidebarOpen,
    openSubcap,
    pushToast,
    openAlerts, activeRuns,
    route,
  };

  return <AppCtx.Provider value={ctx}>
    {children}
    <ToastStack toasts={toasts} remove={removeToast} />
  </AppCtx.Provider>;
}

/* ── Tweaks panel content ────────────────────────────────────────── */
function MyTweaks() {
  const { tweaks, setTweak } = useApp();
  if (!window.TweaksPanel) return null;
  const { TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect } = window;

  return (
    <TweaksPanel title="Tweaks">
      <TweakSection title="Persona">
        <TweakRadio label="Role" value={tweaks.role} onChange={v => setTweak("role", v)} options={[
          { label: "AE",       value: "AE" },
          { label: "Analyst",  value: "ANALYST" },
          { label: "Admin",    value: "ADMIN" },
        ]} />
        <TweakRadio label="Audience" value={tweaks.audience_default} onChange={v => setTweak("audience_default", v)} options={[
          { label: "Internal", value: "internal" },
          { label: "Customer", value: "customer" },
        ]} />
        <TweakToggle label="Intelligence panel default" value={tweaks.ip_open_default} onChange={v => setTweak("ip_open_default", v)} />
      </TweakSection>
      <TweakSection title="Overview layout">
        <TweakRadio label="Hero layout" value={tweaks.overview_layout} onChange={v => setTweak("overview_layout", v)} options={[
          { label: "Balanced",  value: "balanced" },
          { label: "Ring-left", value: "ring-left" },
        ]} />
      </TweakSection>
      <TweakSection title="Heatmap">
        <TweakRadio label="Cell density" value={tweaks.heatmap_density} onChange={v => setTweak("heatmap_density", v)} options={[
          { label: "Compact",     value: "compact" },
          { label: "Comfortable", value: "comfortable" },
        ]} />
        <TweakToggle label="Thin evidence outline" value={tweaks.show_thin_outline} onChange={v => setTweak("show_thin_outline", v)} />
      </TweakSection>
      <TweakSection title="Phase">
        <TweakRadio label="Run pipeline" value={tweaks.phase_mode} onChange={v => setTweak("phase_mode", v)} options={[
          { label: "Phase 0",  value: "phase0" },
          { label: "Phase 1",  value: "phase1" },
        ]} />
      </TweakSection>
    </TweaksPanel>
  );
}

/* ── Router ──────────────────────────────────────────────────────── */
function Router() {
  const { route, authed } = useApp();
  const { path } = route;

  // Auth gate: always start at /login until signed in
  if (!authed && path !== "/login") return <LoginPage />;
  if (path === "/login") return <LoginPage />;

  // Client-scoped routes
  const m = path.match(/^\/clients\/([^/]+)(?:\/([^/]+))?(?:\/(.+))?$/);
  if (m) {
    const id = m[1];
    const tab = m[2] || "overview";
    const sub = m[3];
    const entity = DMA.getEntity(id);
    if (!entity) return <PageShell title="Not found"><div className="empty"><h3>Entity not found</h3></div></PageShell>;
    const runId = route.params.run;
    const run = (runId && entity.runs.find(r => r.id === runId)) || entity.runs[0];

    let page = null;
    switch (tab) {
      case "overview":  page = <ClientOverview entity={entity} run={run} />; break;
      case "insights":  page = <ClientInsights entity={entity} run={run} />; break;
      case "heatmap":   page = <ClientHeatmap entity={entity} run={run} />; break;
      case "platform":  page = <ClientPlatform entity={entity} run={run} />; break;
      case "context":   page = <ClientContext entity={entity} run={run} />; break;
      case "health":    page = <ClientHealth entity={entity} run={run} />; break;
      case "techstack": page = sub ? <ClientTechStackDetail entity={entity} run={run} techId={sub} /> : <ClientTechStack entity={entity} run={run} />; break;
      case "runs":      page = <ClientRuns entity={entity} />; break;
      default:          page = <ClientOverview entity={entity} run={run} />;
    }
    return <ClientShell entity={entity} run={run} tab={tab}>{page}</ClientShell>;
  }

  // Global pages
  if (path === "/" || path === "")            return <DashboardHome />;
  if (path === "/clients")                    return <EntityDirectoryPage />;
  if (path === "/alerts")                     return <AlertsPage />;
  if (path === "/prospecting")                return <ProspectingPage />;
  if (path === "/admin")                      return <AdminPage />;
  if (path === "/admin/import")               return <ImportPage />;
  if (path === "/admin/import/audit")         return <ImportAuditPage />;

  return <PageShell title="Not found"><div className="empty"><h3>Page not found</h3><p>{path}</p><button className="btn btn-primary" onClick={() => navigate("/")}>Back to Dashboard</button></div></PageShell>;
}

/* ── Root ────────────────────────────────────────────────────────── */
function App() {
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    const fontsReady = (typeof document !== "undefined" && document.fonts && document.fonts.ready) || Promise.resolve();
    Promise.all([fontsReady, new Promise(r => setTimeout(r, 600))]).then(() => setBooting(false));
  }, []);
  if (booting) return <LoadingScreen variant="boot" dark />;
  return (
    <AppProvider>
      <ConnectionWatcher />
      <Router />
      <EvidenceDrawer />
      <InsightModal />
      <RecommendationModal />
      <NewRunModal />
      <IntelligencePanel />
      <MyTweaks />
    </AppProvider>
  );
}

// Production divergence: mount OUTSIDE the host framework's hydration
// tree (the host page renders no #app), so server hydration never
// reconciles SPA-owned DOM.
const _mount = document.getElementById("app") || (() => {
  const d = document.createElement("div");
  d.id = "app";
  document.body.appendChild(d);
  return d;
})();
const root = ReactDOM.createRoot(_mount);
root.render(<App />);
