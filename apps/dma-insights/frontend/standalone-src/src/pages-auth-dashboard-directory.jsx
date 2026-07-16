/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Login + Dashboard home + Entity directory
   Sections 19, 20, 21 of the UI/UX brief.
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /login (s19) ─────────────────────────────────────────────────── */
// Google Identity Services client ID — backend re-validates the id_token
// signature + hd claim, so this value is safe to ship in client code.
// Source-of-truth: `dma-insights-oauth-client-id` secret in GCP Secret
// Manager; updated copy lives in DEPLOYMENT.md §3.
const GOOGLE_CLIENT_ID = "306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com";

function LoginPage() {
  const { signIn: ctxSignIn } = useApp();
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | verifying | granting
  const [gisReady, setGisReady] = useState(false);
  const googleBtnRef = useRef(null);

  // Load the Google Identity Services SDK once.
  useEffect(() => {
    if (document.getElementById("gis-script")) {
      if (window.google?.accounts?.id) setGisReady(true);
      return;
    }
    const s = document.createElement("script");
    s.id = "gis-script";
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.defer = true;
    s.onload = () => setGisReady(!!window.google?.accounts?.id);
    s.onerror = () => setErr("Couldn't load Google sign-in. Check your network and retry.");
    document.head.appendChild(s);
  }, []);

  // Initialize the GIS client once SDK is ready + render the official
  // Google-branded button (replaces our custom button to satisfy
  // Google's brand guidelines + ensure popup flow).
  useEffect(() => {
    if (!gisReady || !window.google?.accounts?.id) return;
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleGoogleCredential,
      auto_select: false,
      hosted_domain: "zennify.com",   // soft hint; backend re-checks hd claim
      use_fedcm_for_prompt: true,
    });
    if (googleBtnRef.current) {
      window.google.accounts.id.renderButton(googleBtnRef.current, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: 360,
      });
    }
  }, [gisReady]);

  // Handle the credential returned by GIS — POST to the backend, which
  // verifies the JWT signature, enforces hd=zennify.com, applies the
  // ADMIN_EMAILS / ANALYST_EMAILS allow-list, and returns the canonical
  // user record. Strict mode: any non-2xx response surfaces the error
  // and refuses sign-in. No email/local fallback — Google is the only
  // path in.
  async function handleGoogleCredential(resp) {
    setLoading(true);
    setErr(null);
    setPhase("verifying");
    try {
      const r = await fetch("/api/v1/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        // Backend schema (GoogleAuthRequest) expects `id_token`.
        // GIS returns the JWT in `resp.credential`, so map here.
        body: JSON.stringify({ id_token: resp.credential }),
      });
      if (r.ok) {
        const body = await r.json();
        setPhase("granting");
        // Server is authoritative for role + can_act_as. Pass the
        // FULL response body so signIn() honours server role instead
        // of re-deriving it from the email via ADMIN_EMAILS sets.
        ctxSignIn(body);
        navigate("/");
        return;
      }
      // Always surface the exact backend `detail` so misconfig (e.g.
      // empty GOOGLE_OAUTH_CLIENT_ID env on the backend → audience
      // mismatch → 401) doesn't masquerade as a domain rejection.
      let detail = "";
      try {
        const body = await r.json();
        detail = body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : JSON.stringify(body);
      } catch (_) {
        try { detail = await r.text(); } catch (__) { detail = ""; }
      }
      setErr(`Sign-in failed (${r.status}). ${detail.slice(0, 300)}`);
      setLoading(false);
      setPhase("idle");
    } catch (e) {
      setErr(`Sign-in failed — couldn't reach the auth service. ${(e && e.message) || ""}`);
      setLoading(false);
      setPhase("idle");
    }
  }

  if (phase === "verifying" || phase === "granting") {
    return <LoadingScreen variant="auth" dark
      title={phase === "verifying" ? "Verifying with Google…" : "Setting up your workspace…"}
      body={phase === "verifying" ? "Checking your Zennify account and OAuth scopes." : "Loading your role, alerts, and recent runs."}
      detail={phase === "verifying" ? "Google OAuth · @zennify.com domain check" : "Hydrating session · 1 of 3 caches loaded"} />;
  }

  return (
    <div
      data-page="login"
      style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(0, 1.1fr)", background: "var(--z-bg)" }}
    >
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

        {/* Google-branded official button (popup mode). This is the ONLY
            way in — no email fallback, no quick-in shortcuts. The
            backend validates the JWT signature, enforces hd=zennify.com,
            and applies the ADMIN/ANALYST email allow-lists. */}
        <div ref={googleBtnRef} style={{ marginBottom: 12, minHeight: 44 }} />
        {!gisReady ? (
          <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 12 }}>
            Loading Google sign-in…
          </div>
        ) : null}
        <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 12 }}>
          Google OAuth · <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>@zennify.com</code> only · session expires after 8 hours
        </div>

        {err ? (
          <div className="co co-auth" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={14} />
            <div>
              <div className="co-title">Sign-in error</div>
              <div className="co-body">{err}</div>
            </div>
          </div>
        ) : null}

        <div className="row" style={{ marginTop: "auto", paddingTop: 56, fontSize: 11, color: "var(--z-muted)", justifyContent: "space-between" }}>
          <span>© 2026 Zennify · Confidential</span>
          <span>v0.1 · DMA Insights</span>
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
                { icon: "heatmap",  label: "4-level maturity heatmap",   sub: "Pillar → Category → Capability → Subcap · 851 subcaps per run (V7.0)" },
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
  const { role, openAlerts, audience, openNewRun, user } = useApp();
  const ent = DMA.ENTITIES;
  const active = ent.filter(e => e.in_progress);
  const recent = ent.filter(e => !e.in_progress).slice().sort((a, b) => new Date(b.assessment_date) - new Date(a.assessment_date));
  const stale = ent.filter(e => e.assessment_date && DMA.helpers.freshnessOf(e.assessment_date).tone !== "ok").slice(0, 3);
  const totalAlerts = DMA.ALERTS.filter(a => a.status === "OPEN").length;
  const totalInsights = DMA.INSIGHT_CARDS.length;

  // Avg maturity is the unweighted mean of `entity.overall` across all
  // entities that have a completed run (overall != null). The backend
  // computes overall as Σ(category_score × category_weight) per run +
  // averages categories per pillar; see WIRING_NEEDS.ENTITIES. Until
  // ≥1 entity has a stored `overall`, we show 0 + an "Uncalculated" tag
  // rather than fabricating a number.
  const scoredEntities = ent.filter(e => typeof e.overall === "number" && !isNaN(e.overall));
  const hasScored = scoredEntities.length > 0;
  const avgMaturity = hasScored
    ? scoredEntities.reduce((a, e) => a + e.overall, 0) / scoredEntities.length
    : 0;
  const greetingName = user?.name ? user.name.split(" ")[0] : null;   // first name only

  return (
    <PageShell title="Dashboard" crumbs={[{ label: "Home" }]}>
      <div className="page-head">
        <div>
          <div className="eyebrow">Command centre</div>
          <h1>Good morning{greetingName ? `, ${greetingName}` : ""}</h1>
          <div className="sub">{ent.length} entities · {totalAlerts} open alerts · {active.length} run{active.length === 1 ? "" : "s"} in progress</div>
        </div>
        <div className="actions">
          {role === "ADMIN" ? <button className="btn btn-tertiary" onClick={() => navigate("/admin")}><Icon name="refresh" size={13} /> Re-scan Drive</button> : null}
          <button className="btn btn-primary" onClick={openNewRun}><Icon name="plus" size={13} /> New run</button>
        </div>
      </div>

      {/* KPI strip — Avg maturity tagged "Uncalculated" until ≥1 run lands. */}
      <div className="g4" style={{ marginBottom: 14 }}>
        <KpiCard label="Active assessments" value={ent.filter(e => !e.in_progress).length} sub={ent.length === 0 ? "no runs yet" : "all subverticals"} icon="users"   accent="var(--z-teal)" />
        <KpiCard label="Open alerts"        value={totalAlerts}                              sub={totalAlerts === 0 ? "none open" : "thin-evidence"}    icon="bell"    accent="var(--z-org)"  />
        <KpiCard label="Insight cards"      value={totalInsights}                            sub={totalInsights === 0 ? "no insights yet" : "across all runs"} icon="insight" accent="var(--z-mid)" />
        <KpiCard label="Avg maturity"
                 value={hasScored ? avgMaturity.toFixed(1) : "0"}
                 sub={hasScored ? DMA.helpers.maturityLabel(avgMaturity) : "Uncalculated"}
                 icon="heatmap" accent="var(--z-dpur)"
                 help={hasScored
                   ? "Mean of every entity's overall score (Σ(category × weight) per run; see WIRING_NEEDS.ENTITIES)."
                   : "No scored runs yet — wire ENTITIES via GET /api/v1/entities and the mean will compute automatically."} />
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
          {recent.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "32px 20px" }}>
              <div style={{ width: 48, height: 48, margin: "0 auto 12px", borderRadius: 12, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon name="users" size={20} />
              </div>
              <h3 style={{ fontSize: 14, color: "var(--z-dark)", marginBottom: 6 }}>No assessments yet</h3>
              <p style={{ fontSize: 12, color: "var(--z-muted)", maxWidth: 380, margin: "0 auto 14px", lineHeight: 1.55 }}>
                Click <strong>Request a DMA</strong> to kick off a new assessment via the bot,
                or upload an existing <code style={{ fontSize: 11 }}>{`{Entity}_DMA_Complete_Package.zip`}</code> from Admin → Import.
              </p>
              <div className="row" style={{ justifyContent: "center", gap: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={openNewRun}>
                  <Icon name="plus" size={12} /> Request a DMA
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => navigate("/clients")}>
                  Browse clients <Icon name="arrow-r" size={12} />
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {role !== "AE" ? (
          <div className="col" style={{ gap: 14 }}>
            <div className="card">
              <div className="row" style={{ marginBottom: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 7, background: "rgba(254,151,50,.18)", color: "var(--z-org)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="bell" size={14} /></div>
                <strong style={{ fontSize: 13 }}>Needs attention</strong>
                <span className="b b-org" style={{ marginLeft: "auto" }}>{totalAlerts}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--z-body)", marginBottom: 10, lineHeight: 1.55 }}>Thin-evidence alerts across {new Set(DMA.ALERTS.filter(a => a.status === "OPEN").map(a => a.entity_id)).size} entities.</p>
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
                  <span className="spacer" />
                  <span className="b b-muted" title="Live data not yet wired to GET /api/v1/admin/health">not tracked</span>
                </div>
                <div style={{ display: "grid", gap: 8, fontSize: 11.5 }}>
                  <div className="row" title="Wired via GET /api/v1/admin (drive_crawler.last_run_at)">
                    <span className="muted">Drive crawl</span><span className="spacer" /><span>—</span>
                  </div>
                  <div className="row" title="Vertex AI spend is not yet tracked. Wire by aggregating audit_log rows (one per Gemini call × prompt_tokens × $/1k) — see WIRING_NEEDS.NOTIFICATIONS / GET /api/v1/admin/vertex-budget.">
                    <span className="muted">Vertex AI budget</span><span className="spacer" /><span>$0 / $100</span>
                  </div>
                  <div className="row"><span className="muted">Pending review</span><span className="spacer" /><span>{DMA.PENDING_REVIEW.length} entities</span></div>
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

function KpiCard({ label, value, sub, icon, accent, rounding, help }) {
  // Number-safe display: NaN, Infinity, undefined and null all render as 0.
  let display = value;
  if (typeof display === "number") {
    if (!isFinite(display) || isNaN(display)) display = 0;
    if (rounding) display = Math.round(display);
  } else if (display == null || display === "NaN") {
    display = 0;
  }
  return (
    <div className="card-tile" style={{ padding: 14, borderTop: `3px solid ${accent}` }} title={help || null}>
      <div className="row" style={{ marginBottom: 6 }}>
        <Icon name={icon} size={14} style={{ color: accent }} />
        <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{label}</span>
        {help ? <span className="spacer" /> : null}
        {help ? <Icon name="info" size={11} style={{ color: "var(--z-muted)" }} /> : null}
      </div>
      <div style={{ fontSize: 28, fontWeight: 200, color: "var(--z-dark)", letterSpacing: "-.02em", lineHeight: 1 }}>{display}</div>
      <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function DashboardEntityCard({ e }) {
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  const scored = typeof e.overall === "number" && !isNaN(e.overall);
  const tileHex = scored ? DMA.helpers.maturityHex(e.overall) : "var(--z-sep)";
  return (
    <div className="card-tile clickable" onClick={() => navigate(`/clients/${e.id}/overview`)} style={{ padding: 14 }}>
      <div className="row" style={{ marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: scored ? `linear-gradient(135deg, ${tileHex}, var(--z-mid))` : "var(--z-lav)", color: scored ? "#fff" : "var(--z-muted)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, flexShrink: 0 }}>
          {e.name.split(" ").map(n => n[0]).slice(0, 2).join("")}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }} className="txt-fit-1">{e.name}</div>
          <div style={{ fontSize: 10.5, color: "var(--z-muted)" }} className="txt-fit-1">{DMA.SUBVERTICAL_LABEL[e.subvertical]} · {e.hq}</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 22, fontWeight: 200, color: scored ? tileHex : "var(--z-muted)", lineHeight: 1 }}>
            {scored ? e.overall.toFixed(1) : "0"}
          </div>
          <div style={{ fontSize: 9, color: "var(--z-muted)" }}>{scored ? DMA.helpers.maturityLabel(e.overall).slice(0, 6) : "Uncalc."}</div>
        </div>
      </div>
      {/* Pillar mini-bars */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 4, marginBottom: 8 }}>
        {DMA.PILLARS.map(p => {
          const s = e.pillar_scores?.[p.id];
          return (
            <div key={p.id} title={`${p.id} · ${s?.toFixed(1) || "-"}`}>
              <div style={{ fontSize: 9, color: "var(--z-muted)", marginBottom: 2 }}>{p.id}</div>
              <div style={{ height: 5, background: "var(--z-sep)", borderRadius: 2.5, overflow: "hidden" }}>
                {s ? <div style={{ width: `${s / 5 * 100}%`, height: "100%", background: DMA.helpers.maturityHex(s) }} /> : null}
              </div>
            </div>
          );
        })}
      </div>
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
  const { openNewRun } = useApp();
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
      if (ql && !(e.name.toLowerCase().includes(ql) || (e.domain || "").includes(ql))) return false;
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
          <button className="btn btn-secondary"><Icon name="download" size={13} /> Export</button>
          <button className="btn btn-primary" onClick={openNewRun}><Icon name="plus" size={13} /> New run</button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="grow" style={{ position: "relative" }}>
          <Icon name="search" size={14} style={{ position: "absolute", top: 10, left: 10, color: "var(--z-muted)" }} />
          <input className="inp" style={{ paddingLeft: 32 }} placeholder="Search by name or domain…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="inp" style={{ maxWidth: 200 }} value={subvFilter} onChange={e => setSubvFilter(e.target.value)}>
          <option value="ALL">All subverticals</option>
          {Object.entries(DMA.SUBVERTICAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="inp" style={{ maxWidth: 200 }} value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
          <option value="ALL">All sources</option>
          <option value="PROJECT_API">Project API</option>
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

      {DMA.ENTITIES.length === 0 ? (
        <div className="empty">
          <div className="icon"><Icon name="users" size={22} /></div>
          <h3>No clients indexed yet</h3>
          <p>Run the historical backfill, ingest a DMA package, or request a new assessment from the bot — every completed run lands here automatically.</p>
          <div className="row" style={{ justifyContent: "center", gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" onClick={openNewRun}>
              <Icon name="plus" size={13} /> Request a DMA
            </button>
            <button className="btn btn-secondary" onClick={() => navigate("/admin/import")}>
              <Icon name="drive" size={13} /> Upload a package
            </button>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty">
          <div className="icon"><Icon name="search" size={22} /></div>
          <h3>No clients match your search</h3>
          <p>Try clearing filters or broadening the search term.</p>
          <button className="btn btn-tertiary btn-sm" style={{ marginTop: 8 }}
                  onClick={() => { setQ(""); setSubvFilter("ALL"); setSourceFilter("ALL"); }}>
            Clear filters
          </button>
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
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  return (
    <div className="card-tile clickable" onClick={() => navigate(`/clients/${e.id}/overview`)}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--z-dark)", marginBottom: 2 }}>{e.name}</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{DMA.SUBVERTICAL_LABEL[e.subvertical]} · {e.hq}</div>
        </div>
        {e.in_progress ? (
          <span className="b b-org" style={{ display: "inline-flex", gap: 4 }}>● IN PROGRESS</span>
        ) : (
          <div style={{ textAlign: "right" }}>
            {typeof e.overall === "number" && !isNaN(e.overall) ? (
              <>
                <div style={{ fontSize: 26, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1, letterSpacing: "-.02em" }}>{e.overall.toFixed(1)}</div>
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 2 }}>maturity</div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 26, fontWeight: 200, color: "var(--z-muted)", lineHeight: 1, letterSpacing: "-.02em" }}>0</div>
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 2 }}>uncalculated</div>
              </>
            )}
          </div>
        )}
      </div>
      {/* Pillar strip */}
      {e.pillar_scores ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 4, marginBottom: 10 }}>
          {DMA.PILLARS.map(p => {
            const s = e.pillar_scores[p.id];
            const w = (s / 5) * 100;
            return (
              <div key={p.id}>
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginBottom: 3 }}>{p.id}</div>
                <div style={{ height: 6, background: "var(--z-sep)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${w}%`, height: "100%", background: DMA.helpers.maturityHex(s) }} />
                </div>
                <div style={{ fontSize: 10, color: "var(--z-dark)", marginTop: 2 }}>{s.toFixed(1)}</div>
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
