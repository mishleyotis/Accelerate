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
          {/* The chips name the AXIS, not a mood. `signal` means the direction
              the event moved the ASSESSED POSITION of the cells it lists —
              which is why a merger announcement that has converted nothing is
              NEUTRAL and a remediated breach is not NEGATIVE. Labelled
              Positive/Neutral/Negative the row invited exactly the reading the
              reader had: "why is a merger a negative event?". Advanced ·
              Neutral · Constrained is the same three buckets under the name of
              what they measure, and the group says so above them.

              The STORED values do not move: the filter still compares against
              `e.signal` ∈ positive|neutral|negative, and the payload's enum is
              a contract change nobody has argued for. Only the words change.

              Each bucket carries its count, and a bucket with none is disabled
              rather than pressable-into-nothing. The Unclassified button only
              exists when the run actually has events the contract's vocabulary
              does not cover — it is a defect indicator, not a category. */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 9.5, color: "var(--z-muted)", letterSpacing: ".06em",
                           textTransform: "uppercase", whiteSpace: "nowrap" }}
                  title="the direction each event moved the assessed position of the cells it names — not a reading of the news">
              Effect on assessed maturity</span>
            <div className="toggle-row">
              <button className={signalFilter === "ALL" ? "on" : ""} onClick={() => setSignalFilter("ALL")}>All · {allEvents.length}</button>
              {[["positive", "var(--z-mid)"],
                ["neutral", null],
                ["negative", "var(--z-below)"]].map(([k, c]) => {
                const n = signalCounts[k] || 0;
                const l = (window.MATURITY_EFFECT_LABEL || {})[k] || k;
                return (
                  <button key={k} className={signalFilter === k ? "on" : ""}
                          disabled={!n}
                          title={n ? `${n} event${n === 1 ? "" : "s"} the run scores as ${l.toLowerCase()} for the cells they name`
                                   : `no event in this run ${k === "negative" ? "constrained" : k === "positive" ? "advanced" : "left unchanged"} the cells it names`}
                          onClick={() => n && setSignalFilter(k)}
                          style={{ color: signalFilter === k && c ? c : "var(--z-muted)",
                                   opacity: n ? 1 : 0.45,
                                   cursor: n ? "pointer" : "not-allowed" }}>{l} · {n}</button>
                );
              })}
              {unclassified ? (
                <button className={signalFilter === "unclassified" ? "on" : ""}
                        title="the run did not state a direction for these events"
                        onClick={() => setSignalFilter("unclassified")}
                        style={{ color: "var(--z-org)" }}>Unclassified · {unclassified}</button>
              ) : null}
            </div>
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
          /* `arc_shape` has a closed vocabulary of five. This run serves a
             sentence instead. The app prints what is there either way — a
             dropped arc hides the producer's defect and costs the reader the
             one line that names the shape of the history — but a value the
             contract does not declare is not dressed as one that does: it
             keeps the badge and gains a note saying so, which is what makes
             it fixable rather than invisible. */
          const arc = window.arcShapeOf ? window.arcShapeOf(meta.arc_shape) : null;
          return (
            <div style={{ background: "var(--z-lav)", borderLeft: "3px solid var(--z-dpur)", borderRadius: "0 8px 8px 0", padding: "10px 14px", marginBottom: 14 }}>
              <div className="row" style={{ marginBottom: 4, flexWrap: "wrap", gap: 6 }}>
                <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase" }}>Storyline</span>
                {arc ? (
                  <span className={`b ${arc.in_vocabulary ? "b-purple" : "b-org"}`}
                        title={arc.in_vocabulary
                          ? "the arc shape this run states, from the five the contract declares"
                          : `the arc shape this run states. It is not one of the five the contract declares (${(window.ARC_SHAPES || []).join(" · ").toLowerCase().replace(/_/g, " ")}), so it is printed as promoted`}>
                    {arc.label}</span>
                ) : null}
                {arc && !arc.in_vocabulary ? (
                  <span style={{ fontSize: 9.5, color: "var(--z-org)" }}>
                    not one of the five arc words</span>
                ) : null}
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
          <InteractiveGantt issues={issues} issueOpen={issueOpen} setIssueOpen={setIssueOpen}
                            audience={audience} />
          {/* The detail panel lives HERE, inside the register — but the
              regulatory panel further down opens it too, and from there the
              panel appears a screen and a half above the click. It read as a
              dead control. Anchored so a caller can bring it into view. */}
          <div id="issue-detail-anchor">
            {issueOpen ? <IssueDetail issue={issues.find(i => i.id === issueOpen)} entity={entity} onClose={() => setIssueOpen(null)} openEvidence={openEvidence} openSubcap={openSubcap} audience={audience} /> : null}
          </div>
        </div>
      </div>

      {/* Financial trajectory + Regulatory.
          Was a hard `1.4fr 1fr`, which the ≤760px catch-all in app.css
          collapses and nothing between 760 and 980 does: at 768 the
          regulatory column came out at ~199px, its nowrap "No action found"
          badge needed 100 of them beside a heading, and the whole DOCUMENT
          scrolled sideways by 2px. auto-fit with a readable floor: two
          columns while both fit, one when they do not, no breakpoint. The
          1.4:1 emphasis is kept by giving the chart the larger floor. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 14, marginBottom: 14, alignItems: "start" }}>
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
                            setIssueOpen={setIssueOpen} openEvidence={openEvidence}
                            audience={audience} />
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
                {/* The same axis the timeline chips filter by, on the row that
                    makes the reader ask about it. It was promoted and dropped:
                    a merger with no stated effect reads as an unexplained
                    event, which is exactly the question that came back. */}
                {/* Displayed through the one label map, so this badge cannot
                    read CONSTRAINED beside a filter chip reading Negative —
                    the same axis under two names on one screen. The stored
                    token is unchanged; only the word shown moves. */}
                {a.effect_token ? (
                  <span className={`b ${/CONSTRAIN/.test(a.effect_token) ? "b-below"
                    : /ADVANC/.test(a.effect_token) ? "b-teal" : "b-muted"}`}
                    title="effect on assessed maturity — the direction this moved the cells it affects">
                    {(window.effectTokenLabel
                      ? window.effectTokenLabel(a.effect_token)
                      : a.effect_token).replace(/_/g, " ")}</span>
                ) : null}
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
function RegulatoryStanding({ entity, issues, setIssueOpen, openEvidence, audience }) {
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
  // is the issue's own, never a constant. The contract gives an issue row no
  // `kind`, so this reads the row's own words; the vocabulary covers the
  // statutory and supervisory families a register actually uses (a matter
  // titled "…Community Reinvestment Act…" carries none of the obvious four).
  const regIssues = (issues || []).filter(
    i => /regulat|enforce|compliance|breach|consent|reinvestment|statut|examination|supervis|order\b|obligation/i.test(
      `${i.title || ""} ${i.desc || ""} ${i.status || ""} ${i.kind || ""}`));

  return (
    <div className="card">
      {/* wrap: the verdict badge is nowrap and 100px wide, and in a column
          that narrows to ~200px it sat beside a heading that would not give
          way — the pair pushed the card, then the page, sideways. */}
      <div className="row" style={{ marginBottom: 12, flexWrap: "wrap", gap: 6 }}>
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
        {/* Jurisdictions falls back to the entity's footprint, and when
            neither is stated the row says so in the one way that can be
            acted on: an em dash here read the same whether the producer
            searched and found nothing or was never asked. */}
        <Row k="Jurisdictions" v={list(reg.jurisdictions).join(" · ")
                                  || (entity.footprint || []).join(" · ")
                                  || <EnrichmentGap what="Jurisdictions" audience={audience} />} />
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
              <div className="co-body">{a.summary || a.title
                || <EnrichmentGap what="Enforcement action summary" audience={audience} />}</div>
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
            {regIssues.map(i => {
              const cap = capStateOf(i);
              return (
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
                    <div className="co-title">
                      {i.status || "OPEN"} · {i.id}
                      {cap.kind === "ceiling" ? ` · cap ${fx(cap.ceiling, 1)}`
                        : cap.kind === "held_unleveled" ? " · capped" : null}
                    </div>
                    {/* The invitation names what the click actually opens. It
                        read "click for the cells it caps" on every row,
                        including rows that cap nothing — so a reader who took
                        it up found a panel that did not answer the promise. */}
                    <div className="co-body">
                      {i.title || i.desc}
                      {(cap.kind === "ceiling" || cap.kind === "held_unleveled") ? ` · click for the ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} it caps`
                        : cap.kind === "linked" ? ` · caps nothing · click for the ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} it bears on`
                        : " · click for why it is on the register"}
                    </div>
                  </div>
                  <Icon name="arrow-r" size={12} />
                </div>
              );
            })}
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

/* ── Markers on a percentage track ──────────────────────────────────
   A marker of width w centred on its value — `calc(pct% - w/2)`, or the same
   thing as `translateX(-50%)` — has half of itself OUTSIDE the track at 0%
   and at 100%. That is a real w/2 of content past the box, and it is why the
   context page's slider AND its timeline each measured 8px wider than their
   own track at every viewport tested.

   Blending the offset with the position instead — no inset at the start, the
   marker's full width at the end — keeps a whole marker inside the track at
   both ends and moves its centre across the same span in between. It is the
   geometry a native range input uses, for the same reason. */
function markerLeft(pct, w) {
  const p = Math.max(0, Math.min(100, pct));
  return `calc(${p}% - ${(p * w / 100).toFixed(2)}px)`;
}

function RangeSlider({ min, max, value, onChange }) {
  const [v1, v2] = value;
  const pct = (v) => (max === min ? 0 : (v - min) / (max - min) * 100);
  return (
    <div style={{ position: "relative", height: 26, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 4, background: "var(--z-sep)", borderRadius: 2 }} />
      <div style={{ position: "absolute", left: `${(v1 - min) / (max - min) * 100}%`, right: `${100 - (v2 - min) / (max - min) * 100}%`, height: 4, background: "var(--z-teal)", borderRadius: 2 }} />
      <input type="range" min={min} max={max} value={v1} onChange={e => onChange([Math.min(parseInt(e.target.value), v2), v2])} style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }} />
      <input type="range" min={min} max={max} value={v2} onChange={e => onChange([v1, Math.max(parseInt(e.target.value), v1)])} style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }} />
      {/* Knobs */}
      <div style={{ position: "absolute", left: markerLeft(pct(v1), 16), width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
      <div style={{ position: "absolute", left: markerLeft(pct(v2), 16), width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
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
              style={{ position: "absolute", left: markerLeft(pct, active ? 22 : 16), top: active ? -10 : -7, width: active ? 22 : 16, height: active ? 22 : 16, borderRadius: 11, background: TONE[e.signal], border: "2px solid #fff", cursor: "pointer", boxShadow: active ? "0 0 0 4px " + TONE[e.signal] + "40" : "var(--sh-sm)", transition: "all 160ms var(--ease)", padding: 0 }}
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
            title={e.date ? `${fmtDate(e.date)} · ${e.title}` : e.title}
            style={{ textAlign: "center", lineHeight: 1.4, background: "none",
                     border: 0, padding: 0, cursor: "pointer", minWidth: 0 }}>
            <div className="f-mono" style={{ color: hoverEvent === i || selectedEvent === i ? TONE[e.signal] : "var(--z-muted)" }}>{e.date ? fmtDate(e.date) : ""}</div>
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
        {/* The header badge names the axis, not the news. Same three buckets,
            same stored value, the word the chips above are filtered by. */}
        {event.signal === "unclassified"
          ? <span className="b b-org" title={event.signal_raw || ""}>NO DIRECTION STATED</span>
          : <span className="b b-muted"
                  title="the direction this event moved the assessed position of the cells it names">
              {String((window.MATURITY_EFFECT_LABEL || {})[event.signal] || event.signal).toUpperCase()}
            </span>}
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

      {/* What it did to maturity — read, never generated from the signal.

          `maturity_effect` arrives as "TOKEN — one clause". Printed whole it
          was a 200-character paragraph opening with a shouted enum, which is
          neither a badge nor a sentence. The token is the badge; the clause is
          the body; and where the field carries no token the badge falls back
          to the event's own direction rather than inventing one. */}
      <div style={{ background: "rgba(255,255,255,.6)", border: "1px solid var(--z-sep)", borderRadius: 6, padding: "8px 10px", marginBottom: 10 }}>
        <div className="row" style={{ marginBottom: 4, gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase" }}>
            Effect on assessed maturity
          </span>
          <span className="spacer" />
          {(() => {
            const token = event.effect_token
              || (event.signal !== "unclassified"
                  ? String((window.MATURITY_EFFECT_LABEL || {})[event.signal] || "").toUpperCase()
                  : null);
            if (!token) return null;
            // Tone reads the STORED token; the word shown reads the one label
            // map, so a producer token and a fallback direction print the same
            // vocabulary the filter chips above use.
            const tone = /CONSTRAIN|NEGATIVE/.test(token) ? "b-below"
              : /ADVANC|POSITIVE/.test(token) ? "b-teal" : "b-muted";
            const shown = window.effectTokenLabel
              ? window.effectTokenLabel(token) : token;
            return (
              <span className={`b ${tone}`}
                    title={event.effect_token
                      ? "the effect this run states for the cells this event names"
                      : "the run stated no effect token; this is the event's own direction"}>
                {shown.replace(/_/g, " ")}</span>
            );
          })()}
        </div>
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>
          {event.effect_reason
            || (event.signal === "unclassified"
                ? "Not stated. The run did not classify this event's direction, so no effect is claimed here."
                : "The run stated a direction but no reasoning for it. Nothing is inferred from the direction alone.")}
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

function InteractiveGantt({ issues, issueOpen, setIssueOpen, audience }) {
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
    /* The label column is a RANGE, not a constant. At a flat 200px the header
       row and the issue rows also disagreed below 760px, because the app.css
       catch-all that collapses inline grids matches `div[style*=…]` and every
       issue row here is a <button> — so the header collapsed and the rows did
       not. A range needs no catch-all: both shrink together. */
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(90px, 200px) minmax(0, 1fr)", gap: 12, fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
        <div></div>
        <div style={{ position: "relative", height: 14 }}>
          {years.map(y => {
            const t = Date.parse(`${y}-01-01`);
            const left = Math.max(0, Math.min(100, pct(t)));
            /* A tick near the right edge puts its label OUTSIDE the track —
               the last year is the whole reason this strip was 8px wider than
               its own box at every viewport. The tick stays exactly where the
               date is; the label flips to the other side of it. */
            const atEdge = left > 88;
            return (
              <div key={y} style={{ position: "absolute", left: `${left}%`, top: 0, height: 14,
                                    paddingLeft: atEdge ? 0 : 4, paddingRight: atEdge ? 4 : 0,
                                    borderLeft: atEdge ? 0 : "1px dashed var(--z-sep)",
                                    borderRight: atEdge ? "1px dashed var(--z-sep)" : 0,
                                    transform: atEdge ? "translateX(-100%)" : "none" }}>{y}</div>
            );
          })}
        </div>
      </div>
      {dated.map(iss => {
        const a = at(iss.start);
        // A matter in a TERMINAL status is over, whatever its dates say. The
        // bar used to run to TODAY whenever `end` was null — so ISS-001,
        // status REMEDIATED with no stated resolution date, drew a bar from
        // 2021 to now and tooltipped "→ open" while the drilldown one click
        // deeper said the opposite. The chart asserting a live regulatory
        // matter that the run says is closed is a false statement in the
        // safeguard family. With no end date the honest bar is BOUNDED —
        // a fixed stub past its start — and the tooltip says the date is
        // not stated rather than inventing either endpoint.
        const TERMINAL = /^(REMEDIATED|RESOLVED|CLOSED|RETIRED|EXPIRED|S\d\s+EXPIRED)/i
          .test(String(iss.status || "").trim());
        const b = iss.end ? (at(iss.end) ?? now)
          : TERMINAL ? Math.min((a ?? now) + (now - (a ?? now)) * 0.12 + 1, now)
          : now;
        const left = Math.max(0, Math.min(100, pct(a)));
        const right = Math.max(0, Math.min(100, pct(Math.max(b, a))));
        const width = Math.max(2, right - left);
        const tone = severityTone(iss.severity);
        const color = tone === "b-below" ? "var(--z-below)" : tone === "b-org" ? "var(--z-org)" : "var(--z-muted)";
        const isOpen = issueOpen === iss.id;
        const cap = capStateOf(iss);
        return (
          <button key={iss.id} onClick={() => setIssueOpen(isOpen ? null : iss.id)}
            style={{ display: "grid", gridTemplateColumns: "minmax(90px, 200px) minmax(0, 1fr)", gap: 12, padding: "8px 0", borderTop: "1px solid var(--z-sep)", textAlign: "left", width: "100%", background: isOpen ? "var(--z-lav)" : "transparent", border: "0", borderRadius: 6 }}>
            <div style={{ padding: "0 8px", minWidth: 0 }}>
              <div className="row">
                <span className="chip">{iss.id}</span>
                {iss.severity ? <span className={`b ${tone}`}>{iss.severity}</span> : null}
                {cap.kind === "ceiling" ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} title={`${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} held at M${cap.ceiling}`} />
                  : cap.kind === "held_unleveled" ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} title={`${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} held — level on the assessment caps`} /> : null}
              </div>
              {/* compact: this label column clamps to one line inside a
                  90-200px track, and the queue badge would push the bar
                  lane off the row. */}
              <div style={{ fontSize: 12, marginTop: 4 }} className="txt-fit-1" title={iss.title || iss.type || ""}>{iss.title || iss.type
                || <EnrichmentGap what="Issue title" audience={audience} compact />}</div>
              {/* The prototype's row footer, made honest. It printed
                  "OPEN · cap 3" from a `cap_value` the contract does not
                  carry, so in LIVE it printed the status and stopped. A cap
                  LEVEL renders when the run states one; where the run names
                  cells and no level, the row says how many it bears on —
                  which is the difference between a ceiling and a linkage,
                  and is what the reader is about to open. */}
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
                {iss.status}
                {cap.kind === "ceiling" ? ` · cap ${fx(cap.ceiling, 1)}`
                  : cap.kind === "held_unleveled" ? ` · ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} capped`
                  : cap.kind === "linked" ? ` · ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} · no cap`
                  : " · no cell named"}
              </div>
            </div>
            <div style={{ position: "relative", height: 28 }}>
              {/* The bar carries the matter's TITLE, not its rationale. It
                  read `desc` — the register's rationale — which is an
                  argument of two to four sentences: on a bar 200px wide it
                  rendered as the first six words of a paragraph and told the
                  reader nothing the row label had not already said. The
                  argument belongs in the panel the bar opens; the tooltip
                  keeps the dates. */}
              <div title={`${iss.start}${iss.end ? ` → ${iss.end}`
                     : TERMINAL ? ` → ${String(iss.status).toLowerCase()} · resolution date not stated`
                     : " → open"}${iss.desc ? ` · ${iss.desc}` : ""}`}
                   style={{ position: "absolute", left: `${left}%`, width: `${width}%`, height: 18, top: 5, background: color, borderRadius: 4, opacity: .85, display: "flex", alignItems: "center", padding: "0 6px", color: "#fff", fontSize: 10, fontWeight: 500, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                {iss.title || iss.type || iss.id}
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
          {undated.map(iss => {
            const cap = capStateOf(iss);
            return (
              <button key={iss.id} onClick={() => setIssueOpen(issueOpen === iss.id ? null : iss.id)}
                style={{ display: "flex", gap: 8, alignItems: "center", width: "100%", textAlign: "left", background: issueOpen === iss.id ? "var(--z-lav)" : "transparent", border: 0, borderRadius: 6, padding: "6px 8px", cursor: "pointer" }}>
                <span className="chip">{iss.id}</span>
                {iss.severity ? <span className={`b ${severityTone(iss.severity)}`}>{iss.severity}</span> : null}
                {(cap.kind === "ceiling" || cap.kind === "held_unleveled") ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} title={cap.ceiling != null ? `${cap.entries.length} cells held at M${cap.ceiling}` : `${cap.entries.length} cells held — level on the assessment caps`} /> : null}
                <span style={{ flex: 1, minWidth: 0, fontSize: 12 }} className="txt-fit-1" title={iss.title || ""}>{iss.title || iss.type
                  || <EnrichmentGap what="Issue title" audience={audience} compact />}</span>
                {/* An undated row opens the same panel as a dated bar, so it
                    carries the same cap summary — without it the group read
                    as a list of names with no relationship to the grid. */}
                <span style={{ fontSize: 10, color: "var(--z-muted)", whiteSpace: "nowrap" }}>
                  {iss.status}
                  {cap.kind === "ceiling" ? ` · cap ${fx(cap.ceiling, 1)}`
                    : cap.kind === "held_unleveled" ? ` · ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"} capped`
                    : cap.kind === "linked" ? ` · ${cap.entries.length} cell${cap.entries.length === 1 ? "" : "s"}`
                    : " · no cell"}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/* ── A cap, and what a register row owes a reader ─────────────────────
   A cap is the assessment's own arithmetic: a matter holds named cells to a
   maximum maturity, so a cell sitting at 3.0 has a reason a reader can open
   rather than a number they must accept. The prototype rendered that as a
   row label ("OPEN · cap 3") and a grid of tiles reading "Score capped at
   M3" — the right SHAPE, and as deep as it went: no pre/post arithmetic, no
   argument, no dates, tiles that were not clickable, and — because its caps
   lived in a hardcoded map keyed by issue id — a matter absent from that map
   rendered NO cap section at all, an absence shown as nothing.

   Three states, and each must be said out loud:

     ceiling      the run states a level; show it, and show how many of the
                  linked cells actually sit at it (pre → post)
     linked       the run names cells and states no level; the matter bears
                  on them and caps nothing, which is a finding, not a blank
     unlinked     no cells at all; then and only then does the panel say the
                  matter names no cell — and the narrative must say why it is
                  still on the register

   The middle state is the one this page got wrong: it printed "This matter
   names no capability cell" whenever no LEVEL was stated, which is what the
   register looked like when every row shipped with an empty linkage list. */
function capStateOf(issue) {
  // The adapter now separates the two facts this function used to blur:
  // `caps` holds only cells the matter actually HOLDS (from the contract's
  // capped_subcap_ids — previously read from a key that does not exist, so
  // every matter on every client printed "Cap None"), and `linked` holds the
  // cells it merely bears on. A matter with caps is a ceiling; with only
  // linkage it names cells without holding them; with neither it is unlinked.
  const rec = DMA.ISSUE_CAPS[issue.id] || {};
  const capEntries = Object.entries(rec.caps || {});
  const linked = rec.linked || [];
  const levels = capEntries.map(([, lvl]) => lvl).filter(l => l != null);
  const ceiling = levels.length ? Math.min(...levels.map(Number)) : null;
  if (capEntries.length) {
    // Held cells with no stated level still render as a ceiling — the level
    // lives on the run's caps[] array; "held, level on the assessment caps"
    // is honest where inventing M-numbers is not.
    return { entries: capEntries, ceiling,
             kind: ceiling == null ? "held_unleveled" : "ceiling" };
  }
  const entries = linked.map(c => [c, null]);
  return { entries, ceiling: null, kind: entries.length ? "linked" : "unlinked" };
}

/* Severity is the register's OWN word — the source's vocabulary, never
   normalised (a real run uses S2 EXPIRED, LOW, MEDIUM; the fixture used
   CRITICAL, MATERIAL, MINOR). The tone ladder therefore reads a family of
   words rather than three constants, and an unrecognised word renders
   neutral rather than silently reading as "minor". */
function severityTone(sev) {
  const s = String(sev || "").toUpperCase();
  if (/CRITICAL|SEVERE|S1\b/.test(s)) return "b-below";
  if (/MATERIAL|HIGH|MEDIUM|S2(?!\s*EXPIRED)/.test(s)) return "b-org";
  if (/EXPIRED|RETIRED|CLOSED/.test(s)) return "b-muted";
  return "b-muted";
}

function monthsSince(d) {
  const t = Date.parse(/^\d{4}-\d{2}$/.test(String(d)) ? `${d}-01` : String(d));
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((Date.now() - t) / (1000 * 60 * 60 * 24 * 30.4375)));
}

function IssueDetail({ issue, entity, onClose, openEvidence, openSubcap, audience }) {
  if (!issue) return null;
  const { entries, ceiling, kind } = capStateOf(issue);
  const tone = severityTone(issue.severity);

  /* Each linked cell resolved against the run's OWN scores, so the panel
     shows the position rather than repeating the id. A cell the run does not
     carry resolves to null and says so — it is a dead chip, and the reader
     should see that rather than a tile that opens onto nothing. */
  const cells = entries.map(([id, lvl]) => {
    const s = (entity.subcaps || []).find(x => x.id === id) || null;
    return { id, cap: lvl == null ? null : Number(lvl), row: s,
             name: s ? s.name : null, score: s ? s.score : null,
             thin: s ? s.thin : false, category: s ? s.category : null };
  });
  const scored = cells.filter(c => c.score != null);
  const lo = scored.length ? Math.min(...scored.map(c => c.score)) : null;
  const hi = scored.length ? Math.max(...scored.map(c => c.score)) : null;
  const atCeiling = ceiling == null ? 0 : scored.filter(c => c.score >= ceiling).length;

  /* The categories the linked cells belong to. The contract carries no
     `kind` on an issue row, so the prototype's category word ("Regulatory",
     "Data quality") has no promoted source — inventing one would be reading
     a taxonomy into the register. What IS knowable is where the matter lands
     on the assessment, computed from the cells it names. */
  const cats = [];
  for (const c of cells) {
    if (c.category && !cats.some(x => x.id === c.category)) {
      const meta = DMA.getCategory ? DMA.getCategory(c.category) : null;
      cats.push({ id: c.category, name: meta && meta.name ? meta.name : null });
    }
  }

  const opened = issue.start || null;
  const elapsed = opened ? monthsSince(opened) : null;
  const ev = (issue.evidence || []).map(eid => DMA.getEvidence(eid) || { id: eid, tier: "T3" });

  const Head = ({ children }) => (
    <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 7 }}>{children}</div>
  );

  return (
    <div style={{ marginTop: 14, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${tone === "b-below" ? "var(--z-below)" : tone === "b-org" ? "var(--z-org)" : "var(--z-muted)"}` }}>
      {/* Identity row — the prototype's anatomy (id · severity · category ·
          status), with the category computed from the cells rather than
          invented, and the cap moved onto its own line so it can carry the
          arithmetic instead of being a four-character suffix. */}
      <div className="row" style={{ marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
        <span className="chip">{issue.id}</span>
        {/* `sentence()` takes a string, so the absence is decided before the
            call rather than being sentence-cased into an em dash. */}
        <strong style={{ fontSize: 14, flex: "1 1 320px", minWidth: 0 }}>{(issue.title || issue.type)
          ? sentence(issue.title || issue.type)
          : <EnrichmentGap what="Issue title" audience={audience} />}</strong>
        {issue.severity ? <span className={`b ${tone}`}>{issue.severity}</span> : null}
        {issue.status ? <span className="b b-muted">{issue.status}</span> : null}
        <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" size={14} /></button>
      </div>
      {cats.length ? (
        <div className="row" style={{ gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
          <span style={{ fontSize: 9.5, color: "var(--z-muted)", letterSpacing: ".08em" }}>BEARS ON</span>
          {cats.map(c => (
            <span key={c.id} className="b b-purple" title={c.name || c.id}>{c.id}{c.name ? ` · ${c.name}` : ""}</span>
          ))}
        </div>
      ) : null}

      {/* ── The cap, stated ──────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 12, alignItems: "stretch", flexWrap: "wrap", padding: "10px 12px", background: "var(--z-white, #fff)", border: "1px solid var(--z-sep)", borderRadius: 7, marginBottom: 12 }}>
        <div style={{ minWidth: 108 }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase" }}>Cap</div>
          <div style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.25, color: (kind === "ceiling" || kind === "held_unleveled") ? "var(--z-org)" : "var(--z-body)" }}>
            {kind === "ceiling" ? `M${fx(ceiling, 1)}`
              : kind === "held_unleveled" ? "Held"
              : "None"}
          </div>
          <div style={{ fontSize: 10, color: "var(--z-muted)" }}>
            {(kind === "ceiling" || kind === "held_unleveled") ? `${entries.length} cell${entries.length === 1 ? "" : "s"} held`
              : kind === "linked" ? `${entries.length} cell${entries.length === 1 ? "" : "s"} named`
              : "no cell named"}
          </div>
        </div>
        {/* Pre → post. With a ceiling: how many of the named cells actually
            sit at it. Without: the assessed spread, which is the honest
            answer to "what did this matter do to the score" — nothing. */}
        <div style={{ flex: "1 1 260px", minWidth: 0, borderLeft: "1px solid var(--z-sep)", paddingLeft: 12 }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase" }}>Arithmetic</div>
          {kind === "ceiling" ? (
            <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, marginTop: 3 }}>
              {/* `lo`/`hi` are null when the matter caps cells the run does
                  not score — the dead-chip case above — and fx() renders a
                  null score as an em dash, so this read "Assessed —–— →
                  ceiling M3.0 · 0 of 0 named cells sit at it". The ceiling is
                  stated either way; the assessed spread only when the run
                  states one. Same sentence the `linked` branch already uses
                  for the same condition. */}
              {scored.length ? (
                <>
                  Assessed {fx(lo, 1)}–{fx(hi, 1)} <Icon name="arrow-r" size={11} /> ceiling M{fx(ceiling, 1)}
                  {" · "}{atCeiling} of {scored.length} named cell{scored.length === 1 ? "" : "s"} sit{atCeiling === 1 ? "s" : ""} at it.
                </>
              ) : (
                <>
                  Ceiling M{fx(ceiling, 1)}. The run names {entries.length} cell{entries.length === 1 ? "" : "s"} and
                  scores none of them, so no assessed position can be shown.
                </>
              )}
            </div>
          ) : kind === "linked" ? (
            <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, marginTop: 3 }}>
              {scored.length
                ? (lo === hi
                    ? <>All {scored.length} named cell{scored.length === 1 ? "" : "s"} assessed {fx(lo, 1)}. This matter sets no maximum — the score is the evidence, not a ceiling.</>
                    : <>Assessed {fx(lo, 1)}–{fx(hi, 1)} across {scored.length} named cells. This matter sets no maximum; it bears on them without holding them.</>)
                : <>The run names {entries.length} cell{entries.length === 1 ? "" : "s"} and scores none of them, so no position can be shown.</>}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, marginTop: 3 }}>
              This matter names no capability cell and states no ceiling. It is
              on the register for the reason given below, not for a score it moves.
            </div>
          )}
        </div>
      </div>

      {/* ── Cells, clickable ─────────────────────────────────────────── */}
      {cells.length ? (
        <div style={{ marginBottom: 14 }}>
          <Head>{kind === "ceiling" ? `Cells this matter caps · ${cells.length}` : `Cells this matter bears on · ${cells.length}`}</Head>
          <div className="g2" style={{ gap: 8 }}>
            {cells.map(c => (
              <button key={c.id} className="card-tile"
                      onClick={() => openSubcap && openSubcap(c.id)}
                      disabled={!openSubcap || !c.row}
                      title={c.row ? `Open ${c.id} in the cell drawer` : `${c.id} is not carried by this run`}
                      style={{ padding: 10, textAlign: "left", border: "1px solid var(--z-sep)", background: "var(--z-white, #fff)", borderRadius: 7, cursor: c.row && openSubcap ? "pointer" : "default", width: "100%" }}>
                <div className="row" style={{ marginBottom: 4 }}>
                  <span className="chip purple">{c.id}</span>
                  <span className="spacer" />
                  {c.thin ? <span className="b b-muted" title="thin evidence">THIN</span> : null}
                  {c.cap != null ? <Icon name="lock" size={11} style={{ color: "var(--z-org)" }} /> : null}
                  {c.score != null ? <MaturityChip score={c.score} /> : null}
                </div>
                <div style={{ fontSize: 12, fontWeight: 500 }}>{c.name || c.id}</div>
                <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 4 }}>
                  {c.cap != null
                    ? `Held at M${fx(c.cap, 1)}${c.score != null ? ` · assessed ${fx(c.score, 1)}` : ""}`
                    : c.score != null
                      ? `Assessed ${fx(c.score, 1)} · ${DMA.helpers.maturityLabel(c.score)} · no ceiling from this matter`
                      : "Not carried by this run"}
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── The argument ─────────────────────────────────────────────── */}
      {issue.desc ? (
        <div style={{ marginBottom: 14 }}>
          <Head>Why it constrains</Head>
          <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.65 }}>{sentence(issue.desc)}</div>
        </div>
      ) : (
        <div style={{ marginBottom: 14, fontSize: 12, color: "var(--z-muted)" }}>
          The register gives no rationale for this matter. The row renders on its
          title alone rather than on a composed one.
        </div>
      )}

      {/* ── Dates ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <Head>Timeline</Head>
        <div className="row" style={{ gap: 14, flexWrap: "wrap", fontSize: 11.5, color: "var(--z-body)" }}>
          <span>
            <span style={{ color: "var(--z-muted)" }}>Opened </span>
            {opened
              ? <><strong>{opened}</strong>{elapsed != null ? <span style={{ color: "var(--z-muted)" }}> · {elapsed} months ago</span> : null}</>
              : <em style={{ color: "var(--z-muted)" }}>no opening date established</em>}
          </span>
          <span>
            <span style={{ color: "var(--z-muted)" }}>Closed </span>
            {issue.end
              ? <strong>{issue.end}</strong>
              : <em style={{ color: "var(--z-muted)" }}>{/^REMEDIATED|RESOLVED|CLOSED/i.test(String(issue.status || "")) ? "not dated by the register" : "still open"}</em>}
          </span>
          {issue.status ? (
            <span><span style={{ color: "var(--z-muted)" }}>Status </span><strong>{issue.status}</strong></span>
          ) : null}
        </div>
      </div>

      {/* The issue's OWN cited ids. This used to prefix-sweep the entire
          evidence store for anything sharing four characters with a capped
          cell — and since the caps map was empty in LIVE, it swept nothing, so
          every issue showed no evidence while carrying an e_id of its own. */}
      {ev.length ? (
        <div>
          <Head>Evidence · click to open</Head>
          <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
            {ev.map(e => <button key={e.id} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }} title={`${e.title || e.id}${e.source_pretty ? ` · ${e.source_pretty}` : ""}`} onClick={() => openEvidence && openEvidence(e.id)}>{e.id}</button>)}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 11.5, color: "var(--z-muted)" }}>This matter cites no evidence id.</div>
      )}

      {cells.length ? (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/heatmap`, { hm: "standard", zoom: "subcap", subcap: cells[0].id })}>Open {cells[0].id} in the heatmap <Icon name="arrow-r" size={11} /></button>
        </div>
      ) : null}
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

  /* One tile per AUDIENCE, which is the contract's own unit and the
     prototype's single row of three. Flattening every measured row into one
     grid made this card seven tiles and three rows deep, and — worse — the
     worked-absent ladder was only rendered when the card had NO rows at all,
     so an audience that was searched and could not be established simply
     vanished the moment any other audience had a number. That is how the
     employee ladder stayed invisible while reading "not established": it was
     never a missing measure, it was an unreachable branch.

     Each tile leads with its audience's first row and says how many more it
     holds; an audience with no measure carries the ladder instead. Both open
     onto the same detail, because the ladder IS the finding at that grain. */
  const AUDIENCE_ORDER = ["employee", "customer", "market", "unstated"];
  const byAudience = new Map();
  for (const r of rows) {
    const k = String(r.group || "unstated").toLowerCase();
    if (!byAudience.has(k)) byAudience.set(k, { key: k, label: r.group, rows: [] });
    byAudience.get(k).rows.push(r);
  }
  for (const a of absent) {
    const k = String(a.group || "unstated").toLowerCase();
    if (!byAudience.has(k)) byAudience.set(k, { key: k, label: a.group, rows: [] });
    byAudience.get(k).absent = a;
  }
  const tiles = [...byAudience.values()].sort((x, y) => {
    const i = AUDIENCE_ORDER.indexOf(x.key), j = AUDIENCE_ORDER.indexOf(y.key);
    return (i < 0 ? 99 : i) - (j < 0 ? 99 : j);
  });

  if (!tiles.length) {
    return (
      <div style={{ fontSize: 12, color: "var(--z-muted)", lineHeight: 1.6 }}>
        No sentiment measures promoted for this run.
        {sent && sent.sources_searched && sent.sources_searched.length ? (
          <> Searched: {sent.sources_searched.join(" · ")}.</>
        ) : null}
      </div>
    );
  }

  /* The scale as a token, not as a sentence. The producer states it in full
     ("0-100 % of employees agreeing", "NPS -100..100"), which is right in the
     payload and far too long beside an 18px number — it wrapped the value off
     its own tile. The face carries the denominator; the full wording is one
     click away, where there is room for it. */
  const scaleToken = (scale) => {
    const b = scaleBounds(scale);
    if (!b) return null;
    return b.min === 0 && b.max === 100 && /%/.test(String(scale)) ? "%" : `/${b.max}`;
  };

  return (
    <div className="g3" style={{ gap: 10, alignItems: "start" }}>
      {tiles.map(t => {
        const lead = t.rows[0] || null;
        const more = Math.max(0, t.rows.length - 1);
        const id = `aud-${t.key}`;
        const isOpen = sentOpen === id;
        return (
          <div key={id}>
            <button onClick={() => setSentOpen(isOpen ? null : id)} className="card-tile clickable"
                    style={{ padding: 10, width: "100%", textAlign: "left", minWidth: 0,
                             border: isOpen ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)" }}>
              <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>{t.label}</div>
              <div className="row" style={{ marginTop: 4, minWidth: 0 }}>
                {lead ? (
                  <span style={{ fontSize: 18, fontWeight: 600, whiteSpace: "nowrap" }}>
                    {fx(lead.value, 1)}
                    {scaleToken(lead.scale) ? (
                      <span style={{ fontSize: 11, color: "var(--z-muted)", fontWeight: 400 }}>{scaleToken(lead.scale)}</span>
                    ) : null}
                  </span>
                ) : (
                  <span style={{ fontSize: 12, color: "var(--z-muted)", fontStyle: "italic" }}>Searched, not established</span>
                )}
                <span className="spacer" />
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={11} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
              </div>
              <div style={{ fontSize: 10, color: "var(--z-muted)" }} className="txt-fit-1"
                   title={lead ? `${lead.label}${lead.n != null ? ` · n=${lead.n}` : ""}` : (t.absent && t.absent.note) || ""}>
                {lead
                  ? `${lead.label}${lead.n != null ? ` · n=${Number(lead.n).toLocaleString()}` : ""}${more ? ` · +${more} more` : ""}`
                  : `${(t.absent && (t.absent.sources_searched || []).length) || 0} source${((t.absent && (t.absent.sources_searched || []).length) || 0) === 1 ? "" : "s"} searched`}
              </div>
            </button>
            {isOpen ? (
              <div style={{ marginTop: 6, padding: "10px 12px", background: "var(--z-lav)", borderRadius: 6, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55 }}>
                {t.rows.map(s => (
                  <div key={s.id} style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, color: "var(--z-dark)" }}>
                      {s.label} · {fx(s.value, 1)}{s.scale ? <span style={{ fontWeight: 400, color: "var(--z-muted)" }}> {s.scale}</span> : null}
                      {s.n != null ? <span style={{ fontWeight: 400, color: "var(--z-muted)" }}> · n={Number(s.n).toLocaleString()}</span> : null}
                    </div>
                    {s.note || s.reading ? <div>{s.note || s.reading}</div> : null}
                    {(s.e_ids || []).length ? (
                      <div className="row" style={{ gap: 5, flexWrap: "wrap", marginTop: 5 }}>
                        {s.e_ids.map(eid => (
                          <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
                                  onClick={() => openEvidence(eid)}>{eid}</button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
                {t.absent ? (
                  <div>
                    {t.absent.note || "Searched and not established."}
                    {(t.absent.sources_searched || []).length ? (
                      <> Searched: {t.absent.sources_searched.join(" · ")}.</>
                    ) : null}
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
              style={{ position: "absolute", left: markerLeft(pct, 16), top: -7, width: 16, height: 16, borderRadius: 8, background: TONE[e.signal], border: "2px solid #fff", cursor: "pointer", boxShadow: "var(--sh-sm)" }}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(0, 1fr))", gap: 6, fontSize: 9.5, color: "var(--z-muted)", padding: "0 8px" }}>
        {events.map((e, i) => (
          <div key={e.id} style={{ textAlign: "center", lineHeight: 1.4 }}>
            <div className="f-mono">{e.date ? fmtDate(e.date) : ""}</div>
            <div style={{ color: TONE[e.signal], fontWeight: hover === i ? 600 : 400 }}>{e.title.split(" ").slice(0, 4).join(" ")}{e.title.split(" ").length > 4 ? "…" : ""}</div>
          </div>
        ))}
      </div>
      {hover != null ? (
        <div className="card-tile" style={{ marginTop: 16, padding: 12, background: "var(--z-lav)", border: "none" }}>
          <div className="row" style={{ marginBottom: 6 }}>
            <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{events[hover].date ? fmtDate(events[hover].date) : ""}</span>
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
      <div style={{ display: "grid", gridTemplateColumns: "minmax(90px, 180px) minmax(0, 1fr)", gap: 12, fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
        <div></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gap: 0 }}>
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
          <div key={iss.id} style={{ display: "grid", gridTemplateColumns: "minmax(90px, 180px) minmax(0, 1fr)", gap: 12, padding: "8px 0", borderTop: "1px solid var(--z-sep)" }}>
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

/* ── The evidence-age panel's rows ────────────────────────────────────
   The tracker aged `DMA.EVIDENCE[].recency`, and the adapter sets `recency`
   to the recency BAND — "CURRENT", "AGING", "ARCHIVAL" — whenever the record
   carries one, falling back to the date only when it does not. `new
   Date("CURRENT")` is an Invalid Date, so every one of the 63 rows printed
   "Not computed" in the AGE column and "NO DATE" in the STATUS column, the 22
   that carry both a published date and an age in months included, while the
   DATE column showed the band word where a date belonged.

   Two reads, in order. A run that promotes the panel outright
   (`heatmap.evidence_age.rows`) is read first: 26 rows already dated, aged
   and banded by the producer against the run's own reference date. A run that
   promoted no panel falls back to the evidence records' own date fields,
   `published_date` and `age_months` — never to a band word.

   The age is the producer's arithmetic either way, not a fresh subtraction
   against today's clock: a run's ages are stated against its reference date,
   and re-deriving them here would drift a month for every month the run sits
   promoted, so two readers of one promoted run would see two different
   numbers. A row with no date gets no age and no freshness verdict, because
   both would be assertions about a date nobody established. */
function evidenceAgeRows(entity) {
  const promoted = (typeof DMA.evidenceAgeFor === "function")
    ? (DMA.evidenceAgeFor(entity && entity.id) || []) : [];
  if (promoted.length) {
    return promoted.map(r => ({
      id: r.e_id || r.id || null,
      title: r.title || r.e_id || null,
      source: r.source_domain || null,
      date: r.published_or_asof || null,
      age: r.age_months == null ? null : Number(r.age_months),
      status: r.status || r.band || null,
      identity_ok: r.identity_ok === undefined ? null : r.identity_ok,
    })).filter(r => r.id);
  }
  return (DMA.EVIDENCE || []).map(e => {
    // `recency` is the band word when the record has one and the date when it
    // does not, so it is read only through `calendarValue`, which returns a
    // date for a calendar value and null for a word. That is the whole defect
    // in one line: "CURRENT" used to go into `new Date()`.
    const date = e.published_date || calendarValue(e.recency);
    const age = e.age_months != null ? Number(e.age_months)
      : (date ? monthsSince(date) : null);
    return {
      id: e.id,
      title: e.title,
      source: e.source ? String(e.source).split("/")[0] : null,
      date,
      age,
      // The band is the producer's verdict on the date. "UNVERIFIED" is the
      // ladder's word for "no date to rank this on", not a freshness state,
      // and a verdict nobody reached is left null rather than derived here
      // against a threshold no run declares.
      status: (e.recency_band && e.recency_band !== "UNVERIFIED")
        ? e.recency_band : null,
      identity_ok: e.identity_ok === undefined ? null : e.identity_ok,
    };
  }).filter(r => r.id);
}

/* A calendar value the producer wrote, or null.
   `2026-06-30`, `2026-06`, `2026-Q2` and `2026` are dates at their own
   precision and normalise to the first day of the period they name. A recency
   BAND — CURRENT, AGING, STALE, ARCHIVAL, UNVERIFIED — is a word about a date,
   not a date, and comes back null however confidently it is handed over. */
function calendarValue(v) {
  const s = String(v == null ? "" : v).trim();
  if (!s) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const q = s.match(/^(\d{4})[-\s]?Q([1-4])$/i);
  if (q) return `${q[1]}-${String((+q[2] - 1) * 3 + 1).padStart(2, "0")}-01`;
  if (/^\d{4}-\d{2}$/.test(s)) return `${s}-01`;
  if (/^\d{4}$/.test(s)) return `${s}-01-01`;
  return null;
}

/* Whole months since a stated date is `monthsSince`, already in this file at
   the issue register — one function per fact, so the age a row shows here and
   the age a matter shows there cannot round differently. It is only ever
   reached where the producer stated no `age_months` of its own: a promoted
   age is the producer's arithmetic against the run's reference date and is
   never recomputed, so two readers of one promoted run cannot see two
   numbers. */

/* ── D6 Assessment health ────────────────────────────────────────── */
function ClientHealth({ entity, run }) {
  const { role, audience, pushToast, openEvidence } = useApp();
  const [tab, setTab] = useState("alerts");
  const alerts = DMA.alertsForEntity(entity.id);
  /* A cell id is not a capability name. The alert contract carries
     `subcap_id` and no name, and the run's own cell grain names all 705, so
     the queue resolves the name from the grid rather than printing a
     taxonomy code at a reader or inventing a label. */
  const subcapName = (sid) => {
    const s = (entity.subcaps || []).find(x => x.id === sid);
    return (s && s.name && s.name !== s.id) ? s.name : null;
  };
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
          {/* Singular counts took plural nouns on all three of these — "1
              failing gates · 1 runs in history" — while the first of them
              read zero over a queue of fourteen. */}
          <div className="sub">{(() => {
            const failing = DMA.QA_GATES.filter(g => g.status === "FAIL").length;
            const runs = entity.runs.length;
            return `${alerts.length} open alert${alerts.length === 1 ? "" : "s"}`
                 + ` · ${failing} failing gate${failing === 1 ? "" : "s"}`
                 + ` · ${runs} run${runs === 1 ? "" : "s"} in history`;
          })()}</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast("Feedback file regenerated - routed to DMA bot", "success")}><Icon name="refresh" size={13} /> Re-run feedback file</button>
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

      {/* ── The run's own alert queue ──────────────────────────────────
          This table read `DMA.ALERTS`, which `buildAlerts()` derives by
          walking the BOOT DIRECTORY's cell grain — a key the live directory
          does not carry. So it was empty on every live run, and the empty
          branch below printed a green tick, "✓ No open alerts", and the
          sentence "Evidence coverage meets the minimum threshold." over a run
          carrying fourteen promoted alerts and 33.0% evidence coverage
          against its own 80% gate. A quality surface that reassures where the
          run raised an alarm is worse than no quality surface.

          Two rules follow from that and are why the columns changed. An
          all-clear is now a statement about the QUEUE and nothing else — an
          empty alert list says the run promoted no alert, never that coverage
          is adequate, which is a different section's arithmetic. And every
          column renders a field the producer wrote: `recommended_action` and
          `proxy_searched` are the prototype's own vocabulary, absent from the
          contract, and a "PROXY_ESCALATION" badge or a "✓ Searched" tick that
          nobody decided is a fabricated finding on a client's quality queue.
          What the run does state — the state it reached, how long the row has
          been open, why it was flagged, what would close it, and the ladder
          that was run — is what the reader gets. */}
      {tab === "alerts" ? (
        <div className="card flush">
          <div className="card-head">
            <h3>Thin-evidence alerts</h3>
            {alerts.length ? <span className="b b-org">{alerts.length} open</span> : null}
          </div>
          {alerts.length ? (
          <table className="tbl">
            <thead><tr><th style={{ width: 80 }}>Severity</th><th style={{ width: 190 }}>Sub-capability</th><th style={{ width: 76 }}>Cited</th><th style={{ width: 118 }}>State</th><th>Why it is flagged, and what would close it</th><th style={{ textAlign: "right", width: 140 }}>Queue</th></tr></thead>
            <tbody>
              {alerts.map(a => {
                const name = subcapName(a.subcap_id);
                const searched = a.sources_searched || [];
                const queries = a.queries_run || [];
                return (
                <tr key={a.id}>
                  <td data-label="Severity">
                    <span className={`b ${a.severity === "HIGH" ? "b-below" : a.severity === "LOW" ? "b-muted" : "b-org"}`}>
                      {a.severity || "not stated"}
                    </span>
                  </td>
                  <td data-label="Sub-capability">
                    <div style={{ fontSize: 12, fontWeight: 500 }}>
                      {name || <span style={{ color: "var(--z-muted)", fontStyle: "italic" }}>unnamed in catalogue</span>}
                    </div>
                    <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      {a.subcap_id}{a.score != null ? ` · ${fx(a.score, 1)}` : ""}{a.confidence ? ` · ${a.confidence}` : ""}
                    </div>
                  </td>
                  {/* The count the run states, with no denominator invented for
                      it: "N / 3" was the prototype's house rule and no promoted
                      alert carries a target. */}
                  <td data-label="Cited">
                    {a.evidence_count == null
                      ? <span style={{ color: "var(--z-muted)", fontSize: 11 }}>not stated</span>
                      : <span style={{ fontSize: 12 }}>{a.evidence_count} item{a.evidence_count === 1 ? "" : "s"}</span>}
                  </td>
                  <td data-label="State">
                    <span className="b b-purple">{String(a.state || "OPEN").replace(/_/g, " ")}</span>
                    {a.runs_open != null ? (
                      <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 3 }}>
                        open {a.runs_open} run{a.runs_open === 1 ? "" : "s"}
                      </div>
                    ) : null}
                  </td>
                  <td data-label="Why">
                    {a.justification ? (
                      <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>{a.justification}</div>
                    ) : null}
                    {a.closure_condition ? (
                      <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5, marginTop: 4 }}>
                        <strong style={{ color: "var(--z-body)" }}>Closes when · </strong>{a.closure_condition}
                      </div>
                    ) : null}
                    {searched.length || queries.length ? (
                      <details style={{ marginTop: 5 }}>
                        <summary style={{ fontSize: 10.5, color: "var(--z-mid)", cursor: "pointer" }}>
                          {searched.length} source{searched.length === 1 ? "" : "s"} searched
                          {queries.length ? ` · ${queries.length} quer${queries.length === 1 ? "y" : "ies"} run` : ""}
                        </summary>
                        <ul style={{ margin: "5px 0 0 15px", padding: 0 }}>
                          {searched.map((s, i) => (
                            <li key={`s${i}`} style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5, marginBottom: 3 }}>{asText(s)}</li>
                          ))}
                          {queries.map((q, i) => (
                            <li key={`q${i}`} style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5, marginBottom: 3 }}>Query · {asText(q)}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </td>
                  <td data-label="Queue" style={{ textAlign: "right" }}>
                    <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} moved to IN_REVIEW`, "success")}>In review</button>
                    <button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`${a.subcap_id} waived — add rationale before close`, "warn")}>Waive</button>
                  </td>
                </tr>);
              })}
            </tbody>
          </table>
          ) : (
            /* No tick, no coverage claim. An empty queue is a statement about
               the queue, and the section's own empty_state says why it is
               empty when the producer wrote one. */
            <div style={{ padding: "14px 16px" }}>
              <SectionEmpty
                section="heatmap.alerts"
                absent="This run promoted no thin-evidence alert queue, so there is nothing to work here. It is not a statement about evidence coverage — the coverage panel states that separately."
                empty="The run promoted an alert queue with no rows in it." />
            </div>
          )}
          <div style={{ padding: "0 16px 12px" }}>
            <SectionEmptyFoot section="heatmap.alerts" title="What this queue does not cover" />
          </div>
        </div>
      ) : tab === "diff" ? (
        <VersionDiff entity={entity} baseId={compareBase} targetId={compareTarget} setBase={setCompareBase} setTarget={setCompareTarget} />
      ) : tab === "gates" ? (
        /* Two arrays, kept apart, per the charter: `caps[]` is what the
           ASSESSMENT applied to the scores and `gates[]` is what VALIDATION
           found. The prototype held one blob and the distinction was lost.

           The heading said "G01-G10" and the badge said "N / 10 PASS" against
           a hardcoded ten-gate fixture set. In LIVE the array was empty, so
           production served "0 / 10 PASS" over an empty table while the run
           carried a FAILING grounding gate. A run states its own gate ids; the
           denominator is the length of what it states (invariant 8). */
        (() => {
          const gates = DMA.QA_GATES || [];
          const caps = DMA.SAFEGUARD_CAPS || [];
          const pass = gates.filter(g => g.status === "PASS").length;
          const failed = gates.some(g => g.status === "FAIL");
          return (
        <div className="card flush">
          <div className="card-head">
            <h3>Safeguard gates</h3>
            {gates.length ? (
              <span className={`b ${failed ? "b-org" : "b-teal"}`}>{pass} / {gates.length} PASS</span>
            ) : null}
          </div>
          {gates.length ? (
          <table className="tbl">
            <tbody>
              {gates.map(g => (
                <tr key={g.id}>
                  <td data-label="Gate" style={{ width: 70 }}><span className="chip">{g.id}</span></td>
                  {/* `plain_label` is the sentence an SG renders to a client;
                      the gate id alone is a code nobody outside this build
                      can read. */}
                  <td data-label="Name"><strong>{g.name}</strong></td>
                  <td data-label="Evidence">
                    {g.evidence
                      ? <span style={{ fontSize: 11 }}>{g.evidence}</span>
                      : <EnrichmentGap what="Gate detail" audience={audience} compact />}
                    {g.e_ids && g.e_ids.length ? (
                      <div style={{ marginTop: 3 }}>
                        <PlatformEvChips ids={g.e_ids} openEvidence={openEvidence} />
                      </div>
                    ) : null}
                  </td>
                  {/* NOT_RUN is a third verdict, not a soft fail: the gate
                      abstained and recorded why (V4 abstains when a scoped
                      centroid holds fewer than five members). Rendering it as
                      a failure would report a finding the run did not make. */}
                  <td data-label="Verdict" style={{ width: 90 }}>
                    <span className={`b ${g.status === "PASS" ? "b-above"
                                        : g.status === "NOT_RUN" ? "b-muted" : "b-below"}`}>
                      {g.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          ) : (
            <SectionEmpty section="safeguard_gates" />
          )}

          {caps.length ? (
            <div style={{ borderTop: "1px solid var(--z-sep)" }}>
              <div className="card-head" style={{ borderBottom: 0 }}>
                <h3>Caps the assessment applied · {caps.length}</h3>
              </div>
              <table className="tbl">
                <tbody>
                  {caps.map((c, i) => (
                    <tr key={c.cap_id || i}>
                      <td data-label="Cap" style={{ width: 80 }}><span className="chip">{c.cap_id}</span></td>
                      <td data-label="Ceiling" style={{ width: 70 }}>
                        {c.ceiling != null && c.ceiling !== ""
                          ? <span className="f-mono">{c.ceiling}</span>
                          : <EnrichmentGap what="Ceiling" audience={audience} compact />}
                      </td>
                      <td data-label="Categories" style={{ width: 110 }}>
                        {(c.affected_categories || []).map(k => (
                          <span key={k} className="chip" style={{ marginRight: 3 }}>{k}</span>
                        ))}
                      </td>
                      <td data-label="Why">
                        <span style={{ fontSize: 11 }}>{c.rationale}</span>
                        {c.e_ids && c.e_ids.length ? (
                          <div style={{ marginTop: 3 }}>
                            <PlatformEvChips ids={c.e_ids} openEvidence={openEvidence} />
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
          );
        })()
      ) : tab === "age" ? (
        (() => {
          const rows = evidenceAgeRows(entity);
          // Both header figures are COUNTED from the rows on screen, not read
          // from the promoted `stale_pct` / `undated_pct` (invariant 8: a
          // count is computed where a source of truth exists). They reproduce
          // the promoted pair exactly on this run — 4/26 = 15.4, 5/26 = 19.2.
          const dated = rows.filter(r => r.date);
          const stale = rows.filter(r => String(r.status || "").toUpperCase() === "STALE");
          const pct = (n) => rows.length ? `${(n / rows.length * 100).toFixed(1)}%` : null;
          return (
        <div className="card flush">
          <div className="card-head">
            <h3>Evidence age tracker</h3>
            {rows.length ? (
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {rows.length} row{rows.length === 1 ? "" : "s"} · {dated.length} dated ·
                {" "}{pct(stale.length)} stale · {pct(rows.length - dated.length)} undated
              </span>
            ) : null}
          </div>
          {rows.length ? (
          <table className="tbl">
            <thead><tr><th>Evidence</th><th>Source</th><th>Date</th><th>Age</th><th style={{textAlign:"right"}}>Status</th></tr></thead>
            <tbody>
              {rows.map(r => (
                  <tr key={r.id}>
                    <td data-label="Evidence">
                      <span className="chip">{r.id}</span>
                      <span style={{ marginLeft: 6 }}>{r.title}</span>
                      {/* An identity verdict the producer made is a fact about
                          the row and belongs beside it; a null one asserts
                          nothing and renders nothing. */}
                      {r.identity_ok === false
                        ? <span className="b b-below" style={{ marginLeft: 6 }}
                                title="this row was checked against the entity and did not match">FOREIGN</span>
                        : null}
                    </td>
                    <td data-label="Source" className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.source}</td>
                    {/* The DATE is a field of the evidence record: absent, it
                        is a producer gap the connector can be asked to fill,
                        so it says so (compact — this is a table cell). The AGE
                        is the producer's own arithmetic against the run's
                        reference date, not a fresh subtraction against today's
                        clock, which would drift a month every month the run
                        sits promoted. */}
                    <td data-label="Date">{r.date
                      ? fmtDate(r.date)
                      : <EnrichmentGap what="Evidence date" audience={audience} compact />}</td>
                    <td data-label="Age">{r.age == null
                      ? <span style={{ color: "var(--z-muted)", fontStyle: "italic" }}>no date to age</span>
                      : `${r.age} mo`}</td>
                    <td data-label="Status" style={{ textAlign: "right" }}>
                      {/* The band the producer stated, or nothing. A row that
                          carries a date but no band already says how old it is
                          in the column beside this one; stamping "undated" on
                          it would contradict that, and deriving a freshness
                          word here would apply a threshold no run declares. */}
                      {(() => {
                        const s = String(r.status || "").toUpperCase();
                        if (!s) return r.date ? null : <span className="b b-muted">undated</span>;
                        const cls = s === "FRESH" || s === "CURRENT" ? "b-teal"
                                  : s === "STALE" || s === "ARCHIVAL" ? "b-org"
                                  : s === "UNDATED" ? "b-muted" : "b-purple";
                        return <span className={`b ${cls}`}>{s}</span>;
                      })()}
                    </td>
                  </tr>
              ))}
            </tbody>
          </table>
          ) : (
            <div style={{ padding: "14px 16px" }}>
              {sectionReason("heatmap.evidence_age").stub ? (
                <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 }}>
                  This run promoted no evidence-age panel, and its evidence
                  records carry no dates to age.
                </div>
              ) : <SectionEmpty section="heatmap.evidence_age" />}
            </div>
          )}
          {/* The panel's own account of what it leaves out — on this run, the
              36 ingested rows that carry no excerpt and so cannot be listed
              here. It was promoted and rendered nowhere. */}
          <div style={{ padding: "0 16px 12px" }}>
            <SectionEmptyFoot section="heatmap.evidence_age" title="Rows this panel does not carry" />
          </div>
        </div>
          );
        })()
      ) : (
        /* ── Cross-entity patterns ──────────────────────────────────────
           `DMA.PATTERNS` is the prototype's fixture list and is `[]` in LIVE,
           and this table had no empty branch at all: the card rendered a
           header, a "≥60% threshold" badge and then nothing, with no word
           about why. The reason is a real one and the section states it — a
           cohort needs five promoted runs in the same sub-vertical and the
           corpus holds two — so the reason renders where the rows would be. */
        <div className="card flush">
          <div className="card-head">
            <h3>Cross-entity patterns</h3>
            {DMA.PATTERNS.length ? <span className="b b-muted">≥60% threshold</span> : null}
          </div>
          {DMA.PATTERNS.length ? (
          <table className="tbl">
            <thead><tr><th>Subvertical</th><th>Category</th><th>Pattern</th><th>Count</th><th style={{ textAlign: "right" }}>Action</th></tr></thead>
            <tbody>
              {DMA.PATTERNS.map((p, i) => (
                <tr key={i}>
                  <td data-label="Subvertical"><span className="b b-purple">{DMA.SUBVERTICAL_LABEL[p.subvertical]}</span></td>
                  <td data-label="Category"><span className="chip">{p.category}</span></td>
                  <td data-label="Pattern"><strong>{p.title}</strong></td>
                  <td data-label="Count">{p.count} / {p.total}</td>
                  <td data-label="Action" style={{ textAlign: "right" }}><button className="btn btn-tertiary btn-sm" onClick={() => pushToast(`Drafting outreach campaign · ${p.title}`, "success")}>Build campaign →</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          ) : (
            /* The producer's own reason for this section — its cohort floor,
               its two sources searched, its closure condition — is written and
               destroyed at promote (see `sectionReason`). Until the writer
               persists an envelope-only row, the floor renders from the rule
               rather than from the plumbing sentence the serving tier
               substitutes. */
            <div style={{ padding: "14px 16px" }}>
              {sectionReason("heatmap.cohort_patterns").stub ? (
                <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 }}>
                  No cross-entity pattern is published for this run. A cohort is
                  published only where five promoted runs in the same
                  sub-vertical carry a served score for the same category;
                  cohorts are never pooled across sub-verticals, and one below
                  the floor is withheld rather than shown thin.
                </div>
              ) : <SectionEmpty section="heatmap.cohort_patterns" />}
            </div>
          )}
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
          <select className="inp" style={{ flex: "1 1 200px", minWidth: 0, maxWidth: 320 }} value={baseId} onChange={e => setBase(e.target.value)}>
            {entity.runs.map(r => <option key={r.id} value={r.id}>{fmtDate(r.date)} · {r.status} · {r.data_source}</option>)}
          </select>
          <span style={{ color: "var(--z-muted)" }}>vs</span>
          <select className="inp" style={{ flex: "1 1 200px", minWidth: 0, maxWidth: 320 }} value={targetId} onChange={e => setTarget(e.target.value)}>
            {entity.runs.map(r => <option key={r.id} value={r.id}>{fmtDate(r.date)} · {r.status} · {r.data_source}</option>)}
          </select>
        </div>
      </div>
      <table className="tbl">
        <thead><tr><th>Subcap</th><th>Category</th><th>{fmtDate(base.date)}</th><th>{fmtDate(target.date)}</th><th>Δ</th><th>Evidence</th></tr></thead>
        <tbody>
          {diffs.map(d => (
            <tr key={d.id}>
              <td data-label="Subcap">{d.name} <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{d.id}</span></td>
              <td data-label="Category"><span className="chip">{d.category}</span></td>
              <td data-label="Base"><MaturityChip score={d.base} /></td>
              <td data-label="Target"><MaturityChip score={d.target} /></td>
              <td data-label="Delta"><span style={{ fontFamily: "var(--font-mono)", color: d.delta > 0 ? "var(--z-mid)" : d.delta < 0 ? "var(--z-below)" : "var(--z-muted)" }}>{d.delta > 0 ? "▲" : d.delta < 0 ? "▼" : "-"} {fx(Math.abs(d.delta), 1)}</span></td>
              <td data-label="Evidence"><span style={{ fontSize: 11 }}>{d.evBase} → {d.evTarget}</span></td>
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
  const { pushToast, audience } = useApp();
  const [layer, setLayer] = useState("ALL");
  const [hideAbsent, setHideAbsent] = useState(false);
  // The status filter. ONE piece of state behind three controls — the legend
  // entries, the stat tiles and the hide-absent switch — and behind the list
  // predicate, so no two of them can ever describe a different register.
  const [statusFilter, setStatusFilter] = useState(null);
  /* The single writer. Pressing the status already selected clears it, so a
     control that filters is also the control that un-filters — otherwise a
     reader who filters to ABSENT has no way back except reloading the page.
     Filtering TO absent while absent is hidden shows an empty register, so
     the request wins and releases the switch (and the switch, below, releases
     the filter for the mirror case). */
  const switchStatus = (key) => {
    const next = statusFilter === key ? null : key;
    if (next === "ABSENT" && hideAbsent) setHideAbsent(false);
    setStatusFilter(next);
    // A status the reader picks is a narrower question than "the gap layer",
    // so it replaces it rather than intersecting with it.
    setGapOnly(false);
  };
  // Layer briefly highlighted after a PRIMARY GAP tile click.
  const [flashLayer, setFlashLayer] = useState(null);
  /* The PRIMARY GAP LAYERS filter.
     ─────────────────────────────────────────────────────────────────────
     This tile used to LOCATE — scroll to the flagged card and flash it —
     on the reasoning that the flag belongs to a layer rather than to rows a
     status filter could select. The reader read it as a filter and reported
     it as broken: "primary gap layers do not filter out the gaps only".
     They are right, and the rule this build follows says so: a DERIVED
     relationship may only order content, but a filter THE READER EXPLICITLY
     SELECTS narrows. This is the second kind.

     What it narrows TO is the flag's own arithmetic. `is_primary_gap` is
     awarded to the layer with the fewest CONFIRMED rows (`basis` travels with
     it and reads "0 confirmed of 8 — fewer than any other layer"), so the
     rows that MAKE it the gap are that layer's rows which are not confirmed:
     absent, inferred, claimed. Narrowing to the layer alone would leave the
     confirmed rows in — the ones that are not the gap — and narrowing to
     ABSENT alone would drop six of this run's eight, because a data layer
     with nothing confirmed is a gap whether or not a slot was searched and
     missed. Pressing again clears, like every other filter on this page. */
  const [gapOnly, setGapOnly] = useState(false);

  const allTech = DMA.TECH_STACK;
  const layerRollup = DMA.TECH_LAYERS || [];
  // The layers the promoted rollup flags. Computed before the predicate, which
  // reads it.
  const gapRoll = layerRollup.filter(x => x && x.is_primary_gap);
  const gapLayers = gapRoll.map(x => x.layer);
  const isGapRow = (t) => gapLayers.indexOf(t.layer) >= 0 && t.status !== "CONFIRMED";
  const gapRowCount = allTech.filter(isGapRow).length;
  const list = useMemo(() => allTech.filter(t => {
    if (gapOnly) return isGapRow(t);
    if (layer !== "ALL" && t.layer !== layer) return false;
    if (statusFilter && t.status !== statusFilter) return false;
    if (hideAbsent && t.status === "ABSENT") return false;
    return true;
  }), [layer, hideAbsent, statusFilter, gapOnly, allTech]);

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

  /* Narrow to the gap rows, and land on them. Enabling releases every other
     filter — they would otherwise intersect and the register could come out
     empty under a control that says "8" — and pressing again restores the
     whole register. The scroll and the flash stay: filtering and then leaving
     the reader at the top of a page whose content moved is its own defect. */
  const togglePrimaryGap = () => {
    const L = gapLayers[0];
    if (!L) return;
    const next = !gapOnly;
    setGapOnly(next);
    if (next) { setLayer("ALL"); setStatusFilter(null); setHideAbsent(false); }
    setFlashLayer(next ? L : null);
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
          {/* Whether the technographic scan that widens this register actually
              ran. Without it, twelve human-placed rows and a fifty-one-row
              machine-scanned estate render identically, and the short one
              reads as the client's whole stack. The run's own empty_state said
              the scan had not run and no surface repeated it. */}
          <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).techstack} what="register" audience={audience} />
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
          claim, and each ROW states its own detection basis.

          Every entry is a CONTROL, on the same `statusFilter` the stat tiles
          and the register predicate read. A legend that names the four things
          a row can be, beside a register showing all four, is read as the way
          to see one of them — and it was inert, so the reader clicked four
          swatches and nothing moved. One state means the legend, the tiles and
          the list can never disagree about what is on screen; it also gives
          CLAIMED a control, which the three-status stat strip never had.
          `switchStatus` is the single writer, so the contradiction rules
          (filtering TO absent while hiding absent) hold from either place. */}
      <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <div className="eyebrow" style={{ margin: 0 }}>Legend</div>
          {[
            { label: "Confirmed", key: "CONFIRMED", c: "var(--z-mid)",   bg: "var(--z-ice)",  bd: "rgba(39,187,175,.4)" },
            { label: "Inferred",  key: "INFERRED",  c: "var(--z-dpur)",  bg: "var(--ph0-lt)", bd: "var(--ph0-bd)" },
            { label: "Claimed",   key: "CLAIMED",   c: "#7C3500",        bg: "rgba(254,151,50,.08)", bd: "rgba(254,151,50,.3)" },
            { label: "Absent",    key: "ABSENT",    c: "var(--z-below)", bg: "rgba(194,80,8,.06)",   bd: "rgba(194,80,8,.25)" },
          ].map(s => {
            // Counted from the register, never asserted: a status no row
            // carries has nothing to filter to, so its entry is disabled
            // rather than pressable into an empty list.
            const n = allTech.filter(t => t.status === s.key).length;
            const active = statusFilter === s.key;
            const dead = n === 0;
            return (
              <button key={s.label} className="ts-legend" aria-pressed={active} disabled={dead}
                onClick={() => switchStatus(s.key)}
                title={dead ? `No ${s.key} rows in this register`
                            : (active ? "Show every status again" : `Show only ${s.key} rows`)}
                style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5,
                         color: "var(--z-body)", fontFamily: "inherit",
                         padding: "3px 8px", borderRadius: 999,
                         background: active ? s.bg : "transparent",
                         border: active ? `1.5px solid ${s.c}` : "1.5px solid transparent",
                         opacity: dead ? .45 : 1,
                         cursor: dead ? "not-allowed" : "pointer" }}>
                <span style={{ width: 14, height: 14, background: s.bg, border: `1.5px solid ${s.bd}`, borderRadius: 3, flexShrink: 0 }} />
                <strong style={{ color: s.c }}>{s.label}</strong>
                <span className="muted" style={{ fontSize: 10.5 }}>{n}</span>
              </button>
            );
          })}
          <span className="spacer" />
          <div className="row" style={{ gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Layer</span>
            <select className="inp" style={{ flex: "1 1 150px", minWidth: 0, maxWidth: 200, padding: "5px 10px", fontSize: 12 }} value={layer}
              onChange={e => { setLayer(e.target.value); setGapOnly(false); }}>
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
              setGapOnly(false);
            }} />
            Hide absent
          </label>
        </div>
      </div>

      {/* What the gap filter is showing, and how to leave it. A register that
          silently drops 43 of its 51 rows under a pressed tile is the same
          defect as one that drops nothing under it: the reader has to be able
          to read the narrowing off the page. The basis is the rollup's own
          sentence, not a restatement of it. */}
      {gapOnly ? (
        <div className="co co-teal" style={{ marginBottom: 14 }}>
          <Icon name="filter" size={14} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="co-title">
              {list.length} of {allTech.length} rows · the unconfirmed rows in{" "}
              {gapLayers.map(L => (LAYER_LABEL[L] || {}).name || L).join(" · ")}
            </div>
            <div className="co-body">
              {gapRoll.map(r => r.basis).filter(Boolean).join(" · ")
                || "This layer carries the fewest confirmed rows in the register."}
            </div>
            <div className="co-body" style={{ marginTop: 2 }}>
              Confirmed rows in the same layer are not gaps, so they are held back
              while this is on.
            </div>
          </div>
          <button className="btn btn-tertiary btn-sm" style={{ flexShrink: 0 }}
            onClick={() => { setGapOnly(false); setFlashLayer(null); }}>
            Show all {allTech.length}
          </button>
        </div>
      ) : null}

      {/* Stat strip — a legend that filters, not one that sits there. Each
          status tile toggles the register to just its rows (press again to
          clear), through the SAME statusFilter the list predicate reads, so
          it can never disagree with the layer select or hide-absent switch.
          The PRIMARY GAP tile narrows too — to the flagged layer's own
          unconfirmed rows, which is what makes it the flagged layer — and
          says so in the strip: its number is the row count it will show, not
          a layer count the register has no way to display. The layer count is
          under it in words, because "1" beside a filter that produces eight
          rows is the ambiguity the reader hit.
          A zero-count tile is disabled rather than pressable-into-nothing,
          matching the timeline's effect buttons. */}
      <div className="g4" style={{ marginBottom: 14 }}>
        {[
          { l: "Confirmed",   key: "CONFIRMED", v: allTech.filter(t => t.status === "CONFIRMED").length,  c: "var(--z-mid)",   bg: "var(--z-ice)" },
          { l: "Inferred",    key: "INFERRED",  v: allTech.filter(t => t.status === "INFERRED").length,   c: "var(--z-dpur)",  bg: "var(--ph0-lt)" },
          { l: "Absent",      key: "ABSENT",    v: allTech.filter(t => t.status === "ABSENT").length,     c: "var(--z-below)", bg: "rgba(194,80,8,.06)" },
          // Counted from the promoted rollup, which states the flag per LAYER,
          // and from the rows that flag selects. It used to count a per-row
          // `primary_gap` no adapter emits, so the tile read 0 on every client
          // while a layer card wore the badge.
          { l: "Primary gap rows", key: "GAP", v: gapRowCount, c: "var(--z-blue)", bg: "var(--ph1-lt)",
            sub: gapLayers.length
              ? `unconfirmed in ${gapLayers.map(L => (LAYER_LABEL[L] || {}).short || L).join(" · ")}`
              : null },
        ].map(s => {
          const active = s.key === "GAP" ? gapOnly : statusFilter === s.key;
          const dead = s.v === 0;
          return (
            <button key={s.l} className="card-tile clickable" aria-pressed={active}
              disabled={dead}
              title={s.key === "GAP"
                ? (dead ? "No layer is flagged as the primary gap in this run"
                        : (active ? "Show the whole register again"
                                  : `Show only the ${s.v} unconfirmed rows in the flagged layer`))
                : (dead ? `No ${s.key} rows in this register`
                        : (active ? "Clear the status filter"
                                  : `Show only ${s.key} rows`))}
              onClick={() => {
                if (dead) return;
                if (s.key === "GAP") { togglePrimaryGap(); return; }
                switchStatus(s.key);
              }}
              style={{ borderLeft: `3px solid ${s.c}`, textAlign: "left", width: "100%",
                       fontFamily: "inherit",
                       background: active ? s.bg : "#fff",
                       boxShadow: active ? `inset 0 0 0 1.5px ${s.c}` : "none",
                       opacity: dead ? 0.45 : 1,
                       cursor: dead ? "not-allowed" : "pointer" }}>
              <div style={{ fontSize: 10, color: active ? s.c : "var(--z-muted)", fontWeight: active ? 700 : 400, letterSpacing: ".08em", textTransform: "uppercase" }}>{s.l}</div>
              <div style={{ fontSize: 28, fontWeight: 200, color: s.c, lineHeight: 1, marginTop: 6 }}>{s.v}</div>
              {s.sub ? (
                <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 4, lineHeight: 1.4 }}>{s.sub}</div>
              ) : null}
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

/* The catalogue's own name for a cell, from the run's served grain.
   A cell id is a taxonomy code, not a capability name: the register printed
   `P4C3.2.1 P4C3.2.2 P4C3.3.1 P3C1.2.2` under every product and asked a
   reader to know what those are (T-05). The run names all 705 of them on the
   grain read — the same lookup the detail sub-page has always made — so the
   name is READ, never guessed, and a cell this run did not score falls back
   to its bare id rather than to an invented label. */
function techCellName(entity, sid) {
  const s = ((entity && entity.subcaps) || []).find(x => x.id === sid);
  return (s && s.name && s.name !== s.id) ? s.name : null;
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
        {/* The cells this row is linked to, named. The chip carried the bare
            catalogue code, so thirteen register rows printed forty-odd codes
            and nothing a reader could act on (T-05). The name leads and the
            code stays beside it in mono, because the code is what every other
            surface — the drawer, the heatmap, the detail sub-page — is keyed
            on and a reader following the row needs both. */}
        {t.subcaps_impact && t.subcaps_impact.length > 0 ? (
          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
            {t.subcaps_impact.map(s => {
              const nm = techCellName(entity, s);
              return (
                <span key={s} className="chip"
                      title={nm ? `${nm} · ${s}` : `${s} — this run serves no name for this cell`}>
                  {/* The separator is a character, not a margin: a 4px gap is
                      invisible to innerText, to a screen reader and to
                      copy-paste, all three of which read
                      "Application Portfolio ManagementP4C3.2.1". */}
                  {nm ? <>{nm}{" · "}<span className="f-mono" style={{ opacity: .62 }}>{s}</span></> : s}
                </span>
              );
            })}
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
  const { openEvidence, audience } = useApp();
  const t = DMA.TECH_STACK.find(x => x.id === techId);
  if (!t) return <div className="empty"><h3>Technology not found</h3></div>;

  // The four charter statuses. The labels named Explorium — a vendor this app
  // does not call — and included PARTIAL, which no row can carry. Each status
  // now says what it means, and the row's own detection_basis says how it was
  // established for THIS product.
  const STATUS_STYLE = {
    CONFIRMED: { color: "var(--z-mid)",   label: "Confirmed - in production" },
    INFERRED:  { color: "var(--z-dpur)",  label: "Inferred - from dated public signal" },
    CLAIMED:   { color: "#7C3500",        label: "Claimed - stated, not corroborated" },
    ABSENT:    { color: "var(--z-below)", label: "Absent - searched and not found" },
  };
  // A status is REQUIRED on every register row, so a row without one is a
  // hole in the payload, not a style of row. It renders inside a badge, so
  // the gap is compact — a badge nested in a badge is not a fix.
  const S = STATUS_STYLE[t.status] || {
    color: "var(--z-muted)",
    label: t.status
      || <EnrichmentGap what="Detection status" audience={audience} compact />,
  };

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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: 14, marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="evidence" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Detection evidence</div>
            <span className="spacer" />
            {/* "1 items" on every single-citation product. The idiom is used
                twice more on this same page. */}
            <span className="b b-muted">{t.evidence.length || 0} item{t.evidence.length === 1 ? "" : "s"}</span>
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: 14, marginBottom: 14 }}>
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
      {/* `tbl-reflow`: this is an eight-column table, the widest on any client
          page, and the only thing holding it up at tablet width was the page
          having no other content to push against. */}
      <div className="card flush">
        <div className="tbl-reflow">
        {/* `tbl-clickable` puts a pointer cursor on every row, which promises a
            row click does something — and the row had no handler at all, so the
            QA sweep reported it as a dead target and a reader got the same
            answer by clicking. The row opens the run it names, which is what
            "View" beside it does; the two buttons stop the event so Compare
            still goes where it says. */}
        <table className="tbl tbl-clickable">
          <thead><tr>
            <th>Run date</th><th>Run ID</th><th>Status</th>
            <th className="col-drop">Source</th><th>Score</th>
            <th className="col-drop">Evidence mode</th><th>Subcaps</th><th>Actions</th>
          </tr></thead>
          <tbody>
            {entity.runs.map(r => (
              <tr key={r.id} title={`Open ${r.id}`}
                  onClick={() => navigate(`/clients/${entity.id}/overview`, { run: r.id })}>
                <td data-label="Run date"><strong>{fmtDate(r.date)}</strong></td>
                <td data-label="Run ID" className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{r.id}</td>
                <td data-label="Status"><span className={`b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`}>{r.status}</span></td>
                <td data-label="Source" className="col-drop"><span className={`b ${r.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>{r.data_source === "DRIVE_PARSE" ? "DRIVE PARSE" : "PROJECT API"}</span></td>
                <td data-label="Score"><MaturityChip score={r.overall} /></td>
                <td data-label="Evidence mode" className="col-drop">{r.evidence_mode}</td>
                <td data-label="Subcaps">{r.subcap_count}</td>
                <td data-label="Actions">
                  <button className="btn btn-tertiary btn-sm" onClick={(ev) => { ev.stopPropagation(); navigate(`/clients/${entity.id}/overview`, { run: r.id }); }}>View</button>
                  <button className="btn btn-tertiary btn-sm" onClick={(ev) => { ev.stopPropagation(); navigate(`/clients/${entity.id}/health`, { run: r.id }); }}>Compare</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ClientContext, ClientHealth, ClientTechStack, ClientTechStackDetail, ClientRuns, evidenceAgeRows, calendarValue });
