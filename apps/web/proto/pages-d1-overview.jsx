/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · D1 Entity Intelligence Hub (refined)
   ═══════════════════════════════════════════════════════════════════════ */

function ClientOverview({ entity, run }) {
  const { audience, openEvidence, openInsight, openSubcap, role, setIpSurface, setIpContext, setIpOpen, tweaks, pushToast } = useApp();
  const [scqaExp, setScqaExp] = useState(false);
  const layout = tweaks.overview_layout || "balanced";

  useEffect(() => {
    setIpSurface("why_now");
    setIpContext({ entity });
  }, [entity?.id]);

  if (entity.in_progress) {
    return <InProgressBanner run={run} entity={entity} />;
  }

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 18 }}>
        <div>
          <div className="eyebrow">Entity intelligence</div>
          <h1 style={{ marginBottom: 4 }}>{entity.name}</h1>
          <div className="sub">{[
            DMA.SUBVERTICAL_LABEL[entity.subvertical],
            entity.hq,
            entity.assets != null ? `${fmtAssets(entity.assets, entity.assets_unit)} assets` : null,
            entity.assessment_date ? `Assessment ${fmtDate(entity.assessment_date)}` : null,
            entity.members != null ? `${entity.members.toLocaleString()} members` : null,
          ].filter(Boolean).join(" · ")}</div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Customer-safe scorecard generated · ${entity.name}`, "success")}><Icon name="download" size={13} /> Scorecard</button>
          <button className="btn btn-tertiary" onClick={() => pushToast("Rerun queued - first batch in ~3 min", "success")}><Icon name="refresh" size={13} /> Request rerun</button>
          <button className="btn btn-secondary" onClick={() => { setIpSurface("why_now"); setIpContext({ entity }); setIpOpen(true); }}><Icon name="sparkle" size={13} /> Meeting prep</button>
        </div>
      </div>

      {/* Snapshot strip - 3 columns: score ring + pillar bars + firmographics.
          Its own component, and its own boundary, because everything below is
          a separate read: a malformed pillar list must cost the strip and not
          the findings, the narrative or the leadership roster. */}
      <CardBoundary name="snapshot"><SnapshotStrip entity={entity} run={run} layout={layout} audience={audience} /></CardBoundary>

      {/* Why now */}
      <CardBoundary name="why-now signals">
        <WhyNowStrip entity={entity} openEvidence={openEvidence} audience={audience} openSubcap={openSubcap} />
      </CardBoundary>

      {/* SCQA */}
      <CardBoundary name="executive narrative">
        <SCQACard entity={entity} expanded={scqaExp} onToggle={() => setScqaExp(o => !o)} openEvidence={openEvidence} audience={audience} />
      </CardBoundary>

      {/* Opportunity Surface - per platform */}
      <CardBoundary name="opportunity surface">
        <OpportunitySurfaceStrip entity={entity} run={run} audience={audience} />
      </CardBoundary>

      {/* Two-column: Top findings + Leadership panel */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16, marginBottom: 18 }}>
        <CardBoundary name="top findings">
          <TopFindingsCard entity={entity} openEvidence={openEvidence} audience={audience} />
        </CardBoundary>
        <CardBoundary name="leadership panel">
          <LeadershipPanel audience={audience} />
        </CardBoundary>
      </div>

      {/* Evidence-driven analytics.
          Evidence coverage by pillar, the tier-mix card and the capability
          ceiling / uncertainty card are removed from D1 at the user's request
          (2026-08-05): they report on the ASSESSMENT's own workings rather than
          on the institution, and D7 Health is where that belongs. The sections
          still promote and still serve — nothing was deleted from the pipeline,
          only from this page. */}
      <div className="section-label" style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "4px 0 12px" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", textTransform: "uppercase", letterSpacing: ".06em" }}>Evidence &amp; benchmarks</span>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>extracted from scoring workbook · evidence index · peer set</span>
      </div>
      <div className="cards-grid-2" style={{ marginBottom: 18 }}>
        {/* D1's own trajectory card — the shared one's footer chip is wrong
            at this grain; see FinancialTrajectoryD1. */}
        <CardBoundary name="financial trajectory">
          <FinancialTrajectoryD1 entity={entity} audience={audience} />
        </CardBoundary>
        <CardBoundary name="sentiment">
          <SentimentCard entity={entity} audience={audience} />
        </CardBoundary>
      </div>

      {/* Thought leadership panel - internal-only */}
      {audience !== "customer"
        ? <CardBoundary name="thought leadership"><ThoughtLeadershipPanel /></CardBoundary>
        : null}

      {/* "How this assessment was evidenced" — DELETED 2026-08-19.
          The two sections here reported on the ASSESSMENT rather than on the
          institution: O10 evidence_coverage (33% overall, per-pillar shares,
          the 80% hard gate, "233 of 705 · 51 quote a source · 629 absences")
          and O11 ceilings (16 categories with M-level and uncertainty bands).
          They were restored to this page in an earlier round, and the third
          round of live screenshots is what they look like to a reader: our
          method, with its own percentages, sitting under the client's scores.

          Both are now on the API's NEVER_SERVED allowlist, so this block had
          nothing left to render anyway. It is deleted rather than left
          reading an empty payload, because a heading with no card under it
          is the "did this fail to load?" void this page keeps having to fill.
          Nothing was removed from the pipeline: both sections still promote,
          still validate, and are still readable through the connector. */}
    </div>
  );
}

/* The producer's reasoning trace, per section — DELETED 2026-08-19.

   `OvTrace` rendered the "REASONING TRACE · Self-check · ACCEPT · HIGH ·
   Show" strip under thirteen cards on this page. The third round of live
   screenshots caught three of them on one screen, above the firmographics
   table, below it, and again under the why-now signals.

   The trace is the record of the producer arguing against its own answer.
   That is something we owe the assessment; it is not something we owe the
   reader, and a client meeting "Self-check · ACCEPT" under their own scores
   is reading our working rather than their assessment.

   `r_layer` is now on the API's NEVER_SERVED_KEYS allowlist, stripped at any
   depth for every audience, so this component had nothing left to read. The
   component is deleted rather than left returning null, because a renderer
   that cannot render is indistinguishable from one that is merely quiet, and
   the next reader of this file would have to prove which. It still promotes,
   still validates, and is still readable through the connector. */

/* ── O1 · the four pillar bars ────────────────────────────────────────
   A bar with no figure must not look like a bar with a figure of zero, and
   the reason it carries none must be on the page beside it.

   What this run rendered before: four `.pbar-track` elements at their grey
   background with a zero-width fill, an empty 32px score column, an empty
   50px delta column, and a legend promising a peer median beside a tick that
   is never drawn. Nothing said the pillar grain does not resolve on this run
   — although the payload says exactly that, at length, on all four rows
   (`proxy_disclosure`, ~900 characters, promoted and served).

   So: a served figure renders as a bar; an unserved one renders as the
   sentence saying so, in the slot the bar would have occupied; the promoted
   explanation renders once beneath the rows (identical on all four here, and
   printing one paragraph four times is noise, not disclosure); and the legend
   names only the marks that are actually drawn. The moment a pillar figure or
   a peer median IS served, the same code draws it — this is one renderer
   handling both states, not a special case for an empty run. */
function OvPillarBars({ entity, run, audience }) {
  const sec = DMA.scoresFor ? DMA.scoresFor(entity.id) : null;
  const rows = {};
  for (const r of (sec && sec.pillars) || []) {
    if (r && r.pillar_id) rows[r.pillar_id] = r;
  }
  const scores = entity.pillar_scores || {};
  const peers = entity.pillar_peer_medians || {};
  const num = (v) => (v === null || v === undefined || v === "" || !isFinite(Number(v)))
    ? null : Number(v);

  const anyScore = DMA.PILLARS.some(p => num(scores[p.id]) != null);
  const anyPeer = DMA.PILLARS.some(p => num(peers[p.id]) != null);
  const anyBlank = DMA.PILLARS.some(p => num(scores[p.id]) == null || num(peers[p.id]) == null);

  /* The promoted explanation, de-duplicated. The producer writes it per row
     because a future run may have a different reason per pillar; on this one
     all four are the same paragraph. */
  /* `why` (the four proxy disclosures) and `bases` ("computed_mean_of_subcaps")
     were read here and are deleted with the block that printed them. */
  /* The basis a served figure was computed on, where the run states one.
     Rendered as the row's own tooltip and, when every row agrees, once under
     the bars — a mean nobody can resolve to a basis is the thing the maturity
     grid exists to avoid publishing. */
  const basisOf = (row) => asText(row.basis || row.score_basis) || null;
  const nOf = (row) => num(row.n != null ? row.n : row.n_cells);


  return (
    <div>
      {DMA.PILLARS.map(p => {
        const row = rows[p.id] || {};
        const s = num(scores[p.id]);
        const peer = num(peers[p.id]);
        const peerL = peer == null ? null : (peer / 5) * 100;
        // Both ends or no delta: `null - peer` is -peer, which rendered an
        // unscored pillar as ▼peer — a movement nobody measured.
        const delta = (peer == null || s == null) ? null : s - peer;
        const basis = basisOf(row), n = nOf(row);
        /* The row tooltip carried the 900-character proxy disclosure on an
           unscored pillar. A tooltip is not where a paragraph goes, and this
           one carried "serve grain" and "computed_mean_of_subcaps" into a
           hover a client can trigger by accident. */
        const rowTitle = s != null
          ? [`${p.id} ${fx(s, 1)} / 5`, n != null ? `n=${n}` : null]
              .filter(Boolean).join(" · ")
          : undefined;
        return (
          <div className="pbar" key={p.id} title={rowTitle}
               onClick={() => navigate(`/clients/${entity.id}/heatmap`, { pillar: p.id, run: run.id })}
               style={{ cursor: "pointer" }}>
            <div className="pbar-name">{p.id} · {p.short}</div>
            {(s != null || peer != null) ? (
              <div className="pbar-track">
                {s == null ? null : (
                  <div className="pbar-fill"
                       style={{ width: `${(s / 5) * 100}%`, background: DMA.helpers.maturityHex(s) }} />
                )}
                {peerL == null ? null : (
                  <div className="pbar-peer" style={{ left: `calc(${peerL}% - 1px)` }} title={`Peer ${fx(peer, 1)}`} />
                )}
              </div>
            ) : (
              /* No track at all. An 8px grey rail with nothing in it is read
                 as a score of zero by every reader who does not know the
                 payload, and this run scores none of these pillars — it does
                 not score them at nought. */
              <div style={{ flex: 1, fontSize: 11, color: "var(--z-muted)",
                            lineHeight: 1.4 }} data-no-figure={p.id}>
                No pillar figure is served on this run
              </div>
            )}
            <div className="pbar-score">{s == null ? null : fx(s, 1)}</div>
            <div className="pbar-delta" style={{ color: delta == null ? "var(--z-muted)" : (delta < 0 ? "var(--z-below)" : "var(--z-mid)") }}>
              {delta == null ? null : <>{delta >= 0 ? "▲" : "▼"} {fx(Math.abs(delta), 1)}</>}
            </div>
          </div>
        );
      })}
      {/* The legend names the marks that are DRAWN. It used to promise a peer
          median on every run, including the ones where no tick is ever
          rendered — a legend entry for a mark that does not exist is a
          promise, and the reader spends the next minute looking for it. */}
      {anyScore || anyPeer ? (
        <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)", display: "flex", gap: 14, paddingLeft: 122 }}>
          {anyScore ? (
            <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 12, height: 4, background: "var(--z-teal)", borderRadius: 2 }} /> Entity</span>
          ) : null}
          {anyPeer ? (
            <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 2, height: 10, background: "var(--z-dpur)" }} /> Peer median</span>
          ) : null}
        </div>
      ) : null}
      {/* "Basis · computed_mean_of_subcaps" and the four proxy disclosures —
          DELETED 2026-08-19.

          Both were mine, from the round that made this card explain its own
          blank rails, and the live screenshots show what they became. The
          basis line printed a column name at the reader. The disclosures
          printed FOUR near-identical 900-character paragraphs, one per
          pillar, each opening "This run's workbook states no pillar rollup,
          so this figure is derived at serve grain: the mean of the 187
          evidence-scored subcapability cells...". They were meant to
          de-duplicate; they differ only in the cell count, so the
          `why.includes(t)` guard never matched and all four printed.

          That is three defects in one block: our internal vocabulary
          (serve grain, computed_mean_of_subcaps), the same explanation
          repeated, and a de-duplication that could not work. The short
          version a reader actually needs — that no peer figure is served —
          is said once by `OvPillarBars` itself, below. */}
      {anyBlank && !anyPeer ? (
        <div style={{ marginTop: 8, paddingLeft: 122, fontSize: 10.5,
                      color: "var(--z-muted)", lineHeight: 1.5 }}>
          No peer benchmark is published for this run, so no comparison is drawn.
        </div>
      ) : null}
    </div>
  );
}

/* ── O1 · snapshot strip ──────────────────────────────────────────── */
function SnapshotStrip({ entity, run, layout, audience }) {
  return (
      <div className="card" style={{ marginBottom: 18, padding: "20px 22px" }}>
        <div style={{ display: "grid", gridTemplateColumns: layout === "ring-left" ? "140px 1fr 280px" : "1fr 280px", gap: 28, alignItems: "stretch" }}>
          {layout === "ring-left" ? <ScoreRing score={entity.overall} /> : null}
          <div style={{ minWidth: 0 }}>
            {layout !== "ring-left" ? (
              <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
                <ScoreRing score={entity.overall} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
                    {DMA.helpers.maturityLabel(entity.overall) ? (
                      <span className={`b ${DMA.helpers.maturityClass(entity.overall)}`}>{DMA.helpers.maturityLabel(entity.overall).toUpperCase()}</span>
                    ) : null}
                    <span className="b b-ph1">EVIDENCE · {run.evidence_mode}</span>
                    <FreshnessDot date={entity.assessment_date} withLabel />
                    {entity.data_source === "DRIVE_PARSE" ? <span className="b b-ph0">DRIVE PARSE</span> : null}
                  </div>
                  {/* The run's own framing sentence. This was arithmetic on the
                      fabricated 0.3 offset plus a hardcoded "Gap concentrated in
                      P4 Data foundation" — true of the fixture, asserted of
                      everyone. */}
                  <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5 }}>
                    {/* The composite sentence is itself a fallback, so with no
                        framing AND no composite there is nothing honest left
                        to say here but the gap. */}
                    {asText(entity.framing) || asText(entity.posture_basis) ||
                     (entity.overall != null
                       ? `Composite ${fx(entity.overall, 1)} / 5 across ${DMA.PILLARS.length} pillars.`
                       : <EnrichmentGap what="Run framing" audience={audience} />)}
                  </div>
                </div>
              </div>
            ) : null}
            <OvPillarBars entity={entity} run={run} audience={audience} />
          </div>
          <FirmographicsPanel entity={entity} audience={audience} />
        </div>
      </div>
  );
}

/* ── Firmographics · the promoted figures, and only those ─────────── */
function FirmographicsPanel({ entity, audience }) {
  /* One absent-state builder for every pinned row, so the three states a
     firmographic can be in stay distinguishable wherever they occur:

       stated   the value renders
       HELD     quarantined with the ladder that failed — a finding, and the
                reason is the content
       silent   nobody established it; it is in the connector's worklist

     Held is read from `entity.held[slot]`, which app-root's firmoFields sets
     for a pinned field. Before that existed, a held pinned field rendered no
     row at all and was indistinguishable from one never asked for — which is
     the exact confusion this whole component was rebuilt to end. */
  /* One row builder. A row whose value cannot be established is NOT
     rendered — owner adjudication 2026-08-14, replacing the three-state gap
     vocabulary ("Not stated · queued for enrichment", "Held · reason") with
     silence on the page.

     The reason that is safe now and was not before: the omission is no longer
     invisible to the SYSTEM. `list_enrichment_gaps(run_id)` computes the same
     empty set from the staged payload, and audit_promoted_client.py fails on
     it — so a field the reader never sees is still on the producer's worklist
     and still blocks a clean audit. Hiding it from the page hid it from
     everyone only while nothing else counted.

     `held` is likewise not surfaced: a quarantine reason is internal
     provenance, and the row it belonged to now simply does not appear. */
  const rows = [];
  const row = (k, v) => { if (v !== null && v !== undefined && v !== "") rows.push([k, v]); };

  row(entity.assets_label || "Assets", fmtAssets(entity.assets, entity.assets_unit));
  row("Employees", entity.employees != null ? entity.employees.toLocaleString() : null);
  row("Branches", entity.branches != null ? String(entity.branches) : null);
  row("Members", entity.members != null ? entity.members.toLocaleString() : null);
  row("Customers", entity.customers != null ? entity.customers.toLocaleString() : null);
  /* ONE CAGR row. It rendered twice until 2026-08-14: pinned here from the
     series the adapter computes, and printed again by the passthrough below
     because `cagr` was missing from the pinned KEY set. Computed wins — a
     growth rate is derived and the promoted series is its source of truth —
     and a run that stated its own falls back in with its own basis. */
  row("CAGR", entity.cagr != null
    ? `${fmtPct(entity.cagr)}${entity.cagr_basis ? ` · ${entity.cagr_basis}` : ""}`
    : entity.stated_cagr != null
      ? `${fx(entity.stated_cagr, 1)}%${entity.stated_cagr_basis ? ` · ${entity.stated_cagr_basis}` : ""}`
      : null);
  row("Net worth ratio", entity.net_worth_ratio != null
    ? `${fx(entity.net_worth_ratio, 2)}%` : null);
  row("Regulator", entity.regulator || null);
  // Linked because a domain a reader cannot open is half a fact.
  row("Website", entity.website
    ? <a href={/^https?:/i.test(entity.website) ? entity.website : `https://${entity.website}`}
         target="_blank" rel="noopener noreferrer">{entity.website}</a>
    : null);
  row("HQ", entity.hq || null);
  // Footprint reads the regulatory section's jurisdictions first, then a
  // footprint the firmographics stated — both consumed by this one row.
  row("Footprint", entity.footprint?.length ? entity.footprint.join(" · ")
    : entity.stated_footprint ? String(entity.stated_footprint) : null);
  row("Charter", entity.charter || null);
  row("Founded", entity.founded ? String(entity.founded).slice(0, 4) : null);

  return (
    <div style={{ background: "var(--z-lav)", borderRadius: 12, padding: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>Firmographics</div>
      {/* A `fields` that did not arrive as a list is not an unstated figure —
          it is a section this page cannot read. Named here rather than passed
          off as absence (app-root's firmoFields sets the flag). */}
      {entity.firmographics_unreadable ? (
        <div style={{ fontSize: 11, color: "var(--z-org)", lineHeight: 1.5, marginBottom: 8 }}>
          The firmographics section did not arrive as a list of fields, so no
          figure below is read from it.
        </div>
      ) : null}
      {rows.map(([k, v], i) => <Row key={`f${i}`} k={k} v={v} />)}
      {/* A HELD field renders NO ROW. Owner rule, 2026-08-19: "when there is
          no revenue figure, remove the Revenue row entirely. Do not show the
          explanation."

          What this printed instead, measured from the live app: a Revenue
          label with, in its value column, "A credit union returns its surplus
          to members rather than reporting commercial revenue, so no..." — a
          sentence set in italic, overflowing its column, between Loans and
          Leases and ROA. The explanation is true and it is ours; the reader
          asked for a number.

          The row is still on the wire and still quarantined with its reason,
          because CG-18 is right that a must-present member may be stated or
          held but never simply deleted. This is the render deciding not to
          draw it, which is the correct place for that decision. */}
      {(entity.extra_fields || [])
        .filter(f => !f.held && f.value !== null && f.value !== undefined && f.value !== "")
        .map((f, i) => (
          <Row key={`x${i}`} k={humaniseFieldName(f.field)}
               v={`${f.value}${f.unit ? ` ${f.unit}` : ""}`} />
        ))}
      <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).firmographics}
                      what="firmographics" audience={audience} />
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
        <div className="num" style={{ color: DMA.helpers.maturityHex(score), fontSize: size * 0.32, fontWeight: 300, lineHeight: 1 }}>{fx(score, 1)}</div>
      </div>
    </div>
  );
}

/* ── Why-now strip · card row + full-width drilldown, per-client ────
   Sources DMA.whyNowFor(entity.id): hand-authored for the flagship,
   synthesized from each client's own scoring/evidence otherwise.
   The face is one horizontal row of compact cards — kind chip over the
   trigger sentence — because four stacked full-width rows pushed the rest
   of the page below the fold and read as four cards instead of one strip.
   The drilldown carries everything the stacked rows did (detail · metric ·
   dated event · window · the play · peer context · risk-if-ignored · cost
   of acting · bears-on cells · tier-coded evidence · claim + confidence),
   but it opens BELOW the strip at full width: the detail is prose, and
   expanding it inside a 200px column crushed every sentence. The window
   moves into the drilldown as a labelled row for the same reason it once
   broke the stacked header — it is a 20-40-word clause naming the closing
   event, not a chip-sized phrase. One signal open at a time; none open by
   default — the strip is the summary, the reader chooses the drilldown.
   Customer view keeps positive framing and strips internal rationale. */
function WhyNowStrip({ entity, openEvidence, audience, openSubcap }) {
  const [open, setOpen] = useState(null); // no drilldown until a card is chosen
  const signals = DMA.whyNowFor(entity.id) || [];
  const isCust = audience === "customer";
  const STR = { STRONG: "b-teal", LEADING: "b-purple", SUPPORTING: "b-muted" };
  const CLAIM = { FACT: "b-teal", INFERENCE: "b-purple", HYPOTHESIS: "b-org" };
  // The chip is the signal's `kind`, compressed to one word. The contract's
  // vocabulary is already chip-sized (LEADERSHIP · REGULATORY · TECHNOLOGY);
  // the exceptions map to the word a reader would say, and anything else —
  // fixture categories, future kinds — falls back to the kind text itself,
  // uppercased. Never invented: no kind, no guess, just SIGNAL.
  const CHIP_WORD = { "M&A": "MERGER", "CORE_MIGRATION": "MIGRATION" };
  const chipOf = (kind) => {
    if (!kind) return "SIGNAL";
    const k = String(kind).toUpperCase();
    return CHIP_WORD[k] || k.replace(/_/g, " ");
  };
  const kindChip = (kind) => (
    <span className="f-mono" style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em",
                                      textTransform: "uppercase", color: "var(--z-dpur)",
                                      background: "rgba(115,91,161,.14)", borderRadius: 4,
                                      padding: "2px 7px", flexShrink: 0 }}>
      {chipOf(kind)}
    </span>
  );
  const sel = open != null ? signals[open] : null;
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--ph0-lt)", color: "var(--ph0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="sparkle" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>Why now signals</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{signals.length} trigger{signals.length === 1 ? "" : "s"} · click any signal to drill into the evidence</div>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/context`)}>View timeline <Icon name="arrow-r" size={11} /></button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
        {signals.map((s, i) => {
          const openNow = open === i;
          return (
            <button key={s.id || i} onClick={() => setOpen(o => o === i ? null : i)}
              style={{ textAlign: "left", cursor: "pointer", background: "var(--z-lav)",
                       border: `1px solid ${openNow ? "var(--ph0-bd)" : "var(--z-sep)"}`,
                       borderRadius: 10, padding: "11px 13px", display: "flex",
                       flexDirection: "column", alignItems: "flex-start", gap: 8,
                       transition: "border-color 140ms var(--ease)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                {kindChip(s.category)}
                {!isCust && s.strength ? <span className={`b ${STR[s.strength] || "b-muted"}`}>{s.strength}</span> : null}
              </span>
              {/* The whole trigger sentence, unclamped. A four-line clamp cut
                  every card mid-clause ("BCU announced a leadership evolution
                  on 1 July 2026: Jim Block steps…"), which is the one thing a
                  card face must not do: an argument you have to click to
                  finish reading is not a summary. The cards are a grid row, so
                  they size to the tallest and stay level. */}
              <span style={{ fontSize: 12, fontWeight: 500, color: "var(--z-dark)", lineHeight: 1.45 }}
                    title={s.detail || s.label}>
                {s.label}
              </span>
            </button>
          );
        })}
      </div>
      {/* full-width drilldown for the selected signal. Its header collapses
          it, same as re-clicking the card — two ways out, no dead end. */}
      {sel ? (
        <div style={{ marginTop: 12, border: "1px solid var(--ph0-bd)", borderRadius: 10, background: "var(--ph0-lt)", overflow: "hidden" }}>
          <button onClick={() => setOpen(null)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "12px 14px", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
            {kindChip(sel.category)}
            <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "var(--z-dark)", minWidth: 0 }}>{sel.label}</span>
            <Icon name="chevron-u" size={15} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
          </button>
          <div style={{ padding: "0 14px 14px" }}>
            {(isCust ? sel.impact : sel.detail) ? (
              <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 10 }}>{isCust ? sel.impact : sel.detail}</div>
            ) : null}
            {!isCust && sel.metric ? <div className="f-mono" style={{ fontSize: 11.5, color: "var(--z-dark)", background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 6, padding: "7px 10px", marginBottom: 10, display: "inline-block" }}>{sel.metric}</div> : null}
            {/* timeline event → context */}
            {sel.timeline ? (
              <button onClick={() => navigate(`/clients/${entity.id}/context`)} style={{ display: "flex", alignItems: "center", gap: 7, background: "none", border: 0, padding: 0, cursor: "pointer", marginBottom: 12 }}>
                <Icon name="timeline" size={12} style={{ color: "var(--ph0)" }} />
                <span className="f-mono" style={{ fontSize: 11, color: "var(--z-mid)" }}>{sel.timeline.date}</span>
                <span style={{ fontSize: 11.5, color: "var(--z-body)" }}>{sel.timeline.event}</span>
                <Icon name="arrow-r" size={10} style={{ color: "var(--z-muted)" }} />
              </button>
            ) : null}
            {/* the window — the clause naming what closes it, at full width */}
            {sel.window ? (
              <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5, margin: "0 0 10px" }}>
                <strong style={{ color: "var(--z-dpur)" }}>Window · </strong>{sel.window}
              </div>
            ) : null}
            {/* the play */}
            {sel.play ? (
              <div style={{ background: "rgba(39,187,175,.1)", borderLeft: "3px solid var(--z-teal)", borderRadius: "0 6px 6px 0", padding: "8px 12px", marginBottom: 8 }}>
                <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-teal)", textTransform: "uppercase", marginBottom: 2 }}>The play</div>
                <div style={{ fontSize: 12, color: "var(--z-dark)", lineHeight: 1.55, fontWeight: 500 }}>{sel.play}</div>
              </div>
            ) : null}
            {/* peer context + risk — internal only */}
            {!isCust && sel.peer_context ? <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5, margin: "6px 0" }}><strong style={{ color: "var(--z-body)" }}>Peer context · </strong>{sel.peer_context}</div> : null}
            {!isCust && sel.risk ? (
              <div style={{ background: "rgba(214,109,42,.08)", borderLeft: "3px solid var(--z-org)", borderRadius: "0 6px 6px 0", padding: "8px 12px", marginBottom: 10 }}>
                <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-org)", textTransform: "uppercase", marginBottom: 2 }}>If ignored</div>
                <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>{sel.risk}</div>
              </div>
            ) : null}
            {/* The other side of the argument. `cost_of_acting_now` is a
                REQUIRED contract field — the honest cost of moving, about
                fifty words per signal — and a why-now that states only the
                upside is the shallow reading. */}
            {sel.cost_now ? (
              <div style={{ background: "var(--z-lav)", borderLeft: "3px solid var(--z-dpur)", borderRadius: "0 6px 6px 0", padding: "8px 12px", marginBottom: 10 }}>
                <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 2 }}>Cost of acting now</div>
                <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>{sel.cost_now}</div>
              </div>
            ) : null}
            {/* The cells this trigger bears on — the link back to the DMA. */}
            {(sel.subcaps || []).length ? (
              <div className="row" style={{ gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
                <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Bears on</span>
                {sel.subcaps.map(cid => (
                  <button key={cid} className="chip purple" style={{ cursor: "pointer", border: 0 }}
                          onClick={() => openSubcap && openSubcap(cid)}>{cid}</button>
                ))}
              </div>
            ) : null}
            {/* footer: evidence + confidence/claim */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
              {sel.evidence && sel.evidence.length ? (
                <>
                  <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Evidence</span>
                  {sel.evidence.map(eid => {
                    const e = DMA.getEvidence(eid);
                    return <button key={eid} className={`tier-chip tier-${e ? e.tier : "T3"}`} style={{ cursor: "pointer", border: 0 }} title={e ? e.title : eid} onClick={() => openEvidence(eid)}>{eid}</button>;
                  })}
                </>
              ) : <span style={{ fontSize: 11, color: "var(--z-muted)", fontStyle: "italic" }}>No direct evidence yet — confirm in first meeting</span>}
              <span style={{ flex: 1 }} />
              {!isCust && sel.claim ? <span className={`b ${CLAIM[sel.claim] || "b-muted"}`}>{sel.claim}</span> : null}
              {!isCust && sel.confidence ? <span className="b b-muted">{sel.confidence} confidence</span> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ── SCQA card ──────────────────────────────────────────────────── */
function SCQACard({ entity, expanded, onToggle, openEvidence, audience }) {
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
      <SCQABody entity={entity} expanded={expanded} openEvidence={openEvidence} audience={audience} />
    </div>
  );
}

/* ── The storyline challenge, excluded ────────────────────────────────
   Owner instruction, 2026-08-19, with a screenshot of the internal view:
   "This should be excluded please." The volleys are the producer's
   stress-test of its own story — five objections and what the story did
   with each — and they are owed to the assessment, not to any reader.
   `storyline_challenge` stays in the payload (the contract is law and the
   producer still writes it); the server already strips it for the customer
   audience; no renderer exists for it on any audience, and
   overview-render.test.js asserts the absence with the field present in
   its fixture. */

/* The promoted SCQA, and nothing else. The contract's fields are the card. */
const SCQA_PARTS = [
  ["situation", "Situation"],
  ["complication", "Complication"],
  ["question", "Question"],
  ["answer", "Answer"],
  ["sequencing_rationale", "Why this order"],
  ["cost_of_delay", "Cost of delay"],
];

function SCQABody({ entity, expanded, openEvidence, audience }) {
  const s = DMA.execSummaryFor(entity.id);
  const parts = SCQA_PARTS.filter(([k]) => s && asText(s[k]));
  if (!parts.length) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--z-muted)" }}>
        No executive narrative promoted for this run.
      </div>
    );
  }
  // Collapsed shows the situation and the complication — the constraint is the
  // point of the card; expanded shows all six with their headings.
  const shown = expanded ? parts : parts.slice(0, 2);
  const eIds = Array.isArray(s.e_ids) ? s.e_ids : [];
  return (
    <div style={{ fontSize: 14, color: "var(--z-dark)", lineHeight: 1.7, maxWidth: 880 }}>
      {shown.map(([key, heading]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          {expanded ? (
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".06em",
                          color: "var(--z-mid)", textTransform: "uppercase",
                          marginBottom: 3 }}>{heading}</div>
          ) : null}
          <div>{asText(s[key])}</div>
        </div>
      ))}
      {expanded && eIds.length ? (
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 4 }}>
          <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>EVIDENCE</span>
          {eIds.map(eid => (
            <button key={eid} className="chip" style={{ cursor: "pointer", border: 0 }}
              onClick={() => openEvidence(eid)}>{eid}</button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ── Opportunity Surface · per platform ───────────────────────────────
   O8. Two defects, one component.

   THE SCORE COLUMN. The tile was a flex row with a shrinkable right-hand
   block and no `white-space` rule on the number inside it, so on a five-column
   grid the column collapsed to about 22px and Chromium wrapped the score one
   character per line: `55.5` rendered as `5`/`5.`/`5` in a 72px-tall stack,
   and the label under it as `fit`/`sco`/`re`. Three of the five tiles. The
   fix is the score column refusing to shrink and refusing to wrap, and the
   platform NAME taking the give instead — a name is prose and wraps well, a
   number is not and does not. The figure also goes through `fx(v, 1)`, the
   same formatter D4 uses, because the same composite printed `66.75` here and
   `66.8` there.

   THE TILE BODY. Everything the producer wrote ABOUT the ranking — the cells
   each platform addresses and the feature that addresses each one, the three
   weighted factors and their contributions, the stack context, the rank
   rationale, and the platforms considered and set aside with the reason —
   was promoted on all five tiles, in both audiences, and rendered nowhere. A
   fit score with no working shown is a number a reader has to take on trust;
   it is also the first thing a client asks about. The working opens under the
   strip rather than inside a 200px column, for the same reason the why-now
   drilldown does: the content is prose.

   Navigation is untouched — the tile still opens the platform page — so the
   working is reached from a separate control on the tile rather than by
   replacing the click that was already there. */
function OpportunitySurfaceStrip({ entity, run, audience }) {
  const [open, setOpen] = useState(null);
  const sec = DMA.opportunityFor ? DMA.opportunityFor(entity.id) : null;
  const num = (v) => (v === null || v === undefined || v === "" || !isFinite(Number(v)))
    ? null : Number(v);
  /* The promoted tiles carry the platform's own name, so the static vendor
     catalogue is consulted only for a fixture-mode key. Falls back to the
     score-only `oss` map when no section arrived. */
  const promoted = ((sec && sec.tiles) || [])
    .filter(t => t && t.platform)
    .map(t => ({ ...t, composite: num(t.composite) }));
  const tiles = promoted.length
    ? promoted.slice().sort((a, b) => {
        const ra = num(a.rank), rb = num(b.rank);
        if (ra != null && rb != null && ra !== rb) return ra - rb;
        return (b.composite || 0) - (a.composite || 0);
      })
    : Object.entries(entity.oss || {}).sort((a, b) => b[1] - a[1])
        .map(([pid, score]) => ({ platform: pid, composite: num(score) }));
  /* `discarded` was read here for the "Considered and set aside" block that
     now lives on the Platform page. The section still promotes it; this page
     no longer renders it. */
  /* The strip is the TILES now. `discarded` moved to the Platform page, so a
     run with no tiles and only discards has nothing to draw here. */
  if (!tiles.length) return null;
  const sel = open != null ? tiles[open] : null;

  const factorRows = (t) => (t.factors || []).filter(f => f && f.name).map(f => ({
    name: asText(f.name), value: num(f.value), weight: num(f.weight),
    contribution: num(f.contribution),
  }));

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="platform" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Opportunity Surface · per platform</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Composite fit score 0–100</div>
        </div>
        <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/platform`, { run: run.id })}>Open matrix <Icon name="arrow-r" size={11} /></button>
      </div>
      <div className="g5">
        {tiles.map((t, i) => {
          const pid = t.platform;
          const cat = DMA.getPlatform(pid);
          const name = (cat && cat.name) || pid;
          const score = t.composite;
          const cells = (t.addressable_cells || []).filter(c => c && c.subcap_id);
          const sub = asText(t.headline)
            || ((cat && cat.features) ? cat.features.split(" · ").slice(0, 2).join(" · ") : null);
          return (
            <div key={pid} className="card-tile clickable" onClick={() => navigate(`/clients/${entity.id}/platform`, { platform: pid, run: run.id })}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", lineHeight: 1.3 }}>{name}</div>
                  {sub ? <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.4 }}>{sub}</div> : null}
                </div>
                {/* The whole point of this block: it does not shrink and its
                    contents do not wrap. */}
                <div style={{ textAlign: "right", flexShrink: 0, minWidth: 46 }}>
                  <div style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1, whiteSpace: "nowrap" }}>
                    {score == null ? null : fx(score, 1)}
                  </div>
                  <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)", whiteSpace: "nowrap" }}>fit score</div>
                </div>
              </div>
              <div className="prog" style={{ height: 5 }}>
                <div className="prog-fill" style={{ width: `${score == null ? 0 : score}%`, background: (score || 0) >= 60 ? "var(--z-teal)" : (score || 0) >= 35 ? "var(--m-bld)" : "var(--m-act)" }} />
              </div>
              {(cells.length || t.rank != null || factorRows(t).length) ? (
                <button onClick={(e) => { e.stopPropagation(); setOpen(o => o === i ? null : i); }}
                        style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 5,
                                 background: "none", border: 0, padding: 0, cursor: "pointer",
                                 fontSize: 10.5, color: "var(--z-mid)", whiteSpace: "nowrap" }}>
                  {/* No rank stamp here (owner, 2026-08-20: "remove the
                      #number, just have the writing after"): the tiles are
                      already in rank order and the expansion opens with
                      "Why it ranks here". */}
                  {/* The count is on the tile FACE and the list is one click
                      below it, so a reader who only scans the strip still
                      learns how much of their assessment each platform
                      touches. */}
                  <span>{cells.length ? `Cells it addresses · ${cells.length}` : "Why this ranks"}</span>
                  <Icon name={open === i ? "chevron-u" : "chevron-d"} size={11} />
                </button>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* The working, at full width. */}
      {sel ? (
        <div style={{ marginTop: 12, border: "1px solid var(--z-sep)", borderRadius: 10, background: "var(--z-bg)", overflow: "hidden" }}>
          <button onClick={() => setOpen(null)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "12px 14px", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
            <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "var(--z-dark)", minWidth: 0 }}>
              {(DMA.getPlatform(sel.platform) || {}).name || sel.platform}
              {sel.composite == null ? null : <span style={{ color: "var(--z-muted)", fontWeight: 400 }}> · {fx(sel.composite, 1)} / 100</span>}
            </span>
            <Icon name="chevron-u" size={15} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
          </button>
          <div style={{ padding: "0 14px 14px" }}>
            {asText(sel.rank_rationale) ? (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--z-muted)", marginBottom: 3 }}>Why it ranks here</div>
                <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>{asText(sel.rank_rationale)}</div>
              </div>
            ) : null}
            {asText(sel.their_stack_context) ? (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--z-muted)", marginBottom: 3 }}>Against their stack</div>
                <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>{asText(sel.their_stack_context)}</div>
              </div>
            ) : null}
            {factorRows(sel).length ? (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--z-muted)", marginBottom: 4 }}>How the score is made</div>
                {((fs) => fs.map((f, i) => {
                  /* The bar is the factor's SHARE OF THE COMPOSITE, which is
                     what "how the score is made" means. Drawn as `value * 10`
                     it ranked the factors in the wrong order: a gap-depth
                     count of 11 drew a full bar while the relevance fraction
                     of 0.85 — the larger contribution — drew a sliver. The
                     three factors here are a count and two fractions; only
                     their contributions are on one scale. */
                  const total = fs.reduce((a, x) => a + (x.contribution || 0), 0);
                  const share = (f.contribution != null && total > 0) ? (f.contribution / total) * 100 : null;
                  /* Owner, 2026-08-20, from a screenshot of this block: the
                     `value×weight` working rendered beside the contribution
                     ("+0.5 · 0.9389×0.52") overran its 96px column across the
                     bars, and it is arithmetic the reader never asked to
                     check — "the platform page just gives the scores; I can
                     add up the block figures." The platform page's factor
                     rows are the pattern this block must match: contribution
                     in points of 100, weight on hover, no products. */
                  return (
                    <div key={i} style={{ display: "grid", gridTemplateColumns: "180px 1fr 56px", gap: 8, alignItems: "center", padding: "3px 0" }}>
                      <div style={{ fontSize: 11, color: "var(--z-body)" }}
                        title={f.weight != null ? `weight ${f.weight}` : ""}>{f.name}</div>
                      <div style={{ height: 6, background: "var(--z-sep)", borderRadius: 3, overflow: "hidden" }}>
                        {share == null ? null : <div style={{ width: `${share}%`, height: "100%", background: "var(--z-mid)", borderRadius: 3 }} />}
                      </div>
                      <div className="f-mono" style={{ fontSize: 10.5, color: "var(--z-muted)", textAlign: "right", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                        title="contribution to the fit subtotal, in points of 100">
                        {f.contribution == null ? null : `+${(Number(f.contribution) * 100).toFixed(1)}`}
                      </div>
                    </div>
                  );
                }))(factorRows(sel))}
              </div>
            ) : null}
            {(sel.addressable_cells || []).filter(c => c && c.subcap_id).length ? (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--z-muted)", marginBottom: 4 }}>Cells it addresses</div>
                {(sel.addressable_cells || []).filter(c => c && c.subcap_id).map(c => (
                  <div key={c.subcap_id} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "5px 0", borderTop: "1px solid var(--z-sep)" }}>
                    <span className="chip purple" style={{ flexShrink: 0 }}>{c.subcap_id}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11.5, color: "var(--z-dark)", fontWeight: 500 }}>{asText(c.name) || c.subcap_id}</div>
                      {asText(c.feature_that_addresses_it) ? (
                        <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.45 }}>{asText(c.feature_that_addresses_it)}</div>
                      ) : null}
                    </div>
                    <div className="f-mono" style={{ fontSize: 10.5, color: "var(--z-muted)", textAlign: "right", flexShrink: 0, whiteSpace: "nowrap" }}>
                      {num(c.current) == null ? null : `now ${fx(num(c.current), 1)}`}
                      {num(c.gap) == null ? null : ` · gap ${fx(num(c.gap), 1)}`}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* "Considered and set aside" — MOVED TO THE PLATFORM PAGE, 2026-08-19.

          Seven platforms, each with the reason it is not ranked, rendered
          here under the opportunity strip on the OVERVIEW. The owner's third
          round marks it as wrong-page content: it is a platform argument and
          it belongs beside the platforms.

          It was also being told twice. `platform.platform_story.discarded`
          carries the same seven with its own wording, and rendered inside a
          drawer on the page where the list belongs — so the copy a reader
          met first was the one on the wrong page, and the one on the right
          page was behind a click. The Platform page now shows its own list
          openly; this one is gone rather than duplicated. */}
    </div>
  );
}

/* ── Top findings ─────────────────────────────────────────────────
   The card reads and maps its OWN section. It used to be handed a mapped
   array built in ClientOverview's body, which put the read above every
   boundary: one finding that arrived as null took `f.f_id` with it and the
   whole application unmounted, on a page where four other cards had nothing
   wrong with them. A card owns its read, so a card owns its failure. */
function TopFindingsCard({ entity, openEvidence, audience }) {
  const [openFinding, setOpenFinding] = useState(null);
  // The promoted findings, mapped onto the card's shape. This was a hardcoded
  // five-item array of fictional prose — "three production cores", a CTO
  // "ex-Wells Fargo", a CDO "ex-JPM" — rendered identically for every client,
  // whose evidence ids resolved against nothing, which is why the card's
  // "Evidence · click to view" list was always empty.
  const findings = (DMA.findingsFor(entity.id) || []).map(f => ({
    id: f.f_id,
    title: asText(f.title),
    theme: asText(f.theme),
    platforms: f.platform_chips || [],
    evidence: f.e_ids || [],
    what: asText(f.body),
    why: asText(f.rejected_alternative),
    // The drilldown's SO WHAT is the strategic-alignment argument — which of
    // the client's OWN stated objectives this finding bears on. It was
    // `asText(f.consequence)`: the face's 6–14-word consequence line printed
    // AGAIN under a heading that promises a decision, which is why every
    // drilldown read as generic. The consequence line stays on the face
    // (magnitude, below); the contract states alignment as prose or as
    // {score, statement} — asText unwraps either, never a raw dict — and the
    // stated score travels separately so the card can print it as data.
    so_what: asText(f.strategic_alignment),
    so_what_score: (f.strategic_alignment && typeof f.strategic_alignment === "object"
                    && isFinite(Number(f.strategic_alignment.score)))
      ? Number(f.strategic_alignment.score) : null,
    magnitude: asText(f.consequence),
    subcaps: f.linked_subcap_ids || [],
  }));

  // Nothing to list is a STATE, not a blank panel. This card used to render
  // its header, the count 0 and then literally nothing below the rule — a
  // void that reads as "loading" or as a bug, when the API has already said
  // what happened and why in the section envelope.
  if (!findings.length) {
    return (
      <div className="card flush">
        <div className="card-head">
          <h3>Top findings</h3>
          <span className="b">Nothing to show</span>
        </div>
        <div className="card-body">
          <SectionEmpty
            section="overview.findings"
            absent="No findings section promoted for this run."
            empty="The findings section promoted with no findings in it." />
        </div>
      </div>
    );
  }
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
                    {/* A finding whose run states no alignment argument says so —
                        it never falls back to re-printing the face's consequence
                        line, which is the duplication this block replaces. */}
                    <div style={{ fontSize: 12.5, color: "var(--z-dark)", lineHeight: 1.6, fontWeight: 500 }}>
                      {f.so_what || "The run states no strategic-alignment argument for this finding."}
                    </div>
                    {f.so_what && f.so_what_score != null ? (
                      <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>
                        alignment to stated objectives · {f.so_what_score}
                      </div>
                    ) : null}
                  </div>
                  {/* Resolve FIRST, then decide whether there is a list.
                      This block used to render its heading off
                      `f.evidence.length` and then drop every id the served
                      evidence index could not resolve, one `return null` at a
                      time — so a finding citing two sources showed "Evidence ·
                      click to view" above nothing at all, and a reader could
                      not tell a card with no sources from a card whose sources
                      did not arrive. Invariant 4 makes an unresolvable
                      citation a fail-closed condition; rendering it as an
                      empty list is the silent version of the same thing. */}
                  {f.evidence.length > 0 && f.evidence.every(eid => !DMA.getEvidence(eid)) ? (
                    <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5 }}>
                      The sources behind this finding are not among the evidence served for this run.
                    </div>
                  ) : null}
                  {f.evidence.some(eid => DMA.getEvidence(eid)) ? (
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
      <div style={{ padding: "0 16px 12px" }}>
      </div>
    </div>
  );
}

/* ── Leadership panel + Clay enrichment ─────────────────────────── */
function LeadershipPanel({ audience }) {
  /* Contact detail is PROMOTED, not fetched — and revealed, not shown.

     Clay runs in the PRODUCER's session at synthesis time; its output is
     registered as evidence and written into the roster item (migration 0018),
     so by the time this panel renders the contact route is already a column
     in Postgres, arriving in the same read as the name. The app never calls
     Clay while serving (invariant 1) — which is exactly why the "Enrich via
     Clay" button can exist at all: it is a curtain over data the run already
     holds, not a request. A click flips component state, waits a beat so the
     reveal reads as an action, and shows what was stored. A person the
     producer found no route for gets a transient toast and the curtain comes
     down entirely — a box left standing would promise a route the run cannot
     produce.

     WHAT PERSISTS, and what does not. Owner, 2026-08-15: "When I click enrich
     via Clay, this is not persisted across sessions to me as a user such that
     I never click it again." Correct, and the original "nothing persists" was
     the wrong call for a reader: the curtain reads as a request the first time
     and as busywork every time after, over data the run already holds.

     A REVEAL now persists, per browser and per entity. It is a view
     preference, not content — invariant 2 is untouched, nothing is written
     anywhere the serving tier can see, and a customer-audience payload carries
     no contact columns at all, so a restored reveal on that audience uncovers
     an empty box rather than a leak.

     A "no route" result does NOT persist, deliberately. It is a statement about
     what THIS run found, and freezing it would keep a curtain down over a
     contact a later run fills. Absence is recomputed; only the reader's
     decision is remembered. */
  const { pushToast } = useApp();
  /* Per-entity so a reveal on one client never uncovers another's roster —
     the same identity discipline the registry reads follow. */
  const revealKey = (() => {
    const m = String((typeof window !== "undefined" && window.location.hash) || "")
      .match(/#\/clients\/([^/?]+)/);
    return m ? `dma.reveal.${decodeURIComponent(m[1])}` : null;
  })();
  const [revealed, setRevealed] = useState(() => {
    // Restored on first render rather than in an effect: an effect would paint
    // the closed curtain first and reopen it, which reads as a flicker on
    // exactly the surface this is meant to stop nagging the reader about.
    if (!revealKey || typeof localStorage === "undefined") return {};
    try {
      const ids = JSON.parse(localStorage.getItem(revealKey) || "[]");
      return Array.isArray(ids)
        ? Object.fromEntries(ids.map(id => [id, "done"])) : {};
    } catch (e) {
      return {};   // corrupt storage is not worth a broken panel
    }
  }); // id → "loading" | "done" | "none"
  const remember = (id) => {
    if (!revealKey || typeof localStorage === "undefined") return;
    try {
      const ids = new Set(JSON.parse(localStorage.getItem(revealKey) || "[]"));
      ids.add(id);
      localStorage.setItem(revealKey, JSON.stringify([...ids]));
    } catch (e) { /* private mode, quota — the reveal still works this session */ }
  };
  const [enrichingAll, setEnrichingAll] = useState(false);
  const roster = DMA.LEADERSHIP || [];
  // One route shape for both worlds: live rows carry the promoted email /
  // linkedin_url / phone columns; the fixture's simulated enrichment carries
  // `clay.{email,linkedin}`. Whichever exists is what the reveal shows.
  const routeOf = (ex) => ({
    email: ex.email || (ex.clay && ex.clay.email) || null,
    linkedin: ex.linkedin_url
      || (ex.clay && ex.clay.linkedin ? `https://${ex.clay.linkedin}` : null),
    phone: ex.phone || null,
  });
  const hasRoute = (ex) => {
    const r = routeOf(ex);
    return !!(r.email || r.linkedin || r.phone);
  };
  // An entry with neither a name nor a role. The adapter files it as a gap
  // because it has no name; a gap the producer meant carries the TITLE of the
  // role that is missing, so an entry with neither is not a gap, it is a value
  // this page cannot read. It is never counted as one and never enriched.
  const isUnreadable = (ex) => !ex.title && (!ex.name || ex.name === "-");
  const enrich = (ex, quiet) => {
    setRevealed(m => ({ ...m, [ex.id]: "loading" }));
    setTimeout(() => {
      if (hasRoute(ex)) {
        setRevealed(m => ({ ...m, [ex.id]: "done" }));
        remember(ex.id);
      } else {
        if (!quiet) pushToast(`No stored contact route for ${ex.name}`, "warn");
        setRevealed(m => ({ ...m, [ex.id]: "none" }));
      }
    }, 400);
  };
  const enrichable = roster.filter(x => !x.gap_flag && !isUnreadable(x));
  const enrichAll = () => {
    const targets = enrichable.filter(x => revealed[x.id] !== "done");
    if (!targets.length) return;
    setEnrichingAll(true);
    targets.forEach((ex, i) => setTimeout(() => enrich(ex, true), i * 180));
    // One toast for the whole sweep — a stack of per-person "no route"
    // toasts is noise; one naming the misses is an answer.
    setTimeout(() => {
      const missing = targets.filter(x => !hasRoute(x)).map(x => x.name);
      if (missing.length) pushToast(`No stored contact route for ${missing.join(" · ")}`, "warn");
      setEnrichingAll(false);
    }, targets.length * 180 + 450);
  };
  const doneCount = enrichable.filter(x => revealed[x.id] === "done").length;

  // An empty roster used to render the header, an "Enrich all" button over
  // nobody, and a footer asserting "No critical role gaps in the promoted
  // roster" — a clean bill of health derived from an absence of evidence,
  // which is the fabricated zero-assertion this whole app exists to refuse.
  // Nothing promoted means nothing is claimed, and the API's own account of
  // the absence is what the card shows instead.
  if (!roster.length) {
    return (
      <div className="card flush">
        <div className="card-head">
          <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="users" size={15} /> Leadership panel
          </h3>
          <span className="b">Nothing to show</span>
        </div>
        <div className="card-body">
          <SectionEmpty
            section="overview.leadership"
            absent="No leadership section promoted for this run."
            empty="The leadership section promoted with no named executives in it." />
          <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.55, marginTop: 8 }}>
            With no roster, no role can be called present and none can be called
            missing.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card flush">
      <div className="card-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="users" size={15} /> Leadership panel
        </h3>
        {/* Contact detail for named individuals is internal-only, so the
            customer audience gets no enrichment affordance at all — a button
            whose click could reveal nothing would be a dead control. */}
        {audience !== "customer" ? (
          <button className="btn btn-secondary btn-sm" onClick={enrichAll} disabled={enrichingAll}>
            {enrichingAll ? <><span className="skel" style={{ width: 10, height: 10, borderRadius: 5 }} /> Enriching…</> : <><Icon name="sparkle" size={11} /> Enrich all via Clay</>}
          </button>
        ) : null}
      </div>
      <div style={{ padding: "8px 16px 14px" }}>
        {roster.map(ex => {
          const state = revealed[ex.id]; // undefined | "loading" | "done" | "none"
          const route = routeOf(ex);
          // A row with neither a name nor a title says nothing. The adapter
          // reads "no name" as a role gap, which is right for a producer's
          // deliberate gap row — those carry the title of the missing role —
          // and wrong for an entry that arrived as a string or a number, where
          // every field is undefined. Rendering that as "critical role absent"
          // invents a finding out of a malformed field. Named instead.
          if (isUnreadable(ex)) {
            return (
              <div key={ex.id} style={{ display: "flex", gap: 10, padding: "12px 0",
                                        borderBottom: "1px solid var(--z-sep)" }}
                   data-unreadable-roster-row={ex.id}>
                <div style={{ width: 36, height: 36, borderRadius: 18,
                              background: "var(--z-sep)", color: "var(--z-muted)",
                              display: "flex", alignItems: "center",
                              justifyContent: "center", fontSize: 14, flexShrink: 0 }}>?</div>
                <div style={{ flex: 1, minWidth: 0, fontSize: 11.5,
                              color: "var(--z-muted)", lineHeight: 1.5 }}>
                  This roster entry carries neither a name nor a role, so it
                  states no person and no gap. It is shown rather than dropped:
                  the roster promoted with it in.
                </div>
              </div>
            );
          }
          return (
            <div key={ex.id} style={{ display: "flex", gap: 10, padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
              <div style={{ width: 36, height: 36, borderRadius: 18, background: ex.gap_flag ? "var(--z-sep)" : "linear-gradient(135deg, var(--z-teal), var(--z-mid))", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
                {ex.gap_flag ? "?" : ex.name.split(" ").map(n => n[0]).join("").slice(0, 2)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  {/* The name links out only AFTER the reveal — a linked name
                      beside a box saying "LinkedIn hidden until enriched"
                      would be the route leaking past its own curtain. */}
                  {ex.gap_flag ? (
                    <span style={{ fontWeight: 600, fontSize: 13 }}>-</span>
                  ) : (state === "done" && route.linkedin) ? (
                    <a href={route.linkedin} target="_blank" rel="noreferrer" style={{ fontWeight: 600, fontSize: 13, color: "var(--z-mid)", textDecoration: "none" }} onClick={e => e.stopPropagation()}>{ex.name}</a>
                  ) : (
                    <span style={{ fontWeight: 600, fontSize: 13, color: "var(--z-dark)" }}>{ex.name}</span>
                  )}
                  <span style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>{ex.title}</span>
                  {ex.gap_flag ? <span className="b b-below">GAP</span> :
                   ex.recent_hire ? <span className="b b-org">NEW · {ex.tenure_months} mo</span> :
                   ex.tenure_months != null
                     ? <span style={{ fontSize: 10, color: "var(--z-muted)" }}>· {Math.round(ex.tenure_months / 12)} yr</span>
                     : null}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 4, lineHeight: 1.5 }}>{ex.background}</div>

                {/* The enrichment box, while it has something to say: hidden →
                    the button; loading → the beat; revealed → the stored route
                    and a one-line provenance tag, nothing more (the matching
                    basis is analyst working detail, not panel copy); no route →
                    nothing at all, because the toast already answered. */}
                {ex.gap_flag || audience === "customer" || state === "none" ? null
                 : state === "done" ? (
                  <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--z-ice)", border: "1px solid rgba(39,187,175,.35)", borderRadius: 6 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {route.email ? (
                        <a href={`mailto:${route.email}`} style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} onClick={e => e.stopPropagation()}>
                          <Icon name="envelope" size={11} /> {route.email}
                        </a>
                      ) : null}
                      {route.linkedin ? (
                        <a href={route.linkedin} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} onClick={e => e.stopPropagation()}>
                          <Icon name="linkedin" size={11} /> {String(route.linkedin).replace(/^https?:\/\/(www\.)?/, "")}
                        </a>
                      ) : null}
                      {route.phone ? (
                        <a href={`tel:${String(route.phone).replace(/[^+\d]/g, "")}`} style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} onClick={e => e.stopPropagation()}>
                          <Icon name="phone" size={11} /> {route.phone}
                        </a>
                      ) : null}
                      <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
                        via Clay{ex.enriched_at ? ` · stored ${ex.enriched_at}` : ""}
                      </div>
                    </div>
                  </div>
                ) : state === "loading" ? (
                  <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--z-lav)", border: "1px solid var(--z-sep)", borderRadius: 6 }}>
                    <div className="row" style={{ fontSize: 11, color: "var(--z-dpur)" }}>
                      <span className="skel" style={{ width: 12, height: 12, borderRadius: 6 }} />
                      <span>Checking stored Clay enrichment…</span>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 6 }}>
                    <div className="row" style={{ fontSize: 11 }}>
                      <Icon name="lock" size={11} style={{ color: "var(--z-muted)" }} />
                      <span style={{ color: "var(--z-muted)" }}>Email · LinkedIn hidden until enriched</span>
                      <span className="spacer" />
                      <button className="btn btn-tertiary btn-sm" style={{ padding: "3px 8px", flexShrink: 0 }} onClick={() => enrich(ex)}>
                        <Icon name="sparkle" size={10} /> Enrich via Clay
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ padding: "10px 16px", background: "var(--z-lav)", fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", gap: 6 }}>
        <Icon name="info" size={11} />
        {/* Derived from the roster's own gap rows AND from the roster size the
            run states it reads for. This once read "CISO absent" as a literal,
            so every client was told their CISO was missing; it then read only
            `gap_flag`, and a run whose producer named one of four seats and
            filed NO gap rows got "No critical role gaps in the promoted
            roster." printed eight pixels above its own badge saying "1 of 4
            expected". A clean bill of health is a CLAIM, and this card may
            only make it when the run's own expected count is met.

            `thin_below` is that count, computed at read from the enrichment
            register (`dma_api/computed.py`) and already on this card — the
            badge below prints it. Three states, and they are different facts:
            gap rows the producer named; a roster short of the expected count
            with no rows naming which seats; and a roster that meets it. */}
        {(() => {
          // Read from THIS card's roster, the one rendered above — the line is
          // a statement about the rows on screen, and it is only reachable
          // when there are rows (the empty branch returns above).
          const gaps = roster.filter(x => x.gap_flag && !isUnreadable(x));
          if (gaps.length) {
            const titles = gaps.map(g => g.title || g.domain).filter(Boolean);
            return (
              <span>Critical roles flagged:{" "}
                <strong style={{ color: "var(--z-below)" }}>
                  {titles.length ? `${titles.join(" · ")} absent` : `${gaps.length} absent`}
                </strong>{" "}from evidence</span>
            );
          }
          const st = (DMA.LIVE_ENRICHMENT || {}).leadership || null;
          const expected = st && st.thin_below != null && isFinite(Number(st.thin_below))
            ? Number(st.thin_below) : null;
          const namedRows = roster.filter(x => !x.gap_flag && !isUnreadable(x)).length;
          if (expected != null && namedRows < expected) {
            const short = expected - namedRows;
            return (
              <span>
                {namedRows} of the {expected} leadership seats this assessment reads for
                {namedRows === 1 ? " is named" : " are named"} on this run;
                {" "}{short === 1 ? "the other one is" : `the other ${short} are`} not
                established from a citable source, so no seat below is called present or absent.
              </span>
            );
          }
          if (expected != null) {
            return <span>No critical role gaps in the promoted roster — {namedRows} of {expected} seats named.</span>;
          }
          // No expected count stated: say what is here, claim nothing about
          // what is not. Silence about the denominator is not a clean roster.
          return (
            <span>{namedRows} {namedRows === 1 ? "executive" : "executives"} named on this run;
              {" "}it states no expected roster size, so no seat can be called missing.</span>
          );
        })()}
        <span className="spacer" />
        {doneCount
          ? <span style={{ color: "var(--z-mid)", fontWeight: 600 }}>✓ {doneCount} of {enrichable.length} enriched</span>
          : null}
      </div>
      <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).leadership} what="roster" audience={audience} />
      {/* The trace is where the three unnamed seats ARE named — the producer's
          own domain test lists the accountability set this roster is read
          against, and its counter-case says why naming them without a citable
          route was refused. Internal only. */}
      <div style={{ padding: "0 16px 12px" }}>
      </div>
    </div>
  );
}

/* ── Financial trajectory · D1's own copy ───────────────────────────
   The shared card (cards-data-driven.jsx) prints the regulator through the
   `.chip` class — the right weight for the fixture's "FCA", three mono
   characters, but a credit union's statutory regulator is a full clause
   ("National Credit Union Administration (share insurance); Illinois
   Department of …"), and a chip that long renders as a highlighted block
   that outweighs the chart above it. It also carries the chip's
   cursor:pointer while clicking it does nothing — the page's one dead
   control. The strip is context, not a claim and not a drilldown: the
   prototype's visual weight is small muted text with the regulator in mono,
   nothing highlighted, nothing clickable — so that is what D1 renders. */
function FinancialTrajectoryD1({ entity, audience }) {
  const f = DMA.financialsFor(entity.id);
  if (!f || !(f.fy || []).length) {
    return (
      <div className="card flush">
        <div className="card-head">
          <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
          <span className="b">{absenceBadge("overview.financial_series")}</span>
        </div>
        <div className="card-body">
          <SectionEmpty
            section="overview.financial_series"
            absent="No financial series promoted for this run."
            empty="The financial-series section promoted with no years in it." />
        </div>
      </div>
    );
  }
  const values = (f.total_assets || []).filter(v => v != null);
  const maxA = values.length ? Math.max(...values) : 1;
  const fte = (f.employees || [])[(f.employees || []).length - 1];
  const counts = [
    f.branches != null ? `${f.branches} branches` : null,
    fte != null ? `${fte.toLocaleString()} FTE` : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="card flush" data-source="financial_baseline.json :: total_assets[],net_income_m[],nim_pct[]">
      <div className="card-head">
        <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{f.headline}</span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120 }}>
          {/* Bar tooltips carry only what the series states. The shared card
              interpolates NIM unconditionally, and this section's contract has
              no NIM — so every live bar whispered "NIM null%" on hover. */}
          {f.fy.map((y, i) => (
            <div key={y} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}
                 title={[y, f.total_assets[i] != null ? `$${f.total_assets[i]}${f.unit}` : null,
                         f.nim_pct[i] != null ? `NIM ${f.nim_pct[i]}%` : null].filter(Boolean).join(" · ")}>
              <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--z-dark)" }}>{f.total_assets[i] != null ? `$${f.total_assets[i]}${f.unit}` : null}</div>
              <div style={{ width: "100%", height: `${(f.total_assets[i] || 0) / maxA * 80}px`, background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))", borderRadius: "4px 4px 0 0", transition: "height var(--motion-slow) var(--ease)" }} />
              <div className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{y.replace("FY", "'")}</div>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
          {f.regulator ? <span className="f-mono" style={{ fontSize: 10 }}>{f.regulator}</span> : null}
          {f.geography ? <span>{f.geography}</span> : null}
          <span className="spacer" />
          {counts ? <span style={{ flexShrink: 0 }}>{counts}</span> : null}
        </div>
      </div>
    </div>
  );
}

/* ── Thought leadership ───────────────────────────────────────────
   Three to five entries, not three. The grid was `g3` — three hard columns —
   so a fourth and fifth entry landed in a ragged second row of two, which is
   what made three look like the cap even though nothing here enforced one.
   `auto-fit` with a readable floor lays 3, 4 or 5 out the same way, and the
   heading counts what arrived rather than implying a window.

   WHICH entries are chosen, and how they are weighted towards positions
   Zennify can act on, is the producer's judgement and stays there. This
   renders what the run promoted, in the order it promoted it. */
function ThoughtLeadershipPanel() {
  // `audience` decides how much of the enrichment limit a reader is told: the
  // customer gets the limit on the reading, an internal reader also gets which
  // sources reached it. Read from context rather than threaded through props —
  // passing it in was a ReferenceError the card boundary caught, which is the
  // boundary working and the change still being wrong.
  const { openEvidence, openSubcap, audience } = useApp();
  const entries = DMA.THOUGHT_LEADERSHIP || [];
  return (
    <div className="card flush" style={{ marginBottom: 18 }}>
      <div className="card-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="lightbulb" size={15} /> Thought leadership signal
        </h3>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
          {entries.length
            ? `${entries.length} named executive${entries.length === 1 ? "" : "s"}, in their own words`
            : "Nothing to show"}
        </span>
      </div>
      {/* An empty grid under a heading promising executive signal is a void:
          it reads as a card that failed to load. The section's own account of
          the absence is the answer. */}
      {!entries.length ? (
        <div className="card-body">
          <SectionEmpty
            section="overview.thought_leadership"
            absent="No thought-leadership section promoted for this run."
            empty="The thought-leadership section promoted with no entries in it." />
        </div>
      ) : (
      <div style={{ padding: 16 }}>
        {/* Three tracks, wrapping — so three entries fill one row and five wrap
            3 + 2 rather than 4 + 1. `.g3` carries the responsive collapse
            (two columns at tablet, one below), which an inline auto-fit track
            list cannot: a media query does not reach an inline style. */}
        <div className="g3">
          {entries.map(tl => {
            /* `alignment` is the field the contract calls the most valuable
               thing on this card — a CONTRADICTS entry is the one that must
               never be filtered out — and it was adapted and never rendered.
               An executive quote that argues AGAINST the assessment reads as
               corroboration when its stance is invisible. */
            const al = tl.alignment && typeof tl.alignment === "object" ? tl.alignment : null;
            const stance = al ? String(al.value || "").toUpperCase() : null;
            const stanceTone = stance === "CONTRADICTS" ? "b-org"
              : stance === "EXTENDS" ? "b-purple" : "b-teal";
            return (
            <div key={tl.id} className="card-tile" style={{ padding: 14 }}>
              <div className="row" style={{ marginBottom: 6, gap: 6, flexWrap: "wrap" }}>
                <span className="b b-purple">{String(tl.kind || tl.type || "SIGNAL").toUpperCase()}</span>
                {stance ? (
                  <span className={`b ${stanceTone}`} title={al.clause || ""}>{stance}</span>
                ) : null}
                <span className="spacer" />
                <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{fmtDate(tl.date)}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4, marginBottom: 6 }}>{tl.title}</div>
              {/* WHO said it. The header promises "named executives, in their
                  own words" and the byline was adapted and never rendered, so
                  two executives quoted in the SAME article — different people,
                  different quotes, different cells — rendered as two identical
                  cards and read as a duplication bug. The name is the whole
                  difference between them. */}
              {tl.author ? (
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--z-mid)", marginBottom: 5 }}>
                  {tl.author}
                </div>
              ) : null}
              <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic" }}>"{tl.excerpt}"</div>
              {al && al.clause ? (
                <div style={{ fontSize: 10.5, color: "var(--z-muted)", lineHeight: 1.5, marginTop: 6 }}>
                  {al.clause}
                </div>
              ) : null}
              {/* The link to the assessment. Without it this card is a press
                  clipping; the contract says the cell linkage is what makes it
                  part of the DMA. Fail-closed on evidence, as everywhere: an
                  id this run did not serve is not a drill target. */}
              {(tl.subcaps || []).length || (tl.evidence || []).length ? (
                <div className="row" style={{ gap: 4, flexWrap: "wrap", marginTop: 8 }}>
                  {(tl.subcaps || []).map(sid => (
                    <button key={sid} className="chip f-mono" style={{ fontSize: 9, cursor: "pointer", border: 0 }}
                      title={`Open ${sid} in the heatmap`}
                      onClick={() => openSubcap && openSubcap(sid)}>{sid}</button>
                  ))}
                  {(tl.evidence || []).map(eid => {
                    const e = DMA.getEvidence(eid);
                    return e ? (
                      <button key={eid} className={`tier-chip tier-${e.tier}`} style={{ cursor: "pointer", border: 0 }}
                        title={`${e.title || eid} · ${e.source_pretty || ""}`}
                        onClick={() => openEvidence && openEvidence(eid)}>{eid}</button>
                    ) : (
                      <span key={eid} className="chip muted" title="cited id - not in this run's served evidence">{eid}</span>
                    );
                  })}
                </div>
              ) : null}
              <div className="sep" style={{ margin: "8px 0" }} />
              <div className="row" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                <span style={{ minWidth: 0 }}>{tl.author}</span>
                <span className="spacer" />
                {/* nowrap + no shrink: in a three-column card the four-letter
                    label was breaking to "Ope / n" beside its own icon. */}
                {tl.url ? <a href={`https://${tl.url}`} target="_blank" rel="noreferrer"
                  style={{ color: "var(--z-mid)", display: "inline-flex", alignItems: "center",
                           gap: 3, whiteSpace: "nowrap", flexShrink: 0 }}>Open <Icon name="external" size={10} /></a> : null}
              </div>
            </div>
            );
          })}
        </div>
      </div>
      )}
      <EnrichmentFlag s={(DMA.LIVE_ENRICHMENT || {}).thought_leadership}
                      what="entries" audience={audience} />
      <div style={{ padding: "0 16px 12px" }}>
      </div>
    </div>
  );
}

/* `OvCeilingCard` — DELETED 2026-08-19.

   The "Capability ceiling & uncertainty" card: sixteen categories, each with
   an M-level, a score and an uncertainty band (P1C1 M3 3.0 ±0.4, and so on).
   It is a statement about how confident the ASSESSMENT is, expressed in the
   assessment's own vocabulary, and the third round of live screenshots is
   what that looks like sitting under a client's scores.

   `overview.ceilings` is on the API's NEVER_SERVED allowlist, so this card
   had nothing to read. Deleted rather than left gated, because an
   audience-gated card is one toggle away from rendering and the instruction
   was "renders nowhere". */

/* `OvCoverageBand` — DELETED 2026-08-19.

   The evidence census: 33% overall, per-pillar shares, the 80% hard gate,
   and the "233 of 705 · 51 quote a source · 629 absences · quarantined on
   identity" prose. How well WE evidenced the assessment, on the client's
   own dashboard.

   `overview.evidence_coverage` is on the API's NEVER_SERVED allowlist.
   `CoverageByPillarCard` in cards-data-driven.jsx is deleted with it. */

function Row({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11.5, gap: 8 }}>
      <span style={{ color: "var(--z-muted)", flexShrink: 0, whiteSpace: "nowrap" }}>{k}</span>
      {/* At narrow widths the stylesheet keeps key/value on one line with an
          ellipsis; the title keeps the full value reachable — a regulator name
          cut mid-word with no way to read the rest is a value withheld. */}
      <span style={{ color: "var(--z-dark)", fontWeight: 500, textAlign: "right", minWidth: 0 }}
            title={typeof v === "string" ? v : undefined}>{v}</span>
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
/* Group insight cards into clusters for D2. Priority is the default lens;
   Pillar and Theme are alternates. Cards sort by priority score within a group. */
function groupInsights(cards, mode) {
  // An entry that is not an object is not an insight card, and it must not be
  // scored, filed under a pillar or counted as a "Watch" item — every one of
  // those is a judgement about a card nobody can read. They are held back
  // here and named at the end of the page, each still rendered in place
  // through its own boundary.
  const readable = [], unreadable = [];
  for (const c of cards) (c && typeof c === "object" ? readable : unreadable).push(c);
  const groups = groupReadableInsights(readable, mode);
  if (unreadable.length) {
    groups.push({ key: "__unreadable", label: "Could not be read", color: "org",
      desc: `${unreadable.length} entr${unreadable.length === 1 ? "y" : "ies"} in the `
            + "promoted list is not an insight-card object",
      items: unreadable.map((c, i) => ({ c, p: { score: -1, tier: 0,
                                                 tierLabel: "unreadable",
                                                 tierColor: "org", key: i } })) });
  }
  return groups;
}

function groupReadableInsights(cards, mode) {
  const withP = cards.map(c => ({ c, p: DMA.insightPriority(c) }));
  // Sorting runs ABOVE every card boundary — it walks the whole list before
  // one card renders — so a card whose id is missing must not be able to throw
  // here: `undefined.localeCompare` took the entire page, and the tie-break it
  // was doing is only a stable order. Ordering by an absent id as the empty
  // string states nothing about the card; it just puts it somewhere fixed.
  const byScore = (a, b) => b.p.score - a.p.score
    || String((a.c && a.c.id) || "").localeCompare(String((b.c && b.c.id) || ""));
  if (mode === "pillar") {
    const groups = DMA.PILLARS
      .map(p => ({ key: p.id, label: `${p.id} · ${p.short}`, color: "purple", desc: p.name,
        items: withP.filter(x => x.c.pillar === p.id).sort(byScore) }))
      .filter(g => g.items.length);
    // A card with no pillar and no cell to derive one from is named as such,
    // not filed under a pillar it was never assigned to.
    const orphans = withP.filter(x => !x.c.pillar).sort(byScore);
    if (orphans.length) {
      groups.push({ key: "__nopillar", label: "No pillar stated", color: "org",
        desc: "the run did not state a pillar and the card cites no cell to derive one from",
        items: orphans });
    }
    return groups;
  }
  if (mode === "theme") {
    // "Other" was doing two different jobs: a card the producer themed as
    // "Other", and a card with NO theme at all. Every Baxter card was the
    // second kind, so the theme lens showed one bucket called Other and looked
    // broken. Untriaged cards now group by their pillar with the reason stated,
    // so the lens still clusters usefully while naming what is missing.
    // An insight card has no theme of its own in any contract — the adapter
    // DERIVES it from the O6 finding that shares the card's cell, so a card
    // still without one is a card no finding touches.
    const themed = withP.filter(x => x.c.theme);
    const unthemed = withP.filter(x => !x.c.theme);
    const groups = [...new Set(themed.map(x => x.c.theme))]
      .map(t => {
        const items = themed.filter(x => x.c.theme === t).sort(byScore);
        const why = [...new Set(items.map(x => x.c.theme_source).filter(Boolean))];
        return { key: t, label: t, color: "purple",
                 desc: `${items.length} card${items.length === 1 ? "" : "s"}`
                       + (why.length ? ` · themed by the ${why.join(" / ")}` : ""),
                 items };
      })
      .sort((a, b) => b.items[0].p.score - a.items[0].p.score);
    if (unthemed.length) {
      for (const p of DMA.PILLARS) {
        const items = unthemed.filter(x => x.c.pillar === p.id).sort(byScore);
        if (items.length) {
          groups.push({ key: `__untheme-${p.id}`, label: `${p.id} · ${p.short} · no theme derivable`,
            color: "org",
            desc: `${items.length} card${items.length === 1 ? "" : "s"} whose cells no top finding touches — grouped by pillar instead`,
            items });
        }
      }
      const loose = unthemed.filter(x => !x.c.pillar).sort(byScore);
      if (loose.length) {
        groups.push({ key: "__untheme-none", label: "No theme and no pillar", color: "org",
          desc: "these cards cite no cell, so neither a pillar nor a finding's theme can be derived",
          items: loose });
      }
    }
    return groups;
  }
  const defs = [
    { key: 1, label: "Act now",   color: "below", desc: "Critical gaps + high-confidence, actionable opportunities - lead with these" },
    { key: 2, label: "Plan next", color: "org",   desc: "Opportunities to sequence into the roadmap" },
    { key: 3, label: "Watch",     color: "teal",  desc: "Stable or monitoring items - no immediate action needed" },
  ];
  return defs
    .map(d => ({ ...d, items: withP.filter(x => x.p.tier === d.key).sort(byScore) }))
    .filter(g => g.items.length);
}

/* One insight card's face. Its own component so React invokes it inside the
   boundary that wraps it — see renderCard. */
function InsightTile({ c, p, groupBy, onOpen }) {
  return (
    <div className={`ic ${c.flag.toLowerCase()}`} onClick={() => onOpen(c.id)}>
      <div className="ic-head">
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="ic-id">{c.id}</span>
          <span className="b b-purple">{c.pillar}</span>
          <span className={`b b-${p.tierColor}`}>{p.tierLabel}</span>
          {groupBy !== "theme" && c.theme ? <span className="b b-muted">{c.theme}</span> : null}
        </div>
        {c.annotation ? <span className="b b-above" title="Annotated"><Icon name="edit" size={9} /> NOTE</span> : null}
      </div>
      <div className="ic-title">{c.title}</div>
      <div className="ic-body">{c.what.slice(0, 170)}{c.what.length > 170 ? "…" : ""}</div>
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
        {c.platforms.map(pf => <span key={pf} className="b b-teal">{DMA.getPlatform(pf)?.short}</span>)}
      </div>
    </div>
  );
}

function ClientInsights({ entity, run }) {
  const { openInsight, openEvidence, audience, pushToast } = useApp();
  const [flag, setFlag] = useState("ALL");
  const [pillar, setPillar] = useState("ALL");
  const [conf, setConf] = useState("ALL");
  const [groupBy, setGroupBy] = useState("priority");
  const [collapsed, setCollapsed] = useState({});

  const filtered = useMemo(() => DMA.INSIGHT_CARDS.filter(c => {
    // An entry that is not a card cannot answer a filter question. It is kept
    // rather than dropped: dropping it would hide a malformed payload behind a
    // count that looks right, and groupInsights names it at the foot instead.
    if (!c || typeof c !== "object") return true;
    if (flag !== "ALL" && c.flag !== flag) return false;
    if (pillar !== "ALL" && c.pillar !== pillar) return false;
    if (conf !== "ALL" && c.confidence !== conf) return false;
    return true;
  }), [flag, pillar, conf]);

  const groups = useMemo(() => groupInsights(filtered, groupBy), [filtered, groupBy]);

  const tierCounts = { 1: 0, 2: 0, 3: 0 };
  // Counted over the cards that ARE cards. A tier is a reading of a card's
  // flag and confidence; an entry with neither cannot be read into one, and
  // adding it to WATCH would be a count of something nobody assessed.
  const readableCards = DMA.INSIGHT_CARDS.filter(c => c && typeof c === "object");
  const unreadableCount = DMA.INSIGHT_CARDS.length - readableCards.length;
  readableCards.forEach(c => tierCounts[DMA.insightPriority(c).tier]++);
  const filtersActive = flag !== "ALL" || pillar !== "ALL" || conf !== "ALL";

  // Each card renders inside its OWN boundary. This is the granularity that
  // matters on this page: the list is long, its items come straight from the
  // promoted payload, and until now one item with a title that was an object
  // (or a body that was null) threw during render and React unmounted the
  // WHOLE app — every card on this page, the chrome, the nav, the <body>.
  // One bad item now costs one tile.
  //
  // The tile is a COMPONENT, not a function called inline. An inline call runs
  // during THIS component's render — outside the boundary it was handed to —
  // so the throw would escape and the boundary would never see it. React must
  // be the one to invoke it.
  const renderCard = ({ c, p }, i) => (
    <ItemBoundary key={(c && c.id) || `insight-${i}`}
                  name={(c && c.id) || "an insight card"}>
      <InsightTile c={c} p={p} groupBy={groupBy} onOpen={openInsight} />
    </ItemBoundary>
  );

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Insight cards</div>
          <h1>{DMA.INSIGHT_CARDS.length} insight cards</h1>
          <div className="sub">
            <span className="b b-below" style={{ marginRight: 6 }}>{tierCounts[1]} ACT NOW</span>
            <span className="b b-org" style={{ marginRight: 6 }}>{tierCounts[2]} PLAN NEXT</span>
            <span className="b b-teal">{tierCounts[3]} WATCH</span>
            {unreadableCount ? (
              <span className="b b-org" style={{ marginLeft: 6 }}
                    title="entries in the promoted list that are not insight-card objects">
                {unreadableCount} UNREADABLE</span>
            ) : null}
          </div>
        </div>
        <div className="actions">
          <button className="btn btn-tertiary" onClick={() => pushToast(`Exporting ${filtered.length} insight cards as PDF…`, "success")}><Icon name="download" size={13} /> Export PDF</button>
          <button className="btn btn-secondary" onClick={() => pushToast("Add a note from any insight card - click a card to start", "success")}><Icon name="plus" size={13} /> Add note</button>
        </div>
      </div>

      {/* Group-by + filters */}
      <div className="filter-bar">
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>Group by</span>
        <div className="toggle-row">
          {[["priority", "Priority"], ["pillar", "Pillar"], ["theme", "Theme"]].map(([k, l]) => (
            <button key={k} className={groupBy === k ? "on" : ""} onClick={() => setGroupBy(k)}>{l}</button>
          ))}
        </div>
        <span style={{ width: 1, height: 22, background: "var(--z-sep)", margin: "0 4px" }} />
        <select className="inp" style={{ maxWidth: 150 }} value={pillar} onChange={e => setPillar(e.target.value)}>
          <option value="ALL">All pillars</option>
          {DMA.PILLARS.map(p => <option key={p.id} value={p.id}>{p.id} · {p.short}</option>)}
        </select>
        <select className="inp" style={{ maxWidth: 150 }} value={flag} onChange={e => setFlag(e.target.value)}>
          <option value="ALL">All flags</option>
          <option>CRITICAL</option><option>OPPORTUNITY</option><option>MONITOR</option>
        </select>
        <select className="inp" style={{ maxWidth: 160 }} value={conf} onChange={e => setConf(e.target.value)}>
          <option value="ALL">All confidence</option>
          <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
        </select>
        {filtersActive ? <button className="btn btn-tertiary btn-sm" onClick={() => { setFlag("ALL"); setPillar("ALL"); setConf("ALL"); }}>Clear</button> : null}
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{filtered.length} of {DMA.INSIGHT_CARDS.length} shown</span>
      </div>

      {/* Grouped clusters. Two different nothings, and the page used to call
          both of them "adjust the filters": a run with no insights section
          promoted told the reader to change a filter that was not hiding
          anything. */}
      {groups.length === 0 ? (
        DMA.INSIGHT_CARDS.length === 0 ? (
          <div className="empty" style={{ padding: 40 }}>
            <div className="icon"><Icon name="insight" size={20} /></div>
            <h3>No insight cards for this run</h3>
            <SectionEmpty
              section="insights.insights"
              absent="The insights section did not promote for this run."
              empty="The insights section promoted with no cards in it." />
          </div>
        ) : (
          <div className="empty" style={{ padding: 40 }}><h3>No insight cards match</h3><p>Adjust the filters to see cards.</p></div>
        )
      ) : groups.map(g => {
        const gid = `${groupBy}:${g.key}`;
        const isCollapsed = !!collapsed[gid];
        return (
          <div key={g.key} style={{ marginBottom: 16 }}>
            <button onClick={() => setCollapsed(o => ({ ...o, [gid]: !isCollapsed }))}
              style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "8px 0", background: "none", border: 0, borderBottom: "2px solid var(--z-sep)", cursor: "pointer", textAlign: "left", marginBottom: 12 }}>
              <span className={`b b-${g.color}`}>{g.label}</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{g.items.length}</span>
              <span style={{ fontSize: 11.5, color: "var(--z-muted)", flex: 1, minWidth: 0 }} className="txt-fit-1">{g.desc}</span>
              <Icon name={isCollapsed ? "chevron-d" : "chevron-u"} size={15} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
            </button>
            {!isCollapsed ? <div className="g2">{g.items.map(renderCard)}</div> : null}
          </div>
        );
      })}

      {/* Technology landscape sub-view */}
      <CardBoundary name="technology landscape">
      <div className="card flush" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <h3>Technology landscape</h3>
          <button className="btn btn-tertiary btn-sm" onClick={() => navigate(`/clients/${entity.id}/techstack`, { run: run.id })}>Open full stack <Icon name="arrow-r" size={11} /></button>
        </div>
        <div className="card-body">
          {/* Four zeros are an assertion: they say a register was compiled and
              found nothing confirmed, nothing inferred, nothing claimed and no
              gaps — a technographic scan nobody ran. With no register there is
              no landscape, and the section says so. The counts below are only
              ever computed FROM the register (invariant 8), so they are only
              drawn when there is one. */}
          {!DMA.TECH_STACK.length ? (
            <SectionEmpty
              section="techstack.techstack"
              absent="No technology register promoted for this run, so this run states no landscape."
              empty="The technology section promoted with no rows in it." />
          ) : (
          <div className="g4">
            {[
              { label: "Confirmed",   count: DMA.TECH_STACK.filter(t => t.status === "CONFIRMED").length, tone: "b-teal",   sub: "T1–T3 evidence",   desc: "Active deployments validated via Explorium and primary sources." },
              { label: "Inferred",    count: DMA.TECH_STACK.filter(t => t.status === "INFERRED").length,  tone: "b-purple", sub: "Job + press signals", desc: "Strong circumstantial signal - not yet confirmed." },
              /* Counts are computed from the register, never asserted — the
                 Claimed tile carried a hardcoded 7 — and the Gaps tile names
                 the products THIS client is actually missing rather than the
                 fixture's four. */
              { label: "Claimed",     count: DMA.TECH_STACK.filter(t => t.status === "CLAIMED").length,   tone: "b-org",    sub: "T4–T5 marketing",  desc: "Marketing pages reference platforms not yet confirmed." },
              { label: "Gaps",        count: DMA.TECH_STACK.filter(t => t.status === "ABSENT").length,    tone: "b-below",  sub: "ABSENT confirmed",
                desc: (DMA.TECH_STACK.filter(t => t.status === "ABSENT").map(t => t.name).filter(Boolean).slice(0, 4).join(" · ")
                       || "No confirmed absences in the register.") },
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
          )}
        </div>
      </div>
      </CardBoundary>
    </div>
  );
}

Object.assign(window, { ClientOverview, ClientInsights, ScoreRing,
                        SnapshotStrip, FirmographicsPanel, TopFindingsCard,
                        LeadershipPanel, InsightTile, groupInsights });
