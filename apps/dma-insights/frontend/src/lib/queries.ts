/**
 * TanStack Query hooks against the backend.
 *
 * Conventions:
 *   - One hook per backend endpoint.
 *   - All hooks return `useQuery` results; consumers handle isLoading/error.
 *   - Stale times tuned per the per-surface contract in the plan §⑩.
 *   - SSE invalidation lands in stage 11 frontend wiring; the QueryClient's
 *     5-minute default already gives reasonable freshness.
 */
import { useQuery, type UseQueryResult, useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiGet, apiPatch, apiPost, apiPut, ApiError } from "./api";
import { useUiStore } from "@/store/ui";
import { STARTUP_DASHBOARD, STARTUP_ENTITIES } from "./startup-data";
import { apiOrSnapshot, pageSnapshot, snapshotOrApi, USE_STARTUP_PACK } from "./startup-pages";

/**
 * Subscribe to the audience so this hook re-renders when the operator
 * toggles between internal/customer. Returning the audience as a string
 * makes it easy to splice into a TanStack queryKey -- audience-sensitive
 * hooks always include `useAudienceForKey()` so cache buckets are
 * partitioned by view. Pre-2026-06-05 only the cache wipe in
 * `setAudience` guarded against leak; that left a small window where a
 * concurrent fetch could resolve into the just-cleared cache. The
 * queryKey partitioning closes that window completely.
 */
function useAudienceForKey(): string {
  return useUiStore((s) => s.audience);
}

// ---------- Types matching backend Pydantic schemas ----------

export interface EntitySummary {
  id: string;
  display_id: string;
  name: string;
  domain: string | null;
  subvertical: string | null;
  lobs: string[];
  status: "ACTIVE" | "ARCHIVED" | "MERGED" | "PENDING_REVIEW";
  last_run_at: string | null;
  last_run_request_id: string | null;
  owner_email: string | null;
  owner_name: string | null;
  updated_at: string;
  // Per-run summary fields the dashboard + directory cards render --
  // backend EntitySummary in app/schemas/entities.py exposes all of
  // these. Pre-2026-06-05 the frontend type omitted them and pages
  // cast `(e as { overall_score?: number }).overall_score` everywhere,
  // hiding contract drift. Sync the type to the backend so the
  // compiler catches future drift.
  last_run_status: string | null;
  data_source: string | null;
  in_progress: boolean;
  pillar_scores: Record<string, number> | null;
  overall_score: number | null;
  subcap_count: number | null;
  // 2026-06-06 QA-M4: per-entity open alerts count. Backend now emits
  // this via a LATERAL count(*) against `alerts WHERE closed_at IS NULL`
  // in the entities-list endpoint. Pre-fix the Dashboard + Directory
  // hard-coded 0 here, so the orange alert chip never appeared on
  // entity cards even when alerts existed.
  open_alerts: number;
  // Migration 039: latest run's official assessment date (card date chips +
  // freshness dot). NULL → consumers fall back to last_run_at.
  assessment_date: string | null;
  // 2026-06-13 prototype parity: backend now emits these (app/schemas/
  // entities.py). `hq` is the firmographics HQ ("· San Antonio, TX" after
  // the subvertical on the card); `top_platform` is the top-OSS chip
  // (null when no real fit signal); `current_batch` is the coarse 1..6
  // Setup→Final pill index for an in-progress run (null when complete).
  hq: string | null;
  top_platform: { platform_id: string; short: string; fit_score: number } | null;
  current_batch: number | null;
}

export interface EntityListResponse {
  items: EntitySummary[];
  total: number;
  owner_filter: "me" | "all";
}

export interface RunSummary {
  id: string;
  request_id: string;
  status: "IN_PROGRESS" | "ACTIVE" | "SUPERSEDED" | "STALE" | "FAILED" | "PENDING_REVIEW";
  // 2026-06-05: backend RunSummary literal union mirrors the runs
  // table CHECK constraint (alembic 021); pre-fix the frontend type
  // omitted DRIVE_BACKFILL + BOT_REQUEST so any historical-backfill
  // run that landed in /runs serialised as `unknown` in the UI.
  data_source:
    | "DRIVE_PARSE"
    | "DRIVE_BACKFILL"
    | "PROJECT_API"
    | "MANUAL_BACKFILL"
    | "BOT_REQUEST";
  evidence_mode: "public" | "hybrid";
  ccg_catalog_version: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  overall_score: number | null;
  // 2026-06-09 prototype parity: subcap_scores row count for the run,
  // rendered in the Runs table's "Subcaps" column.
  subcap_count: number | null;
}

export interface DashboardTile {
  kind: string;
  label: string;
  value: number | string;
  delta: number | null;
  last_refreshed_at: string;
}

export interface DashboardResponse {
  scope: "mine" | "all";
  tiles: DashboardTile[];
  active_runs: RunSummary[];
}

export interface OverviewNarrative {
  scqa_md?: string;
  scqa_heading?: string;
  page_number?: number | null;
  benchmark_md?: string;
  gap_prioritization_md?: string;
}

export type FreshnessBand = "current" | "aging" | "dated" | "stale" | "undated";

export interface EvidenceFreshnessRollup {
  current_count: number;
  aging_count: number;
  dated_count: number;
  stale_count: number;
  undated_count: number;
  total: number;
  oldest_published_date: string | null;
  median_age_months: number | null;
  stale_pct: number;
}

export interface IntelligenceProfile {
  total_runs: number;
  maturity_velocity: number | null;
  recurring_themes: string[];
  emerging_themes: string[];
  persistent_gap_subcap_ids: string[];
  closed_gap_subcap_ids: string[];
  intelligence_summary_md: string | null;
  computed_at: string | null;
  catalogue_version: string;
}

export interface EntityOverviewResponse {
  entity: EntitySummary;
  run: RunSummary | null;
  scqa: Record<string, string> | null;
  why_now_signals: Array<Record<string, unknown>>;
  top_findings: Array<Record<string, unknown>>;
  firmographics: Record<string, unknown> | null;
  // Populated from document_sections via section_routing when the
  // Assessment_Report DOCX was ingested. `null` → frontend keeps the
  // skeleton (the existing scqa Record fallback).
  narrative: OverviewNarrative | null;
  // 2026-06-06 QA-M1: backend emits pillar_scores with per-pillar
  // peer_median + subcaps_scored + peer_benchmarked. Pre-fix the
  // frontend Overview synthesised `peer = s + 0.3` -- pure visual
  // theatre -- because this typed shape was missing. The cast
  // `(overviewQ.data as { pillar_scores?: ... }).pillar_scores`
  // hid the contract drift; pinning the type forces tsc to surface
  // any future divergence.
  pillar_scores: Array<{
    pillar_id: string;
    score: number | null;
    peer_median: number | null;
    subcaps_scored: number;
    peer_benchmarked: number;
  }>;
  // Per-entity evidence freshness rollup; `null` before any evidence
  // is ingested.
  evidence_freshness: EvidenceFreshnessRollup | null;
  // Persistent intelligence card; `null` until the first profile
  // recompute fires after ingest.
  intelligence_profile: IntelligenceProfile | null;
  /**
   * C11 (2026-06-07): analyst's assumptions register sourced from the
   * package (Calprivate JSON + Nicola CSV; other folders ship nothing
   * -> empty array). Renders as a footer card on D1 ClientOverview so
   * AE can answer "we assumed X because Y" on sales calls.
   *
   * Each row has at minimum `id` + `assumption`; common extras include
   * `basis`, `confidence`, `category` (Calprivate), `validation_method`,
   * `priority`, `capabilities_affected` (Nicola).
   */
  assumptions_register: Array<{
    id: string;
    assumption: string;
    basis?: string;
    confidence?: string;
    [k: string]: unknown;
  }>;
  /**
   * Source-data quality flags (2026-06-25 contamination remediation). When
   * `source_misattribution` is set, the assessment's analytical content could
   * not be confirmed as belonging to this entity (the audit's beacon-bank case:
   * identity correct, but ticker/run-id/prose are a different institution).
   * `"A"` = corroborated misattribution (render the unverified-source banner);
   * `"B"` = a foreign-looking symbol pending review. Absent on clean entities.
   */
  data_quality?: {
    source_misattribution?: "A" | "B" | null;
    misattribution_markers?: {
      foreign_tickers?: string[];
      foreign_runid_tokens?: string[];
      foreign_entities?: string[];
    };
  } | null;
  /**
   * Migration 045 (Part 4.6 "Evidence & benchmarks" cards). All three
   * are run-scoped JSONB written by derive_evidence_surfaces — null
   * until the deriver has run (cards keep their honest-empty state).
   *   evidence_summary  → EvidenceTierCard histogram
   *   coverage_stats    → CoverageByPillarCard
   *   uncertainty_bands → CeilingEstimateCard
   */
  evidence_summary?: Record<string, unknown> | null;
  coverage_stats?: Record<string, unknown> | null;
  uncertainty_bands?: Record<string, unknown> | null;
  /** FinancialTrajectoryCard's normalized series — null until derived. */
  financial_trajectory?: Record<string, unknown> | null;
  /** SentimentCard's normalized {employee[], customer[], industry_avg,
   *  b2b_b2c_gap} — distinct from firmographics.sentiment; null until
   *  derived. Internal-audience card only. */
  sentiment?: Record<string, unknown> | null;
}

export interface InsightCardOut {
  id: string;
  ic_id: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  what_text: string;
  why_text: string;
  so_what_text: string;
  linked_subcap_id: string;
  linked_e_ids: string[];
  // The recommendation this insight was DERIVED from (faithful single link;
  // null until re-ingest). related_rec_ids is the subcap-join fallback that
  // works on existing data. The callout prefers source_rec_id.
  source_rec_id: string | null;
  related_rec_ids: string[];
  /** E-IDs that DISAGREE with the headline insight ("But also…" section;
   *  empty → "No counter-signals identified"). Backend always emits it —
   *  optional here so existing fixtures stay valid. */
  counter_e_ids?: string[];
  /** Confidence chip: high = ≥3 rows all tier ≥4; medium = ≥2 rows or
   *  mixed tier; low = single row or tier ≤2. */
  confidence_band?: "high" | "medium" | "low" | null;
  /** Migration 046 (interconnection mining) — all additive; absent/empty
   *  until the derivation rebuild fills them. `affects` is the
   *  multi-value cross-pillar subcap set (modal affects chips →
   *  heatmap navigation); linked_subcap_id stays the anchor. */
  affects?: string[];
  /** Implicated platform_ids — card platform badge + "Linked" tab. */
  platforms?: string[];
  /** Mined links [{kind, target_id, note, e_ids}]: counter-evidence,
   *  related recs, tech-stack absences, sibling cards. */
  interconnections?: Array<Record<string, unknown>>;
  /** Short classification label for grouping/filters. */
  theme?: string | null;
}

export interface InsightsNarrative {
  per_pillar?: Record<
    string,
    {
      findings_md?: string;
      heading?: string;
      linked_subcap_ids?: string[];
      linked_e_ids?: string[];
    }
  > | null;
  recommendations_md?: string | null;
}

export interface InsightListResponse {
  entity_display_id: string;
  run_request_id: string | null;
  items: InsightCardOut[];
  narrative: InsightsNarrative | null;
}

export interface HeatmapCell {
  id: string;
  label: string;
  parent_id: string | null;
  score: number | null;
  band: string | null;
  peer_median: number | null;
  peer_gap: number | null;
  is_thin_evidence: boolean;
  cap_applied: boolean;
  cap_reason: string | null;
  issue_count: number;
  aliased_from: string | null;
  /** Provenance of the cell's score/rationale — drives the SynthesisDrawer
   *  chip. EXTRACTED/direct · DERIVED/shallow_broadcast · SYNTHESIZED/llm ·
   *  heuristic. Optional: backend may omit it (chip then hidden). */
  data_source?: string | null;
}

export interface HeatmapNarrative {
  per_pillar_md?: Record<string, string> | null;
  per_subcap_md?: Record<string, string> | null;
  /** Provenance per subcap ("llm" | "heuristic") for the entries in
   *  `per_subcap_md`. The startup pack bakes the durable subcap_narratives
   *  synthesis here so the cold/pack-first SynthesisDrawer can render its
   *  "AI synthesis" panel + source chip without the live per-subcap
   *  endpoint (which is unreachable pack-first). */
  per_subcap_meta?: Record<string, string> | null;
  benchmark_md?: string | null;
  issue_register_md?: string | null;
}

export interface HeatmapResponse {
  entity_display_id: string;
  run_request_id: string | null;
  run_status: string | null;
  zoom: "pillar" | "category" | "capability" | "subcap";
  view_mode: "standard" | "focus" | "value_chain";
  subvertical: string | null;
  peer_overlay: boolean;
  issue_overlay: boolean;
  cells: HeatmapCell[];
  value_chain_buckets: Array<{ stage: string; cell_ids: string[] }>;
  catalogue_version: string;
  warnings: string[];
  narrative: HeatmapNarrative | null;
}

export interface PlatformCard {
  platform_id: string;
  display_name: string;
  pillar: string;
  fit_score: number;
  readiness_index: "green" | "amber" | "red";
  state: "READY" | "PENDING_REVIEW" | "INSUFFICIENT_EVIDENCE" | "RECOMPUTE_NEEDED";
  addressable_subcap_ids: string[];
  prereq_checks: Array<{
    name: string;
    required_subcap_id: string;
    threshold: number;
    status: "MET" | "PARTIAL" | "UNMET" | "MISSING";
    current_score: number | null;
    note: string | null;
  }>;
  conversation_starter: string | null;
  // The prototype's 3 distinct starter cards (08_pages_d.js:206) —
  // deterministic template-fill from the backend composer.
  conversation_starters?: string[];
  // validated Gemini platform story (cache read-back; provenance-badged)
  story_md?: string | null;
  story_source?: string | null;
  /** Migration 053 (fit engine v2) — per-factor contributions + top
   *  contributing subcaps + E-IDs; drives the 6-col gap table + the
   *  fit-tile drilldown drawer. Null until the v2 engine persists rows. */
  fit_breakdown?: FitBreakdown | null;
  /** Position in the prerequisite DAG across platforms+recs. */
  sequence_rank?: number | null;
  /** Prototype fit-tile badges (Part 7.4): confirmed-ABSENT count +
   *  top-2 contributing subcap names. Null until the taxonomy /
   *  fit v2 derivations land. */
  absent_count?: number | null;
  top_subcap_names?: string[] | null;
  /** Evidence ladder (Part 7.1): E-IDs grounding this card — its
   *  addressable subcaps' evidence, falling back to run-level. Empty only
   *  for a truly evidence-less entity. */
  evidence_ids?: string[];
  /** Platform v3 deterministic dossier — three structured sections that back
   *  story_md and drive the D4 dossier panel. Null on legacy/cold packs. */
  dossier?: PlatformDossier | null;
  /** Per-composed-sentence audit chain (claim + source_kind + E-IDs). */
  narrative_provenance?: NarrativeProvenance[];
}

/** One audited claim behind the dossier narrative. */
export interface NarrativeProvenance {
  claim: string;
  source_kind: string;
  e_ids: string[];
}

export interface DossierConfirmedSystem {
  name: string | null;
  status: string;
  e_ids: string[];
  peer_coverage: number | null;
}

export interface DossierReadinessNow {
  light: string | null;
  confirmed_systems: DossierConfirmedSystem[];
  family_present: Array<{ name: string | null; status: string }>;
  greenfield: boolean;
  /** Argument frame (2026-07-14): greenfield | integrate | expand.
   *  `integrate` = the family is absent but a category incumbent
   *  (named in category_incumbents) already occupies the layer.
   *  Optional — packs baked before the lens existed lack it. */
  lens?: "greenfield" | "integrate" | "expand";
  category_incumbents?: string[];
  absent_families: string[];
  open_prereqs: Array<{
    name: string;
    required_subcap_id: string | null;
    current: number | null;
    threshold: number | null;
    status: string;
    /** Related subcaps resolved server-side (gate subcap + category
     *  siblings + nlp matches) — never empty when required_subcap_id is set.
     *  Feeds the readiness card's "backing subcaps" fallback. */
    related_subcaps?: Array<{
      subcap_id: string;
      name: string | null;
      score: number | null;
      e_ids: string[];
    }>;
  }>;
  total_prereqs: number;
}

export interface DossierOpportunity {
  gap_count: number;
  opportunity_points: number | null;
  lead_subcap: {
    name: string | null; score: number | null;
    peer_median: number | null; e_ids: string[];
  } | null;
  next_subcaps: Array<{ name: string | null; score: number | null }>;
}

/** Platform v3 dossier (platform_dossier.compose_dossier). */
export interface PlatformDossier {
  readiness_now: DossierReadinessNow;
  opportunity: DossierOpportunity;
  why_sequence: { rank: number | null; after: string[] };
}

/** One contributing subcap in the fit breakdown (engine v2) — feeds the
 *  6-col gap table rows (name+id | pillar | score | peer | gap |
 *  evidence) and the drilldown's E-ID chips. */
export interface FitSubcapRow {
  subcap_id: string;
  name: string | null;
  pillar: string;
  score: number | null;
  peer_median: number | null;
  gap: number | null;
  opportunity: number | null;
  e_ids: string[];
  /** Best (lowest) evidence tier backing the row — tier-chip color. */
  tier?: number | null;
}

export interface FitFactor {
  value: number;
  points: number;
  dependent_subcaps?: number;
}

/** `platform_scores.fit_breakdown` (migration 053) — the fit engine v2
 *  traceability payload. */
export interface FitBreakdown {
  engine?: string;
  target_band?: string;
  weights?: Record<string, number>;
  factors?: {
    opportunity?: FitFactor;
    interconnect?: FitFactor;
    absent_boost?: FitFactor & {
      /** 2026-07-14 lens: the frame the absence argument takes plus the
       *  named category incumbents and the cohort family share (the same
       *  number the techstack peer-coverage note renders). Optional —
       *  cards computed before the lens existed lack these. */
      stack_lens?: { lens: string | null; category_incumbents: string[] };
      peer_coverage?: number | null;
    };
    readiness?: { light: string; multiplier: number; penalty_points: number };
    /** Present only when < 1.0 — the out-of-vertical cap (e.g. nCino for
     *  an asset manager) with the points it removed and the named reason. */
    vertical_relevance?: { value: number; penalty_points: number; reason: string | null };
  };
  evidence_strength?: number;
  n_addressable?: number;
  top_subcaps?: FitSubcapRow[];
  absent_families?: string[];
  sequence?: { rank: number | null; after: string[] };
  /** Prereq spec snapshot keyed by required_subcap_id — the accordion's
   *  drilldown payload. */
  prereqs?: Record<string, {
    name: string; threshold: number; status: string;
    current_score: number | null;
  }>;
}

/** One transformation-roadmap phase (D4 chevron view). Optional — the
 *  backend may emit only `roadmap_md` prose, in which case the component
 *  degrades to rendering that. */
export interface RoadmapPhase {
  phase: number;
  label: string;
  duration: string;
  platform: string;
  target: string;
  metric: string;
  color?: string | null;
  rec_ids?: string[];
  /** Customer-facing impact KVs for the "Customer impact" roadmap view. */
  customer_impact?: Record<string, string> | null;
  /** rec_ids from EARLIER phases this phase's recs depend on (Part 7.3). */
  dependencies?: string[];
}

export interface PlatformNarrative {
  recommendations_md?: string | null;
  roadmap_md?: string | null;
  gap_prioritization_md?: string | null;
  roadmap_phases?: RoadmapPhase[] | null;
}

export interface PlatformsResponse {
  entity_display_id: string;
  run_request_id: string | null;
  cards: PlatformCard[];
  pillar_offerings: Record<string, string[]>;
  narrative: PlatformNarrative | null;
}

/** Quantified expected outcomes on a rec (migration 048). */
export interface RecOutcomes {
  time?: string | null;
  effort?: string | null;
  metric?: string | null;
  peer?: string | null;
}

export interface RecListItem {
  id: string;
  rec_id: string;
  title: string;
  platform_id: string | null;
  /** Part 7.2 rich-card fields — drive the prototype Recommendations
   *  panel (root-cause chips + outcomes grid + phase pill). Optional:
   *  absent on pre-enrichment snapshots. */
  feature?: string | null;
  phase?: number | null;
  root_cause_e_ids?: string[];
  outcomes?: RecOutcomes | null;
}

export function useEntityRecommendationsList(displayId: string | null) {
  return useQuery({
    queryKey: ["entityRecsList", displayId],
    queryFn: () => apiGet<RecListItem[]>(`/api/v1/entities/${displayId}/recommendations`),
    enabled: displayId !== null,
    staleTime: 60_000,
  });
}

// D4 Transformation Roadmap — backend derives sequence-aware phases
// (explicit corpus phase → prerequisite DAG → effort band → uplift) from
// recommendations (GET /entities/{id}/platforms/roadmap).
export interface RoadmapRec {
  rec_id: string;
  title: string;
  platform_id: string;
  platform_name: string;
  maturity_lift: string | null;
  /** Part 7.3 additive per-rec fields. */
  feature?: string | null;
  metric?: string | null;
  outcomes?: RecOutcomes | null;
}
export interface RoadmapBackendPhase {
  phase: number;
  name: string;
  duration_months: number;
  recommendations: RoadmapRec[];
  /** Part 7.3 additive per-phase fields — real target ("M2 → M3 in
   *  P4C1"), top outcome metric, platform join, customer-impact KVs and
   *  cross-phase dependencies. All optional (older snapshots omit). */
  label?: string | null;
  target?: string | null;
  metric?: string | null;
  platform?: string | null;
  customer_impact?: Record<string, string> | null;
  dependencies?: string[];
}
export interface PlatformRoadmapResponse {
  entity_display_id: string;
  run_request_id: string | null;
  phases: RoadmapBackendPhase[];
  total_duration_months: number;
}

export function useEntityPlatformRoadmap(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<PlatformRoadmapResponse> {
  return useQuery({
    queryKey: ["platformRoadmap", displayId, run ?? "active"],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<PlatformRoadmapResponse>(
          `/api/v1/entities/${displayId}/platforms/roadmap`,
          { run: run ?? undefined },
        ), displayId, "platforms_roadmap"),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
}

/** Map the backend roadmap (phases + recs) to the RoadmapPhase[] the
 *  TransformationRoadmap component renders. Pure — unit-tested.
 *
 *  Part 7.3: the backend now emits REAL per-phase target ("M2 → M3 in
 *  P4C1"), metric (top extracted outcome metric), platform join and
 *  customer_impact — those win outright. The client-side derivation
 *  (maturity-lift target, rec-title-as-metric) survives ONLY as the
 *  fallback for older snapshots that lack the new fields. */
export function mapRoadmapPhases(resp: PlatformRoadmapResponse | undefined): RoadmapPhase[] {
  if (!resp?.phases?.length) return [];
  return resp.phases.map((p) => {
    const platforms = [...new Set(p.recommendations.map((r) => r.platform_name).filter(Boolean))];
    const lifts = p.recommendations.map((r) => r.maturity_lift).filter((x): x is string => !!x);
    return {
      phase: p.phase,
      label: p.label || p.name,
      duration: `${p.duration_months} mo`,
      platform: p.platform || platforms.slice(0, 2).join(" · ") || "—",
      target: p.target || (lifts.length ? `Maturity ${lifts[0]}` : "—"),
      metric: p.metric
        || p.recommendations.map((r) => r.metric).find((m): m is string => !!m)
        || p.recommendations[0]?.title
        || `${p.recommendations.length} recommendation(s)`,
      rec_ids: p.recommendations.map((r) => r.rec_id),
      customer_impact: p.customer_impact
        ?? (lifts.length ? { "Maturity lift": lifts.join(", ") } : undefined),
      dependencies: p.dependencies ?? undefined,
    };
  });
}

export interface AlertOut {
  id: string;
  kind: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  body: string;
  linked_subcap_ids: string[];
  linked_e_ids: string[];
  opened_at: string;
  closed_at: string | null;
  resolution: string | null;
  age_days: number;
  // 2026-06-05 QA finding 9: entity context for the AlertsPage row
  // navigation -- the page now reads entity_display_id to build a
  // valid /clients/:id/heatmap link.
  entity_id: string | null;
  entity_display_id: string | null;
  // Migration 040 (alerts producer): the wireframe health table's
  // Evidence n/3 mini-bar, recommended-action chip and proxy flag.
  // NULL for manually-raised alert kinds.
  evidence_count?: number | null;
  recommended_action?: string | null;
  proxy_searched?: boolean | null;
  entity_name: string | null;
}

// ---------- Query hooks ----------

export function useDashboard(scope: "mine" | "all"): UseQueryResult<DashboardResponse> {
  // JSON-pack-FIRST (2026-06-18 operator mandate "the app is to use the local
  // backfill ie the JSON files"): the committed startup-data pack is the source
  // of truth for the default (all-clients) dashboard, so a junk / stale / still-
  // warming live DB can never override the clean 94 (the recurring "100 junk
  // entities" dashboard). The drive backfill refreshes the pack. Scope "mine"
  // is user-specific (not in the pack) → live API.
  const packAuthoritative = scope === "all" && USE_STARTUP_PACK;
  return useQuery({
    queryKey: ["dashboard", scope],
    queryFn: packAuthoritative
      ? async () => STARTUP_DASHBOARD
      : () => apiGet<DashboardResponse>("/api/v1/dashboard", { scope }),
    staleTime: packAuthoritative ? Number.POSITIVE_INFINITY : 30 * 1000,
    // dev / e2e (not packAuthoritative): keep the original first-paint-then-
    // refetch so the live seeded backend drives the directory/dashboard.
    ...(scope === "all" && !USE_STARTUP_PACK
      ? { initialData: STARTUP_DASHBOARD, initialDataUpdatedAt: 0 }
      : {}),
  });
}

export function useEntities(opts: {
  owner: "me" | "all";
  subvertical?: string;
  search?: string;
}): UseQueryResult<EntityListResponse> {
  // Only the exact default scope (owner=all, no subvertical/search filters)
  // matches the committed snapshot's queryKey — guard so a filtered view
  // never paints the full snapshot.
  const isDefaultScope = opts.owner === "all" && !opts.subvertical && !opts.search;
  // JSON-pack-FIRST (live production only): the committed directory snapshot is
  // authoritative for the default (all-clients, unfiltered) view, so a junk live
  // DB can't repaint it with ~100 junk-named entities. Filtered / search /
  // owner=me views are dynamic → live API. In dev/e2e/standalone the live API
  // drives it (so the seeded-entity e2e assertion holds).
  const packAuthoritative = isDefaultScope && USE_STARTUP_PACK;
  return useQuery({
    queryKey: ["entities", opts.owner, opts.subvertical ?? "", opts.search ?? ""],
    queryFn: packAuthoritative
      ? async () => STARTUP_ENTITIES
      : () =>
          apiGet<EntityListResponse>("/api/v1/entities", {
            owner: opts.owner,
            subvertical: opts.subvertical,
            search: opts.search,
          }),
    staleTime: packAuthoritative ? Number.POSITIVE_INFINITY : 60 * 1000,
    ...(isDefaultScope && !USE_STARTUP_PACK
      ? { initialData: STARTUP_ENTITIES, initialDataUpdatedAt: 0 }
      : {}),
  });
}

export function useEntityOverview(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<EntityOverviewResponse> {
  const aud = useAudienceForKey();
  return useQuery({
    queryKey: ["entityOverview", displayId, run ?? "active", aud],
    // Default (active-run) view → serve the committed pack first; a specific
    // selected run isn't in the pack → live API first.
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<EntityOverviewResponse>(`/api/v1/entities/${displayId}/overview`, {
          run: run ?? undefined,
        }), displayId, "overview"),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

// ── D3 archetype + D5 cross-pillar stories ───────────────────────────────
// Two standalone-only intelligence surfaces ported to the live tree. Both
// endpoints already exist and neither is gated on the 94-package re-ingest
// (archetype ← peer_patterns worker; cross-pillar ← catalogue load). Plain
// useQuery (not part of the startup snapshot pack).

export interface ArchetypeMatch {
  archetype_label: string;
  subvertical: string;
  catalogue_version: string;
  distance: number;
  defining_subcap_ids: string[];
  sample_count: number;
  silhouette_score: number | null;
}

export interface ArchetypeResponse {
  closest: ArchetypeMatch | null;
  all_archetypes: ArchetypeMatch[];
  insufficient_data: boolean;
}

export function useEntityArchetype(
  displayId: string | null,
): UseQueryResult<ArchetypeResponse> {
  return useQuery({
    queryKey: ["entityArchetype", displayId],
    queryFn: () =>
      apiGet<ArchetypeResponse>(`/api/v1/entities/${displayId}/archetype`),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export interface CrossPillarStoryOut {
  story_key: string;
  origin_pillar: string;
  origin_subcap_id: string;
  origin_capability: string | null;
  target_pillar: string;
  themes: string[];
  subcaps_touched: string[];
  sample_subcap_names: string[];
  why_this_matters: string | null;
}

export interface CrossPillarStoryListResponse {
  entity_display_id: string;
  catalogue_version: string;
  pillar_filter: string | null;
  total: number;
  stories: CrossPillarStoryOut[];
  state: string;
}

export function useCrossPillarStories(
  displayId: string | null,
  pillar?: string | null,
): UseQueryResult<CrossPillarStoryListResponse> {
  return useQuery({
    queryKey: ["crossPillarStories", displayId, pillar ?? "all"],
    queryFn: () =>
      apiGet<CrossPillarStoryListResponse>(
        `/api/v1/entities/${displayId}/cross-pillar-stories`,
        pillar ? { pillar } : undefined,
      ),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function useEntityInsights(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<InsightListResponse> {
  const aud = useAudienceForKey();
  // 2026-06-05: include `run` in both the query key + query string so
  // the operator's ClientBar run selection actually drives the data.
  // `run` is the run's request_id (REQ-...) -- matches what the URL
  // carries on ?run= so deep-links into a specific run round-trip.
  return useQuery({
    queryKey: ["entityInsights", displayId, run ?? "active", aud],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<InsightListResponse>(`/api/v1/entities/${displayId}/insights`, {
          run: run ?? undefined,
        }), displayId, "insights"),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function useEntityHeatmap(
  displayId: string | null,
  params: { zoom?: string; hm?: string; peer?: boolean; issues?: boolean; run?: string | null },
): UseQueryResult<HeatmapResponse> {
  const aud = useAudienceForKey();
  return useQuery({
    queryKey: [
      "entityHeatmap", displayId, params.zoom, params.hm,
      params.peer, params.issues, params.run ?? "active", aud,
    ],
    // Snapshot routing (2026-07 D3 pack fidelity): the pack now bakes
    // peer=true (real medians cold), a category-grain names surface, and
    // the hm=value_chain zoom=subcap state. Snapshot-first for any
    // active-run view without the issues overlay — peer on/off is a pure
    // render toggle (cells always carry peer_median in the pack; the FE
    // gates the Peer row on local state), and hm=focus is a client-side
    // FILTER over the same subcap grid, so the standard snapshot is a
    // safe superset. A ?run= selection or issues overlay is dynamic →
    // live API first.
    queryFn: () => {
      const surface =
        (params.hm ?? "standard") === "value_chain"
          ? "heatmap_value_chain"
          : params.zoom === "subcap"
            ? "heatmap"
            : params.zoom === "category"
              ? "heatmap_category"
              : "heatmap_pillar";
      return (USE_STARTUP_PACK && !params.run && !params.issues
        ? snapshotOrApi
        : apiOrSnapshot)(() =>
        apiGet<HeatmapResponse>(`/api/v1/entities/${displayId}/heatmap`, {
          zoom: params.zoom ?? "pillar",
          hm: params.hm ?? "standard",
          peer: params.peer ? "true" : undefined,
          issues: params.issues ? "true" : undefined,
          run: params.run ?? undefined,
        }), displayId, surface);
    },
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function useEntityPlatforms(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<PlatformsResponse> {
  const aud = useAudienceForKey();
  return useQuery({
    queryKey: ["entityPlatforms", displayId, run ?? "active", aud],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<PlatformsResponse>(`/api/v1/entities/${displayId}/platforms`, {
          run: run ?? undefined,
        }), displayId, "platforms"),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

// ── Customer-view-forced variants (QA-6, 2026-06-06) ──────────────────
//
// `useEntityOverview` / `useEntityPlatforms` honour the GLOBAL audience.
// They emit `view=customer` only when the AE has toggled the chrome
// into customer mode. The Prospecting "Scorecard" preview, however,
// claims to be "always Customer-safe -- internal fields are stripped"
// regardless of the operator's chrome state. Until these forced
// variants existed, that claim was a lie: an internal AE saw the
// preview render with internal-only fields.
//
// The forced variants pass `view: "customer"` explicitly in the query
// params. `withAudienceQuery` honours caller-provided `view` (never
// overrides), so the backend ALWAYS gets `view=customer` and the
// `audience_strip` middleware removes internal fields server-side
// before they hit the wire.
//
// The query key includes a stable `"customer"` literal so this is a
// SEPARATE cache entry from the audience-honouring variant -- an AE
// who's already loaded internal overview AND opens the Prospecting
// preview gets two distinct cached responses. No cross-contamination.

export function useEntityOverviewAsCustomer(
  displayId: string | null,
): UseQueryResult<EntityOverviewResponse> {
  return useQuery({
    queryKey: ["entityOverview", displayId, "active", "customer:forced"],
    queryFn: () =>
      apiGet<EntityOverviewResponse>(`/api/v1/entities/${displayId}/overview`, {
        view: "customer",
      }),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function useEntityPlatformsAsCustomer(
  displayId: string | null,
): UseQueryResult<PlatformsResponse> {
  return useQuery({
    queryKey: ["entityPlatforms", displayId, "active", "customer:forced"],
    queryFn: () =>
      apiGet<PlatformsResponse>(`/api/v1/entities/${displayId}/platforms`, {
        view: "customer",
      }),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function useAlerts(): UseQueryResult<{ items: AlertOut[]; open_count: number }> {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => apiGet<{ items: AlertOut[]; open_count: number }>("/api/v1/alerts"),
    staleTime: 30 * 1000,
  });
}

// ---------- Mutations ----------

interface NewRunInput {
  entity_name: string;
  entity_domain?: string;
  notes?: string;
  urls?: string[];
  materials_gs_urls?: string[];
  priority?: "low" | "normal" | "high" | "urgent";
  parent_request_id?: string;
  is_rerun?: boolean;
}

interface NewRunResult {
  request_id: string;
  sheet_row_url: string | null;
  eta_minutes: number | null;
  evidence_mode: "public" | "hybrid";
  state: "SUBMITTED" | "BOT_ACCEPTED";
}

export function useRequestNewRun(): UseMutationResult<NewRunResult, Error, NewRunInput> {
  return useMutation({
    mutationFn: (input) => apiPost<NewRunResult>("/api/v1/runs/new", input),
  });
}

export function useUpdateUserRole(): UseMutationResult<
  unknown, Error, { userId: string; role: "ADMIN" | "ANALYST" | "AE" | "CUSTOMER" }
> {
  return useMutation({
    mutationFn: ({ userId, role }) =>
      apiPatch<unknown>(`/api/v1/admin/users/${userId}/role`, { role }),
  });
}

// ============================================================================
// 2026-06 wireframe rebuild — D5 Context, D6 Health, and the three new
// write surfaces (insight annotations, focus-area KPI overrides,
// notifications) + prospecting scorecard export. Types mirror the backend
// Pydantic schemas added in the rebuild (app/schemas/context.py, health.py,
// write_surfaces.py) so the React pages bind to real fields — no placeholders.
// ============================================================================

// ---------- Run history (D8 + ClientBar run selector) ----------
export interface RunHistoryItem {
  id: string;
  request_id: string;
  status: "IN_PROGRESS" | "ACTIVE" | "SUPERSEDED";
  data_source: string;
  completed_at: string | null;
  overall_score?: number | null;
  evidence_mode?: "public" | "hybrid" | null;
  /** Migration 039: the run's official assessment date — the wireframe
   *  RUN DATE. NULL for pre-039 REQ-hex rows; consumers fall back to
   *  completed_at (the ingest completion timestamp). */
  assessment_date?: string | null;
  assessment_date_source?: string | null;
  subcap_count?: number | null;
}

export interface RunHistoryResponse {
  items: RunHistoryItem[];
}

export function useEntityRuns(displayId: string | null): UseQueryResult<RunHistoryResponse> {
  return useQuery({
    queryKey: ["entityRuns", displayId],
    queryFn: () =>
      (USE_STARTUP_PACK ? snapshotOrApi : apiOrSnapshot)(() =>
        apiGet<RunHistoryResponse>(`/api/v1/entities/${displayId}/runs`),
        displayId, "runs"),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
}

// ---------- D5 Context (B-2 / B-3 / B-4) ----------
export interface TimelineEventOut {
  id: string;
  event_date: string;
  kind: string;
  title: string;
  body: string | null;
  source_url: string | null;
  e_id: string | null;
  /** Migration 047 (NLP event pipeline) — all additive; absent/empty on
   *  rows persisted before the re-derivation. `signal` is the
   *  polarity-classified event signal (native to the claim, not
   *  inferred from kind). */
  signal?: string | null;
  /** day | month | quarter | year | publish_fallback — jitter/cluster
   *  dots by precision so fallback-date pile-ups don't read as real
   *  same-day bursts. */
  date_precision?: string | null;
  /** Multi-value evidence anchors; supersedes the scalar e_id. */
  evidence_e_ids?: string[];
  /** Capability links for the EventDetail cap-impact chips. */
  subcap_ids?: string[];
}

export interface IssueRegisterOut {
  id: string;
  issue_id: string;
  title: string;
  severity: string;
  rationale: string | null;
  opened_on: string | null;
  resolved_on: string | null;
  status: "OPEN" | "RESOLVED";
  linked_subcap_ids: string[];
  /** DMA-impact attribution (2026-07-06, additive - absent on old packs). */
  kind?: string;
  dma_impact?: string | null;
  /** Per-capability cap levels the issue imposes: {"P1C2": 3.0}. */
  caps?: Record<string, number>;
}

export interface AcquisitionOut {
  id: string;
  event_date: string;
  title: string;
  body: string | null;
  source_url: string | null;
  e_id: string | null;
  /** Structured acquisition frame (Part 8.3, prototype ACQ shape) — all
   *  Optional; legacy rows keep the title/body/e_id shape and the panel
   *  degrades gracefully. `amount` is the verbatim deal-size string;
   *  `status` ∈ announced | closed | integrating when present. */
  target?: string | null;
  acquirer?: string | null;
  amount?: string | null;
  status?: string | null;
  announced_on?: string | null;
  closed_on?: string | null;
  details?: string | null;
}

/** Multi-year financial view (B-3) lifted from firmographics.financial_highlights. */
export interface FinancialsView {
  years?: number[];
  series?: Record<string, number[]>;
  metrics?: Record<string, unknown>;
  lines?: string[];
}

export interface PeerComparison {
  peer_name: string;
  role: string | null;
  overall_score: number | null;
  category_scores: Record<string, number>;
}

export interface ContextResponse {
  entity_display_id: string;
  run_request_id: string | null;
  timeline_events: TimelineEventOut[];
  issue_register: IssueRegisterOut[];
  acquisitions: AcquisitionOut[];
  firmographics: Record<string, unknown> | null;
  financials: FinancialsView | null;
  sentiment: Record<string, unknown> | null;
  peers?: PeerComparison[];
  narrative: Record<string, unknown> | null;
}

export function useEntityContext(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<ContextResponse> {
  const aud = useAudienceForKey();
  return useQuery({
    queryKey: ["entityContext", displayId, run ?? "active", aud],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<ContextResponse>(`/api/v1/entities/${displayId}/context`, {
          run: run ?? undefined,
        }), displayId, "context"),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
}

// ---------- D6 Health (B-5 evidence_age) ----------
export interface SafeguardGateOut {
  gate_id: string;
  status: "PASS" | "PARTIAL" | "FAIL" | "DEFERRED";
  detail: string | null;
  evaluated_at: string;
}

export interface EvidenceAgeOut {
  e_id: string;
  source_name: string;
  tier: number;
  published_date: string | null;
  recency_months: number | null;
  freshness_band: FreshnessBand;
}

/** C10 (2026-06-07): one cap-event row from `caps_applied_log`.
 *
 * Surfaces "this subcap scored M2.5 because IR-003 severity capped
 * it" defensibility on D6 Health Gates tab. Sources:
 *   - `07_governance/caps_applied_log.csv` for 4 of 5 real fixtures;
 *   - inline `subcap_scores.caps_applied` string for WSFS-shape
 *     packages (cascaded into the same response by the backend).
 */
export interface CapsAppliedOut {
  log_id: string;
  subcap_id: string;
  cap_type: string | null;
  trigger_condition: string | null;
  cap_ceiling: string | null;
  trigger_evidence: string[];
  affected_categories: string[];
  severity: string | null;
  date_applied: string | null;
  recalc_verified: string | null;
}

/** C5 (2026-06-07): one verdict from the 2-stage QA chain. */
export interface QaVerdictOut {
  verdict: string | null;
  recommendation: string | null;
  verdict_basis: string | null;
  governance_skill_version: string | null;
}

/**
 * C7 (2026-06-07): bot governance audit logs envelope.
 *
 * Each `reasoning_chain` entry has at minimum `subcap_id` + a
 * `decision_path: string[]` (Nicola ships 12 subcaps × 5 steps).
 * Each `contradictions` entry has at minimum `contradiction_id` +
 * `subcap_id` + `winner` + `justification`.
 *
 * Both lists are open Record shapes so extras (final_score,
 * confidence_impact, etc.) flow through unchanged. Strongly-typed
 * known fields surface on the D6 Audit tab; unknown extras render
 * via Object.entries().
 */
export interface AuditLogsOut {
  reasoning_chain: Array<{
    subcap_id: string;
    category?: string;
    decision_path: string[];
    [k: string]: unknown;
  }>;
  contradictions: Array<{
    contradiction_id: string;
    subcap_id?: string;
    evidence_a_id?: string;
    evidence_b_id?: string;
    winner?: string;
    justification?: string;
    contradiction_type?: string;
    [k: string]: unknown;
  }>;
}

export interface HealthResponse {
  entity_display_id: string;
  run_request_id: string | null;
  thin_evidence_subcap_ids: string[];
  safeguard_gates: SafeguardGateOut[];
  alerts: AlertOut[];
  evidence_age: EvidenceAgeOut[];
  caps_applied: CapsAppliedOut[];
  /** C5: first-pass verdict; null when only L2 was shipped. */
  qa_verdict_l1: QaVerdictOut | null;
  /** C5: final-review verdict (canonical qa_verdict.json); null when absent. */
  qa_verdict_l2: QaVerdictOut | null;
  /** C7: bot reasoning chain + contradiction adjudication. null when none shipped. */
  audit_logs: AuditLogsOut | null;
  narrative: Record<string, unknown> | null;
}

export function useEntityHealth(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<HealthResponse> {
  const aud = useAudienceForKey();
  return useQuery({
    queryKey: ["entityHealth", displayId, run ?? "active", aud],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<HealthResponse>(`/api/v1/entities/${displayId}/health`, {
          run: run ?? undefined,
        }), displayId, "health"),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
}

// ---------- B-7 insight annotations ----------
export type AnnotationStatus = "ACTIONED" | "PENDING" | "SUPERSEDED";

export interface AnnotationOut {
  id: string;
  ic_id: string;
  author: string;
  role: string;
  body: string;
  status: AnnotationStatus;
  sf_opp_id: string | null;
  created_at: string;
}

export interface AnnotationListResponse {
  entity_display_id: string;
  ic_id: string;
  items: AnnotationOut[];
}

export function useInsightAnnotations(
  displayId: string | null,
  icId: string | null,
): UseQueryResult<AnnotationListResponse> {
  return useQuery({
    queryKey: ["insightAnnotations", displayId, icId],
    queryFn: () =>
      apiGet<AnnotationListResponse>(
        `/api/v1/entities/${displayId}/insights/${icId}/annotations`,
      ),
    enabled: !!displayId && !!icId,
    staleTime: 30 * 1000,
  });
}

export function useSaveAnnotation(): UseMutationResult<
  AnnotationOut,
  Error,
  { displayId: string; icId: string; body: string; status: AnnotationStatus; sf_opp_id?: string | null }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ displayId, icId, body, status, sf_opp_id }) =>
      apiPost<AnnotationOut>(
        `/api/v1/entities/${displayId}/insights/${icId}/annotations`,
        { body, status, sf_opp_id },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["insightAnnotations", vars.displayId, vars.icId] });
    },
  });
}

// ---------- Focus areas (parsed list) ----------
export interface FocusAreaOut {
  id: string;
  title: string;
  verbatim_quote: string;
  source_path: string;
  page_number: number | null;
  involved_subcap_ids: string[];
  /** Migration 052 (grounding fix) — all additive; absent/null on rows
   *  persisted before the synthesizer rewrite. */
  grounding?: {
    representative_quote?: string | null;
    evidence_e_ids?: string[];
    source_kind?: "docx" | "gemini" | "heuristic" | string;
  } | null;
  /** Quantities match against the financial series (SOURCE block). */
  financial_ref?: string | null;
  /** Server-computed catalogue-weight share per pillar (replaces the
   *  FE count-share proxy). */
  pillars_weight?: Record<string, number> | null;
  /** KPI rows for the CustomizableKpiStrip [{label, current, target,
   *  delta, source_mode}] — [] until derive_focus_area_kpis seeds them. */
  kpis?: Array<Record<string, unknown>>;
}

export interface FocusAreaListResponse {
  entity_display_id: string;
  items: FocusAreaOut[];
}

export function useFocusAreas(
  displayId: string | null,
  run?: string | null,
): UseQueryResult<FocusAreaListResponse> {
  // Focus areas are the D3 DEFAULT view: cold serve used to land on an
  // empty page for all 94 because this hook had NO snapshot fallback and
  // focus_areas wasn't a pack surface. Now the committed `focus_areas`
  // page snapshot serves first (active-run view); a `?run=` selection is
  // dynamic → live API first (audit transition #24: focus follows ?run=).
  return useQuery({
    queryKey: ["focusAreas", displayId, run ?? "active"],
    queryFn: () =>
      (run || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<FocusAreaListResponse>(`/api/v1/entities/${displayId}/focus-areas`, {
          run: run ?? undefined,
        }), displayId, "focus_areas"),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
}

// ---------- Focus-area synthesis (Gemini fallback) ----------
// Triggers backend `POST /entities/{id}/focus-areas:synthesize` — the
// Gemini-powered cluster + match-to-recommendations flow. Invalidates
// the focus areas list query on success so the heatmap re-renders with
// the synthesized rows.
export interface SynthesizedFocusArea {
  title: string;
  description: string;
  involved_subcap_ids: string[];
  matched_recommendation_ids: string[];
  data_source: "gemini-flash" | "heuristic";
  rationale: string;
}
export interface SynthesizeFocusAreasResponse {
  ok: boolean;
  reason: string;
  message: string;
  data_source?: "gemini-flash" | "heuristic";
  focus_areas: SynthesizedFocusArea[];
  persisted_count?: number;
}
export function useSynthesizeFocusAreas(): UseMutationResult<
  SynthesizeFocusAreasResponse,
  Error,
  { displayId: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ displayId }) =>
      apiPost<SynthesizeFocusAreasResponse>(
        `/api/v1/entities/${displayId}/focus-areas:synthesize`, {},
      ),
    onSuccess: (_data, { displayId }) => {
      void qc.invalidateQueries({ queryKey: ["focusAreas", displayId] });
    },
  });
}

// ---------- B-8 focus-area KPI overrides ----------
export type KpiSourceMode = "public" | "client" | "hidden";

export interface KpiOverrideOut {
  fa_id: string;
  kpi_label: string;
  source_mode: KpiSourceMode;
  current_value: string | null;
  target_value: string | null;
  updated_at: string;
}

export interface KpiOverrideListResponse {
  entity_display_id: string;
  fa_id: string;
  items: KpiOverrideOut[];
}

export interface KpiOverrideInput {
  kpi_label: string;
  source_mode: KpiSourceMode;
  current_value?: string | null;
  target_value?: string | null;
}

export function useFocusAreaKpis(
  displayId: string | null,
  faId: string | null,
): UseQueryResult<KpiOverrideListResponse> {
  return useQuery({
    queryKey: ["focusAreaKpis", displayId, faId],
    queryFn: () =>
      apiGet<KpiOverrideListResponse>(
        `/api/v1/entities/${displayId}/focus-areas/${faId}/kpis`,
      ),
    enabled: !!displayId && !!faId,
    staleTime: 60 * 1000,
  });
}

export function useSaveKpiOverrides(): UseMutationResult<
  KpiOverrideListResponse,
  Error,
  { displayId: string; faId: string; overrides: KpiOverrideInput[] }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ displayId, faId, overrides }) =>
      apiPut<KpiOverrideListResponse>(
        `/api/v1/entities/${displayId}/focus-areas/${faId}/kpis`,
        { overrides },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["focusAreaKpis", vars.displayId, vars.faId] });
    },
  });
}

// ---------- B-9 notifications ----------
export interface NotificationOut {
  id: string;
  kind: "alert" | "completion" | "system";
  title: string;
  body: string | null;
  entity_id: string | null;
  route: string | null;
  seen_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationOut[];
  unseen_count: number;
}

// Global quick-search (TopBar ⌘K palette). One query, three surfaces;
// each hit carries a ready-to-render kind/title/sub/route/icon from the
// backend so the popover is a thin renderer (mirrors chrome.jsx).
export interface SearchHit {
  kind: "entity" | "insight" | "evidence";
  title: string;
  sub: string;
  route: string;
  icon: string;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchHit[];
}

/** Live multi-surface search. Disabled below 2 chars — the popover shows
 *  static "Quick links" instead, so we never fire a `%a%` corpus scan. */
export function useSearch(q: string): UseQueryResult<SearchResponse> {
  const term = q.trim();
  return useQuery({
    queryKey: ["search", term],
    queryFn: () => apiGet<SearchResponse>("/api/v1/search", { q: term }),
    enabled: term.length >= 2,
    staleTime: 30 * 1000,
    // Keep the prior results painted while the next keystroke resolves so
    // the list doesn't blank-flash on every character.
    placeholderData: (prev) => prev,
  });
}

export function useNotifications(): UseQueryResult<NotificationListResponse> {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiGet<NotificationListResponse>("/api/v1/notifications"),
    staleTime: 30 * 1000,
  });
}

export function useMarkNotificationsRead(): UseMutationResult<
  { marked_read: number },
  Error,
  { ids?: string[] }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ids }) =>
      apiPost<{ marked_read: number }>("/api/v1/notifications:mark-read", { ids: ids ?? [] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

// ---------- B-6 prospecting scorecard export ----------
/**
 * Triggers a customer-safe scorecard download. Returns the object URL +
 * filename; the caller revokes the URL after the click. `format=pdf`
 * surfaces the backend's 501 (optional weasyprint extra) as an Error.
 *
 * 2026-06-06 QA-M7: switched from raw `fetch` to the shared `apiBlob`
 * helper. Pre-fix, this bypassed the 15s timeout, the
 * `dma:auth-expired` 401 hook, and the audience injection. An AE who
 * let their session expire and clicked Export saw an opaque
 * "Export failed (401)" with no re-login prompt; now the same auth-
 * expired event fires here as on every other endpoint.
 */
export async function exportScorecard(
  displayId: string,
  format: "html" | "pdf",
): Promise<{ url: string; filename: string }> {
  // Canonical filename for the download attribute. The backend's
  // Content-Disposition header may or may not be preserved through
  // Cloud Run + any browser-extension content scripts; we ALWAYS
  // emit a deterministic filename to keep the download UX consistent.
  const canonicalFilename = `dma-scorecard-${displayId}.${format}`;
  try {
    const { blob } = await apiBlob(
      `/api/v1/prospecting/${displayId}/export`,
      { method: "POST", query: { format } },
    );
    return {
      url: URL.createObjectURL(blob),
      filename: canonicalFilename,
    };
  } catch (err) {
    if (err instanceof ApiError) {
      throw new Error(
        err.status === 501
          ? "PDF export isn't enabled on this server (HTML is available)."
          : `Export failed (${err.status}): ${err.message.slice(0, 200)}`,
      );
    }
    throw err;
  }
}

export function useExportScorecard(): UseMutationResult<
  { url: string; filename: string },
  Error,
  { displayId: string; format: "html" | "pdf" }
> {
  return useMutation({
    mutationFn: ({ displayId, format }) => exportScorecard(displayId, format),
  });
}

// ── D6 Health: cross-entity patterns + feedback-file refresh ───────────────
export interface CrossEntityPatternOut {
  pattern_type: string;
  pattern_key: string;
  pattern_label: string;
  primary_subcap_id: string | null;
  entity_count: number;
  severity_mix: Record<string, number>;
  median_peer_gap: number | null;
  sample_subcap_ids: string[];
}

export interface HealthPatternsResponse {
  entity_display_id: string;
  run_request_id: string | null;
  subvertical: string | null;
  catalogue_version: string | null;
  patterns: CrossEntityPatternOut[];
  state: string; // full | no_cohort | insufficient_data | no_active_run
}

export function useHealthPatterns(
  displayId: string | null,
): UseQueryResult<HealthPatternsResponse> {
  return useQuery({
    queryKey: ["healthPatterns", displayId],
    queryFn: () => apiGet<HealthPatternsResponse>(
      `/api/v1/entities/${displayId}/health/patterns`,
    ),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export interface FeedbackRefreshResponse {
  entity_display_id: string;
  run_request_id: string | null;
  state: string;
  written: string[];
  failed: string[];
}

export function useRefreshEntityFeedbackFiles(
  displayId: string | null,
): UseMutationResult<FeedbackRefreshResponse, Error, void> {
  return useMutation({
    mutationFn: () => apiPost<FeedbackRefreshResponse>(
      `/api/v1/entities/${displayId}/feedback-files:refresh`,
    ),
  });
}

export interface FeedbackRefreshAllResponse {
  total: number;
  by_state: Record<string, number>;
  results: {
    entity_display_id: string; state: string;
    written: string[]; failed: string[];
  }[];
}

export function useRefreshAllFeedbackFiles(): UseMutationResult<
  FeedbackRefreshAllResponse, Error, void
> {
  return useMutation({
    mutationFn: () => apiPost<FeedbackRefreshAllResponse>(
      "/api/v1/admin/feedback-files:refresh-all",
    ),
  });
}

// ---------- D7 TechStack (Part 9 honest read model) ----------
//
// The backend now serves the 4-state deployment enum (CONFIRMED / INFERRED /
// CLAIMED / ABSENT, plus CONFIRMED_REMOVED) with server-generated ABSENT
// gap rows per scored platform family, real `since` (mined from evidence,
// never the ingest timestamp), a clean `note`, cohort `peer_coverage` and
// the L1-L5 layer ladder. Committed pre-Part-9 pack snapshots may still
// carry the legacy DETECTED status — TechStackPage.mapStatus normalises.

export type TechStackStatus =
  | "CONFIRMED" | "INFERRED" | "CLAIMED" | "ABSENT" | "CONFIRMED_REMOVED";

export interface TechStackEntryOut {
  id: string;
  tech_id: string;
  vendor: string;
  product: string;
  product_name: string;
  layer: "foundation" | "platform" | "application" | "intelligence";
  // New payloads carry TechStackStatus; legacy snapshots may say DETECTED.
  status: TechStackStatus | "DETECTED" | string;
  l3_id: string | null;
  source: string;
  evidence_e_ids: string[];
  linked_subcap_ids: string[];
  // NULL on server-generated ABSENT gap rows.
  detected_at: string | null;
  since?: string | null;
  note?: string | null;
  peer_coverage?: number | null;
  primary_gap?: boolean;
  layer_code?: string | null;
  layer_full?: string | null;
  dma_pillar?: string | null;
}

export interface TechStackResponse {
  entity_display_id: string;
  items: TechStackEntryOut[];
  last_synced_at: string | null;
  engineering_signal_count?: number;
  engineering_signals?: string[];
  review_queue_count?: number;
}

export interface TechPeerDeployment {
  name: string;
  has_tech: boolean;
}

export interface TechSubcapImpact {
  subcap_id: string;
  name?: string | null;
  score?: number | null;
  peer_median?: number | null;
  thin?: boolean;
}

export interface TechStackDetailResponse {
  entry: TechStackEntryOut;
  linked_subcap_ids: string[];
  evidence_e_ids: string[];
  peer_adoption_count: number;
  peer_coverage?: number | null;
  cohort_size?: number | null;
  cohort_label?: string | null;
  peer_names?: TechPeerDeployment[];
  impacts?: TechSubcapImpact[];
  gap_zones?: string[];
}

export function useTechStack(
  displayId: string | null,
): UseQueryResult<TechStackResponse> {
  return useQuery({
    queryKey: ["techStack", displayId],
    // JSON-pack-first: serve the committed techstack.json snapshot (the 94
    // starter pages) so a junk/stale live DB can't override it; the live API
    // is the fallback only for a client with no snapshot yet.
    queryFn: () => (USE_STARTUP_PACK ? snapshotOrApi : apiOrSnapshot)<TechStackResponse>(
      () => apiGet<TechStackResponse>(`/api/v1/entities/${displayId}/techstack`),
      displayId, "techstack",
    ),
    enabled: displayId !== null,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Pure fallback shape: hydrate a detail payload from an already-snapshotted
 * techstack LIST row. No per-tech snapshot exists in the pack, so on a cold
 * backend the detail page degrades to the list row's fields (cohort peers /
 * named impacts arrive once the API warms — nothing is fabricated).
 */
export function detailFromListRow(
  row: TechStackEntryOut,
): TechStackDetailResponse {
  return {
    entry: row,
    linked_subcap_ids: row.linked_subcap_ids ?? [],
    evidence_e_ids: row.evidence_e_ids ?? [],
    peer_adoption_count: 0,
    peer_coverage: row.peer_coverage ?? null,
    cohort_size: null,
    cohort_label: null,
    peer_names: [],
    impacts: (row.linked_subcap_ids ?? []).map((sid) => ({ subcap_id: sid })),
    gap_zones: [],
  };
}

/**
 * Detail fetch with the cheap pack fallback (Part 9.2): live API first;
 * when it fails cold, find the row in the committed techstack list
 * snapshot and hydrate the detail from it. Re-throws the original error
 * when the snapshot doesn't carry the tech either.
 */
export async function fetchTechStackDetail(
  displayId: string,
  techId: string,
): Promise<TechStackDetailResponse> {
  try {
    return await apiGet<TechStackDetailResponse>(
      `/api/v1/entities/${displayId}/techstack/${encodeURIComponent(techId)}`,
    );
  } catch (err) {
    const snap = await pageSnapshot<TechStackResponse>(displayId, "techstack");
    const row = snap?.items?.find((i) => i.tech_id === techId);
    if (row) return detailFromListRow(row);
    throw err;
  }
}

export function useTechStackDetail(
  displayId: string | null,
  techId: string | null,
): UseQueryResult<TechStackDetailResponse> {
  return useQuery({
    queryKey: ["techDetail", displayId, techId],
    queryFn: () => fetchTechStackDetail(displayId as string, techId as string),
    enabled: displayId !== null && techId !== null,
    staleTime: 5 * 60_000,
  });
}
