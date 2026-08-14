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
        <span className="b">Not promoted</span>
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

/* ── Multi-source sentiment scorecard ──────────────────────────────────
   SOURCE: 08_appendices/A6_sentiment_data.csv  (INTERNAL-only) */
function SentimentCard({ entity, audience }) {
  if (audience === "customer") return null;       // internal-only strip
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
        <div style={{ fontSize: 11, color: "var(--z-body)" }}>{r.source}<span style={{ color: "var(--z-muted)" }}> · {r.metric}</span></div>
        <div style={{ height: 7, background: "var(--z-sep)", borderRadius: 4, overflow: "hidden" }}>
          {pct == null ? null : <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", background: tone, borderRadius: 4, transition: "width var(--motion-slow) var(--ease)" }} />}
        </div>
        {/* A row can arrive with a source, a metric and no rating — the bar
            was found but the figure was not stated. The dash read the same as
            a zero-width bar and gave the reader no route to filling it. The
            payload carries no quarantine marker on these rows (adaptSentiment
            maps rating straight through), so this is a silent gap, never
            `held`. `compact` because the cell is 40px of a three-column grid
            and the badge would break the row. */}
        <div style={{ fontSize: 12, fontWeight: 600, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.score == null ? <EnrichmentGap what={r.metric ? `${r.source} · ${r.metric}` : r.source || "Rating"} audience={audience} compact /> : fx(r.score, 1)}</div>
      </div>
    );
  };
  return (
    <div className="card flush" data-source="A6_sentiment_data.csv :: employee[],customer[]">
      <div className="card-head">
        <div className="row"><Icon name="users" size={14} /><h3>Sentiment</h3>{s.b2b_b2c_gap ? <span className="b b-org">B2B/B2C gap</span> : null}</div>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{s.industry_avg == null ? "" : `Industry avg ${fx(s.industry_avg, 1)}`}</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 2 }}>Employee</div>
        {(s.employee || []).length ? s.employee.map((r, i) => <Row key={"e" + i} r={r} />)
          : <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Not established for this run.</div>}
        <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", margin: "10px 0 2px" }}>Customer</div>
        {(s.customer || []).length ? s.customer.map((r, i) => <Row key={"c" + i} r={r} />)
          : <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Not established for this run.</div>}
        {/* A section can promote rows AND declare what it could not establish —
            Baxter's does: ratings and scales on two audiences, and no citable
            review text behind them. "Not established for this run." beside an
            empty group is true and says nothing; the producer's own account of
            what was searched and what would close it is the answer, and it was
            sitting unread in the envelope. */}
        <SectionEmptyFoot section="overview.sentiment"
                          title="What this section could not establish" />
        {(s.ungrouped || []).length ? (
          <React.Fragment>
            <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", margin: "10px 0 2px" }}>Audience not stated</div>
            {s.ungrouped.map((r, i) => <Row key={"u" + i} r={r} />)}
          </React.Fragment>) : null}
        <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).sentiment} what="rows" />
      </div>
    </div>
  );
}

/* ── Financial trajectory ──────────────────────────────────────────────
   SOURCE: 00_entity_profile/financial_baseline.json + entity_profile.json */
function FinancialTrajectoryCard({ entity }) {
  const f = DMA.financialsFor(entity.id);
  if (!f || !(f.fy || []).length) return <CardAbsent icon="money"
    title="Financial trajectory"
    note="No financial series promoted for this run." section="overview.financial_series" />;
  const values = (f.total_assets || []).filter(v => v != null);
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
      <div className="card flush" data-source="financial_baseline.json :: total_assets[]">
        <div className="card-head">
          <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
          <span className="b b-org">Single point</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 26, fontWeight: 700, color: "var(--z-dark)" }}>
            {fmtAssets(f.total_assets[0], f.unit)}
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
            <span>{f.branches} branches · {f.employees[f.employees.length - 1].toLocaleString()} FTE</span>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="card flush" data-source="financial_baseline.json :: total_assets[],net_income_m[],nim_pct[]">
      <div className="card-head">
        <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{f.headline}</span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120 }}>
          {f.fy.map((y, i) => (
            <div key={y} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }} title={`${y} · $${f.total_assets[i]}${f.unit} · NIM ${f.nim_pct[i]}%`}>
              <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--z-dark)" }}>${f.total_assets[i]}{f.unit}</div>
              <div style={{ width: "100%", height: `${f.total_assets[i] / maxA * 80}px`, background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0", transition: "height var(--motion-slow) var(--ease)" }} />
              <div className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{y.replace("FY", "'")}</div>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
          <span className="chip">{f.regulator}</span>
          <span>{f.geography}</span>
          <span className="spacer" />
          <span>{f.branches} branches · {f.employees[f.employees.length - 1].toLocaleString()} FTE</span>
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
                <div style={{ position: "relative", height: 8, background: "var(--z-sep)", borderRadius: 4 }} title={`Band ${fx(lo, 1)}–${fx(hi, 1)}`}>
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
