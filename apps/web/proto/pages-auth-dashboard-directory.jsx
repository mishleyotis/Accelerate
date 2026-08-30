/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Login + Dashboard home + Entity directory
   Sections 19, 20, 21 of the UI/UX brief.
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /login (s19) ─────────────────────────────────────────────────── */
function LoginPage() {
  const { setRole, setAuthed } = useApp();
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | verifying | granting
  const [email, setEmail] = useState("");

  // Production: identity comes from the Google sign-in IAP performed at
  // the door — /api/signin reads the VERIFIED assertion and mints the
  // app session; nothing typed here is ever trusted. The email input
  // renders only when the server says dev-login is on (local compose).
  const devLogin = !!(window.DMA_LIVE && window.DMA_LIVE.dev_login);

  const signIn = async () => {
    const e = email.trim().toLowerCase();
    if (devLogin && !e) {
      setErr("Enter your @zennify.com email to sign in.");
      return;
    }
    setLoading(true);
    setErr(null);
    setPhase("verifying");
    try {
      const r = await fetch("/api/signin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(devLogin ? { email: e } : {}),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setLoading(false);
        setPhase("idle");
        setErr(body.error || "Sign-in failed. Please use your Zennify Google account.");
        return;
      }
      setPhase("granting");
      // Full reload: the server re-renders DMA_LIVE with the verified
      // identity and fresh directory data — the SPA never renders a
      // session it only half-knows about.
      window.location.assign("/");
    } catch (ex) {
      setLoading(false);
      setPhase("idle");
      setErr("Could not reach the sign-in service. Try again.");
    }
  };

  if (phase === "verifying" || phase === "granting") {
    return <LoadingScreen variant="auth" dark
      title={phase === "verifying" ? "Verifying with Google…" : "Setting up your workspace…"}
      body={phase === "verifying" ? "Checking your Zennify account and OAuth scopes." : "Loading your role, alerts, and recent runs."}
      detail={phase === "verifying" ? "Google OAuth · @zennify.com domain check" : "Hydrating session · 1 of 3 caches loaded"} />;
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(0, 1.1fr)", background: "var(--z-bg)" }}>
      {/* Left - sign-in card */}
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "40px 56px", maxWidth: 560, width: "100%", margin: "0 auto" }}>
        <div className="row" style={{ marginBottom: 36 }}>
          <ZennifyWordmark height={28} color="dark" />
        </div>

        <div className="eyebrow" style={{ marginBottom: 8 }}>DMA Insights</div>
        <h1 style={{ fontSize: 30, fontWeight: 600, color: "var(--z-dark)", letterSpacing: "-.02em", lineHeight: 1.15, marginBottom: 12 }}>
          The DMA, made navigable.
        </h1>
        <p style={{ fontSize: 14, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 28, maxWidth: 440 }}>
          Sign in to explore every assessment, drill into the evidence, and lead with the platform conversation your client needs to hear.
        </p>

        {devLogin ? (
          <React.Fragment>
            <label className="inp-label" htmlFor="signin-email" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--z-dark)", marginBottom: 6 }}>Work email (dev gate)</label>
            <input id="signin-email" className="inp" type="email" placeholder="you@zennify.com"
              value={email} onChange={e => setEmail(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") signIn(); }}
              style={{ width: "100%", marginBottom: 10 }} autoFocus />
          </React.Fragment>
        ) : null}
        <button className="btn btn-primary" disabled={loading} onClick={() => signIn()} style={{ width: "100%", padding: "12px", fontSize: 14, justifyContent: "center", marginBottom: 10, gap: 10 }}>
          {loading ? "Verifying…" : (
            <React.Fragment>
              <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true"><path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z"/><path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 40.4 44 35 44 24c0-1.3-.1-2.6-.4-3.9z"/></svg>
              Continue with Google
            </React.Fragment>
          )}
        </button>
        <div className="inp-help" style={{ marginBottom: 12 }}>Google sign-in · @zennify.com accounts only (enforced server-side) · session expires after 8 hours</div>

        {err ? (
          <div className="co co-auth" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={14} />
            <div>
              <div className="co-title">Domain restricted</div>
              <div className="co-body">{err}</div>
            </div>
          </div>
        ) : null}

        <div style={{ background: "var(--z-lav)", padding: 12, borderRadius: 8, fontSize: 11.5, color: "var(--z-body)", display: "flex", gap: 8, alignItems: "flex-start" }}>
          <Icon name="info" size={13} style={{ color: "var(--z-mid)", flexShrink: 0, marginTop: 1 }} />
          <span>Your role is detected automatically from your Zennify Google account. You can switch roles any time from the account menu.</span>
        </div>

        <div className="row" style={{ marginTop: "auto", paddingTop: 56, fontSize: 11, color: "var(--z-muted)", justifyContent: "space-between" }}>
          <span>© 2026 Zennify · Confidential</span>
          <span>Confidential</span>
        </div>
      </div>

      {/* Right - hero panel with Zennify illustration + product highlights */}
      <div style={{ position: "relative", background: "linear-gradient(135deg, var(--z-dark2), var(--z-dark) 60%, var(--z-navy))", overflow: "hidden" }}>
        <img src={assetUrl("illo_pavilion", "brand/illustrations/pavilion_zennify_branded.jpg")} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: .92 }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, rgba(28,74,77,.45), rgba(0,30,72,.55))" }} />

        <div style={{ position: "relative", zIndex: 2, height: "100%", display: "flex", flexDirection: "column", padding: "44px 56px", color: "#fff" }}>
          <div className="row" style={{ marginBottom: 28 }}>
            <BrandMark size={36} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>DMA Insights</div>
              <div style={{ fontSize: 10.5, color: "var(--z-mint-lt)" }}>by Zennify</div>
            </div>
          </div>

          <div style={{ flex: 1 }}></div>

          <div style={{ background: "rgba(0,30,72,.55)", backdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,.10)", borderRadius: 14, padding: "20px 22px", maxWidth: 460 }}>
            <div className="eyebrow" style={{ color: "var(--z-mint-lt)", marginBottom: 8 }}>What you'll find inside</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                { icon: "heatmap",  label: "4-level maturity heatmap",   sub: "Pillar → Category → Capability → Subcap · 708 cells per run" },
                { icon: "insight",  label: "Insight cards · WHAT/WHY/SO WHAT", sub: "Annotated · evidence-linked · platform-tagged" },
                { icon: "platform", label: "Platform opportunity matrix", sub: "Fit Score per platform · readiness prerequisites · conversation starters" },
                { icon: "timeline", label: "Why now signals + roadmap",   sub: "Triggers from the timeline · 3-phase transformation plan" },
              ].map(p => (
                <div key={p.icon} className="row">
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(39,187,175,.18)", color: "var(--z-mint)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Icon name={p.icon} size={15} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>{p.label}</div>
                    <div style={{ fontSize: 11, color: "var(--z-mint-lt)" }}>{p.sub}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── / Dashboard home (s20) ──────────────────────────────────────── */
function DashboardHome() {
  const { role, openAlerts, audience, openNewRun } = useApp();
  const ent = DMA.ENTITIES;
  const active = ent.filter(e => e.in_progress);
  const recent = ent.filter(e => !e.in_progress).slice().sort((a, b) => new Date(b.assessment_date) - new Date(a.assessment_date));
  const stale = ent.filter(e => e.assessment_date && DMA.helpers.freshnessOf(e.assessment_date).tone !== "ok").slice(0, 3);
  // Directory rows carry open_alerts per entity, counted by serving_directory
  // from the alerts queue. Fall back to the fixture's own list only when
  // there is no live directory at all (the prototype, run standalone).
  const live = typeof window !== "undefined" ? window.DMA_LIVE : null;
  const totalAlerts = live
    ? ent.reduce((a, e) => a + (e.open_alerts || 0), 0)
    : DMA.ALERTS.filter(a => a.status === "OPEN").length;
  const alertEntities = ent.filter(e => (e.open_alerts || 0) > 0).length;

  return (
    <PageShell title="Dashboard" crumbs={[{ label: "Home" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Command centre</div>
          <h1>{(h => h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening")(new Date().getHours())}, {sessionUser().first}</h1>
          <div className="sub">{ent.length} entities · {totalAlerts} open alerts · {active.length} run{active.length === 1 ? "" : "s"} in progress</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => navigate("/admin")}><Icon name="refresh" size={13} /> Re-scan Drive</button>
          <button className="btn btn-primary" onClick={openNewRun}><Icon name="plus" size={13} /> New run</button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="g4" style={{ marginBottom: 14 }}>
        <KpiCard label="Active assessments" value={ent.filter(e => !e.in_progress).length}        sub="all subverticals" icon="users"    accent="var(--z-teal)" />
        <KpiCard label="Open alerts"        value={totalAlerts}                                    sub="thin-evidence"   icon="bell"     accent="var(--z-org)"  />
        {/* Insight-card counts are per-run and live on the D4 page; the
            dashboard reports what the directory knows — promoted runs — and
            says so, rather than scaling a fixture by entity count. */}
        <KpiCard label="Promoted runs"
          value={ent.reduce((a, e) => a + (e.runs || []).length, 0)}
          sub="across all entities" icon="insight" accent="var(--z-mid)" />
        {/* Production divergence: computed or null, never NaN (invariant 9).
            An average over zero scored entities renders its empty state.

            Not an EnrichmentGap: this is a cross-directory aggregate on the
            internal command centre, not a payload field. Nothing in the
            connector's worklist fills it — a promoted run does — and the
            customer wording ("not established in this assessment") names an
            assessment this number is not scoped to. So: a plain honest word. */}
        {(() => {
          const scored = ent.filter(e => e.overall);
          const avg = scored.length ? scored.reduce((a, e) => a + e.overall, 0) / scored.length : null;
          return <KpiCard label="Avg maturity"
            value={avg == null ? "Not computed" : fx(avg, 1)}
            sub={avg == null ? "no promoted runs yet" : DMA.helpers.maturityLabel(avg)}
            icon="heatmap" accent="var(--z-dpur)" />;
        })()}
      </div>

      {/* Active runs */}
      {active.length > 0 ? (
        <div className="card flush" style={{ marginBottom: 14 }}>
          <div className="card-head">
            <div className="row">
              <Icon name="play" size={14} style={{ color: "var(--z-mid)" }} />
              <h3>Active runs</h3>
              <span className="b b-teal">SSE LIVE</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{active.length} in progress</span>
          </div>
          <div style={{ padding: 16 }}>
            {active.map(e => {
              const r = e.runs[0];
              return (
                <div key={e.id} style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 18, alignItems: "center", marginBottom: 8 }}>
                  <div>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <strong style={{ fontSize: 14 }}>{e.name}</strong>
                      <span className="b b-muted">{DMA.SUBVERTICAL_LABEL[e.subvertical]}</span>
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Batch {r.current_batch} / 6 · {r.status.replace(/_/g, " ").toLowerCase()}</span>
                    </div>
                    <div className="batch-row">
                      {["Setup","Evidence","Peers","Scoring","Analysis","Final"].map((b, i) => (
                        <div key={b} className={`batch-pill ${i + 1 < r.current_batch ? "done" : i + 1 === r.current_batch ? "active" : ""}`}>{i+1}</div>
                      ))}
                    </div>
                  </div>
                  <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/clients/${e.id}/overview`)}>Open <Icon name="arrow-r" size={11} /></button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Two-col: client cards + sidebar */}
      <div style={{ display: "grid", gridTemplateColumns: role === "AE" ? "1fr" : "1fr 320px", gap: 14, marginBottom: 14 }}>
        <div>
          <div className="row" style={{ marginBottom: 10 }}>
            <Icon name="users" size={15} />
            <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>Recent assessments</h3>
            <span className="spacer" />
            <a href="#/clients" style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>View all →</a>
          </div>
          <div className="g2">
            {recent.slice(0, 6).map(e => <DashboardEntityCard key={e.id} e={e} />)}
          </div>
        </div>

        {role !== "AE" ? (
          <div className="col" style={{ gap: 14 }}>
            <div className="card">
              <div className="row" style={{ marginBottom: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 7, background: "rgba(254,151,50,.18)", color: "var(--z-org)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="bell" size={14} /></div>
                <strong style={{ fontSize: 13 }}>Needs attention</strong>
                <span className="b b-org" style={{ marginLeft: "auto" }}>{totalAlerts}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 10, lineHeight: 1.55 }}>Thin-evidence alerts across {alertEntities} {alertEntities === 1 ? "entity" : "entities"}.</p>
              <button className="btn btn-secondary btn-sm" style={{ width: "100%", justifyContent: "center" }} onClick={() => navigate("/alerts")}>Review alerts <Icon name="arrow-r" size={11} /></button>
            </div>

            <div className="card">
              <div className="row" style={{ marginBottom: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 7, background: "rgba(194,80,8,.14)", color: "var(--z-below)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="warn" size={14} /></div>
                <strong style={{ fontSize: 13 }}>Stale entities</strong>
              </div>
              {stale.map(e => (
                <div key={e.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderTop: "1px solid var(--z-sep)" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600 }} className="txt-fit-1">{e.name}</div>
                    <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{relTime(e.assessment_date)}</div>
                  </div>
                  <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${e.id}/overview`)}>Rerun</button>
                </div>
              ))}
            </div>

            {role === "ADMIN" ? (
              <div className="card">
                <div className="row" style={{ marginBottom: 10 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--ph0-lt)", color: "var(--z-dpur)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="drive" size={14} /></div>
                  <strong style={{ fontSize: 13 }}>System health</strong>
                </div>
                {/* Production divergence: real rows only — a crawl time or
                    budget nothing measures is a default that looks like data.
                    The scheduled-scan row lights up when the Scheduler lands. */}
                <div style={{ display: "grid", gap: 8, fontSize: 11.5 }}>
                  {/* The package scan is a Cloud Scheduler trigger firing the
                      worker Job, and the admin console reads its real
                      executions. Asserting a schedule here without reading one
                      was a placeholder; point at the page that knows. */}
                  {window.DMA_LIVE ? (
                    <div className="row"><span className="muted">Package scan</span><span className="spacer" />
                      <span>{(live && (live.import_scans || []).length)
                        ? `last ${relTime(live.import_scans[0].started_at)}`
                        : "see import & jobs"}</span></div>
                  ) : (<>
                    <div className="row"><span className="muted">Drive crawl</span><span className="spacer" /><span>2 hr ago</span></div>
                    <div className="row"><span className="muted">Vertex AI budget</span><span className="spacer" /><span>$184 / $400</span></div>
                  </>)}
                  <div className="row"><span className="muted">Pending review</span><span className="spacer" />
                    <span>{(live ? (live.pending_review || []) : DMA.PENDING_REVIEW).length} entities</span></div>
                </div>
                <button className="btn btn-tertiary btn-sm" style={{ width: "100%", justifyContent: "center", marginTop: 10 }} onClick={() => navigate("/admin")}>Open admin <Icon name="arrow-r" size={11} /></button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </PageShell>
  );
}

function KpiCard({ label, value, sub, icon, accent, rounding }) {
  const display = rounding && typeof value === "number" ? Math.round(value) : value;
  return (
    <div className="card-tile" style={{ padding: 14, borderTop: `3px solid ${accent}` }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <Icon name={icon} size={14} style={{ color: accent }} />
        <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 200, color: "var(--z-dark)", letterSpacing: "-.02em", lineHeight: 1 }}>{display}</div>
      <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function DashboardEntityCard({ e }) {
  const { audience } = useApp();
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  const matHex = DMA.helpers.maturityHex(e.overall || 2.5);
  // Band word only where there is a score to band. maturityLabel(null) is
  // already null; the `|| 2.5` fallback printed "BUILDING" beneath an absent
  // score, which reads as a finding and would now contradict the gap above it.
  const matLabel = DMA.helpers.maturityLabel(e.overall);
  return (
    <div className="card-tile clickable" onClick={() => navigate(`/clients/${e.id}/overview`)} style={{ padding: 14, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: `linear-gradient(135deg, ${matHex}, var(--z-mid))`, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, flexShrink: 0 }}>
          {e.name.split(" ").map(n => n[0]).slice(0, 2).join("")}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.3 }} className="txt-fit-2" title={e.name}>{e.name}</div>
          <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.35 }} className="txt-fit-2" title={[DMA.SUBVERTICAL_LABEL[e.subvertical], e.hq].filter(Boolean).join(" · ")}>{[DMA.SUBVERTICAL_LABEL[e.subvertical], e.hq].filter(Boolean).join(" · ")}</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          {/* fx() RETURNS the em dash for a null score, and it returns it as a
              non-empty string — so the old `|| "-"` never fired and an entity
              whose promoted run states no composite rendered a bare dash here.
              `overall` is `num(scores.composite)` in the live adapter, so null
              is a real production value, not a fixture artefact. `compact` and
              a 10px slot: this is the corner of a directory card and the badge
              at 22px would break the row. */}
          {e.overall == null
            ? <div style={{ fontSize: 10, fontWeight: 600 }}><EnrichmentGap what="Overall maturity" audience={audience} compact /></div>
            : <div style={{ fontSize: 22, fontWeight: 200, color: matHex, lineHeight: 1 }}>{fx(e.overall, 1)}</div>}
          <div style={{ fontSize: 8.5, color: matHex, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em", marginTop: 3, whiteSpace: "nowrap" }}>{matLabel}</div>
        </div>
      </div>
      {/* Pillar mini-bars */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 10 }}>
        {DMA.PILLARS.map(p => {
          const s = e.pillar_scores?.[p.id];
          // A title attribute takes a STRING, so no EnrichmentGap in it — an
          // element would stringify to "[object Object]". Same defect as the
          // score above though: fx returned the em dash and `|| "-"` never
          // fired, so a pillar with no score tipped "P1 · —".
          return (
            <div key={p.id} title={`${p.id} · ${s == null ? "not stated" : fx(s, 1)}`} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 9, color: "var(--z-muted)", fontWeight: 600 }}>{p.id}</span>
                {/* Was an EN dash, so the em-dash grep never saw it — but it is
                    the same absent pillar score that EntityCard's strip renders
                    as a gap, and two cards disagreeing on one value is its own
                    defect. `== null` not truthiness: a stated 0 is a score. */}
                <span style={{ fontSize: 9, color: "var(--z-body)", fontWeight: 600 }}>
                  {s == null ? <EnrichmentGap what={`${p.id} score`} audience={audience} compact /> : fx(s, 1)}</span>
              </div>
              <div style={{ height: 5, background: "var(--z-sep)", borderRadius: 2.5, overflow: "hidden" }}>
                {s ? <div style={{ width: `${s / 5 * 100}%`, height: "100%", background: DMA.helpers.maturityHex(s) }} /> : null}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ flex: 1 }} />
      <div className="row" style={{ paddingTop: 8, borderTop: "1px solid var(--z-sep)" }}>
        <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
          <span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}</span>
          {e.open_alerts > 0 ? <span className="b b-org"><Icon name="bell" size={9} /> {e.open_alerts}</span> : null}
          <FreshnessDot date={e.assessment_date} />
        </div>
        {top ? (
          <span className="spacer" style={{ fontSize: 11, color: "var(--z-mid)", textAlign: "right" }}>
            {DMA.getPlatform(top[0])?.short} <strong>{top[1]}</strong>
          </span>
        ) : null}
      </div>
    </div>
  );
}

/* ── /clients Entity directory (s21) ─────────────────────────────── */
function EntityDirectoryPage() {
  const { openNewRun, pushToast } = useApp();
  const [q, setQ] = useState("");
  const [subvFilter, setSubvFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("date");
  const [view, setView] = useState("grid"); // grid | table

  const filtered = useMemo(() => {
    const ql = q.toLowerCase();
    let xs = DMA.ENTITIES.filter(e => {
      if (subvFilter !== "ALL" && e.subvertical !== subvFilter) return false;
      if (sourceFilter !== "ALL" && e.data_source !== sourceFilter) return false;
      if (!entityMatches(e, ql)) return false;
      return true;
    });
    if (sortBy === "date") xs.sort((a, b) => (new Date(b.assessment_date || 0) - new Date(a.assessment_date || 0)));
    if (sortBy === "oss") xs.sort((a, b) => ((b.oss && Math.max(...Object.values(b.oss))) || 0) - ((a.oss && Math.max(...Object.values(a.oss))) || 0));
    if (sortBy === "alerts") xs.sort((a, b) => b.open_alerts - a.open_alerts);
    return xs;
  }, [q, subvFilter, sourceFilter, sortBy]);

  return (
    <PageShell title="Clients" crumbs={[{ label: "Clients" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Entity directory</div>
          <h1>Clients</h1>
          <div className="sub">{filtered.length} of {DMA.ENTITIES.length} entities · sorted by {sortBy}</div>
        </div>
        <div className="actions">
          <div className="toggle-row">
            <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")}><Icon name="grid" size={13} /></button>
            <button className={view === "table" ? "on" : ""} onClick={() => setView("table")}><Icon name="menu" size={13} /></button>
          </div>
          <button className="btn btn-secondary" onClick={() => pushToast(`Exporting ${filtered.length} clients as CSV…`, "success")}><Icon name="download" size={13} /> Export</button>
          <button className="btn btn-primary" onClick={openNewRun}><Icon name="plus" size={13} /> New run</button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="grow" style={{ position: "relative" }}>
          <Icon name="search" size={14} style={{ position: "absolute", top: 10, left: 10, color: "var(--z-muted)" }} />
          <input className="inp" style={{ paddingLeft: 32 }} placeholder="Search by name, ID or domain…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="inp" style={{ maxWidth: 200 }} value={subvFilter} onChange={e => setSubvFilter(e.target.value)}>
          <option value="ALL">All subverticals</option>
          {Object.entries(DMA.SUBVERTICAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="inp" style={{ maxWidth: 200 }} value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
          <option value="ALL">All sources</option>
          <option value="PROJECT_API">Project interface</option>
          <option value="DRIVE_PARSE">Drive parse</option>
        </select>
        <select className="inp" style={{ maxWidth: 200 }} value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="date">Sort: Run date</option>
          <option value="oss">Sort: Top OSS</option>
          <option value="alerts">Sort: Open alerts</option>
        </select>
        {(q || subvFilter !== "ALL" || sourceFilter !== "ALL") ? (
          <button className="btn btn-tertiary btn-sm" onClick={() => { setQ(""); setSubvFilter("ALL"); setSourceFilter("ALL"); }}>Clear filters</button>
        ) : null}
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <div className="icon"><Icon name="search" size={22} /></div>
          <h3>No clients match your search</h3>
          <p>Try clearing filters or broaden the search term.</p>
        </div>
      ) : view === "grid" ? (
        <div className="g3">
          {filtered.map(e => <EntityCard key={e.id} e={e} />)}
        </div>
      ) : (
        <div className="card flush">
          <table className="tbl tbl-clickable">
            <thead><tr><th>Entity</th><th>Subvertical</th><th>Date</th><th>Source</th><th>Open alerts</th><th>Top OSS</th><th style={{ textAlign: "right" }}>Score</th></tr></thead>
            <tbody>
              {filtered.map(e => (
                <tr key={e.id} onClick={() => navigate(`/clients/${e.id}/overview`)}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--z-dark)" }}>{e.name}</div>
                    <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.domain || e.assessment_id}</div>
                  </td>
                  <td>{DMA.SUBVERTICAL_LABEL[e.subvertical]}</td>
                  <td>{fmtDate(e.assessment_date)}</td>
                  <td><span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}</span></td>
                  <td>{e.open_alerts > 0 ? <span className="b b-org">{e.open_alerts}</span> : <span className="muted">0</span>}</td>
                  <td>{e.oss ? (() => { const top = Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0]; return <><span style={{ fontWeight: 600 }}>{top[1]}</span> <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{DMA.getPlatform(top[0])?.short}</span></>; })() : <span className="muted">-</span>}</td>
                  <td style={{ textAlign: "right" }}><MaturityChip score={e.overall} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  );
}

function EntityCard({ e }) {
  const { audience } = useApp();
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  return (
    <div className="card-tile clickable" onClick={() => navigate(`/clients/${e.id}/overview`)}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--z-dark)", marginBottom: 2 }}>{e.name}</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{[DMA.SUBVERTICAL_LABEL[e.subvertical], e.hq].filter(Boolean).join(" · ")}</div>
        </div>
        {e.in_progress ? (
          <span className="b b-org" style={{ display: "inline-flex", gap: 4 }}>● IN PROGRESS</span>
        ) : (
          <div style={{ textAlign: "right" }}>
            {/* Same dead `|| "-"` as the dashboard card: fx returns the em dash
                as a non-empty string, so a completed entity with no composite
                rendered a bare dash. Small slot, `compact` — the badge at 26px
                would break the card head. */}
            {e.overall == null
              ? <div style={{ fontSize: 10, fontWeight: 600 }}><EnrichmentGap what="Overall maturity" audience={audience} compact /></div>
              : <div style={{ fontSize: 26, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1, letterSpacing: "-.02em" }}>{fx(e.overall, 1)}</div>}
            <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 2 }}>maturity</div>
          </div>
        )}
      </div>
      {/* Pillar strip */}
      {e.pillar_scores ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 4, marginBottom: 10 }}>
          {DMA.PILLARS.map(p => {
            const s = e.pillar_scores[p.id];
            const w = (s / 5) * 100;
            // pillarScoresOf KEEPS null entries (unlike pillarPeerMediansOf,
            // which drops them), so `pillar_scores` can be present with a null
            // score inside it. This `fx(s, 1)` was unguarded and printed the em
            // dash outright, and `width: "NaN%"` is rejected by CSS, leaving
            // the fill at its auto width — a FULL bar beside the dash. Guard
            // both, the way the dashboard card already does.
            return (
              <div key={p.id}>
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginBottom: 3 }}>{p.id}</div>
                <div style={{ height: 6, background: "var(--z-sep)", borderRadius: 3, overflow: "hidden" }}>
                  {s == null ? null : <div style={{ width: `${w}%`, height: "100%", background: DMA.helpers.maturityHex(s) }} />}
                </div>
                <div style={{ fontSize: 10, color: "var(--z-dark)", marginTop: 2 }}>
                  {s == null ? <EnrichmentGap what={`${p.id} score`} audience={audience} compact /> : fx(s, 1)}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ marginBottom: 10 }}>
          <div className="prog"><div className="prog-fill" style={{ width: `${(e.runs[0].current_batch / 6) * 100}%`, background: "var(--z-org)" }} /></div>
          <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>Batch {e.runs[0].current_batch} of 6</div>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 10, borderTop: "1px solid var(--z-sep)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}</span>
          {e.assessment_date ? <FreshnessDot date={e.assessment_date} /> : null}
          {e.open_alerts > 0 ? <span className="b b-org"><Icon name="bell" size={9} /> {e.open_alerts}</span> : null}
        </div>
        {top ? (
          <div style={{ fontSize: 11, color: "var(--z-mid)" }}>
            Top OSS · {DMA.getPlatform(top[0])?.short} <strong style={{ marginLeft: 4 }}>{top[1]}</strong>
          </div>
        ) : null}
      </div>
    </div>
  );
}

Object.assign(window, { LoginPage, DashboardHome, EntityDirectoryPage });
