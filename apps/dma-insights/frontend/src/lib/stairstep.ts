/**
 * Stairstep typed hook + types.
 *
 * State-branch contract:
 *   - displayId null            → query disabled, no fetch
 *   - empty_state="no-gaps"     → entity has no scored subcaps yet
 *   - empty_state="no-recs"     → no recommendations to apply
 *   - empty_state="no-applicable-uplift"
 *                               → every pillar already at/above target
 *   - empty_state=null + steps  → happy path
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "./api";

export interface StairStepOut {
  rec_id: string;
  title: string;
  pillar: string;
  score_before: number;
  score_after: number;
  uplift: number;
}

export interface StairstepResponse {
  entity_display_id: string;
  run_request_id: string | null;
  steps_by_pillar: Record<string, StairStepOut[]>;
  current_by_pillar: Record<string, number>;
  end_score_by_pillar: Record<string, number>;
  target_band_score: number;
  empty_state: "no-gaps" | "no-recs" | "no-applicable-uplift" | null;
}

export function useStairstep(
  displayId: string | null,
): UseQueryResult<StairstepResponse> {
  return useQuery({
    queryKey: ["stairstep", displayId],
    queryFn: () => apiGet<StairstepResponse>(`/api/v1/entities/${displayId}/stairstep`),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}
