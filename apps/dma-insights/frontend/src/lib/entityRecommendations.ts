/**
 * Entity recommendations index — maps rec_id (human-readable) to the
 * UUID needed by /recommendations/{id}.
 *
 * Used by PlatformPage when StairstepCurve fires `onRecClick(recId)` —
 * we look up the UUID and then open the RecommendationModal.
 *
 * State-branch contract:
 *   - displayId null      → query disabled
 *   - no active run       → backend returns [] → look-ups return null
 *   - happy path          → look-ups resolve to the UUID
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "./api";

export interface RecRow {
  id: string;
  rec_id: string;
  title: string;
  platform_id: string | null;
}

export function useEntityRecommendations(
  displayId: string | null,
): UseQueryResult<RecRow[]> {
  return useQuery({
    queryKey: ["entityRecs", displayId],
    queryFn: () => apiGet<RecRow[]>(
      `/api/v1/entities/${displayId}/recommendations`,
    ),
    enabled: displayId !== null,
    staleTime: 60 * 1000,
  });
}

export function lookupRecUuid(rows: RecRow[] | undefined, recId: string): string | null {
  if (!rows) return null;
  const hit = rows.find((r) => r.rec_id === recId);
  return hit ? hit.id : null;
}
