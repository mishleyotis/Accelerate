/**
 * Part 9.2 — TechStack detail pack fallback. No per-tech snapshot exists
 * in the committed startup pack, so `fetchTechStackDetail` serves the
 * live API first and, when it is cold, hydrates the detail from the
 * already-snapshotted techstack LIST row (`/startup-data/clients/{id}/
 * techstack.json`). When neither carries the tech, the original API
 * error propagates (honest "Technology not found").
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiPut: vi.fn(),
  apiBlob: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiGet } from "@/lib/api";
import { fetchTechStackDetail } from "@/lib/queries";
import type { TechStackDetailResponse, TechStackEntryOut } from "@/lib/queries";

const row: TechStackEntryOut = {
  id: "absent-ncino", tech_id: "absent-ncino", vendor: "nCino",
  product: "nCino platform family", product_name: "nCino platform family",
  layer: "application", status: "ABSENT", l3_id: "ncino",
  source: "derived:gap_analysis", evidence_e_ids: [],
  linked_subcap_ids: ["P2C2.1.1"], detected_at: null,
  peer_coverage: 0.6, primary_gap: true,
};

const g = globalThis as { fetch?: typeof fetch };
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => ({ entity_display_id: "alma-0001", items: [row], last_synced_at: null }),
  }));
  g.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => { vi.restoreAllMocks(); });

describe("fetchTechStackDetail", () => {
  it("serves the live API when warm (no snapshot read)", async () => {
    const apiDetail = { entry: row, linked_subcap_ids: ["P2C2.1.1"], evidence_e_ids: [], peer_adoption_count: 3 } as TechStackDetailResponse;
    (apiGet as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(apiDetail);
    const got = await fetchTechStackDetail("alma-0001", "absent-ncino");
    expect(got).toBe(apiDetail);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("hydrates from the techstack LIST snapshot row when the API is cold", async () => {
    (apiGet as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("backend cold"));
    const got = await fetchTechStackDetail("alma-0001", "absent-ncino");
    expect(fetchMock).toHaveBeenCalledWith(
      "/startup-data/clients/alma-0001/techstack.json",
      expect.objectContaining({ cache: "force-cache" }),
    );
    expect(got.entry.tech_id).toBe("absent-ncino");
    expect(got.peer_coverage).toBe(0.6);
    // cohort extras are not fabricated by the fallback
    expect(got.peer_names).toEqual([]);
    expect(got.gap_zones).toEqual([]);
  });

  it("re-throws the API error when the snapshot doesn't carry the tech either", async () => {
    (apiGet as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("backend cold"));
    await expect(fetchTechStackDetail("alma-0001", "unknown-tech"))
      .rejects.toThrow("backend cold");
  });
});
