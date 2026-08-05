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
    const key = PLATFORM_ALIASES[String(t.platform || "").toLowerCase()] || platformChips([t.platform])[0] || t.platform;
    const v = num(t.composite);
    if (key && v !== null) out[key] = Math.round(v);
  }
  return out;
}

/* ── financialsFor ───────────────────────────────────────────────────
   The prototype's card draws one bar per fiscal period with the value above
   it and a footer of regulator · footprint · branches · FTE. Periods come
   from the promoted series; the footer figures come from firmographics,
   which is where they are stated. */
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
    scale: scaleMaxOf(b.scale),
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
    scale: scaleMaxOf(b.scale),
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
function headlineOf(text) {
  if (!text) return null;
  const t = String(text).trim();
  const cut = t.search(/[—.;]/);
  const head = cut > 12 ? t.slice(0, cut) : t;
  return head.length > 72 ? `${head.slice(0, 69).trimEnd()}…` : head;
}

/* ── INSIGHT_CARDS ───────────────────────────────────────────────────
   The prototype's `.ic` card and the Act now / Plan next / Watch clustering.
   `flag` drives the card's left border and the priority tier; where the
   producer authored one it is used, and until the schema carries it the
   severity the contract DOES define stands in — mapped, and recorded as
   derived so the surface can say so. */
const SEVERITY_TO_FLAG = {
  critical: "CRITICAL",
  high: "OPPORTUNITY",
  medium: "MONITOR",
  low: "MONITOR"
};
function adaptInsights(insights, recommendations) {
  const cards = insights && insights.cards || [];
  const recPlatforms = {};
  for (const r of recommendations && recommendations.recommendations || []) {
    recPlatforms[r.rec_id] = platformChips([r.l3_area, r.l4_feature]);
  }
  return cards.map(c => {
    const authored = c.flag && String(c.flag).toUpperCase();
    const derived = SEVERITY_TO_FLAG[String(c.severity || "").toLowerCase()];
    return {
      id: c.ic_id,
      pillar: c.pillar_id,
      flag: authored || derived || "MONITOR",
      flag_source: authored ? "authored" : derived ? "severity" : "default",
      confidence: c.confidence,
      theme: c.theme || null,
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
function adaptTechStack(techstack) {
  return (techstack && techstack.items || []).map(t => ({
    id: t.ts_id,
    name: t.product,
    vendor: t.vendor,
    layer: t.layer,
    status: t.status,
    evidence_level: t.evidence_level,
    since: null,
    source: t.detection_basis ? [t.detection_basis] : [],
    note: t.detection_basis || null,
    evidence: t.e_ids || [],
    subcaps_impact: t.linked_subcap_ids || [],
    dma_pillar: t.pillar_id,
    peer_coverage: null
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
      clay: found ? found.payload || null : null,
      enrichment_status: found ? "stored" : null,
      as_of: p.as_of || null,
      confidence: p.confidence || null,
      evidence: p.source_e_id ? [p.source_e_id] : []
    };
  });
}

/* ── the rest ────────────────────────────────────────────────────────
   Straight field mappings; each returns [] or null when absent. */
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
    pillars_weight: null,
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
function adaptTimeline(timeline) {
  const events = timeline && timeline.events || [];
  return events.map((e, i) => ({
    id: `TE-${String(i + 1).padStart(2, "0")}`,
    date: e.event_date || null,
    title: e.title,
    detail: e.body || null,
    kind: e.kind || null,
    // The prototype colours a dot by signal; the contract's values are the
    // producer's own words, lower-cased for the class name and nothing more.
    signal: e.signal ? String(e.signal).toLowerCase() : "neutral",
    cap_impact: (e.capability_ids || [])[0] || null,
    capabilities: e.capability_ids || [],
    maturity_effect: e.maturity_effect || null,
    evidence: e.e_ids || [],
    claim: e.claim_label || null
  }));
}
function adaptIssues(register) {
  return (register && register.issues || []).map(x => ({
    id: x.issue_id,
    type: x.kind || x.severity || "Issue",
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
function adaptRoadmap(roadmap) {
  return (roadmap && roadmap.phases || []).map((p, i) => ({
    id: `PH-${i + 1}`,
    phase: p.phase,
    horizon: p.horizon,
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
function adaptEvidence(evidenceEnvelope) {
  return (evidenceEnvelope && evidenceEnvelope.items || []).map(e => ({
    id: e.e_id,
    title: e.source_name || e.e_id,
    source: (e.source_url || "").replace(/^https?:\/\//, ""),
    source_pretty: e.source_name || e.source_domain || e.e_id,
    tier: e.tier,
    ers: num(e.ers),
    claim: e.claim_type,
    recency: e.recency_band || (e.published_date ? e.published_date : "UNVERIFIED"),
    published_date: e.published_date,
    age_months: e.age_months,
    identity_ok: e.identity_ok,
    subcaps: e.subcaps || [],
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
    overall: num(scores && scores.composite),
    posture: scores && scores.posture || null,
    framing: scores && scores.framing || null,
    claim: scores && scores.claim_label || null,
    confidence: scores && scores.confidence || null,
    narrative_thread: scores && scores.narrative_thread || null,
    subcaps: adaptSubcaps(x.subcaps),
    oss: adaptOss(secOf(overview, "opportunity")),
    opportunity: secOf(overview, "opportunity"),
    firmographics: secOf(overview, "firmographics"),
    exec_summary: secOf(overview, "exec_summary"),
    findings: secOf(overview, "findings"),
    financials: adaptFinancials(secOf(overview, "financial_series"), secOf(overview, "firmographics"), secOf(context, "regulatory_standing")),
    sentiment: adaptSentiment(secOf(overview, "sentiment")),
    coverage: adaptCoverage(secOf(overview, "evidence_coverage")),
    uncertainty: adaptUncertainty(secOf(overview, "ceilings")),
    evidenceSummary: adaptEvidenceSummary(x.evidence),
    whyNow: adaptWhyNow(secOf(overview, "why_now")),
    leadership: adaptLeadership(secOf(overview, "leadership"), x.enrichment),
    thoughtLeadership: adaptThoughtLeadership(secOf(overview, "thought_leadership")),
    insightCards: adaptInsights(secOf(insights, "insights"), recs),
    recommendations: adaptRecommendations(recs),
    platformStory: secOf(platform, "platform_story"),
    starters: (secOf(platform, "starters") || {}).starters || [],
    roadmap: adaptRoadmap(secOf(platform, "roadmap")),
    stairstep: adaptStairstep(secOf(platform, "stairstep")),
    focusAreas: adaptFocusAreas(secOf(heatmap, "focus_areas")),
    workbookScores: secOf(heatmap, "workbook_scores"),
    cellEvidence: (secOf(heatmap, "cell_evidence") || {}).cells || [],
    alerts: (secOf(heatmap, "alerts") || {}).alerts || [],
    caps: (secOf(heatmap, "safeguard_gates") || {}).caps || [],
    gates: (secOf(heatmap, "safeguard_gates") || {}).gates || [],
    evidenceAge: (secOf(heatmap, "evidence_age") || {}).rows || [],
    cohorts: secOf(heatmap, "cohort_patterns"),
    valueChain: secOf(heatmap, "value_chain"),
    timeline: adaptTimeline(secOf(context, "timeline")),
    timelineMeta: secOf(context, "timeline"),
    issues: adaptIssues(secOf(context, "issue_register")),
    regulatory: secOf(context, "regulatory_standing"),
    acquisitions: (secOf(context, "acquisitions") || {}).rows || [],
    techStack: adaptTechStack(secOf(techstack, "techstack")),
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
        redacted_paths: s.redacted_paths || null
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
  platformChips,
  scaleMaxOf,
  headlineOf,
  sectionStates,
  faIndex
});