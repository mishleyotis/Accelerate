/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · New data-driven cards (real DMA deliverable shapes)
   ───────────────────────────────────────────────────────────────────────
   Every card below renders from a DMA.* accessor and is tagged with a
   data-source="<canonical file> :: <field>" attribute on its root element
   AND a // SOURCE: comment, so the extraction-script bindings are
   discoverable directly from the code. Full map: SOURCES.md.

   Cards: EvidenceTierCard · SentimentCard · FinancialTrajectoryCard
          CoverageByPillarCard · CeilingEstimateCard
   All INTERNAL-only cards respect the audience toggle (hidden for customer).
   ═══════════════════════════════════════════════════════════════════════ */

/* Absent is not empty. In production an accessor returns null when the
   section did not promote, and a card that renders zeros in that case
   asserts a measurement nobody made. Each card says which section is
   missing instead.

   `note` is this card's own sentence, written here. `section` is the
   section id, and where the run PROMOTED an empty_state — the producer's
   own account of what they searched and what would close it — that account
   is what the reader gets, because it is the answer and the sentence here
   is only a placeholder for not having one. */
function CardAbsent({ icon, title, note, section }) {
  return (
    <div className="card flush">
      <div className="card-head">
        <div className="row"><Icon name={icon} size={14} /><h3>{title}</h3></div>
        <span className="b">{absenceBadge(section)}</span>
      </div>
      <div className="card-body">
        {section
          ? <SectionEmpty section={section} absent={note} empty={note} />
          : (
            <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55 }}>
              {note}
            </div>
          )}
      </div>
    </div>
  );
}

/* ── Evidence tier distribution (T1–T5) ────────────────────────────────
   SOURCE: 01_evidence/research_handoff.json :: evidence_summary.tier_distribution */
function EvidenceTierCard({ entity }) {
  const s = DMA.evidenceSummaryFor(entity.id);
  if (!s) return <CardAbsent icon="evidence" title="Evidence tier distribution"
    note="This run's evidence store has not been read, so the tier mix cannot be counted." />;
  const tiers = Object.entries(s.tiers || {});
  const max = Math.max(...tiers.map(([, v]) => v), 1);
  return (
    <div className="card flush" data-source="research_handoff.json :: evidence_summary.tier_distribution">
      <div className="card-head">
        <div className="row"><Icon name="evidence" size={14} /><h3>Evidence tier distribution</h3></div>
        <span className="b b-muted">{s.total_items} items · {s.total_facts} facts</span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120, padding: "4px 0 0" }}>
          {tiers.map(([t, v]) => {
            const tier = DMA.getTier(t) || {};
            return (
              <div key={t} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }} title={tier.label || t}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", fontVariantNumeric: "tabular-nums" }}>{v}</div>
                <div style={{ width: "100%", height: `${v / max * 84}px`, minHeight: 3, background: tier.color || "var(--z-mid)", borderRadius: "4px 4px 0 0", transition: "height var(--motion-slow) var(--ease)" }} />
                <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{t}</div>
              </div>
            );
          })}
        </div>
        <div className="row" style={{ marginTop: 12, gap: 6, flexWrap: "wrap" }}>
          {Object.entries(s.claims).filter(([, v]) => v > 0).map(([k, v]) => (
            <span key={k} className="chip" title="claim_distribution">{k.replace("_", " ").toLowerCase()} · {v}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Multi-source sentiment scorecard (O9) ─────────────────────────────
   SOURCE: overview.sentiment :: bars[], themes[], gap_analysis, narrative_thread

   TWO VARIANTS, by owner decision 1 (2026-10-04), which supersedes the
   "withheld from customer" rule of TRD §11 for this section only:

     internal   bars, themes with their cap statements and the cells they
                bear on, the B2B/B2C gap and its analysis, the narrative
     customer   REDUCED — bars and themes. No cell codes, no cap statements
                (cap vocabulary), no internal sources, no reasoning trace.

   The server's default-deny walker decides what reaches each audience; the
   card ALSO refuses to draw the internal half for a customer, so a payload
   that arrived unredacted still cannot put a cell code on a client's page.

   RC-03 / D-01: this card read `bars[]` and nothing else. Six promoted
   themes, a narrative thread and every cap statement reached no screen, and
   an employee group with three themes read "Not established for this run."
   The "Industry avg" header and the gap chip read `industry_avg` and
   `b2b_b2c_gap`, which no contract declares; the chip is now computed from
   `gap_analysis.b2b_b2c` and the header figure is gone. */
function SentimentCard({ entity, audience }) {
  const isCust = audience === "customer";
  const s = DMA.sentimentFor(entity.id);
  if (!s) return <CardAbsent icon="users" title="Sentiment"
    note="No sentiment promoted for this run." section="overview.sentiment" />;
  const Row = ({ r }) => {
    // No stated scale means no bounds, and a bar drawn on assumed bounds is
    // a claim the producer never made. But the reader of the scale has to
    // understand the producer's own notation: this divided the score by
    // `scale` when `scale` was a STRING ("0-100 % of employees agreeing",
    // "1-5 stars"), so every row whose scale was not written with ".."
    // showed a number beside an empty track — Great Place To Work at 88 and
    // the App Store at 4.9 both blank, while NPS alone drew a bar.
    //
    // It also has to use BOTH bounds. NPS runs from -100, so 79.8 sits nine
    // tenths up its range; dividing by the maximum alone put it at four
    // fifths and understated the one row that did render.
    const frac = scaleFraction(r.score, r.scale);
    const pct = frac === null ? null : frac * 100;
    // Tone follows the position within the row's OWN scale, not a 5-point
    // assumption — 88 on a percentage and 4.9 on five stars are both strong,
    // and the old thresholds called the first one weak.
    const tone = frac === null ? "var(--z-muted)"
      : frac >= 0.75 ? "var(--z-teal)" : frac >= 0.5 ? "var(--z-org)" : "var(--z-below)";
    return (
      <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 40px", gap: 8, alignItems: "center", padding: "5px 0" }}>
        <div style={{ fontSize: 11, color: "var(--z-body)", minWidth: 0, overflowWrap: "anywhere" }}>{r.source}<span style={{ color: "var(--z-muted)" }}> · {r.metric}</span></div>
        <div style={{ height: 7, background: "var(--z-sep)", borderRadius: 4, overflow: "hidden" }}>
          {pct == null ? null : <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", background: tone, borderRadius: 4, transition: "width var(--motion-slow) var(--ease)" }} />}
        </div>
        {/* A row can arrive with a source, a metric and no rating — the bar
            was found but the figure was not stated. `compact` because the
            cell is 40px of a three-column grid. */}
        <div style={{ fontSize: 12, fontWeight: 600, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.score == null ? <EnrichmentGap what={r.metric ? `${r.source} · ${r.metric}` : r.source || "Rating"} audience={audience} compact /> : fx(r.score, 1)}</div>
      </div>
    );
  };
  /* One theme. The THEME is the reviewers' own recurring pattern and both
     audiences read it. The cap statement — which cell it caps, at what level
     and why — and the cell chips are the assessment's working: internal. */
  const cellName = (id) => {
    const L = (typeof window !== "undefined" && window.DMA_ENTITY) || entity;
    const c = DMA.getSubcap(L, id);
    return c && c.name && c.name !== id ? c.name : null;
  };
  const Theme = ({ t }) => (
    <div data-sentiment-theme={t.audience || "unstated"}
         style={{ padding: "6px 0", borderTop: "1px solid var(--z-sep)" }}>
      <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.45 }}>{t.theme}</div>
      {!isCust && t.cap_statement ? (
        <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.55, marginTop: 3 }}>{t.cap_statement}</div>
      ) : null}
      {!isCust && t.mapped_subcap_ids.length ? (
        <div className="row" style={{ gap: 4, flexWrap: "wrap", marginTop: 4 }}>
          {t.mapped_subcap_ids.map(id => (
            <span key={id} className="chip f-mono" style={{ fontSize: 10 }}
                  title={cellName(id) ? `${id} · ${cellName(id)}` : id}>{id}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
  const themesFor = (a) => (s.themes || []).filter(t => (t.audience || "unstated") === a);
  const groups = [
    { key: "employee", label: "Employee", bars: s.employee || [] },
    { key: "customer", label: "Customer", bars: s.customer || [] },
    { key: "industry", label: "Industry", bars: s.industry || [] },
  ];
  // Employee and customer always show — the contract's two core audiences —
  // and an empty one says what the PAYLOAD holds for it, which is the only
  // thing this card knows. Industry shows only when the run says something.
  const shown = groups.filter(g => g.key !== "industry" || g.bars.length || themesFor("industry").length);
  const head = { fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", margin: "10px 0 2px" };
  return (
    <div className="card flush" data-source="overview.sentiment :: bars[],themes[],gap_analysis">
      <div className="card-head">
        <div className="row"><Icon name="users" size={14} /><h3>Sentiment</h3>{!isCust && s.b2b_b2c_gap ? <span className="b b-org">B2B/B2C gap</span> : null}</div>
      </div>
      <div className="card-body">
        {shown.map((g, gi) => {
          const th = themesFor(g.key);
          return (
            <React.Fragment key={g.key}>
              <div style={{ ...head, marginTop: gi === 0 ? 0 : 10 }}>{g.label}</div>
              {g.bars.map((r, i) => <Row key={g.key + i} r={r} />)}
              {th.map((t, i) => <Theme key={`${g.key}-t${i}`} t={t} />)}
              {!g.bars.length && !th.length ? (
                <div style={{ fontSize: 11, color: "var(--z-muted)" }}>No rating or theme for this audience in this run.</div>
              ) : !g.bars.length ? (
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2 }}>No rated line for this audience; the themes above are read from review and complaint text.</div>
              ) : null}
            </React.Fragment>
          );
        })}
        {(s.ungrouped || []).length || themesFor("unstated").length ? (
          <React.Fragment>
            <div style={head}>Audience not stated</div>
            {(s.ungrouped || []).map((r, i) => <Row key={"u" + i} r={r} />)}
            {themesFor("unstated").map((t, i) => <Theme key={"ut" + i} t={t} />)}
          </React.Fragment>) : null}
        {!isCust && s.gap_analysis ? (
          <div style={{ marginTop: 10, padding: "8px 10px", background: "var(--z-lav)", borderRadius: 6, fontSize: 11, lineHeight: 1.55, color: "var(--z-body)" }}>
            {s.gap_analysis.b2b_b2c ? <div><strong>B2B/B2C gap · </strong>{s.gap_analysis.b2b_b2c}</div> : null}
            {s.gap_analysis.internal_external ? <div style={{ marginTop: 4 }}><strong>Internal/external gap · </strong>{s.gap_analysis.internal_external}</div> : null}
          </div>
        ) : null}
        {/* The thread is the producer's synthesis across bars, themes and
            gaps — internal. The customer's reduced card is bars and themes
            (decision 1), and nothing else is added to it here. */}
        {!isCust && s.narrative_thread ? (
          <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic" }}>{s.narrative_thread}</div>
        ) : null}
        <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).sentiment} what="rows" audience={audience} />
      </div>
    </div>
  );
}

/* The footer's two counts, each rendered only where the run states one.

   `${f.branches} branches · ${employees.toLocaleString()} FTE` asserted both
   unconditionally: a run with no branch count printed "null branches", and a
   headcount stated in words ("more than 800") threw on `.toLocaleString()`
   of a NaN-coerced null and took the card down to its boundary. `fmtCount`
   renders a number with separators and a stated-in-words figure as the words
   the producer wrote; a count nobody stated contributes nothing. */
function footerCounts(f) {
  const emp = (f.employees || [])[(f.employees || []).length - 1];
  return [
    fmtCount(f.branches) != null ? `${fmtCount(f.branches)} branches` : null,
    // "employees", not "FTE". Short strings slipped past both the payload
    // expander and CG-27 — each skips anything under twelve characters — so a
    // three-letter unit survived every abbreviation sweep and rendered on the
    // overview footer of every client.
    fmtCount(emp) != null ? `${fmtCount(emp)} employees` : null,
  ].filter(Boolean).join(" · ") || null;
}

/* ── Financial trajectory ──────────────────────────────────────────────
   SOURCE: 00_entity_profile/financial_baseline.json + entity_profile.json */
function FinancialTrajectoryCard({ entity }) {
  const f = DMA.financialsFor(entity.id);
  if (!f || !(f.fy || []).length) return <CardAbsent icon="money"
    title="Financial trajectory"
    note="No financial series promoted for this run." section="overview.financial_series" />;
  const values = (f.series_values || []).filter(v => v != null);
  const maxA = values.length ? Math.max(...values) : 1;
  /* A TRAJECTORY needs at least two points. With one, `value / max * 80px`
     is 80px by construction — a single full-height, full-width bar that reads
     as a trend and is a claim the run never made. The producer's own section
     says so ("a multi-year series needs three dated points and one could be
     established"); this renders the figure and that sentence instead of
     drawing a chart out of a single measurement. */
  if (f.fy.length < 2) {
    const only = f.fy[0];
    return (
      <div className="card flush" data-source="overview.financial_series :: series[]">
        <div className="card-head">
          <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
          <span className="b b-org">Single point</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 26, fontWeight: 700, color: "var(--z-dark)" }}>
            {fmtAssets(f.series_values[0], f.unit)}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--z-muted)", marginTop: 2 }}>
            {String(only).replace("FY", "")}{f.basis ? ` · ${f.basis}` : ""}
          </div>
          <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.55, marginTop: 10 }}>
            One dated point was established, so no trajectory is drawn. A trend
            line through a single measurement would assert a direction this run
            did not evidence.
          </div>
          <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
            <span className="chip">{f.regulator}</span>
            <span>{f.geography}</span>
            <span className="spacer" />
            <span>{footerCounts(f)}</span>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="card flush" data-source="overview.financial_series :: series[],net_income_m[],nim_pct[]">
      <div className="card-head">
        <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{f.headline}</span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120 }}>
          {/* Every money label on this card comes out of `fmtMoney` — the
              same call the firmographics Assets row makes. Built by
              interpolation, `$${value}${unit}`, the bar label printed
              `$9687804914` for a run that stated its magnitude in full while
              the row thirty pixels away rendered the identical figure as
              $9.7B. NIM is not in this section's contract, so the tooltip
              names it only when the run carries it. */}
          {f.fy.map((y, i) => {
            const money = fmtMoney(f.series_values[i], f.unit);
            return (
            <div key={y} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}
                 title={[y, money, f.nim_pct[i] != null ? `NIM ${f.nim_pct[i]}%` : null].filter(Boolean).join(" · ")}>
              <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--z-dark)" }}>{money}</div>
              <div style={{ width: "100%", height: `${(f.series_values[i] || 0) / maxA * 80}px`, background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0", transition: "height var(--motion-slow) var(--ease)" }} />
              <div className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{y.replace("FY", "'")}</div>
            </div>
          );})}
        </div>
        <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
          <span className="chip">{f.regulator}</span>
          <span>{f.geography}</span>
          <span className="spacer" />
          <span>{footerCounts(f)}</span>
        </div>
      </div>
    </div>
  );
}

/* ── Coverage by pillar ─────────────────────────────────────────────────
   SOURCE: 03_scoring_workbook/export_coverage_stats.csv */
function CoverageByPillarCard({ entity }) {
  const c = DMA.coverageFor(entity.id);
  if (!c) return <CardAbsent icon="check" title="Evidence coverage"
    note="No coverage figures promoted for this run." section="overview.evidence_coverage" />;
  return (
    <div className="card flush" data-source="export_coverage_stats.csv :: by_pillar[].pct">
      <div className="card-head">
        <div className="row"><Icon name="check" size={14} /><h3>Evidence coverage</h3></div>
        <span className="b b-above">{c.overall_pct}% overall</span>
      </div>
      <div className="card-body">
        {c.by_pillar.map(p => {
          const pill = DMA.PILLARS.find(x => x.id === p.pillar);
          const pass = p.pct >= c.gate_pct;
          return (
            <div key={p.pillar} style={{ display: "grid", gridTemplateColumns: "90px 1fr 38px", gap: 8, alignItems: "center", padding: "5px 0" }} title={`${p.scored}/${p.subcaps} subcaps`}>
              <div style={{ fontSize: 11, color: "var(--z-body)" }}>{pill ? pill.short : p.pillar}</div>
              <div style={{ height: 7, background: "var(--z-sep)", borderRadius: 4, overflow: "hidden", position: "relative" }}>
                <div style={{ position: "absolute", left: `${c.gate_pct}%`, top: -2, bottom: -2, width: 1, background: "var(--z-org)" }} />
                <div style={{ width: `${p.pct}%`, height: "100%", background: pass ? "var(--z-teal)" : "var(--z-org)", borderRadius: 4, transition: "width var(--motion-slow) var(--ease)" }} />
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: pass ? "var(--z-teal)" : "var(--z-org)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{p.pct}%</div>
            </div>
          );
        })}
        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6 }}>Orange line = {c.gate_pct}% hard gate</div>
      </div>
    </div>
  );
}

/* ── Capability ceiling + uncertainty bands ────────────────────────────
   SOURCE: 02_research_workbook/uncertainty_bands.json :: {base,modifiers,total} */
function CeilingEstimateCard({ entity, audience }) {
  if (audience === "customer") return null;       // ceilings are internal estimates
  const { openEvidence } = useApp();
  const [open, setOpen] = useState(null);
  const u = DMA.uncertaintyFor(entity.id);
  if (!u) return <CardAbsent icon="stack" title="Capability ceiling & uncertainty"
    note="No ceiling estimates promoted for this run." section="overview.ceilings" />;
  const rows = Object.entries(u);
  return (
    <div className="card flush" data-source="uncertainty_bands.json :: total,modifiers,evidence ; peer_comparison_table.csv :: *_Ceiling">
      <div className="card-head">
        <div className="row"><Icon name="stack" size={14} /><h3>Capability ceiling &amp; uncertainty</h3></div>
        <span className="b b-purple">{rows.length} categories · click to drill</span>
      </div>
      <div className="card-body" style={{ maxHeight: 340, overflowY: "auto" }}>
        {rows.map(([cat, d]) => {
          const cdef = DMA.getCategory(cat);
          const lo = Math.max(1, d.ceiling - d.band), hi = Math.min(5, d.ceiling + d.band);
          const pct = v => ((v - 1) / 4) * 100;
          const tone = d.ceiling <= 2 ? "var(--z-below)" : d.ceiling < 3 ? "var(--z-org)" : "var(--z-teal)";
          const isOpen = open === cat;
          const ev = (d.evidence || []).map(id => DMA.getEvidence(id)).filter(Boolean);
          return (
            <div key={cat} style={{ borderBottom: "1px solid var(--z-sep)" }}>
              <button onClick={() => setOpen(o => o === cat ? null : cat)}
                style={{ width: "100%", display: "grid", gridTemplateColumns: "128px 1fr 62px 16px", gap: 8, alignItems: "center", padding: "8px 0", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
                <div style={{ fontSize: 10.5, color: "var(--z-body)" }}><span className="f-mono">{cat}</span> {cdef ? cdef.name.slice(0, 14) : ""}</div>
                {/* `lo`/`hi` are arithmetic ON the ceiling, so a null ceiling
                    makes them a fabricated pair (1.0–0.0), not an em dash —
                    the title must not assert bounds nobody stated. */}
                <div style={{ position: "relative", height: 8, background: "var(--z-sep)", borderRadius: 4 }} title={d.ceiling == null ? `${cat} ceiling not stated` : `Band ${fx(lo, 1)}–${fx(hi, 1)}`}>
                  <div style={{ position: "absolute", left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%`, top: 0, bottom: 0, background: "rgba(124,93,201,.25)", borderRadius: 4 }} />
                  <div style={{ position: "absolute", left: `calc(${pct(d.ceiling)}% - 4px)`, top: -1, width: 8, height: 10, borderRadius: 2, background: tone }} />
                </div>
                <div style={{ fontSize: 11, fontWeight: 600, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {/* adaptUncertainty yields `ceiling: null` when the row's
                      ceiling is neither a number nor a band word, and fx prints
                      an em dash for null — utils.jsx keeps fx returning a
                      string on purpose and says the guard belongs to each site
                      that renders a bare score. This is one of them.
                      The band goes with it: "±0.4" beside a point nobody stated
                      asserts an uncertainty about a value that does not exist.
                      `compact` because the column is 62px. */}
                  {d.ceiling == null
                    ? <EnrichmentGap what={`${cat} ceiling`} audience={audience} compact />
                    : <React.Fragment>{fx(d.ceiling, 1)}<span style={{ color: "var(--z-muted)", fontWeight: 400 }}> ±{d.band}</span></React.Fragment>}
                </div>
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={12} style={{ color: "var(--z-muted)" }} />
              </button>
              {isOpen ? (
                <div style={{ padding: "2px 0 12px", paddingLeft: 4 }}>
                  {d.rationale ? <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, marginBottom: 8 }}>{d.rationale}</div> : null}
                  {d.modifiers && d.modifiers.length ? (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 3 }}>Ceiling modifiers</div>
                      {d.modifiers.map((m, i) => <div key={i} style={{ fontSize: 11, color: "var(--z-org)", fontFamily: "var(--font-mono)" }}>{m}</div>)}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>Evidence · click to open</div>
                  {ev.length ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {ev.map(e => (
                        <button key={e.id} onClick={() => openEvidence(e.id)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 9px", background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 6, cursor: "pointer", textAlign: "left", transition: "border-color 120ms" }}
                          onMouseEnter={ev2 => ev2.currentTarget.style.borderColor = "var(--z-teal)"}
                          onMouseLeave={ev2 => ev2.currentTarget.style.borderColor = "var(--z-sep)"}>
                          <span className={`tier-chip tier-${e.tier}`}>{e.id}</span>
                          <span style={{ fontSize: 11, color: "var(--z-dark)", fontWeight: 500, flex: 1, minWidth: 0 }} className="txt-fit-1">{e.source_pretty}</span>
                          <Icon name="arrow-r" size={11} style={{ color: "var(--z-mid)" }} />
                        </button>
                      ))}
                    </div>
                  ) : <div style={{ fontSize: 11, color: "var(--z-muted)" }}>No evidence linked — inferred ceiling.</div>}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Share with other Babel scripts (see CLAUDE.md note on cross-file scope) */
Object.assign(window, {
  EvidenceTierCard, SentimentCard, FinancialTrajectoryCard,
  CoverageByPillarCard, CeilingEstimateCard,
});
