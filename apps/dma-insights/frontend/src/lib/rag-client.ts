/**
 * RAG read API client — for internal IntelligencePanel calls.
 *
 * The Claude project calls our RAG endpoints with the Bearer key from
 * Secret Manager; this client is used by internal panels and reuses the
 * session cookie. Cohort scoping is auto-derived server-side; the optional
 * `crossVertical` parameter forces a mode.
 */
import { apiGet } from "./api";

export type CohortMode = "single" | "multi_lob" | "cross_vertical";

export interface RagEvidence {
  e_id: string;
  entity_name: string;
  subcap_id: string;
  source_name: string;
  excerpt: string;
  tier: number;
  claim_type: string;
  published_date: string | null;
  source_url: string | null;
  cohort_match: number;
}

export interface RagEvidenceResponse {
  cohort_mode: CohortMode;
  n: number;
  insufficient_cohort: boolean;
  items: RagEvidence[];
}

export async function ragEvidence(params: {
  subcapId: string;
  subvertical?: string;
  lobs?: string[];
  crossVertical?: "auto" | "true" | "false";
  minTier?: number;
  maxAgeMonths?: number;
  topK?: number;
}): Promise<RagEvidenceResponse> {
  return apiGet<RagEvidenceResponse>("/api/v1/rag/evidence", {
    subcap_id: params.subcapId,
    subvertical: params.subvertical,
    lobs: params.lobs?.join(","),
    cross_vertical: params.crossVertical ?? "auto",
    min_tier: params.minTier ?? 1,
    max_age_months: params.maxAgeMonths ?? 24,
    top_k: params.topK ?? 20,
  });
}

export interface RagPeerBand {
  insufficient_cohort?: boolean;
  n: number;
  median: number | null;
  p25?: number | null;
  p75?: number | null;
  fallback?: string;
  n_xv?: number;
}

export async function ragPeerBand(
  subvertical: string,
  subcapId: string,
): Promise<RagPeerBand> {
  return apiGet<RagPeerBand>("/api/v1/rag/peer_band", {
    subvertical,
    subcap_id: subcapId,
  });
}
