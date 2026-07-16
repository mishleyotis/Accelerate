/**
 * AE notes for a recommendation (prototype Standalone-3 · RecommendationModal
 * "AE notes"). The prototype persists notes to `localStorage` ("saved
 * locally") and flags them for "future synthesis". We keep that instant
 * local UX AND persist durably to the backend so a note survives across
 * sessions and users (operator mandate) and is available to the future
 * Gemini/ML recalibration pass — which is deliberately NOT run here (the
 * recalibration must be a deep impact simulation, never a deterministic stub).
 *
 * Save policy (offline-safe):
 *   - every keystroke writes `localStorage[dma_rec_note_<recId>]` (instant),
 *   - a debounced PUT syncs it to the backend (durable, cross-user),
 *   - on open we prefer the backend value, falling back to localStorage when
 *     the API is unreachable (fail-soft — the note is never lost).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPut } from "./api";

export interface RecommendationNote {
  note: string;
  author_email: string | null;
  updated_at: string | null;
}

const lsKey = (recId: string): string => `dma_rec_note_${recId}`;

export function readLocalNote(recId: string): string {
  try {
    return localStorage.getItem(lsKey(recId)) ?? "";
  } catch {
    return "";
  }
}

export function writeLocalNote(recId: string, note: string): void {
  try {
    if (note) localStorage.setItem(lsKey(recId), note);
    else localStorage.removeItem(lsKey(recId));
  } catch {
    /* localStorage may be unavailable (private mode) — non-fatal */
  }
}

function notePath(displayId: string, recId: string): string {
  return `/api/v1/entities/${encodeURIComponent(displayId)}/recommendations/${encodeURIComponent(recId)}/note`;
}

/** GET the durable note; falls back to the local copy if the API is cold. */
export function useRecommendationNote(
  displayId: string | null | undefined,
  recId: string | null | undefined,
) {
  return useQuery<RecommendationNote>({
    queryKey: ["rec-note", displayId ?? null, recId ?? null],
    queryFn: async () => {
      try {
        return await apiGet<RecommendationNote>(notePath(displayId!, recId!));
      } catch {
        return { note: readLocalNote(recId!), author_email: null, updated_at: null };
      }
    },
    enabled: Boolean(displayId && recId),
    staleTime: 30 * 1000,
  });
}

/** PUT the note (upsert; a blank note clears it). Optimistic + cache-synced. */
export function useSaveRecommendationNote(
  displayId: string | null | undefined,
  recId: string | null | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (note: string): Promise<RecommendationNote> =>
      apiPut<RecommendationNote>(notePath(displayId!, recId!), { note }),
    onSuccess: (data) => {
      qc.setQueryData(["rec-note", displayId ?? null, recId ?? null], data);
    },
  });
}
