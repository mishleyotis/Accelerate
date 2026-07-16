/**
 * Drift typed hook — fetches `/api/v1/patterns/entities/{id}/drift`.
 *
 * State-branch contract:
 *   - displayId null              → query disabled
 *   - data.pillar_drifts contains rows with drift_score=null when the
 *     pillar has no eligible subcaps (all were skipped as
 *     cohort_insufficient or entity_missing)
 *   - data.overall_drift = null   → no pillar had any drift signal
 *   - data.overall_drift > 0      → entity is above cohort
 *   - data.overall_drift < 0      → entity is below cohort
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "./api";

export type DriftBucket =
  | "critical_low" | "below" | "nominal" | "above" | "critical_high"
  | "cohort_insufficient" | "entity_missing";

export interface PillarDriftOut {
  pillar: string;
  drift_score: number | null;
  subcap_count: number;
  by_bucket: Record<string, number>;
}

export interface DriftReportOut {
  entity_display_id: string;
  cohort_insufficient_count: number;
  entity_missing_count: number;
  overall_drift: number | null;
  pillar_drifts: PillarDriftOut[];
  subcap_drifts: Array<{
    subcap_id: string;
    pillar: string;
    bucket: DriftBucket;
    drift_score: number | null;
    entity_score: number | null;
    peer_median: number | null;
    peer_n: number;
  }>;
}

export function useDrift(displayId: string | null): UseQueryResult<DriftReportOut> {
  return useQuery({
    queryKey: ["entityDrift", displayId],
    queryFn: () => apiGet<DriftReportOut>(
      `/api/v1/patterns/entities/${displayId}/drift`,
    ),
    enabled: displayId !== null,
    staleTime: 5 * 60 * 1000,
  });
}
