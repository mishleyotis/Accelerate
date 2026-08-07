/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Client pages - D5 Context, D6 Health, Tech stack, Runs
   ═══════════════════════════════════════════════════════════════════════ */

/* ── D5 Context & timeline ───────────────────────────────────────── */
function ClientContext({ entity, run }) {
  const { audience, openEvidence, openSubcap } = useApp();
  // The range comes from the events, not from a constant. It was hardcoded
  // [2023, 2026] — the prototype fixture's span — so Baxter's timeline opened
  // having already filtered out everything before 2023, which is six of its ten
  // events including the 2016 origin the storyline turns on.
  const _years = (DMA.TIMELINE_EVENTS || [])
    .map(e => (e.date ? parseInt(String(e.date).slice(0, 4), 10) : NaN))
    .filter(y => Number.isFinite(y));
  const _lo = _years.length ? Math.min(..._years) : 2022;
  const _hi = _years.length ? Math.max(..._years) : 2026;
  const [yearRange, setYearRange] = useState([_lo, _hi]);
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

  // Filter timeline events by year + signal. An event with no date cannot be
  // placed on a range, so it is kept rather than dropped by `parseInt(undefined)`
  // — an undated event is a finding, not something to hide.
  const events = allEvents.filter(e => {
    const y = e.date ? parseInt(String(e.date).slice(0, 4)) : null;
    if (y !== null && (y < yearRange[0] || y > yearRange[1])) return false;
    if (signalFilter !== "ALL" && e.signal !== signalFilter) return false;
    return true;
  });
  // Counts per bucket, so a filter states how many it will match BEFORE it is
  // pressed. Pressing "Positive" and getting an empty timeline used to be
  // indistinguishable from a broken page; it was actually a producer writing
  // prose into the signal field (now refused at submit by CG-09).
  const signalCounts = allEvents.reduce((a, e) => {
    a[e.signal] = (a[e.signal] || 0) + 1; return a;
  }, {});
  const unclassified = signalCounts.unclassified || 0;

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
          {/* Each bucket carries its count, and a bucket with none is disabled
              rather than pressable-into-nothing. The Unclassified button only
              exists when the run actually has events the contract's vocabulary
              does not cover — it is a defect indicator, not a category. */}
          <div className="toggle-row">
            <button className={signalFilter === "ALL" ? "on" : ""} onClick={() => setSignalFilter("ALL")}>All · {allEvents.length}</button>
            {[["positive", "Positive", "var(--z-mid)"],
              ["neutral", "Neutral", null],
              ["negative", "Negative", "var(--z-below)"]].map(([k, l, c]) => {
              const n = signalCounts[k] || 0;
              return (
                <button key={k} className={signalFilter === k ? "on" : ""}
                        disabled={!n}
                        title={n ? `${n} event${n === 1 ? "" : "s"}` : "no events with this signal"}
                        onClick={() => n && setSignalFilter(k)}
                        style={{ color: signalFilter === k && c ? c : "var(--z-muted)",
                                 opacity: n ? 1 : 0.45,
                                 cursor: n ? "pointer" : "not-allowed" }}>{l} · {n}</button>
              );
            })}
            {unclassified ? (
              <button className={signalFilter === "unclassified" ? "on" : ""}
                      title="the run did not state a POSITIVE/NEUTRAL/NEGATIVE signal for these"
                      onClick={() => setSignalFilter("unclassified")}
                      style={{ color: "var(--z-org)" }}>Unclassified · {unclassified}</button>
            ) : null}
          </div>
        </div>
        {unclassified ? (
          <div className="co co-org" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={14} />
            <div>
              <div className="co-title">{unclassified} of {allEvents.length} events carry no signal</div>
              <div className="co-body">
                The clustering needs POSITIVE, NEUTRAL or NEGATIVE per event. These
                are shown in date order and excluded from the three buckets — the
                run has to state the direction for them to cluster.
              </div>
            </div>
          </div>
        ) : null}

        {/* Range slider */}
        <div style={{ background: "var(--z-lav)", padding: "12px 16px", borderRadius: 8, marginBottom: 14 }}>
          <div className="row" style={{ marginBottom: 8, fontSize: 11, color: "var(--z-muted)" }}>
            <Icon name="calendar" size={12} />
            <span>Time range</span>
            <span className="spacer" />
            <strong style={{ color: "var(--z-dark)" }}>{yearRange[0]} – {yearRange[1]}</strong>
          </div>
          <RangeSlider min={_lo} max={_hi} value={yearRange} onChange={setYearRange} />
        </div>

        {/* The promoted storyline: the arc the events describe, which the
            Surface Spec calls the tie back to the DMA. It was adapted onto
            `timelineMeta` and read by no component. */}
        {(() => {
          const meta = DMA.timelineMetaFor(entity.id);
          if (!meta || !meta.storyline) return null;
          return (
            <div style={{ background: "var(--z-lav)", borderLeft: "3px solid var(--z-dpur)", borderRadius: "0 8px 8px 0", padding: "10px 14px", marginBottom: 14 }}>
              <div className="row" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>Storyline</span>
                {meta.arc_shape ? <span className="b b-purple" style={{ marginLeft: 6 }}>{meta.arc_shape}</span> : null}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>{meta.storyline}</div>
            </div>
          );
        })()}

        <InteractiveTimeline events={events} setHoverEvent={setHoverEvent} setSelectedEvent={setSelectedEvent} selectedEvent={selectedEvent} hoverEvent={hoverEvent} />

        {selectedEvent !== null && events[selectedEvent] ? (
          <EventDetail event={events[selectedEvent]} onClose={() => setSelectedEvent(null)} openEvidence={openEvidence} openSubcap={openSubcap} />
        ) : null}
      </div>

      {/* Issue register Gantt */}
      <div className="card flush" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <h3>Issue register · Gantt</h3>
          {/* Counted from the statuses the run actually uses. Hardcoding OPEN and
              RESOLVED printed "0 OPEN · 0 RESOLVED" against REMEDIATED / ACTIVE /
              NEW OBLIGATION. */}
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {Object.entries(issues.reduce((a, i) => { const k = i.status || "unstated"; a[k] = (a[k] || 0) + 1; return a; }, {}))
              .map(([k, n]) => `${n} ${k}`).join(" · ")} · click any bar for detail
          </span>
        </div>
        <div className="card-body">
          <InteractiveGantt issues={issues} issueOpen={issueOpen} setIssueOpen={setIssueOpen} />
          {/* The detail panel lives HERE, inside the register — but the
              regulatory panel further down opens it too, and from there the
              panel appears a screen and a half above the click. It read as a
              dead control. Anchored so a caller can bring it into view. */}
          <div id="issue-detail-anchor">
            {issueOpen ? <IssueDetail issue={issues.find(i => i.id === issueOpen)} entity={entity} onClose={() => setIssueOpen(null)} openEvidence={openEvidence} /> : null}
          </div>
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
        <RegulatoryStanding entity={entity} issues={issues}
                            setIssueOpen={setIssueOpen} openEvidence={openEvidence} />
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
          <SentimentGridInteractive sentOpen={sentOpen} setSentOpen={setSentOpen} openEvidence={openEvidence} entity={entity} />
        </div>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="stack" size={16} />
            <div style={{ fontWeight: 600, fontSize: 13 }}>Acquisition history</div>
          </div>
          {/* The promoted acquisition rows. This was an inline two-item FCE
              fixture (Hudson Valley CU branches, Cazenovia Credit) whose
              declared `evidence: []` was never rendered anyway — so every
              client was shown another institution's M&A history with no
              citations. */}
          {!(DMA.ACQUISITIONS || []).length ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              No acquisitions or mergers promoted for this run.
            </div>
          ) : (DMA.ACQUISITIONS || []).map((a, i, arr) => (
            <div key={a.id || i} style={{ padding: "10px 0", borderBottom: i < arr.length - 1 ? "1px solid var(--z-sep)" : "none", cursor: "pointer" }} onClick={() => setAcqOpen(acqOpen === (a.id || i) ? null : (a.id || i))}>
              <div className="row">
                {/* The date slot holds a date or nothing. It used to print the
                    word "undated" in the date's own place, which reads as a
                    label on the acquisition rather than as the absence of a
                    figure — the run's dating discipline is a producer problem
                    and does not belong in a client's title row. */}
                {a.date ? (
                  <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{a.date}</span>
                ) : null}
                <div style={{ flex: 1, fontWeight: 500, fontSize: 12.5 }}>{a.target}</div>
                {a.kind ? <span className="b b-muted">{a.kind}</span> : null}
                <span className="b b-muted">{a.status}</span>
                <Icon name={acqOpen === (a.id || i) ? "chevron-u" : "chevron-d"} size={12} style={{ color: "var(--z-muted)" }} />
              </div>
              {a.impl && a.impl !== "-" ? <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>{a.impl}</div> : null}
              {acqOpen === (a.id || i) ? (
                <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--z-lav)", borderRadius: 6, fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>
                  <div>{a.details}</div>
                  {(a.subcaps || []).length ? (
                    <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 7 }}>
                      <span style={{ fontSize: 10, color: "var(--z-muted)" }}>AFFECTS</span>
                      {a.subcaps.map(sid => <span key={sid} className="chip purple">{sid}</span>)}
                    </div>
                  ) : null}
                  {(a.evidence || []).length ? (
                    <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 7 }}>
                      <span style={{ fontSize: 10, color: "var(--z-muted)" }}>EVIDENCE</span>
                      {a.evidence.map(eid => (
                        <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
                          onClick={ev => { ev.stopPropagation(); openEvidence(eid); }}>{eid}</button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Regulatory standing (C3) ────────────────────────────────────────
   Every field here is promoted. The card previously printed the DIRECTORY
   row's three identity fields and then a hardcoded open-enforcement callout
   pointing at IS-014 with a "View evidence" button hardcoded to E-218 — an
   issue and an evidence id that exist in the prototype fixture and in no real
   run. That is why the card read close to empty and why the button opened a
   drawer with nothing in it.

   A run with no enforcement action is the common case, and it is a FINDING,
   not a blank: `absence_of_enforcement` carries the ladder that establishes
   it, and the card states what was searched. */
function RegulatoryStanding({ entity, issues, setIssueOpen, openEvidence }) {
  const reg = DMA.regulatoryFor(entity.id);
  const [openLadder, setOpenLadder] = useState(false);
  if (!reg) {
    return (
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <Icon name="shield" size={16} />
          <div style={{ fontWeight: 600, fontSize: 13 }}>Regulatory standing</div>
        </div>
        <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
          The regulatory standing section did not promote for this run.
        </div>
      </div>
    );
  }
  const list = (v) => Array.isArray(v) ? v.filter(Boolean) : (v ? [v] : []);
  const actions = list(reg.enforcement_actions);
  const absence = reg.absence_of_enforcement || null;
  const searched = list(absence && absence.sources_searched);
  // Issues the register carries against a regulatory matter, by id — the link
  // is the issue's own, never a constant.
  const regIssues = (issues || []).filter(
    i => /regulat|enforce|compliance|breach|consent/i.test(
      `${i.title || ""} ${i.desc || ""} ${i.kind || ""}`));

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="shield" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Regulatory standing</div>
        <span className="spacer" />
        {actions.length
          ? <span className="b b-below">{actions.length} action{actions.length === 1 ? "" : "s"}</span>
          : (absence && absence.verified ? <span className="b b-above">No action found</span> : null)}
      </div>
      <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.65 }}>
        <Row k="Primary regulator" v={reg.primary_regulator || entity.regulator} />
        {list(reg.additional_regulators).length ? (
          <Row k="Also regulated by" v={list(reg.additional_regulators).join(" · ")} />
        ) : null}
        <Row k="License type" v={reg.license_type || entity.license} />
        <Row k="Jurisdictions" v={list(reg.jurisdictions).join(" · ")
                                  || (entity.footprint || []).join(" · ") || "—"} />
        {reg.charter_date ? <Row k="Chartered" v={String(reg.charter_date).slice(0, 4)} /> : null}
        <div className="sep" />

        {actions.length ? actions.map((a, i) => (
          <div key={a.action_id || i} className="co co-org" style={{ marginBottom: 8 }}>
            <Icon name="warn" size={14} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="co-title">
                {a.kind || "Enforcement action"}
                {a.dated_on ? ` · ${a.dated_on}` : ""}
                {a.status ? ` · ${a.status}` : ""}
              </div>
              <div className="co-body">{a.summary || a.title || "—"}</div>
              {(a.e_ids || []).length ? (
                <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 6 }}>
                  {a.e_ids.map(eid => (
                    <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
                            onClick={() => openEvidence(eid)}>{eid}</button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        )) : (
          <div className="co co-teal">
            <Icon name="check" size={14} />
            <div style={{ flex: 1 }}>
              <div className="co-title">
                {absence && absence.verified
                  ? "No enforcement action found · searched and verified"
                  : "No enforcement action recorded"}
              </div>
              <div className="co-body">
                {absence && absence.statement
                  ? absence.statement
                  : (searched.length
                      ? `Established against ${searched.length} source${searched.length === 1 ? "" : "s"}.`
                      : "The run recorded no action and no search ladder, so this is an absence of record rather than a verified absence.")}
              </div>
              {searched.length ? (
                <>
                  <button className="btn btn-tertiary btn-sm" style={{ marginTop: 8 }}
                          onClick={() => setOpenLadder(o => !o)}>
                    {openLadder ? "Hide" : "Show"} what was searched
                    <Icon name={openLadder ? "chevron-u" : "chevron-d"} size={12} />
                  </button>
                  {openLadder ? (
                    <ul style={{ margin: "8px 0 0 16px", fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.6 }}>
                      {searched.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        )}

        {/* Register matters that bear on regulatory standing, linked by their
            own ids so the click lands on a real issue. */}
        {regIssues.length ? (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
              On the issue register
            </div>
            {regIssues.map(i => (
              <div key={i.id} className="co co-org" style={{ cursor: "pointer", marginBottom: 6 }}
                   onClick={() => {
                     setIssueOpen(i.id);
                     // Take the reader to the panel the click just opened.
                     // Without this the state changed and the page did not,
                     // because the detail renders up inside the register.
                     requestAnimationFrame(() => {
                       const el = document.getElementById("issue-detail-anchor");
                       if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                     });
                   }}>
                <Icon name="warn" size={14} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="co-title">{i.status || "OPEN"} · {i.id}</div>
                  <div className="co-body">{i.title || i.desc} · click for the cells it caps</div>
                </div>
                <Icon name="arrow-r" size={12} />
              </div>
            ))}
          </div>
        ) : null}

        {(reg.e_ids || []).length ? (
          <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 10 }}>
            <span style={{ fontSize: 10, color: "var(--z-muted)" }}>EVIDENCE</span>
            {reg.e_ids.map(eid => (
              <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
                      onClick={() => openEvidence(eid)}>{eid}</button>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 10 }}>
            This section cites no evidence ids.
          </div>
        )}
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
  // The prototype's fixture dated events YYYY-MM, so it appended "-01" to make
  // a parseable date. The contract's `event_date` is a full DATE and arrives
  // YYYY-MM-DD, which made this "2016-01-01-01" — an Invalid Date, so every
  // pct was NaN and all ten dots and their labels stacked at the same point.
  // That is the overlapping text on this page. Parse what actually arrives.
  const at = (d) => {
    if (!d) return null;
    const s = String(d);
    const t = Date.parse(/^\d{4}-\d{2}$/.test(s) ? `${s}-01` : s);
    return Number.isNaN(t) ? null : t;
  };
  const stamps = events.map(e => at(e.date)).filter(t => t !== null);
  const minDate = stamps.length ? Math.min(...stamps) : 0;
  const maxDate = stamps.length ? Math.max(...stamps) : 1;
  const span = Math.max(1, maxDate - minDate);
  const TONE = { positive: "var(--z-mid)", negative: "var(--z-below)",
                 neutral: "var(--z-purple)", unclassified: "var(--z-org)" };

  return (
    <div style={{ position: "relative", padding: "20px 8px 50px" }}>
      <div style={{ position: "relative", height: 2, background: "var(--z-sep)", margin: "30px 16px" }}>
        {events.map((e, i) => {
          const t = at(e.date);
          // An undated event has no position on a time axis. It renders in the
          // label row below with "undated" rather than being placed at zero,
          // which would read as the earliest event in the run.
          if (t === null) return null;
          const pct = ((t - minDate) / span) * 100;
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
      {/* The label row is a grid of equal columns, so the labels never overlap
          however close two events are on the axis above. Each is clickable —
          the dot is 16px and the title is the real target. */}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${events.length}, minmax(0, 1fr))`, gap: 6, fontSize: 9.5, color: "var(--z-muted)", padding: "0 8px" }}>
        {events.map((e, i) => (
          <button key={e.id} onClick={() => setSelectedEvent(i === selectedEvent ? null : i)}
            onMouseEnter={() => setHoverEvent(i)} onMouseLeave={() => setHoverEvent(null)}
            title={e.date ? `${e.date} · ${e.title}` : e.title}
            style={{ textAlign: "center", lineHeight: 1.4, background: "none",
                     border: 0, padding: 0, cursor: "pointer", minWidth: 0 }}>
            <div className="f-mono" style={{ color: hoverEvent === i || selectedEvent === i ? TONE[e.signal] : "var(--z-muted)" }}>{e.date || ""}</div>
            <div className="txt-fit-2" style={{ fontSize: 9.5, color: hoverEvent === i || selectedEvent === i ? "var(--z-dark)" : "var(--z-muted)", fontWeight: hoverEvent === i ? 600 : 400 }}>{e.title}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* The event drilldown. It used to print a generic sentence chosen by signal —
   the same three sentences for every event in every run — and never showed the
   event's own body, its maturity effect, or the cells it touches. That is why
   the drilldown read as though it had no detail: the detail was promoted and
   unread. `openSubcap` makes each affected cell clickable, which is the link
   from a historical event back to the DMA that was missing. */
function EventDetail({ event, onClose, openEvidence, openSubcap }) {
  const TONE = { positive: "var(--z-mid)", negative: "var(--z-below)",
                 neutral: "var(--z-purple)", unclassified: "var(--z-org)" };
  const caps = event.capabilities && event.capabilities.length
    ? event.capabilities : (event.cap_impact ? [event.cap_impact] : []);
  return (
    <div style={{ marginTop: 16, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${TONE[event.signal] || "var(--z-sep)"}` }}>
      <div className="row" style={{ marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
        <span className="f-mono" style={{ fontSize: 11, color: "var(--z-muted)" }}>{event.date || ""}</span>
        <strong style={{ fontSize: 14, flex: 1, minWidth: 0 }}>{event.title}</strong>
        {event.kind ? <span className="b b-purple">{event.kind}</span> : null}
        {event.claim ? <span className="b b-muted">{event.claim}</span> : null}
        {event.signal === "unclassified"
          ? <span className="b b-org" title={event.signal_raw || ""}>NO SIGNAL STATED</span>
          : <span className="b b-muted">{String(event.signal).toUpperCase()}</span>}
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>

      {/* What happened — the producer's own words. */}
      {event.detail ? (
        <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 10 }}>
          {event.detail}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 10 }}>
          The run recorded this event with no body text.
        </div>
      )}

      {/* What it did to maturity — read, never generated from the signal. */}
      <div style={{ background: "rgba(255,255,255,.6)", border: "1px solid var(--z-sep)", borderRadius: 6, padding: "8px 10px", marginBottom: 10 }}>
        <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>
          Effect on maturity
        </div>
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>
          {event.maturity_effect
            || (event.signal === "unclassified"
                ? "Not stated. The run did not classify this event's direction, so no effect is claimed here."
                : "The run stated a signal but no effect. Nothing is inferred from the signal alone.")}
        </div>
      </div>

      {caps.length ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Affects:</span>
          {caps.map(cid => (
            <button key={cid} className="chip purple" style={{ cursor: "pointer", border: 0 }}
                    onClick={() => openSubcap && openSubcap(cid)}>{cid}</button>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 8 }}>
          No capability linked — this event is context, not a scored constraint.
        </div>
      )}

      {(event.evidence || []).length > 0 ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Evidence:</span>
          {event.evidence.map(eid => {
            const e = DMA.getEvidence(eid);
            const tier = e?.tier || "T3";
            return <button key={eid} className={`tier-chip tier-${tier}`}
                           title={e ? `${e.title} · ${e.source_pretty}` : eid}
                           onClick={() => openEvidence(eid)}>{eid} · {tier}</button>;
          })}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
          This event cites no evidence.
        </div>
      )}
    </div>
  );
}

function InteractiveGantt({ issues, issueOpen, setIssueOpen }) {
  const all = issues || [];
  const undated = all.filter(i => !i.start);
  const dated = all.filter(i => i.start);
  if (!dated.length) {
    return (
      <div className="empty" style={{ padding: "18px 0" }}>
        <h3>No dated issues</h3>
        <p>{undated.length
          ? `${undated.length} issue${undated.length === 1 ? "" : "s"} recorded without an opened date — a time axis needs a date.`
          : "No issues recorded for this run."}</p>
      </div>
    );
  }
  /* The window comes from the issues, not from a constant.

     The axis was hardcoded to start 2024-01-01 and span 36 months, so an issue
     opened 2021-10 computed left:-75% width:162% — the bar began five hundred
     pixels left of its own lane and painted its white text over the id chip and
     the severity badge. That is the overlapping text on this page. The axis now
     covers the issues it is drawing, and every bar is clamped inside it. */
  const at = (d) => {
    if (!d) return null;
    const str = String(d);
    const t = Date.parse(/^\d{4}-\d{2}$/.test(str) ? `${str}-01` : str);
    return Number.isNaN(t) ? null : t;
  };
  const now = Date.now();
  const stamps = [];
  for (const i of dated) {
    const a = at(i.start), b = i.end ? at(i.end) : now;
    if (a !== null) stamps.push(a);
    if (b !== null) stamps.push(b);
  }
  const lo = Math.min(...stamps);
  const hi = Math.max(...stamps, now);
  const span = Math.max(1, hi - lo);
  const pct = (t) => ((t - lo) / span) * 100;
  const yearOf = (t) => new Date(t).getUTCFullYear();
  // One tick per year actually inside the window, labelled with that year —
  // the old strip printed four year labels and two quarter labels over a
  // three-year span, with "2027" sitting above 2026-Q4.
  const years = [];
  for (let y = yearOf(lo); y <= yearOf(hi); y++) years.push(y);

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 12, fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
        <div></div>
        <div style={{ position: "relative", height: 14 }}>
          {years.map(y => {
            const t = Date.parse(`${y}-01-01`);
            const left = Math.max(0, Math.min(100, pct(t)));
            return (
              <div key={y} style={{ position: "absolute", left: `${left}%`, top: 0, paddingLeft: 4, borderLeft: "1px dashed var(--z-sep)", height: 14 }}>{y}</div>
            );
          })}
        </div>
      </div>
      {dated.map(iss => {
        const a = at(iss.start);
        const b = iss.end ? (at(iss.end) ?? now) : now;
        const left = Math.max(0, Math.min(100, pct(a)));
        const right = Math.max(0, Math.min(100, pct(Math.max(b, a))));
        const width = Math.max(2, right - left);
        const color = iss.severity === "CRITICAL" ? "var(--z-below)" : iss.severity === "MATERIAL" ? "var(--z-org)" : "var(--z-muted)";
        const isOpen = issueOpen === iss.id;
        const capped = Object.keys((DMA.ISSUE_CAPS[iss.id] || {}).caps || {}).length;
        return (
          <button key={iss.id} onClick={() => setIssueOpen(isOpen ? null : iss.id)}
            style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 12, padding: "8px 0", borderTop: "1px solid var(--z-sep)", textAlign: "left", width: "100%", background: isOpen ? "var(--z-lav)" : "transparent", border: "0", borderRadius: 6 }}>
            <div style={{ padding: "0 8px", minWidth: 0 }}>
              <div className="row">
                <span className="chip">{iss.id}</span>
                {iss.severity ? <span className={`b ${iss.severity === "CRITICAL" ? "b-below" : iss.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{iss.severity}</span> : null}
                {capped ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} title={`${capped} cell${capped === 1 ? "" : "s"} capped`} /> : null}
              </div>
              <div style={{ fontSize: 12, marginTop: 4 }} className="txt-fit-1" title={iss.title || iss.type || ""}>{iss.title || iss.type || "—"}</div>
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>{iss.status}{iss.cap_value ? ` · cap ${iss.cap_value}` : ""}</div>
            </div>
            <div style={{ position: "relative", height: 28 }}>
              <div title={`${iss.start}${iss.end ? ` → ${iss.end}` : " → open"} · ${iss.desc || ""}`}
                   style={{ position: "absolute", left: `${left}%`, width: `${width}%`, height: 18, top: 5, background: color, borderRadius: 4, opacity: .85, display: "flex", alignItems: "center", padding: "0 6px", color: "#fff", fontSize: 10, fontWeight: 500, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                {iss.desc}
              </div>
            </div>
          </button>
        );
      })}
      {/* Undated issues are listed rather than dropped: the page head counts
          them, so silently omitting three of five made the chart disagree with
          its own header. */}
      {undated.length ? (
        <div style={{ borderTop: "1px solid var(--z-sep)", paddingTop: 10, marginTop: 6 }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
            Not yet placed on the time axis · {undated.length}
          </div>
          {undated.map(iss => (
            <button key={iss.id} onClick={() => setIssueOpen(issueOpen === iss.id ? null : iss.id)}
              style={{ display: "flex", gap: 8, alignItems: "center", width: "100%", textAlign: "left", background: issueOpen === iss.id ? "var(--z-lav)" : "transparent", border: 0, borderRadius: 6, padding: "6px 8px", cursor: "pointer" }}>
              <span className="chip">{iss.id}</span>
              {iss.severity ? <span className="b b-muted">{iss.severity}</span> : null}
              <span style={{ flex: 1, minWidth: 0, fontSize: 12 }} className="txt-fit-1" title={iss.title || ""}>{iss.title || iss.type || "—"}</span>
              <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{iss.status}</span>
            </button>
          ))}
        </div>
      ) : null}
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
        <strong style={{ fontSize: 14 }}>{issue.title || issue.type || "—"}</strong>
        <span className={`b ${issue.severity === "CRITICAL" ? "b-below" : issue.severity === "MATERIAL" ? "b-org" : "b-muted"}`}>{issue.severity}</span>
        <span className="b b-muted">{issue.status}</span>
        <span className="spacer" />
        <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>
      <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 14 }}>{issue.desc}</div>
      {caps.length === 0 ? (
        <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginBottom: 12 }}>
          This matter names no capability cell, so it is not linked to the
          assessment. An issue that constrains a capability should say which.
        </div>
      ) : null}
      {caps.length > 0 ? (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8 }}>Cells this matter bears on · {caps.length}</div>
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
                  {/* A cap LEVEL is only shown when the run states one; the
                      linkage alone does not imply a ceiling. */}
                  <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>
                    {capValue != null
                      ? `Score capped at M${capValue}`
                      : (s.score != null ? `Assessed ${fx(s.score, 1)} · no cap level stated` : "no cap level stated")}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {/* The issue's OWN cited ids. This used to prefix-sweep the entire
          evidence store for anything sharing four characters with a capped
          cell — and since the caps map was empty in LIVE, it swept nothing, so
          every issue showed no evidence while carrying an e_id of its own. */}
      {(() => {
        const own = issue.evidence || [];
        const ev = own.map(eid => DMA.getEvidence(eid) || { id: eid, tier: "T3" });
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
        {caps.length ? (
          <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/heatmap`, { hm: "standard", zoom: "subcap", subcap: caps[0][0] })}>Open {caps[0][0]} in the heatmap <Icon name="arrow-r" size={11} /></button>
        ) : null}
      </div>
    </div>
  );
}

function FinChartInteractive({ entity, hoveredYear, setHoveredYear }) {
  /* The promoted financial series, and only that.

     This chart used to MANUFACTURE five years of balance sheet:

       baseAssets = entity.assets || 11e9
       cagr       = entity.cagr   || 0.06
       val        = baseAssets * (1 + cagr)^(i - 4)

     — a compounded curve from a default asset figure and a default growth rate,
     rendered as this institution's five-year trajectory. With `assets` stated
     in billions (6.5) and then divided by 1e9, every bar read "$0.0B", and the
     footer printed a 6.0% CAGR nobody measured. Inventing a trend line is the
     single most quotable fabrication on the page: an AE reads growth off it.

     The run promotes three dated points (FY2023 5.8, 2025-Q3 6.24, 2025-12
     6.5) with a stated trend. Three is what it has, so three is what renders. */
  const f = DMA.financialsFor(entity.id);
  const pts = ((f && f.fy) || []).map((label, i) => ({
    label,
    val: (f.total_assets || [])[i],
  })).filter(p => p.val != null);

  if (!pts.length) {
    return (
      <div style={{ fontSize: 12, color: "var(--z-muted)", padding: "8px 0" }}>
        No dated financial points promoted for this run, so no trajectory is drawn.
      </div>
    );
  }
  const unit = (f && f.unit) || "";
  const max = Math.max(...pts.map(p => p.val));
  const money = (v) => `${fx(v, v >= 100 ? 0 : 1)}${unit}`;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 140, padding: "0 8px" }}>
        {pts.map(d => (
          <div key={d.label} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
               onMouseEnter={() => setHoveredYear(d.label)} onMouseLeave={() => setHoveredYear(null)}
               title={`${d.label} · ${money(d.val)}`}>
            <div style={{ fontSize: 10, color: hoveredYear === d.label ? "var(--z-teal)" : "var(--z-muted)", fontWeight: hoveredYear === d.label ? 700 : 400 }}>${money(d.val)}</div>
            <div style={{ width: "100%", height: `${(d.val / max) * 120}px`, background: hoveredYear === d.label ? "linear-gradient(180deg, var(--z-mid), var(--z-dark2))" : "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0", transition: "background 160ms" }} />
            <div style={{ fontSize: 10, color: "var(--z-muted)" }} className="txt-fit-1">{d.label}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 10, padding: 8, background: "var(--z-lav)", borderRadius: 6, fontSize: 11, color: "var(--z-body)" }}>
        {pts.length} dated point{pts.length === 1 ? "" : "s"}
        {f && f.cagr != null ? <> · CAGR <strong style={{ color: "var(--z-mid)" }}>{fx(f.cagr * 100, 1)}%</strong>{f.cagr_basis ? ` (${f.cagr_basis})` : ""}</> : null}
        {f && f.trend ? <> · trend <strong>{f.trend}</strong></> : null}
        {f && f.basis ? <span style={{ color: "var(--z-muted)" }}> · {f.basis}</span> : null}
        {pts.length < 3 ? <span style={{ color: "var(--z-muted)" }}> · fewer than three points: no trend is claimed</span> : null}
      </div>
    </div>
  );
}

function SentimentGridInteractive({ sentOpen, setSentOpen, openEvidence, entity }) {
  /* Promoted sentiment only.

     This grid was a hardcoded three-item FCE fixture — Glassdoor 3.8 (n=412),
     App Store 3.4 (n=8,200), a CFPB index of 24, drilldown prose asserting
     "Caps P2C2.1.1 at M3", and evidence chips E-236 and E-271 — rendered under
     whichever real client was open. Clicking one of those chips opened the
     drawer saying the id does not resolve and "a citation that does not resolve
     is a producer defect": the app blaming the producer for its own fixture. */
  /* This card reads the CONTEXT page's own section, not the overview's bars.
     They are different sections with different grains — `context_sentiment`
     carries tiles per audience, each with the measured rows behind it — and
     reading the wrong one is why a promoted section rendered as "nothing
     promoted". The accessor falls back to the overview bars for a run that
     promoted only those. */
  const sent = typeof DMA.contextSentimentFor === "function"
    ? DMA.contextSentimentFor(entity && entity.id)
    : DMA.sentimentFor(entity && entity.id);
  const groups = (sent && sent.groups) || null;
  const rows = [];
  for (const g of Object.keys(groups || {})) {
    for (const b of groups[g] || []) {
      rows.push({ id: `${g}-${b.label}`, group: g, ...b });
    }
  }
  // A tile the producer worked and could not fill is a finding with a ladder
  // behind it, not an empty card: it names what was searched.
  const absent = (sent && sent.absent) || [];
  if (!rows.length) {
    return (
      <div style={{ fontSize: 12, color: "var(--z-muted)", lineHeight: 1.6 }}>
        {absent.length ? (
          absent.map((a, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <strong style={{ color: "var(--z-body)", textTransform: "uppercase", fontSize: 10, letterSpacing: ".08em" }}>{a.group}</strong>
              {a.note ? <> — {a.note}</> : <> — searched and not established.</>}
              {(a.sources_searched || []).length ? (
                <> Searched: {a.sources_searched.join(" · ")}.</>
              ) : null}
            </div>
          ))
        ) : (
          <>
            No sentiment measures promoted for this run.
            {sent && sent.sources_searched && sent.sources_searched.length ? (
              <> Searched: {sent.sources_searched.join(" · ")}.</>
            ) : null}
          </>
        )}
      </div>
    );
  }
  return (
    <div className="g3" style={{ gap: 10 }}>
      {rows.map(s => {
        const isOpen = sentOpen === s.id;
        return (
          <div key={s.id}>
            <button onClick={() => setSentOpen(isOpen ? null : s.id)} className="card-tile clickable" style={{ padding: 10, width: "100%", textAlign: "left", border: isOpen ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)" }}>
              <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{s.group}</div>
              <div className="row" style={{ marginTop: 4 }}>
                <span style={{ fontSize: 18, fontWeight: 600 }}>{fx(s.value, 1)}{s.scale ? <span style={{ fontSize: 11, color: "var(--z-muted)", fontWeight: 400 }}> {s.scale}</span> : null}</span>
                <span className="spacer" />
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={11} style={{ color: "var(--z-muted)" }} />
              </div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }} className="txt-fit-1"
                   title={`${s.label}${s.n != null ? ` · n=${s.n}` : ""}`}>
                {s.label}{s.n != null ? ` · n=${Number(s.n).toLocaleString()}` : ""}
              </div>
            </button>
            {isOpen ? (
              <div style={{ marginTop: 6, padding: "10px 12px", background: "var(--z-lav)", borderRadius: 6, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55 }}>
                {s.note || s.reading || "The run stated this measure with no reading."}
                {(s.e_ids || []).length ? (
                  <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 7 }}>
                    {s.e_ids.map(eid => (
                      <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
                              onClick={() => openEvidence(eid)}>{eid}</button>
                    ))}
                  </div>
                ) : null}
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
                // Age is computed or null — never NaN, and never computed
                // from a date that is not there. An item whose recency is
                // absent gets no age and no freshness verdict, because both
                // would be assertions about a date nobody established.
                const raw = typeof e.recency === "string" ? e.recency : null;
                const parsed = raw
                  ? new Date(raw.replace("Q1","-01-01").replace("Q2","-04-01")
                                .replace("Q3","-07-01").replace("Q4","-10-01"))
                  : null;
                const age = (parsed && !isNaN(parsed))
                  ? Math.round((new Date() - parsed) / (1000*60*60*24*30.4)) : null;
                const stale = age === null ? null : age > 18;
                return (
                  <tr key={e.id}>
                    <td><span className="chip">{e.id}</span> <span style={{ marginLeft: 6 }}>{e.title}</span></td>
                    <td className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{e.source.split("/")[0]}</td>
                    <td>{raw || "—"}</td>
                    <td>{age === null ? "—" : `${age} mo`}</td>
                    <td style={{ textAlign: "right" }}>
                      {stale === null ? <span className="b b-muted">NO DATE</span>
                        : <span className={`b ${stale ? "b-org" : "b-teal"}`}>{stale ? "STALE" : "FRESH"}</span>}
                    </td>
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
  // A version diff needs BOTH runs' scores. The prototype had only one run's
  // data, so it synthesised the base from the target:
  //   base = score - 0.2 - (id.charCodeAt(2) % 5) / 12
  // — a per-cell offset derived from a character of the cell id. Under a real
  // client that renders as movement between two assessments that never
  // happened, with deltas an AE would take into a meeting. In LIVE the base run
  // has to be READ, and until the two-run read path exists this states what it
  // needs rather than inventing it.
  const isLive = typeof window !== "undefined" && !!window.DMA_LIVE;
  if (isLive) {
    return (
      <div className="card">
        <div className="card-head"><h3>Version diff</h3></div>
        <div className="empty" style={{ padding: 24 }}>
          <div className="icon"><Icon name="info" size={20} /></div>
          <h3>Comparing two runs needs both runs' cell scores</h3>
          <p>
            This client has {entity.runs.length} run{entity.runs.length === 1 ? "" : "s"} in
            the register. A diff reads the cell grain of each run and reports the
            movement between them; it is never derived from one run.
            {entity.runs.length < 2
              ? " With a single run there is nothing to compare yet."
              : " The two-run cell read is not wired up yet, so no diff is shown rather than an approximated one."}
          </p>
        </div>
      </div>
    );
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

/* The four technology layers, at module scope because BOTH the register and
   the per-product detail name them and the detail used to reach for a field
   (`layer_full`) that no adapter sets. One map, one source of the names.

   No `primary_gap` here. It used to be hardcoded true on CUST, so every
   client's customer layer wore PRIMARY GAP LAYER whatever their register
   said — and on this one CUST is the BEST covered layer (11 confirmed of 23)
   while DATA has none confirmed at all. It is a judgement the payload makes,
   per layer, in `layers[].is_primary_gap`. */
const TS_LAYERS = ["OPS", "CUST", "DATA", "INFRA"];
const TS_LAYER_LABEL = {
  OPS:   { name: "Operations & core banking",  short: "Operations", dma: "P3" },
  CUST:  { name: "Customer engagement",        short: "Customer",   dma: "P2" },
  DATA:  { name: "Data & analytics",           short: "Data",       dma: "P4" },
  INFRA: { name: "Infrastructure & cloud",     short: "Infra",      dma: "P4" },
};

/* ── Tech stack overview (s41) ───────────────────────────────────── */
function ClientTechStack({ entity, run }) {
  const { pushToast } = useApp();
  const [layer, setLayer] = useState("ALL");
  const [hideAbsent, setHideAbsent] = useState(false);
  // The status filter the stat strip toggles. It lives in the same predicate
  // as the layer select and the hide-absent switch, so a tile click and the
  // filter bar always agree on what the register shows.
  const [statusFilter, setStatusFilter] = useState(null);
  // Layer briefly highlighted after a PRIMARY GAP tile click.
  const [flashLayer, setFlashLayer] = useState(null);

  const allTech = DMA.TECH_STACK;
  const layerRollup = DMA.TECH_LAYERS || [];
  const list = useMemo(() => allTech.filter(t => {
    if (layer !== "ALL" && t.layer !== layer) return false;
    if (statusFilter && t.status !== statusFilter) return false;
    if (hideAbsent && t.status === "ABSENT") return false;
    return true;
  }), [layer, hideAbsent, statusFilter]);

  // Charter correction: the layer keys are OPS · CUST · DATA · INFRA, not
  // L2–L5. L1–L4 already name the EVIDENCE levels, and a register row showing
  // "L3" next to an evidence level "L3" means two different things in the same
  // row. Same four labels, same layout, unambiguous keys.
  const LAYERS = TS_LAYERS;
  const LAYER_LABEL = TS_LAYER_LABEL;
  const byLayer = {};
  LAYERS.forEach(L => byLayer[L] = list.filter(t => t.layer === L));

  // Layer keys are OPS · CUST · DATA · INFRA (charter correction); the
  // customer-engagement and data layers are the ones whose absence gates
  // downstream AI/decisioning work.
  const absentCount = allTech.filter(t => t.status === "ABSENT" && (t.layer === "CUST" || t.layer === "DATA")).length;

  // The layers the promoted rollup flags — the PRIMARY GAP tile locates the
  // flagged card rather than filtering, because the flag belongs to a LAYER,
  // not to rows a status filter could select.
  const gapLayers = layerRollup.filter(x => x && x.is_primary_gap).map(x => x.layer);
  const goToPrimaryGap = () => {
    const L = gapLayers[0];
    if (!L) return;
    // Locate, never filter — but a card the current filters hide entirely
    // cannot be scrolled to, so relax exactly what hides it and nothing else.
    if (layer !== "ALL" && layer !== L) setLayer("ALL");
    const rows = allTech.filter(t => t.layer === L);
    const anyVisible = rows.some(t =>
      (!statusFilter || t.status === statusFilter) && !(hideAbsent && t.status === "ABSENT"));
    if (rows.length && !anyVisible) { setStatusFilter(null); setHideAbsent(false); }
    setFlashLayer(L);
  };
  // Scroll after render, so the card exists even when the click above had to
  // relax a filter first; the highlight clears itself.
  useEffect(() => {
    if (!flashLayer) return;
    const el = document.getElementById(`ts-layer-${flashLayer}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    const tm = window.setTimeout(() => setFlashLayer(null), 2400);
    return () => window.clearTimeout(tm);
  }, [flashLayer]);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Technology intelligence</div>
          <h1>Technology stack - {entity.name}</h1>
          {/* The register's own facts: how many rows, at what detection level.
              This used to read "Explorium synced <date>" — a vendor this app
              does not call, beside the ASSESSMENT date rather than any sync. */}
          <div className="sub">
            {allTech.length} product{allTech.length === 1 ? "" : "s"} across four
            layers · detection level per row, from the run's own evidence
          </div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${entity.name} tech stack as CSV…`, "success")}><Icon name="download" size={13} /> Export</button>
        </div>
      </div>

      {/* Status legend + filters.
          Four statuses, matching the charter and the payload contract:
          CONFIRMED · INFERRED · CLAIMED · ABSENT. The old legend showed
          "Partial", which is not one of them and which no row can ever carry,
          and hung a grey caption off each one naming Explorium — a vendor this
          app does not use. Those captions were redundant with the label and
          wrong about the source, so they are gone; the status itself is the
          claim, and each ROW states its own detection basis. */}
      <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <div className="eyebrow" style={{ margin: 0 }}>Legend</div>
          {[
            { label: "Confirmed", key: "CONFIRMED", c: "var(--z-mid)",   bg: "var(--z-ice)",  bd: "rgba(39,187,175,.4)" },
            { label: "Inferred",  key: "INFERRED",  c: "var(--z-dpur)",  bg: "var(--ph0-lt)", bd: "var(--ph0-bd)" },
            { label: "Claimed",   key: "CLAIMED",   c: "#7C3500",        bg: "rgba(254,151,50,.08)", bd: "rgba(254,151,50,.3)" },
            { label: "Absent",    key: "ABSENT",    c: "var(--z-below)", bg: "rgba(194,80,8,.06)",   bd: "rgba(194,80,8,.25)" },
          ].map(s => {
            const n = allTech.filter(t => t.status === s.key).length;
            return (
              <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--z-body)" }}>
                <span style={{ width: 14, height: 14, background: s.bg, border: `1.5px solid ${s.bd}`, borderRadius: 3 }} />
                <strong style={{ color: s.c }}>{s.label}</strong>
                <span className="muted" style={{ fontSize: 10.5 }}>{n}</span>
              </div>
            );
          })}
          <span className="spacer" />
          <div className="row" style={{ gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Layer</span>
            <select className="inp" style={{ width: 200, padding: "5px 10px", fontSize: 12 }} value={layer} onChange={e => setLayer(e.target.value)}>
              <option value="ALL">All layers</option>
              {LAYERS.map(L => <option key={L} value={L}>{LAYER_LABEL[L].name}</option>)}
            </select>
          </div>
          <label className="row" style={{ fontSize: 11.5, cursor: "pointer" }}>
            <span className={`switch ${hideAbsent ? "on" : ""}`} onClick={() => {
              const next = !hideAbsent;
              // Mirror of the tile rule: hiding absent while filtered TO
              // absent would show nothing, so the switch releases the tile.
              if (next && statusFilter === "ABSENT") setStatusFilter(null);
              setHideAbsent(next);
            }} />
            Hide absent
          </label>
        </div>
      </div>

      {/* Stat strip — a legend that filters, not one that sits there. Each
          status tile toggles the register to just its rows (press again to
          clear), through the SAME statusFilter the list predicate reads, so
          it can never disagree with the layer select or hide-absent switch.
          The PRIMARY GAP tile is different in kind: the flag belongs to a
          layer, so it scrolls to and highlights the flagged card instead.
          A zero-count tile is disabled rather than pressable-into-nothing,
          matching the timeline's signal buttons. */}
      <div className="g4" style={{ marginBottom: 14 }}>
        {[
          { l: "Confirmed",   key: "CONFIRMED", v: allTech.filter(t => t.status === "CONFIRMED").length,  c: "var(--z-mid)",   bg: "var(--z-ice)" },
          { l: "Inferred",    key: "INFERRED",  v: allTech.filter(t => t.status === "INFERRED").length,   c: "var(--z-dpur)",  bg: "var(--ph0-lt)" },
          { l: "Absent",      key: "ABSENT",    v: allTech.filter(t => t.status === "ABSENT").length,     c: "var(--z-below)", bg: "rgba(194,80,8,.06)" },
          // Counted from the promoted rollup, which states it per LAYER. It
          // used to count a per-row `primary_gap` no adapter emits, so the
          // tile read 0 on every client while a layer card wore the badge.
          { l: "Primary gap layers", key: "GAP", v: gapLayers.length, c: "var(--z-blue)", bg: "var(--ph1-lt)" },
        ].map(s => {
          const active = s.key !== "GAP" && statusFilter === s.key;
          const dead = s.v === 0;
          return (
            <button key={s.l} className="card-tile clickable" aria-pressed={active}
              disabled={dead}
              title={s.key === "GAP"
                ? (dead ? "No layer is flagged as the primary gap in this run"
                        : "Scroll to the flagged layer card")
                : (dead ? `No ${s.key} rows in this register`
                        : (active ? "Clear the status filter"
                                  : `Show only ${s.key} rows`))}
              onClick={() => {
                if (dead) return;
                if (s.key === "GAP") { goToPrimaryGap(); return; }
                const next = statusFilter === s.key ? null : s.key;
                // Filtering TO absent while hiding absent is a contradiction;
                // the tile wins and releases the switch (and the switch,
                // below, releases the tile).
                if (next === "ABSENT" && hideAbsent) setHideAbsent(false);
                setStatusFilter(next);
              }}
              style={{ borderLeft: `3px solid ${s.c}`, textAlign: "left", width: "100%",
                       fontFamily: "inherit",
                       background: active ? s.bg : "#fff",
                       boxShadow: active ? `inset 0 0 0 1.5px ${s.c}` : "none",
                       opacity: dead ? 0.45 : 1,
                       cursor: dead ? "not-allowed" : "pointer" }}>
              <div style={{ fontSize: 10, color: active ? s.c : "var(--z-muted)", fontWeight: active ? 700 : 400, letterSpacing: ".08em", textTransform: "uppercase" }}>{s.l}</div>
              <div style={{ fontSize: 28, fontWeight: 200, color: s.c, lineHeight: 1, marginTop: 6 }}>{s.v}</div>
            </button>
          );
        })}
      </div>

      {/* Layer cards */}
      {LAYERS.map(L => {
        const LM = LAYER_LABEL[L];
        const techList = byLayer[L];
        if (!techList || techList.length === 0) return null;
        // The promoted rollup decides this, and it carries its own detected /
        // expected counts. Fall back to counting the rows on screen so the
        // card still states a real ratio when the run promoted no rollup —
        // never to a constant.
        const roll = (layerRollup || []).find(x => x && x.layer === L) || null;
        const isPrimaryGap = !!(roll && roll.is_primary_gap);
        const detected = roll && roll.detected != null
          ? roll.detected : techList.filter(t => t.status !== "ABSENT").length;
        const expected = roll && roll.expected != null ? roll.expected : techList.length;
        return (
          <div key={L} id={`ts-layer-${L}`} className="card"
               style={{ marginBottom: 12, padding: 16,
                        borderColor: isPrimaryGap ? "var(--z-blue)" : "var(--z-sep)",
                        borderWidth: isPrimaryGap ? 1.5 : 1, borderStyle: "solid",
                        // The PRIMARY GAP tile's landing flash (—z-blue at 25%).
                        boxShadow: flashLayer === L ? "0 0 0 4px rgba(61,129,246,.25)" : "none",
                        transition: "box-shadow 240ms var(--ease)" }}>
            <div className="row" style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{LM.name}</div>
              {isPrimaryGap ? <span className="b b-ph1" style={{ background: "var(--ph1-lt)" }}>PRIMARY GAP LAYER</span> : null}
              <span className="spacer" />
              <span className="b b-teal">{(roll && roll.pillar_id) || LM.dma}</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{detected} of {expected} detected</span>
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

/* The row's right rail — SOURCES, derived from the row's own citations.
   ─────────────────────────────────────────────────────────────────────
   The prototype's rail carries short source-kind chips ("Explorium", "Job
   posting", "Press release") and a "Since YYYY-MM". Neither is a field the
   payload has: `techstack_items` has no source-kind column and no `as_of`
   column, so a producer that sent one would have it validated at submit and
   discarded at promotion. Rather than fake the rail from constants — the
   defect that put a 150-character detection sentence in a grey badge and
   overflowed every row — it is COMPUTED from what the row genuinely cites.

   Each chip is one DISTINCT source behind this row, labelled with the
   registrable domain of its URL and toned by the best evidence tier from that
   source. That is the same question the prototype's rail answers — what kind
   of source establishes this row — asked of data the run actually holds.

   The date line is a CITATION date, never a deployment date, and it says so:
   a press release published 2025-04 does not mean the product arrived then,
   and labelling it "Since" would assert exactly that. Rows whose citations
   carry no published date show no date line at all (invariant 9). */
function techRowSources(t) {
  const TIER_RANK = { T1: 1, T2: 2, T3: 3, T4: 4, T5: 5 };
  const byDomain = new Map();
  let newest = null;
  for (const eid of t.evidence || []) {
    const e = DMA.getEvidence(eid);
    if (!e) continue;
    const host = String(e.source || "").split("/")[0].replace(/^www\./, "");
    if (host) {
      // The registrable pair, so `vibeprospecting.explorium.ai` and
      // `explorium.ai` are one source rather than two chips saying it twice.
      const parts = host.split(".");
      const label = parts.length > 2 ? parts.slice(-2).join(".") : host;
      const rank = TIER_RANK[e.tier] || 9;
      const prev = byDomain.get(label);
      if (!prev || rank < prev.rank) byDomain.set(label, { label, rank, tier: e.tier });
    }
    if (e.published_date && (!newest || e.published_date > newest)) {
      newest = e.published_date;
    }
  }
  const chips = [...byDomain.values()].sort((a, b) => a.rank - b.rank);
  let citedTo = null;
  if (newest) {
    const d = new Date(`${String(newest).slice(0, 10)}T00:00:00Z`);
    citedTo = Number.isNaN(d.getTime())
      ? null
      : d.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
  }
  return { chips, citedTo };
}

function TechRow({ t, entity, run }) {
  const { openEvidence } = useApp();
  // The four charter statuses (CONFIRMED · INFERRED · CLAIMED · ABSENT). The
  // fourth key here was PARTIAL — a status no row can carry — so a CLAIMED row
  // fell through to the CONFIRMED palette and disagreed with the legend.
  const STATUS_STYLE = {
    CONFIRMED: { bg: "var(--z-ice)",          bd: "rgba(39,187,175,.4)", color: "var(--z-mid)" },
    INFERRED:  { bg: "var(--ph0-lt)",         bd: "var(--ph0-bd)",       color: "var(--z-dpur)" },
    ABSENT:    { bg: "rgba(194,80,8,.06)",    bd: "rgba(194,80,8,.25)",  color: "var(--z-below)" },
    CLAIMED:   { bg: "rgba(254,151,50,.08)",  bd: "rgba(254,151,50,.3)",  color: "#7C3500" },
  };
  const S = STATUS_STYLE[t.status] || STATUS_STYLE.CONFIRMED;
  const rail = techRowSources(t);

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
        <div className="row" style={{ flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{t.name}</span>
          <span style={{ fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: S.color }}>{t.status}</span>
          {t.evidence_level ? <span className="b b-muted" style={{ fontSize: 9 }}>{t.evidence_level}</span> : null}
          {t.evidence.map(eid => (
            <button key={eid} className="chip purple" style={{ fontSize: 10, padding: "1px 5px" }} onClick={(ev) => { ev.stopPropagation(); openEvidence(eid); }}>{eid}</button>
          ))}
        </div>
        {/* ONE muted line, clamped to one line, exactly as the prototype has
            it. This is `detection_basis`, which the contract defines as ONE
            CLAUSE and CG-12 budgets to 160 characters and a single sentence —
            so it is already the short field, and what was wrong was the
            producer's use of it, not the slot. The version this replaces put
            the whole basis SENTENCE in the right rail as a badge, where a
            150-character paragraph overflowed every row; the version after
            that dropped the line entirely, which cost the register the scent
            the prototype's row carries. It belongs here, one line, with the
            full text on hover and the argument in dma_impact on the detail. */}
        {t.note ? (
          <div className="txt-fit-1" title={t.note}
               style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5, marginTop: 3 }}>
            {t.note}
          </div>
        ) : null}
        {t.subcaps_impact && t.subcaps_impact.length > 0 ? (
          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
            {t.subcaps_impact.map(s => <span key={s} className="chip">{s}</span>)}
          </div>
        ) : null}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-end", flexShrink: 0, maxWidth: 150 }}>
        {rail.chips.slice(0, 3).map(c => (
          <span key={c.label}
                className={`b ${c.rank <= 2 ? "b-teal" : c.rank === 3 ? "b-purple" : "b-muted"}`}
                title={`${c.tier} source`}
                style={{ fontSize: 9, maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {c.label}
          </span>
        ))}
        {rail.chips.length > 3 ? (
          <span className="b b-muted" style={{ fontSize: 9 }}
                title={rail.chips.slice(3).map(c => c.label).join(" · ")}>
            +{rail.chips.length - 3} more
          </span>
        ) : null}
        {/* A citation date, never a deployment date. The payload states no
            `since` for any row, and reading one off a press release would
            assert the product arrived when the press release was written. */}
        {rail.citedTo ? (
          <span style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2 }}>
            Cited to {rail.citedTo}
          </span>
        ) : null}
      </div>
    </button>
  );
}

/* ── Tech stack drilldown (s42) ──────────────────────────────────── */
function ClientTechStackDetail({ entity, run, techId }) {
  const { openEvidence } = useApp();
  const t = DMA.TECH_STACK.find(x => x.id === techId);
  if (!t) return <div className="empty"><h3>Technology not found</h3></div>;

  // The four charter statuses. The labels named Explorium — a vendor this app
  // does not call — and included PARTIAL, which no row can carry. Each status
  // now says what it means, and the row's own detection_basis says how it was
  // established for THIS product.
  const STATUS_STYLE = {
    CONFIRMED: { color: "var(--z-mid)",   label: "Confirmed — in production" },
    INFERRED:  { color: "var(--z-dpur)",  label: "Inferred — from dated public signal" },
    CLAIMED:   { color: "#7C3500",        label: "Claimed — stated, not corroborated" },
    ABSENT:    { color: "var(--z-below)", label: "Absent — searched and not found" },
  };
  const S = STATUS_STYLE[t.status] || { color: "var(--z-muted)", label: t.status || "—" };

  // What the DMA impact IS, and how it was arrived at.
  //
  // It used to be arithmetic with no source: baseline = score − 1.2 and
  // target = score + 1.3 for an absent product, two constants that appear
  // nowhere in the assessment. Asked what the impact was based on, the honest
  // answer was "nothing". A score is never derived here (rule 1: scores come
  // from the workbook), so the impact is now the three things that ARE real:
  // the cells this product is linked to in the register, each cell's SERVED
  // score and band, and the recommendations that touch the same cells. No
  // projected target, because no source states one.
  const recsByCell = {};
  for (const r of (DMA.RECOMMENDATIONS || [])) {
    for (const cid of (r.subcaps || r.affects || [])) {
      (recsByCell[cid] = recsByCell[cid] || []).push(r);
    }
  }
  const impacts = (t.subcaps_impact || []).map(sid => {
    const subcap = entity.subcaps.find(s => s.id === sid) || null;
    return {
      id: sid,
      name: subcap ? subcap.name : null,
      score: subcap ? subcap.score : null,
      band: subcap && subcap.score != null
        ? DMA.helpers.maturityLabel(subcap.score) : null,
      thin: subcap ? subcap.thin : false,
      recs: recsByCell[sid] || [],
      known: !!subcap,
    };
  });

  const peers = DMA.PEER_SETS[entity.subvertical]?.peers || [];

  // What the product does not cover — from the register, not from a template.
  //
  // The old version was four hardcoded sentences per branch, identical for
  // every product and every client, asserting blocked prerequisites and
  // "elevated operating cost" that no evidence in the run supports. Read under
  // a vendor's name it reads as an accusation, and it is not data-backed. What
  // IS in the run: the cells in this product's own pillar that it is NOT
  // linked to. Stated as available value — what the estate does not yet reach —
  // never as a failing.
  const rail = techRowSources(t);
  const coveredIds = new Set(t.subcaps_impact || []);
  const samePillar = (entity.subcaps || []).filter(
    s => t.dma_pillar && String(s.id).startsWith(t.dma_pillar));
  const notCovered = samePillar
    .filter(s => !coveredIds.has(s.id))
    .sort((a, b) => (a.score ?? 9) - (b.score ?? 9))
    .slice(0, 6);

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
          {/* The layer, named. `layer_full` is not a field any adapter sets,
              so this badge rendered EMPTY — a grey bar sitting beside the
              status chip with nothing in it. The layer itself is promoted;
              the full name comes from the register's own label map, and an
              unknown layer renders no badge rather than a blank one. */}
          {TS_LAYER_LABEL[t.layer] ? (
            <span className="b b-muted" style={{ textTransform: "uppercase" }}>
              {TS_LAYER_LABEL[t.layer].name}
            </span>
          ) : null}
          <span className="b b-teal" style={{ background: t.status === "ABSENT" ? "rgba(194,80,8,.10)" : t.status === "INFERRED" ? "var(--ph0-lt)" : "var(--z-ice)", color: S.color, border: `1px solid ${S.color}22` }}>{S.label}</span>
          {/* The same rail the register row carries, so a reader arriving here
              recognises the row they clicked. Sources are the row's OWN
              citations; the date is a citation date and is labelled as one —
              the payload states no deployment date for any product. */}
          {rail.chips.map(c => (
            <span key={c.label}
                  className={`b ${c.rank <= 2 ? "b-teal" : c.rank === 3 ? "b-purple" : "b-muted"}`}
                  title={`${c.tier} source`} style={{ fontSize: 9.5 }}>{c.label}</span>
          ))}
          {rail.citedTo ? <span style={{ fontSize: 11, color: "var(--z-muted)", background: "var(--z-lav)", padding: "2px 8px", borderRadius: 3 }}>Cited to {rail.citedTo}</span> : null}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: "var(--z-dark)", marginBottom: 6 }}>{t.name}</div>
            <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.55, maxWidth: 720 }}>{t.note}</div>
          </div>
          {/* The headline number here was the mean ABSOLUTE PEER DELTA of the
              linked cells, printed as "avg subcap ceiling uplift". A peer delta
              is not a ceiling and it is not an uplift, no source states an
              uplift for any product, and with the fabricated baseline removed
              it rendered "+—". It is replaced by the count it can honestly
              show; the explanation itself is prose and gets the width it needs
              below. */}
          <div style={{ textAlign: "right", flexShrink: 0 }}>
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginBottom: 4 }}>Assessed cells</div>
            <div style={{ fontSize: 32, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1 }}>
              {impacts.length}
            </div>
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
              linked in the register
            </div>
          </div>
        </div>
      </div>

      {/* The DMA assessment impact — the reader's whole reason for opening this
          page, so it is full width and it is first.

          It used to be headed "What this bears on in the assessment" and it
          used to EXPLAIN THE SCORE, which is not what a reader is asking. The
          question under a product name is: what does THIS platform, at the
          edition this institution runs, actually cover here; which assessed
          cells does that reach; where does the product's own documented
          boundary stop; and what work carries the estate across that boundary.
          The contract asks the producer for exactly those four moves in 40-90
          words, so the card names them rather than leaving the reader to find
          them in a paragraph. */}
      {t.dma_impact ? (
        <div className="card" style={{ marginBottom: 14, borderLeft: "3px solid var(--z-teal)" }}>
          {/* No icon. `target` is not in the icon set, so it fell through to
              the fallback glyph and painted a stray dot in front of the
              heading — a bullet on a heading that is not a list. */}
          <div className="row" style={{ marginBottom: 4 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>DMA assessment impact</div>
            <span className="spacer" />
            <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
              Capability · coverage · boundary · pathway
            </span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginBottom: 8, lineHeight: 1.5 }}>
            What {t.name} covers in this estate, which assessed cells that
            reaches, where the product's own documented boundary stops, and the
            work that carries the estate across it. No score is derived here.
          </div>
          <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.65, maxWidth: 860 }}>
            {t.dma_impact}
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>DMA assessment impact</div>
          <div style={{ fontSize: 12, color: "var(--z-muted)", lineHeight: 1.6 }}>
            The run states no assessment impact for this row. The linked cells and
            their served scores are below; the reasoning that connects them was
            not written.
          </div>
        </div>
      )}

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
              {/* The detection basis is NOT repeated here. It is the row's own
                  one-line summary and it already sits under the product name in
                  the header card two blocks up; printing it a second time under
                  "How this was detected" made a short page look like it was
                  padding. What this card owes is the citations themselves. */}
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
            {/* Not "DMA assessment impact" — that is the prose card above, and
                two cards under one heading is why the impact read as a score
                restatement. This one is the register's LINKAGE: the cells, at
                the score the run assessed them. */}
            <div style={{ fontSize: 13, fontWeight: 600 }}>Cells this product is linked to</div>
            <span className="spacer" />
            <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/heatmap`, { run: run.id })}>Open heatmap <Icon name="arrow-r" size={11} /></button>
          </div>
          {impacts.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              The register links this product to no capability cell, so no
              assessment impact is claimed for it.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.55, marginBottom: 8 }}>
                The {impacts.length} cell{impacts.length === 1 ? "" : "s"} this
                product is linked to in the register, at the score the run
                assessed them. No projected uplift is shown: nothing in the
                assessment states one, and a score is never derived here.
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {impacts.map(i => (
                  <div key={i.id} style={{ padding: "8px 12px", background: i.thin ? "rgba(254,151,50,.08)" : "var(--z-ice)", borderRadius: 6, border: i.thin ? "1px solid rgba(254,151,50,.3)" : "1px solid transparent" }}>
                    <div className="row" style={{ gap: 8 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="f-mono" style={{ fontSize: 11, color: "var(--z-dark)" }}>{i.id}</div>
                        {i.name ? (
                          <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 1 }} className="txt-fit-1" title={i.name}>{i.name}</div>
                        ) : (
                          <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 1 }}>
                            not in this run's cell grain
                          </div>
                        )}
                        {i.thin ? <div style={{ fontSize: 9.5, color: "var(--z-org)", marginTop: 2 }}>▲ Thin evidence</div> : null}
                      </div>
                      {i.score != null ? (
                        <div className="row" style={{ gap: 6 }}>
                          <strong style={{ fontSize: 14, color: "var(--z-dark)" }}>{fx(i.score, 1)}</strong>
                          <span className="b b-muted">{i.band}</span>
                        </div>
                      ) : <span style={{ fontSize: 11, color: "var(--z-muted)" }}>no score</span>}
                    </div>
                    {i.recs.length ? (
                      <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 6 }}>
                        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>ADDRESSED BY</span>
                        {i.recs.map(r => (
                          <span key={r.id} className="chip purple" title={r.title}>{r.id}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 2-col: Gap zones + Peer comparison */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={15} style={{ color: "var(--z-below)" }} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              {t.status === "ABSENT"
                ? `Cells ${t.name} is not linked to`
                : `Where the estate does not yet reach through ${t.name}`}
            </div>
          </div>
          {!t.dma_pillar ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              This row states no pillar, so its coverage cannot be placed against
              the assessment.
            </div>
          ) : notCovered.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
              Every {t.dma_pillar} cell in this run is linked to this product.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.55, marginBottom: 8 }}>
                {t.dma_pillar} cells the register does not link to this product,
                lowest-scoring first — read from the run, not asserted.
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {notCovered.map(sc => (
                  <div key={sc.id} style={{ padding: "8px 12px", background: "var(--z-lav)", border: "1px solid var(--z-sep)", borderRadius: 5, fontSize: 12, lineHeight: 1.5 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <span className="f-mono" style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{sc.id}</span>
                      <span style={{ flex: 1, minWidth: 0, color: "var(--z-dark)" }} className="txt-fit-1" title={sc.name || sc.id}>{sc.name || sc.id}</span>
                      {sc.score != null ? <strong style={{ color: "var(--z-dark)" }}>{fx(sc.score, 1)}</strong> : null}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Peer deployment.
            This card claimed a per-peer verdict from a HASH:
              hasIt = (|hashCode(ts_id + peerName)| % 100)/100 < peer_coverage
            — so "✓ Symitar" or "not detected" against a NAMED institution was
            decided by the characters of an id, and peer_coverage itself is null
            in the payload (the contract has no such field), which made the
            header read "—% adopted" over a zero-width bar. A technographic
            claim about a named peer is a research finding; it cannot be
            manufactured. Until the producer researches and promotes it, the
            card states what it needs. */}
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="scale" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Peer platform comparison</div>
            <span className="spacer" />
            {t.peer_coverage != null
              ? <span className="b b-teal">{fmtPct(t.peer_coverage)} adopted</span>
              : ((t.peer_deployments || []).length
                  ? <span className="b b-muted">no share stated</span>
                  : <span className="b b-muted">not researched</span>)}
          </div>
          {(t.peer_deployments || []).length ? (
            <>
              {/* Three verdicts, not two. `deployed: null` is a peer the
                  research could not establish either way, and the contract
                  requires it to be listed rather than dropped — a coverage
                  figure of 2 of 5 with three unknowns behind it is not 2 of 5.
                  The old card had a boolean, so an unknown rendered as "not
                  found": an absence the producer never established, asserted
                  about a named institution on a client's dashboard. */}
              {(() => {
                const rows = t.peer_deployments || [];
                const yes = rows.filter(d => d.deployed === true).length;
                const no = rows.filter(d => d.deployed === false).length;
                const unknown = rows.length - yes - no;
                return (
                  <>
                    {t.peer_coverage != null ? (
                      <div className="prog" style={{ marginBottom: 8 }}>
                        <div className="prog-fill" style={{ width: `${t.peer_coverage * 100}%`, background: "linear-gradient(90deg, var(--z-teal), var(--z-mid))" }} />
                      </div>
                    ) : null}
                    <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 8, lineHeight: 1.5 }}>
                      {yes} of {rows.length} named peer{rows.length === 1 ? "" : "s"} established
                      on this platform · {no} searched and not found
                      {unknown ? ` · ${unknown} not established either way` : ""}.
                    </div>
                  </>
                );
              })()}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {(t.peer_deployments || []).map(d => {
                  const yes = d.deployed === true, no = d.deployed === false;
                  return (
                    <div key={d.peer}
                         style={{ padding: "8px 10px",
                                  background: yes ? "var(--z-ice)" : "var(--z-lav)",
                                  border: `1px solid ${yes ? "rgba(39,187,175,.35)" : "var(--z-sep)"}`,
                                  borderRadius: 5, fontSize: 11.5 }}>
                      <div className="row" style={{ gap: 8 }}>
                        <span style={{ flex: 1, minWidth: 0, color: "var(--z-dark)", fontWeight: 600 }}>{d.peer}</span>
                        <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".04em", textTransform: "uppercase",
                                       color: yes ? "var(--z-mid)" : no ? "var(--z-below)" : "var(--z-muted)" }}>
                          {yes ? "Deployed" : no ? "Not found" : "Not established"}
                        </span>
                      </div>
                      {d.basis ? (
                        <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.5, marginTop: 4, overflowWrap: "anywhere" }}>
                          {d.basis}
                        </div>
                      ) : null}
                      {(d.source_url || d.as_of) ? (
                        <div className="row" style={{ gap: 6, marginTop: 5, flexWrap: "wrap" }}>
                          {d.source_url ? (
                            <a href={d.source_url} target="_blank" rel="noreferrer"
                               className="f-mono"
                               style={{ fontSize: 9.5, color: "var(--z-mid)", overflowWrap: "anywhere" }}>
                              {String(d.source_url).replace(/^https?:\/\/(www\.)?/, "").slice(0, 44)}
                            </a>
                          ) : null}
                          {d.as_of ? <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>as of {d.as_of}</span> : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.6 }}>
              <p style={{ marginBottom: 8 }}>
                No peer technographic research is attached to this product for this
                run, so no adoption figure is shown.
              </p>
              {peers.length ? (
                <>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
                    Peer set that would be searched
                  </div>
                  <div className="row" style={{ gap: 5, flexWrap: "wrap" }}>
                    {peers.slice(0, 8).map(x => <span key={x} className="chip">{x}</span>)}
                  </div>
                </>
              ) : (
                <p style={{ color: "var(--z-muted)" }}>
                  This run states no peer set, so there is no cohort to search
                  against either.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* The recommendations that reach this row's cells.

          This card used to print one hardcoded sentence under every ABSENT
          product on every client — "<product> is the bridge between <client>'s
          current architecture and a unified customer experience" — a claim
          about sequencing that no run states and that reads identically for a
          CDP, an integration bus and a payment rail. The Zennify pathway for
          THIS product is now written, cited, in `dma_impact` above; what
          belongs here is the link from this row to the roadmap items that
          actually name its cells, which is a lookup, not an assertion. */}
      {(() => {
        if (t.status !== "ABSENT") return null;
        const seen = new Set();
        const linked = [];
        for (const i of impacts) {
          for (const r of i.recs) {
            if (!seen.has(r.id)) { seen.add(r.id); linked.push(r); }
          }
        }
        return (
          <div className="card" style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)" }}>
            <div className="row" style={{ marginBottom: 8 }}>
              <Icon name="sparkle" size={15} style={{ color: "var(--z-dpur)" }} />
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dpur)" }}>On the platform roadmap</div>
              <span className="spacer" />
              <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/platform`, { run: run.id })}>See platform matrix <Icon name="arrow-r" size={11} /></button>
            </div>
            {linked.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {linked.map(r => (
                  <div key={r.id} style={{ fontSize: 12.5, color: "#3B0764", lineHeight: 1.55 }}>
                    <span className="chip purple" style={{ marginRight: 6 }}>{r.id}</span>
                    {r.title}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: "#3B0764", lineHeight: 1.65 }}>
                No promoted recommendation names a cell this row is linked to.
                The pathway stated above is the argument for the work; the
                roadmap has not yet sequenced it.
              </div>
            )}
          </div>
        );
      })()}
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
