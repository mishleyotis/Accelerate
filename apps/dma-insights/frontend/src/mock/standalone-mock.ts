/**
 * Standalone mock API.
 *
 * The single-file `dist-standalone` build (ADR 0016 demo / visual-regression
 * surface) has no backend — every `/api/v1/*` call would otherwise hit the
 * static server's `{}` stub and render empty. This module returns realistic,
 * TYPE-CHECKED responses (it imports the real response interfaces from
 * `lib/queries`, so `tsc` rejects any shape drift) so the production React tree
 * renders fully populated — matching the prototype's content for visual parity.
 *
 * Wired into `lib/api.ts`: when `__STANDALONE__`, `api()` resolves a match here
 * before touching the network. Live builds never import this path
 * (`__STANDALONE__` is `false`, tree-shaken out).
 */
import type {
  AcquisitionOut,
  AlertOut,
  ContextResponse,
  DashboardResponse,
  EntityListResponse,
  EntityOverviewResponse,
  EntitySummary,
  EvidenceAgeOut,
  HeatmapCell,
  HeatmapResponse,
  HealthResponse,
  InsightListResponse,
  IssueRegisterOut,
  NotificationListResponse,
  PlatformCard,
  PlatformsResponse,
  QaVerdictOut,
  RunHistoryResponse,
  SafeguardGateOut,
  RunSummary,
  TimelineEventOut,
} from "@/lib/queries";

const NOW = "2026-01-15T09:00:00.000Z";
const CAT = "v7.0";

// ── Entity roster (directory + dashboard) ─────────────────────────────────
interface MockEntity {
  display_id: string;
  name: string;
  subvertical: string;
  overall: number;
  pillars: [number, number, number, number];
  alerts: number;
  in_progress?: boolean;
  source?: string;
}
const ROSTER: MockEntity[] = [
  { display_id: "richbank-community-trust-0001", name: "RichBank Community Trust", subvertical: "SV1", overall: 3.2, pillars: [3.4, 2.9, 3.1, 3.5], alerts: 2, source: "DRIVE_PARSE" },
  { display_id: "alma-bank-0002", name: "Alma Bank", subvertical: "SV1", overall: 2.6, pillars: [2.4, 2.1, 2.9, 3.0], alerts: 4, source: "DRIVE_PARSE" },
  { display_id: "wsfs-financial-0003", name: "WSFS Financial", subvertical: "SV1", overall: 3.8, pillars: [4.0, 3.6, 3.7, 3.9], alerts: 1, source: "PROJECT_API" },
  { display_id: "calprivate-bank-0004", name: "CalPrivate Bank", subvertical: "SV1", overall: 2.9, pillars: [3.1, 2.6, 2.8, 3.1], alerts: 3, source: "DRIVE_PARSE" },
  { display_id: "nicola-wealth-0005", name: "Nicola Wealth", subvertical: "SV6", overall: 3.4, pillars: [3.5, 3.2, 3.3, 3.6], alerts: 0, source: "PROJECT_API" },
  { display_id: "odlum-brown-0006", name: "Odlum Brown", subvertical: "SV6", overall: 3.0, pillars: [3.2, 2.8, 2.9, 3.1], alerts: 1, in_progress: true, source: "DRIVE_PARSE" },
];

function entitySummary(m: MockEntity): EntitySummary {
  const pillar_scores: Record<string, number> = {
    P1: m.pillars[0], P2: m.pillars[1], P3: m.pillars[2], P4: m.pillars[3],
  };
  return {
    id: `id-${m.display_id}`,
    display_id: m.display_id,
    name: m.name,
    domain: `${m.display_id.split("-")[0]}.com`,
    subvertical: m.subvertical,
    lobs: ["Commercial", "Retail"],
    status: "ACTIVE",
    last_run_at: NOW,
    last_run_request_id: `REQ-${m.display_id.slice(0, 8).toUpperCase()}`,
    owner_email: "ae@zennify.com",
    owner_name: "Mishley O.",
    updated_at: NOW,
    last_run_status: m.in_progress ? "IN_PROGRESS" : "ACTIVE",
    data_source: m.source ?? "DRIVE_PARSE",
    in_progress: !!m.in_progress,
    pillar_scores,
    overall_score: m.overall,
    subcap_count: 96,
    open_alerts: m.alerts,
    assessment_date: NOW,
    hq: "San Francisco, CA",
    top_platform: { platform_id: "salesforce", short: "SF", fit_score: 82 },
    current_batch: m.in_progress ? 3 : null,
  };
}

function runSummary(m: MockEntity): RunSummary {
  return {
    id: `run-${m.display_id}`,
    request_id: `REQ-${m.display_id.slice(0, 8).toUpperCase()}`,
    status: m.in_progress ? "IN_PROGRESS" : "ACTIVE",
    data_source: (m.source as RunSummary["data_source"]) ?? "DRIVE_PARSE",
    evidence_mode: "hybrid",
    ccg_catalog_version: CAT,
    started_at: NOW,
    completed_at: m.in_progress ? null : NOW,
    created_at: NOW,
    updated_at: NOW,
    overall_score: m.overall,
    subcap_count: 96,
  };
}

const byId = (id: string): MockEntity =>
  ROSTER.find((e) => e.display_id === id) ?? ROSTER[0];

// ── Heatmap cell generation (pillar → category → subcap) ───────────────────
const PILLARS = [
  { id: "P1", label: "Data & Analytics" },
  { id: "P2", label: "Channels & Experience" },
  { id: "P3", label: "Operations & Automation" },
  { id: "P4", label: "Governance & Risk" },
];
function band(score: number): string {
  if (score < 2) return "ACTIVATING";
  if (score < 3) return "BUILDING";
  if (score < 4) return "COMPETING";
  return "DIFFERENTIATING";
}
function heatmapCells(m: MockEntity, zoom: string): HeatmapCell[] {
  const cells: HeatmapCell[] = [];
  PILLARS.forEach((p, pi) => {
    const base = m.pillars[pi];
    if (zoom === "pillar") {
      cells.push(cell(p.id, p.label, null, base, m));
    } else {
      for (let c = 1; c <= 3; c++) {
        const cid = `${p.id}C${c}`;
        const cscore = clamp(base + (c - 2) * 0.4);
        if (zoom === "category") {
          cells.push(cell(cid, `${p.label} — Category ${c}`, p.id, cscore, m));
        } else {
          for (let s = 1; s <= 3; s++) {
            const sid = `${cid}.${s}`;
            cells.push(cell(sid, `Subcapability ${cid}.${s}`, cid, clamp(cscore + (s - 2) * 0.3), m));
          }
        }
      }
    }
  });
  return cells;
}
function clamp(n: number): number { return Math.max(1, Math.min(5, Math.round(n * 10) / 10)); }
function cell(id: string, label: string, parent: string | null, score: number, m: MockEntity): HeatmapCell {
  const peer = clamp(score - 0.3 + (id.length % 3) * 0.1);
  return {
    id, label, parent_id: parent, score, band: band(score),
    peer_median: peer, peer_gap: Math.round((score - peer) * 10) / 10,
    is_thin_evidence: id.endsWith(".2"), cap_applied: id.endsWith("C2"),
    cap_reason: id.endsWith("C2") ? "Issue-register cap (open audit finding)" : null,
    issue_count: id.endsWith("C2") ? 1 : 0, aliased_from: null,
  };
}

// ── Endpoint table ─────────────────────────────────────────────────────────
type Query = Record<string, string | number | boolean | null | undefined> | undefined;

function overview(id: string): EntityOverviewResponse {
  const m = byId(id);
  return {
    entity: entitySummary(m),
    run: runSummary(m),
    scqa: {
      situation: `${m.name} runs a fragmented data estate across ${m.subvertical} lines of business.`,
      complication: "Peer institutions are 0.4 ahead on Data & Analytics; commercial lending onboarding lags.",
      question: "Where should the next 12 months of digital investment concentrate?",
      answer: "Consolidate the data platform first (P1), then unlock channel automation (P2) — the cross-pillar multiplier.",
    },
    why_now_signals: [
      { title: "nCino renewal window", body: "Contract renewal in 2 quarters — platform decision imminent.", icon: "calendar", date: "2026-Q2" },
      { title: "New CDO appointed", body: "Hired from a digital-first peer; mandate to modernize.", icon: "user", date: "2025-11" },
      { title: "Commercial loan growth", body: "18% YoY — onboarding can't keep pace.", icon: "money", date: "2025" },
    ],
    top_findings: [
      { id: "F1", title: "Data platform fragmentation caps every downstream pillar", flag: "CRITICAL" },
      { id: "F2", title: "Salesforce present but under-adopted in commercial banking", flag: "OPPORTUNITY" },
      { id: "F3", title: "Strong governance posture — a credible modernization foundation", flag: "MONITOR" },
    ],
    firmographics: {
      legal_name: m.name, ticker: m.display_id.includes("wsfs") ? "WSFS" : null,
      headquarters: "Wilmington, DE", employees: 1850, branches: 89,
      total_assets: "$20.6B", roa: "1.21%", efficiency_ratio: "58.4%",
      primary_regulator: "FDIC", sub_vertical: m.subvertical, founded: 1832,
    },
    narrative: {
      scqa_heading: "Executive summary",
      scqa_md: `**${m.name}** is mid-way through a multi-year digital transformation. Current overall maturity ${m.overall.toFixed(1)} / 5 — below the ${m.subvertical} peer median on Data & Analytics, at parity on Governance.`,
      benchmark_md: "Peer set: 8 locked regional banks ($10–50B assets).",
    },
    pillar_scores: PILLARS.map((p, i) => ({
      pillar_id: p.id, score: m.pillars[i], peer_median: clamp(m.pillars[i] - 0.3),
      subcaps_scored: 24, peer_benchmarked: 24,
    })),
    evidence_freshness: {
      current_count: 41, aging_count: 18, dated_count: 9, stale_count: 4, undated_count: 2,
      total: 74, oldest_published_date: "2021-03-01", median_age_months: 11, stale_pct: 5.4,
    },
    intelligence_profile: {
      total_runs: 3, maturity_velocity: 0.3,
      recurring_themes: ["Data fragmentation", "Salesforce under-adoption", "Manual onboarding"],
      emerging_themes: ["AI governance readiness"],
      persistent_gap_subcap_ids: ["P1C1.2", "P2C3.1"], closed_gap_subcap_ids: ["P4C1.1"],
      intelligence_summary_md: `${m.name} has improved +0.3 overall across 3 runs; data-platform gaps persist while governance has closed.`,
      computed_at: NOW, catalogue_version: CAT,
    },
    assumptions_register: [
      { id: "A1", assumption: "Salesforce FSC is the strategic CRM of record", basis: "CIO interview + tech inventory", confidence: "HIGH" },
      { id: "A2", assumption: "Commercial lending is the priority LOB for 2026", basis: "Loan-growth trend + exec mandate", confidence: "MEDIUM" },
    ],
  };
}

function platforms(id: string): PlatformsResponse {
  const m = byId(id);
  const mk = (pid: string, name: string, pillar: string, fit: number, ri: PlatformCard["readiness_index"], starter: string): PlatformsResponse["cards"][number] => ({
    platform_id: pid, display_name: name, pillar, fit_score: fit, readiness_index: ri,
    state: "READY", addressable_subcap_ids: [`${pillar}C1.1`, `${pillar}C2.1`],
    prereq_checks: [
      { name: "Clean customer master", required_subcap_id: `${pillar}C1.1`, threshold: 3, status: fit > 70 ? "MET" : "PARTIAL", current_score: m.pillars[0], note: null },
      { name: "Integration backbone", required_subcap_id: `${pillar}C2.1`, threshold: 3, status: fit > 60 ? "MET" : "UNMET", current_score: clamp(m.pillars[0] - 0.5), note: "MuleSoft present, partial coverage" },
    ],
    conversation_starter: starter,
  });
  return {
    entity_display_id: m.display_id, run_request_id: runSummary(m).request_id,
    cards: [
      mk("salesforce-fsc", "Salesforce FSC", "P2", 82, "green", "How is commercial banking using FSC today vs. retail?"),
      mk("databricks", "Databricks Lakehouse", "P1", 74, "amber", "Where does customer data fragment across your estate?"),
      mk("mulesoft", "MuleSoft", "P1", 68, "amber", "Which integrations are still point-to-point?"),
      mk("ncino", "nCino", "P3", 61, "red", "What's the commercial loan onboarding cycle time?"),
      mk("tableau-crm", "Tableau / CRM Analytics", "P1", 57, "red", "Who consumes analytics today, and how?"),
    ] as PlatformsResponse["cards"],
    pillar_offerings: { P1: ["databricks", "mulesoft", "tableau-crm"], P2: ["salesforce-fsc"], P3: ["ncino"], P4: [] },
    narrative: {
      recommendations_md: "Lead with the data platform (Databricks) — it unblocks FSC analytics and nCino reporting.",
      roadmap_md: "Phase 1 (0–6mo): data foundation · Phase 2 (6–12mo): FSC commercial rollout · Phase 3 (12–18mo): nCino + analytics.",
      roadmap_phases: [
        { phase: 1, label: "Data foundation", duration: "0–6 mo", platform: "Databricks Lakehouse", target: "M2 → M3", metric: "Single customer golden record across core systems", rec_ids: ["REC-1", "REC-2"], customer_impact: { "Onboarding time": "−30%", "Data accuracy": "+25%" } },
        { phase: 2, label: "Commercial rollout", duration: "6–12 mo", platform: "Salesforce FSC", target: "M3 → M4", metric: "FSC adopted by 80% of commercial RMs", rec_ids: ["REC-3"], customer_impact: { "RM productivity": "+18%", "Cross-sell": "+12%" } },
        { phase: 3, label: "Automate + analytics", duration: "12–18 mo", platform: "nCino + CRM Analytics", target: "M4 → M5", metric: "Loan onboarding cycle 21d → 7d", rec_ids: ["REC-4", "REC-5"], customer_impact: { "Loan cycle": "21d → 7d", "NPS": "+9" } },
      ],
    },
  };
}

function insights(id: string): InsightListResponse {
  const m = byId(id);
  const mk = (n: number, sev: "critical" | "high" | "medium" | "low", title: string, subcap: string): InsightListResponse["items"][number] => ({
    id: `ic-${n}`, ic_id: `IC-00${n}`, severity: sev, title,
    what_text: "Observed in evidence across T1–T2 sources.",
    why_text: "Drives downstream maturity ceilings in adjacent capabilities.",
    so_what_text: "Zennify can sequence a remediation that compounds across pillars.",
    linked_subcap_id: subcap, linked_e_ids: ["E-008", "E-028"],
    source_rec_id: null, related_rec_ids: [],
  });
  return {
    entity_display_id: m.display_id, run_request_id: runSummary(m).request_id,
    items: [
      mk(1, "critical", "Data platform fragmentation caps analytics maturity", "P1C1.2"),
      mk(2, "high", "Salesforce FSC under-adopted in commercial banking", "P2C3.1"),
      mk(3, "medium", "Manual loan onboarding extends cycle time", "P3C2.1"),
      mk(4, "low", "Governance posture is a credible modernization base", "P4C1.1"),
    ],
    narrative: { recommendations_md: "Prioritize P1 data consolidation; it is the cross-pillar unlock." },
  };
}

function dashboard(): DashboardResponse {
  return {
    scope: "all",
    tiles: [
      { kind: "entity_count", label: "Active clients", value: ROSTER.length, delta: 1, last_refreshed_at: NOW },
      { kind: "insight_count", label: "Open insights", value: 47, delta: 5, last_refreshed_at: NOW },
      { kind: "alert_count", label: "Open alerts", value: ROSTER.reduce((a, e) => a + e.alerts, 0), delta: -2, last_refreshed_at: NOW },
      { kind: "avg_maturity", label: "Avg maturity", value: "3.2", delta: 0.1, last_refreshed_at: NOW },
    ],
    active_runs: ROSTER.filter((e) => e.in_progress).map(runSummary),
  };
}

function alerts(): { items: AlertOut[]; open_count: number } {
  const items: AlertOut[] = ROSTER.flatMap((m) =>
    Array.from({ length: Math.min(m.alerts, 2) }, (_v, i) => ({
      id: `al-${m.display_id}-${i}`, kind: i === 0 ? "stale_evidence" : "score_regression",
      severity: (i === 0 ? "high" : "medium") as AlertOut["severity"],
      title: i === 0 ? "Evidence aging past 24 months" : "Pillar score regressed vs prior run",
      body: `${m.name}: review recommended.`, linked_subcap_ids: ["P1C1.2"], linked_e_ids: ["E-101"],
      opened_at: NOW, closed_at: null, resolution: null, age_days: 6 + i,
      entity_id: `id-${m.display_id}`, entity_display_id: m.display_id,
      entity_name: m.name,
    })),
  );
  return { items, open_count: items.length };
}

function notifications(): NotificationListResponse {
  return {
    items: [
      { id: "n1", kind: "completion", title: "WSFS Financial assessment completed", body: "Overall 3.8 / 5", entity_id: "id-wsfs-financial-0003", route: "/clients/wsfs-financial-0003/overview", seen_at: null, created_at: NOW },
      { id: "n2", kind: "alert", title: "Alma Bank: 4 open alerts", body: "2 critical", entity_id: "id-alma-bank-0002", route: "/alerts", seen_at: null, created_at: NOW },
      { id: "n3", kind: "system", title: "Catalogue v7.0 applied", body: null, entity_id: null, route: "/admin", seen_at: NOW, created_at: NOW },
    ],
  } as NotificationListResponse;
}

function runs(id: string): RunHistoryResponse {
  const m = byId(id);
  return {
    items: [
      { id: `run-${m.display_id}-3`, request_id: `REQ-${m.display_id.slice(0, 6).toUpperCase()}03`, status: "ACTIVE", data_source: m.source ?? "DRIVE_PARSE", completed_at: "2026-01-12T00:00:00Z", overall_score: m.overall, evidence_mode: "hybrid" },
      { id: `run-${m.display_id}-2`, request_id: `REQ-${m.display_id.slice(0, 6).toUpperCase()}02`, status: "SUPERSEDED", data_source: m.source ?? "DRIVE_PARSE", completed_at: "2025-09-30T00:00:00Z", overall_score: clamp(m.overall - 0.2), evidence_mode: "hybrid" },
      { id: `run-${m.display_id}-1`, request_id: `REQ-${m.display_id.slice(0, 6).toUpperCase()}01`, status: "SUPERSEDED", data_source: "MANUAL_BACKFILL", completed_at: "2025-05-15T00:00:00Z", overall_score: clamp(m.overall - 0.4), evidence_mode: "public" },
    ],
  };
}

const TIMELINE: TimelineEventOut[] = [
  { id: "t1", event_date: "2016-01-01", kind: "milestone", title: "nCino Bank Operating System selected", body: "Commercial lending platform foundation.", source_url: null, e_id: "E-008" },
  { id: "t2", event_date: "2021-03-01", kind: "milestone", title: "Salesforce + MuleSoft integration architecture", body: "MuleSoft chosen as the integration backbone.", source_url: null, e_id: "E-028" },
  { id: "t3", event_date: "2022-01-01", kind: "acquisition", title: "Bryn Mawr Bank Corporation acquired", body: "Wealth expansion; created data-fragmentation challenge.", source_url: null, e_id: "E-041" },
  { id: "t4", event_date: "2025-11-01", kind: "leadership", title: "New CDO appointed", body: "Hired from a digital-first peer with a modernization mandate.", source_url: null, e_id: "E-062" },
];

function context(id: string): ContextResponse {
  const m = byId(id);
  return {
    entity_display_id: m.display_id,
    run_request_id: runSummary(m).request_id,
    timeline_events: TIMELINE,
    issue_register: [
      { id: "i1", issue_id: "ISS-01", title: "Data fragmentation caps analytics maturity", severity: "high", rationale: "Three core systems, no golden record.", opened_on: "2025-06-01", resolved_on: null, status: "OPEN", linked_subcap_ids: ["P1C1.2"] },
      { id: "i2", issue_id: "ISS-02", title: "Manual loan onboarding", severity: "medium", rationale: "21-day cycle across 6 hand-offs.", opened_on: "2025-07-15", resolved_on: null, status: "OPEN", linked_subcap_ids: ["P3C2.1"] },
      { id: "i3", issue_id: "ISS-03", title: "Legacy BSA/AML remediation", severity: "low", rationale: "Closed after 2024 audit.", opened_on: "2024-02-01", resolved_on: "2024-11-01", status: "RESOLVED", linked_subcap_ids: ["P4C1.1"] },
    ] as IssueRegisterOut[],
    acquisitions: [
      { id: "a1", event_date: "2022-01-01", title: "Bryn Mawr Bank Corporation", body: "Wealth + PA footprint; ~$976M stock deal.", source_url: null, e_id: "E-041" },
    ] as AcquisitionOut[],
    firmographics: { legal_name: m.name, primary_regulator: "FDIC", headquarters: "Wilmington, DE" },
    financials: {
      years: [2021, 2022, 2023, 2024, 2025],
      series: { "Total assets ($B)": [14.5, 17.5, 19.0, 20.1, 20.6], "ROA (%)": [1.05, 1.10, 1.15, 1.18, 1.21] },
      lines: ["Total assets ($B)", "ROA (%)"],
    },
    sentiment: { sources: [{ source: "Indeed Overall Rating", rating: "3.6/5.0" }, { source: "Culture & Values", rating: "3.5/5.0" }] },
    narrative: { summary_md: `${m.name} is mid-transformation; data-platform consolidation is the gating dependency.` },
  };
}

function health(id: string): HealthResponse {
  const m = byId(id);
  const v: QaVerdictOut = { verdict: "PASS", recommendation: "Proceed to handoff", verdict_basis: "All 10 safeguard gates passed; citation + peer density within thresholds.", governance_skill_version: "v5.2" };
  return {
    entity_display_id: m.display_id,
    run_request_id: runSummary(m).request_id,
    thin_evidence_subcap_ids: ["P1C1.2", "P2C3.1"],
    safeguard_gates: [
      { gate_id: "G1 · Evidence sufficiency", status: "PASS", detail: "74 evidence items across 4 pillars.", evaluated_at: NOW },
      { gate_id: "G2 · Peer benchmarking", status: "PASS", detail: "8-bank locked peer set.", evaluated_at: NOW },
      { gate_id: "G3 · Citation density", status: "PARTIAL", detail: "2 subcaps below T2 threshold.", evaluated_at: NOW },
      { gate_id: "G4 · Contradiction adjudication", status: "PASS", detail: "1 contradiction resolved.", evaluated_at: NOW },
    ] as SafeguardGateOut[],
    alerts: alerts().items.filter((a) => a.entity_display_id === m.display_id),
    evidence_age: [
      { e_id: "E-008", source_name: "nCino case study", tier: 1, published_date: "2024-06-01", recency_months: 7, freshness_band: "current" },
      { e_id: "E-028", source_name: "Press release", tier: 2, published_date: "2021-03-01", recency_months: 46, freshness_band: "stale" },
      { e_id: "E-041", source_name: "10-K filing", tier: 1, published_date: "2023-02-01", recency_months: 35, freshness_band: "dated" },
    ] as EvidenceAgeOut[],
    caps_applied: [
      { log_id: "c1", subcap_id: "P4C2.1", cap_type: "issue_register", trigger_condition: "Open audit finding", cap_ceiling: "M3", trigger_evidence: ["E-101"], affected_categories: ["P4C2"], severity: "high", date_applied: NOW, recalc_verified: NOW },
    ],
    qa_verdict_l1: { ...v, verdict: "PASS", governance_skill_version: "v5.1" },
    qa_verdict_l2: v,
    audit_logs: {
      reasoning_chain: [
        { subcap_id: "P1C1.2", category: "Data platform", decision_path: ["Evidence gathered (T1/T2)", "Peer compared", "Capped by data fragmentation", "Final M2"] },
      ],
      contradictions: [
        { contradiction_id: "CON-01", subcap_id: "P2C3.1", winner: "E-028", justification: "More recent + higher tier.", contradiction_type: "recency" },
      ],
    },
    narrative: { summary_md: "Assessment passed all gates; two subcaps flagged thin-evidence." },
  };
}

const REC_TITLES = [
  "Stand up the Databricks Lakehouse + golden customer record",
  "Migrate point-to-point integrations onto MuleSoft",
  "Roll out Salesforce FSC to commercial relationship managers",
  "Automate commercial loan onboarding on nCino",
  "Operationalize analytics + AI governance on CRM Analytics",
];
function recDetail(recId: string): unknown {
  const n = Number((recId.match(/(\d+)/) ?? [])[1] ?? 1);
  const title = REC_TITLES[n - 1] ?? REC_TITLES[0];
  return {
    id: recId, rec_id: recId, title,
    description: `${title}. Sequenced to unlock the dependent capabilities in the following phase; grounded in T1–T2 evidence and the locked peer set.`,
    entity_display_id: ROSTER[0].display_id,
    target_subcap_ids: ["P1C1.2", "P2C3.1"], platform_id: "databricks",
    addressable_offerings: ["Lakehouse", "Delta", "Unity Catalog"],
    uplift_per_pillar: { P1: 0.6, P3: 0.3 }, effort_band: "Medium",
    cited_features: [{ kind: "feature", id: "F-101", resolved: true, name: "Unity Catalog governance" }],
    cited_constructs: [{ kind: "construct", id: "C-22", resolved: true, name: "Customer 360" }],
    cited_agents: [], unresolved_count: 0, catalogue_version: CAT,
  };
}

// ── Router ─────────────────────────────────────────────────────────────────
const RE_ENTITY = /\/api\/v1\/entities\/([^/?]+)\/([^/?]+)/;

/** Returns mock data for a path, or `undefined` to fall through to network. */
export function getStandaloneMock(
  path: string,
  method: string,
  query?: Query,
): unknown | undefined {
  const p = path.split("?")[0];
  if (method === "GET") {
    if (p.endsWith("/api/v1/auth/me")) {
      return { user_id: "u-demo", email: "mishley@zennify.com", role: "ADMIN", name: "Mishley O.", can_act_as: ["ADMIN", "ANALYST", "AE"] };
    }
    if (p.endsWith("/api/v1/dashboard")) return dashboard();
    if (p.endsWith("/api/v1/entities")) {
      return { items: ROSTER.map(entitySummary), total: ROSTER.length, owner_filter: "all" } as EntityListResponse;
    }
    if (p.endsWith("/api/v1/alerts")) return alerts();
    if (p.endsWith("/api/v1/notifications")) return notifications();
    // Recommendation detail: /api/v1/recommendations/{rec_id}
    const rm = p.match(/\/api\/v1\/recommendations\/([^/?]+)$/);
    if (rm) return recDetail(rm[1]);
    // Transformation roadmap (backend derives phases from recs by effort band).
    const rd = p.match(/\/api\/v1\/entities\/([^/?]+)\/platforms\/roadmap$/);
    if (rd) {
      const m = byId(rd[1]);
      return {
        entity_display_id: m.display_id, run_request_id: runSummary(m).request_id,
        total_duration_months: 18,
        phases: [
          { phase: 1, name: "Data foundation", duration_months: 6, recommendations: [
            { rec_id: "REC-1", title: REC_TITLES[0], platform_id: "databricks", platform_name: "Databricks Lakehouse", maturity_lift: "+0.6" },
            { rec_id: "REC-2", title: REC_TITLES[1], platform_id: "databricks", platform_name: "MuleSoft", maturity_lift: "+0.3" },
          ] },
          { phase: 2, name: "Commercial rollout", duration_months: 6, recommendations: [
            { rec_id: "REC-3", title: REC_TITLES[2], platform_id: "salesforce", platform_name: "Salesforce FSC", maturity_lift: "+0.5" },
          ] },
          { phase: 3, name: "Automate + analytics", duration_months: 6, recommendations: [
            { rec_id: "REC-4", title: REC_TITLES[3], platform_id: "ncino", platform_name: "nCino", maturity_lift: "+0.4" },
            { rec_id: "REC-5", title: REC_TITLES[4], platform_id: "tableau", platform_name: "CRM Analytics", maturity_lift: "+0.3" },
          ] },
        ],
      };
    }
    // Subcap synthesis detail: /api/v1/entities/{id}/heatmap/subcap/{subcap}
    const sd = p.match(/\/api\/v1\/entities\/([^/?]+)\/heatmap\/subcap\/([^/?]+)$/);
    if (sd) {
      const [, id, subRaw] = sd;
      const sub = decodeURIComponent(subRaw);
      const m = byId(id);
      const c = heatmapCells(m, "subcap").find((x) => x.id === sub) ?? heatmapCells(m, "subcap")[0];
      const ds = sub.endsWith(".2") ? "synthesized" : sub.endsWith(".1") ? "extracted" : "derived";
      return {
        entity_display_id: m.display_id, subcap_id: sub,
        cells: [{ ...c, id: sub, data_source: ds }],
        narrative: { per_subcap_md: { [sub]: `Score reflects ${c.band} maturity for ${sub}. Evidence: E-008 (T1), E-028 (T2). Peer median ${c.peer_median?.toFixed(1)} — gap ${c.peer_gap?.toFixed(1)}.` } },
        catalogue_version: CAT, run_request_id: runSummary(m).request_id,
      };
    }
    const em = p.match(RE_ENTITY);
    if (em) {
      const [, id, surface] = em;
      switch (surface) {
        case "overview": return overview(id);
        case "insights": return insights(id);
        case "platforms": return platforms(id);
        case "focus-areas":
          return {
            entity_display_id: id,
            items: [
              { id: "FA-1", title: "Unify the customer data platform", verbatim_quote: "Customer data fragments across three core systems with no golden record.", source_path: "Client_Profile.docx", page_number: 12, involved_subcap_ids: ["P1C1.1", "P1C1.2", "P1C2.1"] },
              { id: "FA-2", title: "Scale Salesforce FSC into commercial banking", verbatim_quote: "FSC is live in retail but commercial relationship managers still work from spreadsheets.", source_path: "Client_Profile.docx", page_number: 18, involved_subcap_ids: ["P2C1.1", "P2C3.1", "P2C2.2"] },
              { id: "FA-3", title: "Automate commercial loan onboarding", verbatim_quote: "Onboarding a new commercial loan takes 21 days across 6 hand-offs.", source_path: "Assessment_Report.docx", page_number: 24, involved_subcap_ids: ["P3C1.1", "P3C2.1", "P3C2.3"] },
              { id: "FA-4", title: "Operationalize AI governance", verbatim_quote: "No model-risk framework exists ahead of the planned analytics build-out.", source_path: "Assessment_Report.docx", page_number: 31, involved_subcap_ids: ["P4C1.1", "P4C2.1"] },
            ],
          };
        case "heatmap": {
          const m = byId(id);
          // Focus view filters cells by a focus area's subcap ids → it needs
          // subcap-granularity cells to map against.
          const zoom = query?.hm === "focus" ? "subcap" : String(query?.zoom ?? "pillar");
          const resp: HeatmapResponse = {
            entity_display_id: m.display_id, run_request_id: runSummary(m).request_id,
            run_status: "ACTIVE", zoom: zoom as HeatmapResponse["zoom"],
            view_mode: (String(query?.view_mode ?? "standard")) as HeatmapResponse["view_mode"],
            subvertical: m.subvertical, peer_overlay: true, issue_overlay: true,
            cells: heatmapCells(m, zoom),
            value_chain_buckets: [
              { stage: "Acquire", cell_ids: ["P2C1"] },
              { stage: "Onboard", cell_ids: ["P3C1"] },
              { stage: "Serve", cell_ids: ["P2C2"] },
              { stage: "Grow", cell_ids: ["P1C1"] },
            ],
            catalogue_version: CAT, warnings: [],
            narrative: { benchmark_md: "Peer set: 8 regional banks." },
          };
          return resp;
        }
        case "recommendations":
          return REC_TITLES.map((t, i) => ({ id: `REC-${i + 1}`, rec_id: `REC-${i + 1}`, title: t, platform_id: ["databricks", "databricks", "salesforce", "ncino", "tableau"][i] ?? null }));
        case "runs": return runs(id);
        case "context": return context(id);
        case "health": return health(id);
        case "cross-pillar":
          return {
            entity_display_id: id, catalogue_version: CAT, total_stories: 3,
            themes: [
              { theme: "Data foundation unlocks analytics + lending", story_count: 2, target_pillars: { P1: 2, P3: 1 }, origin_capabilities: ["P1C1.2", "P3C2.1"] },
              { theme: "CRM consolidation spans channels + ops", story_count: 1, target_pillars: { P2: 1, P3: 1 }, origin_capabilities: ["P2C3.1"] },
            ],
          };
        default: return undefined;
      }
    }
  }
  // Mutations: acknowledge so the UI shows success toasts in the demo.
  if (method === "POST" || method === "PATCH" || method === "PUT") {
    if (p.includes("notifications:mark-read")) return { ok: true };
    if (p.includes("/runs/new")) return { request_id: "REQ-DEMO1234", status: "queued" };
    return { ok: true };
  }
  return undefined;
}
