/**
 * App entrypoint — Vite reads `index.html`, which loads this module.
 *
 * Responsibilities:
 *   - QueryClient with persistQueryClient → IndexedDB
 *   - Root render of <App/>
 *
 * `App` itself is a deliberately small shell during Stage 3. Stage 4 ports
 * the prototype's chrome (Sidebar / TopBar / NotifPopover / SearchPalette);
 * Stages 6-12 fill in each route's page.
 */
import "../styles/tokens.css";
import "../styles/app.css";
// React-tree page styles. The production React pages (ADR 0016) use a
// different, more semantic class vocabulary than the prototype's app.css
// (.page-body vs .page, .pillar-bar vs .pbar, .tile vs .stat, …). This
// sheet supplies the matching rules so the React surface renders with
// visual parity to the standalone wireframe contract. See the file header.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import * as idb from "idb-keyval";

import { App } from "./App";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 24 * 60 * 60 * 1000,
      retry: (failureCount, error) => {
        // Never retry ANY 4xx — the request is deterministically
        // rejected (401 expired, 403 role/audience-gated, 404 missing,
        // 422 invalid); retrying only stretches the loading state
        // (2026-06-10: customer-audience toggle on a gated page).
        if (
          error &&
          typeof error === "object" &&
          "status" in error &&
          (error as { status: number }).status >= 400 &&
          (error as { status: number }).status < 500
        ) {
          return false;
        }
        return failureCount < 2;
      },
    },
  },
});

export const idbStore = idb.createStore("dma-insights-query-cache", "store");
const persister = createAsyncStoragePersister({
  storage: {
    getItem: async (key) => (await idb.get(key, idbStore)) ?? null,
    setItem: async (key, val) => idb.set(key, val, idbStore),
    removeItem: async (key) => idb.del(key, idbStore),
  },
});

const rootEl = document.getElementById("app");
if (!rootEl) throw new Error("Root element #app missing in index.html");

createRoot(rootEl).render(
  <StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: 24 * 60 * 60 * 1000,
        buster: import.meta.env.VITE_CACHE_BUSTER ?? "v1",
      }}
    >
      <App />
    </PersistQueryClientProvider>
  </StrictMode>,
);
