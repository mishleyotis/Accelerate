/**
 * Regression tests for the 2026-06-10 customer-toggle hang.
 *
 * `setAudience("customer")` used to call `clearClientSessionCache()` —
 * `queryClient.clear()` plus a FULL IndexedDB wipe — which raced the
 * PersistQueryClientProvider restore/persist cycle and left the page in
 * a never-resolving loading state on the live app. The fix drops cached
 * query DATA via `queryClient.resetQueries()` (same security property:
 * internal-stripped fields can't render in customer mode because the
 * data is gone and active observers REFETCH with `?view=customer` —
 * removeQueries/clear leave observed queries pending forever) WITHOUT
 * clearing the persister store or resetting the client.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the entry module BEFORE importing the store so the dynamic
// `import("../entry")` inside setAudience resolves to our spies (and
// never boots the real React tree / IndexedDB persister).
const resetQueries = vi.fn();
const clear = vi.fn();
vi.mock("../../entry", () => ({
  queryClient: { resetQueries, clear },
  idbStore: {},
}));

import { useUiStore } from "../ui";

async function flushMicrotasks() {
  await new Promise((r) => setTimeout(r, 0));
}

beforeEach(() => {
  resetQueries.mockClear();
  clear.mockClear();
  useUiStore.setState({ audience: "internal" });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("setAudience cache policy (2026-06-10 hang fix)", () => {
  it("drops + refetches query data via resetQueries when entering customer mode", async () => {
    useUiStore.getState().setAudience("customer");
    await flushMicrotasks();
    expect(resetQueries).toHaveBeenCalledTimes(1);
  });

  it("NEVER calls queryClient.clear() (the full reset that hung the page)", async () => {
    useUiStore.getState().setAudience("customer");
    await flushMicrotasks();
    expect(clear).not.toHaveBeenCalled();
  });

  it("widening customer -> internal does not wipe anything", async () => {
    useUiStore.setState({ audience: "customer" });
    useUiStore.getState().setAudience("internal");
    await flushMicrotasks();
    expect(resetQueries).not.toHaveBeenCalled();
    expect(clear).not.toHaveBeenCalled();
  });

  it("no-op customer -> customer does not wipe", async () => {
    useUiStore.setState({ audience: "customer" });
    useUiStore.getState().setAudience("customer");
    await flushMicrotasks();
    expect(resetQueries).not.toHaveBeenCalled();
  });
});
