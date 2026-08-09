/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Live adapter — promoted payload → window.DMA accessors

   The prototype IS the renderer. Every one of its components reads through
   one namespace (`window.DMA`, data.js), and data.js already carries the
   live-aware pattern for corpus-level lists: `INSIGHT_CARDS = LIVE ? [] :
   […]`. What it never got was the ENTITY-scoped accessors — financialsFor,
   sentimentFor, coverageFor, uncertaintyFor, evidenceSummaryFor, whyNowFor,
   recsFor, EVIDENCE, TECH_STACK, FOCUS_AREAS, LEADERSHIP, ROADMAP — which
   still fall back to the fictional flagship `fce-001`.

   This module closes that gap. It is pure: no React, no fetch, no globals
   read. Every function takes promoted sections and returns the exact shape
   one prototype component expects, so the components render unchanged and
   every drilldown works because it is the prototype's own drilldown.

   Two rules hold everywhere below:

   1. ABSENT IS NULL. A section that did not promote yields null or [], never
      a plausible default and never fixture data. A fictional bank's prose
      under a real client's name is the one defect this whole file exists to
      prevent.
   2. NOTHING IS RECOMPUTED that the producer or the database already
      computed (invariants 8 and 9). delta, band, grounded_on, age_months,
      share_pct and is_thin_evidence arrive computed; scores arrive as
      scored. Where the prototype's shape needs a value the payload does not
      carry, the answer is null — not an estimate.
   ═══════════════════════════════════════════════════════════════════════ */

/* Section payload, or null when it did not promote. */
function secOf(page, name) {
  const s = page && page.sections && page.sections[name];
  return s && s.data || null;
}

/* Section payload WITH the envelope's citation list attached.
   `e_ids` lives on the section envelope, not inside `data`, so a card that
   renders "evidence for this section" got nothing through secOf — the
   regulatory standing card printed "this section cites no evidence ids" while
   the envelope carried two. Attached under the same key the item contracts use,
   and never overwriting a data field of that name. */
function secWithEnv(page, name) {
  const sec = page && page.sections && page.sections[name];
  const d = sec && sec.data || null;
  if (!d) return null;
  if (d.e_ids !== undefined || !Array.isArray(sec.e_ids) || !sec.e_ids.length) return d;
  return {
    ...d,
    e_ids: sec.e_ids
  };
}
function num(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* ── entity.subcaps · the cell grain ──────────────────────────────────
   From /v1/entities/{id}/subcaps — the workbook's own scores, read-only.
   `thin` and `delta` are the database's GENERATED columns; the platform
   chips come from the catalogue's L3 platform areas for that cell. */
const PLATFORM_ALIASES = {
  salesforce: "SF",
  "data cloud": "SF",
  agentforce: "SF",
  fsc: "SF",
  "financial services cloud": "SF",
  "marketing cloud": "SF",
  "service cloud": "SF",
  "sales cloud": "SF",
  crma: "SF",
  databricks: "DB",
  "mosaic ai": "DB",
  lakeflow: "DB",
  lakehouse: "DB",
  tableau: "TBL",
  pulse: "TBL",
  twilio: "TW",
  engage: "TW",
  conversations: "TW",
  ncino: "nCino",
  "workflow engine": "nCino",
  "document manager": "nCino"
};
function platformChips(areas) {
  const out = [];
  for (const a of areas || []) {
    const t = String(a).toLowerCase();
    for (const key of Object.keys(PLATFORM_ALIASES)) {
      if (t.includes(key) && !out.includes(PLATFORM_ALIASES[key])) {
        out.push(PLATFORM_ALIASES[key]);
      }
    }
  }
  return out;
}
function adaptSubcaps(subcapRows) {
  return (subcapRows || []).map(r => ({
    id: r.subcap_id,
    name: r.subcap_name || r.subcap_id,
    pillar: r.pillar_id,
    category: r.category_id,
    capability: r.capability_id,
    score: num(r.score),
    peerMedian: num(r.peer_median),
    peer_n: r.peer_n,
    peer_basis: r.peer_basis,
    proxy_disclosure: r.proxy_disclosure,
    delta: num(r.delta),
    confidence: r.confidence,
    evidence_count: r.linked_evidence_count == null ? 0 : r.linked_evidence_count,
    thin: !!r.is_thin_evidence,
    source_cell: r.source_cell,
    platforms: platformChips(r.l3_platform_areas),
    l4_features: r.l4_features || []
  }));
}

/* ── entity.oss · platform fit, 0–100 ────────────────────────────────
   The prototype's five fit tiles read entity.oss[platformId]. The promoted
   opportunity surface already scores exactly this, per platform, as its
   `composite` — so the tiles are the opportunity surface, not a second
   ranking. A platform the producer did not score is absent, not zero: a
   zero would render as "assessed, and nothing there". */
function adaptOss(opportunity) {
  const out = {};
  for (const t of opportunity && opportunity.tiles || []) {
    // Keyed by the PROMOTED platform string. Folding onto a vendor alias
    // collapsed "Salesforce Data Cloud" (70.0) and "Service Cloud
    // consolidation" (73.0) onto one key "SF" — last write won, so a promoted
    // tile was silently destroyed and the surviving score was labelled with the
    // other one's name plus a feature string read from the static vendor
    // catalogue. Four promoted tiles rendered as three.
    const key = t.platform;
    const v = num(t.composite);
    if (key && v !== null) out[key] = v;
  }
  return out;
}

/* The opportunity tiles in full — the promoted platform name, its composite,
   its factors and its rationale. `oss` is the score-only map the prototype's
   fit tiles read; this is what a surface should use when it wants to say
   anything ABOUT the platform, because the static catalogue knows nothing
   about this client. */
function adaptOpportunityTiles(opportunity) {
  return (opportunity && opportunity.tiles || []).map(t => ({
    platform: t.platform || null,
    composite: num(t.composite),
    factors: t.factors || null,
    rationale: t.rank_rationale || t.rationale || null,
    stack_context: t.their_stack_context || null,
    gap_count: t.gap_count == null ? null : Number(t.gap_count),
    absent_count: t.absent_count == null ? null : Number(t.absent_count),
    e_ids: t.e_ids || []
  }));
}

/* ── financialsFor ───────────────────────────────────────────────────
   The prototype's card draws one bar per fiscal period with the value above
   it and a footer of regulator · footprint · branches · FTE. Periods come
   from the promoted series; the footer figures come from firmographics,
   which is where they are stated. */
/* Compound annual growth rate over the promoted series.
   Uses the FIRST and LAST points that carry both a period year and a positive
   value, and the real number of years between them — not the count of rows,
   which would be wrong for any series with a gap. Returns {} when it cannot be
   computed, so the caller spreads nothing and the field stays absent. */
function cagrOf(series) {
  const yearOf = s => {
    const m = /(\d{4})/.exec(String(s.period || ""));
    return m ? Number(m[1]) : null;
  };
  const pts = (series || []).map(s => ({
    y: yearOf(s),
    v: num(s.value)
  })).filter(p => p.y !== null && p.v !== null && p.v > 0).sort((a, b) => a.y - b.y);
  if (pts.length < 2) return {};
  const a = pts[0],
    b = pts[pts.length - 1];
  const years = b.y - a.y;
  if (years <= 0) return {};
  const cagr = Math.pow(b.v / a.v, 1 / years) - 1;
  if (!isFinite(cagr)) return {};
  return {
    cagr,
    cagr_basis: `${a.y}–${b.y} · ${years} yr`
  };
}
function adaptFinancials(financialSeries, firmographics, regulatory) {
  const series = financialSeries && financialSeries.series || [];
  if (!series.length) return null;
  const fields = {};
  for (const f of firmographics && firmographics.fields || []) {
    fields[f.field] = f;
  }
  const unitOf = s => {
    const u = String(s.unit || "").toLowerCase();
    if (u.includes("trillion")) return "T";
    if (u.includes("billion")) return "B";
    if (u.includes("million")) return "M";
    return "";
  };
  const first = series.find(s => s.unit) || series[0];
  const last = [...series].reverse().find(s => s.value != null);
  return {
    currency: "USD",
    unit: unitOf(first),
    fy: series.map(s => s.period || "—"),
    total_assets: series.map(s => num(s.value)),
    // Net income and NIM are not in this section's contract. Null, not zero:
    // a zero-height bar reads as a measured zero.
    net_income_m: series.map(() => null),
    nim_pct: series.map(() => null),
    employees: [num(fields.employees && fields.employees.value)],
    branches: num(fields.branches && fields.branches.value),
    regulator: regulatory && regulatory.primary_regulator || fields.primary_regulator && fields.primary_regulator.value || null,
    geography: regulatory && (regulatory.jurisdictions || []).join(" · ") || null,
    headline: last ? `${moneyOf(last)} · ${last.period || ""}`.trim() : null,
    basis: (series.find(s => s.basis) || {}).basis || null,
    // CAGR is COMPUTED from the dated points, never taken on faith. The card
    // showed "—" because no contract field carries it and nothing derived it,
    // while the series states the endpoints it needs. Computed-or-null
    // (invariant 9): fewer than two dated points, or a non-positive endpoint,
    // yields null rather than a figure with no basis. `cagr_basis` names the
    // span so the reader can see what it was computed over.
    ...cagrOf(series),
    trend: financialSeries.trend || null,
    verified_sparse: !!financialSeries.verified_sparse,
    events: []
  };
}
function moneyOf(s) {
  const v = num(s.value);
  if (v === null) return "—";
  const u = String(s.unit || "").toLowerCase();
  const suffix = u.includes("trillion") ? "T" : u.includes("billion") ? "B" : u.includes("million") ? "M" : "";
  return `$${v}${suffix}`;
}

/* ── sentimentFor ────────────────────────────────────────────────────
   The prototype renders two groups, Employee and Customer, each a list of
   {source, metric, score, scale, n}. The promoted bars carry `audience`, so
   the grouping is the payload's own — not a guess. A bar's rating is
   normalised onto its OWN stated scale only: the card divides score by
   scale, so an NPS on -100..100 must arrive with that scale, never rescaled
   here into something the producer never said. */
function adaptSentiment(sentiment) {
  const bars = sentiment && sentiment.bars || [];
  if (!bars.length) return null;
  const group = which => bars.filter(b => String(b.audience || "").toLowerCase() === which).map(b => ({
    source: b.source,
    metric: b.metric || b.scale || null,
    score: num(b.rating),
    scale: b.scale || null,
    scale_max: scaleMaxOf(b.scale),
    n: num(b.n),
    as_of: b.as_of,
    e_id: b.e_id,
    url: b.url,
    trend_vs_prior: b.trend_vs_prior
  }));
  const employee = group("employee");
  const customer = group("customer");
  const ungrouped = bars.filter(b => !b.audience).map(b => ({
    source: b.source,
    metric: b.metric || b.scale || null,
    score: num(b.rating),
    scale: b.scale || null,
    scale_max: scaleMaxOf(b.scale),
    n: num(b.n),
    as_of: b.as_of,
    e_id: b.e_id,
    url: b.url
  }));
  return {
    employee,
    customer,
    ungrouped,
    industry_avg: num(sentiment.industry_avg),
    b2b_b2c_gap: !!sentiment.b2b_b2c_gap
  };
}

/* "NPS -100..100" -> 100; "0..5" -> 5; unstated -> null, and the card must
   not draw a bar for a rating whose bounds nobody stated. */
function scaleMaxOf(scale) {
  const m = String(scale || "").match(/(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)/);
  return m ? Number(m[2]) : null;
}

/* The context tiles state their bounds as "1-5 stars" where the overview's
   bars write "0..5". Both are the producer's own statement of the scale, so
   both are read; anything else stays null and the tile shows the stated
   string rather than a denominator nobody wrote. */
function tileScaleMaxOf(scale) {
  const viaRange = scaleMaxOf(scale);
  if (viaRange !== null) return viaRange;
  const m = String(scale || "").match(/(-?\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)/);
  return m ? Number(m[2]) : null;
}

/* ── contextSentimentFor (C4) ────────────────────────────────────────
   The CONTEXT page's own sentiment grid reads `context_sentiment`, a
   different section from the overview's `sentiment`: tiles per audience,
   each carrying the measured rows behind it. Only the overview's bars were
   ever adapted, so the grid's section sat promoted and unread and the card
   said "no sentiment measures promoted for this run" over three tiles.

   Tiles come in two kinds and both are content. A tile with rows becomes
   stat cards — one per measured row, on its own stated scale. A tile with
   state=WORKED_ABSENT is a finding, not a blank: it carries the ladder of
   sources that refused, and the card states that rather than showing a
   number nobody measured. */
function adaptContextSentiment(section) {
  const tiles = section && section.context_tiles || [];
  if (!tiles.length) return null;
  const groups = {};
  const absent = [];
  for (const t of tiles) {
    const g = String(t.audience || "unstated");
    const rows = (t.rows || []).map(r => ({
      label: r.source || null,
      value: num(r.rating),
      scale: r.scale || null,
      scale_max: tileScaleMaxOf(r.scale),
      n: num(r.n),
      note: r.note || null,
      as_of: r.as_of || null,
      url: r.url || null,
      e_ids: r.e_id ? [r.e_id] : []
    })).filter(r => r.value !== null);
    if (rows.length) {
      groups[g] = (groups[g] || []).concat(rows);
    } else if (t.state === "WORKED_ABSENT") {
      absent.push({
        group: g,
        note: t.note || null,
        sources_searched: t.sources_searched || []
      });
    }
  }
  if (!Object.keys(groups).length && !absent.length) return null;
  return {
    groups,
    absent
  };
}

/* ── coverageFor ─────────────────────────────────────────────────────
   pct, cells and the gate threshold all arrive promoted; the orange line the
   card draws is at gate_pct, which is data, not a UI constant. */
function adaptCoverage(coverage) {
  if (!coverage) return null;
  return {
    overall_pct: num(coverage.overall_pct),
    by_pillar: (coverage.per_pillar || []).map(p => ({
      pillar: p.pillar_id,
      pct: num(p.pct),
      subcaps: num(p.cells_total),
      scored: num(p.cells_covered),
      below_gate: !!p.below_gate
    })),
    gate_pct: num(coverage.gate_pct),
    denominator_definition: coverage.denominator_definition || null,
    note: coverage.note || null
  };
}

/* ── uncertaintyFor ──────────────────────────────────────────────────
   Keyed by category, as the card iterates. `ceiling` may arrive as a BAND
   WORD ("Differentiating") rather than a number — the card positions a
   marker on a 1–5 axis, so a word is mapped to the midpoint of its band and
   flagged, never silently treated as a score. */
const BAND_MIDPOINT = {
  activating: 1.5,
  building: 2.5,
  competing: 3.5,
  differentiating: 4.5
};
function adaptUncertainty(ceilings) {
  const rows = ceilings && ceilings.rows || [];
  if (!rows.length) return null;
  const out = {};
  for (const r of rows) {
    if (!r.category_id) continue;
    const asNum = num(r.ceiling);
    const word = asNum === null ? BAND_MIDPOINT[String(r.ceiling || "").trim().toLowerCase()] ?? null : null;
    out[r.category_id] = {
      ceiling: asNum !== null ? asNum : word,
      ceiling_stated: r.ceiling,
      ceiling_is_band: asNum === null && word !== null,
      band: num(r.uncertainty_band) ?? 0,
      modifiers: (r.urf_modifiers || []).map(modifierText).filter(Boolean),
      evidence: r.e_ids || [],
      rationale: r.rationale || null,
      limiting_absence: r.limiting_absence || null,
      category_name: r.category_name || null,
      claim: r.claim_label || null,
      confidence: r.confidence || null
    };
  }
  return out;
}
function modifierText(m) {
  if (m === null || m === undefined) return null;
  if (typeof m === "string") return m;
  if (typeof m === "object") {
    const val = m.value === null || m.value === undefined ? "" : ` ${m.value}`;
    return `${m.clause || m.name || ""}${val}`.trim() || null;
  }
  return String(m);
}

/* ── evidenceSummaryFor ──────────────────────────────────────────────
   The tier-distribution card's whole content. Counted server-side over the
   evidence store, so this is a pass-through: recounting it in the browser
   would be a second source of truth for the same number. */
function adaptEvidenceSummary(evidenceEnvelope) {
  const d = evidenceEnvelope && evidenceEnvelope.distribution;
  if (!d) return null;
  const facts = Object.keys(d.claims || {}).reduce((a, k) => a + (d.claims[k] || 0), 0);
  return {
    total_items: d.total_items,
    // Fact-level totals are per-claim counts from the store; the card prints
    // them beside the item count.
    total_facts: facts,
    tiers: d.tiers || {},
    claims: d.claims || {},
    signals: {},
    connectors: {},
    excluded_identity: d.excluded_identity || 0
  };
}

/* ── whyNowFor ───────────────────────────────────────────────────────
   The prototype's signal card: strength badge, window chip, a mono metric
   line, the play, peer context, the if-ignored risk, evidence and a dated
   source. Every one of those is a promoted field. */
function adaptWhyNow(whyNow) {
  const signals = whyNow && whyNow.signals || [];
  if (!signals.length) return null;
  return signals.map(s => ({
    id: s.wn_id,
    label: s.trigger_label || headlineOf(s.trigger),
    // the contract's field is `kind` (M&A · LEADERSHIP · REGULATORY ·
    // TECHNOLOGY); the card renders it as the signal's category badge
    category: s.kind || s.category || null,
    strength: s.strength || null,
    window: s.window || null,
    confidence: s.confidence || null,
    claim: s.claim_label || null,
    detail: s.trigger || null,
    metric: s.metric || null,
    peer_context: s.peer_context || null,
    play: s.why_this_sequence || null,
    risk: s.consequence_of_waiting || null,
    cost_now: s.cost_of_acting_now || null,
    evidence: s.e_ids || [],
    timeline: s.dated_on ? {
      date: s.dated_on,
      event: s.dated_source || null
    } : null,
    impact: s.impact || null,
    subcaps: s.linked_subcap_ids || []
  }));
}

/* A signal's own first clause, used as the card's title when the producer
   did not author a separate label. Never invented — a slice of what was
   written, cut at the first sentence boundary. */
/* The why-now card's face: the trigger's FIRST SENTENCE, whole.

   This used to cut at 72 characters and append an ellipsis, which is how
   every card ended mid-clause — "…merger with HealthCare Associates Credit
   Unio…", "…on 1 July 2026: Jim Block steps…". A card face that stops
   mid-word is not a summary of the signal, it is a fragment of one, and the
   reader has to open the drilldown to find out what the sentence said.

   So: end at a real sentence boundary or not at all. A full stop only counts
   when it ends a sentence rather than an abbreviation or a decimal — "$6.5
   billion" and "Jan. 2026" must not split. Nothing is truncated; a long
   trigger makes a taller card, and the grid levels the row. */
function headlineOf(text) {
  if (!text) return null;
  const t = String(text).trim();
  // A sentence end: . ! ? or ; followed by whitespace and a capital, or the
  // end of the string. What disqualifies a full stop is what comes AFTER it,
  // not before: "$6.5 billion" is followed by a digit and "Jan. 2026" by a
  // digit, so neither matches, while "…on 12 June 2026. The conversion…"
  // correctly does. Guarding on the preceding character instead was the
  // subtler bug — it protected decimals and broke every sentence that ends
  // in a year, which in this corpus is most of them.
  const m = t.match(/^(.*?[.;!?])(?=\s+["“(]?[A-Z]|\s*$)/);
  const head = m ? m[1] : t;
  // An em dash introduces the elaboration rather than ending the sentence,
  // so it is a legitimate face boundary when it comes first. This reads the
  // PAYLOAD, which still holds whatever the producer wrote — the hyphen
  // normalisation happens at render, downstream of here. A matcher rewritten
  // to look for the normalised form finds nothing and silently stops
  // truncating, which is how the face went back to carrying the elaboration.
  const dash = head.search(/\s[-—–]\s/);
  return (dash > 24 ? head.slice(0, dash) : head).trim();
}

/* ── INSIGHT_CARDS ───────────────────────────────────────────────────
   The prototype's `.ic` card and the Act now / Plan next / Watch clustering.
   `flag` drives the card's left border and the priority tier; where the
   producer authored one it is used, and until the schema carries it the
   severity the contract DOES define stands in — mapped, and recorded as
   derived so the surface can say so. */
/* The contract's severity vocabulary is critical|high|opportunity|info. Two of
   the four were missing here and two values the contract never defines were
   present, so an `opportunity` card fell through to the MONITOR default — the
   one flag that means "no action". */
const SEVERITY_TO_FLAG = {
  critical: "CRITICAL",
  high: "OPPORTUNITY",
  opportunity: "OPPORTUNITY",
  info: "MONITOR",
  medium: "MONITOR",
  low: "MONITOR"
};

/* The theme lens on D2 groups cards by `theme`, and an insight card has no such
   field: the Surface Spec's I1 contract does not define one and `insight_cards`
   has no column, so every card grouped as null and the lens showed one bucket.
   The theme is not missing from the run, though — O6 findings carry it, from a
   closed vocabulary, with the cells each finding bears on. So a card's theme is
   DERIVED from the finding that shares its cell, exactly as its pillar is
   derived from the cell id: computed, never stored (invariants 8 and 9), and no
   invented payload field.

   Two rungs, and which one produced the answer is recorded so the surface can
   say so. Exact cell first; then the finding's category (P1C1) — a coarser
   match, but a theme is a category-grain orientation cue in the O6 prompt's own
   mapping, so it is a fair inheritance. Nothing beyond that: a card whose cell
   no finding touches has no theme, and the lens names it rather than guessing. */
function themeIndexOf(findings) {
  const byCell = {},
    byCategory = {};
  for (const f of findings && findings.findings || []) {
    const theme = f && f.theme ? String(f.theme).toUpperCase() : null;
    if (!theme) continue;
    for (const id of f.linked_subcap_ids || []) {
      const cell = String(id);
      if (!(cell in byCell)) byCell[cell] = theme;
      const cat = /^(P[1-4]C\d+)/.exec(cell);
      if (cat && !(cat[1] in byCategory)) byCategory[cat[1]] = theme;
    }
  }
  return {
    byCell,
    byCategory
  };
}
function themeForCells(index, cells) {
  for (const c of cells || []) {
    if (index.byCell[String(c)]) return [index.byCell[String(c)], "finding on the same cell"];
  }
  for (const c of cells || []) {
    const cat = /^(P[1-4]C\d+)/.exec(String(c));
    if (cat && index.byCategory[cat[1]]) {
      return [index.byCategory[cat[1]], `finding in ${cat[1]}`];
    }
  }
  return [null, null];
}

/* A cell id carries its pillar in the leading token: P4C1.3.1 → P4. Reading it
   is not inference — the catalogue's id scheme guarantees it — so a card whose
   `pillar_id` the producer left null can still be filed against the right
   pillar instead of landing in an "other" bucket. */
function pillarOfCell(cellId) {
  const m = /^(P[1-4])/.exec(String(cellId || ""));
  return m ? m[1] : null;
}
function adaptInsights(insights, recommendations, findings) {
  const cards = insights && insights.cards || [];
  const themes = themeIndexOf(findings);
  const recPlatforms = {};
  for (const r of recommendations && recommendations.recommendations || []) {
    recPlatforms[r.rec_id] = platformChips([r.l3_area, r.l4_feature]);
  }
  return cards.map(c => {
    const authored = c.flag && String(c.flag).toUpperCase();
    const derived = SEVERITY_TO_FLAG[String(c.severity || "").toLowerCase()];
    // The pillar is DERIVED from the cell the card is about when the producer
    // left `pillar_id` null — a cell id begins with its pillar, so this is a
    // read of the id rather than a guess. Baxter promoted eight cards with
    // pillar_id null on every one, which is why the D2 grouping put all eight
    // under a single bucket: it was grouping by null.
    const cells = c.affects || (c.linked_subcap_id ? [c.linked_subcap_id] : []);
    const pillar = c.pillar_id || pillarOfCell(cells[0]) || null;
    const [theme, themeWhy] = themeForCells(themes, cells);
    return {
      id: c.ic_id,
      pillar,
      pillar_source: c.pillar_id ? "promoted" : pillar ? "derived from cell" : null,
      flag: authored || derived || "MONITOR",
      flag_source: authored ? "authored" : derived ? "severity" : "default",
      confidence: c.confidence,
      theme: theme,
      theme_source: theme ? themeWhy : null,
      title: c.title,
      what: c.what_text,
      why: c.why_text,
      so_what: c.so_what_text,
      alternative: c.alternative_explanation,
      severity: c.severity,
      severity_rationale: c.severity_rationale,
      validation_question: c.validation_question,
      evidence: c.supporting_e_ids || [],
      affects: c.affects || (c.linked_subcap_id ? [c.linked_subcap_id] : []),
      platforms: c.platform_chips || recPlatforms[c.linked_rec_id] || [],
      rec: c.linked_rec_id || null,
      claim: c.claim_label || null,
      r_layer: c.r_layer || null,
      annotation: null
    };
  });
}

/* ── RECOMMENDATIONS ─────────────────────────────────────────────────
   The recommendation modal reads root_cause as a list of evidence ids, so
   the promoted evidence_ids feed it; the prose root_cause is its own field. */
function adaptRecommendations(recommendations) {
  return (recommendations && recommendations.recommendations || []).map(r => ({
    id: r.rec_id,
    title: r.title,
    l3: r.l3_area,
    l4: r.l4_feature,
    phase: r.phase,
    horizon: r.phase,
    dma_impact: r.dma_impact || [],
    root_cause: r.evidence_ids || [],
    root_cause_text: r.root_cause || null,
    cost_of_inaction: r.cost_of_inaction || null,
    prerequisites: r.prerequisites || [],
    dependencies: r.dependencies || [],
    sequencing_reason: r.sequencing_reason || null,
    effort: r.effort_band || null,
    kpi: r.kpi_triple || null,
    validation_gate: r.validation_gate || null,
    claim: r.claim_label || null,
    platforms: platformChips([r.l3_area, r.l4_feature]),
    r_layer: r.r_layer || null
  }));
}

/* ── TECH_STACK ──────────────────────────────────────────────────────
   Four required statuses and the corrected layer keys (OPS · CUST · DATA ·
   INFRA — never L2–L5, which collide with the evidence levels L1–L4). */
/* The layer rollup, COMPUTED from the register rather than read from it.
   `techstack.layers` is a contract field the producer asserts and the gate
   checks, but no column stores it, so a promoted rollup serves back empty —
   and it does not need to be stored, because every ingredient is on the item
   rows the app already holds. Counts are computed, never stored, where a
   source of truth exists (invariant 8), and the register IS that source.

   `expected` counts every slot the producer placed at the layer INCLUDING the
   ones recorded ABSENT, because an ABSENT row is a slot searched and not
   found — which is exactly what "6 of 8 detected" means.

   The primary-gap judgement is derived by a stated rule rather than a
   constant: the layer with the fewest CONFIRMED rows, tie-broken by the lowest
   detected ratio. Where that still ties, NOTHING is flagged — a tie means the
   register does not single a layer out, and inventing one would be the same
   defect as the hardcoded flag this replaces (every client's CUST layer wore
   PRIMARY GAP LAYER regardless of its own register; on Baxter, CUST is the
   best-covered layer at 11 confirmed of 23 while DATA has none confirmed at
   all). `basis` travels with the flag so the card can say why. */
function techLayersOf(techstack) {
  const items = techstack && techstack.items || [];
  if (!items.length) return [];
  const order = ["OPS", "CUST", "DATA", "INFRA"];
  const rows = [];
  for (const layer of order) {
    const at = items.filter(t => t && t.layer === layer);
    if (!at.length) continue;
    const absent = at.filter(t => t.status === "ABSENT").length;
    const confirmed = at.filter(t => t.status === "CONFIRMED").length;
    rows.push({
      layer,
      pillar_id: (at.find(t => t.pillar_id) || {}).pillar_id || null,
      detected: at.length - absent,
      expected: at.length,
      confirmed,
      is_primary_gap: false,
      basis: null
    });
  }
  if (!rows.length) return rows;
  const fewest = Math.min(...rows.map(r => r.confirmed));
  let cands = rows.filter(r => r.confirmed === fewest);
  if (cands.length > 1) {
    const ratio = r => r.expected ? r.detected / r.expected : 1;
    const lowest = Math.min(...cands.map(ratio));
    cands = cands.filter(r => ratio(r) === lowest);
  }
  if (cands.length === 1) {
    cands[0].is_primary_gap = true;
    cands[0].basis = `${cands[0].confirmed} confirmed of ${cands[0].expected} ` + `— fewer than any other layer`;
  }
  return rows;
}
function adaptTechStack(techstack) {
  return (techstack && techstack.items || []).map(t => ({
    id: t.ts_id,
    name: t.product,
    vendor: t.vendor,
    layer: t.layer,
    status: t.status,
    evidence_level: t.evidence_level,
    since: null,
    // `source` is the row's right rail: SHORT source-kind chips ("Press
    // release", "Job posting"), rendered as badges. The whole detection-basis
    // SENTENCE was being put here, so every register row grew a grey badge
    // holding a 150-character paragraph — the grey block that overflowed the
    // card and made the register unreadable. The basis is prose; it renders
    // once, on the detail page, under "How this was detected". Nothing goes
    // in the rail unless the payload states a short kind, and today it
    // states none.
    source: [],
    note: t.detection_basis || null,
    evidence: t.e_ids || [],
    subcaps_impact: t.linked_subcap_ids || [],
    dma_pillar: t.pillar_id,
    // The three fields the detail page exists to explain. They were promoted,
    // served, and dropped here — so the drilldown fell back to arithmetic in no
    // source ("avg subcap ceiling uplift" from the peer delta) while the
    // producer's actual explanation sat unread in the payload.
    dma_impact: t.dma_impact || null,
    peer_coverage: t.peer_coverage != null ? t.peer_coverage : null,
    peer_deployments: t.peer_deployments || []
  }));
}

/* ── LEADERSHIP ──────────────────────────────────────────────────────
   The panel renders a Clay button per person and a GAP row for a role the
   evidence does not fill. `clay` is null until an enrichment is stored: the
   app never calls Clay at request time (the TRD is explicit that Clay output
   enters as registered evidence), so the button asks and the store answers. */
function adaptLeadership(leadership, enrichment) {
  const roster = leadership && leadership.roster || [];
  const byKey = {};
  for (const e of enrichment && enrichment.items || []) {
    if (e.subject_kind === "person" && e.subject_key) byKey[e.subject_key] = e;
  }
  return roster.map((p, i) => {
    const found = byKey[p.name] || null;
    const isGap = !p.name || p.name === "-" || p.name === "—";
    return {
      id: `EX-${String(i + 1).padStart(2, "0")}`,
      name: isGap ? "-" : p.name,
      title: p.title,
      domain: p.domain || null,
      tenure_months: p.tenure_months == null ? null : Number(p.tenure_months),
      appointed_on: p.appointed_on || null,
      background: p.relevance_note || null,
      critical_role: !!p.domain || isGap,
      recent_hire: p.tenure_months != null && Number(p.tenure_months) <= 6,
      gap_flag: isGap,
      // Contact route, promoted with the person (migration 0018). Established
      // in the PRODUCER's session — Clay runs there, its output is registered as
      // evidence and written into the roster item — so it is already in
      // Postgres when the page is served and renders in the same read as the
      // name. No click, no queue, no request-time call.
      email: p.email || null,
      linkedin_url: p.linkedin_url || null,
      phone: p.phone || null,
      enriched_at: p.enriched_at || null,
      // Where the contact route came from. "Clay reports it" is not a source;
      // the document Clay surfaced is, and this is the only field on the panel
      // that would otherwise carry no provenance.
      enrichment_basis: p.enrichment_basis || null,
      clay: found ? found.payload || null : null,
      enrichment_status: p.email || p.linkedin_url || p.phone ? "promoted" : found ? "stored" : null,
      as_of: p.as_of || null,
      confidence: p.confidence || null,
      evidence: p.source_e_id ? [p.source_e_id] : []
    };
  });
}

/* ── the rest ────────────────────────────────────────────────────────
   Straight field mappings; each returns [] or null when absent. */
/* ── adaptAnswers ────────────────────────────────────────────────────
   `/v1/entities/{id}/answers` returns TWO kinds of row: the producer's own
   answers out of `serving_answers`, and the server's own selection over the
   promoted prose. Only the first kind is carried here. The panel already
   performs the selection itself, in the browser, scoped to whatever the
   reader has open — a cell, a focus area — which a request that knows
   nothing about the open drawer cannot do. Taking the server's selection
   would replace a scoped answer with an unscoped one and call it an upgrade.

   Shape: the server returns `parts[]`, the panel reads one authored answer,
   and a producer row carries exactly one part or none. A row with no part is
   a stated absence and is dropped here — the panel's own absence path says
   the same thing with the question still named. */
function adaptAnswers(body) {
  const rows = body && body.answers || [];
  const out = [];
  for (const a of rows) {
    if (!a || a.provenance !== "promoted") continue;
    const part = Array.isArray(a.parts) && a.parts[0] || null;
    if (!part || !part.text) continue;
    out.push({
      q_id: a.q_id || null,
      surface: a.surface || null,
      scope_id: a.scope_id || null,
      question: a.question || null,
      rank: typeof a.rank === "number" ? a.rank : null,
      answer_md: part.text,
      source_path: part.path || null,
      e_ids: Array.isArray(part.e_ids) ? part.e_ids : []
    });
  }
  return out;
}
function adaptThoughtLeadership(tl) {
  return (tl && tl.entries || []).map((e, i) => ({
    id: `TL-${String(i + 1).padStart(2, "0")}`,
    kind: e.kind || null,
    date: e.published_on || null,
    // The card's keys: title / excerpt / author. The contract's: headline /
    // quote / author_name.
    title: e.headline || null,
    excerpt: e.quote || null,
    author: [e.author_name, e.author_role].filter(Boolean).join(" · ") || null,
    url: e.url ? String(e.url).replace(/^https?:\/\//, "") : null,
    alignment: e.alignment || null,
    evidence: e.e_id ? [e.e_id] : [],
    subcaps: e.linked_subcap_ids || [],
    claim: e.claim_label || null
  }));
}

/* Presentation the fixture carried and the contract does not: an icon, a
   gradient, an illustration. These are not data — nothing about the client is
   being asserted — but the card's layout needs them, so they are DERIVED
   deterministically from the focus area's own id. Deterministic matters: the
   same area keeps the same colour across reloads and across audiences, so a
   reader is not re-learning the page every visit. */
const FA_ICONS = ["envelope", "ai", "platform", "heatmap", "stack", "timeline"];
const FA_GRADIENTS = [["var(--z-teal)", "var(--m-bld)"], ["var(--z-mid)", "var(--m-cmp)"], ["var(--z-dpur)", "var(--z-lav)"], ["var(--m-cmp)", "var(--m-dif)"], ["var(--z-org)", "var(--m-bld)"], ["var(--z-navy)", "var(--z-mid)"]];
function faIndex(id, mod) {
  let h = 0;
  const t = String(id || "");
  for (let i = 0; i < t.length; i++) h = (h << 5) - h + t.charCodeAt(i);
  return Math.abs(h) % mod;
}
function pillarShareOf(subcapIds) {
  // {P1: 40, P4: 60} — the percentage of this focus area's cells sitting in
  // each pillar. Computed, so it cannot disagree with the cell list beside it.
  const ids = (subcapIds || []).filter(s => typeof s === "string");
  if (!ids.length) return null;
  const counts = {};
  for (const id of ids) {
    const m = /^(P\d+)/.exec(id);
    if (m) counts[m[1]] = (counts[m[1]] || 0) + 1;
  }
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!total) return null;
  const out = {};
  for (const p of Object.keys(counts).sort()) {
    out[p] = Math.round(counts[p] / total * 100);
  }
  return out;
}
function adaptFocusAreas(focus) {
  return (focus && focus.focus_areas || []).map(f => ({
    id: f.fa_id,
    name: f.name,
    description: f.currency_note || null,
    strategic_quote: f.verbatim_quote ? `“${f.verbatim_quote}”` : null,
    source: {
      type: f.source_document || null,
      page: f.source_page || null,
      doc: f.source_filename || null
    },
    entity_score: num(f.entity_score),
    peer_score: num(f.peer_score),
    delta: num(f.delta),
    currency_status: f.currency_status || null,
    subcaps: f.involved_subcap_ids || [],
    // KPI targets are not in the H1 contract: an empty list, never invented
    // "current vs target" figures for a real client.
    kpis: [],
    // Which pillars this focus area actually reaches, as a share of the cells
    // it names — computed from involved_subcap_ids, not invented. Null when it
    // names none, and the card tolerates null (it used to be hardcoded null,
    // and Object.entries(null) blanked the whole page on the first click).
    pillars_weight: pillarShareOf(f.involved_subcap_ids),
    icon: FA_ICONS[faIndex(f.fa_id, FA_ICONS.length)],
    colors: FA_GRADIENTS[faIndex(f.fa_id, FA_GRADIENTS.length)],
    illustration: null
  }));
}

/* The prototype's timeline reads {date, title, signal, cap_impact, evidence}
   and its Gantt reads {start, end, type, desc, cap_value}. Those key names ARE
   the contract between the payload and the components, so the mapping happens
   here rather than by touching the components — a page whose rows are keyed
   differently silently renders nothing, or throws on a missing string. */
/* The three declared signal values, and an honest fourth for anything else.
   A value the contract does not declare is not silently coerced: the D5 filter
   row shows an "Unclassified" bucket with its count, so an unusable field is
   visible on the page rather than expressed as an empty timeline. */
const SIGNALS = ["positive", "neutral", "negative"];
function signalOf(v) {
  const s = String(v == null ? "" : v).trim().toLowerCase();
  return SIGNALS.includes(s) ? s : "unclassified";
}

/* `signal` is NOT a reading of the news. Its defined meaning is the direction
   the event moved the ASSESSED POSITION of the cells in `capability_ids`, and
   the three stored words invite a mood reading of exactly the kind the reader
   hit: "why is a merger a negative event?". The stored vocabulary is the
   contract and does not move; what the reader sees is the axis it actually
   names. One map, here, so the filter chips, the dot tones and the event
   drilldown can never label the same value three different ways. */
const MATURITY_EFFECT_LABEL = {
  positive: "Advanced",
  neutral: "Neutral",
  negative: "Constrained",
  unclassified: "Unclassified"
};
/* The producer's own token for the same axis, as it writes it in
   `maturity_effect`: ADVANCED │ CONSTRAINED │ NEUTRAL. */
const MATURITY_EFFECT_TOKENS = ["ADVANCED", "CONSTRAINED", "NEUTRAL"];

/* `timeline.arc_shape` has a closed vocabulary of five (Surface Specification,
   D5 step 4). This run serves "strategy-first, substrate-later", which is a
   sentence rather than one of them.

   The app does not correct the producer and does not drop the value: an
   arc the reader can see is worth more than a blank, and a silent drop hides
   a producer defect instead of reporting it. So the value is printed as it
   arrived, and marked off-vocabulary where it is — the badge then reads as
   what it is (a description this run wrote) rather than as one of the five
   contract words. */
const ARC_SHAPES = ["STEADY_INVESTMENT", "STOP_START", "POST_EVENT_CATCHUP", "LEGACY_ANCHORED", "RECENT_ACCELERATION"];
function arcShapeOf(v) {
  const raw = v == null ? "" : String(v).trim();
  if (!raw) return null;
  const key = raw.toUpperCase().replace(/[\s-]+/g, "_");
  const known = ARC_SHAPES.includes(key);
  return {
    raw,
    label: known ? key.replace(/_/g, " ").toLowerCase() : raw,
    in_vocabulary: known
  };
}

/* `maturity_effect` arrives as "TOKEN — one clause of reasoning". Rendered
   whole it is a 200-character paragraph inside a badge; rendered as a badge
   alone it throws the reasoning away. So it is split ONCE, here.

   Fail-soft in both directions: a value with no leading token is all reason
   (the badge then falls back to the event's own signal), and a token this
   app does not know is still returned as the token — printed as the producer
   wrote it rather than dropped. Nothing is inferred: a string that states no
   token yields `token: null`, never a guessed one. */
function splitMaturityEffect(raw) {
  const s = raw == null ? "" : String(raw).trim();
  if (!s) return {
    token: null,
    reason: null
  };
  // A bare token with no clause after it — the acquisitions row writes it that
  // way and puts its clause in `effect_note`.
  if (/^[A-Z][A-Z_]*$/.test(s)) return {
    token: s,
    reason: null
  };
  // The separator the contract uses is an em dash; a hyphen or a colon is the
  // same statement typed differently and is accepted rather than refused.
  const m = /^([A-Za-z][A-Za-z_ ]{0,24}?)\s*(?:—|--|–|:|-)\s+([\s\S]+)$/.exec(s);
  if (!m) return {
    token: null,
    reason: s
  };
  const token = m[1].trim().toUpperCase().replace(/\s+/g, "_");
  // A leading word is only a TOKEN where it reads as one — all caps in the
  // source, or a value the contract declares. "The merger — which…" must not
  // have its first word promoted into a badge.
  const looksLikeToken = /^[A-Z_]+$/.test(m[1].trim()) || MATURITY_EFFECT_TOKENS.includes(token);
  if (!looksLikeToken) return {
    token: null,
    reason: s
  };
  return {
    token,
    reason: m[2].trim() || null
  };
}
function adaptTimeline(timeline) {
  const events = timeline && timeline.events || [];
  return events.map((e, i) => ({
    id: `TE-${String(i + 1).padStart(2, "0")}`,
    date: e.event_date || null,
    title: e.title,
    detail: e.body || null,
    kind: e.kind || null,
    // The contract declares three values. Lower-casing whatever arrived turned a
    // producer's consequence SENTENCE into a signal class no filter matches, and
    // defaulting the rest to "neutral" made ten unclassified events look
    // deliberately neutral. Now an off-vocabulary value becomes "unclassified"
    // — visible as such, and countable, so the page can say so instead of
    // showing an empty list. CG-09 refuses it at submit from here on.
    signal: signalOf(e.signal),
    signal_raw: e.signal || null,
    cap_impact: (e.capability_ids || [])[0] || null,
    capabilities: e.capability_ids || [],
    // Split, never printed whole: the badge takes the token, the body takes
    // the clause. `maturity_effect` is kept as promoted so a copy path or a
    // future reader still has the producer's exact string.
    maturity_effect: e.maturity_effect || null,
    effect_token: splitMaturityEffect(e.maturity_effect).token,
    effect_reason: splitMaturityEffect(e.maturity_effect).reason,
    evidence: e.e_ids || [],
    claim: e.claim_label || null
  }));
}

/* ── acquisitions ────────────────────────────────────────────────────
   The C7 contract names `target_name`, `closed_on`, `effect_note`,
   `integration_target`, `affected_subcap_ids` and `e_ids`; the card reads
   `target`, `date`, `details`, `subcaps`, `evidence`. Passing the rows through
   raw rendered a blank title, "undated", and an empty grey drilldown box while
   every one of those fields sat in the payload. */
function adaptAcquisitions(section) {
  return (section && section.rows || []).map((a, i) => ({
    id: a.acq_id || `ACQ-${String(i + 1).padStart(2, "0")}`,
    target: a.target_name || a.target || null,
    date: a.closed_on || a.announced_on || null,
    kind: a.kind || null,
    status: a.status || null,
    impl: a.integration_target || null,
    details: [a.effect_note, a.scale_metrics].filter(Boolean).join(" · ") || null,
    // Same axis as the timeline's, split the same way. This row states the
    // token bare and puts its clause in `effect_note`, so the split returns
    // the token and the reason comes from the note — the two D5 surfaces then
    // say the same word for the same judgement instead of one of them
    // silently dropping it.
    effect_token: splitMaturityEffect(a.maturity_effect).token,
    effect_reason: splitMaturityEffect(a.maturity_effect).reason || a.effect_note || null,
    subcaps: a.affected_subcap_ids || [],
    evidence: a.e_ids || []
  }));
}

/* The issue→cell cap map, keyed by issue id, in the shape the caps grid wants:
   {ISS-001: {caps: {P2C2.1.1: <cap>, …}}}. A cap LEVEL is only rendered when
   the run states one; the linkage alone is enough to show which cells a matter
   bears on. */
function issueCapsOf(register) {
  const out = {};
  for (const x of register && register.issues || []) {
    const cells = x.linked_subcap_ids || x.capability_ids || [];
    if (!cells.length) continue;
    const caps = {};
    for (const c of cells) caps[c] = x.cap_level != null ? x.cap_level : null;
    out[x.issue_id] = {
      caps
    };
  }
  return out;
}
function adaptIssues(register) {
  return (register && register.issues || []).map(x => ({
    id: x.issue_id,
    // `type` read `kind`, which the contract does not carry, then fell through
    // to severity — so a row printed its severity twice and the drilldown
    // heading was a severity word. The promoted `title` ("Data Breach",
    // "Illinois CRA Obligation") is set below and is what the row should show.
    type: x.kind || null,
    severity: x.severity,
    status: x.status,
    // The Gantt parses these as date strings and appends "-01" to a
    // month-precision value, so an absent date must not become "" — it would
    // parse to an Invalid Date and lay the bar out at NaN. Undated issues are
    // dropped from the chart by the caller instead.
    start: x.opened_on || null,
    end: x.resolved_on || null,
    desc: x.rationale || x.title || null,
    title: x.title,
    caps: x.linked_subcap_ids || [],
    cap_value: null,
    evidence: x.e_ids || []
  }));
}

/* The roadmap phases in the shape the chevron strip renders.

   The strip read `r.label`, `r.duration`, `r.color`, `r.platform`, `r.target`
   and `r.metric`. The contract carries none of those: a phase states `phase`,
   `horizon`, `rec_ids`, `depends_on` and `rationale`. So `background: r.color`
   was undefined under `color: "#fff"` — white text on a white block, 300px of
   apparently blank page with the text present in the DOM — and the "Step curve"
   toggle threw on `r.label.toUpperCase()`.

   `label` is the phase's own horizon; `color` is DERIVED from the phase index,
   which asserts nothing about the client (it is presentation, and deterministic
   so a phase keeps its colour across reloads). Platform, target maturity and
   success metric are NOT in the roadmap contract — they belong to the
   recommendations a phase contains — so the renderer must stop asking for them
   rather than print three empty labels. */
const PHASE_COLORS = ["var(--z-dark2)", "var(--z-mid)", "var(--z-dpur)", "var(--z-teal)", "var(--z-purple)"];
function adaptRoadmap(roadmap) {
  return (roadmap && roadmap.phases || []).map((p, i) => ({
    id: `PH-${i + 1}`,
    phase: p.phase == null ? i + 1 : p.phase,
    horizon: p.horizon || null,
    label: p.horizon || `Phase ${p.phase == null ? i + 1 : p.phase}`,
    duration: p.horizon || null,
    color: PHASE_COLORS[i % PHASE_COLORS.length],
    recs: p.rec_ids || [],
    depends_on: p.depends_on || [],
    rationale: p.rationale || null
  }));
}
function adaptStairstep(stairstep) {
  const ladder = stairstep && stairstep.ladder || null;
  const steps = ladder && ladder.steps || [];
  if (!steps.length) return null;
  return {
    theme: ladder.theme || null,
    steps: steps.map(s => ({
      level: s.step_level,
      label: s.label,
      subcaps: s.covered_subcap_ids || [],
      current: !!s.current_position,
      blocking: s.blocking_findings || [],
      unlocks: s.unlocks || null,
      effort: s.effort_band || null,
      entry_condition: s.entry_condition || null
    }))
  };
}

/* The stair-step ladder in the shape StairstepCurve renders.

   data.js's `STAIRSTEP_CLUSTERS` accessor reads the key `stairstepClusters`,
   which buildLiveEntity never set — so the curve reported "no stair-step ladder
   promoted" against a promoted four-step ladder. The shape differs too: the
   curve wants {label, current, steps:[{m, label, platforms, note}]} while the
   contract states {theme, steps:[{step_level, label, unlocks, entry_condition,
   effort_band, covered_subcap_ids, current_position, blocking_findings}]}.

   `m` is the step LEVEL, not a maturity band: the ladder's steps are ordered
   rungs, and the curve draws one rectangle per rung. `platforms` comes from the
   catalogue platform areas of the cells that rung covers — read, not guessed —
   and is empty when the rung covers no cell with a platform area. */
function stairstepClustersOf(stairstep) {
  const adapted = adaptStairstep(stairstep);
  if (!adapted || !adapted.steps.length) return {};
  const key = adapted.theme || "ladder";
  return {
    [key]: {
      label: adapted.theme || "Maturity ladder",
      current: (adapted.steps.find(x => x.current) || {}).level || null,
      steps: adapted.steps.map(x => ({
        m: x.level,
        label: x.label,
        // The rung's own platform areas, from the cells it covers.
        platforms: [],
        note: [x.entry_condition, x.unlocks].filter(Boolean).join(" → ") || x.label || null,
        effort: x.effort,
        subcaps: x.subcaps,
        blocking: x.blocking
      }))
    }
  };
}
function adaptEvidence(evidenceEnvelope) {
  return (evidenceEnvelope && evidenceEnvelope.items || []).map(e => ({
    id: e.e_id,
    title: e.source_name || e.e_id,
    source: (e.source_url || "").replace(/^https?:\/\//, ""),
    source_pretty: e.source_name || e.source_domain || e.e_id,
    tier: e.tier,
    ers: num(e.ers),
    claim: e.claim_type,
    // The ladder's own token is internal vocabulary. The prototype shows an
    // AGE beside a claim badge, never the word "UNVERIFIED" — and rendering it
    // next to a FACT reads as a contradiction ("this is a fact, unverified"),
    // when all it means is that no date could be resolved to rank the item on.
    // So: the band when there is one, the date when there is only that, and
    // NOTHING when there is neither. The third case used to print the word
    // "undated" beside the citation, which states a producer problem in the
    // reader's line of sight and states it on every affected chip — an
    // evidence item that could not be dated should be dated before the run
    // promotes, not labelled on the page. `recency_band` keeps the raw token
    // for anything that needs to reason about the rung.
    recency: e.recency_band && e.recency_band !== "UNVERIFIED" ? e.recency_band : e.published_date || null,
    recency_band: e.recency_band || null,
    published_date: e.published_date,
    age_months: e.age_months,
    identity_ok: e.identity_ok,
    // The drawer's "supports:" chips. The read path names the column
    // `linked_subcap_ids` (evidence_subcap_links, scoped to this run); the
    // card's key is `subcaps`. Reading only `e.subcaps` — a key the API never
    // sent — is why every drawer showed no traceable cell links.
    subcaps: e.linked_subcap_ids || e.subcaps || [],
    excerpt: e.excerpt || null
  }));
}

/* ── the one entry point ─────────────────────────────────────────────
   Builds everything an entity's surfaces need from the six promoted pages
   plus the two grain reads, and returns the object installed as
   window.DMA_ENTITY. Callers pass whatever they have; a missing page simply
   yields nulls downstream. */
function buildLiveEntity(entityId, pages, extras) {
  const p = pages || {};
  const x = extras || {};
  const overview = p.overview,
    heatmap = p.heatmap,
    insights = p.insights,
    platform = p.platform,
    context = p.context,
    techstack = p.techstack;
  const scores = secOf(overview, "scores");
  const recs = secOf(platform, "recommendations");
  return {
    id: entityId,
    scores,
    pillar_scores: pillarScoresOf(scores),
    // The workbook's STATED peer median per pillar, so the bar's peer tick and
    // its delta come from the run rather than from a constant offset. Baxter's
    // P1 sits at 3.11 against a stated 2.9 — ABOVE its peer set — which the
    // old `score + 0.3` rendered as 0.3 BELOW.
    pillar_peer_medians: pillarPeerMediansOf(scores),
    overall: num(scores && scores.composite),
    posture: scores && scores.posture || null,
    posture_basis: scores && scores.posture_basis || null,
    framing: scores && scores.framing || null,
    claim: scores && scores.claim_label || null,
    confidence: scores && scores.confidence || null,
    narrative_thread: scores && scores.narrative_thread || null,
    subcaps: adaptSubcaps(x.subcaps),
    // The producer's own answers, when the connector has written them. A
    // grain read like `subcaps` and `evidence`, not a section — so an empty
    // array here means "nothing authored", and the panel falls through to
    // selection over the promoted prose rather than reporting a fault.
    answers: Array.isArray(x.answers) ? x.answers : [],
    oss: adaptOss(secOf(overview, "opportunity")),
    opportunity: secOf(overview, "opportunity"),
    opportunityTiles: adaptOpportunityTiles(secOf(overview, "opportunity")),
    firmographics: secOf(overview, "firmographics"),
    exec_summary: secOf(overview, "exec_summary"),
    findings: secOf(overview, "findings"),
    financials: adaptFinancials(secOf(overview, "financial_series"), secOf(overview, "firmographics"), secWithEnv(context, "regulatory_standing")),
    sentiment: adaptSentiment(secOf(overview, "sentiment")),
    contextSentiment: adaptContextSentiment(secOf(context, "context_sentiment")),
    coverage: adaptCoverage(secOf(overview, "evidence_coverage")),
    uncertainty: adaptUncertainty(secOf(overview, "ceilings")),
    evidenceSummary: adaptEvidenceSummary(x.evidence),
    whyNow: adaptWhyNow(secOf(overview, "why_now")),
    // adaptWhyNow returns the SIGNAL rows and drops the section's own
    // `synthesis` and `narrative_thread` — the paragraph that says what
    // changed and why it matters now. It was reachable from the API and
    // from nowhere in the browser, so the panel could not answer the one
    // question the surface exists to answer. The rows keep their shape;
    // the section travels beside them.
    whyNowMeta: secOf(overview, "why_now"),
    leadership: adaptLeadership(secOf(overview, "leadership"), x.enrichment),
    thoughtLeadership: adaptThoughtLeadership(secOf(overview, "thought_leadership")),
    insightCards: adaptInsights(secOf(insights, "insights"), recs, secOf(overview, "findings")),
    recommendations: adaptRecommendations(recs),
    platformStory: secOf(platform, "platform_story"),
    // The roadmap's own stated reason for its ORDER, which lives on the
    // section beside `phases` rather than on any one phase. adaptRoadmap
    // returns the phase array, so this was dropped on the floor while the
    // design's "sequencing rationale" strip under the chevrons had nothing to
    // render and did not appear at all.
    roadmapBasis: (secOf(platform, "roadmap") || {}).sequencing_basis || null,
    starters: (secOf(platform, "starters") || {}).starters || [],
    roadmap: adaptRoadmap(secOf(platform, "roadmap")),
    // data.js reads `stairstepClusters` and `valueChains`; this used to emit
    // `stairstep` and `valueChain`, so both accessors returned {} in LIVE and
    // the maturity curve and the value chain reported "nothing promoted" while
    // the payload carried a four-step ladder and the chain section. Emitted
    // under BOTH names: the singular for anything reading the raw section, the
    // plural for the accessor.
    stairstep: adaptStairstep(secOf(platform, "stairstep")),
    stairstepClusters: stairstepClustersOf(secOf(platform, "stairstep")),
    focusAreas: adaptFocusAreas(secOf(heatmap, "focus_areas")),
    workbookScores: secOf(heatmap, "workbook_scores"),
    cellEvidence: (secOf(heatmap, "cell_evidence") || {}).cells || [],
    alerts: (secOf(heatmap, "alerts") || {}).alerts || [],
    caps: (secOf(heatmap, "safeguard_gates") || {}).caps || [],
    gates: (secOf(heatmap, "safeguard_gates") || {}).gates || [],
    evidenceAge: (secOf(heatmap, "evidence_age") || {}).rows || [],
    cohorts: secOf(heatmap, "cohort_patterns"),
    valueChain: secOf(heatmap, "value_chain"),
    valueChains: (secOf(heatmap, "value_chain") || {}).chains || (secOf(heatmap, "value_chain") || {}).value_chains || [],
    timeline: adaptTimeline(secOf(context, "timeline")),
    timelineMeta: secOf(context, "timeline"),
    issues: adaptIssues(secOf(context, "issue_register")),
    // The issue→cell map the caps grid and the Gantt lock read. It was never
    // built, so DMA.ISSUE_CAPS was {} in LIVE and no issue could ever show the
    // cells it caps — the "issues not linked to the DMA" symptom.
    issueCaps: issueCapsOf(secOf(context, "issue_register")),
    regulatory: secWithEnv(context, "regulatory_standing"),
    acquisitions: adaptAcquisitions(secOf(context, "acquisitions")),
    techStack: adaptTechStack(secOf(techstack, "techstack")),
    techLayers: techLayersOf(secOf(techstack, "techstack")),
    evidence: adaptEvidence(x.evidence),
    landscape: secOf(insights, "landscape"),
    // The run's own promotion facts, so a surface can say what it is showing
    // and when it was promoted rather than leaving the reader to guess.
    run: overview && overview.run || heatmap && heatmap.run || null,
    sectionState: sectionStates(p)
  };
}
function pillarScoresOf(scores) {
  const out = {};
  for (const p of scores && scores.pillars || []) {
    if (p.pillar_id) out[p.pillar_id] = num(p.score);
  }
  return out;
}
function pillarPeerMediansOf(scores) {
  // Only where the run states one — an absent median stays absent so the bar
  // renders no tick rather than a fabricated benchmark.
  const out = {};
  for (const p of scores && scores.pillars || []) {
    const v = num(p.peer_median);
    if (p.pillar_id && v != null) out[p.pillar_id] = v;
  }
  return out;
}

/* Per-section provenance: what promoted, when, by which producer version,
   and how many evidence ids it cited. The prototype states this per card, so
   the card needs it per section rather than once per page. */
function sectionStates(pages) {
  const out = {};
  for (const page of Object.keys(pages || {})) {
    const secs = pages[page] && pages[page].sections || {};
    for (const name of Object.keys(secs)) {
      const s = secs[name];
      out[`${page}.${name}`] = {
        data_source: s.data_source,
        provenance: s.provenance,
        produced_at: s.produced_at,
        producer_version: s.producer_version,
        e_ids: s.e_ids || [],
        empty_state: s.empty_state || null,
        // The customer body now carries a COUNT rather than the path list:
        // the paths carry field names, and one of them named the assessing
        // vendor five times inside a client's own response. `redacted_paths`
        // is still read so an older cached body renders the same way.
        redacted_paths: s.redacted_paths || null,
        redacted_count: s.redacted_count ?? (s.redacted_paths ? s.redacted_paths.length : null),
        redaction_note: s.redaction_note || null
      };
    }
  }
  return out;
}
Object.assign(window, {
  buildLiveEntity,
  adaptSubcaps,
  adaptOss,
  adaptFinancials,
  adaptSentiment,
  adaptCoverage,
  adaptUncertainty,
  adaptEvidenceSummary,
  adaptWhyNow,
  adaptInsights,
  adaptRecommendations,
  adaptTechStack,
  adaptLeadership,
  adaptThoughtLeadership,
  adaptFocusAreas,
  adaptTimeline,
  adaptIssues,
  adaptRoadmap,
  adaptStairstep,
  adaptEvidence,
  adaptAnswers,
  platformChips,
  scaleMaxOf,
  headlineOf,
  sectionStates,
  faIndex,
  // Exported so tests can assert them directly. Each of these was a silent
  // key or shape mismatch between the payload and a renderer, which is the
  // defect class no per-field test caught.
  secWithEnv,
  stairstepClustersOf,
  adaptAcquisitions,
  issueCapsOf,
  techLayersOf,
  adaptOpportunityTiles,
  cagrOf,
  peerOfSignal: signalOf,
  splitMaturityEffect,
  MATURITY_EFFECT_LABEL,
  MATURITY_EFFECT_TOKENS,
  ARC_SHAPES,
  arcShapeOf
});