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
} /*EDITMODE-END*/;

/* ── App provider ────────────────────────────────────────────────── */
function AppProvider({
  children
}) {
  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);
  const [role, setRole] = useState(TWEAK_DEFAULTS.role);
  // Production divergence: the host page verifies the session cookie
  // server-side and passes the verdict in DMA_LIVE.
  const [authed, setAuthed] = useState(!!(typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.authed));
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
  useEffect(() => {
    setRole(tweaks.role);
  }, [tweaks.role]);

  // Compute alert + active counts
  const openAlerts = DMA.ALERTS.filter(a => a.status === "OPEN").length;
  const activeRuns = DMA.ENTITIES.filter(e => e.in_progress).length;
  const pushToast = (text, kind) => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, {
      id,
      text,
      kind
    }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200);
  };
  const removeToast = id => setToasts(t => t.filter(x => x.id !== id));

  // Set up tweaks panel persistence
  const setTweak = useCallback((key, val) => {
    setTweaks(t => {
      const next = typeof key === "object" ? {
        ...t,
        ...key
      } : {
        ...t,
        [key]: val
      };
      try {
        window.parent.postMessage({
          type: "__edit_mode_set_keys",
          edits: next
        }, "*");
      } catch (e) {}
      return next;
    });
  }, []);
  const openEvidence = (evidenceId, subcap) => setEvidenceDrawer({
    evidenceId,
    subcap
  });
  const closeEvidence = () => setEvidenceDrawer(null);
  const openSubcap = subcapId => {
    // Find subcap across entities, jump to heatmap if on a client page
    if (route.path.startsWith("/clients/")) {
      const parts = route.path.split("/");
      const eid = parts[2];
      navigate(`/clients/${eid}/heatmap`, {
        subcap: subcapId
      });
    }
  };
  const openInsight = id => setInsightModal(id);
  const closeInsight = () => setInsightModal(null);
  const openRec = id => setRecModal(id);
  const closeRec = () => setRecModal(null);
  const openNewRun = () => setNewRunOpen(true);
  const closeNewRun = () => setNewRunOpen(false);
  const ctx = {
    tweaks,
    setTweak,
    role,
    setRole,
    authed,
    setAuthed,
    audience,
    setAudience,
    ipOpen,
    setIpOpen,
    ipSurface,
    setIpSurface,
    ipContext,
    setIpContext,
    evidenceDrawer,
    openEvidence,
    closeEvidence,
    insightModal,
    openInsight,
    closeInsight,
    recModal,
    openRec,
    closeRec,
    newRunOpen,
    openNewRun,
    closeNewRun,
    sidebarOpen,
    setSidebarOpen,
    openSubcap,
    pushToast,
    openAlerts,
    activeRuns,
    route
  };
  return /*#__PURE__*/React.createElement(AppCtx.Provider, {
    value: ctx
  }, children, /*#__PURE__*/React.createElement(ToastStack, {
    toasts: toasts,
    remove: removeToast
  }));
}

/* ── Tweaks panel content ────────────────────────────────────────── */
function MyTweaks() {
  const {
    tweaks,
    setTweak
  } = useApp();
  if (!window.TweaksPanel) return null;
  const {
    TweaksPanel,
    TweakSection,
    TweakRadio,
    TweakToggle,
    TweakSelect
  } = window;
  return /*#__PURE__*/React.createElement(TweaksPanel, {
    title: "Tweaks"
  }, /*#__PURE__*/React.createElement(TweakSection, {
    title: "Persona"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Role",
    value: tweaks.role,
    onChange: v => setTweak("role", v),
    options: [{
      label: "AE",
      value: "AE"
    }, {
      label: "Analyst",
      value: "ANALYST"
    }, {
      label: "Admin",
      value: "ADMIN"
    }]
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Audience",
    value: tweaks.audience_default,
    onChange: v => setTweak("audience_default", v),
    options: [{
      label: "Internal",
      value: "internal"
    }, {
      label: "Customer",
      value: "customer"
    }]
  }), /*#__PURE__*/React.createElement(TweakToggle, {
    label: "Intelligence panel default",
    value: tweaks.ip_open_default,
    onChange: v => setTweak("ip_open_default", v)
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Overview layout"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Hero layout",
    value: tweaks.overview_layout,
    onChange: v => setTweak("overview_layout", v),
    options: [{
      label: "Balanced",
      value: "balanced"
    }, {
      label: "Ring-left",
      value: "ring-left"
    }]
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Heatmap"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Cell density",
    value: tweaks.heatmap_density,
    onChange: v => setTweak("heatmap_density", v),
    options: [{
      label: "Compact",
      value: "compact"
    }, {
      label: "Comfortable",
      value: "comfortable"
    }]
  }), /*#__PURE__*/React.createElement(TweakToggle, {
    label: "Thin evidence outline",
    value: tweaks.show_thin_outline,
    onChange: v => setTweak("show_thin_outline", v)
  })), /*#__PURE__*/React.createElement(TweakSection, {
    title: "Phase"
  }, /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Run pipeline",
    value: tweaks.phase_mode,
    onChange: v => setTweak("phase_mode", v),
    options: [{
      label: "Phase 0",
      value: "phase0"
    }, {
      label: "Phase 1",
      value: "phase1"
    }]
  })));
}

/* ── Router ──────────────────────────────────────────────────────── */
function Router() {
  const {
    route,
    authed
  } = useApp();
  const {
    path
  } = route;

  // Auth gate: always start at /login until signed in
  if (!authed && path !== "/login") return /*#__PURE__*/React.createElement(LoginPage, null);
  if (path === "/login") return /*#__PURE__*/React.createElement(LoginPage, null);

  // Client-scoped routes
  const m = path.match(/^\/clients\/([^/]+)(?:\/([^/]+))?(?:\/(.+))?$/);
  if (m) {
    const id = m[1];
    const tab = m[2] || "overview";
    const sub = m[3];
    const entity = DMA.getEntity(id);
    if (!entity) return /*#__PURE__*/React.createElement(PageShell, {
      title: "Not found"
    }, /*#__PURE__*/React.createElement("div", {
      className: "empty"
    }, /*#__PURE__*/React.createElement("h3", null, "Entity not found")));
    const runId = route.params.run;
    const run = runId && entity.runs.find(r => r.id === runId) || entity.runs[0];
    let page = null;
    switch (tab) {
      case "overview":
        page = /*#__PURE__*/React.createElement(ClientOverview, {
          entity: entity,
          run: run
        });
        break;
      case "insights":
        page = /*#__PURE__*/React.createElement(ClientInsights, {
          entity: entity,
          run: run
        });
        break;
      case "heatmap":
        page = /*#__PURE__*/React.createElement(ClientHeatmap, {
          entity: entity,
          run: run
        });
        break;
      case "platform":
        page = /*#__PURE__*/React.createElement(ClientPlatform, {
          entity: entity,
          run: run
        });
        break;
      case "context":
        page = /*#__PURE__*/React.createElement(ClientContext, {
          entity: entity,
          run: run
        });
        break;
      case "health":
        page = /*#__PURE__*/React.createElement(ClientHealth, {
          entity: entity,
          run: run
        });
        break;
      case "techstack":
        page = sub ? /*#__PURE__*/React.createElement(ClientTechStackDetail, {
          entity: entity,
          run: run,
          techId: sub
        }) : /*#__PURE__*/React.createElement(ClientTechStack, {
          entity: entity,
          run: run
        });
        break;
      case "runs":
        page = /*#__PURE__*/React.createElement(ClientRuns, {
          entity: entity
        });
        break;
      default:
        page = /*#__PURE__*/React.createElement(ClientOverview, {
          entity: entity,
          run: run
        });
    }
    return /*#__PURE__*/React.createElement(ClientShell, {
      entity: entity,
      run: run,
      tab: tab
    }, page);
  }

  // Global pages
  if (path === "/" || path === "") return /*#__PURE__*/React.createElement(DashboardHome, null);
  if (path === "/clients") return /*#__PURE__*/React.createElement(EntityDirectoryPage, null);
  if (path === "/alerts") return /*#__PURE__*/React.createElement(AlertsPage, null);
  if (path === "/prospecting") return /*#__PURE__*/React.createElement(ProspectingPage, null);
  if (path === "/admin") return /*#__PURE__*/React.createElement(AdminPage, null);
  if (path === "/admin/import") return /*#__PURE__*/React.createElement(ImportPage, null);
  if (path === "/admin/import/audit") return /*#__PURE__*/React.createElement(ImportAuditPage, null);
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Not found"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("h3", null, "Page not found"), /*#__PURE__*/React.createElement("p", null, path), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: () => navigate("/")
  }, "Back to Dashboard")));
}

/* ── Root ────────────────────────────────────────────────────────── */
function App() {
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    const fontsReady = typeof document !== "undefined" && document.fonts && document.fonts.ready || Promise.resolve();
    Promise.all([fontsReady, new Promise(r => setTimeout(r, 600))]).then(() => setBooting(false));
  }, []);
  if (booting) return /*#__PURE__*/React.createElement(LoadingScreen, {
    variant: "boot",
    dark: true
  });
  return /*#__PURE__*/React.createElement(AppProvider, null, /*#__PURE__*/React.createElement(ConnectionWatcher, null), /*#__PURE__*/React.createElement(Router, null), /*#__PURE__*/React.createElement(EvidenceDrawer, null), /*#__PURE__*/React.createElement(InsightModal, null), /*#__PURE__*/React.createElement(RecommendationModal, null), /*#__PURE__*/React.createElement(NewRunModal, null), /*#__PURE__*/React.createElement(IntelligencePanel, null), /*#__PURE__*/React.createElement(MyTweaks, null));
}
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(/*#__PURE__*/React.createElement(App, null));