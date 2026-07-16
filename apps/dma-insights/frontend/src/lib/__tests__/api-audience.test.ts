/**
 * Regression tests for the 2026-06-05 QA audit findings:
 *
 *   Finding 1 — React API client must propagate `view=customer` to every
 *   GET when the UI is in customer audience. Pre-fix the customer toggle
 *   was UI-only; the backend audience-strip never fired against responses
 *   the React tree cached, leaking peer_median / firmographics fields.
 *
 *   Finding 2 — auth/admin endpoints must NOT be audience-tagged (they
 *   exchange JWTs / drive admin tools; audience is meaningless there).
 *
 * We exercise the actual `api()` function via a mocked `fetch` + a
 * localStorage shim, observing the URL that lands at fetch().
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, apiGet, currentAudience } from "../api";
import { AUDIENCE_KEY, writeAudience } from "../audience";

function mockFetchOnce(jsonBody: unknown) {
  const calls: string[] = [];
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
    calls.push(typeof url === "string" ? url : url.toString());
    return new Response(JSON.stringify(jsonBody), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

afterEach(() => {
  localStorage.removeItem(AUDIENCE_KEY);
  vi.restoreAllMocks();
});

describe("Audience propagation in api()", () => {
  it("appends view=customer when audience is customer", async () => {
    writeAudience("customer");
    expect(currentAudience()).toBe("customer");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/entities/abc/overview");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("view=customer");
  });

  it("does NOT append view=customer when audience is internal", async () => {
    writeAudience("internal");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/entities/abc/overview");
    expect(calls).toHaveLength(1);
    expect(calls[0]).not.toContain("view=customer");
  });

  it("respects caller-provided view (does not override)", async () => {
    writeAudience("customer");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/entities/abc/overview", { view: "internal" });
    expect(calls[0]).toContain("view=internal");
    expect(calls[0]).not.toContain("view=customer");
  });

  it("SKIPS audience injection for /api/v1/auth/* endpoints", async () => {
    writeAudience("customer");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/auth/me");
    expect(calls[0]).not.toContain("view=");
  });

  it("SKIPS audience injection for /api/v1/admin/* endpoints", async () => {
    writeAudience("customer");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/admin/users");
    expect(calls[0]).not.toContain("view=");
  });

  it("honours explicit skipAudience option", async () => {
    writeAudience("customer");
    const calls = mockFetchOnce({ ok: true });
    await api("/api/v1/entities/abc/overview", {
      method: "GET",
      skipAudience: true,
    });
    expect(calls[0]).not.toContain("view=");
  });

  it("preserves existing query params alongside view=customer", async () => {
    writeAudience("customer");
    const calls = mockFetchOnce({ ok: true });
    await apiGet("/api/v1/entities/abc/heatmap", {
      zoom: "subcap",
      peer: "true",
    });
    expect(calls[0]).toContain("zoom=subcap");
    expect(calls[0]).toContain("peer=true");
    expect(calls[0]).toContain("view=customer");
  });
});
