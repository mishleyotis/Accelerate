import { afterEach, describe, expect, it, vi } from "vitest";

import { apiOrSnapshot, pageSnapshot, snapshotOrApi } from "../startup-pages";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("deploy per-page snapshot fallback", () => {
  it("returns the live API result when it succeeds (no snapshot fetch)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const out = await apiOrSnapshot(
      () => Promise.resolve({ source: "api", pillar_scores: [1, 2, 3, 4] }),
      "amarillo-national-bank-0001",
      "overview",
    );
    expect(out).toEqual({ source: "api", pillar_scores: [1, 2, 3, 4] });
    expect(fetchSpy).not.toHaveBeenCalled(); // API won → no static fallback hit
  });

  it("falls back to the committed snapshot when the API throws", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ source: "snapshot", pillar_scores: [3] }), { status: 200 }),
    );
    const out = await apiOrSnapshot<{ source: string }>(
      () => Promise.reject(new Error("ECONNREFUSED")),
      "amarillo-national-bank-0001",
      "overview",
    );
    expect(out.source).toBe("snapshot");
  });

  it("re-throws the API error when no snapshot exists (404)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));
    await expect(
      apiOrSnapshot(() => Promise.reject(new Error("boom")), "x-0001", "overview"),
    ).rejects.toThrow("boom");
  });

  it("snapshotOrApi serves the committed pack FIRST (junk API can't override the 94)", async () => {
    // The committed snapshot exists → it wins; the live API getter is never called.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ source: "snapshot", name: "Langley FCU" }), { status: 200 }),
    );
    const apiGetter = vi.fn(() =>
      Promise.resolve({ source: "api", name: "VNO DMA Engagement FINAL" }),
    );
    const out = await snapshotOrApi<{ source: string }>(
      apiGetter, "langley-federal-credit-union-0001", "overview",
    );
    expect(out.source).toBe("snapshot");
    expect(apiGetter).not.toHaveBeenCalled(); // pack is authoritative
  });

  it("snapshotOrApi falls through to the live API only when no snapshot exists (new client)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));
    const out = await snapshotOrApi<{ source: string }>(
      () => Promise.resolve({ source: "api" }), "brand-new-client-0001", "overview",
    );
    expect(out.source).toBe("api"); // no pack page → live API
  });

  it("pageSnapshot requests the correct deploy path and is null-safe", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await pageSnapshot("frost-bank-0001", "heatmap");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/startup-data/clients/frost-bank-0001/heatmap.json",
      expect.objectContaining({ cache: "force-cache" }),
    );
    expect(await pageSnapshot(null, "overview")).toBeNull();
  });
});
