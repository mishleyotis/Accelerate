/**
 * Runs page "Trigger rerun" — must fire the real useRequestNewRun mutation
 * (POST /api/v1/runs/new) with the parent run, NOT a bare success toast (the
 * 2026-06-23 states audit found it was a toast-only stub).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import * as hashRouter from "@/lib/hash-router";
import * as queries from "@/lib/queries";
import { ClientRunsPage } from "@/pages/ClientRunsPage";

vi.mock("@tanstack/react-query", async (orig) => ({
  ...(await orig<typeof import("@tanstack/react-query")>()),
  useQuery: vi.fn(),
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mount(mutateAsync = vi.fn().mockResolvedValue({ request_id: "REQ-NEW", eta_minutes: 3 })) {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-0001/runs", query: {}, navigate: vi.fn(), setQuery: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  vi.spyOn(queries, "useEntityOverview").mockReturnValue({
    data: { entity: { name: "Alma Bank" } },
  } as unknown as ReturnType<typeof queries.useEntityOverview>);
  vi.spyOn(queries, "useRequestNewRun").mockReturnValue({
    mutateAsync, isPending: false,
  } as unknown as ReturnType<typeof queries.useRequestNewRun>);
  (useQuery as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { items: [{
      request_id: "REQ-PARENT", status: "ACTIVE", data_source: "DRIVE_PARSE",
      evidence_mode: null, overall_score: 3.2, subcaps_scored: 100,
      started_at: "2026-06-01T00:00:00Z", completed_at: "2026-06-01T00:00:00Z",
    }] },
    isLoading: false, error: null,
  });
  return mutateAsync;
}

describe("Runs page · Trigger rerun", () => {
  it("fires the real rerun mutation with the parent request_id", async () => {
    const mutateAsync = mount();
    render(<ClientRunsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Trigger rerun/ }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ is_rerun: true, parent_request_id: "REQ-PARENT" }),
    );
  });

  it("disables the button while a request is pending", () => {
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: "/clients/alma-0001/runs", query: {}, navigate: vi.fn(), setQuery: vi.fn(),
    } as unknown as ReturnType<typeof hashRouter.useRoute>);
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: { entity: { name: "Alma Bank" } },
    } as unknown as ReturnType<typeof queries.useEntityOverview>);
    vi.spyOn(queries, "useRequestNewRun").mockReturnValue({
      mutateAsync: vi.fn(), isPending: true,
    } as unknown as ReturnType<typeof queries.useRequestNewRun>);
    (useQuery as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { items: [{
        request_id: "REQ-PARENT", status: "ACTIVE", data_source: "DRIVE_PARSE",
        evidence_mode: null, overall_score: 3.2, subcaps_scored: 100,
        started_at: "2026-06-01T00:00:00Z", completed_at: "2026-06-01T00:00:00Z",
      }] },
      isLoading: false, error: null,
    });
    render(<ClientRunsPage />);
    expect(screen.getByRole("button", { name: /Requesting/ })).toHaveProperty("disabled", true);
  });
});
