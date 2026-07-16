/**
 * Regression: SSE must dispatch `dma:auth-expired` on a 401 response
 * and STOP reconnecting (QA-M7).
 *
 * Pre-fix, the SSE client retried indefinitely on every non-ok
 * status. A 401 mid-stream meant the AE's JWT had expired but the
 * page-mounted SSE subscriber would happily keep reconnecting every
 * 1s -> 30s without ever surfacing the auth-expired event the rest
 * of the app uses to prompt re-login. The AE would see a silent
 * stream with no chat messages and no obvious cause.
 *
 * The fix:
 *   if (res.status === 401) {
 *     closed = true;
 *     window.dispatchEvent(new CustomEvent("dma:auth-expired"));
 *     return;
 *   }
 *
 * This test mocks fetch to return 401, calls subscribeSSE, and
 * asserts the auth-expired event fires AND no reconnect attempt
 * follows.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { subscribeSSE } from "../sse";


afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});


describe("subscribeSSE auth-expired on 401 (QA-M7)", () => {
  it("dispatches dma:auth-expired and stops reconnecting on 401",
    async () => {
      // Spy on window's CustomEvent dispatch
      const events: string[] = [];
      window.addEventListener(
        "dma:auth-expired",
        () => events.push("auth-expired"),
      );

      let fetchCallCount = 0;
      globalThis.fetch = vi.fn(async () => {
        fetchCallCount += 1;
        return new Response("Unauthorized", { status: 401 });
      }) as typeof fetch;

      const sub = subscribeSSE("/api/v1/rag/answer/stream", {
        message: () => undefined,
      });
      // Let the initial connect() promise settle.
      await new Promise((resolve) => setTimeout(resolve, 50));

      expect(events).toEqual(["auth-expired"]);
      expect(fetchCallCount).toBe(1);
      expect(sub.isOpen()).toBe(false);
    });

  it("STILL reconnects on a non-401 server error (e.g. 503)",
    async () => {
      // Defence: only 401 closes -- a transient 503 should still
      // trigger reconnect (existing behaviour preserved).
      let fetchCallCount = 0;
      globalThis.fetch = vi.fn(async () => {
        fetchCallCount += 1;
        // Reject with a 503 so the reconnect path activates.
        return new Response("temp", { status: 503 });
      }) as typeof fetch;

      vi.useFakeTimers();
      const sub = subscribeSSE("/api/v1/rag/answer/stream", {
        message: () => undefined,
      });
      // First fetch runs immediately; subsequent ones are gated by
      // setTimeout(reconnectDelay).
      await vi.advanceTimersByTimeAsync(50);
      expect(fetchCallCount).toBe(1);

      // Wait > 1s for the first reconnect.
      await vi.advanceTimersByTimeAsync(1100);
      expect(fetchCallCount).toBeGreaterThanOrEqual(2);

      sub.close();
    });
});
