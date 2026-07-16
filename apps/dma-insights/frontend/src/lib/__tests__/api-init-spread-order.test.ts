/**
 * Regression: api() must spread caller-provided `init` FIRST and layer
 * framework defaults (credentials, headers, signal) on TOP.
 *
 * Independent QA (2026-06-06) found:
 *   res = await fetch(url, {
 *     credentials: "include",
 *     headers: { "Content-Type": "application/json", ...init.headers },
 *     signal,
 *     ...init,                         // <-- BUG: clobbers headers/signal/credentials
 *   });
 *
 * If a caller passed `headers: { "X-Custom": "foo" }`, the `...init`
 * spread re-wrote `headers` with the un-merged caller object -- the
 * "Content-Type": "application/json" default was lost. Likewise for
 * `signal` (a caller-provided signal would silently disable the timeout
 * abort) and `credentials` (a caller could downgrade auth).
 *
 * The fix flips the order:
 *   res = await fetch(url, {
 *     ...init,                         // first
 *     credentials: "include",
 *     headers: { "Content-Type": "application/json", ...init.headers },
 *     signal,                          // last -- always the timeout signal
 *   });
 *
 * This file pins that contract.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, apiGet } from "../api";
import { AUDIENCE_KEY, writeAudience } from "../audience";


interface RecordedCall {
  url: string;
  init: RequestInit | undefined;
}


function captureFetch(jsonBody: unknown = { ok: true }): RecordedCall[] {
  const calls: RecordedCall[] = [];
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: typeof url === "string" ? url : url.toString(),
      init,
    });
    return new Response(JSON.stringify(jsonBody), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}


function headersToObject(h: HeadersInit | undefined): Record<string, string> {
  if (!h) return {};
  if (h instanceof Headers) {
    const out: Record<string, string> = {};
    h.forEach((v, k) => {
      out[k] = v;
    });
    return out;
  }
  if (Array.isArray(h)) {
    return Object.fromEntries(h);
  }
  return { ...(h as Record<string, string>) };
}


beforeEach(() => {
  writeAudience("internal");  // pin so no audience query string contaminates assertions
});


afterEach(() => {
  localStorage.removeItem(AUDIENCE_KEY);
  vi.restoreAllMocks();
});


describe("api() init-spread order (QA-M8)", () => {
  it("preserves Content-Type=application/json when caller passes other headers",
    async () => {
      const calls = captureFetch();
      await api("/api/v1/something", {
        method: "POST",
        body: JSON.stringify({ x: 1 }),
        headers: { "X-Custom": "foo" },
      } as Parameters<typeof api>[1]);
      expect(calls).toHaveLength(1);
      const h = headersToObject(calls[0].init?.headers);
      // The framework default MUST still be present.
      expect(h["Content-Type"]).toBe("application/json");
      // The caller-provided header MUST be preserved.
      expect(h["X-Custom"]).toBe("foo");
    });

  it("preserves credentials=include even when caller passes init.credentials",
    async () => {
      const calls = captureFetch();
      // Caller passes a downgraded credentials -- shouldn't override.
      await api("/api/v1/something", {
        method: "POST",
        credentials: "omit",
      } as Parameters<typeof api>[1]);
      expect(calls).toHaveLength(1);
      expect(calls[0].init?.credentials).toBe("include");
    });

  it("uses the framework timeout signal even when caller passes init.signal",
    async () => {
      const calls = captureFetch();
      const callerCtrl = new AbortController();
      await api("/api/v1/something", {
        // The api() function destructures `signal` from opts so this
        // wouldn't be in `init`; but a malicious or buggy caller could
        // construct opts with `init.signal` smuggled in. Even in that
        // edge case the framework signal wins.
        method: "POST",
        signal: callerCtrl.signal,
      } as Parameters<typeof api>[1]);
      expect(calls).toHaveLength(1);
      // The fetched signal is the framework signal (timeout) NOT the
      // caller's signal. The framework signal is a fresh AbortSignal
      // created inside api(); we assert it's not the caller's signal.
      expect(calls[0].init?.signal).not.toBe(callerCtrl.signal);
    });

  it("respects caller method + body (does NOT clobber)",
    async () => {
      const calls = captureFetch();
      await api("/api/v1/something", {
        method: "POST",
        body: JSON.stringify({ x: 1 }),
      } as Parameters<typeof api>[1]);
      expect(calls).toHaveLength(1);
      expect(calls[0].init?.method).toBe("POST");
      expect(calls[0].init?.body).toBe(JSON.stringify({ x: 1 }));
    });

  it("regression: apiGet still attaches Content-Type for empty-init GET",
    async () => {
      const calls = captureFetch();
      await apiGet("/api/v1/something");
      expect(calls).toHaveLength(1);
      const h = headersToObject(calls[0].init?.headers);
      expect(h["Content-Type"]).toBe("application/json");
    });
});
