/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Live client pages (production only)

   Production divergence, and the most important one in this app: a
   client-scoped page in production renders PROMOTED sections or an honest
   empty state — never the prototype's example content. The prototype's
   pages carry illustrative prose about a fictional bank (three cores, an
   nCino migration, named executive hires); rendered under a real client's
   name that is fabrication, so in LIVE mode those components are not
   reached at all.

   What this module IS, then, is the prototype's layout — the same card
   anatomy, the same grids, the same primitives (ScoreRing, MaturityChip,
   pbar, hm-cell, Row, cards-grid-N) — reading the promoted payload
   instead of the fixture. Every surface here is designed; a section that
   did not promote says so in place, and no raw payload is ever the
   client-facing rendering of a surface.

   Charter constraints this file must honour:
   · no colour comes from the payload — score → band → hex happens here,
     in the ONE resolver (DMA.helpers.maturityHex/maturityClass);
   · nothing is recomputed that the producer already computed (deltas,
     shares, ages, counts all render as promoted);
   · a null derived value renders as an EnrichmentGap naming the field,
     never as 0 and never as a sentinel that looks like data. Not an em
     dash either: an em dash cannot say whether the field was searched,
     held or never asked for, and gives the reader no route to filling it.
   ═══════════════════════════════════════════════════════════════════════ */

const LIVE_PAGE_SECTIONS = {
  overview: ["scores", "firmographics", "why_now", "exec_summary", "opportunity",
             "findings", "leadership", "financial_series", "sentiment",
             "ceilings", "evidence_coverage", "thought_leadership"],
  insights: ["insights", "landscape"],
  heatmap: ["workbook_scores", "focus_areas", "cell_evidence", "evidence",
            "value_chain", "alerts", "safeguard_gates", "evidence_age",
            "cohort_patterns"],
  platform: ["platform_story", "recommendations", "starters", "roadmap", "stairstep"],
  context: ["timeline", "issue_register", "regulatory_standing",
            "context_sentiment", "acquisitions"],
  techstack: ["techstack"],
};

/* Sections whose contract names no payload field yet: promote writes an
   envelope, so `data` is legitimately empty. The reason is structural, not a
   production failure, and it must not read as a broken card. */
const ENVELOPE_ONLY = {
  landscape: "the D4 landscape recomputes from the technology register (T1); its own payload contract is unauthored, so this run promoted an envelope only",
  context_sentiment: "the D5 sentiment contract names no payload field yet - the promoted sentiment for this run is on the overview page",
  value_chain: "the H9 value-chain arrangement is server-derived and pinned at stage 6.3; no contract field exists to promote yet",
};

/* A section with no meaningful content: every key is null, or the only keys
   left are the two that every section carries. */
function isBlank(data) {
  if (!data || typeof data !== "object") return true;
  return !Object.keys(data).some((k) => {
    if (k === "r_layer" || k === "narrative_thread") return false;
    const v = data[k];
    if (v === null || v === undefined || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  });
}

const SECTION_TITLES = {
  scores: "Scores & peer benchmarks", firmographics: "Firmographics",
  why_now: "Why now", exec_summary: "Executive summary",
  opportunity: "Opportunity surface", findings: "Top findings",
  leadership: "Leadership", financial_series: "Financial trajectory",
  sentiment: "Sentiment", ceilings: "Capability ceilings & uncertainty",
  evidence_coverage: "Evidence coverage & tier mix",
  thought_leadership: "Thought leadership",
  insights: "Insight cards", landscape: "Technology landscape",
  workbook_scores: "Workbook grain scores", focus_areas: "Focus areas",
  cell_evidence: "Cell evidence", evidence: "Evidence store",
  value_chain: "Value chain", alerts: "Thin-evidence alerts",
  safeguard_gates: "Safeguard gates", evidence_age: "Evidence age",
  cohort_patterns: "Cross-entity patterns",
  platform_story: "Platform story", recommendations: "Recommendations",
  starters: "Conversation starters", roadmap: "Roadmap", stairstep: "Stair-step",
  timeline: "Timeline", issue_register: "Issue register",
  regulatory_standing: "Regulatory standing", context_sentiment: "Context sentiment",
  acquisitions: "Acquisitions", techstack: "Technology register",
};

/* ══ formatting ═════════════════════════════════════════════════════
   Numbers reach the payload as strings, because the producer must not
   round or localise anything. Presentation happens here, once. */

const NBSP = " ";

/* Renderable text from a payload value. A contract can hand back a shape a
   card did not anticipate; React throws on an object child and one throw used
   to blank the whole page, so nothing reaches JSX without passing through
   here. Objects are summarised from their own naming keys — a client surface
   never shows raw JSON. */
function asText(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v || null;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(" · ") || null;
  if (typeof v === "object") {
    for (const k of ["statement", "text", "label", "name", "title", "clause",
                     "value"]) {
      const t = asText(v[k]);
      if (t) return t;
    }
    return null;
  }
  return String(v);
}

function fmtNum(v, opts) {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  if (!isFinite(n)) return String(v);
  const decimals = (opts && opts.decimals !== undefined)
    ? opts.decimals
    : (String(v).includes(".") ? (String(v).split(".")[1] || "").length : 0);
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals,
                                     maximumFractionDigits: decimals });
}

function fmtMoney(n, unit) {
  const u = String(unit || "").toLowerCase();
  const num = Number(n);
  if (!isFinite(num)) return null;
  if (u.includes("trillion")) return `$${fmtNum(n)}T`;
  if (u.includes("billion")) return `$${fmtNum(n)}B`;
  if (u.includes("million")) return `$${fmtNum(n)}M`;
  if (u.includes("thousand")) return `$${fmtNum(n)}K`;
  return `$${fmtNum(n)}`;
}

/* A firmographic field is {field, value, unit, …}. The unit decides the
   presentation: money scales to a suffix, a percent takes a sign, a bare
   count keeps its noun, and a year is never given a thousands separator. */
function fmtFirmoValue(f) {
  const raw = f.value;
  if (raw === null || raw === undefined || raw === "") return null;
  const unit = String(f.unit || "");
  const u = unit.toLowerCase();
  if (!/^-?[\d.,]+$/.test(String(raw).trim())) return String(raw);  // prose
  if (u.includes("usd") || u.includes("dollar")) return fmtMoney(raw, unit);
  if (u.includes("percent") || unit === "%") return `${fmtNum(raw)}%`;
  if (u === "year") return String(raw);
  if (u.includes("ratio") || u === "x") return `${fmtNum(raw)}×`;
  const n = fmtNum(raw);
  return unitRestatesLabel(f) ? n : (unit ? `${n}${NBSP}${unit}` : n);
}

/* "Employees 767 full and part-time employees" says employees twice. A unit
   whose words the row's own label already carries is redundant on the row; it
   stays in the row's title, so nothing from the payload is lost. */
function unitRestatesLabel(f) {
  const unit = String(f.unit || "").toLowerCase();
  if (!unit) return false;
  const label = firmoLabel(f.field).toLowerCase();
  const stem = (w) => w.replace(/(ies|es|s)$/, "");
  const labelStems = label.split(/[^a-z]+/).filter(Boolean).map(stem);
  return unit.split(/[^a-z]+/).filter(Boolean).map(stem)
    .some((w) => w.length > 3 && labelStems.includes(w));
}

const FIRMO_LABELS = {
  total_assets: "Assets", member_count: "Members", customer_count: "Customers",
  employees: "Employees", branches: "Branches", founded: "Founded",
  net_worth_ratio: "Net worth ratio", charter: "Charter",
  primary_regulator: "Regulator", shares: "Shares", loans: "Loans",
  roa: "ROA", aum: "AUM", deposits: "Deposits", revenue: "Revenue",
  premiums_written: "Premiums written",
};

function firmoLabel(k) {
  return FIRMO_LABELS[k] ||
    String(k).replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

const BAND_CLASS = { activating: "b-m1", building: "b-m2", competing: "b-m3",
                     differentiating: "b-m4" };

/* Band class from either a raw score or a band word. The score path defers to
   the ONE resolver; the word path maps the four-value enum and nothing else —
   an unknown word gets no colour rather than a wrong one. */
function bandClass(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (isFinite(n)) return DMA.helpers.maturityClass(n);
  return BAND_CLASS[String(v).trim().toLowerCase()] || "";
}

/* fmtScore and fmtPctVal return TEXT, because both are also read into title
   attributes, where a React element cannot go. The absent case is therefore a
   plain word here; every JSX site that can receive a null renders
   <EnrichmentGap> instead, which names the field and carries the route to
   enrichment. */
function fmtScore(v) {
  return (v === null || v === undefined) ? "not stated" : Number(v).toFixed(1);
}

function fmtPctVal(v, decimals) {
  if (v === null || v === undefined) return "not stated";
  return `${fmtNum(v, { decimals: decimals === undefined ? 0 : decimals })}%`;
}

/* Delta is PROMOTED, never recomputed here (invariant 8). An absent delta is
   an absent peer comparison, not a zero — it renders as the enrichment gap in
   its compact form, because every delta on this page sits in a narrow
   fixed-width numeric column. */
function DeltaBadge({ delta, direction, audience }) {
  if (delta === null || delta === undefined) {
    return <EnrichmentGap what="Peer delta" audience={audience} compact />;
  }
  const below = direction ? direction === "below" : delta < 0;
  return (
    <span className="f-mono" style={{ fontSize: 11,
      color: below ? "var(--z-below)" : "var(--z-mid)" }}>
      {below ? "▼" : "▲"} {Math.abs(delta).toFixed(2)}
    </span>
  );
}

function ClaimChip({ label, confidence }) {
  if (!label) return null;
  const cls = label === "FACT" ? "b-ph1" : label === "INFERENCE" ? "b-ph0" : "b-purple";
  return (
    <span className="row" style={{ gap: 5 }}>
      <span className={`b ${cls}`}>{label}</span>
      {confidence ? <span className="b">{confidence}</span> : null}
    </span>
  );
}

/* Every surface carries its provenance line — who produced it, when it
   promoted, how many evidence ids it cites. Small, at the card's foot. */
function ProvFoot({ state }) {
  if (!state) return null;
  const bits = [];
  if (state.producer_version) bits.push(state.producer_version);
  if (state.produced_at) bits.push(`promoted ${fmtDate(state.produced_at)}`);
  const n = (state.e_ids || []).length;
  if (n) bits.push(`${n} evidence id${n === 1 ? "" : "s"}`);
  if (!bits.length) return null;
  return (
    <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 10,
                  fontFamily: "var(--font-mono)" }}>{bits.join(" · ")}</div>
  );
}

/* A section that did not promote, was withheld, or lives elsewhere. This
   is the ONLY non-designed rendering left, and it carries no payload. */
function LiveMissing({ name, state }) {
  const es = (state && state.empty_state) || {};
  const kind = ENVELOPE_ONLY[name] ? "no_contract_field"
    : (es.kind || (state && state.data_source) || "unavailable");
  const label = { section_not_promoted: "Not promoted",
                  withheld_for_audience: "Not shown to this audience",
                  served_from_evidence_store: "Read per evidence id",
                  no_contract_field: "No payload contract yet",
                  empty: "Nothing to show" }[kind] || "Unavailable";
  const reason = ENVELOPE_ONLY[name] || es.reason;
  return (
    <div className="card" style={{ marginBottom: 14, padding: "14px 18px" }}>
      <div className="row">
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>
          {SECTION_TITLES[name] || name}</span>
        <span className="spacer" />
        <span className="b">{label}</span>
      </div>
      {reason ? (
        <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginTop: 6,
                      lineHeight: 1.5 }}>{reason}</div>
      ) : null}
    </div>
  );
}

/* One bad field must not take the page. A section that throws degrades to a
   notice naming itself, and its neighbours still render — the alternative,
   which this app shipped until now, is a white screen for the whole client. */
class SectionBoundary extends React.Component {
  constructor(props) { super(props); this.state = { failed: null }; }
  static getDerivedStateFromError(err) { return { failed: err }; }
  componentDidCatch(err) {
    if (typeof console !== "undefined") console.error("section render failed", err);
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="card" style={{ marginBottom: 14, padding: "14px 18px",
              borderLeft: "3px solid var(--z-org)" }}>
          <div className="row">
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>
              {SECTION_TITLES[this.props.name] || this.props.name}</span>
            <span className="spacer" />
            <span className="b b-org">Could not render</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginTop: 6 }}>
            This section promoted, but its payload did not fit the surface. The
            other sections on this page are unaffected.
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function Sec({ name, children }) {
  return <SectionBoundary name={name}>{children}</SectionBoundary>;
}

function SectionHead({ title, note, right }) {
  return (
    <div className="row" style={{ marginBottom: 12 }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{title}</div>
        {note ? <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 2 }}>{note}</div> : null}
      </div>
      <span className="spacer" />
      {right || null}
    </div>
  );
}

/* ══ O1 · snapshot strip: ring · pillar bars · firmographics ═════════
   The prototype's D1 opening card, three columns, unchanged in shape. */
function LiveSnapshot({ scores, firmo, entity, run, state, audience }) {
  const d = scores || {};
  const pillars = d.pillars || [];
  const byId = {};
  pillars.forEach((p) => { byId[p.pillar_id] = p; });

  const fields = ((firmo && firmo.fields) || []).filter((f) => f.value !== null &&
    f.value !== undefined && f.value !== "");

  return (
    <div className="card" style={{ marginBottom: 18, padding: "20px 22px" }}>
      <div style={{ display: "grid",
                    gridTemplateColumns: fields.length ? "1fr 280px" : "1fr",
                    gap: 28, alignItems: "stretch" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
            <ScoreRing score={d.composite} />
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", gap: 8, marginBottom: 8,
                            alignItems: "center", flexWrap: "wrap" }}>
                {d.composite != null ? (
                  <span className={`b ${DMA.helpers.maturityClass(d.composite)}`}>
                    {DMA.helpers.maturityLabel(d.composite).toUpperCase()}</span>
                ) : null}
                {d.posture ? <span className="b b-ph1">POSTURE · {d.posture}</span> : null}
                {d.posture_basis ? <span className="b">{d.posture_basis}</span> : null}
                <ClaimChip label={d.claim_label} confidence={d.confidence} />
              </div>
              {d.framing ? (
                <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5 }}>
                  {d.framing}</div>
              ) : null}
            </div>
          </div>

          {pillars.length ? (
            <div>
              {DMA.PILLARS.map((p) => {
                const row = byId[p.id];
                if (!row) return null;
                const s = row.score, peer = row.peer_median;
                return (
                  <div className="pbar" key={p.id} style={{ cursor: "pointer" }}
                       onClick={() => navigate(`/clients/${entity.id}/heatmap`,
                         { pillar: p.id, run: run && run.id })}>
                    <div className="pbar-name">{p.id} · {p.short}</div>
                    <div className="pbar-track">
                      <div className="pbar-fill" style={{ width: `${(s / 5) * 100}%`,
                        background: DMA.helpers.maturityHex(s) }} />
                      {peer != null ? (
                        <div className="pbar-peer"
                             style={{ left: `calc(${(peer / 5) * 100}% - 1px)` }}
                             title={`Peer median ${fmtScore(peer)}${row.peer_n ? ` · n=${row.peer_n}` : ""}`} />
                      ) : null}
                    </div>
                    {/* .pbar-score is 32px and .pbar-delta 50px, so both take
                        the compact gap — a queue badge here would burst the
                        row. */}
                    <div className="pbar-score">
                      {s == null
                        ? <EnrichmentGap what={`${p.id} pillar score`}
                                         audience={audience} compact />
                        : fmtScore(s)}</div>
                    <div className="pbar-delta">
                      <DeltaBadge delta={row.delta} direction={row.direction}
                                  audience={audience} /></div>
                  </div>
                );
              })}
              <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)",
                            display: "flex", gap: 14, paddingLeft: 122, flexWrap: "wrap" }}>
                <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                  <span style={{ width: 12, height: 4, background: "var(--z-teal)",
                                 borderRadius: 2 }} /> Entity</span>
                <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                  <span style={{ width: 2, height: 10, background: "var(--z-dpur)" }} />
                  Peer median</span>
                {pillars[0] && pillars[0].peer_basis ? (
                  <span>peer basis: {pillars[0].peer_basis}</span>) : null}
              </div>
            </div>
          ) : null}

          {d.narrative_thread ? (
            <div style={{ marginTop: 14, paddingTop: 12,
                          borderTop: "1px solid var(--z-sep)", fontSize: 12,
                          color: "var(--z-body)", lineHeight: 1.55 }}>
              {d.narrative_thread}</div>
          ) : null}
          <ProvFoot state={state} />
        </div>

        {fields.length ? (
          <div style={{ background: "var(--z-lav)", borderRadius: 12, padding: 16 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Firmographics</div>
            {fields.map((f) => (
              <Row key={f.field} k={
                <span style={{ whiteSpace: "nowrap" }}>{firmoLabel(f.field)}</span>} v={
                <span title={[f.unit, f.as_of ? `as of ${f.as_of}` : null,
                              f.source_e_id, f.confidence].filter(Boolean).join(" · ")}>
                  {fmtFirmoValue(f)}
                  {f.recency_band && f.recency_band !== "CURRENT" ? (
                    <span className="b" style={{ marginLeft: 6, fontSize: 8.5 }}>
                      {f.recency_band}</span>) : null}
                  {f.quarantined ? (
                    <span className="b b-org" style={{ marginLeft: 6, fontSize: 8.5 }}>
                      QUARANTINED</span>) : null}
                </span>} />
            ))}
            {((firmo && firmo.fields) || []).some((f) => f.value === null) ? (
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 8,
                            paddingTop: 8, borderTop: "1px solid rgba(0,0,0,.06)" }}>
                Not established: {(firmo.fields || []).filter((f) => f.value === null)
                  .map((f) => firmoLabel(f.field).toLowerCase()).join(", ")}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ══ O2 · why now ══════════════════════════════════════════════════ */
function LiveWhyNow({ data, state }) {
  const signals = (data && data.signals) || [];
  if (!signals.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Why now"
        note="dated triggers, with the cost of waiting and of acting"
        right={<span className="b b-org">{signals.length} signal{signals.length === 1 ? "" : "s"}</span>} />
      <div style={{ display: "grid", gap: 12 }}>
        {signals.map((s, i) => (
          <div key={s.wn_id || i} className="card-tile" style={{ padding: 14 }}>
            <div className="row" style={{ marginBottom: 6, gap: 8 }}>
              {s.dated_on ? <span className="b f-mono">{s.dated_on}</span> : (
                <span className="b b-org">UNDATED</span>)}
              <span className="spacer" />
              <ClaimChip label={s.claim_label} confidence={s.confidence} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.45,
                          marginBottom: 8 }}>{s.trigger}</div>
            <div style={{ display: "grid", gap: 8 }}>
              {[["If this waits", s.consequence_of_waiting],
                ["Cost of acting now", s.cost_of_acting_now],
                ["Why first", s.why_this_sequence]].map(([k, v]) => v ? (
                <div key={k}>
                  <div className="eyebrow" style={{ fontSize: 9.5 }}>{k}</div>
                  <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>
                    {v}</div>
                </div>
              ) : null)}
            </div>
            {(s.linked_subcap_ids || []).length ? (
              <div className="row" style={{ marginTop: 10, gap: 4, flexWrap: "wrap" }}>
                {s.linked_subcap_ids.map((id) => (
                  <span key={id} className="chip f-mono" style={{ fontSize: 9.5 }}>{id}</span>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O3 · SCQA executive summary ═══════════════════════════════════ */
function LiveExecSummary({ data, state }) {
  if (!data) return null;
  const parts = [["Situation", data.situation], ["Complication", data.complication],
                 ["Question", data.question], ["Answer", data.answer],
                 ["Why this order", data.sequencing_rationale],
                 ["Cost of delay", data.cost_of_delay]];
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Executive summary" note="situation · complication · question · answer"
        right={<ClaimChip label={data.claim_label} />} />
      <div style={{ display: "grid", gap: 12 }}>
        {parts.map(([k, v]) => v ? (
          <div key={k}>
            <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 3 }}>{k}</div>
            <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>{v}</div>
          </div>
        ) : null)}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O4 · opportunity surface ══════════════════════════════════════ */
function LiveOpportunity({ data, state }) {
  const tiles = (data && data.tiles) || [];
  const discarded = (data && data.discarded) || [];
  if (!tiles.length && !discarded.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Opportunity surface"
        note="where capability gap meets a platform that closes it" />
      <div className="g4">
        {tiles.slice().sort((a, b) => (a.rank || 99) - (b.rank || 99))
          .map((t, i) => (
          <div key={t.platform || i} className="card-tile" style={{ padding: 14 }}>
            <div className="row" style={{ marginBottom: 8, gap: 6 }}>
              {t.rank != null ? <span className="b b-purple">{t.rank}.</span> : null}
              <span style={{ fontSize: 12.5, fontWeight: 600, flex: 1, minWidth: 0 }}>
                {t.platform}</span>
              {t.composite != null ? (
                <span className="b b-ph1 f-mono" title="composite opportunity score">
                  {fmtNum(t.composite, { decimals: 2 })}</span>) : null}
            </div>
            {t.relevance ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5,
                            marginBottom: 6 }}>{t.relevance}</div>) : null}
            {t.their_stack_context ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5,
                            marginBottom: 6 }}>{t.their_stack_context}</div>) : null}
            {(t.factors || []).length ? (
              <div style={{ marginBottom: 8 }}>
                {t.factors.map((f, j) => (
                  <div key={j} className="row" style={{ fontSize: 10.5, gap: 6 }}>
                    <span className="muted" style={{ minWidth: 104 }}
                          title={f.weight != null ? `weight ${f.weight}` : ""}>
                      {String(f.name || "").replace(/_/g, " ")}</span>
                    <div style={{ flex: 1 }}>
                      <div className="prog" style={{ height: 4 }}>
                        <div className="prog-fill" style={{
                          width: `${Math.min(100, (Number(f.value) / 10) * 100)}%`,
                          background: "var(--z-teal)" }} /></div>
                    </div>
                    <span className="f-mono" style={{ minWidth: 26, textAlign: "right" }}>
                      {fmtNum(f.value)}</span>
                    {f.contribution != null ? (
                      <span className="muted f-mono" style={{ minWidth: 40,
                            textAlign: "right", fontSize: 9.5 }}
                            title="contribution to the composite">
                        +{fmtNum(f.contribution, { decimals: 1 })}</span>) : null}
                  </div>))}
              </div>) : null}
            {t.rank_rationale ? (
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5 }}>
                {t.rank_rationale}</div>) : null}
            {(t.addressable_cells || []).length ? (
              <div style={{ marginTop: 8, paddingTop: 8,
                            borderTop: "1px solid var(--z-sep)" }}>
                <div className="eyebrow" style={{ fontSize: 9, marginBottom: 5 }}>
                  Cells it addresses · {t.addressable_cells.length}</div>
                <div style={{ display: "grid", gap: 4 }}>
                  {t.addressable_cells.slice(0, 6).map((c, j) => (
                    <div key={j} className="row" style={{ gap: 6, fontSize: 10.5 }}>
                      <span className="chip f-mono" style={{ fontSize: 9 }}>
                        {typeof c === "string" ? c : c.subcap_id}</span>
                      {typeof c === "object" && c.current != null ? (
                        <span className={`b ${bandClass(c.current)}`}>
                          {fmtScore(c.current)}</span>) : null}
                      <span style={{ flex: 1, minWidth: 0, color: "var(--z-body)",
                                     lineHeight: 1.4 }}>
                        {typeof c === "object"
                          ? (asText(c.feature_that_addresses_it) || asText(c.name) || "")
                          : ""}</span>
                    </div>))}
                  {t.addressable_cells.length > 6 ? (
                    <span className="muted" style={{ fontSize: 9.5 }}>
                      +{t.addressable_cells.length - 6} more cells</span>) : null}
                </div>
              </div>) : null}
          </div>
        ))}
      </div>
      {discarded.length ? (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--z-sep)" }}>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
            Considered and set aside</div>
          <div style={{ display: "grid", gap: 5 }}>
            {discarded.map((x, i) => (
              <div key={i} style={{ fontSize: 11.5, color: "var(--z-muted)" }}>
                <span style={{ color: "var(--z-dark)", fontWeight: 500 }}>
                  {x.platform || x.name}</span>
                {x.reason || x.why_not ? ` — ${x.reason || x.why_not}` : ""}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O5 · top findings ═════════════════════════════════════════════ */
function LiveFindings({ data, state }) {
  const findings = (data && data.findings) || [];
  const [open, setOpen] = useState(null);
  if (!findings.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Top findings"
        note={data.ranking_basis ? `ranked by ${data.ranking_basis.replace(/_/g, " ")}` : null} />
      {data.narrative_thread ? (
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55,
                      marginBottom: 12 }}>{data.narrative_thread}</div>
      ) : null}
      <div style={{ display: "grid", gap: 8 }}>
        {findings.map((f, i) => {
          const isOpen = open === (f.f_id || i);
          return (
            <div key={f.f_id || i} className="card-tile clickable"
                 style={{ padding: "12px 14px" }}
                 onClick={() => setOpen(isOpen ? null : (f.f_id || i))}>
              <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                <span className="b f-mono">{f.f_id}</span>
                {f.theme ? <span className="b b-purple">{f.theme}</span> : null}
                <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4,
                               flex: 1, minWidth: 0 }}>{f.title}</span>
                {f.consequence ? (
                  <span style={{ fontSize: 10.5, color: "var(--z-org)", textAlign: "right",
                                 maxWidth: 210 }}>{f.consequence}</span>) : null}
                <Icon name={isOpen ? "chevron-d" : "chevron-r"} size={12} />
              </div>
              {isOpen ? (
                <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                  {f.body ? (
                    <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.6 }}>
                      {f.body}</div>) : null}
                  {f.rejected_alternative ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>
                        Alternative considered</div>
                      <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>
                        {f.rejected_alternative}</div>
                    </div>) : null}
                  {f.strategic_alignment ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>
                        Strategic alignment{f.strategic_alignment.score != null
                          ? ` · ${fmtNum(f.strategic_alignment.score, { decimals: 2 })}` : ""}</div>
                      <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>
                        {asText(f.strategic_alignment.statement)}</div>
                    </div>) : null}
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {(f.platform_chips || []).map((p) => (
                      <span key={p} className="chip purple">{p}</span>))}
                    {(f.linked_subcap_ids || []).map((id) => (
                      <span key={id} className="chip f-mono" style={{ fontSize: 9.5 }}>{id}</span>))}
                    <span className="spacer" />
                    <ClaimChip label={f.claim_label} confidence={f.confidence} />
                  </div>
                  <RLayer r={f.r_layer} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* The producer's own challenge record. Internal reading, shown inline
   because a finding without its counter-case is half the finding. */
function RLayer({ r }) {
  if (!r) return null;
  return (
    <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: "10px 12px" }}>
      <div className="row" style={{ marginBottom: 5 }}>
        <span className="eyebrow" style={{ fontSize: 9.5 }}>Challenge record</span>
        <span className="spacer" />
        {r.verdict ? <span className={`b ${r.verdict === "ACCEPT" ? "b-ph1" : "b-org"}`}>
          {r.verdict}</span> : null}
        {r.confidence ? <span className="b">{r.confidence}</span> : null}
      </div>
      {r.hypothesis ? <div style={{ fontSize: 11, marginBottom: 4 }}>
        <b>Hypothesis.</b> {r.hypothesis}</div> : null}
      {r.counter ? <div style={{ fontSize: 11, marginBottom: 4 }}>{r.counter}</div> : null}
      {r.domain_test ? <div style={{ fontSize: 11, marginBottom: 4 }}>
        <b>Domain test.</b> {r.domain_test}</div> : null}
      {(r.probes_run || []).length ? (
        <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
          Probes: {r.probes_run.join(" · ")}</div>) : null}
    </div>
  );
}

/* ══ O6 · leadership roster ════════════════════════════════════════ */
function LiveLeadership({ data, state }) {
  const roster = (data && data.roster) || [];
  if (!roster.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Leadership" note={`${roster.length} named`} />
      <div style={{ display: "grid", gap: 8 }}>
        {roster.map((p, i) => (
          <div key={i} className="card-tile" style={{ padding: "10px 12px" }}>
            <div className="row" style={{ gap: 8 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{p.name}</span>
              <span style={{ fontSize: 11.5, color: "var(--z-body)" }}>{p.title}</span>
              {p.domain ? <span className="b b-purple">{p.domain}</span> : null}
              <span className="spacer" />
              {p.appointed_on ? (
                <span className="b f-mono">since {p.appointed_on}</span>) : null}
              {p.tenure_months != null ? (
                <span className="muted" style={{ fontSize: 10 }}>
                  {p.tenure_months} months</span>) : null}
              {p.confidence ? <span className="b">{p.confidence}</span> : null}
            </div>
            {p.relevance_note ? (
              <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>{p.relevance_note}</div>) : null}
            <div className="row" style={{ marginTop: 4, gap: 6 }}>
              {p.as_of ? <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>
                as of {p.as_of}</span> : null}
              <span className="spacer" />
              {p.source_e_id ? (
                <span className="chip f-mono" style={{ fontSize: 9 }}>{p.source_e_id}</span>) : null}
            </div>
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O7 · financial trajectory ═════════════════════════════════════ */
function LiveFinancials({ data, state, audience }) {
  const series = (data && data.series) || [];
  if (!series.length) return null;
  const points = series.filter((s) => s.value != null);
  const max = Math.max(...points.map((p) => Number(p.value) || 0), 1);
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <SectionHead title="Financial trajectory"
        note={data.trend ? `trend ${data.trend.toLowerCase()}` : null}
        right={data.verified_sparse ? <span className="b b-org">SPARSE</span> : null} />
      <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 90,
                    marginBottom: 8 }}>
        {series.map((p, i) => {
          const v = Number(p.value);
          const h = isFinite(v) ? Math.max(4, (v / max) * 82) : 0;
          return (
            <div key={i} style={{ flex: 1, textAlign: "center" }}
                 title={[p.period, p.value == null ? "not established"
                   : (p.unit ? fmtMoney(p.value, p.unit) : fmtNum(p.value)),
                   p.as_of ? `as of ${p.as_of}` : null]
                   .filter(Boolean).join(" · ")}>
              {p.value == null ? (
                <div style={{ height: 82, border: "1px dashed var(--z-sep)",
                              borderRadius: 4 }} />
              ) : (
                <div style={{ height: h, background: "var(--z-teal)",
                              borderRadius: "4px 4px 0 0" }} />
              )}
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {series.map((p, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center", fontSize: 9.5,
                                color: "var(--z-muted)" }}>
            {/* One column per bar, so both gaps are compact — the bar above
                already carries the dashed outline for an absent figure. */}
            <div className="f-mono">
              {p.period || <EnrichmentGap what="Reporting period"
                                          audience={audience} compact />}</div>
            <div style={{ color: "var(--z-dark)", fontWeight: 500 }}>
              {p.value == null
                ? <EnrichmentGap what={p.period ? `${p.period} figure`
                                                : "Financial figure"}
                                 audience={audience} compact />
                : (p.unit ? fmtMoney(p.value, p.unit) : fmtNum(p.value))}</div>
          </div>
        ))}
      </div>
      {series.some((p) => p.basis) ? (
        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 8 }}>
          {asText(series.find((p) => p.basis).basis)}
          {series.find((p) => p.source_e_id)
            ? ` · ${series.find((p) => p.source_e_id).source_e_id}` : ""}</div>) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O8 · evidence coverage & tier mix ═════════════════════════════ */
function LiveCoverage({ data, state, audience }) {
  if (!data) return null;
  const per = data.per_pillar || [];
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <SectionHead title="Evidence coverage"
        right={data.overall_pct != null ? (
          <span className="b b-ph1 f-mono">{fmtPctVal(data.overall_pct, 1)}</span>) : null} />
      {per.map((p, i) => (
        <div key={p.pillar_id || i} style={{ marginBottom: 9 }}>
          <div className="row" style={{ fontSize: 11, marginBottom: 3, gap: 6 }}>
            <span className="f-mono">{p.pillar_id}</span>
            {p.pillar_name && p.pillar_name !== p.pillar_id ? (
              <span className="muted">{p.pillar_name}</span>) : null}
            <span className="spacer" />
            {p.cells_covered != null && p.cells_total != null ? (
              <span className="muted" style={{ fontSize: 10 }}>
                {fmtNum(p.cells_covered)}/{fmtNum(p.cells_total)}</span>) : null}
            <span className="f-mono">
              {p.pct == null
                ? <EnrichmentGap what={`${p.pillar_id || "Pillar"} evidence coverage`}
                                 audience={audience} compact />
                : fmtPctVal(p.pct, 1)}</span>
            {p.below_gate ? (
              <span className="b b-org" title="below the corpus gate threshold">
                BELOW GATE</span>) : null}
          </div>
          <div className="prog">
            <div className="prog-fill" style={{
              width: `${Math.min(100, Number(p.pct) || 0)}%`,
              background: p.below_gate ? "var(--z-org)" : "var(--z-teal)" }} />
          </div>
        </div>
      ))}
      {data.gate_pct != null ? (
        <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 8 }}>
          Corpus gate threshold {fmtPctVal(data.gate_pct, 0)}</div>) : null}
      {data.denominator_definition ? (
        <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 6,
                      lineHeight: 1.5 }}>{data.denominator_definition}</div>) : null}
      {data.note ? (
        <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 6,
                      lineHeight: 1.5 }}>{data.note}</div>) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O9 · sentiment ════════════════════════════════════════════════ */
function LiveSentiment({ data, state, title }) {
  const bars = (data && data.bars) || [];
  if (!bars.length) return null;
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <SectionHead title={title || "Sentiment"} />
      {bars.map((b, i) => {
        // A rating is only a bar if its own scale gives it bounds. NPS runs
        // -100..100, a star rating 0..5; a bar drawn on the wrong scale is a
        // lie, so an unrecognised scale shows the figure and no bar.
        const scale = String(b.scale || "");
        const m = scale.match(/(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)/);
        const lo = m ? Number(m[1]) : null, hi = m ? Number(m[2]) : null;
        const pct = (m && b.rating != null && hi > lo)
          ? Math.max(0, Math.min(100, ((Number(b.rating) - lo) / (hi - lo)) * 100))
          : null;
        return (
          <div key={i} style={{ marginBottom: 12 }}>
            <div className="row" style={{ fontSize: 11.5, marginBottom: 3, gap: 6 }}>
              <span style={{ fontWeight: 500, flex: 1, minWidth: 0 }}>
                {asText(b.source)}</span>
              {b.audience ? <span className="b">{b.audience}</span> : null}
              {b.rating != null ? (
                <span className="f-mono" style={{ fontWeight: 600 }}>
                  {fmtNum(b.rating, { decimals: 1 })}</span>) : null}
              {b.n != null ? (
                <span className="muted" style={{ fontSize: 10 }}>
                  n={fmtNum(b.n)}</span>) : null}
            </div>
            {pct != null ? (
              <div className="prog"><div className="prog-fill" style={{
                width: `${pct}%`, background: "var(--z-teal)" }} /></div>) : null}
            <div className="row" style={{ marginTop: 4, gap: 6, fontSize: 9.5,
                  color: "var(--z-muted)" }}>
              {b.scale ? <span className="f-mono">{b.scale}</span> : null}
              {b.trend_vs_prior ? <span>{asText(b.trend_vs_prior)}</span> : null}
              <span className="spacer" />
              {b.as_of ? <span>as of {b.as_of}</span> : null}
              {b.url ? (
                <a href={b.url} target="_blank" rel="noreferrer"
                   style={{ color: "var(--z-teal)" }}>source ↗</a>) : null}
              {b.e_id ? <span className="chip f-mono" style={{ fontSize: 9 }}>
                {b.e_id}</span> : null}
            </div>
          </div>
        );
      })}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O10 · capability ceilings ═════════════════════════════════════ */
function LiveCeilings({ data, state }) {
  const rows = (data && data.rows) || [];
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  const shown = all ? rows : rows.slice(0, 8);
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <SectionHead title="Capability ceilings & uncertainty"
        note={`${rows.length} bounded estimate${rows.length === 1 ? "" : "s"}`} />
      <div style={{ display: "grid", gap: 6 }}>
        {shown.map((r, i) => (
          <div key={i} className="card-tile" style={{ padding: "10px 12px" }}>
            <div className="row" style={{ gap: 8 }}>
              <span className="f-mono b">{r.category_id}</span>
              <span style={{ fontSize: 12, fontWeight: 500, flex: 1, minWidth: 0 }}>
                {r.category_name}</span>
              {r.uncertainty_band != null ? (
                <span className="b f-mono" title="uncertainty band on the estimate">
                  ±{fmtNum(r.uncertainty_band, { decimals: 2 })}</span>) : null}
              {r.ceiling != null ? (
                <span className={`b ${bandClass(r.ceiling)}`}
                      title="the highest band the evidence tier licenses">
                  ceiling {isFinite(Number(r.ceiling))
                    ? fmtScore(r.ceiling) : r.ceiling}</span>) : null}
            </div>
            {r.rationale ? (
              <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>{r.rationale}</div>) : null}
            {r.limiting_absence ? (
              <div style={{ fontSize: 11, color: "var(--z-org)", marginTop: 4,
                            lineHeight: 1.5 }}>
                What is missing: {r.limiting_absence}</div>) : null}
            <div className="row" style={{ marginTop: 4, gap: 4, flexWrap: "wrap" }}>
              {(r.urf_modifiers || []).map((m, j) => (
                <span key={j} className="chip" style={{ fontSize: 9.5 }}
                      title="uncertainty-reduction modifier applied to the band">
                  {typeof m === "object" && m
                    ? [asText(m.clause), m.value != null
                        ? fmtNum(m.value, { decimals: 2 }) : null]
                      .filter(Boolean).join(" ")
                    : asText(m)}</span>))}
              <span className="spacer" />
              <ClaimChip label={r.claim_label} confidence={r.confidence} />
            </div>
          </div>
        ))}
      </div>
      {rows.length > 8 ? (
        <button className="btn btn-tertiary btn-sm" style={{ marginTop: 8 }}
                onClick={() => setAll((o) => !o)}>
          {all ? "Show fewer" : `Show all ${rows.length}`}</button>) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ O11 · thought leadership (internal) ═══════════════════════════ */
function LiveThoughtLeadership({ data, state }) {
  const entries = (data && data.entries) || [];
  if (!entries.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Thought leadership"
        note="what the institution says in public, in its own words"
        right={<span className="b b-purple">INTERNAL</span>} />
      <div style={{ display: "grid", gap: 10 }}>
        {entries.map((e, i) => (
          <div key={i} className="card-tile" style={{ padding: 12 }}>
            <div className="row" style={{ gap: 8, marginBottom: 5 }}>
              {e.kind ? <span className="b b-purple">{e.kind}</span> : null}
              {e.author_name ? (
                <span style={{ fontSize: 12, fontWeight: 600 }}>{e.author_name}</span>) : null}
              {e.author_role ? <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {e.author_role}</span> : null}
              <span className="spacer" />
              {e.published_on ? <span className="b f-mono">{e.published_on}</span> : null}
              <ClaimChip label={e.claim_label} />
            </div>
            {e.headline ? (
              <div style={{ fontSize: 12.5, fontWeight: 600, lineHeight: 1.45,
                            marginBottom: 6 }}>{e.headline}</div>) : null}
            {e.quote ? (
              <div style={{ fontSize: 12, fontStyle: "italic", lineHeight: 1.55,
                            borderLeft: "2px solid var(--z-teal)", paddingLeft: 10 }}>
                “{e.quote}”</div>) : null}
            {e.alignment ? (
              <div className="row" style={{ marginTop: 8, gap: 8,
                    alignItems: "flex-start" }}>
                {typeof e.alignment === "object" && e.alignment.value ? (
                  <span className="b b-ph1"
                        title="how this signal relates to the assessment">
                    {e.alignment.value}</span>) : null}
                <span style={{ fontSize: 11.5, color: "var(--z-body)", flex: 1,
                               minWidth: 0, lineHeight: 1.5 }}>
                  {typeof e.alignment === "object"
                    ? asText(e.alignment.clause) : asText(e.alignment)}</span>
              </div>) : null}
            <div className="row" style={{ marginTop: 6, gap: 4, flexWrap: "wrap" }}>
              {(e.linked_subcap_ids || []).map((id) => (
                <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
              <span className="spacer" />
              {e.url ? (
                <a href={e.url} target="_blank" rel="noreferrer"
                   style={{ fontSize: 10, color: "var(--z-teal)" }}
                   onClick={(ev) => ev.stopPropagation()}>source ↗</a>) : null}
              {e.e_id ? <span className="chip f-mono" style={{ fontSize: 9 }}>
                {e.e_id}</span> : null}
            </div>
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H4 · the workbook grid ════════════════════════════════════════
   The prototype's category heatmap, rendered from promoted pillar and
   category scores. Colour is resolved here from the raw score — the
   payload carries no hex, by invariant 7. */
function LiveWorkbookGrid({ data, state, entity, run, onDrill, audience }) {
  const [showPeers, setShowPeers] = useState(true);
  const [pillarFocus, setPillarFocus] = useState(null);
  if (!data) return null;
  const pillars = data.pillars || {};
  const cats = data.categories || {};
  const shown = DMA.PILLARS.filter((p) => !pillarFocus || p.id === pillarFocus);
  const offCatalogue = Object.keys(cats)
    .filter((cid) => !DMA.CATEGORIES.some((c) => c.id === cid)).sort();
  const catsOf = (pid) => Object.keys(cats).filter((c) => c.startsWith(pid)).sort();

  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Maturity grid"
        note={[`${Object.keys(pillars).length} pillars`,
               `${Object.keys(cats).length} categories, as scored in the workbook`,
               offCatalogue.length
                 ? `${offCatalogue.join(", ")} not in the current catalogue`
                 : null].filter(Boolean).join(" · ")}
        right={
          <div className="row" style={{ gap: 10 }}>
            <label className="row" style={{ fontSize: 11, cursor: "pointer" }}>
              <span className={`switch ${showPeers ? "on" : ""}`}
                    onClick={() => setShowPeers((p) => !p)} /> Peers</label>
            {pillarFocus ? (
              <button className="btn btn-tertiary btn-sm"
                      onClick={() => setPillarFocus(null)}>Reset</button>) : null}
          </div>} />

      {/* pillar tiles */}
      <div className="g4" style={{ marginBottom: 18 }}>
        {DMA.PILLARS.map((p) => {
          const row = pillars[p.id];
          if (!row) return null;
          return (
            <div key={p.id} className="card-tile clickable" style={{ padding: 14 }}
                 onClick={() => setPillarFocus(pillarFocus === p.id ? null : p.id)}>
              <div className="row" style={{ marginBottom: 10 }}>
                <div>
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>{p.id}</div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                </div>
                <span className="spacer" />
                <MaturityChip score={row.score} large />
              </div>
              {row.band ? (
                <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginBottom: 6,
                              letterSpacing: ".04em" }}
                     title="band generated by the database from the raw score">
                  {String(row.band).toUpperCase()}</div>) : null}
              <div className="prog"><div className="prog-fill" style={{
                width: `${(row.score / 5) * 100}%`,
                background: DMA.helpers.maturityHex(row.score) }} /></div>
              <div className="row" style={{ marginTop: 8, fontSize: 10.5 }}>
                <span style={{ color: "var(--z-muted)" }}>
                  {row.peer_median == null
                    ? <EnrichmentGap what={`${p.id} peer median`}
                                     audience={audience} compact />
                    : `Peer ${fmtScore(row.peer_median)}`}</span>
                {row.delta != null
                  ? <DeltaBadge delta={Number(row.delta)} audience={audience} /> : null}
                <span className="spacer" />
                <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>
                  {catsOf(p.id).length} categories</span>
              </div>
              {row.source_cell ? (
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 6,
                              fontFamily: "var(--font-mono)" }}>{row.source_cell}</div>) : null}
            </div>
          );
        })}
      </div>

      {/* category grid, per pillar */}
      {shown.map((p) => {
        const ids = catsOf(p.id);
        if (!ids.length) return null;
        return (
          <div key={p.id} style={{ marginBottom: 16 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="b b-purple">{p.id}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
              {pillars[p.id] ? <MaturityChip score={pillars[p.id].score} /> : null}
              <span className="spacer" />
              <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                {ids.length} categories</span>
            </div>
            <div style={{ display: "grid",
                          gridTemplateColumns: `72px repeat(${ids.length}, minmax(0,1fr))`,
                          gap: 4 }}>
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", display: "flex",
                            alignItems: "center", justifyContent: "flex-end",
                            paddingRight: 8 }}>Entity</div>
              {ids.map((cid) => {
                const c = cats[cid];
                return (
                  <button key={cid}
                    className={`hm-cell b ${DMA.helpers.maturityClass(c.score)}`}
                    onClick={() => onDrill && onDrill(cid)}
                    style={{ border: 0, padding: "8px 6px", minHeight: 44 }}
                    title={[cid, c.band, `score ${fmtScore(c.score)}`,
                            c.peer_median != null ? `peer ${fmtScore(c.peer_median)}` : null,
                            c.delta != null ? `delta ${Number(c.delta) >= 0 ? "+" : ""}${Number(c.delta).toFixed(2)}` : null,
                            c.source_cell, "click for cell evidence"]
                           .filter(Boolean).join(" · ")}>
                    <div style={{ display: "flex", flexDirection: "column",
                                  lineHeight: 1.15, gap: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>
                        {c.score == null
                          ? <EnrichmentGap what={`${cid} score`}
                                           audience={audience} compact />
                          : fmtScore(c.score)}</div>
                      {c.delta != null ? (
                        <div style={{ fontSize: 8, fontWeight: 600 }}>
                          {Number(c.delta) >= 0 ? "▲" : "▼"}{Math.abs(Number(c.delta)).toFixed(1)}
                        </div>) : null}
                    </div>
                  </button>
                );
              })}
              {showPeers ? (
                <>
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", display: "flex",
                                alignItems: "center", justifyContent: "flex-end",
                                paddingRight: 8 }}>Peer</div>
                  {ids.map((cid) => {
                    const pm = cats[cid].peer_median;
                    /* A null median is NOT a zero: banded and printed as 0.0
                       it would read as a peer set that scores nothing. It is
                       a gap in the cohort benchmark, and it is enrichable. */
                    return pm == null ? (
                      <div key={cid} className="hm-cell peer"
                           style={{ minHeight: 30, padding: "4px 6px" }}>
                        <EnrichmentGap what={`${cid} peer median`}
                                       audience={audience} compact /></div>
                    ) : (
                      <div key={cid}
                           className={`hm-cell peer b ${DMA.helpers.maturityClass(pm)}`}
                           style={{ minHeight: 30, padding: "4px 6px" }}>
                        {fmtScore(pm)}</div>
                    );
                  })}
                </>
              ) : null}
              <div />
              {ids.map((cid) => {
                const cat = DMA.CATEGORIES.find((c) => c.id === cid);
                const label = cat && cat.name && cat.name !== cid ? cat.name : null;
                return (
                  <div key={`l-${cid}`} style={{ fontSize: 9, color: "var(--z-muted)",
                        textAlign: "center", padding: "4px 2px 0", lineHeight: 1.3 }}>
                    <div className="f-mono">{cid}</div>
                    {label ? <div className="txt-fit-2">{label}</div>
                      : !cat ? (
                        <div className="txt-fit-2" style={{ color: "var(--z-org)" }}
                             title={`${cid} is not in catalogue ${
                               (window.DMA_LIVE && window.DMA_LIVE.catalogue_version) || "current"
                             }; the run scored it, so it renders`}>
                          off-catalogue</div>) : null}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
      <div className="row" style={{ marginTop: 10, gap: 10, flexWrap: "wrap" }}>
        {[["Activating", 1.5], ["Building", 2.5], ["Competing", 3.5],
          ["Differentiating", 4.5]].map(([label, s]) => (
          <span key={label} className="row" style={{ gap: 5, fontSize: 10.5 }}>
            <span style={{ width: 12, height: 12, borderRadius: 3,
                           background: DMA.helpers.maturityHex(s) }} />{label}</span>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H1 · focus areas ══════════════════════════════════════════════ */
function LiveFocusAreas({ data, state, audience }) {
  const areas = (data && data.focus_areas) || [];
  const [open, setOpen] = useState(null);
  if (!areas.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Focus areas"
        note="where the assessment concentrates, in the client's own words" />
      <div style={{ display: "grid", gap: 10 }}>
        {areas.map((fa, i) => {
          const isOpen = open === (fa.fa_id || i);
          const delta = (fa.entity_score != null && fa.peer_score != null)
            ? fa.entity_score - fa.peer_score : null;
          return (
            <div key={fa.fa_id || i} className="card-tile clickable" style={{ padding: 14 }}
                 onClick={() => setOpen(isOpen ? null : (fa.fa_id || i))}>
              <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                <span className="b f-mono">{fa.fa_id}</span>
                <span style={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0,
                               lineHeight: 1.4 }}>{fa.name}</span>
                {fa.entity_score != null ? <MaturityChip score={fa.entity_score} /> : null}
                {fa.peer_score != null ? (
                  <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                    peer {fmtScore(fa.peer_score)}</span>) : null}
                {delta != null ? <DeltaBadge delta={delta} audience={audience} /> : null}
              </div>
              {fa.verbatim_quote ? (
                <div style={{ fontSize: 12, fontStyle: "italic", marginTop: 8,
                              borderLeft: "2px solid var(--z-teal)", paddingLeft: 10,
                              lineHeight: 1.55 }}>“{fa.verbatim_quote}”</div>) : null}
              <div className="row" style={{ marginTop: 8, gap: 6, flexWrap: "wrap" }}>
                {fa.source_document ? (
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    {fa.source_document}{fa.source_page ? ` p.${fa.source_page}` : ""}</span>) : null}
                <span className="spacer" />
                {fa.currency_status ? (
                  <span className={`b ${fa.currency_status === "CONFIRMED_CURRENT"
                    ? "b-ph1" : "b-org"}`}>{fa.currency_status.replace(/_/g, " ")}</span>) : null}
              </div>
              {isOpen ? (
                <div style={{ marginTop: 10, paddingTop: 10,
                              borderTop: "1px solid var(--z-sep)" }}>
                  {fa.currency_note ? (
                    <div style={{ fontSize: 11.5, color: "var(--z-body)",
                                  marginBottom: 8, lineHeight: 1.5 }}>{fa.currency_note}</div>) : null}
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {(fa.involved_subcap_ids || []).map((id) => (
                      <span key={id} className="chip f-mono" style={{ fontSize: 9.5 }}>{id}</span>))}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H2 · cell evidence ════════════════════════════════════════════
   The grid's drill target. 69 flat rows is a list, not a drilldown, so the
   cells group by category and open on the one the grid was clicked on. */
function LiveCellEvidence({ data, state, filter, onClearFilter }) {
  const all = (data && data.cells) || [];
  const [q, setQ] = useState("");
  const [open, setOpen] = useState({});
  if (!all.length) return null;

  const matches = all.filter((c) => {
    const id = c.subcap_id || "";
    if (filter && !String(id).startsWith(filter)) return false;
    if (q && !JSON.stringify(c).toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const groups = {};
  matches.forEach((c) => {
    const cat = String(c.subcap_id || "?").slice(0, 4);
    (groups[cat] = groups[cat] || []).push(c);
  });
  const cats = Object.keys(groups).sort();
  // A filter or a search is itself the intent to look inside.
  const forced = !!(filter || q);
  const catName = (cid) => {
    const c = DMA.CATEGORIES.find((x) => x.id === cid);
    return c && c.name && c.name !== cid ? c.name : null;
  };

  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Cell evidence"
        note={`${matches.length} of ${all.length} evidenced cells across ${cats.length} categor${cats.length === 1 ? "y" : "ies"}`}
        right={
          <div className="row" style={{ gap: 8 }}>
            {filter ? (
              <span className="chip purple" style={{ cursor: "pointer" }}
                    onClick={onClearFilter} title="clear the grid filter">
                {filter} ✕</span>) : null}
            <input className="inp" placeholder="Filter cells…" value={q}
                   onChange={(e) => setQ(e.target.value)}
                   style={{ fontSize: 11, padding: "4px 8px", width: 160 }} />
          </div>} />
      {cats.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {cats.map((cid) => {
            const rows = groups[cid];
            const cited = rows.reduce(
              (a, c) => a + (c.grounded_on != null ? Number(c.grounded_on)
                             : (c.e_ids || []).length), 0);
            const thin = rows.filter((c) => (c.grounded_on != null
              ? Number(c.grounded_on) : (c.e_ids || []).length) === 0).length;
            const isOpen = forced || !!open[cid];
            return (
              <div key={cid} className="card-tile" style={{ padding: 0,
                    overflow: "hidden" }}>
                <div className="row clickable" style={{ gap: 8, padding: "10px 12px",
                      cursor: "pointer" }}
                     onClick={() => setOpen((o) => ({ ...o, [cid]: !o[cid] }))}>
                  <Icon name={isOpen ? "chevron-d" : "chevron-r"} size={11} />
                  <span className="b f-mono">{cid}</span>
                  {catName(cid) ? (
                    <span style={{ fontSize: 12, fontWeight: 600 }}>
                      {catName(cid)}</span>) : null}
                  <span className="spacer" />
                  <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                    {rows.length} cell{rows.length === 1 ? "" : "s"} · {cited} citation{cited === 1 ? "" : "s"}</span>
                  {thin ? <span className="b b-org"
                    title="cells with no citation on this run">{thin} uncited</span> : null}
                </div>
                {isOpen ? (
                  <div style={{ borderTop: "1px solid var(--z-sep)" }}>
                    {rows.map((c, i) => {
                      const n = c.grounded_on != null ? Number(c.grounded_on)
                        : (c.e_ids || []).length;
                      return (
                        <div key={c.subcap_id || i} style={{ padding: "8px 12px",
                              borderBottom: i === rows.length - 1 ? 0
                                : "1px solid var(--z-sep)" }}>
                          <div className="row" style={{ gap: 8 }}>
                            <span className="f-mono" style={{ fontSize: 11,
                                  minWidth: 78 }}>{c.subcap_id}</span>
                            <span className={`b ${n === 0 ? "b-org" : ""}`}
                                  title="grounded_on - the length of the citation list, computed by the database">
                              {n} cited</span>
                            <span className="spacer" />
                            {(c.e_ids || []).slice(0, 8).map((e) => (
                              <span key={e} className="chip f-mono"
                                    style={{ fontSize: 9 }}>{e}</span>))}
                            {(c.e_ids || []).length > 8 ? (
                              <span className="muted" style={{ fontSize: 9.5 }}>
                                +{c.e_ids.length - 8}</span>) : null}
                          </div>
                          {c.synthesis ? (
                            <div style={{ fontSize: 11.5, color: "var(--z-body)",
                                  marginTop: 5, lineHeight: 1.5 }}>
                              {c.synthesis}</div>) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ fontSize: 11.5, color: "var(--z-muted)" }}>
          No evidenced cell matches this filter.</div>
      )}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H5 · thin-evidence alerts ═════════════════════════════════════ */
function LiveAlerts({ data, state }) {
  const alerts = (data && data.alerts) || [];
  if (!alerts.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Thin-evidence alerts"
        right={<span className="b b-org">{alerts.length} open</span>} />
      <div style={{ display: "grid", gap: 6 }}>
        {alerts.map((a, i) => (
          <div key={i} className="card-tile" style={{ padding: "10px 12px",
                borderLeft: "3px solid var(--z-org)" }}>
            <div className="row" style={{ gap: 8 }}>
              {a.subcap_id ? <span className="f-mono b">{a.subcap_id}</span> : null}
              {a.severity ? <span className="b b-org">{a.severity}</span> : null}
              {a.state ? <span className="b">{a.state.replace(/_/g, " ")}</span> : null}
              <span className="spacer" />
              <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                {a.evidence_count != null
                  ? `${a.evidence_count} evidence item${a.evidence_count === 1 ? "" : "s"}` : ""}
                {a.score != null ? ` · scored ${fmtScore(a.score)}` : " · unscored"}
                {a.runs_open ? ` · open ${a.runs_open} run${a.runs_open === 1 ? "" : "s"}` : ""}
              </span>
            </div>
            {a.justification ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 6,
                            lineHeight: 1.55 }}>{a.justification}</div>) : null}
            {a.closure_condition ? (
              <div style={{ fontSize: 11, color: "var(--z-teal)", marginTop: 6 }}>
                Closes on: {a.closure_condition}</div>) : null}
            {(a.sources_searched || []).length ? (
              <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6,
                            lineHeight: 1.5 }}>
                Searched: {a.sources_searched.join(" · ")}</div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H6 · caps applied + safeguard gates ═══════════════════════════
   Two arrays, never one blob (charter correction): caps the assessment
   applied, and SG results — a failing gate DISCLOSES and still promotes,
   so it must render, with its plain label, not be hidden. */
function LiveSafeguards({ data, state }) {
  const caps = (data && data.caps) || [];
  const gates = (data && data.gates) || [];
  if (!caps.length && !gates.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Caps & safeguard gates"
        note="caps the assessment applied · gate results disclosed with the run" />
      {caps.length ? (
        <div style={{ marginBottom: gates.length ? 14 : 0 }}>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
            Caps applied</div>
          <div style={{ display: "grid", gap: 6 }}>
            {caps.map((c, i) => (
              <div key={i} className="card-tile" style={{ padding: "10px 12px" }}>
                <div className="row" style={{ gap: 8 }}>
                  <Icon name="lock" size={11} />
                  <span className="b f-mono">{c.cap_id}</span>
                  {c.kind ? <span className="b b-purple">{c.kind}</span> : null}
                  <span className="spacer" />
                  {(c.affected_categories || []).map((cat) => (
                    <span key={cat} className="chip f-mono" style={{ fontSize: 9.5 }}>
                      {cat}</span>))}
                  {c.ceiling != null ? (
                    <span className={`b ${bandClass(c.ceiling)}`}>
                      ceiling {isFinite(Number(c.ceiling))
                        ? fmtScore(c.ceiling) : c.ceiling}</span>) : null}
                </div>
                {c.rationale ? (
                  <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 5,
                                lineHeight: 1.5 }}>{c.rationale}</div>) : null}
                {(c.e_ids || []).length ? (
                  <div className="row" style={{ marginTop: 5, gap: 4, flexWrap: "wrap" }}>
                    {c.e_ids.map((e) => (
                      <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
                  </div>) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {gates.length ? (
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
            Safeguard gates</div>
          <div style={{ display: "grid", gap: 6 }}>
            {gates.map((g, i) => (
              <div key={i} className="row" style={{ gap: 8, fontSize: 11.5,
                    borderBottom: "1px solid var(--z-sep)", paddingBottom: 6 }}>
                <span className="f-mono b">{g.gate_id || g.gate}</span>
                <span className={`b ${g.result === "PASS" ? "b-ph1"
                  : g.result === "NOT_RUN" ? "" : "b-org"}`}>{g.result}</span>
                <span style={{ flex: 1, minWidth: 0 }}>{g.plain_label}</span>
                {g.reason ? <span className="muted" style={{ fontSize: 10.5 }}>
                  {g.reason}</span> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H7 · evidence age ═════════════════════════════════════════════ */
/* The evidence ladder's own vocabulary (12/24/36/48 months). The DB
   generates band and status; nothing here recomputes them — this map only
   chooses a tone for a value that already arrived. */
const AGE_BANDS = ["FRESH", "CURRENT", "AGING", "DATED", "STALE", "UNDATED"];
const AGE_TONE = { FRESH: "b-ph1", CURRENT: "b-ph1", AGING: "", DATED: "b-org",
                   STALE: "b-org", UNDATED: "b-org" };

function LiveEvidenceAge({ data, state, audience }) {
  const rows = (data && data.rows) || [];
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  const counts = {};
  rows.forEach((r) => {
    const b = r.status || r.band || "UNDATED";
    counts[b] = (counts[b] || 0) + 1;
  });
  const shown = all ? rows : rows.slice(0, 10);
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Evidence age"
        note={`${rows.length} evidence items on the 12/24/36/48-month ladder`} />
      <div className="row" style={{ gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {AGE_BANDS.filter((b) => counts[b]).map((b) => (
          <span key={b} className={`b ${AGE_TONE[b] || ""}`}>{b} {counts[b]}</span>))}
        {Object.keys(counts).filter((b) => !AGE_BANDS.includes(b)).map((b) => (
          <span key={b} className="b">{b} {counts[b]}</span>))}
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {shown.map((r, i) => (
          <div key={r.e_id || i} className="row" style={{ gap: 8, fontSize: 11,
                borderBottom: "1px solid var(--z-sep)", paddingBottom: 4 }}>
            <span className="f-mono" style={{ minWidth: 88 }}>{r.e_id}</span>
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden",
                           textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={r.title || ""}>
              {r.title || <EnrichmentGap what={`Title of ${r.e_id || "this evidence item"}`}
                                         audience={audience} compact />}</span>
            {r.source_domain ? (
              <span className="muted" style={{ minWidth: 110, fontSize: 10,
                    overflow: "hidden", textOverflow: "ellipsis",
                    whiteSpace: "nowrap" }}>{r.source_domain}</span>) : null}
            <span className="muted f-mono" style={{ minWidth: 76, textAlign: "right" }}>
              {r.published_or_asof || "undated"}</span>
            {r.age_months != null ? (
              <span className="muted f-mono" style={{ minWidth: 48, textAlign: "right",
                    fontSize: 10 }} title="months between publication and the run's
 reference date, computed by the database">{r.age_months}mo</span>) : null}
            {r.identity_ok === false ? (
              <span className="b b-org" title="the cited domain did not resolve to this
 entity">IDENTITY</span>) : null}
            <span className={`b ${AGE_TONE[r.status || r.band] || ""}`}>
              {r.status || r.band || "UNDATED"}</span>
          </div>
        ))}
      </div>
      {rows.length > 10 ? (
        <button className="btn btn-tertiary btn-sm" style={{ marginTop: 8 }}
                onClick={() => setAll((o) => !o)}>
          {all ? "Show fewer" : `Show all ${rows.length}`}</button>) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ H8 · cohort patterns (entity ids always stripped server-side) ══ */
function LiveCohorts({ data, state, audience }) {
  const patterns = (data && data.patterns) || [];
  const insufficient = (data && data.insufficient_cohorts) || [];
  if (!patterns.length && !insufficient.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Cross-entity patterns"
        note={data.threshold_pct != null
          ? `shares at or above ${fmtPctVal(data.threshold_pct, 0)} of the cohort` : null} />
      <div style={{ display: "grid", gap: 5 }}>
        {patterns.map((p, i) => (
          <div key={i} className="row" style={{ gap: 8, fontSize: 11.5 }}>
            <span className="f-mono" style={{ minWidth: 70 }}>
              {p.category_id || p.subcap_id}</span>
            <div style={{ flex: 1 }}>
              <div className="prog"><div className="prog-fill" style={{
                width: `${Math.min(100, Number(p.share_pct) || 0)}%`,
                background: "var(--z-dpur)" }} /></div>
            </div>
            <span className="f-mono" style={{ minWidth: 52, textAlign: "right" }}>
              {p.share_pct == null
                ? <EnrichmentGap what="Cohort share" audience={audience} compact />
                : fmtPctVal(p.share_pct, 0)}</span>
          </div>
        ))}
      </div>
      {insufficient.length ? (
        <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 10 }}>
          Cohorts too small to report: {insufficient.map((c) =>
            `${c.sub_vertical} (n=${c.entity_count})`).join(", ")}</div>) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D4 · insight cards ════════════════════════════════════════════ */
function LiveInsights({ data, state }) {
  const cards = (data && data.cards) || [];
  const [open, setOpen] = useState(null);
  if (!cards.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Insight cards" note={`${cards.length} promoted`} />
      {data.narrative_thread ? (
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55,
                      marginBottom: 12 }}>{data.narrative_thread}</div>) : null}
      <div style={{ display: "grid", gap: 10 }}>
        {cards.map((c, i) => {
          const isOpen = open === (c.ic_id || i);
          return (
            <div key={c.ic_id || i} className="card-tile clickable" style={{ padding: 14 }}
                 onClick={() => setOpen(isOpen ? null : (c.ic_id || i))}>
              <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                <span className="b f-mono">{c.ic_id}</span>
                {c.pillar_id ? <span className="b b-purple">{c.pillar_id}</span> : null}
                <span style={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0,
                               lineHeight: 1.4 }}>{c.title}</span>
                {c.severity ? (
                  <span className="b b-org" title={c.severity_rationale || ""}>
                    {c.severity}</span>) : null}
                <Icon name={isOpen ? "chevron-d" : "chevron-r"} size={12} />
              </div>
              {c.so_what_text ? (
                <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 6,
                              lineHeight: 1.55 }}>{c.so_what_text}</div>) : null}
              {isOpen ? (
                <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                  {[["What", c.what_text], ["Why", c.why_text],
                    ["Alternative explanation", c.alternative_explanation],
                    ["Severity rationale", c.severity_rationale],
                    ["Affects", c.affects],
                    ["Validation question", c.validation_question]].map(([k, v]) => v ? (
                    <div key={k}>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>{k}</div>
                      <div style={{ fontSize: 11.5, color: "var(--z-body)",
                                    lineHeight: 1.55 }}>{v}</div>
                    </div>) : null)}
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {c.linked_subcap_id ? (
                      <span className="chip f-mono" style={{ fontSize: 9.5 }}>
                        {c.linked_subcap_id}</span>) : null}
                    {c.linked_rec_id ? (
                      <span className="chip purple" style={{ fontSize: 9.5 }}>
                        → {c.linked_rec_id}</span>) : null}
                    {(c.supporting_e_ids || []).map((e) => (
                      <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
                    <span className="spacer" />
                    <ClaimChip label={c.claim_label} confidence={c.confidence} />
                  </div>
                  <RLayer r={c.r_layer} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D2 · platform story ═══════════════════════════════════════════ */
function LivePlatformStory({ data, state }) {
  const platforms = (data && data.platforms) || [];
  const discarded = (data && data.discarded) || [];
  if (!platforms.length && !discarded.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Platform story"
        note="what the estate needs, and what was ruled out" />
      <div style={{ display: "grid", gap: 10 }}>
        {platforms.map((p, i) => (
          <div key={i} className="card-tile" style={{ padding: 14 }}>
            {(p.gaps || []).length ? (
              <div style={{ marginBottom: 10 }}>
                <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
                  Gaps this platform closes · {p.gaps.length}</div>
                <div style={{ display: "grid", gap: 6 }}>
                  {p.gaps.map((g, j) => (
                    <div key={j} className="card-tile" style={{ padding: "9px 11px" }}>
                      <div className="row" style={{ gap: 8 }}>
                        {g.subcap_id ? (
                          <span className="b f-mono">{g.subcap_id}</span>) : null}
                        {g.pillar ? <span className="b b-purple">{g.pillar}</span> : null}
                        <span style={{ fontSize: 12, fontWeight: 600, flex: 1,
                                       minWidth: 0 }}>{asText(g.name)}</span>
                        {g.current_score != null ? (
                          <MaturityChip score={g.current_score} />) : null}
                        {g.peer_score != null ? (
                          <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                            peer {fmtScore(g.peer_score)}</span>
                        ) : g.peer_basis ? (
                          <span className="b" title={asText(g.peer_note) || ""}>
                            {String(g.peer_basis).replace(/_/g, " ")}</span>) : null}
                      </div>
                      {g.catalogue_path ? (
                        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>
                          {asText(g.catalogue_path)}</div>) : null}
                      {asText(g.gap) ? (
                        <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 4,
                                      lineHeight: 1.5 }}>{asText(g.gap)}</div>) : null}
                      {(g.e_ids || []).length ? (
                        <div className="row" style={{ marginTop: 4, gap: 4,
                              flexWrap: "wrap" }}>
                          <span className="spacer" />
                          {g.e_ids.map((e) => (
                            <span key={e} className="chip f-mono"
                                  style={{ fontSize: 9 }}>{e}</span>))}
                        </div>) : null}
                    </div>))}
                </div>
              </div>) : null}
            {p.story_md ? (
              <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.65,
                            whiteSpace: "pre-wrap" }}>{p.story_md}</div>) : null}
          </div>
        ))}
      </div>
      {discarded.length ? (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--z-sep)" }}>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
            Ruled out</div>
          {discarded.map((x, i) => (
            <div key={i} className="row" style={{ fontSize: 11.5, marginBottom: 5,
                  gap: 8, alignItems: "flex-start" }}>
              <span style={{ fontWeight: 500, minWidth: 190 }}>
                {asText(x.platform) || asText(x.name)}</span>
              {x.relevance != null ? (
                <span className="b f-mono" title="relevance to the assessed gaps">
                  {fmtNum(x.relevance, { decimals: 2 })}</span>) : null}
              <span style={{ color: "var(--z-muted)", flex: 1, minWidth: 0,
                             lineHeight: 1.5 }}>{asText(x.reason)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D2 · recommendations ══════════════════════════════════════════ */
function LiveRecommendations({ data, state, audience }) {
  const recs = (data && data.recommendations) || [];
  const [open, setOpen] = useState(null);
  if (!recs.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Recommendations" note={`${recs.length} authored`} />
      <div style={{ display: "grid", gap: 8 }}>
        {recs.map((r, i) => {
          const isOpen = open === (r.rec_id || i);
          return (
            <div key={r.rec_id || i} className="card-tile clickable"
                 style={{ padding: "12px 14px" }}
                 onClick={() => setOpen(isOpen ? null : (r.rec_id || i))}>
              <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                <span className="b f-mono">{r.rec_id}</span>
                {r.phase ? <span className="b b-purple">{r.phase}</span> : null}
                <span style={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0,
                               lineHeight: 1.4 }}>{r.title}</span>
                {r.effort_band ? <span className="b">{r.effort_band}</span> : null}
                {(r.dma_impact || []).length ? (
                  <span className="b b-ph1" title="cells this recommendation moves">
                    {r.dma_impact.length} cell{r.dma_impact.length === 1 ? "" : "s"}</span>
                ) : null}
                <Icon name={isOpen ? "chevron-d" : "chevron-r"} size={12} />
              </div>
              {r.l3_area || r.l4_feature ? (
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 4 }}>
                  {[r.l3_area, r.l4_feature].filter(Boolean).join(" · ")}</div>) : null}
              {isOpen ? (
                <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                  {[["Root cause", r.root_cause],
                    ["Cost of inaction", r.cost_of_inaction],
                    ["Why in this order", r.sequencing_reason],
                    ["Depends on", (r.dependencies || []).map(asText)
                      .filter(Boolean).join(" · ")]].map(([k, v]) => v ? (
                    <div key={k}>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>{k}</div>
                      <div style={{ fontSize: 11.5, color: "var(--z-body)",
                                    lineHeight: 1.55 }}>{v}</div>
                    </div>) : null)}
                  {(r.dma_impact || []).length ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>
                        Projected movement</div>
                      <div style={{ display: "grid", gap: 3 }}>
                        {r.dma_impact.map((c, j) => (
                          <div key={j} className="row" style={{ gap: 6, fontSize: 10.5 }}
                               title={asText(c.target_basis) || ""}>
                            <span className="chip f-mono" style={{ fontSize: 9 }}>
                              {c.subcap_id}</span>
                            <span style={{ flex: 1, minWidth: 0 }}>{asText(c.name)}</span>
                            <span className="f-mono">
                              {c.current == null
                                ? <EnrichmentGap what={`${c.subcap_id || "Cell"} current score`}
                                                 audience={audience} compact />
                                : fmtScore(c.current)}</span>
                            <Icon name="chevron-r" size={9} />
                            <span className="f-mono" style={{ fontWeight: 600 }}>
                              {c.target == null
                                ? <EnrichmentGap what={`${c.subcap_id || "Cell"} target score`}
                                                 audience={audience} compact />
                                : fmtScore(c.target)}</span>
                            {c.delta != null ? (
                              <span className="f-mono" style={{ minWidth: 34,
                                    textAlign: "right", color: "var(--z-mid)" }}>
                                +{fmtNum(c.delta, { decimals: 2 })}</span>) : null}
                          </div>))}
                      </div>
                      <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 4 }}>
                        projections from the assessment's stated uplift, not measurements
                      </div>
                    </div>) : null}
                  {(r.prerequisites || []).length ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>Prerequisites</div>
                      <div style={{ display: "grid", gap: 4 }}>
                        {r.prerequisites.map((q, j) => (
                          /* wrap: the basis chip is a sentence-shaped status
                             label, so on a narrow card it takes its own line
                             rather than running past the card edge. */
                          <div key={j} className="row"
                               style={{ gap: 6, fontSize: 11, flexWrap: "wrap" }}>
                            {q.verdict ? (
                              <span className={`b ${q.verdict === "MET" ? "b-ph1" : "b-org"}`}>
                                {q.verdict}</span>) : null}
                            {q.cell ? <span className="chip f-mono"
                              style={{ fontSize: 9 }}>{q.cell}</span> : null}
                            <span style={{ flex: 1, minWidth: 0, lineHeight: 1.45 }}>
                              {asText(q.condition) || (q.minimum != null
                                ? `at or above ${fmtScore(q.minimum)}` : "")}
                              {q.current != null ? (
                                <span className="muted"> — currently {fmtScore(q.current)}</span>
                              ) : null}
                              {asText(q.note) ? (
                                <span className="muted"> {asText(q.note)}</span>) : null}
                            </span>
                            {q.basis ? <span className="b">{q.basis}</span> : null}
                          </div>))}
                      </div>
                    </div>) : null}
                  {r.validation_gate && typeof r.validation_gate === "object" ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>Validation gate</div>
                      <div className="row" style={{ gap: 6, fontSize: 11, marginBottom: 4 }}>
                        {r.validation_gate.verdict ? (
                          <span className={`b ${r.validation_gate.verdict === "MET"
                            ? "b-ph1" : "b-org"}`}>{r.validation_gate.verdict}</span>) : null}
                        <span className="f-mono">{asText(r.validation_gate.threshold)}</span>
                        {r.validation_gate.cell ? (
                          <span className="chip f-mono" style={{ fontSize: 9 }}>
                            {r.validation_gate.cell}</span>) : null}
                      </div>
                      {(r.validation_gate.backing_cells || []).length ? (
                        <div className="row" style={{ gap: 5, flexWrap: "wrap" }}>
                          {r.validation_gate.backing_cells.map((b, j) => (
                            <span key={j} className="chip f-mono" style={{ fontSize: 9 }}
                                  title={asText(b.name) || ""}>
                              {b.subcap_id}{" "}
                              {b.score == null
                                ? <EnrichmentGap what={`${b.subcap_id || "Backing cell"} score`}
                                                 audience={audience} compact />
                                : fmtScore(b.score)}</span>))}
                        </div>) : null}
                      {asText(r.validation_gate.grain_note) ? (
                        <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 4,
                                      lineHeight: 1.45 }}>
                          {asText(r.validation_gate.grain_note)}</div>) : null}
                    </div>) : null}
                  {r.kpi_triple && typeof r.kpi_triple === "object" ? (
                    <div>
                      <div className="eyebrow" style={{ fontSize: 9.5 }}>
                        KPI{r.kpi_triple.baseline_as_of
                          ? ` · baseline as of ${r.kpi_triple.baseline_as_of}` : ""}</div>
                      <div style={{ display: "grid",
                                    gridTemplateColumns: "repeat(3, minmax(0,1fr))",
                                    gap: 8 }}>
                        {[["Metric", r.kpi_triple.metric],
                          ["Baseline", r.kpi_triple.baseline],
                          ["Target", r.kpi_triple.target]].map(([k, v]) => (
                          <div key={k}>
                            <div style={{ fontSize: 9, color: "var(--z-muted)",
                                          textTransform: "uppercase",
                                          letterSpacing: ".06em" }}>{k}</div>
                            <div style={{ fontSize: 11, lineHeight: 1.45 }}>
                              {asText(v) || <EnrichmentGap what={`KPI ${k.toLowerCase()}`}
                                                           audience={audience} compact />}</div>
                          </div>))}
                      </div>
                    </div>) : null}
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {(r.evidence_ids || []).map((e) => (
                      <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
                    <span className="spacer" />
                    <ClaimChip label={r.claim_label} />
                  </div>
                  <RLayer r={r.r_layer} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D2 · conversation starters ════════════════════════════════════ */
function LiveStarters({ data, state }) {
  const starters = (data && data.starters) || [];
  if (!starters.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Conversation starters"
        note="questions the evidence earns the right to ask" />
      <div style={{ display: "grid", gap: 8 }}>
        {starters.slice().sort((a, b) => (a.rank || 99) - (b.rank || 99))
          .map((st, i) => (
          <div key={i} className="card-tile" style={{ padding: "12px 14px" }}>
            <div className="row" style={{ gap: 8, marginBottom: 5 }}>
              {st.rank != null ? <span className="b b-purple">{st.rank}.</span> : null}
              {st.opens_on ? <span className="b">{st.opens_on}</span> : null}
              <span className="spacer" />
              {st.named_gap_subcap_id ? (
                <span className="chip f-mono" style={{ fontSize: 9.5 }}>
                  {st.named_gap_subcap_id}</span>) : null}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.5 }}>
              {st.text}</div>
            {st.followup_question ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 6,
                            lineHeight: 1.5 }}>Follow up: {st.followup_question}</div>) : null}
            {st.peer_reference ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 5,
                            lineHeight: 1.5 }}>Peer: {st.peer_reference}</div>) : null}
            {st.their_system_reference ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 3,
                            lineHeight: 1.5 }}>
                Their estate: {st.their_system_reference}</div>) : null}
            {(st.e_ids || []).length ? (
              <div className="row" style={{ marginTop: 6, gap: 4, flexWrap: "wrap" }}>
                {st.e_ids.map((e) => (
                  <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
              </div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D2 · roadmap ══════════════════════════════════════════════════ */
function LiveRoadmap({ data, state }) {
  const phases = (data && data.phases) || [];
  if (!phases.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Roadmap" note={`${phases.length} phases, in sequence`} />
      <div style={{ display: "grid",
                    gridTemplateColumns: `repeat(${phases.length}, minmax(0,1fr))`,
                    gap: 10 }}>
        {phases.map((p, i) => (
          <div key={i} className="card-tile" style={{ padding: 14,
                borderTop: "3px solid var(--z-teal)" }}>
            <div className="row" style={{ marginBottom: 6 }}>
              <span className="b b-purple">{i + 1}</span>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{p.phase}</span>
            </div>
            {p.horizon ? (
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginBottom: 6 }}>
                {p.horizon}</div>) : null}
            {p.rationale ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>
                {p.rationale}</div>) : null}
            {(p.depends_on || []).length ? (
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 6 }}>
                after {p.depends_on.join(" · ")}</div>) : null}
            {(p.rec_ids || []).length ? (
              <div className="row" style={{ marginTop: 8, gap: 4, flexWrap: "wrap" }}>
                {p.rec_ids.map((id) => (
                  <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
              </div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D2 · stair-step ladder ════════════════════════════════════════ */
function LiveStairstep({ data, state }) {
  const ladder = (data && data.ladder) || {};
  const steps = ladder.steps || [];
  if (!steps.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Stair-step" note={ladder.theme || null} />
      <div style={{ display: "grid", gap: 8 }}>
        {steps.map((st, i) => (
          <div key={i} className="card-tile" style={{ padding: "12px 14px",
                marginLeft: i * 18 }}>
            <div className="row" style={{ gap: 8 }}>
              <span className="b b-purple">{st.step_level != null ? st.step_level : i + 1}</span>
              <span style={{ fontSize: 12.5, fontWeight: 600, flex: 1, minWidth: 0 }}>
                {st.label}</span>
              {st.effort_band ? <span className="b">{st.effort_band}</span> : null}
              {st.current_position ? (
                <span className="b b-ph1" title="the estate is here today">YOU ARE HERE</span>
              ) : null}
            </div>
            {st.entry_condition ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>Entry: {st.entry_condition}</div>) : null}
            {st.unlocks ? (
              <div style={{ fontSize: 11, color: "var(--z-teal)", marginTop: 5 }}>
                Unlocks: {st.unlocks}</div>) : null}
            {(st.blocking_findings || []).length ? (
              <div className="row" style={{ marginTop: 5, gap: 4, flexWrap: "wrap" }}>
                <span style={{ fontSize: 10, color: "var(--z-org)" }}>Blocked by:</span>
                {st.blocking_findings.map((f, i) => {
                  const id = findingChipId(f);
                  return (
                    <span key={`${id}-${i}`} className="chip f-mono"
                          style={{ fontSize: 9 }}>{id}</span>);
                })}
              </div>) : null}
            {(st.covered_subcap_ids || []).length ? (
              <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 5 }}>
                {st.covered_subcap_ids.length} cells covered</div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D5 · timeline ═════════════════════════════════════════════════ */
function LiveTimeline({ data, state }) {
  const events = (data && data.events) || [];
  if (!events.length && !data.storyline) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Timeline"
        note={data.arc_shape ? data.arc_shape.replace(/_/g, " ") : null}
        right={data.verified_sparse ? <span className="b b-org">SPARSE</span> : null} />
      {data.storyline ? (
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.6,
                      marginBottom: 14 }}>{data.storyline}</div>) : null}
      <div style={{ borderLeft: "2px solid var(--z-sep)", paddingLeft: 16 }}>
        {events.map((e, i) => (
          <div key={i} style={{ position: "relative", paddingBottom: 14 }}>
            <span style={{ position: "absolute", left: -22, top: 4, width: 8, height: 8,
                           borderRadius: 4, background: e.event_date
                             ? "var(--z-teal)" : "var(--z-org)" }} />
            <div className="row" style={{ gap: 8 }}>
              <span className="b f-mono">{e.event_date || "undated"}</span>
              {e.kind ? <span className="b b-purple">{e.kind}</span> : null}
              <span className="spacer" />
              {/* Split, never printed whole — the token is the badge, the
                  clause renders under the body. `maturity_effect` arrives as
                  "TOKEN — one clause of reasoning" and as one string it is a
                  paragraph inside a pill. */}
              {(window.splitMaturityEffect
                ? window.splitMaturityEffect(e.maturity_effect).token : null) ? (
                <span className="b b-ph1" title="effect on assessed maturity">
                  {window.splitMaturityEffect(e.maturity_effect).token
                    .replace(/_/g, " ")}</span>) : null}
              <ClaimChip label={e.claim_label} />
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 600, marginTop: 4,
                          lineHeight: 1.45 }}>{e.title}</div>
            {e.body ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 4,
                            lineHeight: 1.5 }}>{e.body}</div>) : null}
            {/* The reasoning half of `maturity_effect`, not the enum. The
                enum's own word is the badge above. */}
            {(window.splitMaturityEffect
              ? window.splitMaturityEffect(e.maturity_effect).reason : null) ? (
              <div style={{ fontSize: 11.5, color: "var(--z-dark)", marginTop: 5,
                            paddingLeft: 9, borderLeft: "2px solid var(--z-lav)",
                            lineHeight: 1.5 }}>
                {window.splitMaturityEffect(e.maturity_effect).reason}</div>) : null}
            <div className="row" style={{ marginTop: 5, gap: 4, flexWrap: "wrap" }}>
              {(e.capability_ids || []).map((id) => (
                <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
              <span className="spacer" />
              {(e.e_ids || []).map((x) => (
                <span key={x} className="chip f-mono" style={{ fontSize: 9 }}>{x}</span>))}
            </div>
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D5 · issue register ═══════════════════════════════════════════ */
function LiveIssueRegister({ data, state }) {
  const issues = (data && data.issues) || [];
  if (!issues.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Issue register" note={`${issues.length} recorded`} />
      <div style={{ display: "grid", gap: 6 }}>
        {issues.map((x, i) => (
          <div key={x.issue_id || i} className="card-tile" style={{ padding: "10px 12px" }}>
            <div className="row" style={{ gap: 8 }}>
              {x.issue_id ? <span className="b f-mono">{x.issue_id}</span> : null}
              {x.severity ? <span className="b b-org">{x.severity}</span> : null}
              <span style={{ fontSize: 12, fontWeight: 500, flex: 1, minWidth: 0 }}>
                {x.title}</span>
              {x.status ? <span className="b">{x.status}</span> : null}
              {x.opened_on ? <span className="muted f-mono" style={{ fontSize: 10 }}
                title="opened">{x.opened_on}</span> : null}
              {x.resolved_on ? <span className="b b-ph1 f-mono" style={{ fontSize: 9 }}
                title="resolved">→ {x.resolved_on}</span> : null}
            </div>
            {x.rationale ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>{x.rationale}</div>) : null}
            <div className="row" style={{ marginTop: 6, gap: 4, flexWrap: "wrap" }}>
              {(x.linked_subcap_ids || []).length ? (
                <span style={{ fontSize: 10, color: "var(--z-muted)" }}>Caps:</span>) : null}
              {(x.linked_subcap_ids || []).map((id) => (
                <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
              <span className="spacer" />
              {(x.e_ids || []).map((e) => (
                <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
            </div>
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D5 · regulatory standing ══════════════════════════════════════ */
function LiveRegulatory({ data, state, audience }) {
  if (!data) return null;
  const enf = data.enforcement_actions || [];
  const abs = data.absence_of_enforcement || null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Regulatory standing" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
        <div>
          {/* Full-width label/value rows, so these carry the queue badge. */}
          <Row k="Primary regulator" v={data.primary_regulator
            || <EnrichmentGap what="Primary regulator" audience={audience} />} />
          <Row k="Licence type" v={data.license_type
            || <EnrichmentGap what="Licence type" audience={audience} />} />
          <Row k="Charter date" v={data.charter_date
            || <EnrichmentGap what="Charter date" audience={audience} />} />
          <Row k="Additional" v={(data.additional_regulators || []).join(" · ")
            || <EnrichmentGap what="Additional regulators" audience={audience} />} />
          <Row k="Jurisdictions" v={(data.jurisdictions || []).join(" · ")
            || <EnrichmentGap what="Jurisdictions" audience={audience} />} />
        </div>
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 6 }}>
            Enforcement</div>
          {enf.length ? (
            <div style={{ display: "grid", gap: 6 }}>
              {enf.map((a, i) => (
                <div key={i} className="card-tile" style={{ padding: "8px 10px" }}>
                  <div className="row" style={{ gap: 6 }}>
                    <span className="b b-org">{a.kind || "ACTION"}</span>
                    {a.dated_on ? <span className="b f-mono">{a.dated_on}</span> : null}
                  </div>
                  <div style={{ fontSize: 11.5, marginTop: 4 }}>{a.detail || a.title}</div>
                </div>
              ))}
            </div>
          ) : abs ? (
            <div>
              <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                <span className={`b ${abs.verified ? "b-ph1" : "b-org"}`}>
                  {abs.verified ? "NONE FOUND · VERIFIED" : "NOT VERIFIED"}</span>
              </div>
              {(abs.sources_searched || []).length ? (
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5 }}>
                  Searched: {abs.sources_searched.join(" · ")}</div>) : null}
            </div>
          ) : (
            <div style={{ fontSize: 11.5, color: "var(--z-muted)" }}>Not established.</div>
          )}
        </div>
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D5 · acquisitions ═════════════════════════════════════════════ */
function LiveAcquisitions({ data, state, audience }) {
  const rows = (data && data.rows) || [];
  if (!rows.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Acquisitions & mergers" note={`${rows.length} recorded`} />
      <div style={{ display: "grid", gap: 6 }}>
        {rows.map((r, i) => (
          <div key={i} className="card-tile" style={{ padding: "10px 12px" }}>
            <div className="row" style={{ gap: 8 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{r.target_name}</span>
              {r.kind ? <span className="b b-purple">{r.kind}</span> : null}
              <span className="spacer" />
              {r.closed_on ? <span className="b f-mono">{r.closed_on}</span> : null}
              {r.status ? <span className="b">{r.status}</span> : null}
              {(window.splitMaturityEffect
                ? window.splitMaturityEffect(r.maturity_effect).token : null) ? (
                <span className="b b-ph1" title="effect on assessed maturity">
                  {window.splitMaturityEffect(r.maturity_effect).token
                    .replace(/_/g, " ")}</span>) : null}
            </div>
            {r.scale_metrics && typeof r.scale_metrics === "object" ? (
              <div className="row" style={{ gap: 10, marginTop: 5, flexWrap: "wrap" }}>
                {Object.keys(r.scale_metrics).map((k) => (
                  <span key={k} style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                    {k.replace(/_/g, " ")}{" "}
                    <b style={{ color: "var(--z-dark)" }}>
                      {fmtNum(r.scale_metrics[k]) || asText(r.scale_metrics[k])
                        || <EnrichmentGap what={`${r.target_name || "Target"} ${
                              k.replace(/_/g, " ")}`}
                              audience={audience} compact />}</b></span>))}
              </div>) : null}
            {r.integration_target ? (
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 5 }}>
                Lands on: {r.integration_target}</div>) : null}
            {r.effect_note ? (
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>{r.effect_note}</div>) : null}
            {(r.affected_subcap_ids || []).length ? (
              <div className="row" style={{ marginTop: 6, gap: 4, flexWrap: "wrap" }}>
                {r.affected_subcap_ids.map((id) => (
                  <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
              </div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D6 · technology register ══════════════════════════════════════
   Four required statuses (charter correction): CONFIRMED · INFERRED ·
   CLAIMED · ABSENT, and the four layer keys OPS/CUST/DATA/INFRA — never
   L2–L5, which would collide with evidence levels. */
const TECH_STATUS = {
  CONFIRMED: { cls: "b-ph1", note: "verified in evidence" },
  INFERRED: { cls: "b-purple", note: "derived, not stated" },
  CLAIMED: { cls: "b-org", note: "asserted, unverified" },
  ABSENT: { cls: "", note: "searched, not found" },
};
const TECH_LAYERS = [["OPS", "Operations"], ["CUST", "Customer"],
                     ["DATA", "Data"], ["INFRA", "Infrastructure"]];
const LAYER_NAME = { OPS: "Operations", CUST: "Customer", DATA: "Data",
                     INFRA: "Infrastructure" };

function LiveTechStack({ data, state }) {
  const items = (data && data.items) || [];
  const [layer, setLayer] = useState(null);
  const [status, setStatus] = useState(null);
  if (!items.length) return null;
  const rows = items.filter((it) =>
    (!layer || it.layer === layer) && (!status || it.status === status));
  const countBy = (key, v) => items.filter((it) => it[key] === v).length;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Technology register"
        note={`${rows.length} of ${items.length} systems`}
        right={
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            <div className="toggle-row">
              <button className={!layer ? "on" : ""} onClick={() => setLayer(null)}>All</button>
              {TECH_LAYERS.filter(([k]) => countBy("layer", k)).map(([k, name]) => (
                <button key={k} className={layer === k ? "on" : ""}
                        onClick={() => setLayer(layer === k ? null : k)}
                        title={name}>{k} {countBy("layer", k)}</button>))}
            </div>
          </div>} />
      <div className="row" style={{ gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {Object.keys(TECH_STATUS).map((s) => {
          const n = countBy("status", s);
          if (!n) return null;
          return (
            <span key={s} className={`b ${TECH_STATUS[s].cls}`}
                  style={{ cursor: "pointer",
                           opacity: status && status !== s ? 0.45 : 1 }}
                  title={TECH_STATUS[s].note}
                  onClick={() => setStatus(status === s ? null : s)}>{s} {n}</span>
          );
        })}
      </div>
      <div style={{ display: "grid", gap: 5 }}>
        {rows.map((it, i) => {
          const st = TECH_STATUS[it.status] || TECH_STATUS.ABSENT;
          const provisional = it.status === "CLAIMED" || it.status === "INFERRED";
          return (
            <div key={i} className="card-tile" style={{ padding: "9px 12px",
                  border: provisional ? "1px dashed var(--z-sep)" : undefined }}>
              <div className="row" style={{ gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, minWidth: 0 }}>
                  {it.product}</span>
                {it.vendor && it.vendor !== it.product ? (
                  <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                    {it.vendor}</span>) : null}
                <span className="spacer" />
                {it.pillar_id ? <span className="b b-purple">{it.pillar_id}</span> : null}
                {it.layer ? <span className="b" title={LAYER_NAME[it.layer] || it.layer}>
                  {it.layer}</span> : null}
                {it.evidence_level ? (
                  <span className="chip f-mono" style={{ fontSize: 9.5 }}
                        title="evidence level on the L1–L4 ladder">
                    {it.evidence_level}</span>) : null}
                <span className={`b ${st.cls}`} title={st.note}>{it.status}</span>
              </div>
              {it.detection_basis ? (
                <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4,
                              lineHeight: 1.5 }}>{it.detection_basis}</div>) : null}
              <div className="row" style={{ marginTop: 4, gap: 4, flexWrap: "wrap" }}>
                {(it.linked_subcap_ids || []).slice(0, 6).map((id) => (
                  <span key={id} className="chip f-mono" style={{ fontSize: 9 }}>{id}</span>))}
                <span className="spacer" />
                {(it.e_ids || []).map((e) => (
                  <span key={e} className="chip f-mono" style={{ fontSize: 9 }}>{e}</span>))}
              </div>
            </div>
          );
        })}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ page assembly ═════════════════════════════════════════════════
   Each page lays its promoted sections out in the prototype's order and
   grid. A section that did not promote renders LiveMissing, in place —
   the page never silently loses a row. */

function PageHead({ eyebrow, title, sub, right }) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {sub ? <div className="sub">{sub}</div> : null}
      </div>
      {right ? <div className="actions">{right}</div> : null}
    </div>
  );
}

function LiveClientPage({ entity, run, tab, live }) {
  const { audience } = useApp();
  const [cellFilter, setCellFilter] = useState(null);
  const page = tab === "health" ? "heatmap" : tab;
  const sections = LIVE_PAGE_SECTIONS[page];

  if (tab === "runs") {
    return <LiveRuns entity={entity} run={run} />;
  }
  if (!sections) {
    return (
      <div className="empty">
        <h3>Not a promoted surface</h3>
        <p>The {tab} view is not part of the promoted page set.</p>
      </div>
    );
  }
  if (live && live.loading) return <SectionLoader />;
  if (live && live.error) {
    return (
      <div className="empty">
        <h3>Could not load this page</h3>
        <p>{live.error}</p>
      </div>
    );
  }

  const S = (name) => liveSection(live, name);
  const St = (name) => liveSectionState(live, name);
  const has = (name) => { const d = S(name); return !!d && !isBlank(d); };
  const missing = (name) => <LiveMissing key={name} name={name} state={St(name)} />;

  const runMeta = (live && live.run) || {};
  const subline = [
    runMeta.request_id,
    runMeta.scored_cells != null && runMeta.catalogue_cells != null
      ? `${fmtNum(runMeta.scored_cells)} of ${fmtNum(runMeta.catalogue_cells)} cells scored`
      : null,
    runMeta.ccg_catalog_version ? `catalogue ${runMeta.ccg_catalog_version}` : null,
    runMeta.promoted_at ? `promoted ${fmtDate(runMeta.promoted_at)}` : null,
  ].filter(Boolean).join(" · ");

  if (page === "overview") {
    return (
      <div>
        <PageHead eyebrow="Assessment overview" title={entity.name} sub={subline} />
        {has("scores") || has("firmographics") ? (
          <Sec name="scores"><LiveSnapshot scores={S("scores")} firmo={S("firmographics")}
                        entity={entity} run={run} state={St("scores")}
                        audience={audience} /></Sec>
        ) : missing("scores")}
        {has("why_now") ? <Sec name="why_now"><LiveWhyNow data={S("why_now")} state={St("why_now")} /></Sec>
          : missing("why_now")}
        {has("exec_summary") ? <Sec name="exec_summary"><LiveExecSummary data={S("exec_summary")}
          state={St("exec_summary")} /></Sec>
          : missing("exec_summary")}
        {has("opportunity") ? <Sec name="opportunity"><LiveOpportunity data={S("opportunity")}
          state={St("opportunity")} /></Sec>
          : missing("opportunity")}
        <div style={{ display: "grid", gridTemplateColumns: has("leadership")
                        ? "1.55fr 1fr" : "1fr", gap: 16, marginBottom: 18,
                      alignItems: "start" }}>
          {has("findings") ? <Sec name="findings"><LiveFindings data={S("findings")} state={St("findings")} /></Sec>
          : missing("findings")}
          {has("leadership") ? <Sec name="leadership"><LiveLeadership data={S("leadership")}
            state={St("leadership")} /></Sec>
          : null}
        </div>
        <div className="section-label" style={{ display: "flex", alignItems: "baseline",
              gap: 8, margin: "4px 0 12px" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)",
                         textTransform: "uppercase", letterSpacing: ".06em" }}>
            Evidence &amp; benchmarks</span>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
            from the scoring workbook, evidence index and peer set</span>
        </div>
        <div className="cards-grid-3" style={{ marginBottom: 16 }}>
          {has("financial_series") ? <Sec name="financial_series"><LiveFinancials data={S("financial_series")}
            state={St("financial_series")} audience={audience} /></Sec>
          : missing("financial_series")}
          {has("evidence_coverage") ? <Sec name="evidence_coverage"><LiveCoverage data={S("evidence_coverage")}
            state={St("evidence_coverage")} audience={audience} /></Sec>
          : missing("evidence_coverage")}
          {has("sentiment") ? <Sec name="sentiment"><LiveSentiment data={S("sentiment")}
            state={St("sentiment")} /></Sec>
          : missing("sentiment")}
        </div>
        {has("ceilings") ? <div style={{ marginBottom: 18 }}>
          <Sec name="ceilings">
            <LiveCeilings data={S("ceilings")} state={St("ceilings")} /></Sec></div>
          : missing("ceilings")}
        {audience !== "customer" ? (
          has("thought_leadership")
            ? <Sec name="thought_leadership">
                <LiveThoughtLeadership data={S("thought_leadership")}
                                       state={St("thought_leadership")} /></Sec>
            : missing("thought_leadership")
        ) : null}
      </div>
    );
  }

  if (page === "heatmap") {
    return (
      <div>
        <PageHead eyebrow="Maturity heatmap" title={`Where ${entity.name} is today`}
                  sub={subline} />
        {has("workbook_scores") ? (
          <Sec name="workbook_scores">
            <LiveWorkbookGrid data={S("workbook_scores")} state={St("workbook_scores")}
                              entity={entity} run={run} onDrill={setCellFilter}
                              audience={audience} /></Sec>
        ) : missing("workbook_scores")}
        {has("focus_areas") ? <Sec name="focus_areas"><LiveFocusAreas data={S("focus_areas")}
          state={St("focus_areas")} audience={audience} /></Sec>
          : missing("focus_areas")}
        {has("cell_evidence") ? (
          <Sec name="cell_evidence">
            <LiveCellEvidence data={S("cell_evidence")} state={St("cell_evidence")}
                              filter={cellFilter}
                              onClearFilter={() => setCellFilter(null)} /></Sec>
        ) : missing("cell_evidence")}
        {has("value_chain") ? <Sec name="value_chain"><LiveValueChain data={S("value_chain")}
          state={St("value_chain")} /></Sec>
          : missing("value_chain")}
        {has("alerts") ? <Sec name="alerts"><LiveAlerts data={S("alerts")} state={St("alerts")} /></Sec>
          : missing("alerts")}
        {has("safeguard_gates") ? <Sec name="safeguard_gates"><LiveSafeguards data={S("safeguard_gates")}
          state={St("safeguard_gates")} /></Sec>
          : missing("safeguard_gates")}
        {has("evidence_age") ? <Sec name="evidence_age"><LiveEvidenceAge data={S("evidence_age")}
          state={St("evidence_age")} audience={audience} /></Sec>
          : missing("evidence_age")}
        {has("cohort_patterns") ? <Sec name="cohort_patterns"><LiveCohorts data={S("cohort_patterns")}
          state={St("cohort_patterns")} audience={audience} /></Sec>
          : missing("cohort_patterns")}
        {missing("evidence")}
      </div>
    );
  }

  if (page === "insights") {
    return (
      <div>
        <PageHead eyebrow="Insights" title={`What the evidence says about ${entity.name}`}
                  sub={subline} />
        {has("insights") ? <Sec name="insights"><LiveInsights data={S("insights")} state={St("insights")} /></Sec>
          : missing("insights")}
        {has("landscape") ? <Sec name="landscape"><LiveLandscape data={S("landscape")}
          state={St("landscape")} /></Sec>
          : missing("landscape")}
      </div>
    );
  }

  if (page === "platform") {
    return (
      <div>
        <PageHead eyebrow="Platform recommendation"
                  title={`What ${entity.name} should build next`} sub={subline} />
        {has("platform_story") ? <Sec name="platform_story"><LivePlatformStory data={S("platform_story")}
          state={St("platform_story")} /></Sec>
          : missing("platform_story")}
        {has("recommendations") ? <Sec name="recommendations"><LiveRecommendations data={S("recommendations")}
          state={St("recommendations")} audience={audience} /></Sec>
          : missing("recommendations")}
        {has("roadmap") ? <Sec name="roadmap"><LiveRoadmap data={S("roadmap")} state={St("roadmap")} /></Sec>
          : missing("roadmap")}
        {has("stairstep") ? <Sec name="stairstep"><LiveStairstep data={S("stairstep")} state={St("stairstep")} /></Sec>
          : missing("stairstep")}
        {has("starters") ? <Sec name="starters"><LiveStarters data={S("starters")} state={St("starters")} /></Sec>
          : missing("starters")}
      </div>
    );
  }

  if (page === "context") {
    return (
      <div>
        <PageHead eyebrow="Context" title={`How ${entity.name} got here`} sub={subline} />
        {has("timeline") ? <Sec name="timeline"><LiveTimeline data={S("timeline")} state={St("timeline")} /></Sec>
          : missing("timeline")}
        {has("acquisitions") ? <Sec name="acquisitions"><LiveAcquisitions data={S("acquisitions")}
          state={St("acquisitions")} audience={audience} /></Sec>
          : missing("acquisitions")}
        {has("regulatory_standing") ? <Sec name="regulatory_standing"><LiveRegulatory data={S("regulatory_standing")}
          state={St("regulatory_standing")} audience={audience} /></Sec>
          : missing("regulatory_standing")}
        {has("issue_register") ? <Sec name="issue_register"><LiveIssueRegister data={S("issue_register")}
          state={St("issue_register")} /></Sec>
          : missing("issue_register")}
        {has("context_sentiment") ? <Sec name="context_sentiment"><LiveSentiment data={S("context_sentiment")}
          state={St("context_sentiment")} title="Context sentiment" /></Sec>
          : missing("context_sentiment")}
      </div>
    );
  }

  if (page === "techstack") {
    return (
      <div>
        <PageHead eyebrow="Technology" title={`${entity.name}'s estate`} sub={subline} />
        {has("techstack") ? <Sec name="techstack"><LiveTechStack data={S("techstack")} state={St("techstack")} /></Sec>
          : missing("techstack")}
      </div>
    );
  }
  return null;
}

/* ══ Run register ══════════════════════════════════════════════════
   Not a promoted page: the run rows come from the directory, which is the
   one materialised view the app reads for header and rows alike
   (invariant 8). Active is whichever run promote flagged — never recomputed
   here, and never inferred from ordering. */
function LiveRuns({ entity, run }) {
  const runs = (entity.runs || []).slice();
  return (
    <div>
      <PageHead eyebrow="Run history" title={`${entity.name} · runs`}
        sub={`${runs.length} promoted run${runs.length === 1 ? "" : "s"}`} />
      {runs.length ? (
        <div className="card" style={{ padding: "18px 20px" }}>
          <div style={{ display: "grid", gap: 6 }}>
            {runs.map((r, i) => {
              const active = r.status === "ACTIVE";
              return (
                <div key={r.run_id || i} className="card-tile clickable"
                     style={{ padding: "12px 14px",
                       borderLeft: active ? "3px solid var(--z-teal)" : undefined }}
                     onClick={() => navigate(`/clients/${entity.id}/overview`,
                       { run: r.id })}>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="b f-mono">{r.id}</span>
                    <span className={`b ${active ? "b-ph1" : ""}`}>
                      {active ? "ACTIVE" : r.status}</span>
                    {r.overall != null ? <MaturityChip score={r.overall} /> : null}
                    <span className="spacer" />
                    {r.subcap_count != null ? (
                      <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                        {fmtNum(r.subcap_count)} cells scored</span>) : null}
                    {r.promoted_at ? (
                      <span className="muted f-mono" style={{ fontSize: 10 }}>
                        promoted {fmtDate(r.promoted_at)}</span>) : null}
                  </div>
                  <div className="row" style={{ marginTop: 4, gap: 8, fontSize: 9.5,
                        color: "var(--z-muted)" }}>
                    <span className="f-mono">{r.run_id}</span>
                    <span className="spacer" />
                    {r.date ? <span>assessed {r.date}</span>
                      : <span>assessment date not stated in the package</span>}
                    {r.data_source ? <span className="b">{r.data_source}</span> : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="empty"><h3>No promoted runs</h3>
          <p>This entity exists in the register but has never promoted a run.</p></div>
      )}
    </div>
  );
}

/* ══ H3 · value chain (optional heatmap section) ═══════════════════ */
function LiveValueChain({ data, state }) {
  const stages = (data && (data.stages || data.rows)) || [];
  if (!stages.length) return null;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Value chain" note="capability read along the member journey" />
      <div style={{ display: "grid",
                    gridTemplateColumns: `repeat(${stages.length}, minmax(0,1fr))`,
                    gap: 6 }}>
        {stages.map((s, i) => (
          <div key={i} className="card-tile" style={{ padding: 12 }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 6 }}>
              {s.stage || s.name}</div>
            {s.score != null ? <MaturityChip score={s.score} /> : null}
            {(s.subcap_ids || []).length ? (
              <div style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 6 }}>
                {s.subcap_ids.length} cells</div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

/* ══ D4 · technology landscape (recomputed from the T1 register) ════ */
function LiveLandscape({ data, state }) {
  const tiles = (data && (data.tiles || data.layers)) || [];
  if (!tiles.length) return <LiveMissing name="landscape" state={state} />;
  return (
    <div className="card" style={{ marginBottom: 18, padding: "18px 20px" }}>
      <SectionHead title="Technology landscape"
        note="recomputed from the technology register, never stored" />
      <div className="g4">
        {tiles.map((t, i) => (
          <div key={i} className="card-tile" style={{ padding: 14 }}>
            <div className="row" style={{ marginBottom: 6 }}>
              <span className="b">{t.layer || t.key}</span>
              <span className="spacer" />
              {t.count != null ? <span className="f-mono" style={{ fontSize: 15,
                fontWeight: 700 }}>{fmtNum(t.count)}</span> : null}
            </div>
            {t.label || t.name ? (
              <div style={{ fontSize: 11.5, fontWeight: 500 }}>{t.label || t.name}</div>) : null}
            {t.detail ? (
              <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 5,
                            lineHeight: 1.5 }}>{t.detail}</div>) : null}
          </div>
        ))}
      </div>
      <ProvFoot state={state} />
    </div>
  );
}

Object.assign(window, { LiveClientPage, LIVE_PAGE_SECTIONS, SECTION_TITLES,
                        fmtNum, fmtMoney, fmtFirmoValue, firmoLabel });
