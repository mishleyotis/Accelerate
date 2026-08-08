/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Alerts, Prospecting, Admin pages
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /alerts (Analyst alert dashboard) ───────────────────────────── */
function AlertsPage() {
  const { role, pushToast } = useApp();
  const [statusFilter, setStatusFilter] = useState("OPEN");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [tab, setTab] = useState("alerts");

  const all = DMA.ALERTS;
  const filtered = all.filter(a => {
    if (statusFilter !== "ALL" && a.status !== statusFilter) return false;
    if (severityFilter !== "ALL" && a.severity !== severityFilter) return false;
    return true;
  });

  if (role !== "ANALYST" && role !== "ADMIN") {
    return <PageShell title="Alerts" crumbs={[{ label: "Alerts" }]}>
      <div className="empty"><div className="icon"><Icon name="lock" size={22} /></div><h3>Analyst access required</h3><p>This page requires Analyst or Admin permissions.</p></div>
    </PageShell>;
  }

  return (
    <PageShell title="Alerts" crumbs={[{ label: "Alerts" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Global alert dashboard</div>
          <h1>Thin-evidence alerts</h1>
          <div className="sub">{all.filter(a => a.status === "OPEN").length} OPEN across {new Set(all.map(a => a.entity_id)).size} entities</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${filtered.length} alerts as CSV…`, "success")}><Icon name="download" size={13} /> Export CSV</button>
          <button className="btn btn-secondary" onClick={() => pushToast("Feedback file regenerated - routed to DMA bot", "success")}><Icon name="refresh" size={13} /> Refresh feedback file</button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "alerts" ? "on" : ""} onClick={() => setTab("alerts")}>Alerts</button>
          <button className={tab === "patterns" ? "on" : ""} onClick={() => setTab("patterns")}>Patterns</button>
          <button className={tab === "waived" ? "on" : ""} onClick={() => setTab("waived")}>Waived</button>
        </div>
        <span className="spacer" />
        {tab === "alerts" ? <>
          <select className="inp" style={{ maxWidth: 180 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="ALL">All statuses</option>
            <option>OPEN</option><option>IN_REVIEW</option><option>RESOLVED</option>
          </select>
          <select className="inp" style={{ maxWidth: 180 }} value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}>
            <option value="ALL">All severities</option>
            <option>HIGH</option><option>MEDIUM</option>
          </select>
        </> : null}
      </div>

      {tab === "alerts" ? (
        <div className="card flush">
          <table className="tbl">
            <thead><tr><th>Severity</th><th>Entity</th><th>Subcap</th><th>Evidence</th><th>Action</th><th style={{ textAlign: "right" }}>Manage</th></tr></thead>
            <tbody>
              {filtered.map(a => {
                const e = DMA.getEntity(a.entity_id);
                return (
                  <tr key={a.id}>
                    <td><span className={`b ${a.severity === "HIGH" ? "b-below" : "b-org"}`}>{a.severity}</span></td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 12.5 }}>{e?.name}</div>
                      <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{DMA.SUBVERTICAL_LABEL[e?.subvertical]}</div>
                    </td>
                    <td>
                      <div style={{ fontSize: 12, fontWeight: 500 }}>{a.subcap_name}</div>
                      <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.subcap_id}</div>
                    </td>
                    <td><span className="f-mono" style={{ fontSize: 11 }}>{a.evidence_count} / 3</span></td>
                    <td><span className="b b-purple">{a.recommended_action}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${a.entity_id}/heatmap`, { subcap: a.subcap_id })}>Heatmap</button>
                      <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} moved to IN_REVIEW`, "success")}>Review</button>
                      <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} waived — add rationale before close`, "warn")}>Waive</button>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 ? <tr><td colSpan={6} className="tbl-empty"><div style={{ color: "var(--z-mid)", fontSize: 13, fontWeight: 500 }}>✓ No open alerts matching</div></td></tr> : null}
            </tbody>
          </table>
        </div>
      ) : tab === "patterns" ? (
        <div className="card flush">
          <div className="card-head"><h3>Cross-entity pattern finder</h3><span className="b b-muted">≥60% subvertical concentration</span></div>
          <table className="tbl">
            <thead><tr><th>Pattern</th><th>Subvertical</th><th>Category</th><th>Cohort</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
            <tbody>
              {DMA.PATTERNS.map((p, i) => (
                <tr key={i}>
                  <td><strong>{p.title}</strong></td>
                  <td><span className="b b-purple">{DMA.SUBVERTICAL_LABEL[p.subvertical]}</span></td>
                  <td><span className="chip">{p.category}</span></td>
                  <td>{p.count} / {p.total} entities</td>
                  <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Drafting outreach campaign · ${p.title}`, "success")}>Build campaign</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card flush">
          <div className="empty"><div className="icon"><Icon name="check" size={22} /></div><h3>No waived alerts</h3><p>Waived alerts will appear here with their rationale.</p></div>
        </div>
      )}
    </PageShell>
  );
}

/* ── /prospecting (AE self-service) ──────────────────────────────── */
function ProspectingPage() {
  const { pushToast } = useApp();
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [downloadReady, setDownloadReady] = useState(false);
  const matches = q ? DMA.ENTITIES.filter(e => e.name.toLowerCase().includes(q.toLowerCase()) && !e.in_progress).slice(0, 5) : [];

  return (
    <PageShell title="Prospecting" crumbs={[{ label: "Prospecting" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Customer-safe export</div>
          <h1>Prospecting</h1>
          <div className="sub">Search → one-page scorecard → export PDF or HTML</div>
        </div>
        <span className="b b-org" style={{ alignSelf: "center" }}><Icon name="lock" size={10} /> CUSTOMER-SAFE MODE</span>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ position: "relative", maxWidth: 600 }}>
          <Icon name="search" size={14} style={{ position: "absolute", top: 10, left: 10, color: "var(--z-muted)" }} />
          <input className="inp" style={{ paddingLeft: 32, fontSize: 14, padding: "11px 14px 11px 32px" }} placeholder="Search by institution name…" value={q} onChange={e => setQ(e.target.value)} />
          {matches.length > 0 ? (
            <div style={{ position: "absolute", top: 46, left: 0, right: 0, background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 8, boxShadow: "var(--sh-lg)", zIndex: 5 }}>
              {matches.map(e => (
                <button key={e.id} style={{ display: "flex", width: "100%", padding: "10px 14px", borderBottom: "1px solid var(--z-sep)", textAlign: "left", gap: 12, alignItems: "center" }} onClick={() => { setPicked(e); setQ(""); setDownloadReady(false); }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{e.name}</div>
                    <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{DMA.SUBVERTICAL_LABEL[e.subvertical]} · {e.hq}</div>
                  </div>
                  <MaturityChip score={e.overall} />
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: "var(--z-muted)" }}>
          Recent searches: Synovus · Fulton Bank · SL Green
        </div>
      </div>

      {picked ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ marginBottom: 14 }}>
            <Icon name="evidence" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Scorecard preview · always Customer View</div>
            <span className="spacer" />
            <button className="btn btn-tertiary" disabled={exporting} onClick={() => { setExporting(true); setTimeout(() => { setExporting(false); setDownloadReady(true); }, 1400); }}>
              {exporting ? <span className="row"><span className="skel" style={{ width: 12, height: 12, borderRadius: 6 }} /> Generating…</span> : <><Icon name="download" size={13} /> Export PDF</>}
            </button>
            <button className="btn btn-secondary" onClick={() => pushToast(`Downloaded standalone HTML scorecard · ${picked.name}`, "success")}><Icon name="download" size={13} /> Download HTML</button>
          </div>
          {downloadReady ? (
            <div className="co co-teal" style={{ marginBottom: 14 }}>
              <Icon name="check" size={14} />
              <div><div className="co-title">Ready</div><div className="co-body">Your PDF is ready - link valid for 24 hours.</div></div>
            </div>
          ) : null}
          <ScorecardPreview e={picked} />
        </div>
      ) : (
        <div className="empty">
          <div className="icon"><Icon name="envelope" size={22} /></div>
          <h3>Search to begin</h3>
          <p>Search the institution name to load a one-page scorecard. The export is always Customer-safe - internal fields are stripped.</p>
        </div>
      )}
    </PageShell>
  );
}

function ScorecardPreview({ e }) {
  return (
    <div style={{ background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 12, padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".1em" }}>Zennify · DMA Scorecard</div>
          <div style={{ fontSize: 24, fontWeight: 600, marginTop: 4 }}>{e.name}</div>
          <div style={{ fontSize: 12, color: "var(--z-muted)" }}>{DMA.SUBVERTICAL_LABEL[e.subvertical]} · {e.hq} · {fmtAssets(e.assets)} · Assessment {fmtDate(e.assessment_date)}</div>
        </div>
        <ScoreRing score={e.overall} />
      </div>
      <div className="g4">
        {DMA.PILLARS.map(p => (
          <div key={p.id} className="card-tile">
            <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{p.id}</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{p.short}</div>
            <div className="row" style={{ marginTop: 6 }}>
              <MaturityChip score={e.pillar_scores[p.id]} />
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{DMA.helpers.maturityLabel(e.pillar_scores[p.id])}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="sep" />
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Top 3 platform opportunities</div>
      <div className="g3">
        {Object.entries(e.oss).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([pid, score]) => (
          <div key={pid} className="card-tile">
            <strong>{DMA.getPlatform(pid).name}</strong>
            <div style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>{score}<span style={{ fontSize: 11, color: "var(--z-muted)" }}>/100</span></div>
            <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{DMA.getPlatform(pid).features.split(" · ").slice(0, 2).join(" · ")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Live import streaming panel (SSE-style progress) ────────────── */
const IMPORT_STAGES = [
  { key: "crawl",    label: "Drive crawl",      icon: "drive"    },
  { key: "classify", label: "Classify",         icon: "evidence" },
  { key: "dedupe",   label: "Deduplicate",      icon: "stack"    },
  { key: "infer",    label: "Entity inference", icon: "users"    },
  { key: "ingest",   label: "Ingest & index",   icon: "play"     },
];
const IMPORT_SCRIPT = [
  { stage: 0, log: "Connecting to Drive folder 1uvt3kh…2O0P", level: "info" },
  { stage: 0, log: "Listing candidate files…", c: { scanned: 64 } },
  { stage: 0, log: "Found 187 candidate files in 12 subfolders", c: { scanned: 187 } },
  { stage: 1, log: "Applying classification rules R01–R06", level: "info" },
  { stage: 1, log: "R03 excluded TEST_CASE_template.xlsx", level: "warn", c: { excluded: 1 } },
  { stage: 1, log: "R05 excluded 4 sample / demo workbooks", level: "warn", c: { excluded: 5 } },
  { stage: 1, log: "Classified 182 DMA reports · 5 excluded", c: { kept: 182 } },
  { stage: 2, log: "Hashing content for near-duplicate detection", level: "info" },
  { stage: 2, log: "Collapsed 9 duplicate revisions into latest", c: { kept: 173 } },
  { stage: 3, log: "Entity inference · 4-signal cascade", level: "info" },
  { stage: 3, log: "Matched “Farm Credit East” (filename + header)", c: { entities: 1 } },
  { stage: 3, log: "Matched “Synovus Bank” (domain + content)", c: { entities: 2 } },
  { stage: 3, log: "Matched “SL Green Realty” (firmographic)", c: { entities: 3 } },
  { stage: 3, log: "3 low-confidence files queued for review", level: "warn" },
  { stage: 4, log: "Writing assessment rows to store", level: "info" },
  { stage: 4, log: "Indexing evidence + building intelligence cache", level: "info" },
  { stage: 4, log: "Import complete · 6 entities · 173 files", level: "ok", done: true },
];

function LiveImportStream() {
  const { pushToast } = useApp();
  const [idx, setIdx] = useState(0);
  const [logs, setLogs] = useState([]);
  const [counts, setCounts] = useState({ scanned: 0, kept: 0, excluded: 0, entities: 0 });
  const [running, setRunning] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const logRef = useRef(null);

  // advance through scripted events
  useEffect(() => {
    if (!running) return;
    if (idx >= IMPORT_SCRIPT.length) { setRunning(false); return; }
    const step = IMPORT_SCRIPT[idx];
    const t = setTimeout(() => {
      const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
      const ss = String(elapsed % 60).padStart(2, "0");
      setLogs(l => [...l, { ts: `${mm}:${ss}`, stage: step.stage, text: step.log, level: step.level || "info" }]);
      if (step.c) setCounts(c => ({ ...c, ...step.c }));
      if (step.done) { setRunning(false); pushToast("Drive crawl complete · 6 entities imported", "success"); }
      setIdx(i => i + 1);
    }, idx === 0 ? 450 : 720);
    return () => clearTimeout(t);
  }, [idx, running]);

  // elapsed clock
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  // autoscroll log to bottom
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);

  const reset = () => { setIdx(0); setLogs([]); setCounts({ scanned: 0, kept: 0, excluded: 0, entities: 0 }); setElapsed(0); setRunning(true); };
  const cancel = () => { setRunning(false); pushToast("Crawl cancelled", "warn"); };

  const activeStage = running ? Math.min(IMPORT_SCRIPT[Math.min(idx, IMPORT_SCRIPT.length - 1)]?.stage ?? 0, IMPORT_STAGES.length - 1) : IMPORT_STAGES.length - 1;
  const pct = running ? Math.min(99, Math.round((idx / IMPORT_SCRIPT.length) * 100)) : 100;
  const done = !running && idx >= IMPORT_SCRIPT.length;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const levelColor = { info: "var(--z-muted)", warn: "var(--z-org)", ok: "var(--z-teal)" };

  return (
    <div className="card flush" style={{ marginBottom: 16, overflow: "hidden" }}>
      <div className="card-head">
        <div className="row">
          <Icon name="play" size={14} style={{ color: done ? "var(--z-teal)" : "var(--z-mid)" }} />
          <h3>Active job · IJ-10 · Drive crawl</h3>
          {done ? <span className="b b-above">COMPLETED</span> : <span className="b b-teal" style={{ display: "inline-flex", gap: 4 }}><span className="live-dot" /> SSE LIVE</span>}
        </div>
        <span style={{ fontSize: 11, color: "var(--z-muted)", fontVariantNumeric: "tabular-nums" }}>Elapsed {mm}:{ss}</span>
      </div>
      <div style={{ padding: 16 }}>
        {/* Stage pipeline */}
        <div className="import-stages">
          {IMPORT_STAGES.map((s, i) => {
            const state = i < activeStage || done ? "done" : i === activeStage && running ? "active" : i === activeStage ? "done" : "todo";
            return (
              <div key={s.key} className={`import-stage ${state}`}>
                <div className="import-stage-dot"><Icon name={state === "done" ? "check" : s.icon} size={12} /></div>
                <div className="import-stage-label">{s.label}</div>
                {i < IMPORT_STAGES.length - 1 ? <div className="import-stage-bar"><div className="import-stage-bar-fill" style={{ width: (i < activeStage || done) ? "100%" : "0%" }} /></div> : null}
              </div>
            );
          })}
        </div>

        {/* Overall progress */}
        <div className="row" style={{ marginTop: 16, marginBottom: 6 }}>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)" }}>{done ? "Finished" : IMPORT_STAGES[activeStage].label}</span>
          <span className="spacer" />
          <span style={{ fontSize: 11.5, color: "var(--z-muted)", fontVariantNumeric: "tabular-nums" }}>{pct}%</span>
        </div>
        <div className="prog"><div className="prog-fill" style={{ width: `${pct}%`, background: done ? "var(--z-teal)" : "linear-gradient(90deg, var(--m-cmp), var(--m-bld))" }} /></div>

        {/* Live counters */}
        <div className="g4" style={{ gap: 10, marginTop: 14 }}>
          {[
            { label: "Scanned",  value: counts.scanned,  color: "var(--z-mid)"  },
            { label: "Kept",     value: counts.kept,     color: "var(--z-teal)" },
            { label: "Excluded", value: counts.excluded, color: "var(--z-org)"  },
            { label: "Entities", value: counts.entities, color: "var(--z-dpur)" },
          ].map(k => (
            <div key={k.label} className="card-tile" style={{ padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>{k.label}</div>
              <div style={{ fontSize: 22, fontWeight: 200, color: k.color, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{k.value}</div>
            </div>
          ))}
        </div>

        {/* Streaming log */}
        <div ref={logRef} className="import-log" aria-live="polite">
          {logs.length === 0 ? <div className="import-log-line" style={{ color: "rgba(255,255,255,.4)" }}>Awaiting first event…</div> : null}
          {logs.map((l, i) => (
            <div key={i} className="import-log-line">
              <span style={{ color: "rgba(255,255,255,.35)" }}>{l.ts}</span>
              <span style={{ color: "rgba(255,255,255,.3)" }}>[{IMPORT_STAGES[l.stage].key}]</span>
              <span style={{ color: l.level === "warn" ? "#FEC07A" : l.level === "ok" ? "#7FE3D6" : "rgba(255,255,255,.82)" }}>{l.text}</span>
            </div>
          ))}
          {running ? <div className="import-log-line"><span className="import-cursor" /></div> : null}
        </div>

        {/* Controls */}
        <div className="row" style={{ marginTop: 12, gap: 8 }}>
          {done ? (
            <>
              <button className="btn btn-primary btn-sm" onClick={reset}><Icon name="refresh" size={12} /> Run new crawl</button>
              <button className="btn btn-tertiary btn-sm" onClick={() => navigate("/admin/import/audit")}>View audit queue <Icon name="arrow-r" size={11} /></button>
            </>
          ) : (
            <button className="btn btn-tertiary btn-sm" onClick={cancel}>Cancel job</button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Editable users & roles (Admin) ──────────────────────────────── */
function AdminUsersCard() {
  const { pushToast } = useApp();
  // Production divergence: LIVE mode renders the REAL role grants the
  // server resolves sign-ins against (DMA_LIVE.role_grants, admin
  // sessions only) — read-only until the users table lands; grants
  // change via deployment env, never via this card. The mutable mock
  // roster renders solely in local preview.
  const LIVE = !!window.DMA_LIVE;
  const liveGrantRows = (() => {
    if (!LIVE) return null;
    const g = window.DMA_LIVE.role_grants;
    if (!g) return [];
    const nameOf = (e) => {
      const parts = e.split("@")[0].split(/[._-]+/).filter(Boolean);
      if (parts.length === 1 && parts[0].length <= 3) return parts[0].toUpperCase();
      return parts.map(w => w[0].toUpperCase() + w.slice(1)).join(" ") || e;
    };
    const me = sessionUser().email;
    const rows = [];
    g.admins.forEach((e, i) => rows.push({ id: `adm-${i}`, name: nameOf(e), email: e, role: "ADMIN", active: true, last: e === me ? "now (this session)" : "—" }));
    g.analysts.filter(e => !g.admins.includes(e)).forEach((e, i) =>
      rows.push({ id: `ana-${i}`, name: nameOf(e), email: e, role: "ANALYST", active: true, last: e === me ? "now (this session)" : "—" }));
    return rows;
  })();
  const [users, setUsers] = useState(LIVE ? (liveGrantRows || []) : [
    { id: 1, name: "Mishley Andrade", email: "mishley@zennify.com", role: "ANALYST", active: true,  last: "2 min ago"  },
    { id: 2, name: "Dev Patel",       email: "dev@zennify.com",     role: "ADMIN",   active: true,  last: "1 hr ago"   },
    { id: 3, name: "Sara Lin",        email: "sara@zennify.com",    role: "AE",      active: true,  last: "Yesterday"  },
    { id: 4, name: "Tom Reyes",       email: "tom@zennify.com",     role: "AE",      active: false, last: "3 wk ago"   },
  ]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("AE");

  const setRole = (id, role) => {
    if (LIVE) { pushToast("Grants are set per deployment (ADMIN_EMAILS / ANALYST_EMAILS) until the users table lands", "warn"); return; }
    setUsers(us => us.map(u => u.id === id ? { ...u, role } : u)); pushToast(`Role updated to ${role}`, "success");
  };
  const toggleActive = (id) => {
    if (LIVE) { pushToast("Grants are set per deployment (ADMIN_EMAILS / ANALYST_EMAILS) until the users table lands", "warn"); return; }
    setUsers(us => us.map(u => u.id === id ? (pushToast(`${u.name} ${u.active ? "deactivated" : "reactivated"}`, u.active ? "warn" : "success"), { ...u, active: !u.active }) : u));
  };
  const invite = () => {
    if (LIVE) { pushToast("Invites arrive with the users table; today every @zennify.com Google account signs in as AE automatically", "warn"); return; }
    const email = inviteEmail.trim();
    if (!email) { pushToast("Enter an email to invite", "warn"); return; }
    if (!/@zennify\.com$/i.test(email)) { pushToast("Only @zennify.com addresses can be invited", "warn"); return; }
    const name = email.split("@")[0].split(".").map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
    setUsers(us => [...us, { id: Date.now(), name, email, role: inviteRole, active: true, last: "Invited" }]);
    pushToast(`Invitation sent to ${email}`, "success");
    setInviteEmail("");
  };

  return (
    <div className="card flush" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <div className="row"><Icon name="users" size={14} /><h3>Users &amp; roles</h3></div>
        <span className="b b-muted">{users.filter(u => u.active).length} active</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>User</th><th>Role</th><th>Last active</th><th>Status</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ opacity: u.active ? 1 : 0.55 }}>
                <td data-label="User">
                  <div style={{ fontWeight: 600, color: "var(--z-dark)" }}>{u.name}</div>
                  <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{u.email}</div>
                </td>
                <td data-label="Role">
                  <select className="inp inp-sm" value={u.role} onChange={e => setRole(u.id, e.target.value)} style={{ maxWidth: 130 }} aria-label={`Role for ${u.name}`}>
                    <option value="AE">AE</option>
                    <option value="ANALYST">Analyst</option>
                    <option value="ADMIN">Admin</option>
                  </select>
                </td>
                <td data-label="Last active" style={{ fontSize: 11.5, color: "var(--z-muted)" }}>{u.last}</td>
                <td data-label="Status"><span className={`b ${u.active ? "b-above" : "b-muted"}`}>{u.active ? "Active" : "Deactivated"}</span></td>
                <td data-label="Action" style={{ textAlign: "right" }}>
                  <button className="btn btn-tertiary btn-sm" onClick={() => toggleActive(u.id)}>{u.active ? "Deactivate" : "Reactivate"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {LIVE ? (
        <div className="card-body" style={{ borderTop: "1px solid var(--z-sep)", fontSize: 11.5, color: "var(--z-muted)", display: "flex", gap: 8, alignItems: "flex-start" }}>
          <Icon name="info" size={13} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Every other @zennify.com Google account signs in as <strong>AE</strong> automatically. ADMIN and ANALYST are deploy-time grants (ADMIN_EMAILS / ANALYST_EMAILS); per-user management arrives with the users table.</span>
        </div>
      ) : (
        <div className="card-body" style={{ borderTop: "1px solid var(--z-sep)", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input className="inp inp-sm" style={{ flex: 1, minWidth: 200 }} placeholder="name@zennify.com" value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} onKeyDown={e => { if (e.key === "Enter") invite(); }} />
          <select className="inp inp-sm" value={inviteRole} onChange={e => setInviteRole(e.target.value)} style={{ maxWidth: 130 }} aria-label="Invite role">
            <option value="AE">AE</option>
            <option value="ANALYST">Analyst</option>
            <option value="ADMIN">Admin</option>
          </select>
          <button className="btn btn-primary btn-sm" onClick={invite}><Icon name="plus" size={12} /> Invite user</button>
        </div>
      )}
    </div>
  );
}

/* ── /admin home + import + audit ────────────────────────────────── */
function AdminPage() {
  const { role, pushToast } = useApp();
  const LIVE = !!window.DMA_LIVE;
  const [scanning, setScanning] = useState(false);
  const [folder, setFolder] = useState(
    LIVE ? (window.DMA_LIVE.intake_folder_id || "not configured") : "1uvt3kh…2O0P");
  const [schedule, setSchedule] = useState(LIVE ? "30m" : "6h");
  const [editingFolder, setEditingFolder] = useState(false);
  const [budgetCap, setBudgetCap] = useState(400);
  const [autoDowngrade, setAutoDowngrade] = useState(true);
  if (role !== "ADMIN") return <PageShell title="Admin"><div className="empty"><div className="icon"><Icon name="lock" size={22} /></div><h3>Admin access required</h3><p>Switch to the Admin role to manage users, ingest, and system settings.</p></div></PageShell>;
  // Production divergence: the scan button fires a real execution of the
  // package-scan worker Job (same Job Cloud Scheduler fires every 30
  // minutes). No fake progress, no fake counts — the import audit page
  // shows what the execution actually did.
  const runScan = (kind) => {
    if (LIVE) {
      setScanning(true);
      fetch("/api/admin/scan", { method: "POST" })
        .then(r => r.json().then(b => ({ ok: r.ok, b })))
        .then(({ ok, b }) => {
          setScanning(false);
          if (ok) pushToast("Package scan started - new client folders land as the Job completes", "success");
          else pushToast(b.error || "Scan trigger failed", "warn");
        })
        .catch(() => { setScanning(false); pushToast("Scan trigger failed", "warn"); });
      return;
    }
    setScanning(true); pushToast(kind === "full" ? "Full Drive rescan started" : "Delta scan started", "success"); setTimeout(() => { setScanning(false); pushToast(`Scan complete: ${kind === "full" ? "187 files" : "3 new candidates"}`, "success"); }, 2000);
  };

  return (
    <PageShell title="Admin" crumbs={[{ label: "Admin" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Settings &amp; operations</div>
          <h1>Admin</h1>
          <div className="sub">User management · ingest pipeline · system settings</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" disabled={scanning} onClick={() => runScan("delta")}>{scanning ? <><span className="spinner" /> Scanning…</> : <><Icon name="refresh" size={13} /> Delta scan</>}</button>
          <button className="btn btn-primary" onClick={() => navigate("/admin/import")}><Icon name="play" size={13} /> Import &amp; jobs</button>
        </div>
      </div>

      {/* PENDING_REVIEW entities */}
      <div className="card flush" style={{ marginBottom: 16 }}>
        <div className="card-head"><div className="row"><Icon name="users" size={14} /><h3>Pending review · Phase 0 entity inferences</h3></div><span className="b b-org">{DMA.PENDING_REVIEW.length} entities</span></div>
        <div className="card-body">
          {DMA.PENDING_REVIEW.map(e => (
            <div key={e.id} className="card-tile" style={{ marginBottom: 8, padding: 14 }}>
              <div className="row" style={{ marginBottom: 6, flexWrap: "wrap", gap: 6 }}>
                <strong>{e.inferred_name}</strong>
                <span className="b b-purple">{DMA.SUBVERTICAL_LABEL[e.inferred_subvertical] || e.inferred_subvertical}</span>
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Confidence <strong style={{ color: "var(--z-mid)" }}>{e.confidence.toFixed(2)}</strong></span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--z-body)" }}>
                Inferred via <strong>{e.signal}</strong> · source: <span className="f-mono">{e.drive_file}</span>
              </div>
              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn btn-primary btn-sm" onClick={() => pushToast(`Confirmed ${e.inferred_name}`, "success")}>Confirm</button>
                <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Rejected ${e.inferred_name}`, "warn")}>Reject</button>
                <button className="btn btn-tertiary btn-sm" onClick={() => navigate("/admin/import/audit")}>View source</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Editable users & roles */}
      <AdminUsersCard />

      <div className="g2">
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="drive" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Drive crawl</div>
            <span className="spacer" />
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{LIVE ? "History → Import audit" : "Last crawl 2 hr ago"}</span>
          </div>

          {/* Target folder: in production this is the deployed intake
              tree (worker env), shown read-only — editing it here would
              only pretend to change the Job. */}
          <label className="field-label">Target folder ID</label>
          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            {editingFolder && !LIVE ? (
              <input className="inp inp-sm" style={{ flex: 1 }} value={folder} autoFocus
                onChange={e => setFolder(e.target.value)}
                onBlur={() => { setEditingFolder(false); pushToast("Target folder updated", "success"); }}
                onKeyDown={e => { if (e.key === "Enter") { setEditingFolder(false); pushToast("Target folder updated", "success"); } }} />
            ) : (
              <>
                <span className="f-mono" style={{ flex: 1, fontSize: 12, padding: "7px 10px", background: "var(--z-bg)", borderRadius: 6, border: "1px solid var(--z-sep)" }}>{folder}</span>
                {LIVE ? (
                  <button className="btn btn-tertiary btn-sm" onClick={() => pushToast("The intake folder is set on the worker Job (INTAKE_FOLDER_ID) at deploy time", "warn")}><Icon name="lock" size={12} /> Deploy-set</button>
                ) : (
                  <button className="btn btn-tertiary btn-sm" onClick={() => setEditingFolder(true)}><Icon name="edit" size={12} /> Edit</button>
                )}
              </>
            )}
          </div>

          {/* Schedule: production runs on the Cloud Scheduler trigger. */}
          <label className="field-label">Crawl schedule</label>
          {LIVE ? (
            <div className="f-mono" style={{ fontSize: 12, padding: "7px 10px", background: "var(--z-bg)", borderRadius: 6, border: "1px solid var(--z-sep)", marginBottom: 14 }}>
              Every 30 minutes · Cloud Scheduler (dmai-package-scan)
            </div>
          ) : (
            <select className="inp inp-sm" value={schedule} onChange={e => { setSchedule(e.target.value); pushToast("Crawl schedule updated", "success"); }} style={{ marginBottom: 14 }}>
              <option value="1h">Every hour</option>
              <option value="6h">Every 6 hours</option>
              <option value="24h">Daily</option>
              <option value="manual">Manual only</option>
            </select>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary btn-sm" disabled={scanning} onClick={() => runScan("delta")}>{scanning ? <><span className="spinner" /> Scanning…</> : <><Icon name="refresh" size={12} /> Delta scan</>}</button>
            <button className="btn btn-tertiary btn-sm" disabled={scanning} onClick={() => runScan("full")}>Full re-scan…</button>
            <button className="btn btn-tertiary btn-sm" onClick={() => navigate("/admin/import/audit")}>Import audit →</button>
            <button className="btn btn-tertiary btn-sm" onClick={() => navigate("/admin/import")}>Job history →</button>
          </div>
        </div>

        <div className="card">
          {LIVE ? (
            /* Production divergence: there is no model budget to show —
               the serving path performs no inference (charter invariant).
               Synthesis runs in Claude Cowork against the connector. */
            <React.Fragment>
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="insight" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Synthesis pipeline</div>
              </div>
              <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.6 }}>
                This application performs <strong>no inference at request time</strong>.
                Page content is produced ahead of time by the synthesis agent in
                Claude Cowork through the DMA connector, validated against
                structured verdicts, and promoted atomically — all six pages or
                none. What renders here is exactly what was promoted.
              </div>
              <div style={{ marginTop: 12, fontSize: 11.5, color: "var(--z-muted)" }}>
                Ingestion → scan Job (every 30 min) · Synthesis → Cowork session ·
                Serving → promoted tables only
              </div>
            </React.Fragment>
          ) : (
            <React.Fragment>
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="money" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Vertex AI budget</div>
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>$184 / ${budgetCap} · {Math.round(184 / budgetCap * 100)}%</span>
              </div>
              <div className="prog"><div className="prog-fill" style={{ width: `${Math.min(100, 184 / budgetCap * 100)}%`, background: 184 / budgetCap > 0.8 ? "var(--z-org)" : "var(--z-teal)" }} /></div>

              {/* Mini per-day bars */}
              <div style={{ display: "flex", gap: 3, alignItems: "flex-end", height: 36, marginTop: 14 }}>
                {[12, 18, 9, 22, 14, 28, 19, 24, 11, 16, 21, 17].map((v, i) => (
                  <div key={i} title={`Day ${i + 1} · $${v}`} style={{ flex: 1, height: `${v / 28 * 100}%`, background: i % 3 === 2 ? "var(--z-dpur)" : "var(--z-mid)", borderRadius: 2, opacity: 0.85 }} />
                ))}
              </div>
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>Flash 76% · Pro 24% · last 12 days</div>

              {/* Editable budget cap */}
              <label className="field-label" style={{ marginTop: 14 }}>Monthly budget cap (USD)</label>
              <input className="inp inp-sm" type="number" min="50" step="50" value={budgetCap} onChange={e => setBudgetCap(Number(e.target.value) || 0)} onBlur={() => pushToast(`Budget cap set to $${budgetCap}`, "success")} style={{ marginBottom: 12 }} />

              <button className="toggle-pill" onClick={() => { setAutoDowngrade(v => !v); pushToast(`Auto-downgrade to Flash ${!autoDowngrade ? "enabled" : "disabled"}`, "success"); }} aria-pressed={autoDowngrade}>
                <span className={`toggle-track ${autoDowngrade ? "on" : ""}`}><span className="toggle-knob" /></span>
                <span style={{ fontSize: 12, color: "var(--z-dark)" }}>Auto-downgrade to Flash at 90% spend</span>
              </button>
            </React.Fragment>
          )}
        </div>
      </div>
    </PageShell>
  );
}

function ImportPage() {
  const { role, pushToast } = useApp();
  const LIVE = !!window.DMA_LIVE;
  const [scanning, setScanning] = useState(false);
  const [tab, setTab] = useState("jobs");
  if (role !== "ADMIN") return <PageShell title="Import"><div className="empty"><div className="icon"><Icon name="lock" size={22} /></div><h3>Admin access required</h3></div></PageShell>;

  // Production divergence: LIVE renders the REAL scan ledger
  // (import_scans via the API) — every row is an actual execution of the
  // package-scan Job. The mock history renders solely in local preview.
  const jobs = LIVE ? (window.DMA_LIVE.import_scans || []).map(s => {
    const ms = s.started_at && s.finished_at ? (new Date(s.finished_at) - new Date(s.started_at)) : null;
    return {
      id: `SCAN-${s.id}`,
      kind: `Package scan · ${s.files_new ?? 0} new / ${s.files_changed ?? 0} changed`,
      status: (s.status || "").toUpperCase() === "SUCCEEDED" ? "COMPLETED" : (s.status || "?").toUpperCase(),
      started: s.started_at ? new Date(s.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—",
      files: s.files_seen ?? "—",
      entities: s.runs_created ?? 0,
      took: ms == null ? "—" : (ms < 1000 ? "<1 s" : `${Math.round(ms / 1000)} s`),
    };
  }) : [
    { id: "IJ-09", kind: "Drive crawl",   status: "COMPLETED",  started: "Jun 4 09:12", files: 187, entities: 6, took: "2 m 14 s" },
    { id: "IJ-08", kind: "Phase 1 ingest", status: "COMPLETED",  started: "Jun 3 17:48", files: 1,   entities: 1, took: "18 s" },
    { id: "IJ-07", kind: "Drive crawl",   status: "COMPLETED",  started: "Jun 3 03:00", files: 182, entities: 0, took: "1 m 56 s" },
    { id: "IJ-06", kind: "Catalog import", status: "FAILED",    started: "Jun 2 14:22", files: 4,   entities: 0, took: "6 s",  err: "Invalid sheet header on P2 tab" },
    { id: "IJ-05", kind: "Drive crawl",   status: "COMPLETED",  started: "Jun 2 03:00", files: 176, entities: 1, took: "1 m 38 s" },
  ];
  const lastScan = LIVE ? (window.DMA_LIVE.import_scans || [])[0] : null;
  const runScanLive = () => {
    setScanning(true);
    fetch("/api/admin/scan", { method: "POST" })
      .then(r => r.json().then(b => ({ ok: r.ok, b })))
      .then(({ ok, b }) => { setScanning(false); pushToast(ok ? "Package scan started" : (b.error || "Scan trigger failed"), ok ? "success" : "warn"); })
      .catch(() => { setScanning(false); pushToast("Scan trigger failed", "warn"); });
  };

  return (
    <PageShell title="Import & jobs" crumbs={[{ label: "Admin", href: "/admin" }, { label: "Import & jobs" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · ingest pipeline</div>
          <h1>Import &amp; jobs</h1>
          <div className="sub">Phase 0 Drive crawl · Phase 1 ingest payloads · V7 catalog updates</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" disabled={scanning} onClick={() => { if (LIVE) { runScanLive(); } else { setScanning(true); setTimeout(() => setScanning(false), 2400); } }}>
            {scanning ? <><span className="spinner" /> Scanning…</> : <><Icon name="refresh" size={13} /> Run scan now</>}
          </button>
          {LIVE ? null : (
            <button className="btn btn-secondary" onClick={() => pushToast("Upload payload - drop your app_payload_v1.json file here", "success")}><Icon name="download" size={13} /> Upload payload</button>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "jobs" ? "on" : ""} onClick={() => setTab("jobs")}>Job history</button>
          <button className={tab === "drive" ? "on" : ""} onClick={() => setTab("drive")}>Drive crawl</button>
          <button className={tab === "phase1" ? "on" : ""} onClick={() => setTab("phase1")}>Phase 1 ingest</button>
          <button className={tab === "catalog" ? "on" : ""} onClick={() => setTab("catalog")}>V7 catalog</button>
        </div>
      </div>

      {tab === "jobs" ? (
        <>
          <LiveImportStream />
          <div className="card-head" style={{ padding: "0 0 10px", border: 0 }}>
            <div className="row"><Icon name="evidence" size={14} /><h3>Job history</h3></div>
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Last {jobs.length} jobs</span>
          </div>
          <div className="card flush">
            <table className="tbl">
              <thead><tr><th>Job</th><th>Kind</th><th>Started</th><th>Files</th><th>Entities</th><th>Took</th><th style={{ textAlign: "right" }}>Status</th></tr></thead>
              <tbody>
                {jobs.map(j => (
                  <tr key={j.id} title={j.err || ""}>
                    <td data-label="Job"><span className="chip">{j.id}</span></td>
                    <td data-label="Kind">{j.kind}</td>
                    <td data-label="Started">{j.started}</td>
                    <td data-label="Files">{j.files}</td>
                    <td data-label="Entities">{j.entities}</td>
                    <td data-label="Took">{j.took}</td>
                    <td data-label="Status" style={{ textAlign: "right" }}>
                      <span className={`b ${j.status === "COMPLETED" ? "b-above" : j.status === "FAILED" ? "b-below" : "b-muted"}`}>{j.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : tab === "drive" ? (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="drive" size={16} />
            <div style={{ fontWeight: 600 }}>{LIVE ? "Drive intake · scanned every 30 minutes (Cloud Scheduler)" : "Drive folder · scheduled every 6 hours"}</div>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 11 }}>{LIVE
              ? (lastScan?.started_at ? `Last scan ${new Date(lastScan.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "No scans recorded yet")
              : "Last crawl 2 h ago"}</span>
          </div>
          <div className="g3" style={{ gap: 10 }}>
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Files seen</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>{LIVE ? (lastScan?.files_seen ?? "—") : 187}</div></div>
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>{LIVE ? "New / changed" : "Imported"}</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-mid)", marginTop: 4 }}>{LIVE ? `${lastScan?.files_new ?? 0} / ${lastScan?.files_changed ?? 0}` : 6}</div></div>
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>{LIVE ? "Folders" : "Audit queue"}</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-org)", marginTop: 4 }}>{LIVE ? (lastScan?.folders_seen ?? "—") : DMA.IMPORT_AUDIT.length}</div></div>
          </div>
          <div className="sep" />
          <button className="btn btn-tertiary" onClick={() => navigate("/admin/import/audit")}>Open audit queue <Icon name="arrow-r" size={12} /></button>
        </div>
      ) : tab === "phase1" ? (LIVE ? (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="play" size={16} />
            <div style={{ fontWeight: 600 }}>Synthesis intake · MCP connector</div>
            <span className="spacer" />
            <span className="b b-teal">Connector live</span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>
            Serving content enters this application <strong>only</strong> through the
            DMA connector: the synthesis agent in Claude Cowork submits each page,
            validation issues a structured verdict, and a run promotes atomically —
            all six pages or none. There is no payload upload and no ingest API key;
            nothing else can write serving content.
          </p>
          <div className="sep" />
          <div className="row">
            <Icon name="evidence" size={14} />
            <span style={{ fontSize: 12 }}>Ingestion (workbooks, reports, evidence) arrives via the package scan · synthesis via the connector's 13 tools</span>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="play" size={16} />
            <div style={{ fontWeight: 600 }}>Phase 1 ingest</div>
            <span className="spacer" />
            <span className="b b-teal">API key active</span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>Phase 1 receives <code>app_payload_v1.json</code> from the DMA Claude project on Batch 6 completion. Authenticated with a static bearer token rotated quarterly.</p>
          <div className="sep" />
          <div className="row">
            <Icon name="evidence" size={14} />
            <span style={{ fontSize: 12 }}>Endpoint: <code>POST /api/v1/ingest/assessment</code></span>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn btn-tertiary" onClick={() => pushToast("API key rotated - new key sent via secure channel", "success")}><Icon name="refresh" size={13} /> Rotate API key</button>
            <button className="btn btn-secondary" onClick={() => pushToast("Upload payload manually - select app_payload_v1.json", "success")}><Icon name="download" size={13} /> Upload payload manually</button>
          </div>
        </div>
      )) : (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="stack" size={16} />
            <div style={{ fontWeight: 600 }}>Capability catalogue</div>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 11 }}>{LIVE ? `Current: ${window.DMA_LIVE.catalogue_version || "—"}` : "Current: v7.2 · loaded May 1"}</span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>Updating the catalogue creates a new version. Existing runs retain their original catalogue reference{LIVE ? " (runs pinned to v5.0 serve against it; cross-version diffs mark the retired ESG category NOT_COMPARABLE)" : ""}.</p>
          <div className="row" style={{ marginTop: 10 }}>
            {LIVE ? (
              <button className="btn btn-tertiary" onClick={() => pushToast("Catalogue versions load via the migrate Job (LOAD_CATALOGUES) - no upload from the browser", "warn")}><Icon name="lock" size={13} /> Deploy-managed</button>
            ) : (
              <React.Fragment>
                <button className="btn btn-tertiary" onClick={() => pushToast("V7.3 catalog uploaded - new runs will use the new version", "success")}><Icon name="download" size={13} /> Upload v7.3</button>
                <button className="btn btn-tertiary" onClick={() => pushToast("Opening V7 catalog change log", "success")}>View change log</button>
              </React.Fragment>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}

function ImportAuditPage() {
  const { pushToast } = useApp();
  const [tab, setTab] = useState("REVIEW");
  const items = DMA.IMPORT_AUDIT.filter(i => tab === "ALL" || i.status === tab);

  return (
    <PageShell title="Import audit" crumbs={[{ label: "Admin", href: "/admin" }, { label: "Import audit" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · Phase 0</div>
          <h1>Drive import audit</h1>
          <div className="sub">Files excluded or flagged for review during the last Drive crawl · 6 rules R01–R06</div>
        </div>
      </div>

      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="card-tile"><div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Last crawl</div><div style={{ fontSize: 14, marginTop: 4 }}>Jun 4, 09:12</div></div>
        <div className="card-tile"><div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Candidates processed</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>187</div></div>
        <div className="card-tile"><div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Excluded</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-below)", marginTop: 4 }}>{DMA.IMPORT_AUDIT.filter(i => i.status === "EXCLUDED").length}</div></div>
        <div className="card-tile"><div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Awaiting review</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-org)", marginTop: 4 }}>{DMA.IMPORT_AUDIT.filter(i => i.status === "REVIEW").length}</div></div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "ALL" ? "on" : ""} onClick={() => setTab("ALL")}>All</button>
          <button className={tab === "REVIEW" ? "on" : ""} onClick={() => setTab("REVIEW")}>Review</button>
          <button className={tab === "EXCLUDED" ? "on" : ""} onClick={() => setTab("EXCLUDED")}>Excluded</button>
        </div>
      </div>

      <div className="card flush">
        <table className="tbl">
          <thead><tr><th>Filename</th><th>Rules</th><th>Owner</th><th>Modified</th><th>Status</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
          <tbody>
            {items.map(i => (
              <tr key={i.id}>
                <td data-label="Filename"><div className="f-mono" style={{ fontSize: 11.5, fontWeight: 500 }}>{i.filename}</div><div style={{ fontSize: 10, color: "var(--z-muted)" }}>{i.rationale}</div></td>
                <td data-label="Rules">{i.rules.map(r => <span key={r} className="chip" style={{ marginRight: 2 }}>{r}</span>)}</td>
                <td data-label="Owner" className="f-mono" style={{ fontSize: 10 }}>{i.owner}</td>
                <td data-label="Modified">{fmtDate(i.modifiedTime)}</td>
                <td data-label="Status"><span className={`b ${i.status === "REVIEW" ? "b-org" : "b-below"}`}>{i.status}</span></td>
                <td data-label="Action" style={{ textAlign: "right" }}>
                  {i.status === "REVIEW" ? (
                    <>
                      <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${i.filename} imported`, "success")}>Import</button>
                      <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${i.filename} excluded`, "warn")}>Exclude</button>
                    </>
                  ) : (
                    <span style={{ fontSize: 11, color: "var(--z-muted)" }}>-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}

Object.assign(window, { AlertsPage, ProspectingPage, AdminPage, ImportPage, ImportAuditPage });
