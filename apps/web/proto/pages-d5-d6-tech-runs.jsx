/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client pages - D5 Context, D6 Health, Tech stack, Runs
   ═══════════════════════════════════════════════════════════════════════ */

/* ── D5 Context & timeline ───────────────────────────────────────── */
function ClientContext({ entity, run }) {
  const { audience, openEvidence } = useApp();
  const [yearRange, setYearRange] = useState([2023, 2026]);
  const [signalFilter, setSignalFilter] = useState("ALL");
  const [hoverEvent, setHoverEvent] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [issueOpen, setIssueOpen] = useState(null);
  const [hoveredYear, setHoveredYear] = useState(null);
  const [acqOpen, setAcqOpen] = useState(null);
  const [sentOpen, setSentOpen] = useState(null);

  if (audience === "customer") {
    return (
      <div className="empty">
        <div className="icon"><Icon name="lock" size={20} /></div>
        <h3>Context &amp; timeline is internal-only</h3>
        <p>This dashboard contains internal team-preparation data. Switch back to Internal mode to view.</p>
      </div>
    );
  }

  const allEvents = DMA.TIMELINE_EVENTS;
  const issues = DMA.ISSUES;

  // Filter timeline events by year + signal
  const events = allEvents.filter(e => {
    const y = parseInt(e.date.slice(0, 4));
    if (y < yearRange[0] || y > yearRange[1]) return false;
    if (signalFilter !== "ALL" && e.signal !== signalFilter) return false;
    return true;
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Context &amp; timeline</div>
          <h1>Historical intelligence</h1>
          <div className="sub">Internal-only · {events.length} of {allEvents.length} events · {issues.length} issues · 5-year financials</div>
        </div>
        <div className="actions">
          <span className="b b-org" style={{ alignSelf: "center" }}><Icon name="lock" size={10} /> INTERNAL ONLY</span>
        </div>
      </div>

      {/* Timeline */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ marginBottom: 14 }}>
          <Icon name="timeline" size={16} />
          <div style={{ fontWeight: 600, fontSize: 13 }}>Digital evolution timeline</div>
          <span className="spacer" />
          <div className="toggle-row">
            <button className={signalFilter === "ALL" ? "on" : ""} onClick={() => setSignalFilter("ALL")}>All</button>
            <button className={signalFilter === "positive" ? "on" : ""} onClick={() => setSignalFilter("positive")} style={{ color: signalFilter === "positive" ? "var(--z-mid)" : "var(--z-muted)" }}>Positive</button>
            <button className={signalFilter === "neutral" ? "on" : ""} onClick={() => setSignalFilter("neutral")}>Neutral</button>
            <button className={signalFilter === "negative" ? "on" : ""} onClick={() => setSignalFilter("negative")} style={{ color: signalFilter === "negative" ? "var(--z-below)" : "var(--z-muted)" }}>Negative</button>
          </div>
        </div>

        {/* Range slider */}
        <div style={{ background: "var(--z-lav)", padding: "12px 16px", borderRadius: 8, marginBottom: 14 }}>
          <div className="row" style={{ marginBottom: 8, fontSize: 11, color: "var(--z-muted)" }}>
            <Icon name="calendar" size={12} />
            <span>Time range</span>
            <span className="spacer" />
            <strong style={{ color: "var(--z-dark)" }}>{yearRange[0]} – {yearRange[1]}</strong>
          </div>
          <RangeSlider min={2022} max={2026} value={yearRange} onChange={setYearRange} />
        </div>

        <InteractiveTimeline events={events} setHoverEvent={setHoverEvent} setSelectedEvent={setSelectedEvent} selectedEvent={selectedEvent} hoverEvent={hoverEvent} />

        {selectedEvent !== null && events[selectedEvent] ? (
          <EventDetail event={events[selectedEvent]} onClose={() => setSelectedEvent(null)} openEvidence={openEvidence} />
        ) : null}
      </div>

      {/* Issue register Gantt */}
      <div className="card flush" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <h3>Issue register · Gantt</h3>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{issues.filter(i => i.status === "OPEN").length} OPEN · {issues.filter(i => i.status === "RESOLVED").length} RESOLVED · click any bar for detail</span>
        </div>
        <div className="card-body">
          <InteractiveGantt issues={issues} issueOpen={issueOpen} setIssueOpen={setIssueOpen} />
          {issueOpen ? <IssueDetail issue={issues.find(i => i.id === issueOpen)} entity={entity} onClose={() => setIssueOpen(null)} openEvidence={openEvidence} /> : null}
        </div>
      </div>

      {/* Financial trajectory + Regulatory */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14, marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="money" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Financial trajectory</div>
            <span className="spacer" />
            <span className="b b-above">{entity.trend}</span>
          </div>
          <FinChartInteractive entity={entity} hoveredYear={hoveredYear} setHoveredYear={setHoveredYear} />
        </div>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="shield" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Regulatory standing</div>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.65 }}>
            <Row k="Primary regulator" v={entity.regulator} />
            <Row k="License type" v={entity.license} />
            <Row k="Jurisdictions" v={entity.footprint?.join(" · ") || "-"} />
            <div className="sep" />
            <div className="co co-org" style={{ cursor: "pointer" }} onClick={() => setIssueOpen("IS-014")}>
              <Icon name="warn" size={14} />
              <div style={{ flex: 1 }}>
                <div className="co-title">Open enforcement · IS-014</div>
                <div className="co-body">{issues[0].desc} · click to view caps</div>
              </div>
              <Icon name="arrow-r" size={12} />
            </div>
            <button className="btn btn-tertiary btn-sm" style={{ marginTop: 10 }} onClick={() => openEvidence("E-218")}>View evidence <Icon name="arrow-r" size={12} /></button>
          </div>
        </div>
      </div>

      {/* Sentiment + acquisitions */}
      <div className="g2">
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="users" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Sentiment overview</div>
            <span className="spacer" />
            <span style={{ fontSize: 10, color: "var(--z-muted)" }}>Click any card for source</span>
          </div>
          <SentimentGridInteractive sentOpen={sentOpen} setSentOpen={setSentOpen} openEvidence={openEvidence} />
        </div>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="stack" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Acquisition history</div>
          </div>
          {[
            { id: "ACQ-01", date: "2024-08", target: "Hudson Valley CU branches",  status: "Integrating", impl: "P2C1 channel fragmentation", details: "32 branches · ~$420M in deposits · integration tracking to Q3 2026 · expected to reduce P2C1 score temporarily during cutover.", evidence: [] },
            { id: "ACQ-02", date: "2022-03", target: "Cazenovia Credit",             status: "Complete",    impl: "-",                                       details: "Single-branch agricultural lender · fully integrated into FCE technology stack by Q4 2023.", evidence: [] },
          ].map((a, i) => (
            <div key={a.id} style={{ padding: "10px 0", borderBottom: i === 0 ? "1px solid var(--z-sep)" : "none", cursor: "pointer" }} onClick={() => setAcqOpen(acqOpen === a.id ? null : a.id)}>
              <div className="row">
                <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.date}</span>
                <div style={{ flex: 1, fontWeight: 500, fontSize: 12.5 }}>{a.target}</div>
                <span className="b b-muted">{a.status}</span>
                <Icon name={acqOpen === a.id ? "chevron-u" : "chevron-d"} size={12} style={{ color: "var(--z-muted)" }} />
              </div>
              {a.impl !== "-" ? <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>{a.impl}</div> : null}
              {acqOpen === a.id ? <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--z-lav)", borderRadius: 6, fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>{a.details}</div> : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Range slider ───────────────────────────────────────────────── */
function RangeSlider({ min, max, value, onChange }) {
  const [v1, v2] = value;
  return (
    <div style={{ position: "relative", height: 26, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 4, background: "var(--z-sep)", borderRadius: 2 }} />
      <div style={{ position: "absolute", left: `${(v1 - min) / (max - min) * 100}%`, right: `${100 - (v2 - min) / (max - min) * 100}%`, height: 4, background: "var(--z-teal)", borderRadius: 2 }} />
      <input type="range" min={min} max={max} value={v1} onChange={e => onChange([Math.min(parseInt(e.target.value), v2), v2])} style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }} />
      <input type="range" min={min} max={max} value={v2} onChange={e => onChange([v1, Math.max(parseInt(e.target.value), v1)])} style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }} />
      {/* Knobs */}
      <div style={{ position: "absolute", left: `calc(${(v1 - min) / (max - min) * 100}% - 8px)`, width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
      <div style={{ position: "absolute", left: `calc(${(v2 - min) / (max - min) * 100}% - 8px)`, width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
      {/* Tick marks */}
      <div style={{ position: "absolute", bottom: -16, left: 0, right: 0, display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--z-muted)" }}>
        {Array.from({ length: max - min + 1 }).map((_, i) => <span key={i}>{min + i}</span>)}
      </div>
    </div>
  );
}

function InteractiveTimeline({ events, setHoverEvent, setSelectedEvent, selectedEvent, hoverEvent }) {
  if (events.length === 0) {
    return <div className="empty" style={{ padding: 30 }}><div className="icon"><Icon name="calendar" size={20} /></div><h3>No events in range</h3><p>Expand the time range or change the signal filter.</p></div>;
  }
  const minDate = new Date(events[0].date + "-01");
  const maxDate = new Date(events[events.length - 1].date + "-01");
  const span = Math.max(1, maxDate - minDate);
  const TONE = { positive: "var(--z-mid)", negative: "var(--z-below)", neutral: "var(--z-purple)" };

  return (
    <div style={{ position: "relative", padding: "20px 8px 50px" }}>
      <div style={{ position: "relative", height: 2, background: "var(--z-sep)", margin: "30px 16px" }}>
        {events.map((e, i) => {
          const pct = ((new Date(e.date + "-01") - minDate) / span) * 100;
          const active = selectedEvent === i || hoverEvent === i;
          return (
            <button key={e.id}
              style={{ position: "absolute", left: `${pct}%`, top: active ? -10 : -7, width: active ? 22 : 16, height: active ? 22 : 16, borderRadius: 11, background: TONE[e.signal], transform: "translateX(-50%)", border: "2px solid #fff", cursor: "pointer", boxShadow: active ? "0 0 0 4px " + TONE[e.signal] + "40" : "var(--sh-sm)", transition: "all 160ms var(--ease)", padding: 0 }}
              onClick={() => setSelectedEvent(i === selectedEvent ? null : i)}
              onMouseEnter={() => setHoverEvent(i)}
              onMouseLeave={() => setHoverEvent(null)}
            />
          );
        })}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${events.length}, 1fr)`, gap: 6, fontSize: 9.5, color: "var(--z-muted)", padding: "0 8px" }}>
        {events.map((e, i) => (
          <div key={e.id} style={{ textAlign: "center", lineHeight: 1.4 }}>
            <div className="f-mono" style={{ color: hoverEvent === i || selectedEvent === i ? TONE[e.signal] : "var(--z-muted)" }}>{e.date}</div>
            <div className="txt-fit-2" style={{ fontSize: 9.5, color: hoverEvent === i || selectedEvent === i ? "var(--z-dark)" : "var(--z-muted)", fontWeight: hoverEvent === i ? 600 : 400 }}>{e.title}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EventDetail({ event, onClose, openEvidence }) {
  const TONE = { positive: "var(--z-mid)", negative: "var(--z-below)", neutral: "var(--z-purple)" };
  return (
    <div style={{ marginTop: 16, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${TONE[event.signal]}` }}>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="f-mono" style={{ fontSize: 11, color: "var(--z-muted)" }}>{event.date}</span>
        <strong style={{ fontSize: 14 }}>{event.title}</strong>
        <span className="b b-purple">{event.cap_impact}</span>
        <span className="spacer" />
        <span className="b b-muted">{event.signal.toUpperCase()}</span>
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 10 }}>
        {event.signal === "positive" ? "Positive signal - increases the maturity ceiling on the affected capability." :
         event.signal === "negative" ? "Negative signal - caps the maturity score on the affected capability." :
         "Neutral signal - context for understanding the entity's trajectory, no direct score effect."}
      </div>
      {event.evidence.length > 0 ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Evidence:</span>
          {event.evidence.map(eid => {
            const e = DMA.getEvidence(eid);
            const tier = e?.tier || "T1";
            return <button key={eid} className={`tier-chip tier-${tier}`} onClick={() => openEvidence(eid)}>{eid} · {tier}</button>;
          })}
        </div>
      ) : null}
    </div>
  );
}

function InteractiveGantt({ issues, issueOpen, setIssueOpen }) {
  const undated = (issues || []).filter(i => !i.start);
  issues = (issues || []).filter(i => i.start);
  if (!issues.length) {
    return (
      <div className="empty" style={{ padding: "18px 0" }}>
        <h3>No dated issues</h3>
        <p>{undated.length
          ? `${undated.length} issue${undated.length === 1 ? "" : "s"} recorded without an opened date — a time axis needs a date.`
          : "No issues recorded for this run."}</p>
      </div>
    );
  }
  const start = new Date("2024-01-01");
  const today = new Date();
  const months = 36;
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 12, fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
        <div></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 0 }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} style={{ borderLeft: i === 0 ? "none" : "1px dashed var(--z-sep)", paddingLeft: 4 }}>{`${i % 3 === 0 ? (2024 + Math.floor(i / 3)) : "Q" + ((i % 3) + 1)}`}</div>
          ))}
        </div>
      </div>
      {issues.map(iss => {
        const startD = new Date(iss.start + (iss.start.length === 7 ? "-01" : ""));
        const endD = iss.end ? new Date(iss.end + (iss.end.length === 7 ? "-01" : "")) : today;
        const startPct = ((startD - start) / (1000*60*60*24*30.4) / months) * 100;
        const widthPct = ((endD - startD) / (1000*60*60*24*30.4) / months) * 100;
        const color = iss.severity === "CRITICAL" ? "var(--z-below)" : iss.severity === "MATERIAL" ? "var(--z-org)" : "var(--z-muted)";
        const isOpen = issueOpen === iss.id;
        return (
          <button key={iss.id} onClick={() => setIssueOpen(isOpen ? null : iss.id)}
            style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 12, padding: "8px 0", borderTop: "1px solid var(--z-sep)", textAlign: "left", width: "100%", background: isOpen ? "var(--z-lav)" : "transparent", border: "0", borderRadius: 6 }}>
            <div style={{ padding: "0 8px" }}>
              <div className="row">
                <span className="chip">{iss.id}</span>
                <span className={`b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{iss.severity}</span>
                {Object.keys(DMA.ISSUE_CAPS[iss.id]?.caps || {}).length > 0 ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} /> : null}
              </div>
              <div style={{ fontSize: 12, marginTop: 4 }}>{iss.type}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>{iss.status} {iss.cap_value ? `· cap ${iss.cap_value}` : ""}</div>
            </div>
            <div style={{ position: "relative", height: 28 }}>
              <div style={{ position: "absolute", left: `${startPct}%`, width: `${Math.max(2, widthPct)}%`, height: 18, top: 5, background: color, borderRadius: 4, opacity: .85, display: "flex", alignItems: "center", padding: "0 6px", color: "#fff", fontSize: 10, fontWeight: 500, overflow: "hidden", whiteSpace: "nowrap" }} className="txt-trunc">
                {iss.desc}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function IssueDetail({ issue, entity, onClose, openEvidence }) {
  if (!issue) return null;
  const caps = Object.entries(DMA.ISSUE_CAPS[issue.id]?.caps || {});
  return (
    <div style={{ marginTop: 14, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${issue.severity === "CRITICAL" ? "var(--z-below)" : issue.severity === "MATERIAL" ? "var(--z-org)" : "var(--z-muted)"}` }}>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="chip">{issue.id}</span>
        <strong style={{ fontSize: 14 }}>{issue.type}</strong>
        <span className={`b ${issue.severity === "CRITICAL" ? "b-below" : issue.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{issue.severity}</span>
        <span className="b b-muted">{issue.status}</span>
        <span className="spacer" />
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>
      <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 14 }}>{issue.desc}</div>
      {caps.length > 0 ? (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Caps placed by this issue · {caps.length}</div>
          <div className="g2" style={{ gap: 8 }}>
            {caps.map(([subcapId, capValue]) => {
              const s = entity.subcaps.find(x => x.id === subcapId) || { name: subcapId, score: capValue };
              return (
                <div key={subcapId} className="card-tile" style={{ padding: 10 }}>
                  <div className="row" style={{ marginBottom: 4 }}>
                    <span className="chip purple">{subcapId}</span>
                    <span className="spacer" />
                    <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} />
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{s.name}</div>
                  <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>Score capped at M{capValue}</div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {(() => {
        const ev = DMA.EVIDENCE.filter(e => e.subcaps && e.subcaps.some(sid => caps.some(([cid]) => sid.slice(0, 4) === cid.slice(0, 4))));
        if (!ev.length) return null;
        return (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Evidence · click to open</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
              {ev.map(e => <button key={e.id} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }} title={`${e.title} · ${e.source_pretty}`} onClick={() => openEvidence && openEvidence(e.id)}>{e.id}</button>)}
            </div>
          </div>
        );
      })()}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/heatmap`, { hm: "standard", zoom: "subcap" })}>View capped cells in heatmap <Icon name="arrow-r" size={11} /></button>
      </div>
    </div>
  );
}

function FinChartInteractive({ entity, hoveredYear, setHoveredYear }) {
  const years = [2022, 2023, 2024, 2025, 2026];
  const baseAssets = entity.assets || 11e9;
  const cagr = entity.cagr || 0.06;
  const data = years.map((y, i) => ({ year: y, val: baseAssets * Math.pow(1 + cagr, i - 4) }));
  const max = Math.max(...data.map(d => d.val));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 140, padding: "0 8px" }}>
        {data.map(d => (
          <div key={d.year} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, cursor: "pointer" }} onMouseEnter={() => setHoveredYear(d.year)} onMouseLeave={() => setHoveredYear(null)}>
            <div style={{ fontSize: 10, color: hoveredYear === d.year ? "var(--z-teal)" : "var(--z-muted)", fontWeight: hoveredYear === d.year ? 700 : 400 }}>${fx((d.val / 1e9), 1)}B</div>
            <div style={{ width: "100%", height: `${(d.val / max) * 120}px`, background: hoveredYear === d.year ? "linear-gradient(180deg, var(--z-mid), var(--z-dark2))" : "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0", transition: "background 160ms" }} />
            <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{d.year}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 10, padding: 8, background: "var(--z-lav)", borderRadius: 6, fontSize: 11, color: "var(--z-body)" }}>
        Total asset CAGR <strong style={{ color: "var(--z-mid)" }}>{fx((cagr * 100), 1)}%</strong> · trend classified <strong>{entity.trend}</strong>
        {hoveredYear ? <span style={{ marginLeft: 8, color: "var(--z-teal)", fontWeight: 600 }}>· {hoveredYear}: ${fx((data.find(d => d.year === hoveredYear).val / 1e9), 2)}B</span> : null}
      </div>
    </div>
  );
}

function SentimentGridInteractive({ sentOpen, setSentOpen, openEvidence }) {
  const sentiments = [
    { id: "S-01", label: "Glassdoor",       value: 3.8, max: 5,   n: 412,  label2: "Employee", evidence: "E-236", url: "glassdoor.com/Reviews/FCE", drilldown: "Recurring themes: manual processing, spreadsheet-heavy work in ops. Engineering scores 4.2 - front-line ops scores 3.1." },
    { id: "S-02", label: "App Store",       value: 3.4, max: 5,   n: 8200, label2: "Mobile",   evidence: "E-271", url: "apps.apple.com/...", drilldown: "Recent reviews cite slow transfers, branch dependency. Banking apps for regional peers average 4.2 stars (Forrester Q1 2026)." },
    { id: "S-03", label: "CFPB complaints", value: 24,  max: 100, n: 24,   label2: "Index",    evidence: null,    url: null, drilldown: "Below industry median (43). Most complaints relate to ACH processing delays, not service quality. Caps P2C2.1.1 at M3 until reduced below 18." },
  ];
  return (
    <div className="g3" style={{ gap: 10 }}>
      {sentiments.map(s => {
        const isOpen = sentOpen === s.id;
        return (
          <div key={s.id}>
            <button onClick={() => setSentOpen(isOpen ? null : s.id)} className="card-tile clickable" style={{ padding: 10, width: "100%", textAlign: "left", border: isOpen ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)" }}>
              <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{s.label2}</div>
              <div className="row" style={{ marginTop: 4 }}>
                <span style={{ fontSize: 18, fontWeight: 600 }}>{s.value}<span style={{ fontSize: 11, color: "var(--z-muted)", fontWeight: 400 }}>/{s.max}</span></span>
                <span className="spacer" />
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={11} style={{ color: "var(--z-muted)" }} />
              </div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.label} · n={s.n.toLocaleString()}</div>
            </button>
            {isOpen ? (
              <div style={{ marginTop: 6, padding: "10px 12px", background: "var(--z-lav)", borderRadius: 6, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55 }}>
                {s.drilldown}
                {s.evidence ? <div style={{ marginTop: 8 }}><button className={`tier-chip tier-T6`} onClick={(e) => { e.stopPropagation(); openEvidence(s.evidence); }}>{s.evidence}</button></div> : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function Timeline({ events, hover, setHover, openEvidence }) {
  const minDate = new Date(events[0].date + "-01");
  const maxDate = new Date(events[events.length - 1].date + "-01");
  const span = maxDate - minDate;
  const TONE = { positive: "var(--z-mid)", negative: "var(--z-below)", neutral: "var(--z-muted)" };

  return (
    <div style={{ position: "relative", padding: "20px 8px 50px" }}>
      <div style={{ position: "relative", height: 2, background: "var(--z-sep)", margin: "30px 16px" }}>
        {events.map((e, i) => {
          const pct = ((new Date(e.date + "-01") - minDate) / span) * 100;
          return (
            <button key={e.id}
              style={{ position: "absolute", left: `${pct}%`, top: -7, width: 16, height: 16, borderRadius: 8, background: TONE[e.signal], transform: "translateX(-8px)", border: "2px solid #fff", cursor: "pointer", boxShadow: "var(--sh-sm)" }}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: 6, fontSize: 9.5, color: "var(--z-muted)", padding: "0 8px" }}>
        {events.map((e, i) => (
          <div key={e.id} style={{ textAlign: "center", lineHeight: 1.4 }}>
            <div className="f-mono">{e.date}</div>
            <div style={{ color: TONE[e.signal], fontWeight: hover === i ? 600 : 400 }}>{e.title.split(" ").slice(0, 4).join(" ")}{e.title.split(" ").length > 4 ? "…" : ""}</div>
          </div>
        ))}
      </div>
      {hover != null ? (
        <div className="card-tile" style={{ marginTop: 16, padding: 12, background: "var(--z-lav)", border: "none" }}>
          <div className="row" style={{ marginBottom: 6 }}>
            <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{events[hover].date}</span>
            <strong style={{ fontSize: 13 }}>{events[hover].title}</strong>
            <span className="spacer" />
            <span className="b b-purple">{events[hover].cap_impact}</span>
            <span className="b b-muted">{events[hover].signal.toUpperCase()}</span>
          </div>
          {events[hover].evidence.length > 0 ? (
            <div>{events[hover].evidence.map(eid => <button key={eid} className="chip" style={{ marginRight: 4 }} onClick={() => openEvidence(eid)}>{eid}</button>)}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Gantt({ issues }) {
  issues = (issues || []).filter(i => i.start);
  if (!issues.length) return null;
  // Build axis: 2024 Q1 - 2026 Q4
  const months = 36, start = new Date("2024-01-01");
  const today = new Date();
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 12, fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
        <div></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 0 }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} style={{ borderLeft: i === 0 ? "none" : "1px dashed var(--z-sep)", paddingLeft: 4 }}>{`${i % 3 === 0 ? (2024 + Math.floor(i / 3)) : "Q" + ((i % 3) + 1)}`}</div>
          ))}
        </div>
      </div>
      {issues.map(iss => {
        const startD = new Date(iss.start + (iss.start.length === 7 ? "-01" : "-01"));
        const endD = iss.end ? new Date(iss.end + (iss.end.length === 7 ? "-01" : "-01")) : today;
        const startPct = ((startD - start) / (1000*60*60*24*30.4) / months) * 100;
        const widthPct = ((endD - startD) / (1000*60*60*24*30.4) / months) * 100;
        const color = iss.severity === "CRITICAL" ? "var(--z-below)" : iss.severity === "MATERIAL" ? "var(--z-org)" : "var(--z-muted)";
        return (
          <div key={iss.id} style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 12, padding: "8px 0", borderTop: "1px solid var(--z-sep)" }}>
            <div>
              <div className="row">
                <span className="chip">{iss.id}</span>
                <span className={`b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{iss.severity}</span>
              </div>
              <div style={{ fontSize: 12, marginTop: 4 }}>{iss.type}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>{iss.status} {iss.cap_value ? `· cap ${iss.cap_value}` : ""}</div>
            </div>
            <div style={{ position: "relative", height: 28 }}>
              <div style={{ position: "absolute", left: `${startPct}%`, width: `${Math.max(2, widthPct)}%`, height: 18, top: 5, background: color, borderRadius: 4, opacity: .85, display: "flex", alignItems: "center", padding: "0 6px", color: "#fff", fontSize: 10, fontWeight: 500, overflow: "hidden", whiteSpace: "nowrap" }}>
                {iss.desc.slice(0, 60)}{iss.desc.length > 60 ? "…" : ""}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FinChart({ entity }) {
  const years = [2022, 2023, 2024, 2025, 2026];
  const baseAssets = entity.assets || 11e9;
  const cagr = entity.cagr || 0.06;
  const data = years.map((y, i) => ({ year: y, val: baseAssets * Math.pow(1 + cagr, i - 4) }));
  const max = Math.max(...data.map(d => d.val));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 140, padding: "0 8px" }}>
        {data.map(d => (
          <div key={d.year} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <div style={{ fontSize: 10, color: "var(--z-muted)" }}>${fx((d.val / 1e9), 1)}B</div>
            <div style={{ width: "100%", height: `${(d.val / max) * 120}px`, background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0" }} />
            <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{d.year}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 10, padding: 8, background: "var(--z-lav)", borderRadius: 6, fontSize: 11, color: "var(--z-body)" }}>
        Total asset CAGR <strong style={{ color: "var(--z-mid)" }}>{fx((cagr * 100), 1)}%</strong> · trend classified <strong>{entity.trend}</strong>
      </div>
    </div>
  );
}

function SentimentGrid() {
  const sentiments = [
    { label: "Glassdoor",      value: 3.8, max: 5, n: 412, label2: "Employee" },
    { label: "App Store",      value: 3.4, max: 5, n: 8200, label2: "Mobile" },
    { label: "CFPB complaints", value: 24,  max: 100, n: 24, label2: "Index (lower better)" },
  ];
  return (
    <div className="g3" style={{ gap: 10 }}>
      {sentiments.map(s => (
        <div key={s.label} className="card-tile" style={{ padding: 10, border: "none", background: "var(--z-lav)" }}>
          <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{s.label2}</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{s.value}<span style={{ fontSize: 11, color: "var(--z-muted)", fontWeight: 400 }}>/{s.max}</span></div>
          <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.label} · n={s.n.toLocaleString()}</div>
        </div>
      ))}
    </div>
  );
}

/* ── D6 Assessment health ────────────────────────────────────────── */
function ClientHealth({ entity, run }) {
  const { role, audience, pushToast } = useApp();
  const [tab, setTab] = useState("alerts");
  const alerts = DMA.alertsForEntity(entity.id);
  const [compareBase, setCompareBase] = useState(entity.runs[1]?.id);
  const [compareTarget, setCompareTarget] = useState(entity.runs[0]?.id);

  if (audience === "customer" || (role !== "ANALYST" && role !== "ADMIN")) {
    return <div className="empty"><div className="icon"><Icon name="lock" size={20} /></div><h3>Analyst access required</h3><p>This section requires Analyst access.</p></div>;
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Assessment health</div>
          <h1>Quality &amp; controls</h1>
          <div className="sub">{alerts.length} open alerts · {DMA.QA_GATES.filter(g => g.status === "FAIL").length} failing gates · {entity.runs.length} runs in history</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast("Feedback file regenerated — routed to DMA bot", "success")}><Icon name="refresh" size={13} /> Re-run feedback file</button>
          <button className="btn btn-secondary" onClick={() => pushToast(`Exporting ${entity.name} health report as CSV…`, "success")}><Icon name="download" size={13} /> CSV export</button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="toggle-row">
          {[["alerts","Thin-evidence alerts"],["diff","Version diff"],["gates","Safeguard gates"],["age","Evidence age"],["patterns","Cross-entity patterns"]].map(([k, l]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
      </div>

      {tab === "alerts" ? (
        <div className="card flush">
          <div className="card-head"><h3>Thin-evidence alerts</h3><span className="b b-org">{alerts.length} open</span></div>
          <table className="tbl">
            <thead><tr><th>Severity</th><th>Subcap</th><th>Evidence</th><th>Action</th><th>Proxy</th><th style={{ textAlign: "right" }}>Status</th></tr></thead>
            <tbody>
              {alerts.map(a => (
                <tr key={a.id}>
                  <td><span className={`b ${a.severity === "HIGH" ? "b-below" : "b-org"}`}>{a.severity}</span></td>
                  <td><div style={{ fontSize: 12, fontWeight: 500 }}>{a.subcap_name}</div><div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.subcap_id}</div></td>
                  <td>
                    <div style={{ fontSize: 12 }}>{a.evidence_count} / 3</div>
                    <div className="prog" style={{ marginTop: 4, width: 80, height: 4 }}><div className="prog-fill" style={{ width: `${(a.evidence_count / 3) * 100}%`, background: "var(--z-org)" }} /></div>
                  </td>
                  <td><span className="b b-purple">{a.recommended_action}</span></td>
                  <td>{a.proxy_searched ? <span style={{ color: "var(--z-mid)", fontSize: 11 }}>✓ Searched</span> : <span style={{ color: "var(--z-org)", fontSize: 11 }}>Not yet</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} moved to IN_REVIEW`, "success")}>In review</button>
                    <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} waived — add rationale before close`, "warn")}>Waive</button>
                  </td>
                </tr>
              ))}
              {alerts.length === 0 ? <tr><td colSpan={6} className="tbl-empty"><div style={{ color: "var(--z-mid)", fontSize: 13, fontWeight: 500 }}>✓ No open alerts</div><div style={{ fontSize: 11, marginTop: 4 }}>Evidence coverage meets the minimum threshold.</div></td></tr> : null}
            </tbody>
          </table>
        </div>
      ) : tab === "diff" ? (
        <VersionDiff entity={entity} baseId={compareBase} targetId={compareTarget} setBase={setCompareBase} setTarget={setCompareTarget} />
      ) : tab === "gates" ? (
        <div className="card flush">
          <div className="card-head"><h3>Safeguard gates · G01–G10</h3><span className={`b ${DMA.QA_GATES.some(g => g.status === "FAIL") ? "b-org" : "b-teal"}`}>{DMA.QA_GATES.filter(g => g.status === "PASS").length} / 10 PASS</span></div>
          <table className="tbl">
            <tbody>
              {DMA.QA_GATES.map(g => (
                <tr key={g.id}>
                  <td style={{ width: 60 }}><span className="chip">{g.id}</span></td>
                  <td><strong>{g.name}</strong></td>
                  <td>{g.evidence}</td>
                  <td style={{ width: 80 }}><span className={`b ${g.status === "PASS" ? "b-above" : "b-below"}`}>{g.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : tab === "age" ? (
        <div className="card flush">
          <div className="card-head"><h3>Evidence age tracker</h3></div>
          <table className="tbl">
            <thead><tr><th>Evidence</th><th>Source</th><th>Date</th><th>Age</th><th style={{textAlign:"right"}}>Status</th></tr></thead>
            <tbody>
              {DMA.EVIDENCE.map(e => {
                const age = Math.round((new Date() - new Date(e.recency.replace("Q1","-01-01").replace("Q2","-04-01").replace("Q3","-07-01").replace("Q4","-10-01"))) / (1000*60*60*24*30.4));
                const stale = age > 18;
                return (
                  <tr key={e.id}>
                    <td><span className="chip">{e.id}</span> <span style={{ marginLeft: 6 }}>{e.title}</span></td>
                    <td className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.source.split("/")[0]}</td>
                    <td>{e.recency}</td>
                    <td>{age} mo</td>
                    <td style={{ textAlign: "right" }}><span className={`b ${stale ? "b-org" : "b-teal"}`}>{stale ? "STALE" : "FRESH"}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card flush">
          <div className="card-head"><h3>Cross-entity patterns</h3><span className="b b-muted">≥60% threshold</span></div>
          <table className="tbl">
            <thead><tr><th>Subvertical</th><th>Category</th><th>Pattern</th><th>Count</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
            <tbody>
              {DMA.PATTERNS.map((p, i) => (
                <tr key={i}>
                  <td><span className="b b-purple">{DMA.SUBVERTICAL_LABEL[p.subvertical]}</span></td>
                  <td><span className="chip">{p.category}</span></td>
                  <td><strong>{p.title}</strong></td>
                  <td>{p.count} / {p.total}</td>
                  <td style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Drafting outreach campaign · ${p.title}`, "success")}>Build campaign →</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function VersionDiff({ entity, baseId, targetId, setBase, setTarget }) {
  const base = entity.runs.find(r => r.id === baseId);
  const target = entity.runs.find(r => r.id === targetId);
  if (!base || !target) {
    return <div className="empty"><div className="icon"><Icon name="info" size={20} /></div><h3>Pick two runs to compare</h3><p>This entity has {entity.runs.length} runs.</p></div>;
  }
  const diffs = entity.subcaps.slice(0, 18).map(s => {
    const baseScore = DMA.helpers.round1(s.score - 0.2 - ((s.id.charCodeAt(2) % 5) / 12));
    return { id: s.id, name: s.name, category: s.category, base: baseScore, target: s.score, delta: DMA.helpers.round1(s.score - baseScore), evBase: Math.max(0, s.evidence_count - 1), evTarget: s.evidence_count };
  });
  return (
    <div className="card flush">
      <div className="card-head" style={{ flexWrap: "wrap", gap: 8 }}>
        <h3>Version diff</h3>
        <div className="row">
          <select className="inp" style={{ minWidth: 240 }} value={baseId} onChange={e => setBase(e.target.value)}>
            {entity.runs.map(r => <option key={r.id} value={r.id}>{fmtDate(r.date)} · {r.status} · {r.data_source}</option>)}
          </select>
          <span style={{ color: "var(--z-muted)" }}>vs</span>
          <select className="inp" style={{ minWidth: 240 }} value={targetId} onChange={e => setTarget(e.target.value)}>
            {entity.runs.map(r => <option key={r.id} value={r.id}>{fmtDate(r.date)} · {r.status} · {r.data_source}</option>)}
          </select>
        </div>
      </div>
      <table className="tbl">
        <thead><tr><th>Subcap</th><th>Category</th><th>{fmtDate(base.date)}</th><th>{fmtDate(target.date)}</th><th>Δ</th><th>Evidence</th></tr></thead>
        <tbody>
          {diffs.map(d => (
            <tr key={d.id}>
              <td>{d.name} <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{d.id}</span></td>
              <td><span className="chip">{d.category}</span></td>
              <td><MaturityChip score={d.base} /></td>
              <td><MaturityChip score={d.target} /></td>
              <td><span style={{ fontFamily: "var(--font-mono)", color: d.delta > 0 ? "var(--z-mid)" : d.delta < 0 ? "var(--z-below)" : "var(--z-muted)" }}>{d.delta > 0 ? "▲" : d.delta < 0 ? "▼" : "-"} {fx(Math.abs(d.delta), 1)}</span></td>
              <td><span style={{ fontSize: 11 }}>{d.evBase} → {d.evTarget}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Tech stack overview (s41) ───────────────────────────────────── */
function ClientTechStack({ entity, run }) {
  const { pushToast } = useApp();
  const [layer, setLayer] = useState("ALL");
  const [hideAbsent, setHideAbsent] = useState(false);

  const allTech = DMA.TECH_STACK;
  const list = useMemo(() => allTech.filter(t => {
    if (layer !== "ALL" && t.layer !== layer) return false;
    if (hideAbsent && t.status === "ABSENT") return false;
    return true;
  }), [layer, hideAbsent]);

  // Charter correction: the layer keys are OPS · CUST · DATA · INFRA, not
  // L2–L5. L1–L4 already name the EVIDENCE levels, and a register row showing
  // "L3" next to an evidence level "L3" means two different things in the same
  // row. Same four labels, same layout, unambiguous keys.
  const LAYERS = ["OPS", "CUST", "DATA", "INFRA"];
  const LAYER_LABEL = {
    OPS:   { name: "Operations & core banking",  short: "Operations", dma: "P3" },
    CUST:  { name: "Customer engagement",        short: "Customer",   dma: "P2", primary_gap: true },
    DATA:  { name: "Data & analytics",           short: "Data",       dma: "P4" },
    INFRA: { name: "Infrastructure & cloud",     short: "Infra",      dma: "P4" },
  };
  const byLayer = {};
  LAYERS.forEach(L => byLayer[L] = list.filter(t => t.layer === L));

  const absentCount = allTech.filter(t => t.status === "ABSENT" && (t.layer === "L3" || t.layer === "L4")).length;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Technology intelligence</div>
          <h1>Technology stack - {entity.name}</h1>
          <div className="sub">Confirmed vs absent across the 4 product layers · Explorium synced {fmtDate(entity.assessment_date)}</div>
        </div>
        <div className="actions">
          <span className="b b-teal" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Icon name="check" size={10} /> Explorium synced</span>
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${entity.name} tech stack as CSV…`, "success")}><Icon name="download" size={13} /> Export</button>
        </div>
      </div>

      {/* Status legend + filters */}
      <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <div className="eyebrow" style={{ margin: 0 }}>Legend</div>
          {[
            { label: "Confirmed", c: "var(--z-mid)",   bg: "var(--z-ice)",  bd: "rgba(39,187,175,.4)",  desc: "Explorium technographic" },
            { label: "Inferred",  c: "var(--z-dpur)",  bg: "var(--ph0-lt)", bd: "var(--ph0-bd)",        desc: "Job postings · press" },
            { label: "Partial",   c: "#7C3500",        bg: "rgba(254,151,50,.08)", bd: "rgba(254,151,50,.3)", desc: "Limited rollout" },
            { label: "Absent",    c: "var(--z-below)", bg: "rgba(194,80,8,.06)",   bd: "rgba(194,80,8,.25)",   desc: "Confirmed via Explorium" },
          ].map(s => (
            <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--z-body)" }}>
              <span style={{ width: 14, height: 14, background: s.bg, border: `1.5px solid ${s.bd}`, borderRadius: 3 }} />
              <strong style={{ color: s.c }}>{s.label}</strong>
              <span className="muted" style={{ fontSize: 10.5 }}>{s.desc}</span>
            </div>
          ))}
          <span className="spacer" />
          <div className="row" style={{ gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Layer</span>
            <select className="inp" style={{ width: 200, padding: "5px 10px", fontSize: 12 }} value={layer} onChange={e => setLayer(e.target.value)}>
              <option value="ALL">All layers</option>
              {LAYERS.map(L => <option key={L} value={L}>{LAYER_LABEL[L].name}</option>)}
            </select>
          </div>
          <label className="row" style={{ fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${hideAbsent ? "on" : ""}`} onClick={() => setHideAbsent(v => !v)} />
            Hide absent
          </label>
        </div>
      </div>

      {/* Stat strip */}
      <div className="g4" style={{ marginBottom: 14 }}>
        {[
          { l: "Confirmed",   v: allTech.filter(t => t.status === "CONFIRMED").length,  c: "var(--z-mid)" },
          { l: "Inferred",    v: allTech.filter(t => t.status === "INFERRED").length,   c: "var(--z-dpur)" },
          { l: "Absent",      v: allTech.filter(t => t.status === "ABSENT").length,     c: "var(--z-below)" },
          { l: "Primary gaps", v: allTech.filter(t => t.primary_gap).length,            c: "var(--z-blue)" },
        ].map(s => (
          <div key={s.l} className="card-tile" style={{ borderLeft: `3px solid ${s.c}` }}>
            <div style={{ fontSize: 10, color: "var(--z-muted)", letterSpacing: ".08em", textTransform: "uppercase" }}>{s.l}</div>
            <div style={{ fontSize: 28, fontWeight: 200, color: s.c, lineHeight: 1, marginTop: 6 }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* Layer cards */}
      {LAYERS.map(L => {
        const LM = LAYER_LABEL[L];
        const techList = byLayer[L];
        if (!techList || techList.length === 0) return null;
        const isPrimaryGap = LM.primary_gap;
        return (
          <div key={L} className="card" style={{ marginBottom: 12, padding: 16, borderColor: isPrimaryGap ? "var(--z-blue)" : "var(--z-sep)", borderWidth: isPrimaryGap ? 1.5 : 1, borderStyle: "solid" }}>
            <div className="row" style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{LM.name}</div>
              {isPrimaryGap ? <span className="b b-ph1" style={{ background: "var(--ph1-lt)" }}>PRIMARY GAP LAYER</span> : null}
              <span className="spacer" />
              <span className="b b-teal">{LM.dma}</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{techList.filter(t => t.status !== "ABSENT").length} of {techList.length} detected</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {techList.map(t => <TechRow key={t.id} t={t} entity={entity} run={run} />)}
            </div>
          </div>
        );
      })}

      {/* Gap summary footer */}
      <div className="card" style={{ background: "var(--z-lav)", border: "none", padding: 14, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--z-below)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="platform" size={18} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{absentCount} technologies absent across customer + data layers - the primary Zennify engagement opportunity</div>
          <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 3 }}>All absent-technology rows link directly to platform recommendations.</div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => navigate(`/clients/${entity.id}/platform`, { run: run.id })}>View platform matrix <Icon name="arrow-r" size={11} /></button>
      </div>
    </div>
  );
}

function TechRow({ t, entity, run }) {
  const { openEvidence } = useApp();
  const STATUS_STYLE = {
    CONFIRMED: { bg: "var(--z-ice)",          bd: "rgba(39,187,175,.4)", color: "var(--z-mid)" },
    INFERRED:  { bg: "var(--ph0-lt)",         bd: "var(--ph0-bd)",       color: "var(--z-dpur)" },
    ABSENT:    { bg: "rgba(194,80,8,.06)",    bd: "rgba(194,80,8,.25)",  color: "var(--z-below)" },
    PARTIAL:   { bg: "rgba(254,151,50,.08)",  bd: "rgba(254,151,50,.3)",  color: "#7C3500" },
  };
  const S = STATUS_STYLE[t.status] || STATUS_STYLE.CONFIRMED;

  return (
    <button onClick={() => navigate(`/clients/${entity.id}/techstack/${t.id}`, { run: run.id })}
      style={{
        background: S.bg, border: `1.5px solid ${S.bd}`, borderRadius: 8, padding: "10px 14px",
        textAlign: "left", display: "flex", gap: 12, alignItems: "flex-start",
        cursor: "pointer", transition: "transform 120ms, box-shadow 120ms"
      }}
      onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "var(--sh-md)"; }}
      onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ marginBottom: 4, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{t.name}</span>
          <span style={{ fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: S.color }}>{t.status}</span>
          {t.evidence.map(eid => (
            <button key={eid} className="chip purple" style={{ fontSize: 10, padding: "1px 5px" }} onClick={(ev) => { ev.stopPropagation(); openEvidence(eid); }}>{eid}</button>
          ))}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>{t.note}</div>
        {t.subcaps_impact && t.subcaps_impact.length > 0 ? (
          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
            {t.subcaps_impact.map(s => <span key={s} className="chip">{s}</span>)}
          </div>
        ) : null}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end", maxWidth: 160 }}>
        {t.source.map((src, i) => (
          <span key={i} className={`b ${
            src === "Explorium" ? "b-teal" :
            src === "Press release" ? "b-purple" :
            src === "Job posting" ? "b-ph1" : "b-muted"
          }`} style={{ fontSize: 9 }}>{src}</span>
        ))}
        {t.since ? <span style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2 }}>Since {t.since}</span> : null}
      </div>
    </button>
  );
}

/* ── Tech stack drilldown (s42) ──────────────────────────────────── */
function ClientTechStackDetail({ entity, run, techId }) {
  const { openEvidence } = useApp();
  const t = DMA.TECH_STACK.find(x => x.id === techId);
  if (!t) return <div className="empty"><h3>Technology not found</h3></div>;

  const STATUS_STYLE = {
    CONFIRMED: { color: "var(--z-mid)",   label: "Confirmed - Explorium" },
    INFERRED:  { color: "var(--z-dpur)",  label: "Inferred - job posting · press" },
    ABSENT:    { color: "var(--z-below)", label: "Absent - confirmed via Explorium" },
    PARTIAL:   { color: "#7C3500",        label: "Partial deployment" },
  };
  const S = STATUS_STYLE[t.status];

  // Build subcap impact rows
  const impacts = t.subcaps_impact.map(sid => {
    const subcap = entity.subcaps.find(s => s.id === sid) || { id: sid, name: sid, score: 2.0 };
    const baseline = t.status === "ABSENT" ? subcap.score : Math.max(1, subcap.score - 1.2);
    const target = t.status === "ABSENT" ? Math.min(5, subcap.score + 1.3) : subcap.score;
    const delta = target - baseline;
    return { ...subcap, baseline, target, delta, thin: subcap.thin };
  });

  const peers = DMA.PEER_SETS[entity.subvertical]?.peers || [];

  const gapZones = t.status === "ABSENT" ? [
    `No ${t.layer === "L3" ? "CRM or member 360 profile layer" : "data foundation"} when ${t.name} is absent.`,
    `Blocks Agentforce prerequisites (P2C2 + P4C1 must be ≥ 2.0).`,
    `Creates downstream constraint for any AI/decisioning investment.`,
    `Operating cost stays elevated - manual workflows persist.`,
  ] : [
    `No integrated AI/ML decisioning layer on top of ${t.name}.`,
    `No omnichannel servicing (post-origination).`,
    `Integration bus gap to other cores remains.`,
    `Self-service analytics not yet exposed to operations leadership.`,
  ];

  return (
    <div>
      {/* Breadcrumb */}
      <div className="row" style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 14 }}>
        <a href={`#/clients/${entity.id}/techstack?run=${run.id}`} style={{ color: "var(--z-mid)", fontWeight: 500 }}>Tech stack overview</a>
        <Icon name="chevron-r" size={12} />
        <strong style={{ color: "var(--z-dark)" }}>{t.name}</strong>
      </div>

      {/* Header card */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ marginBottom: 8, flexWrap: "wrap" }}>
          <span className="b b-muted" style={{ textTransform: "uppercase" }}>{t.layer_full}</span>
          <span className="b b-teal" style={{ background: t.status === "ABSENT" ? "rgba(194,80,8,.10)" : t.status === "INFERRED" ? "var(--ph0-lt)" : "var(--z-ice)", color: S.color, border: `1px solid ${S.color}22` }}>{S.label}</span>
          {t.since ? <span style={{ fontSize: 11, color: "var(--z-muted)", background: "var(--z-lav)", padding: "2px 8px", borderRadius: 3 }}>Since {t.since}</span> : null}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: "var(--z-dark)", marginBottom: 6 }}>{t.name}</div>
            <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.55, maxWidth: 720 }}>{t.note}</div>
          </div>
          <div style={{ textAlign: "right", flexShrink: 0 }}>
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginBottom: 4 }}>DMA impact</div>
            <div style={{ fontSize: 32, fontWeight: 200, color: t.status === "ABSENT" ? "var(--z-below)" : "var(--z-teal)", lineHeight: 1 }}>
              {t.status === "ABSENT" ? "−" : "+"}{fx((impacts.reduce((a, i) => a + Math.abs(i.delta), 0) / Math.max(1, impacts.length)), 1)}
            </div>
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>avg subcap ceiling {t.status === "ABSENT" ? "blocked" : "uplift"}</div>
          </div>
        </div>
      </div>

      {/* 2-col: Evidence + DMA assessment impact */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="evidence" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Detection evidence</div>
            <span className="spacer" />
            <span className="b b-muted">{t.evidence.length || 0} items</span>
          </div>
          {t.evidence.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)", padding: "8px 12px", background: "var(--z-lav)", borderRadius: 6 }}>
              No evidence items - {t.status === "ABSENT" ? "this entry was inferred (ABSENT) from technographic data" : "still gathering"}.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* Always show source signals first */}
              {t.source.map((src, i) => (
                <div key={i} style={{ padding: "8px 10px", background: i === 0 ? "var(--z-ice)" : "var(--z-lav)", borderLeft: `3px solid ${i === 0 ? "var(--z-teal)" : "var(--z-sep)"}`, borderRadius: 4 }}>
                  <div className="row" style={{ marginBottom: 3, fontSize: 11 }}>
                    <span className={`b ${src === "Explorium" ? "b-teal" : src === "Press release" ? "b-purple" : src === "Job posting" ? "b-ph1" : "b-muted"}`}>{src}</span>
                    <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{src === "Explorium" ? "Technographic · Q4 refresh" : "Detected"}</span>
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--z-dark)" }}>{src === "Explorium" ? `Confirmed active deployment - high confidence signal` : src === "Job posting" ? `Active job listings reference the platform - intent signal` : `Public mention confirms deployment scope`}</div>
                </div>
              ))}
              {t.evidence.map(eid => {
                const e = DMA.getEvidence(eid);
                if (!e) return null;
                return (
                  <div key={eid} style={{ padding: "10px 12px", background: "var(--z-bg)", borderLeft: "3px solid var(--z-sep)", borderRadius: 4 }}>
                    <div className="row" style={{ marginBottom: 4 }}>
                      <button className="chip" onClick={() => openEvidence(eid)}>{e.id}</button>
                      <span className="b b-muted">{e.tier}</span>
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{e.recency}</span>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{e.title}</div>
                    <div style={{ fontSize: 11.5, fontStyle: "italic", color: "var(--z-body)" }}>"{e.excerpt.slice(0, 140)}…"</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="heatmap" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>DMA assessment impact</div>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/heatmap`, { run: run.id })}>Open heatmap <Icon name="arrow-r" size={11} /></button>
          </div>
          {impacts.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>No subcap impact mapped.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {impacts.map(i => (
                <div key={i.id} style={{ padding: "8px 12px", background: i.thin ? "rgba(254,151,50,.08)" : "var(--z-ice)", borderRadius: 6, border: i.thin ? "1px solid rgba(254,151,50,.3)" : "1px solid transparent" }}>
                  <div className="row">
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="f-mono" style={{ fontSize: 11, color: "var(--z-dark)" }}>{i.id}</div>
                      {i.thin ? <div style={{ fontSize: 9.5, color: "var(--z-org)", marginTop: 1 }}>▲ Thin evidence - 1 item</div> : null}
                    </div>
                    <div className="row" style={{ gap: 6 }}>
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{fx(i.baseline, 1)} →</span>
                      <strong style={{ fontSize: 14, color: t.status === "ABSENT" ? "var(--z-below)" : "var(--z-mid)" }}>{fx(i.target, 1)}</strong>
                      <span style={{ fontSize: 10, color: t.status === "ABSENT" ? "var(--z-below)" : "var(--z-mid)", fontWeight: 600 }}>{t.status === "ABSENT" ? "" : "+"}{fx(i.delta, 1)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 2-col: Gap zones + Peer comparison */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={15} style={{ color: "var(--z-below)" }} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>{t.status === "ABSENT" ? `Gap zones - what ${t.name} would unlock` : `What ${t.name} does not cover`}</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {gapZones.map((g, i) => (
              <div key={i} style={{ padding: "8px 12px", background: "rgba(194,80,8,.05)", border: "1px solid rgba(194,80,8,.15)", borderRadius: 5, fontSize: 12, color: "var(--z-below)", lineHeight: 1.5 }}>{g}</div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="scale" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Peer deployment</div>
            <span className="spacer" />
            <span className="b b-teal">{fmtPct(t.peer_coverage)} adopted</span>
          </div>
          <div className="prog" style={{ marginBottom: 14 }}>
            <div className="prog-fill" style={{ width: `${t.peer_coverage * 100}%`, background: "linear-gradient(90deg, var(--z-teal), var(--z-mid))" }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {peers.slice(0, 4).map((p, i) => {
              const hasIt = ((Math.abs(hashCode(t.id + p)) % 100) / 100) < t.peer_coverage;
              return (
                <div key={p} style={{ padding: "6px 10px", background: hasIt ? "var(--z-ice)" : "var(--z-lav)", borderRadius: 5, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11.5 }}>
                  <span style={{ color: "var(--z-dark)", fontWeight: 500 }}>{p}</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: hasIt ? "var(--z-mid)" : "var(--z-muted)" }}>{hasIt ? `✓ ${t.name.split(" ")[0]}` : "not detected"}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recommendation callout (if absent) */}
      {t.status === "ABSENT" ? (
        <div className="card" style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)" }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <Icon name="sparkle" size={15} style={{ color: "var(--z-dpur)" }} />
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dpur)" }}>Zennify recommendation</div>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/platform`, { run: run.id })}>See platform matrix <Icon name="arrow-r" size={11} /></button>
          </div>
          <div style={{ fontSize: 13, color: "#3B0764", lineHeight: 1.65 }}>
            {t.name} is the bridge between {entity.name}'s current architecture and a unified customer experience. Sequence it after the foundation prerequisites are met (see Readiness Index in D4 Platform).
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ── Runs list ───────────────────────────────────────────────────── */
function ClientRuns({ entity }) {
  const { pushToast } = useApp();
  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Run history</div>
          <h1>Runs - {entity.name}</h1>
          <div className="sub">{entity.runs.length} immutable run records · sortable by date</div>
        </div>
        <div className="actions">
          <button className="btn btn-secondary" onClick={() => pushToast(`Rerun queued for ${entity.name} — first batch in ~3 min`, "success")}><Icon name="refresh" size={13} /> Trigger rerun</button>
        </div>
      </div>
      <div className="card flush">
        <table className="tbl tbl-clickable">
          <thead><tr><th>Run date</th><th>Run ID</th><th>Status</th><th>Source</th><th>Score</th><th>Evidence mode</th><th>Subcaps</th><th>Actions</th></tr></thead>
          <tbody>
            {entity.runs.map(r => (
              <tr key={r.id}>
                <td><strong>{fmtDate(r.date)}</strong></td>
                <td className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.id}</td>
                <td><span className={`b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`}>{r.status}</span></td>
                <td><span className={`b ${r.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{r.data_source === "DRIVE_PARSE" ? "DRIVE PARSE" : "PROJECT API"}</span></td>
                <td><MaturityChip score={r.overall} /></td>
                <td>{r.evidence_mode}</td>
                <td>{r.subcap_count}</td>
                <td>
                  <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/overview`, { run: r.id })}>View</button>
                  <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/health`, { run: r.id })}>Compare</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

Object.assign(window, { ClientContext, ClientHealth, ClientTechStack, ClientTechStackDetail, ClientRuns });
