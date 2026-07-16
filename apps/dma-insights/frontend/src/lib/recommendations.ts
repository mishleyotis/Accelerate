/**
 * Recommendation detail typed hook.
 *
 * State-branch contract (driving the modal):
 *   - rec_id null              → query disabled
 *   - isLoading                → spinner row in the modal body
 *   - error/404                → "Couldn't load recommendation" empty
 *   - unresolved_count > 0     → amber "Pending review" banner above
 *                                the cited refs (cited ids that didn't
 *                                resolve render with strikethrough)
 *   - unresolved_count == 0    → happy: all citations clickable +
 *                                resolved name shown
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "./api";

export interface CitedReference {
  kind: "feature" | "construct" | "agent";
  id: string;
  resolved: boolean;
  name: string | null;
}

export interface RecommendationDetail {
  id: string;
  rec_id: string;
  title: string;
  description: string;
  entity_display_id: string;
  target_subcap_ids: string[];
  platform_id: string | null;
  addressable_offerings: string[];
  uplift_per_pillar: Record<string, number> | null;
  effort_band: string | null;
  cited_features: CitedReference[];
  cited_constructs: CitedReference[];
  cited_agents: CitedReference[];
  unresolved_count: number;
  catalogue_version: string;
  // D4 DependencyMap: prerequisites (parsed at ingest) + the read-time
  // inverse unlocks. Both empty until the corpus is re-ingested.
  dependencies: { prerequisites: string[]; unlocks: string[] };
  /** Migration 048 (recommendations_detail.json / REC-NN.json ingest) —
   *  all additive; absent/empty until re-ingest fills them. `feature`
   *  is the concrete platform feature the rec ships; `phase` feeds the
   *  multi-phase roadmap. */
  feature?: string | null;
  phase?: number | null;
  /** E-IDs grounding the rec's root cause (modal "Root-cause evidence"
   *  tab). */
  root_cause_e_ids?: string[];
  /** Quantified expected outcomes {time, effort, metric, peer}. */
  outcomes?: {
    time?: string | null;
    effort?: string | null;
    metric?: string | null;
    peer?: string | null;
  } | null;
}

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/**
 * Detail-fetch path builder (exported for the vitest ID contract).
 *
 * The stairstep curve and roadmap chevrons only hold the human-readable
 * `REC-NN` display code — codes are unique per run, not globally, so a
 * non-UUID id must carry the `display_id` scope for the backend to
 * resolve it (2026-07-06 drilldown-load fix; previously the code hit the
 * UUID-only lookup and 500'd, so those openers never loaded).
 */
export function recommendationDetailPath(
  recommendationId: string,
  displayId: string | null,
): string {
  const base = `/api/v1/recommendations/${encodeURIComponent(recommendationId)}`;
  if (!UUID_RE.test(recommendationId) && displayId) {
    return `${base}?display_id=${encodeURIComponent(displayId)}`;
  }
  return base;
}

/** Compose a RecommendationDetail from the client's baked roadmap row —
 * the pack-first fallback when the live API can't resolve the rec
 * (2026-07-06 deploy review: "I cannot load the recommendation from the
 * platform page" — pack rows carry rec_id forms, the endpoint knew only
 * uuids, and the hook had no snapshot tier at all). */
async function recFromSnapshot(
  recommendationId: string,
  displayId: string | null,
): Promise<RecommendationDetail | null> {
  if (!displayId) return null;
  const { pageSnapshot } = await import("./startup-pages");
  const rd = await pageSnapshot<{
    phases?: Array<{ recommendations?: Array<Record<string, unknown>> }>;
  }>(displayId, "platforms_roadmap");
  const want = recommendationId.toUpperCase();
  for (const ph of rd?.phases ?? []) {
    for (const r of ph.recommendations ?? []) {
      const rid = String(r.rec_id ?? r.id ?? "").toUpperCase();
      if (rid !== want && String(r.id ?? "") !== recommendationId) continue;
      const out = (r.outcomes ?? null) as RecommendationDetail["outcomes"];
      return {
        id: String(r.id ?? rid),
        rec_id: String(r.rec_id ?? rid),
        title: String(r.title ?? ""),
        description: String(r.description ?? r.body ?? ""),
        entity_display_id: displayId,
        target_subcap_ids: (r.target_subcap_ids as string[]) ?? [],
        platform_id: (r.platform_id as string) || null,
        addressable_offerings: [],
        uplift_per_pillar: null,
        effort_band: (r.effort_band as string) ?? null,
        cited_features: [], cited_constructs: [], cited_agents: [],
        unresolved_count: 0,
        catalogue_version: "",
        dependencies: { prerequisites: [], unlocks: [] },
        feature: (r.feature as string) ?? null,
        phase: (r.phase as number) ?? null,
        root_cause_e_ids: (r.root_cause_e_ids as string[]) ?? [],
        outcomes: out,
      };
    }
  }
  return null;
}

export function useRecommendationDetail(
  recommendationId: string | null,
  displayId: string | null = null,
): UseQueryResult<RecommendationDetail> {
  return useQuery({
    queryKey: ["recommendation", recommendationId, displayId],
    queryFn: async () => {
      try {
        // Live API first — REC-NN display codes carry the ?display_id=
        // scope (drilldown-load fix); UUIDs hit the bare detail path.
        return await apiGet<RecommendationDetail>(
          recommendationDetailPath(recommendationId as string, displayId),
        );
      } catch (err) {
        // Pack-first fallback (deploy review): compose from the client's
        // baked roadmap snapshot when the live API can't resolve the rec.
        const snap = await recFromSnapshot(String(recommendationId), displayId);
        if (snap) return snap;
        throw err;
      }
    },
    enabled: recommendationId !== null,
    staleTime: 60 * 1000,
  });
}
