/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Data module (deployable / data-empty)
   ═══════════════════════════════════════════════════════════════════════

   This module publishes window.DMA. It KEEPS the V7 framework spine
   (PILLARS, PLATFORMS, CATEGORIES, VALUE_CHAINS, helpers, etc.) so the
   pages can render their structural chrome, but EMPTIES every client-
   and run-scoped collection so the app deploys without mock content.

   Pages will render their natural empty states until each collection
   below is wired to the corresponding backend endpoint (see the
   `WIRING_NEEDS` map at the bottom — a single source of truth for what
   surfaces are awaiting which API).

   Source-of-truth for the framework spine: the prototype
   `standalone-src/src/data.js` shipped by design.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  /* ── Maturity color helpers (pure) ─────────────────────────────────
     A score is "uncalculated" when null/undefined/NaN OR exactly 0 (a
     score of 0 doesn't exist on the M1..M5 ladder — the minimum is 1.0
     for "Activating"). All three branches return the same muted styling
     + "Uncalculated" label so the UI never lies about a fabricated band.
  */
  function isUncalculated(s) {
    return s == null || typeof s !== "number" || isNaN(s) || s <= 0;
  }
  function maturityClass(s) {
    if (isUncalculated(s)) return "b-muted";
    if (s < 2) return "b-act";
    if (s < 3) return "b-bld";
    if (s < 4) return "b-cmp";
    return "b-dif";
  }
  function maturityHex(s) {
    if (isUncalculated(s)) return "#E5E7EB";
    if (s < 2) return "#FFCB99";
    if (s < 3) return "#62D7B8";
    if (s < 4) return "#27BBAF";
    return "#139F94";
  }
  function maturityLabel(s) {
    if (isUncalculated(s)) return "Uncalculated";
    if (s < 2) return "Activating";
    if (s < 3) return "Building";
    if (s < 4) return "Competing";
    return "Differentiating";
  }
  function freshnessOf(date) {
    if (!date) return { tone: "muted", label: "—", months: null };
    const now = new Date();
    const d = new Date(date);
    const months = (now - d) / (1000 * 60 * 60 * 24 * 30.4);
    if (months > 12) return { tone: "below", label: "Stale", months: Math.round(months) };
    if (months > 6)  return { tone: "warn",  label: "Aging", months: Math.round(months) };
    return { tone: "ok", label: "Current", months: Math.round(months) };
  }
  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }
  function round1(n) { return Math.round(n * 10) / 10; }

  /* ══════════════════════════════════════════════════════════════════
     V7 FRAMEWORK SPINE (static — same across all runs)
     ══════════════════════════════════════════════════════════════════
     These constants come from the V7.0 Comprehensive Capability Mapping
     and the Zennify platform/data-product catalogue. They are NOT run-
     scoped — every page reads them as the structural backbone (pillar
     bars, heatmap rows/cols, platform cards, value-chain pivots).
  */
  const PILLARS = [
    { id: "P1", name: "Strategy & Governance",  short: "Strategy" },
    { id: "P2", name: "Customer Experience",    short: "Customer" },
    { id: "P3", name: "Operations & Workflow",  short: "Operations" },
    { id: "P4", name: "Data & Technology",      short: "Data & Tech" },
  ];

  const PLATFORMS = [
    { id: "SF",    name: "Salesforce", short: "SF",  features: "Agentforce · Data Cloud · FSC · CRMA · Marketing · Platform", color: "#00A1E0" },
    { id: "DB",    name: "Databricks", short: "DB",  features: "Mosaic AI · Agent Bricks · Lakeflow",                          color: "#FF3621" },
    { id: "TBL",   name: "Tableau",    short: "TBL", features: "Embedded · Next · Pulse",                                       color: "#1F4E79" },
    { id: "TW",    name: "Twilio",     short: "TW",  features: "Engage · Conversations",                                        color: "#F22F46" },
    { id: "nCino", name: "nCino",      short: "nC",  features: "Workflow Engine · Document Manager",                            color: "#0067A0" },
  ];

  const CATEGORIES = [
    { id: "P1C1", pillar: "P1", name: "Digital Strategy",            weight: .28 },
    { id: "P1C2", pillar: "P1", name: "Governance & Risk",           weight: .22 },
    { id: "P1C3", pillar: "P1", name: "Innovation Operating Model",  weight: .18 },
    { id: "P1C4", pillar: "P1", name: "Talent & Culture",            weight: .16 },
    { id: "P2C1", pillar: "P2", name: "Channel Experience",          weight: .26 },
    { id: "P2C2", pillar: "P2", name: "Digital Service Model",       weight: .24 },
    { id: "P2C3", pillar: "P2", name: "Customer Journey",            weight: .26 },
    { id: "P2C4", pillar: "P2", name: "Personalisation",             weight: .14 },
    { id: "P3C1", pillar: "P3", name: "Workflow Automation",         weight: .28 },
    { id: "P3C2", pillar: "P3", name: "Loan Origination",            weight: .24 },
    { id: "P3C3", pillar: "P3", name: "Servicing Efficiency",        weight: .20 },
    { id: "P3C4", pillar: "P3", name: "Process Intelligence",        weight: .18 },
    { id: "P4C1", pillar: "P4", name: "Data Foundation",             weight: .32 },
    { id: "P4C2", pillar: "P4", name: "Analytics & Insight",         weight: .22 },
    { id: "P4C3", pillar: "P4", name: "AI & Decisioning",            weight: .22 },
    { id: "P4C4", pillar: "P4", name: "Architecture & Cloud",        weight: .18 },
    { id: "P4C5", pillar: "P4", name: "Security & Trust",            weight: .14 },
  ];

  const VALUE_CHAINS = [
    { id: "VC1", name: "Digital Account Opening",     subcaps: ["P2C3.1.1","P2C1.1.1","P4C1.3.1","P4C5.1.1"] },
    { id: "VC2", name: "Loan Origination",             subcaps: ["P3C2.1.1","P3C2.2.1","P3C2.3.1","P4C1.5.1"] },
    { id: "VC3", name: "Member Servicing",             subcaps: ["P2C2.1.1","P2C2.2.1","P3C3.1.1","P3C3.2.1"] },
    { id: "VC4", name: "Cross-Sell & Marketing",       subcaps: ["P2C4.1.1","P2C4.2.1","P4C3.1.1"] },
    { id: "VC5", name: "Risk & Compliance Operations", subcaps: ["P1C2.1.1","P1C2.2.1","P4C5.2.1"] },
    { id: "VC6", name: "Data-Driven Decisioning",      subcaps: ["P4C1.3.1","P4C2.2.1","P4C3.2.1"] },
  ];

  const EVIDENCE_TIERS = {
    T1: { label: "Audited / regulatory", note: "10-K, FRB orders, audited financials", weight: 1.0 },
    T2: { label: "Issuer / company source", note: "earnings calls, annual reports, press releases", weight: 0.9 },
    T3: { label: "Analyst & research firm", note: "Forrester, Gartner, McKinsey", weight: 0.85 },
    T4: { label: "Verified executive disclosure", note: "named-author LinkedIn, conference keynote", weight: 0.7 },
    T5: { label: "Vendor confirmation", note: "case study, partner press release", weight: 0.65 },
    T6: { label: "Employee / customer signal", note: "Glassdoor, Trustpilot, app store reviews", weight: 0.55 },
    T7: { label: "Hiring & job market", note: "LinkedIn, Indeed job posts", weight: 0.55 },
    T8: { label: "Open social / community", note: "Reddit, Twitter, forums", weight: 0.4 },
  };

  const PEER_SETS = {
    REGIONAL_BANK: { label: "Regional banks (assets $5–25B)", n: 12 },
    FARM_CREDIT:   { label: "Farm Credit System affiliates",  n: 5 },
    CREDIT_UNION:  { label: "Credit unions (members 100k–1M)", n: 24 },
  };

  const SUBVERTICAL_LABEL = {
    RB: "Regional Bank",
    CU: "Credit Union",
    CL: "Commercial Lending",
    CIB: "Corporate & Investment Banking",
    FC: "Farm Credit",
    AM: "Asset Management",
    RIA: "RIA / Wealth",
    IC: "Insurance Carrier",
    IB: "Insurance Brokerage",
  };

  /* ══════════════════════════════════════════════════════════════════
     RUN-SCOPED COLLECTIONS — EMPTY UNTIL WIRED TO BACKEND
     ══════════════════════════════════════════════════════════════════
     Every collection below renders as an empty state in the UI today.
     See `WIRING_NEEDS` at the bottom for the backend endpoint that will
     populate each. Adding live data is a per-surface task — replace
     the empty default with the fetched payload; no other code changes.
  */
  const ENTITIES           = [];   // GET /api/v1/entities
  const EVIDENCE           = [];   // GET /api/v1/entities/:id/evidence
  const INSIGHT_CARDS      = [];   // GET /api/v1/entities/:id/insights
  const RECOMMENDATIONS    = [];   // GET /api/v1/entities/:id/recommendations
  const ISSUES             = [];   // (part of /entities/:id/overview)
  const TIMELINE_EVENTS    = [];   // GET /api/v1/entities/:id/context
  const LEADERSHIP         = [];   // GET /api/v1/entities/:id/overview (firmographics.leadership)
  const THOUGHT_LEADERSHIP = [];   // GET /api/v1/entities/:id/overview (firmographics.thought_leadership)
  const ROADMAP            = [];   // GET /api/v1/entities/:id/platforms (transformation_roadmap)
  const STAIRSTEP_CLUSTERS = {};   // GET /api/v1/entities/:id/platforms (stairstep_clusters)
  const FOCUS_AREAS        = [];   // GET /api/v1/entities/:id/overview (focus_areas)
  const ROADMAP_IMPACTS    = {};   // computed client-side from RECOMMENDATIONS
  const ISSUE_CAPS         = {};   // (part of /entities/:id/heatmap)
  const NOTIFICATIONS      = [];   // GET /api/v1/notifications
  const TECH_STACK         = [];   // GET /api/v1/entities/:id/techstack
  const QA_GATES           = [];   // GET /api/v1/entities/:id/health
  const IMPORT_AUDIT       = [];   // GET /api/v1/admin/imports/audit
  const PENDING_REVIEW     = [];   // GET /api/v1/admin/imports/audit?status=pending_review
  const ACTIVE_RUNS        = [];   // GET /api/v1/dashboard (active_runs)
  const PATTERNS           = [];   // GET /api/v1/patterns
  const ALERTS             = [];   // GET /api/v1/alerts

  /* ══════════════════════════════════════════════════════════════════
     EXPORT — window.DMA contract (consumed by every page synchronously)
     ══════════════════════════════════════════════════════════════════ */
  window.DMA = {
    /* framework spine */
    PILLARS, PLATFORMS, CATEGORIES, VALUE_CHAINS, PEER_SETS,
    SUBVERTICAL_LABEL, EVIDENCE_TIERS,
    /* run-scoped (empty until wired) */
    ENTITIES, EVIDENCE, INSIGHT_CARDS, RECOMMENDATIONS,
    ISSUES, TIMELINE_EVENTS, TECH_STACK, QA_GATES,
    IMPORT_AUDIT, PENDING_REVIEW, ACTIVE_RUNS, PATTERNS,
    LEADERSHIP, THOUGHT_LEADERSHIP, ROADMAP, STAIRSTEP_CLUSTERS,
    FOCUS_AREAS, ROADMAP_IMPACTS, ISSUE_CAPS, NOTIFICATIONS,
    ALERTS,
    /* helpers */
    helpers: { maturityClass, maturityHex, maturityLabel, freshnessOf, clamp, round1 },
    /* accessors (return null/undefined when collections are empty) */
    getEntity:         id => ENTITIES.find(e => e.id === id || e.slug === id),
    getInsight:        id => INSIGHT_CARDS.find(c => c.id === id),
    getEvidence:       id => EVIDENCE.find(e => e.id === id),
    getSubcap:         (entity, id) => entity && entity.subcaps ? entity.subcaps.find(s => s.id === id) : null,
    getCategory:       id => CATEGORIES.find(c => c.id === id),
    getPlatform:       id => PLATFORMS.find(p => p.id === id),
    getRecommendation: id => RECOMMENDATIONS.find(r => r.id === id),
    getFocusArea:      id => FOCUS_AREAS.find(f => f.id === id),
    getTier:           id => EVIDENCE_TIERS[id],
    issueCapsFor:      subcapId => {
      const out = [];
      Object.entries(ISSUE_CAPS).forEach(([iid, info]) => {
        if (info && info.caps && info.caps[subcapId] != null)
          out.push({ id: iid, cap: info.caps[subcapId], issue: ISSUES.find(x => x.id === iid) });
      });
      return out;
    },
    alertsForEntity: id => ALERTS.filter(a => a.entity_id === id),
  };

  /* ══════════════════════════════════════════════════════════════════
     WIRING_NEEDS — single source of truth for live-data integration
     ══════════════════════════════════════════════════════════════════
     For each empty collection above, this map records:
       - the backend endpoint that supplies it
       - which UI surfaces consume it
       - which page fields are direct placeholders (texts / scores /
         colors / lists) versus computed-from-data derivatives

     The next iteration replaces each row's `data` with the fetched
     response. No page code needs to change.
  */
  window.DMA.WIRING_NEEDS = {
    ENTITIES: {
      endpoint: "GET /api/v1/entities",
      surfaces: ["EntityDirectoryPage (/clients)", "Dashboard (/) — recent + active tiles", "ClientShell (top-bar entity selector + run pill)"],
      needs: {
        text:   ["entity.name", "entity.slug", "entity.subvertical_label", "entity.run.request_id", "entity.run.completed_at"],
        score:  ["entity.overall_score", "entity.pillar_scores[]", "entity.run.confidence"],
        color:  ["entity.run.status (active/in_progress/stale → pill color)"],
        list:   ["entity.subcaps[]", "entity.firmographics", "entity.assigned_to"],
      },
    },
    INSIGHT_CARDS: {
      endpoint: "GET /api/v1/entities/:display_id/insights",
      surfaces: ["ClientInsights (/clients/:id/insights — D2)", "InsightModal (modal stack)"],
      needs: {
        text:  ["title", "what", "why", "so_what"],
        score: ["confidence", "flag (CRITICAL/OPPORTUNITY/MONITOR)"],
        list:  ["evidence[] (E-ID refs)", "affects[] (subcap_id refs)", "platforms[]"],
      },
    },
    EVIDENCE: {
      endpoint: "GET /api/v1/entities/:display_id/evidence",
      surfaces: ["EvidenceDrawer (layered above every modal)", "InsightModal (citation chips)", "D3 subcap drill (evidence list)"],
      needs: {
        text:  ["title", "source_pretty", "excerpt", "recency"],
        score: ["tier (T1..T8 → tier-chip class)", "ers (0..1)"],
        list:  ["subcaps[] (subcap_id refs)", "claim ∈ {FACT, INFERENCE, HYPOTHESIS}"],
      },
    },
    RECOMMENDATIONS: {
      endpoint: "GET /api/v1/entities/:display_id/recommendations",
      surfaces: ["ClientPlatform (/clients/:id/platform — D4)", "RecommendationModal", "TransformationRoadmap (3-view variants)"],
      needs: {
        text:  ["title", "rationale", "before_after.before", "before_after.after"],
        score: ["uplift_per_pillar.{P1..P4}", "fit_score", "readiness_index"],
        list:  ["addressable_subcaps[]", "platforms[]", "ccg_l4_features[] (cited agent/construct/feature IDs)"],
      },
    },
    ALERTS: {
      endpoint: "GET /api/v1/alerts",
      surfaces: ["AlertsPage (/alerts)", "Sidebar (alert badge count)", "Dashboard (Alerts tile)"],
      needs: {
        text:  ["title", "rationale"],
        score: ["severity", "age_days"],
        color: ["status ∈ {OPEN, WAIVED, RESOLVED} → status pill"],
        list:  ["entity_id (FK to ENTITIES)", "subcap_ids[]"],
      },
    },
    ACTIVE_RUNS: {
      endpoint: "GET /api/v1/dashboard (active_runs)",
      surfaces: ["Dashboard active tiles", "Sidebar (run dot animation)"],
      needs: {
        text:  ["entity_name", "current_stage", "ETA"],
        score: ["progress_percent"],
      },
    },
    TIMELINE_EVENTS: {
      endpoint: "GET /api/v1/entities/:display_id/context (D5)",
      surfaces: ["ClientContext (D5) — timeline narrative overlay + financials Gantt"],
      needs: {
        text:  ["event_title", "narrative", "source_ref"],
        score: ["sentiment (−1..1)"],
        list:  ["event_date", "category ∈ {news, regulatory, financial, leadership}"],
      },
    },
    FOCUS_AREAS: {
      endpoint: "GET /api/v1/entities/:display_id/overview (focus_areas)",
      surfaces: ["ClientHeatmap (/clients/:id/heatmap?hm=focus) — SynthesisDrawer", "FocusAreaView hero card"],
      needs: {
        text:  ["name", "source_quote (verbatim from client profile)", "source_path", "financial_reference"],
        score: ["page_number"],
        list:  ["involved_subcap_ids[]"],
      },
    },
    LEADERSHIP: {
      endpoint: "GET /api/v1/entities/:display_id/overview (firmographics.leadership)",
      surfaces: ["ClientOverview (/clients/:id/overview — D1) — Leadership Panel cards"],
      needs: {
        text:  ["name", "title", "bio_snippet", "tenure"],
        list:  ["recent_signals[] (Clay enrichment)"],
      },
      sync_clock: "firmographics.clay_synced_at — green<7d, amber 7-30d, red >30d",
    },
    THOUGHT_LEADERSHIP: {
      endpoint: "GET /api/v1/entities/:display_id/overview (firmographics.thought_leadership)",
      surfaces: ["ClientOverview (D1) — Thought Leadership feed"],
      needs: {
        text:  ["title", "summary", "source"],
        list:  ["date", "type ∈ {article, podcast, conference, webinar}"],
      },
    },
    ROADMAP: {
      endpoint: "GET /api/v1/entities/:display_id/platforms (transformation_roadmap)",
      surfaces: ["ClientPlatform (D4) — TransformationRoadmap 3-view (phases / waves / quarters)"],
      needs: {
        text:  ["phase_name", "outcome_narrative"],
        score: ["pillar_uplift.{P1..P4}", "quarter_offset"],
        list:  ["milestones[]", "dependencies[]"],
      },
    },
    STAIRSTEP_CLUSTERS: {
      endpoint: "GET /api/v1/entities/:display_id/platforms (stairstep_clusters)",
      surfaces: ["ClientPlatform (D4) — StairstepCurve milestones per subcap"],
      needs: {
        score: ["current_band (M1..M5)", "target_band", "delta"],
        list:  ["subcap_ids per cluster"],
      },
    },
    TECH_STACK: {
      endpoint: "GET /api/v1/entities/:display_id/techstack",
      surfaces: ["ClientTechStack (/clients/:id/techstack)", "TechStackDetail (per-tech subpage)"],
      needs: {
        text:  ["vendor", "product_name", "category", "l3_id"],
        score: ["detection_confidence"],
        color: ["status pill (DETECTED / CONFIRMED / CONFIRMED_REMOVED)"],
        list:  ["evidence_ids[]", "linked_subcap_ids[]"],
      },
    },
    QA_GATES: {
      endpoint: "GET /api/v1/entities/:display_id/health",
      surfaces: ["ClientHealth (/clients/:id/health — D6, Analyst/Admin only)"],
      needs: {
        text:  ["gate_id", "description"],
        color: ["status ∈ {PASS, PARTIAL, DEFERRED, FAIL} → status pill"],
        list:  ["evidence_url", "evaluated_at"],
      },
    },
    ISSUES: {
      endpoint: "Part of /api/v1/entities/:display_id/heatmap (issue_register)",
      surfaces: ["ClientHeatmap (D3) — IssueRegisterBanner (lock icons on capped cells)"],
      needs: {
        text:  ["title", "rationale", "issue_id"],
        score: ["severity"],
        list:  ["capped_subcap_ids[]"],
      },
    },
    ISSUE_CAPS: {
      endpoint: "Computed from ISSUES: { issue_id → { caps: { subcap_id: cap_value } } }",
      surfaces: ["D3 Heatmap — lock icon overlay + cap pill on hover"],
      needs: { score: ["cap_value per (issue, subcap)"] },
    },
    IMPORT_AUDIT: {
      endpoint: "GET /api/v1/admin/imports/audit",
      surfaces: ["ImportAuditPage (/admin/import/audit)"],
      needs: {
        text:  ["file_name", "scan_id", "parser_warnings[]"],
        color: ["status ∈ {COMPLETED, FAILED, PENDING_REVIEW}"],
      },
    },
    PENDING_REVIEW: {
      endpoint: "Filter of IMPORT_AUDIT where status='PENDING_REVIEW'",
      surfaces: ["Admin queue tile"],
      needs: { text: ["reason"] },
    },
    PATTERNS: {
      endpoint: "GET /api/v1/patterns",
      surfaces: ["ProspectingPage (/prospecting) — cross-entity pattern tiles"],
      needs: {
        text:  ["title"],
        score: ["count / total (cohort frequency)"],
        list:  ["subvertical", "category"],
      },
    },
    NOTIFICATIONS: {
      endpoint: "GET /api/v1/notifications (planned)",
      surfaces: ["TopBar NotificationsPopover"],
      needs: { text: ["title", "body"], list: ["kind ∈ {alert, completion, system}"] },
    },
    ROADMAP_IMPACTS: {
      endpoint: "Computed client-side from RECOMMENDATIONS",
      surfaces: ["D4 — pillar-uplift bars on recommendation hover"],
      needs: { score: ["per-recommendation pillar uplift sums"] },
    },
  };
})();
