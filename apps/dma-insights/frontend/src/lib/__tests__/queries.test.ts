/**
 * Queries module — verifies the hook factory builds the right cache keys
 * and URLs. We don't exercise real fetch here; the API client is tested
 * separately. Hook execution is covered by integration tests against a
 * dev backend.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  exportScorecard,
  useAlerts,
  useDashboard,
  useEntities,
  useEntityContext,
  useEntityHealth,
  useEntityHeatmap,
  useEntityOverview,
  useFocusAreaKpis,
  useInsightAnnotations,
  useMarkNotificationsRead,
  useNotifications,
  useSaveAnnotation,
  useSaveKpiOverrides,
} from "../queries";

// Smoke-test: the module compiles and exports the expected functions.
describe("queries module shape", () => {
  it("exports the documented hooks", () => {
    expect(typeof useDashboard).toBe("function");
    expect(typeof useEntities).toBe("function");
    expect(typeof useEntityOverview).toBe("function");
    expect(typeof useEntityHeatmap).toBe("function");
    expect(typeof useAlerts).toBe("function");
  });

  it("exports the 2026-06 rebuild hooks (Context/Health + write surfaces)", () => {
    for (const fn of [
      useEntityContext,
      useEntityHealth,
      useInsightAnnotations,
      useSaveAnnotation,
      useFocusAreaKpis,
      useSaveKpiOverrides,
      useNotifications,
      useMarkNotificationsRead,
    ]) {
      expect(typeof fn).toBe("function");
    }
  });
});

describe("exportScorecard (B-6)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs the export endpoint with the requested format and returns a blob URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["<html></html>"], { type: "text/html" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:fake"),
    } as unknown as typeof URL);

    const out = await exportScorecard("prov-001", "html");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/prospecting/prov-001/export?format=html",
      expect.objectContaining({ method: "POST" }),
    );
    expect(out.filename).toBe("dma-scorecard-prov-001.html");
    expect(out.url).toBe("blob:fake");
  });

  it("maps a 501 (PDF extra not installed) to a friendly error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 501,
      text: async () => "weasyprint missing",
    }));
    await expect(exportScorecard("prov-001", "pdf")).rejects.toThrow(
      /PDF export isn't enabled/,
    );
  });

  it("surfaces other failures with status + detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => "entity not found",
    }));
    await expect(exportScorecard("nope", "html")).rejects.toThrow(/404/);
  });
});
