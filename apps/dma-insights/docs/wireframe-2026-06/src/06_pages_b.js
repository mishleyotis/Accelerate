/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · D1 Entity Intelligence Hub (refined)
   ═══════════════════════════════════════════════════════════════════════ */

function ClientOverview({ entity, run }) {
  const { audience, openEvidence, openInsight, role, setIpSurface, setIpContext, setIpOpen, tweaks, pushToast } = useApp();
  const [findingOpen, setFindingOpen] = useState(null);
  const [scqaExp, setScqaExp] = useState(false);
  const layout = tweaks.overview_layout || "balanced";

  useEffect(() => {
    setIpSurface("why_now");
    setIpContext({ entity });
  }, [entity?.id]);

  if (entity.in_progress) {
    return <InProgressBanner run={run} entity={entity} />;
  }

  const findings = [
    {
      id: "F-01", title: "Data fragmentation is the root constraint, not under-investment",
      theme: "Data foundation", platforms: ["SF", "DB"], evidence: ["E-047", "E-141"],
      what: "Three production cores run in parallel with no canonical customer profile — a customer with a mortgage, a deposit account, and a card appears as three unrelated records.",
      why: "Each core was retained through prior acquisitions rather than consolidated. The organization has invested heavily in analytics on top, but every downstream initiative inherits the fragmentation underneath.",
      so_what: "Every channel or CX investment made before the substrate is fixed compounds the problem. The data foundation is the highest-leverage conversation on the board right now.",
      magnitude: "Blocks 34 downstream subcaps",
    },
    {
      id: "F-02", title: "Loan origination is where automation lands first",
      theme: "Workflow", platforms: ["nCino"], evidence: ["E-236"],
      what: "Loan origination is still substantially manual — hand-offs between underwriting, credit, and closing are tracked in email and spreadsheets.",
      why: "The nCino migration already underway includes a Workflow Engine that isn't yet switched on for origination. The capability is bought but unused.",
      so_what: "This is the fastest credible win: a 5–7 month cycle compression using a tool they already own, with no new procurement. It builds the proof point for the larger data conversation.",
      magnitude: "5–7 month cycle compression",
    },
    {
      id: "F-03", title: "The team generates insight faster than it acts on it",
      theme: "Decisioning", platforms: ["DB", "TBL"], evidence: ["E-250", "E-283"],
      what: "Tableau adoption is strong and broad, but insight rarely converts into an automated action or a next-best-action in the channel.",
      why: "The reporting layer matured ahead of the activation layer. Analysts produce dashboards; there's no decisioning fabric to operationalize what they surface.",
      so_what: "The appetite for data is already proven — so lead with activation (Data Cloud + Agentforce), not more BI. The muscle exists; it needs a destination.",
      magnitude: "Readiness signal, not a gap",
    },
    {
      id: "F-04", title: "Mobile is the weakest customer-facing channel",
      theme: "Channels", platforms: ["TW", "SF"], evidence: ["E-271"],
      what: "App-store sentiment sits meaningfully below regional-bank peers; customers cite friction in onboarding and servicing, not missing features.",
      why: "The mobile experience is built on the fragmented data layer — personalization and straight-through servicing can't work when the customer isn't a single record.",
      so_what: "Mobile is a symptom of F-01, not an independent project. Twilio Engage + Service Cloud close most of the experience gap once the profile is unified — sequence it after the substrate.",
      magnitude: "Trails peer sentiment by ~0.8★",
    },
    {
      id: "F-05", title: "Two C-suite hires open a 6–9 month decision window",
      theme: "Timing", platforms: [], evidence: ["E-203"],
      what: "A new CTO (ex-Wells Fargo, Apr 2026) and CDO (ex-JPM, May 2026) are both in their first two quarters.",
      why: "New executives set platform direction early and lock commitments after. Combined with five open Data Cloud Architect roles, the organization is visibly preparing for a CDP decision it hasn't made yet.",
      so_what: "This is the relationship window of the cycle. Engage now to shape the criteria before a point-solution is chosen — the technical case (F-01) and the political timing align exactly once.",
      magnitude: "Window closes at nCino go-live",
    },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 18 }}>
        <div>
          <div className="eyebrow">Entity intelligence</div>
          <h1 style={{ marginBottom: 4 }}>{entity.name}</h1>
          <div className="sub">{DMA.SUBVERTICAL_LABEL[entity.subvertical]} · {entity.hq} · {fmtAssets(entity.assets)} assets · Assessment {fmtDate(entity.assessment_date)}</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Customer-safe scorecard generated · ${entity.name}`, "success")}><Icon name="download" size={13} /> Scorecard</button>
          <button className="btn btn-tertiary" onClick={() => pushToast("Rerun queued — first batch in ~3 min", "success")}><Icon name="refresh" size={13} /> Request rerun</button>
          <button className="btn btn-secondary" onClick={() => { setIpSurface("why_now"); setIpContext({ entity }); setIpOpen(true); }}><Icon name="sparkle" size={13} /> Meeting prep</button>
        </div>
      </div>

      {/* Snapshot strip - 3 columns: score ring + pillar bars + firmographics */}
      <div className="card" style={{ marginBottom: 18, padding: "20px 22px" }}>
        <div style={{ display: "grid", gridTemplateColumns: layout === "ring-left" ? "140px 1fr 280px" : "1fr 280px", gap: 28, alignItems: "stretch" }}>
          {layout === "ring-left" ? <ScoreRing score={entity.overall} /> : null}
          <div style={{ minWidth: 0 }}>
            {layout !== "ring-left" ? (
              <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
                <ScoreRing score={entity.overall} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span className={`b ${DMA.helpers.maturityClass(entity.overall)}`}>{DMA.helpers.maturityLabel(entity.overall).toUpperCase()}</span>
                    <span className="b b-ph1">EVIDENCE · {run.evidence_mode}</span>
                    <FreshnessDot date={entity.assessment_date} withLabel />
                    {entity.data_source === "DRIVE_PARSE" ? <span className="b b-ph0">DRIVE PARSE</span> : null}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5 }}>
                    Trails {DMA.SUBVERTICAL_LABEL[entity.subvertical].toLowerCase()} peer median by {((entity.pillar_scores.P1 + entity.pillar_scores.P2 + entity.pillar_scores.P3 + entity.pillar_scores.P4) / 4 - entity.overall - 0.3).toFixed(1)} points. Gap concentrated in P4 Data foundation.
                  </div>
                </div>
              </div>
            ) : null}
            <div>
              {DMA.PILLARS.map(p => {
                const s = entity.pillar_scores[p.id];
                const peer = s + 0.3;
                const w = (s / 5) * 100;
                const peerL = (peer / 5) * 100;
                const delta = s - peer;
                return (
                  <div className="pbar" key={p.id} onClick={() => navigate(`/clients/${entity.id}/heatmap`, { pillar: p.id, run: run.id })} style={{ cursor: "pointer" }}>
                    <div className="pbar-name">{p.id} · {p.short}</div>
                    <div className="pbar-track">
                      <div className="pbar-fill" style={{ width: `${w}%`, background: DMA.helpers.maturityHex(s) }} />
                      <div className="pbar-peer" style={{ left: `calc(${peerL}% - 1px)` }} title={`Peer ${peer.toFixed(1)}`} />
                    </div>
                    <div className="pbar-score">{s.toFixed(1)}</div>
                    <div className="pbar-delta" style={{ color: delta < 0 ? "var(--z-below)" : "var(--z-mid)" }}>{delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}</div>
                  </div>
                );
              })}
              <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)", display: "flex", gap: 14, paddingLeft: 122 }}>
                <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 12, height: 4, background: "var(--z-teal)", borderRadius: 2 }} /> Entity</span>
                <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 2, height: 10, background: "var(--z-dpur)" }} /> Peer median</span>
              </div>
            </div>
          </div>
          <div style={{ background: "var(--z-lav)", borderRadius: 12, padding: 16 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Firmographics</div>
            <Row k="Assets"     v={fmtAssets(entity.assets)} />
            <Row k="Employees"  v={entity.employees?.toLocaleString() || "-"} />
            <Row k="Branches"   v={entity.branches?.toString() || "-"} />
            <Row k="CAGR"       v={entity.cagr ? `${fmtPct(entity.cagr)} · ${entity.trend}` : "-"} />
            <Row k="Regulator"  v={entity.regulator} />
            <Row k="Footprint"  v={entity.footprint?.join(" · ") || "-"} />
          </div>
        </div>
      </div>

      {/* Why now */}
      {audience !== "customer" ? <WhyNowStrip entity={entity} openEvidence={openEvidence} /> : null}

      {/* SCQA */}
      <SCQACard entity={entity} expanded={scqaExp} onToggle={() => setScqaExp(o => !o)} openEvidence={openEvidence} />

      {/* Opportunity Surface - per platform */}
      <OpportunitySurfaceStrip entity={entity} run={run} />

      {/* Two-column: Top findings + Leadership panel */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16, marginBottom: 18 }}>
        <TopFindingsCard findings={findings} openFinding={findingOpen} setOpenFinding={setFindingOpen} openEvidence={openEvidence} />
        <LeadershipPanel audience={audience} />
      </div>

      {/* Evidence-driven analytics — sourced from real DMA deliverable files (see SOURCES.md) */}
      <div className="section-label" style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "4px 0 12px" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", textTransform: "uppercase", letterSpacing: ".06em" }}>Evidence &amp; benchmarks</span>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>extracted from scoring workbook · evidence index · peer set</span>
      </div>
      <div className="cards-grid-3" style={{ marginBottom: 16 }}>
        <FinancialTrajectoryCard entity={entity} />
        <CoverageByPillarCard entity={entity} />
        <EvidenceTierCard entity={entity} />
      </div>
      <div className="cards-grid-2" style={{ marginBottom: 18 }}>
        <CeilingEstimateCard entity={entity} audience={audience} />
        <SentimentCard entity={entity} audience={audience} />
      </div>

      {/* Thought leadership panel - internal-only */}
      {audience !== "customer" ? <ThoughtLeadershipPanel /> : null}
    </div>
  );
}

/* ── Score ring ─────────────────────────────────────────────────── */
function ScoreRing({ score, size = 110 }) {
  if (score == null) return null;
  const r = size * 0.34, c = 2 * Math.PI * r, pct = (score / 5);
  return (
    <div className="score-ring" style={{ width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} className="ring-bg" strokeWidth="6" />
        <circle cx={size/2} cy={size/2} r={r} className="ring-fg" stroke={DMA.helpers.maturityHex(score)} strokeWidth="6" strokeDasharray={c} strokeDashoffset={c * (1 - pct)} strokeLinecap="round" />
      </svg>
      <div style={{ position: "absolute", textAlign: "center", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
        <div className="num" style={{ color: DMA.helpers.maturityHex(score), fontSize: size * 0.32, fontWeight: 300, lineHeight: 1 }}>{score.toFixed(1)}</div>
      </div>
    </div>
  );
}

/* ── Why-now strip ──────────────────────────────────────────────── */
function WhyNowStrip({ entity, openEvidence }) {
  const signals = [
    { tag: "MIGRATION",  icon: "refresh",  body: "nCino core migration in flight. Target completion Q2 2026 - integration decisions are still open.", ev: ["E-047"] },
    { tag: "LEADERSHIP", icon: "users",    body: "New CTO from Wells Fargo (April 2026) and new CDO (May 2026). Two policy seats open.", ev: ["E-203"] },
    { tag: "HIRING",     icon: "doc",      body: "5 Data Cloud Architect openings posted Q1 2026 - platform decision precedes posting.", ev: ["E-112"] },
    { tag: "REGULATORY", icon: "shield",   body: "AML consent order remediation closes Q4 2026. Compliance posture stable.", ev: ["E-218"] },
  ];
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--ph0-lt)", color: "var(--ph0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="sparkle" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>Why now signals</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>2–4 triggers · &lt;24 months · template-fill from timeline + issue register</div>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/context`)}>View timeline <Icon name="arrow-r" size={11} /></button>
      </div>
      <div className="g4">
        {signals.map((s, i) => (
          <div key={i} className="card-tile" style={{ background: "var(--ph0-lt)", borderColor: "var(--ph0-bd)", padding: 14 }}>
            <div className="row" style={{ marginBottom: 6 }}>
              <Icon name={s.icon} size={13} style={{ color: "var(--ph0)" }} />
              <span className="b b-purple" style={{ background: "rgba(115,91,161,.18)" }}>{s.tag}</span>
            </div>
            <div style={{ fontSize: 12, color: "#3B0764", lineHeight: 1.55, marginBottom: 8 }}>{s.body}</div>
            <div>
              {s.ev.map(e => <button key={e} className="chip purple" style={{ marginRight: 4 }} onClick={() => openEvidence(e)}>{e}</button>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── SCQA card ──────────────────────────────────────────────────── */
function SCQACard({ entity, expanded, onToggle, openEvidence }) {
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 12 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="doc" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Executive narrative</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>SCQA · Assessment Report · stored verbatim</div>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={onToggle}>{expanded ? "Collapse ↑" : "Read full ↓"}</button>
      </div>
      <div style={{ fontSize: 14, color: "var(--z-dark)", lineHeight: 1.7, maxWidth: 880 }}>
        <span style={{ fontWeight: 600 }}>{entity.name}</span> is a mid-tier {DMA.SUBVERTICAL_LABEL[entity.subvertical].toLowerCase()} mid-way through a multi-year digital transformation. Current overall maturity ({entity.overall.toFixed(1)} / 5) trails the peer median by 0.4, with the gap concentrated in P4 Data Foundation. Two recent C-suite hires open a 6-9 month integration window.{" "}
        {expanded ? (
          <>The institution has invested visibly in front-end channels (Tableau Cloud, Marketing Cloud roles, mobile redesign) but lacks the data substrate to operate any of these as a coherent customer-experience system. Without intervention, fragmentation deepens as nCino lands on top of FIS Profile core, and a future re-platform becomes harder. The strategic question is whether to invest now in a unified customer-data layer ahead of the nCino go-live, or continue to layer point solutions and accept the operating cost. Recommendation: lead the next 9 months with Salesforce Data Cloud + Databricks as the substrate <button className="chip" onClick={() => openEvidence("E-047")}>E-047</button> <button className="chip" onClick={() => openEvidence("E-089")}>E-089</button>.</>
        ) : null}
      </div>
    </div>
  );
}

/* ── Opportunity Surface - platform cards ───────────────────────── */
function OpportunitySurfaceStrip({ entity, run }) {
  const sorted = Object.entries(entity.oss).sort((a, b) => b[1] - a[1]);
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="platform" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Opportunity Surface · per platform</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Composite fit score 0–100 · Σ(priority × gap) for ABSENT, high-confidence subcaps</div>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/platform`, { run: run.id })}>Open matrix <Icon name="arrow-r" size={11} /></button>
      </div>
      <div className="g5">
        {sorted.map(([pid, score]) => {
          const p = DMA.getPlatform(pid);
          return (
            <div key={pid} className="card-tile clickable" onClick={() => navigate(`/clients/${entity.id}/platform`, { platform: pid, run: run.id })}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>{p.features.split(" · ").slice(0, 2).join(" · ")}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1 }}>{score}</div>
                  <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)" }}>fit score</div>
                </div>
              </div>
              <div className="prog" style={{ height: 5 }}>
                <div className="prog-fill" style={{ width: `${score}%`, background: score >= 60 ? "var(--z-teal)" : score >= 35 ? "var(--m-bld)" : "var(--m-act)" }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Top findings ───────────────────────────────────────────────── */
function TopFindingsCard({ findings, openFinding, setOpenFinding, openEvidence }) {
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Top findings</h3>
        <span className="b b-muted">{findings.length}</span>
      </div>
      <div>
        {findings.map(f => {
          const isOpen = openFinding === f.id;
          return (
            <div key={f.id} style={{ padding: "12px 16px", borderTop: "1px solid var(--z-sep)", transition: "background 120ms" }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }} onClick={() => setOpenFinding(o => o === f.id ? null : f.id)}
                onMouseEnter={e => e.currentTarget.parentElement.style.background = "var(--z-lav)"}
                onMouseLeave={e => e.currentTarget.parentElement.style.background = ""}>
                <span className="chip" style={{ marginTop: 1 }}>{f.id}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.35 }}>{f.title}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, color: "var(--z-mid)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em" }}>{f.theme}</span>
                    {f.magnitude ? <><span style={{ color: "var(--z-sep)" }}>·</span><span style={{ fontSize: 11, color: "var(--z-body)" }}>{f.magnitude}</span></> : null}
                  </div>
                </div>
                {f.platforms.map(p => <span key={p} className="b b-teal" style={{ marginTop: 1 }}>{DMA.getPlatform(p)?.short}</span>)}
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={14} style={{ color: "var(--z-muted)", marginTop: 3, flexShrink: 0 }} />
              </div>
              {isOpen ? (
                <div style={{ marginTop: 10, padding: 14, background: "var(--z-bg)", borderRadius: 8 }}>
                  {[
                    { k: "What", v: f.what, c: "var(--z-dark)" },
                    { k: "Why", v: f.why, c: "var(--z-body)" },
                  ].map(row => (
                    <div key={row.k} style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 3 }}>{row.k}</div>
                      <div style={{ fontSize: 12.5, color: row.c, lineHeight: 1.6 }}>{row.v}</div>
                    </div>
                  ))}
                  <div style={{ background: "rgba(39,187,175,.1)", borderLeft: "3px solid var(--z-teal)", borderRadius: "0 6px 6px 0", padding: "9px 12px", marginBottom: f.evidence.length ? 12 : 0 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-teal)", textTransform: "uppercase", marginBottom: 3 }}>So what</div>
                    <div style={{ fontSize: 12.5, color: "var(--z-dark)", lineHeight: 1.6, fontWeight: 500 }}>{f.so_what}</div>
                  </div>
                  {f.evidence.length > 0 ? (
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>Evidence · click to view</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {f.evidence.map(eid => {
                          const e = DMA.getEvidence(eid);
                          if (!e) return null;
                          return (
                            <button key={eid} onClick={ev => { ev.stopPropagation(); openEvidence(eid); }} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 6, cursor: "pointer", textAlign: "left", transition: "all 120ms" }}
                              onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--z-teal)"; e.currentTarget.style.transform = "translateX(2px)"; }}
                              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--z-sep)"; e.currentTarget.style.transform = ""; }}>
                              <span className={`tier-chip tier-${e.tier}`}>{eid}</span>
                              <span style={{ fontSize: 11.5, color: "var(--z-dark)", fontWeight: 500, flex: 1, minWidth: 0 }} className="txt-fit-1">{e.title}</span>
                              <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.recency}</span>
                              <Icon name="arrow-r" size={11} style={{ color: "var(--z-mid)" }} />
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Leadership panel + Clay enrichment ─────────────────────────── */
function LeadershipPanel({ audience }) {
  const [enriched, setEnriched] = useState({}); // id → "loading" | "done"
  const [enrichingAll, setEnrichingAll] = useState(false);
  const enrich = (id) => {
    setEnriched(e => ({ ...e, [id]: "loading" }));
    setTimeout(() => setEnriched(e => ({ ...e, [id]: "done" })), 900);
  };
  const enrichAll = () => {
    setEnrichingAll(true);
    DMA.LEADERSHIP.forEach((ex, i) => setTimeout(() => {
      if (ex.gap_flag) return;
      enrich(ex.id);
      if (i === DMA.LEADERSHIP.length - 1) setTimeout(() => setEnrichingAll(false), 1000);
    }, i * 240));
  };
  const anyEnriched = Object.values(enriched).some(v => v === "done");

  return (
    <div className="card flush">
      <div className="card-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="users" size={15} /> Leadership panel
        </h3>
        <button className="btn btn-secondary btn-sm" onClick={enrichAll} disabled={enrichingAll}>
          {enrichingAll ? <><span className="skel" style={{ width: 10, height: 10, borderRadius: 5 }} /> Enriching…</> : <><Icon name="sparkle" size={11} /> Enrich all via Clay</>}
        </button>
      </div>
      <div style={{ padding: "8px 16px 14px" }}>
        {DMA.LEADERSHIP.map(ex => {
          const state = enriched[ex.id]; // undefined | "loading" | "done"
          const hasClay = ex.clay && !ex.gap_flag;
          const isEnriched = state === "done" && hasClay;
          return (
            <div key={ex.id} style={{ display: "flex", gap: 10, padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
              <div style={{ width: 36, height: 36, borderRadius: 18, background: ex.gap_flag ? "var(--z-sep)" : "linear-gradient(135deg, var(--z-teal), var(--z-mid))", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
                {ex.gap_flag ? "?" : ex.name.split(" ").map(n => n[0]).join("").slice(0, 2)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  {ex.gap_flag ? (
                    <span style={{ fontWeight: 600, fontSize: 13 }}>-</span>
                  ) : isEnriched && ex.clay?.linkedin ? (
                    <a href={`https://${ex.clay.linkedin}`} target="_blank" rel="noreferrer" style={{ fontWeight: 600, fontSize: 13, color: "var(--z-mid)", textDecoration: "none" }} onClick={e => e.stopPropagation()}>{ex.name}</a>
                  ) : (
                    <span style={{ fontWeight: 600, fontSize: 13, color: "var(--z-dark)" }}>{ex.name}</span>
                  )}
                  <span style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>{ex.title}</span>
                  {ex.gap_flag ? <span className="b b-below">GAP</span> :
                   ex.recent_hire ? <span className="b b-org">NEW · {ex.tenure_months} mo</span> :
                   <span style={{ fontSize: 10, color: "var(--z-muted)" }}>· {Math.round(ex.tenure_months / 12)} yr</span>}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 4, lineHeight: 1.5 }}>{ex.background}</div>

                {/* Enrichment state */}
                {hasClay && audience !== "customer" ? (
                  <div style={{ marginTop: 8, padding: "8px 10px", background: isEnriched ? "var(--z-ice)" : state === "loading" ? "var(--z-lav)" : "var(--z-bg)", border: `1px solid ${isEnriched ? "rgba(39,187,175,.35)" : "var(--z-sep)"}`, borderRadius: 6 }}>
                    {!state ? (
                      <div className="row" style={{ fontSize: 11 }}>
                        <Icon name="lock" size={11} style={{ color: "var(--z-muted)" }} />
                        <span style={{ color: "var(--z-muted)" }}>Email · LinkedIn hidden until enriched</span>
                        <span className="spacer" />
                        <button className="btn btn-tertiary btn-sm" style={{ padding: "3px 8px" }} onClick={() => enrich(ex.id)}>
                          <Icon name="sparkle" size={10} /> Enrich via Clay
                        </button>
                      </div>
                    ) : state === "loading" ? (
                      <div className="row" style={{ fontSize: 11, color: "var(--z-dpur)" }}>
                        <span className="skel" style={{ width: 12, height: 12, borderRadius: 6 }} />
                        <span>Querying Clay enrichment…</span>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <div className="row" style={{ fontSize: 11, color: "var(--z-mid)" }}>
                          <Icon name="check" size={11} />
                          <strong style={{ color: "var(--z-mid)" }}>Enriched</strong>
                          <span className="spacer" />
                          <span style={{ fontSize: 10, color: "var(--z-muted)" }}>via Clay · just now</span>
                        </div>
                        <a href={`mailto:${ex.clay.email}`} style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} onClick={e => e.stopPropagation()}>
                          <Icon name="envelope" size={11} /> {ex.clay.email}
                        </a>
                        <a href={`https://${ex.clay.linkedin}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} onClick={e => e.stopPropagation()}>
                          <Icon name="linkedin" size={11} /> {ex.clay.linkedin}
                        </a>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ padding: "10px 16px", background: "var(--z-lav)", fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", gap: 6 }}>
        <Icon name="info" size={11} />
        <span>Critical roles flagged: <strong style={{ color: "var(--z-below)" }}>CISO absent</strong> from evidence</span>
        <span className="spacer" />
        {anyEnriched ? <span style={{ color: "var(--z-mid)", fontWeight: 600 }}>✓ {Object.values(enriched).filter(v => v === "done").length} of {DMA.LEADERSHIP.filter(x => !x.gap_flag).length} enriched</span> : null}
      </div>
    </div>
  );
}

/* ── Thought leadership ─────────────────────────────────────────── */
function ThoughtLeadershipPanel() {
  return (
    <div className="card flush" style={{ marginBottom: 18 }}>
      <div className="card-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="lightbulb" size={15} /> Thought leadership signal
        </h3>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>From executives - recent 6 months</span>
      </div>
      <div style={{ padding: 16 }}>
        <div className="g3">
          {DMA.THOUGHT_LEADERSHIP.map(tl => (
            <div key={tl.id} className="card-tile" style={{ padding: 14 }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <span className="b b-purple">{tl.type.toUpperCase()}</span>
                <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{fmtDate(tl.date)}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4, marginBottom: 6 }}>{tl.title}</div>
              <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic" }}>"{tl.excerpt}"</div>
              <div className="sep" style={{ margin: "8px 0" }} />
              <div className="row" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                <span>{tl.author}</span>
                <span className="spacer" />
                <a href={`https://${tl.url}`} target="_blank" rel="noreferrer" style={{ color: "var(--z-mid)", display: "inline-flex", alignItems: "center", gap: 3 }}>Open <Icon name="external" size={10} /></a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11.5, gap: 8 }}>
      <span style={{ color: "var(--z-muted)" }}>{k}</span>
      <span style={{ color: "var(--z-dark)", fontWeight: 500, textAlign: "right" }}>{v}</span>
    </div>
  );
}

function InProgressBanner({ run, entity }) {
  return (
    <div>
      <div className="card" style={{ background: "var(--ph1-lt)", border: "1px solid var(--ph1-bd)" }}>
        <div className="row" style={{ marginBottom: 12 }}>
          <Icon name="info" size={16} style={{ color: "var(--ph1)" }} />
          <div style={{ fontSize: 14, fontWeight: 600, color: "#1E3A8A" }}>Assessment in progress · Batch {run.current_batch} of 6</div>
          <span className="spacer" />
          <span className="b b-ph1">SSE LIVE</span>
        </div>
        <p style={{ fontSize: 12, color: "#1E3A8A", marginBottom: 12, lineHeight: 1.55 }}>{entity.name} is currently being researched. Subcap scoring begins at Batch 4. Insight cards appear after Batch 5.</p>
        <div className="batch-row" style={{ marginBottom: 16 }}>
          {["Setup","Evidence","Peers","Scoring","Analysis","Final"].map((b, i) => (
            <div key={b} className={`batch-pill ${i + 1 < run.current_batch ? "done" : i + 1 === run.current_batch ? "active" : ""}`}>{i+1} {b}</div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Per-tab unlocks: D3 Heatmap unlocks at Batch 4 · D2 Insights at Batch 5 · D5 Context at Batch 6</div>
      </div>
    </div>
  );
}

/* ── D2 Insight card surface ─────────────────────────────────────── */
function ClientInsights({ entity, run }) {
  const { openInsight, openEvidence, audience, pushToast } = useApp();
  const [flag, setFlag] = useState("ALL");
  const [pillar, setPillar] = useState("ALL");
  const [conf, setConf] = useState("ALL");

  const list = useMemo(() => DMA.INSIGHT_CARDS.filter(c => {
    if (flag !== "ALL" && c.flag !== flag) return false;
    if (pillar !== "ALL" && c.pillar !== pillar) return false;
    if (conf !== "ALL" && c.confidence !== conf) return false;
    return true;
  }).sort((a, b) => {
    const order = { CRITICAL: 0, OPPORTUNITY: 1, MONITOR: 2 };
    return (order[a.flag] - order[b.flag]) || a.id.localeCompare(b.id);
  }), [flag, pillar, conf]);

  const counts = { CRITICAL: 0, OPPORTUNITY: 0, MONITOR: 0 };
  DMA.INSIGHT_CARDS.forEach(c => counts[c.flag]++);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Insight cards</div>
          <h1>{DMA.INSIGHT_CARDS.length} insight cards</h1>
          <div className="sub">
            <span className="b b-below" style={{ marginRight: 6 }}>{counts.CRITICAL} CRITICAL</span>
            <span className="b b-org" style={{ marginRight: 6 }}>{counts.OPPORTUNITY} OPPORTUNITY</span>
            <span className="b b-teal">{counts.MONITOR} MONITOR</span>
          </div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${list.length} insight cards as PDF…`, "success")}><Icon name="download" size={13} /> Export PDF</button>
          <button className="btn btn-secondary" onClick={() => pushToast("Add a note from any insight card — click a card to start", "success")}><Icon name="plus" size={13} /> Add note</button>
        </div>
      </div>

      <div className="filter-bar">
        <select className="inp" style={{ maxWidth: 160 }} value={pillar} onChange={e => setPillar(e.target.value)}>
          <option value="ALL">All pillars</option>
          {DMA.PILLARS.map(p => <option key={p.id} value={p.id}>{p.id} · {p.short}</option>)}
        </select>
        <select className="inp" style={{ maxWidth: 160 }} value={flag} onChange={e => setFlag(e.target.value)}>
          <option value="ALL">All flags</option>
          <option>CRITICAL</option><option>OPPORTUNITY</option><option>MONITOR</option>
        </select>
        <select className="inp" style={{ maxWidth: 180 }} value={conf} onChange={e => setConf(e.target.value)}>
          <option value="ALL">All confidence</option>
          <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
        </select>
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{list.length} matching</span>
      </div>

      <div className="g2" style={{ marginBottom: 18 }}>
        {list.map(c => (
          <div key={c.id} className={`ic ${c.flag.toLowerCase()}`} onClick={() => openInsight(c.id)}>
            <div className="ic-head">
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className="ic-id">{c.id}</span>
                <span className="b b-purple">{c.pillar}</span>
                <span className={`b ${c.flag === "CRITICAL" ? "b-below" : c.flag === "OPPORTUNITY" ? "b-org" : "b-teal"}`}>{c.flag}</span>
              </div>
              {c.annotation ? <span className="b b-above" title="Annotated"><Icon name="edit" size={9} /> NOTE</span> : null}
            </div>
            <div className="ic-title">{c.title}</div>
            <div className="ic-body">{c.what.slice(0, 180)}{c.what.length > 180 ? "…" : ""}</div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
              {c.evidence.slice(0, 4).map(eid => {
                const e = DMA.getEvidence(eid);
                if (!e) return null;
                return <span key={eid} className={`tier-chip tier-${e.tier}`} title={e.title}>{eid}</span>;
              })}
              {c.evidence.length > 4 ? <span className="chip muted">+{c.evidence.length - 4}</span> : null}
            </div>
            <div className="ic-foot">
              <span style={{ fontSize: 10, color: "var(--z-muted)", marginRight: "auto" }}>
                {c.evidence.length} evidence · {c.affects.length} caps {c.rec ? `· ${c.rec}` : ""}
              </span>
              {c.platforms.map(p => <span key={p} className="b b-teal">{DMA.getPlatform(p)?.short}</span>)}
            </div>
          </div>
        ))}
      </div>

      {/* Technology landscape sub-view */}
      <div className="card flush" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <h3>Technology landscape</h3>
          <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/techstack`, { run: run.id })}>Open full stack <Icon name="arrow-r" size={11} /></button>
        </div>
        <div className="card-body">
          <div className="g4">
            {[
              { label: "Confirmed",   count: DMA.TECH_STACK.filter(t => t.status === "CONFIRMED").length, tone: "b-teal",   sub: "T1–T3 evidence",   desc: "Active deployments validated via Explorium and primary sources." },
              { label: "Inferred",    count: DMA.TECH_STACK.filter(t => t.status === "INFERRED").length,  tone: "b-purple", sub: "Job + press signals", desc: "Strong circumstantial signal - not yet confirmed." },
              { label: "Claimed",     count: 7,                                                            tone: "b-org",    sub: "T4–T5 marketing",  desc: "Marketing pages reference platforms not yet confirmed." },
              { label: "Gaps",        count: DMA.TECH_STACK.filter(t => t.status === "ABSENT").length,    tone: "b-below",  sub: "ABSENT confirmed", desc: "Data Cloud · Databricks · Mosaic AI · Twilio Engage." },
            ].map((q, i) => (
              <div key={i} className="card-tile">
                <div className="row" style={{ marginBottom: 8 }}>
                  <span className={`b ${q.tone}`}>{q.label}</span>
                  <span className="spacer" />
                  <span style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", letterSpacing: "-.02em", lineHeight: 1 }}>{q.count}</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{q.sub}</div>
                <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 6, lineHeight: 1.5 }}>{q.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ClientOverview, ClientInsights, ScoreRing });
