/**
 * Build-time startup-data — the dashboard's first-paint payload.
 *
 * `apps/dma-insights/startup-data/dashboard.json` is a committed, read-only
 * snapshot of the seeded database produced through the SAME API SQL the live
 * endpoints serve (see backend `app/scripts/export_startup_data.py`). Bundling
 * it at build time means the dashboard paints real numbers + cards on a COLD
 * load — no empty/stale flash, no fetch race — and the live API immediately
 * replaces it on the first refetch (the hooks set `initialDataUpdatedAt: 0`).
 *
 * The import path resolves identically in dev (sibling of `frontend/`) and in
 * the Docker build (startup-data is COPY'd to `/app/startup-data`). The build
 * FAILS LOUDLY if the snapshot is missing — that is intentional: a deploy must
 * never ship a frontend without its first-paint data.
 */
import type { DashboardResponse, EntityListResponse, EntitySummary } from "./queries";

// eslint-disable-next-line @typescript-eslint/consistent-type-imports
import snapshot from "../../../startup-data/dashboard.json";

interface StartupSnapshot {
  generated_at: string;
  source_sha: string;
  dashboard: DashboardResponse;
  entity_cards: EntitySummary[];
}

const snap = snapshot as unknown as StartupSnapshot;

/** The committed /dashboard response (scope=all). */
export const STARTUP_DASHBOARD: DashboardResponse = snap.dashboard;

/** The committed /entities cards (owner=all, no filters) as a list response. */
export const STARTUP_ENTITIES: EntityListResponse = {
  items: snap.entity_cards,
  total: snap.entity_cards.length,
  owner_filter: "all",
};

/** SHA of the commit the snapshot was generated from (QA / debugging). */
export const STARTUP_SOURCE_SHA: string = snap.source_sha;
