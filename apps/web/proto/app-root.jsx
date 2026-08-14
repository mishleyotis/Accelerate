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
  // The role the SERVER granted this session. Never settable from the UI: it
  // decides whether an "acting as" control exists at all, and the proxy clamps
  // every read against it (lib/identity.effectiveRole).
  const grantedRole =
    (typeof window !== "undefined" && window.DMA_LIVE && window.DMA_LIVE.role)
    || TWEAK_DEFAULTS.role;
  // Whether this session may preview another role. An AE has exactly one view,
  // so it gets no toggle rather than a toggle with one dead option.
  const canActAs = ["ADMIN", "ANALYST"].includes(String(grantedRole).toUpperCase());
  // EVERY session lands on the AE view. The AE is the reader the pages are
  // written for, so an analyst or admin should see what the field sees first and
  // opt into the internal detail deliberately. Previously the landing view was
  // the granted role, so an admin never saw the page an AE opens.
  const _landingRole = "AE";
  const [tweaks, setTweaks] = useState({ ...TWEAK_DEFAULTS, role: _landingRole });
  const [role, setRole] = useState(_landingRole);
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

  // Sync role tweak — but a session that may not act as another role cannot be
  // moved off its own view by the tweaks panel either.
  useEffect(() => {
    setRole(canActAs ? tweaks.role : grantedRole);
  }, [tweaks.role, canActAs, grantedRole]);

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
    grantedRole, canActAs,
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
  const { tweaks, setTweak, canActAs } = useApp();
  if (!window.TweaksPanel) return null;
  const { TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect } = window;

  return (
    <TweaksPanel title="Tweaks">
      <TweakSection title="Persona">
        {/* The Role radio is a DESIGN control for the standalone prototype. In
            the app it was a second, competing source of truth for the same
            state as the header's "Acting as": picking a view in the popover
            left this radio showing the old value, and the next tweaks sync put
            it back — the choice reverted with no explanation. It renders only
            where an acting-as control legitimately exists, and the header
            popover stays the one place to switch. */}
        {canActAs ? (
          <TweakRadio label="Role (preview)" value={tweaks.role} onChange={v => setTweak("role", v)} options={(() => {
            const RANK = { AE: 0, ANALYST: 1, ADMIN: 2 };
            const cap = RANK[grantedRole()] ?? 0;
            return [
              { label: "AE",       value: "AE" },
              { label: "Analyst",  value: "ANALYST" },
              { label: "Admin",    value: "ADMIN" },
            ].filter(o => RANK[o.value] <= cap);
          })()} />
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

/* ── Client-scoped route ─────────────────────────────────────────────
   ONE set of page components, fixture or live. The prototype is the
   renderer; in production its accessors read the promoted payload through
   window.DMA_ENTITY, which useLiveEntity installs before the first render
   and clears on every entity change. There is no second renderer to keep
   in step, and no path by which the fixture's fictional institution can
   appear under a real client's name — in LIVE mode every entity-scoped
   accessor answers null rather than falling back (data.js, and
   tests/adapter.test.js).

   What LIVE still changes is WHEN we render: nothing is drawn until the
   promoted pages have arrived, because a page that renders empty and then
   fills in reads as a page with nothing on it. */
const LIVE_MODE = typeof window !== "undefined" && !!window.DMA_LIVE;

/* The firmographics section states each figure as its own row; the prototype's
   entity shape reads them as named properties. Mapped by field name, and only
   where the producer stated a value — a field it left null stays absent so the
   panel prints a dash rather than a zero. */
/* Field names this mapper pins onto the prototype's entity shape. Everything
   NOT in here still renders — see `extra_fields` below — because the contract
   says the SUB-VERTICAL decides which fields exist ("SV5: AUM, client count,
   revenue, ADVISOR COUNT"), and a reader with a fixed vocabulary silently
   drops whatever its author had not met.

   Measured 2026-08-14 on a wealth-manager run: 13 fields served, 5 rendered
   nowhere (AUM, HQ, advisor_count, ownership, business_model) and Assets
   printed an em dash while `AUM 18.0 CAD billions` sat in the payload. The
   panel read as "this client disclosed almost nothing"; the producer had
   disclosed it and the reader threw it away. */
/* ONE declaration, read by both halves of this panel: the slot a served key
   maps onto, and — derived from it below — the set of keys a pinned row has
   already consumed.

   It is one table because it was two, and the two drifted. `cagr` was rendered
   as a pinned row and was NOT in the pinned key set, so the passthrough that
   exists to stop fields being dropped printed it a SECOND time underneath, as
   "Cagr". The build owner saw both rows. `footprint` had the same shape and had
   simply not been stated by a run yet. A key added to the row list now cannot
   be forgotten here, because there is no second place to forget it in. */
const FIRMO_ROWS = [
  // The contract states this one as a disjunction ("AUM or assets"), so a
  // sub-vertical reports one of the three and the panel keeps one row.
  { slot: "assets", keys: ["total_assets", "assets", "aum"] },
  { slot: "employees", keys: ["employees"] },
  { slot: "branches", keys: ["branches"] },
  { slot: "members", keys: ["member_count"] },
  { slot: "customers", keys: ["customer_count"] },
  { slot: "cagr", keys: ["cagr", "growth_rate"] },
  { slot: "net_worth_ratio", keys: ["net_worth_ratio"] },
  { slot: "regulator", keys: ["primary_regulator"] },
  // The spellings match the read path in dma_api/computed.py::_entity_domains,
  // because the same stated field both renders here and supplies O11's
  // denominator — one field recognised in two places by two different lists is
  // the drift class this build has paid for repeatedly.
  { slot: "website", keys: ["website", "web site", "domain", "primary domain",
                            "web domain", "entity website", "url"] },
  { slot: "hq", keys: ["hq", "headquarters"] },
  { slot: "footprint", keys: ["footprint"] },
  { slot: "charter", keys: ["charter"] },
  { slot: "founded", keys: ["founded", "founded_year", "year_founded"] },
];

const FIRMO_PINNED = new Set(FIRMO_ROWS.flatMap((r) => r.keys));
const FIRMO_SLOT = new Map(
  FIRMO_ROWS.flatMap((r) => r.keys.map((k) => [k, r.slot])));

/* `AUM` and `total_assets` are the same row on this panel: the contract's
   must-present set names them as a disjunction ("AUM or assets"), so a
   sub-vertical states one or the other and the panel has one Assets row. */
function firmoFields(firmo) {
  const out = {};
  // A `fields` that is not a list is not an absent section: it is a section
  // that cannot be read. `for…of` on it throws HERE, above every card and
  // above the shell, which is the one place a boundary cannot save the page —
  // so the shape is checked and the panel is told, rather than printing an em
  // dash per row and passing a malformed payload off as an unstated one.
  const fields = firmo && firmo.fields;
  if (fields !== null && fields !== undefined && !Array.isArray(fields)) {
    return { firmographics_unreadable: true };
  }
  out.extra_fields = [];
  for (const f of fields || []) {
    const key = String(f.field == null ? "" : f.field).trim().toLowerCase();
    if (f.value === null || f.value === undefined || f.value === "") {
      // A field the producer HELD (quarantined, with its reason) is a finding
      // and renders as a documented em dash. Silently skipping it is how a
      // held field became indistinguishable from one nobody asked for.
      if (f.quarantined && !FIRMO_PINNED.has(key)) {
        out.extra_fields.push({ field: f.field, value: null, unit: null,
                                as_of: f.as_of || null, held: true,
                                reason: f.quarantine_reason || null });
      }
      continue;
    }
    const n = Number(f.value);
    const num = isFinite(n) ? n : null;
    if (!FIRMO_PINNED.has(key)) {
      out.extra_fields.push({ field: f.field, value: f.value,
                              unit: f.unit || null, as_of: f.as_of || null,
                              held: false, reason: null });
      continue;
    }
    switch (FIRMO_SLOT.get(key)) {
      // One Assets row, whichever of the disjunction the sub-vertical states.
      case "assets":       out.assets = num; out.assets_unit = f.unit;
                           out.assets_label = key === "aum" ? "AUM" : "Assets";
                           break;
      case "employees":    out.employees = num; break;
      case "branches":     out.branches = num; break;
      case "regulator":    out.regulator = f.value; break;
      case "members":      out.members = num; break;
      case "customers":    out.customers = num; break;
      case "net_worth_ratio": out.net_worth_ratio = num; break;
      case "founded":      out.founded = f.value; break;
      case "charter":      out.charter = f.value; break;
      case "hq":           out.hq = f.value; break;
      case "website":      out.website = f.value; break;
      case "footprint":    out.stated_footprint = f.value; break;
      // The panel's CAGR row prefers the value COMPUTED from the promoted
      // financial series (adapter `cagrOf`), because a growth rate is a derived
      // value and the series is its source of truth. A run that also STATES one
      // is kept here as the fallback, carrying its own basis — so a client whose
      // series is too sparse to compute a rate still shows the rate it stated,
      // and neither renders twice.
      case "cagr":         out.stated_cagr = num;
                           out.stated_cagr_basis = f.unit || null; break;
      default: break;
    }
  }
  return out;
}

/* `advisor_count` -> "Advisor count". The producer's own key, humanised — not
   translated, because a label this app invented would disagree with the field
   name every other surface and every verdict uses. */
function humaniseFieldName(k) {
  const s = String(k == null ? "" : k).replace(/[_-]+/g, " ").trim();
  if (!s) return "";
  // Acronyms the producer wrote in caps stay in caps (AUM, CAGR, HQ, ROA).
  return s.split(" ").map(w =>
    w.length <= 4 && w === w.toUpperCase() ? w
      : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(" ");
}

function ClientRoute({ id, tab, sub }) {
  const { route, audience, role } = useApp();
  const entity = DMA.getEntity(id);
  const runId = route.params.run;
  const run = entity && ((runId && entity.runs.find(r => r.id === runId)) || entity.runs[0]);
  // The acting-as role is part of the read key: switching view re-fetches so the
  // SERVER decides what that role sees, rather than the client hiding fields it
  // already holds.
  const live = useLiveEntity(LIVE_MODE && entity ? entity.id : null,
                             audience, run && run.run_id, role);

  if (!entity) {
    return <PageShell title="Not found"><div className="empty"><h3>Entity not found</h3></div></PageShell>;
  }
  // The directory row carries identity (name, slug, runs, sub-vertical); the
  // promoted payload carries the assessment (cells, scores, platform fit).
  // Merged here, once, so every prototype component receives the entity shape
  // it was written against and none of them needs to know about LIVE.
  const ent = (LIVE_MODE && live.status === "ready" && live.entity)
    ? { ...entity, ...firmoFields(live.entity.firmographics),
        subcaps: live.entity.subcaps, oss: live.entity.oss,
        pillar_scores: Object.keys(live.entity.pillar_scores || {}).length
          ? live.entity.pillar_scores : entity.pillar_scores,
        // Whatever this merge omits reaches no card, which is how the run's own
        // peer medians and framing sentence stayed unread while the hero
        // rendered a constant offset and a hardcoded gap.
        pillar_peer_medians: live.entity.pillar_peer_medians || {},
        // The run's own pillar/category table (heatmap.workbook_scores): stated
        // category scores and peer medians, including categories the CURRENT
        // catalogue does not list. Every heatmap grain reads it, so a run
        // scored against v5.0's 17 categories renders all 17 instead of
        // silently dropping the ones v7.0 killed.
        workbookScores: live.entity.workbookScores || null,
        // The per-cell citation lists the producer actually sent. The drawer
        // resolves these ids rather than reverse-deriving a list from the link
        // table, which is what made one cell's drawer contradict its payload.
        cellEvidence: live.entity.cellEvidence || [],
        // CAGR is computed from the promoted financial series (adapter
        // `cagrOf`); footprint is the regulatory section's jurisdictions. Both
        // were adapted and then dropped here, so the firmographics card printed
        // an em dash for two values the run actually carries. Whatever this
        // merge omits reaches no card — that is the failure mode this block
        // keeps reproducing, so each new field is added here deliberately.
        cagr: (live.entity.financials && live.entity.financials.cagr) != null
          ? live.entity.financials.cagr : null,
        cagr_basis: (live.entity.financials && live.entity.financials.cagr_basis) || null,
        footprint: (live.entity.regulatory && live.entity.regulatory.jurisdictions)
          || entity.footprint || [],
        license: (live.entity.regulatory && live.entity.regulatory.license_type)
          || entity.license || null,
        framing: live.entity.framing || null,
        posture: live.entity.posture || null,
        posture_basis: live.entity.posture_basis || null,
        overall: live.entity.overall != null ? live.entity.overall : entity.overall,
        assessment_date: (live.entity.run && live.entity.run.completed_at)
          || entity.assessment_date || null }
    : entity;
  if (LIVE_MODE && live.status === "loading") {
    return <ClientShell entity={entity} run={run} tab={tab}><SectionLoader /></ClientShell>;
  }
  if (LIVE_MODE && live.status === "error") {
    // Two different failures, and telling them apart is the whole point: a run
    // with nothing promoted is a state of the RUN; a payload the adapter could
    // not read is a state of this APP, and calling the second one "nothing
    // promoted" would blame the producer for the reader's page.
    const unreadable = live.code === "payload_unreadable";
    return (
      <ClientShell entity={entity} run={run} tab={tab}>
        <div className="empty">
          <h3>{unreadable
            ? "This run's payload could not be read into the page"
            : "Nothing promoted for this run"}</h3>
          <p>{unreadable
            ? "The run promoted, but one of its sections did not arrive in the shape this page reads. Nothing here is missing from the assessment."
            : live.code === "no_promoted_pages"
              ? "No page of this run has promoted yet, so there is nothing to show."
              : live.code}</p>
          {unreadable && live.detail ? (
            <p className="f-mono" style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 8 }}>
              {live.detail}</p>
          ) : null}
        </div>
      </ClientShell>
    );
  }

  // A dashboard the server refused: a locked state naming the reason, not a
  // white page. The refusal is the API's (default-deny, invariant 5); the app
  // reports it rather than re-deciding it.
  const withheldReason = (LIVE_MODE && live.withheld && live.withheld[tab]) || null;
  if (withheldReason) {
    return (
      <ClientShell entity={ent} run={run} tab={tab}>
        <div className="empty">
          <div className="icon"><Icon name="lock" size={20} /></div>
          <h3>This dashboard is not available in the current view</h3>
          <p>{withheldReason}</p>
          <p style={{ marginTop: 8 }}>
            {audience === "customer"
              ? "Switch back to the internal audience to read it."
              : "Ask an administrator if you need access."}
          </p>
        </div>
      </ClientShell>
    );
  }

  let page = null;
  switch (tab) {
    case "overview":  page = <ClientOverview entity={ent} run={run} />; break;
    case "insights":  page = <ClientInsights entity={ent} run={run} />; break;
    case "heatmap":   page = <ClientHeatmap entity={ent} run={run} />; break;
    case "platform":  page = <ClientPlatform entity={ent} run={run} />; break;
    case "context":   page = <ClientContext entity={ent} run={run} />; break;
    case "health":    page = <ClientHealth entity={ent} run={run} />; break;
    case "techstack": page = sub ? <ClientTechStackDetail entity={ent} run={run} techId={sub} /> : <ClientTechStack entity={ent} run={run} />; break;
    case "runs":      page = <ClientRuns entity={ent} />; break;
    default:          page = <ClientOverview entity={ent} run={run} />;
  }
  // The boundary sits INSIDE the shell, never around it: a page that cannot
  // render must leave the reader the tab strip, the client bar and the nav,
  // because the way out of a broken dashboard is the next dashboard. Cards
  // carry their own boundaries (CardBoundary, per surface); this one only
  // catches what is above them — a page's own frame, or a section list the
  // page walks before it reaches a card.
  return (
    <ClientShell entity={ent} run={run} tab={tab}>
      <PageBoundary name={TAB_LABEL[tab] || tab}>{page}</PageBoundary>
    </ClientShell>
  );
}

const TAB_LABEL = {
  overview: "overview", insights: "insight cards", heatmap: "capability heatmap",
  platform: "platform fit", context: "context", health: "assessment health",
  techstack: "technology stack", runs: "runs",
};

/* ── Router ──────────────────────────────────────────────────────── */
function Router() {
  const { route, authed } = useApp();
  const { path } = route;

  // Auth gate: always start at /login until signed in
  if (!authed && path !== "/login") return <LoginPage />;
  if (path === "/login") return <LoginPage />;

  // Client-scoped routes — a component of its own because it holds hooks
  // (the live serving-tier read), and a hook inside a router branch would
  // change hook order as the route changes.
  const m = path.match(/^\/clients\/([^/]+)(?:\/([^/]+))?(?:\/(.+))?$/);
  if (m) return <ClientRoute id={m[1]} tab={m[2] || "overview"} sub={m[3]} />;

  // Global pages
  if (path === "/" || path === "")            return <DashboardHome />;
  if (path === "/clients")                    return <EntityDirectoryPage />;
  if (path === "/alerts")                     return <AlertsPage />;
  if (path === "/prospecting")                return <ProspectingPage />;
  // Production divergence: admin surfaces require the server-granted
  // ADMIN role — direct hash navigation included, not just the nav.
  if (path.startsWith("/admin")) {
    if (grantedRole() !== "ADMIN") {
      return <PageShell title="Not authorised"><div className="empty"><h3>Not authorised</h3><p>The admin console requires an ADMIN grant on your account.</p><button className="btn btn-primary" onClick={() => navigate("/")}>Back to Dashboard</button></div></PageShell>;
    }
    if (path === "/admin")                    return <AdminPage />;
    if (path === "/admin/import")             return <ImportPage />;
    if (path === "/admin/import/audit")       return <ImportAuditPage />;
  }

  return <PageShell title="Not found"><div className="empty"><h3>Page not found</h3><p>{path}</p><button className="btn btn-primary" onClick={() => navigate("/")}>Back to Dashboard</button></div></PageShell>;
}

/* ── Root ────────────────────────────────────────────────────────── */
/* The backstop. It renders the app's own frame — brand, a sentence, and the
   two actions that exist — so a fault above every card is a page the reader
   can act on rather than a white screen. It claims nothing about the data. */
function RootBoundary({ children }) {
  return (
    <RenderBoundary name="application" fallback={(err) => (
      <div className="loader-page">
        <div className="loader-card">
          <BrandMark size={34} />
          <div>
            <div className="loader-title">This page could not be rendered</div>
            <div className="loader-body" style={{ marginTop: 6 }}>
              DMA Insights hit a value it cannot draw. Nothing in the assessment
              has changed, and no data was written.
            </div>
          </div>
          <div className="f-mono" style={{ fontSize: 10.5, color: "var(--z-muted)",
                                           wordBreak: "break-word" }}>
            {(err && err.message) || String(err)}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-primary" onClick={() => window.location.reload()}>Reload</button>
            <button className="btn btn-tertiary" onClick={() => { navigate("/"); window.location.reload(); }}>Back to dashboard</button>
          </div>
        </div>
      </div>
    )}>{children}</RenderBoundary>
  );
}

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
      {/* The last stop, and only the last stop. Cards carry their own
          boundaries and every client page carries one inside its shell; this
          catches what is above both — the router itself, the shell's chrome,
          the entity merge in ClientRoute. Without it those faults still empty
          the <body>, which is the state this repair exists to make
          impossible. It is deliberately NOT the app's only boundary: one
          boundary at the root turns a blank page into a blank page with a
          sentence on it, and loses every card that was rendering fine. */}
      <RootBoundary><Router /></RootBoundary>
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
