/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Mock data
   Schema names align to PRD v3 + Backend Schema v2.0
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  /* Live boot (production divergence, charter-sanctioned): when the host
     page supplies window.DMA_LIVE, the catalogue and every corpus-level
     list come from svc_api; the mock below remains as the shape
     reference and the local-preview fallback. Entity-scoped mock data
     is unreachable once ENTITIES is live. */
  const LIVE = typeof window !== "undefined" && window.DMA_LIVE || null;
  /* ── Maturity color helpers ──────────────────────────────────────── */
  function maturityClass(s) {
    if (s == null) return "muted";
    if (s < 2) return "b-act";
    if (s < 3) return "b-bld";
    if (s < 4) return "b-cmp";
    return "b-dif";
  }
  function maturityHex(s) {
    if (s == null) return "#E5E7EB";
    if (s < 2) return "#FFCB99";
    if (s < 3) return "#62D7B8";
    if (s < 4) return "#27BBAF";
    return "#139F94";
  }
  function maturityLabel(s) {
    if (s === null || s === undefined || !isFinite(Number(s))) return null;
    if (s < 2) return "Activating";
    if (s < 3) return "Building";
    if (s < 4) return "Competing";
    return "Differentiating";
  }
  function freshnessOf(date) {
    const now = new Date();
    const d = new Date(date);
    const months = (now - d) / (1000 * 60 * 60 * 24 * 30.4);
    if (months > 12) return {
      tone: "below",
      label: "Stale",
      months: Math.round(months)
    };
    if (months > 6) return {
      tone: "warn",
      label: "Aging",
      months: Math.round(months)
    };
    return {
      tone: "ok",
      label: "Current",
      months: Math.round(months)
    };
  }

  /* ── Pillars ─────────────────────────────────────────────────────── */
  const PILLARS = LIVE && LIVE.pillars || [{
    id: "P1",
    name: "Strategy & Governance",
    short: "Strategy"
  }, {
    id: "P2",
    name: "Customer Experience",
    short: "Customer"
  }, {
    id: "P3",
    name: "Operations & Workflow",
    short: "Operations"
  }, {
    id: "P4",
    name: "Data & Technology",
    short: "Data & Tech"
  }];

  /* ── Platforms (PRD) ─────────────────────────────────────────── */
  const PLATFORMS = [{
    id: "SF",
    name: "Salesforce",
    short: "SF",
    features: "Agentforce · Data Cloud · FSC · CRMA · Marketing · Platform",
    color: "#00A1E0"
  }, {
    id: "DB",
    name: "Databricks",
    short: "DB",
    features: "Mosaic AI · Agent Bricks · Lakeflow",
    color: "#FF3621"
  }, {
    id: "TBL",
    name: "Tableau",
    short: "TBL",
    features: "Embedded · Next · Pulse",
    color: "#1F4E79"
  }, {
    id: "TW",
    name: "Twilio",
    short: "TW",
    features: "Engage · Conversations",
    color: "#F22F46"
  }, {
    id: "nCino",
    name: "nCino",
    short: "nC",
    features: "Workflow Engine · Document Manager",
    color: "#0067A0"
  }];

  /* ── Categories (compressed for prototype) ───────────────────────── */
  const CATEGORIES = LIVE && LIVE.categories || [{
    id: "P1C1",
    pillar: "P1",
    name: "Digital Strategy",
    weight: .28
  }, {
    id: "P1C2",
    pillar: "P1",
    name: "Governance & Risk",
    weight: .22
  }, {
    id: "P1C3",
    pillar: "P1",
    name: "Innovation Operating Model",
    weight: .18
  }, {
    id: "P1C4",
    pillar: "P1",
    name: "Talent & Culture",
    weight: .16
  }, {
    id: "P2C1",
    pillar: "P2",
    name: "Channel Experience",
    weight: .26
  }, {
    id: "P2C2",
    pillar: "P2",
    name: "Digital Service Model",
    weight: .24
  }, {
    id: "P2C3",
    pillar: "P2",
    name: "Customer Journey",
    weight: .26
  }, {
    id: "P2C4",
    pillar: "P2",
    name: "Personalisation",
    weight: .14
  }, {
    id: "P3C1",
    pillar: "P3",
    name: "Workflow Automation",
    weight: .28
  }, {
    id: "P3C2",
    pillar: "P3",
    name: "Loan Origination",
    weight: .24
  }, {
    id: "P3C3",
    pillar: "P3",
    name: "Servicing Efficiency",
    weight: .20
  }, {
    id: "P3C4",
    pillar: "P3",
    name: "Process Intelligence",
    weight: .18
  }, {
    id: "P4C1",
    pillar: "P4",
    name: "Data Foundation",
    weight: .32
  }, {
    id: "P4C2",
    pillar: "P4",
    name: "Analytics & Insight",
    weight: .22
  }, {
    id: "P4C3",
    pillar: "P4",
    name: "AI & Decisioning",
    weight: .22
  }, {
    id: "P4C4",
    pillar: "P4",
    name: "Architecture & Cloud",
    weight: .18
  }, {
    id: "P4C5",
    pillar: "P4",
    name: "Security & Trust",
    weight: .14
  }];

  /* ── Capabilities + Subcaps generator ────────────────────────────── */
  // A handful of subcap names per category. We generate ~6 subcaps per category
  // for prototype density. Schema fields match Backend Schema
  const SUBCAP_NAMES = {
    P1C1: ["Digital Strategy Charter", "Business Alignment", "Strategic Refresh Cycle", "Vision Comms", "OKR Cascade", "Board Visibility"],
    P1C2: ["Risk Framework", "Regulatory Compliance", "Data Governance", "Ethics & AI Policy", "Vendor Oversight", "Audit Discipline"],
    P1C3: ["Innovation Pipeline", "Sandbox Capacity", "Partnership Model", "Decision Velocity", "KPI Discipline", "Funding Mechanism"],
    P1C4: ["Talent Strategy", "Digital Skills", "Hiring Signal", "Culture & Change", "Leadership Pipeline", "Performance Model"],
    P2C1: ["Mobile Experience", "Web Channel", "Branch Digital", "Call Center", "Self-Service Tooling", "Channel Consistency"],
    P2C2: ["Service Tiers", "Agent-Assisted Service", "Service Recovery", "SLAs", "Knowledge Base", "Conversational UX"],
    P2C3: ["Journey Mapping", "Onboarding Flow", "Servicing Flow", "Cross-Channel Hand-off", "Friction Telemetry", "NPS Discipline"],
    P2C4: ["Segment Strategy", "Next-Best-Action", "Channel Personalisation", "Content Library", "Consent & Preferences", "Behavior Models"],
    P3C1: ["RPA Footprint", "Process Library", "STP Rate", "Exception Handling", "Operational Telemetry", "Bot Governance"],
    P3C2: ["Application Intake", "Underwriting", "Decisioning Latency", "Booking & Closing", "Doc Manager", "Cycle Time"],
    P3C3: ["Servicing Cases", "Self-Heal", "Member Lifecycle", "Cross-Sell Hooks", "Field Ops", "Quality Sampling"],
    P3C4: ["Process Mining", "Forecasting", "Capacity Modelling", "Quality KPIs", "Bottleneck Detection", "Continuous Improvement"],
    P4C1: ["Data Platform", "Master Data", "Unified Customer Profile", "Streaming Ingestion", "Data Quality", "Master Lineage"],
    P4C2: ["Reporting & BI", "Embedded Analytics", "Decision Dashboards", "Self-Service Analytics", "Metric Catalog", "Data Literacy"],
    P4C3: ["GenAI Foundation", "Decisioning Engine", "Model Ops", "Feature Store", "AI Governance", "Agent Strategy"],
    P4C4: ["Cloud Posture", "Integration Platform", "API Strategy", "Event-Driven Arch", "DevOps Velocity", "Resiliency"],
    P4C5: ["Identity & Access", "Zero-Trust", "Data Protection", "Threat Detection", "Privacy by Design", "Vendor Security"]
  };

  // L2 leaf aspects — each L1 capability cluster expands into several of these
  const SUBCAP_LEAVES = ["Framework & Standards", "Operating Model", "Process Automation", "Telemetry & Metrics", "Governance & Controls", "Tooling & Platform", "Playbook & Runbooks", "Continuous Improvement", "Integration & Interop", "Roles & Ownership"];
  function makeSubcaps(entityScores) {
    // entityScores: function(catId) -> avg score; we derive subcap scores.
    // Real V7 hierarchy: Category (L0) → L1 capability cluster → L2 sub-cap.
    // Each name in SUBCAP_NAMES is an L1 cluster; each cluster expands into
    // 6–9 L2 sub-caps so per-category counts match the real catalog
    // (P1≈205, P2≈292, P3≈164, P4≈190 sub-caps across their categories).
    const out = [];
    for (const cat of CATEGORIES) {
      const baseScore = entityScores(cat.id);
      const clusters = SUBCAP_NAMES[cat.id];
      const platforms0 = pickPlatforms(cat.id);
      clusters.forEach((clusterName, ci) => {
        // deterministic leaf count per cluster (6–9)
        const leafCount = 6 + (ci * 7 + Math.round(cat.weight * 97)) % 4;
        for (let li = 0; li < leafCount; li++) {
          const seed = (ci + 1) * 131 + (li + 1) * 17 + cat.id.charCodeAt(3) * 3;
          const jitter = (seed % 100 / 100 - 0.5) * 1.5;
          const score = clamp(round1(baseScore + jitter), 1, 5);
          const peerMedian = clamp(round1(baseScore + 0.35 + (li + ci) % 3 * 0.2), 1, 5);
          const evCount = seed % 9; // 0–8 evidence items
          const id = `${cat.id}.${ci + 1}.${li + 1}`;
          const thin = evCount < 3;
          // vary platform footprint across leaves
          const platforms = li % 4 === 3 && platforms0.length > 1 ? [platforms0[1]] : [platforms0[0]];
          const locked = cat.id === "P2C2" && ci === 1 && li === 0 || cat.id === "P4C5" && ci === 1 && li === 0 ? "IS-014" : null;
          out.push({
            id,
            name: `${clusterName} · ${SUBCAP_LEAVES[li % SUBCAP_LEAVES.length]}`,
            l1: ci + 1,
            l1name: clusterName,
            category: cat.id,
            pillar: cat.pillar,
            score,
            peerMedian,
            evidence_count: evCount,
            confidence: thin ? "LOW" : evCount > 5 ? "HIGH" : "MEDIUM",
            thin,
            platforms,
            locked,
            weight: cat.weight
          });
        }
      });
    }
    return out;
  }
  function pickPlatforms(catId) {
    if (catId.startsWith("P1")) return ["SF"];
    if (catId === "P2C1" || catId === "P2C3") return ["SF", "TW"];
    if (catId === "P2C2") return ["SF"];
    if (catId === "P2C4") return ["SF", "DB"];
    if (catId === "P3C1") return ["nCino", "SF"];
    if (catId === "P3C2") return ["nCino"];
    if (catId === "P3C3") return ["SF", "nCino"];
    if (catId === "P3C4") return ["DB", "TBL"];
    if (catId === "P4C1") return ["SF", "DB"];
    if (catId === "P4C2") return ["TBL", "DB"];
    if (catId === "P4C3") return ["DB", "SF"];
    if (catId === "P4C4") return ["DB"];
    if (catId === "P4C5") return ["SF"];
    return ["SF"];
  }
  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }
  function round1(n) {
    return Math.round(n * 10) / 10;
  }

  /* ── Value chains (V7) ───────────────────────────────────────── */
  const VALUE_CHAINS = [{
    id: "VC1",
    name: "Digital Account Opening",
    subcaps: ["P2C3.1.1", "P2C1.1.1", "P4C1.3.1", "P4C5.1.1"]
  }, {
    id: "VC2",
    name: "Loan Origination",
    subcaps: ["P3C2.1.1", "P3C2.2.1", "P3C2.3.1", "P4C1.5.1"]
  }, {
    id: "VC3",
    name: "Member Servicing",
    subcaps: ["P2C2.1.1", "P2C2.2.1", "P3C3.1.1", "P3C3.2.1"]
  }, {
    id: "VC4",
    name: "Cross-Sell & Marketing",
    subcaps: ["P2C4.1.1", "P2C4.2.1", "P4C3.1.1"]
  }, {
    id: "VC5",
    name: "Risk & Compliance Operations",
    subcaps: ["P1C2.1.1", "P1C2.2.1", "P4C5.2.1"]
  }, {
    id: "VC6",
    name: "Data-Driven Decisioning",
    subcaps: ["P4C1.3.1", "P4C2.2.1", "P4C3.2.1"]
  }];

  /* ── Evidence items (run-scoped) - TIER COLOR-CODED (T1–T8) ─── */
  const EVIDENCE = [{
    id: "E-047",
    title: "FCE 2025 annual report - IT modernization disclosure",
    source: "farmcrediteast.com/annual-report-2025.pdf",
    source_pretty: "FCE annual report 2025",
    tier: "T1",
    ers: 0.92,
    claim: "FACT",
    recency: "2025-Q4",
    subcaps: ["P4C1.1.1", "P4C1.1.2", "P4C4.2.1"],
    excerpt: "We are mid-migration from our legacy core to nCino with target completion in Q2 2026. The transition has temporarily increased data complexity across three production systems."
  }, {
    id: "E-089",
    title: "Q1 2026 earnings call - CIO commentary",
    source: "seekingalpha.com/transcript/fce-q1-2026",
    source_pretty: "Earnings call · Q1 2026",
    tier: "T2",
    ers: 0.81,
    claim: "INFERENCE",
    recency: "2026-Q1",
    subcaps: ["P4C1.2.1", "P4C1.3.1"],
    excerpt: "[CIO] We've been evaluating Data Cloud as a customer 360 layer for about six months - we have not yet selected a vendor, but it's a priority for FY27."
  }, {
    id: "E-112",
    title: "Job posting - Data Cloud Architect (LinkedIn)",
    source: "linkedin.com/jobs/view/40-data-cloud-architect",
    source_pretty: "LinkedIn job · Data Cloud Architect",
    tier: "T7",
    ers: 0.74,
    claim: "INFERENCE",
    recency: "2026-Q1",
    subcaps: ["P4C1.2.1", "P4C3.1.1"],
    excerpt: "Lead the build-out of our enterprise Customer Data Platform on Salesforce Data Cloud..."
  }, {
    id: "E-141",
    title: "10-K filing - Risk factors",
    source: "sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=...",
    source_pretty: "10-K filing 2025",
    tier: "T1",
    ers: 0.93,
    claim: "FACT",
    recency: "2025-Q3",
    subcaps: ["P4C1.1.1", "P4C4.2.1"],
    excerpt: "We face risk from system integration delays following multiple core system platform consolidations."
  }, {
    id: "E-203",
    title: "CDO LinkedIn announcement - new hire",
    source: "linkedin.com/in/raj-iyer-cdo/",
    source_pretty: "Raj Iyer LinkedIn",
    tier: "T4",
    ers: 0.62,
    claim: "INFERENCE",
    recency: "2026-Q2",
    subcaps: ["P1C4.1.1", "P4C1.3.1"],
    excerpt: "Excited to join Farm Credit East as Chief Data Officer to lead a multi-year data foundation transformation."
  }, {
    id: "E-218",
    title: "AML enforcement action - FRB consent order",
    source: "federalreserve.gov/enforcement/cease-and-desist",
    source_pretty: "FRB consent order",
    tier: "T1",
    ers: 0.95,
    claim: "FACT",
    recency: "2024-Q4",
    subcaps: ["P1C2.1.1", "P1C2.2.1", "P4C5.2.1"],
    excerpt: "Consent order requires remediation of transaction monitoring controls within 18 months."
  }, {
    id: "E-236",
    title: "Glassdoor reviews - operations team",
    source: "glassdoor.com/Reviews/FCE-ops",
    source_pretty: "Glassdoor · Operations",
    tier: "T6",
    ers: 0.58,
    claim: "HYPOTHESIS",
    recency: "2026-Q1",
    subcaps: ["P3C2.1.1", "P3C2.2.1"],
    excerpt: "Manual loan processing - too many spreadsheets and PDF re-keying."
  }, {
    id: "E-250",
    title: "Press release - Tableau Cloud deployment",
    source: "fce.com/news/tableau-cloud-deployment-2025",
    source_pretty: "FCE press release · 2025-Q2",
    tier: "T2",
    ers: 0.86,
    claim: "FACT",
    recency: "2025-Q2",
    subcaps: ["P4C2.1.1", "P4C2.2.1"],
    excerpt: "FCE has completed enterprise-wide rollout of Tableau Cloud to 1,800 employees."
  }, {
    id: "E-271",
    title: "App store reviews - mobile app",
    source: "apps.apple.com/us/app/farm-credit-east",
    source_pretty: "Apple App Store reviews",
    tier: "T6",
    ers: 0.66,
    claim: "INFERENCE",
    recency: "2026-Q2",
    subcaps: ["P2C1.1.1", "P2C2.2.1"],
    excerpt: "Mobile transfers are slow. Branch staff still required for many tasks."
  }, {
    id: "E-283",
    title: "Job posting - Tableau Pulse Specialist",
    source: "indeed.com/viewjob?jk=tableau-pulse",
    source_pretty: "Indeed · Tableau Pulse",
    tier: "T7",
    ers: 0.71,
    claim: "INFERENCE",
    recency: "2026-Q2",
    subcaps: ["P4C2.2.1", "P4C3.1.1"],
    excerpt: "Help our growing analytics team rollout Tableau Pulse to relationship managers."
  }, {
    id: "E-302",
    title: "WSJ - regional bank consolidation trends",
    source: "wsj.com/articles/regional-bank-consolidation",
    source_pretty: "Wall Street Journal",
    tier: "T3",
    ers: 0.78,
    claim: "INFERENCE",
    recency: "2025-Q4",
    subcaps: ["P1C1.1.1"],
    excerpt: "Regional banks face mounting pressure to consolidate technology stacks as digital expectations rise."
  }, {
    id: "E-311",
    title: "Forrester - Banking CX 2026 Q1",
    source: "forrester.com/report/banking-cx-q1-2026",
    source_pretty: "Forrester analyst report",
    tier: "T3",
    ers: 0.82,
    claim: "INFERENCE",
    recency: "2026-Q1",
    subcaps: ["P2C1.1.1", "P2C4.1.1"],
    excerpt: "Regional and community banks trail national peers in mobile-first servicing by 14 months on average."
  }, {
    id: "E-340",
    title: "Subreddit /r/farmcredit thread",
    source: "reddit.com/r/farmcredit/comments/abc",
    source_pretty: "Reddit thread",
    tier: "T8",
    ers: 0.35,
    claim: "HYPOTHESIS",
    recency: "2026-Q1",
    subcaps: ["P2C2.1.1"],
    excerpt: "Always have to call my rep for anything - there's no self-service for ag loans."
  }];

  /* ── Insight cards (Client Profile) ─────────────────────────── */
  const INSIGHT_CARDS = LIVE ? [] : [{
    id: "IC-003",
    pillar: "P4",
    flag: "CRITICAL",
    confidence: "HIGH",
    theme: "Data foundation",
    title: "Data architecture fragmentation",
    what: "FCE's data architecture spans three disconnected core systems with no unified customer data layer confirmed.",
    why: "Without a unified customer data foundation, real-time personalisation, AI-driven decisioning, and cross-channel consistency are architecturally impossible regardless of front-end investment. This is the root constraint behind the M2 scores across P2C2, P2C3, and P4C1.",
    so_what: "Salesforce Data Cloud + Databricks Lakehouse removes this constraint. The institution is at the stage - hiring signals, leadership awareness - where this conversation is timely before they commit to a point-solution that creates further fragmentation.",
    evidence: ["E-047", "E-089", "E-112", "E-141"],
    affects: ["P2C2.2.1", "P2C3.4.1", "P4C1.1.1", "P4C1.3.1"],
    platforms: ["SF", "DB"],
    rec: "REC-04",
    annotation: null
  }, {
    id: "IC-007",
    pillar: "P2",
    flag: "OPPORTUNITY",
    confidence: "HIGH",
    theme: "Customer experience",
    title: "Digital channel investment signals",
    what: "Hiring signals indicate digital strategy maturation underway - 5 open Marketing Cloud and Service Cloud roles posted in Q1 2026, with public LinkedIn announcements naming Marketing Cloud and Twilio Engage as in-scope.",
    why: "FCE's investment posture aligns with M3 ambition in customer experience but their current digital channel scores (P2C1 = 2.4) reflect M2 maturity. The capacity gap will become acute as new platforms are deployed without unified data.",
    so_what: "Lead with a CX roadmap conversation framed against the announced talent build - Twilio Engage plus Marketing Cloud paired with Data Cloud creates a coherent stack rather than another point integration.",
    evidence: ["E-089", "E-112", "E-203"],
    affects: ["P2C1.1.1", "P2C1.2.1", "P2C4.1.1"],
    platforms: ["SF", "TW"],
    rec: "REC-07",
    annotation: {
      author: "M. Otiende",
      role: "ANALYST",
      body: "Discussed with Delivery Lead before the Farm Credit call. CIO mentioned they have been evaluating Data Cloud for 6 months but have not committed. Connected to SF opportunity SF-2847.",
      status: "ACTIONED",
      when: "Jun 2, 2026 · 9:32 AM"
    }
  }, {
    id: "IC-009",
    pillar: "P3",
    flag: "OPPORTUNITY",
    confidence: "MEDIUM",
    theme: "Operational efficiency",
    title: "Workflow automation gap in loan origination",
    what: "Loan origination workflow steps are ~85% manual based on Glassdoor commentary and process documentation. STP rate in the underwriting subcap is at 1.8.",
    why: "Manual rework cycles cap P3C2 scores at M2 and indirectly cap P3C1 capability scores by exception volume. The gap is workflow surface, not core technology - addressable without core replacement.",
    so_what: "nCino Workflow Engine plus a thin Service Cloud layer can compress 12-day cycle to 4-day median, with Tableau Pulse providing live KPI visibility for ops leadership. Proven 40% cycle-time reduction at named regional peers.",
    evidence: ["E-236", "E-283"],
    affects: ["P3C2.1.1", "P3C2.2.1", "P3C2.3.1"],
    platforms: ["nCino", "SF"],
    rec: "REC-09",
    annotation: null
  }, {
    id: "IC-011",
    pillar: "P1",
    flag: "MONITOR",
    confidence: "HIGH",
    theme: "Risk & compliance",
    title: "Regulatory posture stable",
    what: "FCA examination Q3 2025 confirmed no material findings. AML consent order from 2024 remediation track on schedule for closure Q4 2026.",
    why: "Regulatory standing is a deal-complexity input, not an opportunity. Stable posture means platform conversations need not focus on compliance remediation as the lead theme.",
    so_what: "Anchor discovery on growth, not compliance - FCE's regulatory base is solid enough to invest in customer experience and data with confidence.",
    evidence: ["E-218"],
    affects: ["P1C2.1.1", "P1C2.2.1"],
    platforms: [],
    rec: null,
    annotation: null
  }, {
    id: "IC-014",
    pillar: "P4",
    flag: "OPPORTUNITY",
    confidence: "HIGH",
    theme: "Data & AI",
    title: "Analytics adoption ahead of decisioning capability",
    what: "Tableau Cloud rolled to ~1,800 employees in 2025. P4C2 (Analytics & Insight) at 3.1. P4C3 (AI & Decisioning) at 1.8.",
    why: "Self-service analytics maturity outpaces decisioning infrastructure. Reports are produced widely; outcomes don't yet drive automated actions. Mosaic AI on Databricks bridges that gap with existing skill base.",
    so_what: "Position Mosaic AI as an outcome layer on the existing Tableau investment - a natural next step, not a re-platforming, framed as 'analytics → action'.",
    evidence: ["E-250", "E-283"],
    affects: ["P4C2.2.1", "P4C3.1.1", "P4C3.2.1"],
    platforms: ["DB", "TBL"],
    rec: "REC-14",
    annotation: null
  }, {
    id: "IC-018",
    pillar: "P2",
    flag: "CRITICAL",
    confidence: "MEDIUM",
    theme: "Customer experience",
    title: "Mobile experience trails peer median",
    what: "App store ratings trail the regional bank peer median by 0.8 stars. User reviews cite slow mobile transfers and branch dependency.",
    why: "Mobile is the lowest-cost servicing channel - every percentage point of branch-dependency translates to operating cost AND attrition risk in the 18-34 segment.",
    so_what: "A Twilio Engage + Service Cloud lift focused on mobile self-service can compress branch dependency without a full core replacement. Time-to-impact: 8-10 months.",
    evidence: ["E-271"],
    affects: ["P2C1.1.1", "P2C2.2.1"],
    platforms: ["TW", "SF"],
    rec: "REC-18",
    annotation: null
  }];

  /* ── Recommendations (REC-XX) ────────────────────────────────────── */
  const RECOMMENDATIONS = [{
    id: "REC-04",
    title: "Establish unified customer data foundation",
    platform: "SF",
    feature: "Data Cloud",
    phase: "Phase 1 (0–6 mo)",
    root_cause: ["E-047", "E-141"],
    outcomes: {
      time: "6-9 months",
      effort: "M",
      metric: "Single customer view across 3 core systems",
      peer: "Synovus, M&T"
    }
  }, {
    id: "REC-07",
    title: "Sequence Marketing Cloud + Twilio Engage",
    platform: "SF",
    feature: "Marketing Cloud",
    phase: "Phase 2 (6–12 mo)",
    root_cause: ["E-089"],
    outcomes: {
      time: "9-12 months",
      effort: "M",
      metric: "Multi-channel campaign attribution",
      peer: "TD Bank"
    }
  }, {
    id: "REC-09",
    title: "nCino Workflow Engine on loan origination",
    platform: "nCino",
    feature: "Workflow Engine",
    phase: "Phase 1 (0–6 mo)",
    root_cause: ["E-236"],
    outcomes: {
      time: "5-7 months",
      effort: "S",
      metric: "Loan origination cycle ↓ 40%",
      peer: "First Citizens"
    }
  }, {
    id: "REC-14",
    title: "Mosaic AI on Databricks for decisioning",
    platform: "DB",
    feature: "Mosaic AI",
    phase: "Phase 3 (12-18 mo)",
    root_cause: ["E-250", "E-283"],
    outcomes: {
      time: "12-18 months",
      effort: "L",
      metric: "Real-time risk scoring & next-best-action",
      peer: "Capital One"
    }
  }, {
    id: "REC-18",
    title: "Mobile self-service uplift",
    platform: "TW",
    feature: "Engage",
    phase: "Phase 2 (6–12 mo)",
    root_cause: ["E-271"],
    outcomes: {
      time: "8-10 months",
      effort: "M",
      metric: "Branch deflection rate +18pts",
      peer: "BMO, Truist"
    }
  }];

  /* Per-entity recommendation resolver ───────────────────────────────
     The flagship carries hand-authored recs; every other client gets recs
     synthesized from its own sub-capability gaps so ALL clients are
     represented on the Platform page. Synthesized recs are cached so the
     recommendation modal (getRecommendation) can resolve them by id.
     SOURCE: 08_appendices/recommendations.json (per entity at ingest). */
  const RECS_CACHE = {};
  function recsFor(id) {
    const e = ENTITIES.find(x => x.id === id);
    if (id === "fce-001") return RECOMMENDATIONS;
    if (!e || !e.subcaps || !e.subcaps.length) return []; // no completed run → honest empty state
    if (RECS_CACHE["__ent_" + id]) return RECS_CACHE["__ent_" + id];
    const short = (id.split("-")[0] || id).toUpperCase().slice(0, 4);
    const byPlat = {};
    e.subcaps.filter(s => s.score < 3 && s.platforms && s.platforms.length).forEach(s => {
      const p = s.platforms[0];
      (byPlat[p] = byPlat[p] || []).push(s);
    });
    // High-maturity client with no sub-3.0 gaps: fall back to its own lowest subcaps
    if (Object.keys(byPlat).length === 0) {
      [...e.subcaps].filter(s => s.platforms && s.platforms.length).sort((a, b) => a.score - b.score).slice(0, 3).forEach(s => {
        const p = s.platforms[0];
        (byPlat[p] = byPlat[p] || []).push(s);
      });
    }
    const out = [];
    let n = 1;
    Object.entries(byPlat).forEach(([pid, subs]) => {
      subs.sort((a, b) => b.peerMedian - b.score - (a.peerMedian - a.score));
      const s = subs[0];
      const plat = PLATFORMS.find(x => x.id === pid);
      const cat = CATEGORIES.find(c => c.id === s.category);
      const ev = EVIDENCE.filter(x => x.subcaps && x.subcaps.some(sid => sid.slice(0, 4) === s.id.slice(0, 4))).map(x => x.id).slice(0, 2);
      const phaseIdx = out.length;
      const rec = {
        id: `REC-${short}-${String(n++).padStart(2, "0")}`,
        title: `Close ${cat && cat.name || s.category} gap with ${plat && plat.name || pid}`,
        platform: pid,
        feature: plat && plat.name ? `${plat.name} capability` : "Platform capability",
        phase: phaseIdx === 0 ? "Phase 1 (0–6 mo)" : phaseIdx === 1 ? "Phase 2 (6–12 mo)" : "Phase 3 (12-18 mo)",
        root_cause: ev,
        synth: true,
        outcomes: {
          time: phaseIdx === 0 ? "5-7 months" : "9-12 months",
          effort: subs.length > 3 ? "L" : subs.length > 1 ? "M" : "S",
          metric: `Lift ${s.id} from ${s.score.toFixed(1)} toward peer median ${s.peerMedian.toFixed(1)} (${subs.length} subcap${subs.length === 1 ? "" : "s"} in scope)`,
          peer: (SUBVERTICAL_LABEL[e.subvertical] || "peer") + " cohort"
        }
      };
      RECS_CACHE[rec.id] = rec;
      out.push(rec);
    });
    RECS_CACHE["__ent_" + id] = out.length ? out : [];
    return RECS_CACHE["__ent_" + id];
  }

  /* ── Issue register (Assessment Report) ───────────────────────── */
  const ISSUES = [{
    id: "IS-014",
    type: "Regulatory",
    severity: "MATERIAL",
    desc: "AML consent order - transaction monitoring remediation track on schedule.",
    caps: ["P1C2", "P4C5"],
    cap_value: 3.0,
    status: "OPEN",
    start: "2024-12",
    end: null
  }, {
    id: "IS-018",
    type: "Process",
    severity: "MINOR",
    desc: "Quarterly close cycle delays in finance ops.",
    caps: ["P3C3"],
    cap_value: 3.5,
    status: "RESOLVED",
    start: "2025-Q2",
    end: "2025-Q4"
  }, {
    id: "IS-021",
    type: "Data quality",
    severity: "MATERIAL",
    desc: "Customer master data quality issues - duplicate records across 3 cores.",
    caps: ["P4C1", "P2C3"],
    cap_value: 2.5,
    status: "OPEN",
    start: "2025-Q1",
    end: null
  }, {
    id: "IS-027",
    type: "Operational",
    severity: "MINOR",
    desc: "Branch network rationalization in upstate NY.",
    caps: ["P2C1"],
    cap_value: 3.5,
    status: "OPEN",
    start: "2025-Q4",
    end: null
  }];

  /* ── Timeline events (Digital Evolution Timeline) ───────────────── */
  const TIMELINE_EVENTS = [{
    id: "TE-01",
    date: "2023-04",
    title: "Tableau Cloud rollout begins",
    signal: "positive",
    cap_impact: "P4C2",
    evidence: ["E-250"]
  }, {
    id: "TE-02",
    date: "2023-11",
    title: "nCino core migration announced (Q2 2026 target)",
    signal: "neutral",
    cap_impact: "P4C4",
    evidence: ["E-047"]
  }, {
    id: "TE-03",
    date: "2024-08",
    title: "Acquisition of Hudson Valley CU branches",
    signal: "neutral",
    cap_impact: "P2C1",
    evidence: []
  }, {
    id: "TE-04",
    date: "2024-12",
    title: "AML enforcement action - FRB consent order",
    signal: "negative",
    cap_impact: "P1C2",
    evidence: ["E-218"]
  }, {
    id: "TE-05",
    date: "2025-06",
    title: "5,000 employee Tableau full enablement",
    signal: "positive",
    cap_impact: "P4C2",
    evidence: ["E-250"]
  }, {
    id: "TE-06",
    date: "2026-01",
    title: "5x Data Cloud Architect openings posted",
    signal: "positive",
    cap_impact: "P4C1",
    evidence: ["E-112"]
  }, {
    id: "TE-07",
    date: "2026-04",
    title: "CTO hired from Wells Fargo",
    signal: "positive",
    cap_impact: "P1C4",
    evidence: ["E-203"]
  }, {
    id: "TE-08",
    date: "2026-05",
    title: "CDO hire - multi-year data transformation",
    signal: "positive",
    cap_impact: "P4C1",
    evidence: ["E-203"]
  }];

  /* ── Leadership (Client Profile) + Clay enrichment ─────────── */
  const LEADERSHIP = [{
    id: "EX-01",
    name: "Mark Hochberg",
    title: "CEO",
    tenure_months: 38,
    background: "Previously COO at AgFirst Farm Credit Bank. 24 years FSI experience.",
    critical_role: false,
    clay: {
      email: "m.hochberg@farmcrediteast.com",
      linkedin: "linkedin.com/in/mhochberg"
    },
    evidence: ["E-203"]
  }, {
    id: "EX-02",
    name: "Diana Solis",
    title: "CTO",
    tenure_months: 2,
    background: "From Wells Fargo (8 yrs, head of Commercial Tech). Hired April 2026.",
    critical_role: true,
    recent_hire: true,
    clay: {
      email: "d.solis@farmcrediteast.com",
      linkedin: "linkedin.com/in/dianasolis"
    },
    evidence: ["E-203"]
  }, {
    id: "EX-03",
    name: "Raj Iyer",
    title: "CDO",
    tenure_months: 1,
    background: "From JPM Chase (Data Cloud lead, FSI). Joined May 2026.",
    critical_role: true,
    recent_hire: true,
    clay: {
      email: "r.iyer@farmcrediteast.com",
      linkedin: "linkedin.com/in/rajiyer-data"
    },
    evidence: ["E-203"]
  }, {
    id: "EX-04",
    name: "Linnea Beck",
    title: "CFO",
    tenure_months: 19,
    background: "Previously CFO at NY Community Bank. CPA.",
    critical_role: false,
    clay: {
      email: "l.beck@farmcrediteast.com",
      linkedin: "linkedin.com/in/lbeck-cfo"
    },
    evidence: []
  }, {
    id: "EX-05",
    name: "-",
    title: "CISO",
    tenure_months: null,
    background: "No confirmed CISO from publicly available evidence.",
    critical_role: true,
    gap_flag: true,
    clay: null,
    evidence: []
  }, {
    id: "EX-06",
    name: "Karim Hadid",
    title: "CHRO",
    tenure_months: 44,
    background: "Long-tenured CHRO. Led 2024 talent strategy refresh.",
    critical_role: false,
    clay: {
      email: "k.hadid@farmcrediteast.com",
      linkedin: "linkedin.com/in/kahadid"
    },
    evidence: []
  }];

  /* ── Thought leadership signals (LinkedIn posts, panels, articles) ─ */
  const THOUGHT_LEADERSHIP = [{
    id: "TL-01",
    author: "Diana Solis (CTO)",
    type: "LinkedIn post",
    date: "2026-05-14",
    title: "Why we're investing in a unified customer data layer before re-platforming our core",
    excerpt: "Data fragmentation is the constraint behind every CX investment we've seen. Closing it changes everything…",
    url: "linkedin.com/posts/dianasolis-..."
  }, {
    id: "TL-02",
    author: "Mark Hochberg (CEO)",
    type: "Conference",
    date: "2026-04-22",
    title: "Panel · The agricultural lender of 2030 - what scale and member experience need to look like",
    excerpt: "We talked about the integration debt across three cores and how nCino is just the first step.",
    url: "fce.com/news/icba-2026-panel"
  }, {
    id: "TL-03",
    author: "Raj Iyer (CDO)",
    type: "Article",
    date: "2026-05-30",
    title: "From reports to actions - what 'data-driven decisioning' actually means",
    excerpt: "Tableau adoption is widespread; outcomes that act on insights are not. Mosaic AI is our bridge.",
    url: "fce.com/insights/raj-iyer-mosaic"
  }];

  /* ── Roadmap (Transformation roadmap) ────────────────────────── */
  const ROADMAP = [{
    phase: 1,
    label: "Foundation",
    duration: "0–6 mo",
    color: "var(--z-dark2)",
    recs: ["REC-04", "REC-09"],
    target: "M2 → M3 in P4C1, P3C2",
    metric: "Unified customer profile · loan cycle ↓ 40%",
    platform: "SF Data Cloud + nCino"
  }, {
    phase: 2,
    label: "Customer layer",
    duration: "6–12 mo",
    color: "var(--z-mid)",
    recs: ["REC-07", "REC-18"],
    target: "M2 → M3 in P2C1, P2C4",
    metric: "Multi-channel attribution · branch deflection +18pts",
    platform: "SF Marketing + Twilio Engage"
  }, {
    phase: 3,
    label: "Decisioning",
    duration: "12–18 mo",
    color: "var(--z-teal)",
    recs: ["REC-14"],
    target: "M3 → M4 in P4C2, P4C3",
    metric: "Real-time decisioning · risk scoring",
    platform: "Databricks Mosaic AI"
  }];

  /* ── Stairstep curve data (Pattern H from DMA brief) ─────────────── */
  // For a focus capability cluster: current → M3 → M4 → M5, annotated with enabling platform per step
  const STAIRSTEP_CLUSTERS = {
    "P4-data": {
      label: "Data foundation",
      current: 2.1,
      steps: [{
        m: 2,
        label: "Building",
        pct: 100,
        platforms: ["-"],
        note: "Today - fragmented across 3 cores"
      }, {
        m: 3,
        label: "Competing",
        pct: 100,
        platforms: ["SF"],
        note: "Salesforce Data Cloud - unified customer profile"
      }, {
        m: 4,
        label: "Differentiating",
        pct: 100,
        platforms: ["DB"],
        note: "Databricks Lakehouse - operational + ML-ready"
      }, {
        m: 5,
        label: "Leading",
        pct: 100,
        platforms: ["DB", "SF"],
        note: "Mosaic AI on Lakehouse - real-time decisioning"
      }]
    },
    "P3-loans": {
      label: "Loan origination",
      current: 1.8,
      steps: [{
        m: 2,
        label: "Building",
        pct: 100,
        platforms: ["-"],
        note: "Today - 85% manual, 12-day cycle"
      }, {
        m: 3,
        label: "Competing",
        pct: 100,
        platforms: ["nCino"],
        note: "nCino Workflow Engine - 4-day cycle"
      }, {
        m: 4,
        label: "Differentiating",
        pct: 100,
        platforms: ["nCino", "SF"],
        note: "Service Cloud servicing layer - post-origination"
      }, {
        m: 5,
        label: "Leading",
        pct: 100,
        platforms: ["nCino", "DB"],
        note: "Mosaic AI underwriting - automated decisioning"
      }]
    }
  };

  /* ── Evidence tier definitions (T1–T8) - used for color coding ── */
  const EVIDENCE_TIERS = {
    T1: {
      label: "Primary disclosure",
      desc: "10-K · annual report · regulator filing · official press release",
      color: "var(--z-mid)",
      bg: "var(--z-ice)",
      weight: 1.00
    },
    T2: {
      label: "Earnings & investor",
      desc: "Earnings call transcript · investor day · official IR comms",
      color: "var(--m-cmp)",
      bg: "var(--z-ice)",
      weight: 0.92
    },
    T3: {
      label: "Trade press · analyst",
      desc: "WSJ · Bloomberg · industry analyst report",
      color: "var(--ph1)",
      bg: "var(--ph1-lt)",
      weight: 0.80
    },
    T4: {
      label: "Marketing claim",
      desc: "Vendor website · co-branded press · case study (entity-published)",
      color: "var(--z-org)",
      bg: "rgba(254,151,50,.14)",
      weight: 0.55
    },
    T5: {
      label: "Analyst inference",
      desc: "Estimate based on industry pattern · proxy from peer behaviour",
      color: "var(--z-dpur)",
      bg: "var(--ph0-lt)",
      weight: 0.50
    },
    T6: {
      label: "Sentiment / review",
      desc: "Glassdoor · App Store · CFPB complaints · indexed",
      color: "var(--z-purple)",
      bg: "var(--z-lav)",
      weight: 0.45
    },
    T7: {
      label: "Job posting · proxy",
      desc: "LinkedIn / Indeed listings · BLS jobs data · proxy signal",
      color: "var(--z-blue)",
      bg: "var(--ph1-lt)",
      weight: 0.42
    },
    T8: {
      label: "Social / hypothesis",
      desc: "Twitter / Reddit · low-confidence signal · hypothesis only",
      color: "var(--z-muted)",
      bg: "var(--z-lav)",
      weight: 0.25
    }
  };

  /* ── Focus areas (strategic priorities synthesised from Client Profile) ── */
  // Each focus area is a synthesis from the entity's strategic priorities,
  // referencing the Client Research Report source. Maps to many subcaps.
  const FOCUS_AREAS = [{
    id: "FA-01",
    name: "Digital Account Opening",
    description: "Member-facing originations from first click to funded account.",
    strategic_quote: "“We are investing to compress account opening from 9 minutes to under 3, with no branch dependency.”",
    source: {
      type: "Client Profile",
      page: 7,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "10-K FY2025 - Strategic Initiatives",
    subcaps: ["P2C1.1.1", "P2C1.1.2", "P2C3.1.1", "P2C3.2.1", "P4C1.2.1", "P4C1.3.1", "P4C5.1.1"],
    pillars_weight: {
      P1: 10,
      P2: 50,
      P3: 10,
      P4: 30
    },
    icon: "envelope",
    colors: ["var(--z-teal)", "var(--m-bld)"],
    illustration: "brand/illustrations/horizon_minimal_band.jpg",
    kpis: [{
      label: "Channel conversion",
      current: "2.8%",
      target: "4.2%",
      delta: "+1.4pt"
    }, {
      label: "Opening time",
      current: "9 min",
      target: "3 min",
      delta: "−66%"
    }, {
      label: "Branch dependency",
      current: "44%",
      target: "18%",
      delta: "−26pt"
    }]
  }, {
    id: "FA-02",
    name: "AI Strategy & Implementation",
    description: "From dashboards to decisioning - AI as outcomes layer, not reports.",
    strategic_quote: "“By FY27, every analyst report we run today should drive a decision; not just describe one.”",
    source: {
      type: "Client Profile",
      page: 11,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "Q1 2026 earnings call - CIO remarks",
    subcaps: ["P4C2.2.1", "P4C3.1.1", "P4C3.2.1", "P4C3.3.1", "P4C1.3.1", "P2C4.1.1"],
    pillars_weight: {
      P1: 5,
      P2: 15,
      P3: 10,
      P4: 70
    },
    icon: "sparkle",
    colors: ["var(--z-dpur)", "var(--ph0)"],
    illustration: "brand/illustrations/platform_dark_horizon.jpg",
    kpis: [{
      label: "Decisioning latency",
      current: "24h",
      target: "Real-time",
      delta: "−99%"
    }, {
      label: "AI use cases live",
      current: "0",
      target: "3",
      delta: "+3"
    }, {
      label: "Model governance",
      current: "Ad-hoc",
      target: "Formal",
      delta: "-"
    }]
  }, {
    id: "FA-03",
    name: "Data Foundation",
    description: "Unified customer data across three core systems.",
    strategic_quote: "“We need a single customer view before we add another channel to the front.”",
    source: {
      type: "Client Profile",
      page: 13,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "Annual report - IT modernization disclosure",
    subcaps: ["P4C1.1.1", "P4C1.1.2", "P4C1.2.1", "P4C1.3.1", "P4C1.4.1", "P4C4.2.1"],
    pillars_weight: {
      P1: 5,
      P2: 15,
      P3: 5,
      P4: 75
    },
    icon: "stack",
    colors: ["var(--z-mid)", "var(--z-teal)"],
    illustration: "brand/illustrations/zen_garden_dark_mint.jpg",
    kpis: [{
      label: "Customer profile",
      current: "Fragmented",
      target: "Unified",
      delta: "-"
    }, {
      label: "Data quality score",
      current: "62%",
      target: "92%",
      delta: "+30pt"
    }, {
      label: "Real-time ingestion",
      current: "0 streams",
      target: "12",
      delta: "+12"
    }]
  }, {
    id: "FA-04",
    name: "Loan Origination Modernization",
    description: "Workflow automation across nCino-on-FIS architecture.",
    strategic_quote: "“Our loan cycle is 12 days; the regional median is 5. We need to close the gap before refinance volume returns.”",
    source: {
      type: "Client Profile",
      page: 17,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "Q4 2025 10-Q - Loan portfolio commentary",
    subcaps: ["P3C2.1.1", "P3C2.2.1", "P3C2.3.1", "P3C1.1.1", "P4C1.1.3"],
    pillars_weight: {
      P1: 5,
      P2: 10,
      P3: 70,
      P4: 15
    },
    icon: "route",
    colors: ["var(--z-blue)", "var(--ph1)"],
    illustration: "brand/illustrations/mountain_ladder_climbing.jpg",
    kpis: [{
      label: "Cycle time",
      current: "12 days",
      target: "4 days",
      delta: "−66%"
    }, {
      label: "STP rate",
      current: "18%",
      target: "55%",
      delta: "+37pt"
    }, {
      label: "Exception volume",
      current: "high",
      target: "low",
      delta: "−"
    }]
  }, {
    id: "FA-05",
    name: "Customer Experience Transformation",
    description: "Omnichannel servicing - mobile-first, branch-light.",
    strategic_quote: "“Branch dependency cannot be how we serve a generation that won't visit branches.”",
    source: {
      type: "Client Profile",
      page: 21,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "Member sentiment survey - 2025 Q4",
    subcaps: ["P2C1.1.1", "P2C1.2.1", "P2C2.1.1", "P2C2.2.1", "P2C3.4.1", "P2C4.1.1"],
    pillars_weight: {
      P1: 5,
      P2: 70,
      P3: 15,
      P4: 10
    },
    icon: "users",
    colors: ["var(--z-org)", "var(--m-act)"],
    illustration: "brand/illustrations/pavilion_team_collaboration.jpg",
    kpis: [{
      label: "Mobile NPS",
      current: "12",
      target: "38",
      delta: "+26"
    }, {
      label: "App store rating",
      current: "3.4",
      target: "4.2",
      delta: "+0.8"
    }, {
      label: "Branch deflection",
      current: "32%",
      target: "50%",
      delta: "+18pt"
    }]
  }, {
    id: "FA-06",
    name: "Risk & Compliance Operations",
    description: "Continuous AML / KYC monitoring with auditable lineage.",
    strategic_quote: "“Compliance must compound - every control we add should reduce the next remediation cost.”",
    source: {
      type: "Client Profile",
      page: 25,
      doc: "FCE_DMA_Client_Profile_FINAL.docx"
    },
    financial_ref: "FRB consent order disclosure",
    subcaps: ["P1C2.1.1", "P1C2.2.1", "P4C5.1.1", "P4C5.2.1", "P4C5.3.1"],
    pillars_weight: {
      P1: 60,
      P2: 5,
      P3: 15,
      P4: 20
    },
    icon: "shield",
    colors: ["var(--z-below)", "var(--m-act-t)"],
    illustration: "brand/illustrations/staircase_figures_descending.jpg",
    kpis: [{
      label: "Open enforcement",
      current: "1 active",
      target: "0",
      delta: "−1"
    }, {
      label: "Control automation",
      current: "32%",
      target: "80%",
      delta: "+48pt"
    }, {
      label: "Audit cycle",
      current: "Annual",
      target: "Continuous",
      delta: "-"
    }]
  }];

  /* ── Roadmap initiative impacts (current vs after each phase) ── */
  // Tracks projected subcap score per phase for impact viz
  const ROADMAP_IMPACTS = {
    "REC-04": {
      initiative: "Salesforce Data Cloud",
      phase: 1,
      before: {
        P4: 2.1,
        P2: 2.5
      },
      after: {
        P4: 2.9,
        P2: 2.7
      },
      customer_impact: {
        latency: "−40%",
        profile_completeness: "+62pt",
        time_to_personalize: "−85%"
      },
      dependencies: []
    },
    "REC-09": {
      initiative: "nCino Workflow Engine",
      phase: 1,
      before: {
        P3: 3.0
      },
      after: {
        P3: 3.5
      },
      customer_impact: {
        loan_cycle: "−40%",
        exception_rate: "−24pt",
        stp_rate: "+25pt"
      },
      dependencies: []
    },
    "REC-07": {
      initiative: "Marketing Cloud + Twilio Engage",
      phase: 2,
      before: {
        P2: 2.7
      },
      after: {
        P2: 3.4
      },
      customer_impact: {
        branch_deflection: "+18pt",
        journey_attribution: "+100%",
        retention: "+9pt"
      },
      dependencies: ["REC-04"]
    },
    "REC-18": {
      initiative: "Mobile self-service uplift",
      phase: 2,
      before: {
        P2: 3.4
      },
      after: {
        P2: 3.8
      },
      customer_impact: {
        app_rating: "+0.8",
        branch_visits: "−22%",
        nps: "+15"
      },
      dependencies: ["REC-04", "REC-07"]
    },
    "REC-14": {
      initiative: "Mosaic AI on Databricks",
      phase: 3,
      before: {
        P4: 2.9,
        P2: 3.8
      },
      after: {
        P4: 3.8,
        P2: 4.2
      },
      customer_impact: {
        decision_latency: "Real-time",
        model_governance: "Formal",
        risk_score: "+18pt"
      },
      dependencies: ["REC-04", "REC-14"]
    }
  };

  /* ── Issue → subcap cap mapping (for heatmap issues overlay) ── */
  // Visible reference of which subcaps each issue caps and by how much
  const ISSUE_CAPS = {
    "IS-014": {
      caps: {
        "P1C2.2.1": 3.0,
        "P4C5.2.1": 3.0,
        "P4C5.3.1": 3.0
      }
    },
    "IS-021": {
      caps: {
        "P4C1.1.1": 2.5,
        "P4C1.1.2": 2.5,
        "P4C1.3.1": 2.5,
        "P2C3.1.1": 2.5
      }
    },
    "IS-027": {
      caps: {
        "P2C1.1.1": 3.5,
        "P2C1.2.1": 3.5
      }
    }
  };

  /* ── Notifications (for the bell icon) ── */
  const NOTIFICATIONS = LIVE ? [] : [{
    id: "N-01",
    kind: "alert",
    title: "8 new thin-evidence alerts",
    body: "Farm Credit East · Batch 4 just ingested",
    when: "2 min ago",
    entity: "fce-001",
    route: "/alerts"
  }, {
    id: "N-02",
    kind: "completion",
    title: "Synovus run completed",
    body: "Overall 3.0 · 5 alerts open",
    when: "1 h ago",
    entity: "syn-001",
    route: "/clients/syn-001/overview"
  }, {
    id: "N-03",
    kind: "system",
    title: "Drive crawl complete",
    body: "187 candidates · 6 routed to audit",
    when: "2 h ago",
    entity: null,
    route: "/admin/import/audit"
  }, {
    id: "N-04",
    kind: "completion",
    title: "SL Green run completed",
    body: "Overall 3.1 · 3 alerts open",
    when: "8 h ago",
    entity: "slg-001",
    route: "/clients/slg-001/overview"
  }, {
    id: "N-05",
    kind: "alert",
    title: "Citizens Financial scoring started",
    body: "Batch 2 / 6 in progress",
    when: "1 d ago",
    entity: "ctzn-001",
    route: "/clients/ctzn-001/overview"
  }];

  /* ── Tech stack entries (5-layer architecture: L1 Strategy · L2 Operations · L3 Customer engagement · L4 Data · L5 Infrastructure) ──────────────────────────────────────────── */
  const TS_LAYER_FIX = {
    L2: "OPS",
    L3: "CUST",
    L4: "DATA",
    L5: "INFRA"
  };
  const TECH_STACK = [
  // L2 Operations & core banking
  {
    id: "TS-01",
    name: "FIS Profile (legacy core)",
    layer: "L2",
    layer_full: "Operations & core banking",
    status: "CONFIRMED",
    source: ["Annual report", "Explorium"],
    since: "2018-01",
    evidence: ["E-141"],
    subcaps_impact: ["P3C1.1.1", "P3C2.1.2"],
    note: "Legacy core · in migration to nCino · 47 branches",
    peer_coverage: 0.31,
    dma_pillar: "P3"
  }, {
    id: "TS-02",
    name: "nCino Loan Origination",
    layer: "L2",
    layer_full: "Operations & core banking",
    status: "CONFIRMED",
    source: ["Explorium", "Press release", "Job posting"],
    since: "2025-Q3",
    evidence: ["E-047", "E-089"],
    subcaps_impact: ["P2C1.1.2", "P3C2.3.1", "P4C1.1.3"],
    note: "LOS go-live Q3 2025 · agricultural lending focus · 5 admin roles open",
    peer_coverage: 0.44,
    dma_pillar: "P3"
  }, {
    id: "TS-03",
    name: "MuleSoft / integration bus",
    layer: "L2",
    layer_full: "Operations & core banking",
    status: "ABSENT",
    source: ["Explorium"],
    since: null,
    evidence: [],
    subcaps_impact: ["P4C1.1.3"],
    note: "No integration platform detected · API gap between FIS Profile and nCino · IMP-001",
    peer_coverage: 0.46,
    dma_pillar: "P4"
  },
  // L3 Customer engagement
  {
    id: "TS-04",
    name: "Member digital banking portal",
    layer: "L3",
    layer_full: "Customer engagement",
    status: "INFERRED",
    source: ["Assessment", "Job posting"],
    since: "2021-Q1",
    evidence: ["E-103"],
    subcaps_impact: ["P2C1.1.1"],
    note: "Custom-built · no vendor platform detected",
    peer_coverage: 0.22,
    dma_pillar: "P2"
  }, {
    id: "TS-05",
    name: "Salesforce Sales Cloud / FSC",
    layer: "L3",
    layer_full: "Customer engagement",
    status: "ABSENT",
    primary_gap: true,
    source: ["Explorium"],
    since: null,
    evidence: [],
    subcaps_impact: ["P2C2.1.1", "P2C4.1.2"],
    note: "No CRM detected · biggest L3 gap · blocks Member 360 + pipeline mgmt",
    peer_coverage: 0.66,
    dma_pillar: "P2"
  }, {
    id: "TS-06",
    name: "Salesforce Marketing Cloud",
    layer: "L3",
    layer_full: "Customer engagement",
    status: "ABSENT",
    source: ["Explorium", "Job posting"],
    since: null,
    evidence: ["E-089"],
    subcaps_impact: ["P2C3.2.1"],
    note: "5 Marketing Cloud roles posted Q1 2026 - intent signal",
    peer_coverage: 0.39,
    dma_pillar: "P2"
  }, {
    id: "TS-07",
    name: "Agentforce (AI service)",
    layer: "L3",
    layer_full: "Customer engagement",
    status: "ABSENT",
    source: ["Explorium"],
    since: null,
    evidence: [],
    subcaps_impact: ["P2C4.3.1"],
    note: "No AI service deployed · nCino go-live = natural integration window",
    peer_coverage: 0.12,
    dma_pillar: "P2"
  }, {
    id: "TS-08",
    name: "Twilio Engage",
    layer: "L3",
    layer_full: "Customer engagement",
    status: "ABSENT",
    source: ["Explorium"],
    since: null,
    evidence: [],
    subcaps_impact: ["P2C1.2.1"],
    note: "No omnichannel comms platform",
    peer_coverage: 0.27,
    dma_pillar: "P2"
  },
  // L4 Data & analytics
  {
    id: "TS-09",
    name: "Tableau Cloud",
    layer: "L4",
    layer_full: "Data & analytics",
    status: "CONFIRMED",
    source: ["Press release"],
    since: "2023-04",
    evidence: ["E-250", "E-283"],
    subcaps_impact: ["P4C2.1.1", "P4C2.2.1"],
    note: "Enterprise rollout · 1,800 users",
    peer_coverage: 0.72,
    dma_pillar: "P4"
  }, {
    id: "TS-10",
    name: "Power BI (limited)",
    layer: "L4",
    layer_full: "Data & analytics",
    status: "INFERRED",
    source: ["Job posting"],
    since: "2024-Q2",
    evidence: [],
    subcaps_impact: ["P4C2.4.1"],
    note: "Power BI skills in 3 finance roles · not confirmed as enterprise",
    peer_coverage: 0.41,
    dma_pillar: "P4"
  }, {
    id: "TS-11",
    name: "Salesforce Data Cloud / CDP",
    layer: "L4",
    layer_full: "Data & analytics",
    status: "ABSENT",
    primary_gap: true,
    source: ["Explorium"],
    since: null,
    evidence: ["E-112"],
    subcaps_impact: ["P4C1.2.1", "P4C1.3.1"],
    note: "Prerequisite for unified member profile and Agentforce",
    peer_coverage: 0.18,
    dma_pillar: "P4"
  }, {
    id: "TS-12",
    name: "Databricks / Mosaic AI",
    layer: "L4",
    layer_full: "Data & analytics",
    status: "ABSENT",
    source: ["Explorium"],
    since: null,
    evidence: [],
    subcaps_impact: ["P4C2.3.1", "P4C3.1.1"],
    note: "No ML platform · advanced analytics gap",
    peer_coverage: 0.22,
    dma_pillar: "P4"
  },
  // L5 Infrastructure
  {
    id: "TS-13",
    name: "Microsoft Azure",
    layer: "L5",
    layer_full: "Infrastructure & cloud",
    status: "CONFIRMED",
    source: ["Job posting"],
    since: "2022-Q4",
    evidence: ["E-112"],
    subcaps_impact: ["P4C4.1.1"],
    note: "Primary cloud · 200+ engineers tagged",
    peer_coverage: 0.61,
    dma_pillar: "P4"
  }, {
    id: "TS-14",
    name: "Okta (Identity)",
    layer: "L5",
    layer_full: "Infrastructure & cloud",
    status: "CONFIRMED",
    source: ["Job posting"],
    since: "2021-Q2",
    evidence: [],
    subcaps_impact: ["P4C5.1.1"],
    note: "Enterprise IDP · workforce + customer-facing",
    peer_coverage: 0.71,
    dma_pillar: "P4"
  }];

  /* ── Entities ────────────────────────────────────────────────────── */
  // Six entities - mix of Phase 0 (DRIVE_PARSE) and Phase 1 (PROJECT_API)
  const ENTITIES = LIVE ? LIVE.entities || [] : [{
    id: "fce-001",
    slug: "farm-credit-east",
    name: "Farm Credit East",
    domain: "farmcrediteast.com",
    ticker: null,
    subvertical: "FARM_CREDIT",
    size_tier: "MEDIUM",
    assets: 11.3e9,
    hq: "Enfield, CT",
    footprint: ["CT", "NY", "NJ", "MA", "NH"],
    regulator: "Farm Credit Administration",
    license: "Federal land bank",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: "2026-06-01",
    assessment_id: "DMA-ASM-FCE-20260601-0001",
    overall: 2.8,
    pillar_scores: {
      P1: 3.2,
      P2: 2.5,
      P3: 3.0,
      P4: 2.1
    },
    open_alerts: 8,
    oss: {
      SF: 82,
      DB: 41,
      TBL: 24,
      TW: 36,
      nCino: 28
    },
    employees: 1900,
    branches: 25,
    cagr: 0.082,
    trend: "ACCELERATING",
    runs: [{
      id: "DMA-ASM-FCE-20260601-0001",
      date: "2026-06-01",
      status: "ACTIVE",
      data_source: "PROJECT_API",
      overall: 2.8,
      evidence_mode: "HYBRID",
      subcap_count: 708
    }, {
      id: "DMA-ASM-FCE-20260201-0001",
      date: "2026-02-01",
      status: "SUPERSEDED",
      data_source: "PROJECT_API",
      overall: 2.6,
      evidence_mode: "INTERNAL",
      subcap_count: 708
    }, {
      id: "DMA-ASM-FCE-20251001-0001",
      date: "2025-10-01",
      status: "SUPERSEDED",
      data_source: "DRIVE_PARSE",
      overall: 2.4,
      evidence_mode: "PUBLIC",
      subcap_count: 580
    }]
  }, {
    id: "slg-001",
    slug: "sl-green",
    name: "SL Green Realty",
    domain: "slgreen.com",
    ticker: "SLG",
    subvertical: "REIT",
    size_tier: "LARGE",
    assets: 18.5e9,
    hq: "New York, NY",
    footprint: ["NY"],
    regulator: "-",
    license: "-",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: "2026-05-12",
    assessment_id: "DMA-ASM-SLGRN-20260512-0001",
    overall: 3.1,
    pillar_scores: {
      P1: 3.3,
      P2: 2.9,
      P3: 3.0,
      P4: 3.2
    },
    open_alerts: 3,
    oss: {
      SF: 51,
      DB: 64,
      TBL: 33,
      TW: 18,
      nCino: 6
    },
    employees: 1100,
    branches: 0,
    cagr: 0.041,
    trend: "STABLE",
    runs: [{
      id: "DMA-ASM-SLGRN-20260512-0001",
      date: "2026-05-12",
      status: "ACTIVE",
      data_source: "PROJECT_API",
      overall: 3.1,
      evidence_mode: "HYBRID",
      subcap_count: 708
    }]
  }, {
    id: "ful-001",
    slug: "fulton-bank",
    name: "Fulton Bank",
    domain: "fultonbank.com",
    ticker: "FULT",
    subvertical: "REGIONAL_BANK",
    size_tier: "LARGE",
    assets: 27.6e9,
    hq: "Lancaster, PA",
    footprint: ["PA", "NJ", "MD", "DE", "VA"],
    regulator: "OCC",
    license: "National bank",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: "2026-04-22",
    assessment_id: "DMA-ASM-FULT-20260422-0001",
    overall: 2.6,
    pillar_scores: {
      P1: 2.7,
      P2: 2.4,
      P3: 2.5,
      P4: 2.7
    },
    open_alerts: 12,
    oss: {
      SF: 76,
      DB: 58,
      TBL: 28,
      TW: 44,
      nCino: 51
    },
    employees: 3400,
    branches: 198,
    cagr: 0.054,
    trend: "STABLE",
    runs: [{
      id: "DMA-ASM-FULT-20260422-0001",
      date: "2026-04-22",
      status: "ACTIVE",
      data_source: "PROJECT_API",
      overall: 2.6,
      evidence_mode: "HYBRID",
      subcap_count: 708
    }, {
      id: "DMA-ASM-FULT-20251110-0001",
      date: "2025-11-10",
      status: "SUPERSEDED",
      data_source: "DRIVE_PARSE",
      overall: 2.4,
      evidence_mode: "PUBLIC",
      subcap_count: 590
    }]
  }, {
    id: "zb-001",
    slug: "zions-bancorporation",
    name: "Zions Bancorporation",
    domain: "zionsbancorporation.com",
    ticker: "ZION",
    subvertical: "REGIONAL_BANK",
    size_tier: "LARGE",
    assets: 87.9e9,
    hq: "Salt Lake City, UT",
    footprint: ["UT", "CA", "NV", "AZ", "CO", "WA", "ID", "TX"],
    regulator: "OCC",
    license: "National bank holding co.",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: "2026-05-03",
    assessment_id: "DMA-ASM-ZION-20260503-0001",
    overall: 3.4,
    pillar_scores: {
      P1: 3.7,
      P2: 3.5,
      P3: 3.2,
      P4: 3.2
    },
    open_alerts: 2,
    oss: {
      SF: 38,
      DB: 47,
      TBL: 14,
      TW: 22,
      nCino: 18
    },
    employees: 9700,
    branches: 414,
    cagr: 0.035,
    trend: "STABLE",
    runs: [{
      id: "DMA-ASM-ZION-20260503-0001",
      date: "2026-05-03",
      status: "ACTIVE",
      data_source: "PROJECT_API",
      overall: 3.4,
      evidence_mode: "HYBRID",
      subcap_count: 708
    }]
  }, {
    id: "pcan-001",
    slug: "payments-canada",
    name: "Payments Canada",
    domain: "payments.ca",
    ticker: null,
    subvertical: "FINTECH_SAAS",
    size_tier: "MEDIUM",
    assets: 0,
    hq: "Ottawa, ON",
    footprint: ["CA"],
    regulator: "Bank of Canada",
    license: "Designated payment system",
    status: "ACTIVE",
    data_source: "DRIVE_PARSE",
    assessment_date: "2025-09-18",
    assessment_id: "DMA-ASM-PMTCAN-20250918-0001",
    overall: 2.2,
    pillar_scores: {
      P1: 2.8,
      P2: 1.9,
      P3: 2.4,
      P4: 1.8
    },
    open_alerts: 14,
    oss: {
      SF: 43,
      DB: 71,
      TBL: 49,
      TW: 12,
      nCino: 8
    },
    employees: 480,
    branches: 0,
    cagr: null,
    trend: "VARIABLE",
    runs: [{
      id: "DMA-ASM-PMTCAN-20250918-0001",
      date: "2025-09-18",
      status: "ACTIVE",
      data_source: "DRIVE_PARSE",
      overall: 2.2,
      evidence_mode: "PUBLIC",
      subcap_count: 612
    }],
    drive_note: "Phase 0 - parsed from research handoff Sep 2025. Data completeness may vary from a Phase 1 structured run."
  }, {
    id: "syn-001",
    slug: "synovus",
    name: "Synovus Financial",
    domain: "synovus.com",
    ticker: "SNV",
    subvertical: "REGIONAL_BANK",
    size_tier: "LARGE",
    assets: 60.3e9,
    hq: "Columbus, GA",
    footprint: ["GA", "AL", "FL", "SC", "TN", "NC"],
    regulator: "Federal Reserve / FDIC",
    license: "State member bank",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: "2026-05-25",
    assessment_id: "DMA-ASM-SNV-20260525-0001",
    overall: 3.0,
    pillar_scores: {
      P1: 3.1,
      P2: 3.2,
      P3: 2.8,
      P4: 2.9
    },
    open_alerts: 5,
    oss: {
      SF: 64,
      DB: 51,
      TBL: 19,
      TW: 31,
      nCino: 26
    },
    employees: 4900,
    branches: 244,
    cagr: 0.061,
    trend: "STABLE",
    runs: [{
      id: "DMA-ASM-SNV-20260525-0001",
      date: "2026-05-25",
      status: "ACTIVE",
      data_source: "PROJECT_API",
      overall: 3.0,
      evidence_mode: "HYBRID",
      subcap_count: 708
    }],
    in_progress: false
  }, {
    id: "ctzn-001",
    slug: "citizens-financial",
    name: "Citizens Financial Group",
    domain: "citizensbank.com",
    ticker: "CFG",
    subvertical: "REGIONAL_BANK",
    size_tier: "ENTERPRISE",
    assets: 222.3e9,
    hq: "Providence, RI",
    footprint: ["RI", "MA", "CT", "NJ", "NY", "PA", "OH", "NH", "DE", "VT", "FL"],
    regulator: "Federal Reserve",
    license: "State member bank",
    status: "ACTIVE",
    data_source: "PROJECT_API",
    assessment_date: null,
    assessment_id: "DMA-ASM-CFG-20260603-0001",
    overall: null,
    pillar_scores: null,
    open_alerts: 0,
    oss: null,
    employees: 18000,
    branches: 1100,
    cagr: 0.025,
    trend: "STABLE",
    runs: [{
      id: "DMA-ASM-CFG-20260603-0001",
      date: "2026-06-03",
      status: "RESEARCH_IN_PROGRESS",
      data_source: "PROJECT_API",
      overall: null,
      evidence_mode: "-",
      subcap_count: 0,
      current_batch: 2
    }],
    in_progress: true
  }];

  /* ── Subcaps per entity ──────────────────────────────────────────── */
  // For prototype: pre-generate subcaps for the focused entity (FCE),
  // then derive for others using their pillar scores.
  function scoresForEntity(e) {
    return function (catId) {
      if (!e.pillar_scores) return 2.5;
      const p = catId.slice(0, 2);
      const base = e.pillar_scores[p] || 2.5;
      const wig = catId.charCodeAt(3) * 31 % 7 / 12 - 0.3;
      return base + wig;
    };
  }
  ENTITIES.forEach(e => {
    if (!LIVE && e.pillar_scores) {
      // mock-only: the preview generates plausible cells. A LIVE entity
      // renders only what the serving tier promoted — synthesising cells
      // from real pillar scores would be fabricated data on a real client.
      e.subcaps = makeSubcaps(scoresForEntity(e));
    } else {
      e.subcaps = e.subcaps || [];
    }
  });

  /* ── Thin evidence alerts ───────────────────────────────────────── */
  function buildAlerts() {
    const alerts = [];
    ENTITIES.forEach(e => {
      if (!e.subcaps) return;
      e.subcaps.forEach(s => {
        if (s.thin) {
          alerts.push({
            id: `AL-${e.id}-${s.id}`,
            entity_id: e.id,
            subcap_id: s.id,
            subcap_name: s.name,
            evidence_count: s.evidence_count,
            severity: s.evidence_count === 0 ? "HIGH" : "MEDIUM",
            status: "OPEN",
            recommended_action: s.evidence_count === 0 ? "PROXY_ESCALATION" : "TIER_UPGRADE",
            proxy_searched: s.evidence_count > 1,
            created_at: e.assessment_date
          });
        }
      });
    });
    return alerts;
  }

  /* ── QA gates ───────────────────────────────────────────────────── */
  const QA_GATES = LIVE ? [] : [{
    id: "G01",
    name: "Source diversity",
    status: "PASS",
    evidence: "Evidence across T1-T7 tiers"
  }, {
    id: "G02",
    name: "Peer set integrity",
    status: "PASS",
    evidence: "5 named peers locked for subvertical"
  }, {
    id: "G03",
    name: "Subcap coverage",
    status: "PASS",
    evidence: "708/708 subcaps scored"
  }, {
    id: "G04",
    name: "Evidence per subcap",
    status: "FAIL",
    evidence: "8 subcaps below threshold of 3"
  }, {
    id: "G05",
    name: "Confidence calibration",
    status: "PASS",
    evidence: "Confidence distribution within bounds"
  }, {
    id: "G06",
    name: "Issue register coverage",
    status: "PASS",
    evidence: "4 active issues mapped"
  }, {
    id: "G07",
    name: "Recommendations grounded",
    status: "PASS",
    evidence: "5/5 recommendations have ≥2 E-IDs"
  }, {
    id: "G08",
    name: "Platform mapping",
    status: "PASS",
    evidence: "All subcaps with score <3.0 mapped"
  }, {
    id: "G09",
    name: "Internal-only flags",
    status: "PASS",
    evidence: "Customer-safe fields verified"
  }, {
    id: "G10",
    name: "Schema version",
    status: "PASS",
    evidence: "Framework v5.5"
  }];

  /* ── Import audit ───────────────────────────────────────────────── */
  const IMPORT_AUDIT = LIVE ? [] : [{
    id: "IA-01",
    filename: "Nyumba_Zetu_Final_Research_Report.gdoc",
    rules: ["R02", "R03"],
    status: "EXCLUDED",
    owner: "dma@zennify.com",
    modifiedTime: "2025-08-04",
    entity: "-",
    rationale: "PropTech (Nairobi) - non-FSI"
  }, {
    id: "IA-02",
    filename: "DMA_Assessment_Report_ClientX.gdoc",
    rules: ["R05"],
    status: "REVIEW",
    owner: "john.smith@clientx.com",
    modifiedTime: "2026-05-12",
    entity: "ClientX (inferred)",
    rationale: "Outside @zennify.com domain"
  }, {
    id: "IA-03",
    filename: "Legacy_Assessment_STCU_Framework_v5.0.gdoc",
    rules: ["R06"],
    status: "REVIEW",
    owner: "dma@zennify.com",
    modifiedTime: "2024-03-21",
    entity: "STCU (inferred)",
    rationale: "Pre-v5.5 schema"
  }, {
    id: "IA-04",
    filename: "Test_Assessment_Run.gdoc",
    rules: ["R01"],
    status: "EXCLUDED",
    owner: "dma@zennify.com",
    modifiedTime: "2025-09-02",
    entity: "-",
    rationale: "Contains 'Test' in filename"
  }, {
    id: "IA-05",
    filename: "DMA_Assessment_Report_Template_v3.docx",
    rules: ["R04"],
    status: "EXCLUDED",
    owner: "dma@zennify.com",
    modifiedTime: "2024-12-01",
    entity: "-",
    rationale: "Unfilled template tokens"
  }, {
    id: "IA-06",
    filename: "Ag_Lending_Solution_Blueprint_v2.gdoc",
    rules: ["R02"],
    status: "EXCLUDED",
    owner: "dma@zennify.com",
    modifiedTime: "2025-07-15",
    entity: "-",
    rationale: "No Assessment ID - non-DMA artifact"
  }];

  /* ── Pending review entities (Phase 0) ──────────────────────────── */
  const PENDING_REVIEW = LIVE ? LIVE.pending_review || [] : [{
    id: "PR-01",
    inferred_name: "Provident Bank",
    inferred_subvertical: "REGIONAL_BANK",
    confidence: 0.78,
    signal: "Entity name from document header",
    drive_file: "DMA_Assessment_Report_ProvBank.gdoc",
    date: "2026-06-04"
  }, {
    id: "PR-02",
    inferred_name: "United FCS",
    inferred_subvertical: "FARM_CREDIT",
    confidence: 0.72,
    signal: "Filename token extraction",
    drive_file: "United_FCS_Assessment_FINAL.gdoc",
    date: "2026-06-02"
  }];

  /* ── Peer benchmarks (selected) ─────────────────────────────────── */
  const PEER_SETS = {
    FARM_CREDIT: {
      peers: ["Farm Credit Mid-America", "AgFirst", "CoBank", "Northwest Farm Credit", "American AgCredit"]
    },
    REGIONAL_BANK: {
      peers: ["First Citizens", "M&T Bank", "Synovus", "BankUnited", "Pinnacle Financial"]
    },
    REIT: {
      peers: ["Boston Properties", "Vornado", "Brookfield Property", "Empire State Realty", "Kilroy Realty"]
    },
    FINTECH_SAAS: {
      peers: ["Plaid", "Marqeta", "Stripe", "Adyen", "FIS"]
    }
  };

  /* ── Subvertical labels ─────────────────────────────────────────── */
  // Production divergence: live sub-vertical labels merge over the mock
  // vocabulary (the API derives them from the promoted entities).
  const SUBVERTICAL_LABEL = {
    REGIONAL_BANK: "Regional Bank",
    FARM_CREDIT: "Farm Credit",
    REIT: "REIT",
    INSURANCE_CARRIER: "Insurance Carrier",
    INSURANCE_BROKER: "Insurance Broker",
    WEALTH_RIA: "Wealth / RIA",
    ASSET_MANAGER: "Asset Manager",
    FINTECH_SAAS: "FinTech / SaaS",
    CU: "Credit Union"
  };
  Object.assign(SUBVERTICAL_LABEL, LIVE && LIVE.subvertical_labels || {});

  /* ── Active runs (in-progress dashboard strip) ───────────────────── */
  const ACTIVE_RUNS = LIVE ? LIVE.active_runs || [] : [{
    entity_id: "ctzn-001",
    current_batch: 2,
    started: "2026-06-03 09:12",
    eta_min: 38
  }];

  /* ── Cross-entity pattern (for D6) ──────────────────────────────── */
  const PATTERNS = LIVE ? [] : [{
    subvertical: "REGIONAL_BANK",
    category: "P4C3",
    title: "AI & Decisioning <2.5 in 67% of cohort",
    count: 4,
    total: 6
  }, {
    subvertical: "REGIONAL_BANK",
    category: "P4C1",
    title: "Data Foundation <2.5 in 50% of cohort",
    count: 3,
    total: 6
  }, {
    subvertical: "FARM_CREDIT",
    category: "P3C2",
    title: "Loan Origination workflows <2.5 in 60%",
    count: 3,
    total: 5
  }];

  /* ═══════════════════════════════════════════════════════════════════
     NEW-CARD DATA  ·  every block below is keyed to the flagship entity
     and tagged with the canonical deliverable file it extracts from.
     See SOURCES.md for the full field-level map + entity-alias table.
     ═══════════════════════════════════════════════════════════════════ */

  /* ── Financial trajectory ──────────────────────────────────────────
     SOURCE: 00_entity_profile/financial_baseline.json + entity_profile.json
     FIELDS: total_assets[], net_income[], nim[], employees, branches, fy[] */
  const FINANCIALS = {
    "fce-001": {
      currency: "USD",
      unit: "B",
      fy: ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"],
      total_assets: [9.8, 10.4, 11.1, 11.6, 12.2],
      // $B
      net_income_m: [188, 214, 199, 221, 243],
      // $M
      nim_pct: [3.05, 3.12, 2.98, 3.04, 3.10],
      employees: [1640, 1680, 1710, 1755, 1788],
      branches: 64,
      regulator: "FCA",
      geography: "NY · NJ · CT · MA · NH (5 states)",
      headline: "$12.2B assets · FY2025",
      events: [{
        fy: "FY2023",
        label: "nCino core migration announced"
      }, {
        fy: "FY2025",
        label: "CDO hired · data transformation"
      }]
    }
  };

  /* ── Multi-source sentiment scorecard ──────────────────────────────
     SOURCE: 08_appendices/A6_sentiment_data.csv  (naming varies: A6_Sentiment_Analysis.csv, A9_sentiment_data.csv)
     plus report_analysis.json.sentiment{}.  Normalize every row to 5.0 scale.
     INTERNAL-ONLY: omitted under view=customer. */
  const SENTIMENT = {
    "fce-001": {
      employee: [{
        source: "Glassdoor",
        metric: "Overall",
        score: 3.6,
        scale: 5,
        n: 312
      }, {
        source: "Glassdoor",
        metric: "CEO approval",
        score: 3.9,
        scale: 5
      }, {
        source: "Glassdoor",
        metric: "Culture & values",
        score: 3.5,
        scale: 5
      }, {
        source: "Indeed",
        metric: "Overall",
        score: 3.4,
        scale: 5,
        n: 188
      }],
      customer: [{
        source: "App Store",
        metric: "Mobile app",
        score: 2.9,
        scale: 5,
        n: 1240,
        flag: "below_peer"
      }, {
        source: "Google Play",
        metric: "Mobile app",
        score: 3.1,
        scale: 5,
        n: 870
      }, {
        source: "BBB",
        metric: "Customer rating",
        score: 3.3,
        scale: 5
      }],
      industry_avg: 3.5,
      b2b_b2c_gap: true
    }
  };

  /* ── Coverage by pillar (evidence completeness) ────────────────────
     SOURCE: 03_scoring_workbook/export_coverage_stats.csv + research_handoff.json.coverage_percentage
     80% hard-gate is a UI constant, not from data. */
  const COVERAGE_STATS = {
    "fce-001": {
      overall_pct: 96,
      by_pillar: [{
        pillar: "P1",
        pct: 98,
        subcaps: 71,
        scored: 71
      }, {
        pillar: "P2",
        pct: 94,
        subcaps: 290,
        scored: 273
      }, {
        pillar: "P3",
        pct: 97,
        subcaps: 165,
        scored: 160
      }, {
        pillar: "P4",
        pct: 95,
        subcaps: 182,
        scored: 173
      }],
      gate_pct: 80
    }
  };

  /* ── Capability ceiling + uncertainty bands ────────────────────────
     SOURCE: 02_research_workbook/uncertainty_bands.json  { <cat>: {base, modifiers[], total} }
     ceiling ← 06_peers/peer_comparison_table.csv <ENTITY>_Ceiling column */
  const UNCERTAINTY_BANDS = {
    "fce-001": {
      P1C1: {
        ceiling: 3.0,
        band: 0.3,
        modifiers: [],
        evidence: ["E-047"],
        rationale: "Digital strategy is documented in the annual report; ceiling set at M3 because execution cadence is confirmed but no innovation-lab or dedicated transformation office is evidenced."
      },
      P1C2: {
        ceiling: 3.5,
        band: 0.4,
        modifiers: [],
        evidence: ["E-218"],
        rationale: "Governance ceiling constrained by the open AML consent order — remediation is on-track, so the band is moderate, but the cap holds until closure is confirmed."
      },
      P1C3: {
        ceiling: 2.5,
        band: 0.4,
        modifiers: ["+0.1 no innovation lab confirmed"],
        evidence: ["E-047", "E-302"],
        rationale: "Operating-model maturity inferred from org disclosures; upside if an innovation function is later evidenced."
      },
      P1C4: {
        ceiling: 3.0,
        band: 0.5,
        modifiers: [],
        evidence: ["E-203"],
        rationale: "New CDO hire raises the leadership ceiling, but tenure is <6 months so the band is wide until direction is set."
      },
      P2C1: {
        ceiling: 3.0,
        band: 0.4,
        modifiers: [],
        evidence: ["E-271", "E-311"],
        rationale: "Channel ceiling anchored by app-store sentiment and the Forrester mobile-servicing lag; both are indirect, hence the band."
      },
      P2C2: {
        ceiling: 3.0,
        band: 0.4,
        modifiers: ["+0.1 STP rate unknown"],
        evidence: ["E-271"],
        rationale: "Digital service model inferred from customer reviews; straight-through-processing rate is unconfirmed."
      },
      P2C3: {
        ceiling: 2.0,
        band: 0.5,
        modifiers: ["+0.1 channel utilization unknown"],
        evidence: ["E-340"],
        rationale: "Customer-journey ceiling low — self-service gaps evidenced only by community/social signal (T8), so confidence is low and band wide."
      },
      P2C4: {
        ceiling: 2.5,
        band: 0.5,
        modifiers: [],
        evidence: ["E-311"],
        rationale: "Personalization ceiling from analyst benchmark; no first-party evidence of a personalization engine."
      },
      P3C1: {
        ceiling: 3.0,
        band: 0.4,
        modifiers: [],
        evidence: ["E-047"],
        rationale: "Workflow-automation ceiling supported by the nCino migration disclosure."
      },
      P3C2: {
        ceiling: 2.0,
        band: 0.6,
        modifiers: ["+0.2 manual process depth uncertain"],
        evidence: ["E-236"],
        rationale: "Loan-origination ceiling constrained by Glassdoor operations reviews describing manual processing; depth of manual work is uncertain, so the band is the widest on the board."
      },
      P4C1: {
        ceiling: 2.5,
        band: 0.5,
        modifiers: ["+0.1 core consolidation in-flight"],
        evidence: ["E-047", "E-141"],
        rationale: "Data-foundation ceiling capped by the three-core fragmentation disclosed in the 10-K; upside once consolidation completes."
      },
      P4C2: {
        ceiling: 3.5,
        band: 0.3,
        modifiers: [],
        evidence: ["E-250"],
        rationale: "Analytics ceiling is the highest — Tableau enterprise rollout is a confirmed press-release fact (T2)."
      },
      P4C3: {
        ceiling: 2.0,
        band: 0.6,
        modifiers: ["+0.2 no AI deploy evidence"],
        evidence: ["E-283"],
        rationale: "AI-decisioning ceiling low — only a Tableau Pulse hiring signal; no deployed decisioning evidence, so provisional."
      },
      P4C5: {
        ceiling: 3.0,
        band: 0.4,
        modifiers: [],
        evidence: ["E-218"],
        rationale: "Security & resiliency ceiling tied to the consent-order remediation scope."
      }
    }
  };

  /* ── Evidence summary (tier counts + claim/signal mix) ─────────────
     SOURCE: 01_evidence/research_handoff.json.evidence_summary
     { total_items, tier_distribution{T1..T5}, claim_distribution, signal_distribution } */
  const EVIDENCE_SUMMARY = {
    "fce-001": {
      total_items: 110,
      total_facts: 387,
      tiers: {
        T1: 8,
        T2: 15,
        T3: 70,
        T4: 5,
        T5: 12
      },
      claims: {
        FACT: 342,
        INFERENCE: 41,
        HYPOTHESIS: 0,
        CEILING_ESTIMATE: 4
      },
      signals: {
        POSITIVE: 62,
        CONTRADICTORY: 17,
        NEGATIVE: 10,
        NEUTRAL: 21
      },
      connectors: {
        Explorium: 15,
        Clay: 3,
        Indeed: 6
      }
    }
  };

  /* ── SOURCE MAP ·  machine-readable extraction registry ────────────
     Mirrors SOURCES.md as data so a Phase-0/Phase-1 ingest script can
     iterate card→file bindings programmatically. Each card component also
     carries a data-source="<file> :: <field>" attribute on its root. */
  const SOURCE_MAP = {
    score_ring: {
      file: "03_scoring_workbook/export_pillar_summary.csv",
      fields: ["Pillar", "Score", "Weight", "Weighted"],
      transform: "Overall row = headline"
    },
    heatmap: {
      file: "03_scoring_workbook/export_category_summary.csv",
      fields: ["Category", "Score", "Subcaps", "Peer_Median", "Gap", "Priority"]
    },
    gap_waterfall: {
      file: "03_scoring_workbook/export_category_summary.csv",
      fields: ["Gap"],
      also: "06_peers/peer_comparison_table.csv::Peer_P75"
    },
    peer_ranking: {
      file: "06_peers/peer_comparison_table.csv",
      fields: ["*_Ceiling", "Peer_Median", "Peer_P25", "Peer_P75", "*_vs_Median"]
    },
    evidence_tiers: {
      file: "01_evidence/research_handoff.json",
      fields: ["evidence_summary.tier_distribution", "claim_distribution", "signal_distribution"]
    },
    coverage_by_pillar: {
      file: "03_scoring_workbook/export_coverage_stats.csv",
      also: "research_handoff.json::coverage_percentage"
    },
    ceiling_estimate: {
      file: "02_research_workbook/uncertainty_bands.json",
      fields: ["base", "modifiers", "total"],
      also: "peer_comparison_table.csv::*_Ceiling"
    },
    financial_traj: {
      file: "00_entity_profile/financial_baseline.json",
      also: "entity_profile.json"
    },
    sentiment: {
      file: "08_appendices/A6_sentiment_data.csv",
      note: "naming drifts; match 'sentiment' token; INTERNAL-ONLY"
    },
    issue_timeline: {
      file: "07_governance/issue_register.csv",
      also: "07_governance/caps_applied_log.csv"
    },
    recommendations: {
      file: "08_appendices/recommendations.json",
      alt: "08_appendices/recommendations/REC-*.json + recommendations_master.json"
    },
    tech_stack: {
      file: "08_appendices/*_Explorium_*.xlsx",
      alt: "tech_stack.json / A4_tech_stack_map.csv"
    },
    qa_badge: {
      file: "07_governance/qa_verdict.json",
      also: "run_manifest*.json"
    }
  };

  /* ── Entity aliases (ticker / short-code → canonical) ──────────────
     SOURCE: research_handoff.json.entity.name + subvertical_classification.json
     Used by ingest to canonicalize file-name tokens. See SOURCES.md §2. */
  const ENTITY_ALIASES = {
    SSB: "SouthState Corporation",
    FCNCA: "First Citizens BancShares",
    CACU: "Corporate America Credit Union",
    CWB: "Community West Bank",
    MFCU: "Members 1st FCU",
    AMH: "American Homes 4 Rent",
    VNO: "Vornado Realty Trust",
    SLG: "SL Green Realty",
    TCB: "Texas Capital Bank",
    ANBTX: "American National Bank of Texas",
    GFCU: "Global FCU",
    OZK: "Bank OZK",
    TII: "Travel Insurance International",
    VFP: "Virtuity Financial Partners",
    CIF: "CI Financial",
    VESTGEN: "VestGen Wealth Partners",
    CFR: "Frost Bank",
    ABCB: "Ameris Bank",
    ZION: "Zions Bancorporation"
  };

  /* ── Why-Now trigger signals (drillable) ───────────────────────────
     SOURCE: 01_evidence/evidence_index.json (trigger-tagged items)
             + 05_context/timeline_events.csv + report_synthesis.md.why_now
     Each signal is drillable: detail + evidence chips + timeline event + impact.
     INTERNAL rationale is stripped under view=customer (keep label + window). */
  const WHY_NOW = {
    "fce-001": [{
      id: "WN-1",
      label: "Core migration mid-flight",
      category: "core_migration",
      strength: "STRONG",
      window: "closes Q2 2026",
      confidence: "HIGH",
      claim: "FACT",
      detail: "Legacy core → nCino migration is in flight with target completion Q2 2026. The window to influence the data substrate is open now and closes at the go-live freeze — after which every change becomes a change-request against a live core, not a design decision on a greenfield one.",
      metric: "Target go-live Q2 2026 · ~2 quarters of design runway left",
      peer_context: "Synovus and First Citizens both set their Data Cloud direction during — not after — their core programs; entities that waited re-platformed twice.",
      play: "Open the Data Cloud substrate conversation in the next 60 days; frame it as underneath the new core, sequenced before FSC and Agentforce.",
      risk: "If the point-CDP decision is made post-go-live, FCE inherits the three-core fragmentation into the new core and the P4 ceiling stays capped at ~2.5 for the next cycle.",
      evidence: ["E-047", "E-141", "E-089"],
      timeline: {
        date: "2025-09",
        event: "nCino migration announced (Q1 earnings call)"
      },
      impact: "Position Data Cloud as the substrate underneath the new core — not a bolt-on after go-live."
    }, {
      id: "WN-2",
      label: "Two C-suite hires",
      category: "leadership",
      strength: "STRONG",
      window: "6–9 month policy window",
      confidence: "HIGH",
      claim: "INFERENCE",
      detail: "A new CTO (ex-Wells Fargo, Apr 2026) and CDO (ex-JPM, May 2026) are both in their first two quarters. New executives set platform direction early and lock commitments after — this is the single relationship window of the cycle where criteria are still being written.",
      metric: "2 net-new C-suite technology leaders in <90 days",
      peer_context: "In this subvertical, a new CDO's first major platform commitment has landed within 6–9 months of start date in 3 of the last 4 comparable hires.",
      play: "Align the data-foundation narrative to the CDO's public mandate; secure an executive briefing before the FY27 planning cycle closes.",
      risk: "Miss the window and the next touchpoint is a competitive RFP where FCE has already framed the requirements around a specific vendor.",
      evidence: ["E-203", "E-047"],
      timeline: {
        date: "2026-04",
        event: "CTO hire announced (LinkedIn)"
      },
      impact: "Executive sponsorship is winnable now; align the data-foundation narrative to the CDO's mandate."
    }, {
      id: "WN-3",
      label: "5 Data Cloud Architect openings",
      category: "hiring",
      strength: "LEADING",
      window: "90–120 day lead signal",
      confidence: "MEDIUM",
      claim: "INFERENCE",
      detail: "Five Data Cloud Architect roles posted in Q1 — a leading indicator the team is preparing for a customer-data-platform decision without yet committing to a vendor. The job descriptions explicitly reference building an enterprise CDP on Salesforce Data Cloud.",
      metric: "5 open reqs · CDP-specific · posted within one quarter",
      peer_context: "Zennify has observed platform commitments follow this exact hiring pattern within 90–120 days across prior engagements.",
      play: "Engage now, before headcount is hired against a point-solution (Snowflake-only or vendor-bundled) that then defines the architecture.",
      risk: "Once the architects are hired against a chosen stack, the platform decision is effectively already made in the org chart.",
      evidence: ["E-112", "E-283"],
      timeline: {
        date: "2026-01",
        event: "5 Data Cloud Architect roles posted (Explorium)"
      },
      impact: "Engage before a point-solution creates the next decade of fragmentation."
    }, {
      id: "WN-4",
      label: "Analytics outpaces decisioning",
      category: "market",
      strength: "SUPPORTING",
      window: "structural",
      confidence: "HIGH",
      claim: "FACT",
      detail: "Tableau Cloud reached ~1,800 employees in 2025, but the organization generates reports faster than it acts on them — P4C2 (analytics) sits well ahead of P4C3 (decisioning). This is a readiness signal, not a gap: the appetite for data is proven; the missing piece is the activation layer.",
      metric: "P4C2 analytics 3.1 vs P4C3 decisioning 1.8 — a 1.3-point internal gap",
      peer_context: "Peers who added a decisioning layer (Mosaic AI / Agentforce) on top of mature BI saw activation ROI in 2 quarters without re-platforming.",
      play: "Lead with activation — Data Cloud + Agentforce as the outcome layer on the existing Tableau investment; frame as 'analytics → action', not a new BI purchase.",
      risk: "Continued BI investment without activation widens the say-do gap and entrenches report-culture over decision-culture.",
      evidence: ["E-250", "E-283"],
      timeline: {
        date: "2025-11",
        event: "Tableau enterprise rollout completed (press release)"
      },
      impact: "Lead with activation (Data Cloud + Agentforce), not more BI — the reporting muscle already exists."
    }, {
      id: "WN-5",
      label: "AML consent order remediation",
      category: "regulatory",
      strength: "SUPPORTING",
      window: "18-month remediation clock",
      confidence: "HIGH",
      claim: "FACT",
      detail: "An open FRB consent order requires remediation of transaction-monitoring controls. It caps the P1 governance ceiling until closure, and it makes data lineage and quality a board-level priority — which is precisely the substrate a Data Cloud program delivers.",
      metric: "Remediation due within 18 months of the order",
      peer_context: "Remediation programs are a common on-ramp: the data-quality work required for AML doubles as the foundation for a unified customer profile.",
      play: "Tie the data-foundation business case to the remediation mandate — one investment satisfies the regulator and unlocks the CX roadmap.",
      risk: "Treating remediation as a standalone compliance spend misses the chance to fund the substrate under a board-backed mandate.",
      evidence: ["E-218"],
      timeline: {
        date: "2024-11",
        event: "FRB consent order issued"
      },
      impact: "Frame data foundation as satisfying the remediation mandate and unlocking CX in one investment."
    }]
  };

  /* Per-entity Why-Now synthesizer — every client gets relevant signals derived
     from its own scoring/evidence when no hand-authored set exists. Mirrors what
     the Gemini why_now surface would produce at view time in production. */
  function synthWhyNow(id) {
    const e = ENTITIES.find(x => x.id === id);
    if (!e || !e.subcaps || !e.subcaps.length) return WHY_NOW["fce-001"];
    const sub = SUBVERTICAL_LABEL[e.subvertical] || "peer";
    const evFor = sid => EVIDENCE.filter(ev => ev.subcaps && ev.subcaps.some(s => s.slice(0, 4) === sid.slice(0, 4))).map(ev => ev.id).slice(0, 3);
    const when = e.assessment_date ? e.assessment_date.slice(0, 7) : "recent";
    const signals = [];

    // 1 · deepest capability gap vs peer
    const gaps = e.subcaps.filter(s => s.peerMedian != null).sort((a, b) => b.peerMedian - b.score - (a.peerMedian - a.score));
    const g = gaps[0];
    if (g) {
      const cat = CATEGORIES.find(c => c.id === g.category);
      signals.push({
        id: "WN-1",
        label: `${cat && cat.name || g.category} is the deepest gap`,
        category: "market",
        strength: "STRONG",
        window: "structural",
        confidence: g.thin ? "LOW" : "MEDIUM",
        claim: "INFERENCE",
        detail: `${g.name} scores ${g.score.toFixed(1)} against a ${sub.toLowerCase()} peer median of ${g.peerMedian.toFixed(1)} — the widest gap in ${e.name}'s assessment. ${g.thin ? "Evidence is thin, so the score is provisional." : "The finding is evidence-supported."}`,
        metric: `${g.id} · ${g.score.toFixed(1)} vs peer ${g.peerMedian.toFixed(1)} (−${(g.peerMedian - g.score).toFixed(1)})`,
        peer_context: `Peers in the ${sub} cohort average ${g.peerMedian.toFixed(1)} on this capability.`,
        play: `Lead the ${cat && cat.name || "capability"} conversation with the platform candidates that close this gap fastest.`,
        risk: "Left unaddressed, this gap caps the parent pillar and compounds across dependent capabilities.",
        evidence: evFor(g.id),
        timeline: {
          date: when,
          event: "Latest DMA run"
        },
        impact: `Closing ${g.id} lifts the parent category and unblocks downstream work.`
      });
    }
    // 2 · thin-evidence coverage
    const thin = e.subcaps.filter(s => s.thin).length;
    if (thin > 0) {
      signals.push({
        id: "WN-2",
        label: `${thin} subcaps on thin evidence`,
        category: "hiring",
        strength: "LEADING",
        window: "confirm before commit",
        confidence: "MEDIUM",
        claim: "HYPOTHESIS",
        detail: `${thin} of ${e.subcaps.length} subcaps are scored on fewer than 3 evidence items. These are the highest-value questions to resolve in a first meeting — a small amount of client-provided data sharply raises confidence.`,
        metric: `${thin} thin subcaps · ${Math.round(thin / e.subcaps.length * 100)}% of assessment`,
        peer_context: "Thin areas are where public inference is weakest and a discovery call adds the most signal.",
        play: "Use the first meeting to confirm the thin subcaps; treat their scores as provisional until then.",
        risk: "Acting on provisional scores risks mis-prioritizing the roadmap.",
        evidence: [],
        timeline: {
          date: when,
          event: "Coverage from latest run"
        },
        impact: "Resolve the thin subcaps first — highest confidence-per-question."
      });
    }
    // 3 · lead platform fit
    if (e.oss) {
      const top = Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0];
      if (top) {
        const p = PLATFORMS.find(x => x.id === top[0]);
        const gapCount = e.subcaps.filter(s => s.score < 3 && s.platforms && s.platforms.includes(top[0])).length;
        signals.push({
          id: "WN-3",
          label: `${p && p.name || top[0]} is the lead platform fit`,
          category: "core_migration",
          strength: "SUPPORTING",
          window: "next planning cycle",
          confidence: "MEDIUM",
          claim: "INFERENCE",
          detail: `${p && p.name || top[0]} scores ${top[1]}/100 on fit for ${e.name}, addressing ${gapCount} subcap gap${gapCount === 1 ? "" : "s"} where the technology footprint is confirmed-absent.`,
          metric: `${p && p.name || top[0]} · ${top[1]}/100 OSS · ${gapCount} addressable gaps`,
          peer_context: "Fit score blends gap coverage, prerequisite readiness, and confirmed-absent footprint.",
          play: `Sequence the ${p && p.name || top[0]} conversation after its prerequisites are met — see the Platform tab.`,
          risk: "Introducing the platform before prerequisites are met stalls adoption.",
          evidence: [],
          timeline: {
            date: when,
            event: "Platform fit from latest run"
          },
          impact: `${p && p.name || top[0]} is the highest-leverage first platform conversation.`
        });
      }
    }
    return signals.length ? signals : WHY_NOW["fce-001"];
  }

  /* Insight-card prioritization + clustering (used by D2) ─────────────
     SOURCE: derived at view time from insight_cards.json fields —
     flag (severity) + confidence + reach (affects[]) + actionability
     (linked recommendation). Mirrors the ranker the production API
     applies before returning insight_cards. See SOURCES.md. */
  function insightPriority(c) {
    const flagW = {
      CRITICAL: 3,
      OPPORTUNITY: 2,
      MONITOR: 1
    }[c.flag] || 1;
    const confW = {
      HIGH: 3,
      MEDIUM: 2,
      LOW: 1
    }[c.confidence] || 1;
    const reach = c.affects ? c.affects.length : 0;
    const actionable = c.rec ? 1 : 0;
    const score = flagW * 100 + confW * 10 + reach * 2 + actionable * 5;
    let tier, tierLabel, tierColor;
    if (c.flag === "CRITICAL" || c.flag === "OPPORTUNITY" && c.confidence === "HIGH" && c.rec) {
      tier = 1;
      tierLabel = "Act now";
      tierColor = "below";
    } else if (c.flag === "OPPORTUNITY") {
      tier = 2;
      tierLabel = "Plan next";
      tierColor = "org";
    } else {
      tier = 3;
      tierLabel = "Watch";
      tierColor = "teal";
    }
    return {
      score,
      tier,
      tierLabel,
      tierColor,
      reach,
      actionable: !!c.rec
    };
  }

  /* ── Live registry ───────────────────────────────────────────────
     useLiveEntity installs the adapted entity here before rendering a
     client route. Read through a function, never captured in a closure:
     the object is replaced when the route changes entity, run or audience. */
  function liveEntity() {
    return typeof window !== "undefined" && window.DMA_ENTITY || null;
  }
  function liveField(id, key) {
    const L = liveEntity();
    // Guarded on identity: a stale registry from the previously viewed client
    // must not answer for this one.
    return L && (L.id === id || !id) ? L[key] === undefined ? null : L[key] : null;
  }

  /* ── EXPORT ─────────────────────────────────────────────────────── */
  window.DMA = {
    WHY_NOW,
    FINANCIALS,
    SENTIMENT,
    COVERAGE_STATS,
    UNCERTAINTY_BANDS,
    EVIDENCE_SUMMARY,
    SOURCE_MAP,
    ENTITY_ALIASES,
    PILLARS,
    PLATFORMS,
    CATEGORIES,
    VALUE_CHAINS,
    ENTITIES,
    /* Getters, not values: a client route replaces DMA_ENTITY when the
       entity, run or audience changes, and a captured array would keep
       rendering the previous client's rows. */
    get EVIDENCE() {
      return LIVE ? liveField(null, "evidence") || [] : EVIDENCE;
    },
    get INSIGHT_CARDS() {
      return LIVE ? liveField(null, "insightCards") || [] : INSIGHT_CARDS;
    },
    get RECOMMENDATIONS() {
      return LIVE ? liveField(null, "recommendations") || [] : RECOMMENDATIONS;
    },
    get ISSUES() {
      return LIVE ? liveField(null, "issues") || [] : ISSUES;
    },
    get TIMELINE_EVENTS() {
      return LIVE ? liveField(null, "timeline") || [] : TIMELINE_EVENTS;
    },
    get TECH_STACK() {
      if (LIVE) return liveField(null, "techStack") || [];
      // The fixture predates the charter's layer-key correction; mapped on
      // read so the reference data itself is not rewritten.
      return TECH_STACK.map(t => ({
        ...t,
        layer: TS_LAYER_FIX[t.layer] || t.layer
      }));
    },
    get LEADERSHIP() {
      return LIVE ? liveField(null, "leadership") || [] : LEADERSHIP;
    },
    get THOUGHT_LEADERSHIP() {
      return LIVE ? liveField(null, "thoughtLeadership") || [] : THOUGHT_LEADERSHIP;
    },
    get FOCUS_AREAS() {
      return LIVE ? liveField(null, "focusAreas") || [] : FOCUS_AREAS;
    },
    get ROADMAP() {
      return LIVE ? liveField(null, "roadmap") || [] : ROADMAP;
    },
    QA_GATES,
    IMPORT_AUDIT,
    PENDING_REVIEW,
    ACTIVE_RUNS,
    PATTERNS,
    PEER_SETS,
    SUBVERTICAL_LABEL,
    STAIRSTEP_CLUSTERS,
    EVIDENCE_TIERS,
    ROADMAP_IMPACTS,
    ISSUE_CAPS,
    NOTIFICATIONS,
    ALERTS: buildAlerts(),
    helpers: {
      maturityClass,
      maturityHex,
      maturityLabel,
      freshnessOf,
      clamp,
      round1
    },
    getEntity: id => ENTITIES.find(e => e.id === id || e.slug === id),
    /* In LIVE these resolve against the viewed entity's promoted payload, so
       an id from one client can never resolve to another's row. */
    getInsight: id => (LIVE ? liveField(null, "insightCards") || [] : INSIGHT_CARDS).find(c => c.id === id),
    getEvidence: id => (LIVE ? liveField(null, "evidence") || [] : EVIDENCE).find(e => e.id === id),
    getSubcap: (entity, id) => entity && entity.subcaps ? entity.subcaps.find(s => s.id === id) : null,
    getCategory: id => CATEGORIES.find(c => c.id === id),
    getPlatform: id => PLATFORMS.find(p => p.id === id),
    getRecommendation: id => LIVE ? (liveField(null, "recommendations") || []).find(r => r.id === id) : RECOMMENDATIONS.find(r => r.id === id) || RECS_CACHE[id],
    recsFor: id => LIVE ? liveField(id, "recommendations") || [] : recsFor(id),
    getFocusArea: id => (LIVE ? liveField(null, "focusAreas") || [] : FOCUS_AREAS).find(f => f.id === id),
    getTier: id => EVIDENCE_TIERS[id],
    /* Entity-scoped accessors. In LIVE mode they read the promoted payload
       through window.DMA_ENTITY (installed by useLiveEntity) and return
       null/[] when a section did not promote — NEVER the fixture. The
       flagship fallback below is how the fictional bank's prose used to
       reach a real client's page, and it is the reason a whole second
       renderer existed. Outside LIVE the mock answers, unchanged, so the
       prototype still runs standalone as the design reference. */
    financialsFor: id => LIVE ? liveField(id, "financials") : FINANCIALS[id] || FINANCIALS["fce-001"],
    sentimentFor: id => LIVE ? liveField(id, "sentiment") : SENTIMENT[id] || SENTIMENT["fce-001"],
    coverageFor: id => LIVE ? liveField(id, "coverage") : COVERAGE_STATS[id] || COVERAGE_STATS["fce-001"],
    uncertaintyFor: id => LIVE ? liveField(id, "uncertainty") : UNCERTAINTY_BANDS[id] || UNCERTAINTY_BANDS["fce-001"],
    evidenceSummaryFor: id => LIVE ? liveField(id, "evidenceSummary") : EVIDENCE_SUMMARY[id] || EVIDENCE_SUMMARY["fce-001"],
    sourceFor: cardId => SOURCE_MAP[cardId] || null,
    whyNowFor: id => LIVE ? liveField(id, "whyNow") : WHY_NOW[id] || synthWhyNow(id),
    /* Per-section provenance for the live run: what promoted, when, by which
       producer version. The prototype states provenance per card, so a card
       asks for its own section rather than the page's. */
    sectionStateFor: key => LIVE ? ((liveEntity() || {}).sectionState || {})[key] || null : null,
    runFor: id => LIVE ? liveField(id, "run") : null,
    startersFor: id => LIVE ? liveField(id, "starters") || [] : [],
    insightPriority,
    issueCapsFor: subcapId => {
      const out = [];
      Object.entries(ISSUE_CAPS).forEach(([iid, info]) => {
        if (info.caps[subcapId] != null) out.push({
          id: iid,
          cap: info.caps[subcapId],
          issue: ISSUES.find(x => x.id === iid)
        });
      });
      return out;
    },
    alertsForEntity: id => buildAlerts().filter(a => a.entity_id === id)
  };
})();