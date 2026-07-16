/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Alerts, Prospecting, Admin pages
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /alerts (Analyst alert dashboard) ───────────────────────────── */
function AlertsPage() {
  const { role } = useApp();
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
          <button className="btn btn-tertiary"><Icon name="download" size={13} /> Export CSV</button>
          <button className="btn btn-secondary"><Icon name="refresh" size={13} /> Refresh feedback file</button>
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
                      <button className="btn btn-tertiary btn-sm">Review</button>
                      <button className="btn btn-tertiary btn-sm">Waive</button>
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
                  <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Build campaign</button></td>
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
            <div style={{ position: "absolute", top: 46, left: 0, right: 0, background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 8, boxShadow: "var(--sh-lg)", zIndex: 20 }}>
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
        {/* Recent searches are wired via GET /api/v1/prospecting (recent_queries
            field, scoped to current user). Hidden until that ships. */}
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
            <button className="btn btn-secondary"><Icon name="download" size={13} /> Download HTML</button>
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

/* ── Admin page hooks ────────────────────────────────────────────────
   Each admin sub-tab uses useAdminResource(loader) to surface a
   {loading, error, data, refetch} triple so the page can show a
   spinner / error banner / empty state / live data branch.
*/
/* ── useAdminResource ────────────────────────────────────────────────
   ERROR HISTORY F1: prior implementation passed loaderFn through a
   useCallback dep array. Callers wrap loaders as inline arrow funcs
   (e.g. `() => window.DMA.admin?.listJobExecutions({limit:50})`),
   which means loaderFn is a fresh closure every render → fetchOnce
   is recreated → useEffect fires → setState → re-render → infinite
   loop. The page would 'still load forever' AND tie up the React
   queue so sidebar nav clicks never processed.

   Operator reported on 2026-05-24: 'while on Import & jobs tab I
   cannot move to any other page.' Symptom = infinite render loop.

   Fix: store loaderFn in a ref so changes don't retrigger the
   effect; depKey is the explicit refetch trigger. Mounts fetch once.
*/
function useAdminResource(loaderFn, depKey) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const loaderRef = useRef(loaderFn);
  loaderRef.current = loaderFn;  // updated on every render but doesn't trigger effects

  const fetchOnce = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: null }));
    const fn = loaderRef.current;
    if (!fn) {
      setState({ loading: false, error: "Backend loader not registered", data: null });
      return;
    }
    try {
      const r = await fn();
      if (r && r.ok) setState({ loading: false, error: null, data: r.data });
      else setState({ loading: false, error: r?.error || "Unknown error", data: null });
    } catch (err) {
      // Promise rejection MUST be caught — uncaught rejections in the
      // useEffect tick stop subsequent React updates and lock the UI.
      setState({ loading: false, error: String(err?.message || err), data: null });
    }
  }, []);  // stable forever
  useEffect(() => { fetchOnce(); }, [fetchOnce, depKey]);
  return { ...state, refetch: fetchOnce };
}

function AdminSectionLoader({ label }) {
  return (
    <div className="loader-section" style={{ padding: "40px 24px" }}>
      <div className="spinner" />
      <div style={{ fontSize: 12.5, color: "var(--z-muted)", marginTop: 8 }}>{label || "Loading…"}</div>
    </div>
  );
}

function AdminSectionError({ error, onRetry }) {
  return (
    <div className="co co-auth" style={{ margin: "12px 0" }}>
      <Icon name="warn" size={14} />
      <div style={{ flex: 1 }}>
        <div className="co-title">Failed to load</div>
        <div className="co-body" style={{ fontSize: 12 }}>{error}</div>
      </div>
      {onRetry ? <button className="btn btn-tertiary btn-sm" onClick={onRetry}><Icon name="refresh" size={11} /> Retry</button> : null}
    </div>
  );
}

function AdminSectionEmpty({ icon, title, body }) {
  return (
    <div className="empty">
      <div className="icon"><Icon name={icon || "evidence"} size={22} /></div>
      <h3>{title}</h3>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

/* ── User-role-edit modal ───────────────────────────────────────────
   Opened by clicking a user row in /admin Users tab. PATCHes the
   /api/v1/admin/users/:id/role endpoint. Server enforces ADMIN. */
function UserRoleEditModal({ user, onClose, onSaved }) {
  const { pushToast } = useApp();
  const [role, setRole] = useState(user?.role || "AE");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  if (!user) return null;
  const save = async () => {
    setSaving(true); setErr(null);
    const r = await (window.DMA.admin?.updateUserRole?.(user.id, role) ?? Promise.resolve({ ok: false, error: "Backend not wired" }));
    setSaving(false);
    if (r.ok) {
      pushToast(`${user.email} role updated to ${role}`, "success");
      onSaved && onSaved(r.data);
      onClose();
    } else {
      setErr(r.error);
    }
  };
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 480 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div className="eyebrow">Edit user role</div>
            <div style={{ fontSize: 17, fontWeight: 600 }}>{user.name || user.email}</div>
            <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{user.email}</div>
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="modal-body">
          {err ? <AdminSectionError error={err} /> : null}
          <div className="field-group">
            <label className="inp-label">Role</label>
            <select className="inp" value={role} onChange={e => setRole(e.target.value)}>
              <option value="AE">AE</option>
              <option value="ANALYST">Analyst</option>
              <option value="ADMIN">Admin</option>
            </select>
            <div className="inp-help">PATCHes <span className="f-mono">/api/v1/admin/users/{user.id}/role</span>. Server re-checks the actor is ADMIN.</div>
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-tertiary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={saving || role === user.role} onClick={save}>
            {saving ? <><span className="spinner" /> Saving…</> : "Save role"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Generic detail drawer for admin row click ──────────────────── */
function AdminDetailDrawer({ title, sub, payload, onClose }) {
  if (!payload) return null;
  return (
    <>
      <div className="drawer-mask" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="title">{title}</div>
            <div className="sub">{sub}</div>
          </div>
          <button className="icon-btn close" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">
          <pre style={{ background: "var(--z-lav)", padding: 12, borderRadius: 6, fontSize: 11, lineHeight: 1.5, overflow: "auto", fontFamily: "var(--font-mono)", color: "var(--z-dark)" }}>
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
        <div className="drawer-foot">
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </>
  );
}

/* ── /admin home + import + audit ──────────────────────────────────
   State-transition contract for the admin home job-trigger surface:
     idle          → user clicks 'Full Drive rescan' or 'Delta scan'
     triggering    → POST /api/v1/admin/jobs/drive_crawler:execute fires
     running       → row created with status='running'; UI polls every 3s
     succeeded     → status flips; tile shows 'Last run: <ts> · <summary>'
     failed        → tile shows error_message; 'View log' opens stderr_tail
     cancelled     → tile shows 'cancelled by operator'
   The previously-hardcoded files-count toast was a Phase-0 wireframe
   stub; every count rendered by this page is now sourced from
   job_executions + import_files via window.DMA.admin.*.
*/
function useJobTrigger(jobName) {
  const { pushToast } = useApp();
  const [execution, setExecution] = useState(null);  // last/current row
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef(null);

  // Stop polling on unmount so we don't leak intervals.
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // Load the most recent execution so 'Last run' shows on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!window.DMA?.admin?.listJobExecutions) return;
      const r = await window.DMA.admin.listJobExecutions({ job_name: jobName, limit: 1 });
      if (cancelled) return;
      if (r.ok && r.data?.items?.length) setExecution(r.data.items[0]);
    })();
    return () => { cancelled = true; };
  }, [jobName]);

  const poll = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      if (!window.DMA?.admin?.getJobExecution) return;
      const r = await window.DMA.admin.getJobExecution(id);
      if (r.ok && r.data) {
        setExecution(r.data);
        if (r.data.status !== "running") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          pushToast(
            r.data.status === "succeeded"
              ? `${jobName} succeeded · ${r.data.result_summary}`
              : `${jobName} ${r.data.status} · ${r.data.result_summary}`,
            r.data.status === "succeeded" ? "success" : "warn",
          );
        }
      }
    }, 3000);
  }, [jobName, pushToast]);

  const trigger = useCallback(async (mode, args) => {
    if (!window.DMA?.admin?.executeJob) {
      pushToast(`Backend loader missing — cannot trigger ${jobName}`, "warn");
      return null;
    }
    setTriggering(true);
    const r = await window.DMA.admin.executeJob(jobName, { mode, args: args || null });
    setTriggering(false);
    if (r.ok && r.data) {
      setExecution(r.data);
      pushToast(`${jobName} ${mode || "default"} started`, "success");
      poll(r.data.id);
      return r.data;
    }
    pushToast(`Failed to trigger ${jobName}: ${r.error || "unknown"}`, "warn");
    return null;
  }, [jobName, poll, pushToast]);

  return { execution, triggering, trigger };
}

function JobStatusLine({ execution, label }) {
  if (!execution) return <span className="b b-muted" data-source="api-empty">no runs yet</span>;
  const tone = execution.status === "running" ? "b-org"
             : execution.status === "succeeded" ? "b-above"
             : execution.status === "failed"    ? "b-below"
             : "b-muted";
  const summary = execution.result_summary || execution.status;
  return (
    <span data-source="api" data-execution-id={execution.id} data-status={execution.status}>
      <span className={`b ${tone}`}>{execution.status.toUpperCase()}</span>
      <span style={{ marginLeft: 6, fontSize: 11, color: "var(--z-muted)" }}>
        {label || "Last run"}: {fmtDate(execution.completed_at || execution.started_at)} · {summary}
        {execution.error_count > 0 ? ` · ${execution.error_count} errors` : ""}
      </span>
    </span>
  );
}

function JobLogDrawer({ execution, onClose }) {
  if (!execution) return null;
  return (
    <>
      <div className="drawer-mask" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="title">{execution.job_name} · {execution.status}</div>
            <div className="sub">Started {fmtDate(execution.started_at)} · {execution.trigger_source}</div>
          </div>
          <button className="icon-btn close" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">
          <div style={{ marginBottom: 12 }}>
            <strong style={{ fontSize: 12 }}>Result summary</strong>
            <div style={{ fontSize: 12.5, color: "var(--z-body)" }}>{execution.result_summary}</div>
          </div>
          {execution.error_message ? (
            <div style={{ marginBottom: 12 }}>
              <strong style={{ fontSize: 12, color: "var(--z-below)" }}>Error</strong>
              <pre style={{ fontSize: 11, background: "var(--z-bg)", padding: 8, borderRadius: 4 }}>{execution.error_message}</pre>
            </div>
          ) : null}
          {execution.stderr_tail ? (
            <div>
              <strong style={{ fontSize: 12 }}>stderr tail (last 50 lines)</strong>
              <pre style={{ fontSize: 11, background: "var(--z-lav)", padding: 10, borderRadius: 4, overflow: "auto", maxHeight: 320 }}>{execution.stderr_tail}</pre>
            </div>
          ) : null}
          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer", fontSize: 11, color: "var(--z-muted)" }}>Raw row</summary>
            <pre style={{ fontSize: 10, background: "var(--z-lav)", padding: 10, borderRadius: 4, overflow: "auto" }}>{JSON.stringify(execution, null, 2)}</pre>
          </details>
        </div>
      </div>
    </>
  );
}

/* ── PendingReviewCard ──────────────────────────────────────────────
   Live-data version of the Phase-0 inference review card. Hits
   /api/v1/admin/pending-review (returns { items, total }). When the
   backend has no rows OR returns an error, the card renders nothing
   and the in-memory DMA.PENDING_REVIEW fixture block below stays
   visible -- demo data doesn't regress while the backend warms up. */
function PendingReviewCard({ onDetail, pushToast }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.pendingReview);
  if (loading) return null;
  if (error || !data) return null;
  const items = Array.isArray(data?.items) ? data.items : [];
  if (items.length === 0) return null;
  return (
    <div className="card flush" data-card="pending-review-live" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>Pending review · Phase 0 entity inferences</h3>
        <span className="b b-org">{items.length} entities</span>
        <span className="spacer" />
        <button className="btn btn-tertiary btn-sm" onClick={refetch}>
          <Icon name="refresh" size={11} /> Refresh
        </button>
      </div>
      <div className="card-body">
        {items.map((e) => {
          const name = e.inferred_name || e.name || e.id;
          const subv = e.inferred_subvertical || e.subvertical || "—";
          const confidence = typeof e.confidence === "number" ? e.confidence : null;
          return (
            <div key={e.id || name} className="card-tile" style={{ marginBottom: 8, padding: 14 }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <strong>{name}</strong>
                <span className="b b-purple">{DMA.SUBVERTICAL_LABEL?.[subv] || subv}</span>
                <span className="spacer" />
                {confidence !== null ? (
                  <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                    Confidence <strong style={{ color: "var(--z-mid)" }}>{confidence.toFixed(2)}</strong>
                  </span>
                ) : null}
              </div>
              {e.signal || e.drive_file ? (
                <div style={{ fontSize: 11.5, color: "var(--z-body)" }}>
                  {e.signal ? <>Inferred via <strong>{e.signal}</strong></> : null}
                  {e.signal && e.drive_file ? " · " : null}
                  {e.drive_file ? <>source: <span className="f-mono">{e.drive_file}</span></> : null}
                </div>
              ) : null}
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={() => pushToast(`Confirmed ${name}`, "success")}>Confirm</button>
                <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Rejected ${name}`, "warn")}>Reject</button>
                <button className="btn btn-tertiary btn-sm" onClick={() => onDetail({ title: name, sub: "Inference source", data: e })}>View source</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


/* ── Operations card ─────────────────────────────────────────────────
   Ported from the Vite-tree `frontend/src/components/OperationsPanel.tsx`
   (which is NOT served in prod per ADR 0011). This is the production
   surface for:
     - end-to-end pipeline trace (proves the full ingest → DB → API →
       UI render chain — was the single biggest visibility gap)
     - 5-category diagnostics (orphan runs, stuck jobs, catalogue
       stubs, missing fixtures, backfill folders flagged for retry)
     - abort button on every running job (closes the "stuck-on-running"
       UX gap)
     - run-full-backfill + retry-failed-only (first-deploy bootstrap +
       the per-folder quarantine retry round-trip)
     - one-click catalogue stub repair + close-stuck-jobs
   The hook polls diagnostics every 10s and trace every 15s. Polls
   stop when the card unmounts. */
function useOperationsPolling() {
  const [diag, setDiag] = useState({ loading: true, error: null, data: null });
  const [trace, setTrace] = useState({ loading: true, error: null, data: null });
  const [jobs, setJobs] = useState({ loading: true, error: null, data: null });
  const refs = useRef({ diag: null, trace: null, jobs: null });

  const pullDiag = useCallback(async () => {
    const fn = window.DMA?.admin?.diagnostics;
    if (!fn) { setDiag({ loading: false, error: "Backend loader not registered", data: null }); return; }
    try {
      const r = await fn();
      if (r?.ok) setDiag({ loading: false, error: null, data: r.data });
      else setDiag({ loading: false, error: r?.error || "Unknown error", data: null });
    } catch (e) {
      setDiag({ loading: false, error: String(e?.message || e), data: null });
    }
  }, []);
  const pullTrace = useCallback(async () => {
    const fn = window.DMA?.admin?.traceIngest;
    if (!fn) { setTrace({ loading: false, error: "Backend loader not registered", data: null }); return; }
    try {
      const r = await fn();
      if (r?.ok) setTrace({ loading: false, error: null, data: r.data });
      else setTrace({ loading: false, error: r?.error || "Unknown error", data: null });
    } catch (e) {
      setTrace({ loading: false, error: String(e?.message || e), data: null });
    }
  }, []);
  const pullJobs = useCallback(async () => {
    const fn = window.DMA?.admin?.listJobExecutions;
    if (!fn) { setJobs({ loading: false, error: "Backend loader not registered", data: null }); return; }
    try {
      const r = await fn({ limit: 10 });
      if (r?.ok) setJobs({ loading: false, error: null, data: r.data });
      else setJobs({ loading: false, error: r?.error || "Unknown error", data: null });
    } catch (e) {
      setJobs({ loading: false, error: String(e?.message || e), data: null });
    }
  }, []);

  // Initial pull on mount + interval polling. Mirrors the Vite-tree
  // TanStack Query refetchInterval pattern: diag every 10s, trace every
  // 15s, jobs adaptive 3s/30s depending on whether anything is running.
  useEffect(() => {
    pullDiag(); pullTrace(); pullJobs();
    refs.current.diag = setInterval(pullDiag, 10_000);
    refs.current.trace = setInterval(pullTrace, 15_000);
    return () => {
      if (refs.current.diag) clearInterval(refs.current.diag);
      if (refs.current.trace) clearInterval(refs.current.trace);
      if (refs.current.jobs) clearInterval(refs.current.jobs);
    };
  }, [pullDiag, pullTrace, pullJobs]);

  // Adaptive jobs polling — fast (3s) when any row is running, slow
  // (30s) otherwise. Cuts request volume by 10× when the operator is
  // just watching for results.
  useEffect(() => {
    if (refs.current.jobs) clearInterval(refs.current.jobs);
    const anyRunning = (jobs.data?.items || []).some(j => j.status === "running");
    refs.current.jobs = setInterval(pullJobs, anyRunning ? 3_000 : 30_000);
    return () => { if (refs.current.jobs) clearInterval(refs.current.jobs); };
  }, [jobs.data, pullJobs]);

  return {
    diag, trace, jobs,
    refetchDiag: pullDiag,
    refetchTrace: pullTrace,
    refetchJobs: pullJobs,
  };
}

function fmtTraceDetail(detail) {
  // Per-step compact rendering. Matches OperationsPanel.tsx semantics
  // so the same /trace/ingest response shape renders identically in
  // both surfaces during the production cutover.
  if (!detail || typeof detail !== "object") return "—";
  if ("error" in detail) return `⚠ ${String(detail.error).slice(0, 80)}`;
  if ("count" in detail) {
    const note = (detail.note || "").slice(0, 60);
    return note ? `${detail.count} (${note})` : String(detail.count);
  }
  if ("subcap_score_count" in detail) {
    return `${detail.subcap_score_count} scores · avg=${detail.average_score ?? "—"}`;
  }
  if ("request_id" in detail) return `${detail.request_id} (${detail.entity_name ?? ""})`;
  if ("reason" in detail) return String(detail.reason).slice(0, 80);
  return JSON.stringify(detail).slice(0, 100);
}

function OperationsCard({ onViewLog }) {
  const { pushToast } = useApp();
  const { diag, trace, jobs, refetchDiag, refetchJobs, refetchTrace } = useOperationsPolling();
  const [busy, setBusy] = useState(null);  // 'stubs' | 'closeStuck' | 'full' | 'retry' | abort-id

  const doMutation = useCallback(async (key, fn, successFmt, failurePrefix) => {
    setBusy(key);
    try {
      const r = await fn();
      if (r?.ok) {
        pushToast(successFmt(r.data), "success");
        refetchDiag(); refetchJobs(); refetchTrace();
      } else {
        pushToast(`${failurePrefix}: ${r?.error || "unknown"}`, "warn");
      }
    } catch (e) {
      pushToast(`${failurePrefix}: ${String(e?.message || e)}`, "warn");
    } finally {
      setBusy(null);
    }
  }, [pushToast, refetchDiag, refetchJobs, refetchTrace]);

  if (diag.loading) {
    return (
      <div className="card flush" style={{ marginBottom: 16 }}>
        <div className="card-head"><h3>Operations</h3></div>
        <div className="card-body"><AdminSectionLoader label="Loading diagnostics…" /></div>
      </div>
    );
  }
  if (diag.error) {
    return (
      <div className="card flush" style={{ marginBottom: 16 }}>
        <div className="card-head"><h3>Operations</h3></div>
        <div className="card-body">
          <AdminSectionError error={`Couldn't load diagnostics: ${diag.error}`} onRetry={refetchDiag} />
        </div>
      </div>
    );
  }

  const d = diag.data || {};
  const summary = d._summary || {};
  const healthy = summary.healthy === true;
  const traceSteps = trace.data?.steps || [];
  const recentJobs = (jobs.data?.items || []);

  return (
    <div className="card flush" data-card="operations" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>Operations</h3>
        <span className={`b ${healthy ? "b-above" : "b-org"}`}>
          {healthy ? "Healthy" : "Issues detected"}
        </span>
      </div>
      <div className="card-body">

        {/* ── Pipeline trace ── */}
        <section style={{ marginBottom: 18 }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <strong style={{ fontSize: 12.5 }}>Pipeline trace</strong>
            <span style={{ fontSize: 11, color: "var(--z-muted)", marginLeft: 8 }}>
              ingest → DB → API → UI render · polls every 15s
            </span>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={refetchTrace}>
              <Icon name="refresh" size={11} /> Refresh
            </button>
          </div>
          {trace.error ? (
            <AdminSectionError
              error={`Couldn't load /admin/trace/ingest: ${trace.error}. Diagnostics below still poll independently.`}
              onRetry={refetchTrace}
            />
          ) : traceSteps.length === 0 ? (
            <div className="empty" style={{ padding: "24px 12px" }}>
              <div className="icon"><Icon name="evidence" size={20} /></div>
              <h3>No ingest activity yet</h3>
              <p style={{ fontSize: 12 }}>
                Once a run lands, this surface shows the per-step status from drive scan
                through UI render. Use the Backfill actions below to start one.
              </p>
            </div>
          ) : (
            <div className="table" data-source="api" data-source-uri="/api/v1/admin/trace/ingest">
              <table>
                <thead>
                  <tr><th style={{ width: 32 }}>#</th><th>Step</th><th>Status</th><th>Detail</th></tr>
                </thead>
                <tbody>
                  {traceSteps.map((s, i) => (
                    <tr key={i} data-step={s.step} data-status={s.status}>
                      <td style={{ color: "var(--z-muted)", fontFamily: "var(--font-mono)", fontSize: 11 }}>{i + 1}</td>
                      <td style={{ fontWeight: 500 }}>{s.step}</td>
                      <td>
                        <span className={`b ${s.status === "ok" ? "b-above" : s.status === "warning" ? "b-org" : "b-below"}`}>
                          {s.status}
                        </span>
                      </td>
                      <td style={{ fontSize: 11.5, color: "var(--z-body)" }}>{fmtTraceDetail(s.detail)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Diagnostics tiles ── */}
        <section style={{ marginBottom: 18 }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <strong style={{ fontSize: 12.5 }}>Diagnostics</strong>
            <span style={{ fontSize: 11, color: "var(--z-muted)", marginLeft: 8 }}>
              polls every 10s · last checked {fmtDate(d._summary?.checked_at)}
            </span>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={refetchDiag}>
              <Icon name="refresh" size={11} /> Refresh
            </button>
          </div>
          <div className="g4" style={{ gap: 10 }}>
            {Object.entries(d).filter(([k]) => !k.startsWith("_")).map(([key, value]) => {
              const count = typeof value === "object" && value ? (value.count ?? 0) : 0;
              const note = typeof value === "object" && value ? value.note : null;
              const ok = count === 0;
              return (
                <div key={key} className="card-tile" style={{ padding: 12 }}>
                  <div className="row" style={{ marginBottom: 4 }}>
                    <strong style={{ fontSize: 11.5 }}>{key.replace(/_/g, " ")}</strong>
                    <span className="spacer" />
                    <span className={`b ${ok ? "b-above" : "b-org"}`}>{ok ? "OK" : count}</span>
                  </div>
                  {note ? <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{note}</div> : null}
                </div>
              );
            })}
          </div>
        </section>

        {/* ── Action row: backfill + repair ── */}
        <section style={{ marginBottom: 18 }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <strong style={{ fontSize: 12.5 }}>Actions</strong>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              data-action="run-full-backfill"
              className="btn btn-primary btn-sm"
              disabled={busy === "full"}
              onClick={() => doMutation(
                "full",
                () => window.DMA.admin.runFullBackfill(),
                (data) => `Dispatched full historical backfill (id=${(data?.id || "").slice(0, 8)}…). Watch Recent jobs.`,
                "Backfill dispatch failed",
              )}
            >
              {busy === "full" ? <><span className="spinner" /> Dispatching…</> : <><Icon name="play" size={11} /> Run full backfill</>}
            </button>
            <button
              data-action="run-retry-failed"
              className="btn btn-secondary btn-sm"
              disabled={busy === "retry"}
              onClick={() => doMutation(
                "retry",
                () => window.DMA.admin.runRetryFailedBackfill(),
                (data) => `Dispatched retry-only backfill (id=${(data?.id || "").slice(0, 8)}…).`,
                "Retry dispatch failed",
              )}
            >
              {busy === "retry" ? <><span className="spinner" /> Dispatching…</> : <><Icon name="refresh" size={11} /> Retry failed only</>}
            </button>
            <button
              data-action="repair-catalogue-stubs"
              className="btn btn-tertiary btn-sm"
              disabled={busy === "stubs"}
              onClick={() => doMutation(
                "stubs",
                () => window.DMA.admin.repairCatalogueStubs(),
                (data) => {
                  const n = data?.count ?? (data?.inserted_versions?.length || 0);
                  return n > 0
                    ? `Inserted ${n} catalogue band-aid row(s).`
                    : "Catalogue rows already present — no action needed.";
                },
                "Repair failed",
              )}
            >
              {busy === "stubs" ? <><span className="spinner" /> Repairing…</> : "Repair catalogue stubs"}
            </button>
            <button
              data-action="repair-close-stuck"
              className="btn btn-tertiary btn-sm"
              disabled={busy === "closeStuck"}
              onClick={() => doMutation(
                "closeStuck",
                () => window.DMA.admin.repairCloseStuckJobs(),
                (data) => {
                  const n = data?.closed_count ?? 0;
                  return n > 0 ? `Auto-closed ${n} stuck job row(s).` : "No stuck jobs found.";
                },
                "Close-stuck failed",
              )}
            >
              {busy === "closeStuck" ? <><span className="spinner" /> Working…</> : "Close stuck jobs"}
            </button>
          </div>
        </section>

        {/* ── Recent jobs with abort buttons ── */}
        <section>
          <div className="row" style={{ marginBottom: 8 }}>
            <strong style={{ fontSize: 12.5 }}>Recent jobs</strong>
            <span style={{ fontSize: 11, color: "var(--z-muted)", marginLeft: 8 }}>
              adaptive polling — 3s while running, 30s idle
            </span>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={refetchJobs}>
              <Icon name="refresh" size={11} /> Refresh
            </button>
          </div>
          {jobs.error ? (
            <AdminSectionError error={jobs.error} onRetry={refetchJobs} />
          ) : recentJobs.length === 0 ? (
            <AdminSectionEmpty icon="evidence" title="No job executions yet" body="Trigger a job above to see it here." />
          ) : (
            <div className="table" data-source="api" data-source-uri="/api/v1/admin/jobs/executions">
              <table>
                <thead>
                  <tr>
                    <th>Job</th><th>Status</th><th>Started</th>
                    <th>Result</th><th style={{ width: 96 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {recentJobs.map((j) => (
                    <tr key={j.id} data-execution-id={j.id} data-status={j.status}>
                      <td>
                        <div style={{ fontWeight: 500, fontSize: 12 }}>{j.job_name}</div>
                        <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{j.mode || "—"}</div>
                      </td>
                      <td>
                        <span className={`b ${
                          j.status === "running"   ? "b-org" :
                          j.status === "succeeded" ? "b-above" :
                          j.status === "failed"    ? "b-below" :
                          j.status === "cancelled" ? "b-muted" : "b-muted"
                        }`}>{j.status}</span>
                      </td>
                      <td style={{ fontSize: 11, color: "var(--z-body)" }}>{fmtDate(j.started_at)}</td>
                      <td style={{ fontSize: 11, color: "var(--z-body)" }}>{j.result_summary || "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        {j.status === "running" ? (
                          <button
                            data-action="abort-job"
                            className="btn btn-tertiary btn-sm"
                            disabled={busy === `abort:${j.id}`}
                            onClick={() => doMutation(
                              `abort:${j.id}`,
                              () => window.DMA.admin.abortJob(j.id),
                              (data) => `Aborted ${data?.job_name || j.job_name}.`,
                              "Abort failed",
                            )}
                          >
                            {busy === `abort:${j.id}` ? <span className="spinner" /> : "Abort"}
                          </button>
                        ) : j.error_message || j.stderr_tail ? (
                          <button className="btn btn-tertiary btn-sm" onClick={() => onViewLog(j)}>View log</button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}


function AdminPage() {
  const { role, pushToast } = useApp();
  const [tab, setTab] = useState("home");
  // Drawer / modal state shared across sub-tabs
  const [editUser, setEditUser] = useState(null);
  const [detail, setDetail] = useState(null);
  const [logDrawer, setLogDrawer] = useState(null);

  // Job triggers for each admin home button.
  const drive = useJobTrigger("drive_crawler");
  const embedder = useJobTrigger("embedder");
  const peer = useJobTrigger("peer_patterns");

  if (role !== "ADMIN") return <PageShell title="Admin"><div className="empty"><div className="icon"><Icon name="lock" size={22} /></div><h3>Admin access required</h3></div></PageShell>;

  // Each useAdminResource lazily fetches when its tab is first shown.
  // We mount unconditionally (cheap; refetch is a no-op) and the
  // <AdminUsersTab> / <AdminBuildQaTab> / <AdminCatalogueTab> wrappers
  // bind to the relevant resource hook.

  return (
    <PageShell title="Admin" crumbs={[{ label: "Admin" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Settings &amp; operations</div>
          <h1>Admin</h1>
          <div className="sub">System operations &amp; user management · live data from /api/v1/admin/*</div>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "home" ? "on" : ""} onClick={() => setTab("home")}>Overview</button>
          <button className={tab === "users" ? "on" : ""} onClick={() => setTab("users")}>Users</button>
          <button className={tab === "audit" ? "on" : ""} onClick={() => setTab("audit")}>Import audit</button>
          <button className={tab === "catalogue" ? "on" : ""} onClick={() => setTab("catalogue")}>Catalogue</button>
          <button className={tab === "buildqa" ? "on" : ""} onClick={() => setTab("buildqa")}>Build QA</button>
          <button className={tab === "assignments" ? "on" : ""} onClick={() => setTab("assignments")}>Assignments</button>
          <button className={tab === "budget" ? "on" : ""} onClick={() => setTab("budget")}>Vertex budget</button>
        </div>
      </div>

      {tab === "home" ? (
        <>
          {/* Operations panel — pipeline trace + diagnostics + abort
              buttons + repair actions. Sits at the TOP of the home
              tab because operator-reported gaps were "I can't see
              what the pipeline is doing" and "I can't abort a stuck
              run" — both fixed here. Wave 3 of the 2026-05-28 audit. */}
          <OperationsCard onViewLog={setLogDrawer} />

          {/* PENDING_REVIEW entities — Phase 0 entity inferences from
              drive_crawler. Wired live to /api/v1/admin/pending-review
              via window.DMA.admin.pendingReview (Wave 3b audit fix --
              previously this read DMA.PENDING_REVIEW fixture data).
              Falls back to the in-memory fixture when the backend
              returns no rows so the seeded demo still has content. */}
          <PendingReviewCard onDetail={setDetail} pushToast={pushToast} />

          {DMA.PENDING_REVIEW.length > 0 ? (
            <div className="card flush" style={{ marginBottom: 16 }}>
              <div className="card-head"><h3>Pending review · Phase 0 entity inferences (fixture)</h3><span className="b b-muted">{DMA.PENDING_REVIEW.length} entities · in-memory</span></div>
              <div className="card-body">
                {DMA.PENDING_REVIEW.map(e => (
                  <div key={e.id} className="card-tile" style={{ marginBottom: 8, padding: 14 }}>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <strong>{e.inferred_name}</strong>
                      <span className="b b-purple">{DMA.SUBVERTICAL_LABEL[e.inferred_subvertical] || e.inferred_subvertical}</span>
                      <span className="spacer" />
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Confidence <strong style={{ color: "var(--z-mid)" }}>{e.confidence.toFixed(2)}</strong></span>
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--z-body)" }}>
                      Inferred via <strong>{e.signal}</strong> · source: <span className="f-mono">{e.drive_file}</span>
                    </div>
                    <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                      <button className="btn btn-primary btn-sm" onClick={() => pushToast(`Confirmed ${e.inferred_name}`, "success")}>Confirm</button>
                      <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Rejected ${e.inferred_name}`, "warn")}>Reject</button>
                      <button className="btn btn-tertiary btn-sm" onClick={() => setDetail({ title: e.inferred_name, sub: "Inference source", data: e })}>View source</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="g2">
            <div className="card" data-job-card="drive_crawler">
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="drive" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Drive crawl</div>
                <span className="spacer" />
                <JobStatusLine execution={drive.execution} />
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 12, lineHeight: 1.55 }}>Scheduled every 6 hours · target folder <span className="f-mono" style={{ fontSize: 11 }}>1uvt3kh…2O0P</span></p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button data-job-action="drive_crawler:delta" className="btn btn-primary btn-sm" disabled={drive.triggering || drive.execution?.status === "running"} onClick={() => drive.trigger("delta")}>
                  {drive.triggering || drive.execution?.status === "running" ? <><span className="spinner" /> Running…</> : <><Icon name="refresh" size={12} /> Delta scan</>}
                </button>
                <button data-job-action="drive_crawler:full" className="btn btn-tertiary btn-sm" disabled={drive.triggering || drive.execution?.status === "running"} onClick={() => drive.trigger("full")}>Full Drive rescan…</button>
                {drive.execution?.status === "failed" || drive.execution?.stderr_tail ? (
                  <button className="btn btn-tertiary btn-sm" onClick={() => setLogDrawer(drive.execution)}>View log</button>
                ) : null}
                <button className="btn btn-tertiary btn-sm" onClick={() => setTab("audit")}>Import audit →</button>
                <button className="btn btn-tertiary btn-sm" onClick={() => navigate("/admin/import")}>Job history →</button>
              </div>
            </div>
            <div className="card" data-job-card="embedder">
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="stack" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Embeddings worker</div>
                <span className="spacer" />
                <JobStatusLine execution={embedder.execution} />
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 12, lineHeight: 1.55 }}>Recomputes evidence + section pgvector embeddings. Use Delta after a fresh ingest; Full when the catalogue version changes.</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button data-job-action="embedder:delta" className="btn btn-primary btn-sm" disabled={embedder.triggering || embedder.execution?.status === "running"} onClick={() => embedder.trigger("delta")}>
                  {embedder.triggering || embedder.execution?.status === "running" ? <><span className="spinner" /> Running…</> : <><Icon name="refresh" size={12} /> Trigger embedder (delta)</>}
                </button>
                <button data-job-action="embedder:full" className="btn btn-tertiary btn-sm" disabled={embedder.triggering || embedder.execution?.status === "running"} onClick={() => embedder.trigger("full")}>Full re-embed</button>
                {embedder.execution?.status === "failed" ? (
                  <button className="btn btn-tertiary btn-sm" onClick={() => setLogDrawer(embedder.execution)}>View log</button>
                ) : null}
              </div>
            </div>
            <div className="card" data-job-card="peer_patterns">
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="users" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Peer patterns (KMeans archetypes)</div>
                <span className="spacer" />
                <JobStatusLine execution={peer.execution} />
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 12, lineHeight: 1.55 }}>Re-clusters subcap-score vectors per subvertical → peer_archetypes rows.</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button data-job-action="peer_patterns:full" className="btn btn-primary btn-sm" disabled={peer.triggering || peer.execution?.status === "running"} onClick={() => peer.trigger("full")}>
                  {peer.triggering || peer.execution?.status === "running" ? <><span className="spinner" /> Running…</> : <><Icon name="refresh" size={12} /> Run peer_patterns now</>}
                </button>
                {peer.execution?.status === "failed" ? (
                  <button className="btn btn-tertiary btn-sm" onClick={() => setLogDrawer(peer.execution)}>View log</button>
                ) : null}
              </div>
            </div>
            <div className="card">
              <div className="row" style={{ marginBottom: 12 }}>
                <Icon name="money" size={16} />
                <div style={{ fontWeight: 600, fontSize: 13 }}>Vertex AI budget</div>
                <span className="spacer" />
                <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Live · /api/v1/admin/vertex-budget</span>
              </div>
              <AdminVertexBudgetMini />
            </div>
          </div>
        </>
      ) : null}

      {tab === "users" ? (
        <AdminUsersTab onEditUser={setEditUser} onDetail={setDetail} />
      ) : null}
      {tab === "audit" ? (
        <AdminImportAuditTab onDetail={setDetail} />
      ) : null}
      {tab === "catalogue" ? (
        <AdminCatalogueTab onDetail={setDetail} />
      ) : null}
      {tab === "buildqa" ? (
        <AdminBuildQaTab onDetail={setDetail} />
      ) : null}
      {tab === "assignments" ? (
        <AdminAssignmentsTab onDetail={setDetail} />
      ) : null}
      {tab === "budget" ? (
        <AdminBudgetTab />
      ) : null}

      {editUser ? <UserRoleEditModal user={editUser} onClose={() => setEditUser(null)} onSaved={() => setEditUser(null)} /> : null}
      {detail ? <AdminDetailDrawer title={detail.title} sub={detail.sub} payload={detail.data} onClose={() => setDetail(null)} /> : null}
      {logDrawer ? <JobLogDrawer execution={logDrawer} onClose={() => setLogDrawer(null)} /> : null}
    </PageShell>
  );
}

/* ── Vertex budget mini-tile ────────────────────────────────────────
   Sources directly from /api/v1/admin/vertex-budget (already wired by
   the backend). Empty-state when audit_log has zero rows. */
function AdminVertexBudgetMini() {
  const { loading, error, data } = useAdminResource(window.DMA.admin?.vertexBudget);
  if (loading) return <div style={{ fontSize: 11, color: "var(--z-muted)" }} data-source="loading">Loading…</div>;
  if (error) return <div style={{ fontSize: 11, color: "var(--z-below)" }} data-source="error">{error}</div>;
  if (!data) return <div style={{ fontSize: 11, color: "var(--z-muted)" }} data-source="api-empty">No usage yet</div>;
  const spent = data.spent_usd ?? 0;
  const cap = data.budget_usd ?? 100;
  const pct = data.pct_used ?? 0;
  return (
    <div data-source="api">
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
        <span>${spent.toFixed(2)} / ${cap.toFixed(0)}</span>
        <span style={{ color: "var(--z-muted)" }}>{pct.toFixed(1)}%</span>
      </div>
      <div className="prog"><div className="prog-fill" style={{ width: `${Math.min(100, pct)}%` }} /></div>
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--z-muted)" }}>
        Period {data.period} · {(data.top_surfaces || []).length} surfaces tracked
      </div>
    </div>
  );
}

function AdminUsersTab({ onEditUser, onDetail }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.listUsers);
  const items = data?.items || [];
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Users · {loading ? "loading…" : items.length}</h3>
        <button className="btn btn-tertiary btn-sm" onClick={refetch}><Icon name="refresh" size={11} /> Refresh</button>
      </div>
      {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/users…" /> :
       error   ? <AdminSectionError error={error} onRetry={refetch} /> :
       items.length === 0 ? <AdminSectionEmpty icon="users" title="No users yet" body="Once people sign in via OAuth, their rows land in the users table and appear here." /> :
       (
         <table className="tbl tbl-clickable">
           <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Active</th><th>Last login</th><th style={{ textAlign: "right" }}>Manage</th></tr></thead>
           <tbody>
             {items.map(u => (
               <tr key={u.id} onClick={() => onDetail({ title: u.name || u.email, sub: u.email, data: u })}>
                 <td className="f-mono" style={{ fontSize: 11.5 }}>{u.email}</td>
                 <td>{u.name || "—"}</td>
                 <td><span className={`b ${u.role === "ADMIN" ? "b-below" : u.role === "ANALYST" ? "b-ph0" : "b-teal"}`}>{u.role}</span></td>
                 <td>{u.is_active ? <span className="b b-above">YES</span> : <span className="b b-muted">NO</span>}</td>
                 <td style={{ fontSize: 11 }}>{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                 <td style={{ textAlign: "right" }} onClick={e => e.stopPropagation()}>
                   <button className="btn btn-tertiary btn-sm" onClick={() => onEditUser(u)}><Icon name="edit" size={11} /> Edit role</button>
                 </td>
               </tr>
             ))}
           </tbody>
         </table>
       )}
    </div>
  );
}

function AdminImportAuditTab({ onDetail }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.listImportAudit);
  const items = data?.items || [];
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Import audit · {loading ? "loading…" : items.length}</h3>
        <button className="btn btn-tertiary btn-sm" onClick={refetch}><Icon name="refresh" size={11} /> Refresh</button>
      </div>
      {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/imports/audit…" /> :
       error   ? <AdminSectionError error={error} onRetry={refetch} /> :
       items.length === 0 ? <AdminSectionEmpty icon="evidence" title="No files awaiting review" body="When the Drive crawler flags candidates for review, they appear here." /> :
       (
         <table className="tbl tbl-clickable">
           <thead><tr><th>File</th><th>Rules</th><th>Owner</th><th>Modified</th><th>Status</th><th style={{ textAlign: "right" }}>Detail</th></tr></thead>
           <tbody>
             {items.map(i => (
               <tr key={i.id || i.file_id} onClick={() => onDetail({ title: i.filename || i.file_name, sub: (i.rules || []).join(", ") || i.rationale, data: i })}>
                 <td className="f-mono" style={{ fontSize: 11.5 }}>{i.filename || i.file_name}</td>
                 <td>{(i.rules || []).map(r => <span key={r} className="chip" style={{ marginRight: 2 }}>{r}</span>)}</td>
                 <td className="f-mono" style={{ fontSize: 10 }}>{i.owner || "—"}</td>
                 <td style={{ fontSize: 11 }}>{i.modifiedTime ? fmtDate(i.modifiedTime) : "—"}</td>
                 <td><span className={`b ${i.status === "REVIEW" ? "b-org" : i.status === "EXCLUDED" ? "b-below" : "b-muted"}`}>{i.status}</span></td>
                 <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Open</button></td>
               </tr>
             ))}
           </tbody>
         </table>
       )}
    </div>
  );
}

function AdminCatalogueTab({ onDetail }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.listCatalogue);
  const items = data?.items || data?.versions || [];
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Catalogue versions · {loading ? "loading…" : items.length}</h3>
        <button className="btn btn-tertiary btn-sm" onClick={refetch}><Icon name="refresh" size={11} /> Refresh</button>
      </div>
      {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/catalogue…" /> :
       error   ? <AdminSectionError error={error} onRetry={refetch} /> :
       items.length === 0 ? <AdminSectionEmpty icon="stack" title="No catalogue versions" body="Run the V7 loader (workers.ccg_loader) to seed the first version." /> :
       (
         <table className="tbl tbl-clickable">
           <thead><tr><th>Version</th><th>Loaded at</th><th>Subcaps</th><th>Status</th><th style={{ textAlign: "right" }}>Detail</th></tr></thead>
           <tbody>
             {items.map(v => (
               <tr key={v.version || v.id} onClick={() => onDetail({ title: `Catalogue ${v.version || v.id}`, sub: v.status || "—", data: v })}>
                 <td className="f-mono">{v.version || v.id}</td>
                 <td style={{ fontSize: 11 }}>{v.loaded_at ? fmtDate(v.loaded_at) : v.created_at ? fmtDate(v.created_at) : "—"}</td>
                 <td>{v.subcap_count ?? v.subcaps ?? "—"}</td>
                 <td><span className={`b ${v.status === "ACTIVE" ? "b-above" : "b-muted"}`}>{v.status || "—"}</span></td>
                 <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Diff</button></td>
               </tr>
             ))}
           </tbody>
         </table>
       )}
    </div>
  );
}

function AdminBuildQaTab({ onDetail }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.listBuildQa);
  const items = data?.gates || data?.items || [];
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Build QA gates · {loading ? "loading…" : items.length}</h3>
        <button className="btn btn-tertiary btn-sm" onClick={refetch}><Icon name="refresh" size={11} /> Refresh</button>
      </div>
      {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/build-qa…" /> :
       error   ? <AdminSectionError error={error} onRetry={refetch} /> :
       items.length === 0 ? <AdminSectionEmpty icon="shield" title="No QA gate rows yet" body="CI writes one row per gate per build into build_qa_gates. The first CI run fills this list." /> :
       (
         <table className="tbl tbl-clickable">
           <thead><tr><th>Build</th><th>Stage</th><th>Gate</th><th>Status</th><th>Reason</th><th style={{ textAlign: "right" }}>Detail</th></tr></thead>
           <tbody>
             {items.map((g, i) => (
               <tr key={(g.id || i) + ":" + (g.gate || g.gate_id)} onClick={() => onDetail({ title: g.gate || g.gate_id, sub: g.build_id || "—", data: g })}>
                 <td className="f-mono" style={{ fontSize: 11 }}>{g.build_id || g.build || "—"}</td>
                 <td>{g.stage || "—"}</td>
                 <td>{g.gate || g.gate_id}</td>
                 <td><span className={`b ${g.status === "PASS" ? "b-above" : g.status === "FAIL" ? "b-below" : "b-org"}`}>{g.status}</span></td>
                 <td style={{ fontSize: 11 }}>{g.reason || g.message || "—"}</td>
                 <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Open</button></td>
               </tr>
             ))}
           </tbody>
         </table>
       )}
    </div>
  );
}

function AdminAssignmentsTab({ onDetail }) {
  const { loading, error, data, refetch } = useAdminResource(window.DMA.admin?.listAssignments);
  const items = data?.items || [];
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>AE assignments · {loading ? "loading…" : items.length}</h3>
        <button className="btn btn-tertiary btn-sm" onClick={refetch}><Icon name="refresh" size={11} /> Refresh</button>
      </div>
      {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/assignments…" /> :
       error   ? <AdminSectionError error={error} onRetry={refetch} /> :
       items.length === 0 ? <AdminSectionEmpty icon="users" title="No assignments pending review" body="Hybrid AE assignment (Ops Sheet + Drive owner inference) lands disagreements here for admin override." /> :
       (
         <table className="tbl tbl-clickable">
           <thead><tr><th>Entity</th><th>Sheet AE</th><th>Drive owner</th><th>Confidence</th><th style={{ textAlign: "right" }}>Detail</th></tr></thead>
           <tbody>
             {items.map((a, i) => (
               <tr key={a.id || i} onClick={() => onDetail({ title: a.entity_name || a.display_id, sub: "Assignment review", data: a })}>
                 <td>{a.entity_name || a.display_id}</td>
                 <td className="f-mono" style={{ fontSize: 11 }}>{a.sheet_ae || "—"}</td>
                 <td className="f-mono" style={{ fontSize: 11 }}>{a.drive_owner || "—"}</td>
                 <td>{a.confidence != null ? a.confidence.toFixed(2) : "—"}</td>
                 <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Resolve</button></td>
               </tr>
             ))}
           </tbody>
         </table>
       )}
    </div>
  );
}

function AdminBudgetTab() {
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="money" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Vertex AI budget</div>
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Endpoint pending — GET /api/v1/admin/vertex-budget</span>
      </div>
      <div className="prog"><div className="prog-fill" style={{ width: "0%" }} /></div>
      <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55 }}>
        Spend is summed from <span className="f-mono">audit_log</span> rows (one per Gemini call) using Flash $0.0001875/1k vs Pro $0.0035/1k. Cap of $100/mo is configurable in Terraform var.vertex_budget_usd.
        <div style={{ marginTop: 6, color: "var(--z-muted)" }}>
          TODO(backend): expose a /api/v1/admin/vertex-budget endpoint returning {`{ spent_usd, cap_usd, period_start, calls }`}.
        </div>
      </div>
    </div>
  );
}

/* ── /admin/import ─ Live job history sourced from /admin/jobs/executions
   State-transition contract:
     mounted        → fetch jobs registry + recent executions
     summary_loaded → 4 tiles show summary counts from import-audit/summary
     row_click      → AdminDetailDrawer with the raw row JSON
     trigger        → "Delta scan" calls useJobTrigger('drive_crawler') */
function ImportPage() {
  const { role, pushToast } = useApp();
  const [tab, setTab] = useState("jobs");
  const drive = useJobTrigger("drive_crawler");
  const summary = useAdminResource(window.DMA.admin?.importAuditSummary);
  const executions = useAdminResource(
    () => window.DMA.admin?.listJobExecutions({ limit: 50 }),
  );
  const [detail, setDetail] = useState(null);
  const [logDrawer, setLogDrawer] = useState(null);
  if (role !== "ADMIN") return <PageShell title="Import"><div className="empty"><div className="icon"><Icon name="lock" size={22} /></div><h3>Admin access required</h3></div></PageShell>;

  const items = executions.data?.items || [];
  const s = summary.data || {};

  return (
    <PageShell title="Import & jobs" crumbs={[{ label: "Admin", href: "/admin" }, { label: "Import & jobs" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · ingest pipeline</div>
          <h1>Import &amp; jobs</h1>
          <div className="sub">Live from /api/v1/admin/jobs/executions · scheduler + admin-ui triggers · errors expand</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" data-job-action="drive_crawler:delta"
                  disabled={drive.triggering || drive.execution?.status === "running"}
                  onClick={() => drive.trigger("delta")}>
            {drive.triggering || drive.execution?.status === "running"
              ? <><span className="spinner" /> Running…</>
              : <><Icon name="refresh" size={13} /> Delta scan</>}
          </button>
          <button className="btn btn-tertiary" onClick={executions.refetch}><Icon name="refresh" size={13} /> Refresh</button>
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
        <div className="card flush" data-source="api">
          {executions.loading ? <AdminSectionLoader label="Fetching /api/v1/admin/jobs/executions…" /> :
           executions.error   ? <AdminSectionError error={executions.error} onRetry={executions.refetch} /> :
           items.length === 0 ? <AdminSectionEmpty icon="evidence" title="No job executions yet" body="Trigger a scan from the buttons above; rows land here in real-time." /> :
           (
             <table className="tbl tbl-clickable">
               <thead><tr><th>Job</th><th>Mode</th><th>Status</th><th>Started</th><th>Result</th><th>Duration</th><th>Trigger</th><th style={{ textAlign: "right" }}>Detail</th></tr></thead>
               <tbody>
                 {items.map(j => (
                   <tr key={j.id} data-job-name={j.job_name} data-status={j.status}
                       onClick={() => setDetail({ title: `${j.job_name} · ${j.id.slice(0, 8)}`, sub: j.status, data: j })}>
                     <td><span className="chip">{j.job_name}</span></td>
                     <td>{j.mode || "—"}</td>
                     <td>
                       <span className={`b ${j.status === "succeeded" ? "b-above" : j.status === "failed" ? "b-below" : j.status === "running" ? "b-org" : "b-muted"}`}>
                         {j.status.toUpperCase()}
                       </span>
                     </td>
                     <td style={{ fontSize: 11 }}>{fmtDate(j.started_at)}</td>
                     <td style={{ fontSize: 11.5 }}>{j.result_summary || "—"}{j.error_count > 0 ? ` · ${j.error_count} errors` : ""}</td>
                     <td style={{ fontSize: 11 }}>{j.duration_sec != null ? `${Math.round(j.duration_sec)}s` : "—"}</td>
                     <td style={{ fontSize: 11 }}>{j.trigger_source}</td>
                     <td style={{ textAlign: "right" }} onClick={e => e.stopPropagation()}>
                       {j.stderr_tail || j.error_message
                         ? <button className="btn btn-tertiary btn-sm" onClick={() => setLogDrawer(j)}>View log</button>
                         : <button className="btn btn-tertiary btn-sm" onClick={() => setDetail({ title: j.job_name, sub: j.status, data: j })}>Open</button>}
                     </td>
                   </tr>
                 ))}
               </tbody>
             </table>
           )}
        </div>
      ) : tab === "drive" ? (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="drive" size={16} />
            <div style={{ fontWeight: 600 }}>Drive folder · scheduled every 6 hours</div>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 11 }} data-source={summary.loading ? "loading" : "api"}>
              {summary.loading ? "loading…"
                : s.last_crawl_at ? `Last crawl ${fmtDate(s.last_crawl_at)}`
                : "Never crawled"}
            </span>
          </div>
          <div className="g3" style={{ gap: 10 }} data-source="api">
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Candidates</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>{s.candidates_processed ?? 0}</div></div>
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Imported</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-mid)", marginTop: 4 }}>{s.files_imported ?? 0}</div></div>
            <div className="card-tile"><div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em" }}>Audit queue</div><div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-org)", marginTop: 4 }}>{s.files_awaiting_review ?? 0}</div></div>
          </div>
          <div className="sep" />
          <button className="btn btn-tertiary" onClick={() => navigate("/admin/import/audit")}>Open audit queue <Icon name="arrow-r" size={12} /></button>
        </div>
      ) : tab === "phase1" ? (
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
            <button className="btn btn-tertiary"
                    onClick={() => pushToast("Key rotation is operator-only — run `gcloud secrets versions add dma-insights-bot-api-key --data-file=-` from Cloud Shell", "warn")}>
              <Icon name="refresh" size={13} /> Rotate API key
            </button>
            {/* ERROR HISTORY (admin UI): the 'Upload payload manually' button
                was unwired prior to 2026-05-24; operator reported 'button
                does not even work'. Wired here to a hidden file input that
                POSTs the JSON to /api/v1/ingest/assessment via
                window.DMA.admin.uploadAssessment. */}
            <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
              <Icon name="download" size={13} /> Upload payload manually
              <input type="file" accept="application/json,.json" style={{ display: "none" }}
                     onChange={async (e) => {
                       const file = e.target.files?.[0];
                       e.target.value = "";  // allow re-selecting the same file
                       if (!file || !window.DMA?.admin?.uploadAssessment) return;
                       const r = await window.DMA.admin.uploadAssessment(file);
                       if (r.ok) {
                         pushToast(`Payload accepted · run_id=${r.data?.run_id || "?"}`, "success");
                         executions.refetch();
                       } else {
                         pushToast(`Upload failed: ${r.error}`, "warn");
                       }
                     }} />
            </label>
          </div>
        </div>
      ) : (
        <CatalogUploadCard />
      )}

      {detail ? <AdminDetailDrawer title={detail.title} sub={detail.sub} payload={detail.data} onClose={() => setDetail(null)} /> : null}
      {logDrawer ? <JobLogDrawer execution={logDrawer} onClose={() => setLogDrawer(null)} /> : null}
    </PageShell>
  );
}

/* ── /admin/import/audit ─ Live audit with per-client drilldown
   State-transition contract:
     mounted              → fetch summary, files, by-entity in parallel
     tab=files            → flat file list with status filter chips
     tab=by_client        → entity rollup with click-to-drill
     entity_click         → AdminEntityDrilldownDrawer with runs + jobs
     retry_click          → POST /imports/files/:id:retry
     empty                → "No imports yet" empty state per filter
*/
function ImportAuditPage() {
  const { pushToast } = useApp();
  const [tab, setTab] = useState("files");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [drilldownEntity, setDrilldownEntity] = useState(null);

  const summary = useAdminResource(window.DMA.admin?.importAuditSummary);
  const audit = useAdminResource(window.DMA.admin?.listImportAudit);
  const byEntity = useAdminResource(window.DMA.admin?.importAuditByEntity);

  const s = summary.data || {};
  const allFiles = audit.data?.items || [];
  const filteredFiles = statusFilter === "ALL"
    ? allFiles
    : allFiles.filter(f => f.status === statusFilter);
  const entityRows = byEntity.data?.items || [];

  const handleRetry = async (file) => {
    if (!window.DMA.admin?.retryImportFile) return;
    const r = await window.DMA.admin.retryImportFile(file.id);
    if (r.ok) {
      pushToast(`${file.filename} retry queued (execution ${r.data.id.slice(0,8)})`, "success");
      audit.refetch();
    } else {
      pushToast(`Retry failed: ${r.error}`, "warn");
    }
  };

  return (
    <PageShell title="Import audit" crumbs={[{ label: "Admin", href: "/admin" }, { label: "Import audit" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · Phase 0</div>
          <h1>Drive import audit</h1>
          <div className="sub">Real data from /admin/import-audit/* · click a client row to see every run and rerun for that entity</div>
        </div>
      </div>

      <div className="g4" style={{ marginBottom: 16 }} data-source={summary.loading ? "loading" : "api"}>
        <div className="card-tile">
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Last crawl</div>
          <div style={{ fontSize: 14, marginTop: 4 }}>{s.last_crawl_at ? fmtDate(s.last_crawl_at) : "Never"}</div>
        </div>
        <div className="card-tile">
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Candidates processed</div>
          <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>{s.candidates_processed ?? 0}</div>
        </div>
        <div className="card-tile">
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Excluded</div>
          <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-below)", marginTop: 4 }}>{s.files_excluded ?? 0}</div>
        </div>
        <div className="card-tile">
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase" }}>Awaiting review</div>
          <div style={{ fontSize: 22, fontWeight: 200, color: "var(--z-org)", marginTop: 4 }}>{s.files_awaiting_review ?? 0}</div>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          <button className={tab === "files" ? "on" : ""} onClick={() => setTab("files")}>Files</button>
          <button className={tab === "by_client" ? "on" : ""} onClick={() => setTab("by_client")}>By client</button>
        </div>
        {tab === "files" ? (
          <>
            <span className="spacer" />
            <div className="toggle-row">
              <button className={statusFilter === "ALL" ? "on" : ""} onClick={() => setStatusFilter("ALL")}>All</button>
              <button className={statusFilter === "PENDING_REVIEW" ? "on" : ""} onClick={() => setStatusFilter("PENDING_REVIEW")}>Review</button>
              <button className={statusFilter === "SKIPPED" ? "on" : ""} onClick={() => setStatusFilter("SKIPPED")}>Excluded</button>
              <button className={statusFilter === "FAILED" ? "on" : ""} onClick={() => setStatusFilter("FAILED")}>Errored</button>
            </div>
          </>
        ) : null}
      </div>

      {tab === "files" ? (
        <div className="card flush" data-source={audit.loading ? "loading" : "api"}>
          {audit.loading ? <AdminSectionLoader label="Fetching /api/v1/admin/imports/audit…" /> :
           audit.error   ? <AdminSectionError error={audit.error} onRetry={audit.refetch} /> :
           filteredFiles.length === 0 ? <AdminSectionEmpty icon="evidence" title="No files match this filter" body="When the Drive crawler runs, files land in import_files and show up here." /> :
           (
             <table className="tbl">
               <thead><tr><th>Filename</th><th>Kind</th><th>Entity</th><th>Run</th><th>Status</th><th>Created</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
               <tbody>
                 {filteredFiles.map(f => (
                   <tr key={f.id} data-file-id={f.id} data-status={f.status}>
                     <td>
                       <div className="f-mono" style={{ fontSize: 11.5, fontWeight: 500 }}>{f.filename || f.file_name}</div>
                       {f.parser_warnings && Object.keys(f.parser_warnings).length > 0
                         ? <div style={{ fontSize: 10, color: "var(--z-org)" }}>⚠ {Object.keys(f.parser_warnings).length} parser warning(s)</div>
                         : null}
                     </td>
                     <td>{f.file_kind || "—"}</td>
                     <td className="f-mono" style={{ fontSize: 11 }}>{f.entity_display_id || "—"}</td>
                     <td className="f-mono" style={{ fontSize: 10 }}>{f.run_request_id || "—"}</td>
                     <td><span className={`b ${f.status === "PENDING_REVIEW" ? "b-org" : f.status === "FAILED" ? "b-below" : f.status === "OK" ? "b-above" : "b-muted"}`}>{f.status}</span></td>
                     <td style={{ fontSize: 11 }}>{f.created_at ? fmtDate(f.created_at) : "—"}</td>
                     <td style={{ textAlign: "right" }}>
                       <button className="btn btn-tertiary btn-sm" onClick={() => handleRetry(f)}>Retry parse</button>
                     </td>
                   </tr>
                 ))}
               </tbody>
             </table>
           )}
        </div>
      ) : (
        <div className="card flush" data-source={byEntity.loading ? "loading" : "api"}>
          <div className="card-head">
            <h3>By client · {byEntity.loading ? "loading…" : entityRows.length}</h3>
            <button className="btn btn-tertiary btn-sm" onClick={byEntity.refetch}><Icon name="refresh" size={11} /> Refresh</button>
          </div>
          {byEntity.loading ? <AdminSectionLoader label="Fetching /api/v1/admin/import-audit/by-entity…" /> :
           byEntity.error   ? <AdminSectionError error={byEntity.error} onRetry={byEntity.refetch} /> :
           entityRows.length === 0 ? <AdminSectionEmpty icon="users" title="No entities ingested yet" body="Once a DMA package is ingested via /ingest/package, the client lands here." /> :
           (
             <table className="tbl tbl-clickable">
               <thead><tr><th>Client</th><th>Latest run</th><th>Runs</th><th>Status</th><th>Dedup audit</th><th>Enrichments</th><th style={{ textAlign: "right" }}>Drill</th></tr></thead>
               <tbody>
                 {entityRows.map(e => (
                   <tr key={e.entity_id} data-entity-id={e.entity_id} data-entity-display-id={e.entity_display_id}
                       onClick={() => setDrilldownEntity(e)}>
                     <td>
                       <div style={{ fontWeight: 600, fontSize: 12.5 }}>{e.entity_name}</div>
                       <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.entity_display_id}</div>
                     </td>
                     <td style={{ fontSize: 11 }}>{e.latest_run_completed_at ? fmtDate(e.latest_run_completed_at) : "—"}</td>
                     <td>{e.runs_count}</td>
                     <td>{e.latest_status ? <span className={`b ${e.latest_status === "ACTIVE" ? "b-above" : "b-muted"}`}>{e.latest_status}</span> : "—"}</td>
                     <td>{e.dedup_audit_count}</td>
                     <td>{e.enrichment_count}</td>
                     <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm">Drill →</button></td>
                   </tr>
                 ))}
               </tbody>
             </table>
           )}
        </div>
      )}

      {drilldownEntity ? (
        <AdminEntityDrilldownDrawer entity={drilldownEntity} onClose={() => setDrilldownEntity(null)} />
      ) : null}
    </PageShell>
  );
}

/* ── Per-entity drilldown drawer (Defect 4) ──────────────────────
   Opens when the user clicks a client row on the By-client tab.
   Renders:
     - timeline of every run for the entity (with parent_request_id chain)
     - rerun history: every Cloud Run Job execution that touched this entity
     - empty-state when the entity has 0 runs (graceful per the contract)
*/
function AdminEntityDrilldownDrawer({ entity, onClose }) {
  const loader = useCallback(
    () => window.DMA.admin?.importAuditEntityDetail(entity.entity_display_id || entity.entity_id),
    [entity],
  );
  const { loading, error, data } = useAdminResource(loader);
  const runs = data?.runs || [];
  const jobs = data?.job_executions || [];
  return (
    <>
      <div className="drawer-mask" onClick={onClose} />
      <div className="drawer" data-entity-drilldown={entity.entity_display_id} data-source="api">
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="title">{entity.entity_name}</div>
            <div className="sub">{entity.entity_display_id} · {entity.runs_count} runs · {entity.dedup_audit_count} dedup, {entity.enrichment_count} enrichments</div>
          </div>
          <button className="icon-btn close" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">
          {loading ? <AdminSectionLoader label="Fetching /api/v1/admin/import-audit/entities/…" /> :
           error   ? <AdminSectionError error={error} /> :
           (
             <>
               <h4 style={{ fontSize: 12, marginBottom: 8 }}>Runs · {runs.length}</h4>
               {runs.length === 0 ? (
                 <AdminSectionEmpty icon="refresh" title="No runs for this entity" body="Once a DMA package is ingested for this entity, the run lands here." />
               ) : (
                 <table className="tbl" style={{ marginBottom: 16 }}>
                   <thead><tr><th>Request</th><th>Status</th><th>Completed</th><th>Parent</th><th>Evidence</th><th>Embeddings</th></tr></thead>
                   <tbody>
                     {runs.map(r => (
                       <tr key={r.run_id} data-run-id={r.run_id}>
                         <td className="f-mono" style={{ fontSize: 10 }}>{r.request_id}</td>
                         <td><span className={`b ${r.status === "ACTIVE" ? "b-above" : "b-muted"}`}>{r.status}</span></td>
                         <td style={{ fontSize: 11 }}>{r.completed_at ? fmtDate(r.completed_at) : "—"}</td>
                         <td className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.parent_request_id || "—"}</td>
                         <td>{r.evidence_count}</td>
                         <td>{r.embedding_count}</td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
               )}

               <h4 style={{ fontSize: 12, marginBottom: 8 }}>Rerun history · {jobs.length}</h4>
               {jobs.length === 0 ? (
                 <AdminSectionEmpty icon="refresh" title="No rerun jobs for this entity" body="Every Cloud Run Job execution scoped to this entity (drive_crawler, embedder, intelligence_recompute, peer_patterns) lands here." />
               ) : (
                 <table className="tbl">
                   <thead><tr><th>Job</th><th>Status</th><th>Started</th><th>Duration</th></tr></thead>
                   <tbody>
                     {jobs.map(j => (
                       <tr key={j.id} data-job-id={j.id}>
                         <td><span className="chip">{j.job_name}</span></td>
                         <td><span className={`b ${j.status === "succeeded" ? "b-above" : j.status === "failed" ? "b-below" : j.status === "running" ? "b-org" : "b-muted"}`}>{j.status.toUpperCase()}</span></td>
                         <td style={{ fontSize: 11 }}>{fmtDate(j.started_at)}</td>
                         <td style={{ fontSize: 11 }}>{j.duration_sec != null ? `${Math.round(j.duration_sec)}s` : "—"}</td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
               )}
             </>
           )}
        </div>
      </div>
    </>
  );
}

/* ── Catalog upload card (Promise 11) ─────────────────────────────
   State branches:
     idle       → "Upload next version" button + hidden <input type=file>
     selecting  → file picker open via ref.current.click()
     uploading  → POST /api/v1/admin/catalogue:upload via FormData
     success    → toast + Refresh of catalogue list
     failure    → toast warn + error reason
   No backend? executeJob/uploadCatalogue returns ok:false → toast warn. */
function CatalogUploadCard() {
  const { pushToast } = useApp();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [versions, setVersions] = useState({ items: [], current: null, loading: true });
  const [showChangelog, setShowChangelog] = useState(false);

  // Load catalog versions to display "Current: v7.0"
  useEffect(() => {
    let cancelled = false;
    if (!window.DMA?.admin?.listCatalogue) return;
    window.DMA.admin.listCatalogue().then(r => {
      if (cancelled) return;
      const items = r?.data?.items || r?.data?.versions || [];
      const active = items.find(v => v.status === "ACTIVE") || items[0];
      setVersions({ items, current: active, loading: false });
    });
    return () => { cancelled = true; };
  }, []);

  const onPick = () => fileRef.current?.click();
  const onChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!window.DMA?.admin?.uploadCatalogue) {
      pushToast("Backend loader missing — cannot upload catalogue", "warn");
      return;
    }
    setUploading(true);
    const r = await window.DMA.admin.uploadCatalogue(file);
    setUploading(false);
    e.target.value = "";  // allow re-picking the same file after error
    if (r.ok) {
      pushToast(`Catalogue uploaded: ${r.data?.version || "new version"}`, "success");
      // refetch versions
      const lr = await window.DMA.admin.listCatalogue();
      const items = lr?.data?.items || lr?.data?.versions || [];
      const active = items.find(v => v.status === "ACTIVE") || items[0];
      setVersions({ items, current: active, loading: false });
    } else {
      pushToast(`Upload failed: ${r.error}`, "warn");
    }
  };

  return (
    <div className="card" data-source="api" data-catalog-upload>
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="stack" size={16} />
        <div style={{ fontWeight: 600 }}>V7 capability catalog</div>
        <span className="spacer" />
        <span className="muted" style={{ fontSize: 11 }}>
          Current: {versions.current?.version || "v7.0"} · loaded by ccg_loader
        </span>
      </div>
      <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>
        Updating the catalog creates a new version. Existing runs retain their original catalog reference.
      </p>
      <div className="row" style={{ marginTop: 10 }}>
        <input ref={fileRef} type="file" accept=".zip,.xlsx,.json"
               data-catalog-file-input style={{ display: "none" }}
               onChange={onChange} />
        <button className="btn btn-tertiary" data-action="upload-catalogue"
                disabled={uploading} onClick={onPick}>
          {uploading
            ? <><span className="spinner" /> Uploading…</>
            : <><Icon name="download" size={13} /> Upload next version</>}
        </button>
        <button className="btn btn-tertiary" data-action="view-changelog"
                onClick={() => setShowChangelog(o => !o)}>
          View change log
        </button>
      </div>
      {showChangelog ? (
        <div style={{ marginTop: 12, padding: 10, background: "var(--z-lav)", borderRadius: 6 }}>
          {versions.loading ? <span className="muted" style={{ fontSize: 11 }}>Loading…</span>
            : versions.items.length === 0 ? <span className="muted" style={{ fontSize: 11 }}>No catalog versions yet.</span>
            : (
              <table className="tbl">
                <thead><tr><th>Version</th><th>Loaded</th><th>Subcaps</th><th>Status</th></tr></thead>
                <tbody>
                  {versions.items.map(v => (
                    <tr key={v.version || v.id}>
                      <td className="f-mono">{v.version || v.id}</td>
                      <td style={{ fontSize: 11 }}>{v.loaded_at ? fmtDate(v.loaded_at) : v.created_at ? fmtDate(v.created_at) : "—"}</td>
                      <td>{v.subcap_count ?? v.subcaps ?? "—"}</td>
                      <td><span className={`b ${v.status === "ACTIVE" ? "b-above" : "b-muted"}`}>{v.status || "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      ) : null}
    </div>
  );
}

Object.assign(window, {
  AlertsPage, ProspectingPage, AdminPage, ImportPage, ImportAuditPage,
  CatalogUploadCard,
  // Admin helpers exposed for potential reuse + easier debugging.
  useAdminResource, AdminSectionLoader, AdminSectionError, AdminSectionEmpty,
  UserRoleEditModal, AdminDetailDrawer,
  // Job-trigger surface (Defect 2)
  useJobTrigger, JobStatusLine, JobLogDrawer, AdminVertexBudgetMini,
  // Per-entity drilldown (Defect 4)
  AdminEntityDrilldownDrawer,
});
