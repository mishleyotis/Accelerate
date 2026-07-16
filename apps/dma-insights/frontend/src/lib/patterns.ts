/**
 * Pattern-recognition typed hooks — connects the frontend to the new
 * pgvector-backed `/api/v1/patterns/*` endpoints.
 *
 * State-branch contract:
 *   - cohort_match=0          → row scored "distant"; UI greys it out.
 *   - n=0                     → empty state in InsightModal.
 *   - text_similarity < 0.4   → marked "weak match" by the consumer.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "./api";

export interface SimilarInsightOut {
  insight_card_id: string;
  ic_id: string;
  entity_name: string;
  title: string;
  severity: string;
  linked_subcap_id: string;
  cohort_match: number;
  text_similarity: number;
  combined_score: number;
}

export interface SimilarInsightsResponse {
  seed_ic_id: string;
  cohort_mode: "single" | "multi_lob" | "cross_vertical";
  items: SimilarInsightOut[];
}

export interface RecurringSubcapTheme {
  title: string;
  severity: string;
  occurrence_count: number;
  sample_entities: string[];
}

export interface RecurringSubcapResponse {
  subcap_id: string;
  cohort_mode: "single" | "multi_lob" | "cross_vertical";
  themes: RecurringSubcapTheme[];
}

export function useSimilarInsights(
  insightCardId: string | null,
  opts: { topK?: number; crossVertical?: "auto" | "true" | "false" } = {},
): UseQueryResult<SimilarInsightsResponse> {
  return useQuery({
    queryKey: [
      "similarInsights", insightCardId, opts.topK ?? 8, opts.crossVertical ?? "auto",
    ],
    queryFn: () =>
      apiGet<SimilarInsightsResponse>(
        `/api/v1/patterns/insights/${insightCardId}/similar`,
        { top_k: opts.topK ?? 8, cross_vertical: opts.crossVertical ?? "auto" },
      ),
    enabled: insightCardId !== null,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecurringSubcapThemes(
  subcapId: string | null,
  opts: { subvertical?: string; topK?: number } = {},
): UseQueryResult<RecurringSubcapResponse> {
  return useQuery({
    queryKey: [
      "recurringSubcap", subcapId, opts.subvertical ?? "", opts.topK ?? 5,
    ],
    queryFn: () =>
      apiGet<RecurringSubcapResponse>(
        `/api/v1/patterns/subcaps/${subcapId}/recurring`,
        { subvertical: opts.subvertical, top_k: opts.topK ?? 5 },
      ),
    enabled: subcapId !== null,
    staleTime: 5 * 60 * 1000,
  });
}
