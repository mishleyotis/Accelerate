/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · App root - router + provider + tweaks
   ═══════════════════════════════════════════════════════════════════════ */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "role": "AE",
  "audience_default": "internal",
  "ip_open_default": false,
  "overview_layout": "balanced",
  "heatmap_density": "comfortable",
  "show_thin_outline": true,
  "phase_mode": "phase1",
  "accent_palette": "teal"
}/*EDITMODE-END*/;

/* ── Role allow-lists (single source of truth for client-side gating) ─
   The backend (Stage 11) re-checks these against ADMIN_EMAILS in
   `backend/app/auth.py`; the frontend only uses them to pick which
   chrome to render and which role toggles to enable. Server-side
   audience/role enforcement is the real defence — these lists
   are belt-and-suspenders for the UI.
*/
const ADMIN_EMAILS = new Set([
  "mishley.otiende@zennify.com",
  "richard.odhiambo@zennify.com",
  "sam.friedewald@zennify.com",
  "kevin.murray@zennify.com",
  "chris.conant@zennify.com",
  "carlie.welsh@zennify.com",
  "tom.hedgecoth@zennify.com",
]);
const ANALYST_EMAILS = new Set([
  "richard.odhiambo@zennify.com",
  "dma@zennify.com",
]);

function deriveRoleFromEmail(email) {
  const e = (email || "").trim().toLowerCase();
  if (ADMIN_EMAILS.has(e))   return "ADMIN";
  if (ANALYST_EMAILS.has(e)) return "ANALYST";
  return "AE";
}

function deriveNameFromEmail(email) {
  const local = (email || "").split("@")[0] || "";
  // first.last → First Last (titlecase). Handles middle dots gracefully.
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map(s => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase())
    .join(" ")
    || "User";
}

function deriveInitialsFromName(name) {
  return (name || "User")
    .split(/\s+/)
    .filter(Boolean)
    .map(s => s[0].toUpperCase())
    .slice(0, 2)
    .join("");
}

// Persist user across hash navigations + reloads (session-scoped).
function loadStoredUser() {
  try {
    const raw = sessionStorage.getItem("dma_user");
    if (!raw) return null;
    const u = JSON.parse(raw);
    if (!u || !u.email) return null;
    return u;
  } catch (e) { return null; }
}

// Acting-as persistence: the "ACTING AS" segmented control downgrades
// only — an Admin can act as AE for testing, an AE cannot escalate. The
// effective role used everywhere is the minimum (least-privilege) of the
// real role and the acting-as role, ordered AE=1, ANALYST=2, ADMIN=3.
const ROLE_RANK = { AE: 1, ANALYST: 2, ADMIN: 3 };
function loadActingAs() {
  try {
    const v = localStorage.getItem("dma:acting-as");
    return v && ROLE_RANK[v] ? v : null;
  } catch (e) { return null; }
}
function saveActingAs(role) {
  try {
    if (role) localStorage.setItem("dma:acting-as", role);
    else localStorage.removeItem("dma:acting-as");
  } catch (e) {}
}
function effectiveRole(realRole, actingAs) {
  if (!actingAs) return realRole || "AE";
  const r = ROLE_RANK[realRole] || 1;
  const a = ROLE_RANK[actingAs] || 1;
  // Downgrade only — clamp acting-as to realRole's privilege ceiling.
  return ROLE_RANK[realRole] != null && a <= r ? actingAs : (realRole || "AE");
}

// can_act_as defaulting per role rank. Server is the source of truth
// but provides a sensible fallback when the response shape is partial.
function canActAsForRole(role) {
  if (role === "ADMIN")    return ["ADMIN", "ANALYST", "AE"];
  if (role === "ANALYST")  return ["ANALYST", "AE"];
  if (role === "CUSTOMER") return ["CUSTOMER"];
  return ["AE"];
}

// Normalize a user object from either a server response
// ({user_id, email, role, name, can_act_as}) or a back-compat email
// string. Server role wins — the previous implementation discarded
// the server role and re-derived from email via ADMIN_EMAILS /
// ANALYST_EMAILS hardcoded sets, which silently dropped any server
// promotion/demotion. Now the server is authoritative.
function normalizeServerUser(input) {
  if (typeof input === "string") {
    const email = (input || "").trim().toLowerCase();
    const role = deriveRoleFromEmail(email);
    return {
      email,
      role,
      name: deriveNameFromEmail(email),
      initials: deriveInitialsFromName(deriveNameFromEmail(email)),
      can_act_as: canActAsForRole(role),
    };
  }
  const obj = input || {};
  const email = String(obj.email || "").trim().toLowerCase();
  const role = obj.role || (email ? deriveRoleFromEmail(email) : "AE");
  const name = obj.name || deriveNameFromEmail(email);
  return {
    user_id: obj.user_id,
    email,
    role,
    name,
    initials: deriveInitialsFromName(name),
    can_act_as: (
      Array.isArray(obj.can_act_as) && obj.can_act_as.length > 0
        ? obj.can_act_as
        : canActAsForRole(role)
    ),
  };
}

/* ── App provider ────────────────────────────────────────────────── */
function AppProvider({ children }) {
  const stored = loadStoredUser();
  const storedActing = loadActingAs();
  // Seed role from stored acting-as IF the user can downgrade to it,
  // otherwise use the user's real role. effectiveRole() handles the
  // clamp + null fallback.
  const seedRole = stored
    ? effectiveRole(stored.role, storedActing)
    : (storedActing || TWEAK_DEFAULTS.role);
  // Seed the tweaks-panel role from the stored user so the useEffect
  // sync below doesn't downgrade a logged-in ADMIN to TWEAK_DEFAULTS.
  const [tweaks, setTweaks] = useState({
    ...TWEAK_DEFAULTS,
    role: seedRole,
  });
  const [user, setUserState] = useState(stored);                          // { email, name, role, initials } | null
  const [role, setRoleState] = useState(seedRole);
  const [authed, setAuthed] = useState(!!stored);

  // Persist user on every change; clear on sign-out.
  const setUser = useCallback((next) => {
    setUserState(next);
    try {
      if (next) sessionStorage.setItem("dma_user", JSON.stringify(next));
      else sessionStorage.removeItem("dma_user");
    } catch (e) {}
  }, []);

  // setRole is gated client-side to roles the signed-in user is
  // permitted to act as (downgrade-only). Server still re-checks every
  // request. The selected acting-as role is persisted to localStorage
  // so it survives page reloads.
  const setRole = useCallback((newRole) => {
    if (!user) { setRoleState(newRole); return; }
    if (!user.can_act_as.includes(newRole)) return;     // silently refuse — UI button is also disabled
    // Defence-in-depth: even with can_act_as honoured, never allow an
    // effective role that exceeds the user's real privilege.
    const effective = effectiveRole(user.role, newRole);
    setRoleState(effective);
    setUser({ ...user, role: effective });
    saveActingAs(effective === user.role ? null : effective);
    setTweaks(t => ({ ...t, role: effective }));
  }, [user, setUser]);

  // signIn is called from LoginPage / quick-in buttons / /auth/me on
  // boot. The server is authoritative for role + can_act_as; the
  // string-email signature is a back-compat shim for callers that only
  // have an email (quick-in buttons in dev tweaks panel).
  const signIn = useCallback((serverUserOrEmail) => {
    const next = normalizeServerUser(serverUserOrEmail);
    setUser(next);
    // Apply any previously-persisted acting-as (downgrade-only). If the
    // saved value isn't in can_act_as, fall through to the server role.
    const acting = loadActingAs();
    const initialRole = acting && next.can_act_as.includes(acting)
      ? effectiveRole(next.role, acting)
      : next.role;
    setRoleState(initialRole);
    setAuthed(true);
    setTweaks(t => ({ ...t, role: initialRole }));
  }, [setUser]);

  const signOut = useCallback(() => {
    setUser(null);
    setRoleState(TWEAK_DEFAULTS.role);
    setAuthed(false);
    saveActingAs(null);
  }, [setUser]);

  // ── Boot hydration from /api/v1/auth/me ─────────────────────────────
  // The dma_session JWT cookie is HttpOnly so the SPA can't read it
  // directly. Instead, on first mount we call /auth/me — when the
  // cookie is valid the backend returns the user record and we
  // signIn() with it. When the cookie is missing/expired the call
  // 401s and we leave authed=false so the Router shows LoginPage.
  //
  // Without this:
  //   - E2E tests inject the JWT via Playwright's addCookies and
  //     verify /auth/me returns 200, but the SPA never reads it →
  //     stays on LoginPage → every authenticated assertion times out.
  //   - Operators returning to the app after closing their tab have
  //     to sign in again even though their cookie is still valid.
  //
  // Idempotent: re-running on an already-signed-in user is a no-op
  // (signIn re-applies the same state). Best-effort: network errors
  // / 5xx leave authed=false; the operator sees LoginPage with the
  // backend-error banner from /healthz polling.
  const [hydrating, setHydrating] = useState(!stored);
  useEffect(() => {
    if (stored) {
      // sessionStorage had a user — already authed, no boot fetch needed.
      setHydrating(false);
      return;
    }
    // Hard 2.5s timeout — without this, a slow /auth/me (DB pool cold
    // start, sidecar warmup, proxy hang) leaves the SPA in the
    // hydration spinner forever and every E2E selector misses for the
    // full 15s test timeout. The CI symptom is "Admin persona › Admin
    // page is accessible times out" while OTHER admin routes pass
    // because they hit the same /auth/me on a warm cache.
    //
    // 2.5s is generous — /auth/me is a sub-100ms DB read on a warm
    // pool. The timeout only trips on genuinely-stuck networks; the
    // operator-visible behaviour is "if my cookie didn't validate in
    // 2.5s, treat me as logged out and show LoginPage".
    let cancelled = false;
    let fallbackTimer = null;
    // Belt-and-braces: even if AbortController doesn't fire (Chromium
    // sometimes swallows the abort), this hard timer ALSO flips
    // hydrating=false so the LoginPage renders + the helper finds
    // [data-page="login"].
    fallbackTimer = setTimeout(() => {
      if (!cancelled) setHydrating(false);
    }, 3000);
    const ctl = new AbortController();
    const fetchTimeout = setTimeout(() => ctl.abort(), 2500);
    (async () => {
      try {
        const r = await fetch("/api/v1/auth/me", {
          credentials: "include",
          headers: { Accept: "application/json" },
          signal: ctl.signal,
        });
        if (cancelled) return;
        if (r.ok) {
          const body = await r.json();
          if (body && body.email) {
            signIn(body);
          }
        }
      } catch (e) {
        // AbortError / network blip / proxy down → stay on LoginPage.
        // The BackendErrorBanner surfaces the underlying failure.
      } finally {
        clearTimeout(fetchTimeout);
        clearTimeout(fallbackTimer);
        if (!cancelled) setHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(fetchTimeout);
      clearTimeout(fallbackTimer);
    };
  // signIn / stored only change as a side-effect of THIS hook so the
  // empty-deps form is correct here — we want a one-shot boot fetch.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [audience, setAudienceState] = useState(TWEAK_DEFAULTS.audience_default);
  // 2026-05-28 audit fix (Probe 8): mirror audience into window.DMA.tweaks
  // so backend-loader.js::_withAudience can read it without re-importing
  // React state. The previous "Customer view" toggle was UI-only — the
  // backend audience strip never fired because no call carried ?view=customer.
  const setAudience = (next) => {
    setAudienceState(next);
    if (window.DMA) {
      window.DMA.tweaks = window.DMA.tweaks || {};
      window.DMA.tweaks.audience = next;
    }
  };
  useEffect(() => {
    if (window.DMA) {
      window.DMA.tweaks = window.DMA.tweaks || {};
      window.DMA.tweaks.audience = audience;
    }
  }, [audience]);
  const [ipOpen, setIpOpen] = useState(TWEAK_DEFAULTS.ip_open_default);
  // ipSurface starts null so the IntelligencePanel falls into welcome
  // mode by default. Pages set this when the user opens a per-surface
  // synthesis (subcap drill, platform card, focus area, insight card).
  const [ipSurface, setIpSurface] = useState(null);
  const [ipContext, setIpContext] = useState(null);
  const [evidenceDrawer, setEvidenceDrawer] = useState(null);
  const [insightModal, setInsightModal] = useState(null);
  const [recModal, setRecModal] = useState(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const route = useRoute();

  // Sync role tweak (tweaks panel) — but only honour roles the signed-in
  // user is permitted to act as (downgrade-only), AND only when the
  // tweak diverges from the current effective role. Without the
  // divergence check, the first render of TWEAK_DEFAULTS.role ("AE")
  // would silently downgrade an ADMIN user to AE before they could act.
  useEffect(() => {
    if (!user) { setRoleState(tweaks.role); return; }
    if (tweaks.role === role) return;                            // already in sync
    if (user.can_act_as.includes(tweaks.role)) setRole(tweaks.role);
  }, [tweaks.role, user, role, setRole]);

  // Compute alert + active counts (always safe on empty arrays).
  const openAlerts = (DMA.ALERTS || []).filter(a => a.status === "OPEN").length;
  const activeRuns = (DMA.ENTITIES || []).filter(e => e.in_progress).length;

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
    user, signIn, signOut,
    role, setRole,
    authed, setAuthed, hydrating,
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
  const { tweaks, setTweak, user } = useApp();
  if (!window.TweaksPanel) return null;
  const { TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect } = window;
  // Role options gated by the signed-in user's allow-list (can_act_as).
  // Hide tiers the user can't act as — don't grey them out. AE-only
  // users (one option) get no role row at all.
  const canActAs = user?.can_act_as || ["AE"];
  const allRoleOptions = [
    { label: "AE",      value: "AE" },
    { label: "Analyst", value: "ANALYST" },
    { label: "Admin",   value: "ADMIN" },
  ];
  const roleOptions = allRoleOptions.filter(o => canActAs.includes(o.value));

  return (
    <TweaksPanel title="Tweaks">
      <TweakSection title="Persona">
        {roleOptions.length > 1 ? (
          <TweakRadio label="Role" value={tweaks.role} onChange={v => setTweak("role", v)} options={roleOptions} />
        ) : null}
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
  const { route, authed, hydrating } = useApp();
  const { path } = route;

  // While the boot /auth/me probe is in flight (cookie present from a
  // prior session OR injected by Playwright), render a spinner instead
  // of flashing LoginPage. Without this, the user would briefly see
  // LoginPage even though their cookie is valid + the SPA was about to
  // signIn from the /auth/me response.
  if (hydrating) return <LoadingScreen variant="boot" dark />;

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

const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App />);
