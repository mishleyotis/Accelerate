/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · App shell - Sidebar, TopBar, ClientShell, Banners
   ═══════════════════════════════════════════════════════════════════════ */

function Sidebar() {
  const { route, role, openAlerts, activeRuns, setAuthed, sidebarOpen, setSidebarOpen } = useApp();
  const path = route.path;
  const allHrefs = ["/", "/clients", "/alerts", "/prospecting", "/admin", "/admin/import", "/admin/import/audit"];
  const activeHref = (() => {
    if (path === "/") return "/";
    const matches = allHrefs.filter(h => h !== "/" && (path === h || path.startsWith(h + "/")));
    if (matches.length === 0) return null;
    // Pick longest (most specific)
    return matches.sort((a, b) => b.length - a.length)[0];
  })();
  const isOn = (href) => href === activeHref;

  const go = (href) => { setSidebarOpen(false); navigate(href); };

  const NavItem = ({ href, icon, label, badge, dim, dot, indent }) => (
    <button
      className={`sb-a ${isOn(href) ? "on" : ""} ${dim ? "dim" : ""}`}
      onClick={() => !dim && go(href)}
      style={indent ? { marginLeft: 12 } : null}
    >
      {icon ? <Icon name={icon} size={15} /> : null}
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      {badge != null && badge > 0 ? <span className="sb-badge">{badge}</span> : null}
      {dot ? <span className="sb-dot" /> : null}
    </button>
  );

  return (
    <>
      {sidebarOpen ? <div className="sb-backdrop" onClick={() => setSidebarOpen(false)} /> : null}
      <aside className={`sb ${sidebarOpen ? "open" : ""}`}>
        <div className="sb-head">
          <BrandMark size={32} />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="sb-brand">DMA Insights</div>
            <div className="sb-sub">Zennify</div>
          </div>
          <button className="icon-btn" style={{ color: "rgba(255,255,255,.6)", display: "none" }} onClick={() => setSidebarOpen(false)} aria-label="Close menu"><Icon name="x" size={14} /></button>
        </div>

        <nav className="sb-nav">
          <NavItem href="/"            icon="home"     label="Dashboard" />
          <NavItem href="/clients"     icon="users"    label="Clients"   dot={activeRuns > 0} />
          <NavItem href="/alerts"      icon="bell"     label="Alerts"
            badge={role === "ANALYST" || role === "ADMIN" ? openAlerts : null}
            dim={role === "AE"} />
          <NavItem href="/prospecting" icon="envelope" label="Prospecting" />

          {role === "ADMIN" ? (
            <div className="sb-grp">
              <div className="sb-gl">Admin</div>
              <NavItem href="/admin"              icon="settings" label="Admin home" />
              <NavItem href="/admin/import"       icon="drive"    label="Import &amp; jobs" />
              <NavItem href="/admin/import/audit" icon="evidence" label="Import audit" />
            </div>
          ) : null}
        </nav>

        <div className="sb-foot">
          <div className="sb-avatar">MO</div>
          <div className="sb-foot-meta">
            <div className="sb-foot-name">Mishley O.</div>
            <div className="sb-foot-role">{role}</div>
          </div>
          <button className="icon-btn" style={{ color: "rgba(255,255,255,.6)" }} title="Sign out" onClick={() => { setAuthed(false); navigate("/login"); }}>
            <Icon name="logout" size={14} />
          </button>
        </div>
      </aside>
    </>
  );
}

/* ── Top bar (global) ─────────────────────────────────────────────── */
function TopBar({ title, crumbs, right }) {
  const { setSidebarOpen } = useApp();
  const [openPop, setOpenPop] = useState(null); // 'notif' | 'settings' | 'search' | null
  const [q, setQ] = useState("");
  const [showMobileSearch, setShowMobileSearch] = useState(false);

  // Quick search results
  const ql = q.toLowerCase().trim();
  const searchResults = useMemo(() => {
    if (!ql) return null;
    const entities = DMA.ENTITIES.filter(e => e.name.toLowerCase().includes(ql) || (e.domain || "").includes(ql)).slice(0, 4)
      .map(e => ({ kind: "entity", title: e.name, sub: DMA.SUBVERTICAL_LABEL[e.subvertical], route: `/clients/${e.id}/overview`, icon: "users" }));
    const insights = DMA.INSIGHT_CARDS.filter(c => c.title.toLowerCase().includes(ql) || c.id.toLowerCase().includes(ql)).slice(0, 3)
      .map(c => ({ kind: "insight", title: c.title, sub: `${c.id} · ${c.flag}`, route: `/clients/fce-001/insights?card=${c.id}`, icon: "insight" }));
    const evidence = DMA.EVIDENCE.filter(e => e.title.toLowerCase().includes(ql) || e.id.toLowerCase().includes(ql)).slice(0, 3)
      .map(e => ({ kind: "evidence", title: e.title, sub: `${e.id} · ${e.tier}`, route: `/clients/fce-001/insights?evidence=${e.id}`, icon: "evidence" }));
    return [...entities, ...insights, ...evidence];
  }, [ql]);

  // ⌘K shortcut
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setOpenPop("search"); }
      else if (e.key === "Escape") setOpenPop(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const notifUnread = DMA.NOTIFICATIONS.filter((n, i) => i < 3).length;

  return (
    <header className="topbar">
      <button className="sb-mobile-btn" onClick={() => setSidebarOpen(o => !o)} aria-label="Menu" title="Menu">
        <Icon name="menu" size={18} />
      </button>
      <div className="topbar-l">
        {crumbs ? (
          <div className="topbar-crumbs">
            {crumbs.map((c, i) => (
              <React.Fragment key={i}>
                {c.href ? <a href={`#${c.href}`}>{c.label}</a> : <span className={i === crumbs.length - 1 ? "current" : ""}>{c.label}</span>}
                {i < crumbs.length - 1 ? <Icon name="chevron-r" size={12} className="sep" /> : null}
              </React.Fragment>
            ))}
          </div>
        ) : (
          <div className="topbar-title">{title}</div>
        )}
      </div>
      <div className="topbar-r">
        <div className="topbar-search" onClick={() => setOpenPop("search")}>
          <Icon name="search" size={14} />
          <input placeholder="Search clients, evidence, IC-ID…"
                 value={openPop === "search" ? q : ""}
                 onChange={e => { setQ(e.target.value); setOpenPop("search"); }}
                 onFocus={() => setOpenPop("search")} />
          <kbd>⌘K</kbd>
        </div>
        {right}
        <button className="icon-btn" onClick={() => setOpenPop(o => o === "notif" ? null : "notif")} aria-label="Notifications">
          <Icon name="bell" size={16} />
          {notifUnread > 0 ? <span className="dot" /> : null}
        </button>
        <button className="icon-btn" onClick={() => setOpenPop(o => o === "settings" ? null : "settings")} aria-label="Settings">
          <Icon name="settings" size={16} />
        </button>
      </div>

      <Portal>
        {openPop ? <div className="popover-mask" onClick={() => setOpenPop(null)} /> : null}

        {openPop === "search" ? <SearchPopover q={q} setQ={setQ} results={searchResults} onClose={() => setOpenPop(null)} /> : null}
        {openPop === "notif" ? <NotificationsPopover onClose={() => setOpenPop(null)} /> : null}
        {openPop === "settings" ? <SettingsPopover onClose={() => setOpenPop(null)} /> : null}
      </Portal>
    </header>
  );
}

function SearchPopover({ q, setQ, results, onClose }) {
  return (
    <div className="popover" style={{ top: 50, right: "auto", left: "50%", transform: "translateX(-50%)", width: 480, maxHeight: 520 }}>
      <div className="popover-head" style={{ padding: 0 }}>
        <div style={{ position: "relative", flex: 1, padding: "12px 14px" }}>
          <Icon name="search" size={14} style={{ position: "absolute", top: 16, left: 14, color: "var(--z-muted)" }} />
          <input autoFocus placeholder="Search entities, insights (IC-XXX), evidence (E-XXX)…"
                 value={q} onChange={e => setQ(e.target.value)}
                 style={{ width: "100%", padding: "6px 0 6px 26px", border: 0, outline: 0, fontSize: 14, background: "transparent" }} />
        </div>
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>
      <div className="popover-body">
        {!q.trim() ? (
          <div style={{ padding: "8px 14px", fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".1em" }}>Quick links</div>
        ) : null}
        {!q.trim() ? [
          { title: "Farm Credit East", sub: "Farm Credit · CT, NY", route: "/clients/fce-001/overview", icon: "users" },
          { title: "All clients", sub: "Browse directory", route: "/clients", icon: "grid" },
          { title: "Alerts", sub: "Thin-evidence alerts", route: "/alerts", icon: "bell" },
          { title: "Prospecting", sub: "Scorecard export", route: "/prospecting", icon: "envelope" },
        ].map((r, i) => (
          <button key={i} className="popover-row" style={{ width: "100%", border: 0, background: "none", textAlign: "left" }} onClick={() => { navigate(r.route); onClose(); }}>
            <div className="icon-wrap" style={{ background: "var(--z-ice)", color: "var(--z-mid)" }}><Icon name={r.icon} size={14} /></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>{r.title}</div>
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{r.sub}</div>
            </div>
          </button>
        )) : null}
        {results && results.length === 0 ? <div className="empty" style={{ padding: 20 }}><h3 style={{ fontSize: 13 }}>No results</h3><p style={{ fontSize: 11 }}>Try an entity name, IC-XXX, or E-XXX.</p></div> : null}
        {results && results.length > 0 ? results.map((r, i) => (
          <button key={i} className="popover-row" style={{ width: "100%", border: 0, background: "none", textAlign: "left" }} onClick={() => { navigate(r.route); onClose(); }}>
            <div className="icon-wrap" style={{ background: r.kind === "evidence" ? "var(--ph0-lt)" : r.kind === "insight" ? "var(--z-ice)" : "var(--z-lav)", color: r.kind === "evidence" ? "var(--z-dpur)" : "var(--z-mid)" }}>
              <Icon name={r.icon} size={14} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-1">{r.title}</div>
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{r.sub}</div>
            </div>
            <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>{r.kind}</span>
          </button>
        )) : null}
      </div>
      <div className="popover-foot" style={{ justifyContent: "space-between" }}>
        <span className="muted" style={{ fontSize: 11 }}>↑ ↓ to navigate · enter to open</span>
        <span className="muted" style={{ fontSize: 11 }}>esc to close</span>
      </div>
    </div>
  );
}

function NotificationsPopover({ onClose }) {
  const { pushToast } = useApp();
  const ICONS = { alert: "bell", completion: "check", system: "info" };
  const COLORS = {
    alert:      { bg: "rgba(254,151,50,.16)", c: "#7C3500" },
    completion: { bg: "var(--z-ice)",          c: "var(--z-mid)" },
    system:     { bg: "var(--z-lav)",          c: "var(--z-dpur)" },
  };
  return (
    <div className="popover">
      <div className="popover-head">
        <Icon name="bell" size={14} />
        <h4>Notifications</h4>
        <span className="spacer" />
        <button className="btn btn-tertiary btn-sm" onClick={() => { pushToast("All notifications marked as read", "success"); onClose(); }}>Mark all read</button>
      </div>
      <div className="popover-body">
        {DMA.NOTIFICATIONS.map(n => {
          const C = COLORS[n.kind];
          return (
            <button key={n.id} className="popover-row" style={{ width: "100%", border: 0, background: "none", textAlign: "left" }} onClick={() => { navigate(n.route); onClose(); }}>
              <div className="icon-wrap" style={{ background: C.bg, color: C.c }}><Icon name={ICONS[n.kind]} size={14} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-1">{n.title}</div>
                <div style={{ fontSize: 11, color: "var(--z-muted)" }} className="txt-fit-1">{n.body}</div>
              </div>
              <span style={{ fontSize: 10, color: "var(--z-muted)", flexShrink: 0 }}>{n.when}</span>
            </button>
          );
        })}
      </div>
      <div className="popover-foot">
        <a href="#/alerts" onClick={onClose} style={{ color: "var(--z-mid)", fontWeight: 600 }}>View all in alerts →</a>
      </div>
    </div>
  );
}

function SettingsPopover({ onClose }) {
  const { role, setRole, audience, setAudience, setAuthed } = useApp();
  const items = [
    { label: "Profile",          icon: "user",     route: "/admin",       sub: "Mishley Otiende" },
    { label: "Tweaks panel",     icon: "settings", action: () => { try { window.parent.postMessage({ type: "__activate_edit_mode" }, "*"); } catch(e){}; window.dispatchEvent(new MessageEvent("message", { data: { type: "__activate_edit_mode" } })); onClose(); }, sub: "Toggle in-page tweaks" },
    { label: "Sign out",          icon: "logout",   action: () => { setAuthed(false); navigate("/login"); onClose(); },     sub: "End session" },
  ];
  return (
    <div className="popover" style={{ width: 280 }}>
      <div className="popover-head">
        <div className="sb-avatar" style={{ width: 32, height: 32, fontSize: 11 }}>MO</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>Mishley Otiende</div>
          <div style={{ fontSize: 11, color: "var(--z-mid)" }}>mishley@zennify.com</div>
        </div>
      </div>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--z-sep)" }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>Acting as</div>
        <div className="toggle-row" style={{ width: "100%" }}>
          {[["AE","AE"],["ANALYST","Analyst"],["ADMIN","Admin"]].map(([k, l]) => (
            <button key={k} className={role === k ? "on" : ""} style={{ flex: 1 }} onClick={() => { setRole(k); onClose(); }}>{l}</button>
          ))}
        </div>
      </div>
      <div className="popover-body" style={{ padding: 0 }}>
        {items.map((it, i) => (
          <button key={i} className="popover-row" style={{ width: "100%", border: 0, background: "none", textAlign: "left" }} onClick={() => { if (it.route) navigate(it.route); if (it.action) it.action(); onClose(); }}>
            <div className="icon-wrap" style={{ background: "var(--z-lav)", color: "var(--z-dark2)" }}><Icon name={it.icon} size={14} /></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: "var(--z-dark)" }}>{it.label}</div>
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{it.sub}</div>
            </div>
            <Icon name="chevron-r" size={12} style={{ color: "var(--z-muted)" }} />
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Client bar (dark client-context strip + tabs) ──────────────── */
function ClientBar({ entity, run, tab }) {
  const { audience, setAudience, role } = useApp();
  const [runOpen, setRunOpen] = useState(false);
  const fresh = entity.assessment_date ? DMA.helpers.freshnessOf(entity.assessment_date) : null;
  const isSuperseded = run && run.status !== "ACTIVE" && !run.status.includes("IN_PROGRESS");
  const dsPill = run?.data_source === "DRIVE_PARSE" ? "pill-drive" : "pill-api";

  const TAB = (id, label, badge, icon) => (
    <button key={id} className={`client-tab ${tab === id ? "on" : ""}`} onClick={() => navigate(`/clients/${entity.id}/${id}`, run ? { run: run.id } : null)}>
      {icon ? <Icon name={icon} size={13} /> : null}
      <span>{label}</span>
      {badge ? <span className="count">{badge}</span> : null}
    </button>
  );

  return (
    <>
      <div className="client-bar">
        <button className="icon-btn" style={{ color: "rgba(255,255,255,.7)" }} onClick={() => navigate("/clients")} title="Back to directory">
          <Icon name="chevron-l" size={16} />
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div className="name">{entity.name}</div>
          {run ? <span className={`pill pill-active`}>{run.status.replace(/_/g, " ")}</span> : null}
          {run ? <span className={`pill ${dsPill}`}>{run.data_source === "DRIVE_PARSE" ? "DRIVE PARSE" : "PROJECT API"}</span> : null}
          {fresh ? <span className={`pill ${fresh.tone === "ok" ? "pill-fresh" : "pill-stale"}`}>● {fresh.label} · {fresh.months} mo</span> : null}
        </div>
        <div className="client-bar-r">
          <div style={{ position: "relative" }}>
            <button className="run-selector" onClick={() => setRunOpen(o => !o)}>
              <Icon name="calendar" size={12} />
              <span>{run ? `${fmtDate(run.date)} · ${run.overall ?? "-"}` : "Pick a run"}</span>
              <Icon name="chevron-d" size={12} />
            </button>
            {runOpen ? (
              <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 8, boxShadow: "var(--sh-lg)", padding: 6, zIndex: 92, minWidth: 320 }}>
                {entity.runs.map(r => (
                  <button key={r.id}
                    style={{ display: "flex", width: "100%", padding: "8px 10px", borderRadius: 5, textAlign: "left", gap: 10, alignItems: "center", background: run?.id === r.id ? "var(--z-ice)" : "transparent", color: "var(--z-dark)" }}
                    onClick={() => { setRunOpen(false); navigate(`/clients/${entity.id}/${tab}`, { run: r.id }); }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{fmtDate(r.date)} · <span style={{ color: "var(--z-teal)" }}>{r.overall ?? "-"}</span></div>
                      <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.id}</div>
                    </div>
                    <span className={`b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`}>{r.status}</span>
                    <span className={`b ${r.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{r.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className={`audience-toggle ${audience === "customer" ? "customer" : ""}`} title="Internal view shows full team-prep data. Customer view strips fields that should not be screen-shared.">
            <button className={audience === "internal" ? "on" : ""} onClick={() => setAudience("internal")}>
              <Icon name="lock" size={11} /> Internal
            </button>
            <button className={audience === "customer" ? "on" : ""} onClick={() => setAudience("customer")}>
              <Icon name="users" size={11} /> Customer
            </button>
          </div>
        </div>
      </div>

      <div className="client-tabs">
        {TAB("overview",  "Overview",  null, "home")}
        {TAB("insights",  "Insights",  null, "insight")}
        {TAB("heatmap",   "Heatmap",   null, "heatmap")}
        {TAB("platform",  "Platform",  null, "platform")}
        {audience !== "customer" ? TAB("context", "Context", null, "timeline") : null}
        {TAB("techstack", "Tech stack", null, "stack")}
        {(role === "ANALYST" || role === "ADMIN") && audience !== "customer" ? TAB("health", "Health", entity.open_alerts, "shield") : null}
        {TAB("runs",      "Runs", null, "refresh")}
      </div>

      {audience === "customer" ? (
        <div className="customer-banner">
          <Icon name="users" size={14} />
          <span><strong>Customer view</strong> - share-safe presentation mode · evidence rationale, ERS, alert counts, and the Context tab are hidden</span>
          <span className="spacer" />
          <button className="btn btn-tertiary btn-sm" style={{ color: "#7C3500" }} onClick={() => setAudience("internal")}>Switch back to Internal →</button>
        </div>
      ) : null}

      {isSuperseded ? (
        <div className="superseded-banner">
          <Icon name="info" size={14} />
          <span>Viewing <strong>{fmtDate(run.date)}</strong> run · <span className="b b-muted">SUPERSEDED</span>. The ACTIVE run is from {fmtDate(entity.runs[0].date)}.</span>
          <span className="spacer" />
          <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/${tab}`)}>Return to active →</button>
        </div>
      ) : null}
    </>
  );
}

/* ── Page layout shells ──────────────────────────────────────────── */
function PageShell({ title, crumbs, children, narrow, right }) {
  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <TopBar title={title} crumbs={crumbs} right={right} />
        <main className={`page ${narrow ? "page-narrow" : ""}`}>{children}</main>
      </div>
    </div>
  );
}

function ClientShell({ entity, run, tab, children }) {
  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <TopBar
          crumbs={[
            { label: "Clients", href: "/clients" },
            { label: entity.name },
            { label: tab[0].toUpperCase() + tab.slice(1).replace("stack"," stack") },
          ]}
        />
        <ClientBar entity={entity} run={run} tab={tab} />
        <main className="page">{children}</main>
      </div>
    </div>
  );
}

Object.assign(window, { Sidebar, TopBar, ClientBar, PageShell, ClientShell });
