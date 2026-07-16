/**
 * AE notes on rec cards / roadmap items (migration 057) — typed hooks.
 *
 * State-branch contract:
 *   - displayId/targetId null → queries disabled
 *   - 403 (CUSTOMER)          → panel renders nothing (internal surface)
 *   - note.recalibrate        → `assessment_status` chip; the assessment
 *                               endpoint 404s until a simulation ran
 *   - assessment.validators_passed=false → assessment_md/impact are null
 *                               (fail-closed: unvalidated Gemini output
 *                               never reaches an AE)
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { apiGet, apiPost } from "./api";

export type NoteTargetKind = "recommendation" | "roadmap_phase" | "insight_card";
export type NoteStatus = "ACTIONED" | "PENDING" | "SUPERSEDED";

export interface AeNote {
  id: string;
  target_kind: NoteTargetKind;
  target_id: string;
  author_email: string;
  author_role: string;
  status: NoteStatus;
  body: string;
  sf_opp_id: string | null;
  recalibrate: boolean;
  created_at: string;
  assessment_status: string | null;
}

export interface NoteListResponse {
  entity_display_id: string;
  items: AeNote[];
}

export interface NoteAssessment {
  id: string;
  note_id: string;
  status: "PENDING" | "SIMULATED" | "FAILED" | "REVIEWED";
  assessment_md: string | null;
  impact: Record<string, unknown> | null;
  model: string | null;
  grounding_evidence_ids: string[];
  validators_passed: boolean;
  failure_reason: string | null;
  created_at: string;
}

export interface CreateNoteInput {
  target_kind: NoteTargetKind;
  target_id: string;
  body: string;
  status?: NoteStatus;
  sf_opp_id?: string | null;
  recalibrate?: boolean;
}

export function useEntityNotes(
  displayId: string | null,
  targetKind: NoteTargetKind | null,
  targetId: string | null,
): UseQueryResult<NoteListResponse> {
  return useQuery({
    queryKey: ["aeNotes", displayId, targetKind, targetId],
    queryFn: () =>
      apiGet<NoteListResponse>(`/api/v1/entities/${displayId}/notes`, {
        target_kind: targetKind ?? undefined,
        target_id: targetId ?? undefined,
      }),
    enabled: displayId !== null && targetId !== null,
    staleTime: 30 * 1000,
  });
}

export function useCreateNote(
  displayId: string | null,
): UseMutationResult<AeNote, Error, CreateNoteInput> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input) =>
      apiPost<AeNote>(`/api/v1/entities/${displayId}/notes`, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["aeNotes", displayId] });
    },
  });
}

export function useNoteAssessment(
  noteId: string | null,
): UseQueryResult<NoteAssessment> {
  return useQuery({
    queryKey: ["noteAssessment", noteId],
    queryFn: () => apiGet<NoteAssessment>(`/api/v1/notes/${noteId}/assessment`),
    enabled: noteId !== null,
    staleTime: 30 * 1000,
    retry: false, // 404 = no simulation yet; don't hammer
  });
}

/** Initials for the note author avatar — "mishley.otiende@zennify.com"
 *  → "MO". Pure; exported for tests. */
export function authorInitials(email: string): string {
  const local = (email || "").split("@")[0] ?? "";
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
